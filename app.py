import os
import re
import sys
import time
import uuid
import shutil
import secrets
import threading
import subprocess
import zipfile
import json
import hashlib
import functools
import ftplib
import requests
from flask import Flask, request, jsonify, send_file, render_template, abort, Response, session, redirect, url_for

import yt_dlp
from yt_dlp.utils import download_range_func

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ytsite_secret_session_key_2026_super_secure")
APP_VERSION = "2.7.4"






APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")


COOKIES_FILE = os.environ.get("COOKIES_FILE", "/app/cookies.txt")
USERS_FILE = os.environ.get("USERS_FILE", "/app/users.json")
CONFIG_FILE = os.environ.get("CONFIG_FILE", "/app/config.json")
CLOUD_CONFIG_FILE = os.environ.get("CLOUD_CONFIG_FILE", "/app/cloud_sync.json")
DOWNLOADS_META_FILE = os.environ.get("DOWNLOADS_META_FILE", "/app/downloads_meta.json")
QUEUE_STATE_FILE = os.environ.get("QUEUE_STATE_FILE", "/app/queue_state.json")
POT_PROVIDER_URL = os.environ.get("POT_PROVIDER_URL", "http://potprovider:4416")
COBALT_URL = os.environ.get("COBALT_URL", "http://cobalt:9000/")
START_TIME = time.time()

JOBS = {}
JOBS_LOCK = threading.RLock()
BATCH_JOBS = {}
BATCH_LOCK = threading.RLock()
QUEUE_LIST = []
QUEUE_LOCK = threading.RLock()
ACTIVE_WORKER_JOB = None






def cookies_opts():
    if os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        return {"cookiefile": COOKIES_FILE}
    return {}


PLAYER_CLIENTS_ENV = os.environ.get("PLAYER_CLIENTS", "default").strip()


def player_client_opts(clients=None, for_download: bool = True):
    opts = {"extractor_args": {}}
    if for_download:
        opts["extractor_args"]["youtubepot-bgutilhttp"] = {"base_url": [POT_PROVIDER_URL]}

    target = clients
    if target is None and PLAYER_CLIENTS_ENV and PLAYER_CLIENTS_ENV != "default":
        target = PLAYER_CLIENTS_ENV.split(",")
    if target and target != ["default"] and target != "default":
        if isinstance(target, str):
            target = [target]
        opts["extractor_args"]["youtube"] = {"player_client": target}
    return opts




def hash_password(password: str) -> str:
    salt = "ytsite_salt_2026"
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return secrets.compare_digest(hash_password(password), hashed)


def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for uinfo in data.values():
                    if "status" not in uinfo:
                        uinfo["status"] = "active"
                return data
        except Exception:
            pass
    initial_users = {
        APP_USERNAME: {
            "password_hash": hash_password(APP_PASSWORD),
            "role": "admin",
            "status": "active",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    }
    save_users(initial_users)
    return initial_users


def save_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def check_auth(username, password):
    if not username or not password:
        return False
    users = load_users()
    if username in users:
        u = dict(users[username])
        u["username"] = username
        if verify_password(password, u.get("password_hash", "")) or (username == APP_USERNAME and secrets.compare_digest(password, APP_PASSWORD)):
            if u.get("status") == "suspended":
                return "SUSPENDED"
            return u
    if secrets.compare_digest(username, APP_USERNAME) and secrets.compare_digest(password, APP_PASSWORD):
        return {"role": "admin", "username": username, "status": "active"}
    return False


@app.before_request
def protect_all_routes():
    # Allow public endpoints without authentication
    if (
        request.path == "/login"
        or request.path == "/logout"
        or request.path.startswith("/static/")
        or request.path in ("/manifest.json", "/sw.js")
    ):
        return None

    # 1. Check Flask Web Session
    sess_user = session.get("username")
    if sess_user:
        users = load_users()
        if sess_user in users:
            u = dict(users[sess_user])
            u["username"] = sess_user
            if u.get("status") == "suspended":
                session.clear()
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Tu cuenta se encuentra suspendida por el administrador."}), 403
                return redirect(url_for("login", error="Tu cuenta ha sido suspendida."))
            request.current_user = u
            request.current_username = sess_user
            return None
        elif secrets.compare_digest(sess_user, APP_USERNAME):
            request.current_user = {"role": "admin", "username": sess_user, "status": "active"}
            request.current_username = sess_user
            return None

    # 2. Check HTTP Basic Auth (for automated tests / API clients)
    auth = request.authorization
    if auth:
        u = check_auth(auth.username, auth.password)
        if u == "SUSPENDED":
            return Response("Acceso denegado: tu cuenta ha sido suspendida por el administrador.", 403)
        if u:
            request.current_user = u
            request.current_username = auth.username
            return None

    # 3. Unauthenticated requests
    if request.path.startswith("/api/"):
        return jsonify({"error": "Autenticación requerida. Iniciá sesión en la web o enviá credenciales HTTP Basic."}), 401

    next_param = request.full_path.rstrip("?") if request.path != "/" else None
    return redirect(url_for("login", next=next_param))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next") or "/"

        u = check_auth(username, password)
        if u == "SUSPENDED":
            return render_template(
                "login.html",
                config=load_config(),
                error="Tu cuenta se encuentra suspendida por el administrador.",
                username=username,
                next_url=next_url,
            ), 403
        if not u:
            return render_template(
                "login.html",
                config=load_config(),
                error="Usuario o contraseña incorrectos.",
                username=username,
                next_url=next_url,
            ), 401

        session["username"] = u.get("username", username)
        session["role"] = u.get("role", "downloader")
        return redirect(next_url if next_url.startswith("/") else "/")

    if session.get("username"):
        return redirect("/")

    return render_template(
        "login.html",
        config=load_config(),
        error=request.args.get("error"),
        msg=request.args.get("msg"),
        next_url=request.args.get("next"),
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login", msg="logged_out"))


def require_admin(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        u = getattr(request, "current_user", None)
        if not u or u.get("role") != "admin":
            return jsonify({"error": "Acceso denegado: se requieren permisos de Administrador"}), 403


        return f(*args, **kwargs)
    return decorated



def get_ytdlp_version():
    try:
        return yt_dlp.version.__version__
    except Exception:
        return "desconocida"


def run_pip_update():
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]"],
        capture_output=True, text=True, timeout=180,
    )


def restart_process_soon(delay=1.5):
    def _restart():
        time.sleep(delay)
        os._exit(0)
    threading.Thread(target=_restart, daemon=True).start()


@app.route("/api/ytdlp-version")
def ytdlp_version():
    return jsonify({"version": get_ytdlp_version()})


@app.route("/api/update-ytdlp", methods=["POST"])
def update_ytdlp():
    old_version = get_ytdlp_version()
    try:
        result = run_pip_update()
    except Exception as e:
        return jsonify({"error": f"No se pudo ejecutar la actualización: {e}"}), 500

    if result.returncode != 0:
        return jsonify({"error": (result.stderr or "Error desconocido")[-1000:]}), 500

    updated = "Successfully installed" in (result.stdout or "")

    if updated:
        restart_process_soon()
        return jsonify({
            "updated": True,
            "old_version": old_version,
            "message": "yt-dlp se actualizó. El servicio se está reiniciando, esperá unos segundos y recargá la página.",
        })

    return jsonify({
        "updated": False,
        "old_version": old_version,
        "message": "yt-dlp ya estaba en la última versión.",
    })


AUTO_UPDATE_YTDLP = os.environ.get("AUTO_UPDATE_YTDLP", "true").lower() == "true"
AUTO_UPDATE_INTERVAL_HOURS = float(os.environ.get("AUTO_UPDATE_INTERVAL_HOURS", "24"))


def auto_update_loop():
    while True:
        time.sleep(max(AUTO_UPDATE_INTERVAL_HOURS, 1) * 3600)
        try:
            result = run_pip_update()
            if result.returncode == 0 and "Successfully installed" in (result.stdout or ""):
                restart_process_soon(delay=0)
        except Exception:
            pass


if AUTO_UPDATE_YTDLP and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    threading.Thread(target=auto_update_loop, daemon=True).start()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

CLEANUP_AFTER_HOURS = float(os.environ.get("CLEANUP_AFTER_HOURS", "24"))
CLEANUP_CHECK_INTERVAL_MINUTES = float(os.environ.get("CLEANUP_CHECK_INTERVAL_MINUTES", "30"))

# job_id -> dict con status, progreso, metadatos de playlist, etc.
JOBS = {}
JOBS_LOCK = threading.Lock()


def format_speed(bytes_per_sec):
    if not bytes_per_sec:
        return None
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.1f} {unit}"
        bytes_per_sec /= 1024
    return f"{bytes_per_sec:.1f} TB/s"


DISK_EMERGENCY_THRESHOLD_PERCENT = float(os.environ.get("DISK_EMERGENCY_THRESHOLD_PERCENT", "85"))
DISK_EMERGENCY_MIN_FREE_GB = float(os.environ.get("DISK_EMERGENCY_MIN_FREE_GB", "2"))


def load_config() -> dict:
    default_cfg = {
        "site_title": "🎬 Descargador Multimedia",
        "site_subtitle": "Descargá videos, playlists o música pegando el enlace.",
        "default_theme": "cyberpunk",
        "cleanup_after_hours": CLEANUP_AFTER_HOURS,
        "disk_emergency_threshold": DISK_EMERGENCY_THRESHOLD_PERCENT,
        "default_engine": "ytdlp",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default_cfg.update(cfg)
        except Exception:
            pass
    return default_cfg


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_cloud_config() -> dict:
    default_cfg = {
        "webdav": {"enabled": False, "url": "", "username": "", "password": "", "remote_path": "/ytsite"},
        "ftp": {"enabled": False, "host": "", "port": 21, "username": "", "password": "", "remote_dir": "/"},
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "webhook": {"enabled": False, "url": ""},
    }
    if os.path.exists(CLOUD_CONFIG_FILE):
        try:
            with open(CLOUD_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                for k, v in cfg.items():
                    if k in default_cfg and isinstance(v, dict):
                        default_cfg[k].update(v)
        except Exception:
            pass
    return default_cfg


def save_cloud_config(cfg: dict):
    with open(CLOUD_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_downloads_meta() -> dict:
    if os.path.exists(DOWNLOADS_META_FILE):
        try:
            with open(DOWNLOADS_META_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_downloads_meta(meta: dict):
    try:
        with open(DOWNLOADS_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving downloads meta: {e}")


def record_download_meta(job_id: str, filename: str, username: str, size_bytes: int, folder_name: str = None, group_id: str = None):
    meta = load_downloads_meta()
    meta[job_id] = {
        "job_id": job_id,
        "filename": filename,
        "username": username or "admin",
        "size_bytes": size_bytes,
        "created_at": time.time(),
        "folder_name": folder_name,
        "group_id": group_id,
    }
    save_downloads_meta(meta)


def delete_download_meta(job_id: str):
    meta = load_downloads_meta()
    if job_id in meta:
        meta.pop(job_id, None)
        save_downloads_meta(meta)


def save_queue_state():
    try:
        with QUEUE_LOCK:
            q_ids = list(QUEUE_LIST)
        with JOBS_LOCK:
            jobs_to_save = {
                jid: {k: v for k, v in JOBS[jid].items() if k not in ("user_cloud_sync",)}
                for jid in q_ids if jid in JOBS and JOBS[jid].get("status") in ("queued", "downloading")
            }
        state = {"queue": q_ids, "jobs": jobs_to_save}
        with open(QUEUE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_queue_state():
    global QUEUE_LIST
    if os.path.exists(QUEUE_STATE_FILE):
        try:
            with open(QUEUE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                saved_jobs = state.get("jobs", {})
                with JOBS_LOCK:
                    for jid, data in saved_jobs.items():
                        if jid not in JOBS:
                            data["status"] = "queued"
                            JOBS[jid] = data
                with QUEUE_LOCK:
                    QUEUE_LIST = [jid for jid in state.get("queue", []) if jid in saved_jobs]
        except Exception:
            pass


def enqueue_job(job_id: str, job_spec: dict):
    with JOBS_LOCK:
        JOBS[job_id] = job_spec
    with QUEUE_LOCK:
        if job_id not in QUEUE_LIST:
            QUEUE_LIST.append(job_id)
    save_queue_state()



def sync_to_cloud(filepath: str, filename: str, job_info: dict = None, user_cloud_cfg: dict = None):
    if not filepath or not os.path.exists(filepath):
        return
    cfg = load_cloud_config()
    
    # If user provided their own cloud settings (e.g. Nextcloud/WebDAV, FTP, Webhook), merge/prioritize them
    if user_cloud_cfg and isinstance(user_cloud_cfg, dict):
        if "webdav" in user_cloud_cfg and user_cloud_cfg["webdav"].get("enabled"):
            cfg["webdav"] = user_cloud_cfg["webdav"]
        if "ftp" in user_cloud_cfg and user_cloud_cfg["ftp"].get("enabled"):
            cfg["ftp"] = user_cloud_cfg["ftp"]
        if "webhook" in user_cloud_cfg and user_cloud_cfg["webhook"].get("enabled"):
            cfg["webhook"] = user_cloud_cfg["webhook"]

    # 1. Webhook
    if cfg.get("webhook", {}).get("enabled") and cfg["webhook"].get("url"):
        try:
            requests.post(
                cfg["webhook"]["url"],
                json={
                    "event": "download_completed",
                    "filename": filename,
                    "size_bytes": os.path.getsize(filepath),
                    "job_info": job_info or {},
                    "timestamp": time.time(),
                },
                timeout=10,
            )
        except Exception as e:
            print(f"[CloudSync Webhook Error] {e}")

    # 2. WebDAV / Nextcloud
    wd = cfg.get("webdav", {})
    if wd.get("enabled") and wd.get("url"):
        try:
            base_url = wd["url"].rstrip("/")
            remote_path = wd.get("remote_path", "").strip("/ ")
            target_url = f"{base_url}/{remote_path}/{filename}" if remote_path else f"{base_url}/{filename}"
            auth = (wd.get("username", ""), wd.get("password", "")) if wd.get("username") else None
            with open(filepath, "rb") as f:
                requests.put(target_url, data=f, auth=auth, timeout=60)
        except Exception as e:
            print(f"[CloudSync WebDAV Error] {e}")

    # 3. FTP
    ftp_cfg = cfg.get("ftp", {})
    if ftp_cfg.get("enabled") and ftp_cfg.get("host"):
        try:
            ftp = ftplib.FTP()
            ftp.connect(ftp_cfg["host"], int(ftp_cfg.get("port", 21)), timeout=30)
            ftp.login(ftp_cfg.get("username", "anonymous"), ftp_cfg.get("password", ""))
            remote_dir = ftp_cfg.get("remote_dir", "/").strip()
            if remote_dir and remote_dir != "/":
                try:
                    ftp.cwd(remote_dir)
                except Exception:
                    pass
            with open(filepath, "rb") as f:
                ftp.storbinary(f"STOR {filename}", f)
            ftp.quit()
        except Exception as e:
            print(f"[CloudSync FTP Error] {e}")

    # 4. Telegram Bot (Admin Only)
    tg = cfg.get("telegram", {})
    if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
        try:
            token = tg["bot_token"]
            chat_id = tg["chat_id"]
            if os.path.getsize(filepath) <= 50 * 1024 * 1024:
                with open(filepath, "rb") as f:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendDocument",
                        data={"chat_id": chat_id, "caption": f"🎬 {filename}"},
                        files={"document": (filename, f)},
                        timeout=120,
                    )
        except Exception as e:
            print(f"[CloudSync Telegram Error] {e}")


def get_project_memory_bytes() -> int:
    # 1. Try cgroups v2 (standard inside modern Docker)
    if os.path.exists("/sys/fs/cgroup/memory.current"):
        try:
            with open("/sys/fs/cgroup/memory.current", "r") as f:
                val = int(f.read().strip())
                if val > 0:
                    return val
        except Exception:
            pass
    # 2. Try cgroups v1
    for p in ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory.usage_in_bytes"):
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    val = int(f.read().strip())
                    if val > 0:
                        return val
            except Exception:
                pass
    # 3. Fallback to /proc/self/status VmRSS
    if os.path.exists("/proc/self/status"):
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        return int(parts[1]) * 1024
        except Exception:
            pass
    return 0


def get_ram_status():
    try:
        total = 0
        free = 0
        used = 0
        percent = 0
        if os.path.exists("/proc/meminfo"):
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        meminfo[key] = int(val) * 1024
            total = meminfo.get("MemTotal", 0)
            free = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            used = total - free
            percent = round((used / total) * 100, 1) if total > 0 else 0

        project_bytes = get_project_memory_bytes()
        project_percent = round((project_bytes / total) * 100, 2) if total > 0 else 0

        return {
            # VPS System RAM
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "total_formatted": format_bytes(total),
            "used_formatted": format_bytes(used),
            "free_formatted": format_bytes(free),
            "percent_used": percent,

            # Project / Container RAM
            "project_bytes": project_bytes,
            "project_formatted": format_bytes(project_bytes),
            "project_percent_used": project_percent,
        }
    except Exception:
        pass
    return {
        "total_bytes": 0, "used_bytes": 0, "free_bytes": 0,
        "total_formatted": "N/A", "used_formatted": "N/A", "free_formatted": "N/A",
        "percent_used": 0,
        "project_bytes": 0, "project_formatted": "N/A", "project_percent_used": 0,
    }





def format_bytes(bytes_val: int) -> str:
    if bytes_val is None:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"


def get_disk_status():
    try:
        total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
        percent = round((used / total) * 100, 1) if total > 0 else 0
        return {
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "total_formatted": format_bytes(total),
            "used_formatted": format_bytes(used),
            "free_formatted": format_bytes(free),
            "percent_used": percent,
            "is_emergency": (percent >= DISK_EMERGENCY_THRESHOLD_PERCENT) or (free < (DISK_EMERGENCY_MIN_FREE_GB * (1024**3))),
        }
    except Exception as e:
        return {
            "total_bytes": 0, "used_bytes": 0, "free_bytes": 0,
            "total_formatted": "N/A", "used_formatted": "N/A", "free_formatted": "N/A",
            "percent_used": 0, "is_emergency": False, "error": str(e),
        }


def purge_downloads(force_all=False):
    cleaned_count = 0
    reclaimed_bytes = 0
    with JOBS_LOCK:
        active_ids = {
            jid for jid, j in JOBS.items()
            if j.get("status") in ("queued", "downloading", "processing")
        }
        stale_ids = [
            jid for jid, j in JOBS.items()
            if force_all or j.get("status") in ("finished", "error")
        ]

    for jid in stale_ids:
        with JOBS_LOCK:
            job = JOBS.pop(jid, None)
        if job and job.get("filepath") and os.path.exists(job["filepath"]):
            try:
                size = os.path.getsize(job["filepath"])
                os.remove(job["filepath"])
                reclaimed_bytes += size
                cleaned_count += 1
            except OSError:
                pass

    if os.path.exists(DOWNLOAD_DIR):
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry == ".gitkeep":
                continue
            entry_path = os.path.join(DOWNLOAD_DIR, entry)
            job_id_guess = entry.split("_", 1)[0].replace(".zip", "")
            if job_id_guess in active_ids and not force_all:
                continue
            try:
                if os.path.isdir(entry_path):
                    for root, _, files in os.walk(entry_path):
                        for f in files:
                            reclaimed_bytes += os.path.getsize(os.path.join(root, f))
                    shutil.rmtree(entry_path, ignore_errors=True)
                    cleaned_count += 1
                else:
                    size = os.path.getsize(entry_path)
                    os.remove(entry_path)
                    reclaimed_bytes += size
                    cleaned_count += 1
            except OSError:
                pass

    return {
        "cleaned_count": cleaned_count,
        "reclaimed_bytes": reclaimed_bytes,
        "reclaimed_formatted": format_bytes(reclaimed_bytes),
    }


def cleanup_loop():
    while True:
        time.sleep(max(CLEANUP_CHECK_INTERVAL_MINUTES, 1) * 60)
        try:
            # 1. Emergency disk auto-purge
            disk_info = get_disk_status()
            if disk_info.get("is_emergency"):
                purge_downloads(force_all=False)

            # 2. Regular TTL cleanup
            if CLEANUP_AFTER_HOURS > 0:
                cutoff = time.time() - (CLEANUP_AFTER_HOURS * 3600)
                with JOBS_LOCK:
                    active_ids = {
                        jid for jid, j in JOBS.items()
                        if j.get("status") in ("queued", "downloading", "processing")
                    }
                    stale_ids = [
                        jid for jid, j in JOBS.items()
                        if j.get("status") in ("finished", "error")
                        and j.get("finished_at", 0) < cutoff
                    ]

                for jid in stale_ids:
                    with JOBS_LOCK:
                        job = JOBS.pop(jid, None)
                    if job and job.get("filepath") and os.path.exists(job["filepath"]):
                        try:
                            os.remove(job["filepath"])
                        except OSError:
                            pass

                for entry in os.listdir(DOWNLOAD_DIR):
                    if entry == ".gitkeep":
                        continue
                    entry_path = os.path.join(DOWNLOAD_DIR, entry)
                    job_id_guess = entry.split("_", 1)[0].replace(".zip", "")
                    if job_id_guess in active_ids:
                        continue
                    try:
                        mtime = os.path.getmtime(entry_path)
                    except OSError:
                        continue
                    if mtime < cutoff:
                        if os.path.isdir(entry_path):
                            shutil.rmtree(entry_path, ignore_errors=True)
                        else:
                            os.remove(entry_path)
        except Exception:
            pass


threading.Thread(target=cleanup_loop, daemon=True).start()



def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name.strip()[:150] or "video"


def format_for_quality(quality: str) -> str:
    mapping = {
        "best": "bv*+ba/b",
        "2160p": "bv*[height<=2160]+ba/b[height<=2160]/bv*+ba/b",
        "1440p": "bv*[height<=1440]+ba/b[height<=1440]/bv*+ba/b",
        "1080p": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
        "720p": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
        "480p": "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b",
    }
    if quality in mapping:
        return mapping[quality]
    if quality.startswith("audio"):
        return "ba/b"
    return mapping["best"]


AUDIO_BITRATES = {"audio_128": "128", "audio_192": "192", "audio_256": "256", "audio_320": "320"}


def is_audio_quality(quality: str) -> bool:
    return quality.startswith("audio")


def parse_time_to_seconds(value):
    if value is None or value == "":
        return None
    value = str(value).strip()
    parts = value.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"Formato de tiempo inválido: '{value}' (usá HH:MM:SS, MM:SS o segundos)")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


@app.after_request
def add_noindex_header(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
    return response


@app.route("/robots.txt")
def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


def is_permanent_error(err_str: str) -> bool:
    err_lower = str(err_str).lower()
    return any(p in err_lower for p in [
        "playlist does not exist",
        "video is unavailable",
        "this video is private",
        "private video",
        "drm protection",
        "copyright",
        "account has been terminated",
        "confirm your age",
        "sign in if you've been granted access",
    ])


def extract_with_fallback(url, ydl_opts_base, download):
    """Prueba combinaciones de clientes en orden:
    1) default (cadena inteligente de yt-dlp con Deno para JS challenges y bgutil para PO Token)
    2) web_embedded, tv_downgraded, mweb
    3) tv
    4) web
    """
    candidates = [
        ["default"],
        ["web_embedded", "tv_downgraded", "mweb"],
        ["tv"],
        ["web"],
    ] if download else [
        ["default"],
        ["web_embedded", "tv_downgraded", "mweb"],
    ]

    last_exc = None
    for clients in candidates:
        opts = dict(ydl_opts_base)
        opts["extractor_args"] = player_client_opts(clients, for_download=download)["extractor_args"]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)

        except yt_dlp.utils.DownloadError as e:
            last_exc = e
            if is_permanent_error(str(e)):
                break
            continue
    raise last_exc



def normalize_url(url: str) -> str:

    url = url.strip()
    # Normalize YouTube Shorts to standard watch URL for maximum compatibility
    shorts_match = re.match(r"^https?://(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]+)", url)
    if shorts_match:
        video_id = shorts_match.group(1)
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "deezer.com" in url_lower or "deezer.page.link" in url_lower:
        return "Deezer"
    if "spotify.com" in url_lower:
        return "Spotify"
    if "youtube.com/shorts" in url_lower:
        return "YouTube Shorts"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    if "instagram.com" in url_lower:
        return "Instagram"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "Facebook"
    if "twitch.tv" in url_lower:
        return "Twitch"
    if "kick.com" in url_lower:
        return "Kick"
    if "tiktok.com" in url_lower:
        return "TikTok"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "Twitter / X"
    return "Web"


def get_deezer_info(url: str):
    try:
        track_m = re.search(r"deezer\.com/(?:[a-zA-Z-]+/)?track/(\d+)", url)
        if track_m:
            track_id = track_m.group(1)
            r = requests.get(f"https://api.deezer.com/track/{track_id}", timeout=10)
            data = r.json()
            if "error" not in data:
                artist = data.get("artist", {}).get("name", "Artista")
                title = data.get("title", "Canción")
                album = data.get("album", {}).get("title", "")
                cover = data.get("album", {}).get("cover_xl") or data.get("album", {}).get("cover_big")
                return {
                    "type": "video",
                    "platform": "Deezer",
                    "title": f"{artist} - {title}",
                    "artist": artist,
                    "track_title": title,
                    "album": album,
                    "duration": data.get("duration"),
                    "thumbnail": cover,
                    "url": url,
                }

        album_m = re.search(r"deezer\.com/(?:[a-zA-Z-]+/)?album/(\d+)", url)
        if album_m:
            album_id = album_m.group(1)
            r = requests.get(f"https://api.deezer.com/album/{album_id}", timeout=10)
            data = r.json()
            if "error" not in data:
                tracks = data.get("tracks", {}).get("data", [])
                artist = data.get("artist", {}).get("name", "Artista")
                title = data.get("title", "Álbum")
                cover = data.get("cover_xl") or data.get("cover_big")
                items = [
                    {
                        "index": i + 1,
                        "id": str(t.get("id")),
                        "title": f"{t.get('artist', {}).get('name', artist)} - {t.get('title', '')}",
                        "url": t.get("link") or f"https://www.deezer.com/track/{t.get('id')}",
                        "duration": t.get("duration"),
                        "duration_formatted": f"{int(t.get('duration', 0))//60}:{int(t.get('duration', 0))%60:02d}" if t.get("duration") else None,
                        "thumbnail": cover,
                    }
                    for i, t in enumerate(tracks[:300])
                ]
                return {
                    "type": "playlist",
                    "platform": "Deezer",
                    "title": f"{artist} - {title}",
                    "count": len(tracks),
                    "thumbnail": cover,
                    "entries": tracks,
                    "items": items,
                    "url": url,
                }

        playlist_m = re.search(r"deezer\.com/(?:[a-zA-Z-]+/)?playlist/(\d+)", url)
        if playlist_m:
            pl_id = playlist_m.group(1)
            r = requests.get(f"https://api.deezer.com/playlist/{pl_id}", timeout=10)
            data = r.json()
            if "error" not in data:
                tracks = data.get("tracks", {}).get("data", [])
                cover = data.get("picture_xl") or data.get("picture_big")
                items = [
                    {
                        "index": i + 1,
                        "id": str(t.get("id")),
                        "title": f"{t.get('artist', {}).get('name', 'Artista')} - {t.get('title', '')}",
                        "url": t.get("link") or f"https://www.deezer.com/track/{t.get('id')}",
                        "duration": t.get("duration"),
                        "duration_formatted": f"{int(t.get('duration', 0))//60}:{int(t.get('duration', 0))%60:02d}" if t.get("duration") else None,
                        "thumbnail": (t.get("album", {}).get("cover_medium") or cover),
                    }
                    for i, t in enumerate(tracks[:300])
                ]
                return {
                    "type": "playlist",
                    "platform": "Deezer",
                    "title": f"Playlist: {data.get('title', 'Deezer')}",
                    "count": len(tracks),
                    "thumbnail": cover,
                    "entries": tracks,
                    "items": items,
                    "url": url,
                }
    except Exception:
        pass
    return None


def get_spotify_info(url: str):
    try:
        track_m = re.search(r"open\.spotify\.com/(?:[a-zA-Z-]+/)?track/([a-zA-Z0-9]+)", url)
        if track_m:
            r = requests.get(f"https://open.spotify.com/oembed?url={url}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                raw_title = data.get("title", "Spotify Track")
                parts = raw_title.split(" by ", 1)
                if len(parts) == 2:
                    track_title, artist = parts[0], parts[1]
                else:
                    track_title, artist = raw_title, "Artista"
                return {
                    "type": "video",
                    "platform": "Spotify",
                    "title": f"{artist} - {track_title}",
                    "artist": artist,
                    "track_title": track_title,
                    "album": "Spotify",
                    "thumbnail": data.get("thumbnail_url"),
                    "url": url,
                }
    except Exception:
        pass
    return None


def run_download_music(job_id: str, url: str, quality: str, deezer_arl: str = "", music_meta: dict = None, owner: str = "admin", user_cloud_sync: dict = None, folder_name: str = None, group_id: str = None):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)

    os.makedirs(job_dir, exist_ok=True)

    try:
        platform = detect_platform(url)
        meta = music_meta or {}
        if not meta:
            if platform == "Deezer":
                meta = get_deezer_info(url) or {}
            elif platform == "Spotify":
                meta = get_spotify_info(url) or {}

        title = meta.get("track_title") or meta.get("title") or "Canción"
        artist = meta.get("artist") or "Artista"
        album = meta.get("album") or "Música"
        cover_url = meta.get("thumbnail")
        display_name = f"{artist} - {title}"

        raw_audio_tmpl = os.path.join(job_dir, "raw_audio.%(ext)s")
        cover_file = os.path.join(job_dir, "cover.jpg")
        final_filename = safe_filename(display_name) + ".mp3"
        final_path = os.path.join(DOWNLOAD_DIR, f"{job_id}_{final_filename}")

        downloaded_direct = False

        # Attempt direct Deezer download if ARL is provided
        if platform == "Deezer" and deezer_arl:
            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "downloading",
                    "current_title": f"Descargando de Deezer Hi-Fi ({display_name})...",
                    "file_percent": 10,
                })
            try:
                ydl_opts = {
                    "format": "best",
                    "outtmpl": raw_audio_tmpl,
                    "quiet": True,
                    "http_headers": {"Cookie": f"arl={deezer_arl}"},
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)
                downloaded_direct = True
            except Exception as e:
                with JOBS_LOCK:
                    JOBS[job_id].update({
                        "current_title": f"ARL inválido o expirado. Descargando sin ARL ({display_name})...",
                    })

        if not downloaded_direct:
            search_query = f"ytsearch1:{artist} - {title} audio"
            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "downloading",
                    "current_title": f"Buscando audio de alta calidad para '{display_name}'...",
                    "file_percent": 20,
                })
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": raw_audio_tmpl,
                "quiet": True,
                **cookies_opts(),
            }
            extract_with_fallback(search_query, ydl_opts, download=True)

        found_files = [f for f in os.listdir(job_dir) if f.startswith("raw_audio.")]
        if not found_files:
            raise RuntimeError("No se pudo descargar el stream de audio")
        actual_audio = os.path.join(job_dir, found_files[0])

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "processing",
                "current_title": "Incrustando carátula y metadatos ID3...",
            })

        # Download Cover
        has_cover = False
        if cover_url:
            try:
                cr = requests.get(cover_url, timeout=10)
                if cr.status_code == 200:
                    with open(cover_file, "wb") as cf:
                        cf.write(cr.content)
                    has_cover = True
            except Exception:
                pass

        # Target bitrate
        bitrate_map = {"audio_128": "128k", "audio_192": "192k", "audio_256": "256k", "audio_320": "320k"}
        br = bitrate_map.get(quality, "320k")

        ffmpeg_cmd = ["ffmpeg", "-y", "-i", actual_audio]
        if has_cover:
            ffmpeg_cmd.extend([
                "-i", cover_file,
                "-map", "0:a", "-map", "1:v",
                "-c:v", "mjpeg",
                "-metadata:s:v", 'title="Album cover"',
                "-metadata:s:v", 'comment="Cover (front)"'
            ])
        else:
            ffmpeg_cmd.extend(["-map", "0:a"])

        ffmpeg_cmd.extend([
            "-c:a", "libmp3lame", "-b:a", br, "-id3v2_version", "3",
            "-metadata", f"title={title}",
            "-metadata", f"artist={artist}",
            "-metadata", f"album={album}",
            final_path,
        ])

        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {proc.stderr[:200]}")

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "finished",
                "percent": 100,
                "file_percent": 100,
                "filepath": final_path,
                "filename": final_filename,
                "finished_at": time.time(),
                "speed": None,
                "owner": owner,
            })
            job_snap = dict(JOBS[job_id])

        if os.path.exists(final_path):
            record_download_meta(job_id, final_filename, owner, os.path.getsize(final_path), folder_name=folder_name, group_id=group_id)
        threading.Thread(target=sync_to_cloud, args=(final_path, final_filename, job_snap, user_cloud_sync), daemon=True).start()
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "error",
                "error": str(e),
                "finished_at": time.time(),
            })
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)



@app.route("/")
def index():
    cfg = load_config()
    user = getattr(request, "current_user", {}) or {}
    is_admin = (user.get("role") == "admin")
    return render_template(
        "index.html",
        version=APP_VERSION,
        config=cfg,
        is_admin=is_admin,
        username=user.get("username", "admin"),
    )


@app.route("/manifest.json")
def manifest():
    return send_file(os.path.join(app.root_path, "static", "manifest.json"), mimetype="application/manifest+json")


@app.route("/sw.js")
def service_worker():
    return send_file(os.path.join(app.root_path, "static", "sw.js"), mimetype="application/javascript")


@app.route("/api/version")
def api_version():
    return jsonify({
        "app_version": APP_VERSION,
        "ytdlp_version": get_ytdlp_version(),
    })


@app.route("/api/disk-status")
def api_disk_status():
    return jsonify(get_disk_status())


@app.route("/api/cleanup", methods=["POST"])
@require_admin
def api_cleanup():
    res = purge_downloads(force_all=False)
    disk = get_disk_status()
    return jsonify({
        "success": True,
        "cleaned_count": res["cleaned_count"],
        "reclaimed_formatted": res["reclaimed_formatted"],
        "disk": disk,
    })


@app.route("/api/recent-downloads")
def recent_downloads():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")
    show_all = is_admin and (request.args.get("all") == "1")

    meta = load_downloads_meta()
    standalone_items = []
    folders = {}

    if os.path.exists(DOWNLOAD_DIR):
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry == ".gitkeep":
                continue
            entry_path = os.path.join(DOWNLOAD_DIR, entry)
            if os.path.isfile(entry_path):
                try:
                    stat = os.stat(entry_path)
                    parts = entry.split("_", 1)
                    job_id = parts[0].replace(".zip", "")
                    clean_name = parts[1] if len(parts) > 1 else entry

                    item_meta = meta.get(job_id, {})
                    item_owner = item_meta.get("username")
                    if not item_owner:
                        with JOBS_LOCK:
                            job = JOBS.get(job_id)
                            if job:
                                item_owner = job.get("owner")
                    if not item_owner:
                        item_owner = "admin"

                    if not show_all and item_owner != username and not (is_admin and item_owner in ("admin", username)):
                        continue

                    folder_name = item_meta.get("folder_name")
                    group_id = item_meta.get("group_id")

                    item_obj = {
                        "job_id": job_id,
                        "filename": clean_name,
                        "size_bytes": stat.st_size,
                        "size_formatted": format_bytes(stat.st_size),
                        "mtime": stat.st_mtime,
                        "owner": item_owner,
                        "download_url": f"/api/files/{job_id}",
                    }

                    if folder_name and group_id:
                        if group_id not in folders:
                            folders[group_id] = {
                                "group_id": group_id,
                                "folder_name": folder_name,
                                "owner": item_owner,
                                "items": [],
                                "total_bytes": 0,
                                "mtime": stat.st_mtime,
                            }
                        folders[group_id]["items"].append(item_obj)
                        folders[group_id]["total_bytes"] += stat.st_size
                        if stat.st_mtime > folders[group_id]["mtime"]:
                            folders[group_id]["mtime"] = stat.st_mtime
                    else:
                        standalone_items.append(item_obj)
                except OSError:
                    continue

    standalone_items.sort(key=lambda x: x["mtime"], reverse=True)
    folder_list = list(folders.values())
    for f in folder_list:
        f["total_formatted"] = format_bytes(f["total_bytes"])
        f["count"] = len(f["items"])
        f["items"].sort(key=lambda x: x["mtime"], reverse=False)
    folder_list.sort(key=lambda x: x["mtime"], reverse=True)

    return jsonify({
        "items": standalone_items[:40],
        "folders": folder_list[:30],
        "downloads": standalone_items[:40],
        "is_admin": is_admin,
        "user": username,
    })


@app.route("/api/my-downloads/folder/<group_id>", methods=["DELETE"])
def delete_folder_downloads(group_id):
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    meta = load_downloads_meta()
    matching_jids = [
        jid for jid, info in meta.items()
        if info.get("group_id") == group_id and (is_admin or info.get("username") == username)
    ]

    deleted_count = 0
    if os.path.exists(DOWNLOAD_DIR):
        for jid in matching_jids:
            for entry in os.listdir(DOWNLOAD_DIR):
                if entry.startswith(jid):
                    try:
                        os.remove(os.path.join(DOWNLOAD_DIR, entry))
                        deleted_count += 1
                    except Exception:
                        pass
            delete_download_meta(jid)

    return jsonify({"success": True, "deleted_count": deleted_count})


@app.route("/api/my-downloads/folder-zip/<group_id>")
def folder_download_zip(group_id):
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    meta = load_downloads_meta()
    matching_jids = {
        jid: info for jid, info in meta.items()
        if info.get("group_id") == group_id and (is_admin or info.get("username") == username)
    }

    if not matching_jids:
        abort(404)

    folder_name = next(iter(matching_jids.values())).get("folder_name", f"folder_{group_id[:8]}")
    safe_f_name = safe_filename(folder_name)
    zip_path = os.path.join(DOWNLOAD_DIR, f"folder_{group_id}.zip")

    files_added = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for jid in matching_jids:
            for entry in os.listdir(DOWNLOAD_DIR):
                if entry.startswith(jid) and entry != f"folder_{group_id}.zip":
                    fpath = os.path.join(DOWNLOAD_DIR, entry)
                    disp_name = entry[len(jid):].lstrip("_-") or entry
                    if os.path.isfile(fpath):
                        zf.write(fpath, arcname=disp_name)
                        files_added += 1

    if files_added == 0:
        abort(404)

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"{safe_f_name}.zip",
        mimetype="application/zip",
    )


@app.route("/api/my-downloads/<job_id>", methods=["DELETE"])
def delete_single_my_download(job_id):
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    meta = load_downloads_meta()
    item_owner = meta.get(job_id, {}).get("username")
    with JOBS_LOCK:
        job = JOBS.pop(job_id, None)
        if job and not item_owner:
            item_owner = job.get("owner")
    if not item_owner:
        item_owner = "admin"

    if not is_admin and item_owner != username:
        return jsonify({"error": "No tenés permiso para eliminar este archivo"}), 403

    deleted = False
    if os.path.exists(DOWNLOAD_DIR):
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry.startswith(job_id):
                fpath = os.path.join(DOWNLOAD_DIR, entry)
                try:
                    os.remove(fpath)
                    deleted = True
                except Exception:
                    pass
    delete_download_meta(job_id)
    return jsonify({"success": True, "deleted": deleted})


@app.route("/api/my-downloads/cleanup", methods=["POST"])
def cleanup_my_downloads():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")

    meta = load_downloads_meta()
    user_job_ids = [jid for jid, info in meta.items() if info.get("username") == username]

    cleaned_count = 0
    reclaimed_bytes = 0
    if os.path.exists(DOWNLOAD_DIR):
        for jid in user_job_ids:
            for entry in os.listdir(DOWNLOAD_DIR):
                if entry.startswith(jid):
                    fpath = os.path.join(DOWNLOAD_DIR, entry)
                    try:
                        size = os.path.getsize(fpath)
                        os.remove(fpath)
                        cleaned_count += 1
                        reclaimed_bytes += size
                    except Exception:
                        pass
            delete_download_meta(jid)
            with JOBS_LOCK:
                JOBS.pop(jid, None)

    return jsonify({
        "success": True,
        "cleaned_count": cleaned_count,
        "reclaimed_formatted": format_bytes(reclaimed_bytes),
    })



@app.route("/wiki")
def wiki_page():
    cfg = load_config()
    return render_template("wiki.html", version=APP_VERSION, config=cfg)


# ==================== ADMIN PANEL & API ====================

@app.route("/admin")
@require_admin
def admin_panel():
    cfg = load_config()
    return render_template("admin.html", version=APP_VERSION, config=cfg)


@app.route("/api/admin/services-status")
@require_admin
def admin_services_status():
    pot_ok = False
    pot_lat = 0
    try:
        t0 = time.time()
        requests.get(POT_PROVIDER_URL, timeout=3)
        pot_lat = round((time.time() - t0) * 1000)
        pot_ok = True
    except Exception:
        pass

    cobalt_ok = False
    cobalt_lat = 0
    try:
        t0 = time.time()
        requests.get(COBALT_URL, timeout=3)
        cobalt_lat = round((time.time() - t0) * 1000)
        cobalt_ok = True
    except Exception:
        pass

    deno_path = shutil.which("deno") or "/usr/local/bin/deno"
    deno_installed = False
    deno_ver = ""
    try:
        dr = subprocess.run([deno_path, "--version"], capture_output=True, text=True, timeout=3)
        if dr.returncode == 0:
            deno_installed = True
            deno_ver = dr.stdout.splitlines()[0]
    except Exception:
        pass

    uptime_s = round(time.time() - START_TIME)
    return jsonify({
        "app": {"version": APP_VERSION, "uptime_seconds": uptime_s},
        "potprovider": {"online": pot_ok, "latency_ms": pot_lat},
        "cobalt": {"online": cobalt_ok, "latency_ms": cobalt_lat},
        "deno": {"installed": deno_installed, "available": deno_installed, "version": deno_ver},
        "disk": get_disk_status(),
        "ram": get_ram_status(),
    })


@app.route("/api/admin/test-deno", methods=["POST"])
@require_admin
def admin_test_deno():
    deno_path = shutil.which("deno") or "/usr/local/bin/deno"
    try:
        t0 = time.time()
        js_test_code = "const payload = { engine: 'Deno JS Runtime', status: 'OK', calc: (1337 * 7), timestamp: Date.now() }; console.log(JSON.stringify(payload));"
        res = subprocess.run(
            [deno_path, "eval", js_test_code],
            capture_output=True, text=True, timeout=5
        )
        ver_res = subprocess.run([deno_path, "--version"], capture_output=True, text=True, timeout=3)
        elapsed_ms = round((time.time() - t0) * 1000)

        if res.returncode == 0:
            return jsonify({
                "success": True,
                "version": ver_res.stdout.strip(),
                "output": res.stdout.strip(),
                "elapsed_ms": elapsed_ms,
                "message": f"Motor Deno JS probado con éxito ({elapsed_ms}ms)."
            })
        else:
            return jsonify({
                "success": False,
                "error": res.stderr.strip() or "Error al ejecutar Deno",
                "message": f"Deno retornó código de error {res.returncode}."
            }), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/check-updates")
@require_admin
def admin_check_updates():

    curr = get_ytdlp_version()
    latest = curr
    has_update = False
    try:
        r = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=4)
        if r.status_code == 200:
            latest = r.json().get("info", {}).get("version", curr)
            if latest and latest != curr:
                has_update = True
    except Exception:
        pass
    return jsonify({
        "current_version": curr,
        "latest_version": latest,
        "update_available": has_update,
    })



@app.route("/api/admin/config", methods=["GET", "POST"])
@require_admin
def admin_config():
    global CLEANUP_AFTER_HOURS, DISK_EMERGENCY_THRESHOLD_PERCENT
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        cfg = load_config()
        if "site_title" in data:
            cfg["site_title"] = str(data["site_title"]).strip() or "🎬 Descargador Multimedia"
        if "site_subtitle" in data:
            cfg["site_subtitle"] = str(data["site_subtitle"]).strip()
        if "default_theme" in data:
            cfg["default_theme"] = str(data["default_theme"]).strip()
        if "cleanup_after_hours" in data:
            cfg["cleanup_after_hours"] = float(data["cleanup_after_hours"])
            CLEANUP_AFTER_HOURS = cfg["cleanup_after_hours"]
        if "disk_emergency_threshold" in data:
            cfg["disk_emergency_threshold"] = float(data["disk_emergency_threshold"])
            DISK_EMERGENCY_THRESHOLD_PERCENT = cfg["disk_emergency_threshold"]
        if "default_engine" in data:
            cfg["default_engine"] = str(data["default_engine"])
        save_config(cfg)
        return jsonify({"message": "Configuración guardada exitosamente", "config": cfg})
    return jsonify({"config": load_config()})



@app.route("/api/admin/cookies", methods=["GET", "POST"])
@require_admin
def admin_cookies():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        content = data.get("content", "")
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"message": "Archivo cookies.txt guardado exitosamente"})

    has_cookies = os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0
    content = ""
    lines = 0
    size_formatted = "0 B"
    if has_cookies:
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            lines = len(content.splitlines())
            size_formatted = format_bytes(os.path.getsize(COOKIES_FILE))
        except Exception:
            pass
    return jsonify({
        "has_cookies": has_cookies,
        "content": content,
        "lines": lines,
        "size_formatted": size_formatted,
    })


@app.route("/api/admin/users", methods=["GET", "POST"])
@require_admin
def admin_users():
    users = load_users()
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")
        role = data.get("role", "downloader")
        status = data.get("status", "active")
        if not username or not password:
            return jsonify({"error": "Falta usuario o contraseña"}), 400
        if username in users:
            return jsonify({"error": f"El usuario '{username}' ya existe"}), 400
        users[username] = {
            "password_hash": hash_password(password),
            "role": role,
            "status": status,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_users(users)
        return jsonify({"message": f"Usuario '{username}' creado exitosamente"})

    meta = load_downloads_meta()
    user_stats = {}
    for job_id, item in meta.items():
        u = item.get("username", "admin")
        if u not in user_stats:
            user_stats[u] = {"count": 0, "bytes": 0}
        user_stats[u]["count"] += 1
        user_stats[u]["bytes"] += item.get("size_bytes", 0)

    user_list = [
        {
            "username": u,
            "role": d.get("role", "downloader"),
            "status": d.get("status", "active"),
            "created_at": d.get("created_at", "Inicial"),
            "downloads_count": user_stats.get(u, {}).get("count", 0),
            "downloads_bytes": user_stats.get(u, {}).get("bytes", 0),
            "downloads_formatted": format_bytes(user_stats.get(u, {}).get("bytes", 0)),
        }
        for u, d in users.items()
    ]
    return jsonify({"users": user_list})


@app.route("/api/admin/users/<username>", methods=["PUT", "DELETE"])
@require_admin
def admin_user_detail(username):
    users = load_users()
    if username not in users:
        return jsonify({"error": "Usuario no encontrado"}), 404
    if request.method == "DELETE":
        if username == APP_USERNAME or username == getattr(request, "current_username", "") or (len([u for u, d in users.items() if d.get("role") == "admin"]) <= 1 and users[username].get("role") == "admin"):
            return jsonify({"error": "No se puede eliminar el administrador principal"}), 400
        del users[username]
        save_users(users)
        # Purge user downloads
        meta = load_downloads_meta()
        user_jobs = [jid for jid, item in meta.items() if item.get("username") == username]
        if os.path.exists(DOWNLOAD_DIR):
            for jid in user_jobs:
                for entry in os.listdir(DOWNLOAD_DIR):
                    if entry.startswith(jid):
                        try:
                            os.remove(os.path.join(DOWNLOAD_DIR, entry))
                        except Exception:
                            pass
                delete_download_meta(jid)
        return jsonify({"message": f"Usuario '{username}' y sus descargas eliminados exitosamente"})
    if request.method == "PUT":
        data = request.get_json(force=True) or {}
        if "password" in data and data["password"]:
            users[username]["password_hash"] = hash_password(data["password"])
        if "role" in data and data["role"]:
            users[username]["role"] = data["role"]
        if "status" in data and data["status"]:
            users[username]["status"] = data["status"]
        save_users(users)
        return jsonify({"message": f"Usuario '{username}' actualizado exitosamente"})


@app.route("/api/admin/users/<username>/toggle-status", methods=["POST"])
@require_admin
def admin_user_toggle_status(username):
    users = load_users()
    if username not in users:
        return jsonify({"error": "Usuario no encontrado"}), 404
    if username == APP_USERNAME or username == getattr(request, "current_username", ""):
        return jsonify({"error": "No podés suspender tu propia cuenta de administrador"}), 400
    current = users[username].get("status", "active")
    new_status = "suspended" if current == "active" else "active"
    users[username]["status"] = new_status
    save_users(users)
    return jsonify({
        "success": True,
        "message": f"Usuario '{username}' ahora está {new_status}",
        "status": new_status,
    })


@app.route("/api/admin/users/<username>/clean-downloads", methods=["POST"])
@require_admin
def admin_user_clean_downloads(username):
    meta = load_downloads_meta()
    user_jobs = [jid for jid, item in meta.items() if item.get("username") == username]
    cleaned_count = 0
    reclaimed_bytes = 0
    if os.path.exists(DOWNLOAD_DIR):
        for jid in user_jobs:
            for entry in os.listdir(DOWNLOAD_DIR):
                if entry.startswith(jid):
                    fpath = os.path.join(DOWNLOAD_DIR, entry)
                    try:
                        size = os.path.getsize(fpath)
                        os.remove(fpath)
                        cleaned_count += 1
                        reclaimed_bytes += size
                    except Exception:
                        pass
            delete_download_meta(jid)
            with JOBS_LOCK:
                JOBS.pop(jid, None)
    return jsonify({
        "success": True,
        "cleaned_count": cleaned_count,
        "reclaimed_formatted": format_bytes(reclaimed_bytes),
    })


# ==================== COBALT MAINTENANCE & UPDATES ====================

@app.route("/api/admin/cobalt-status")
@require_admin
def admin_cobalt_status():
    curr_ver = "Desconocida"
    online = False
    services = []
    try:
        r = requests.get(COBALT_URL, timeout=4)
        if r.status_code == 200:
            data = r.json()
            cobalt_info = data.get("cobalt", {})
            curr_ver = cobalt_info.get("version", "v11.x")
            services = cobalt_info.get("services", [])
            online = True
    except Exception:
        pass

    latest_ver = curr_ver
    update_available = False
    try:
        gh_r = requests.get(
            "https://api.github.com/repos/imputnet/cobalt/releases/latest",
            headers={"User-Agent": "ytsite"},
            timeout=4,
        )
        if gh_r.status_code == 200:
            latest_ver = gh_r.json().get("tag_name", "").lstrip("v")
            if latest_ver and latest_ver != curr_ver.lstrip("v"):
                update_available = True
    except Exception:
        pass

    return jsonify({
        "online": online,
        "current_version": curr_ver,
        "latest_version": latest_ver,
        "update_available": update_available,
        "services": services,
    })


@app.route("/api/admin/update-cobalt", methods=["POST"])
@require_admin
def admin_update_cobalt():
    try:
        r = requests.get(COBALT_URL, timeout=4)
        if r.status_code == 200:
            ver = r.json().get("cobalt", {}).get("version", "11")
            return jsonify({
                "success": True,
                "message": f"Contenedor Cobalt v{ver} verificado y en funcionamiento óptimo.",
            })
    except Exception as e:
        return jsonify({"error": f"Error al verificar Cobalt: {e}"}), 500
    return jsonify({"message": "Estado de Cobalt verificado."})



# ==================== MEDIA INFO & DOWNLOADS ====================

@app.route("/api/info", methods=["POST"])

def info():
    data = request.get_json(force=True)
    raw_url = (data or {}).get("url", "").strip()
    if not raw_url:
        return jsonify({"error": "Falta la URL"}), 400

    url = normalize_url(raw_url)
    platform = detect_platform(raw_url)

    if platform == "Deezer":
        d_info = get_deezer_info(raw_url)
        if d_info:
            return jsonify(d_info)
    elif platform == "Spotify":
        s_info = get_spotify_info(raw_url)
        if s_info:
            return jsonify(s_info)

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
        "ignore_no_formats_error": True,
        "socket_timeout": 10,
        "playlistend": 300,
        "ignoreerrors": True,
        **cookies_opts(),
    }
    try:
        result = extract_with_fallback(url, ydl_opts, download=False)
    except Exception as e:
        err_msg = str(e)
        if "playlist does not exist" in err_msg.lower():
            return jsonify({"error": "La playlist no existe o fue eliminada de YouTube."}), 400
        elif "private" in err_msg.lower():
            return jsonify({"error": "El video o la playlist es privada."}), 400
        return jsonify({"error": f"No se pudo inspeccionar el enlace: {err_msg}"}), 400

    if not result or not isinstance(result, dict):
        return jsonify({"error": "No se pudo obtener información del enlace (la playlist o video no existe o es privado)."}), 400

    if "entries" in result:
        entries = [e for e in (result.get("entries") or []) if e]
        items = []
        for idx, e in enumerate(entries[:300]):
            vid_id = e.get("id") or ""
            vid_url = e.get("url") or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else "")
            thumbs = e.get("thumbnails") or []
            thumb = thumbs[-1]["url"] if thumbs else None
            dur = e.get("duration")
            items.append({
                "index": idx + 1,
                "id": vid_id,
                "title": e.get("title") or f"Elemento {idx + 1}",
                "url": vid_url,
                "duration": dur,
                "duration_formatted": f"{int(dur)//60}:{int(dur)%60:02d}" if dur else None,
                "thumbnail": thumb,
            })
        return jsonify({
            "type": "playlist",
            "title": result.get("title", "Playlist"),
            "count": len(entries),
            "platform": platform,
            "thumbnail": (entries[0].get("thumbnails", [{}])[-1].get("url")
                          if entries and entries[0].get("thumbnails") else (items[0].get("thumbnail") if items else None)),
            "items": items,
        })
    else:
        thumbs = result.get("thumbnails") or []
        return jsonify({
            "type": "video",
            "title": result.get("title", "Video"),
            "duration": result.get("duration"),
            "platform": platform,
            "thumbnail": thumbs[-1]["url"] if thumbs else result.get("thumbnail"),
        })





def is_audio_quality(quality: str) -> bool:
    if not quality:
        return False
    q = str(quality).lower()
    return q.startswith("audio_") or q in (
        "flac", "m4a", "opus", "wav", "mp3", "aac", "alac", "vorbis"
    )


QUALITY_FORMAT_MAP = {
    "best": "bestvideo+bestaudio/best",
    "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
    "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
}


COBALT_QUALITY_MAP = {
    "best": "max",
    "2160p": "2160",
    "1440p": "1440",
    "1080p": "1080",
    "720p": "720",
    "480p": "480",
}

CONTENT_TYPE_EXT = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
}
COBALT_AUDIO_BITRATES = {
    "audio_128": "128",
    "audio_192": "256",
    "audio_256": "256",
    "audio_320": "320",
}


def append_job_log(job_id: str, message: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            if "logs" not in job:
                job["logs"] = []
            job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": message})
            if len(job["logs"]) > 150:
                job["logs"] = job["logs"][-150:]


def run_download_cobalt(job_id: str, url: str, quality: str, video_title: str = "", owner: str = "admin", user_cloud_sync: dict = None, folder_name: str = None, group_id: str = None):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    append_job_log(job_id, f"[*] [Cobalt v11] Solicitando stream para: {url}")

    try:
        payload = {"url": url, "downloadMode": "auto"}
        if is_audio_quality(quality):
            payload["downloadMode"] = "audio"
            payload["audioFormat"] = "mp3"
            bitrate = COBALT_AUDIO_BITRATES.get(quality, "320")
            if bitrate:
                payload["audioBitrate"] = bitrate
        else:
            payload["videoQuality"] = COBALT_QUALITY_MAP.get(quality, "max")


        resp = requests.post(
            COBALT_URL, json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=60,
        )
        data = resp.json()
        status = data.get("status")

        if status == "error":
            msg = (data.get("error") or {}).get("code", "Error desconocido de Cobalt")
            raise RuntimeError(f"Cobalt: {msg}")
        if status == "picker":
            items = data.get("picker") or []
            if not items:
                raise RuntimeError("Cobalt devolvió varias opciones pero ninguna usable")
            stream_url = items[0].get("url")
        elif status in ("tunnel", "redirect"):
            stream_url = data.get("url")
        else:
            raise RuntimeError(f"Respuesta inesperada de Cobalt: {status}")

        if not stream_url:
            raise RuntimeError("Cobalt no devolvió un link de descarga")

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "downloading"

        append_job_log(job_id, "[*] [Cobalt v11] Descargando stream directo a disco...")
        with requests.get(stream_url, stream=True, timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            ext = CONTENT_TYPE_EXT.get((r.headers.get("Content-Type") or "").split(";")[0].strip(), ".mp4")
            base_name = safe_filename(video_title) or "descarga"
            out_path = os.path.join(job_dir, base_name + ext)

            downloaded = 0
            last_update = time.time()
            last_downloaded = 0
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_update >= 0.5:
                        speed = (downloaded - last_downloaded) / (now - last_update)
                        with JOBS_LOCK:
                            job = JOBS.get(job_id)
                            if job:
                                job["file_percent"] = int(downloaded * 100 / total) if total else 0
                                job["percent"] = job["file_percent"]
                                job["speed"] = format_speed(speed)
                                job["completed_count"] = 0
                        last_update = now
                        last_downloaded = downloaded

        final_name = base_name + ext
        final_path = os.path.join(DOWNLOAD_DIR, f"{job_id}_{final_name}")
        shutil.move(out_path, final_path)

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "finished",
                "percent": 100,
                "filepath": final_path,
                "filename": final_name,
                "finished_at": time.time(),
                "speed": None,
                "owner": owner,
            })
            job_snap = dict(JOBS[job_id])
        if os.path.exists(final_path):
            record_download_meta(job_id, final_name, owner, os.path.getsize(final_path), folder_name=folder_name, group_id=group_id)
        append_job_log(job_id, f"[+] Archivo completado: {final_name}")
        threading.Thread(target=sync_to_cloud, args=(final_path, final_name, job_snap, user_cloud_sync), daemon=True).start()
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update({"status": "error", "error": str(e), "finished_at": time.time()})
        append_job_log(job_id, f"[!] Error en Cobalt: {e}")
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def run_download(job_id: str, url: str, quality: str, playlist_mode: bool, total_count: int = 0,
                  start_time=None, end_time=None, video_format="mp4", subtitles="none",
                  owner: str = "admin", user_cloud_sync: dict = None,
                  selected_indexes: list = None, playlist_delivery: str = "zip",
                  folder_name: str = None, group_id: str = None):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    append_job_log(job_id, f"[*] [yt-dlp] Iniciando proceso de descarga ({quality})...")

    completed_ids = set()
    last_log_milestone = [-1]

    def hook(d):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return

            info = d.get("info_dict") or {}
            playlist_index = info.get("playlist_index")
            playlist_count = info.get("playlist_count") or total_count
            video_id = info.get("id")

            if playlist_count:
                job["total_count"] = playlist_count
            if playlist_index:
                job["current_index"] = playlist_index
            if info.get("title"):
                job["current_title"] = info.get("title")

            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                job["file_percent"] = int(downloaded * 100 / total) if total else 0
                job["speed"] = format_speed(d.get("speed"))
                job["eta_seconds"] = d.get("eta")
                job["status"] = "downloading"
            elif d["status"] == "finished":
                if video_id:
                    completed_ids.add(video_id)
                job["completed_count"] = len(completed_ids)
                job["status"] = "processing"
                job["speed"] = None

            job["completed_count"] = len(completed_ids)
            total_for_pct = job.get("total_count") or 1
            file_fraction = (job.get("file_percent") or 0) / 100
            job["percent"] = min(100, int((job["completed_count"] + file_fraction) / total_for_pct * 100))

            # Periodic user-friendly console logging
            milestone = job["percent"] // 20
            if milestone > last_log_milestone[0] and job["percent"] > 0:
                last_log_milestone[0] = milestone
                if "logs" not in job:
                    job["logs"] = []
                job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": f"[+] Progreso: {job['percent']}% - Velocidad: {job.get('speed') or 'estable'}"})
                if len(job["logs"]) > 150:
                    job["logs"] = job["logs"][-150:]


    try:
        outtmpl = os.path.join(job_dir, "%(playlist_index&{:02d} - |)s%(title).100B.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": not playlist_mode,
            "ignoreerrors": True,
            **cookies_opts(),
        }

        if selected_indexes and len(selected_indexes) > 0:
            ydl_opts["playlist_items"] = ",".join(str(i) for i in selected_indexes)

        if is_audio_quality(quality):
            bitrate_map = {
                "audio_128": "128", "audio_192": "192",
                "audio_256": "256", "audio_320": "320",
            }
            target_format = "mp3"
            if quality in ("flac", "m4a", "opus", "wav"):
                target_format = quality

            pp = {
                "key": "FFmpegExtractAudio",
                "preferredcodec": target_format,
            }
            if target_format == "mp3":
                pp["preferredquality"] = bitrate_map.get(quality, "320")

            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [pp]
        else:
            fmt_str = QUALITY_FORMAT_MAP.get(quality, "bestvideo+bestaudio/best")
            ydl_opts["format"] = fmt_str
            ydl_opts["merge_output_format"] = video_format if video_format in ("mp4", "mkv", "webm") else "mp4"

        if subtitles in ("embed", "download"):
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitleslangs"] = ["es", "en", "all"]
            if subtitles == "embed" and not is_audio_quality(quality):
                if "postprocessors" not in ydl_opts:
                    ydl_opts["postprocessors"] = []
                ydl_opts["postprocessors"].append({
                    "key": "FFmpegEmbedSubtitle",
                    "already_have_subtitle": False,
                })

        if start_time is not None or end_time is not None:
            ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
                None, [(start_time or 0, end_time or float("inf"))]
            )
            ydl_opts["force_keyframes_at_cuts"] = True

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "downloading"

        extract_with_fallback(url, ydl_opts, download=True)

        files = [f for f in os.listdir(job_dir) if not f.endswith(".part") and not f.endswith(".ytdl")]
        if not files:
            raise RuntimeError("No se generó ningún archivo")

        if playlist_mode and playlist_delivery == "individual":
            individual_files = []
            f_group_name = folder_name or f"Playlist {job_id[:8]}"
            f_group_id = group_id or job_id
            for f in files:
                fname = f"{job_id}_{f}"
                fpath = os.path.join(DOWNLOAD_DIR, fname)
                shutil.move(os.path.join(job_dir, f), fpath)
                fsize = os.path.getsize(fpath) if os.path.exists(fpath) else 0
                item_jid = f"{job_id}_{len(individual_files)+1}"
                record_download_meta(item_jid, f, owner, fsize, folder_name=f_group_name, group_id=f_group_id)
                individual_files.append({"name": f, "path": fpath, "size": fsize, "job_id": item_jid})
            
            final_path = individual_files[0]["path"] if individual_files else None
            final_name = f"{len(files)} archivos descargados individualmente"
            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "finished",
                    "percent": 100,
                    "filepath": final_path,
                    "filename": final_name,
                    "files_count": len(files),
                    "finished_at": time.time(),
                    "speed": None,
                    "owner": owner,
                    "delivery": "individual",
                })
            append_job_log(job_id, f"[+] Se procesaron {len(files)} archivos individualmente.")
        elif playlist_mode:
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "zipping"
                JOBS[job_id]["current_title"] = "Comprimiendo playlist en ZIP..."
            append_job_log(job_id, "[*] Comprimiendo elementos en archivo ZIP...")
            zip_filename = f"playlist_{job_id[:8]}.zip"
            zip_path = os.path.join(DOWNLOAD_DIR, f"{job_id}_{zip_filename}")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(os.path.join(job_dir, f), f)
            final_path = zip_path
            final_name = zip_filename
            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "finished",
                    "percent": 100,
                    "filepath": final_path,
                    "filename": final_name,
                    "finished_at": time.time(),
                    "speed": None,
                    "owner": owner,
                    "delivery": "zip",
                })
            if os.path.exists(final_path):
                record_download_meta(job_id, final_name, owner, os.path.getsize(final_path), folder_name=folder_name, group_id=group_id)
            append_job_log(job_id, f"[+] Archivo ZIP generado: {final_name}")
        else:
            final_filename = f"{job_id}_{files[0]}"
            final_path = os.path.join(DOWNLOAD_DIR, final_filename)
            shutil.move(os.path.join(job_dir, files[0]), final_path)
            final_name = files[0]
            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "finished",
                    "percent": 100,
                    "filepath": final_path,
                    "filename": final_name,
                    "finished_at": time.time(),
                    "speed": None,
                    "owner": owner,
                })
            if os.path.exists(final_path):
                record_download_meta(job_id, final_name, owner, os.path.getsize(final_path), folder_name=folder_name, group_id=group_id)
            append_job_log(job_id, f"[+] Archivo descargado: {final_name}")

        job_snap = dict(JOBS[job_id])
        if final_path and os.path.exists(final_path):
            threading.Thread(target=sync_to_cloud, args=(final_path, final_name, job_snap, user_cloud_sync), daemon=True).start()
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update({"status": "error", "error": str(e), "finished_at": time.time()})
        append_job_log(job_id, f"[!] Error en yt-dlp: {e}")
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def run_download_cascade(job_id: str, url: str, quality: str, playlist_mode: bool, total_count: int = 0,
                         start_time=None, end_time=None, video_format="mp4", subtitles="none",
                         owner: str = "admin", user_cloud_sync: dict = None,
                         selected_indexes: list = None, playlist_delivery: str = "zip",
                         video_title: str = "", deezer_arl: str = "",
                         folder_name: str = None, group_id: str = None):
    attempts = []
    platform = detect_platform(url)
    append_job_log(job_id, f"[*] [Cascada Inteligente] Analizando contenido ({platform})...")

    # 1. First attempt: Cobalt v11 (for single video/audio, non-playlist)
    if not playlist_mode and start_time is None and end_time is None and subtitles == "none":
        append_job_log(job_id, "[*] [1/3] Probando extracción con Motor Cobalt Oficial...")
        try:
            run_download_cobalt(job_id, url, quality, video_title, owner, user_cloud_sync, folder_name=folder_name, group_id=group_id)
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get("status") == "finished":
                    append_job_log(job_id, "[+] Proceso finalizado exitosamente con Cobalt.")
                    return
        except Exception as e:
            err = str(e)
            attempts.append({"engine": "Cobalt v11 (API)", "status": "failed", "error": err})
            append_job_log(job_id, f"[!] Cobalt no pudo extraer el stream ({err}). Pasando a siguiente método...")

    # 2. Second attempt: Specialized Music Engine if Spotify/Deezer
    if platform in ("Deezer", "Spotify") and not playlist_mode:
        append_job_log(job_id, f"[*] [2/3] Probando Motor Musical Especializado ({platform})...")
        try:
            run_download_music(job_id, url, quality, deezer_arl, None, owner, user_cloud_sync, folder_name=folder_name, group_id=group_id)
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get("status") == "finished":
                    append_job_log(job_id, "[+] Proceso finalizado exitosamente con Motor Musical.")
                    return
        except Exception as e:
            err = str(e)
            attempts.append({"engine": f"Motor Música ({platform})", "status": "failed", "error": err})
            append_job_log(job_id, f"[!] Motor musical no pudo procesar ({err}). Pasando a yt-dlp...")

    # 3. Third attempt: yt-dlp with PoToken Provider and fallback clients
    append_job_log(job_id, "[*] [3/3] Probando extracción completa con yt-dlp (PoToken & Multi-Cliente)...")
    try:
        run_download(
            job_id, url, quality, playlist_mode, total_count, start_time, end_time,
            video_format, subtitles, owner, user_cloud_sync, selected_indexes, playlist_delivery,
            folder_name=folder_name, group_id=group_id
        )
        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get("status") == "finished":
                append_job_log(job_id, "[+] Proceso finalizado exitosamente con yt-dlp.")
                return
    except Exception as e:
        err = str(e)
        attempts.append({"engine": "yt-dlp (Extractor Principal)", "status": "failed", "error": err})
        append_job_log(job_id, f"[!] yt-dlp falló: {err}")

    # If all engines failed, record detailed error report
    with JOBS_LOCK:
        JOBS[job_id].update({
            "status": "error",
            "error": "Todos los métodos y motores de descarga fallaron al procesar este enlace.",
            "attempts": attempts,
            "finished_at": time.time(),
        })
    append_job_log(job_id, "[!] ERROR: Se agotaron todos los métodos de descarga disponibles.")


# ==================== BACKGROUND QUEUE WORKER ====================

def background_queue_worker():
    global ACTIVE_WORKER_JOB
    while True:
        job_id = None
        with QUEUE_LOCK:
            current_queue = list(QUEUE_LIST)

        for jid in current_queue:
            with JOBS_LOCK:
                j = JOBS.get(jid)
                status = j.get("status") if j else None
            if status == "queued":
                job_id = jid
                break
            elif status in ("finished", "error", "cancelled", None):
                with QUEUE_LOCK:
                    if jid in QUEUE_LIST:
                        QUEUE_LIST.remove(jid)

        if not job_id:
            ACTIVE_WORKER_JOB = None
            time.sleep(1)
            continue

        ACTIVE_WORKER_JOB = job_id
        job_copy = None
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job and job.get("status") != "cancelled":
                job["status"] = "downloading"
                job["started_at"] = time.time()
                job_copy = dict(job)

        if not job_copy:
            with QUEUE_LOCK:
                if job_id in QUEUE_LIST:
                    QUEUE_LIST.remove(job_id)
            ACTIVE_WORKER_JOB = None
            continue

        save_queue_state()

        try:
            engine = job_copy.get("engine", "auto")
            url = job_copy.get("url")
            quality = job_copy.get("quality", "best")
            playlist_mode = job_copy.get("playlist", False)
            total_count = job_copy.get("total_count", 0)
            start_time = job_copy.get("start_time")
            end_time = job_copy.get("end_time")
            video_format = job_copy.get("video_format", "mp4")
            subtitles = job_copy.get("subtitles", "none")
            owner = job_copy.get("owner", "admin")

            user_cloud_sync = job_copy.get("user_cloud_sync")
            selected_indexes = job_copy.get("selected_indexes")
            playlist_delivery = job_copy.get("playlist_delivery", "zip")
            video_title = job_copy.get("video_title", "")
            deezer_arl = job_copy.get("deezer_arl", "")
            folder_name = job_copy.get("folder_name")
            group_id = job_copy.get("group_id")


            if engine in ("auto", "cascade"):
                run_download_cascade(
                    job_id, url, quality, playlist_mode, total_count, start_time, end_time,
                    video_format, subtitles, owner, user_cloud_sync, selected_indexes,
                    playlist_delivery, video_title, deezer_arl, folder_name=folder_name, group_id=group_id
                )
            elif detect_platform(url) in ("Deezer", "Spotify") and not playlist_mode:
                run_download_music(
                    job_id, url, quality, deezer_arl, None, owner, user_cloud_sync,
                    folder_name=folder_name, group_id=group_id
                )
            elif engine == "cobalt":
                run_download_cobalt(
                    job_id, url, quality, video_title, owner, user_cloud_sync,
                    folder_name=folder_name, group_id=group_id
                )
            else:
                run_download(
                    job_id, url, quality, playlist_mode, total_count, start_time, end_time,
                    video_format, subtitles, owner, user_cloud_sync, selected_indexes,
                    playlist_delivery, folder_name=folder_name, group_id=group_id
                )
        except Exception as e:
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["status"] = "error"
                    JOBS[job_id]["error"] = str(e)
                    JOBS[job_id]["finished_at"] = time.time()
        finally:
            with QUEUE_LOCK:
                if job_id in QUEUE_LIST:
                    QUEUE_LIST.remove(job_id)
            ACTIVE_WORKER_JOB = None
            save_queue_state()


# Load persisted queue and start worker
load_queue_state()
threading.Thread(target=background_queue_worker, daemon=True).start()


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(force=True)
    raw_url = (data or {}).get("url", "").strip()
    quality = (data or {}).get("quality", "best")
    video_format = (data or {}).get("video_format", "mp4")
    subtitles = (data or {}).get("subtitles", "none")
    playlist_mode = bool((data or {}).get("playlist", False))
    total_count = int((data or {}).get("total_count") or 0)
    start_raw = (data or {}).get("start_time")
    end_raw = (data or {}).get("end_time")
    engine = (data or {}).get("engine", "auto")
    video_title = (data or {}).get("video_title", "")
    user_cloud_sync = (data or {}).get("user_cloud_sync")
    selected_indexes = (data or {}).get("selected_indexes") or []
    playlist_delivery = (data or {}).get("playlist_delivery", "zip")
    folder_name = (data or {}).get("folder_name")
    group_id = (data or {}).get("group_id")

    user = getattr(request, "current_user", {}) or {}
    owner = user.get("username", "admin")

    if not raw_url:
        return jsonify({"error": "Falta la URL"}), 400

    url = normalize_url(raw_url)

    if engine == "cobalt" and playlist_mode:
        return jsonify({"error": "Cobalt no soporta descargar playlists completas todavía, usá yt-dlp para eso"}), 400

    start_time = end_time = None
    if not playlist_mode:
        try:
            start_time = parse_time_to_seconds(start_raw)
            end_time = parse_time_to_seconds(end_raw)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if start_time is not None and end_time is not None and start_time >= end_time:
            return jsonify({"error": "El tiempo de inicio tiene que ser menor al de fin"}), 400
        if engine == "cobalt" and (start_time is not None or end_time is not None):
            return jsonify({"error": "Cobalt no soporta recorte de video todavía, usá yt-dlp para eso"}), 400

    job_id = uuid.uuid4().hex
    deezer_arl = (data or {}).get("deezer_arl", "").strip()

    job_spec = {
        "status": "queued",
        "percent": 0,
        "completed_count": 0,
        "total_count": total_count if not selected_indexes else len(selected_indexes),
        "current_index": None,
        "current_title": video_title or url,
        "file_percent": 0,
        "speed": None,
        "eta_seconds": None,
        "owner": owner,
        "url": url,
        "quality": quality,
        "video_format": video_format,
        "subtitles": subtitles,
        "playlist": playlist_mode,
        "selected_indexes": selected_indexes,
        "playlist_delivery": playlist_delivery,
        "engine": engine,
        "video_title": video_title,
        "deezer_arl": deezer_arl,
        "folder_name": folder_name,
        "group_id": group_id,
        "user_cloud_sync": user_cloud_sync,
        "created_at": time.time(),
        "logs": [{"time": time.strftime("%H:%M:%S"), "text": f"[*] Solicitud encolada para descarga en segundo plano ({quality})."}],
        "attempts": [],
    }

    enqueue_job(job_id, job_spec)

    return jsonify({"job_id": job_id, "status": "queued"})




# ==================== QUEUE CONTROL API ====================

@app.route("/api/queue")
def get_queue():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    with QUEUE_LOCK:
        q_ids = list(QUEUE_LIST)

    active_job = None
    queued_jobs = []
    completed_jobs = []

    with JOBS_LOCK:
        if ACTIVE_WORKER_JOB and ACTIVE_WORKER_JOB in JOBS:
            j = JOBS[ACTIVE_WORKER_JOB]
            if is_admin or j.get("owner") == username:
                active_job = dict(j)
                active_job["job_id"] = ACTIVE_WORKER_JOB

        for jid in q_ids:
            if jid == ACTIVE_WORKER_JOB:
                continue
            j = JOBS.get(jid)
            if j and (is_admin or j.get("owner") == username):
                item = dict(j)
                item["job_id"] = jid
                queued_jobs.append(item)

        for jid, j in list(JOBS.items())[-30:]:
            if j.get("status") in ("finished", "error", "cancelled"):
                if is_admin or j.get("owner") == username:
                    item = dict(j)
                    item["job_id"] = jid
                    completed_jobs.append(item)

    return jsonify({
        "active": active_job,
        "queue": queued_jobs,
        "completed": completed_jobs,
        "total_queued": len(queued_jobs) + (1 if active_job else 0),
    })


@app.route("/api/queue/move", methods=["POST"])
def move_queue_item():
    data = request.get_json(force=True) or {}
    job_id = data.get("job_id")
    direction = data.get("direction", "up")

    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job or (not is_admin and job.get("owner") != username):
            return jsonify({"error": "No tenés permiso sobre este elemento"}), 403

    with QUEUE_LOCK:
        if job_id not in QUEUE_LIST:
            return jsonify({"error": "El trabajo no está en la cola pendiente"}), 400
        
        idx = QUEUE_LIST.index(job_id)
        start_idx = 1 if (ACTIVE_WORKER_JOB and QUEUE_LIST and QUEUE_LIST[0] == ACTIVE_WORKER_JOB) else 0

        if direction == "up" and idx > start_idx:
            QUEUE_LIST[idx], QUEUE_LIST[idx - 1] = QUEUE_LIST[idx - 1], QUEUE_LIST[idx]
        elif direction == "down" and idx < len(QUEUE_LIST) - 1:
            QUEUE_LIST[idx], QUEUE_LIST[idx + 1] = QUEUE_LIST[idx + 1], QUEUE_LIST[idx]

    save_queue_state()
    return jsonify({"success": True, "queue": QUEUE_LIST})


@app.route("/api/queue/<job_id>", methods=["DELETE"])
def cancel_queue_item(job_id):
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Trabajo no encontrado"}), 404
        if not is_admin and job.get("owner") != username:
            return jsonify({"error": "No tenés permiso sobre este trabajo"}), 403

        job["status"] = "cancelled"
        job["finished_at"] = time.time()
        if "logs" not in job:
            job["logs"] = []
        job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": "[!] Descarga cancelada por el usuario."})

    with QUEUE_LOCK:
        if job_id in QUEUE_LIST:
            QUEUE_LIST.remove(job_id)

    save_queue_state()
    return jsonify({"success": True, "message": "Elemento quitado/cancelado de la cola"})


@app.route("/api/queue/cancel-all", methods=["POST"])
def cancel_all_queue():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    cancelled_count = 0
    with QUEUE_LOCK:
        q_ids = list(QUEUE_LIST)

    for jid in q_ids:
        if jid == ACTIVE_WORKER_JOB:
            continue
        with JOBS_LOCK:
            job = JOBS.get(jid)
            if job and (is_admin or job.get("owner") == username):
                job["status"] = "cancelled"
                job["finished_at"] = time.time()
                if "logs" not in job:
                    job["logs"] = []
                job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": "[!] Descarga cancelada por vaciado de cola."})
        with QUEUE_LOCK:
            if jid in QUEUE_LIST:
                QUEUE_LIST.remove(jid)
                cancelled_count += 1

    save_queue_state()

    return jsonify({"success": True, "cancelled_count": cancelled_count})


@app.route("/api/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


@app.route("/api/files/<job_id>")
def files(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job and job.get("status") == "finished" and job.get("filepath") and os.path.exists(job["filepath"]):
        return send_file(job["filepath"], as_attachment=True, download_name=job.get("filename"))

    # Fallback to search in DOWNLOAD_DIR
    if os.path.exists(DOWNLOAD_DIR):
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry.startswith(job_id):
                full_path = os.path.join(DOWNLOAD_DIR, entry)
                if os.path.isfile(full_path):
                    disp_name = entry[len(job_id):].lstrip("_-") or entry
                    return send_file(full_path, as_attachment=True, download_name=disp_name)

    abort(404)


# ==================== BATCH DOWNLOAD QUEUE API ====================

@app.route("/api/batch-download", methods=["POST"])
def batch_download():
    data = request.get_json(force=True) or {}
    urls_raw = data.get("urls", [])
    if isinstance(urls_raw, str):
        urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
    elif isinstance(urls_raw, list):
        urls = [str(u).strip() for u in urls_raw if str(u).strip()]
    else:
        urls = []

    if not urls:
        return jsonify({"error": "No se enviaron URLs válidas"}), 400

    quality = data.get("quality", "best")
    video_format = data.get("video_format", "mp4")
    subtitles = data.get("subtitles", "none")
    engine = data.get("engine", "auto")
    deezer_arl = data.get("deezer_arl", "").strip()
    user_cloud_sync = data.get("user_cloud_sync")

    user = getattr(request, "current_user", {}) or {}
    owner = user.get("username", "admin")

    batch_id = uuid.uuid4().hex
    batch_folder_name = f"Lote ({time.strftime('%Y-%m-%d %H:%M')})"
    job_ids = []

    for raw_url in urls:
        job_id = uuid.uuid4().hex
        job_ids.append(job_id)
        job_spec = {
            "status": "queued",
            "percent": 0,
            "completed_count": 0,
            "total_count": 1,
            "current_index": 1,
            "current_title": raw_url,
            "file_percent": 0,
            "speed": None,
            "eta_seconds": None,
            "url": raw_url,
            "quality": quality,
            "video_format": video_format,
            "subtitles": subtitles,
            "playlist": False,
            "engine": engine,
            "deezer_arl": deezer_arl,
            "batch_id": batch_id,
            "folder_name": batch_folder_name,
            "group_id": batch_id,
            "owner": owner,
            "user_cloud_sync": user_cloud_sync,
            "created_at": time.time(),
            "logs": [{"time": time.strftime("%H:%M:%S"), "text": "[*] Encolado en lote para procesamiento en segundo plano."}],
        }
        enqueue_job(job_id, job_spec)

    with BATCH_LOCK:
        BATCH_JOBS[batch_id] = {
            "batch_id": batch_id,
            "created_at": time.time(),
            "job_ids": job_ids,
            "total_count": len(job_ids),
        }

    return jsonify({"batch_id": batch_id, "job_ids": job_ids, "total": len(job_ids)})


@app.route("/api/batch-status/<batch_id>")
def batch_status(batch_id):
    with BATCH_LOCK:
        batch = BATCH_JOBS.get(batch_id)
    if not batch:
        abort(404)

    jobs_summary = []
    completed_count = 0
    with JOBS_LOCK:
        for jid in batch["job_ids"]:
            j = JOBS.get(jid, {})
            st = j.get("status", "unknown")
            if st in ("finished", "error"):
                completed_count += 1
            jobs_summary.append({
                "job_id": jid,
                "url": j.get("url"),
                "status": st,
                "percent": j.get("percent", 0),
                "title": j.get("current_title") or j.get("filename"),
                "filename": j.get("filename"),
                "error": j.get("error"),
                "download_url": f"/api/files/{jid}" if st == "finished" else None,
            })

    all_done = (completed_count == len(batch["job_ids"]))
    return jsonify({
        "batch_id": batch_id,
        "total_count": len(batch["job_ids"]),
        "completed_count": completed_count,
        "all_finished": all_done,
        "jobs": jobs_summary,
    })


@app.route("/api/batch-download-zip/<batch_id>")
def batch_download_zip(batch_id):
    with BATCH_LOCK:
        batch = BATCH_JOBS.get(batch_id)
    if not batch:
        abort(404)

    files_to_zip = []
    with JOBS_LOCK:
        for jid in batch["job_ids"]:
            j = JOBS.get(jid)
            if j and j.get("status") == "finished" and j.get("filepath") and os.path.exists(j["filepath"]):
                files_to_zip.append((j["filepath"], j.get("filename") or os.path.basename(j["filepath"])))

    if not files_to_zip:
        return jsonify({"error": "No hay archivos terminados para empaquetar"}), 404

    zip_path = os.path.join(DOWNLOAD_DIR, f"batch_{batch_id}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath, fname in files_to_zip:
            zf.write(fpath, arcname=fname)

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"lote_{batch_id[:8]}.zip",
        mimetype="application/zip",
    )


# ==================== CLOUD SYNC ADMIN API ====================

@app.route("/api/admin/cloud-sync", methods=["GET", "POST"])
@require_admin
def admin_cloud_sync():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        save_cloud_config(data)
        return jsonify({"message": "Configuración de Sincronización en la Nube guardada exitosamente", "cloud_sync": data})
    return jsonify({"cloud_sync": load_cloud_config()})


@app.route("/api/admin/cloud-sync/test", methods=["POST"])
@require_admin
def admin_cloud_sync_test():
    data = request.get_json(force=True) or {}
    service = data.get("service")
    config = data.get("config", {})

    if service == "webhook":
        url = config.get("url")
        if not url:
            return jsonify({"error": "Falta la URL del webhook"}), 400
        try:
            r = requests.post(url, json={"test": True, "message": "ytsite cloud sync test"}, timeout=5)
            return jsonify({"success": True, "message": f"Webhook respondió HTTP {r.status_code}"})
        except Exception as e:
            return jsonify({"error": f"Error conectando al webhook: {e}"}), 400

    if service == "telegram":
        token = config.get("bot_token")
        chat_id = config.get("chat_id")
        if not token or not chat_id:
            return jsonify({"error": "Falta Bot Token o Chat ID"}), 400
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "✅ Prueba de conexión de ytsite exitosa!"},
                timeout=6,
            )
            res = r.json()
            if res.get("ok"):
                return jsonify({"success": True, "message": "Mensaje de prueba enviado a Telegram correctamente"})
            return jsonify({"error": res.get("description", "Error de Telegram")}), 400
        except Exception as e:
            return jsonify({"error": f"Error conectando con Telegram: {e}"}), 400

    if service == "ftp":
        host = config.get("host")
        port = int(config.get("port", 21))
        user = config.get("username", "anonymous")
        pwd = config.get("password", "")
        if not host:
            return jsonify({"error": "Falta host FTP"}), 400
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=6)
            ftp.login(user, pwd)
            ftp.quit()
            return jsonify({"success": True, "message": "Conexión FTP exitosa"})
        except Exception as e:
            return jsonify({"error": f"Error conectando a FTP: {e}"}), 400

    if service == "webdav":
        url = config.get("url")
        if not url:
            return jsonify({"error": "Falta URL WebDAV"}), 400
        try:
            auth = (config.get("username", ""), config.get("password", "")) if config.get("username") else None
            r = requests.request("PROPFIND", url, auth=auth, headers={"Depth": "0"}, timeout=6)
            if r.status_code in (200, 207, 301, 302, 401):
                if r.status_code == 401:
                    return jsonify({"error": "Autenticación WebDAV fallida (401)"}), 400
                return jsonify({"success": True, "message": f"Servidor WebDAV respondió HTTP {r.status_code}"})
            return jsonify({"error": f"WebDAV respondió HTTP {r.status_code}"}), 400
        except Exception as e:
            return jsonify({"error": f"Error WebDAV: {e}"}), 400

    return jsonify({"error": "Servicio desconocido"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)


