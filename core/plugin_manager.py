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
import threading
import uuid
import time
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
            module_name = f"dhtools_plugin_{plugin_id}"
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


# Singleton global
plugin_manager = PluginManager()

