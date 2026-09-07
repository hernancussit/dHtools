"""
Test suite de verificación del desacoplamiento total de proveedores de nube (Cloud Storage Plugins)
"""

import os
import sys
import unittest
import uuid
import threading
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask
from core.plugin_manager import PluginManager
from core.telegram_bot import TelegramBot, TELEGRAM_MEDIA_CACHE, TELEGRAM_MEDIA_CACHE_LOCK


class MockOneDrivePlugin:
    """Simula un plugin de OneDrive implementando el Cloud Storage Protocol."""
    def __init__(self):
        self.plugin_id = "onedrive"
        self.name = "Microsoft OneDrive"
        self.icon = "☁️"

    def get_download_cloud_option(self, username=None):
        # Usuario 'alice' lo tiene activo; 'bob' desactivado
        is_active = (username == "alice")
        return {
            "plugin_id": "onedrive",
            "name": "Microsoft OneDrive",
            "icon": "☁️",
            "enabled": is_active,
            "auto_upload": is_active,
            "status_label": "ACTIVO" if is_active else "DESACTIVADO",
            "settings_url": "/plugin/onedrive/settings"
        }

    def upload_job_for_user(self, job_id, username, progress_callback=None):
        if username != "alice":
            return False, {"error": "Integración de OneDrive desactivada"}
        return True, {"filename": "video.mp4", "web_link": f"https://onedrive.live.com/view/{job_id}"}

    def upload_file_for_user(self, filepath, username, progress_callback=None):
        if username != "alice":
            return False, {"error": "OneDrive desactivado para este usuario"}
        fname = os.path.basename(filepath)
        return True, {"filename": fname, "web_link": f"https://onedrive.live.com/files/{fname}"}

    def get_user_nav_item(self, username=None):
        return {
            "id": "onedrive",
            "title": "OneDrive",
            "full_title": "OneDrive Cloud Sync",
            "icon": "☁️",
            "url": "/plugin/onedrive/settings"
        }


class TestCloudPluginDecoupling(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
        self.app.config["TESTING"] = True
        self.manager = PluginManager()
        self.manager.init_app(self.app)

        # Inyectar el mock de OneDrive
        self.onedrive_mock = MockOneDrivePlugin()
        self.manager._instances["onedrive"] = self.onedrive_mock
        self.manager._plugins["onedrive"] = {
            "name": "Microsoft OneDrive",
            "icon": "☁️",
            "version": "1.0.0",
            "enabled": True
        }

    def test_get_user_cloud_providers(self):
        """Verifica que PluginManager liste todos los proveedores y respete el estado por usuario."""
        # Usuario 'alice': OneDrive activo
        alice_provs = self.manager.get_user_cloud_providers(username="alice")
        od_alice = next((p for p in alice_provs if p["id"] == "onedrive"), None)
        self.assertIsNotNone(od_alice)
        self.assertTrue(od_alice["enabled"])
        self.assertEqual(od_alice["name"], "Microsoft OneDrive")

        # Usuario 'bob': OneDrive desactivado
        bob_provs = self.manager.get_user_cloud_providers(username="bob")
        od_bob = next((p for p in bob_provs if p["id"] == "onedrive"), None)
        self.assertIsNotNone(od_bob)
        self.assertFalse(od_bob["enabled"])

    def test_upload_job_to_cloud_dispatcher(self):
        """Verifica que upload_job_to_cloud despache correctamente a cualquier plugin."""
        # Subida exitosa para alice
        ok, res = self.manager.upload_job_to_cloud("onedrive", "job123", "alice")
        self.assertTrue(ok)
        self.assertIn("onedrive.live.com/view/job123", res["web_link"])

        # Subida rechazada para bob (desactivado)
        ok, res = self.manager.upload_job_to_cloud("onedrive", "job123", "bob")
        self.assertFalse(ok)
        self.assertIn("desactivada", res["error"])

        # Plugin inexistente
        ok, res = self.manager.upload_job_to_cloud("dropbox", "job123", "alice")
        self.assertFalse(ok)
        self.assertIn("no disponible", res["error"])

    def test_upload_file_to_cloud_dispatcher(self):
        """Verifica que upload_file_to_cloud despache cualquier archivo arbitrario en disco a la nube."""
        dummy_file = os.path.join(BASE_DIR, "tests", "dummy_test_report.txt")
        with open(dummy_file, "w", encoding="utf-8") as f:
            f.write("Reporte de diagnóstico de prueba")

        try:
            # Subida exitosa para alice
            ok, res = self.manager.upload_file_to_cloud("onedrive", dummy_file, "alice")
            self.assertTrue(ok)
            self.assertEqual(res["filename"], "dummy_test_report.txt")
            self.assertIn("onedrive.live.com/files/dummy_test_report.txt", res["web_link"])

            # Subida rechazada para bob (desactivado)
            ok, res = self.manager.upload_file_to_cloud("onedrive", dummy_file, "bob")
            self.assertFalse(ok)
            self.assertIn("desactivado", res["error"])

            # Archivo inexistente
            ok, res = self.manager.upload_file_to_cloud("onedrive", "/tmp/non_existent.txt", "alice")
            self.assertFalse(ok)
            self.assertIn("no existe", res["error"])

        finally:
            if os.path.exists(dummy_file):
                os.remove(dummy_file)

    def test_get_user_nav_items(self):
        """Verifica que los nav items se recolecten de todos los plugins."""
        items = self.manager.get_user_nav_items(username="alice")
        self.assertIsInstance(items, list)
        
        # Debe estar Google Drive
        gdrive_nav = next((i for i in items if i["id"] == "google_drive"), None)
        self.assertIsNotNone(gdrive_nav, "Google Drive debe proveer su nav item")
        self.assertEqual(gdrive_nav["title"], "Drive")
        self.assertEqual(gdrive_nav["url"], "/plugin/google_drive/settings")

        # Debe estar OneDrive
        od_nav = next((i for i in items if i["id"] == "onedrive"), None)
        self.assertIsNotNone(od_nav, "OneDrive debe proveer su nav item")
        self.assertEqual(od_nav["title"], "OneDrive")
        self.assertEqual(od_nav["url"], "/plugin/onedrive/settings")

    def test_get_queue_status(self):
        """Verifica que get_queue_status retorne tareas activas y encoladas con filtrado por usuario."""
        from core.state import JOBS, JOBS_LOCK, QUEUE_LIST, QUEUE_LOCK
        import core.state

        with JOBS_LOCK:
            JOBS["test_job_1"] = {
                "id": "test_job_1",
                "title": "Video de Alice",
                "status": "downloading",
                "percent": 45,
                "owner": "alice"
            }
            JOBS["test_job_2"] = {
                "id": "test_job_2",
                "title": "Video de Bob",
                "status": "queued",
                "percent": 0,
                "owner": "bob"
            }

        with QUEUE_LOCK:
            QUEUE_LIST.clear()
            QUEUE_LIST.append("test_job_2")

        core.state.ACTIVE_WORKER_JOB = "test_job_1"

        try:
            # Visión para Alice (solo sus descargas)
            q_alice = self.manager.get_queue_status(username="alice")
            self.assertEqual(len(q_alice["active_jobs"]), 1)
            self.assertEqual(q_alice["active_jobs"][0]["job_id"], "test_job_1")
            self.assertEqual(len(q_alice["queued_jobs"]), 0)

            # Visión para Bob (solo sus descargas)
            q_bob = self.manager.get_queue_status(username="bob")
            self.assertEqual(len(q_bob["active_jobs"]), 0)
            self.assertEqual(len(q_bob["queued_jobs"]), 1)
            self.assertEqual(q_bob["queued_jobs"][0]["job_id"], "test_job_2")

            # Visión global (username=None)
            q_all = self.manager.get_queue_status()
            self.assertEqual(len(q_all["active_jobs"]), 1)
            self.assertEqual(len(q_all["queued_jobs"]), 1)
            self.assertEqual(q_all["total"], 2)

        finally:
            # Limpiar estado
            with JOBS_LOCK:
                JOBS.pop("test_job_1", None)
                JOBS.pop("test_job_2", None)
            with QUEUE_LOCK:
                QUEUE_LIST.clear()
            core.state.ACTIVE_WORKER_JOB = None


class TestTelegramBotDecoupling(unittest.TestCase):
    def setUp(self):
        self.bot = TelegramBot()
        self.bot.send_message = MagicMock(return_value={"ok": True, "result": {"message_id": 101}})
        self.bot.edit_message = MagicMock(return_value={"ok": True})
        self.bot.answer_callback_query = MagicMock(return_value={"ok": True})

    def test_build_media_keyboard_multi_cloud(self):
        """Verifica que el teclado inline genere botones dinámicos para múltiples nubes."""
        cache_id = "test1234"
        cached_data = {
            "title": "Prueba",
            "cloud_options": {
                "google_drive": {"name": "Google Drive", "icon": "📁", "enabled": True},
                "onedrive": {"name": "Microsoft OneDrive", "icon": "☁️", "enabled": False}
            }
        }
        kb = self.bot._build_media_keyboard(cache_id, cached_data)
        flat_buttons = [b for row in kb["inline_keyboard"] for b in row]

        # Verificar botón Google Drive
        btn_gdrive = next((b for b in flat_buttons if "cloud_tog:google_drive:" in b.get("callback_data", "")), None)
        self.assertIsNotNone(btn_gdrive)
        self.assertIn("✅ SÍ", btn_gdrive["text"])

        # Verificar botón OneDrive
        btn_od = next((b for b in flat_buttons if "cloud_tog:onedrive:" in b.get("callback_data", "")), None)
        self.assertIsNotNone(btn_od)
        self.assertIn("⬜ NO", btn_od["text"])

    def test_cloud_toggle_callback(self):
        """Verifica que el callback genérico cloud_tog alterne el estado y redibuje el mensaje."""
        cache_id = uuid.uuid4().hex[:8]
        cached_data = {
            "title": "Video de prueba",
            "owner": "alice",
            "cloud_options": {
                "onedrive": {"name": "Microsoft OneDrive", "icon": "☁️", "enabled": False}
            }
        }
        with TELEGRAM_MEDIA_CACHE_LOCK:
            TELEGRAM_MEDIA_CACHE[cache_id] = cached_data

        update = {
            "callback_query": {
                "id": "q1",
                "data": f"cloud_tog:onedrive:{cache_id}",
                "message": {"chat": {"id": 123}, "message_id": 50},
                "from": {"id": 999}
            }
        }

        with patch("core.telegram_bot.get_user_by_telegram_chat_id", return_value=("alice", {})):
            self.bot._handle_callback_query(update["callback_query"])

        # Estado debe haber cambiado a True
        self.assertTrue(cached_data["cloud_options"]["onedrive"]["enabled"])
        self.bot.edit_message.assert_called()

    def test_legacy_toggle_drive_callback(self):
        """Verifica compatibilidad hacia atrás con el callback toggle_drive."""
        cache_id = uuid.uuid4().hex[:8]
        cached_data = {
            "title": "Video de prueba",
            "owner": "alice",
            "drive_upload": False,
            "cloud_options": {
                "google_drive": {"name": "Google Drive", "icon": "📁", "enabled": False}
            }
        }
        with TELEGRAM_MEDIA_CACHE_LOCK:
            TELEGRAM_MEDIA_CACHE[cache_id] = cached_data

        update = {
            "callback_query": {
                "id": "q2",
                "data": f"toggle_drive:{cache_id}",
                "message": {"chat": {"id": 123}, "message_id": 51},
                "from": {"id": 999}
            }
        }

        with patch("core.telegram_bot.get_user_by_telegram_chat_id", return_value=("alice", {})):
            self.bot._handle_callback_query(update["callback_query"])

        # Tanto el campo legacy como el dict cloud_options deben haber sido actualizados
        self.assertTrue(cached_data["drive_upload"])
        self.assertTrue(cached_data["cloud_options"]["google_drive"]["enabled"])


if __name__ == "__main__":
    unittest.main()
