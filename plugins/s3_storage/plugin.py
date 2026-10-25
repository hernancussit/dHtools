"""
Plugin Oficial de Almacenamiento S3 para dHtools.
Permite sincronizar y respaldar descargas multimedia en cualquier almacenamiento compatible con S3
(AWS S3, MinIO, Cloudflare R2, Backblaze B2, Wasabi) con streaming multipart (RAM-Safe),
modo Safe Offload opcional, aislamiento multi-usuario estricto y soporte para el Bot de Telegram.
"""

import os
import json
import time
import logging
import threading
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List
from flask import Blueprint, jsonify, request, render_template, redirect, url_for, session, has_request_context

from core.state import JOBS, JOBS_LOCK
from core.utils import load_downloads_meta, save_downloads_meta, load_cloud_config
from core.config import DOWNLOAD_DIR

# Import local client
try:
    from . import s3_client
except (ImportError, ValueError):
    import s3_client

logger = logging.getLogger("dhtools.plugins.s3_storage")


class Plugin:
    """Clase principal del Plugin de S3 Storage."""

    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.metadata = metadata or {}
        self.plugin_id = self.metadata.get("id", "s3_storage")
        self.name = self.metadata.get("name", "S3 Object Storage")
        self.version = self.metadata.get("version", "1.0.0")
        self._lock = threading.RLock()

        # Determinar directorio base del plugin
        self.plugin_dir = self.metadata.get("_path")
        if not self.plugin_dir or not os.path.isdir(self.plugin_dir):
            self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

        self.users_data_dir = os.path.join(self.plugin_dir, "users_data")
        try:
            os.makedirs(self.users_data_dir, exist_ok=True)
        except Exception:
            pass

        self.config_path = os.path.join(self.plugin_dir, "config.json")
        logger.info(f"Inicializando {self.name} v{self.version} en '{self.plugin_dir}'")

    # =========================================================================
    # GESTIÓN DE CONFIGURACIÓN Y AISLAMIENTO MULTI-USUARIO
    # =========================================================================

    def get_user_dir(self, username: str) -> str:
        """Retorna el directorio aislado en disco para un usuario con permisos restringidos."""
        raw_user = (username or "admin").strip().lower()
        safe_user = "".join(c for c in raw_user if c.isalnum() or c in ("-", "_")).strip() or "admin"
        udir = os.path.join(self.users_data_dir, safe_user)
        os.makedirs(udir, exist_ok=True)
        try:
            os.chmod(udir, 0o700)
        except Exception:
            pass
        return udir

    def get_server_config(self) -> Dict[str, Any]:
        """Carga la configuración base a nivel servidor o hereda de cloud_sync.json global."""
        with self._lock:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Error leyendo {self.config_path}: {e}")

            # Heredar de la configuración global de dHtools si existe
            try:
                global_cloud = load_cloud_config()
                if "s3" in global_cloud and isinstance(global_cloud["s3"], dict):
                    s3_base = global_cloud["s3"]
                    return {
                        "enabled": bool(s3_base.get("enabled", False)),
                        "auto_upload": False,
                        "safe_offload": False,
                        "endpoint_url": s3_base.get("endpoint_url", ""),
                        "bucket_name": s3_base.get("bucket_name") or s3_base.get("bucket") or "",
                        "access_key": s3_base.get("access_key", ""),
                        "secret_key": s3_base.get("secret_key", ""),
                        "region": s3_base.get("region", "us-east-1"),
                        "remote_dir": s3_base.get("remote_dir", "")
                    }
            except Exception:
                pass

            return {
                "enabled": False,
                "auto_upload": False,
                "safe_offload": False,
                "endpoint_url": "",
                "bucket_name": "",
                "access_key": "",
                "secret_key": "",
                "region": "us-east-1",
                "remote_dir": ""
            }

    def get_user_config(self, username: str) -> Dict[str, Any]:
        """Obtiene la configuración específica del usuario con herencia de servidor."""
        safe_u = (username or "admin").strip().lower()
        u_dir = self.get_user_dir(safe_u)
        u_cfg_path = os.path.join(u_dir, "config.json")

        server_cfg = self.get_server_config()
        u_cfg = {}

        with self._lock:
            if os.path.exists(u_cfg_path):
                try:
                    with open(u_cfg_path, "r", encoding="utf-8") as f:
                        u_cfg = json.load(f)
                except Exception as e:
                    logger.error(f"Error leyendo config S3 para usuario {safe_u}: {e}")

        # Herencia segura
        endpoint = u_cfg.get("endpoint_url")
        if endpoint is None:
            endpoint = server_cfg.get("endpoint_url", "")

        bucket = u_cfg.get("bucket_name") or u_cfg.get("bucket")
        if bucket is None:
            bucket = server_cfg.get("bucket_name") or server_cfg.get("bucket") or ""

        access_key = u_cfg.get("access_key")
        if access_key is None:
            access_key = server_cfg.get("access_key", "")

        secret_key = u_cfg.get("secret_key")
        if secret_key is None:
            secret_key = server_cfg.get("secret_key", "")

        region = u_cfg.get("region")
        if region is None:
            region = server_cfg.get("region", "us-east-1")

        remote_dir = u_cfg.get("remote_dir") or u_cfg.get("prefix")
        if remote_dir is None:
            remote_dir = server_cfg.get("remote_dir", "")

        return {
            "enabled": bool(u_cfg.get("enabled", False) if "enabled" in u_cfg else server_cfg.get("enabled", False)),
            "auto_upload": bool(u_cfg.get("auto_upload", False)),
            "safe_offload": bool(u_cfg.get("safe_offload", False)),
            "endpoint_url": endpoint.strip() if isinstance(endpoint, str) else "",
            "bucket_name": bucket.strip() if isinstance(bucket, str) else "",
            "access_key": access_key.strip() if isinstance(access_key, str) else "",
            "secret_key": secret_key.strip() if isinstance(secret_key, str) else "",
            "region": region.strip() if isinstance(region, str) else "us-east-1",
            "remote_dir": remote_dir.strip("/ ") if isinstance(remote_dir, str) else ""
        }

    def save_user_config(self, username: str, new_cfg: Dict[str, Any]) -> bool:
        """Guarda la configuración personalizada del usuario en disco con permisos 0600."""
        safe_u = (username or "admin").strip().lower()
        u_dir = self.get_user_dir(safe_u)
        u_cfg_path = os.path.join(u_dir, "config.json")

        with self._lock:
            try:
                with open(u_cfg_path, "w", encoding="utf-8") as f:
                    json.dump(new_cfg, f, indent=2, ensure_ascii=False)
                try:
                    os.chmod(u_cfg_path, 0o600)
                except Exception:
                    pass

                # Si es el usuario admin, actualizar también config.json del plugin
                if safe_u == "admin":
                    try:
                        with open(self.config_path, "w", encoding="utf-8") as f:
                            json.dump(new_cfg, f, indent=2, ensure_ascii=False)
                        try:
                            os.chmod(self.config_path, 0o600)
                        except Exception:
                            pass
                    except Exception:
                        pass
                return True
            except Exception as e:
                logger.error(f"Error guardando config S3 para usuario {safe_u}: {e}")
                return False

    def _get_request_username(self) -> Optional[str]:
        """Determina de forma estricta el usuario autenticado en la sesión actual. Retorna None si no está autenticado."""
        try:
            if not has_request_context():
                return None
            user = getattr(request, "current_user", {}) or {}
            u = user.get("username") or getattr(request, "current_username", None)
            if not u:
                u = session.get("username")
            return u.strip().lower() if u else None
        except Exception:
            return None

    def _append_job_log(self, job_id: Optional[str], msg: str):
        if not job_id:
            return
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                if "logs" not in job:
                    job["logs"] = []
                job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": msg})
                if len(job["logs"]) > 150:
                    job["logs"] = job["logs"][-150:]

    # =========================================================================
    # PROTOCOLO CLOUD STORAGE PROVIDER (DHTOOLS INTEROP)
    # =========================================================================

    def get_download_cloud_option(self, username: Optional[str] = None) -> Dict[str, Any]:
        """Informa a dHtools y al Bot de Telegram el estado y disponibilidad de S3."""
        target_user = (username or self._get_request_username() or "admin").strip().lower()
        cfg = self.get_user_config(target_user)

        has_creds = bool(cfg.get("bucket_name") and cfg.get("access_key") and cfg.get("secret_key"))
        is_enabled = bool(cfg.get("enabled", False) and has_creds)
        auto_up = bool(cfg.get("auto_upload", False) and is_enabled)

        if is_enabled:
            status = "ACTIVO (Subida Automática)" if auto_up else "ACTIVO (Subida Manual)"
        elif has_creds:
            status = "CONFIGURADO (Desactivado)"
        else:
            status = "NO CONFIGURADO"

        return {
            "plugin_id": self.plugin_id,
            "name": "S3 Storage",
            "icon": "🪣",
            "enabled": is_enabled,
            "auto_upload": auto_up,
            "status_label": status,
            "settings_url": f"/plugin/{self.plugin_id}/settings"
        }

    def upload_job_for_user(
        self,
        job_id: str,
        username: str,
        progress_callback=None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Sube una descarga al bucket S3 del usuario.
        Aplica modo Safe Offload si está activo y valida propiedad del trabajo (Prevención IDOR).
        """
        target_user = (username or "admin").strip().lower()
        cfg = self.get_user_config(target_user)

        # 1. Localizar archivo y verificar propiedad (Prevención IDOR)
        file_path = None
        file_name = None
        target_owner = None

        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                file_path = job.get("filepath")
                file_name = job.get("filename")
                target_owner = job.get("owner")

        meta = load_downloads_meta()
        if job_id in meta:
            m_info = meta[job_id]
            if not file_path:
                file_path = m_info.get("filepath")
            if not file_name:
                file_name = m_info.get("filename")
            target_owner = target_owner or m_info.get("username") or m_info.get("owner")

        # Seguridad / IDOR: Solo el dueño o admin pueden gestionar el archivo
        is_admin = (target_user == "admin")
        if has_request_context():
            try:
                current_user = getattr(request, "current_user", {}) or {}
                if not current_user and "role" in session:
                    is_admin = is_admin or (session.get("role") == "admin")
                else:
                    is_admin = is_admin or (current_user.get("role") == "admin")
            except Exception:
                pass

        if target_owner and not is_admin and target_owner.lower() != target_user:
            logger.warning(f"[Security] Denegada subida en S3: usuario '{target_user}' intentó acceder al archivo de '{target_owner}' (job {job_id})")
            return False, {"error": "No tienes permiso para gestionar ni transferir este archivo ajeno.", "status_code": 403}

        # 2. Validar credenciales
        if not cfg.get("bucket_name") or not cfg.get("access_key") or not cfg.get("secret_key"):
            return False, {"error": "Credenciales o bucket S3 no configurados.", "status_code": 400}

        if not file_path and os.path.exists(DOWNLOAD_DIR):
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(f"{job_id}_") or f.startswith(job_id):
                    cand = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.isfile(cand):
                        file_path = cand
                        file_name = f
                        break

        if not file_path or not os.path.exists(file_path):
            return False, {"error": f"No se encontró el archivo local para la descarga '{job_id}'.", "status_code": 404}

        # 3. Subir archivo a S3
        self._append_job_log(job_id, f"[*] [S3] Iniciando subida a bucket '{cfg.get('bucket_name')}'...")

        up_ok, up_res = s3_client.upload_file_multipart(
            filepath=file_path,
            filename=file_name,
            config=cfg,
            progress_callback=progress_callback
        )

        if not up_ok:
            err_msg = up_res.get("error", "Fallo subiendo archivo a S3")
            self._append_job_log(job_id, f"[!] [S3] Error en transferencia: {err_msg}")
            return False, up_res

        s3_uri = up_res.get("s3_uri", "")
        self._append_job_log(job_id, f"[+] [S3] Archivo transferido con éxito: {s3_uri}")

        # 4. Actualizar metadata y Safe Offload
        safe_offload = bool(cfg.get("safe_offload", False))

        meta = load_downloads_meta()
        if job_id in meta:
            meta[job_id]["cloud_synced"] = True
            meta[job_id]["cloud_provider"] = "s3_storage"
            meta[job_id]["cloud_link"] = s3_uri
            if safe_offload:
                meta[job_id]["offloaded"] = True
                meta[job_id]["offload_provider"] = "s3_storage"
                meta[job_id]["filepath"] = None
            save_downloads_meta(meta)

        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["cloud_synced"] = True
                JOBS[job_id]["cloud_link"] = s3_uri
                if safe_offload:
                    JOBS[job_id]["offloaded"] = True
                    JOBS[job_id]["filepath"] = None

        if safe_offload:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"[Safe Offload] Archivo local eliminado tras subida a S3: {file_path}")
                    self._append_job_log(job_id, f"[+] [Safe Offload] Archivo local eliminado del VPS. Respaldado en {s3_uri}")
            except Exception as ex:
                logger.warning(f"[Safe Offload] No se pudo borrar archivo local tras subida a S3: {ex}")

        return True, {
            "success": True,
            "filename": file_name,
            "web_link": s3_uri,
            "s3_uri": s3_uri,
            "offloaded": safe_offload,
            "provider": "s3_storage"
        }

    def upload_file_for_user(
        self,
        filepath: str,
        username: str,
        progress_callback=None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Sube cualquier archivo arbitrario en disco al bucket S3 del usuario."""
        if not filepath or not os.path.isfile(filepath):
            return False, {"error": f"El archivo no existe o no es accesible: '{filepath}'"}

        target_user = (username or "admin").strip().lower()
        cfg = self.get_user_config(target_user)

        if not cfg.get("bucket_name") or not cfg.get("access_key") or not cfg.get("secret_key"):
            return False, {"error": "Credenciales o bucket S3 no configurados."}

        return s3_client.upload_file_multipart(
            filepath=filepath,
            filename=os.path.basename(filepath),
            config=cfg,
            progress_callback=progress_callback
        )

    def get_user_nav_item(self, username: Optional[str] = None) -> Dict[str, Any]:
        """Genera el acceso directo para el sidebar y menú móvil."""
        return {
            "id": self.plugin_id,
            "title": "S3 Storage",
            "full_title": "S3 Object Storage",
            "icon": "🪣",
            "url": f"/plugin/{self.plugin_id}/settings"
        }

    def get_admin_cloud_panel(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Inyecta la tarjeta de S3 Storage en la pestaña Cloud Sync de /admin."""
        cfg = config or self.get_server_config()
        is_enabled = cfg.get("enabled", False)
        bucket = cfg.get("bucket_name") or cfg.get("bucket") or "No configurado"
        endpoint = cfg.get("endpoint_url") or "AWS S3 Oficial"

        status_badge = (
            '<span style="background:rgba(16,185,129,0.2); color:#10b981; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:700;">ACTIVO</span>'
            if is_enabled else
            '<span style="background:rgba(107,114,128,0.2); color:#9ca3af; padding:2px 8px; border-radius:4px; font-size:0.75rem;">DESACTIVADO</span>'
        )

        html = f"""
        <div style="font-size:0.83rem; color:var(--muted); line-height:1.6;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span>Estado: {status_badge}</span>
            <span>Bucket: <strong style="color:var(--text);">{bucket}</strong></span>
          </div>
          <div>Endpoint: <code style="color:var(--accent-blue);">{endpoint}</code></div>
          <div style="margin-top:8px; font-size:0.78rem;">
            Soporta AWS S3, MinIO, Cloudflare R2, Backblaze B2 y Wasabi con subida multipart en streaming.
          </div>
        </div>
        """

        return {
            "id": self.plugin_id,
            "title": "S3 Object Storage",
            "icon": "🪣",
            "badge": "OFICIAL",
            "settings_url": f"/plugin/{self.plugin_id}/settings",
            "html_content": html
        }

    def on_download_complete(self, job_data: Dict[str, Any]):
        """
        Gancho ejecutado tras completarse cualquier descarga.
        Sube el archivo a S3 si está activado para el usuario (auto_upload o marcado en descarga).
        """
        owner = job_data.get("owner", "admin")
        user_cfg = self.get_user_config(owner)

        if not user_cfg.get("enabled", False):
            return

        user_cloud = job_data.get("user_cloud_sync") or {}
        plugin_prefs = (user_cloud.get("plugins") or {}).get(self.plugin_id) or {}
        legacy_s3_prefs = user_cloud.get("s3") or {}

        is_auto = user_cfg.get("auto_upload", False)
        is_job_checked = plugin_prefs.get("enabled", False) or legacy_s3_prefs.get("enabled", False)

        if not is_auto and not is_job_checked:
            return

        job_id = job_data.get("job_id") or job_data.get("id")
        self.upload_job_for_user(job_id=job_id, username=owner)

    # =========================================================================
    # RUTAS FLASK (BLUEPRINT)
    # =========================================================================

    def register_routes(self, app):
        """Registra las rutas del Blueprint del plugin bajo /plugin/s3_storage/."""
        bp = Blueprint(
            f"plugin_{self.plugin_id}",
            __name__,
            template_folder=os.path.join(self.plugin_dir, "templates")
        )

        @bp.route("/settings")
        def view_settings():
            username = self._get_request_username()
            if not username:
                try:
                    return redirect(url_for("auth_bp.login", next=request.full_path))
                except Exception:
                    return redirect(f"/login?next={urllib.parse.quote(request.full_path)}")

            cfg = self.get_user_config(username)

            # Sanitización de credenciales: NUNCA exponer secret_key en texto plano al DOM
            template_cfg = dict(cfg)
            has_secret = bool(template_cfg.get("secret_key"))
            template_cfg["has_secret_key"] = has_secret
            template_cfg["secret_key"] = ""  # Sanitizado

            return render_template(
                "s3_storage/settings.html",
                plugin_id=self.plugin_id,
                name=self.name,
                version=self.version,
                config=template_cfg,
                username=username
            )

        @bp.route("/api/settings", methods=["POST"])
        def api_save_settings():
            username = self._get_request_username()
            if not username:
                return jsonify({"success": False, "error": "Autenticación requerida."}), 401

            data = request.get_json(silent=True) or request.form.to_dict()
            current_cfg = self.get_user_config(username)

            current_cfg["enabled"] = bool(data.get("enabled", False))
            current_cfg["auto_upload"] = bool(data.get("auto_upload", False))
            current_cfg["safe_offload"] = bool(data.get("safe_offload", False))
            current_cfg["endpoint_url"] = str(data.get("endpoint_url", "")).strip()
            current_cfg["bucket_name"] = str(data.get("bucket_name", "")).strip()
            current_cfg["access_key"] = str(data.get("access_key", "")).strip()
            current_cfg["region"] = str(data.get("region", "us-east-1")).strip() or "us-east-1"
            current_cfg["remote_dir"] = str(data.get("remote_dir", "")).strip("/ ")

            # Preservar secret_key existente si no se envió uno nuevo
            new_secret = str(data.get("secret_key", "")).strip()
            if new_secret:
                current_cfg["secret_key"] = new_secret

            ok = self.save_user_config(username, current_cfg)
            if ok:
                return jsonify({"success": True, "message": "Configuración de S3 guardada correctamente."})
            return jsonify({"success": False, "error": "No se pudo guardar la configuración en disco."}), 500

        @bp.route("/api/test", methods=["POST"])
        def api_test_connection():
            username = self._get_request_username()
            if not username:
                return jsonify({"success": False, "error": "Autenticación requerida."}), 401

            data = request.get_json(silent=True) or request.form.to_dict() or {}
            cfg = self.get_user_config(username)

            # Si se enviaron datos puntuales de prueba, combinarlos
            test_cfg = dict(cfg)
            for k in ["endpoint_url", "bucket_name", "access_key", "region", "remote_dir"]:
                if k in data and str(data[k]).strip():
                    test_cfg[k] = str(data[k]).strip()
            if data.get("secret_key") and str(data["secret_key"]).strip():
                test_cfg["secret_key"] = str(data["secret_key"]).strip()

            ok, msg = s3_client.test_connection(test_cfg)
            if ok:
                return jsonify({"success": True, "message": msg})
            return jsonify({"success": False, "error": msg}), 400

        @bp.route("/api/upload/<job_id>", methods=["POST"])
        def api_upload_job(job_id):
            username = self._get_request_username()
            if not username:
                return jsonify({"success": False, "error": "Autenticación requerida."}), 401

            ok, res = self.upload_job_for_user(job_id=job_id, username=username)
            if ok:
                return jsonify({"success": True, "result": res})
            status_code = res.get("status_code", 400) if isinstance(res, dict) else 400
            err_msg = res.get("error", "Error subiendo archivo a S3") if isinstance(res, dict) else str(res)
            return jsonify({"success": False, "error": err_msg}), status_code

        app.register_blueprint(bp, url_prefix=f"/plugin/{self.plugin_id}")
        logger.info(f"Rutas de {self.name} registradas bajo /plugin/{self.plugin_id}/")
