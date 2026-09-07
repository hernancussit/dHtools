"""
Test suite para verificar actualizaciones de plugins vía GitHub en PluginManager y routes/admin.py.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ajustar PYTHONPATH
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from core.plugin_manager import PluginManager


class TestPluginGitHubUpdates(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pm = PluginManager()
        self.pm.plugins_dir = self.temp_dir

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_plugin_git_info_from_manifest(self):
        """Verifica que PluginManager extraiga repo y rama desde plugin.json."""
        p_dir = os.path.join(self.temp_dir, "test_plugin")
        os.makedirs(p_dir, exist_ok=True)
        manifest = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "repository": "https://github.com/usuario/test-repo",
            "branch": "develop",
            "enabled": True
        }
        with open(os.path.join(p_dir, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        with open(os.path.join(p_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write("class Plugin:\n    pass\n")

        self.pm.discover_and_load_plugins()

        git_info = self.pm.get_plugin_git_info("test_plugin")
        self.assertEqual(git_info["plugin_id"], "test_plugin")
        self.assertEqual(git_info["repo_url"], "https://github.com/usuario/test-repo")
        self.assertEqual(git_info["github_repo"], "usuario/test-repo")
        self.assertEqual(git_info["branch"], "develop")
        self.assertTrue(git_info["can_update"])
        self.assertFalse(git_info["is_git_repo"])

    def test_check_plugin_update_newer_version(self):
        """Verifica detección de actualización cuando GitHub tiene una versión superior."""
        p_dir = os.path.join(self.temp_dir, "my_ext")
        os.makedirs(p_dir, exist_ok=True)
        manifest = {
            "id": "my_ext",
            "name": "My Extension",
            "version": "1.0.0",
            "repository": "usuario/my_ext",
            "enabled": True
        }
        with open(os.path.join(p_dir, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        with open(os.path.join(p_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write("class Plugin:\n    pass\n")

        self.pm.discover_and_load_plugins()

        # Simular respuestas de GitHub API: release v1.2.0
        mock_commit_resp = MagicMock()
        mock_commit_resp.status_code = 200
        mock_commit_resp.json.return_value = {
            "sha": "a1b2c3d4e5f6",
            "commit": {"message": "Release v1.2.0\nDetails", "committer": {"date": "2026-09-06T12:00:00Z"}}
        }

        mock_release_resp = MagicMock()
        mock_release_resp.status_code = 200
        mock_release_resp.json.return_value = {
            "tag_name": "v1.2.0"
        }

        def mock_get(url, *args, **kwargs):
            if "releases/latest" in url:
                return mock_release_resp
            return mock_commit_resp

        with patch("requests.get", side_effect=mock_get):
            update_status = self.pm.check_plugin_update("my_ext")

        self.assertTrue(update_status["update_available"])
        self.assertEqual(update_status["remote_version"], "1.2.0")
        self.assertEqual(update_status["remote_commit"], "a1b2c3d")
        self.assertEqual(update_status["commit_message"], "Release v1.2.0")

    def test_update_plugin_preserves_config(self):
        """Verifica que config.json y credenciales privadas se preserven durante una actualización."""
        p_dir = os.path.join(self.temp_dir, "remote_assist")
        os.makedirs(p_dir, exist_ok=True)
        manifest = {
            "id": "remote_assist",
            "name": "Remote Assist",
            "version": "1.0.0",
            "repository": "https://github.com/owner/remote-assist",
            "branch": "main",
            "enabled": True
        }
        with open(os.path.join(p_dir, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        with open(os.path.join(p_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write("class Plugin:\n    pass\n")

        # Archivo de credenciales privadas que debe conservarse intacto
        secret_config = {"api_key": "SUPER_SECRET_TOKEN_12345", "channels": [123, 456]}
        with open(os.path.join(p_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(secret_config, f)

        self.pm.discover_and_load_plugins()

        # Simular subprocess.run para git commands
        def fake_run(cmd, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "OK"
            mock_res.stderr = ""
            # Simular que durante el git pull / checkout, se actualiza plugin.json a 1.1.0
            new_manifest = dict(manifest)
            new_manifest["version"] = "1.1.0"
            with open(os.path.join(p_dir, "plugin.json"), "w", encoding="utf-8") as f:
                json.dump(new_manifest, f)
            # Simular que git borraría o sobreescribiría config.json si no estuviera protegido
            with open(os.path.join(p_dir, "config.json"), "w", encoding="utf-8") as f:
                f.write('{"api_key": "DELETED_BY_GIT"}')
            return mock_res

        with patch("subprocess.run", side_effect=fake_run):
            ok, msg, details = self.pm.update_plugin("remote_assist")

        self.assertTrue(ok)
        self.assertIn("v1.1.0", msg)

        # Verificar que config.json fue restaurado con el contenido privado original
        with open(os.path.join(p_dir, "config.json"), "r", encoding="utf-8") as f:
            restored = json.load(f)
        self.assertEqual(restored["api_key"], "SUPER_SECRET_TOKEN_12345")
        self.assertEqual(restored["channels"], [123, 456])

    def test_admin_api_endpoints(self):
        """Verifica que los endpoints de /api/admin/plugins respondan adecuadamente."""
        from app import app
        app.config["TESTING"] = True

        p_dir = os.path.join(self.temp_dir, "cloud_bot")
        os.makedirs(p_dir, exist_ok=True)
        manifest = {
            "id": "cloud_bot",
            "name": "Cloud Bot",
            "version": "1.0.0",
            "repository": "https://github.com/bot/cloud_bot",
            "enabled": True
        }
        with open(os.path.join(p_dir, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        with open(os.path.join(p_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write("class Plugin:\n    pass\n")

        from core.plugin_manager import plugin_manager
        old_dir = plugin_manager.plugins_dir
        plugin_manager.plugins_dir = self.temp_dir
        plugin_manager.discover_and_load_plugins()

        try:
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["logged_in"] = True
                    sess["username"] = "admin"
                    sess["role"] = "admin"

                # 1. GET /api/admin/plugins
                res = client.get("/api/admin/plugins")
                self.assertEqual(res.status_code, 200)
                d = res.get_json()
                self.assertTrue(d["success"])
                self.assertEqual(d["count"], 1)
                self.assertEqual(d["plugins"][0]["id"], "cloud_bot")
                self.assertTrue(d["plugins"][0]["can_update"])

                # 2. GET /api/admin/plugins/check-updates (mock requests)
                with patch("requests.get") as mock_get:
                    mock_get.return_value.status_code = 200
                    mock_get.return_value.json.return_value = {"sha": "999888777", "commit": {"message": "Test commit"}}
                    res_up = client.get("/api/admin/plugins/check-updates")
                    self.assertEqual(res_up.status_code, 200)
                    up_data = res_up.get_json()
                    self.assertTrue(up_data["success"])
                    self.assertEqual(len(up_data["updates"]), 1)

        finally:
            plugin_manager.plugins_dir = old_dir
            plugin_manager.discover_and_load_plugins()


if __name__ == "__main__":
    unittest.main()
