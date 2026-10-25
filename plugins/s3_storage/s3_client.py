"""
Cliente modular de integración con almacenamiento compatible con S3 para dHtools.
Soporta AWS S3, MinIO, Cloudflare R2, Backblaze B2 y Wasabi mediante streaming multipart
(TransferConfig, RAM-Safe) y verificación de conectividad.
"""

import os
import logging
from typing import Tuple, Dict, Any, Optional, Callable

logger = logging.getLogger("dhtools.plugins.s3_storage.client")


def check_dependencies() -> Tuple[bool, str]:
    """Verifica si la librería boto3 se encuentra instalada en el entorno."""
    try:
        import boto3
        import botocore
        return True, "boto3 disponible"
    except ImportError:
        return False, "Librería boto3 no instalada en el entorno"


def test_connection(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verifica conectividad y permisos hacia un bucket compatible con S3.
    Retorna (ok: bool, mensaje: str).
    """
    if not config or not isinstance(config, dict):
        return False, "Configuración S3 vacía o inválida"

    bucket = (config.get("bucket_name") or config.get("bucket") or "").strip()
    key_id = (config.get("access_key") or "").strip()
    secret = (config.get("secret_key") or "").strip()
    endpoint = (config.get("endpoint_url") or "").strip() or None
    region = (config.get("region") or "").strip() or "us-east-1"

    if not bucket:
        return False, "Falta especificar el nombre del Bucket S3"
    if not key_id or not secret:
        return False, "Faltan credenciales Access Key o Secret Key"

    deps_ok, deps_msg = check_dependencies()
    if not deps_ok:
        return False, deps_msg

    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError, EndpointConnectionError
    except ImportError:
        return False, "Librería boto3 no disponible"

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
        s3.head_bucket(Bucket=bucket)
        dest_desc = f"Bucket '{bucket}' en {endpoint or 'AWS S3'}"
        return True, f"Conexión S3 exitosa ({dest_desc})"
    except ClientError as e:
        error_code = str(e.response.get("Error", {}).get("Code", "Desconocido"))
        msg = e.response.get("Error", {}).get("Message", str(e))
        if error_code in ("403", "AccessDenied"):
            return False, f"Acceso denegado (403): Verificá Access Key, Secret Key y permisos del Bucket '{bucket}'."
        if error_code in ("404", "NoSuchBucket"):
            return False, f"El bucket '{bucket}' no existe o el nombre es incorrecto."
        return False, f"Error de S3 ({error_code}): {msg}"
    except EndpointConnectionError:
        return False, f"No se pudo conectar al endpoint S3: {endpoint or 'AWS S3'}"
    except Exception as e:
        return False, f"Error al verificar S3: {str(e)}"


def upload_file_multipart(
    filepath: str,
    filename: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Sube un archivo local a un bucket S3 usando streaming multipart con TransferConfig.
    Garantiza bajo consumo de RAM en archivos gigantes (> 100 MB / 4K).
    """
    if not filepath or not os.path.isfile(filepath):
        return False, {"error": f"Archivo local no encontrado o inválido: '{filepath}'"}

    config = config or {}
    bucket = (config.get("bucket_name") or config.get("bucket") or "").strip()
    key_id = (config.get("access_key") or "").strip()
    secret = (config.get("secret_key") or "").strip()
    endpoint = (config.get("endpoint_url") or "").strip() or None
    region = (config.get("region") or "").strip() or "us-east-1"
    remote_dir = (config.get("remote_dir") or config.get("prefix") or "").strip("/ ")

    if not bucket or not key_id or not secret:
        return False, {"error": "Configuración S3 incompleta (bucket o credenciales faltantes)"}

    deps_ok, deps_msg = check_dependencies()
    if not deps_ok:
        return False, {"error": deps_msg}

    try:
        import boto3
        from boto3.s3.transfer import TransferConfig
        from botocore.config import Config
    except ImportError:
        return False, {"error": "Librería boto3 no disponible"}

    clean_filename = filename or os.path.basename(filepath)
    object_key = f"{remote_dir}/{clean_filename}" if remote_dir else clean_filename

    total_bytes = os.path.getsize(filepath)
    uploaded_bytes = 0

    class S3ProgressCallback:
        def __init__(self, total_size, cb):
            self.total_size = total_size
            self.uploaded = 0
            self.cb = cb

        def __call__(self, bytes_amount):
            self.uploaded += bytes_amount
            if self.cb and self.total_size > 0:
                pct = int((self.uploaded / self.total_size) * 100)
                pct = min(max(pct, 0), 100)
                self.cb(pct, f"Subiendo a S3: {pct}% ({self.uploaded // (1024*1024)}/{self.total_size // (1024*1024)} MB)")

    try:
        boto_cfg = Config(
            region_name=region,
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=15,
            read_timeout=30,
        )
        s3 = boto3.client(
            "s3",
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            endpoint_url=endpoint,
            config=boto_cfg,
        )

        # 10MB chunk threshold para streaming multipart, 4 hilos concurrentes
        transfer_config = TransferConfig(
            multipart_threshold=10 * 1024 * 1024,
            max_concurrency=4,
            multipart_chunksize=10 * 1024 * 1024,
            use_threads=True,
        )

        cb_obj = S3ProgressCallback(total_bytes, progress_callback) if progress_callback else None

        s3.upload_file(
            Filename=filepath,
            Bucket=bucket,
            Key=object_key,
            Config=transfer_config,
            Callback=cb_obj,
        )

        s3_uri = f"s3://{bucket}/{object_key}"
        web_link = f"{endpoint.rstrip('/')}/{bucket}/{object_key}" if endpoint else f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}"

        return True, {
            "success": True,
            "filename": clean_filename,
            "bucket": bucket,
            "key": object_key,
            "s3_uri": s3_uri,
            "web_link": s3_uri,
            "http_link": web_link,
            "provider": "s3_storage",
            "bytes_uploaded": total_bytes
        }
    except Exception as e:
        logger.error(f"Error subiendo '{filepath}' a S3 ({bucket}): {e}", exc_info=True)
        return False, {"error": f"Error subiendo a S3: {e}"}
