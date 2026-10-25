"""
Test suite de verificación para el Plugin Oficial de FTP / FTPS Storage (plugins/ftp_storage/)
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
from plugins.ftp_storage.plugin import Plugin as FTPPlugin
from plugins.ftp_storage import ftp_client
from core.state import JOBS, JOBS_LOCK


class TestFTPStoragePlugin(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="dhtools_test_ftp_")
        self.manager = PluginManager()
        self.plugin = FTPPlugin(
            manager=self.manager,
            metadata={"id": "ftp_storage", "name": "FTP / FTPS Storage", "version": "1.0.0"}
        )
        self.plugin.users_data_dir = os.path.join(self.test_dir, "users_data")
        os.makedirs(self.plugin.users_data_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_plugin_discovery_and_metadata(self):
        """Verifica que PluginManager descubra y cargue la metadata de ftp_storage."""
        self.manager.discover_and_load_plugins()
        discovered = self.manager._plugins
        self.assertIn("ftp_storage", discovered)
        meta = discovered["ftp_storage"]
        self.assertEqual(meta.get("id"), "ftp_storage")
        self.assertEqual(meta.get("icon"), "🌐")
        self.assertEqual(meta.get("settings_url"), "/plugin/ftp_storage/settings")

    def test_multi_user_isolation(self):
        """Verifica que las configuraciones de FTP estén aisladas entre usuarios."""
        self.plugin.save_user_config("alice", {
            "enabled": True,
            "auto_upload": True,
            "host": "ftp.alice.com",
            "port": 2121,
            "username": "alice",
            "password": "pwd_alice",
            "remote_dir": "/alice/media",
            "use_tls": True
        })

        self.plugin.save_user_config("bob", {
            "enabled": False,
            "auto_upload": False,
            "host": "ftp.bob.com",
            "port": 21,
            "username": "bob",
            "password": "pwd_bob",
            "remote_dir": "/bob/files",
            "use_tls": False
        })

        res_alice = self.plugin.get_user_config("alice")
        res_bob = self.plugin.get_user_config("bob")

        self.assertTrue(res_alice["enabled"])
        self.assertEqual(res_alice["host"], "ftp.alice.com")
        self.assertEqual(res_alice["port"], 2121)
        self.assertTrue(res_alice["use_tls"])

        self.assertFalse(res_bob["enabled"])
        self.assertEqual(res_bob["host"], "ftp.bob.com")
        self.assertEqual(res_bob["port"], 21)
        self.assertFalse(res_bob["use_tls"])

    def test_get_download_cloud_option(self):
        """Verifica que get_download_cloud_option reporte el estado preciso."""
        self.plugin.save_user_config("alice", {
            "enabled": True,
            "auto_upload": True,
            "host": "ftp.example.com"
        })
        opt_alice = self.plugin.get_download_cloud_option("alice")
        self.assertTrue(opt_alice["enabled"])
        self.assertTrue(opt_alice["auto_upload"])
        self.assertIn("ACTIVO", opt_alice["status_label"])

        opt_bob = self.plugin.get_download_cloud_option("bob")
        self.assertFalse(opt_bob["enabled"])
        self.assertEqual(opt_bob["status_label"], "NO CONFIGURADO")

    def test_ftp_client_test_connection_mocked(self):
        """Prueba test_connection con simulación de ftplib."""
        ok, msg = ftp_client.test_connection({})
        self.assertFalse(ok)
        self.assertIn("vacía", msg)

        ok, msg = ftp_client.test_connection({"port": 21})
        self.assertFalse(ok)
        self.assertIn("host", msg)


        mock_ftp = MagicMock()
        mock_ftp.getwelcome.return_value = "220 Welcome to FTP"

        with patch("plugins.ftp_storage.ftp_client._get_ftp_connection", return_value=mock_ftp):
            ok, msg = ftp_client.test_connection({"host": "127.0.0.1", "port": 21})
            self.assertTrue(ok)
            self.assertIn("exitosa", msg)

    def test_ftp_client_upload_file_mocked(self):
        """Prueba upload_file con simulación de ftplib y creación recursiva de directorios."""
        dummy_file = os.path.join(self.test_dir, "test_ftp_video.mp4")
        with open(dummy_file, "w") as f:
            f.write("content for ftp storbinary upload")

        cfg = {
            "host": "ftp.example.com",
            "port": 21,
            "username": "user",
            "password": "pwd",
            "remote_dir": "/downloads/media"
        }

        mock_ftp = MagicMock()
        with patch("plugins.ftp_storage.ftp_client._get_ftp_connection", return_value=mock_ftp):
            ok, res = ftp_client.upload_file(dummy_file, "test_ftp_video.mp4", cfg)
            self.assertTrue(ok)
            self.assertEqual(res["filename"], "test_ftp_video.mp4")
            self.assertIn("ftp://ftp.example.com:21/downloads/media/test_ftp_video.mp4", res["ftp_url"])
            mock_ftp.storbinary.assert_called_once()

    def test_upload_job_for_user_with_safe_offload(self):
        """Verifica la subida de un job con modo Safe Offload en FTP."""
        dummy_file = os.path.join(self.test_dir, "ftp_offload.mp4")
        with open(dummy_file, "w") as f:
            f.write("video content for ftp offload")

        self.plugin.save_user_config("alice", {
            "enabled": True,
            "safe_offload": True,
            "host": "ftp.alice.com",
            "port": 21
        })

        job_id = "job_ftp_offload_test"
        with JOBS_LOCK:
            JOBS[job_id] = {
                "owner": "alice",
                "filepath": dummy_file,
                "filename": "ftp_offload.mp4",
                "status": "finished"
            }

        mock_res = {
            "success": True,
            "filename": "ftp_offload.mp4",
            "ftp_url": "ftp://ftp.alice.com:21/ftp_offload.mp4",
            "web_link": "ftp://ftp.alice.com:21/ftp_offload.mp4",
            "provider": "ftp_storage"
        }

        with patch("plugins.ftp_storage.ftp_client.upload_file", return_value=(True, mock_res)):
            ok, res = self.plugin.upload_job_for_user(job_id, username="alice")
            self.assertTrue(ok)
            self.assertTrue(res["offloaded"])
            self.assertFalse(os.path.exists(dummy_file), "Safe Offload debe eliminar el archivo tras subida a FTP")


if __name__ == "__main__":
    unittest.main()
