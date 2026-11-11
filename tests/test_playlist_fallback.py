import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from core.downloader import extract_with_fallback, YtDlpJobLogger, JOBS, JOBS_LOCK, append_job_log
from core.config import DOWNLOAD_DIR


class TestPlaylistFallback(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.job_id = "test_pl_job_123"
        with JOBS_LOCK:
            JOBS[self.job_id] = {
                "id": self.job_id,
                "status": "queued",
                "logs": [],
                "percent": 0,
                "file_percent": 0,
            }

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        with JOBS_LOCK:
            JOBS.pop(self.job_id, None)

    def test_playlist_candidates_exclude_web_music(self):
        """Verifica que para playlists estándar de YouTube, web_music no sea candidato primario."""
        url = "https://www.youtube.com/playlist?list=PLr7vGfvSkIyF6Nn3FOPEdbbGT3d6lVmhc"
        ydl_opts_base = {"quiet": True, "noplaylist": False}

        captured_candidates = []

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_instance = MagicMock()
            mock_ydl_cls.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = {"id": "test_pl", "entries": []}

            # Simular directorio con archivo para evitar raise de 0 archivos
            job_dir = os.path.join(DOWNLOAD_DIR, self.job_id)
            os.makedirs(job_dir, exist_ok=True)
            dummy_file = os.path.join(job_dir, "test.mp3")
            with open(dummy_file, "w") as f:
                f.write("data")

            try:
                extract_with_fallback(url, ydl_opts_base, download=True, job_id=self.job_id)
            finally:
                shutil.rmtree(job_dir, ignore_errors=True)

            # Verificar que el primer candidato usado no sea web_music
            call_opts = mock_ydl_cls.call_args[0][0]
            player_clients = call_opts.get("extractor_args", {}).get("youtube", {}).get("player_client", [])
            self.assertNotIn("web_music", player_clients)

    def test_music_url_uses_web_music_primary(self):
        """Verifica que URLs explícitas de music.youtube.com sí tengan web_music como primario."""
        url = "https://music.youtube.com/playlist?list=PL12345"
        ydl_opts_base = {"quiet": True}

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_instance = MagicMock()
            mock_ydl_cls.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = {"id": "music_pl"}

            extract_with_fallback(url, ydl_opts_base, download=False, job_id=self.job_id)

            call_opts = mock_ydl_cls.call_args[0][0]
            player_clients = call_opts.get("extractor_args", {}).get("youtube", {}).get("player_client", [])
            self.assertIn("web_music", player_clients)

    def test_fallback_advances_when_zero_files_produced(self):
        """Verifica que si extract_info retorna dict pero no produce archivos en job_dir, avanza al siguiente candidato."""
        url = "https://www.youtube.com/watch?v=sample123"
        ydl_opts_base = {"quiet": True}

        attempts = []

        def side_effect_extract(u, download=False):
            attempts.append(len(attempts) + 1)
            job_dir = os.path.join(DOWNLOAD_DIR, self.job_id)
            os.makedirs(job_dir, exist_ok=True)
            if len(attempts) == 1:
                # Intento 1: No genera archivos (simula fallo silencioso con ignoreerrors)
                return {"id": "sample123"}
            else:
                # Intento 2: Genera archivo válido
                with open(os.path.join(job_dir, "video.mp4"), "w") as f:
                    f.write("content")
                return {"id": "sample123"}

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_instance = MagicMock()
            mock_ydl_cls.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.side_effect = side_effect_extract

            job_dir = os.path.join(DOWNLOAD_DIR, self.job_id)
            try:
                res = extract_with_fallback(url, ydl_opts_base, download=True, job_id=self.job_id)
                self.assertIsNotNone(res)
                self.assertGreaterEqual(len(attempts), 2, "Debería haber probado el segundo candidato al no hallar archivos")
            finally:
                shutil.rmtree(job_dir, ignore_errors=True)

    def test_ytdlp_job_logger_captures_item_errors(self):
        """Verifica que YtDlpJobLogger capture errores de elementos de la playlist a los logs del job."""
        logger = YtDlpJobLogger(self.job_id)
        logger.error("ERROR: [youtube] p_oH-bEQxNM: Video unavailable. This video is not available")

        with JOBS_LOCK:
            logs = JOBS[self.job_id]["logs"]
            self.assertTrue(any("Aviso en elemento:" in l["text"] for l in logs))
            self.assertTrue(any("Video unavailable" in l["text"] for l in logs))


if __name__ == "__main__":
    unittest.main()
