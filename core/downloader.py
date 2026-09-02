import os
import sys
import time
import json
import re
import shutil
import threading
import subprocess
import requests
import logging
import zipfile
import ftplib
import yt_dlp
from yt_dlp.utils import download_range_func

from core.config import (
    COOKIES_FILE, POT_PROVIDER_URL, PLAYER_CLIENTS_ENV, DOWNLOAD_DIR, COBALT_URL,
    APP_VERSION, AUTO_UPDATE_INTERVAL_HOURS, CLEANUP_CHECK_INTERVAL_MINUTES,
    CLEANUP_AFTER_HOURS
)
import core.state
from core.state import (
    JOBS, JOBS_LOCK, QUEUE_LIST, QUEUE_LOCK, BATCH_JOBS, BATCH_LOCK,
    START_TIME
)
from core.utils import (
    cookies_opts, player_client_opts, format_speed, load_config,
    load_cloud_config, load_downloads_meta, save_downloads_meta,
    record_download_meta, delete_download_meta, save_queue_state,
    load_queue_state, get_disk_status, format_bytes, safe_filename,
    format_for_quality, is_audio_quality, parse_time_to_seconds,
    safe_download_path, enqueue_job, format_seconds
)

QUALITY_FORMAT_MAP = {
    "best": "bestvideo+bestaudio/best",
    "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
    "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
}

COBALT_QUALITY_MAP = {
    "best": "max",
    "2160p": "2160",
    "1440p": "1440",
    "1080p": "1080",
    "720p": "720",
    "480p": "480",
}

CONTENT_TYPE_EXT = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
}

COBALT_AUDIO_BITRATES = {
    "audio_128": "128",
    "audio_192": "256",
    "audio_256": "256",
    "audio_320": "320",
}


def get_ytdlp_version():
    try:
        return yt_dlp.version.__version__
    except Exception:
        return "desconocida"


def run_pip_update():
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]"],
        capture_output=True, text=True, timeout=180,
    )


def restart_process_soon(delay=1.5):
    def _restart():
        time.sleep(delay)
        os._exit(0)
    threading.Thread(target=_restart, daemon=True).start()


def auto_update_loop():
    while True:
        time.sleep(max(AUTO_UPDATE_INTERVAL_HOURS, 1) * 3600)
        try:
            result = run_pip_update()
            if result.returncode == 0 and "Successfully installed" in (result.stdout or ""):
                restart_process_soon(delay=0)
        except Exception:
            pass


def sync_to_cloud(filepath: str, filename: str, job_info: dict = None, user_cloud_cfg: dict = None):
    if not filepath or not os.path.exists(filepath):
        return
    cfg = load_cloud_config()
    
    # If user provided their own cloud settings (e.g. Nextcloud/WebDAV, FTP, Webhook), merge/prioritize them
    if user_cloud_cfg and isinstance(user_cloud_cfg, dict):
        if "webdav" in user_cloud_cfg and user_cloud_cfg["webdav"].get("enabled"):
            cfg["webdav"] = user_cloud_cfg["webdav"]
        if "ftp" in user_cloud_cfg and user_cloud_cfg["ftp"].get("enabled"):
            cfg["ftp"] = user_cloud_cfg["ftp"]
        if "webhook" in user_cloud_cfg and user_cloud_cfg["webhook"].get("enabled"):
            cfg["webhook"] = user_cloud_cfg["webhook"]

    # 1. Webhook
    if cfg.get("webhook", {}).get("enabled") and cfg["webhook"].get("url"):
        try:
            requests.post(
                cfg["webhook"]["url"],
                json={
                    "event": "download_completed",
                    "filename": filename,
                    "size_bytes": os.path.getsize(filepath),
                    "job_info": job_info or {},
                    "timestamp": time.time(),
                },
                timeout=10,
            )
        except Exception as e:
            print(f"[CloudSync Webhook Error] {e}")

    # 2. WebDAV / Nextcloud
    wd = cfg.get("webdav", {})
    if wd.get("enabled") and wd.get("url"):
        try:
            base_url = wd["url"].rstrip("/")
            remote_path = wd.get("remote_path", "").strip("/ ")
            target_url = f"{base_url}/{remote_path}/{filename}" if remote_path else f"{base_url}/{filename}"
            auth = (wd.get("username", ""), wd.get("password", "")) if wd.get("username") else None
            with open(filepath, "rb") as f:
                requests.put(target_url, data=f, auth=auth, timeout=60)
        except Exception as e:
            print(f"[CloudSync WebDAV Error] {e}")

    # 3. FTP
    ftp_cfg = cfg.get("ftp", {})
    if ftp_cfg.get("enabled") and ftp_cfg.get("host"):
        try:
            ftp = ftplib.FTP()
            ftp.connect(ftp_cfg["host"], int(ftp_cfg.get("port", 21)), timeout=30)
            ftp.login(ftp_cfg.get("username", "anonymous"), ftp_cfg.get("password", ""))
            remote_dir = ftp_cfg.get("remote_dir", "/").strip()
            if remote_dir and remote_dir != "/":
                try:
                    ftp.cwd(remote_dir)
                except Exception:
                    pass
            with open(filepath, "rb") as f:
                ftp.storbinary(f"STOR {filename}", f)
            ftp.quit()
        except Exception as e:
            print(f"[CloudSync FTP Error] {e}")

    # 4. Telegram Bot (Personal upload if job originated from Telegram, or Admin fallback)
    tg_chat_id = (job_info or {}).get("telegram_chat_id")
    job_id_val = (job_info or {}).get("job_id") or (job_info or {}).get("id")
    if tg_chat_id:
        try:
            from core.telegram_bot import telegram_bot
            telegram_bot.notify_finished(job_id_val, filepath, filename)
        except Exception as e:
            print(f"[TelegramBot notify_finished Error] {e}")
    else:
        tg = cfg.get("telegram", {})
        if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
            try:
                token = tg["bot_token"]
                chat_id = tg["chat_id"]
                if os.path.getsize(filepath) <= 50 * 1024 * 1024:
                    with open(filepath, "rb") as f:
                        requests.post(
                            f"https://api.telegram.org/bot{token}/sendDocument",
                            data={"chat_id": chat_id, "caption": f"🎬 {filename}"},
                            files={"document": (filename, f)},
                            timeout=120,
                        )
            except Exception as e:
                print(f"[CloudSync Telegram Error] {e}")


def purge_downloads(force_all=False):
    cleaned_count = 0
    reclaimed_bytes = 0
    with JOBS_LOCK:
        active_ids = {
            jid for jid, j in JOBS.items()
            if j.get("status") in ("queued", "downloading", "processing")
        }
        stale_ids = [
            jid for jid, j in JOBS.items()
            if force_all or j.get("status") in ("finished", "error")
        ]

    for jid in stale_ids:
        with JOBS_LOCK:
            job = JOBS.pop(jid, None)
        if job and job.get("filepath") and os.path.exists(job["filepath"]):
            try:
                size = os.path.getsize(job["filepath"])
                os.remove(job["filepath"])
                reclaimed_bytes += size
                cleaned_count += 1
            except OSError:
                pass

    if os.path.exists(DOWNLOAD_DIR):
        for entry in os.listdir(DOWNLOAD_DIR):
            if entry == ".gitkeep":
                continue
            entry_path = os.path.join(DOWNLOAD_DIR, entry)
            job_id_guess = entry.split("_", 1)[0].replace(".zip", "")
            if job_id_guess in active_ids and not force_all:
                continue
            try:
                if os.path.isdir(entry_path):
                    for root, _, files in os.walk(entry_path):
                        for f in files:
                            reclaimed_bytes += os.path.getsize(os.path.join(root, f))
                    shutil.rmtree(entry_path, ignore_errors=True)
                    cleaned_count += 1
                else:
                    size = os.path.getsize(entry_path)
                    os.remove(entry_path)
                    reclaimed_bytes += size
                    cleaned_count += 1
            except OSError:
                pass

    return {
        "cleaned_count": cleaned_count,
        "reclaimed_bytes": reclaimed_bytes,
        "reclaimed_formatted": format_bytes(reclaimed_bytes),
    }


def cleanup_loop():
    while True:
        time.sleep(max(CLEANUP_CHECK_INTERVAL_MINUTES, 1) * 60)
        try:
            # 1. Emergency disk auto-purge
            disk_info = get_disk_status()
            if disk_info.get("is_emergency"):
                purge_downloads(force_all=False)

            # 2. Regular TTL cleanup
            if CLEANUP_AFTER_HOURS > 0:
                cutoff = time.time() - (CLEANUP_AFTER_HOURS * 3600)
                with JOBS_LOCK:
                    active_ids = {
                        jid for jid, j in JOBS.items()
                        if j.get("status") in ("queued", "downloading", "processing")
                    }
                    stale_ids = [
                        jid for jid, j in JOBS.items()
                        if j.get("status") in ("finished", "error")
                        and j.get("finished_at", 0) < cutoff
                    ]

                for jid in stale_ids:
                    with JOBS_LOCK:
                        job = JOBS.pop(jid, None)
                    if job and job.get("filepath") and os.path.exists(job["filepath"]):
                        try:
                            os.remove(job["filepath"])
                        except OSError:
                            pass

                for entry in os.listdir(DOWNLOAD_DIR):
                    if entry == ".gitkeep":
                        continue
                    entry_path = os.path.join(DOWNLOAD_DIR, entry)
                    job_id_guess = entry.split("_", 1)[0].replace(".zip", "")
                    if job_id_guess in active_ids:
                        continue
                    try:
                        mtime = os.path.getmtime(entry_path)
                    except OSError:
                        continue
                    if mtime < cutoff:
                        if os.path.isdir(entry_path):
                            shutil.rmtree(entry_path, ignore_errors=True)
                        else:
                            os.remove(entry_path)
        except Exception:
            pass


def is_permanent_error(err_str: str) -> bool:
    err_lower = str(err_str).lower()
    return any(p in err_lower for p in [
        "playlist does not exist",
        "copyright",
        "account has been terminated",
        "drm protection",
    ])


def format_friendly_error(err_str: str) -> str:
    err = str(err_str)
    err_lower = err.lower()
    if "confirm you’re not a bot" in err_lower or "not a bot" in err_lower or "sign in to confirm" in err_lower:
        if "no longer valid" in err_lower or "rotated" in err_lower:
            return "YouTube requiere verificación de cuenta y las cookies guardadas en el servidor expiraron. Por favor actualizá cookies.txt en el panel de Admin."
        return "YouTube bloqueó la petición solicitando verificar que no eres un robot. Por favor subí o actualizá cookies.txt en el panel de Administración."
    if "no longer valid" in err_lower or "rotated" in err_lower:
        return "Las cookies de YouTube en el servidor expiraron o fueron rotadas por seguridad. Por favor actualizá cookies.txt en Administración."
    if "confirm your age" in err_lower or "age-restricted" in err_lower:
        return "Este video tiene restricción de edad de YouTube. Requiere una sesión activa con cookies válidas en Administración."
    if "this video is private" in err_lower or "private video" in err_lower:
        return "El video es privado o requiere permisos especiales de acceso en YouTube."
    if "no se generó ningún archivo" in err_lower:
        return "No se pudo generar el archivo. Los servidores de streaming denegaron o limitaron las fuentes de video."
    return err


def extract_with_fallback(url, ydl_opts_base, download, job_id: str = None):
    """Prueba combinaciones de clientes y credenciales en orden optimizado:
    Para YouTube:
    1) default con PO Token + Deno sin cookies (para evitar la degradación a 360p del experimento SABR)
    2) default con cookies (si existen en el servidor, para videos restringidos/privados o con login)
    3) mweb (cliente web móvil, alta calidad sin restricciones de SABR en web)
    4) web_embedded, tv_downgraded
    5) tv
    Para otras plataformas:
    Usa cookies de inmediato si están configuradas.
    """
    is_yt = detect_platform(url) == "YouTube"
    has_cookies = bool(os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0)

    candidates = []
    if is_yt:
        candidates.append((["default"], False))
        if has_cookies:
            candidates.append((["default"], True))
        candidates.append((["mweb"], False))
        if has_cookies:
            candidates.append((["mweb"], True))
        candidates.append((["web_embedded", "tv_downgraded"], False))
        candidates.append((["tv"], False))
    else:
        candidates.append((["default"], has_cookies))

    last_exc = None
    for clients, use_ck in candidates:
        if job_id:
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get("status") == "cancelled":
                    return None
        opts = dict(ydl_opts_base)
        if use_ck and has_cookies:
            opts["cookiefile"] = COOKIES_FILE
        else:
            opts.pop("cookiefile", None)

        opts["extractor_args"] = player_client_opts(clients, for_download=download)["extractor_args"]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                res = ydl.extract_info(url, download=download)
                if not res:
                    raise yt_dlp.utils.DownloadError("El cliente no pudo extraer el video o no devolvió datos.")
                return res
        except (yt_dlp.utils.DownloadCancelled, yt_dlp.utils.MaxDownloadsReached):
            return None
        except yt_dlp.utils.DownloadError as e:
            last_exc = e
            if job_id:
                with JOBS_LOCK:
                    if JOBS.get(job_id, {}).get("status") == "cancelled":
                        return None
            if is_permanent_error(str(e)):
                break
            continue
        except Exception as e:
            last_exc = e
            if job_id:
                with JOBS_LOCK:
                    if JOBS.get(job_id, {}).get("status") == "cancelled":
                        return None
            break

    if job_id:
        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get("status") == "cancelled":
                return None

    if last_exc:
        raise last_exc
    return None


def normalize_url(url: str) -> str:

    url = url.strip()
    # Normalize YouTube Shorts to standard watch URL for maximum compatibility
    shorts_match = re.match(r"^https?://(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]+)", url)
    if shorts_match:
        video_id = shorts_match.group(1)
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "deezer.com" in url_lower or "deezer.page.link" in url_lower:
        return "Deezer"
    if "spotify.com" in url_lower:
        return "Spotify"
    if "youtube.com/shorts" in url_lower:
        return "YouTube Shorts"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    if "instagram.com" in url_lower:
        return "Instagram"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "Facebook"
    if "twitch.tv" in url_lower:
        return "Twitch"
    if "kick.com" in url_lower:
        return "Kick"
    if "tiktok.com" in url_lower:
        return "TikTok"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "Twitter / X"
    return "Web"


def is_playlist_url(url: str) -> bool:
    url_l = (url or "").lower()
    if "youtube.com/playlist" in url_l or "list=" in url_l:
        return True
    if "spotify.com/playlist" in url_l or "spotify.com/album" in url_l:
        return True
    if "deezer.com/playlist" in url_l or "deezer.com/album" in url_l:
        return True
    return False


def get_deezer_info(url: str):

    try:
        track_m = re.search(r"deezer\.com/(?:[a-zA-Z-]+/)?track/(\d+)", url)
        if track_m:
            track_id = track_m.group(1)
            r = requests.get(f"https://api.deezer.com/track/{track_id}", timeout=10)
            data = r.json()
            if "error" not in data:
                artist = data.get("artist", {}).get("name", "Artista")
                title = data.get("title", "Canción")
                album = data.get("album", {}).get("title", "")
                cover = data.get("album", {}).get("cover_xl") or data.get("album", {}).get("cover_big")
                return {
                    "type": "video",
                    "platform": "Deezer",
                    "title": f"{artist} - {title}",
                    "artist": artist,
                    "track_title": title,
                    "album": album,
                    "duration": data.get("duration"),
                    "thumbnail": cover,
                    "url": url,
                }

        album_m = re.search(r"deezer\.com/(?:[a-zA-Z-]+/)?album/(\d+)", url)
        if album_m:
            album_id = album_m.group(1)
            r = requests.get(f"https://api.deezer.com/album/{album_id}", timeout=10)
            data = r.json()
            if "error" not in data:
                tracks = data.get("tracks", {}).get("data", [])
                artist = data.get("artist", {}).get("name", "Artista")
                title = data.get("title", "Álbum")
                cover = data.get("cover_xl") or data.get("cover_big")
                items = [
                    {
                        "index": i + 1,
                        "id": str(t.get("id")),
                        "title": f"{t.get('artist', {}).get('name', artist)} - {t.get('title', '')}",
                        "url": t.get("link") or f"https://www.deezer.com/track/{t.get('id')}",
                        "duration": t.get("duration"),
                        "duration_formatted": f"{int(t.get('duration', 0))//60}:{int(t.get('duration', 0))%60:02d}" if t.get("duration") else None,
                        "thumbnail": cover,
                    }
                    for i, t in enumerate(tracks[:300])
                ]
                return {
                    "type": "playlist",
                    "platform": "Deezer",
                    "title": f"{artist} - {title}",
                    "count": len(tracks),
                    "thumbnail": cover,
                    "entries": tracks,
                    "items": items,
                    "url": url,
                }

        playlist_m = re.search(r"deezer\.com/(?:[a-zA-Z-]+/)?playlist/(\d+)", url)
        if playlist_m:
            pl_id = playlist_m.group(1)
            r = requests.get(f"https://api.deezer.com/playlist/{pl_id}", timeout=10)
            data = r.json()
            if "error" not in data:
                tracks = data.get("tracks", {}).get("data", [])
                cover = data.get("picture_xl") or data.get("picture_big")
                items = [
                    {
                        "index": i + 1,
                        "id": str(t.get("id")),
                        "title": f"{t.get('artist', {}).get('name', 'Artista')} - {t.get('title', '')}",
                        "url": t.get("link") or f"https://www.deezer.com/track/{t.get('id')}",
                        "duration": t.get("duration"),
                        "duration_formatted": f"{int(t.get('duration', 0))//60}:{int(t.get('duration', 0))%60:02d}" if t.get("duration") else None,
                        "thumbnail": (t.get("album", {}).get("cover_medium") or cover),
                    }
                    for i, t in enumerate(tracks[:300])
                ]
                return {
                    "type": "playlist",
                    "platform": "Deezer",
                    "title": f"Playlist: {data.get('title', 'Deezer')}",
                    "count": len(tracks),
                    "thumbnail": cover,
                    "entries": tracks,
                    "items": items,
                    "url": url,
                }
    except Exception:
        pass
    return None


def get_spotify_info(url: str):
    try:
        track_m = re.search(r"open\.spotify\.com/(?:[a-zA-Z-]+/)?track/([a-zA-Z0-9]+)", url)
        if track_m:
            r = requests.get(f"https://open.spotify.com/oembed?url={url}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                raw_title = data.get("title", "Spotify Track")
                parts = raw_title.split(" by ", 1)
                if len(parts) == 2:
                    track_title, artist = parts[0], parts[1]
                else:
                    track_title, artist = raw_title, "Artista"
                return {
                    "type": "video",
                    "platform": "Spotify",
                    "title": f"{artist} - {track_title}",
                    "artist": artist,
                    "track_title": track_title,
                    "album": "Spotify",
                    "thumbnail": data.get("thumbnail_url"),
                    "url": url,
                }
    except Exception:
        pass
    return None


def run_download_music(job_id: str, url: str, quality: str, deezer_arl: str = "", music_meta: dict = None, owner: str = "admin", user_cloud_sync: dict = None, folder_name: str = None, group_id: str = None):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)

    os.makedirs(job_dir, exist_ok=True)

    try:
        platform = detect_platform(url)
        meta = music_meta or {}
        if not meta:
            if platform == "Deezer":
                meta = get_deezer_info(url) or {}
            elif platform == "Spotify":
                meta = get_spotify_info(url) or {}

        title = meta.get("track_title") or meta.get("title") or "Canción"
        artist = meta.get("artist") or "Artista"
        album = meta.get("album") or "Música"
        cover_url = meta.get("thumbnail")
        display_name = f"{artist} - {title}"

        raw_audio_tmpl = os.path.join(job_dir, "raw_audio.%(ext)s")
        cover_file = os.path.join(job_dir, "cover.jpg")
        final_filename = safe_filename(display_name) + ".mp3"
        final_path = os.path.join(DOWNLOAD_DIR, f"{job_id}_{final_filename}")

        downloaded_direct = False

        # Attempt direct Deezer download if ARL is provided
        if platform == "Deezer" and deezer_arl:
            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "downloading",
                    "current_title": f"Descargando de Deezer Hi-Fi ({display_name})...",
                    "file_percent": 10,
                })
            try:
                ydl_opts = {
                    "format": "best",
                    "outtmpl": raw_audio_tmpl,
                    "quiet": True,
                    "http_headers": {"Cookie": f"arl={deezer_arl}"},
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)
                downloaded_direct = True
            except Exception as e:
                with JOBS_LOCK:
                    JOBS[job_id].update({
                        "current_title": f"ARL inválido o expirado. Descargando sin ARL ({display_name})...",
                    })

        if not downloaded_direct:
            search_query = f"ytsearch1:{artist} - {title} audio"
            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "downloading",
                    "current_title": f"Buscando audio de alta calidad para '{display_name}'...",
                    "file_percent": 20,
                })
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": raw_audio_tmpl,
                "quiet": True,
                **cookies_opts(for_url="youtube"),
            }
            extract_with_fallback(search_query, ydl_opts, download=True, job_id=job_id)


        found_files = [f for f in os.listdir(job_dir) if f.startswith("raw_audio.")]
        if not found_files:
            raise RuntimeError("No se pudo descargar el stream de audio")
        actual_audio = os.path.join(job_dir, found_files[0])

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "processing",
                "current_title": "Incrustando carátula y metadatos ID3...",
            })

        # Download Cover
        has_cover = False
        if cover_url:
            try:
                cr = requests.get(cover_url, timeout=10)
                if cr.status_code == 200:
                    with open(cover_file, "wb") as cf:
                        cf.write(cr.content)
                    has_cover = True
            except Exception:
                pass

        # Target bitrate
        bitrate_map = {"audio_128": "128k", "audio_192": "192k", "audio_256": "256k", "audio_320": "320k"}
        br = bitrate_map.get(quality, "320k")

        ffmpeg_cmd = ["ffmpeg", "-y", "-i", actual_audio]
        if has_cover:
            ffmpeg_cmd.extend([
                "-i", cover_file,
                "-map", "0:a", "-map", "1:v",
                "-c:v", "mjpeg",
                "-metadata:s:v", 'title="Album cover"',
                "-metadata:s:v", 'comment="Cover (front)"'
            ])
        else:
            ffmpeg_cmd.extend(["-map", "0:a"])

        ffmpeg_cmd.extend([
            "-c:a", "libmp3lame", "-b:a", br, "-id3v2_version", "3",
            "-metadata", f"title={title}",
            "-metadata", f"artist={artist}",
            "-metadata", f"album={album}",
            final_path,
        ])

        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {proc.stderr[:200]}")

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "finished",
                "percent": 100,
                "file_percent": 100,
                "filepath": final_path,
                "filename": final_filename,
                "finished_at": time.time(),
                "speed": None,
                "owner": owner,
            })
            job_snap = dict(JOBS[job_id])

        if os.path.exists(final_path):
            record_download_meta(job_id, final_filename, owner, os.path.getsize(final_path), folder_name=folder_name, group_id=group_id)
        threading.Thread(target=sync_to_cloud, args=(final_path, final_filename, job_snap, user_cloud_sync), daemon=True).start()
    except Exception as e:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            is_cancelled = (job and job.get("status") == "cancelled") or "cancelled" in str(e).lower()
            if is_cancelled:
                if job:
                    job["status"] = "cancelled"
                    job["finished_at"] = time.time()
                append_job_log(job_id, "[!] Descarga de música cancelada por el usuario.")
            else:
                if job:
                    job.update({
                        "status": "error",
                        "error": str(e),
                        "finished_at": time.time(),
                    })
                append_job_log(job_id, f"[!] Error en motor musical: {e}")
        if is_cancelled:
            return
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def append_job_log(job_id: str, message: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            if "logs" not in job:
                job["logs"] = []
            job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": message})
            if len(job["logs"]) > 150:
                job["logs"] = job["logs"][-150:]


def run_download_cobalt(job_id: str, url: str, quality: str, video_title: str = "", owner: str = "admin", user_cloud_sync: dict = None, folder_name: str = None, group_id: str = None):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    append_job_log(job_id, f"[*] [Cobalt v11] Solicitando stream para: {url}")

    try:
        payload = {"url": url, "downloadMode": "auto"}
        if is_audio_quality(quality):
            payload["downloadMode"] = "audio"
            payload["audioFormat"] = "mp3"
            bitrate = COBALT_AUDIO_BITRATES.get(quality, "320")
            if bitrate:
                payload["audioBitrate"] = bitrate
        else:
            payload["videoQuality"] = COBALT_QUALITY_MAP.get(quality, "max")


        resp = requests.post(
            COBALT_URL, json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=60,
        )
        data = resp.json()
        status = data.get("status")

        if status == "error":
            msg = (data.get("error") or {}).get("code", "Error desconocido de Cobalt")
            raise RuntimeError(f"Cobalt: {msg}")
        if status == "picker":
            items = data.get("picker") or []
            if not items:
                raise RuntimeError("Cobalt devolvió varias opciones pero ninguna usable")
            stream_url = items[0].get("url")
        elif status in ("tunnel", "redirect"):
            stream_url = data.get("url")
        else:
            raise RuntimeError(f"Respuesta inesperada de Cobalt: {status}")

        if not stream_url:
            raise RuntimeError("Cobalt no devolvió un link de descarga")

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "downloading"

        append_job_log(job_id, "[*] [Cobalt v11] Descargando stream directo a disco...")
        with requests.get(stream_url, stream=True, timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            ext = CONTENT_TYPE_EXT.get((r.headers.get("Content-Type") or "").split(";")[0].strip(), ".mp4")
            base_name = safe_filename(video_title) or "descarga"
            out_path = os.path.join(job_dir, base_name + ext)

            downloaded = 0
            last_update = time.time()
            last_downloaded = 0
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_update >= 0.5:
                        speed = (downloaded - last_downloaded) / (now - last_update)
                        with JOBS_LOCK:
                            job = JOBS.get(job_id)
                            if job:
                                job["file_percent"] = int(downloaded * 100 / total) if total else 0
                                job["percent"] = job["file_percent"]
                                job["speed"] = format_speed(speed)
                                job["completed_count"] = 0
                        last_update = now
                        last_downloaded = downloaded

        final_name = base_name + ext
        final_path = os.path.join(DOWNLOAD_DIR, f"{job_id}_{final_name}")
        shutil.move(out_path, final_path)

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "finished",
                "percent": 100,
                "filepath": final_path,
                "filename": final_name,
                "finished_at": time.time(),
                "speed": None,
                "owner": owner,
            })
            job_snap = dict(JOBS[job_id])
        if os.path.exists(final_path):
            record_download_meta(job_id, final_name, owner, os.path.getsize(final_path), folder_name=folder_name, group_id=group_id)
        append_job_log(job_id, f"[+] Archivo completado: {final_name}")
        threading.Thread(target=sync_to_cloud, args=(final_path, final_name, job_snap, user_cloud_sync), daemon=True).start()
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update({"status": "error", "error": str(e), "finished_at": time.time()})
        append_job_log(job_id, f"[!] Error en Cobalt: {e}")
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def run_download(job_id: str, url: str, quality: str, playlist_mode: bool, total_count: int = 0,
                  start_time=None, end_time=None, video_format="mp4", subtitles="none",
                  owner: str = "admin", user_cloud_sync: dict = None,
                  selected_indexes: list = None, playlist_delivery: str = "zip",
                  folder_name: str = None, group_id: str = None):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    append_job_log(job_id, f"[*] [yt-dlp] Iniciando proceso de descarga ({quality})...")

    completed_ids = set()
    last_log_milestone = [-1]

    def check_cancelled():
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job or job.get("status") == "cancelled":
                raise yt_dlp.utils.DownloadCancelled("Descarga cancelada por el usuario.")

    def match_filter_cancel(info_dict, *args, **kwargs):
        check_cancelled()
        return None

    def hook(d):
        check_cancelled()
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return

            info = d.get("info_dict") or {}
            playlist_index = info.get("playlist_index")
            playlist_count = info.get("playlist_count") or total_count
            video_id = info.get("id")

            if playlist_count:
                job["total_count"] = playlist_count
            if playlist_index:
                job["current_index"] = playlist_index
            if info.get("title"):
                job["current_title"] = info.get("title")

            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                job["file_percent"] = int(downloaded * 100 / total) if total else 0
                job["speed"] = format_speed(d.get("speed"))
                job["eta_seconds"] = d.get("eta")
                job["status"] = "downloading"
            elif d["status"] == "finished":
                if video_id:
                    completed_ids.add(video_id)
                job["completed_count"] = len(completed_ids)
                job["status"] = "processing"
                job["speed"] = None

            job["completed_count"] = len(completed_ids)
            total_for_pct = job.get("total_count") or 1
            file_fraction = (job.get("file_percent") or 0) / 100
            job["percent"] = min(100, int((job["completed_count"] + file_fraction) / total_for_pct * 100))

            if job.get("telegram_chat_id"):
                try:
                    from core.telegram_bot import telegram_bot
                    from core.utils import format_seconds
                    eta_s = format_seconds(job.get("eta_seconds")) if job.get("eta_seconds") else None
                    telegram_bot.notify_progress(job_id, job["percent"], job.get("speed"), eta_s)
                except Exception:
                    pass

            # Periodic user-friendly console logging
            milestone = job["percent"] // 20
            if milestone > last_log_milestone[0] and job["percent"] > 0:
                last_log_milestone[0] = milestone
                if "logs" not in job:
                    job["logs"] = []
                job["logs"].append({"time": time.strftime("%H:%M:%S"), "text": f"[+] Progreso: {job['percent']}% - Velocidad: {job.get('speed') or 'estable'}"})
                if len(job["logs"]) > 150:
                    job["logs"] = job["logs"][-150:]


    try:
        outtmpl = os.path.join(job_dir, "%(playlist_index&{:02d} - |)s%(title).100B.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "progress_hooks": [hook],
            "postprocessor_hooks": [lambda d: check_cancelled()],
            "match_filter": match_filter_cancel,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": not playlist_mode,
            "ignoreerrors": bool(playlist_mode),
            **cookies_opts(for_url=url),
            **player_client_opts(for_download=True),
        }

        if selected_indexes and len(selected_indexes) > 0:
            ydl_opts["playlist_items"] = ",".join(str(i) for i in selected_indexes)

        if is_audio_quality(quality):
            bitrate_map = {
                "audio_128": "128", "audio_192": "192",
                "audio_256": "256", "audio_320": "320",
            }
            target_format = "mp3"
            if quality in ("flac", "m4a", "opus", "wav"):
                target_format = quality

            pp = {
                "key": "FFmpegExtractAudio",
                "preferredcodec": target_format,
            }
            if target_format == "mp3":
                pp["preferredquality"] = bitrate_map.get(quality, "320")

            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [pp]
        else:
            fmt_str = QUALITY_FORMAT_MAP.get(quality, "bestvideo+bestaudio/best")
            ydl_opts["format"] = fmt_str
            ydl_opts["merge_output_format"] = video_format if video_format in ("mp4", "mkv", "webm") else "mp4"

        if subtitles in ("embed", "download"):
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitleslangs"] = ["es", "en", "all"]
            if subtitles == "embed" and not is_audio_quality(quality):
                if "postprocessors" not in ydl_opts:
                    ydl_opts["postprocessors"] = []
                ydl_opts["postprocessors"].append({
                    "key": "FFmpegEmbedSubtitle",
                    "already_have_subtitle": False,
                })

        if start_time is not None or end_time is not None:
            st_str = format_seconds(start_time) if start_time else "00:00"
            et_str = format_seconds(end_time) if end_time else "fin"
            append_job_log(job_id, f"[*] Recorte temporal inteligente: solicitando rango {st_str} -> {et_str}.")
            append_job_log(job_id, "[*] Descarga por segmentos activos (sin transferir el video completo).")
            ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
                None, [(start_time or 0, end_time or float("inf"))]
            )
            ydl_opts["force_keyframes_at_cuts"] = True

        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get("status") == "cancelled":
                return
            JOBS[job_id]["status"] = "downloading"

        extract_with_fallback(url, ydl_opts, download=True, job_id=job_id)


        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job or job.get("status") == "cancelled":
                append_job_log(job_id, "[!] Proceso detenido: descarga cancelada.")
                return

        files = [f for f in os.listdir(job_dir) if not f.endswith(".part") and not f.endswith(".ytdl")]
        if not files:
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get("status") == "cancelled":
                    return
            raise RuntimeError("No se generó ningún archivo")

        if playlist_mode or len(files) > 1:
            individual_files = []
            f_group_name = folder_name or JOBS.get(job_id, {}).get("current_title") or f"Playlist {job_id[:8]}"
            f_group_id = group_id or f"pl_{job_id}"
            
            for idx, f in enumerate(files, start=1):
                item_jid = f"{job_id}_{idx}"
                fname = f"{item_jid}_{f}"
                fpath = os.path.join(DOWNLOAD_DIR, fname)
                shutil.move(os.path.join(job_dir, f), fpath)
                fsize = os.path.getsize(fpath) if os.path.exists(fpath) else 0
                record_download_meta(item_jid, f, owner, fsize, folder_name=f_group_name, group_id=f_group_id)
                individual_files.append({"name": f, "path": fpath, "size": fsize, "job_id": item_jid})
            
            zip_filename = f"{safe_filename(f_group_name)}.zip"
            zip_path = os.path.join(DOWNLOAD_DIR, f"{job_id}_{zip_filename}")
            if playlist_delivery == "zip":
                with JOBS_LOCK:
                    JOBS[job_id]["status"] = "zipping"
                    JOBS[job_id]["current_title"] = "Generando archivo ZIP de la playlist..."
                append_job_log(job_id, "[*] Comprimiendo elementos en archivo ZIP...")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for item in individual_files:
                        if os.path.exists(item["path"]):
                            zf.write(item["path"], arcname=item["name"])
                final_path = zip_path
                final_name = zip_filename
            else:
                final_path = individual_files[0]["path"] if individual_files else None
                final_name = f"{len(files)} archivos descargados en la carpeta '{f_group_name}'"

            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "finished",
                    "percent": 100,
                    "filepath": final_path,
                    "filename": final_name,
                    "files_count": len(files),
                    "finished_at": time.time(),
                    "speed": None,
                    "owner": owner,
                    "delivery": playlist_delivery,
                    "folder_name": f_group_name,
                    "group_id": f_group_id,
                })
            append_job_log(job_id, f"[+] Se descargaron {len(files)} archivos en la carpeta '{f_group_name}'.")
        else:

            final_filename = f"{job_id}_{files[0]}"
            final_path = os.path.join(DOWNLOAD_DIR, final_filename)
            shutil.move(os.path.join(job_dir, files[0]), final_path)
            final_name = files[0]
            with JOBS_LOCK:
                JOBS[job_id].update({
                    "status": "finished",
                    "percent": 100,
                    "filepath": final_path,
                    "filename": final_name,
                    "finished_at": time.time(),
                    "speed": None,
                    "owner": owner,
                })
            if os.path.exists(final_path):
                record_download_meta(job_id, final_name, owner, os.path.getsize(final_path), folder_name=folder_name, group_id=group_id)
            append_job_log(job_id, f"[+] Archivo descargado: {final_name}")

        job_snap = dict(JOBS[job_id])
        if final_path and os.path.exists(final_path):
            threading.Thread(target=sync_to_cloud, args=(final_path, final_name, job_snap, user_cloud_sync), daemon=True).start()
    except Exception as e:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            is_cancelled = (job and job.get("status") == "cancelled") or "cancelled" in str(e).lower() or isinstance(e, yt_dlp.utils.DownloadCancelled)
            if is_cancelled:
                if job:
                    job["status"] = "cancelled"
                    job["finished_at"] = time.time()
                append_job_log(job_id, "[!] Descarga abortada y cancelada por el usuario.")
            else:
                friendly_msg = format_friendly_error(str(e))
                if job:
                    job.update({"status": "error", "error": friendly_msg, "finished_at": time.time()})
                append_job_log(job_id, f"[!] Error en yt-dlp: {friendly_msg}")
        if is_cancelled:
            return
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def run_download_cascade(job_id: str, url: str, quality: str, playlist_mode: bool, total_count: int = 0,
                         start_time=None, end_time=None, video_format="mp4", subtitles="none",
                         owner: str = "admin", user_cloud_sync: dict = None,
                         selected_indexes: list = None, playlist_delivery: str = "zip",
                         video_title: str = "", deezer_arl: str = "",
                         folder_name: str = None, group_id: str = None):
    attempts = []
    platform = detect_platform(url)
    append_job_log(job_id, f"[*] [Cascada Inteligente] Analizando contenido ({platform})...")

    # 1. First attempt: Cobalt v11 (for single video/audio, non-playlist)
    if not playlist_mode and start_time is None and end_time is None and subtitles == "none":
        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get("status") == "cancelled":
                return
        append_job_log(job_id, "[*] [1/3] Probando extracción con Motor Cobalt Oficial...")
        try:
            run_download_cobalt(job_id, url, quality, video_title, owner, user_cloud_sync, folder_name=folder_name, group_id=group_id)
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get("status") == "finished":
                    append_job_log(job_id, "[+] Proceso finalizado exitosamente con Cobalt.")
                    return
                if JOBS.get(job_id, {}).get("status") == "cancelled":
                    return
        except Exception as e:
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get("status") == "cancelled":
                    return
            err = str(e)
            if "error.api.youtube.login" in err:
                err = "Requiere inicio de sesión (Cobalt no procesa videos con login o restricción de edad)."
            attempts.append({"engine": "Cobalt v11 (API)", "status": "failed", "error": err})
            append_job_log(job_id, f"[!] Cobalt no pudo extraer el stream ({err}). Pasando a siguiente método...")

    # 2. Second attempt: Specialized Music Engine if Spotify/Deezer
    if platform in ("Deezer", "Spotify") and not playlist_mode:
        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get("status") == "cancelled":
                return
        append_job_log(job_id, f"[*] [2/3] Probando Motor Musical Especializado ({platform})...")
        try:
            run_download_music(job_id, url, quality, deezer_arl, None, owner, user_cloud_sync, folder_name=folder_name, group_id=group_id)
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get("status") == "finished":
                    append_job_log(job_id, "[+] Proceso finalizado exitosamente con Motor Musical.")
                    return
                if JOBS.get(job_id, {}).get("status") == "cancelled":
                    return
        except Exception as e:
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get("status") == "cancelled":
                    return
            err = str(e)
            attempts.append({"engine": f"Motor Música ({platform})", "status": "failed", "error": err})
            append_job_log(job_id, f"[!] Motor musical no pudo procesar ({err}). Pasando a yt-dlp...")

    # 3. Third attempt: yt-dlp with PoToken Provider and fallback clients
    with JOBS_LOCK:
        if JOBS.get(job_id, {}).get("status") == "cancelled":
            return
    append_job_log(job_id, "[*] [3/3] Probando extracción completa con yt-dlp (PoToken & Multi-Cliente)...")
    try:
        run_download(
            job_id, url, quality, playlist_mode, total_count, start_time, end_time,
            video_format, subtitles, owner, user_cloud_sync, selected_indexes, playlist_delivery,
            folder_name=folder_name, group_id=group_id
        )
        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get("status") == "finished":
                append_job_log(job_id, "[+] Proceso finalizado exitosamente con yt-dlp.")
                return
            if JOBS.get(job_id, {}).get("status") == "cancelled":
                return
    except Exception as e:
        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get("status") == "cancelled":
                return
        err = format_friendly_error(str(e))
        attempts.append({"engine": "yt-dlp (Extractor Principal)", "status": "failed", "error": err})
        append_job_log(job_id, f"[!] yt-dlp falló: {err}")

    # If all engines failed, record detailed error report
    with JOBS_LOCK:
        if JOBS.get(job_id, {}).get("status") != "cancelled":
            JOBS[job_id].update({
                "status": "error",
                "error": "Todos los métodos y motores de descarga fallaron al procesar este enlace.",
                "attempts": attempts,
                "finished_at": time.time(),
            })
            append_job_log(job_id, "[!] ERROR: Se agotaron todos los métodos de descarga disponibles.")


def background_queue_worker():
    global ACTIVE_WORKER_JOB
    while True:
        job_id = None
        with QUEUE_LOCK:
            current_queue = list(QUEUE_LIST)

        for jid in current_queue:
            with JOBS_LOCK:
                j = JOBS.get(jid)
                status = j.get("status") if j else None
            if status == "queued":
                job_id = jid
                break
            elif status in ("finished", "error", "cancelled", None):
                with QUEUE_LOCK:
                    if jid in QUEUE_LIST:
                        QUEUE_LIST.remove(jid)

        if not job_id:
            core.state.ACTIVE_WORKER_JOB = None
            ACTIVE_WORKER_JOB = None
            time.sleep(1)
            continue

        core.state.ACTIVE_WORKER_JOB = job_id
        ACTIVE_WORKER_JOB = job_id
        job_copy = None
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job and job.get("status") != "cancelled":
                job["status"] = "downloading"
                job["started_at"] = time.time()
                job_copy = dict(job)

        if not job_copy:
            with QUEUE_LOCK:
                if job_id in QUEUE_LIST:
                    QUEUE_LIST.remove(job_id)
            core.state.ACTIVE_WORKER_JOB = None
            ACTIVE_WORKER_JOB = None
            continue

        save_queue_state()

        try:
            engine = job_copy.get("engine", "auto")
            url = job_copy.get("url")
            quality = job_copy.get("quality", "best")
            playlist_mode = job_copy.get("playlist", False)
            total_count = job_copy.get("total_count", 0)
            start_time = job_copy.get("start_time")
            end_time = job_copy.get("end_time")
            video_format = job_copy.get("video_format", "mp4")
            subtitles = job_copy.get("subtitles", "none")
            owner = job_copy.get("owner", "admin")

            user_cloud_sync = job_copy.get("user_cloud_sync")
            selected_indexes = job_copy.get("selected_indexes")
            playlist_delivery = job_copy.get("playlist_delivery", "zip")
            video_title = job_copy.get("video_title", "")
            deezer_arl = job_copy.get("deezer_arl", "")
            folder_name = job_copy.get("folder_name")
            group_id = job_copy.get("group_id")


            if engine in ("auto", "cascade"):
                run_download_cascade(
                    job_id, url, quality, playlist_mode, total_count, start_time, end_time,
                    video_format, subtitles, owner, user_cloud_sync, selected_indexes,
                    playlist_delivery, video_title, deezer_arl, folder_name=folder_name, group_id=group_id
                )
            elif detect_platform(url) in ("Deezer", "Spotify") and not playlist_mode:
                run_download_music(
                    job_id, url, quality, deezer_arl, None, owner, user_cloud_sync,
                    folder_name=folder_name, group_id=group_id
                )
            elif engine == "cobalt":
                run_download_cobalt(
                    job_id, url, quality, video_title, owner, user_cloud_sync,
                    folder_name=folder_name, group_id=group_id
                )
            else:
                run_download(
                    job_id, url, quality, playlist_mode, total_count, start_time, end_time,
                    video_format, subtitles, owner, user_cloud_sync, selected_indexes,
                    playlist_delivery, folder_name=folder_name, group_id=group_id
                )
        except Exception as e:
            with JOBS_LOCK:
                if job_id in JOBS and JOBS[job_id].get("status") != "cancelled":
                    JOBS[job_id]["status"] = "error"
                    JOBS[job_id]["error"] = str(e)
                    JOBS[job_id]["finished_at"] = time.time()
        finally:

            with QUEUE_LOCK:
                if job_id in QUEUE_LIST:
                    QUEUE_LIST.remove(job_id)
            core.state.ACTIVE_WORKER_JOB = None
            ACTIVE_WORKER_JOB = None
            save_queue_state()
