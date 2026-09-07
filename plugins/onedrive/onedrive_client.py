"""
Cliente de integración con Microsoft Graph API v1.0 para Microsoft OneDrive y SharePoint en dHtools.
Soporta cuentas personales (Outlook/Hotmail) y cuentas educativas/empresariales de Microsoft 365,
subida por bloques resumables (chunked upload sessions, RAM-Safe) y autenticación OAuth 2.0.
"""

import os
import time
import json
import logging
import urllib.parse
from typing import Tuple, Dict, Any, Optional, Callable
import requests

logger = logging.getLogger("dhtools.plugins.onedrive.client")

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_SCOPES = ["offline_access", "Files.ReadWrite", "User.Read"]

# El tamaño de fragmento para Microsoft Graph DEBE ser múltiplo exacto de 320 KiB (327,680 bytes).
# 10 * 327,680 = 3,276,800 bytes (~3.2 MB por bloque). Ideal para transferencias rápidas sin sobrecargar RAM.
CHUNK_SIZE = 10 * 320 * 1024


def get_login_endpoint(tenant: str = "common") -> str:
    """Retorna la URL base del endpoint OAuth2 según el tenant configurado."""
    t = (tenant or "common").strip()
    return f"https://login.microsoftonline.com/{t}/oauth2/v2.0"


def get_authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    tenant: str = "common",
    scopes: Optional[list] = None
) -> str:
    """Genera la URL de inicio de sesión y autorización OAuth2 de Microsoft."""
    req_scopes = scopes or DEFAULT_SCOPES
    base = f"{get_login_endpoint(tenant)}/authorize"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(req_scopes),
        "state": state
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    tenant: str = "common"
) -> Tuple[bool, Dict[str, Any]]:
    """Intercambia el código de autorización por tokens de acceso y refresco."""
    token_url = f"{get_login_endpoint(tenant)}/token"
    payload = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": " ".join(DEFAULT_SCOPES)
    }
    if client_secret and client_secret.strip():
        payload["client_secret"] = client_secret.strip()

    try:
        resp = requests.post(token_url, data=payload, timeout=20)
        data = resp.json()
        if resp.status_code != 200:
            err_msg = data.get("error_description") or data.get("error") or str(data)
            return False, {"error": f"Error al obtener token de Microsoft: {err_msg}"}

        expires_in = int(data.get("expires_in", 3600))
        token_data = {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "token_type": data.get("token_type", "Bearer"),
            "expires_in": expires_in,
            "expires_at": time.time() + expires_in - 120,  # 2 minutos de margen de seguridad
            "scope": data.get("scope", "")
        }
        return True, token_data
    except Exception as e:
        logger.error(f"Excepción en exchange_code_for_token: {e}", exc_info=True)
        return False, {"error": f"Excepción al conectar con Microsoft: {e}"}


def refresh_token_if_needed(
    client_id: str,
    client_secret: str,
    token_data: Dict[str, Any],
    tenant: str = "common"
) -> Tuple[bool, Dict[str, Any], bool]:
    """
    Verifica si el access_token ha expirado y lo renueva si es necesario mediante el refresh_token.
    Retorna: (success, updated_token_data, was_refreshed)
    """
    if not token_data or not token_data.get("access_token"):
        return False, {"error": "Token de acceso no disponible."}, False

    now = time.time()
    expires_at = token_data.get("expires_at", 0)

    # Si todavía es válido, retornamos el token actual
    if now < expires_at:
        return True, token_data, False

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return False, {"error": "El token ha expirado y no hay refresh_token guardado para renovarlo."}, False

    token_url = f"{get_login_endpoint(tenant)}/token"
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(DEFAULT_SCOPES)
    }
    if client_secret and client_secret.strip():
        payload["client_secret"] = client_secret.strip()

    try:
        resp = requests.post(token_url, data=payload, timeout=20)
        data = resp.json()
        if resp.status_code != 200:
            err_msg = data.get("error_description") or data.get("error") or str(data)
            return False, {"error": f"Error renovando token: {err_msg}"}, False

        expires_in = int(data.get("expires_in", 3600))
        new_token_data = dict(token_data)
        new_token_data["access_token"] = data.get("access_token")
        if data.get("refresh_token"):
            new_token_data["refresh_token"] = data.get("refresh_token")
        new_token_data["expires_in"] = expires_in
        new_token_data["expires_at"] = time.time() + expires_in - 120
        return True, new_token_data, True
    except Exception as e:
        logger.error(f"Excepción en refresh_token_if_needed: {e}", exc_info=True)
        return False, {"error": f"Error de red renovando sesión de OneDrive: {e}"}, False


def get_user_and_drive_info(access_token: str) -> Tuple[bool, Dict[str, Any]]:
    """Obtiene la información del perfil de usuario y la cuota de almacenamiento de OneDrive."""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        # 1. Perfil del usuario
        user_name = "Usuario Microsoft"
        user_email = ""
        u_resp = requests.get(f"{GRAPH_API_BASE}/me", headers=headers, timeout=10)
        if u_resp.status_code == 200:
            u_data = u_resp.json()
            user_name = u_data.get("displayName") or user_name
            user_email = u_data.get("mail") or u_data.get("userPrincipalName") or ""

        # 2. Drive y cuota
        d_resp = requests.get(f"{GRAPH_API_BASE}/me/drive", headers=headers, timeout=10)
        if d_resp.status_code != 200:
            return False, {"error": f"Error obteniendo unidad OneDrive (HTTP {d_resp.status_code}): {d_resp.text}"}

        d_data = d_resp.json()
        quota = d_data.get("quota", {})
        total_bytes = int(quota.get("total", 0))
        used_bytes = int(quota.get("used", 0))
        remaining_bytes = int(quota.get("remaining", max(0, total_bytes - used_bytes)))

        return True, {
            "display_name": user_name,
            "email": user_email,
            "drive_id": d_data.get("id"),
            "drive_type": d_data.get("driveType", "personal"),
            "quota_total": total_bytes,
            "quota_used": used_bytes,
            "quota_remaining": remaining_bytes,
            "quota_state": quota.get("state", "normal"),
            "web_url": d_data.get("webUrl", "")
        }
    except Exception as e:
        logger.error(f"Excepción en get_user_and_drive_info: {e}", exc_info=True)
        return False, {"error": f"Error consultando Microsoft Graph: {e}"}


def list_folders(access_token: str, parent_id: Optional[str] = None) -> Tuple[bool, Any]:
    """Lista las carpetas disponibles en la raíz o dentro de un directorio específico."""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        if not parent_id or parent_id == "root":
            url = f"{GRAPH_API_BASE}/me/drive/root/children?$filter=folder ne null&$select=id,name,webUrl,folder"
        else:
            url = f"{GRAPH_API_BASE}/me/drive/items/{parent_id}/children?$filter=folder ne null&$select=id,name,webUrl,folder"

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return False, {"error": f"Error listando carpetas (HTTP {resp.status_code}): {resp.text}"}

        items = resp.json().get("value", [])
        folders = []
        for it in items:
            folders.append({
                "id": it.get("id"),
                "name": it.get("name"),
                "web_url": it.get("webUrl", ""),
                "child_count": it.get("folder", {}).get("childCount", 0)
            })
        folders.sort(key=lambda x: x["name"].lower())
        return True, folders
    except Exception as e:
        logger.error(f"Excepción en list_folders: {e}", exc_info=True)
        return False, {"error": f"Error consultando carpetas: {e}"}


def upload_file_resumable(
    access_token: str,
    file_path: str,
    folder_id: Optional[str] = None,
    folder_path: Optional[str] = None,
    progress_callback: Optional[Callable[[float, int, int], None]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Sube un archivo a OneDrive de forma resumable y por bloques (RAM-Safe).
    - Archivos < 4 MB: Subida atómica directa en un solo PUT.
    - Archivos >= 4 MB: Crea una Upload Session y sube en fragmentos de CHUNK_SIZE (~3.2 MB).
    """
    if not file_path or not os.path.isfile(file_path):
        return False, {"error": f"El archivo local no existe: '{file_path}'"}

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        # Resolver URL de subida según destino
        has_folder_id = bool(folder_id and folder_id.strip() and folder_id.strip() != "root")
        clean_path = (folder_path or "/dHtools").strip().strip("/")
        if not clean_path:
            clean_path = "dHtools"

        encoded_name = urllib.parse.quote(file_name)

        # ---------------------------------------------------------------------
        # CASO 1: Archivo pequeño (< 4 MB) -> Subida atómica directa
        # ---------------------------------------------------------------------
        if file_size < 4 * 1024 * 1024:
            if has_folder_id:
                upload_url = f"{GRAPH_API_BASE}/me/drive/items/{folder_id.strip()}:/{encoded_name}:/content"
            else:
                upload_url = f"{GRAPH_API_BASE}/me/drive/root:/{clean_path}/{encoded_name}:/content"

            with open(file_path, "rb") as f:
                resp = requests.put(upload_url, headers=headers, data=f, timeout=60)

            if resp.status_code in (200, 201):
                item = resp.json()
                if progress_callback:
                    progress_callback(100.0, file_size, file_size)
                return True, {
                    "id": item.get("id"),
                    "name": item.get("name", file_name),
                    "size": item.get("size", file_size),
                    "web_link": item.get("webUrl", ""),
                    "created_at": item.get("createdDateTime", "")
                }
            else:
                return False, {"error": f"Fallo al subir archivo pequeño (HTTP {resp.status_code}): {resp.text}"}

        # ---------------------------------------------------------------------
        # CASO 2: Archivo grande (>= 4 MB) -> Chunked Upload Session (RAM-Safe)
        # ---------------------------------------------------------------------
        if has_folder_id:
            session_endpoint = f"{GRAPH_API_BASE}/me/drive/items/{folder_id.strip()}:/{encoded_name}:/createUploadSession"
        else:
            session_endpoint = f"{GRAPH_API_BASE}/me/drive/root:/{clean_path}/{encoded_name}:/createUploadSession"

        session_payload = {
            "item": {
                "@microsoft.graph.conflictBehavior": "rename"
            }
        }
        s_resp = requests.post(session_endpoint, headers=headers, json=session_payload, timeout=30)
        if s_resp.status_code not in (200, 201):
            return False, {"error": f"No se pudo crear la sesión de subida en OneDrive (HTTP {s_resp.status_code}): {s_resp.text}"}

        upload_url = s_resp.json().get("uploadUrl")
        if not upload_url:
            return False, {"error": "Microsoft Graph no retornó la URL de subida de la sesión."}

        # Transmitir fragmentos secuenciales
        uploaded_bytes = 0
        with open(file_path, "rb") as f:
            while uploaded_bytes < file_size:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                chunk_len = len(chunk)
                start_byte = uploaded_bytes
                end_byte = uploaded_bytes + chunk_len - 1

                chunk_headers = {
                    "Content-Length": str(chunk_len),
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}"
                }

                # Reintentos por fragmento en caso de fluctuaciones de red
                max_retries = 3
                chunk_ok = False
                last_err = ""
                final_item = None

                for attempt in range(max_retries):
                    try:
                        c_resp = requests.put(upload_url, headers=chunk_headers, data=chunk, timeout=60)
                        if c_resp.status_code in (200, 201):
                            # Subida del último bloque exitosa
                            final_item = c_resp.json()
                            chunk_ok = True
                            break
                        elif c_resp.status_code == 202:
                            # Fragmento intermedio aceptado correctamente
                            chunk_ok = True
                            break
                        else:
                            last_err = f"HTTP {c_resp.status_code}: {c_resp.text}"
                            time.sleep(1.5)
                    except Exception as ex:
                        last_err = str(ex)
                        time.sleep(2)

                if not chunk_ok:
                    # Cancelar sesión de subida en caso de error fatal
                    try:
                        requests.delete(upload_url, timeout=10)
                    except Exception:
                        pass
                    return False, {"error": f"Error subiendo fragmento [{start_byte}-{end_byte}]: {last_err}"}

                uploaded_bytes += chunk_len
                if progress_callback:
                    pct = round((uploaded_bytes / file_size) * 100, 1)
                    progress_callback(pct, uploaded_bytes, file_size)

        # Si llegamos al final pero final_item no se asignó en el loop (caso edge de retorno 202 en último chunk)
        if not final_item:
            final_item = {"name": file_name, "webUrl": f"https://onedrive.live.com/?id={urllib.parse.quote(clean_path)}"}

        return True, {
            "id": final_item.get("id"),
            "name": final_item.get("name", file_name),
            "size": final_item.get("size", file_size),
            "web_link": final_item.get("webUrl", ""),
            "created_at": final_item.get("createdDateTime", "")
        }

    except Exception as e:
        logger.error(f"Excepción en upload_file_resumable: {e}", exc_info=True)
        return False, {"error": f"Error durante la subida a OneDrive: {e}"}
