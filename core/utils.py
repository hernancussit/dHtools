import os, json, time, re, shutil
import logging
from flask import send_file

from core.config import CONFIG_FILE, CLOUD_CONFIG_FILE, DOWNLOADS_META_FILE, QUEUE_STATE_FILE
from core.state import JOBS_LOCK, JOBS, QUEUE_LIST, QUEUE_LOCK

def validate_media_url(url: str) -> bool:
    if not url or not isinstance(url, str): return False
    url = url.strip()
    if len(url) > 2048: return False
    forbidden = [";", "|", "`", "$", "\n", "\r", "\t", "<", ">", '"', "'", "\0", "\\"]
    if any(c in url for c in forbidden): return False
    return True

def safe_download_path(filename_or_subpath: str) -> str:
    from core.config import DOWNLOAD_DIR
    if not filename_or_subpath or not isinstance(filename_or_subpath, str): raise ValueError("Ruta inválida")
    if "\0" in filename_or_subpath or ".." in filename_or_subpath: raise ValueError("Ruta contiene secuencias peligrosas")
    parts = [p for p in filename_or_subpath.replace("\\", "/").split("/") if p and p != "." and p != ".."]
    if not parts: raise ValueError("Ruta resuelta vacía")
    base = os.path.abspath(DOWNLOAD_DIR)
    target = os.path.abspath(os.path.join(base, *parts))
    if not target.startswith(base): raise ValueError("Path traversal detectado")
    return target

def format_bytes(bytes_val: int) -> str:
    if bytes_val < 1024: return f"{bytes_val} B"
    elif bytes_val < 1024**2: return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024**3: return f"{bytes_val / 1024**2:.1f} MB"
    else: return f"{bytes_val / 1024**3:.2f} GB"

def get_disk_status():
    try:
        total, used, free = shutil.disk_usage("/")
        perc = (used / total) * 100
        return {"total_bytes": total, "used_bytes": used, "free_bytes": free, "percent": round(perc, 1), "formatted_total": format_bytes(total), "formatted_used": format_bytes(used), "formatted_free": format_bytes(free)}
    except Exception as e: return {"error": str(e)}

def get_ram_status():
    mem = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2: mem[parts[0].rstrip(":")] = int(parts[1]) * 1024
        total = mem.get("MemTotal", 1)
        free = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = total - free
        perc = (used / total) * 100
        return {"total_bytes": total, "used_bytes": used, "free_bytes": free, "percent": round(perc, 1), "formatted_total": format_bytes(total), "formatted_used": format_bytes(used), "formatted_free": format_bytes(free)}
    except Exception: return {"error": "Not available"}

def safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def format_for_quality(quality: str) -> str:
    qmap = {"best": "La mejor calidad", "audio_128": "Audio MP3 (128kbps)", "audio_192": "Audio MP3 (192kbps)", "audio_256": "Audio MP3 (256kbps)", "audio_320": "Audio MP3 (320kbps)"}
    return qmap.get(quality, quality)

def is_audio_quality(quality: str) -> bool:
    return quality.startswith("audio_")

def parse_time_to_seconds(value):
    if not value: return 0
    if isinstance(value, (int, float)): return int(value)
    if isinstance(value, str):
        if ":" in value:
            parts = value.split(":")
            if len(parts) == 3: return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
            if len(parts) == 2: return int(parts[0])*60 + int(parts[1])
        try: return int(float(value))
        except ValueError: pass
    return 0

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {"site_title": "⚡ dHtools", "site_subtitle": "Media Downloader", "default_theme": "dark", "cleanup_after_hours": 24, "disk_emergency_threshold": 95.0, "default_engine": "yt-dlp"}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2, ensure_ascii=False)

def load_downloads_meta() -> dict:
    if os.path.exists(DOWNLOADS_META_FILE):
        try:
            with open(DOWNLOADS_META_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {}

def save_downloads_meta(meta: dict):
    with open(DOWNLOADS_META_FILE, "w", encoding="utf-8") as f: json.dump(meta, f, indent=2, ensure_ascii=False)

def record_download_meta(job_id: str, filename: str, username: str, size_bytes: int, folder_name: str = None, group_id: str = None):
    meta = load_downloads_meta()
    meta[job_id] = {"filename": filename, "username": username, "size_bytes": size_bytes, "created_at": time.time(), "folder_name": folder_name, "group_id": group_id}
    save_downloads_meta(meta)

def delete_download_meta(job_id: str):
    meta = load_downloads_meta()
    if job_id in meta:
        del meta[job_id]
        save_downloads_meta(meta)

def load_cloud_config() -> dict:
    if os.path.exists(CLOUD_CONFIG_FILE):
        try:
            with open(CLOUD_CONFIG_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {}

def save_cloud_config(cfg: dict):
    with open(CLOUD_CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2, ensure_ascii=False)

def enqueue_job(job_id: str, job_spec: dict):
    with JOBS_LOCK: JOBS[job_id] = job_spec
    with QUEUE_LOCK: QUEUE_LIST.append(job_id)
    save_queue_state()

def save_queue_state():
    with QUEUE_LOCK: q_copy = list(QUEUE_LIST)
    try:
        with open(QUEUE_STATE_FILE, "w", encoding="utf-8") as f: json.dump(q_copy, f, indent=2)
    except Exception as e: logging.exception(f"Exception caught: {e}")
