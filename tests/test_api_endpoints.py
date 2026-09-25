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


if __name__ == "__main__":
    unittest.main()
