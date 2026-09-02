import os
import json
import time
import re
import shutil
import logging
from flask import send_file

from core.config import (
    CONFIG_FILE, CLOUD_CONFIG_FILE, DOWNLOADS_META_FILE, QUEUE_STATE_FILE,
    COOKIES_FILE, DOWNLOAD_DIR, PLAYER_CLIENTS_ENV,
    CLEANUP_AFTER_HOURS, DISK_EMERGENCY_THRESHOLD_PERCENT
)
from core.state import JOBS_LOCK, JOBS, QUEUE_LIST, QUEUE_LOCK

def validate_media_url(url: str) -> bool:
    """Strictly validates media URLs to prevent command injection, RCE, and protocol smuggling."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if len(url) > 2048:
        return False
    # Check for forbidden shell metacharacters / control chars / quotes (note: & is allowed as standard URL query delimiter)
    forbidden = [";", "|", "`", "$", "\n", "\r", "\t", "<", ">", '"', "'", "\0", "\\"]
    if any(c in url for c in forbidden):
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        return True
    except Exception:
        return False


def safe_download_path(filename_or_subpath: str) -> str:
    """Verifies that filename_or_subpath resolves strictly inside DOWNLOAD_DIR without path traversal."""
    if not filename_or_subpath:
        return None
    try:
        raw = str(filename_or_subpath).strip()
        abs_download_dir = os.path.abspath(DOWNLOAD_DIR)
        if os.path.isabs(raw):
            full_path = os.path.abspath(raw)
        else:
            clean = os.path.normpath(raw).lstrip("/\\")
            full_path = os.path.abspath(os.path.join(abs_download_dir, clean))

        if os.path.commonpath([full_path, abs_download_dir]) == abs_download_dir:
            return full_path
    except Exception:
        pass
    return None


def format_speed(bytes_per_sec):

    if not bytes_per_sec:
        return None
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.1f} {unit}"
        bytes_per_sec /= 1024
    return f"{bytes_per_sec:.1f} TB/s"


def load_config() -> dict:
    default_cfg = {
        "site_title": "⚡ dHtools",
        "site_subtitle": "Suite multimedia avanzada para descargas y extracción.",
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
        "webdav": {"enabled": False, "url": "", "username": "", "password": "", "remote_path": "/dhtools"},

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


def is_audio_quality(quality: str) -> bool:
    if not quality:
        return False
    q = str(quality).lower()
    return q.startswith("audio_") or q in (
        "flac", "m4a", "opus", "wav", "mp3", "aac", "alac", "vorbis"
    )


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


def cookies_opts():
    if os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        return {"cookiefile": COOKIES_FILE}
    return {}


def player_client_opts(clients=None, for_download: bool = True):
    opts = {
        "extractor_args": {
            "youtubetab": {"skip": ["authcheck"]}
        }
    }
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
