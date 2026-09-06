import os
import threading
from flask import Flask, request, session

from core.config import get_or_create_flask_secret, APP_VERSION
from core.state import START_TIME
from core.downloader import background_queue_worker, cleanup_loop, auto_update_loop

from routes.auth import auth_bp, protect_all_routes
from routes.admin import admin_bp
from routes.api import api_bp
from routes.ui import ui_bp
from core.plugin_manager import plugin_manager

app = Flask(__name__)

# Flask Config
app.secret_key = get_or_create_flask_secret()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(ui_bp)

# [EXPERIMENTAL] Initialize Plugin Manager and dynamic blueprints
plugin_manager.init_app(app)

# Global Security
app.before_request(protect_all_routes)

# Inject variables for templates globally
@app.context_processor
def inject_globals():
    from core.utils import load_config
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username") or getattr(request, "current_username", None) or session.get("username", "admin")

    google_drive_enabled = False
    try:
        gdrive_inst = plugin_manager.get_plugin_instance("google_drive")
        if gdrive_inst and hasattr(gdrive_inst, "get_user_config"):
            u_cfg = gdrive_inst.get_user_config(username)
            google_drive_enabled = bool(u_cfg.get("enabled", False))
    except Exception:
        google_drive_enabled = False

    return {
        "version": APP_VERSION,
        "config": load_config(),
        "plugins": plugin_manager.get_active_plugins_summary(),
        "plugin_cloud_admin_panels": plugin_manager.get_admin_cloud_panels(),
        "plugin_download_cloud_options": plugin_manager.get_download_cloud_options(username=username),
        "google_drive_enabled": google_drive_enabled
    }

from core.telegram_bot import telegram_bot

# Start background worker threads (queue processor, cleanup, auto-updater, telegram bot, plugins)
_threads_started = False
_threads_lock = threading.Lock()

def start_background_threads():
    global _threads_started
    with _threads_lock:
        if not _threads_started:
            threading.Thread(target=background_queue_worker, daemon=True).start()
            threading.Thread(target=cleanup_loop, daemon=True).start()
            threading.Thread(target=auto_update_loop, daemon=True).start()
            telegram_bot.start()
            plugin_manager.start_background_plugins()
            _threads_started = True

start_background_threads()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

