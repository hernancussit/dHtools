import os
import sys
import shutil
import json
import unittest

# Ensure repo root in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.plugin_manager import PluginManager

class TestPluginSystem(unittest.TestCase):
    def setUp(self):
        self.manager = PluginManager()
        self.test_plugin_dir = os.path.join(self.manager.plugins_dir, "test_custom_private_bot")

    def tearDown(self):
        # Cleanup dummy plugin if created
        if os.path.exists(self.test_plugin_dir):
            shutil.rmtree(self.test_plugin_dir, ignore_errors=True)

    def test_discovery_and_template_example(self):
        """Verifica que el plugin de ejemplo sea descubierto correctamente."""
        self.manager.discover_and_load_plugins()
        all_plugins = self.manager.get_all_plugins()
        plugin_ids = [p["id"] for p in all_plugins]
        self.assertIn("template_example", plugin_ids, "template_example debe ser descubierto")
        
        tmpl = next(p for p in all_plugins if p["id"] == "template_example")
        self.assertTrue(tmpl.get("experimental"), "Debe tener la marca experimental")
        self.assertFalse(tmpl.get("is_enabled"), "Debe estar deshabilitado por defecto")

    def test_custom_plugin_lifecycle_and_hooks(self):
        """Crea un plugin de prueba activo y comprueba la ejecución de hooks."""
        os.makedirs(self.test_plugin_dir, exist_ok=True)
        
        # Manifest
        manifest = {
            "id": "test_custom_private_bot",
            "name": "Test Private Bot",
            "version": "1.0.0",
            "enabled": True
        }
        with open(os.path.join(self.test_plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
            
        # Code with hook counters
        code = """
class Plugin:
    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.startup_called = False
        self.downloads_completed = []
        self.errors_received = []

    def on_startup(self, app, context):
        self.startup_called = True

    def on_download_complete(self, job_data):
        self.downloads_completed.append(job_data)

    def on_download_error(self, job_data, error=None):
        self.errors_received.append((job_data, error))
"""
        with open(os.path.join(self.test_plugin_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write(code)

        # Reload
        self.manager.discover_and_load_plugins()
        self.assertIn("test_custom_private_bot", self.manager._instances)
        instance = self.manager._instances["test_custom_private_bot"]

        # Test on_download_complete hook
        dummy_job = {
            "job_id": "test12345",
            "title": "Video de Prueba",
            "filepath": "/app/downloads/test.mp4",
            "owner": "admin"
        }
        self.manager.trigger_hook("on_download_complete", dummy_job)
        self.assertEqual(len(instance.downloads_completed), 1)
        self.assertEqual(instance.downloads_completed[0]["job_id"], "test12345")

        # Test on_download_error hook
        self.manager.trigger_hook("on_download_error", dummy_job, error="Test Error")
        self.assertEqual(len(instance.errors_received), 1)
        self.assertEqual(instance.errors_received[0][1], "Test Error")

    def test_faulty_plugin_isolation(self):
        """Verifica que un plugin que lance excepciones deliberadas no rompa la aplicación."""
        os.makedirs(self.test_plugin_dir, exist_ok=True)
        manifest = {
            "id": "test_custom_private_bot",
            "name": "Faulty Plugin",
            "enabled": True
        }
        with open(os.path.join(self.test_plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
            
        code = """
class Plugin:
    def on_download_complete(self, job_data):
        raise ValueError("Excepción intencional para probar aislamiento de fallos")
"""
        with open(os.path.join(self.test_plugin_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write(code)

        self.manager.discover_and_load_plugins()
        # Trigger hook: it should catch the exception and log, without raising
        try:
            self.manager.trigger_hook("on_download_complete", {"job_id": "abc"})
        except Exception as e:
            self.fail(f"trigger_hook no aisló la excepción del plugin: {e}")

if __name__ == "__main__":
    unittest.main()
