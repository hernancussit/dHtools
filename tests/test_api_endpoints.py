import unittest
from unittest.mock import patch
from app import app


class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()

    @patch("routes.api.enqueue_job")
    @patch("routes.api.validate_media_url", return_value={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "platform": "youtube"})
    def test_api_download_with_clipping(self, mock_val, mock_enq):
        """Verifica que /api/download procese correctamente recorte con parse_time_to_seconds sin NameError."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        payload = {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "quality": "best",
            "format_type": "video",
            "start_time": "00:10",
            "end_time": "00:45"
        }
        res = self.client.post("/api/download", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("job_id", data)
        self.assertTrue(mock_enq.called)

    def test_recent_downloads_endpoint(self):
        """Verifica que /api/recent-downloads se ejecute sin NameError con time."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        res = self.client.get("/api/recent-downloads")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn("items", data)

    @patch("routes.admin.load_downloads_meta")
    def test_admin_user_downloads_endpoint(self, mock_meta):
        """Verifica que el admin pueda obtener el historial de descargas de un usuario con fecha/hora."""
        mock_meta.return_value = {
            "job123": {
                "job_id": "job123",
                "filename": "video_test.mp4",
                "username": "tester",
                "size_bytes": 1048576,
                "created_at": 1700000000.0,
                "folder_name": "Mi Coleccion",
                "group_id": "grp1"
            }
        }
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        with patch("routes.admin.load_users", return_value={"tester": {"role": "downloader"}}):
            res = self.client.get("/api/admin/users/tester/downloads")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("total_count"), 1)
            self.assertEqual(len(data.get("downloads")), 1)
            dl = data["downloads"][0]
            self.assertEqual(dl["job_id"], "job123")
            self.assertEqual(dl["filename"], "video_test.mp4")
            self.assertIn("created_at_formatted", dl)
            self.assertNotEqual(dl["created_at_formatted"], "Desconocida")
            self.assertEqual(dl["folder_name"], "Mi Coleccion")

    @patch("routes.admin.delete_download_meta")
    @patch("routes.admin.load_downloads_meta")
    def test_admin_user_delete_download(self, mock_load, mock_del):
        """Verifica que el admin pueda eliminar una descarga específica de un usuario."""
        mock_load.return_value = {
            "job999": {
                "job_id": "job999",
                "filename": "delete_me.mp4",
                "username": "tester",
                "size_bytes": 500
            }
        }
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        res = self.client.delete("/api/admin/users/tester/downloads/job999")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        mock_del.assert_called_once_with("job999")

    @patch("routes.api.enqueue_job")
    @patch("routes.api.validate_media_url", return_value=True)
    def test_download_strips_playlist_when_unchecked(self, mock_val, mock_enq):
        """Verifica que si playlist=False, una URL con list=RD... se limpie y solo descargue el video individual."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        payload = {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ&start_radio=1",
            "quality": "best",
            "format_type": "video",
            "playlist": False
        }
        res = self.client.post("/api/download", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(mock_enq.called)
        # Check args passed to enqueue_job(job_id, job_spec)
        call_args = mock_enq.call_args[0]
        job_spec = call_args[1]
        called_url = job_spec["url"]
        called_playlist_mode = job_spec["playlist"]
        self.assertEqual(called_playlist_mode, False)
        self.assertNotIn("list=", called_url)
        self.assertNotIn("start_radio=1", called_url)
        self.assertIn("v=dQw4w9WgXcQ", called_url)

    @patch("routes.api.enqueue_job")
    @patch("routes.api.validate_media_url", return_value=True)
    def test_download_keeps_playlist_when_checked(self, mock_val, mock_enq):
        """Verifica que si playlist=True, la URL conserve la lista y playlist_mode=True."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        payload = {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL12345678",
            "quality": "best",
            "format_type": "video",
            "playlist": True
        }
        res = self.client.post("/api/download", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(mock_enq.called)
        call_args = mock_enq.call_args[0]
        job_spec = call_args[1]
        called_url = job_spec["url"]
        called_playlist_mode = job_spec["playlist"]
        self.assertEqual(called_playlist_mode, True)
        self.assertIn("list=PL12345678", called_url)

    @patch("routes.api.enqueue_job")
    @patch("routes.api.validate_media_url", return_value=True)
    def test_download_non_youtube_services_unaffected(self, mock_val, mock_enq):
        """Verifica que Instagram, Twitch, Deezer, TikTok no se alteren con los cambios de playlist."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        urls_to_test = [
            "https://www.instagram.com/reel/C8xyz123/",
            "https://www.twitch.tv/videos/123456789",
            "https://www.deezer.com/track/987654321",
            "https://www.tiktok.com/@user/video/1234567890"
        ]

        for test_url in urls_to_test:
            mock_enq.reset_mock()
            payload = {
                "url": test_url,
                "quality": "best",
                "format_type": "video",
                "playlist": False
            }
            res = self.client.post("/api/download", json=payload)
            self.assertEqual(res.status_code, 200)
            self.assertTrue(mock_enq.called)
            job_spec = mock_enq.call_args[0][1]
            self.assertEqual(job_spec["url"], test_url)
            self.assertEqual(job_spec["playlist"], False)

    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=1024)
    def test_media_studio_process_convert(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Verifica que /api/studio/process procese una conversión con ffmpeg y retorne la descarga."""
        mock_proc = unittest.mock.MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        payload = {
            "tool": "convert",
            "source_filename": "test_video.mp4",
            "target_format": "mp3",
            "audio_bitrate": "320k"
        }
        res = self.client.post("/api/studio/process", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("job_id", data)
        self.assertTrue(data["download_url"].startswith("/api/files/"))
        self.assertTrue(mock_run.called)

    @patch("routes.auth.load_users")
    @patch("routes.auth.save_users")
    @patch("routes.auth.check_auth")
    def test_user_change_password(self, mock_check, mock_save, mock_load):
        """Verifica el endpoint /api/user/change-password con validaciones de contraseña."""
        mock_check.return_value = True
        mock_load.return_value = {"testuser": {"password_hash": "oldhash", "role": "downloader"}}

        with self.client.session_transaction() as sess:
            sess["username"] = "testuser"
            sess["role"] = "downloader"

        # 1. Contraseña muy corta
        res = self.client.post("/api/user/change-password", json={
            "current_password": "currentpass",
            "new_password": "123"
        })
        self.assertEqual(res.status_code, 400)

        # 2. Contraseña actual incorrecta
        mock_check.return_value = False
        res = self.client.post("/api/user/change-password", json={
            "current_password": "wrongpass",
            "new_password": "newsecretpassword123"
        })
        self.assertEqual(res.status_code, 403)

        # 3. Éxito
        mock_check.return_value = True
        res = self.client.post("/api/user/change-password", json={
            "current_password": "correctpass",
            "new_password": "newsecretpassword123"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertTrue(mock_save.called)

    @patch("routes.api.subprocess.run")
    @patch("routes.api.load_downloads_meta", return_value={})
    @patch("core.utils.save_downloads_meta")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=2048)
    def test_media_studio_process_merge(self, mock_size, mock_exists, mock_save, mock_meta, mock_run):
        """Verifica que /api/studio/process con tool=merge concatene 2 o más archivos correctamente."""
        mock_proc = unittest.mock.MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["user_id"] = "admin"
            sess["role"] = "admin"

        # 1. Menos de 2 archivos falla
        res = self.client.post("/api/studio/process", json={
            "tool": "merge",
            "files": ["part1.mp3"]
        })
        self.assertEqual(res.status_code, 400)

        # 2. Unión exitosa de 2 archivos
        payload = {
            "tool": "merge",
            "files": ["part1.mp3", "part2.mp3"],
            "output_format": "mp3"
        }
        res = self.client.post("/api/studio/process", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("job_id", data)
        self.assertTrue(data["download_url"].startswith("/api/files/"))
        self.assertTrue(mock_run.called)


if __name__ == "__main__":
    unittest.main()
