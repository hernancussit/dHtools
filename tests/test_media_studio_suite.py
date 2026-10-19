import unittest
from unittest.mock import patch, MagicMock
import io
import json
import os
import subprocess
from app import app


class TestMediaStudioSuite(unittest.TestCase):
    """
    Suite completa de pruebas automatizadas para todas las funciones del Estudio Multimedia (Media Studio):
    - Subida de archivos multipart/form-data y selección desde descargas locales.
    - Conversión de formatos (audio: MP3, FLAC, WAV, M4A, Opus, OGG; video: MP4, MKV, WebM, AVI; GIF animado).
    - Compresión inteligente (Perfiles WhatsApp 16MB/25MB, Discord, CRF personalizado y compresión de audio).
    - Recortes (Lossless stream-copy y extracción a MP3).
    - Normalización de sonoridad profesional (EBU R128 loudnorm para audio y video).
    - Fusión / Unión de múltiples archivos multimedia con fallback inteligente.
    - Manejo exhaustivo de errores (401, 400, 404, 500, 504).
    """

    def setUp(self):
        self.app = app
        self.client = self.app.test_client()

    def _login(self, username="admin", role="admin"):
        with self.client.session_transaction() as sess:
            sess["username"] = username
            sess["user_id"] = username
            sess["role"] = role

    # ==================== 1. AUTENTICACIÓN ====================
    def test_auth_required(self):
        """Rechaza peticiones anónimas con 401."""
        res = self.client.post("/api/studio/process", json={"tool": "convert"})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn("error", data)

    # ==================== 2. CONVERSIÓN DE FORMATOS ====================
    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=5242880)
    def test_convert_video_to_mp3(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Conversión de video a MP3 con tasa de bits personalizada y descarte de video (-vn)."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        payload = {
            "tool": "convert",
            "source_filename": "clip.mp4",
            "target_format": "mp3",
            "audio_bitrate": "192k"
        }
        res = self.client.post("/api/studio/process", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["filename"].endswith(".mp3"))
        self.assertIn("job_id", data)

        # Verificar parámetros exactos enviados a FFmpeg
        called_args = mock_run.call_args[0][0]
        self.assertIn("-vn", called_args)
        self.assertIn("libmp3lame", called_args)
        self.assertIn("192k", called_args)

    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=1024000)
    def test_convert_audio_formats(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Conversión a otros formatos de audio: FLAC, WAV, M4A, Opus, OGG."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        format_codecs = {
            "flac": "flac",
            "wav": "pcm_s16le",
            "m4a": "aac",
            "opus": "libopus",
            "ogg": "libvorbis"
        }

        for target_fmt, expected_codec in format_codecs.items():
            payload = {
                "tool": "convert",
                "source_filename": "track.mp3",
                "target_format": target_fmt
            }
            res = self.client.post("/api/studio/process", json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["success"])
            self.assertTrue(data["filename"].endswith(f".{target_fmt}"))

            called_args = mock_run.call_args[0][0]
            self.assertIn(expected_codec, called_args)

    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=10240000)
    def test_convert_video_formats(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Conversión a formatos de video: MP4, MKV, WebM, AVI."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        video_codecs = {
            "mp4": "libx264",
            "mkv": "libx264",
            "webm": "libvpx-vp9",
            "avi": "libxvid"
        }

        for target_fmt, expected_codec in video_codecs.items():
            payload = {
                "tool": "convert",
                "source_filename": "input_video.mov",
                "target_format": target_fmt
            }
            res = self.client.post("/api/studio/process", json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["success"])
            self.assertTrue(data["filename"].endswith(f".{target_fmt}"))

            called_args = mock_run.call_args[0][0]
            self.assertIn(expected_codec, called_args)

    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=2048000)
    def test_convert_video_to_gif(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Generación de GIF animado con paleta optimizada, tiempo de inicio y duración."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        payload = {
            "tool": "convert",
            "source_filename": "scene.mp4",
            "target_format": "gif",
            "start_time": "00:01:20",
            "duration": "6"
        }
        res = self.client.post("/api/studio/process", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["filename"].endswith(".gif"))

        called_args = mock_run.call_args[0][0]
        self.assertIn("-ss", called_args)
        self.assertIn("00:01:20", called_args)
        self.assertIn("-t", called_args)
        self.assertIn("6", called_args)
        filter_arg = next(arg for arg in called_args if "palettegen" in arg)
        self.assertIn("paletteuse", filter_arg)

    # ==================== 3. COMPRESIÓN INTELIGENTE ====================
    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=15000000)
    def test_compress_video_profiles(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Prueba los perfiles de compresión: whatsapp_16, whatsapp_25 y discord."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        # 1. WhatsApp 16MB (720p, crf 28, audio 96k)
        res1 = self.client.post("/api/studio/process", json={
            "tool": "compress",
            "source_filename": "heavy_video.mp4",
            "profile": "whatsapp_16"
        })
        self.assertEqual(res1.status_code, 200)
        args1 = mock_run.call_args[0][0]
        self.assertIn("scale=-2:720", args1)
        self.assertIn("28", args1)
        self.assertIn("96k", args1)

        # 2. WhatsApp 25MB (1080p, crf 26, audio 128k)
        res2 = self.client.post("/api/studio/process", json={
            "tool": "compress",
            "source_filename": "heavy_video.mp4",
            "profile": "whatsapp_25"
        })
        self.assertEqual(res2.status_code, 200)
        args2 = mock_run.call_args[0][0]
        self.assertIn("scale=-2:1080", args2)
        self.assertIn("26", args2)

        # 3. Discord (crf 25, aac 128k)
        res3 = self.client.post("/api/studio/process", json={
            "tool": "compress",
            "source_filename": "heavy_video.mp4",
            "profile": "discord"
        })
        self.assertEqual(res3.status_code, 200)
        args3 = mock_run.call_args[0][0]
        self.assertIn("25", args3)
        self.assertIn("128k", args3)

    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=2048000)
    def test_compress_audio_file(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Compresión inteligente aplicada a un archivo de audio (reduce bitrate MP3)."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        res = self.client.post("/api/studio/process", json={
            "tool": "compress",
            "source_filename": "podcast_raw.wav",
            "profile": "whatsapp_16"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["filename"].endswith(".mp3"))

        args = mock_run.call_args[0][0]
        self.assertIn("-vn", args)
        self.assertIn("64k", args)
        self.assertIn("libmp3lame", args)

    # ==================== 4. RECORTES (TRIM) ====================
    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=3145728)
    def test_trim_lossless_stream_copy(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Recorte lossless sin re-codificación (-c copy)."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        payload = {
            "tool": "trim",
            "source_filename": "stream.mp4",
            "start_time": "00:00:15",
            "end_time": "00:01:45",
            "extract_audio": False
        }
        res = self.client.post("/api/studio/process", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["filename"].endswith(".mp4"))

        args = mock_run.call_args[0][0]
        self.assertIn("-ss", args)
        self.assertIn("00:00:15", args)
        self.assertIn("-to", args)
        self.assertIn("00:01:45", args)
        self.assertIn("-c", args)
        self.assertIn("copy", args)

    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=2048000)
    def test_trim_extract_audio_variations(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Verifica que extract_audio booleano y string ('1', '0', 'true', 'false') se evalúen fielmente."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        # Caso A: extract_audio=True -> extrae audio en MP3
        res_a = self.client.post("/api/studio/process", json={
            "tool": "trim",
            "source_filename": "video.mp4",
            "start_time": "00:00:10",
            "extract_audio": True
        })
        self.assertEqual(res_a.status_code, 200)
        self.assertTrue(res_a.get_json()["filename"].endswith(".mp3"))
        args_a = mock_run.call_args[0][0]
        self.assertIn("-vn", args_a)
        self.assertIn("libmp3lame", args_a)

        # Caso B: extract_audio='0' (enviado por FormData) -> NO debe extraer audio
        res_b = self.client.post("/api/studio/process", data={
            "tool": "trim",
            "source_filename": "video.mp4",
            "start_time": "00:00:10",
            "extract_audio": "0"
        })
        self.assertEqual(res_b.status_code, 200)
        self.assertTrue(res_b.get_json()["filename"].endswith(".mp4"))
        args_b = mock_run.call_args[0][0]
        self.assertIn("copy", args_b)

        # Caso C: extract_audio='1' -> extrae audio en MP3
        res_c = self.client.post("/api/studio/process", data={
            "tool": "trim",
            "source_filename": "video.mp4",
            "start_time": "00:00:10",
            "extract_audio": "1"
        })
        self.assertEqual(res_c.status_code, 200)
        self.assertTrue(res_c.get_json()["filename"].endswith(".mp3"))

    # ==================== 5. NORMALIZACIÓN DE SONORIDAD (EBU R128) ====================
    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=4194304)
    def test_normalize_audio_and_video(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Normalización EBU R128 loudnorm para audios y videos."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        # Audio
        res_audio = self.client.post("/api/studio/process", json={
            "tool": "normalize",
            "source_filename": "song.mp3"
        })
        self.assertEqual(res_audio.status_code, 200)
        args_audio = mock_run.call_args[0][0]
        self.assertIn("loudnorm=I=-14:TP=-1.5:LRA=11", args_audio)
        self.assertIn("libmp3lame", args_audio)

        # Video (mantiene video -c:v copy y normaliza audio)
        res_video = self.client.post("/api/studio/process", json={
            "tool": "normalize",
            "source_filename": "movie_clip.mp4"
        })
        self.assertEqual(res_video.status_code, 200)
        args_video = mock_run.call_args[0][0]
        self.assertIn("-c:v", args_video)
        self.assertIn("copy", args_video)
        self.assertIn("loudnorm=I=-14:TP=-1.5:LRA=11", args_video)
        self.assertIn("aac", args_video)

    # ==================== 6. FUSIÓN / UNIÓN DE ARCHIVOS (MERGE) ====================
    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=8388608)
    def test_merge_success_and_fallback(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Unión de archivos con lista de orden y verificación de fallback en códec mismatch."""
        self._login()
        # Primer llamado exitoso (-c copy)
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        payload = {
            "tool": "merge",
            "files": ["part1.mp4", "part2.mp4", "part3.mp4"],
            "output_format": "mp4"
        }
        res = self.client.post("/api/studio/process", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("union_3_archivos", data["filename"])

        # Caso con fallback: -c copy falla (returncode=1), debe reintentar con re-codificación
        mock_fail = MagicMock(returncode=1, stderr="Codec mismatch")
        mock_success = MagicMock(returncode=0, stderr="")
        mock_run.side_effect = [mock_fail, mock_success]

        res_fallback = self.client.post("/api/studio/process", json=payload)
        self.assertEqual(res_fallback.status_code, 200)
        self.assertEqual(mock_run.call_count, 3)  # 1 del test anterior + 2 del fallback

    def test_merge_validation_errors(self):
        """Valida que menos de 2 archivos devuelva error 400 y archivos inexistentes 404."""
        self._login()

        # Menos de 2 archivos
        res1 = self.client.post("/api/studio/process", json={
            "tool": "merge",
            "files": ["single_file.mp4"]
        })
        self.assertEqual(res1.status_code, 400)
        self.assertIn("al menos 2 archivos", res1.get_json()["error"])

        # Archivo inexistente
        with patch("os.path.exists", return_value=False):
            res2 = self.client.post("/api/studio/process", json={
                "tool": "merge",
                "files": ["nonexistent_a.mp4", "nonexistent_b.mp4"]
            })
            self.assertEqual(res2.status_code, 404)
            self.assertIn("no encontrado", res2.get_json()["error"])

    # ==================== 7. SUBIDA MULTIPART / FORM-DATA ====================
    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=1234567)
    def test_upload_file_multipart_processing(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Simula la subida de un archivo físico vía multipart/form-data y su procesamiento directo."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        fake_file_bytes = io.BytesIO(b"FAKE_RAW_MEDIA_BYTES_HEADER")
        data = {
            "tool": "convert",
            "target_format": "mp3",
            "audio_bitrate": "320k",
            "file": (fake_file_bytes, "mi_cancion_subida.wav")
        }

        res = self.client.post(
            "/api/studio/process",
            data=data,
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 200)
        res_data = res.get_json()
        self.assertTrue(res_data["success"])
        self.assertIn("mi_cancion_subida_convert.mp3", res_data["filename"])

        # Verificar que se guardó en metadatos el nombre original subido
        self.assertTrue(mock_save.called)
        saved_dict = mock_save.call_args[0][0]
        meta_entry = list(saved_dict.values())[-1]
        self.assertEqual(meta_entry["source_file"], "mi_cancion_subida.wav")

    # ==================== 8. MANEJO DE ERRORES Y EXCEPCIONES ====================
    def test_missing_source_file_and_no_upload(self):
        """Retorna 400 si no se proporciona ni archivo de origen ni subida."""
        self._login()
        res = self.client.post("/api/studio/process", json={"tool": "convert"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Debe seleccionar un archivo", res.get_json()["error"])

    @patch("os.path.exists", return_value=False)
    def test_nonexistent_source_file_returns_404(self, mock_exists):
        """Retorna 404 si el archivo de origen no existe en el almacenamiento."""
        self._login()
        res = self.client.post("/api/studio/process", json={
            "tool": "convert",
            "source_filename": "fantasma.mp4"
        })
        self.assertEqual(res.status_code, 404)
        self.assertIn("no encontrado", res.get_json()["error"])

    @patch("routes.api.subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_ffmpeg_execution_failure_returns_500(self, mock_exists, mock_run):
        """Retorna 500 con detalle en stderr si FFmpeg falla durante la ejecución."""
        self._login()
        mock_proc = MagicMock(returncode=1, stderr="Invalid data found when processing input")
        mock_run.return_value = mock_proc

        res = self.client.post("/api/studio/process", json={
            "tool": "convert",
            "source_filename": "corrupt.mp4",
            "target_format": "mp3"
        })
        self.assertEqual(res.status_code, 500)
        self.assertIn("Invalid data found", res.get_json()["error"])

    @patch("routes.api.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=300))
    @patch("os.path.exists", return_value=True)
    def test_ffmpeg_timeout_returns_504(self, mock_exists, mock_run):
        """Retorna 504 si FFmpeg excede el límite de tiempo de 5 minutos."""
        self._login()
        res = self.client.post("/api/studio/process", json={
            "tool": "convert",
            "source_filename": "gigantic_file.mkv",
            "target_format": "mp4"
        })
        self.assertEqual(res.status_code, 504)
        self.assertIn("excedió el límite de tiempo", res.get_json()["error"])


    @patch("routes.api.check_user_storage_quota", return_value=(False, "Has alcanzado tu límite de cuota de almacenamiento (1.0 GB)."))
    def test_quota_exceeded_blocks_studio_process(self, mock_quota):
        """Valida que un usuario que excedió su cuota de almacenamiento no pueda procesar archivos (403)."""
        self._login()
        res = self.client.post("/api/studio/process", json={
            "tool": "convert",
            "source_filename": "video.mp4"
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("Has alcanzado tu límite de cuota", res.get_json()["error"])

    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=5000)
    @patch("os.remove")
    def test_uploaded_file_cleaned_up_after_processing(self, mock_remove, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Verifica que el archivo temporal subido por el usuario se elimine tras el procesamiento para no malgastar cuota."""
        self._login()
        mock_proc = MagicMock(returncode=0, stderr="")
        mock_run.return_value = mock_proc

        data = {
            "tool": "convert",
            "target_format": "mp3",
            "file": (io.BytesIO(b"DUMMY_DATA"), "sample.wav")
        }
        res = self.client.post("/api/studio/process", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        # os.remove debe haber sido invocado para eliminar el source_path temporal
        self.assertTrue(mock_remove.called)


if __name__ == "__main__":
    unittest.main()
