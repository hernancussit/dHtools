import unittest
from unittest.mock import patch, MagicMock
from app import app
from core.downloader import search_youtube, search_deezer, search_soundcloud, search_media, format_views


class TestSearchApi(unittest.TestCase):
    """
    Suite de pruebas para el Buscador Multimedia Integrado (Roadmap v2.0.0):
    - Validaciones de entrada y límites.
    - Extracción y mapeo de YouTube, Deezer y SoundCloud.
    - Combinación multicanal inteligente.
    - Endpoint REST /api/search y autenticación.
    """

    def setUp(self):
        self.app = app
        self.client = self.app.test_client()

    def _login(self, username="admin", role="admin"):
        with self.client.session_transaction() as sess:
            sess["username"] = username
            sess["user_id"] = username
            sess["role"] = role

    # ==================== 1. FORMATO DE VISTAS ====================
    def test_format_views(self):
        self.assertIsNone(format_views(None))
        self.assertIsNone(format_views(0))
        self.assertEqual(format_views(500), "500 vistas")
        self.assertEqual(format_views(1500), "1.5K vistas")
        self.assertEqual(format_views(2500000), "2.5M vistas")
        self.assertEqual(format_views(1200000000), "1.2B vistas")

    # ==================== 2. AUTENTICACIÓN Y VALIDACIONES ====================
    def test_search_unauthenticated_returns_401(self):
        res = self.client.get("/api/search?q=coldplay")
        self.assertEqual(res.status_code, 401)
        self.assertIn("error", res.get_json())

    def test_search_missing_query_returns_400(self):
        self._login()
        res = self.client.get("/api/search")
        self.assertEqual(res.status_code, 400)
        self.assertIn("término de búsqueda", res.get_json()["error"])

    def test_search_empty_query_returns_400(self):
        self._login()
        res = self.client.get("/api/search?q=   ")
        self.assertEqual(res.status_code, 400)
        self.assertIn("término de búsqueda", res.get_json()["error"])

    def test_search_query_too_long_returns_400(self):
        self._login()
        long_q = "a" * 257
        res = self.client.get(f"/api/search?q={long_q}")
        self.assertEqual(res.status_code, 400)
        self.assertIn("demasiado extenso", res.get_json()["error"])

    # ==================== 3. EXTRACCIÓN Y MAPEO ====================
    @patch("yt_dlp.YoutubeDL")
    def test_search_youtube_extractor(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "entries": [
                {
                    "id": "dQw4w9WgXcQ",
                    "title": "Rick Astley - Never Gonna Give You Up",
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "uploader": "Rick Astley",
                    "duration": 213,
                    "view_count": 1400000000,
                    "thumbnails": [{"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"}]
                }
            ]
        }
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        items = search_youtube("rick astley", limit=1)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "dQw4w9WgXcQ")
        self.assertEqual(item["title"], "Rick Astley - Never Gonna Give You Up")
        self.assertEqual(item["duration_formatted"], "03:33")
        self.assertEqual(item["platform"], "youtube")
        self.assertEqual(item["views_formatted"], "1.4B vistas")

    @patch("requests.get")
    def test_search_deezer_extractor(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": 12345,
                    "title": "Fix You",
                    "artist": {"name": "Coldplay"},
                    "album": {"title": "X&Y", "cover_medium": "https://e-cdns-images.dzcdn.net/cover.jpg"},
                    "duration": 295,
                    "link": "https://www.deezer.com/track/12345",
                    "preview": "https://cdnt-preview.dzcdn.net/sample.mp3"
                }
            ]
        }
        mock_get.return_value = mock_resp

        items = search_deezer("coldplay fix you", limit=1)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "12345")
        self.assertEqual(item["title"], "Coldplay - Fix You")
        self.assertEqual(item["artist"], "Coldplay")
        self.assertEqual(item["album"], "X&Y")
        self.assertEqual(item["duration_formatted"], "04:55")
        self.assertEqual(item["platform"], "deezer")
        self.assertEqual(item["preview_url"], "https://cdnt-preview.dzcdn.net/sample.mp3")

    @patch("yt_dlp.YoutubeDL")
    def test_search_soundcloud_extractor(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "entries": [
                {
                    "id": 999,
                    "title": "Remix Track",
                    "url": "https://soundcloud.com/artist/remix",
                    "uploader": "DJ Producer",
                    "duration": 180,
                    "thumbnails": [{"url": "https://i1.sndcdn.com/artworks.jpg"}]
                }
            ]
        }
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        items = search_soundcloud("remix", limit=1)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["platform"], "soundcloud")
        self.assertEqual(item["title"], "Remix Track")

    @patch("core.downloader.search_youtube")
    @patch("core.downloader.search_deezer")
    def test_search_media_router(self, mock_dz, mock_yt):
        mock_yt.return_value = [{"id": "yt1", "platform": "youtube"}, {"id": "yt2", "platform": "youtube"}]
        mock_dz.return_value = [{"id": "dz1", "platform": "deezer"}, {"id": "dz2", "platform": "deezer"}]

        # Canal combinado
        res_all = search_media("query", platform="all", limit=4)
        self.assertEqual(len(res_all), 4)
        # Intercalado
        self.assertEqual(res_all[0]["platform"], "youtube")
        self.assertEqual(res_all[1]["platform"], "deezer")
        self.assertEqual(res_all[2]["platform"], "youtube")
        self.assertEqual(res_all[3]["platform"], "deezer")

    # ==================== 4. ENDPOINT HTTP /api/search ====================
    @patch("routes.api.search_media")
    def test_api_media_search_endpoint(self, mock_search):
        mock_search.return_value = [
            {"id": "v1", "title": "Result 1", "platform": "youtube"},
            {"id": "v2", "title": "Result 2", "platform": "deezer"},
        ]
        self._login()

        res = self.client.get("/api/search?q=dua+lipa&platform=all&limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["query"], "dua lipa")
        self.assertEqual(data["platform"], "all")
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["results"]), 2)
        mock_search.assert_called_with("dua lipa", platform="all", limit=5)

    @patch("routes.api.search_media", side_effect=Exception("Timeout en servicio de búsqueda"))
    def test_api_media_search_error_handling(self, mock_search):
        self._login()
        res = self.client.get("/api/search?q=test")
        self.assertEqual(res.status_code, 500)
        data = res.get_json()
        self.assertIn("Fallo al buscar multimedia", data["error"])


if __name__ == "__main__":
    unittest.main()
