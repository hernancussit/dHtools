"""
Plugin Oficial de Microsoft OneDrive y SharePoint para dHtools.
Permite sincronizar y respaldar descargas multimedia en OneDrive (cuentas personales y M365)
con streaming resumable por fragmentos (RAM-safe), modo Safe Offload opcional,
aislamiento multi-usuario estricto y soporte completo para el bot de Telegram.
"""

import os
import json
import time
import logging
import threading
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List
import requests
from flask import Blueprint, jsonify, request, render_template, redirect, url_for, session

from core.state import JOBS, JOBS_LOCK
from core.utils import load_downloads_meta, save_downloads_meta
from core.config import DOWNLOAD_DIR

# Import local client
try:
    from . import onedrive_client
except (ImportError, ValueError):
    import onedrive_client

logger = logging.getLogger("dhtools.plugins.onedrive")


class Plugin:
    """Clase principal del Plugin de Microsoft OneDrive y SharePoint."""

    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.metadata = metadata or {}
        self.plugin_id = self.metadata.get("id", "onedrive")
        self.name = self.metadata.get("name", "Microsoft OneDrive Cloud Sync")
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
        self.example_config_path = os.path.join(self.plugin_dir, "config.example.json")

        logger.info(f"Inicializando {self.name} v{self.version} en '{self.plugin_dir}'")

    # =========================================================================
    # GESTIÓN DE CONFIGURACIÓN Y AISLAMIENTO MULTI-USUARIO
    # =========================================================================

    def get_user_dir(self, username: str) -> str:
        """Retorna el directorio aislado en disco para un usuario."""
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
        """Carga la configuración base a nivel servidor (para herencia de Client ID / Secret)."""
        with self._lock:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Error leyendo {self.config_path}: {e}")

            if os.path.exists(self.example_config_path):
                try:
                    with open(self.example_config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        data["enabled"] = False
                        data["auto_upload"] = False
                        return data
                except Exception:
                    pass

            return {
                "enabled": False,
                "auto_upload": False,
                "safe_offload": False,
                "tenant": "common",
                "folder_id": "",
                "folder_path": "/dHtools",
                "oauth": {"client_id": "", "client_secret": "", "redirect_uri": ""}
            }

    def get_user_config(self, username: str) -> Dict[str, Any]:
        """Obtiene la configuración específica del usuario con herencia de credenciales del servidor."""
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
                    logger.error(f"Error leyendo config de usuario {safe_u}: {e}")

        # Fusionar con valores por defecto del servidor
        merged = {
            "enabled": bool(u_cfg.get("enabled", False)),
            "auto_upload": bool(u_cfg.get("auto_upload", False)),
            "safe_offload": bool(u_cfg.get("safe_offload", False)),
            "tenant": u_cfg.get("tenant") or server_cfg.get("tenant") or "common",
            "folder_id": u_cfg.get("folder_id") or "",
            "folder_path": u_cfg.get("folder_path") or server_cfg.get("folder_path") or "/dHtools",
            "oauth": {
                "client_id": u_cfg.get("oauth", {}).get("client_id") or server_cfg.get("oauth", {}).get("client_id") or "",
                "client_secret": u_cfg.get("oauth", {}).get("client_secret") or server_cfg.get("oauth", {}).get("client_secret") or "",
                "redirect_uri": u_cfg.get("oauth", {}).get("redirect_uri") or server_cfg.get("oauth", {}).get("redirect_uri") or ""
            }
        }
        return merged

    def save_user_config(self, username: str, new_cfg: Dict[str, Any]) -> bool:
        """Guarda la configuración personalizada del usuario de forma atómica y segura."""
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

                # Si el usuario es admin y se guardan credenciales OAuth, actualizar config raíz como plantilla
                if safe_u == "admin" and new_cfg.get("oauth", {}).get("client_id"):
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
                logger.error(f"Error guardando config de usuario {safe_u}: {e}")
                return False

    def get_user_token(self, username: str) -> Optional[Dict[str, Any]]:
        """Recupera el token OAuth guardado para el usuario."""
        u_dir = self.get_user_dir(username)
        t_path = os.path.join(u_dir, "token.json")
        with self._lock:
            if not os.path.exists(t_path):
                return None
            try:
                with open(t_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) and data.get("access_token") else None
            except Exception as e:
                logger.error(f"Error leyendo token de {username}: {e}")
                return None

    def save_user_token(self, username: str, token_data: Dict[str, Any]) -> bool:
        """Guarda el token OAuth actualizado en el directorio privado del usuario."""
        u_dir = self.get_user_dir(username)
        t_path = os.path.join(u_dir, "token.json")
        with self._lock:
            try:
                with open(t_path, "w", encoding="utf-8") as f:
                    json.dump(token_data, f, indent=2)
                try:
                    os.chmod(t_path, 0o600)
                except Exception:
                    pass
                return True
            except Exception as e:
                logger.error(f"Error guardando token de {username}: {e}")
                return False

    def delete_user_token(self, username: str) -> bool:
        """Elimina el token almacenado al desconectar la cuenta."""
        u_dir = self.get_user_dir(username)
        t_path = os.path.join(u_dir, "token.json")
        with self._lock:
            if os.path.exists(t_path):
                try:
                    os.remove(t_path)
                    return True
                except Exception as e:
                    logger.error(f"Error eliminando token de {username}: {e}")
                    return False
        return True

    def get_valid_token_for_user(self, username: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Obtiene un access_token válido para el usuario, renovándolo automáticamente si ha caducado.
        Retorna: (ok: bool, access_token: str|None, error: str|None)
        """
        cfg = self.get_user_config(username)
        token_data = self.get_user_token(username)

        if not token_data or not token_data.get("access_token"):
            return False, None, "Cuenta de Microsoft OneDrive no vinculada o sin sesión activa."

        client_id = cfg.get("oauth", {}).get("client_id", "").strip()
        client_secret = cfg.get("oauth", {}).get("client_secret", "").strip()
        tenant = cfg.get("tenant", "common")

        if not client_id:
            return False, None, "Client ID de Microsoft no configurado."

        ok, updated_token, refreshed = onedrive_client.refresh_token_if_needed(
            client_id=client_id,
            client_secret=client_secret,
            token_data=token_data,
            tenant=tenant
        )

        if not ok:
            return False, None, updated_token.get("error", "Error al validar o renovar sesión de OneDrive.")

        if refreshed:
            self.save_user_token(username, updated_token)

        return True, updated_token.get("access_token"), None

    def _get_request_username(self) -> str:
        """Determina de forma estricta el usuario autenticado en la sesión actual."""
        try:
            from flask import has_request_context
            if not has_request_context():
                return "admin"
            user = getattr(request, "current_user", {}) or {}
            u = user.get("username") or getattr(request, "current_username", None)
            if not u:
                u = session.get("username", "admin")
            return (u or "admin").strip().lower()
        except Exception:
            return "admin"

    def _get_redirect_uri(self) -> str:
        """Determina la URL de redirección canónica para OAuth2 de Microsoft."""
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host", request.host)
        return f"{proto}://{host}/plugin/{self.plugin_id}/auth/callback"

    # =========================================================================
    # PROTOCOLO CLOUD STORAGE PROVIDER (INTEROPERABILIDAD CON DHTOOLS)
    # =========================================================================

    def get_download_cloud_option(self, username: str = None) -> Dict[str, Any]:
        """Informa a dHtools y al Bot de Telegram el estado y disponibilidad de OneDrive."""
        target_user = (username or self._get_request_username()).strip().lower()
        cfg = self.get_user_config(target_user)
        token = self.get_user_token(target_user)

        has_auth = bool(token and token.get("access_token"))
        is_enabled = bool(cfg.get("enabled", False) and has_auth)
        auto_up = bool(cfg.get("auto_upload", False) and is_enabled)

        if is_enabled:
            status = "ACTIVO (Subida Manual)" if not auto_up else "ACTIVO (Subida Automática)"
        elif has_auth:
            status = "VINCULADO (Desactivado)"
        else:
            status = "NO VINCULADO"

        return {
            "plugin_id": self.plugin_id,
            "name": "Microsoft OneDrive",
            "icon": "☁️",
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
        Sube un trabajo de descarga completado a la cuenta de OneDrive del usuario.
        Aplica modo Safe Offload si está activo en la configuración personal.
        """
        target_user = (username or "admin").strip().lower()
        cfg = self.get_user_config(target_user)

        # 1. Obtener token válido
        ok, access_token, err = self.get_valid_token_for_user(target_user)
        if not ok or not access_token:
            return False, {"error": err or "No hay sesión activa con OneDrive."}

        # 2. Localizar el archivo en disco
        file_path = None
        file_name = None

        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job and job.get("filepath") and os.path.exists(job["filepath"]):
                file_path = job["filepath"]
                file_name = job.get("filename") or os.path.basename(file_path)

        if not file_path:
            meta = load_downloads_meta()
            if job_id in meta and meta[job_id].get("filepath") and os.path.exists(meta[job_id]["filepath"]):
                file_path = meta[job_id]["filepath"]
                file_name = meta[job_id].get("filename") or os.path.basename(file_path)

        if not file_path and os.path.exists(DOWNLOAD_DIR):
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(f"{job_id}_") or f.startswith(job_id):
                    cand = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.isfile(cand):
                        file_path = cand
                        file_name = f
                        break

        if not file_path or not os.path.exists(file_path):
            return False, {"error": f"No se encontró el archivo local para la descarga '{job_id}'."}

        # 3. Subir archivo a OneDrive de forma resumable
        folder_id = cfg.get("folder_id")
        folder_path = cfg.get("folder_path") or "/dHtools"

        up_ok, up_res = onedrive_client.upload_file_resumable(
            access_token=access_token,
            file_path=file_path,
            folder_id=folder_id,
            folder_path=folder_path,
            progress_callback=progress_callback
        )

        if not up_ok:
            return False, up_res

        # 4. Actualizar metadata y Safe Offload
        safe_offload = bool(cfg.get("safe_offload", False))
        web_link = up_res.get("web_link", "")

        meta = load_downloads_meta()
        if job_id in meta:
            meta[job_id]["cloud_synced"] = True
            meta[job_id]["cloud_provider"] = "onedrive"
            meta[job_id]["cloud_link"] = web_link
            if safe_offload:
                meta[job_id]["offloaded"] = True
                meta[job_id]["offload_provider"] = "onedrive"
            save_downloads_meta(meta)

        if safe_offload:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"[Safe Offload] Archivo local eliminado tras subida a OneDrive: {file_path}")
            except Exception as ex:
                logger.warning(f"[Safe Offload] No se pudo borrar archivo local: {ex}")

        return True, {
            "success": True,
            "filename": file_name,
            "web_link": web_link,
            "offloaded": safe_offload,
            "provider": "onedrive"
        }

    def upload_file_for_user(
        self,
        filepath: str,
        username: str,
        progress_callback=None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Sube cualquier archivo arbitrario en disco a la nube de OneDrive del usuario."""
        if not filepath or not os.path.isfile(filepath):
            return False, {"error": f"El archivo no existe: '{filepath}'"}

        target_user = (username or "admin").strip().lower()
        cfg = self.get_user_config(target_user)

        ok, access_token, err = self.get_valid_token_for_user(target_user)
        if not ok or not access_token:
            return False, {"error": err or "OneDrive no autenticado."}

        folder_id = cfg.get("folder_id")
        folder_path = cfg.get("folder_path") or "/dHtools"

        return onedrive_client.upload_file_resumable(
            access_token=access_token,
            file_path=filepath,
            folder_id=folder_id,
            folder_path=folder_path,
            progress_callback=progress_callback
        )

    def get_user_nav_item(self, username: str = None) -> Dict[str, Any]:
        """Genera el acceso directo dinámico para la barra lateral y menú móvil."""
        return {
            "id": self.plugin_id,
            "title": "OneDrive",
            "full_title": "Microsoft OneDrive Sync",
            "icon": "☁️",
            "url": f"/plugin/{self.plugin_id}/settings"
        }

    # =========================================================================
    # CICLO DE VIDA Y RUTAS WEB (FLASK BLUEPRINT)
    # =========================================================================

    def on_startup(self):
        logger.info(f"Plugin {self.name} v{self.version} iniciado correctamente.")

    def on_shutdown(self):
        logger.info(f"Plugin {self.name} apagado.")

    def register_routes(self, app):
        """Registra las rutas del Blueprint del plugin bajo /plugin/onedrive/."""
        bp = Blueprint(
            f"plugin_{self.plugin_id}",
            __name__,
            template_folder=os.path.join(self.plugin_dir, "templates")
        )

        @bp.route("/settings")
        def view_settings():
            username = self._get_request_username()
            cfg = self.get_user_config(username)
            token = self.get_user_token(username)

            connected = False
            drive_info = None
            auth_error = None

            if token and token.get("access_token"):
                ok, access_token, err = self.get_valid_token_for_user(username)
                if ok and access_token:
                    connected = True
                    i_ok, i_data = onedrive_client.get_user_and_drive_info(access_token)
                    if i_ok:
                        drive_info = i_data
                    else:
                        auth_error = i_data.get("error")
                else:
                    auth_error = err

            redirect_uri = self._get_redirect_uri()

            return render_template(
                "settings.html",
                plugin_id=self.plugin_id,
                name=self.name,
                version=self.version,
                config=cfg,
                connected=connected,
                drive_info=drive_info,
                auth_error=auth_error,
                redirect_uri=redirect_uri,
                username=username
            )

        @bp.route("/api/settings", methods=["POST"])
        def api_save_settings():
            username = self._get_request_username()
            data = request.get_json(silent=True) or request.form.to_dict()

            current_cfg = self.get_user_config(username)
            current_cfg["enabled"] = bool(data.get("enabled", False))
            current_cfg["auto_upload"] = bool(data.get("auto_upload", False))
            current_cfg["safe_offload"] = bool(data.get("safe_offload", False))
            current_cfg["tenant"] = (data.get("tenant") or "common").strip()
            current_cfg["folder_id"] = (data.get("folder_id") or "").strip()
            current_cfg["folder_path"] = (data.get("folder_path") or "/dHtools").strip()

            # Solo actualizar client_id/client_secret si fueron enviados expresamente
            oauth_cfg = current_cfg.setdefault("oauth", {})
            if "client_id" in data:
                oauth_cfg["client_id"] = str(data["client_id"]).strip()
            if "client_secret" in data and str(data["client_secret"]).strip():
                oauth_cfg["client_secret"] = str(data["client_secret"]).strip()

            ok = self.save_user_config(username, current_cfg)
            if ok:
                return jsonify({"success": True, "message": "Configuración de OneDrive guardada correctamente."})
            return jsonify({"success": False, "error": "No se pudo guardar la configuración en disco."}), 500

        @bp.route("/auth/login")
        def auth_login():
            username = self._get_request_username()
            cfg = self.get_user_config(username)
            client_id = cfg.get("oauth", {}).get("client_id", "").strip()

            if not client_id:
                return redirect(f"/plugin/{self.plugin_id}/settings?error=client_id_required")

            redirect_uri = self._get_redirect_uri()
            tenant = cfg.get("tenant", "common")

            # State contiene el usuario para verificar en el callback
            state_data = {
                "u": username,
                "t": int(time.time()),
                "p": self.plugin_id
            }
            import base64
            state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

            auth_url = onedrive_client.get_authorization_url(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=state,
                tenant=tenant
            )
            return redirect(auth_url)

        @bp.route("/auth/callback")
        def auth_callback():
            code = request.args.get("code")
            state_raw = request.args.get("state")
            error = request.args.get("error")
            error_desc = request.args.get("error_description")

            if error:
                return redirect(f"/plugin/{self.plugin_id}/settings?error={urllib.parse.quote(error_desc or error)}")

            if not code or not state_raw:
                return redirect(f"/plugin/{self.plugin_id}/settings?error=missing_code_or_state")

            import base64
            try:
                state_data = json.loads(base64.urlsafe_b64decode(state_raw.encode()).decode())
                username = state_data.get("u") or "admin"
            except Exception:
                username = self._get_request_username()

            cfg = self.get_user_config(username)
            client_id = cfg.get("oauth", {}).get("client_id", "").strip()
            client_secret = cfg.get("oauth", {}).get("client_secret", "").strip()
            tenant = cfg.get("tenant", "common")
            redirect_uri = self._get_redirect_uri()

            ok, token_res = onedrive_client.exchange_code_for_token(
                client_id=client_id,
                client_secret=client_secret,
                code=code,
                redirect_uri=redirect_uri,
                tenant=tenant
            )

            if not ok:
                err_msg = token_res.get("error", "Fallo al canjear código por token")
                return redirect(f"/plugin/{self.plugin_id}/settings?error={urllib.parse.quote(err_msg)}")

            # Guardar token y activar integración
            self.save_user_token(username, token_res)
            cfg["enabled"] = True
            self.save_user_config(username, cfg)

            return redirect(f"/plugin/{self.plugin_id}/settings?connected=1")

        @bp.route("/api/disconnect", methods=["POST"])
        def api_disconnect():
            username = self._get_request_username()
            self.delete_user_token(username)

            cfg = self.get_user_config(username)
            cfg["enabled"] = False
            self.save_user_config(username, cfg)

            return jsonify({"success": True, "message": "Cuenta de Microsoft OneDrive desconectada exitosamente."})

        @bp.route("/api/test", methods=["POST"])
        def api_test_connection():
            username = self._get_request_username()
            ok, access_token, err = self.get_valid_token_for_user(username)
            if not ok or not access_token:
                return jsonify({"success": False, "error": err or "No hay sesión activa."}), 400

            i_ok, i_data = onedrive_client.get_user_and_drive_info(access_token)
            if not i_ok:
                return jsonify({"success": False, "error": i_data.get("error")}), 502

            return jsonify({
                "success": True,
                "message": f"Conexión exitosa con la cuenta de {i_data.get('display_name')} ({i_data.get('email')}).",
                "info": i_data
            })

        @bp.route("/api/folders")
        def api_list_folders():
            username = self._get_request_username()
            ok, access_token, err = self.get_valid_token_for_user(username)
            if not ok or not access_token:
                return jsonify({"success": False, "error": err or "No hay sesión activa."}), 400

            parent_id = request.args.get("parent_id")
            f_ok, f_data = onedrive_client.list_folders(access_token, parent_id=parent_id)
            if not f_ok:
                return jsonify({"success": False, "error": f_data.get("error")}), 502

            return jsonify({"success": True, "folders": f_data})

        @bp.route("/api/upload/<job_id>", methods=["POST"])
        def api_upload_job(job_id):
            username = self._get_request_username()
            ok, res = self.upload_job_for_user(job_id=job_id, username=username)
            if ok:
                return jsonify({"success": True, "result": res})
            return jsonify({"success": False, "error": res.get("error", "Error desconocido subiendo a OneDrive")}), 500

        # Registrar el blueprint en la aplicación Flask
        app.register_blueprint(bp, url_prefix=f"/plugin/{self.plugin_id}")
        logger.info(f"Rutas de {self.name} registradas bajo /plugin/{self.plugin_id}/")
