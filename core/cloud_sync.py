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
    if not config:
        return False, "Configuración S3 vacía"

    bucket = (config.get("bucket_name") or config.get("bucket") or "").strip()
    key_id = (config.get("access_key") or "").strip()
    secret = (config.get("secret_key") or "").strip()
    endpoint = (config.get("endpoint_url") or "").strip() or None
    region = (config.get("region") or "").strip() or "us-east-1"

    if not bucket:
        return False, "Falta especificar el nombre del Bucket S3"
    if not key_id or not secret:
        return False, "Faltan credenciales Access Key o Secret Key"

    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError, EndpointConnectionError
    except ImportError:
        return False, "Librería boto3 no instalada en el entorno"

    try:
        boto_cfg = Config(
            region_name=region,
            signature_version="s3v4",
            retries={"max_attempts": 2, "mode": "standard"},
            connect_timeout=10,
            read_timeout=10,
        )
        s3 = boto3.client(
            "s3",
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            endpoint_url=endpoint,
            config=boto_cfg,
        )
        # Attempt to verify bucket access
        s3.head_bucket(Bucket=bucket)
        dest_desc = f"Bucket '{bucket}' en {endpoint or 'AWS S3'}"
        return True, f"Conexión S3 exitosa ({dest_desc})"
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Desconocido")
        msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code in ("403", "AccessDenied"):
            return False, f"Acceso denegado (403): Verificá Access Key, Secret Key y permisos del Bucket '{bucket}'."
        if error_code in ("404", "NoSuchBucket"):
            return False, f"El bucket '{bucket}' no existe o el nombre es incorrecto."
        return False, f"Error de S3 ({error_code}): {msg}"
    except EndpointConnectionError:
        return False, f"No se pudo conectar al endpoint S3: {endpoint}"
    except Exception as e:
        return False, f"Error al verificar S3: {str(e)}"


def upload_to_s3(filepath: str, filename: str, config: dict) -> Tuple[bool, str]:
    """Uploads a local file to an S3-compatible bucket using multipart streaming."""
    if not filepath or not os.path.isfile(filepath):
        return False, "Archivo local no encontrado"

    bucket = (config.get("bucket_name") or config.get("bucket") or "").strip()
    key_id = (config.get("access_key") or "").strip()
    secret = (config.get("secret_key") or "").strip()
    endpoint = (config.get("endpoint_url") or "").strip() or None
    region = (config.get("region") or "").strip() or "us-east-1"
    remote_dir = (config.get("remote_dir") or config.get("prefix") or "").strip("/ ")

    if not bucket or not key_id or not secret:
        return False, "Configuración S3 incompleta (bucket o credenciales faltantes)"

    try:
        import boto3
        from boto3.s3.transfer import TransferConfig
        from botocore.config import Config
    except ImportError:
        return False, "Librería boto3 no disponible"

    object_key = f"{remote_dir}/{filename}" if remote_dir else filename

    try:
        boto_cfg = Config(
            region_name=region,
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        )
        s3 = boto3.client(
            "s3",
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            endpoint_url=endpoint,
            config=boto_cfg,
        )

        # 10MB chunk threshold for multipart upload, 4 concurrent threads
        transfer_config = TransferConfig(
            multipart_threshold=10 * 1024 * 1024,
            max_concurrency=4,
            multipart_chunksize=10 * 1024 * 1024,
            use_threads=True,
        )

        s3.upload_file(
            Filename=filepath,
            Bucket=bucket,
            Key=object_key,
            Config=transfer_config,
        )
        return True, f"s3://{bucket}/{object_key}"
    except Exception as e:
        return False, f"Error subiendo a S3: {e}"


def upload_to_webdav(filepath: str, filename: str, config: dict) -> Tuple[bool, str]:
    """Uploads a local file to a WebDAV / Nextcloud server via HTTP PUT."""
    if not filepath or not os.path.isfile(filepath):
        return False, "Archivo local no encontrado"

    base_url = (config.get("url") or "").rstrip("/")
    remote_path = (config.get("remote_path") or "").strip("/ ")
    username = config.get("username", "")
    password = config.get("password", "")

    if not base_url:
        return False, "Falta URL WebDAV"

    target_url = f"{base_url}/{remote_path}/{filename}" if remote_path else f"{base_url}/{filename}"
    auth = (username, password) if username else None

    try:
        with open(filepath, "rb") as f:
            resp = requests.put(target_url, data=f, auth=auth, timeout=300)
        if resp.status_code in (200, 201, 204):
            return True, target_url
        return False, f"WebDAV respondió HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Error WebDAV: {e}"


def upload_to_ftp(filepath: str, filename: str, config: dict) -> Tuple[bool, str]:
    """Uploads a local file to an FTP server."""
    if not filepath or not os.path.isfile(filepath):
        return False, "Archivo local no encontrado"

    host = config.get("host")
    port = int(config.get("port", 21))
    username = config.get("username", "anonymous")
    password = config.get("password", "")
    remote_dir = (config.get("remote_dir") or "/").strip()

    if not host:
        return False, "Falta host FTP"

    try:
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=60)
        ftp.login(username, password)

        if remote_dir and remote_dir != "/":
            # Navigate or create directories recursively
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

        with open(filepath, "rb") as f:
            ftp.storbinary(f"STOR {filename}", f)
        ftp.quit()
        return True, f"ftp://{host}:{port}{remote_dir.rstrip('/')}/{filename}"
    except Exception as e:
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
