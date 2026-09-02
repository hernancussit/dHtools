import os
import secrets

def get_or_create_flask_secret() -> str:
    env_secret = os.environ.get("FLASK_SECRET_KEY")
    if env_secret and env_secret.strip() and env_secret != "dhtools_secret_session_key_2026_super_secure":
        return env_secret.strip()
    secret_file = "/app/.flask_secret" if os.path.exists("/app") else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".flask_secret")
    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r", encoding="utf-8") as f:
                sec = f.read().strip()
                if sec:
                    return sec
        generated = secrets.token_hex(32)
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(generated)
        try:
            os.chmod(secret_file, 0o600)
        except Exception as e:
            pass
        return generated
    except Exception as e:
        return secrets.token_hex(32)

APP_VERSION = "1.2.0"
APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")

MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes lockout

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _resolve_path(env_var: str, default_filename: str) -> str:
    val = os.environ.get(env_var)
    if val:
        return val
    if os.path.exists("/app"):
        return f"/app/{default_filename}"
    return os.path.join(BASE_DIR, default_filename)

COOKIES_FILE = _resolve_path("COOKIES_FILE", "cookies.txt")
USERS_FILE = _resolve_path("USERS_FILE", "users.json")
CONFIG_FILE = _resolve_path("CONFIG_FILE", "config.json")
CLOUD_CONFIG_FILE = _resolve_path("CLOUD_CONFIG_FILE", "cloud_sync.json")
DOWNLOADS_META_FILE = _resolve_path("DOWNLOADS_META_FILE", "downloads_meta.json")
QUEUE_STATE_FILE = _resolve_path("QUEUE_STATE_FILE", "queue_state.json")
ROLLBACK_STATE_FILE = _resolve_path("ROLLBACK_STATE_FILE", "rollback_state.json")
POT_PROVIDER_URL = os.environ.get("POT_PROVIDER_URL", "http://potprovider:4416")
COBALT_URL = os.environ.get("COBALT_URL", "http://cobalt:9000/")

PLAYER_CLIENTS_ENV = os.environ.get("PLAYER_CLIENTS", "default")
DOWNLOAD_DIR = _resolve_path("DOWNLOAD_DIR", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

AUTO_UPDATE_YTDLP = os.environ.get("AUTO_UPDATE_YTDLP", "true").lower() == "true"
AUTO_UPDATE_INTERVAL_HOURS = float(os.environ.get("AUTO_UPDATE_INTERVAL_HOURS", "24"))
CLEANUP_AFTER_HOURS = float(os.environ.get("CLEANUP_AFTER_HOURS", "24"))
CLEANUP_CHECK_INTERVAL_MINUTES = float(os.environ.get("CLEANUP_CHECK_INTERVAL_MINUTES", "30"))
DISK_EMERGENCY_THRESHOLD_PERCENT = float(os.environ.get("DISK_EMERGENCY_THRESHOLD_PERCENT", "85"))
DISK_EMERGENCY_MIN_FREE_GB = float(os.environ.get("DISK_EMERGENCY_MIN_FREE_GB", "2"))

