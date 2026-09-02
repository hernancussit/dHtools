import os
import time
import json
import secrets
import hashlib
import functools
import urllib.parse
import threading
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, Response
from werkzeug.security import generate_password_hash, check_password_hash

from core.config import USERS_FILE, APP_USERNAME, APP_PASSWORD, MAX_FAILED_LOGINS, LOCKOUT_DURATION_SECONDS
from core.state import LOGIN_ATTEMPTS, LOGIN_ATTEMPTS_LOCK, ACTIVE_SESSIONS, ACTIVE_SESSIONS_LOCK
from core.utils import load_config, send_system_email
from core.totp import (
    generate_totp_secret, get_totp_code, verify_totp_code,
    generate_backup_codes, get_totp_uri
)

auth_bp = Blueprint("auth_bp", __name__)

RESET_TOKENS = {}
RESET_TOKENS_LOCK = threading.Lock()

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
    try:
        os.chmod(USERS_FILE, 0o600)
    except Exception:
        pass



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
        or request.path in ("/manifest.json", "/sw.js", "/robots.txt", "/favicon.ico")
        or request.path in ("/api/auth/forgot-password", "/api/auth/reset-password", "/api/auth/verify-2fa")
    ):
        return None

    # 1. Check Flask Web Session
    sess_user = session.get("username")
    sess_id = session.get("session_id")
    if sess_user:
        # Check active session revocation
        if sess_id:
            with ACTIVE_SESSIONS_LOCK:
                sess_info = ACTIVE_SESSIONS.get(sess_id)
                if sess_info and sess_info.get("revoked"):
                    session.clear()
                    if request.path.startswith("/api/"):
                        return jsonify({"error": "Tu sesión ha sido revocada por el administrador."}), 401
                    return redirect(url_for("auth_bp.login", error="Tu sesión ha sido cerrada remotamente."))
                elif not sess_info:
                    ACTIVE_SESSIONS[sess_id] = {
                        "session_id": sess_id,
                        "username": sess_user,
                        "role": session.get("role", "downloader"),
                        "ip": get_client_ip(),
                        "user_agent": request.headers.get("User-Agent", "Desconocido")[:120],
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_active": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_active_ts": time.time(),
                        "revoked": False
                    }
                else:
                    sess_info["last_active"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    sess_info["last_active_ts"] = time.time()

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

        # Check if user has TOTP (2FA) enabled
        users = load_users()
        user_data = users.get(username, {})
        if user_data.get("totp_enabled"):
            session["pending_2fa"] = {
                "username": username,
                "role": u.get("role", "downloader"),
                "next_url": next_url,
                "expires": time.time() + 300
            }
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
                return jsonify({"require_2fa": True, "message": "Autenticación de Dos Factores (2FA) requerida."})
            return render_template(
                "login.html",
                config=load_config(),
                step="2fa",
                username=username,
                next_url=next_url
            )

        # Successful login: clear IP record
        with LOGIN_ATTEMPTS_LOCK:
            LOGIN_ATTEMPTS.pop(ip, None)

        session_id = secrets.token_urlsafe(24)
        session["username"] = u.get("username", username)
        session["role"] = u.get("role", "downloader")
        session["session_id"] = session_id

        # Register in ACTIVE_SESSIONS
        with ACTIVE_SESSIONS_LOCK:
            ACTIVE_SESSIONS[session_id] = {
                "session_id": session_id,
                "username": session["username"],
                "role": session["role"],
                "ip": ip,
                "user_agent": request.headers.get("User-Agent", "Desconocido")[:120],
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_active": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_active_ts": time.time(),
                "revoked": False
            }

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
    sess_id = session.get("session_id")
    if sess_id:
        with ACTIVE_SESSIONS_LOCK:
            ACTIVE_SESSIONS.pop(sess_id, None)
    session.clear()
    return redirect(url_for("auth_bp.login", msg="logged_out"))


@auth_bp.route("/api/auth/verify-2fa", methods=["POST"])
def verify_2fa():
    pending = session.get("pending_2fa")
    if not pending or pending.get("expires", 0) < time.time():
        return jsonify({"error": "La sesión de verificación 2FA ha expirado. Por favor iniciá sesión nuevamente."}), 400

    username = pending["username"]
    data = request.get_json(silent=True) or request.form
    code = str(data.get("code") or "").strip()

    if not code:
        return jsonify({"error": "Ingresá el código de verificación de 6 dígitos o un código de respaldo."}), 400

    users = load_users()
    user_data = users.get(username)
    if not user_data:
        return jsonify({"error": "Usuario no encontrado."}), 400

    totp_secret = user_data.get("totp_secret", "")
    backup_codes = user_data.get("backup_codes", [])

    is_valid = False
    used_backup = False

    # Check 6-digit TOTP
    clean_numeric = code.replace(" ", "").replace("-", "")
    if len(clean_numeric) == 6 and clean_numeric.isdigit():
        if verify_totp_code(totp_secret, clean_numeric):
            is_valid = True

    # Check Backup Code (e.g. A1B2-C3D4)
    if not is_valid and backup_codes:
        normalized_code = code.upper().replace(" ", "").replace("-", "")
        for bc in list(backup_codes):
            if bc.replace("-", "") == normalized_code:
                is_valid = True
                used_backup = True
                backup_codes.remove(bc)
                user_data["backup_codes"] = backup_codes
                save_users(users)
                break

    if not is_valid:
        return jsonify({"error": "Código de autenticación o de respaldo inválido."}), 401

    # Login success
    session.pop("pending_2fa", None)
    ip = get_client_ip()
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.pop(ip, None)

    session_id = secrets.token_urlsafe(24)
    session["username"] = username
    session["role"] = pending.get("role", "downloader")
    session["session_id"] = session_id

    with ACTIVE_SESSIONS_LOCK:
        ACTIVE_SESSIONS[session_id] = {
            "session_id": session_id,
            "username": username,
            "role": session["role"],
            "ip": ip,
            "user_agent": request.headers.get("User-Agent", "Desconocido")[:120],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_active_ts": time.time(),
            "revoked": False
        }

    next_url = pending.get("next_url") or "/"
    if not is_safe_redirect_url(next_url):
        next_url = "/"

    msg = "Inicio de sesión exitoso."
    if used_backup:
        msg += f" Has usado un código de respaldo. Te quedan {len(backup_codes)} códigos disponibles."

    return jsonify({"success": True, "message": msg, "redirect": next_url})


@auth_bp.route("/api/auth/2fa/status", methods=["GET"])
def totp_status():
    username = session.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    users = load_users()
    user_data = users.get(username, {})
    return jsonify({
        "totp_enabled": bool(user_data.get("totp_enabled")),
        "backup_codes_count": len(user_data.get("backup_codes", []))
    })


@auth_bp.route("/api/auth/2fa/setup", methods=["POST"])
def totp_setup():
    username = session.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    temp_secret = generate_totp_secret()
    backup_codes = generate_backup_codes(8)
    session["temp_totp_secret"] = temp_secret
    session["temp_backup_codes"] = backup_codes
    otpauth_uri = get_totp_uri(username, temp_secret)
    formatted_secret = " ".join([temp_secret[i:i+4] for i in range(0, len(temp_secret), 4)])
    return jsonify({
        "secret": temp_secret,
        "formatted_secret": formatted_secret,
        "otpauth_uri": otpauth_uri,
        "backup_codes": backup_codes
    })


@auth_bp.route("/api/auth/2fa/enable", methods=["POST"])
def totp_enable():
    username = session.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    temp_secret = session.get("temp_totp_secret")
    temp_backup_codes = session.get("temp_backup_codes")
    if not temp_secret or not temp_backup_codes:
        return jsonify({"error": "No se ha iniciado el proceso de configuración de 2FA."}), 400

    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip()

    if not verify_totp_code(temp_secret, code):
        return jsonify({"error": "El código de 6 dígitos ingresado es incorrecto o expiró."}), 400

    users = load_users()
    if username not in users:
        users[username] = {"password_hash": "", "role": session.get("role", "downloader"), "status": "active"}

    users[username]["totp_enabled"] = True
    users[username]["totp_secret"] = temp_secret
    users[username]["backup_codes"] = temp_backup_codes
    save_users(users)

    session.pop("temp_totp_secret", None)
    session.pop("temp_backup_codes", None)

    return jsonify({"success": True, "message": "¡Autenticación de Dos Factores (2FA) activada exitosamente!"})


@auth_bp.route("/api/auth/2fa/disable", methods=["POST"])
def totp_disable():
    username = session.get("username")
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")

    if not check_auth(username, password):
        return jsonify({"error": "Contraseña incorrecta."}), 403

    users = load_users()
    if username in users:
        users[username]["totp_enabled"] = False
        users[username].pop("totp_secret", None)
        users[username].pop("backup_codes", None)
        save_users(users)

    return jsonify({"success": True, "message": "Autenticación de Dos Factores desactivada."})



@auth_bp.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(force=True) or {}
    identifier = str(data.get("identifier", "")).strip().lower()
    if not identifier:
        return jsonify({"error": "Ingresá tu nombre de usuario o correo electrónico."}), 400

    users = load_users()
    target_user = None
    target_username = None

    for u, d in users.items():
        if u.lower() == identifier or (d.get("email") and d.get("email").strip().lower() == identifier):
            target_user = d
            target_username = u
            break

    if not target_user:
        return jsonify({"message": "Si la cuenta existe y tiene un correo asociado, recibirás las instrucciones en breve."})

    user_email = (target_user.get("email") or "").strip()
    cfg = load_config()
    smtp_enabled = cfg.get("smtp", {}).get("enabled", False)

    if not user_email:
        if not smtp_enabled:
            return jsonify({"error": "El servidor de correo no está configurado. Contactá al Administrador para restablecer tu contraseña."}), 400
        return jsonify({"error": "Tu cuenta no tiene una dirección de correo registrada. Contactá al Administrador para recuperar tu acceso."}), 400

    if not smtp_enabled:
        return jsonify({"error": "El servicio de correo electrónico está desactivado temporalmente. Contactá al Administrador."}), 400

    token = secrets.token_urlsafe(32)
    with RESET_TOKENS_LOCK:
        now = time.time()
        for t, rec in list(RESET_TOKENS.items()):
            if rec.get("expires", 0) < now or rec.get("username") == target_username:
                RESET_TOKENS.pop(t, None)
        RESET_TOKENS[token] = {
            "username": target_username,
            "expires": now + 3600
        }

    reset_url = request.host_url.rstrip("/") + f"/login?reset_token={token}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; background: #0f172a; color: #f8fafc; padding: 24px; border-radius: 12px; border: 1px solid #334155;">
        <h2 style="color: #38bdf8; margin-top: 0;">⚡ dHtools — Restablecimiento de Contraseña</h2>
        <p>Hola <strong>{target_username}</strong>,</p>
        <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta en dHtools.</p>
        <div style="text-align: center; margin: 24px 0;">
            <a href="{reset_url}" style="background: #ef4444; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Restablecer mi Contraseña</a>
        </div>
        <p style="font-size: 0.85rem; color: #94a3b8;">O copiá y pegá este enlace en tu navegador:</p>
        <p style="font-size: 0.78rem; word-break: break-all; color: #38bdf8;">{reset_url}</p>
        <hr style="border: 0; border-top: 1px solid #334155; margin: 20px 0;">
        <p style="font-size: 0.75rem; color: #64748b;">Este enlace es válido por 1 hora. Si no solicitaste este cambio, podés ignorar este correo de forma segura.</p>
    </div>
    """
    text = f"Hola {target_username},\n\nPara restablecer tu contraseña en dHtools, ingresá al siguiente enlace:\n{reset_url}\n\nEl enlace caduca en 1 hora."

    success, msg = send_system_email(user_email, "⚡ dHtools — Recuperación de Contraseña", html, text)
    if not success:
        return jsonify({"error": f"No se pudo enviar el correo de recuperación: {msg}"}), 500

    masked = user_email
    if "@" in user_email:
        prefix, domain = user_email.split("@", 1)
        masked = (prefix[:2] + "***@" + domain) if len(prefix) > 2 else ("*@" + domain)
    return jsonify({"message": f"Se enviaron las instrucciones de recuperación a {masked}."})


@auth_bp.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(force=True) or {}
    token = str(data.get("token", "")).strip()
    new_password = str(data.get("password", "")).strip()

    if not token or not new_password:
        return jsonify({"error": "Falta el token o la nueva contraseña."}), 400

    if len(new_password) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres."}), 400

    with RESET_TOKENS_LOCK:
        rec = RESET_TOKENS.get(token)
        if not rec or rec.get("expires", 0) < time.time():
            RESET_TOKENS.pop(token, None)
            return jsonify({"error": "El enlace de restablecimiento es inválido o ha caducado. Solicitá uno nuevo."}), 400

        username = rec.get("username")
        RESET_TOKENS.pop(token, None)

    users = load_users()
    if username not in users:
        return jsonify({"error": "Usuario no encontrado."}), 404

    users[username]["password_hash"] = hash_password(new_password)
    save_users(users)
    return jsonify({"message": "¡Contraseña actualizada exitosamente! Ya podés iniciar sesión."})


@auth_bp.route("/api/user/telegram-status", methods=["GET"])
def user_telegram_status():
    from flask import session
    current_user = getattr(request, "current_username", None) or session.get("username")
    if not current_user:
        return jsonify({"error": "No autenticado"}), 401

    from core.telegram_bot import telegram_bot
    bot_info = telegram_bot.get_bot_info(force_refresh=True)
    bot_username = bot_info.get("username") if bot_info else None

    users = load_users()
    user_data = users.get(current_user, {})
    tg_chat_id = user_data.get("telegram_chat_id")
    tg_user = user_data.get("telegram_username")

    return jsonify({
        "is_linked": bool(tg_chat_id),
        "telegram_chat_id": tg_chat_id,
        "telegram_username": tg_user,
        "bot_username": bot_username,
        "bot_active": telegram_bot.is_running(),
        "bot_enabled": telegram_bot.is_enabled() and bool(telegram_bot.get_token())
    })


@auth_bp.route("/api/user/telegram-token", methods=["POST"])
def user_telegram_token():
    from flask import session
    current_user = getattr(request, "current_username", None) or session.get("username")
    if not current_user:
        return jsonify({"error": "No autenticado"}), 401

    from core.telegram_bot import telegram_bot
    if not telegram_bot.is_enabled() or not telegram_bot.get_token():
        return jsonify({"error": "El asistente de Telegram está desactivado por el administrador."}), 403

    from core.utils import create_telegram_link_token
    token = create_telegram_link_token(current_user)
    bot_info = telegram_bot.get_bot_info(force_refresh=True)
    bot_username = bot_info.get("username") if bot_info else None
    deep_link = f"https://t.me/{bot_username}?start=link_{token}" if bot_username else None

    return jsonify({
        "success": True,
        "token": token,
        "bot_username": bot_username,
        "deep_link": deep_link
    })




@auth_bp.route("/api/user/telegram-unlink", methods=["POST"])
def user_telegram_unlink():
    from flask import session
    current_user = getattr(request, "current_username", None) or session.get("username")
    if not current_user:
        return jsonify({"error": "No autenticado"}), 401

    from core.utils import unlink_user_telegram
    unlink_user_telegram(current_user)
    return jsonify({"success": True, "message": "Cuenta de Telegram desvinculada exitosamente."})

