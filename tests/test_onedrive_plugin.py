"""
Test suite de verificación para el Plugin Oficial de Microsoft OneDrive y SharePoint (plugins/onedrive/)
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
from plugins.onedrive.plugin import Plugin as OneDrivePlugin
from plugins.onedrive import onedrive_client


class TestOneDrivePlugin(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="dhtools_test_onedrive_")
        self.manager = PluginManager()
        self.plugin = OneDrivePlugin(
            manager=self.manager,
            metadata={"id": "onedrive", "name": "Microsoft OneDrive Cloud Sync", "version": "1.0.0"}
        )
        # Redirigir el users_data_dir a directorio temporal para no tocar producción
        self.plugin.users_data_dir = os.path.join(self.test_dir, "users_data")
        os.makedirs(self.plugin.users_data_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_plugin_discovery_and_metadata(self):
        """Verifica que el gestor de plugins descubra y cargue la metadata de OneDrive correctamente."""
        self.manager.discover_and_load_plugins()
        discovered = self.manager._plugins
        self.assertIn("onedrive", discovered)
        meta = discovered["onedrive"]
        self.assertEqual(meta.get("id"), "onedrive")
        self.assertEqual(meta.get("icon"), "☁️")
        self.assertEqual(meta.get("settings_url"), "/plugin/onedrive/settings")

    def test_multi_user_isolation(self):
        """Verifica que las configuraciones y tokens de diferentes usuarios estén estrictamente aislados."""
        # Configurar para alice
        cfg_alice = {
            "enabled": True,
            "auto_upload": True,
            "folder_path": "/Alice/Media",
            "oauth": {"client_id": "client-alice-123"}
        }
        self.plugin.save_user_config("alice", cfg_alice)
        self.plugin.save_user_token("alice", {"access_token": "token-alice", "expires_at": time.time() + 3600})

        # Configurar para bob
        cfg_bob = {
            "enabled": False,
            "auto_upload": False,
            "folder_path": "/Bob/Files",
            "oauth": {"client_id": "client-bob-456"}
        }
        self.plugin.save_user_config("bob", cfg_bob)
        self.plugin.save_user_token("bob", {"access_token": "token-bob", "expires_at": time.time() + 3600})

        # Comprobar lectura aislada
        res_alice = self.plugin.get_user_config("alice")
        res_bob = self.plugin.get_user_config("bob")

        self.assertTrue(res_alice["enabled"])
        self.assertEqual(res_alice["folder_path"], "/Alice/Media")
        self.assertEqual(self.plugin.get_user_token("alice")["access_token"], "token-alice")

        self.assertFalse(res_bob["enabled"])
        self.assertEqual(res_bob["folder_path"], "/Bob/Files")
        self.assertEqual(self.plugin.get_user_token("bob")["access_token"], "token-bob")

    def test_get_download_cloud_option(self):
        """Verifica que el contrato get_download_cloud_option retorne el estado correcto por usuario."""
        # Alice con token y activo
        self.plugin.save_user_config("alice", {"enabled": True, "auto_upload": True})
        self.plugin.save_user_token("alice", {"access_token": "tok123"})
        opt_alice = self.plugin.get_download_cloud_option("alice")
        self.assertTrue(opt_alice["enabled"])
        self.assertTrue(opt_alice["auto_upload"])
        self.assertIn("ACTIVO", opt_alice["status_label"])

        # Bob sin token
        opt_bob = self.plugin.get_download_cloud_option("bob")
        self.assertFalse(opt_bob["enabled"])
        self.assertEqual(opt_bob["status_label"], "NO VINCULADO")

    def test_get_user_nav_item(self):
        """Verifica que el acceso directo de navegación genere el enlace correcto."""
        nav = self.plugin.get_user_nav_item()
        self.assertEqual(nav["id"], "onedrive")
        self.assertEqual(nav["icon"], "☁️")
        self.assertEqual(nav["url"], "/plugin/onedrive/settings")

    def test_client_authorization_url(self):
        """Verifica la generación correcta de la URL de autorización de Microsoft."""
        url = onedrive_client.get_authorization_url(
            client_id="test-app-id",
            redirect_uri="https://dhtools.local/callback",
            state="state123",
            tenant="common"
        )
        self.assertIn("https://login.microsoftonline.com/common/oauth2/v2.0/authorize", url)
        self.assertIn("client_id=test-app-id", url)
        self.assertIn("state=state123", url)
        self.assertIn("scope=offline_access", url)

    @patch("requests.post")
    def test_client_exchange_code_for_token(self, mock_post):
        """Verifica el canje de código por token de acceso."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "mock_access_token_123",
            "refresh_token": "mock_refresh_token_456",
            "expires_in": 3600
        }
        mock_post.return_value = mock_resp

        ok, data = onedrive_client.exchange_code_for_token(
            client_id="cid",
            client_secret="sec",
            code="auth_code",
            redirect_uri="https://dhtools.local/callback"
        )
        self.assertTrue(ok)
        self.assertEqual(data["access_token"], "mock_access_token_123")
        self.assertEqual(data["refresh_token"], "mock_refresh_token_456")
        self.assertGreater(data["expires_at"], time.time())

    @patch("requests.post")
    def test_client_token_refresh_when_expired(self, mock_post):
        """Verifica la renovación automática del token si ha expirado."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_refreshed_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_resp

        old_token_data = {
            "access_token": "expired_token",
            "refresh_token": "valid_refresh_token",
            "expires_at": time.time() - 100  # Ya caducó
        }

        ok, new_data, was_refreshed = onedrive_client.refresh_token_if_needed(
            client_id="cid",
            client_secret="sec",
            token_data=old_token_data
        )
        self.assertTrue(ok)
        self.assertTrue(was_refreshed)
        self.assertEqual(new_data["access_token"], "new_refreshed_token")

    @patch("requests.get")
    def test_get_user_and_drive_info(self, mock_get):
        """Verifica la obtención consolidada de perfil y cuota de almacenamiento."""
        resp_me = MagicMock()
        resp_me.status_code = 200
        resp_me.json.return_value = {"displayName": "Hernán Cussit", "mail": "hernan@outlook.com"}

        resp_drive = MagicMock()
        resp_drive.status_code = 200
        resp_drive.json.return_value = {
            "id": "drive123",
            "driveType": "personal",
            "webUrl": "https://onedrive.live.com",
            "quota": {
                "total": 107374182400,
                "used": 10737418240,
                "remaining": 96636764160,
                "state": "normal"
            }
        }

        mock_get.side_effect = [resp_me, resp_drive]

        ok, info = onedrive_client.get_user_and_drive_info("valid_token")
        self.assertTrue(ok)
        self.assertEqual(info["display_name"], "Hernán Cussit")
        self.assertEqual(info["email"], "hernan@outlook.com")
        self.assertEqual(info["quota_total"], 107374182400)
        self.assertEqual(info["quota_used"], 10737418240)

    @patch("requests.put")
    def test_upload_small_file_resumable(self, mock_put):
        """Verifica la subida directa en un solo PUT para archivos menores a 4 MB."""
        dummy_path = os.path.join(self.test_dir, "small_video.mp4")
        with open(dummy_path, "wb") as f:
            f.write(b"0" * 1024 * 100)  # 100 KB

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "item_123",
            "name": "small_video.mp4",
            "size": 102400,
            "webUrl": "https://onedrive.live.com/view/item_123"
        }
        mock_put.return_value = mock_resp

        progress_calls = []
        def progress_cb(pct, up, total):
            progress_calls.append((pct, up, total))

        ok, res = onedrive_client.upload_file_resumable(
            access_token="fake_token",
            file_path=dummy_path,
            folder_path="/dHtools",
            progress_callback=progress_cb
        )

        self.assertTrue(ok)
        self.assertEqual(res["id"], "item_123")
        self.assertEqual(res["web_link"], "https://onedrive.live.com/view/item_123")
        self.assertEqual(len(progress_calls), 1)
        self.assertEqual(progress_calls[0][0], 100.0)

    @patch("requests.put")
    @patch("requests.post")
    def test_upload_large_file_chunked_session(self, mock_post, mock_put):
        """Verifica la creación de uploadSession y subida por fragmentos para archivos >= 4 MB."""
        large_path = os.path.join(self.test_dir, "large_movie.mp4")
        # Creamos un archivo de 5 MB
        total_size = 5 * 1024 * 1024
        with open(large_path, "wb") as f:
            f.seek(total_size - 1)
            f.write(b"0")

        # 1. Mock de creación de upload session
        session_resp = MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"uploadUrl": "https://graph.microsoft.com/upload_session_xyz"}
        mock_post.return_value = session_resp

        # 2. Mock de subida de fragmentos: primero 202 (intermedio), segundo 201 (final)
        chunk1_resp = MagicMock()
        chunk1_resp.status_code = 202

        chunk2_resp = MagicMock()
        chunk2_resp.status_code = 201
        chunk2_resp.json.return_value = {
            "id": "item_large_999",
            "name": "large_movie.mp4",
            "size": total_size,
            "webUrl": "https://onedrive.live.com/view/item_large_999"
        }

        mock_put.side_effect = [chunk1_resp, chunk2_resp]

        ok, res = onedrive_client.upload_file_resumable(
            access_token="fake_token",
            file_path=large_path,
            folder_path="/dHtools"
        )

        self.assertTrue(ok)
        self.assertEqual(res["id"], "item_large_999")
        self.assertEqual(mock_put.call_count, 2)
        # Comprobar que el header Content-Range fue enviado correctamente
        first_call_headers = mock_put.call_args_list[0][1]["headers"]
        self.assertIn("Content-Range", first_call_headers)
        self.assertTrue(first_call_headers["Content-Range"].startswith("bytes 0-"))

    @patch("plugins.onedrive.onedrive_client.upload_file_resumable")
    def test_upload_job_for_user_with_safe_offload(self, mock_upload):
        """Verifica la subida de un job y la ejecución segura de Safe Offload."""
        dummy_video = os.path.join(self.test_dir, "job_123_video.mp4")
        with open(dummy_video, "w") as f:
            f.write("test media content")

        mock_upload.return_value = (True, {"web_link": "https://onedrive.live.com/job123"})

        self.plugin.save_user_config("alice", {
            "enabled": True,
            "safe_offload": True,
            "oauth": {"client_id": "test_id"}
        })
        self.plugin.save_user_token("alice", {"access_token": "token_alice", "expires_at": time.time() + 3600})

        # Simular descarga en JOBS
        from core.state import JOBS, JOBS_LOCK
        with JOBS_LOCK:
            JOBS["job_123"] = {
                "status": "finished",
                "filepath": dummy_video,
                "filename": "job_123_video.mp4"
            }

        ok, res = self.plugin.upload_job_for_user("job_123", username="alice")
        self.assertTrue(ok)
        self.assertTrue(res["offloaded"])
        self.assertEqual(res["provider"], "onedrive")
        # El archivo local debe haberse eliminado por Safe Offload
        self.assertFalse(os.path.exists(dummy_video))

    @patch("plugins.onedrive.onedrive_client.upload_file_resumable")
    def test_upload_file_for_user_dispatcher(self, mock_upload):
        """Verifica que upload_file_for_user suba cualquier archivo arbitrario en disco."""
        dummy_file = os.path.join(self.test_dir, "report.pdf")
        with open(dummy_file, "w") as f:
            f.write("pdf data")

        mock_upload.return_value = (True, {"id": "pdf123", "web_link": "https://onedrive.live.com/report.pdf"})

        self.plugin.save_user_config("alice", {"enabled": True, "oauth": {"client_id": "cid"}})
        self.plugin.save_user_token("alice", {"access_token": "token_alice", "expires_at": time.time() + 3600})

        ok, res = self.plugin.upload_file_for_user(dummy_file, username="alice")
        self.assertTrue(ok)
        self.assertEqual(res["id"], "pdf123")


if __name__ == "__main__":
    unittest.main()
