"""
Test suite de verificación para el Plugin Oficial de WebDAV / Nextcloud Storage (plugins/webdav_storage/)
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
from plugins.webdav_storage.plugin import Plugin as WebDAVPlugin
from plugins.webdav_storage import webdav_client
from core.state import JOBS, JOBS_LOCK


class TestWebDAVStoragePlugin(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="dhtools_test_webdav_")
        self.manager = PluginManager()
        self.plugin = WebDAVPlugin(
            manager=self.manager,
            metadata={"id": "webdav_storage", "name": "WebDAV / Nextcloud Storage", "version": "1.0.0"}
        )
        self.plugin.users_data_dir = os.path.join(self.test_dir, "users_data")
        os.makedirs(self.plugin.users_data_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_plugin_discovery_and_metadata(self):
        """Verifica que PluginManager descubra y cargue la metadata de webdav_storage."""
        self.manager.discover_and_load_plugins()
        discovered = self.manager._plugins
        self.assertIn("webdav_storage", discovered)
        meta = discovered["webdav_storage"]
        self.assertEqual(meta.get("id"), "webdav_storage")
        self.assertEqual(meta.get("icon"), "📁")
        self.assertEqual(meta.get("settings_url"), "/plugin/webdav_storage/settings")

    def test_multi_user_isolation(self):
        """Verifica que las configuraciones de WebDAV estén aisladas entre usuarios."""
        self.plugin.save_user_config("alice", {
            "enabled": True,
            "auto_upload": True,
            "url": "https://nextcloud.alice.com/remote.php/dav/files/alice",
            "username": "alice",
            "password": "secret_password_alice",
            "remote_path": "dHtools/Alice"
        })

        self.plugin.save_user_config("bob", {
            "enabled": False,
            "auto_upload": False,
            "url": "https://nextcloud.bob.com/remote.php/dav/files/bob",
            "username": "bob",
            "password": "secret_password_bob",
            "remote_path": "dHtools/Bob"
        })

        res_alice = self.plugin.get_user_config("alice")
        res_bob = self.plugin.get_user_config("bob")

        self.assertTrue(res_alice["enabled"])
        self.assertEqual(res_alice["url"], "https://nextcloud.alice.com/remote.php/dav/files/alice")
        self.assertEqual(res_alice["username"], "alice")
        self.assertEqual(res_alice["password"], "secret_password_alice")

        self.assertFalse(res_bob["enabled"])
        self.assertEqual(res_bob["url"], "https://nextcloud.bob.com/remote.php/dav/files/bob")
        self.assertEqual(res_bob["username"], "bob")
        self.assertEqual(res_bob["password"], "secret_password_bob")

    def test_get_download_cloud_option(self):
        """Verifica que get_download_cloud_option reporte el estado preciso."""
        self.plugin.save_user_config("alice", {
            "enabled": True,
            "auto_upload": True,
            "url": "https://nextcloud.example.com"
        })
        opt_alice = self.plugin.get_download_cloud_option("alice")
        self.assertTrue(opt_alice["enabled"])
        self.assertTrue(opt_alice["auto_upload"])
        self.assertIn("ACTIVO", opt_alice["status_label"])

        opt_bob = self.plugin.get_download_cloud_option("bob")
        self.assertFalse(opt_bob["enabled"])
        self.assertEqual(opt_bob["status_label"], "NO CONFIGURADO")

    def test_webdav_client_test_connection(self):
        """Prueba la validación y ejecución de test_connection con simulación de requests."""
        # Config vacía
        ok, msg = webdav_client.test_connection({})
        self.assertFalse(ok)
        self.assertIn("vacía", msg)

        # Falta URL
        ok, msg = webdav_client.test_connection({"username": "alice"})
        self.assertFalse(ok)
        self.assertIn("URL", msg)


        # Simular respuesta exitosa 207 Multi-Status
        mock_resp = MagicMock()
        mock_resp.status_code = 207
        with patch("requests.request", return_value=mock_resp):
            ok, msg = webdav_client.test_connection({"url": "https://nextcloud.example.com/dav"})
            self.assertTrue(ok)
            self.assertIn("207", msg)

        # Simular 401 Unauthorized
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        with patch("requests.request", return_value=mock_resp_401):
            ok, msg = webdav_client.test_connection({"url": "https://nextcloud.example.com/dav"})
            self.assertFalse(ok)
            self.assertIn("401", msg)

    def test_webdav_client_upload_file(self):
        """Prueba la subida por PUT con simulación de requests."""
        dummy_file = os.path.join(self.test_dir, "test_webdav_file.mp4")
        with open(dummy_file, "w") as f:
            f.write("content for webdav PUT upload")

        cfg = {
            "url": "https://nextcloud.example.com/remote.php/dav/files/user",
            "username": "user",
            "password": "pwd",
            "remote_path": "dHtools"
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 201

        with patch("requests.put", return_value=mock_resp) as mock_put:
            ok, res = webdav_client.upload_file(dummy_file, "test_webdav_file.mp4", cfg)
            self.assertTrue(ok)
            self.assertEqual(res["filename"], "test_webdav_file.mp4")
            self.assertIn("https://nextcloud.example.com/remote.php/dav/files/user/dHtools/test_webdav_file.mp4", res["web_link"])
            mock_put.assert_called_once()

    def test_upload_job_for_user_with_safe_offload(self):
        """Verifica la subida de un job con modo Safe Offload en WebDAV."""
        dummy_file = os.path.join(self.test_dir, "webdav_offload.mp4")
        with open(dummy_file, "w") as f:
            f.write("video content for webdav offload")

        self.plugin.save_user_config("alice", {
            "enabled": True,
            "safe_offload": True,
            "url": "https://nextcloud.alice.com/dav",
            "username": "alice",
            "password": "pwd"
        })

        job_id = "job_wd_offload_test"
        with JOBS_LOCK:
            JOBS[job_id] = {
                "owner": "alice",
                "filepath": dummy_file,
                "filename": "webdav_offload.mp4",
                "status": "finished"
            }

        mock_res = {
            "success": True,
            "filename": "webdav_offload.mp4",
            "target_url": "https://nextcloud.alice.com/dav/dHtools/webdav_offload.mp4",
            "web_link": "https://nextcloud.alice.com/dav/dHtools/webdav_offload.mp4",
            "provider": "webdav_storage"
        }

        with patch("plugins.webdav_storage.webdav_client.upload_file", return_value=(True, mock_res)):
            ok, res = self.plugin.upload_job_for_user(job_id, username="alice")
            self.assertTrue(ok)
            self.assertTrue(res["offloaded"])
            self.assertFalse(os.path.exists(dummy_file), "Safe Offload debe borrar el archivo tras subir a WebDAV")


if __name__ == "__main__":
    unittest.main()
