import os
import threading
from flask import Flask

from core.config import get_or_create_flask_secret, APP_VERSION
from core.state import START_TIME
from core.downloader import background_queue_worker, cleanup_loop, auto_update_loop

from routes.auth import auth_bp, protect_all_routes
from routes.admin import admin_bp
from routes.api import api_bp
from routes.ui import ui_bp

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

# Global Security
app.before_request(protect_all_routes)

# Inject variables for templates globally
@app.context_processor
def inject_globals():
    from core.utils import load_config
    return {
        "version": APP_VERSION,
        "config": load_config()
    }

# Start background worker threads (queue processor, cleanup, auto-updater)
_threads_started = False
_threads_lock = threading.Lock()

def start_background_threads():
    global _threads_started
    with _threads_lock:
        if not _threads_started:
            threading.Thread(target=background_queue_worker, daemon=True).start()
            threading.Thread(target=cleanup_loop, daemon=True).start()
            threading.Thread(target=auto_update_loop, daemon=True).start()
            _threads_started = True

start_background_threads()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

