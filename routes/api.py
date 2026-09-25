import os
import re
import time
import zipfile
import uuid
import subprocess
from flask import Blueprint, request, jsonify, send_file, abort

from core.config import DOWNLOAD_DIR
from core.state import (
    JOBS, JOBS_LOCK, BATCH_JOBS, BATCH_LOCK, QUEUE_LIST, QUEUE_LOCK,
    ACTIVE_WORKER_JOB
)
from core.utils import (
    validate_media_url, format_bytes, enqueue_job, load_downloads_meta,
    save_queue_state, cookies_opts, check_user_storage_quota,
    get_user_storage_used, format_seconds, parse_time_to_seconds,
    safe_download_path
)
from core.downloader import (
    get_ytdlp_version, run_pip_update, restart_process_soon,
    extract_with_fallback, normalize_url, detect_platform, is_playlist_url,
    get_deezer_info, get_spotify_info, strip_playlist_from_url, is_pure_playlist_url
)

api_bp = Blueprint("api_bp", __name__)

@api_bp.route("/api/user/quota")
def user_quota():
    from flask import session
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username") or session.get("username", "admin")
    from routes.auth import load_users
    users = load_users()
    user_data = users.get(username, {})
    try:
        quota_gb = float(user_data.get("quota_gb", 0) or 0)
    except (ValueError, TypeError):
        quota_gb = 0
    used_bytes = get_user_storage_used(username)
    quota_bytes = int(quota_gb * (1024 ** 3)) if quota_gb > 0 else 0
    percent = round((used_bytes / quota_bytes * 100), 1) if quota_bytes > 0 else 0
    return jsonify({
        "username": username,
        "quota_gb": quota_gb,
        "quota_bytes": quota_bytes,
        "quota_formatted": f"{quota_gb:.1f} GB" if quota_gb > 0 else "Ilimitada",
        "used_bytes": used_bytes,
        "used_formatted": format_bytes(used_bytes),
        "percent_used": min(percent, 100),
        "is_exceeded": (quota_bytes > 0 and used_bytes >= quota_bytes)
    })



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
    playlist_requested = bool((data or {}).get("playlist", False))
    if not raw_url:
        return jsonify({"error": "Falta la URL"}), 400
    if not validate_media_url(raw_url):
        return jsonify({"error": "La URL ingresada no es válida o contiene caracteres no permitidos"}), 400

    if not playlist_requested:
        raw_url = strip_playlist_from_url(raw_url)

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
        "noplaylist": not playlist_requested,
        "ignore_no_formats_error": True,
        "socket_timeout": 10,
        "playlistend": 300,
        "ignoreerrors": True,
        **cookies_opts(for_url=url),
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
    if not playlist_mode:
        cleaned_url = strip_playlist_from_url(raw_url)
        if cleaned_url != raw_url:
            raw_url = cleaned_url
        elif is_pure_playlist_url(raw_url):
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

    # Enforce Storage Quota per user
    quota_ok, quota_err = check_user_storage_quota(owner)
    if not quota_ok:
        return jsonify({"error": quota_err}), 403

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

    init_log_text = f"[*] Solicitud encolada para descarga en segundo plano ({quality})."
    if start_time is not None or end_time is not None:
        st_label = format_seconds(start_time) if start_time is not None else "00:00"
        et_label = format_seconds(end_time) if end_time is not None else "fin"
        init_log_text = f"[*] Solicitud encolada con recorte inteligente: {st_label} -> {et_label} ({quality})."

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
        "start_time": start_time,
        "end_time": end_time,
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
        "logs": [{"time": time.strftime("%H:%M:%S"), "text": init_log_text}],
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

    # Enforce Storage Quota per user
    quota_ok, quota_err = check_user_storage_quota(owner)
    if not quota_ok:
        return jsonify({"error": quota_err}), 403

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

    is_stream = (request.args.get("stream") == "1" or request.args.get("preview") == "1")
    as_attachment = not is_stream

    if job and job.get("status") == "finished" and job.get("filepath"):
        safe_path = safe_download_path(job["filepath"])
        if safe_path and os.path.isfile(safe_path):
            dl_name = job.get("filename") or os.path.basename(safe_path)
            return send_file(safe_path, as_attachment=as_attachment, download_name=dl_name)

    # If this is a group/playlist or batch job, search for the pre-generated zip first!
    if os.path.exists(DOWNLOAD_DIR):
        # 1. Priority 1: Look for .zip matching job_id
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry.startswith(job_id) and entry.lower().endswith(".zip"):
                safe_path = safe_download_path(entry)
                if safe_path and os.path.isfile(safe_path):
                    disp_name = entry[len(job_id):].lstrip("_-") or entry
                    return send_file(safe_path, as_attachment=as_attachment, download_name=disp_name)

        # 2. Priority 2: Look for any single file starting with job_id
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry.startswith(job_id):
                safe_path = safe_download_path(entry)
                if safe_path and os.path.isfile(safe_path):
                    disp_name = entry[len(job_id):].lstrip("_-") or entry
                    return send_file(safe_path, as_attachment=as_attachment, download_name=disp_name)

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


# ==================== USER CLOUD PRESETS (CLOUD STORAGE HUB) ====================

@api_bp.route("/api/user/cloud-presets", methods=["GET"])
def api_get_user_cloud_presets():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    from core.utils import get_user_cloud_presets
    presets = get_user_cloud_presets(username)
    return jsonify({"presets": presets})


@api_bp.route("/api/user/cloud-presets", methods=["POST"])
def api_save_user_cloud_preset():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json(force=True) or {}
    from core.utils import save_user_cloud_preset
    ok, saved = save_user_cloud_preset(username, data)
    if ok:
        return jsonify({"success": True, "preset": saved})
    return jsonify({"error": "No se pudo guardar el preset"}), 400


@api_bp.route("/api/user/cloud-presets/<preset_id>", methods=["DELETE"])
def api_delete_user_cloud_preset(preset_id):
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    from core.utils import delete_user_cloud_preset
    ok = delete_user_cloud_preset(username, preset_id)
    if ok:
        return jsonify({"success": True, "message": "Preset eliminado correctamente"})
    return jsonify({"error": "Preset no encontrado"}), 404


@api_bp.route("/api/user/cloud-presets/test", methods=["POST"])
def api_test_user_cloud_preset():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json(force=True) or {}
    service = data.get("service")
    config = data.get("config", {})
    from core.utils import test_cloud_connection
    ok, msg = test_cloud_connection(service, config)
    if ok:
        return jsonify({"success": True, "message": msg})
    return jsonify({"error": msg}), 400


# ==================== MEDIA STUDIO API (ROADMAP v1.6.0) ====================

@api_bp.route("/api/studio/process", methods=["POST"])
def api_studio_process():
    from flask import session
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username") or session.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401

    import subprocess
    import shutil

    if request.is_json:
        data = request.get_json(force=True) or {}
    else:
        data = request.form.to_dict()

    tool = data.get("tool", "convert")  # convert, compress, trim, normalize, merge
    source_filename = (data.get("source_filename") or "").strip()

    # SPECIAL TOOL: MERGE MULTIPLE FILES
    if tool == "merge":
        files_to_merge = data.get("files", [])
        if isinstance(files_to_merge, str):
            try:
                import json
                files_to_merge = json.loads(files_to_merge)
            except Exception:
                files_to_merge = [f.strip() for f in files_to_merge.split(",") if f.strip()]
        if not isinstance(files_to_merge, list) or len(files_to_merge) < 2:
            return jsonify({"error": "Debe seleccionar al menos 2 archivos para realizar la unión o concatenación"}), 400

        resolved_paths = []
        for fname in files_to_merge:
            fname = str(fname).strip()
            target = safe_download_path(fname)
            if not target or not os.path.exists(target):
                found = False
                if os.path.exists(DOWNLOAD_DIR):
                    for entry in os.listdir(DOWNLOAD_DIR):
                        if entry == fname or entry.endswith(fname):
                            cand = os.path.join(DOWNLOAD_DIR, entry)
                            if os.path.isfile(cand):
                                target = cand
                                found = True
                                break
                if not found or not target or not os.path.exists(target):
                    return jsonify({"error": f"Archivo '{fname}' no encontrado en el servidor"}), 404
            resolved_paths.append(target)

        target_fmt = (data.get("output_format") or "").strip().lower().lstrip(".")
        if not target_fmt:
            first_ext = os.path.splitext(resolved_paths[0])[1].lower().lstrip(".")
            target_fmt = first_ext if first_ext else "mp4"

        output_ext = target_fmt
        new_jid = uuid.uuid4().hex
        clean_base = f"union_{len(resolved_paths)}_archivos"
        out_filename = f"{new_jid}_{clean_base}.{output_ext}"
        out_path = os.path.join(DOWNLOAD_DIR, out_filename)

        import tempfile
        concat_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
        try:
            for p in resolved_paths:
                clean_p = os.path.abspath(p).replace("\\", "/").replace("'", "'\\''")
                concat_file.write(f"file '{clean_p}'\n")
            concat_file.close()

            args_copy = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file.name, "-c", "copy", out_path]
            proc = subprocess.run(args_copy, capture_output=True, text=True, timeout=300)
            if proc.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                if output_ext in ("mp3", "wav", "m4a", "flac", "ogg", "opus"):
                    args_trans = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file.name,
                                  "-c:a", "libmp3lame", "-b:a", "320k", out_path]
                else:
                    args_trans = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file.name,
                                  "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", out_path]
                proc = subprocess.run(args_trans, capture_output=True, text=True, timeout=300)

            if proc.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                err_msg = proc.stderr[-400:] if proc.stderr else "Error desconocido de concatenación FFmpeg"
                return jsonify({"error": f"Fallo al unir archivos: {err_msg}"}), 500

            file_size = os.path.getsize(out_path)
            from core.utils import save_downloads_meta
            meta = load_downloads_meta()
            meta[new_jid] = {
                "job_id": new_jid,
                "filename": f"{clean_base}.{output_ext}",
                "username": username,
                "size_bytes": file_size,
                "mtime": time.time(),
                "tool": "merge",
                "created_at_formatted": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source_files": files_to_merge,
            }
            save_downloads_meta(meta)

            return jsonify({
                "success": True,
                "job_id": new_jid,
                "filename": f"{clean_base}.{output_ext}",
                "size_formatted": format_bytes(file_size),
                "download_url": f"/api/files/{new_jid}",
                "message": f"¡{len(resolved_paths)} archivos unidos exitosamente!"
            })
        finally:
            if os.path.exists(concat_file.name):
                try:
                    os.remove(concat_file.name)
                except Exception:
                    pass

    uploaded_file = request.files.get("file")
    source_path = None

    if uploaded_file and uploaded_file.filename:
        safe_up_name = safe_download_path(uploaded_file.filename)
        if not safe_up_name:
            return jsonify({"error": "Nombre de archivo no válido"}), 400
        source_path = safe_up_name
        uploaded_file.save(source_path)
    elif source_filename:
        target = safe_download_path(source_filename)
        if not target or not os.path.exists(target):
            found = False
            if os.path.exists(DOWNLOAD_DIR):
                for entry in os.listdir(DOWNLOAD_DIR):
                    if entry == source_filename or entry.endswith(source_filename):
                        cand = os.path.join(DOWNLOAD_DIR, entry)
                        if os.path.isfile(cand):
                            target = cand
                            found = True
                            break
            if not found or not target or not os.path.exists(target):
                return jsonify({"error": f"Archivo '{source_filename}' no encontrado en el servidor"}), 404
        source_path = target
    else:
        return jsonify({"error": "Debe seleccionar un archivo de origen o subir uno nuevo"}), 400

    base_name, orig_ext = os.path.splitext(os.path.basename(source_path))
    clean_base = re.sub(r'^[a-f0-9]{32}_?', '', base_name)
    if not clean_base:
        clean_base = "media"

    output_ext = orig_ext.lstrip(".")
    ffmpeg_args = ["ffmpeg", "-y", "-i", source_path]

    if tool == "convert":
        target_format = data.get("target_format", "mp4").lower().strip(".")
        output_ext = target_format
        if target_format in ("mp3", "flac", "wav", "aac", "m4a", "opus", "ogg"):
            ffmpeg_args.extend(["-vn"])
            if target_format == "mp3":
                bitrate = data.get("audio_bitrate", "320k")
                ffmpeg_args.extend(["-c:a", "libmp3lame", "-b:a", bitrate])
            elif target_format == "flac":
                ffmpeg_args.extend(["-c:a", "flac"])
            elif target_format == "wav":
                ffmpeg_args.extend(["-c:a", "pcm_s16le"])
            elif target_format == "m4a":
                ffmpeg_args.extend(["-c:a", "aac", "-b:a", "256k"])
            elif target_format == "opus":
                ffmpeg_args.extend(["-c:a", "libopus", "-b:a", "192k"])
            elif target_format == "ogg":
                ffmpeg_args.extend(["-c:a", "libvorbis", "-q:a", "6"])
        elif target_format == "gif":
            start = data.get("start_time", "00:00:00")
            dur = data.get("duration", "5")
            ffmpeg_args = ["ffmpeg", "-y", "-ss", start, "-t", str(dur), "-i", source_path,
                           "-vf", "fps=12,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                           "-loop", "0"]
        else:
            if target_format == "mp4":
                ffmpeg_args.extend(["-c:v", "libx264", "-c:a", "aac", "-preset", "medium", "-crf", "22"])
            elif target_format == "mkv":
                ffmpeg_args.extend(["-c:v", "libx264", "-c:a", "aac"])
            elif target_format == "webm":
                ffmpeg_args.extend(["-c:v", "libvpx-vp9", "-c:a", "libopus"])
            elif target_format == "avi":
                ffmpeg_args.extend(["-c:v", "libxvid", "-c:a", "mp3"])

    elif tool == "compress":
        profile = data.get("profile", "whatsapp_16")
        output_ext = "mp4"
        if profile == "whatsapp_16":
            ffmpeg_args.extend(["-c:v", "libx264", "-preset", "slow", "-crf", "28", "-vf", "scale=-2:720", "-c:a", "aac", "-b:a", "96k"])
        elif profile == "whatsapp_25":
            ffmpeg_args.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "26", "-vf", "scale=-2:1080", "-c:a", "aac", "-b:a", "128k"])
        elif profile == "discord":
            ffmpeg_args.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "25", "-c:a", "aac", "-b:a", "128k"])
        else:
            crf = str(data.get("crf", "24"))
            ffmpeg_args.extend(["-c:v", "libx264", "-preset", "medium", "-crf", crf, "-c:a", "aac", "-b:a", "128k"])

    elif tool == "trim":
        start_time = data.get("start_time", "").strip()
        end_time = data.get("end_time", "").strip()
        extract_audio = bool(data.get("extract_audio", False))

        args = ["ffmpeg", "-y"]
        if start_time:
            args.extend(["-ss", start_time])
        args.extend(["-i", source_path])
        if end_time:
            args.extend(["-to", end_time])

        if extract_audio:
            output_ext = "mp3"
            args.extend(["-vn", "-c:a", "libmp3lame", "-b:a", "320k"])
        else:
            args.extend(["-c", "copy"])
        ffmpeg_args = args

    elif tool == "normalize":
        output_ext = "mp3" if orig_ext.lower() in (".mp3", ".wav", ".flac", ".m4a", ".ogg") else orig_ext.lstrip(".")
        if output_ext == "mp3":
            ffmpeg_args.extend(["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "libmp3lame", "-b:a", "320k"])
        else:
            ffmpeg_args.extend(["-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k"])

    new_jid = uuid.uuid4().hex
    out_filename = f"{new_jid}_{clean_base}_{tool}.{output_ext}"
    out_path = os.path.join(DOWNLOAD_DIR, out_filename)
    ffmpeg_args.append(out_path)

    try:
        proc = subprocess.run(ffmpeg_args, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0 or not os.path.exists(out_path):
            err_msg = proc.stderr[-400:] if proc.stderr else "Error desconocido de FFmpeg"
            return jsonify({"error": f"Fallo al procesar con FFmpeg: {err_msg}"}), 500

        file_size = os.path.getsize(out_path)
        from core.utils import save_downloads_meta
        meta = load_downloads_meta()
        meta[new_jid] = {
            "job_id": new_jid,
            "filename": f"{clean_base}_{tool}.{output_ext}",
            "username": username,
            "size_bytes": file_size,
            "mtime": time.time(),
            "tool": tool,
            "created_at_formatted": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_file": source_filename,
        }
        save_downloads_meta(meta)

        return jsonify({
            "success": True,
            "job_id": new_jid,
            "filename": f"{clean_base}_{tool}.{output_ext}",
            "size_formatted": format_bytes(file_size),
            "download_url": f"/api/files/{new_jid}",
            "message": "Archivo procesado exitosamente en Estudio Multimedia."
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "El procesamiento excedió el límite de tiempo de 5 minutos"}), 504
    except Exception as e:
        return jsonify({"error": f"Error inesperado: {str(e)}"}), 500


