"""
Plugin Oficial de Almacenamiento FTP / FTPS para dHtools.
Permite sincronizar y respaldar descargas multimedia en servidores FTP / FTPS con navegación
recursiva, modo Safe Offload opcional, aislamiento multi-usuario estricto y soporte para el Bot de Telegram.
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
    from . import ftp_client
except (ImportError, ValueError):
    import ftp_client

logger = logging.getLogger("dhtools.plugins.ftp_storage")


class Plugin:
    """Clase principal del Plugin de FTP Storage."""

    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.metadata = metadata or {}
        self.plugin_id = self.metadata.get("id", "ftp_storage")
        self.name = self.metadata.get("name", "FTP / FTPS Storage")
        self.version = self.metadata.get("version", "1.0.0")
        self._lock = threading.RLock()

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
        """Retorna el directorio aislado en disco para un usuario con permisos 0700."""
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

            # Heredar de la configuración global de dHtools
            try:
                global_cloud = load_cloud_config()
                if "ftp" in global_cloud and isinstance(global_cloud["ftp"], dict):
                    ftp_base = global_cloud["ftp"]
                    return {
                        "enabled": bool(ftp_base.get("enabled", False)),
                        "auto_upload": False,
                        "safe_offload": False,
                        "host": ftp_base.get("host", ""),
                        "port": int(ftp_base.get("port", 21)),
                        "username": ftp_base.get("username", "anonymous"),
                        "password": ftp_base.get("password", ""),
                        "remote_dir": ftp_base.get("remote_dir", "/"),
                        "use_tls": bool(ftp_base.get("use_tls", False))
                    }
            except Exception:
                pass

            return {
                "enabled": False,
                "auto_upload": False,
                "safe_offload": False,
                "host": "",
                "port": 21,
                "username": "anonymous",
                "password": "",
                "remote_dir": "/",
                "use_tls": False
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
                    logger.error(f"Error leyendo config FTP para usuario {safe_u}: {e}")

        host = u_cfg.get("host") if u_cfg.get("host") is not None else server_cfg.get("host", "")
        port = u_cfg.get("port") if u_cfg.get("port") is not None else server_cfg.get("port", 21)
        u_name = u_cfg.get("username") if u_cfg.get("username") is not None else server_cfg.get("username", "anonymous")
        pwd = u_cfg.get("password") if u_cfg.get("password") is not None else server_cfg.get("password", "")
        r_dir = u_cfg.get("remote_dir") if u_cfg.get("remote_dir") is not None else server_cfg.get("remote_dir", "/")
        use_tls = u_cfg.get("use_tls") if u_cfg.get("use_tls") is not None else server_cfg.get("use_tls", False)

        try:
            port = int(port)
        except Exception:
            port = 21

        return {
            "enabled": bool(u_cfg.get("enabled", False) if "enabled" in u_cfg else server_cfg.get("enabled", False)),
            "auto_upload": bool(u_cfg.get("auto_upload", False)),
            "safe_offload": bool(u_cfg.get("safe_offload", False)),
            "host": host.strip() if isinstance(host, str) else "",
            "port": port,
            "username": u_name.strip() if isinstance(u_name, str) else "anonymous",
            "password": pwd.strip() if isinstance(pwd, str) else "",
            "remote_dir": r_dir.strip() if isinstance(r_dir, str) else "/",
            "use_tls": bool(use_tls)
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
                logger.error(f"Error guardando config FTP para usuario {safe_u}: {e}")
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
        """Informa a dHtools y al Bot de Telegram el estado y disponibilidad de FTP."""
        target_user = (username or self._get_request_username() or "admin").strip().lower()
        cfg = self.get_user_config(target_user)

        has_creds = bool(cfg.get("host"))
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
            "name": "FTP Storage",
            "icon": "🌐",
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
        Sube una descarga al servidor FTP del usuario.
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
            logger.warning(f"[Security] Denegada subida en FTP: usuario '{target_user}' intentó acceder al archivo de '{target_owner}' (job {job_id})")
            return False, {"error": "No tienes permiso para gestionar ni transferir este archivo ajeno.", "status_code": 403}

        # 2. Validar credenciales
        if not cfg.get("host"):
            return False, {"error": "Host de servidor FTP no configurado.", "status_code": 400}

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

        # 3. Subir archivo a FTP
        self._append_job_log(job_id, f"[*] [FTP] Iniciando transferencia a servidor FTP ({cfg.get('host')})...")

        up_ok, up_res = ftp_client.upload_file(
            filepath=file_path,
            filename=file_name,
            config=cfg,
            progress_callback=progress_callback
        )

        if not up_ok:
            err_msg = up_res.get("error", "Fallo subiendo archivo a FTP")
            self._append_job_log(job_id, f"[!] [FTP] Error en transferencia: {err_msg}")
            return False, up_res

        ftp_url = up_res.get("ftp_url", "")
        self._append_job_log(job_id, f"[+] [FTP] Archivo subido con éxito a FTP: {ftp_url}")

        # 4. Actualizar metadata y Safe Offload
        safe_offload = bool(cfg.get("safe_offload", False))

        meta = load_downloads_meta()
        if job_id in meta:
            meta[job_id]["cloud_synced"] = True
            meta[job_id]["cloud_provider"] = "ftp_storage"
            meta[job_id]["cloud_link"] = ftp_url
            if safe_offload:
                meta[job_id]["offloaded"] = True
                meta[job_id]["offload_provider"] = "ftp_storage"
                meta[job_id]["filepath"] = None
            save_downloads_meta(meta)

        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["cloud_synced"] = True
                JOBS[job_id]["cloud_link"] = ftp_url
                if safe_offload:
                    JOBS[job_id]["offloaded"] = True
                    JOBS[job_id]["filepath"] = None

        if safe_offload:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"[Safe Offload] Archivo local eliminado tras subida a FTP: {file_path}")
                    self._append_job_log(job_id, f"[+] [Safe Offload] Archivo local eliminado del VPS. Respaldado en FTP.")
            except Exception as ex:
                logger.warning(f"[Safe Offload] No se pudo borrar archivo local tras subida a FTP: {ex}")

        return True, {
            "success": True,
            "filename": file_name,
            "web_link": ftp_url,
            "ftp_url": ftp_url,
            "offloaded": safe_offload,
            "provider": "ftp_storage"
        }

    def upload_file_for_user(
        self,
        filepath: str,
        username: str,
        progress_callback=None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Sube cualquier archivo arbitrario en disco a FTP."""
        if not filepath or not os.path.isfile(filepath):
            return False, {"error": f"El archivo no existe o no es accesible: '{filepath}'"}

        target_user = (username or "admin").strip().lower()
        cfg = self.get_user_config(target_user)

        if not cfg.get("host"):
            return False, {"error": "Host de servidor FTP no configurado."}

        return ftp_client.upload_file(
            filepath=filepath,
            filename=os.path.basename(filepath),
            config=cfg,
            progress_callback=progress_callback
        )

    def get_user_nav_item(self, username: Optional[str] = None) -> Dict[str, Any]:
        """Genera el acceso directo para el sidebar y menú móvil."""
        return {
            "id": self.plugin_id,
            "title": "FTP Storage",
            "full_title": "FTP / FTPS Storage",
            "icon": "🌐",
            "url": f"/plugin/{self.plugin_id}/settings"
        }

    def get_admin_cloud_panel(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Inyecta la tarjeta de FTP en la pestaña Cloud Sync de /admin."""
        cfg = config or self.get_server_config()
        is_enabled = cfg.get("enabled", False)
        host_desc = cfg.get("host") or "No configurado"
        user_desc = cfg.get("username") or "anonymous"
        port_desc = cfg.get("port") or 21

        status_badge = (
            '<span style="background:rgba(16,185,129,0.2); color:#10b981; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:700;">ACTIVO</span>'
            if is_enabled else
            '<span style="background:rgba(107,114,128,0.2); color:#9ca3af; padding:2px 8px; border-radius:4px; font-size:0.75rem;">DESACTIVADO</span>'
        )

        html = f"""
        <div style="font-size:0.83rem; color:var(--muted); line-height:1.6;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span>Estado: {status_badge}</span>
            <span>Usuario: <strong style="color:var(--text);">{user_desc}</strong></span>
          </div>
          <div>Servidor: <code style="color:var(--accent-blue);">{host_desc}:{port_desc}</code></div>
          <div style="margin-top:8px; font-size:0.78rem;">
            Soporta subidas directas y navegación recursiva en servidores FTP y FTPS (TLS).
          </div>
        </div>
        """

        return {
            "id": self.plugin_id,
            "title": "FTP / FTPS Storage",
            "icon": "🌐",
            "badge": "OFICIAL",
            "settings_url": f"/plugin/{self.plugin_id}/settings",
            "html_content": html
        }

    def on_download_complete(self, job_data: Dict[str, Any]):
        """Gancho ejecutado tras completarse cualquier descarga."""
        owner = job_data.get("owner", "admin")
        user_cfg = self.get_user_config(owner)

        if not user_cfg.get("enabled", False):
            return

        user_cloud = job_data.get("user_cloud_sync") or {}
        plugin_prefs = (user_cloud.get("plugins") or {}).get(self.plugin_id) or {}
        legacy_ftp_prefs = user_cloud.get("ftp") or {}

        is_auto = user_cfg.get("auto_upload", False)
        is_job_checked = plugin_prefs.get("enabled", False) or legacy_ftp_prefs.get("enabled", False)

        if not is_auto and not is_job_checked:
            return

        job_id = job_data.get("job_id") or job_data.get("id")
        self.upload_job_for_user(job_id=job_id, username=owner)

    # =========================================================================
    # RUTAS FLASK (BLUEPRINT)
    # =========================================================================

    def register_routes(self, app):
        """Registra las rutas del Blueprint del plugin bajo /plugin/ftp_storage/."""
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

            template_cfg = dict(cfg)
            has_pwd = bool(template_cfg.get("password"))
            template_cfg["has_password"] = has_pwd
            template_cfg["password"] = ""  # Sanitizado: NUNCA enviar al DOM

            return render_template(
                "ftp_storage/settings.html",
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
            current_cfg["host"] = str(data.get("host", "")).strip()
            try:
                current_cfg["port"] = int(data.get("port", 21))
            except Exception:
                current_cfg["port"] = 21
            current_cfg["username"] = str(data.get("username", "anonymous")).strip() or "anonymous"
            current_cfg["remote_dir"] = str(data.get("remote_dir", "/")).strip()
            current_cfg["use_tls"] = bool(data.get("use_tls", False))

            new_pwd = str(data.get("password", "")).strip()
            if new_pwd:
                current_cfg["password"] = new_pwd

            ok = self.save_user_config(username, current_cfg)
            if ok:
                return jsonify({"success": True, "message": "Configuración de FTP guardada correctamente."})
            return jsonify({"success": False, "error": "No se pudo guardar la configuración en disco."}), 500

        @bp.route("/api/test", methods=["POST"])
        def api_test_connection():
            username = self._get_request_username()
            if not username:
                return jsonify({"success": False, "error": "Autenticación requerida."}), 401

            data = request.get_json(silent=True) or request.form.to_dict() or {}
            cfg = self.get_user_config(username)

            test_cfg = dict(cfg)
            for k in ["host", "port", "username", "remote_dir", "use_tls"]:
                if k in data and data[k] is not None:
                    test_cfg[k] = data[k]
            if data.get("password") and str(data["password"]).strip():
                test_cfg["password"] = str(data["password"]).strip()

            ok, msg = ftp_client.test_connection(test_cfg)
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
            err_msg = res.get("error", "Error subiendo archivo a FTP") if isinstance(res, dict) else str(res)
            return jsonify({"success": False, "error": err_msg}), status_code

        app.register_blueprint(bp, url_prefix=f"/plugin/{self.plugin_id}")
        logger.info(f"Rutas de {self.name} registradas bajo /plugin/{self.plugin_id}/")
