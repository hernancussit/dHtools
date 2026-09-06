"""
[EXPERIMENTAL] Plugin Oficial de Google Drive para dHtools.
Permite sincronizar y respaldar descargas directamente en Google Drive
con streaming por fragmentos (RAM-safe) y modo Safe Offload opcional.
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
from flask import Blueprint, jsonify, request, render_template, redirect, url_for

from core.state import JOBS, JOBS_LOCK
from core.utils import load_downloads_meta, save_downloads_meta

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
        self.version = self.metadata.get("version", "1.0.0")
        self._lock = threading.RLock()

        # Determinar ruta base del plugin
        self.plugin_dir = self.metadata.get("_path")
        if not self.plugin_dir or not os.path.isdir(self.plugin_dir):
            self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

        self.config_path = os.path.join(self.plugin_dir, "config.json")
        self.example_config_path = os.path.join(self.plugin_dir, "config.example.json")

        logger.info(f"[EXPERIMENTAL] Inicializando {self.name} v{self.version} en '{self.plugin_dir}'")

    # =========================================================================
    # GESTIÓN DE CONFIGURACIÓN
    # =========================================================================

    def get_config(self) -> Dict[str, Any]:
        """Carga y retorna la configuración actual del plugin."""
        with self._lock:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Error leyendo {self.config_path}: {e}")

            # Cargar defaults desde config.example.json si existe
            if os.path.exists(self.example_config_path):
                try:
                    with open(self.example_config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        data["enabled"] = False
                        return data
                except Exception:
                    pass

            return {
                "enabled": False,
                "auth_type": "service_account",
                "folder_id": "",
                "safe_offload": false,
                "service_account_file": "service_account.json",
                "oauth": {"client_id": "", "client_secret": "", "token_file": "token.json"}
            }

    def save_config(self, new_cfg: Dict[str, Any]) -> bool:
        """Guarda la configuración del plugin en disco."""
        with self._lock:
            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(new_cfg, f, indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                logger.error(f"Error guardando {self.config_path}: {e}")
                return False

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
            cfg = self.get_config()
            deps_ok, deps_msg = drive_client.check_dependencies()
            
            # Comprobar si existe el archivo de service account
            sa_file = drive_client._resolve_path(cfg.get("service_account_file", "service_account.json"), self.plugin_dir)
            sa_exists = os.path.exists(sa_file)

            # Comprobar si existe un token OAuth2 real y válido
            oauth_token = drive_client._resolve_path(cfg.get("oauth", {}).get("token_file", "token.json"), self.plugin_dir)
            token_exists = self.is_valid_token_file(oauth_token)

            redirect_uri = self._get_redirect_uri()

            return render_template(
                "settings.html",
                plugin=self,
                config=cfg,
                dependencies_ok=deps_ok,
                dependencies_msg=deps_msg,
                service_account_exists=sa_exists,
                oauth_token_exists=token_exists,
                redirect_uri=redirect_uri
            )

        @bp.route(f"/plugin/{self.plugin_id}/api/save", methods=["POST"])
        def api_save():
            data = request.get_json() or {}
            cfg = self.get_config()

            # Actualizar valores
            cfg["enabled"] = bool(data.get("enabled", False))
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
                    # Guardar directo en service_account.json dentro del directorio del plugin
                    sa_file_path = os.path.join(self.plugin_dir, "service_account.json")
                    with open(sa_file_path, "w", encoding="utf-8") as f:
                        json.dump(parsed_sa, f, indent=2)
                    cfg["service_account_file"] = "service_account.json"
                except Exception as e:
                    return jsonify({"success": False, "error": f"JSON de Cuenta de Servicio inválido: {e}"}), 400

            # Manejo de OAuth2
            if "oauth" not in cfg:
                cfg["oauth"] = {}
            if "client_id" in data:
                cfg["oauth"]["client_id"] = data["client_id"].strip()
            if "client_secret" in data:
                # No sobrescribir si viene vacío
                if data["client_secret"].strip():
                    cfg["oauth"]["client_secret"] = data["client_secret"].strip()

            ok = self.save_config(cfg)
            if ok:
                return jsonify({"success": True, "message": "Configuración guardada exitosamente."})
            return jsonify({"success": False, "error": "No se pudo escribir el archivo de configuración."}), 500

        @bp.route(f"/plugin/{self.plugin_id}/api/test", methods=["POST"])
        def api_test():
            req_data = request.get_json() or {}
            cfg = self.get_config()
            
            # Permitir probar parámetros enviados en el request sin haberlos guardado aún
            if req_data:
                test_cfg = dict(cfg)
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
            else:
                test_cfg = cfg

            ok, res = drive_client.test_connection(test_cfg, base_dir=self.plugin_dir)
            if ok:
                return jsonify({"success": True, "details": res})
            return jsonify({"success": False, "error": res.get("error", "Error desconocido de conexión.")}), 400

        @bp.route(f"/plugin/{self.plugin_id}/oauth/start", methods=["GET"])
        def oauth_start():
            cfg = self.get_config()
            client_id = (cfg.get("oauth", {}).get("client_id") or "").strip()
            client_secret = (cfg.get("oauth", {}).get("client_secret") or "").strip()

            if not client_id or not client_secret:
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote("Debe ingresar y guardar Client ID y Client Secret antes de iniciar la conexión con Google."))

            redirect_uri = request.args.get("redirect_uri") or self._get_redirect_uri()

            state_payload = {
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

            cfg = self.get_config()
            client_id = (cfg.get("oauth", {}).get("client_id") or "").strip()
            client_secret = (cfg.get("oauth", {}).get("client_secret") or "").strip()

            if not client_id or not client_secret:
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote("Client ID o Client Secret no configurados en el servidor."))

            redirect_uri = self._get_redirect_uri()
            state_param = request.args.get("state")
            if state_param:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(state_param.encode("utf-8")).decode("utf-8"))
                    if "redirect_uri" in decoded:
                        redirect_uri = decoded["redirect_uri"]
                except Exception as e:
                    logger.warning(f"No se pudo decodificar state de OAuth: {e}")

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
                token_file_path = os.path.join(self.plugin_dir, "token.json")
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

                # Asegurar auth_type oauth2 en la configuración
                cfg["auth_type"] = "oauth2"
                if "oauth" not in cfg:
                    cfg["oauth"] = {}
                cfg["oauth"]["token_file"] = "token.json"
                self.save_config(cfg)

                logger.info("Token OAuth2 de Google Drive guardado exitosamente tras autorización web.")
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_status=success")

            except Exception as e:
                logger.error(f"Excepción procesando callback OAuth2: {e}")
                return redirect(f"/plugin/{self.plugin_id}/settings?oauth_error=" + quote(f"Error de conexión: {e}"))

        @bp.route(f"/plugin/{self.plugin_id}/oauth/manual-token", methods=["POST"])
        def oauth_manual_token():
            data = request.get_json() or {}
            raw_token = (data.get("token_content") or "").strip()
            if not raw_token:
                return jsonify({"success": False, "error": "No se recibió contenido de token."}), 400

            try:
                token_dict = json.loads(raw_token)
                if not isinstance(token_dict, dict):
                    raise ValueError("El contenido no es un objeto JSON válido.")

                # Detección inteligente: Si el usuario pegó el archivo client_secret.json descargado de Google Cloud
                if "web" in token_dict or "installed" in token_dict:
                    client_block = token_dict.get("web") or token_dict.get("installed") or {}
                    extracted_id = (client_block.get("client_id") or "").strip()
                    extracted_secret = (client_block.get("client_secret") or "").strip()
                    if extracted_id and extracted_secret:
                        cfg = self.get_config()
                        if "oauth" not in cfg:
                            cfg["oauth"] = {}
                        cfg["oauth"]["client_id"] = extracted_id
                        cfg["oauth"]["client_secret"] = extracted_secret
                        self.save_config(cfg)
                        
                        # Limpiar token.json si contenía este archivo client_secret
                        token_file_path = os.path.join(self.plugin_dir, "token.json")
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

                cfg = self.get_config()
                client_id = cfg.get("oauth", {}).get("client_id", "").strip()
                client_secret = cfg.get("oauth", {}).get("client_secret", "").strip()

                if "client_id" not in token_dict and client_id:
                    token_dict["client_id"] = client_id
                if "client_secret" not in token_dict and client_secret:
                    token_dict["client_secret"] = client_secret
                if "token_uri" not in token_dict:
                    token_dict["token_uri"] = "https://oauth2.googleapis.com/token"
                if "scopes" not in token_dict:
                    token_dict["scopes"] = drive_client.DRIVE_SCOPES

                token_file_path = os.path.join(self.plugin_dir, "token.json")
                with open(token_file_path, "w", encoding="utf-8") as f:
                    json.dump(token_dict, f, indent=2)

                cfg["auth_type"] = "oauth2"
                if "oauth" not in cfg:
                    cfg["oauth"] = {}
                cfg["oauth"]["token_file"] = "token.json"
                self.save_config(cfg)

                return jsonify({"success": True, "message": "Token OAuth2 guardado exitosamente."})
            except Exception as e:
                return jsonify({"success": False, "error": f"JSON de token inválido: {e}"}), 400

        @bp.route(f"/plugin/{self.plugin_id}/oauth/revoke", methods=["POST"])
        def oauth_revoke():
            token_file_path = os.path.join(self.plugin_dir, "token.json")
            if os.path.exists(token_file_path):
                try:
                    os.remove(token_file_path)
                    return jsonify({"success": True, "message": "Token OAuth2 eliminado exitosamente."})
                except Exception as e:
                    return jsonify({"success": False, "error": f"No se pudo eliminar el token: {e}"}), 500
            return jsonify({"success": True, "message": "No había ningún token almacenado."})

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

        status_badge = (
            '<span style="background:rgba(16,185,129,0.2); color:#10b981; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:700;">ACTIVO</span>'
            if is_enabled else
            '<span style="background:rgba(107,114,128,0.2); color:#9ca3af; padding:2px 8px; border-radius:4px; font-size:0.75rem;">DESACTIVADO</span>'
        )

        html = f"""
        <div style="font-size:0.83rem; color:var(--muted); line-height:1.6;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span>Estado: {status_badge}</span>
            <span>Método: <strong style="color:var(--text);">{auth_type}</strong></span>
          </div>
          <div>Carpeta Destino: <code style="color:var(--accent-blue);">{folder_desc}</code></div>
          <div style="margin-top:8px; font-size:0.78rem;">
            Streaming multipart en fragmentos de 10 MB (RAM-Safe). Subida directa y automática al finalizar descargas.
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
        cfg = self.get_config()
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
                    "placeholder": f"ID de carpeta (vacío = {cfg.get('folder_id') or 'raíz'})"
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

        cfg = self.get_config()
        if not cfg.get("enabled"):
            bot.send_message(
                chat_id,
                "📁 <b>Google Drive:</b> La sincronización está <i>desactivada</i> en la plataforma.\n"
                "Podés activarla desde el panel de administración web: <code>/plugin/google_drive/settings</code>"
            )
            return True

        # Enviar aviso provisional
        sent = bot.send_message(chat_id, "🔍 <i>Consultando estado y cuota de Google Drive...</i>")
        msg_id = sent.get("result", {}).get("message_id") if sent else None

        ok, res = drive_client.test_connection(cfg, base_dir=self.plugin_dir)

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

            text = (
                f"📁 <b>Google Drive Cloud Sync</b>\n\n"
                f"• <b>Cuenta:</b> {res.get('user_name', 'N/A')} (<code>{res.get('email', 'N/A')}</code>)\n"
                f"• <b>Carpeta activa:</b> <i>{res.get('folder_name', 'Raíz')}</i>\n"
                f"• <b>Almacenamiento:</b> {used_str} de {tot_str} ({pct}% en uso)\n"
                f"• <b>Modo Offload:</b> {'✅ Activado (borra local)' if cfg.get('safe_offload') else '❌ Desactivado (mantiene local)'}\n\n"
                f"💡 <i>Las descargas finalizadas se respaldarán automáticamente en esta unidad.</i>"
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
        Sube el archivo a Google Drive si el plugin o la tarea lo tienen habilitado.
        """
        cfg = self.get_config()

        # Verificar si hay personalización de nube en el trabajo o si es auto-sync global
        user_cloud = job_data.get("user_cloud_sync") or {}
        plugin_prefs = (user_cloud.get("plugins") or {}).get(self.plugin_id) or {}

        # Determinar si este trabajo debe subir a Google Drive
        should_upload = cfg.get("enabled", False) or plugin_prefs.get("enabled", False)
        if not should_upload:
            return

        # Si el usuario especificó una carpeta personalizada en la descarga
        custom_folder = plugin_prefs.get("folder_id")
        if custom_folder:
            cfg = dict(cfg)
            cfg["folder_id"] = custom_folder.strip()

        filepath = job_data.get("filepath")
        filename = job_data.get("filename")
        job_id = job_data.get("job_id") or job_data.get("id")
        owner = job_data.get("owner", "admin")

        if not filepath or not os.path.isfile(filepath):
            return

        is_offload_requested = cfg.get("safe_offload", False) or user_cloud.get("offload", False)

        from plugins.google_drive import drive_client

        deps_ok, _ = drive_client.check_dependencies()
        if not deps_ok:
            self._append_job_log(
                job_id,
                "[!] [GoogleDrive] Plugin inactivo: faltan librerías de Google API en el servidor."
            )
            return

        self._append_job_log(
            job_id,
            f"[*] [GoogleDrive] Iniciando respaldo en Google Drive ({filename})..."
        )

        def _progress(percent: int, message: str):
            self._append_job_log(job_id, f"[*] [GoogleDrive] {message}")

        ok, result = drive_client.upload_file_resumable(
            filepath=filepath,
            filename=filename,
            config=cfg,
            base_dir=self.plugin_dir,
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
