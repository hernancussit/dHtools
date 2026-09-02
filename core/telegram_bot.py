import os
import time
import json
import uuid
import logging
import threading
import urllib.parse
import requests

from core.config import (
    DOWNLOAD_DIR, TELEGRAM_BOT_TOKEN_ENV, TELEGRAM_BOT_ENABLED_ENV,
    POT_PROVIDER_URL, CLOUD_CONFIG_FILE
)
from core.state import (
    JOBS, JOBS_LOCK, QUEUE_LIST, QUEUE_LOCK,
    TELEGRAM_LINK_TOKENS, TELEGRAM_LINK_LOCK,
    TELEGRAM_ACTIVE_MESSAGES, TELEGRAM_ACTIVE_MESSAGES_LOCK,
    TELEGRAM_MEDIA_CACHE, TELEGRAM_MEDIA_CACHE_LOCK
)
from core.utils import (
    validate_media_url, safe_filename, safe_download_path,
    enqueue_job, format_bytes, format_seconds,
    load_downloads_meta, check_user_storage_quota,
    get_user_storage_used, load_cloud_config, save_cloud_config,
    get_user_by_telegram_chat_id, consume_telegram_link_token,
    unlink_user_telegram
)

logger = logging.getLogger("dhtools.telegram")


def render_progress_bar(pct: float, length: int = 12) -> str:
    filled = int(round(length * (pct / 100.0)))
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)


class TelegramBot:
    def __init__(self):
        self._running = False
        self._thread = None
        self._offset = 0
        self._bot_info = None
        self._lock = threading.RLock()
        self._last_progress_edit = {}  # job_id -> timestamp

    def get_token(self) -> str:
        cfg = load_cloud_config()
        token = cfg.get("telegram", {}).get("bot_token", "").strip()
        if not token:
            token = TELEGRAM_BOT_TOKEN_ENV
        return token

    def is_enabled(self) -> bool:
        cfg = load_cloud_config()
        # Default to True if token exists
        tg_cfg = cfg.get("telegram", {})
        if "enabled" in tg_cfg:
            return bool(tg_cfg.get("enabled"))
        return bool(TELEGRAM_BOT_ENABLED_ENV and self.get_token())

    def start(self):
        with self._lock:
            if self._running:
                return
            token = self.get_token()
            if not token:
                logger.info("[TelegramBot] No bot token configured. Bot is idle.")
                return
            if not self.is_enabled():
                logger.info("[TelegramBot] Bot is disabled in configuration.")
                return

            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramBotPoll")
            self._thread.start()
            logger.info("[TelegramBot] Polling worker started successfully.")

    def stop(self):
        with self._lock:
            self._running = False
            self._bot_info = None
            logger.info("[TelegramBot] Stopping bot worker.")

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def get_bot_info(self, force_refresh: bool = False) -> dict | None:
        if self._bot_info and not force_refresh:
            return self._bot_info
        token = self.get_token()
        if not token:
            return None
        try:
            res = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    self._bot_info = data.get("result", {})
                    return self._bot_info
        except Exception as e:
            logger.warning(f"[TelegramBot] Failed to getMe: {e}")
        return None

    # ==================== TELEGRAM HTTP API WRAPPERS ====================

    def _api_call(self, method: str, payload: dict = None, files: dict = None, timeout: int = 30) -> dict | None:
        token = self.get_token()
        if not token:
            return None
        url = f"https://api.telegram.org/bot{token}/{method}"
        try:
            if files:
                res = requests.post(url, data=payload, files=files, timeout=timeout)
            else:
                res = requests.post(url, json=payload, timeout=timeout)
            if res.status_code == 200:
                return res.json()
            else:
                logger.warning(f"[TelegramBot] API error on {method}: {res.status_code} - {res.text[:200]}")
                try:
                    return res.json()
                except Exception:
                    return None
        except Exception as e:
            logger.error(f"[TelegramBot] Network exception on {method}: {e}")
            return None

    def send_message(self, chat_id: int | str, text: str, reply_markup: dict = None, parse_mode: str = "HTML") -> dict | None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._api_call("sendMessage", payload)

    def edit_message(self, chat_id: int | str, message_id: int, text: str, reply_markup: dict = None, parse_mode: str = "HTML") -> dict | None:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._api_call("editMessageText", payload)

    def answer_callback_query(self, callback_query_id: str, text: str = None, show_alert: bool = False):
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        self._api_call("answerCallbackQuery", payload)

    def send_media(self, chat_id: int | str, file_path: str, caption: str = "", title: str = None, performer: str = None) -> bool:
        if not os.path.exists(file_path):
            return False
        token = self.get_token()
        if not token:
            return False

        ext = os.path.splitext(file_path)[1].lower()
        size = os.path.getsize(file_path)
        if size > 50 * 1024 * 1024:
            logger.info(f"[TelegramBot] File {file_path} exceeds 50MB ({size} bytes). Skipping direct upload.")
            return False

        base_name = os.path.basename(file_path)

        try:
            with open(file_path, "rb") as f:
                if ext in (".mp3", ".m4a", ".flac", ".wav", ".opus"):
                    method = "sendAudio"
                    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
                    if title: data["title"] = title
                    if performer: data["performer"] = performer
                    files = {"audio": (base_name, f)}
                elif ext in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
                    method = "sendVideo"
                    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", "supports_streaming": True}
                    files = {"video": (base_name, f)}
                else:
                    method = "sendDocument"
                    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
                    files = {"document": (base_name, f)}

                res = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=data, files=files, timeout=180)
                if res.status_code == 200 and res.json().get("ok"):
                    return True
                else:
                    logger.warning(f"[TelegramBot] sendMedia error: {res.status_code} - {res.text[:200]}")
        except Exception as e:
            logger.error(f"[TelegramBot] Failed to upload media: {e}")
        return False

    # ==================== POLLING LOOP & DISPATCHER ====================

    def _poll_loop(self):
        logger.info("[TelegramBot] Polling loop active.")
        while self._running:
            token = self.get_token()
            if not token or not self.is_enabled():
                time.sleep(5)
                continue

            try:
                payload = {
                    "offset": self._offset,
                    "timeout": 20,
                    "allowed_updates": ["message", "callback_query"]
                }
                res = requests.post(f"https://api.telegram.org/bot{token}/getUpdates", json=payload, timeout=25)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for update in updates:
                            up_id = update.get("update_id")
                            self._offset = up_id + 1
                            try:
                                self._dispatch_update(update)
                            except Exception as e:
                                logger.error(f"[TelegramBot] Error dispatching update {up_id}: {e}", exc_info=True)
                elif res.status_code in (401, 404):
                    logger.error(f"[TelegramBot] Invalid bot token: {res.text[:100]}. Pausing polling.")
                    time.sleep(30)
                else:
                    time.sleep(3)
            except requests.exceptions.Timeout:
                continue
            except Exception as e:
                logger.warning(f"[TelegramBot] Polling error: {e}")
                time.sleep(5)

    def _dispatch_update(self, update: dict):
        if "message" in update:
            self._handle_message(update["message"])
        elif "callback_query" in update:
            self._handle_callback_query(update["callback_query"])

    # ==================== MESSAGE HANDLER ====================

    def _handle_message(self, message: dict):
        chat_id = message.get("chat", {}).get("id")
        from_user = message.get("from", {})
        telegram_username = from_user.get("username", "")
        first_name = from_user.get("first_name", "Usuario")
        text = (message.get("text") or "").strip()

        if not chat_id or not text:
            return

        username, user_data = get_user_by_telegram_chat_id(chat_id)

        # Check for commands
        if text.startswith("/"):
            parts = text.split()
            cmd = parts[0].lower().split("@")[0]
            args = parts[1:] if len(parts) > 1 else []

            if cmd == "/start":
                self._cmd_start(chat_id, first_name, username, args, telegram_username)
            elif cmd == "/vincular":
                self._cmd_vincular(chat_id, args, telegram_username)
            elif cmd == "/desvincular":
                self._cmd_desvincular(chat_id, username)
            elif cmd == "/descargas" or cmd == "/misdescargas":
                self._cmd_descargas(chat_id, username)
            elif cmd == "/cola":
                self._cmd_cola(chat_id, username)
            elif cmd == "/cuota":
                self._cmd_cuota(chat_id, username, user_data)
            elif cmd == "/ayuda" or cmd == "/help":
                self._cmd_ayuda(chat_id, username)
            else:
                self.send_message(chat_id, "❓ Comando no reconocido. Escribí /ayuda para ver los comandos disponibles.")
            return

        # Not a command -> Check if it's a URL
        if text.startswith("http://") or text.startswith("https://") or "youtube.com" in text or "youtu.be" in text or "spotify.com" in text or "deezer.com" in text:
            if not username:
                self.send_message(
                    chat_id,
                    "🔒 <b>Cuenta no vinculada</b>\n\n"
                    "Para descargar contenido, tenés que vincular tu cuenta de Telegram con tu usuario de <b>dHtools</b>.\n\n"
                    "1. Ingresá a la plataforma web de dHtools.\n"
                    "2. En tu perfil, hacé clic en <b>🤖 Vincular con Telegram</b> para obtener tu código.\n"
                    "3. Enviame: <code>/vincular DHT-XXXXXX</code>"
                )
                return
            self._handle_media_url(chat_id, text, username)
        else:
            self.send_message(
                chat_id,
                "💡 Enviame un enlace de video o audio (YouTube, Spotify, Deezer, TikTok, Instagram, Twitter, etc.) para descargarlo, o usá /descargas para explorar tus archivos."
            )

    # ==================== COMMANDS ====================

    def _cmd_start(self, chat_id: int, first_name: str, username: str | None, args: list, telegram_username: str):
        if args:
            raw_token = args[0]
            ok, res_username = consume_telegram_link_token(raw_token, chat_id, telegram_username)
            if ok:
                self.send_message(
                    chat_id,
                    f"🎉 <b>¡Vinculación Exitosa!</b>\n\n"
                    f"Tu cuenta de Telegram quedó vinculada a tu usuario: <b>{res_username}</b>.\n\n"
                    f"Ahora podés:\n"
                    f"• 🔗 <b>Pegar cualquier enlace</b> para descargarlo al instante.\n"
                    f"• 📂 <code>/descargas</code> - Ver y recibir tus archivos.\n"
                    f"• ⏳ <code>/cola</code> - Monitorizar descargas activas.\n"
                    f"• 💾 <code>/cuota</code> - Ver tu espacio de almacenamiento."
                )
                return
            else:
                self.send_message(
                    chat_id,
                    f"⚠️ <b>Error de vinculación:</b> {res_username}\n\n"
                    f"Generá un nuevo código de vinculación desde la plataforma web."
                )
                return

        if username:
            self.send_message(
                chat_id,
                f"👋 ¡Hola <b>{first_name}</b>! Bienvenido a <b>dHtools Bot</b>.\n\n"
                f"👤 Sesión activa vinculada como: <b>{username}</b>.\n\n"
                f"Enviame cualquier enlace (YouTube, Spotify, Deezer, TikTok, etc.) para descargarlo con opciones interactivas, o usá:\n"
                f"• /descargas - Tus archivos recientes\n"
                f"• /cola - Descargas en curso\n"
                f"• /cuota - Espacio disponible\n"
                f"• /desvincular - Desconectar tu cuenta"
            )
        else:
            self.send_message(
                chat_id,
                f"👋 ¡Hola <b>{first_name}</b>! Bienvenido a <b>dHtools Bot</b>.\n\n"
                f"🔒 <b>Tu cuenta de Telegram aún no está vinculada.</b>\n\n"
                f"Para activar las descargas y acceder a tus archivos:\n"
                f"1. Ingresá a la web de dHtools.\n"
                f"2. Abrí tu perfil y hacé clic en <b>🤖 Vincular con Telegram</b>.\n"
                f"3. Enviá aquí: <code>/vincular &lt;código&gt;</code> (o usá el enlace directo generado en la web)."
            )

    def _cmd_vincular(self, chat_id: int, args: list, telegram_username: str):
        if not args:
            self.send_message(
                chat_id,
                "ℹ️ <b>Uso del comando:</b> <code>/vincular DHT-XXXXXX</code>\n\n"
                "Generá el código desde la web de dHtools (en tu perfil de usuario)."
            )
            return
        token = args[0]
        ok, res_user = consume_telegram_link_token(token, chat_id, telegram_username)
        if ok:
            self.send_message(
                chat_id,
                f"✅ <b>¡Cuenta vinculada con éxito!</b>\n\n"
                f"Tu Telegram ahora está asociado al usuario: <b>{res_user}</b>.\n"
                f"¡Ya podés enviar enlaces para descargar o usar /descargas!"
            )
        else:
            self.send_message(chat_id, f"❌ <b>Error:</b> {res_user}")

    def _cmd_desvincular(self, chat_id: int, username: str | None):
        if not username:
            self.send_message(chat_id, "ℹ️ Tu cuenta de Telegram no está vinculada a ningún usuario.")
            return
        unlink_user_telegram(username)
        self.send_message(
            chat_id,
            f"🔌 Se desvinculó tu cuenta de Telegram del usuario <b>{username}</b>.\n"
            f"Para volver a conectarte, generá un nuevo código en la web."
        )

    def _cmd_descargas(self, chat_id: int, username: str | None):
        if not username:
            self.send_message(chat_id, "🔒 Vinculá tu cuenta con /vincular para ver tus descargas.")
            return

        meta = load_downloads_meta()
        user_items = []
        for filename, info in meta.items():
            if info.get("owner") == username:
                user_items.append((filename, info))

        # Sort by timestamp desc
        user_items.sort(key=lambda x: x[1].get("timestamp", 0), reverse=True)

        if not user_items:
            self.send_message(
                chat_id,
                "📂 <b>Mis Descargas</b>\n\n"
                "Todavía no tenés archivos descargados. Enviame un enlace para comenzar."
            )
            return

        recent = user_items[:5]
        self.send_message(chat_id, f"📂 <b>Tus últimas {len(recent)} descargas:</b>")

        for fn, info in recent:
            title = info.get("title") or info.get("display_name") or fn
            size_mb = round(info.get("size_bytes", 0) / (1024 * 1024), 1)
            dur = format_seconds(info.get("duration", 0))
            is_audio = info.get("is_audio", False)
            ext = info.get("format") or os.path.splitext(fn)[1].lstrip(".")

            txt = (
                f"{'🎵' if is_audio else '🎬'} <b>{title}</b>\n"
                f"📦 Peso: {size_mb} MB | ⏱️ {dur} | 🏷️ {ext.upper()}"
            )

            # Build keyboard
            buttons = []
            if size_mb <= 50:
                buttons.append([{"text": "📥 Enviar a este chat", "callback_data": f"send:{fn[:40]}"}])

            markup = {"inline_keyboard": buttons} if buttons else None
            self.send_message(chat_id, txt, reply_markup=markup)

    def _cmd_cola(self, chat_id: int, username: str | None):
        if not username:
            self.send_message(chat_id, "🔒 Vinculá tu cuenta con /vincular para ver la cola.")
            return

        active_found = []
        with JOBS_LOCK:
            for jid, j in JOBS.items():
                if j.get("owner") == username and j.get("status") in ("downloading", "queued"):
                    active_found.append((jid, j))

        if not active_found:
            self.send_message(chat_id, "⏳ No tenés ninguna descarga activa ni en cola en este momento.")
            return

        msg = "⏳ <b>Tus descargas en curso:</b>\n\n"
        for jid, j in active_found:
            title = j.get("video_title") or j.get("url") or "Descarga"
            st = j.get("status")
            pct = j.get("percent", 0)
            spd = j.get("speed") or ""
            bar = render_progress_bar(pct, 10)
            msg += f"• <b>{title}</b>\n  Estado: <code>{st}</code> [{bar}] {pct}% {spd}\n"

        self.send_message(chat_id, msg)

    def _cmd_cuota(self, chat_id: int, username: str | None, user_data: dict | None):
        if not username or not user_data:
            self.send_message(chat_id, "🔒 Vinculá tu cuenta con /vincular para ver tu cuota.")
            return

        used_bytes = get_user_storage_used(username)
        used_fmt = format_bytes(used_bytes)
        try:
            quota_gb = float(user_data.get("quota_gb", 0) or 0)
        except Exception:
            quota_gb = 0

        if quota_gb <= 0:
            msg = (
                f"💾 <b>Estado de Almacenamiento</b>\n\n"
                f"👤 Usuario: <b>{username}</b>\n"
                f"📊 Espacio ocupado: <b>{used_fmt}</b>\n"
                f"♾️ Cuota asignada: <b>Ilimitada</b>"
            )
        else:
            quota_bytes = int(quota_gb * (1024 ** 3))
            pct = min(100.0, round((used_bytes / max(1, quota_bytes)) * 100, 1))
            bar = render_progress_bar(pct, 12)
            msg = (
                f"💾 <b>Estado de Almacenamiento</b>\n\n"
                f"👤 Usuario: <b>{username}</b>\n"
                f"📊 Espacio ocupado: <b>{used_fmt}</b> de <b>{quota_gb:.1f} GB</b> ({pct}%)\n"
                f"[{bar}] {pct}%"
            )
        self.send_message(chat_id, msg)

    def _cmd_ayuda(self, chat_id: int, username: str | None):
        status_line = f"👤 Sesión: <b>{username}</b>" if username else "🔒 Sesión: <i>No vinculada</i>"
        msg = (
            f"⚡ <b>dHtools Telegram Assistant</b>\n{status_line}\n\n"
            f"<b>Comandos disponibles:</b>\n"
            f"• 🔗 <i>Enviá cualquier enlace:</i> YouTube, Spotify, Deezer, TikTok, Instagram, Twitter, etc., y elegí calidad con botones.\n"
            f"• /descargas - Explorá tus archivos recientes y recibilos en el chat.\n"
            f"• /cola - Consultá tareas en ejecución.\n"
            f"• /cuota - Verificá tu almacenamiento en disco.\n"
            f"• /vincular &lt;token&gt; - Conectá tu cuenta de Telegram.\n"
            f"• /desvincular - Desconectá tu cuenta.\n"
            f"• /ayuda - Esta guía de ayuda.\n\n"
            f"💡 <i>Los archivos de hasta 50 MB se enviarán automáticamente a este chat cuando finalice la descarga.</i>"
        )
        self.send_message(chat_id, msg)

    # ==================== URL INSPECTION & QUALITY SELECTION ====================

    def _handle_media_url(self, chat_id: int, url: str, username: str):
        # Validate URL
        if not validate_media_url(url):
            self.send_message(chat_id, "⚠️ El enlace no parece ser una URL multimedia válida o contiene caracteres peligrosos.")
            return

        # Check user quota first
        can_dl, q_err = check_user_storage_quota(username)
        if not can_dl:
            self.send_message(chat_id, f"⚠️ <b>Cuota de almacenamiento excedida:</b>\n{q_err}")
            return

        sent = self.send_message(chat_id, f"🔍 <b>Inspeccionando enlace...</b>\n<code>{url[:80]}</code>")
        msg_id = sent.get("result", {}).get("message_id") if sent else None

        # Inspect asynchronously in worker thread
        def do_inspect():
            from core.downloader import extract_with_fallback, normalize_url, detect_platform
            clean_url = normalize_url(url)
            platform = detect_platform(clean_url)
            title = clean_url
            duration_str = "Desconocida"

            try:
                info = extract_with_fallback(clean_url, {"quiet": True}, download=False)
                if info:
                    title = info.get("title") or title
                    dur = info.get("duration")
                    if dur:
                        duration_str = format_seconds(dur)
            except Exception as e:
                logger.warning(f"[TelegramBot] Quick inspect failed: {e}")

            cache_id = uuid.uuid4().hex[:8]
            with TELEGRAM_MEDIA_CACHE_LOCK:
                TELEGRAM_MEDIA_CACHE[cache_id] = {
                    "url": clean_url,
                    "title": title,
                    "owner": username,
                    "platform": platform,
                    "created_at": time.time()
                }

            # Build inline keyboard
            # Row 1: Video
            # Row 2: Audio
            # Row 3: Cancel
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🎬 1080p", "callback_data": f"dl:1080p:mp4:{cache_id}"},
                        {"text": "🎬 720p", "callback_data": f"dl:720p:mp4:{cache_id}"},
                        {"text": "🎬 480p", "callback_data": f"dl:480p:mp4:{cache_id}"},
                    ],
                    [
                        {"text": "🎵 MP3 320k", "callback_data": f"dl:audio_320:mp3:{cache_id}"},
                        {"text": "🎵 MP3 192k", "callback_data": f"dl:audio_192:mp3:{cache_id}"},
                        {"text": "🎵 FLAC", "callback_data": f"dl:flac:flac:{cache_id}"},
                    ],
                    [
                        {"text": "❌ Cancelar", "callback_data": f"cancel_select:{cache_id}"}
                    ]
                ]
            }

            text = (
                f"📌 <b>{title}</b>\n"
                f"🌐 Origen: <b>{platform}</b> | ⏱️ Duración: <b>{duration_str}</b>\n\n"
                f"Elegí el formato y calidad para comenzar la descarga:"
            )

            if msg_id:
                self.edit_message(chat_id, msg_id, text, reply_markup=keyboard)
            else:
                self.send_message(chat_id, text, reply_markup=keyboard)

        threading.Thread(target=do_inspect, daemon=True).start()

    # ==================== CALLBACK QUERIES ====================

    def _handle_callback_query(self, query: dict):
        q_id = query.get("id")
        data = query.get("data", "")
        message = query.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        username, _ = get_user_by_telegram_chat_id(chat_id)
        if not username:
            self.answer_callback_query(q_id, "🔒 Cuenta no vinculada", show_alert=True)
            return

        if data.startswith("cancel_select:"):
            cache_id = data.split(":", 1)[1] if ":" in data else ""
            with TELEGRAM_MEDIA_CACHE_LOCK:
                cached = TELEGRAM_MEDIA_CACHE.get(cache_id)
            if cached and cached.get("owner") != username:
                self.answer_callback_query(q_id, "⛔ No tenés permiso para cancelar esta acción", show_alert=True)
                return
            self.answer_callback_query(q_id, "Selección cancelada")
            self.edit_message(chat_id, message_id, "❌ <i>Descarga cancelada.</i>")
            return

        if data.startswith("cancel_job:"):
            job_id = data.split(":", 1)[1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job and job.get("owner") != username:
                    self.answer_callback_query(q_id, "⛔ No tenés permiso para cancelar este trabajo", show_alert=True)
                    return
                if job_id in JOBS:
                    JOBS[job_id]["status"] = "cancelled"
            with QUEUE_LOCK:
                if job_id in QUEUE_LIST:
                    QUEUE_LIST.remove(job_id)
            self.answer_callback_query(q_id, "Descarga cancelada")
            self.edit_message(chat_id, message_id, "🚫 <i>Descarga cancelada por el usuario.</i>")
            return

        if data.startswith("send:"):
            fn = data.split(":", 1)[1]
            meta = load_downloads_meta()
            matched = None
            matched_info = None
            for stored_fn, finfo in meta.items():
                if stored_fn.startswith(fn) or fn in stored_fn:
                    matched = stored_fn
                    matched_info = finfo
                    break

            if not matched or not matched_info:
                self.answer_callback_query(q_id, "Archivo no encontrado", show_alert=True)
                return

            if matched_info.get("owner") != username:
                self.answer_callback_query(q_id, "⛔ No tenés permiso para acceder a este archivo", show_alert=True)
                return

            self.answer_callback_query(q_id, "Enviando archivo...")
            fpath = safe_download_path(matched)
            if fpath and os.path.exists(fpath):
                ok = self.send_media(chat_id, fpath, caption=f"📥 <b>{matched}</b>")
                if not ok:
                    self.send_message(chat_id, "⚠️ El archivo supera los 50 MB de límite de Telegram o hubo un error al transferirlo.")
            else:
                self.send_message(chat_id, "❌ El archivo ya no se encuentra en el servidor (fue purgado).")
            return

        if data.startswith("dl:"):
            # dl:<quality>:<fmt>:<cache_id>
            parts = data.split(":")
            if len(parts) < 4:
                self.answer_callback_query(q_id, "Datos inválidos")
                return
            quality = parts[1]
            video_format = parts[2]
            cache_id = parts[3]

            with TELEGRAM_MEDIA_CACHE_LOCK:
                cached = TELEGRAM_MEDIA_CACHE.get(cache_id)

            if not cached:
                self.answer_callback_query(q_id, "La sesión de descarga expiró. Volvé a enviar el enlace.", show_alert=True)
                self.edit_message(chat_id, message_id, "⚠️ <i>Sesión expirada. Por favor reenviá el enlace.</i>")
                return

            if cached.get("owner") != username:
                self.answer_callback_query(q_id, "⛔ Esta solicitud pertenece a otro usuario", show_alert=True)
                return

            can_dl, q_err = check_user_storage_quota(username)
            if not can_dl:
                self.answer_callback_query(q_id, "Cuota de almacenamiento excedida", show_alert=True)
                self.edit_message(chat_id, message_id, f"⚠️ <b>Límite de cuota alcanzado:</b>\n{q_err}")
                return

            self.answer_callback_query(q_id, "¡Encolado para descarga!")

            job_id = uuid.uuid4().hex
            job_spec = {
                "status": "queued",
                "percent": 0,
                "completed_count": 0,
                "total_count": 1,
                "current_index": None,
                "current_title": cached["title"],
                "file_percent": 0,
                "speed": None,
                "eta_seconds": None,
                "owner": username,
                "url": cached["url"],
                "quality": quality,
                "video_format": video_format,
                "subtitles": "none",
                "playlist": False,
                "engine": "auto",
                "video_title": cached["title"],
                "created_at": time.time(),
                "telegram_chat_id": chat_id,
                "telegram_message_id": message_id,
                "logs": [{"time": time.strftime("%H:%M:%S"), "text": f"[*] Encolado desde Telegram ({quality})."}],
                "attempts": [],
            }

            enqueue_job(job_id, job_spec)

            with TELEGRAM_ACTIVE_MESSAGES_LOCK:
                TELEGRAM_ACTIVE_MESSAGES[job_id] = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "last_edit": time.time(),
                    "title": cached["title"],
                    "quality": quality
                }

            cancel_kb = {
                "inline_keyboard": [
                    [{"text": "❌ Cancelar Descarga", "callback_data": f"cancel_job:{job_id}"}]
                ]
            }

            self.edit_message(
                chat_id,
                message_id,
                f"⏳ <b>Encolado para descarga en segundo plano</b>\n"
                f"📌 <b>{cached['title']}</b>\n"
                f"⚙️ Calidad seleccionada: <code>{quality}</code> ({video_format.upper()})\n\n"
                f"<i>Iniciando worker de extracción...</i>",
                reply_markup=cancel_kb
            )

    # ==================== PROGRESS & COMPLETION HOOKS ====================

    def notify_progress(self, job_id: str, percent: float, speed: str = None, eta: str = None):
        with TELEGRAM_ACTIVE_MESSAGES_LOCK:
            info = TELEGRAM_ACTIVE_MESSAGES.get(job_id)
            if not info:
                return

            now = time.time()
            if now - info.get("last_edit", 0) < 3.0:
                return  # Throttle to max 1 edit per 3s to respect Telegram limits

            info["last_edit"] = now
            chat_id = info["chat_id"]
            msg_id = info["message_id"]
            title = info.get("title", "Descarga")
            quality = info.get("quality", "Auto")

        bar = render_progress_bar(percent, 12)
        spd_str = f" | {speed}" if speed else ""
        eta_str = f" | ETA: {eta}" if eta else ""

        text = (
            f"⚡ <b>Descargando:</b> {title}\n"
            f"[{bar}] <b>{percent}%</b>{spd_str}{eta_str}\n"
            f"⚙️ Calidad: <code>{quality}</code>"
        )
        cancel_kb = {
            "inline_keyboard": [
                [{"text": "❌ Cancelar", "callback_data": f"cancel_job:{job_id}"}]
            ]
        }
        self.edit_message(chat_id, msg_id, text, reply_markup=cancel_kb)

    def notify_finished(self, job_id: str, file_path: str, filename: str):
        with TELEGRAM_ACTIVE_MESSAGES_LOCK:
            info = TELEGRAM_ACTIVE_MESSAGES.pop(job_id, None)
            if not info:
                return

        chat_id = info["chat_id"]
        msg_id = info["message_id"]
        title = info.get("title", filename)

        if not file_path or not os.path.exists(file_path):
            self.edit_message(chat_id, msg_id, f"✅ <b>¡Descarga completada!</b>\n📌 {title}")
            return

        size = os.path.getsize(file_path)
        size_fmt = format_bytes(size)

        # Telegram bot direct upload limit: 50MB
        if size <= 50 * 1024 * 1024:
            self.edit_message(chat_id, msg_id, f"⬆️ <b>Subiendo archivo al chat...</b>\n📌 {title} ({size_fmt})")
            caption = f"✅ <b>{title}</b>\n📦 {size_fmt}"
            uploaded = self.send_media(chat_id, file_path, caption=caption, title=title)
            if uploaded:
                self.edit_message(chat_id, msg_id, f"✅ <b>¡Archivo entregado con éxito!</b>\n📌 {title} ({size_fmt})")
            else:
                self.edit_message(chat_id, msg_id, f"✅ <b>Descarga completada:</b>\n📌 {title} ({size_fmt})\n<i>(No se pudo transferir directamente al chat)</i>")
        else:
            # Over 50MB -> Send web download button
            cfg = load_cloud_config()
            self.edit_message(
                chat_id,
                msg_id,
                f"✅ <b>¡Descarga completada con éxito!</b>\n\n"
                f"📌 <b>{title}</b>\n"
                f"📦 Peso: <b>{size_fmt}</b>\n\n"
                f"ℹ️ <i>El archivo supera los 50 MB de límite que impone Telegram para bots. Podés descargarlo directamente desde tu panel web de dHtools en la sección 'Mis Descargas'.</i>"
            )

    def notify_error(self, job_id: str, error_msg: str):
        with TELEGRAM_ACTIVE_MESSAGES_LOCK:
            info = TELEGRAM_ACTIVE_MESSAGES.pop(job_id, None)
            if not info:
                return

        chat_id = info["chat_id"]
        msg_id = info["message_id"]
        title = info.get("title", "Descarga")

        self.edit_message(
            chat_id,
            msg_id,
            f"❌ <b>Error en la descarga:</b>\n"
            f"📌 <b>{title}</b>\n\n"
            f"<code>{str(error_msg)[:200]}</code>"
        )


# Global singleton instance
telegram_bot = TelegramBot()
