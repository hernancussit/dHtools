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


if __name__ == "__main__":
    unittest.main()
