"""
[EXPERIMENTAL] Plugin Manager para dHtools
Permite descubrir, cargar y gestionar extensiones y plugins de manera desacoplada
sin alterar el código base del proyecto ni exponer componentes privados a Git/GitHub.
"""

import os
import sys
import json
import logging
import importlib.util
import types
import threading
import uuid
import time
import re
import subprocess
import requests
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("dhtools.plugins")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[PluginManager] [EXPERIMENTAL] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class PluginManager:
    """
    [EXPERIMENTAL] Gestor centralizado del ciclo de vida de Plugins para dHtools.
    """
    def __init__(self):
        self._plugins: Dict[str, Dict[str, Any]] = {}
        self._instances: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._app = None
        self._background_started = False
        
        # Determinar ruta base del directorio /plugins
        if os.path.exists("/app") and os.path.isdir("/app"):
            self.plugins_dir = "/app/plugins"
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.plugins_dir = os.path.join(base, "plugins")

    def init_app(self, app):
        """Inicializa el gestor con la instancia Flask y carga los plugins activos."""
        self._app = app
        logger.info(f"Iniciando gestor de plugins (Ruta: {self.plugins_dir})")
        self.discover_and_load_plugins()

    def discover_and_load_plugins(self):
        """Escanea el directorio de plugins y carga las instancias habilitadas."""
        with self._lock:
            if not os.path.exists(self.plugins_dir):
                try:
                    os.makedirs(self.plugins_dir, exist_ok=True)
                except Exception as e:
                    logger.warning(f"No se pudo crear el directorio de plugins: {e}")
                    return

            discovered = {}
            for item in os.listdir(self.plugins_dir):
                plugin_path = os.path.join(self.plugins_dir, item)
                if not os.path.isdir(plugin_path) or item.startswith(".") or item.startswith("__"):
                    continue

                manifest_file = os.path.join(plugin_path, "plugin.json")
                entry_file = os.path.join(plugin_path, "plugin.py")

                if not os.path.exists(manifest_file):
                    continue

                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception as e:
                    logger.error(f"Error leyendo manifiesto en '{item}': {e}")
                    continue

                plugin_id = manifest.get("id") or item
                manifest["_folder"] = item
                manifest["_path"] = plugin_path
                manifest["_entry"] = entry_file if os.path.exists(entry_file) else None
                manifest["experimental"] = True
                discovered[plugin_id] = manifest

            self._plugins = discovered
            logger.info(f"Plugins descubiertos: {len(self._plugins)} ({', '.join(self._plugins.keys()) if self._plugins else 'ninguno'})")

            # Cargar e instanciar plugins que tengan enabled=True
            for plugin_id, meta in self._plugins.items():
                if meta.get("enabled", False):
                    self._load_plugin(plugin_id, meta)

    def _load_plugin(self, plugin_id: str, meta: Dict[str, Any]):
        """Carga dinámicamente un plugin específico en un entorno aislado."""
        entry_file = meta.get("_entry")
        if not entry_file or not os.path.exists(entry_file):
            logger.warning(f"Plugin '{plugin_id}' no tiene archivo plugin.py ejecutable.")
            return

        try:
            plugin_path = meta.get("_path") or os.path.dirname(entry_file)
            pkg_name = f"plugins.{plugin_id}"

            # Registrar namespace del plugin como paquete para permitir importaciones relativas (ej. from .core...)
            if pkg_name not in sys.modules:
                pkg_mod = types.ModuleType(pkg_name)
                pkg_mod.__path__ = [plugin_path]
                pkg_mod.__package__ = pkg_name
                pkg_mod.__file__ = entry_file
                sys.modules[pkg_name] = pkg_mod
            else:
                sys.modules[pkg_name].__path__ = [plugin_path]

            module_name = f"{pkg_name}.plugin"
            spec = importlib.util.spec_from_file_location(module_name, entry_file)
            if not spec or not spec.loader:
                logger.error(f"No se pudo crear spec para plugin '{plugin_id}'")
                return

            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)

            # Buscar la clase del plugin o la función constructora
            plugin_class = getattr(mod, "Plugin", None) or getattr(mod, f"{plugin_id.capitalize()}Plugin", None)
            if not plugin_class:
                # Buscar cualquier clase que termine en 'Plugin'
                for attr_name in dir(mod):
                    if attr_name.endswith("Plugin") and attr_name != "Plugin":
                        plugin_class = getattr(mod, attr_name)
                        break

            if not plugin_class:
                logger.error(f"Plugin '{plugin_id}' no define una clase 'Plugin' en plugin.py")
                return

            # Instanciar el plugin con soporte para múltiples firmas de constructor
            try:
                instance = plugin_class(manager=self, metadata=meta)
            except TypeError:
                try:
                    instance = plugin_class(manager=self)
                except TypeError:
                    instance = plugin_class()

            self._instances[plugin_id] = instance
            logger.info(f"Plugin cargado exitosamente: '{meta.get('name', plugin_id)}' v{meta.get('version', '1.0')} [EXPERIMENTAL]")

            # Registrar rutas Blueprint si el plugin lo implementa y Flask ya está iniciado
            if self._app and hasattr(instance, "register_routes"):
                try:
                    instance.register_routes(self._app)
                    logger.info(f"Rutas registradas para plugin '{plugin_id}'")
                except Exception as e:
                    logger.error(f"Error registrando rutas para plugin '{plugin_id}': {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error crítico al instanciar plugin '{plugin_id}': {e}", exc_info=True)

    def start_background_plugins(self):
        """Dispara on_startup y tareas en segundo plano de plugins cargados."""
        with self._lock:
            if self._background_started:
                return
            self._background_started = True

            for plugin_id, inst in list(self._instances.items()):
                if hasattr(inst, "on_startup"):
                    def _run_startup(pid=plugin_id, instance=inst):
                        try:
                            context = {
                                "app": self._app,
                                "plugins_dir": self.plugins_dir,
                                "plugin_dir": self._plugins.get(pid, {}).get("_path")
                            }
                            instance.on_startup(self._app, context)
                            logger.info(f"Hook on_startup ejecutado para plugin '{pid}'")
                        except Exception as err:
                            logger.error(f"Error en on_startup de plugin '{pid}': {err}", exc_info=True)

                    threading.Thread(target=_run_startup, daemon=True, name=f"plugin-startup-{plugin_id}").start()

    def trigger_hook(self, hook_name: str, *args, **kwargs):
        """
        Dispara un gancho de ciclo de vida en todos los plugins habilitados.
        Cada llamada se ejecuta dentro de un try/except aislado para blindar el Core.
        """
        with self._lock:
            instances = list(self._instances.items())

        for plugin_id, inst in instances:
            if hasattr(inst, hook_name):
                try:
                    func = getattr(inst, hook_name)
                    func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Excepción en hook '{hook_name}' del plugin '{plugin_id}': {e}", exc_info=True)

    def get_all_plugins(self) -> List[Dict[str, Any]]:
        """Retorna lista de todos los plugins descubiertos y su estado."""
        with self._lock:
            res = []
            for pid, meta in self._plugins.items():
                info = dict(meta)
                info["is_loaded"] = (pid in self._instances)
                info["is_enabled"] = meta.get("enabled", False)
                try:
                    git_info = self.get_plugin_git_info(pid)
                    info["git"] = git_info
                    info["has_git"] = git_info.get("is_git_repo", False)
                    info["repository"] = git_info.get("repo_url") or meta.get("repository") or meta.get("git_url")
                    info["branch"] = git_info.get("branch") or meta.get("branch") or "main"
                    info["can_update"] = git_info.get("can_update", False)
                except Exception as e:
                    info["git"] = {}
                    info["has_git"] = False
                    info["can_update"] = False
                res.append(info)
            return res

    def get_active_plugins_summary(self) -> List[Dict[str, Any]]:
        """Retorna resumen ligero de plugins activos para inyección en templates."""
        with self._lock:
            return [
                {
                    "id": pid,
                    "name": self._plugins[pid].get("name", pid),
                    "version": self._plugins[pid].get("version", "1.0"),
                    "icon": self._plugins[pid].get("icon", "🧩"),
                    "has_ui": hasattr(self._instances.get(pid), "get_ui_nav_item"),
                    "nav_item": getattr(self._instances.get(pid), "get_ui_nav_item")() if hasattr(self._instances.get(pid), "get_ui_nav_item") else None
                }
                for pid in self._instances
            ]

    def get_admin_cloud_panels(self) -> List[Dict[str, Any]]:
        """
        [EXPERIMENTAL] Recolecta tarjetas/paneles de proveedores cloud provistos por plugins
        para inyección directa en la pestaña Cloud Sync de /admin.
        """
        panels = []
        with self._lock:
            instances = list(self._instances.items())

        for pid, inst in instances:
            if hasattr(inst, "get_admin_cloud_panel"):
                try:
                    cfg = inst.get_config() if hasattr(inst, "get_config") else {}
                    p = inst.get_admin_cloud_panel(cfg)
                    if p and isinstance(p, dict):
                        p.setdefault("plugin_id", pid)
                        p.setdefault("title", self._plugins.get(pid, {}).get("name", pid))
                        p.setdefault("icon", self._plugins.get(pid, {}).get("icon", "☁️"))
                        panels.append(p)
                except Exception as e:
                    logger.error(f"Error obteniendo panel cloud de plugin '{pid}': {e}", exc_info=True)
        return panels

    def get_plugin_instance(self, plugin_id: str):
        """Retorna la instancia en ejecución de un plugin específico o None."""
        with self._lock:
            return self._instances.get(plugin_id)

    def get_download_cloud_options(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        [EXPERIMENTAL] Recolecta opciones de destino cloud para inyección en el selector
        de la interfaz principal de descargas y presets de usuario.
        """
        options = []
        with self._lock:
            instances = list(self._instances.items())

        if not username:
            try:
                from flask import request, session
                user = getattr(request, "current_user", {}) or {}
                username = user.get("username") or getattr(request, "current_username", None) or session.get("username")
            except Exception:
                username = None

        for pid, inst in instances:
            if hasattr(inst, "get_download_cloud_option"):
                try:
                    import inspect
                    sig = inspect.signature(inst.get_download_cloud_option)
                    if "username" in sig.parameters:
                        opt = inst.get_download_cloud_option(username=username)
                    else:
                        opt = inst.get_download_cloud_option()
                    if opt and isinstance(opt, dict):
                        opt.setdefault("plugin_id", pid)
                        opt.setdefault("name", self._plugins.get(pid, {}).get("name", pid))
                        opt.setdefault("icon", self._plugins.get(pid, {}).get("icon", "☁️"))
                        options.append(opt)
                except Exception as e:
                    logger.error(f"Error obteniendo opción de descarga de plugin '{pid}': {e}", exc_info=True)
        return options

    def get_user_cloud_providers(self, username: str = None) -> List[Dict[str, Any]]:
        """
        Retorna los plugins de almacenamiento en la nube disponibles y activados por el usuario.
        Cualquier plugin que implemente get_download_cloud_option o upload_job_for_user
        es compatible con este contrato.
        """
        providers = []
        options = self.get_download_cloud_options(username=username)
        for opt in options:
            pid = opt.get("plugin_id")
            inst = self.get_plugin_instance(pid)
            if not inst:
                continue
            providers.append({
                "id": pid,
                "name": opt.get("name", pid),
                "icon": opt.get("icon", "☁️"),
                "enabled": bool(opt.get("enabled", False)),
                "auto_upload": bool(opt.get("auto_upload", False)),
                "status_label": opt.get("status_label", "DESACTIVADO"),
                "instance": inst
            })
        return providers

    def upload_job_to_cloud(self, plugin_id: str, job_id: str, username: str, progress_callback=None) -> Tuple[bool, Dict[str, Any]]:
        """
        Despacha la subida manual de una descarga hacia un plugin de almacenamiento en la nube específico
        para un usuario determinado, respetando el contrato estandarizado upload_job_for_user.
        """
        inst = self.get_plugin_instance(plugin_id)
        if not inst:
            return False, {"error": f"Extensión de almacenamiento '{plugin_id}' no disponible."}
        if not hasattr(inst, "upload_job_for_user"):
            return False, {"error": f"La extensión '{plugin_id}' no implementa 'upload_job_for_user'."}

        try:
            return inst.upload_job_for_user(job_id=job_id, username=username, progress_callback=progress_callback)
        except Exception as e:
            logger.error(f"Error despachando subida a nube en plugin '{plugin_id}': {e}", exc_info=True)
            return False, {"error": str(e)}

    def upload_file_to_cloud(self, plugin_id: str, filepath: str, username: str, progress_callback=None) -> Tuple[bool, Dict[str, Any]]:
        """
        Permite a cualquier plugin o servicio subir un archivo arbitrario en disco directamente al almacenamiento
        en la nube especificado del usuario (ej: Google Drive, OneDrive), respetando el contrato upload_file_for_user.
        """
        if not filepath or not os.path.isfile(filepath):
            return False, {"error": f"El archivo local a transferir no existe o no es accesible: '{filepath}'"}

        inst = self.get_plugin_instance(plugin_id)
        if not inst:
            return False, {"error": f"Extensión de almacenamiento '{plugin_id}' no disponible o desactivada."}

        if not hasattr(inst, "upload_file_for_user"):
            return False, {"error": f"La extensión '{plugin_id}' no implementa 'upload_file_for_user'."}

        try:
            return inst.upload_file_for_user(filepath=filepath, username=username, progress_callback=progress_callback)
        except Exception as e:
            logger.error(f"Error despachando subida de archivo a nube en plugin '{plugin_id}': {e}", exc_info=True)
            return False, {"error": str(e)}

    def get_user_nav_items(self, username: str = None) -> List[Dict[str, Any]]:
        """
        Recolecta dinámicamente accesos directos o elementos de navegación provistos por los plugins
        para el usuario actual (ej: accesos a ajustes de nube personales como Google Drive, OneDrive, etc.).
        """
        items = []
        with self._lock:
            instances = list(self._instances.items())

        for pid, inst in instances:
            if hasattr(inst, "get_user_nav_item"):
                try:
                    import inspect
                    sig = inspect.signature(inst.get_user_nav_item)
                    if "username" in sig.parameters:
                        item = inst.get_user_nav_item(username=username)
                    else:
                        item = inst.get_user_nav_item()
                    if item and isinstance(item, dict):
                        item.setdefault("id", pid)
                        item.setdefault("title", self._plugins.get(pid, {}).get("name", pid))
                        item.setdefault("icon", self._plugins.get(pid, {}).get("icon", "🔌"))
                        item.setdefault("url", f"/plugin/{pid}/settings")
                        items.append(item)
                except Exception as e:
                    logger.error(f"Error obteniendo nav item de plugin '{pid}': {e}")
        return items

    # =========================================================================
    # TELEGRAM BOT INTEGRATION (Hooks & Dispatchers)
    # =========================================================================

    def dispatch_telegram_command(self, cmd: str, args: list, message: dict, bot) -> bool:
        """
        [EXPERIMENTAL] Despacha un comando de Telegram hacia los plugins activos.
        Retorna True si algún plugin manejó el comando exitosamente.
        """
        with self._lock:
            instances = list(self._instances.items())

        for pid, inst in instances:
            if hasattr(inst, "on_telegram_command"):
                try:
                    handled = inst.on_telegram_command(cmd, args, message, bot)
                    if handled:
                        logger.info(f"Comando de Telegram '{cmd}' manejado por plugin '{pid}'")
                        return True
                except Exception as e:
                    logger.error(f"Excepción al ejecutar comando '{cmd}' en plugin '{pid}': {e}", exc_info=True)
                    try:
                        chat_id = message.get("chat", {}).get("id")
                        if chat_id and hasattr(bot, "send_message"):
                            bot.send_message(chat_id, f"⚠️ Error interno en la extensión '{pid}': {e}")
                        return True
                    except Exception:
                        pass
        return False

    def dispatch_telegram_callback(self, query: dict, data: str, bot) -> bool:
        """
        [EXPERIMENTAL] Despacha una interacción de botón inline (callback_query)
        hacia los plugins activos.
        """
        with self._lock:
            instances = list(self._instances.items())

        for pid, inst in instances:
            if hasattr(inst, "on_telegram_callback"):
                try:
                    handled = inst.on_telegram_callback(query, data, bot)
                    if handled:
                        return True
                except Exception as e:
                    logger.error(f"Excepción en callback Telegram en plugin '{pid}': {e}", exc_info=True)
        return False

    def get_telegram_commands_help(self) -> List[Dict[str, str]]:
        """
        [EXPERIMENTAL] Recolecta la lista de comandos adicionales provistos por los plugins
        para enriquecer el comando /ayuda de Telegram.
        """
        commands = []
        with self._lock:
            instances = list(self._instances.items())

        for pid, inst in instances:
            if hasattr(inst, "get_telegram_commands"):
                try:
                    cmds = inst.get_telegram_commands()
                    if isinstance(cmds, list):
                        for c in cmds:
                            if isinstance(c, dict) and "command" in c:
                                commands.append(c)
                except Exception as e:
                    logger.error(f"Error obteniendo comandos de Telegram de '{pid}': {e}")
        return commands

    # =========================================================================
    # SDK HELPER API PARA PLUGINS (Acceso de conveniencia al Core)
    # =========================================================================

    def enqueue_download(self, url: str, quality: str = "best", format_type: str = "video",
                         owner: str = "admin", title: str = "", extra_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Permite a un plugin (ej. bot secundario de Telegram o webhook externo)
        solicitar una descarga al motor de dHtools sin necesidad de peticiones HTTP.
        """
        try:
            from core.utils import enqueue_job, validate_media_url, normalize_url
            raw_url = (url or "").strip()
            if not raw_url or not validate_media_url(raw_url):
                return {"success": False, "error": "URL no válida o vacía"}

            norm_url = normalize_url(raw_url)
            job_id = uuid.uuid4().hex

            job_spec = {
                "id": job_id,
                "job_id": job_id,
                "url": norm_url,
                "raw_url": raw_url,
                "quality": quality,
                "video_format": extra_params.get("video_format", "mp4") if extra_params else "mp4",
                "format_type": format_type,
                "subtitles": extra_params.get("subtitles", "none") if extra_params else "none",
                "owner": owner,
                "title": title or "Descarga vía Plugin",
                "engine": extra_params.get("engine", "auto") if extra_params else "auto",
                "user_cloud_sync": extra_params.get("user_cloud_sync") if extra_params else None,
                "deezer_arl": extra_params.get("deezer_arl", "") if extra_params else "",
                "status": "queued",
                "percent": 0,
                "speed": None,
                "eta": None,
                "created_at": time.time(),
                "logs": [f"[*] [Plugin] Tarea encolada por extensión de dHtools ({quality})."]
            }

            enqueue_job(job_id, job_spec)
            logger.info(f"Plugin solicitó descarga exitosa: {job_id} ({norm_url})")
            return {"success": True, "job_id": job_id, "url": norm_url}

        except Exception as e:
            logger.error(f"Error al encolar descarga desde plugin: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def get_queue_status(self, username: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna información thread-safe de las tareas activas y en espera para plugins de monitoreo y mensajería.
        Si se especifica username, filtra únicamente las tareas pertenecientes a ese usuario.
        Si username es None, retorna la visión global de la cola.
        """
        try:
            from core.state import JOBS, JOBS_LOCK, QUEUE_LIST, QUEUE_LOCK, ACTIVE_WORKER_JOB

            with QUEUE_LOCK:
                q_ids = list(QUEUE_LIST)

            active_jobs = []
            queued_jobs = []

            with JOBS_LOCK:
                # Tarea actualmente en descarga por el worker en segundo plano
                if ACTIVE_WORKER_JOB and ACTIVE_WORKER_JOB in JOBS:
                    j = JOBS[ACTIVE_WORKER_JOB]
                    if not username or j.get("owner") == username:
                        active_jobs.append({
                            "job_id": ACTIVE_WORKER_JOB,
                            "title": j.get("title") or j.get("video_title") or "Descarga en curso",
                            "status": j.get("status", "downloading"),
                            "percent": j.get("percent", 0),
                            "speed": j.get("speed"),
                            "eta": j.get("eta"),
                            "owner": j.get("owner"),
                            "format_type": j.get("format_type", "video"),
                            "quality": j.get("quality", "best")
                        })

                # Tareas en espera en la cola
                for jid in q_ids:
                    if jid == ACTIVE_WORKER_JOB:
                        continue
                    j = JOBS.get(jid)
                    if j and (not username or j.get("owner") == username):
                        queued_jobs.append({
                            "job_id": jid,
                            "title": j.get("title") or j.get("video_title") or j.get("url"),
                            "status": j.get("status", "queued"),
                            "percent": j.get("percent", 0),
                            "owner": j.get("owner"),
                            "format_type": j.get("format_type", "video"),
                            "quality": j.get("quality", "best")
                        })

            return {
                "active_jobs": active_jobs,
                "queued_jobs": queued_jobs,
                "total_active": len(active_jobs),
                "total_queued": len(queued_jobs),
                "total": len(active_jobs) + len(queued_jobs)
            }

        except Exception as e:
            logger.error(f"Error al obtener estado de la cola para plugin: {e}", exc_info=True)
            return {
                "active_jobs": [],
                "queued_jobs": [],
                "total_active": 0,
                "total_queued": 0,
                "total": 0,
                "error": str(e)
            }

    def restart_process(self, delay: float = 1.5) -> None:
        """
        [EXPERIMENTAL] Solicita un reinicio ordenado del proceso del servidor (Docker / Gunicorn)
        con un retardo de cortesía en segundos para permitir responder a la petición actual.
        """
        try:
            from core.downloader import restart_process_soon
            logger.info(f"Plugin solicitó reinicio del sistema en {delay}s...")
            restart_process_soon(delay)
        except Exception as e:
            logger.error(f"Error al solicitar reinicio de proceso desde plugin: {e}", exc_info=True)

    def _ensure_git_safe_directory(self, path: Optional[str] = None):
        """Configura safe.directory en Git para evitar errores de permisos en contenedores."""
        try:
            subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True, timeout=2)
            if path and os.path.exists(path):
                subprocess.run(["git", "config", "--global", "--add", "safe.directory", path], capture_output=True, timeout=2)
        except Exception:
            pass

    def get_plugin_git_info(self, plugin_id: str) -> Dict[str, Any]:
        """
        [EXPERIMENTAL] Obtiene información del repositorio Git o GitHub de un plugin.
        Detecta tanto subcarpetas clonadas con .git como manifiestos con 'repository' declarado.
        """
        with self._lock:
            meta = self._plugins.get(plugin_id, {})
        plugin_path = meta.get("_path")

        is_git_repo = False
        repo_url = meta.get("repository") or meta.get("git_url") or meta.get("github") or ""
        branch = meta.get("branch") or "main"
        commit = "unknown"
        commit_date = ""

        if plugin_path and os.path.isdir(os.path.join(plugin_path, ".git")):
            is_git_repo = True
            self._ensure_git_safe_directory(plugin_path)
            try:
                r_url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=plugin_path, capture_output=True, text=True, timeout=3)
                if r_url.returncode == 0 and r_url.stdout.strip():
                    repo_url = r_url.stdout.strip()
            except Exception:
                pass

            try:
                r_head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=plugin_path, capture_output=True, text=True, timeout=3)
                if r_head.returncode == 0 and r_head.stdout.strip():
                    commit = r_head.stdout.strip()
            except Exception:
                pass

            try:
                r_br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=plugin_path, capture_output=True, text=True, timeout=3)
                if r_br.returncode == 0 and r_br.stdout.strip() and r_br.stdout.strip() != "HEAD":
                    branch = r_br.stdout.strip()
            except Exception:
                pass

            try:
                r_date = subprocess.run(["git", "log", "-1", "--format=%cd", "--date=short"], cwd=plugin_path, capture_output=True, text=True, timeout=3)
                if r_date.returncode == 0 and r_date.stdout.strip():
                    commit_date = r_date.stdout.strip()
            except Exception:
                pass

        # Normalizar repo_url y extraer owner/repo de GitHub si corresponde
        github_repo = None
        if repo_url:
            clean_url = repo_url.strip()
            if clean_url.startswith("git@github.com:"):
                clean_url = clean_url.replace("git@github.com:", "https://github.com/")
            if clean_url.endswith(".git"):
                clean_url = clean_url[:-4]
            m = re.search(r"github\.com/([^/\s]+/[^/\s]+)", clean_url)
            if m:
                github_repo = m.group(1)
            elif "/" in clean_url and not clean_url.startswith("http"):
                github_repo = clean_url
                clean_url = f"https://github.com/{clean_url}"
            repo_url = clean_url

        return {
            "plugin_id": plugin_id,
            "is_git_repo": is_git_repo,
            "repo_url": repo_url,
            "github_repo": github_repo,
            "branch": branch,
            "commit": commit,
            "commit_date": commit_date,
            "can_update": bool(repo_url or is_git_repo)
        }

    def check_plugin_update(self, plugin_id: str) -> Dict[str, Any]:
        """
        [EXPERIMENTAL] Consulta si existe una versión o commit más reciente en GitHub para el plugin.
        """
        with self._lock:
            meta = self._plugins.get(plugin_id, {})
        git_info = self.get_plugin_git_info(plugin_id)

        current_version = meta.get("version", "1.0.0")
        current_commit = git_info.get("commit")

        result = {
            "plugin_id": plugin_id,
            "name": meta.get("name", plugin_id),
            "version": current_version,
            "repository": git_info.get("repo_url"),
            "github_repo": git_info.get("github_repo"),
            "branch": git_info.get("branch", "main"),
            "current_commit": current_commit,
            "is_git_repo": git_info.get("is_git_repo", False),
            "remote_commit": None,
            "remote_version": None,
            "commit_message": None,
            "commit_date": None,
            "update_available": False,
            "can_update": git_info.get("can_update", False),
            "error": None
        }

        if not result["can_update"]:
            result["error"] = "Plugin no declara repositorio ni es un repositorio Git."
            return result

        def _v_tuple(v):
            try:
                return tuple(int(x) for x in re.findall(r"\d+", str(v)))
            except Exception:
                return (0,)

        gh_repo = git_info.get("github_repo")
        branch = git_info.get("branch", "main")
        checked_via_api = False

        if gh_repo:
            # 1. Consultar último commit en GitHub API
            try:
                commit_url = f"https://api.github.com/repos/{gh_repo}/commits/{branch}"
                r = requests.get(commit_url, headers={"User-Agent": "dHtools-PluginManager"}, timeout=4)
                if r.status_code == 200:
                    cdata = r.json()
                    sha = (cdata.get("sha") or "")[:7]
                    result["remote_commit"] = sha
                    result["commit_message"] = (cdata.get("commit", {}).get("message") or "").splitlines()[0]
                    result["commit_date"] = cdata.get("commit", {}).get("committer", {}).get("date", "")[:10]
                    checked_via_api = True

                    if current_commit and current_commit != "unknown" and sha and sha != current_commit:
                        result["update_available"] = True
            except Exception as e:
                logger.debug(f"Error consultando commits de GitHub para {plugin_id}: {e}")

            # 2. Consultar releases / tags para comparar SemVer
            try:
                rel_url = f"https://api.github.com/repos/{gh_repo}/releases/latest"
                r = requests.get(rel_url, headers={"User-Agent": "dHtools-PluginManager"}, timeout=4)
                if r.status_code == 200:
                    rel_data = r.json()
                    tag = (rel_data.get("tag_name") or "").lstrip("v")
                    if tag:
                        result["remote_version"] = tag
                        if _v_tuple(tag) > _v_tuple(current_version):
                            result["update_available"] = True
            except Exception as e:
                logger.debug(f"Error consultando releases de GitHub para {plugin_id}: {e}")

        # Si no se pudo verificar por API o no es de GitHub directo, usar git ls-remote si es posible
        if not checked_via_api and git_info.get("repo_url"):
            try:
                self._ensure_git_safe_directory()
                cmd = ["git", "ls-remote", git_info["repo_url"], f"refs/heads/{branch}"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                if res.returncode == 0 and res.stdout.strip():
                    parts = res.stdout.strip().split()
                    if parts:
                        remote_sha = parts[0][:7]
                        result["remote_commit"] = remote_sha
                        if current_commit and current_commit != "unknown" and remote_sha != current_commit:
                            result["update_available"] = True
            except Exception as e:
                if not result.get("error"):
                    result["error"] = str(e)

        return result

    def check_all_plugin_updates(self) -> List[Dict[str, Any]]:
        """[EXPERIMENTAL] Comprueba actualizaciones de todos los plugins descubiertos."""
        with self._lock:
            plugin_ids = list(self._plugins.keys())

        updates = []
        for pid in plugin_ids:
            try:
                res = self.check_plugin_update(pid)
                updates.append(res)
            except Exception as e:
                logger.error(f"Error al verificar actualización de '{pid}': {e}")
                updates.append({
                    "plugin_id": pid,
                    "name": pid,
                    "error": str(e),
                    "can_update": False,
                    "update_available": False
                })
        return updates

    def update_plugin(self, plugin_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        [EXPERIMENTAL] Actualiza un plugin desde GitHub o su repositorio Git.
        Preserva automáticamente config.json y credenciales privadas del plugin.
        """
        with self._lock:
            meta = self._plugins.get(plugin_id)
            if not meta:
                return False, f"Plugin '{plugin_id}' no encontrado.", {}

        plugin_path = meta.get("_path")
        if not plugin_path or not os.path.isdir(plugin_path):
            return False, f"Directorio de plugin inválido: {plugin_path}", {}

        git_info = self.get_plugin_git_info(plugin_id)
        if not git_info.get("can_update"):
            return False, f"El plugin '{plugin_id}' no posee un repositorio configurado ni es un repositorio Git.", {}

        repo_url = git_info.get("repo_url")
        branch = git_info.get("branch") or "main"

        # 1. Respaldar archivos privados (config.json, credenciales, etc.)
        preserved_files = {}
        for fname in ["config.json", "credentials.json", "token.json", "data.json", ".env"]:
            fpath = os.path.join(plugin_path, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "rb") as f:
                        preserved_files[fname] = f.read()
                    logger.info(f"Archivo protegido respaldado para actualización: {fname} en '{plugin_id}'")
                except Exception as err:
                    logger.warning(f"No se pudo respaldar {fname} en '{plugin_id}': {err}")

        self._ensure_git_safe_directory(plugin_path)
        output_log = []

        try:
            if git_info.get("is_git_repo"):
                # Actualización de repositorio Git existente
                logger.info(f"Actualizando plugin Git '{plugin_id}' desde {repo_url} (rama {branch})...")
                fetch_res = subprocess.run(["git", "fetch", "origin"], cwd=plugin_path, capture_output=True, text=True, timeout=45)
                output_log.append(f"[git fetch]\n{fetch_res.stdout}\n{fetch_res.stderr}")

                pull_res = subprocess.run(["git", "pull", "--rebase", "origin", branch], cwd=plugin_path, capture_output=True, text=True, timeout=60)
                output_log.append(f"[git pull --rebase]\n{pull_res.stdout}\n{pull_res.stderr}")

                if pull_res.returncode != 0:
                    logger.warning(f"Pull con rebase falló en '{plugin_id}', aplicando reset a origin/{branch}...")
                    reset_res = subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=plugin_path, capture_output=True, text=True, timeout=30)
                    output_log.append(f"[git reset --hard]\n{reset_res.stdout}\n{reset_res.stderr}")
                    if reset_res.returncode != 0:
                        raise RuntimeError(f"Fallo al restaurar repositorio a origin/{branch}: {reset_res.stderr}")
            else:
                # Inicializar y clonar rama en directorio existente sin .git
                logger.info(f"Inicializando Git y descargando '{plugin_id}' desde {repo_url}...")
                subprocess.run(["git", "init"], cwd=plugin_path, capture_output=True, timeout=15)
                subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=plugin_path, capture_output=True, timeout=15)
                fetch_res = subprocess.run(["git", "fetch", "origin"], cwd=plugin_path, capture_output=True, text=True, timeout=60)
                output_log.append(f"[git init & fetch]\n{fetch_res.stdout}\n{fetch_res.stderr}")
                co_res = subprocess.run(["git", "checkout", "-f", "-B", branch, f"origin/{branch}"], cwd=plugin_path, capture_output=True, text=True, timeout=30)
                output_log.append(f"[git checkout]\n{co_res.stdout}\n{co_res.stderr}")
                if co_res.returncode != 0:
                    raise RuntimeError(f"Fallo en checkout de {branch}: {co_res.stderr}")

            # 2. Restaurar archivos privados protegidos
            for fname, data in preserved_files.items():
                dest_path = os.path.join(plugin_path, fname)
                try:
                    with open(dest_path, "wb") as f:
                        f.write(data)
                    logger.info(f"Archivo protegido restaurado con éxito: {fname} en '{plugin_id}'")
                except Exception as err:
                    logger.error(f"Error al restaurar {fname} en '{plugin_id}': {err}")

            # 3. Recargar manifiesto actualizado
            manifest_file = os.path.join(plugin_path, "plugin.json")
            if os.path.exists(manifest_file):
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        new_manifest = json.load(f)
                    new_manifest["_folder"] = meta.get("_folder", plugin_id)
                    new_manifest["_path"] = plugin_path
                    new_manifest["_entry"] = os.path.join(plugin_path, "plugin.py")
                    new_manifest["experimental"] = True
                    with self._lock:
                        self._plugins[plugin_id] = new_manifest
                except Exception as err:
                    logger.error(f"Error releyendo manifiesto de '{plugin_id}': {err}")

            # 4. Recargar plugin en memoria
            reloaded = self.reload_plugin(plugin_id)
            new_git = self.get_plugin_git_info(plugin_id)
            new_ver = self._plugins.get(plugin_id, {}).get("version", "1.0.0")

            msg = f"Plugin '{plugin_id}' actualizado exitosamente a v{new_ver} (commit {new_git.get('commit')})."
            if reloaded:
                msg += " Plugin recargado en memoria."
            logger.info(msg)

            return True, msg, {
                "plugin_id": plugin_id,
                "version": new_ver,
                "commit": new_git.get("commit"),
                "reloaded": reloaded,
                "output": "\n".join(output_log)
            }

        except Exception as e:
            logger.error(f"Error actualizando plugin '{plugin_id}': {e}", exc_info=True)
            # Restaurar archivos protegidos incluso en caso de fallo
            for fname, data in preserved_files.items():
                dest_path = os.path.join(plugin_path, fname)
                try:
                    with open(dest_path, "wb") as f:
                        f.write(data)
                except Exception:
                    pass
            return False, f"Error al actualizar plugin '{plugin_id}': {str(e)}", {
                "plugin_id": plugin_id,
                "output": "\n".join(output_log)
            }

    def reload_plugin(self, plugin_id: str) -> bool:
        """
        [EXPERIMENTAL] Recarga en caliente un plugin específico en memoria sin reiniciar dHtools.
        """
        with self._lock:
            meta = self._plugins.get(plugin_id)
            if not meta:
                return False

            # Limpiar instancia previa si existe
            if plugin_id in self._instances:
                old_inst = self._instances.pop(plugin_id, None)
                if hasattr(old_inst, "on_unload"):
                    try:
                        old_inst.on_unload()
                    except Exception as e:
                        logger.warning(f"Error en on_unload de '{plugin_id}': {e}")

            # Limpiar módulos de sys.modules
            prefix = f"plugins.{plugin_id}"
            legacy_name = f"dhtools_plugin_{plugin_id}"
            to_del = [m for m in list(sys.modules.keys()) if m == prefix or m.startswith(f"{prefix}.") or m == legacy_name]
            for m in to_del:
                sys.modules.pop(m, None)

            # Volver a cargar si está habilitado
            if meta.get("enabled", False):
                self._load_plugin(plugin_id, meta)
                return plugin_id in self._instances
            return True


# Singleton global
plugin_manager = PluginManager()

