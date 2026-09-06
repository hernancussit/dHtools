"""
[EXPERIMENTAL] Plugin Oficial de Google Drive para dHtools.
Permite sincronizar y respaldar descargas directamente en Google Drive
con streaming por fragmentos (RAM-safe) y modo Safe Offload opcional.
"""

import os
import json
import time
import logging
import threading
from typing import Dict, Any, Optional
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

            # Comprobar si existe el token OAuth2
            oauth_token = drive_client._resolve_path(cfg.get("oauth", {}).get("token_file", "token.json"), self.plugin_dir)
            token_exists = os.path.exists(oauth_token)

            return render_template(
                "settings.html",
                plugin=self,
                config=cfg,
                dependencies_ok=deps_ok,
                dependencies_msg=deps_msg,
                service_account_exists=sa_exists,
                oauth_token_exists=token_exists
            )

        @bp.route(f"/plugin/{self.plugin_id}/api/save", methods=["POST"])
        def api_save():
            data = request.get_json() or {}
            cfg = self.get_config()

            # Actualizar valores
            cfg["enabled"] = bool(data.get("enabled", False))
            cfg["auth_type"] = data.get("auth_type", "service_account")
            cfg["folder_id"] = (data.get("folder_id") or "").strip()
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
            else:
                test_cfg = cfg

            ok, res = drive_client.test_connection(test_cfg, base_dir=self.plugin_dir)
            if ok:
                return jsonify({"success": True, "details": res})
            return jsonify({"success": False, "error": res.get("error", "Error desconocido de conexión.")}), 400

        app.register_blueprint(bp)
        logger.info(f"Rutas de Google Drive registradas bajo /plugin/{self.plugin_id}/")

    # =========================================================================
    # EXTENSIONES DE NAVEGACIÓN
    # =========================================================================

    def get_ui_nav_item(self):
        """Retorna el enlace de navegación para la barra superior/menú de dHtools."""
        return {
            "title": "Google Drive",
            "url": f"/plugin/{self.plugin_id}/settings",
            "icon": "📁",
            "badge": "EXP"
        }

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
        if not cfg.get("enabled"):
            return

        filepath = job_data.get("filepath")
        filename = job_data.get("filename")
        job_id = job_data.get("job_id") or job_data.get("id")
        owner = job_data.get("owner", "admin")

        if not filepath or not os.path.isfile(filepath):
            return

        # Verificar si hay personalización de nube en el trabajo o si es auto-sync global
        user_cloud = job_data.get("user_cloud_sync") or {}
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
