import os
from flask import Blueprint, render_template, request, send_file, jsonify
from core.config import APP_VERSION
from core.utils import load_config, get_disk_status
from routes.auth import require_admin

ui_bp = Blueprint('ui_bp', __name__)


def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")



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



def manifest():
    return send_file(os.path.join(app.root_path, "static", "manifest.json"), mimetype="application/manifest+json")



def service_worker():
    return send_file(os.path.join(app.root_path, "static", "sw.js"), mimetype="application/javascript")



def api_version():
    return jsonify({
        "app_version": APP_VERSION,
        "ytdlp_version": get_ytdlp_version(),
    })



def api_disk_status():
    return jsonify(get_disk_status())



def api_cleanup():
    res = purge_downloads(force_all=False)
    disk = get_disk_status()
    return jsonify({
        "success": True,
        "cleaned_count": res["cleaned_count"],
        "reclaimed_formatted": res["reclaimed_formatted"],
        "disk": disk,
    })



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


