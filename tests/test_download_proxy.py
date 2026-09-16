import unittest
import os
import tempfile
import json
from unittest.mock import patch

from core.utils import (
    get_download_proxy_config,
    save_download_proxy_config,
    get_residential_proxy_config,
    save_residential_proxy_config
)
from app import app

class TestDownloadProxy(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.app = app
        self.client = self.app.test_client()

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass

    def test_default_config_is_disabled(self):
        with patch("core.utils.CONFIG_FILE", self.temp_file.name):
            cfg = get_download_proxy_config()
            self.assertEqual(cfg.get("mode"), "disabled")
            self.assertFalse(cfg.get("enabled"))
            self.assertEqual(cfg.get("url"), "")

    def test_save_and_load_proxy_modes(self):
        with patch("core.utils.CONFIG_FILE", self.temp_file.name):
            # Test 'always'
            save_download_proxy_config({
                "mode": "always",
                "url": "socks5h://user:pass@1.2.3.4:1080",
                "fallback_on_quality_loss": True
            })
            cfg = get_download_proxy_config()
            self.assertEqual(cfg["mode"], "always")
            self.assertTrue(cfg["enabled"])
            self.assertEqual(cfg["url"], "socks5h://user:pass@1.2.3.4:1080")

            # Test 'disabled'
            save_download_proxy_config({"mode": "disabled", "url": "socks5h://1.2.3.4:1080"})
            cfg = get_download_proxy_config()
            self.assertEqual(cfg["mode"], "disabled")
            self.assertFalse(cfg["enabled"])

            # Test 'failsafe'
            save_download_proxy_config({"mode": "failsafe", "url": "socks5h://1.2.3.4:1080"})
            cfg = get_download_proxy_config()
            self.assertEqual(cfg["mode"], "failsafe")
            self.assertTrue(cfg["enabled"])

    def test_backward_compatibility_residential_proxy_config(self):
        with patch("core.utils.CONFIG_FILE", self.temp_file.name):
            # Saving via legacy residential function
            save_residential_proxy_config({
                "enabled": True,
                "url": "socks5h://res.proxy.net:9999",
                "auto_fallback": True,
                "fallback_on_quality_loss": True
            })
            # Legacy getter
            legacy_cfg = get_residential_proxy_config()
            self.assertTrue(legacy_cfg["enabled"])
            self.assertEqual(legacy_cfg["url"], "socks5h://res.proxy.net:9999")
            
            # New proxy config getter should map auto_fallback=True -> mode='failsafe'
            new_cfg = get_download_proxy_config()
            self.assertEqual(new_cfg["mode"], "failsafe")
            self.assertEqual(new_cfg["url"], "socks5h://res.proxy.net:9999")

    def test_admin_api_proxy(self):
        with patch("core.utils.CONFIG_FILE", self.temp_file.name):
            with self.client.session_transaction() as sess:
                sess["username"] = "admin"
                sess["role"] = "admin"

            # GET proxy config
            resp = self.client.get("/api/admin/proxy")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertIn("download_proxy", data)

            # POST update proxy config
            resp = self.client.post("/api/admin/proxy", json={
                "mode": "failsafe",
                "url": "socks5h://user:secret@127.0.0.1:1080",
                "fallback_on_quality_loss": True
            })
            self.assertEqual(resp.status_code, 200)

            # GET again and verify masked password
            resp = self.client.get("/api/admin/proxy")
            data = resp.get_json()
            proxy_data = data["download_proxy"]
            self.assertEqual(proxy_data["mode"], "failsafe")
            self.assertIn("••••••••", proxy_data["url_masked"])

            # Legacy endpoint /api/admin/residential-proxy also works seamlessly
            resp_legacy = self.client.get("/api/admin/residential-proxy")
            self.assertEqual(resp_legacy.status_code, 200)
            legacy_data = resp_legacy.get_json()
            self.assertIn("residential_proxy", legacy_data)

if __name__ == "__main__":
    unittest.main()
