"""
[EXPERIMENTAL] Cliente de integración con Google Drive API v3 para dHtools.
Soporta autenticación por Service Account y OAuth 2.0, streaming resumable
en bloques de 10 MB para no saturar memoria RAM y compatibilidad con Shared Drives.
"""

import os
import gc
import json
import logging
import mimetypes
from typing import Tuple, Dict, Any, Optional, Callable

logger = logging.getLogger("dhtools.plugins.google_drive.client")

# Scopes requeridos para Drive
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]


def check_dependencies() -> Tuple[bool, str]:
    """Verifica si las dependencias de Google API están instaladas."""
    try:
        import googleapiclient.discovery
        import google.oauth2.service_account
        return True, "Dependencias instaladas correctamente"
    except ImportError as e:
        return False, (
            "Faltan dependencias de Google API. "
            "Instálelas ejecutando: pip install google-api-python-client google-auth google-auth-oauthlib"
        )


def sanitize_folder_id(raw_id: str) -> str:
    """Extrae el ID alfanumérico limpio de Google Drive si viene con URL o parámetros ?hl=es."""
    if not raw_id:
        return ""
    val = raw_id.strip()
    if "?" in val:
        val = val.split("?")[0]
    if "/folders/" in val:
        val = val.split("/folders/")[-1]
    return val.strip().strip("/")


def _resolve_path(path_str: str, base_dir: Optional[str] = None) -> str:
    """Resuelve rutas relativas contra el directorio del plugin."""
    if not path_str:
        return ""
    if os.path.isabs(path_str):
        return path_str
    if base_dir:
        return os.path.join(base_dir, path_str)
    return path_str


def get_drive_service(config: Dict[str, Any], base_dir: Optional[str] = None):
    """
    Construye y retorna el cliente de servicio googleapiclient para Google Drive v3.
    """
    ok, err = check_dependencies()
    if not ok:
        raise RuntimeError(err)

    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    auth_type = config.get("auth_type", "service_account")

    if auth_type == "service_account":
        sa_file = _resolve_path(config.get("service_account_file", "service_account.json"), base_dir)
        sa_content = config.get("service_account_json_content")

        if sa_content and isinstance(sa_content, (dict, str)):
            if isinstance(sa_content, str):
                try:
                    sa_info = json.loads(sa_content)
                except Exception as e:
                    raise ValueError(f"El contenido JSON de Service Account es inválido: {e}")
            else:
                sa_info = sa_content
            creds = service_account.Credentials.from_service_account_info(sa_info, scopes=DRIVE_SCOPES)
        elif sa_file and os.path.exists(sa_file):
            creds = service_account.Credentials.from_service_account_file(sa_file, scopes=DRIVE_SCOPES)
        else:
            raise FileNotFoundError(
                f"No se encontró el archivo de Service Account ('{sa_file}'). "
                f"Súbalo en /plugin/google_drive/settings o verifique la ruta."
            )

        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service

    elif auth_type == "oauth2":
        oauth_cfg = config.get("oauth", {})
        token_file = _resolve_path(oauth_cfg.get("token_file", "token.json"), base_dir)
        creds = None

        # Soporte para token provisto en caliente vía config (pruebas o contenido pegado)
        token_content = config.get("oauth_token_json_content")
        if token_content and isinstance(token_content, (dict, str)):
            if isinstance(token_content, str):
                try:
                    t_info = json.loads(token_content)
                except Exception as e:
                    raise ValueError(f"El contenido JSON del token OAuth2 es inválido: {e}")
            else:
                t_info = token_content

            if isinstance(t_info, dict):
                if "access_token" in t_info and "token" not in t_info:
                    t_info["token"] = t_info["access_token"]
                if "token_uri" not in t_info:
                    t_info["token_uri"] = "https://oauth2.googleapis.com/token"
                try:
                    creds = Credentials.from_authorized_user_info(t_info, scopes=DRIVE_SCOPES)
                except Exception as e:
                    logger.warning(f"Error cargando credenciales OAuth2 desde info: {e}")

        elif os.path.exists(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    t_info = json.load(f)
                if isinstance(t_info, dict):
                    if "web" in t_info or "installed" in t_info:
                        raise ValueError(
                            "El archivo token.json contiene las credenciales de la app (client_secret.json) en lugar del token del usuario. "
                            "Por favor haga clic en 'Conectar con Google' en /plugin/google_drive/settings para autorizar el acceso."
                        )
                    if "access_token" in t_info and "token" not in t_info:
                        t_info["token"] = t_info["access_token"]
                    if "token_uri" not in t_info:
                        t_info["token_uri"] = "https://oauth2.googleapis.com/token"
                    creds = Credentials.from_authorized_user_info(t_info, scopes=DRIVE_SCOPES)
            except ValueError:
                raise
            except Exception as e:
                logger.warning(f"Error cargando token OAuth2: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_file, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            else:
                raise RuntimeError(
                    "Credenciales OAuth2 no encontradas o expiradas. "
                    "Por favor complete la autorización en /plugin/google_drive/settings"
                )

        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service

    else:
        raise ValueError(f"Tipo de autenticación desconocido: '{auth_type}'")


def test_connection(config: Dict[str, Any], base_dir: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Prueba la conexión con Google Drive, devuelve información de cuota y valida la carpeta.
    """
    try:
        service = get_drive_service(config, base_dir)
        
        # 1. Obtener información de usuario y cuota
        about = service.about().get(fields="user,storageQuota").execute()
        user_info = about.get("user", {})
        quota = about.get("storageQuota", {})

        clean_folder = sanitize_folder_id(config.get("folder_id", ""))

        result = {
            "status": "success",
            "user_name": user_info.get("displayName", "Desconocido"),
            "email": user_info.get("emailAddress", "N/A"),
            "storage_used_bytes": int(quota.get("usage", 0)),
            "storage_total_bytes": int(quota.get("limit", 0)) if quota.get("limit") else None,
            "folder_id": clean_folder,
            "folder_name": "Raíz de Mi Unidad"
        }

        # 2. Validar carpeta destino si fue provista
        folder_id = clean_folder
        if folder_id and folder_id.lower() != "root":
            try:
                f_meta = service.files().get(
                    fileId=folder_id,
                    fields="id,name,mimeType,capabilities",
                    supportsAllDrives=True
                ).execute()
                result["folder_name"] = f_meta.get("name", folder_id)
                can_add = f_meta.get("capabilities", {}).get("canAddChildren", True)
                if not can_add:
                    return False, {
                        "status": "error",
                        "error": f"La cuenta no tiene permisos para subir archivos en la carpeta '{result['folder_name']}'."
                    }
            except Exception as fe:
                return False, {
                    "status": "error",
                    "error": f"No se pudo acceder a la carpeta destino ('{folder_id}'): {fe}"
                }

        return True, result

    except Exception as e:
        logger.error(f"Error al verificar conexión Google Drive: {e}")
        return False, {"status": "error", "error": str(e)}


def upload_file_resumable(
    filepath: str,
    filename: str,
    config: Dict[str, Any],
    base_dir: Optional[str] = None,
    owner: str = "admin",
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Sube un archivo a Google Drive en fragmentos de 10 MB usando MediaFileUpload resumable.
    Garantiza bajo consumo de RAM y soporte para reconexión.
    """
    if not filepath or not os.path.isfile(filepath):
        return False, {"error": "Archivo local no encontrado"}

    try:
        service = get_drive_service(config, base_dir)
    except Exception as e:
        return False, {"error": f"Error de autenticación con Google Drive: {e}"}

    from googleapiclient.http import MediaFileUpload

    file_size = os.path.getsize(filepath)
    mime_type, _ = mimetypes.guess_type(filepath)
    if not mime_type:
        mime_type = "application/octet-stream"

    # Preparar metadatos del archivo
    file_metadata = {
        "name": filename,
        "description": f"Descargado por dHtools para usuario {owner}"
    }

    folder_id = (config.get("folder_id") or "").strip()
    if folder_id and folder_id.lower() != "root":
        file_metadata["parents"] = [folder_id]

    try:
        # Fragmentos de 10 MB (10 * 1024 * 1024)
        chunk_size = 10 * 1024 * 1024
        media = MediaFileUpload(
            filepath,
            mimetype=mime_type,
            chunksize=chunk_size,
            resumable=True
        )

        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,name,webViewLink,webContentLink,size",
            supportsAllDrives=True
        )

        response = None
        last_percent = -1

        if progress_callback:
            progress_callback(0, f"Iniciando subida a Google Drive ({filename})...")

        while response is None:
            status, response = request.next_chunk()
            if status:
                percent = int(status.progress() * 100)
                if percent != last_percent and percent % 5 == 0:
                    last_percent = percent
                    if progress_callback:
                        progress_callback(percent, f"Subiendo a Google Drive: {percent}%")
                    logger.debug(f"[GoogleDrive] {filename} -> {percent}%")
            
            # Liberar descriptores y memoria tras cada trozo
            gc.collect()

        file_id = response.get("id")
        web_link = response.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

        if progress_callback:
            progress_callback(100, f"Subida completada con éxito en Google Drive.")

        return True, {
            "file_id": file_id,
            "filename": filename,
            "size": response.get("size", file_size),
            "web_link": web_link,
            "drive_folder": folder_id or "root"
        }

    except Exception as e:
        logger.error(f"Error durante la subida a Google Drive de '{filename}': {e}", exc_info=True)
        return False, {"error": str(e)}
