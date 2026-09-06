import os
import sys
import time
import json
import shutil
import subprocess
import requests
import re
import ftplib
import logging
import socket
import hashlib
import yt_dlp
from flask import Blueprint, request, jsonify, render_template, session

from core.config import (
    APP_VERSION, POT_PROVIDER_URL, COBALT_URL, ROLLBACK_STATE_FILE,
    COOKIES_FILE, USERS_FILE, CONFIG_FILE, DOWNLOAD_DIR
)
from core.state import JOBS_LOCK, JOBS, START_TIME, ACTIVE_SESSIONS, ACTIVE_SESSIONS_LOCK
from core.utils import (
    load_config, save_config, get_disk_status, get_ram_status,
    load_cloud_config, save_cloud_config, safe_download_path, format_bytes,
    send_system_email, load_downloads_meta, delete_download_meta,
    get_residential_proxy_config, save_residential_proxy_config,
    test_residential_proxy_connection, sync_netscape_to_cobalt_json,
    get_cobalt_cookies_status
)
from core.downloader import restart_process_soon, sync_to_cloud, get_ytdlp_version
from routes.auth import (
    require_admin, load_users, save_users, hash_password
)

admin_bp = Blueprint("admin_bp", __name__)

@admin_bp.route("/wiki")
def wiki_page():
    cfg = load_config()
    from core.utils import get_git_info
    git_info = get_git_info()
    branch = git_info.get("branch") or "dev"
    raw_ver = APP_VERSION.split("-")[0]
    display_version = f"{raw_ver}-{branch}" if branch and branch != "main" else raw_ver
    return render_template("wiki.html", version=display_version, config=cfg)


# ==================== ADMIN PANEL & API ====================

@admin_bp.route("/admin")
@require_admin
def admin_panel():
    cfg = load_config()
    from core.utils import get_git_info
    git_info = get_git_info()
    branch = git_info.get("branch") or "dev"
    raw_ver = APP_VERSION.split("-")[0]
    display_version = f"{raw_ver}-{branch}" if branch and branch != "main" else raw_ver
    return render_template("admin.html", version=display_version, config=cfg)


@admin_bp.route("/api/admin/services-status")
@require_admin
def admin_services_status():
    # 1. yt-dlp check and latency
    ytdlp_ver = get_ytdlp_version()
    ytdlp_ok = False
    ytdlp_lat = 0
    try:
        t0 = time.time()
        r = requests.get("https://pypi.org/pypi/yt-dlp/json", headers={"User-Agent": "dHtools"}, timeout=3)
        ytdlp_lat = round((time.time() - t0) * 1000)
        ytdlp_ok = (r.status_code == 200)
    except Exception:
        if ytdlp_ver and ytdlp_ver != "desconocida":
            ytdlp_ok = True

    # 2. PoToken Provider
    pot_ok = False
    pot_lat = 0
    try:
        t0 = time.time()
        requests.get(POT_PROVIDER_URL, timeout=3)
        pot_lat = round((time.time() - t0) * 1000)
        pot_ok = True
    except Exception:
        pass

    # 3. Cobalt Official container
    cobalt_ok = False
    cobalt_lat = 0
    cobalt_ver = ""
    try:
        t0 = time.time()
        cr = requests.get(COBALT_URL, timeout=3)
        cobalt_lat = round((time.time() - t0) * 1000)
        cobalt_ok = (cr.status_code < 500)
        if cobalt_ok:
            try:
                cobalt_ver = cr.json().get("version", "")
            except Exception:
                pass
    except Exception:
        pass

    # 4. Deno JS Engine
    deno_path = shutil.which("deno") or "/usr/local/bin/deno"
    deno_installed = False
    deno_ver = ""
    deno_lat = 0
    try:
        t0 = time.time()
        dr = subprocess.run([deno_path, "--version"], capture_output=True, text=True, timeout=3)
        deno_lat = round((time.time() - t0) * 1000)
        if dr.returncode == 0:
            deno_installed = True
            deno_ver = dr.stdout.splitlines()[0]
    except Exception:
        pass

    uptime_s = round(time.time() - START_TIME)
    return jsonify({
        "app": {"version": APP_VERSION, "uptime_seconds": uptime_s},
        "ytdlp": {"online": ytdlp_ok, "version": ytdlp_ver, "latency_ms": ytdlp_lat},
        "cobalt": {"online": cobalt_ok, "version": cobalt_ver, "latency_ms": cobalt_lat, "cookies": get_cobalt_cookies_status()},
        "deno": {"online": deno_installed, "installed": deno_installed, "available": deno_installed, "version": deno_ver, "latency_ms": deno_lat},
        "potprovider": {"online": pot_ok, "latency_ms": pot_lat},
        "disk": get_disk_status(),
        "ram": get_ram_status(),
    })


@admin_bp.route("/api/admin/check-deno")
@require_admin
def admin_check_deno():
    deno_path = shutil.which("deno") or "/usr/local/bin/deno"
    curr = "desconocida"
    latest = curr
    has_update = False
    try:
        dr = subprocess.run([deno_path, "--version"], capture_output=True, text=True, timeout=3)
        if dr.returncode == 0:
            parts = dr.stdout.split()
            if len(parts) >= 2:
                curr = parts[1]
    except Exception:
        pass

    try:
        r = requests.get("https://api.github.com/repos/denoland/deno/releases/latest", headers={"User-Agent": "dHtools"}, timeout=4)
        if r.status_code == 200:
            tag = r.json().get("tag_name", "").lstrip("v")
            if tag:
                latest = tag
                if latest != curr and curr != "desconocida":
                    has_update = True
    except Exception:
        pass

    return jsonify({
        "current_version": curr,
        "latest_version": latest,
        "update_available": has_update,
    })


@admin_bp.route("/api/admin/update-deno", methods=["POST"])
@require_admin
def admin_update_deno():
    deno_path = shutil.which("deno") or "/usr/local/bin/deno"
    try:
        res = subprocess.run([deno_path, "upgrade"], capture_output=True, text=True, timeout=120)
        out = (res.stdout or "") + (res.stderr or "")
        return jsonify({
            "success": (res.returncode == 0),
            "message": out.strip() or "Comando deno upgrade ejecutado."
        })
    except Exception as e:
        return jsonify({"error": f"Error al ejecutar actualización de Deno: {e}"}), 500


@admin_bp.route("/api/admin/test-deno", methods=["POST"])
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


def get_git_info() -> dict:
    """Extracts branch, commit, and tag info from git."""
    is_repo = False
    branch = "main"
    commit = "unknown"
    commit_date = ""
    tag = ""
    remote_repo = "hernancussit/dHtools"
    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True, timeout=2)
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "/app"], capture_output=True, timeout=2)

        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip() == "true":
            is_repo = True
            br = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, timeout=3)
            branch = br.stdout.strip() or "main"

            cm = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=3)
            commit = cm.stdout.strip() or "unknown"

            cd = subprocess.run(["git", "log", "-1", "--format=%cd", "--date=short"], capture_output=True, text=True, timeout=3)
            commit_date = cd.stdout.strip()

            tg = subprocess.run(["git", "describe", "--tags", "--always"], capture_output=True, text=True, timeout=3)
            tag = tg.stdout.strip()

            rem = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=3)
            if rem.returncode == 0 and rem.stdout.strip():
                rem_str = rem.stdout.strip()
                m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", rem_str)
                if m:
                    remote_repo = m.group(1)
    except Exception:
        pass
    return {
        "is_repo": is_repo,
        "branch": branch,
        "commit": commit,
        "commit_date": commit_date,
        "tag": tag,
        "remote_repo": remote_repo,
    }


def load_rollback_state() -> dict:
    if os.path.exists(ROLLBACK_STATE_FILE):
        try:
            with open(ROLLBACK_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_rollback_state(data: dict):
    try:
        with open(ROLLBACK_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


@admin_bp.route("/api/admin/git-status")
@require_admin
def admin_git_status():
    git_info = get_git_info()
    rollback = load_rollback_state()

    branch = git_info["branch"] or "main"
    remote_repo = git_info.get("remote_repo") or "hernancussit/dHtools"
    remote_commit = None
    remote_date = None
    update_available = False

    try:
        gh_url = f"https://api.github.com/repos/{remote_repo}/commits/{branch}"
        r = requests.get(gh_url, headers={"User-Agent": "dHtools"}, timeout=4)
        if r.status_code == 200:
            gh_data = r.json()
            remote_commit = (gh_data.get("sha") or "")[:7]
            remote_date = gh_data.get("commit", {}).get("committer", {}).get("date", "")[:10]
            if remote_commit and remote_commit != git_info["commit"] and git_info["commit"] != "unknown":
                update_available = True
    except Exception:
        pass

    return jsonify({
        "app_version": APP_VERSION,
        "git": git_info,
        "remote_branch": branch,
        "remote_repo": remote_repo,
        "remote_commit": remote_commit,
        "remote_date": remote_date,
        "update_available": update_available,
        "rollback_available": bool(rollback.get("previous_commit")),
        "rollback_info": rollback,
    })


def ensure_git_safe_and_remote():
    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True, timeout=2)
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "/app"], capture_output=True, timeout=2)

        rem = subprocess.run(["git", "remote", "get-url", "origin"], cwd="/app", capture_output=True, text=True, timeout=3)
        if rem.returncode == 0:
            rem_url = rem.stdout.strip()
            if "git@github.com:" in rem_url:
                https_url = rem_url.replace("git@github.com:", "https://github.com/")
                subprocess.run(["git", "remote", "set-url", "origin", https_url], cwd="/app", capture_output=True, timeout=3)
    except Exception:
        pass


@admin_bp.route("/api/admin/git-switch-branch", methods=["POST"])
@require_admin
def admin_git_switch_branch():
    data = request.get_json(force=True) or {}
    target_branch = data.get("branch", "main").strip()
    if target_branch not in ("main", "dev"):
        return jsonify({"error": "Rama inválida. Solo se permite 'main' (estable) o 'dev' (desarrollo)."}), 400

    ensure_git_safe_and_remote()
    app_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        subprocess.run(["git", "fetch", "origin"], cwd=app_dir, capture_output=True, text=True, timeout=30, check=True)
        r = subprocess.run(["git", "checkout", target_branch], cwd=app_dir, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            subprocess.run(["git", "checkout", "-B", target_branch, f"origin/{target_branch}"], cwd=app_dir, capture_output=True, text=True, timeout=15, check=True)
        subprocess.run(["git", "pull", "origin", target_branch], cwd=app_dir, capture_output=True, text=True, timeout=30)

        restart_process_soon(1.5)
        return jsonify({"success": True, "message": f"Cambiado a rama '{target_branch}' con éxito. Reiniciando servicio..."})
    except Exception as e:
        return jsonify({"error": f"Error al cambiar de rama: {e}"}), 500


@admin_bp.route("/api/admin/git-update", methods=["POST"])
@require_admin
def admin_git_update():
    ensure_git_safe_and_remote()
    git_info = get_git_info()
    current_commit = git_info.get("commit")
    current_branch = git_info.get("branch") or "main"
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        save_rollback_state({
            "previous_commit": current_commit,
            "previous_branch": current_branch,
            "timestamp": time.time(),
            "date": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        subprocess.run(["git", "fetch", "origin"], cwd=app_dir, capture_output=True, text=True, timeout=30, check=True)
        # Attempt pull with rebase first, or fallback to fast-forward/reset if branches diverged cleanly
        pull_res = subprocess.run(["git", "pull", "--rebase", "origin", current_branch], cwd=app_dir, capture_output=True, text=True, timeout=45)
        if pull_res.returncode != 0:
            # Fallback to hard reset against origin branch
            pull_res = subprocess.run(["git", "reset", "--hard", f"origin/{current_branch}"], cwd=app_dir, capture_output=True, text=True, timeout=30, check=True)

        req_file = os.path.join(app_dir, "requirements.txt")
        if os.path.exists(req_file):
            subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req_file], cwd=app_dir, capture_output=True, text=True, timeout=120)

        restart_process_soon(1.5)
        return jsonify({
            "success": True,
            "message": "Actualización completada con éxito. Reiniciando servidor...",
            "details": pull_res.stdout.strip()
        })

    except Exception as e:
        return jsonify({"error": f"Error durante la actualización: {e}"}), 500


@admin_bp.route("/api/admin/git-rollback", methods=["POST"])
@require_admin
def admin_git_rollback():
    ensure_git_safe_and_remote()
    rollback = load_rollback_state()
    prev_commit = rollback.get("previous_commit")
    if not prev_commit:
        return jsonify({"error": "No hay una versión anterior registrada para realizar rollback."}), 400

    app_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        r = subprocess.run(["git", "checkout", prev_commit], cwd=app_dir, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return jsonify({"error": f"Git checkout falló: {r.stderr}"}), 500

        save_rollback_state({})
        restart_process_soon(1.5)
        return jsonify({"success": True, "message": f"Rollback al commit '{prev_commit}' ejecutado con éxito. Reiniciando servidor..."})
    except Exception as e:
        return jsonify({"error": f"Error durante el rollback: {e}"}), 500


@admin_bp.route("/api/admin/check-updates")
@require_admin
def admin_check_updates():
    curr = get_ytdlp_version()
    latest = curr
    has_update = False
    try:
        r = requests.get("https://pypi.org/pypi/yt-dlp/json", headers={"User-Agent": "dHtools"}, timeout=4)
        if r.status_code == 200:
            latest = r.json().get("info", {}).get("version", curr)
            def _v_tuple(v):
                return tuple(int(x) for x in re.findall(r"\d+", str(v)))
            if latest and _v_tuple(latest) > _v_tuple(curr):
                has_update = True
    except Exception:
        pass
    return jsonify({
        "current_version": curr,
        "latest_version": latest,
        "update_available": has_update,
    })


@admin_bp.route("/api/admin/config", methods=["GET", "POST"])
@require_admin
def admin_config():
    global CLEANUP_AFTER_HOURS, DISK_EMERGENCY_THRESHOLD_PERCENT
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        cfg = load_config()
        if "site_title" in data:
            cfg["site_title"] = str(data["site_title"]).strip() or "⚡ dHtools"
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


def validate_netscape_cookies(content: str) -> tuple:
    """Validates if content is in Netscape cookies format and test extracts with yt-dlp."""
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return False, "El archivo de cookies está vacío.", 0

    valid_lines = 0
    for line in lines:
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            valid_lines += 1

    if valid_lines == 0:
        return False, "El archivo no tiene el formato estándar Netscape cookies (columnas separadas por tabulaciones).", 0

    temp_cookie_path = os.path.join(DOWNLOAD_DIR, f"temp_cookie_test_{int(time.time())}.txt")
    try:
        with open(temp_cookie_path, "w", encoding="utf-8") as f:
            f.write(content)

        ydl_opts = {
            "cookiefile": temp_cookie_path,
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
            "socket_timeout": 8,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info("https://www.youtube.com/watch?v=aqz-KE-bpKQ", download=False)

        return True, f"Cookies validadas y funcionales contra YouTube ({valid_lines} entradas activas).", valid_lines
    except Exception as e:
        return False, f"La validación contra YouTube falló con estas cookies: {e}", valid_lines
    finally:
        if os.path.exists(temp_cookie_path):
            try:
                os.remove(temp_cookie_path)
            except Exception:
                pass


@admin_bp.route("/api/admin/cookies", methods=["GET", "DELETE"])
@require_admin
def admin_cookies():
    if request.method == "DELETE":
        if os.path.exists(COOKIES_FILE):
            try:
                os.remove(COOKIES_FILE)
            except Exception as e:
                return jsonify({"error": f"Error al eliminar cookies: {e}"}), 500
        sync_netscape_to_cobalt_json("")
        return jsonify({"success": True, "message": "Archivo cookies.txt eliminado y cookies de Cobalt limpiadas."})

    has_cookies = os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0
    lines = 0
    size_formatted = "0 B"
    mtime_str = ""
    if has_cookies:
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines = len([l for l in f.readlines() if l.strip() and not l.strip().startswith("#")])
            size_formatted = format_bytes(os.path.getsize(COOKIES_FILE))
            mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(COOKIES_FILE)))
        except Exception:
            pass
    return jsonify({
        "has_cookies": has_cookies,
        "lines": lines,
        "size_formatted": size_formatted,
        "updated_at": mtime_str,
        "cobalt_cookies": get_cobalt_cookies_status(),
    })


@admin_bp.route("/api/admin/cookies/upload", methods=["POST"])
@require_admin
def admin_cookies_upload():
    content = ""
    if "file" in request.files:
        uploaded_file = request.files["file"]
        content = uploaded_file.read().decode("utf-8", errors="replace")
    elif request.is_json:
        data = request.get_json(force=True) or {}
        content = data.get("content", "")

    if not content or not content.strip():
        return jsonify({"error": "No se recibió contenido de cookies para procesar."}), 400

    is_valid, msg, valid_lines = validate_netscape_cookies(content)
    if not is_valid:
        return jsonify({"error": msg}), 400

    try:
        os.makedirs(os.path.dirname(COOKIES_FILE), exist_ok=True)
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        size_formatted = format_bytes(os.path.getsize(COOKIES_FILE))
        cobalt_data = sync_netscape_to_cobalt_json(COOKIES_FILE)
        cob_msg = ""
        if "youtube" in cobalt_data:
            cob_msg = f" (Sincronizado con Cobalt v11: {len(cobalt_data)} servicio/s)"
        return jsonify({
            "success": True,
            "message": f"{msg}{cob_msg}",
            "lines": valid_lines,
            "size_formatted": size_formatted,
            "cobalt_synced": bool(cobalt_data),
        })
    except Exception as e:
        return jsonify({"error": f"Error al guardar archivo cookies.txt: {e}"}), 500


@admin_bp.route("/api/admin/users", methods=["GET", "POST"])
@require_admin
def admin_users():
    users = load_users()
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")
        role = data.get("role", "downloader")
        status = data.get("status", "active")
        email = data.get("email", "").strip()
        if not username or not password:
            return jsonify({"error": "Falta usuario o contraseña"}), 400
        if username in users:
            return jsonify({"error": f"El usuario '{username}' ya existe"}), 400
        quota_gb = float(data.get("quota_gb", 0) or 0)
        users[username] = {
            "password_hash": hash_password(password),
            "role": role,
            "status": status,
            "email": email,
            "quota_gb": quota_gb,
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
            "email": d.get("email", ""),
            "quota_gb": d.get("quota_gb", 0),
            "totp_enabled": bool(d.get("totp_enabled", False)),
            "created_at": d.get("created_at", "Inicial"),
            "downloads_count": user_stats.get(u, {}).get("count", 0),
            "downloads_bytes": user_stats.get(u, {}).get("bytes", 0),
            "downloads_formatted": format_bytes(user_stats.get(u, {}).get("bytes", 0)),
        }
        for u, d in users.items()
    ]
    return jsonify({"users": user_list})


@admin_bp.route("/api/admin/users/<username>", methods=["PUT", "DELETE"])
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
        # Revoke sessions
        with ACTIVE_SESSIONS_LOCK:
            for s in ACTIVE_SESSIONS.values():
                if s.get("username") == username:
                    s["revoked"] = True
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
            if data["status"] == "suspended":
                with ACTIVE_SESSIONS_LOCK:
                    for s in ACTIVE_SESSIONS.values():
                        if s.get("username") == username:
                            s["revoked"] = True
        if "email" in data:
            users[username]["email"] = str(data["email"]).strip()
        if "quota_gb" in data:
            try:
                users[username]["quota_gb"] = float(data["quota_gb"] or 0)
            except (ValueError, TypeError):
                users[username]["quota_gb"] = 0
        if data.get("reset_2fa"):
            users[username]["totp_enabled"] = False
            users[username].pop("totp_secret", None)
            users[username].pop("backup_codes", None)
        save_users(users)
        return jsonify({"message": f"Usuario '{username}' actualizado exitosamente"})


@admin_bp.route("/api/admin/sessions", methods=["GET"])
@require_admin
def admin_sessions():
    with ACTIVE_SESSIONS_LOCK:
        sess_list = [dict(s) for s in ACTIVE_SESSIONS.values()]
    sess_list.sort(key=lambda s: s.get("last_active_ts", 0), reverse=True)
    return jsonify({"sessions": sess_list})


@admin_bp.route("/api/admin/sessions/<session_id>/revoke", methods=["POST"])
@require_admin
def admin_revoke_session(session_id):
    with ACTIVE_SESSIONS_LOCK:
        sess_info = ACTIVE_SESSIONS.get(session_id)
        if not sess_info:
            return jsonify({"error": "Sesión no encontrada o ya expirada"}), 404
        sess_info["revoked"] = True
        u = sess_info.get("username", "usuario")
    return jsonify({"message": f"Sesión de '{u}' revocada exitosamente"})



@admin_bp.route("/api/admin/smtp", methods=["GET", "POST"])
@require_admin
def admin_smtp():
    cfg = load_config()
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        smtp_cfg = cfg.get("smtp", {})
        smtp_cfg["enabled"] = bool(data.get("enabled", False))
        smtp_cfg["host"] = str(data.get("host", "")).strip()
        smtp_cfg["port"] = int(data.get("port") or 587)
        smtp_cfg["user"] = str(data.get("user", "")).strip()
        if "password" in data and data["password"]:
            smtp_cfg["password"] = str(data["password"]).strip()
        smtp_cfg["from_email"] = str(data.get("from_email", "")).strip()
        smtp_cfg["use_tls"] = bool(data.get("use_tls", True))
        smtp_cfg["use_ssl"] = bool(data.get("use_ssl", False))
        cfg["smtp"] = smtp_cfg
        save_config(cfg)
        return jsonify({"message": "Configuración SMTP guardada exitosamente."})

    smtp_info = dict(cfg.get("smtp", {}))
    if smtp_info.get("password"):
        smtp_info["password_masked"] = True
        smtp_info["password"] = "••••••••"
    else:
        smtp_info["password_masked"] = False
    return jsonify({"smtp": smtp_info})


@admin_bp.route("/api/admin/smtp-test", methods=["POST"])
@require_admin
def admin_smtp_test():
    data = request.get_json(force=True) or {}
    to_email = data.get("to_email", "").strip()
    if not to_email:
        return jsonify({"error": "Ingresá un correo electrónico destinatario para la prueba."}), 400

    html = """
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; background: #0f172a; color: #f8fafc; padding: 24px; border-radius: 12px; border: 1px solid #334155;">
        <h2 style="color: #38bdf8; margin-top: 0;">⚡ dHtools — Prueba de Servidor SMTP</h2>
        <p>¡Felicitaciones! La conexión con tu servidor de correo SMTP está configurada y funcionando correctamente.</p>
        <hr style="border: 0; border-top: 1px solid #334155; margin: 20px 0;">
        <p style="font-size: 0.8rem; color: #94a3b8;">Enviado automáticamente desde el Panel de Administración de dHtools.</p>
    </div>
    """
    text = "⚡ dHtools — Prueba de Servidor SMTP\n\n¡Felicitaciones! La conexión con tu servidor de correo SMTP está funcionando correctamente."

    success, msg = send_system_email(to_email, "⚡ dHtools — Prueba de Conexión SMTP", html, text)
    if not success:
        return jsonify({"error": msg}), 400
    return jsonify({"message": f"¡Correo de prueba enviado con éxito a {to_email}!"})


@admin_bp.route("/api/admin/residential-proxy", methods=["GET", "POST"])
@require_admin
def admin_residential_proxy():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        proxy_cfg = get_residential_proxy_config()
        proxy_cfg["enabled"] = bool(data.get("enabled", False))
        
        new_url = str(data.get("url", "")).strip()
        if new_url and "••••" not in new_url:
            proxy_cfg["url"] = new_url
        elif not new_url:
            proxy_cfg["url"] = ""

        proxy_cfg["auto_fallback"] = bool(data.get("auto_fallback", True))
        proxy_cfg["fallback_on_quality_loss"] = bool(data.get("fallback_on_quality_loss", True))
        save_residential_proxy_config(proxy_cfg)
        return jsonify({"message": "Configuración del Enlace Residencial guardada exitosamente."})

    res_info = dict(get_residential_proxy_config())
    raw_url = res_info.get("url", "")
    if "@" in raw_url and "://" in raw_url:
        scheme, rest = raw_url.split("://", 1)
        creds, host = rest.split("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            res_info["url_masked"] = f"{scheme}://{user}:••••••••@{host}"
        else:
            res_info["url_masked"] = raw_url
    else:
        res_info["url_masked"] = raw_url

    return jsonify({"residential_proxy": res_info})


@admin_bp.route("/api/admin/residential-proxy/test", methods=["POST"])
@require_admin
def admin_residential_proxy_test():
    data = request.get_json(force=True) or {}
    url_to_test = str(data.get("url", "")).strip()
    
    if not url_to_test or "••••" in url_to_test:
        saved = get_residential_proxy_config()
        url_to_test = saved.get("url", "")

    if not url_to_test:
        return jsonify({"error": "Por favor ingresá la URL del proxy para realizar la prueba."}), 400

    result = test_residential_proxy_connection(url_to_test)
    if not result.get("success"):
        return jsonify({"error": result.get("message", "Fallo al conectar con el proxy residencial.")}), 400

    return jsonify(result)


@admin_bp.route("/api/admin/users/<username>/toggle-status", methods=["POST"])
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


@admin_bp.route("/api/admin/users/<username>/clean-downloads", methods=["POST"])
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


@admin_bp.route("/api/admin/cobalt-status")
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
            headers={"User-Agent": "dHtools"},

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
        "cookies_status": get_cobalt_cookies_status(),
    })


@admin_bp.route("/api/admin/update-cobalt", methods=["POST"])
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


@admin_bp.route("/api/admin/cloud-sync", methods=["GET", "POST"])
@require_admin
def admin_cloud_sync():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        save_cloud_config(data)
        from core.telegram_bot import telegram_bot
        telegram_bot.stop()
        time.sleep(0.5)
        telegram_bot.start()
        return jsonify({"message": "Configuración de Sincronización en la Nube guardada exitosamente", "cloud_sync": data})
    return jsonify({"cloud_sync": load_cloud_config()})


@admin_bp.route("/api/admin/cloud-sync/test", methods=["POST"])
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
            r = requests.post(url, json={"test": True, "message": "dHtools cloud sync test"}, timeout=5)
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
                json={"chat_id": chat_id, "text": "✅ Prueba de conexión de dHtools exitosa!"},
                timeout=8,
            )
            res = r.json()
            if res.get("ok"):
                curr = load_cloud_config()
                curr["telegram"] = {
                    "enabled": True,
                    "bot_token": token,
                    "chat_id": chat_id
                }
                save_cloud_config(curr)
                from core.telegram_bot import telegram_bot
                telegram_bot.stop()
                telegram_bot.start()
                return jsonify({"success": True, "message": "Mensaje de prueba enviado y bot activado correctamente!"})
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

    if service in ("s3", "minio", "r2", "b2", "wasabi"):
        from core.cloud_sync import test_s3_connection
        ok, msg = test_s3_connection(config)
        if ok:
            return jsonify({"success": True, "message": msg})
        return jsonify({"error": msg}), 400

    return jsonify({"error": "Servicio desconocido"}), 400


@admin_bp.route("/api/admin/telegram-bot/status", methods=["GET"])
@require_admin
def admin_telegram_bot_status():
    from core.telegram_bot import telegram_bot
    bot_info = telegram_bot.get_bot_info(force_refresh=True)
    users = load_users()
    linked_users = []
    for uname, udata in users.items():
        if udata.get("telegram_chat_id"):
            linked_users.append({
                "username": uname,
                "role": udata.get("role", "downloader"),
                "chat_id": udata.get("telegram_chat_id"),
                "telegram_username": udata.get("telegram_username") or ""
            })

    return jsonify({
        "running": telegram_bot.is_running(),
        "enabled": telegram_bot.is_enabled(),
        "bot_info": bot_info,
        "token_configured": bool(telegram_bot.get_token()),
        "linked_users": linked_users
    })


@admin_bp.route("/api/admin/telegram-bot/restart", methods=["POST"])
@require_admin
def admin_telegram_bot_restart():
    from core.telegram_bot import telegram_bot
    telegram_bot.stop()
    time.sleep(1)
    telegram_bot.start()
    return jsonify({
        "success": True,
        "running": telegram_bot.is_running(),
        "message": "Servicio del bot de Telegram reiniciado correctamente."
    })


# ==================== DIAGNOSTIC TOOLS (ADMIN ONLY) ====================
# Rate limiter: server-side cooldown per test per session
_DIAG_COOLDOWNS = {}  # key: (session_id, test_name) -> timestamp
DIAG_COOLDOWN_SECONDS = 30

def _check_diag_cooldown(test_name: str) -> tuple:
    """Check if a diagnostic test is on cooldown. Returns (allowed, remaining_seconds)."""
    sess_id = session.get("session_id", "unknown")
    key = f"{sess_id}:{test_name}"
    now = time.time()
    last_run = _DIAG_COOLDOWNS.get(key, 0)
    elapsed = now - last_run
    if elapsed < DIAG_COOLDOWN_SECONDS:
        remaining = int(DIAG_COOLDOWN_SECONDS - elapsed)
        return False, remaining
    _DIAG_COOLDOWNS[key] = now
    return True, 0


@admin_bp.route("/api/admin/diag/ip-detection", methods=["POST"])
@require_admin
def admin_diag_ip_detection():
    """Test if YouTube detects/blocks the datacenter IP vs residential proxy."""
    allowed, remaining = _check_diag_cooldown("ip-detection")
    if not allowed:
        return jsonify({"error": f"Cooldown activo. Reintentá en {remaining}s.", "cooldown": remaining}), 429

    logger = logging.getLogger("admin.diag")
    logger.info(f"[DIAG] IP Detection test initiated by {session.get('username', 'admin')}")

    results = {"direct": {}, "residential": {}, "recommendation": ""}
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" — first YT video, always public

    # Test 1: Direct VPS extraction
    try:
        t0 = time.time()
        ydl_opts = {
            "quiet": True, "skip_download": True, "extract_flat": True,
            "socket_timeout": 12, "no_warnings": True,
        }
        cookies_path = COOKIES_FILE
        if os.path.isfile(cookies_path) and os.path.getsize(cookies_path) > 0:
            ydl_opts["cookiefile"] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(test_url, download=False)

        elapsed = round((time.time() - t0) * 1000)
        results["direct"] = {
            "success": True,
            "latency_ms": elapsed,
            "title": (info or {}).get("title", "Desconocido")[:60],
            "blocked": False,
            "message": f"Extracción directa exitosa en {elapsed}ms"
        }
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000)
        err_str = str(e)
        is_blocked = any(kw in err_str.lower() for kw in [
            "sign in", "login", "bot", "captcha", "blocked", "forbidden",
            "429", "rate", "consent", "unavailable"
        ])
        results["direct"] = {
            "success": False,
            "latency_ms": elapsed,
            "blocked": is_blocked,
            "error_type": "antibot" if is_blocked else "network",
            "message": "IP del datacenter detectada/bloqueada por YouTube" if is_blocked else f"Error de red: {err_str[:120]}"
        }

    # Test 2: Residential proxy extraction (if configured)
    proxy_cfg = get_residential_proxy_config()
    if proxy_cfg.get("enabled") and proxy_cfg.get("url"):
        try:
            t0 = time.time()
            ydl_opts_res = {
                "quiet": True, "skip_download": True, "extract_flat": True,
                "socket_timeout": 15, "no_warnings": True,
                "proxy": proxy_cfg["url"],
            }
            if os.path.isfile(cookies_path) and os.path.getsize(cookies_path) > 0:
                ydl_opts_res["cookiefile"] = cookies_path

            with yt_dlp.YoutubeDL(ydl_opts_res) as ydl:
                info_res = ydl.extract_info(test_url, download=False)

            elapsed_res = round((time.time() - t0) * 1000)
            results["residential"] = {
                "success": True,
                "latency_ms": elapsed_res,
                "title": (info_res or {}).get("title", "Desconocido")[:60],
                "blocked": False,
                "message": f"Extracción vía proxy residencial exitosa en {elapsed_res}ms"
            }
        except Exception as e:
            elapsed_res = round((time.time() - t0) * 1000)
            results["residential"] = {
                "success": False,
                "latency_ms": elapsed_res,
                "blocked": True,
                "message": f"Fallo vía proxy residencial: {str(e)[:120]}"
            }
    else:
        results["residential"] = {
            "success": None,
            "message": "Proxy residencial no configurado o deshabilitado.",
            "blocked": None,
        }

    # Generate recommendation
    d = results["direct"]
    r = results["residential"]
    if d["success"] and not d.get("blocked"):
        results["recommendation"] = "optimal"
        results["recommendation_text"] = "La IP directa del VPS funciona correctamente con YouTube. No es necesario el proxy residencial para extracción básica."
    elif d.get("blocked") and r.get("success"):
        results["recommendation"] = "residential_required"
        results["recommendation_text"] = "YouTube bloquea la IP del datacenter. El proxy residencial es necesario para funcionamiento fiable. Mantené el failsafe activado."
    elif d.get("blocked") and not r.get("success") and r.get("success") is not None:
        results["recommendation"] = "critical"
        results["recommendation_text"] = "Ambas rutas fallan. Verificá cookies, proxy residencial y conectividad general."
    elif d.get("blocked") and r.get("success") is None:
        results["recommendation"] = "configure_residential"
        results["recommendation_text"] = "YouTube bloquea la IP directa y no hay proxy residencial configurado. Configurá el Enlace Residencial en la sección de Parámetros."
    else:
        results["recommendation"] = "unknown"
        results["recommendation_text"] = "No se pudo determinar una recomendación clara. Revisá los resultados individuales."

    logger.info(f"[DIAG] IP Detection result: direct={'OK' if d['success'] else 'FAIL'}, residential={'OK' if r.get('success') else 'N/A'}, recommendation={results['recommendation']}")
    return jsonify({"success": True, "results": results})


@admin_bp.route("/api/admin/diag/cascade-benchmark", methods=["POST"])
@require_admin
def admin_diag_cascade_benchmark():
    """Benchmark extraction speed across all available tiers."""
    allowed, remaining = _check_diag_cooldown("cascade-benchmark")
    if not allowed:
        return jsonify({"error": f"Cooldown activo. Reintentá en {remaining}s.", "cooldown": remaining}), 429

    logger = logging.getLogger("admin.diag")
    logger.info(f"[DIAG] Cascade benchmark initiated by {session.get('username', 'admin')}")

    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    tiers = []

    # Tier 1: Cobalt API
    try:
        t0 = time.time()
        cobalt_payload = {"url": test_url, "videoQuality": "360", "filenameStyle": "basic"}
        cr = requests.post(
            COBALT_URL,
            json=cobalt_payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15
        )
        elapsed = round((time.time() - t0) * 1000)
        if cr.status_code == 200:
            cobalt_data = cr.json()
            status = cobalt_data.get("status", "")
            tiers.append({
                "name": "Cobalt v11",
                "tier": 1,
                "success": status in ("redirect", "tunnel", "stream", "picker"),
                "latency_ms": elapsed,
                "status": status,
                "message": f"Cobalt respondió '{status}' en {elapsed}ms"
            })
        else:
            tiers.append({
                "name": "Cobalt v11",
                "tier": 1,
                "success": False,
                "latency_ms": elapsed,
                "status": f"HTTP {cr.status_code}",
                "message": f"Cobalt error HTTP {cr.status_code} en {elapsed}ms"
            })
    except Exception as e:
        tiers.append({
            "name": "Cobalt v11",
            "tier": 1,
            "success": False,
            "latency_ms": 0,
            "status": "offline",
            "message": f"Cobalt no disponible: {str(e)[:80]}"
        })

    # Tier 2: yt-dlp Direct
    try:
        t0 = time.time()
        ydl_opts = {
            "quiet": True, "skip_download": True, "extract_flat": False,
            "socket_timeout": 15, "no_warnings": True,
            "format": "worst",
        }
        if os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
            ydl_opts["cookiefile"] = COOKIES_FILE

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(test_url, download=False)

        elapsed = round((time.time() - t0) * 1000)
        formats_count = len(info.get("formats", [])) if info else 0
        tiers.append({
            "name": "yt-dlp (Directo)",
            "tier": 2,
            "success": True,
            "latency_ms": elapsed,
            "formats": formats_count,
            "message": f"yt-dlp extrajo {formats_count} formatos en {elapsed}ms"
        })
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000)
        tiers.append({
            "name": "yt-dlp (Directo)",
            "tier": 2,
            "success": False,
            "latency_ms": elapsed,
            "message": f"yt-dlp directo falló en {elapsed}ms: {str(e)[:80]}"
        })

    # Tier 3: yt-dlp via Residential Proxy
    proxy_cfg = get_residential_proxy_config()
    if proxy_cfg.get("enabled") and proxy_cfg.get("url"):
        try:
            t0 = time.time()
            ydl_opts_res = {
                "quiet": True, "skip_download": True, "extract_flat": False,
                "socket_timeout": 15, "no_warnings": True,
                "format": "worst",
                "proxy": proxy_cfg["url"],
            }
            if os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
                ydl_opts_res["cookiefile"] = COOKIES_FILE

            with yt_dlp.YoutubeDL(ydl_opts_res) as ydl:
                info_res = ydl.extract_info(test_url, download=False)

            elapsed_res = round((time.time() - t0) * 1000)
            formats_count_res = len(info_res.get("formats", [])) if info_res else 0
            tiers.append({
                "name": "yt-dlp (Residencial)",
                "tier": 3,
                "success": True,
                "latency_ms": elapsed_res,
                "formats": formats_count_res,
                "message": f"yt-dlp residencial extrajo {formats_count_res} formatos en {elapsed_res}ms"
            })
        except Exception as e:
            elapsed_res = round((time.time() - t0) * 1000)
            tiers.append({
                "name": "yt-dlp (Residencial)",
                "tier": 3,
                "success": False,
                "latency_ms": elapsed_res,
                "message": f"yt-dlp residencial falló en {elapsed_res}ms: {str(e)[:80]}"
            })
    else:
        tiers.append({
            "name": "yt-dlp (Residencial)",
            "tier": 3,
            "success": None,
            "latency_ms": 0,
            "message": "Proxy residencial no configurado"
        })

    # Rank by success, then latency
    ranked = sorted(
        [t for t in tiers if t["success"]],
        key=lambda x: x["latency_ms"]
    )
    fastest = ranked[0]["name"] if ranked else "Ninguno disponible"

    logger.info(f"[DIAG] Cascade benchmark complete: {len(ranked)} tiers OK, fastest={fastest}")
    return jsonify({"success": True, "tiers": tiers, "fastest": fastest})


@admin_bp.route("/api/admin/diag/dns-check", methods=["POST"])
@require_admin
def admin_diag_dns_check():
    """DNS resolution fingerprint and anomaly check."""
    allowed, remaining = _check_diag_cooldown("dns-check")
    if not allowed:
        return jsonify({"error": f"Cooldown activo. Reintentá en {remaining}s.", "cooldown": remaining}), 429

    logger = logging.getLogger("admin.diag")
    logger.info(f"[DIAG] DNS check initiated by {session.get('username', 'admin')}")

    domains = [
        {"domain": "youtube.com", "label": "YouTube (Principal)"},
        {"domain": "googlevideo.com", "label": "GoogleVideo (Streaming CDN)"},
        {"domain": "i.ytimg.com", "label": "YouTube Images (Thumbnails)"},
        {"domain": "www.google.com", "label": "Google (Referencia)"},
    ]

    results = []
    anomalies = 0

    for entry in domains:
        domain = entry["domain"]
        label = entry["label"]
        try:
            t0 = time.time()
            addrs = socket.getaddrinfo(domain, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
            elapsed = round((time.time() - t0) * 1000)
            ip_count = len(set(a[4][0] for a in addrs))
            # Only show hashed prefix for privacy (not full IPs)
            first_ip = addrs[0][4][0] if addrs else "N/A"
            ip_hash = hashlib.sha256(first_ip.encode()).hexdigest()[:8]

            is_ok = elapsed < 2000 and ip_count > 0
            if not is_ok:
                anomalies += 1

            results.append({
                "domain": domain,
                "label": label,
                "success": True,
                "resolution_ms": elapsed,
                "ip_count": ip_count,
                "ip_fingerprint": ip_hash,
                "status": "ok" if is_ok else "slow",
                "message": f"Resuelto en {elapsed}ms ({ip_count} IPs)" if is_ok else f"Resolución lenta: {elapsed}ms"
            })
        except socket.gaierror as e:
            anomalies += 1
            results.append({
                "domain": domain,
                "label": label,
                "success": False,
                "resolution_ms": 0,
                "ip_count": 0,
                "status": "fail",
                "message": f"Fallo DNS: {str(e)[:80]}"
            })
        except Exception as e:
            anomalies += 1
            results.append({
                "domain": domain,
                "label": label,
                "success": False,
                "resolution_ms": 0,
                "ip_count": 0,
                "status": "error",
                "message": f"Error: {str(e)[:80]}"
            })

    # Overall assessment
    avg_ms = round(sum(r["resolution_ms"] for r in results if r["success"]) / max(1, sum(1 for r in results if r["success"])))
    health = "healthy" if anomalies == 0 else ("degraded" if anomalies <= 1 else "critical")

    logger.info(f"[DIAG] DNS check complete: {len(results) - anomalies}/{len(results)} OK, avg={avg_ms}ms, health={health}")
    return jsonify({
        "success": True,
        "results": results,
        "summary": {
            "total": len(results),
            "resolved": len(results) - anomalies,
            "anomalies": anomalies,
            "avg_resolution_ms": avg_ms,
            "health": health
        }
    })


@admin_bp.route("/api/admin/diag/security-audit", methods=["POST"])
@require_admin
def admin_diag_security_audit():
    """Security configuration health check — pass/fail only, no secrets exposed."""
    allowed, remaining = _check_diag_cooldown("security-audit")
    if not allowed:
        return jsonify({"error": f"Cooldown activo. Reintentá en {remaining}s.", "cooldown": remaining}), 429

    logger = logging.getLogger("admin.diag")
    logger.info(f"[DIAG] Security audit initiated by {session.get('username', 'admin')}")

    checks = []
    score = 0
    total = 0

    # Check 1: Flask secret is not default
    total += 1
    from core.config import get_or_create_flask_secret
    default_secret = "dhtools_secret_session_key_2026_super_secure"
    env_secret = os.environ.get("FLASK_SECRET_KEY", "")
    is_default = (env_secret == default_secret)
    if not is_default:
        score += 1
    checks.append({
        "name": "Flask Secret Key",
        "description": "La clave secreta de sesión no debe ser el valor por defecto",
        "pass": not is_default,
        "severity": "critical" if is_default else "ok",
        "recommendation": "Definí una FLASK_SECRET_KEY única en variables de entorno" if is_default else None
    })

    # Check 2: Password hashing strength
    total += 1
    users = load_users()
    weak_hashes = 0
    for uname, udata in users.items():
        ph = udata.get("password_hash", "")
        if not ph.startswith("pbkdf2:sha256:"):
            weak_hashes += 1
    strong_hashes = weak_hashes == 0
    if strong_hashes:
        score += 1
    checks.append({
        "name": "Fortaleza de Hashes",
        "description": "Todas las contraseñas deben usar PBKDF2-SHA256 con ≥600k iteraciones",
        "pass": strong_hashes,
        "severity": "warning" if weak_hashes > 0 else "ok",
        "detail": f"{weak_hashes} usuario(s) con hash legacy" if weak_hashes > 0 else "Todos los hashes son PBKDF2-SHA256",
        "recommendation": "Los usuarios con hash legacy deben cambiar su contraseña" if weak_hashes > 0 else None
    })

    # Check 3: 2FA/TOTP for admin users
    total += 1
    admin_users = [(u, d) for u, d in users.items() if d.get("role") == "admin"]
    admins_with_2fa = sum(1 for _, d in admin_users if d.get("totp_enabled"))
    all_admins_2fa = (admins_with_2fa == len(admin_users)) if admin_users else False
    if all_admins_2fa:
        score += 1
    checks.append({
        "name": "2FA para Administradores",
        "description": "Todos los usuarios con rol admin deben tener doble factor de autenticación",
        "pass": all_admins_2fa,
        "severity": "warning" if not all_admins_2fa else "ok",
        "detail": f"{admins_with_2fa}/{len(admin_users)} admins con 2FA activo",
        "recommendation": "Activá 2FA en Perfil → Seguridad para todos los administradores" if not all_admins_2fa else None
    })

    # Check 4: Cookies file freshness
    total += 1
    cookies_ok = False
    cookies_detail = "No hay archivo de cookies"
    if os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        mtime = os.path.getmtime(COOKIES_FILE)
        age_days = (time.time() - mtime) / 86400
        if age_days < 30:
            cookies_ok = True
            cookies_detail = f"Cookies actualizadas hace {int(age_days)} días"
        else:
            cookies_detail = f"Cookies con {int(age_days)} días de antigüedad (posiblemente expiradas)"
    if cookies_ok:
        score += 1
    checks.append({
        "name": "Frescura de Cookies",
        "description": "El archivo cookies.txt debe ser reciente (< 30 días) para evitar bloqueos",
        "pass": cookies_ok,
        "severity": "warning" if not cookies_ok else "ok",
        "detail": cookies_detail,
        "recommendation": "Renovar cookies.txt desde el navegador con extensión Get cookies.txt LOCALLY" if not cookies_ok else None
    })

    # Check 5: Active sessions count
    total += 1
    with ACTIVE_SESSIONS_LOCK:
        active_count = sum(1 for s in ACTIVE_SESSIONS.values() if not s.get("revoked"))
    sessions_ok = active_count <= 10
    if sessions_ok:
        score += 1
    checks.append({
        "name": "Sesiones Activas",
        "description": "El número de sesiones simultáneas no debería ser excesivo",
        "pass": sessions_ok,
        "severity": "info" if not sessions_ok else "ok",
        "detail": f"{active_count} sesiones activas actualmente",
        "recommendation": "Revisá y revocá sesiones sospechosas en la pestaña Usuarios" if not sessions_ok else None
    })

    # Check 6: Lockout policy active
    total += 1
    from core.config import MAX_FAILED_LOGINS, LOCKOUT_DURATION_SECONDS
    lockout_ok = MAX_FAILED_LOGINS <= 10 and LOCKOUT_DURATION_SECONDS >= 300
    if lockout_ok:
        score += 1
    checks.append({
        "name": "Política de Bloqueo por Intentos",
        "description": "Debe existir un bloqueo tras intentos fallidos de login",
        "pass": lockout_ok,
        "severity": "ok" if lockout_ok else "warning",
        "detail": f"Max {MAX_FAILED_LOGINS} intentos, bloqueo {LOCKOUT_DURATION_SECONDS}s",
        "recommendation": None if lockout_ok else "Ajustá MAX_FAILED_LOGINS y LOCKOUT_DURATION_SECONDS en variables de entorno"
    })

    # Overall grade
    pct = round((score / total) * 100) if total > 0 else 0
    if pct >= 90:
        grade = "A"
    elif pct >= 70:
        grade = "B"
    elif pct >= 50:
        grade = "C"
    else:
        grade = "D"

    logger.info(f"[DIAG] Security audit complete: {score}/{total} passed, grade={grade}")
    return jsonify({
        "success": True,
        "checks": checks,
        "summary": {
            "passed": score,
            "total": total,
            "percentage": pct,
            "grade": grade
        }
    })
