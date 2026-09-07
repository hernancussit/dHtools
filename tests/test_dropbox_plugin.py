"""
Test suite de verificación para el Plugin Oficial de Dropbox (plugins/dropbox/)
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.plugin_manager import PluginManager
from plugins.dropbox.plugin import Plugin as DropboxPlugin
from plugins.dropbox import dropbox_client


class TestDropboxPlugin(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="dhtools_test_dropbox_")
        self.manager = PluginManager()
        self.plugin = DropboxPlugin(
            manager=self.manager,
            metadata={"id": "dropbox", "name": "Dropbox Cloud Sync", "version": "1.0.0"}
        )
        self.plugin.users_data_dir = os.path.join(self.test_dir, "users_data")
        os.makedirs(self.plugin.users_data_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_plugin_discovery_and_metadata(self):
        """Verifica que PluginManager descubra y cargue la metadata de Dropbox."""
        self.manager.discover_and_load_plugins()
        discovered = self.manager._plugins
        self.assertIn("dropbox", discovered)
        meta = discovered["dropbox"]
        self.assertEqual(meta.get("id"), "dropbox")
        self.assertEqual(meta.get("icon"), "📦")
        self.assertEqual(meta.get("settings_url"), "/plugin/dropbox/settings")

    def test_multi_user_isolation(self):
        """Verifica que las configuraciones y tokens de Dropbox estén estrictamente aislados entre usuarios."""
        # Alice
        self.plugin.save_user_config("alice", {
            "enabled": True,
            "auto_upload": True,
            "folder_path": "/Alice/Media",
            "oauth": {"app_key": "key-alice-123"}
        })
        self.plugin.save_user_token("alice", {"access_token": "token-alice", "expires_at": time.time() + 3600})

        # Bob
        self.plugin.save_user_config("bob", {
            "enabled": False,
            "auto_upload": False,
            "folder_path": "/Bob/Files",
            "oauth": {"app_key": "key-bob-456"}
        })
        self.plugin.save_user_token("bob", {"access_token": "token-bob", "expires_at": time.time() + 3600})

        res_alice = self.plugin.get_user_config("alice")
        res_bob = self.plugin.get_user_config("bob")

        self.assertTrue(res_alice["enabled"])
        self.assertEqual(res_alice["folder_path"], "/Alice/Media")
        self.assertEqual(self.plugin.get_user_token("alice")["access_token"], "token-alice")

        self.assertFalse(res_bob["enabled"])
        self.assertEqual(res_bob["folder_path"], "/Bob/Files")
        self.assertEqual(self.plugin.get_user_token("bob")["access_token"], "token-bob")

    def test_get_download_cloud_option(self):
        """Verifica que get_download_cloud_option reporte el estado preciso para Web y Telegram."""
        # Alice activa
        self.plugin.save_user_config("alice", {"enabled": True, "auto_upload": True})
        self.plugin.save_user_token("alice", {"access_token": "tok_dropbox_123"})
        opt_alice = self.plugin.get_download_cloud_option("alice")
        self.assertTrue(opt_alice["enabled"])
        self.assertTrue(opt_alice["auto_upload"])
        self.assertIn("ACTIVO", opt_alice["status_label"])

        # Bob inactivo
        opt_bob = self.plugin.get_download_cloud_option("bob")
        self.assertFalse(opt_bob["enabled"])
        self.assertEqual(opt_bob["status_label"], "NO VINCULADO")

    def test_get_user_nav_item(self):
        """Verifica la generación del enlace de navegación para la barra lateral."""
        nav = self.plugin.get_user_nav_item()
        self.assertEqual(nav["id"], "dropbox")
        self.assertEqual(nav["icon"], "📦")
        self.assertEqual(nav["url"], "/plugin/dropbox/settings")

    def test_client_authorization_url(self):
        """Verifica la construcción de la URL de autorización de Dropbox con token_access_type=offline."""
        url = dropbox_client.get_authorization_url(
            app_key="my_app_key",
            redirect_uri="https://dhtools.local/callback",
            state="state_xyz"
        )
        self.assertIn("https://www.dropbox.com/oauth2/authorize", url)
        self.assertIn("client_id=my_app_key", url)
        self.assertIn("token_access_type=offline", url)
        self.assertIn("state=state_xyz", url)

    @patch("requests.post")
    def test_client_exchange_code_for_token(self, mock_post):
        """Verifica el canje de código por token de acceso y refresco de Dropbox."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "dropbox_access_token_123",
            "refresh_token": "dropbox_refresh_token_456",
            "account_id": "dbid:AAAHZ",
            "expires_in": 14400
        }
        mock_post.return_value = mock_resp

        ok, data = dropbox_client.exchange_code_for_token(
            app_key="my_key",
            app_secret="my_sec",
            code="code123",
            redirect_uri="https://dhtools.local/callback"
        )
        self.assertTrue(ok)
        self.assertEqual(data["access_token"], "dropbox_access_token_123")
        self.assertEqual(data["refresh_token"], "dropbox_refresh_token_456")
        self.assertGreater(data["expires_at"], time.time())

    @patch("requests.post")
    def test_client_token_refresh_when_expired(self, mock_post):
        """Verifica la renovación automática del token cuando caduca."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_refreshed_dropbox_token",
            "expires_in": 14400
        }
        mock_post.return_value = mock_resp

        old_token = {
            "access_token": "expired_token",
            "refresh_token": "my_refresh_token",
            "expires_at": time.time() - 100
        }

        ok, new_data, was_refreshed = dropbox_client.refresh_token_if_needed(
            app_key="key",
            app_secret="sec",
            token_data=old_token
        )
        self.assertTrue(ok)
        self.assertTrue(was_refreshed)
        self.assertEqual(new_data["access_token"], "new_refreshed_dropbox_token")
        self.assertEqual(new_data["refresh_token"], "my_refresh_token")

    @patch("requests.post")
    def test_get_account_and_space_info(self, mock_post):
        """Verifica la consulta de perfil y cuota en Dropbox."""
        resp_acc = MagicMock()
        resp_acc.status_code = 200
        resp_acc.json.return_value = {
            "name": {"display_name": "Hernán Cussit"},
            "email": "hernan@dropbox.test",
            "account_id": "dbid:123"
        }

        resp_space = MagicMock()
        resp_space.status_code = 200
        resp_space.json.return_value = {
            "used": 2147483648,  # 2 GB
            "allocation": {
                ".tag": "individual",
                "allocated": 10737418240  # 10 GB
            }
        }

        mock_post.side_effect = [resp_acc, resp_space]

        ok, info = dropbox_client.get_account_and_space_info("valid_token")
        self.assertTrue(ok)
        self.assertEqual(info["display_name"], "Hernán Cussit")
        self.assertEqual(info["email"], "hernan@dropbox.test")
        self.assertEqual(info["quota_used"], 2147483648)
        self.assertEqual(info["quota_total"], 10737418240)
        self.assertEqual(info["quota_remaining"], 8589934592)

    @patch("plugins.dropbox.dropbox_client.create_shared_link")
    @patch("requests.post")
    def test_upload_small_file_resumable(self, mock_post, mock_link):
        """Verifica la subida atómica directa para archivos menores a 4 MB."""
        dummy_path = os.path.join(self.test_dir, "small_song.mp3")
        with open(dummy_path, "wb") as f:
            f.write(b"0" * 1024 * 80)  # 80 KB

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "id:small123",
            "name": "small_song.mp3",
            "path_display": "/dHtools/small_song.mp3",
            "size": 81920
        }
        mock_post.return_value = mock_resp
        mock_link.return_value = "https://www.dropbox.com/s/small123/small_song.mp3?dl=0"

        ok, res = dropbox_client.upload_file_resumable(
            access_token="fake_token",
            file_path=dummy_path,
            dropbox_folder="/dHtools"
        )

        self.assertTrue(ok)
        self.assertEqual(res["id"], "id:small123")
        self.assertEqual(res["web_link"], "https://www.dropbox.com/s/small123/small_song.mp3?dl=0")

    @patch("plugins.dropbox.dropbox_client.create_shared_link")
    @patch("requests.post")
    def test_upload_large_file_chunked_session(self, mock_post, mock_link):
        """Verifica la sesión upload_session (start, append_v2, finish) para archivos grandes."""
        large_path = os.path.join(self.test_dir, "large_video.mp4")
        # Archivo de 6 MB (supera CHUNK_SIZE de 4 MB)
        total_size = 6 * 1024 * 1024
        with open(large_path, "wb") as f:
            f.seek(total_size - 1)
            f.write(b"0")

        # Mock 1: upload_session/start
        start_resp = MagicMock()
        start_resp.status_code = 200
        start_resp.json.return_value = {"session_id": "sess_abc123"}

        # Mock 2: upload_session/finish (segundo bloque completa los 6 MB)
        finish_resp = MagicMock()
        finish_resp.status_code = 200
        finish_resp.json.return_value = {
            "id": "id:large999",
            "name": "large_video.mp4",
            "path_display": "/dHtools/large_video.mp4",
            "size": total_size
        }

        mock_post.side_effect = [start_resp, finish_resp]
        mock_link.return_value = "https://www.dropbox.com/s/large999/large_video.mp4?dl=0"

        progress_history = []
        def on_progress(pct, up, total):
            progress_history.append(pct)

        ok, res = dropbox_client.upload_file_resumable(
            access_token="fake_token",
            file_path=large_path,
            dropbox_folder="/dHtools",
            progress_callback=on_progress
        )

        self.assertTrue(ok)
        self.assertEqual(res["id"], "id:large999")
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(progress_history[-1], 100.0)

    @patch("plugins.dropbox.dropbox_client.upload_file_resumable")
    def test_upload_job_for_user_with_safe_offload(self, mock_upload):
        """Verifica la subida de una descarga con eliminación segura en disco (Safe Offload)."""
        dummy_media = os.path.join(self.test_dir, "job_dropbox_1.mp4")
        with open(dummy_media, "w") as f:
            f.write("content")

        mock_upload.return_value = (True, {"web_link": "https://www.dropbox.com/s/job1"})

        self.plugin.save_user_config("alice", {
            "enabled": True,
            "safe_offload": True,
            "oauth": {"app_key": "appkey123"}
        })
        self.plugin.save_user_token("alice", {"access_token": "token_alice", "expires_at": time.time() + 3600})

        from core.state import JOBS, JOBS_LOCK
        with JOBS_LOCK:
            JOBS["job_dbx_1"] = {
                "status": "finished",
                "filepath": dummy_media,
                "filename": "job_dropbox_1.mp4"
            }

        ok, res = self.plugin.upload_job_for_user("job_dbx_1", username="alice")
        self.assertTrue(ok)
        self.assertTrue(res["offloaded"])
        self.assertEqual(res["provider"], "dropbox")
        # El archivo local debe haberse borrado
        self.assertFalse(os.path.exists(dummy_media))

    @patch("plugins.dropbox.dropbox_client.upload_file_resumable")
    def test_upload_file_for_user_dispatcher(self, mock_upload):
        """Verifica que upload_file_for_user suba cualquier archivo arbitrario en disco a Dropbox."""
        dummy_file = os.path.join(self.test_dir, "backup.zip")
        with open(dummy_file, "w") as f:
            f.write("zip content")

        mock_upload.return_value = (True, {"id": "zip123", "web_link": "https://www.dropbox.com/s/zip123"})

        self.plugin.save_user_config("alice", {"enabled": True, "oauth": {"app_key": "ak"}})
        self.plugin.save_user_token("alice", {"access_token": "token_alice", "expires_at": time.time() + 3600})

        ok, res = self.plugin.upload_file_for_user(dummy_file, username="alice")
        self.assertTrue(ok)
        self.assertEqual(res["id"], "zip123")


if __name__ == "__main__":
    unittest.main()
