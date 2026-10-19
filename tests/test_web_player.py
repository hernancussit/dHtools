import os
import unittest
from unittest.mock import patch
from app import app
from core.config import DOWNLOAD_DIR
from core.state import JOBS, JOBS_LOCK


class TestWebPlayerStreaming(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        # Create dummy media files (UUID-like hex job ID without underscores)
        self.test_job_id = "playerjob1234567890abcdef"
        self.test_filename = f"{self.test_job_id}_sample_music.mp3"
        self.test_filepath = os.path.join(DOWNLOAD_DIR, self.test_filename)
        with open(self.test_filepath, "wb") as f:
            f.write(b"ID3" + b"\x00" * 200 + b"AUDIO_DATA_PAYLOAD_TEST_BYTES" * 10)

        with JOBS_LOCK:
            JOBS[self.test_job_id] = {
                "id": self.test_job_id,
                "status": "finished",
                "filepath": self.test_filename,
                "filename": "sample_music.mp3",
                "owner": "admin",
            }

    def tearDown(self):
        if os.path.exists(self.test_filepath):
            try:
                os.remove(self.test_filepath)
            except OSError:
                pass
        with JOBS_LOCK:
            JOBS.pop(self.test_job_id, None)

    def test_stream_param_inline_disposition(self):
        """Verifica que con ?stream=1 o ?preview=1 Content-Disposition sea inline."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["role"] = "admin"

        res = self.client.get(f"/api/files/{self.test_job_id}?stream=1")
        self.assertEqual(res.status_code, 200)
        cd = res.headers.get("Content-Disposition", "")
        self.assertTrue("inline" in cd or "attachment" not in cd)
        self.assertIn("Accept-Ranges", res.headers)
        self.assertEqual(res.headers.get("Accept-Ranges"), "bytes")
        res.close()

    def test_download_param_attachment_disposition(self):
        """Verifica que sin stream el archivo se entregue como attachment para descarga."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["role"] = "admin"

        res = self.client.get(f"/api/files/{self.test_job_id}")
        self.assertEqual(res.status_code, 200)
        cd = res.headers.get("Content-Disposition", "")
        self.assertIn("attachment", cd)
        res.close()

    def test_http_range_request_partial_content(self):
        """Verifica que send_file con conditional=True responda 206 Partial Content en Range requests."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["role"] = "admin"

        headers = {"Range": "bytes=0-49"}
        res = self.client.get(f"/api/files/{self.test_job_id}?stream=1", headers=headers)
        self.assertEqual(res.status_code, 206)
        self.assertIn("Content-Range", res.headers)
        self.assertTrue(res.headers["Content-Range"].startswith("bytes 0-49/"))
        self.assertEqual(len(res.data), 50)
        res.close()

    def test_recent_downloads_media_metadata(self):
        """Verifica que /api/recent-downloads entregue metadatos enriquecidos para el reproductor web."""
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["role"] = "admin"

        res = self.client.get("/api/recent-downloads")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("items", data)

        # Buscar el archivo de prueba
        found = next((item for item in data["items"] if item["job_id"] == self.test_job_id), None)
        self.assertIsNotNone(found)
        self.assertTrue(found["is_audio"])
        self.assertFalse(found["is_video"])
        self.assertTrue(found["is_playable"])
        self.assertEqual(found["extension"], "mp3")
        self.assertEqual(found["stream_url"], f"/api/files/{self.test_job_id}?stream=1")

    @patch("routes.auth.load_users")
    def test_unauthorized_user_cannot_stream_other_user_file(self, mock_users):
        """Verifica que un usuario común no pueda reproducir ni transmitir archivos de otro usuario."""
        mock_users.return_value = {
            "bob": {"username": "bob", "role": "user", "status": "active"},
            "alice": {"username": "alice", "role": "user", "status": "active"}
        }

        with JOBS_LOCK:
            JOBS[self.test_job_id]["owner"] = "alice"

        with self.client.session_transaction() as sess:
            sess["username"] = "bob"
            sess["role"] = "user"

        res = self.client.get(f"/api/files/{self.test_job_id}?stream=1")
        self.assertEqual(res.status_code, 403)

    @patch("routes.ui.load_downloads_meta")
    def test_recent_downloads_folder_playable_count(self, mock_meta):
        """Verifica que las carpetas calculen playable_count para reproducción continua."""
        mock_meta.return_value = {
            self.test_job_id: {
                "job_id": self.test_job_id,
                "filename": "sample_music.mp3",
                "username": "admin",
                "folder_name": "Mi Playlist Test",
                "group_id": "test_group_456"
            }
        }
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["role"] = "admin"

        res = self.client.get("/api/recent-downloads")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        folders = data.get("folders", [])
        found_f = next((f for f in folders if f["group_id"] == "test_group_456"), None)
        self.assertIsNotNone(found_f)
        self.assertEqual(found_f["playable_count"], 1)


if __name__ == "__main__":
    unittest.main()
