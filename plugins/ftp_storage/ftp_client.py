"""
Cliente modular de integración con servidores FTP / FTPS para dHtools.
Permite verificar conectividad y transferir archivos por streaming binario con gestión
recursiva de directorios remotos.
"""

import os
import ftplib
import logging
from typing import Tuple, Dict, Any, Optional, Callable

logger = logging.getLogger("dhtools.plugins.ftp_storage.client")


def _get_ftp_connection(config: Dict[str, Any], timeout: int = 20) -> ftplib.FTP:
    """Instancia y conecta un cliente FTP o FTP_TLS según la configuración."""
    host = (config.get("host") or "").strip()
    port = int(config.get("port", 21))
    use_tls = bool(config.get("use_tls", False))

    if use_tls:
        ftp = ftplib.FTP_TLS(timeout=timeout)
    else:
        ftp = ftplib.FTP(timeout=timeout)

    ftp.connect(host, port)
    return ftp


def test_connection(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verifica conectividad y credenciales con el servidor FTP.
    Retorna (ok: bool, mensaje: str).
    """
    if not config or not isinstance(config, dict):
        return False, "Configuración FTP vacía o inválida"

    host = (config.get("host") or "").strip()
    port = int(config.get("port", 21))
    username = (config.get("username") or "anonymous").strip() or "anonymous"
    password = config.get("password") or ""
    use_tls = bool(config.get("use_tls", False))

    if not host:
        return False, "Falta especificar el host o dirección IP del servidor FTP"

    try:
        ftp = _get_ftp_connection(config, timeout=10)
        if use_tls and isinstance(ftp, ftplib.FTP_TLS):
            ftp.auth()
        ftp.login(username, password)
        if use_tls and isinstance(ftp, ftplib.FTP_TLS):
            ftp.prot_p()

        welcome = ftp.getwelcome()
        ftp.quit()
        protocol_desc = "FTPS (TLS)" if use_tls else "FTP Estándar"
        return True, f"Conexión {protocol_desc} exitosa con {host}:{port}"
    except ftplib.error_perm as e:
        return False, f"Error de autenticación o permisos en FTP ({e})"
    except TimeoutError:
        return False, f"Tiempo de espera agotado al conectar a {host}:{port}"
    except Exception as e:
        return False, f"Error al conectar con FTP: {str(e)}"


def upload_file(
    filepath: str,
    filename: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Sube un archivo local al servidor FTP navegando o creando carpetas recursivamente.
    """
    if not filepath or not os.path.isfile(filepath):
        return False, {"error": f"Archivo local no encontrado: '{filepath}'"}

    config = config or {}
    host = (config.get("host") or "").strip()
    port = int(config.get("port", 21))
    username = (config.get("username") or "anonymous").strip() or "anonymous"
    password = config.get("password") or ""
    remote_dir = (config.get("remote_dir") or "/").strip()
    use_tls = bool(config.get("use_tls", False))

    if not host:
        return False, {"error": "Falta host FTP"}

    clean_filename = filename or os.path.basename(filepath)
    total_size = os.path.getsize(filepath)

    try:
        ftp = _get_ftp_connection(config, timeout=60)
        if use_tls and isinstance(ftp, ftplib.FTP_TLS):
            ftp.auth()
        ftp.login(username, password)
        if use_tls and isinstance(ftp, ftplib.FTP_TLS):
            ftp.prot_p()

        # Navegación y creación recursiva de directorios remotos
        if remote_dir and remote_dir != "/":
            parts = [p for p in remote_dir.split("/") if p]
            for part in parts:
                try:
                    ftp.cwd(part)
                except Exception:
                    try:
                        ftp.mkd(part)
                        ftp.cwd(part)
                    except Exception:
                        pass

        if progress_callback:
            progress_callback(10, f"Iniciando subida binaria a FTP: {clean_filename}")

        with open(filepath, "rb") as f:
            ftp.storbinary(f"STOR {clean_filename}", f)

        try:
            ftp.quit()
        except Exception:
            pass

        clean_remote = remote_dir.rstrip("/")
        full_remote_path = f"{clean_remote}/{clean_filename}" if clean_remote else f"/{clean_filename}"
        ftp_url = f"ftp://{host}:{port}{full_remote_path}"

        if progress_callback:
            progress_callback(100, f"Archivo transferido con éxito a FTP ({total_size // (1024*1024)} MB)")

        return True, {
            "success": True,
            "filename": clean_filename,
            "ftp_url": ftp_url,
            "web_link": ftp_url,
            "provider": "ftp_storage",
            "bytes_uploaded": total_size
        }
    except Exception as e:
        logger.error(f"Error subiendo '{filepath}' a FTP ({host}): {e}", exc_info=True)
        return False, {"error": f"Error FTP: {e}"}
