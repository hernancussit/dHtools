"""
Cliente modular de integración con WebDAV / Nextcloud para dHtools.
Permite verificar conectividad (PROPFIND / HEAD) y transferir archivos por streaming HTTP PUT.
"""

import os
import logging
from typing import Tuple, Dict, Any, Optional, Callable
import requests

logger = logging.getLogger("dhtools.plugins.webdav_storage.client")


def test_connection(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verifica conectividad y autenticación con un servidor WebDAV / Nextcloud.
    Retorna (ok: bool, mensaje: str).
    """
    if not config or not isinstance(config, dict):
        return False, "Configuración WebDAV vacía o inválida"

    url = (config.get("url") or "").strip().rstrip("/")
    username = (config.get("username") or "").strip()
    password = config.get("password") or ""

    if not url:
        return False, "Falta especificar la URL del servidor WebDAV"

    auth = (username, password) if username else None

    try:
        # Petición PROPFIND estándar WebDAV con profundidad 0
        r = requests.request("PROPFIND", url, auth=auth, headers={"Depth": "0"}, timeout=10)
        if r.status_code in (200, 207):
            return True, f"Conexión WebDAV exitosa (HTTP {r.status_code})"
        if r.status_code == 401:
            return False, "Autenticación WebDAV fallida (401 Unauthorized). Verificá usuario y contraseña."
        if r.status_code in (301, 302, 307, 308):
            redirect_to = r.headers.get("Location", "")
            return True, f"Servidor WebDAV activo (Redirección HTTP {r.status_code} a {redirect_to})"
        if r.status_code == 405:
            # PROPFIND no permitido, intentar OPTIONS o HEAD
            r_opts = requests.options(url, auth=auth, timeout=8)
            if r_opts.status_code in (200, 204):
                return True, f"Conexión WebDAV verificada vía OPTIONS (HTTP {r_opts.status_code})"
            return False, f"Servidor WebDAV no admite PROPFIND (HTTP 405)"

        return False, f"Servidor WebDAV respondió HTTP {r.status_code}"
    except requests.exceptions.SSLError:
        return False, "Error de certificado SSL al conectar con el servidor WebDAV."
    except requests.exceptions.ConnectionError:
        return False, f"No se pudo conectar al servidor WebDAV en '{url}'."
    except requests.exceptions.Timeout:
        return False, "Tiempo de espera agotado al conectar con el servidor WebDAV."
    except Exception as e:
        return False, f"Error WebDAV: {str(e)}"


def upload_file(
    filepath: str,
    filename: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Sube un archivo local a un servidor WebDAV mediante streaming HTTP PUT (RAM-Safe).
    """
    if not filepath or not os.path.isfile(filepath):
        return False, {"error": f"Archivo local no encontrado: '{filepath}'"}

    config = config or {}
    base_url = (config.get("url") or "").strip().rstrip("/")
    remote_path = (config.get("remote_path") or "").strip("/ ")
    username = (config.get("username") or "").strip()
    password = config.get("password") or ""

    if not base_url:
        return False, {"error": "Falta URL del servidor WebDAV"}

    clean_filename = filename or os.path.basename(filepath)
    if remote_path:
        target_url = f"{base_url}/{remote_path}/{clean_filename}"
    else:
        target_url = f"{base_url}/{clean_filename}"

    auth = (username, password) if username else None
    total_size = os.path.getsize(filepath)

    try:
        if progress_callback:
            progress_callback(10, f"Iniciando transferencia a WebDAV: {clean_filename}")

        with open(filepath, "rb") as f:
            resp = requests.put(target_url, data=f, auth=auth, timeout=300)

        if resp.status_code in (200, 201, 204):
            if progress_callback:
                progress_callback(100, f"Subida WebDAV completada con éxito ({total_size // (1024*1024)} MB)")
            return True, {
                "success": True,
                "filename": clean_filename,
                "target_url": target_url,
                "web_link": target_url,
                "provider": "webdav_storage",
                "bytes_uploaded": total_size
            }

        if resp.status_code == 409:
            # Conflicto: la carpeta intermedia remota puede no existir. Intentar crearla con MKCOL
            if remote_path:
                folder_url = f"{base_url}/{remote_path}"
                try:
                    requests.request("MKCOL", folder_url, auth=auth, timeout=10)
                    with open(filepath, "rb") as f2:
                        resp2 = requests.put(target_url, data=f2, auth=auth, timeout=300)
                    if resp2.status_code in (200, 201, 204):
                        return True, {
                            "success": True,
                            "filename": clean_filename,
                            "target_url": target_url,
                            "web_link": target_url,
                            "provider": "webdav_storage",
                            "bytes_uploaded": total_size
                        }
                except Exception:
                    pass

        return False, {"error": f"WebDAV respondió HTTP {resp.status_code}"}
    except Exception as e:
        logger.error(f"Error WebDAV subiendo '{filepath}': {e}", exc_info=True)
        return False, {"error": f"Error WebDAV: {e}"}
