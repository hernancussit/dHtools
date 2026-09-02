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

APP_VERSION = "1.1.1"
APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")

MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes lockout

COOKIES_FILE = os.environ.get("COOKIES_FILE", "/app/cookies.txt")
USERS_FILE = os.environ.get("USERS_FILE", "/app/users.json")
CONFIG_FILE = os.environ.get("CONFIG_FILE", "/app/config.json")
CLOUD_CONFIG_FILE = os.environ.get("CLOUD_CONFIG_FILE", "/app/cloud_sync.json")
DOWNLOADS_META_FILE = os.environ.get("DOWNLOADS_META_FILE", "/app/downloads_meta.json")
QUEUE_STATE_FILE = os.environ.get("QUEUE_STATE_FILE", "/app/queue_state.json")
ROLLBACK_STATE_FILE = os.environ.get("ROLLBACK_STATE_FILE", "/app/rollback_state.json")
POT_PROVIDER_URL = os.environ.get("POT_PROVIDER_URL", "http://potprovider:4416")
COBALT_URL = os.environ.get("COBALT_URL", "http://cobalt:9000/")

PLAYER_CLIENTS_ENV = os.environ.get("PLAYER_CLIENTS", "default")
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/app/downloads")

AUTO_UPDATE_INTERVAL_HOURS = 24
CLEANUP_CHECK_INTERVAL_MINUTES = 30

