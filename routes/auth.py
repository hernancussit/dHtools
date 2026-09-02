import os
import time
import json
import secrets
import hashlib
import functools
import urllib.parse
import logging
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, Response
from werkzeug.security import generate_password_hash, check_password_hash

from core.config import USERS_FILE, APP_USERNAME, APP_PASSWORD, MAX_FAILED_LOGINS, LOCKOUT_DURATION_SECONDS
from core.state import LOGIN_ATTEMPTS, LOGIN_ATTEMPTS_LOCK
from core.utils import load_config

auth_bp = Blueprint("auth_bp", __name__)

def get_client_ip() -> str:
    """Extracts client IP respecting proxy headers."""
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    if request.headers.get("X-Real-IP"):
        return request.headers.get("X-Real-IP").strip()
    return request.remote_addr or "127.0.0.1"


def hash_password(password: str) -> str:
    return generate_password_hash(password, method="pbkdf2:sha256:600000")


def verify_password(password: str, hashed: str) -> bool:
    if not password or not hashed:
        return False
    if hashed.startswith("pbkdf2:") or hashed.startswith("scrypt:"):
        return check_password_hash(hashed, password)
    # Transparent legacy SHA-256 migration support
    legacy_salt = "ytsite_salt_2026"
    leg_hash1 = hashlib.sha256(f"{legacy_salt}:{password}".encode("utf-8")).hexdigest()
    if secrets.compare_digest(leg_hash1, hashed):
        return True
    leg_hash2 = hashlib.sha256(f"{legacy_salt}_{password}".encode("utf-8")).hexdigest()
    return secrets.compare_digest(leg_hash2, hashed)


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
        stored_hash = u.get("password_hash", "")
        if verify_password(password, stored_hash) or (username == APP_USERNAME and secrets.compare_digest(password, APP_PASSWORD)):
            if u.get("status") == "suspended":
                return "SUSPENDED"
            # Upgrade legacy hash automatically
            if not stored_hash.startswith("pbkdf2:") and not stored_hash.startswith("scrypt:"):
                try:
                    users[username]["password_hash"] = hash_password(password)
                    save_users(users)
                except Exception:
                    pass
            return u
    if secrets.compare_digest(username, APP_USERNAME) and secrets.compare_digest(password, APP_PASSWORD):
        try:
            users[username] = {
                "password_hash": hash_password(password),
                "role": "admin",
                "status": "active",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_users(users)
        except Exception:
            pass
        return {"role": "admin", "username": username, "status": "active"}
    return False


def protect_all_routes():
    # Allow public endpoints without authentication
    if (
        request.path == "/login"
        or request.path == "/logout"
        or request.path.startswith("/static/")
        or request.path in ("/manifest.json", "/sw.js", "/robots.txt")
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
                return redirect(url_for("auth_bp.login", error="Tu cuenta ha sido suspendida."))
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
    return redirect(url_for("auth_bp.login", next=next_param))


def is_safe_redirect_url(target: str) -> bool:
    if not target or not isinstance(target, str):
        return False
    target = target.strip()
    if not target.startswith("/") or target.startswith("//") or target.startswith("/\\"):
        return False
    try:
        parsed = urllib.parse.urlparse(target)
        return not parsed.netloc and not parsed.scheme
    except Exception:
        return False


def require_admin(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        u = getattr(request, "current_user", None)
        if not u or u.get("role") != "admin":
            return jsonify({"error": "Acceso denegado: se requieren permisos de Administrador"}), 403


        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    ip = get_client_ip()

    # Check if IP is currently locked out
    with LOGIN_ATTEMPTS_LOCK:
        rec = LOGIN_ATTEMPTS.get(ip)
        if rec:
            blocked_until = rec.get("blocked_until", 0)
            if blocked_until > time.time():
                wait_min = int((blocked_until - time.time()) // 60) + 1
                return render_template(
                    "login.html",
                    config=load_config(),
                    error=f"Demasiados intentos fallidos. Tu IP está bloqueada temporalmente. Esperá {wait_min} min para reintentar.",
                    username="",
                    next_url="/",
                ), 429

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
            with LOGIN_ATTEMPTS_LOCK:
                rec = LOGIN_ATTEMPTS.setdefault(ip, {"count": 0, "first_fail": time.time(), "blocked_until": 0})
                if time.time() - rec["first_fail"] > 900:
                    rec["count"] = 1
                    rec["first_fail"] = time.time()
                else:
                    rec["count"] += 1
                count = rec["count"]
                if count >= MAX_FAILED_LOGINS:
                    rec["blocked_until"] = time.time() + LOCKOUT_DURATION_SECONDS
                    return render_template(
                        "login.html",
                        config=load_config(),
                        error="Has superado el límite de 5 intentos. Tu IP ha sido bloqueada temporalmente por 15 minutos.",
                        username=username,
                        next_url=next_url,
                    ), 429

            delay = min(2.0, 0.3 * (count ** 1.3))
            time.sleep(delay)
            remaining = MAX_FAILED_LOGINS - count
            return render_template(
                "login.html",
                config=load_config(),
                error=f"Usuario o contraseña incorrectos. (Intentos restantes: {remaining})",
                username=username,
                next_url=next_url,
            ), 401

        # Successful login: clear IP record
        with LOGIN_ATTEMPTS_LOCK:
            LOGIN_ATTEMPTS.pop(ip, None)

        session["username"] = u.get("username", username)
        session["role"] = u.get("role", "downloader")
        if is_safe_redirect_url(next_url):
            return redirect(next_url)
        return redirect("/")

    if session.get("username"):
        return redirect("/")

    return render_template(
        "login.html",
        config=load_config(),
        error=request.args.get("error"),
        msg=request.args.get("msg"),
        next_url=request.args.get("next"),
    )


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth_bp.login", msg="logged_out"))
