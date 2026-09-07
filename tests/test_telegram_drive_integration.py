"""
Tests de integración para Google Drive en el Asistente de Telegram
"""

import os
import sys
import json
import uuid
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask
from core.telegram_bot import telegram_bot, TELEGRAM_MEDIA_CACHE, TELEGRAM_MEDIA_CACHE_LOCK
from core.plugin_manager import plugin_manager


class TestTelegramDriveIntegration(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test_sec"
        plugin_manager.init_app(self.app)
        self.gdrive = plugin_manager.get_plugin_instance("google_drive")
        self.assertIsNotNone(self.gdrive)

    def test_media_keyboard_toggle_drive(self):
        """Verifica que el teclado de Telegram ofrezca el botón de Drive solo si está disponible."""
        cache_id = "test1234"
        
        # 1. Drive no disponible
        cached_no_drive = {
            "drive_available": False,
            "drive_upload": False
        }
        kb1 = telegram_bot._build_media_keyboard(cache_id, cached_no_drive)
        flat_kb1 = [btn for row in kb1["inline_keyboard"] for btn in row]
        self.assertFalse(any("toggle_drive:" in btn.get("callback_data", "") for btn in flat_kb1))

        # 2. Drive disponible pero apagado
        cached_drive_off = {
            "drive_available": True,
            "drive_upload": False
        }
        kb2 = telegram_bot._build_media_keyboard(cache_id, cached_drive_off)
        flat_kb2 = [btn for row in kb2["inline_keyboard"] for btn in row]
        drive_btn = next((b for b in flat_kb2 if "toggle_drive:" in b.get("callback_data", "")), None)
        self.assertIsNotNone(drive_btn)
        self.assertIn("NO", drive_btn["text"])

        # 3. Drive disponible y encendido
        cached_drive_on = {
            "drive_available": True,
            "drive_upload": True
        }
        kb3 = telegram_bot._build_media_keyboard(cache_id, cached_drive_on)
        flat_kb3 = [btn for row in kb3["inline_keyboard"] for btn in row]
        drive_btn3 = next((b for b in flat_kb3 if "toggle_drive:" in b.get("callback_data", "")), None)
        self.assertIsNotNone(drive_btn3)
        self.assertIn("SÍ", drive_btn3["text"])

    def test_toggle_drive_callback(self):
        """Verifica que toggle_drive alterne el estado en TELEGRAM_MEDIA_CACHE."""
        cache_id = "cache_test_toggle"
        with TELEGRAM_MEDIA_CACHE_LOCK:
            TELEGRAM_MEDIA_CACHE[cache_id] = {
                "owner": "testuser",
                "title": "Video de prueba",
                "platform": "YouTube",
                "duration_str": "03:00",
                "drive_available": True,
                "drive_upload": False
            }

        with patch.object(telegram_bot, "get_token", return_value="fake_token"), \
             patch("core.telegram_bot.get_user_by_telegram_chat_id", return_value=("testuser", {})), \
             patch.object(telegram_bot, "answer_callback_query") as mock_ans, \
             patch.object(telegram_bot, "edit_message") as mock_edit:

            query = {
                "id": "q1",
                "data": f"toggle_drive:{cache_id}",
                "message": {"chat": {"id": 12345}, "message_id": 999}
            }

            telegram_bot._handle_callback_query(query)
            mock_ans.assert_called_once()
            self.assertTrue(TELEGRAM_MEDIA_CACHE[cache_id]["drive_upload"])

            # Alternar de nuevo
            telegram_bot._handle_callback_query(query)
            self.assertFalse(TELEGRAM_MEDIA_CACHE[cache_id]["drive_upload"])

    def test_drive_command_respects_activation(self):
        """Verifica que /drive reporte desactivado para usuario con enabled=False."""
        self.gdrive.save_user_config("testuser", {"enabled": False})

        with patch.object(telegram_bot, "get_token", return_value="fake_token"), \
             patch("core.utils.get_user_by_telegram_chat_id", return_value=("testuser", {})), \
             patch("plugins.google_drive.drive_client.check_dependencies", return_value=(True, "")), \
             patch.object(telegram_bot, "send_message") as mock_send:

            handled = self.gdrive.on_telegram_command(
                "/drive", [], {"chat": {"id": 12345}}, telegram_bot
            )
            self.assertTrue(handled)
            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][1]
            self.assertIn("desactivada", sent_text.lower())
            self.assertIn("testuser", sent_text)

    def test_drive_upload_callback_rejects_when_disabled(self):
        """Verifica que el callback drive_upload alerte si el usuario tiene Google Drive desactivado."""
        self.gdrive.save_user_config("testuser", {"enabled": False})

        with patch.object(telegram_bot, "get_token", return_value="fake_token"), \
             patch("core.telegram_bot.get_user_by_telegram_chat_id", return_value=("testuser", {})), \
             patch.object(telegram_bot, "answer_callback_query") as mock_ans:

            query = {
                "id": "q2",
                "data": "drive_upload:some_job_123",
                "message": {"chat": {"id": 12345}, "message_id": 999}
            }

            telegram_bot._handle_callback_query(query)
            mock_ans.assert_called_once()
            alert_text = mock_ans.call_args[0][1]
            self.assertIn("desactivado", alert_text.lower())

    def test_telegram_public_url_resolution(self):
        """Verifica que la URL pública se resuelva dinámicamente y no existan dominios fijos."""
        # 1. Sin configurar
        with patch.dict(os.environ, {}, clear=True), \
             patch("core.telegram_bot.load_cloud_config", return_value={}):
            self.assertEqual(telegram_bot.get_public_url(), "")

        # 2. Configurado vía variable de entorno PUBLIC_URL
        with patch.dict(os.environ, {"PUBLIC_URL": "https://midominio.com/"}):
            self.assertEqual(telegram_bot.get_public_url(), "https://midominio.com")

        # 3. Configurado vía cloud_sync.json
        with patch.dict(os.environ, {}, clear=True), \
             patch("core.telegram_bot.load_cloud_config", return_value={"telegram": {"public_url": "https://telegram.org/custom"}}):
            self.assertEqual(telegram_bot.get_public_url(), "https://telegram.org/custom")


if __name__ == "__main__":
    unittest.main()
