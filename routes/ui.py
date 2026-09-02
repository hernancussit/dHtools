import os
import zipfile
import shutil
from flask import Blueprint, render_template, request, send_file, jsonify, Response, current_app, abort

from core.config import APP_VERSION, DOWNLOAD_DIR
from core.state import JOBS_LOCK, JOBS
from core.utils import (
    load_config, get_disk_status, load_downloads_meta, save_downloads_meta,
    format_bytes, safe_download_path, delete_download_meta, safe_filename
)
from core.downloader import purge_downloads, get_ytdlp_version
from routes.auth import require_admin

ui_bp = Blueprint("ui_bp", __name__)

@ui_bp.route("/robots.txt")
def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@ui_bp.route("/")
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


@ui_bp.route("/manifest.json")
def manifest():
    return send_file(os.path.join(current_app.root_path, "static", "manifest.json"), mimetype="application/manifest+json")


@ui_bp.route("/sw.js")
def service_worker():
    return send_file(os.path.join(current_app.root_path, "static", "sw.js"), mimetype="application/javascript")


@ui_bp.route("/favicon.ico")
def favicon_ico():
    return send_file(os.path.join(current_app.root_path, "static", "favicon.ico"), mimetype="image/x-icon")



@ui_bp.route("/api/version")
def api_version():
    return jsonify({
        "app_version": APP_VERSION,
        "ytdlp_version": get_ytdlp_version(),
    })


@ui_bp.route("/api/disk-status")
def api_disk_status():
    return jsonify(get_disk_status())


@ui_bp.route("/api/cleanup", methods=["POST"])
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


@ui_bp.route("/api/recent-downloads")
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
            if not os.path.isfile(entry_path):
                continue
            try:
                stat = os.stat(entry_path)

                matched_jid = None
                item_meta = None
                clean_name = entry

                # 1. Match against registered meta items
                for jid, info in meta.items():
                    if entry.startswith(f"{jid}_"):
                        matched_jid = jid
                        item_meta = info
                        clean_name = entry[len(jid) + 1:]
                        break
                    elif entry == jid or entry == f"{jid}.zip":
                        matched_jid = jid
                        item_meta = info
                        clean_name = info.get("filename", entry)
                        break

                # 2. Fallback prefix split
                if not matched_jid:
                    parts = entry.split("_", 1)
                    matched_jid = parts[0].replace(".zip", "")
                    clean_name = parts[1] if len(parts) > 1 else entry
                    item_meta = meta.get(matched_jid, {})

                folder_name = (item_meta or {}).get("folder_name")
                group_id = (item_meta or {}).get("group_id")

                # If entry is an auto-generated whole-folder zip, skip duplicate display
                if entry.startswith("folder_") and entry.endswith(".zip"):
                    continue

                item_owner = (item_meta or {}).get("username")
                if not item_owner:
                    with JOBS_LOCK:
                        job = JOBS.get(matched_jid)
                        if job:
                            item_owner = job.get("owner")
                if not item_owner:
                    item_owner = "admin"

                if not show_all and item_owner != username and not (is_admin and item_owner in ("admin", username)):
                    continue

                item_obj = {
                    "job_id": matched_jid,
                    "filename": clean_name,
                    "size_bytes": stat.st_size,
                    "size_formatted": format_bytes(stat.st_size),
                    "mtime": stat.st_mtime,
                    "owner": item_owner,
                    "download_url": f"/api/files/{matched_jid}",
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


@ui_bp.route("/api/my-downloads/folder/<group_id>", methods=["DELETE"])
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


@ui_bp.route("/api/my-downloads/folder-zip/<group_id>")
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
        with JOBS_LOCK:
            matching_jids = {
                jid: job for jid, job in JOBS.items()
                if job.get("group_id") == group_id and (is_admin or job.get("owner") == username)
            }

    if not matching_jids:
        abort(404)

    folder_name = next(iter(matching_jids.values())).get("folder_name", f"folder_{group_id[:8]}")
    safe_f_name = safe_filename(folder_name) or f"coleccion_{group_id[:8]}"
    zip_path = os.path.join(DOWNLOAD_DIR, f"folder_{group_id}.zip")

    # If already generated and valid, return immediately
    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 100:
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f"{safe_f_name}.zip",
            mimetype="application/zip",
        )

    # Collect unique individual files
    files_to_zip = []
    if os.path.exists(DOWNLOAD_DIR):
        for jid in matching_jids:
            for entry in os.listdir(DOWNLOAD_DIR):
                if entry.startswith(jid) and not entry.lower().endswith(".zip"):
                    fpath = os.path.join(DOWNLOAD_DIR, entry)
                    if os.path.isfile(fpath):
                        disp_name = entry[len(jid):].lstrip("_-") or entry
                        files_to_zip.append((fpath, disp_name))

    if not files_to_zip:
        # Check if a pre-existing zip for this group is in DOWNLOAD_DIR
        for entry in os.listdir(DOWNLOAD_DIR):
            if group_id in entry and entry.lower().endswith(".zip"):
                return send_file(
                    os.path.join(DOWNLOAD_DIR, entry),
                    as_attachment=True,
                    download_name=f"{safe_f_name}.zip",
                    mimetype="application/zip",
                )
        abort(404)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath, arcname in files_to_zip:
            if os.path.exists(fpath):
                zf.write(fpath, arcname=arcname)

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"{safe_f_name}.zip",
        mimetype="application/zip",
    )


@ui_bp.route("/api/my-downloads/<job_id>", methods=["DELETE"])
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


@ui_bp.route("/api/my-downloads/cleanup", methods=["POST"])
def cleanup_my_downloads():
    user = getattr(request, "current_user", {}) or {}
    username = user.get("username", "admin")
    is_admin = (user.get("role") == "admin")

    meta = load_downloads_meta()
    cleaned_count = 0
    reclaimed_bytes = 0

    if os.path.exists(DOWNLOAD_DIR):
        if is_admin:
            for entry in os.listdir(DOWNLOAD_DIR):
                if entry == ".gitkeep":
                    continue
                fpath = os.path.join(DOWNLOAD_DIR, entry)
                try:
                    if os.path.isdir(fpath):
                        for root, _, files in os.walk(fpath):
                            for f in files:
                                reclaimed_bytes += os.path.getsize(os.path.join(root, f))
                        shutil.rmtree(fpath, ignore_errors=True)
                    else:
                        reclaimed_bytes += os.path.getsize(fpath)
                        os.remove(fpath)
                    cleaned_count += 1
                except Exception:
                    pass
            for jid in list(meta.keys()):
                delete_download_meta(jid)
            with JOBS_LOCK:
                JOBS.clear()
        else:
            user_job_ids = [jid for jid, info in meta.items() if info.get("username") == username]
            for jid in user_job_ids:
                for entry in os.listdir(DOWNLOAD_DIR):
                    if entry.startswith(jid):
                        fpath = os.path.join(DOWNLOAD_DIR, entry)
                        try:
                            reclaimed_bytes += os.path.getsize(fpath)
                            os.remove(fpath)
                            cleaned_count += 1
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
