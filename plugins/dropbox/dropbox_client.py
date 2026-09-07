"""
Cliente de integración con Dropbox API v2 para dHtools.
Soporta autenticación OAuth 2.0 con tokens de refresco permanentes (token_access_type=offline),
subida por sesiones de fragmentos (upload_session, RAM-Safe) y creación automática de enlaces compartidos.
"""

import os
import time
import json
import logging
import urllib.parse
from typing import Tuple, Dict, Any, Optional, Callable, List
import requests

logger = logging.getLogger("dhtools.plugins.dropbox.client")

API_BASE = "https://api.dropboxapi.com/2"
CONTENT_BASE = "https://content.dropboxapi.com/2"
OAUTH_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
OAUTH_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"

# Tamaño de bloque para upload_session: 4 MB (óptimo para streaming en Dropbox sin cargar RAM)
CHUNK_SIZE = 4 * 1024 * 1024


def get_authorization_url(app_key: str, redirect_uri: str, state: str) -> str:
    """Genera la URL de autorización OAuth2 de Dropbox solicitando token de refresco offline."""
    params = {
        "client_id": app_key.strip(),
        "response_type": "code",
        "token_access_type": "offline",
        "redirect_uri": redirect_uri.strip(),
        "state": state
    }
    return f"{OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(
    app_key: str,
    app_secret: str,
    code: str,
    redirect_uri: str
) -> Tuple[bool, Dict[str, Any]]:
    """Intercambia el código de autorización por tokens de acceso y refresco de Dropbox."""
    data = {
        "code": code.strip(),
        "grant_type": "authorization_code",
        "client_id": app_key.strip(),
        "client_secret": app_secret.strip(),
        "redirect_uri": redirect_uri.strip()
    }
    try:
        resp = requests.post(OAUTH_TOKEN_URL, data=data, timeout=20)
        res_data = resp.json()

        if resp.status_code != 200:
            err_msg = res_data.get("error_description") or res_data.get("error") or str(res_data)
            return False, {"error": f"Error al canjear código de Dropbox: {err_msg}"}

        expires_in = int(res_data.get("expires_in", 14400))  # Generalmente 4 horas
        token_data = {
            "access_token": res_data.get("access_token"),
            "refresh_token": res_data.get("refresh_token"),
            "token_type": res_data.get("token_type", "bearer"),
            "account_id": res_data.get("account_id"),
            "expires_in": expires_in,
            "expires_at": time.time() + expires_in - 120,  # 2 minutos de margen
            "scope": res_data.get("scope", "")
        }
        return True, token_data
    except Exception as e:
        logger.error(f"Excepción en exchange_code_for_token de Dropbox: {e}", exc_info=True)
        return False, {"error": f"Excepción al conectar con Dropbox: {e}"}


def refresh_token_if_needed(
    app_key: str,
    app_secret: str,
    token_data: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any], bool]:
    """
    Renueva el token de acceso mediante el refresh_token si ha caducado.
    Retorna: (success, updated_token_data, was_refreshed)
    """
    if not token_data or not token_data.get("access_token"):
        return False, {"error": "Token no disponible."}, False

    now = time.time()
    expires_at = token_data.get("expires_at", 0)

    # Si todavía es válido, reutilizar
    if now < expires_at:
        return True, token_data, False

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return False, {"error": "El token expiró y no hay refresh_token guardado para Dropbox."}, False

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": app_key.strip(),
        "client_secret": app_secret.strip()
    }
    try:
        resp = requests.post(OAUTH_TOKEN_URL, data=data, timeout=20)
        res_data = resp.json()

        if resp.status_code != 200:
            err_msg = res_data.get("error_description") or res_data.get("error") or str(res_data)
            return False, {"error": f"Error renovando token de Dropbox: {err_msg}"}, False

        expires_in = int(res_data.get("expires_in", 14400))
        new_token_data = dict(token_data)
        new_token_data["access_token"] = res_data.get("access_token")
        if res_data.get("refresh_token"):
            new_token_data["refresh_token"] = res_data.get("refresh_token")
        new_token_data["expires_in"] = expires_in
        new_token_data["expires_at"] = time.time() + expires_in - 120
        return True, new_token_data, True
    except Exception as e:
        logger.error(f"Excepción en refresh_token_if_needed de Dropbox: {e}", exc_info=True)
        return False, {"error": f"Error de red renovando sesión de Dropbox: {e}"}, False


def get_account_and_space_info(access_token: str) -> Tuple[bool, Dict[str, Any]]:
    """Obtiene los datos del perfil y la cuota de almacenamiento disponible en Dropbox."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    try:
        # 1. Perfil del usuario
        display_name = "Usuario Dropbox"
        email = ""
        account_id = ""

        u_resp = requests.post(f"{API_BASE}/users/get_current_account", headers=headers, json=None, timeout=10)
        if u_resp.status_code == 200:
            u_data = u_resp.json()
            display_name = u_data.get("name", {}).get("display_name") or display_name
            email = u_data.get("email", "")
            account_id = u_data.get("account_id", "")

        # 2. Uso de espacio
        s_resp = requests.post(f"{API_BASE}/users/get_space_usage", headers=headers, json=None, timeout=10)
        if s_resp.status_code != 200:
            return False, {"error": f"Error obteniendo espacio de Dropbox (HTTP {s_resp.status_code}): {s_resp.text}"}

        s_data = s_resp.json()
        used_bytes = int(s_data.get("used", 0))
        allocation = s_data.get("allocation", {})
        total_bytes = 0

        if allocation.get(".tag") == "individual":
            total_bytes = int(allocation.get("allocated", 0))
        elif allocation.get(".tag") == "team":
            total_bytes = int(allocation.get("allocated", 0))

        remaining_bytes = max(0, total_bytes - used_bytes)

        return True, {
            "display_name": display_name,
            "email": email,
            "account_id": account_id,
            "quota_total": total_bytes,
            "quota_used": used_bytes,
            "quota_remaining": remaining_bytes
        }
    except Exception as e:
        logger.error(f"Excepción en get_account_and_space_info de Dropbox: {e}", exc_info=True)
        return False, {"error": f"Error consultando Dropbox API: {e}"}


def list_folders(access_token: str, folder_path: str = "") -> Tuple[bool, Any]:
    """Lista las subcarpetas existentes dentro de la ruta especificada."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    clean_path = folder_path.strip()
    if clean_path in ("/", "", "\\"):
        clean_path = ""
    elif not clean_path.startswith("/"):
        clean_path = f"/{clean_path}"

    payload = {
        "path": clean_path,
        "recursive": False,
        "include_media_info": False,
        "include_deleted": False,
        "include_has_explicit_shared_members": False
    }

    try:
        resp = requests.post(f"{API_BASE}/files/list_folder", headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            return False, {"error": f"Error listando carpetas (HTTP {resp.status_code}): {resp.text}"}

        entries = resp.json().get("entries", [])
        folders = []
        for e in entries:
            if e.get(".tag") == "folder":
                folders.append({
                    "id": e.get("id"),
                    "name": e.get("name"),
                    "path_display": e.get("path_display")
                })
        folders.sort(key=lambda x: x["name"].lower())
        return True, folders
    except Exception as e:
        logger.error(f"Excepción en list_folders de Dropbox: {e}", exc_info=True)
        return False, {"error": f"Error explorando carpetas de Dropbox: {e}"}


def create_shared_link(access_token: str, dropbox_path: str) -> str:
    """Crea o recupera un enlace compartido público para el archivo subido."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    clean_path = dropbox_path if dropbox_path.startswith("/") else f"/{dropbox_path}"

    # 1. Intentar crear nuevo enlace compartido
    try:
        resp = requests.post(
            f"{API_BASE}/sharing/create_shared_link_with_settings",
            headers=headers,
            json={"path": clean_path, "settings": {"requested_visibility": "public"}},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("url", "")
    except Exception:
        pass

    # 2. Si ya existía, listar enlaces compartidos existentes para este archivo
    try:
        resp = requests.post(
            f"{API_BASE}/sharing/list_shared_links",
            headers=headers,
            json={"path": clean_path, "direct_only": True},
            timeout=10
        )
        if resp.status_code == 200:
            links = resp.json().get("links", [])
            if links:
                return links[0].get("url", "")
    except Exception:
        pass

    return f"https://www.dropbox.com/home{clean_path}"


def upload_file_resumable(
    access_token: str,
    file_path: str,
    dropbox_folder: str = "/dHtools",
    progress_callback: Optional[Callable[[float, int, int], None]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Sube un archivo local a Dropbox de forma resumable y por bloques (RAM-Safe).
    - Archivos < 4 MB: Subida atómica directa en un solo POST a /files/upload.
    - Archivos >= 4 MB: Sesión /files/upload_session (start, append_v2, finish).
    """
    if not file_path or not os.path.isfile(file_path):
        return False, {"error": f"El archivo local no existe: '{file_path}'"}

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    folder_clean = (dropbox_folder or "/dHtools").strip().rstrip("/")
    if not folder_clean.startswith("/"):
        folder_clean = f"/{folder_clean}"
    target_path = f"{folder_clean}/{file_name}"

    try:
        # ---------------------------------------------------------------------
        # CASO 1: Archivo menor a 4 MB -> Subida atómica directa
        # ---------------------------------------------------------------------
        if file_size < 4 * 1024 * 1024:
            upload_headers = {
                "Authorization": f"Bearer {access_token}",
                "Dropbox-API-Arg": json.dumps({
                    "path": target_path,
                    "mode": "add",
                    "autorename": True,
                    "mute": False
                }),
                "Content-Type": "application/octet-stream"
            }
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{CONTENT_BASE}/files/upload",
                    headers=upload_headers,
                    data=f,
                    timeout=60
                )

            if resp.status_code == 200:
                item = resp.json()
                if progress_callback:
                    progress_callback(100.0, file_size, file_size)
                shared_url = create_shared_link(access_token, item.get("path_display", target_path))
                return True, {
                    "id": item.get("id"),
                    "name": item.get("name", file_name),
                    "path": item.get("path_display", target_path),
                    "size": item.get("size", file_size),
                    "web_link": shared_url
                }
            else:
                return False, {"error": f"Fallo al subir a Dropbox (HTTP {resp.status_code}): {resp.text}"}

        # ---------------------------------------------------------------------
        # CASO 2: Archivo grande (>= 4 MB) -> Sesión de Subida por Bloques (RAM-Safe)
        # ---------------------------------------------------------------------
        with open(file_path, "rb") as f:
            # 1. Iniciar sesión de subida con el primer fragmento
            first_chunk = f.read(CHUNK_SIZE)
            start_headers = {
                "Authorization": f"Bearer {access_token}",
                "Dropbox-API-Arg": json.dumps({"close": False}),
                "Content-Type": "application/octet-stream"
            }
            start_resp = requests.post(
                f"{CONTENT_BASE}/files/upload_session/start",
                headers=start_headers,
                data=first_chunk,
                timeout=60
            )

            if start_resp.status_code != 200:
                return False, {"error": f"Error iniciando sesión de subida en Dropbox (HTTP {start_resp.status_code}): {start_resp.text}"}

            session_id = start_resp.json().get("session_id")
            if not session_id:
                return False, {"error": "Dropbox no devolvió session_id para la subida."}

            offset = len(first_chunk)
            if progress_callback:
                progress_callback(round((offset / file_size) * 100, 1), offset, file_size)

            # 2. Transmitir bloques intermedios y finalizar
            while offset < file_size:
                chunk = f.read(CHUNK_SIZE)
                chunk_len = len(chunk)

                # Si es el último bloque de datos
                if (offset + chunk_len) >= file_size:
                    finish_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Dropbox-API-Arg": json.dumps({
                            "cursor": {
                                "session_id": session_id,
                                "offset": offset
                            },
                            "commit": {
                                "path": target_path,
                                "mode": "add",
                                "autorename": True,
                                "mute": False
                            }
                        }),
                        "Content-Type": "application/octet-stream"
                    }
                    fin_resp = requests.post(
                        f"{CONTENT_BASE}/files/upload_session/finish",
                        headers=finish_headers,
                        data=chunk,
                        timeout=120
                    )
                    if fin_resp.status_code != 200:
                        return False, {"error": f"Error al finalizar sesión de subida en Dropbox (HTTP {fin_resp.status_code}): {fin_resp.text}"}

                    final_item = fin_resp.json()
                    offset += chunk_len
                    if progress_callback:
                        progress_callback(100.0, file_size, file_size)

                    shared_url = create_shared_link(access_token, final_item.get("path_display", target_path))
                    return True, {
                        "id": final_item.get("id"),
                        "name": final_item.get("name", file_name),
                        "path": final_item.get("path_display", target_path),
                        "size": final_item.get("size", file_size),
                        "web_link": shared_url
                    }

                # Si es un bloque intermedio
                append_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Dropbox-API-Arg": json.dumps({
                        "cursor": {
                            "session_id": session_id,
                            "offset": offset
                        },
                        "close": False
                    }),
                    "Content-Type": "application/octet-stream"
                }
                app_resp = requests.post(
                    f"{CONTENT_BASE}/files/upload_session/append_v2",
                    headers=append_headers,
                    data=chunk,
                    timeout=60
                )
                if app_resp.status_code != 200:
                    return False, {"error": f"Error subiendo fragmento a Dropbox en offset {offset} (HTTP {app_resp.status_code}): {app_resp.text}"}

                offset += chunk_len
                if progress_callback:
                    progress_callback(round((offset / file_size) * 100, 1), offset, file_size)

        return False, {"error": "Subida incompleta o flujo interrumpido en Dropbox."}

    except Exception as e:
        logger.error(f"Excepción en upload_file_resumable de Dropbox: {e}", exc_info=True)
        return False, {"error": f"Error durante la subida a Dropbox: {e}"}
