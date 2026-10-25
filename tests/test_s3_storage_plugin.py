"""
Test suite de verificación para el Plugin Oficial de S3 Storage (plugins/s3_storage/)
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
from plugins.s3_storage.plugin import Plugin as S3Plugin
from plugins.s3_storage import s3_client
from core.state import JOBS, JOBS_LOCK


class TestS3StoragePlugin(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="dhtools_test_s3_")
        self.manager = PluginManager()
        self.plugin = S3Plugin(
            manager=self.manager,
            metadata={"id": "s3_storage", "name": "S3 Object Storage", "version": "1.0.0"}
        )
        self.plugin.users_data_dir = os.path.join(self.test_dir, "users_data")
        os.makedirs(self.plugin.users_data_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_plugin_discovery_and_metadata(self):
        """Verifica que PluginManager descubra y cargue la metadata de s3_storage."""
        self.manager.discover_and_load_plugins()
        discovered = self.manager._plugins
        self.assertIn("s3_storage", discovered)
        meta = discovered["s3_storage"]
        self.assertEqual(meta.get("id"), "s3_storage")
        self.assertEqual(meta.get("icon"), "🪣")
        self.assertEqual(meta.get("settings_url"), "/plugin/s3_storage/settings")

    def test_multi_user_isolation(self):
        """Verifica que las configuraciones de S3 estén estrictamente aisladas entre usuarios."""
        # Alice
        self.plugin.save_user_config("alice", {
            "enabled": True,
            "auto_upload": True,
            "bucket_name": "alice-bucket",
            "access_key": "alice_key",
            "secret_key": "alice_secret",
            "region": "us-west-2"
        })

        # Bob
        self.plugin.save_user_config("bob", {
            "enabled": False,
            "auto_upload": False,
            "bucket_name": "bob-bucket",
            "access_key": "bob_key",
            "secret_key": "bob_secret",
            "region": "eu-central-1"
        })

        res_alice = self.plugin.get_user_config("alice")
        res_bob = self.plugin.get_user_config("bob")

        self.assertTrue(res_alice["enabled"])
        self.assertEqual(res_alice["bucket_name"], "alice-bucket")
        self.assertEqual(res_alice["access_key"], "alice_key")
        self.assertEqual(res_alice["region"], "us-west-2")

        self.assertFalse(res_bob["enabled"])
        self.assertEqual(res_bob["bucket_name"], "bob-bucket")
        self.assertEqual(res_bob["access_key"], "bob_key")
        self.assertEqual(res_bob["region"], "eu-central-1")

    def test_get_download_cloud_option(self):
        """Verifica que get_download_cloud_option reporte el estado preciso."""
        # Alice activa con credenciales completas
        self.plugin.save_user_config("alice", {
            "enabled": True,
            "auto_upload": True,
            "bucket_name": "bucket-prod",
            "access_key": "key",
            "secret_key": "secret"
        })
        opt_alice = self.plugin.get_download_cloud_option("alice")
        self.assertTrue(opt_alice["enabled"])
        self.assertTrue(opt_alice["auto_upload"])
        self.assertIn("ACTIVO", opt_alice["status_label"])

        # Bob sin credenciales
        opt_bob = self.plugin.get_download_cloud_option("bob")
        self.assertFalse(opt_bob["enabled"])
        self.assertEqual(opt_bob["status_label"], "NO CONFIGURADO")

    def test_get_user_nav_item(self):
        """Verifica la generación del enlace de navegación para el menú lateral."""
        nav = self.plugin.get_user_nav_item()
        self.assertEqual(nav["id"], "s3_storage")
        self.assertEqual(nav["icon"], "🪣")
        self.assertEqual(nav["url"], "/plugin/s3_storage/settings")

    def test_s3_client_test_connection_validation(self):
        """Verifica las validaciones de configuración en test_connection."""
        # Vacía
        ok, msg = s3_client.test_connection({})
        self.assertFalse(ok)
        self.assertIn("vacía", msg)

        # Falta bucket
        ok, msg = s3_client.test_connection({"access_key": "k", "secret_key": "s"})
        self.assertFalse(ok)
        self.assertIn("Bucket", msg)

        # Faltan credenciales
        ok, msg = s3_client.test_connection({"bucket_name": "b"})
        self.assertFalse(ok)
        self.assertIn("credenciales", msg.lower())

    def test_s3_client_upload_file_multipart_mocked(self):
        """Prueba la subida multipart simulada con boto3."""
        dummy_file = os.path.join(self.test_dir, "test_s3_upload.mp4")
        with open(dummy_file, "w") as f:
            f.write("test content for s3 upload")

        cfg = {
            "bucket_name": "my-bucket",
            "access_key": "test_access",
            "secret_key": "test_secret",
            "region": "us-east-1",
            "remote_dir": "backup"
        }

        progress_calls = []
        def _cb(pct, msg):
            progress_calls.append((pct, msg))

        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3, "boto3.s3.transfer": MagicMock(), "botocore": MagicMock(), "botocore.config": MagicMock()}):
            with patch("plugins.s3_storage.s3_client.check_dependencies", return_value=(True, "ok")):
                ok, res = s3_client.upload_file_multipart(dummy_file, "test_s3_upload.mp4", cfg, progress_callback=_cb)
                self.assertTrue(ok)
                self.assertEqual(res["bucket"], "my-bucket")
                self.assertEqual(res["key"], "backup/test_s3_upload.mp4")
                self.assertEqual(res["s3_uri"], "s3://my-bucket/backup/test_s3_upload.mp4")

    def test_upload_job_for_user_with_safe_offload(self):
        """Verifica la subida de un job con modo Safe Offload (borrado de archivo local)."""
        dummy_file = os.path.join(self.test_dir, "video_to_offload.mp4")
        with open(dummy_file, "w") as f:
            f.write("content to offload to S3")

        self.plugin.save_user_config("alice", {
            "enabled": True,
            "safe_offload": True,
            "bucket_name": "prod-bucket",
            "access_key": "AKIA123",
            "secret_key": "SEC123"
        })

        job_id = "job_s3_offload_test"
        with JOBS_LOCK:
            JOBS[job_id] = {
                "owner": "alice",
                "filepath": dummy_file,
                "filename": "video_to_offload.mp4",
                "status": "finished"
            }

        mock_upload_res = {
            "success": True,
            "filename": "video_to_offload.mp4",
            "bucket": "prod-bucket",
            "key": "video_to_offload.mp4",
            "s3_uri": "s3://prod-bucket/video_to_offload.mp4",
            "web_link": "s3://prod-bucket/video_to_offload.mp4",
            "provider": "s3_storage"
        }

        with patch("plugins.s3_storage.s3_client.upload_file_multipart", return_value=(True, mock_upload_res)):
            ok, res = self.plugin.upload_job_for_user(job_id, username="alice")
            self.assertTrue(ok)
            self.assertTrue(res["offloaded"])
            # El archivo local debe haberse eliminado por Safe Offload
            self.assertFalse(os.path.exists(dummy_file), "Safe Offload debe eliminar el archivo tras subida exitosa")


if __name__ == "__main__":
    unittest.main()
