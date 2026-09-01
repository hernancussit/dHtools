import os
import re
import sys
import time
import uuid
import shutil
import secrets
import threading
import subprocess
import zipfile
import requests
from flask import Flask, request, jsonify, send_file, render_template, abort, Response

import yt_dlp
from yt_dlp.utils import download_range_func

app = Flask(__name__)

APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")

COOKIES_FILE = os.environ.get("COOKIES_FILE", "/app/cookies.txt")
POT_PROVIDER_URL = os.environ.get("POT_PROVIDER_URL", "http://potprovider:4416")
COBALT_URL = os.environ.get("COBALT_URL", "http://cobalt:9000/")


def cookies_opts():
    if os.path.isfile(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        return {"cookiefile": COOKIES_FILE}
    return {}


PLAYER_CLIENTS_ENV = os.environ.get("PLAYER_CLIENTS", "default").strip()


def player_client_opts(clients=None):
    opts = {
        "extractor_args": {
            "youtubepot-bgutilhttp": {"base_url": [POT_PROVIDER_URL]},
        }
    }
    target = clients
    if target is None and PLAYER_CLIENTS_ENV and PLAYER_CLIENTS_ENV != "default":
        target = PLAYER_CLIENTS_ENV.split(",")
    if target and target != ["default"] and target != "default":
        if isinstance(target, str):
            target = [target]
        opts["extractor_args"]["youtube"] = {"player_client": target}
    return opts



def check_auth(username, password):
    return secrets.compare_digest(username, APP_USERNAME) and secrets.compare_digest(password, APP_PASSWORD)


def require_auth():
    return Response(
        "Autenticación requerida", 401,
        {"WWW-Authenticate": 'Basic realm="Descargador de YouTube"'},
    )


@app.before_request
def protect_all_routes():
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return require_auth()


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


@app.route("/api/ytdlp-version")
def ytdlp_version():
    return jsonify({"version": get_ytdlp_version()})


@app.route("/api/update-ytdlp", methods=["POST"])
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


AUTO_UPDATE_YTDLP = os.environ.get("AUTO_UPDATE_YTDLP", "true").lower() == "true"
AUTO_UPDATE_INTERVAL_HOURS = float(os.environ.get("AUTO_UPDATE_INTERVAL_HOURS", "24"))


def auto_update_loop():
    while True:
        time.sleep(max(AUTO_UPDATE_INTERVAL_HOURS, 1) * 3600)
        try:
            result = run_pip_update()
            if result.returncode == 0 and "Successfully installed" in (result.stdout or ""):
                restart_process_soon(delay=0)
        except Exception:
            pass


if AUTO_UPDATE_YTDLP and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    threading.Thread(target=auto_update_loop, daemon=True).start()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

CLEANUP_AFTER_HOURS = float(os.environ.get("CLEANUP_AFTER_HOURS", "24"))
CLEANUP_CHECK_INTERVAL_MINUTES = float(os.environ.get("CLEANUP_CHECK_INTERVAL_MINUTES", "30"))

# job_id -> dict con status, progreso, metadatos de playlist, etc.
JOBS = {}
JOBS_LOCK = threading.Lock()


def format_speed(bytes_per_sec):
    if not bytes_per_sec:
        return None
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.1f} {unit}"
        bytes_per_sec /= 1024
    return f"{bytes_per_sec:.1f} TB/s"


def cleanup_loop():
    while True:
        time.sleep(max(CLEANUP_CHECK_INTERVAL_MINUTES, 1) * 60)
        if CLEANUP_AFTER_HOURS <= 0:
            continue
        cutoff = time.time() - (CLEANUP_AFTER_HOURS * 3600)
        try:
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
                    os.remove(job["filepath"])

            for entry in os.listdir(DOWNLOAD_DIR):
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


threading.Thread(target=cleanup_loop, daemon=True).start()


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name.strip()[:150] or "video"


def format_for_quality(quality: str) -> str:
    mapping = {
        "best": "bv*+ba/b",
        "2160p": "bv*[height<=2160]+ba/b[height<=2160]/bv*+ba/b",
        "1440p": "bv*[height<=1440]+ba/b[height<=1440]/bv*+ba/b",
        "1080p": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
        "720p": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
        "480p": "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b",
    }
    if quality in mapping:
        return mapping[quality]
    if quality.startswith("audio"):
        return "ba/b"
    return mapping["best"]


AUDIO_BITRATES = {"audio_128": "128", "audio_192": "192", "audio_256": "256", "audio_320": "320"}


def is_audio_quality(quality: str) -> bool:
    return quality.startswith("audio")


def parse_time_to_seconds(value):
    if value is None or value == "":
        return None
    value = str(value).strip()
    parts = value.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"Formato de tiempo inválido: '{value}' (usá HH:MM:SS, MM:SS o segundos)")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


@app.after_request
def add_noindex_header(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
    return response


@app.route("/robots.txt")
def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


def extract_with_fallback(url, ydl_opts_base, download):
    """Prueba combinaciones de clientes en orden:
    1) default (cadena inteligente de yt-dlp con Deno para JS challenges y bgutil para PO Token)
    2) web_embedded, tv_downgraded, mweb
    3) tv
    4) web
    """
    candidates = [
        ["default"],
        ["web_embedded", "tv_downgraded", "mweb"],
        ["tv"],
        ["web"],
    ]

    last_exc = None
    for clients in candidates:
        opts = dict(ydl_opts_base)
        opts["extractor_args"] = player_client_opts(clients)["extractor_args"]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as e:
            last_exc = e
            continue
    raise last_exc



APP_VERSION = "1.0.0"


@app.route("/")
def index():
    return render_template("index.html", version=APP_VERSION)


@app.route("/api/version")
def api_version():
    return jsonify({
        "app_version": APP_VERSION,
        "ytdlp_version": get_ytdlp_version(),
    })



@app.route("/api/info", methods=["POST"])
def info():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "Falta la URL"}), 400

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
        "ignore_no_formats_error": True,
        **cookies_opts(),
    }
    try:
        result = extract_with_fallback(url, ydl_opts, download=False)
    except Exception as e:
        return jsonify({"error": f"No se pudo leer la URL: {e}"}), 400

    if "entries" in result:
        entries = [e for e in result["entries"] if e]
        return jsonify({
            "type": "playlist",
            "title": result.get("title", "Playlist"),
            "count": len(entries),
            "thumbnail": (entries[0].get("thumbnails", [{}])[-1].get("url")
                          if entries and entries[0].get("thumbnails") else None),
        })
    else:
        thumbs = result.get("thumbnails") or []
        return jsonify({
            "type": "video",
            "title": result.get("title", "Video"),
            "duration": result.get("duration"),
            "thumbnail": thumbs[-1]["url"] if thumbs else result.get("thumbnail"),
        })


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


def run_download_cobalt(job_id: str, url: str, quality: str, video_title: str = ""):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

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

        final_name = os.path.basename(out_path)
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
            })
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update({"status": "error", "error": str(e), "finished_at": time.time()})
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def run_download(job_id: str, url: str, quality: str, playlist_mode: bool, total_count: int = 0,
                  start_time=None, end_time=None):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    completed_ids = set()

    def hook(d):
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

    ydl_opts = {
        "outtmpl": os.path.join(job_dir, "%(title)s.%(ext)s"),
        "format": format_for_quality(quality),
        "format_sort": ["res", "fps", "vcodec:av01", "acodec:opus"],
        "noplaylist": not playlist_mode,
        "progress_hooks": [hook],
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        **cookies_opts(),
    }

    if is_audio_quality(quality):
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": AUDIO_BITRATES.get(quality, "192"),
        }]
        ydl_opts.pop("merge_output_format", None)

    if not playlist_mode and (start_time is not None or end_time is not None):
        ydl_opts["download_ranges"] = download_range_func(None, [(start_time or 0, end_time or None)])
        ydl_opts["force_keyframes_at_cuts"] = True

    try:
        info_result = extract_with_fallback(url, ydl_opts, download=True)

        title = info_result.get("title", "descarga")

        files = [f for f in os.listdir(job_dir) if os.path.isfile(os.path.join(job_dir, f))]
        if not files:
            raise RuntimeError("No se generó ningún archivo")

        if len(files) > 1 or "entries" in info_result:
            zip_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(os.path.join(job_dir, f), arcname=f)
            final_path = zip_path
            final_name = safe_filename(title) + ".zip"
        else:
            src = os.path.join(job_dir, files[0])
            final_path = os.path.join(DOWNLOAD_DIR, f"{job_id}_{files[0]}")
            shutil.move(src, final_path)
            final_name = files[0]

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "finished",
                "percent": 100,
                "filepath": final_path,
                "filename": final_name,
                "finished_at": time.time(),
                "speed": None,
            })
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update({"status": "error", "error": str(e), "finished_at": time.time()})
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    quality = (data or {}).get("quality", "best")
    playlist_mode = bool((data or {}).get("playlist", False))
    total_count = int((data or {}).get("total_count") or 0)
    start_raw = (data or {}).get("start_time")
    end_raw = (data or {}).get("end_time")
    engine = (data or {}).get("engine", "ytdlp")
    video_title = (data or {}).get("video_title", "")

    if not url:
        return jsonify({"error": "Falta la URL"}), 400

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
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "queued",
            "percent": 0,
            "completed_count": 0,
            "total_count": total_count,
            "current_index": None,
            "current_title": None,
            "file_percent": 0,
            "speed": None,
            "eta_seconds": None,
        }

    if engine == "cobalt":
        thread = threading.Thread(
            target=run_download_cobalt, args=(job_id, url, quality, video_title), daemon=True
        )
    else:
        thread = threading.Thread(
            target=run_download,
            args=(job_id, url, quality, playlist_mode, total_count, start_time, end_time),
            daemon=True,
        )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


@app.route("/api/files/<job_id>")
def files(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or job.get("status") != "finished":
        abort(404)
    return send_file(job["filepath"], as_attachment=True, download_name=job["filename"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
