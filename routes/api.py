import os
import sys
import re
import json
import time
import logging
import threading
import zipfile
import shutil
import uuid
from flask import Blueprint, request, jsonify, send_file, Response, render_template, abort

from core.config import DOWNLOAD_DIR, COBALT_URL
from core.state import (
    JOBS, JOBS_LOCK, BATCH_JOBS, BATCH_LOCK, QUEUE_LIST, QUEUE_LOCK,
    ACTIVE_WORKER_JOB
)
from core.utils import (
    validate_media_url, is_audio_quality, format_for_quality, format_bytes,
    load_config, safe_filename, enqueue_job, record_download_meta,
    delete_download_meta, load_downloads_meta, save_queue_state,
    safe_download_path, parse_time_to_seconds, cookies_opts
)
from core.downloader import (
    run_download, run_download_cascade, append_job_log, purge_downloads,
    get_ytdlp_version, run_pip_update, restart_process_soon,
    extract_with_fallback, normalize_url, detect_platform, is_playlist_url,
    get_deezer_info, get_spotify_info
)
from routes.auth import require_admin

api_bp = Blueprint("api_bp", __name__)

@api_bp.route("/api/ytdlp-version")
def ytdlp_version():
    return jsonify({"version": get_ytdlp_version()})


@api_bp.route("/api/update-ytdlp", methods=["POST"])
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


@api_bp.route("/api/info", methods=["POST"])
def info():
    data = request.get_json(force=True)
    raw_url = (data or {}).get("url", "").strip()
    if not raw_url:
        return jsonify({"error": "Falta la URL"}), 400
    if not validate_media_url(raw_url):
        return jsonify({"error": "La URL ingresada no es válida o contiene caracteres no permitidos"}), 400

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


@api_bp.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(force=True)
    raw_url = (data or {}).get("url", "").strip()
    quality = (data or {}).get("quality", "best")
    video_format = (data or {}).get("video_format", "mp4")
    subtitles = (data or {}).get("subtitles", "none")
    playlist_mode = bool((data or {}).get("playlist", False))
    if not playlist_mode and is_playlist_url(raw_url):
        playlist_mode = True
    total_count = int((data or {}).get("total_count") or 0)
    start_raw = (data or {}).get("start_time")
    end_raw = (data or {}).get("end_time")
    engine = (data or {}).get("engine", "auto")
    video_title = (data or {}).get("video_title") or (data or {}).get("title") or ""
    user_cloud_sync = (data or {}).get("user_cloud_sync")
    selected_indexes = (data or {}).get("selected_indexes") or []
    playlist_delivery = (data or {}).get("playlist_delivery", "zip")
    folder_name = (data or {}).get("folder_name")
    group_id = (data or {}).get("group_id")

    user = getattr(request, "current_user", {}) or {}
    owner = user.get("username", "admin")

    if not raw_url:
        return jsonify({"error": "Falta la URL"}), 400
    if not validate_media_url(raw_url):
        return jsonify({"error": "La URL ingresada no es válida o contiene caracteres no permitidos"}), 400

    url = normalize_url(raw_url)


    job_id = uuid.uuid4().hex
    if playlist_mode and not group_id:
        group_id = f"pl_{int(time.time())}_{job_id[:6]}"

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


@api_bp.route("/api/playlist-download", methods=["POST"])
def playlist_download():
    data = request.get_json(force=True) or {}
    items = data.get("items") or []
    playlist_url = data.get("playlist_url") or ""
    quality = data.get("quality", "best")
    video_format = data.get("video_format", "mp4")
    subtitles = data.get("subtitles", "none")
    engine = data.get("engine", "auto")
    folder_name = data.get("folder_name") or "Playlist"
    group_id = data.get("group_id") or f"pl_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    playlist_delivery = data.get("playlist_delivery", "individual")
    user_cloud_sync = data.get("user_cloud_sync")

    user = getattr(request, "current_user", {}) or {}
    owner = user.get("username", "admin")

    if not items and not playlist_url:
        return jsonify({"error": "No se recibieron elementos de playlist para descargar"}), 400
    if playlist_url and not validate_media_url(playlist_url):
        return jsonify({"error": "La URL de playlist no es válida o contiene caracteres no permitidos"}), 400


    created_job_ids = []
    total_items = len(items)

    if playlist_delivery == "individual" and items:
        for idx, item in enumerate(items):
            item_url = item.get("url") or (f"https://www.youtube.com/watch?v={item.get('id')}" if item.get('id') else playlist_url)
            item_title = item.get("title") or f"Pista {idx + 1}"
            item_thumb = item.get("thumbnail") or ""
            item_idx = item.get("index") or (idx + 1)
            
            jid = uuid.uuid4().hex
            job_spec = {
                "status": "queued",
                "percent": 0,
                "file_percent": 0,
                "completed_count": 0,
                "total_count": total_items,
                "current_index": item_idx,
                "current_title": item_title,
                "speed": None,
                "eta_seconds": None,
                "owner": owner,
                "url": normalize_url(item_url),
                "quality": quality,
                "video_format": video_format,
                "subtitles": subtitles,
                "playlist": False,
                "selected_indexes": [],
                "playlist_delivery": "individual",
                "engine": engine,
                "video_title": item_title,
                "thumbnail": item_thumb,
                "deezer_arl": data.get("deezer_arl", "").strip(),
                "folder_name": folder_name,
                "group_id": group_id,
                "item_index": item_idx,
                "user_cloud_sync": user_cloud_sync,
                "created_at": time.time(),
                "logs": [{"time": time.strftime("%H:%M:%S"), "text": f"[*] Pista #{item_idx} '{item_title}' encolada en segundo plano."}],
                "attempts": [],
            }
            enqueue_job(jid, job_spec)
            created_job_ids.append(jid)
    else:
        # Monolithic / ZIP playlist download as 1 master job
        jid = uuid.uuid4().hex
        selected_indexes = data.get("selected_indexes") or []
        job_spec = {
            "status": "queued",
            "percent": 0,
            "completed_count": 0,
            "total_count": len(selected_indexes) if selected_indexes else total_items,
            "current_index": None,
            "current_title": folder_name,
            "file_percent": 0,
            "speed": None,
            "eta_seconds": None,
            "owner": owner,
            "url": normalize_url(playlist_url or (items[0].get("url") if items else "")),
            "quality": quality,
            "video_format": video_format,
            "subtitles": subtitles,
            "playlist": True,
            "selected_indexes": selected_indexes,
            "playlist_delivery": playlist_delivery,
            "engine": engine,
            "video_title": folder_name,
            "deezer_arl": data.get("deezer_arl", "").strip(),
            "folder_name": folder_name,
            "group_id": group_id,
            "user_cloud_sync": user_cloud_sync,
            "created_at": time.time(),
            "logs": [{"time": time.strftime("%H:%M:%S"), "text": f"[*] Playlist '{folder_name}' encolada para empaquetado ZIP."}],
            "attempts": [],
        }
        enqueue_job(jid, job_spec)
        created_job_ids.append(jid)

    return jsonify({
        "success": True,
        "group_id": group_id,
        "job_ids": created_job_ids,
        "total": len(created_job_ids),
        "folder_name": folder_name,
    })


@api_bp.route("/api/playlist-status/<group_id>")
def playlist_status(group_id):
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    with JOBS_LOCK:
        items = []
        completed_count = 0
        error_count = 0
        cancelled_count = 0
        running_job = None
        folder_title = None

        for jid, j in JOBS.items():
            if j.get("group_id") == group_id:
                if is_admin or j.get("owner") == username:
                    item = dict(j)
                    item["job_id"] = jid
                    items.append(item)
                    if not folder_title and j.get("folder_name"):
                        folder_title = j.get("folder_name")
                    if j.get("status") == "finished":
                        completed_count += 1
                    elif j.get("status") == "error":
                        error_count += 1
                    elif j.get("status") == "cancelled":
                        cancelled_count += 1
                    elif j.get("status") in ("downloading", "processing", "zipping"):
                        running_job = item

    items.sort(key=lambda x: x.get("item_index", 0))
    total_count = len(items)
    all_finished = total_count > 0 and (completed_count + error_count + cancelled_count >= total_count)
    overall_percent = int((completed_count / total_count * 100)) if total_count > 0 else 0

    return jsonify({
        "group_id": group_id,
        "folder_name": folder_title or "Playlist",
        "total_count": total_count,
        "completed_count": completed_count,
        "error_count": error_count,
        "cancelled_count": cancelled_count,
        "all_finished": all_finished,
        "overall_percent": overall_percent,
        "active_item": running_job,
        "items": items,
    })


@api_bp.route("/api/playlist-cancel/<group_id>", methods=["POST"])
def playlist_cancel(group_id):
    global QUEUE_LIST
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    cancelled_count = 0
    with QUEUE_LOCK:
        with JOBS_LOCK:
            for jid, j in list(JOBS.items()):
                if j.get("group_id") == group_id and (is_admin or j.get("owner") == username):
                    if j.get("status") in ("queued", "downloading", "processing"):
                        j["status"] = "cancelled"
                        j["finished_at"] = time.time()
                        if "logs" not in j:
                            j["logs"] = []
                        j["logs"].append({"time": time.strftime("%H:%M:%S"), "text": "[!] Cancelado por usuario."})
                        cancelled_count += 1
            QUEUE_LIST = [jid for jid in QUEUE_LIST if JOBS.get(jid, {}).get("group_id") != group_id or JOBS.get(jid, {}).get("status") not in ("cancelled", "error")]
    save_queue_state()
    return jsonify({"success": True, "cancelled_count": cancelled_count, "group_id": group_id})


@api_bp.route("/api/queue")
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
            if j.get("status") in ("downloading", "processing", "zipping", "queued") and (is_admin or j.get("owner") == username):
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


@api_bp.route("/api/debug-threads")
def debug_threads():
    import traceback
    res = {}
    for th in threading.enumerate():
        frame = sys._current_frames().get(th.ident)
        stack = traceback.format_stack(frame) if frame else []
        res[th.name] = {
            "daemon": th.daemon,
            "alive": th.is_alive(),
            "stack": stack,
        }
    return jsonify(res)


@api_bp.route("/api/queue/move", methods=["POST"])

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


@api_bp.route("/api/queue/<job_id>", methods=["DELETE"])
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


@api_bp.route("/api/queue/cancel-all", methods=["POST"])
def cancel_all_queue():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    cancelled_count = 0
    with QUEUE_LOCK:
        q_ids = list(QUEUE_LIST)

    for jid in q_ids:
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

    if ACTIVE_WORKER_JOB:
        with JOBS_LOCK:
            act_job = JOBS.get(ACTIVE_WORKER_JOB)
            if act_job and (is_admin or act_job.get("owner") == username):
                act_job["status"] = "cancelled"
                act_job["finished_at"] = time.time()
                if "logs" not in act_job:
                    act_job["logs"] = []
                act_job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": "[!] Descarga activa abortada por vaciado de cola."})
                cancelled_count += 1

    save_queue_state()
    return jsonify({"success": True, "cancelled_count": cancelled_count})


@api_bp.route("/api/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


@api_bp.route("/api/files/<job_id>")
def files(job_id):
    if not job_id or not re.match(r"^[a-zA-Z0-9_-]+$", str(job_id)):
        abort(400)

    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    with JOBS_LOCK:
        job = JOBS.get(job_id)

    # Ownership check on in-memory jobs
    if job:
        job_owner = job.get("owner")
        if job_owner and not is_admin and job_owner != username:
            return jsonify({"error": "No tenés permiso para acceder a este archivo"}), 403

    # Ownership check on persistent downloads meta
    meta = load_downloads_meta()
    meta_entry = meta.get(job_id)
    if meta_entry:
        meta_owner = meta_entry.get("username")
        if meta_owner and not is_admin and meta_owner != username:
            return jsonify({"error": "No tenés permiso para acceder a este archivo"}), 403

    if job and job.get("status") == "finished" and job.get("filepath"):
        safe_path = safe_download_path(job["filepath"])
        if safe_path and os.path.isfile(safe_path):
            dl_name = job.get("filename") or os.path.basename(safe_path)
            return send_file(safe_path, as_attachment=True, download_name=dl_name)

    # If this is a group/playlist or batch job, search for the pre-generated zip first!
    if os.path.exists(DOWNLOAD_DIR):
        # 1. Priority 1: Look for .zip matching job_id
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry.startswith(job_id) and entry.lower().endswith(".zip"):
                safe_path = safe_download_path(entry)
                if safe_path and os.path.isfile(safe_path):
                    disp_name = entry[len(job_id):].lstrip("_-") or entry
                    return send_file(safe_path, as_attachment=True, download_name=disp_name)

        # 2. Priority 2: Look for any single file starting with job_id
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry.startswith(job_id):
                safe_path = safe_download_path(entry)
                if safe_path and os.path.isfile(safe_path):
                    disp_name = entry[len(job_id):].lstrip("_-") or entry
                    return send_file(safe_path, as_attachment=True, download_name=disp_name)

    abort(404)


@api_bp.route("/api/batch-download", methods=["POST"])
def batch_download():
    data = request.get_json(force=True) or {}
    urls_raw = data.get("urls", [])
    if isinstance(urls_raw, str):
        urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
    elif isinstance(urls_raw, list):
        urls = [str(u).strip() for u in urls_raw if str(u).strip()]
    else:
        urls = []

    valid_urls = [u for u in urls if validate_media_url(u)]
    if not valid_urls:
        return jsonify({"error": "No se enviaron URLs válidas para descargar"}), 400
    urls = valid_urls


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


@api_bp.route("/api/batch-status/<batch_id>")
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


@api_bp.route("/api/batch-download-zip/<batch_id>")
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
