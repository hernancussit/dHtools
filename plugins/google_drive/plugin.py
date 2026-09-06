"""
[EXPERIMENTAL] Plugin Oficial de Google Drive para dHtools.
Permite sincronizar y respaldar descargas directamente en Google Drive
con streaming por fragmentos (RAM-safe), modo Safe Offload opcional,
aislamiento multi-usuario de credenciales y subida bajo demanda.
"""

import os
import json
import time
import base64
import logging
import threading
from urllib.parse import urlencode, quote
from typing import Dict, Any, Optional
import requests
from flask import Blueprint, jsonify, request, render_template, redirect, url_for, session

from core.state import JOBS, JOBS_LOCK
from core.utils import load_downloads_meta, save_downloads_meta
from core.config import DOWNLOAD_DIR

logger = logging.getLogger("dhtools.plugins.google_drive")


class Plugin:
    """
    [EXPERIMENTAL] Clase principal del Plugin Oficial de Google Drive.
    """
    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.metadata = metadata or {}
        self.plugin_id = self.metadata.get("id", "google_drive")
        self.name = self.metadata.get("name", "Google Drive Cloud Sync")
        self.version = self.metadata.get("version", "1.1.0")
        self._lock = threading.RLock()

        # Determinar ruta base del plugin
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

        logger.info(f"[EXPERIMENTAL] Inicializando {self.name} v{self.version} en '{self.plugin_dir}'")

    # =========================================================================
    # GESTIÓN DE CONFIGURACIÓN MULTI-USUARIO
    # =========================================================================

    def get_user_dir(self, username: str) -> str:
        """Retorna el directorio de almacenamiento aislado para un usuario."""
        raw_user = (username or "admin").strip().lower()
        safe_user = "".join(c for c in raw_user if c.isalnum() or c in ("-", "_")).strip() or "admin"
        udir = os.path.join(self.users_data_dir, safe_user)
        os.makedirs(udir, exist_ok=True)
        return udir

    def get_server_config(self) -> Dict[str, Any]:
        """Carga la configuración base o global del servidor (para herencia de OAuth App)."""
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
                "auth_type": "service_account",
                "folder_id": "",
                "safe_offload": False,
                "service_account_file": "service_account.json",
                "oauth": {"client_id": "", "client_secret": "", "token_file": "token.json"}
            }

    def get_user_config(self, username: str) -> Dict[str, Any]:
        """Carga la configuración de un usuario específico, con herencia inteligente de credenciales OAuth."""
        username = (username or "admin").strip().lower()
        udir = self.get_user_dir(username)
        u_cfg_path = os.path.join(udir, "config.json")
        server_cfg = self.get_server_config()

        with self._lock:
            cfg = None
            if os.path.exists(u_cfg_path):
                try:
                    with open(u_cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception as e:
                    logger.error(f"Error leyendo {u_cfg_path}: {e}")

            if not cfg:
                # Si es admin y existe el config.json raíz, usarlo como base inicial
                if username == "admin" and os.path.exists(self.config_path):
                    cfg = dict(server_cfg)
                else:
                    cfg = {
                        "enabled": False,
                        "auto_upload": False,
                        "auth_type": "service_account",
                        "folder_id": "",
                        "safe_offload": False,
                        "service_account_file": "service_account.json",
                        "oauth": {"client_id": "", "client_secret": "", "token_file": "token.json"}
                    }

            # Asegurar claves por defecto
            cfg.setdefault("enabled", False)
            cfg.setdefault("auto_upload", False)
            cfg.setdefault("auth_type", "service_account")
            cfg.setdefault("folder_id", "")
            cfg.setdefault("safe_offload", False)
            cfg.setdefault("service_account_file", "service_account.json")
            if "oauth" not in cfg or not isinstance(cfg["oauth"], dict):
                cfg["oauth"] = {}
            cfg["oauth"].setdefault("client_id", "")
            cfg["oauth"].setdefault("client_secret", "")
            cfg["oauth"].setdefault("token_file", "token.json")

            # Herencia de Client ID / Client Secret si el usuario no los definió
            # pero el admin los configuró a nivel global en el servidor
            srv_oauth = server_cfg.get("oauth", {})
            user_client_id = cfg["oauth"].get("client_id", "").strip()
            user_client_secret = cfg["oauth"].get("client_secret", "").strip()
            srv_client_id = srv_oauth.get("client_id", "").strip()
            srv_client_secret = srv_oauth.get("client_secret", "").strip()

            if not user_client_id and srv_client_id:
                cfg["oauth"]["_inherited_client_id"] = True
                cfg["oauth"]["effective_client_id"] = srv_client_id
            else:
                cfg["oauth"]["_inherited_client_id"] = False
                cfg["oauth"]["effective_client_id"] = user_client_id

            if not user_client_secret and srv_client_secret:
                cfg["oauth"]["_inherited_client_secret"] = True
                cfg["oauth"]["effective_client_secret"] = srv_client_secret
            else:
                cfg["oauth"]["_inherited_client_secret"] = False
                cfg["oauth"]["effective_client_secret"] = user_client_secret

            return cfg

    def save_user_config(self, username: str, new_cfg: Dict[str, Any]) -> bool:
        """Guarda la configuración específica de un usuario en disco."""
        username = (username or "admin").strip().lower()
        udir = self.get_user_dir(username)
        u_cfg_path = os.path.join(udir, "config.json")
        with self._lock:
            try:
                # Limpiar banderas de herencia antes de guardar
                save_cfg = dict(new_cfg)
                if "oauth" in save_cfg and isinstance(save_cfg["oauth"], dict):
                    oauth_clean = dict(save_cfg["oauth"])
                    oauth_clean.pop("_inherited_client_id", None)
                    oauth_clean.pop("_inherited_client_secret", None)
                    oauth_clean.pop("effective_client_id", None)
                    oauth_clean.pop("effective_client_secret", None)
                    save_cfg["oauth"] = oauth_clean

                with open(u_cfg_path, "w", encoding="utf-8") as f:
                    json.dump(save_cfg, f, indent=2, ensure_ascii=False)

                # Si es admin, sincronizar también config.json raíz para compatibilidad con el servidor
                if username == "admin":
                    try:
                        with open(self.config_path, "w", encoding="utf-8") as f:
                            json.dump(save_cfg, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass
                return True
            except Exception as e:
                logger.error(f"Error guardando {u_cfg_path}: {e}")
                return False

    def get_config(self) -> Dict[str, Any]:
        """Compatibilidad con llamadas legacy: retorna la configuración de admin."""
        return self.get_user_config("admin")

    def save_config(self, new_cfg: Dict[str, Any]) -> bool:
        """Compatibilidad con llamadas legacy: guarda la configuración de admin."""
        return self.save_user_config("admin", new_cfg)

    def _get_request_username(self, allow_override: bool = False) -> str:
        """Obtiene el nombre de usuario autenticado de la solicitud actual."""
        user = getattr(request, "current_user", {}) or {}
        username = user.get("username") or getattr(request, "current_username", None)
        if not username:
            username = session.get("username", "admin")

        username = (username or "admin").strip().lower()
        is_admin = (user.get("role") == "admin")

        # Si el usuario es administrador, puede gestionar otro perfil vía ?for_user=
        if allow_override and is_admin:
            target = request.args.get("for_user")
            if not target and request.is_json:
                data = request.get_json(silent=True) or {}
                target = data.get("for_user")
            if target and isinstance(target, str) and target.strip():
                return target.strip().lower()

        return username

    def _get_redirect_uri(self) -> str:
        """Determina la URI de redirección canónica para OAuth2."""
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host", request.host)
        return f"{proto}://{host}/plugin/{self.plugin_id}/oauth/callback"

    def is_valid_token_file(self, filepath: str) -> bool:
        """Verifica que el archivo de token exista y sea un token real (no client_secret)."""
        if not filepath or not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            if "web" in data or "installed" in data:
                return False
            return bool(data.get("refresh_token") or data.get("token") or data.get("access_token"))
        except Exception:
            return False

    # =========================================================================
    # RUTAS FLASK / BLUEPRINT
    # =========================================================================

    def register_routes(self, app):
        """Registra el Blueprint del plugin con su panel de control y APIs."""
        template_dir = os.path.join(self.plugin_dir, "templates")
        bp = Blueprint(
            f"plugin_{self.plugin_id}",
            __name__,
            template_folder=template_dir,
            static_folder=os.path.join(self.plugin_dir, "static")
        )

        from plugins.google_drive import drive_client

        @bp.route(f"/plugin/{self.plugin_id}/settings", methods=["GET"])
        def view_settings():
            current_user = getattr(request, "current_user", {}) or {}
            is_admin = (current_user.get("role") == "admin")
            target_username = self._get_request_username(allow_override=True)
            cfg = self.get_user_config(target_username)
            udir = self.get_user_dir(target_username)

            deps_ok, deps_msg = drive_client.check_dependencies()
            
            # Comprobar si existe el archivo de service account del usuario
            sa_user_file = os.path.join(udir, cfg.get("service_account_file", "service_account.json"))
            sa_exists = os.path.exists(sa_user_file)
            if not sa_exists and (is_admin or target_username == "admin"):
                sa_exists = os.path.exists(os.path.join(self.plugin_dir, "service_account.json"))

            # Comprobar si existe un token OAuth2 real y válido para el usuario
            oauth_token_file = os.path.join(udir, cfg.get("oauth", {}).get("token_file", "token.json"))
            token_exists = self.is_valid_token_file(oauth_token_file)
            if not token_exists and (is_admin or target_username == "admin"):
                token_exists = self.is_valid_token_file(os.path.join(self.plugin_dir, "token.json"))

            redirect_uri = self._get_redirect_uri()

            # Lista de usuarios para el selector si es admin
            all_usernames = []
            if is_admin:
                try:
                    from routes.auth import load_users
                    all_usernames = list(load_users().keys())
                except Exception:
                    all_usernames = ["admin"]

            return render_template(
                "settings.html",
                plugin=self,
                config=cfg,
                target_username=target_username,
                is_admin=is_admin,
                all_usernames=all_usernames,
                dependencies_ok=deps_ok,
                dependencies_msg=deps_msg,
                service_account_exists=sa_exists,
                oauth_token_exists=token_exists,
                redirect_uri=redirect_uri
            )

        @bp.route(f"/plugin/{self.plugin_id}/api/save", methods=["POST"])
        def api_save():
            data = request.get_json(force=True) or {}
            target_username = self._get_request_username(allow_override=True)
            cfg = self.get_user_config(target_username)
            udir = self.get_user_dir(target_username)

            # Actualizar valores
            cfg["enabled"] = bool(data.get("enabled", False))
            cfg["auto_upload"] = bool(data.get("auto_upload", False))
            cfg["auth_type"] = data.get("auth_type", "service_account")
            cfg["folder_id"] = drive_client.sanitize_folder_id(data.get("folder_id") or "")
            cfg["safe_offload"] = bool(data.get("safe_offload", False))
            cfg["subfolder_by_owner"] = bool(data.get("subfolder_by_owner", False))

            # Manejo de Service Account (archivo o pegado de contenido)
            sa_json_pasted = (data.get("service_account_json_content") or "").strip()
            if sa_json_pasted:
                try:
                    # Validar sintaxis JSON antes de guardar
                    parsed_sa = json.loads(sa_json_pasted)
                    sa_file_path = os.path.join(udir, "service_account.json")
                    with open(sa_file_path, "w", encoding="utf-8") as f:
                        json.dump(parsed_sa, f, indent=2)
                    cfg["service_account_file"] = "service_account.json"
                except Exception as e:
                    return jsonify({"success": False, "error": f"JSON de Cuenta de Servicio inválido: {e}"}), 400

            # Manejo de OAuth2
            if "oauth" not in cfg or not isinstance(cfg["oauth"], dict):
                cfg["oauth"] = {}
            if "client_id" in data:
                cfg["oauth"]["client_id"] = data["client_id"].strip()
            if "client_secret" in data:
                # No sobrescribir si viene vacío
                if data["client_secret"].strip():
                    cfg["oauth"]["client_secret"] = data["client_secret"].strip()

            ok = self.save_user_config(target_username, cfg)
            if ok:
                return jsonify({
                    "success": True,
                    "message": f"Configuración guardada exitosamente para el usuario '{target_username}'."
                })
            return jsonify({"success": False, "error": "No se pudo escribir el archivo de configuración."}), 500

        @bp.route(f"/plugin/{self.plugin_id}/api/test", methods=["POST"])
        def api_test():
            req_data = request.get_json(force=True) or {}
            target_username = self._get_request_username(allow_override=True)
            cfg = self.get_user_config(target_username)
            udir = self.get_user_dir(target_username)
            
            # Permitir probar parámetros enviados en el request sin haberlos guardado aún
            test_cfg = dict(cfg)
            if req_data:
                test_cfg.update(req_data)
                sa_raw = (req_data.get("service_account_json_content") or "").strip()
                if sa_raw:
                    try:
                        test_cfg["service_account_json_content"] = json.loads(sa_raw)
                    except Exception:
                        pass
                oauth_raw = (req_data.get("oauth_token_json_content") or "").strip()
                if oauth_raw:
                    try:
                        test_cfg["oauth_token_json_content"] = json.loads(oauth_raw)
                    except Exception:
                        pass

            current_user = getattr(request, "current_user", {}) or {}
            is_admin = (current_user.get("role") == "admin")
            fallback_dir = self.plugin_dir if (is_admin or target_username == "admin") else None

            ok, res = drive_client.test_connection(test_cfg, base_dir=udir, fallback_dir=fallback_dir)
            if ok:
                return jsonify({"success": True, "details": res})
            return jsonify({"success": False, "error": res.get("error", "Error desconocido de conexión.")}), 400

        @bp.route(f"/plugin/{self.plugin_id}/oauth/start", methods=["GET"])
        def oauth_start():
            target_username = self._get_request_username(allow_override=False)
            cfg = self.get_user_config(target_username)
            
            client_id = (cfg.get("oauth", {}).get("effective_client_id") or cfg.get("oauth", {}).get("client_id") or "").strip()
            client_secret = (cfg.get("oauth", {}).get("effective_client_secret") or cfg.get("oauth", {}).get("client_secret") or "").strip()

            if not client_id or not client_secret:
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote("Debe ingresar y guardar Client ID y Client Secret antes de iniciar la conexión con Google."))

            redirect_uri = request.args.get("redirect_uri") or self._get_redirect_uri()

            state_payload = {
                "username": target_username,
                "redirect_uri": redirect_uri,
                "ts": int(time.time())
            }
            state_token = base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")

            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(drive_client.DRIVE_SCOPES),
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": state_token
            }
            auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
            return redirect(auth_url)

        @bp.route(f"/plugin/{self.plugin_id}/oauth/callback", methods=["GET"])
        def oauth_callback():
            error = request.args.get("error")
            if error:
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote(f"Google devolvió un error: {error}"))

            code = request.args.get("code")
            if not code:
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote("No se recibió código de autorización de Google."))

            # Determinar usuario y redirect_uri desde el parámetro state
            target_username = self._get_request_username(allow_override=False)
            redirect_uri = self._get_redirect_uri()
            state_param = request.args.get("state")
            if state_param:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(state_param.encode("utf-8")).decode("utf-8"))
                    if decoded.get("username"):
                        target_username = decoded["username"]
                    if decoded.get("redirect_uri"):
                        redirect_uri = decoded["redirect_uri"]
                except Exception as e:
                    logger.warning(f"No se pudo decodificar state de OAuth: {e}")

            cfg = self.get_user_config(target_username)
            client_id = (cfg.get("oauth", {}).get("effective_client_id") or cfg.get("oauth", {}).get("client_id") or "").strip()
            client_secret = (cfg.get("oauth", {}).get("effective_client_secret") or cfg.get("oauth", {}).get("client_secret") or "").strip()

            if not client_id or not client_secret:
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote("Client ID o Client Secret no configurados en el servidor."))

            token_endpoint = "https://oauth2.googleapis.com/token"
            exchange_data = {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }

            try:
                resp = requests.post(token_endpoint, data=exchange_data, timeout=20)
                if resp.status_code != 200:
                    err_msg = resp.text
                    try:
                        resp_json = resp.json()
                        err_msg = resp_json.get("error_description") or resp_json.get("error") or err_msg
                    except Exception:
                        pass
                    return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote(f"Error al canjear token con Google: {err_msg}"))

                token_data = resp.json()
                udir = self.get_user_dir(target_username)
                token_file_path = os.path.join(udir, "token.json")
                token_payload = {
                    "token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scopes": drive_client.DRIVE_SCOPES
                }

                # Preservar refresh_token anterior si Google no devolvió uno nuevo en re-autorización
                if not token_payload.get("refresh_token") and os.path.exists(token_file_path):
                    try:
                        with open(token_file_path, "r", encoding="utf-8") as f:
                            old_t = json.load(f)
                            if old_t.get("refresh_token"):
                                token_payload["refresh_token"] = old_t["refresh_token"]
                    except Exception:
                        pass

                with open(token_file_path, "w", encoding="utf-8") as f:
                    json.dump(token_payload, f, indent=2)

                # Si es admin, actualizar también token.json raíz
                if target_username == "admin":
                    try:
                        with open(os.path.join(self.plugin_dir, "token.json"), "w", encoding="utf-8") as f:
                            json.dump(token_payload, f, indent=2)
                    except Exception:
                        pass

                # Asegurar auth_type oauth2 en la configuración del usuario
                cfg["auth_type"] = "oauth2"
                if "oauth" not in cfg:
                    cfg["oauth"] = {}
                cfg["oauth"]["token_file"] = "token.json"
                self.save_user_config(target_username, cfg)

                logger.info(f"Token OAuth2 de Google Drive guardado exitosamente para '{target_username}'.")
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_status=success")

            except Exception as e:
                logger.error(f"Excepción procesando callback OAuth2: {e}")
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote(f"Error de conexión: {e}"))

        @bp.route(f"/plugin/{self.plugin_id}/oauth/manual-token", methods=["POST"])
        def oauth_manual_token():
            target_username = self._get_request_username(allow_override=True)
            data = request.get_json(force=True) or {}
            raw_token = (data.get("token_content") or "").strip()
            if not raw_token:
                return jsonify({"success": False, "error": "No se recibió contenido de token."}), 400

            try:
                token_dict = json.loads(raw_token)
                if not isinstance(token_dict, dict):
                    raise ValueError("El contenido no es un objeto JSON válido.")

                udir = self.get_user_dir(target_username)

                # Detección inteligente: Si el usuario pegó el archivo client_secret.json descargado de Google Cloud
                if "web" in token_dict or "installed" in token_dict:
                    client_block = token_dict.get("web") or token_dict.get("installed") or {}
                    extracted_id = (client_block.get("client_id") or "").strip()
                    extracted_secret = (client_block.get("client_secret") or "").strip()
                    if extracted_id and extracted_secret:
                        cfg = self.get_user_config(target_username)
                        if "oauth" not in cfg:
                            cfg["oauth"] = {}
                        cfg["oauth"]["client_id"] = extracted_id
                        cfg["oauth"]["client_secret"] = extracted_secret
                        self.save_user_config(target_username, cfg)
                        
                        token_file_path = os.path.join(udir, "token.json")
                        if os.path.exists(token_file_path):
                            try:
                                os.remove(token_file_path)
                            except Exception:
                                pass
                                
                        return jsonify({
                            "success": True,
                            "is_client_credentials": True,
                            "client_id": extracted_id,
                            "message": "Has importado el archivo client_secret.json de Google Cloud. Tus credenciales (Client ID y Client Secret) han sido autocompletadas y guardadas. Ahora por favor haz clic en 'Conectar con Google' para autorizar el acceso."
                        })

                cfg = self.get_user_config(target_username)
                client_id = (cfg.get("oauth", {}).get("effective_client_id") or cfg.get("oauth", {}).get("client_id") or "").strip()
                client_secret = (cfg.get("oauth", {}).get("effective_client_secret") or cfg.get("oauth", {}).get("client_secret") or "").strip()

                if "client_id" not in token_dict and client_id:
                    token_dict["client_id"] = client_id
                if "client_secret" not in token_dict and client_secret:
                    token_dict["client_secret"] = client_secret
                if "token_uri" not in token_dict:
                    token_dict["token_uri"] = "https://oauth2.googleapis.com/token"
                if "scopes" not in token_dict:
                    token_dict["scopes"] = drive_client.DRIVE_SCOPES

                token_file_path = os.path.join(udir, "token.json")
                with open(token_file_path, "w", encoding="utf-8") as f:
                    json.dump(token_dict, f, indent=2)

                if target_username == "admin":
                    try:
                        with open(os.path.join(self.plugin_dir, "token.json"), "w", encoding="utf-8") as f:
                            json.dump(token_dict, f, indent=2)
                    except Exception:
                        pass

                cfg["auth_type"] = "oauth2"
                if "oauth" not in cfg:
                    cfg["oauth"] = {}
                cfg["oauth"]["token_file"] = "token.json"
                self.save_user_config(target_username, cfg)

                return jsonify({"success": True, "message": "Token OAuth2 guardado exitosamente."})
            except Exception as e:
                return jsonify({"success": False, "error": f"JSON de token inválido: {e}"}), 400

        @bp.route(f"/plugin/{self.plugin_id}/oauth/revoke", methods=["POST"])
        def oauth_revoke():
            target_username = self._get_request_username(allow_override=True)
            udir = self.get_user_dir(target_username)
            token_file_path = os.path.join(udir, "token.json")
            removed = False
            if os.path.exists(token_file_path):
                try:
                    os.remove(token_file_path)
                    removed = True
                except Exception as e:
                    return jsonify({"success": False, "error": f"No se pudo eliminar el token: {e}"}), 500

            if target_username == "admin":
                root_tok = os.path.join(self.plugin_dir, "token.json")
                if os.path.exists(root_tok):
                    try:
                        os.remove(root_tok)
                        removed = True
                    except Exception:
                        pass

            if removed:
                return jsonify({"success": True, "message": "Token OAuth2 eliminado exitosamente."})
            return jsonify({"success": True, "message": "No había ningún token almacenado."})

        # =====================================================================
        # SUBIDA BAJO DEMANDA / ON-DEMAND UPLOAD API
        # =====================================================================

        @bp.route(f"/plugin/{self.plugin_id}/api/upload-job", methods=["POST"])
        def api_upload_job():
            current_username = self._get_request_username(allow_override=False)
            current_user = getattr(request, "current_user", {}) or {}
            is_admin = (current_user.get("role") == "admin")

            data = request.get_json(force=True) or {}
            job_id = data.get("job_id")
            if not job_id:
                return jsonify({"success": False, "error": "Falta el identificador del trabajo (job_id)."}), 400

            # 1. Localizar archivo y comprobar propiedad
            target_filepath = None
            target_filename = None
            target_owner = current_username
            is_offloaded = False

            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job:
                    target_filepath = job.get("filepath")
                    target_filename = job.get("filename")
                    target_owner = job.get("owner", current_username)
                    is_offloaded = job.get("offloaded", False)

            meta = load_downloads_meta()
            if job_id in meta:
                info = meta[job_id]
                target_filename = target_filename or info.get("filename")
                target_owner = info.get("username") or target_owner
                is_offloaded = is_offloaded or info.get("offloaded", False)

            if not is_admin and target_owner != current_username:
                return jsonify({"success": False, "error": "No tienes permiso para gestionar este archivo."}), 403

            if is_offloaded:
                return jsonify({"success": False, "error": "Este archivo ya fue transferido a la nube previamente."}), 400

            # Localizar archivo en disco si target_filepath no existe
            if not target_filepath or not os.path.isfile(target_filepath):
                if os.path.exists(DOWNLOAD_DIR):
                    for entry in os.listdir(DOWNLOAD_DIR):
                        if entry.startswith(job_id) and not entry.lower().endswith(".zip"):
                            cand = os.path.join(DOWNLOAD_DIR, entry)
                            if os.path.isfile(cand):
                                target_filepath = cand
                                if not target_filename:
                                    target_filename = entry[len(job_id):].lstrip("_-") or entry
                                break

            if not target_filepath or not os.path.isfile(target_filepath):
                return jsonify({"success": False, "error": "El archivo físico ya no está presente en el disco local del VPS."}), 404

            # 2. Cargar configuración de Google Drive del usuario que realiza la acción
            user_cfg = self.get_user_config(current_username)
            deps_ok, deps_err = drive_client.check_dependencies()
            if not deps_ok:
                return jsonify({"success": False, "error": f"Google API dependencies missing: {deps_err}"}), 500

            udir = self.get_user_dir(current_username)
            clean_name = target_filename or os.path.basename(target_filepath)
            self._append_job_log(job_id, f"[*] [GoogleDrive] Subida bajo demanda iniciada por {current_username} ({clean_name})...")

            def _progress(percent: int, message: str):
                self._append_job_log(job_id, f"[*] [GoogleDrive] {message}")

            fallback_dir = self.plugin_dir if (is_admin or current_username == "admin") else None

            ok, result = drive_client.upload_file_resumable(
                filepath=target_filepath,
                filename=clean_name,
                config=user_cfg,
                base_dir=udir,
                fallback_dir=fallback_dir,
                owner=current_username,
                progress_callback=_progress
            )

            if ok:
                web_link = result.get("web_link", "")
                dest_entry = f"Google Drive ({web_link})"
                self._append_job_log(job_id, f"[+] [GoogleDrive] Archivo respaldado con éxito en Drive: {web_link}")

                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    if job:
                        if "cloud_destinations" not in job:
                            job["cloud_destinations"] = []
                        if dest_entry not in job["cloud_destinations"]:
                            job["cloud_destinations"].append(dest_entry)

                if job_id in meta:
                    if "cloud_destinations" not in meta[job_id]:
                        meta[job_id]["cloud_destinations"] = []
                    if dest_entry not in meta[job_id]["cloud_destinations"]:
                        meta[job_id]["cloud_destinations"].append(dest_entry)
                    save_downloads_meta(meta)

                # Aplicar Safe Offload si está activo en la config de este usuario
                if user_cfg.get("safe_offload", False) and os.path.exists(target_filepath):
                    try:
                        os.remove(target_filepath)
                        self._append_job_log(job_id, "[+] [Offload] Archivo local eliminado tras subida confirmada a Google Drive.")
                        with JOBS_LOCK:
                            job = JOBS.get(job_id)
                            if job:
                                job["offloaded"] = True
                                job["filepath"] = None
                        if job_id in meta:
                            meta[job_id]["offloaded"] = True
                            save_downloads_meta(meta)
                    except Exception as err:
                        self._append_job_log(job_id, f"[!] [Offload] Error eliminando archivo local: {err}")

                return jsonify({
                    "success": True,
                    "message": "Archivo subido exitosamente a Google Drive.",
                    "web_link": web_link,
                    "filename": clean_name
                })
            else:
                err_msg = result.get("error", "Error desconocido de subida.")
                self._append_job_log(job_id, f"[!] [GoogleDrive] Falló la subida manual: {err_msg}")
                return jsonify({"success": False, "error": err_msg}), 400

        if f"plugin_{self.plugin_id}" not in app.blueprints:
            app.register_blueprint(bp)
            logger.info(f"Rutas de Google Drive registradas bajo /plugin/{self.plugin_id}/")


    # =========================================================================
    # EXTENSIONES DE INTERFAZ (UI HOOK SLOTS)
    # =========================================================================

    def get_ui_nav_item(self):
        """Retorna el enlace de navegación para la barra superior/menú de dHtools."""
        return {
            "title": "Google Drive",
            "url": f"/plugin/{self.plugin_id}/settings",
            "icon": "📁",
            "badge": "EXP"
        }

    def get_admin_cloud_panel(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        [EXPERIMENTAL] Inyecta la tarjeta de Google Drive en la pestaña Cloud Sync de /admin.
        """
        cfg = config or self.get_config()
        is_enabled = cfg.get("enabled", False)
        auth_type = "Cuenta de Servicio" if cfg.get("auth_type") != "oauth2" else "OAuth 2.0"
        folder_desc = cfg.get("folder_id") or "Raíz de Mi Unidad"
        auto_upload_desc = "Automática" if cfg.get("auto_upload") else "Bajo Demanda"

        status_badge = (
            '<span style="background:rgba(16,185,129,0.2); color:#10b981; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:700;">ACTIVO</span>'
            if is_enabled else
            '<span style="background:rgba(107,114,128,0.2); color:#9ca3af; padding:2px 8px; border-radius:4px; font-size:0.75rem;">DESACTIVADO</span>'
        )

        html = f"""
        <div style="font-size:0.83rem; color:var(--muted); line-height:1.6;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span>Estado: {status_badge}</span>
            <span>Subida: <strong style="color:var(--text);">{auto_upload_desc}</strong></span>
          </div>
          <div>Método: <strong style="color:var(--text);">{auth_type}</strong> | Carpeta: <code style="color:var(--accent-blue);">{folder_desc}</code></div>
          <div style="margin-top:8px; font-size:0.78rem;">
            Soporte multiusuario: Cada usuario puede configurar su propia cuenta de Google Drive en <code>/plugin/google_drive/settings</code>.
          </div>
        </div>
        """

        return {
            "id": self.plugin_id,
            "title": "Google Drive Cloud Sync",
            "icon": "📁",
            "badge": "EXP",
            "settings_url": f"/plugin/{self.plugin_id}/settings",
            "html_content": html
        }

    def get_download_cloud_option(self) -> Dict[str, Any]:
        """
        [EXPERIMENTAL] Inyecta la opción de Google Drive en el selector de descargas
        y en los presets de usuario del Modo Avanzado.
        """
        return {
            "id": self.plugin_id,
            "name": "Google Drive",
            "icon": "📁",
            "badge": "EXP",
            "description": "Sube el archivo descargado a tu Google Drive mediante streaming resumible.",
            "fields": [
                {
                    "id": "folder_id",
                    "label": "Carpeta Destino (opcional)",
                    "type": "text",
                    "placeholder": "ID de carpeta (vacío = carpeta por defecto de tus ajustes)"
                }
            ],
            "settings_url": f"/plugin/{self.plugin_id}/settings"
        }

    # =========================================================================
    # INTEGRACIÓN CON BOT DE TELEGRAM
    # =========================================================================

    def get_telegram_commands(self) -> list:
        """Comandos que este plugin provee al asistente de Telegram."""
        return [
            {
                "command": "/drive",
                "description": "Consultar almacenamiento y estado de Google Drive"
            }
        ]

    def on_telegram_command(self, cmd: str, args: list, message: dict, bot) -> bool:
        """
        Hook ejecutado cuando un usuario de Telegram envía un comando.
        Retorna True si fue manejado por este plugin.
        """
        if cmd != "/drive":
            return False

        chat_id = message.get("chat", {}).get("id")
        if not chat_id:
            return True

        from plugins.google_drive import drive_client
        deps_ok, deps_err = drive_client.check_dependencies()
        if not deps_ok:
            bot.send_message(
                chat_id,
                "⚠️ <b>Google Drive no disponible:</b>\nFaltan dependencias en el servidor para Google API."
            )
            return True

        # Telegram interactúa con la configuración del servidor / admin
        cfg = self.get_user_config("admin")
        if not cfg.get("enabled"):
            bot.send_message(
                chat_id,
                "📁 <b>Google Drive:</b> La sincronización está <i>desactivada</i> en la plataforma.\n"
                "Podés activarla desde el panel web: <code>/plugin/google_drive/settings</code>"
            )
            return True

        sent = bot.send_message(chat_id, "🔍 <i>Consultando estado y cuota de Google Drive...</i>")
        msg_id = sent.get("result", {}).get("message_id") if sent else None

        udir = self.get_user_dir("admin")
        ok, res = drive_client.test_connection(cfg, base_dir=udir, fallback_dir=self.plugin_dir)

        def _format_b(b):
            if not b:
                return "0 B"
            for u in ['B', 'KB', 'MB', 'GB', 'TB']:
                if b < 1024:
                    return f"{b:.1f} {u}"
                b /= 1024
            return f"{b:.1f} PB"

        if ok:
            used_str = _format_b(res.get("storage_used_bytes", 0))
            tot_bytes = res.get("storage_total_bytes")
            tot_str = _format_b(tot_bytes) if tot_bytes else "Ilimitado"
            pct = round((res.get("storage_used_bytes", 0) / tot_bytes) * 100, 1) if tot_bytes else 0

            auto_label = "✅ Automático" if cfg.get("auto_upload") else "🎯 Bajo Demanda"
            text = (
                f"📁 <b>Google Drive Cloud Sync</b>\n\n"
                f"• <b>Cuenta:</b> {res.get('user_name', 'N/A')} (<code>{res.get('email', 'N/A')}</code>)\n"
                f"• <b>Carpeta activa:</b> <i>{res.get('folder_name', 'Raíz')}</i>\n"
                f"• <b>Almacenamiento:</b> {used_str} de {tot_str} ({pct}% en uso)\n"
                f"• <b>Modo de Subida:</b> {auto_label}\n"
                f"• <b>Modo Offload:</b> {'✅ Activado (borra local)' if cfg.get('safe_offload') else '❌ Desactivado (mantiene local)'}\n\n"
                f"💡 <i>Cada usuario de dHtools puede configurar su propia cuenta en /plugin/google_drive/settings</i>"
            )
        else:
            err = res.get("error", "Error desconocido")
            text = (
                f"⚠️ <b>Error de conexión con Google Drive:</b>\n"
                f"<code>{err}</code>\n\n"
                f"Revisá la configuración en la web: <code>/plugin/google_drive/settings</code>"
            )

        if msg_id:
            bot.edit_message(chat_id, msg_id, text)
        else:
            bot.send_message(chat_id, text)

        return True

    # =========================================================================
    # HOOKS DEL CICLO DE VIDA
    # =========================================================================

    def _append_job_log(self, job_id: str, text: str):
        """Añade una línea de bitácora en la consola interactiva de la descarga."""
        if not job_id:
            return
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                if "logs" not in job:
                    job["logs"] = []
                job["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "text": text
                })
                if len(job["logs"]) > 150:
                    job["logs"] = job["logs"][-150:]

    def on_download_complete(self, job_data: Dict[str, Any]):
        """
        Gancho ejecutado tras completarse cualquier descarga.
        Sube el archivo a Google Drive si el plugin está habilitado para el usuario
        y si la subida automática está activa o si fue solicitada expresamente para este trabajo.
        """
        owner = job_data.get("owner", "admin")
        user_cfg = self.get_user_config(owner)

        # 1. El usuario debe tener habilitada la integración con Google Drive
        if not user_cfg.get("enabled", False):
            return

        # 2. Comprobar si hay solicitud de subida: auto_upload activado O marcado en la descarga
        user_cloud = job_data.get("user_cloud_sync") or {}
        plugin_prefs = (user_cloud.get("plugins") or {}).get(self.plugin_id) or {}

        is_auto = user_cfg.get("auto_upload", False)
        is_job_checked = plugin_prefs.get("enabled", False)

        # Si NO es auto-upload y tampoco se tildó la opción para esta descarga -> RESPETAR PREFERENCIA BAJO DEMANDA
        if not is_auto and not is_job_checked:
            return

        # Si el usuario especificó una carpeta personalizada en la descarga puntual
        custom_folder = plugin_prefs.get("folder_id")
        if custom_folder:
            user_cfg = dict(user_cfg)
            user_cfg["folder_id"] = custom_folder.strip()

        filepath = job_data.get("filepath")
        filename = job_data.get("filename")
        job_id = job_data.get("job_id") or job_data.get("id")

        if not filepath or not os.path.isfile(filepath):
            return

        is_offload_requested = user_cfg.get("safe_offload", False) or user_cloud.get("offload", False)

        from plugins.google_drive import drive_client

        deps_ok, _ = drive_client.check_dependencies()
        if not deps_ok:
            self._append_job_log(
                job_id,
                "[!] [GoogleDrive] Plugin inactivo: faltan librerías de Google API en el servidor."
            )
            return

        clean_name = filename or os.path.basename(filepath)
        trigger_reason = "Automática" if is_auto else "Bajo Demanda"
        self._append_job_log(
            job_id,
            f"[*] [GoogleDrive] Iniciando respaldo en Google Drive de {owner} [{trigger_reason}] ({clean_name})..."
        )

        def _progress(percent: int, message: str):
            self._append_job_log(job_id, f"[*] [GoogleDrive] {message}")

        udir = self.get_user_dir(owner)
        fallback_dir = self.plugin_dir if owner == "admin" else None

        ok, result = drive_client.upload_file_resumable(
            filepath=filepath,
            filename=clean_name,
            config=user_cfg,
            base_dir=udir,
            fallback_dir=fallback_dir,
            owner=owner,
            progress_callback=_progress
        )

        if ok:
            web_link = result.get("web_link", "")
            self._append_job_log(
                job_id,
                f"[+] [GoogleDrive] Archivo respaldado con éxito en Drive: {web_link}"
            )

            # Actualizar destinos en el trabajo
            dest_entry = f"Google Drive ({web_link})"
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job:
                    if "cloud_destinations" not in job:
                        job["cloud_destinations"] = []
                    if dest_entry not in job["cloud_destinations"]:
                        job["cloud_destinations"].append(dest_entry)

            # Aplicar Safe Offload si está activo
            if is_offload_requested and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    self._append_job_log(
                        job_id,
                        f"[+] [Offload] Archivo local eliminado del VPS tras subida confirmada a Google Drive."
                    )
                    with JOBS_LOCK:
                        job = JOBS.get(job_id)
                        if job:
                            job["offloaded"] = True
                            job["filepath"] = None

                    meta = load_downloads_meta()
                    if job_id in meta:
                        meta[job_id]["offloaded"] = True
                        if "cloud_destinations" not in meta[job_id]:
                            meta[job_id]["cloud_destinations"] = []
                        if dest_entry not in meta[job_id]["cloud_destinations"]:
                            meta[job_id]["cloud_destinations"].append(dest_entry)
                        save_downloads_meta(meta)
                except Exception as err:
                    self._append_job_log(job_id, f"[!] [Offload] Error eliminando archivo local: {err}")

        else:
            err_msg = result.get("error", "Error desconocido")
            self._append_job_log(job_id, f"[!] [GoogleDrive] Falló la subida a Drive: {err_msg}")

    def on_download_error(self, job_data: Dict[str, Any], error: Optional[str] = None):
        """Gancho ejecutado si la descarga falla."""
        job_id = job_data.get("job_id") or job_data.get("id")
        logger.debug(f"[EXPERIMENTAL] GoogleDrive: Tarea {job_id} falló ({error}). No se ejecuta subida.")
