import os
import time
import ftplib
import logging
import requests
from typing import Tuple, Dict, Any, List

from core.config import DOWNLOAD_DIR
from core.state import JOBS, JOBS_LOCK
from core.utils import (
    load_cloud_config, record_download_meta, load_downloads_meta,
    save_downloads_meta
)

logger = logging.getLogger("dHtools.CloudSync")


def test_s3_connection(config: dict) -> Tuple[bool, str]:
    """Tests connectivity and permissions to an S3-compatible bucket."""
    try:
        from plugins.s3_storage import s3_client
        return s3_client.test_connection(config)
    except Exception as e:
        logger.error(f"Error delegating to s3_client: {e}")
        return False, f"Error al verificar S3: {str(e)}"


def test_webdav_connection(config: dict) -> Tuple[bool, str]:
    """Tests connectivity and credentials for a WebDAV / Nextcloud server."""
    try:
        from plugins.webdav_storage import webdav_client
        return webdav_client.test_connection(config)
    except Exception as e:
        logger.error(f"Error delegating to webdav_client: {e}")
        return False, f"Error WebDAV: {str(e)}"


def test_ftp_connection(config: dict) -> Tuple[bool, str]:
    """Tests connectivity and credentials for an FTP / FTPS server."""
    try:
        from plugins.ftp_storage import ftp_client
        return ftp_client.test_connection(config)
    except Exception as e:
        logger.error(f"Error delegating to ftp_client: {e}")
        return False, f"Error FTP: {str(e)}"


def upload_to_s3(filepath: str, filename: str, config: dict) -> Tuple[bool, str]:
    """Uploads a local file to an S3-compatible bucket using multipart streaming."""
    try:
        from plugins.s3_storage import s3_client
        ok, res = s3_client.upload_file_multipart(filepath, filename, config)
        if ok:
            return True, res.get("s3_uri", "")
        return False, res.get("error", "Error subiendo a S3")
    except Exception as e:
        logger.error(f"Error delegating upload_to_s3: {e}")
        return False, f"Error subiendo a S3: {e}"


def upload_to_webdav(filepath: str, filename: str, config: dict) -> Tuple[bool, str]:
    """Uploads a local file to a WebDAV / Nextcloud server via HTTP PUT."""
    try:
        from plugins.webdav_storage import webdav_client
        ok, res = webdav_client.upload_file(filepath, filename, config)
        if ok:
            return True, res.get("web_link", "")
        return False, res.get("error", "Error subiendo a WebDAV")
    except Exception as e:
        logger.error(f"Error delegating upload_to_webdav: {e}")
        return False, f"Error WebDAV: {e}"


def upload_to_ftp(filepath: str, filename: str, config: dict) -> Tuple[bool, str]:
    """Uploads a local file to an FTP server."""
    try:
        from plugins.ftp_storage import ftp_client
        ok, res = ftp_client.upload_file(filepath, filename, config)
        if ok:
            return True, res.get("ftp_url", "")
        return False, res.get("error", "Error subiendo a FTP")
    except Exception as e:
        logger.error(f"Error delegating upload_to_ftp: {e}")
        return False, f"Error FTP: {e}"



def execute_cloud_sync(filepath: str, filename: str, job_info: dict = None, user_cloud_cfg: dict = None):
    """Centralized orchestrator for cloud sync, Telegram delivery, and Offload mode."""
    if not filepath or not os.path.exists(filepath):
        return

    cfg = load_cloud_config()
    job_id = (job_info or {}).get("job_id") or (job_info or {}).get("id")

    def _append_log(msg: str):
        if job_id:
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job:
                    if "logs" not in job:
                        job["logs"] = []
                    job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": msg})
                    if len(job["logs"]) > 150:
                        job["logs"] = job["logs"][-150:]

    # Merge user presets / personal overrides if provided
    is_offload_requested = False
    if user_cloud_cfg and isinstance(user_cloud_cfg, dict):
        if "s3" in user_cloud_cfg and user_cloud_cfg["s3"].get("enabled"):
            cfg["s3"] = user_cloud_cfg["s3"]
        if "webdav" in user_cloud_cfg and user_cloud_cfg["webdav"].get("enabled"):
            cfg["webdav"] = user_cloud_cfg["webdav"]
        if "ftp" in user_cloud_cfg and user_cloud_cfg["ftp"].get("enabled"):
            cfg["ftp"] = user_cloud_cfg["ftp"]
        if "webhook" in user_cloud_cfg and user_cloud_cfg["webhook"].get("enabled"):
            cfg["webhook"] = user_cloud_cfg["webhook"]
        if user_cloud_cfg.get("offload") or user_cloud_cfg.get("move_to_cloud"):
            is_offload_requested = True

    successful_destinations = []
    file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0

    # 1. Webhook Notification
    if cfg.get("webhook", {}).get("enabled") and cfg["webhook"].get("url"):
        try:
            requests.post(
                cfg["webhook"]["url"],
                json={
                    "event": "download_completed",
                    "filename": filename,
                    "size_bytes": file_size,
                    "job_info": job_info or {},
                    "timestamp": time.time(),
                },
                timeout=10,
            )
            _append_log(f"[*] [CloudSync] Notificación enviada exitosamente a Webhook.")
        except Exception as e:
            _append_log(f"[!] [CloudSync] Error Webhook: {e}")

    # 2. S3 / Object Storage Upload
    s3_cfg = cfg.get("s3", {})
    if s3_cfg.get("enabled"):
        b_name = s3_cfg.get("bucket_name") or s3_cfg.get("bucket")
        _append_log(f"[*] [CloudSync] Iniciando transferencia a bucket S3 '{b_name}'...")
        ok, res = upload_to_s3(filepath, filename, s3_cfg)
        if ok:
            successful_destinations.append(f"S3 ({res})")
            _append_log(f"[+] [CloudSync] Archivo subido con éxito a S3: {res}")
        else:
            _append_log(f"[!] [CloudSync] Falló la subida a S3: {res}")

    # 3. WebDAV / Nextcloud Upload
    wd_cfg = cfg.get("webdav", {})
    if wd_cfg.get("enabled"):
        _append_log("[*] [CloudSync] Iniciando transferencia a servidor WebDAV / Nextcloud...")
        ok, res = upload_to_webdav(filepath, filename, wd_cfg)
        if ok:
            successful_destinations.append(f"WebDAV ({res})")
            _append_log(f"[+] [CloudSync] Archivo subido con éxito a WebDAV: {res}")
        else:
            _append_log(f"[!] [CloudSync] Falló la subida a WebDAV: {res}")

    # 4. FTP Upload
    ftp_cfg = cfg.get("ftp", {})
    if ftp_cfg.get("enabled"):
        _append_log(f"[*] [CloudSync] Iniciando transferencia a servidor FTP ({ftp_cfg.get('host')})...")
        ok, res = upload_to_ftp(filepath, filename, ftp_cfg)
        if ok:
            successful_destinations.append(f"FTP ({res})")
            _append_log(f"[+] [CloudSync] Archivo subido con éxito a FTP: {res}")
        else:
            _append_log(f"[!] [CloudSync] Falló la subida a FTP: {res}")

    # 5. Telegram Bot notification / media delivery
    tg_chat_id = (job_info or {}).get("telegram_chat_id")
    tg_msg_id = (job_info or {}).get("telegram_message_id")
    if tg_chat_id:
        try:
            from core.telegram_bot import telegram_bot
            telegram_bot.notify_finished(job_id, filepath, filename, chat_id=tg_chat_id, message_id=tg_msg_id)
        except Exception as e:
            logger.error(f"Telegram notify_finished error: {e}")

    # 6. Safe Offload ("Subir y Mover" / Eliminar archivo local)
    if is_offload_requested and successful_destinations:
        _append_log(f"[*] [Offload] Modo 'Subir y Mover' activo. Verificando subida exitosa...")
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                _append_log(f"[+] [Offload] Archivo local eliminado del VPS. Almacenado de forma segura en: {', '.join(successful_destinations)}")

                # Update metadata in memory and disk
                if job_id:
                    with JOBS_LOCK:
                        if job_id in JOBS:
                            JOBS[job_id]["offloaded"] = True
                            JOBS[job_id]["cloud_destinations"] = successful_destinations
                            JOBS[job_id]["filepath"] = None

                    meta = load_downloads_meta()
                    if job_id in meta:
                        meta[job_id]["offloaded"] = True
                        meta[job_id]["cloud_destinations"] = successful_destinations
                        save_downloads_meta(meta)
        except Exception as e:
            _append_log(f"[!] [Offload] Error eliminando archivo local: {e}")
    elif is_offload_requested and not successful_destinations:
        _append_log("[!] [Offload] ATENCIÓN: El archivo local NO fue eliminado porque fallaron todos los destinos en la nube configurados.")
