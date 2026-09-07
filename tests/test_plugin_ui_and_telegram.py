"""
Test suite de verificación para la inyección de UI y despacho del bot de Telegram en plugins [EXPERIMENTAL]
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask
from core.plugin_manager import PluginManager


class DummyBot:
    """Mock del TelegramBot para probar el despacho de comandos de plugins."""
    def __init__(self):
        self.sent_messages = []
        self.edited_messages = []
        self.answered_callbacks = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return {"ok": True, "result": {"message_id": 999}}

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        self.edited_messages.append({"chat_id": chat_id, "message_id": message_id, "text": text})
        return {"ok": True}

    def answer_callback_query(self, query_id, text=None, show_alert=False):
        self.answered_callbacks.append({"query_id": query_id, "text": text, "alert": show_alert})
        return {"ok": True}


class TestPluginUIAndTelegram(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
        self.app.config["TESTING"] = True
        self.manager = PluginManager()
        self.manager.init_app(self.app)
        self.client = self.app.test_client()
        self.bot = DummyBot()

    def test_admin_cloud_panels(self):
        """Verifica que get_admin_cloud_panels devuelva tarjetas de plugins activos."""
        panels = self.manager.get_admin_cloud_panels()
        self.assertIsInstance(panels, list)
        gdrive_panel = next((p for p in panels if p["plugin_id"] == "google_drive"), None)
        self.assertIsNotNone(gdrive_panel, "Google Drive debe proveer su panel en /admin")
        self.assertIn("Google Drive", gdrive_panel["title"])
        self.assertIn("settings_url", gdrive_panel)

    def test_download_cloud_options(self):
        """Verifica que get_download_cloud_options devuelva opciones para la web de descargas."""
        options = self.manager.get_download_cloud_options()
        self.assertIsInstance(options, list)
        gdrive_opt = next((o for o in options if o["plugin_id"] == "google_drive"), None)
        self.assertIsNotNone(gdrive_opt, "Google Drive debe proveer opción de descarga")
        self.assertEqual(gdrive_opt["name"], "Google Drive")
        self.assertTrue(any(f["id"] == "folder_id" for f in gdrive_opt.get("fields", [])))

    def test_telegram_commands_help(self):
        """Verifica la lista dinámica de comandos de plugins para /ayuda."""
        cmds = self.manager.get_telegram_commands_help()
        self.assertIsInstance(cmds, list)
        drive_cmd = next((c for c in cmds if c["command"] == "/drive"), None)
        self.assertIsNotNone(drive_cmd, "Debe registrarse el comando /drive")

    def test_telegram_command_dispatch(self):
        """Verifica el despacho seguro de /drive hacia el plugin de Google Drive."""
        mock_msg = {
            "message_id": 101,
            "chat": {"id": 12345678},
            "from": {"id": 12345678, "first_name": "TestUser"},
            "text": "/drive"
        }
        handled = self.manager.dispatch_telegram_command("/drive", [], mock_msg, self.bot)
        self.assertTrue(handled, "El comando /drive debe ser manejado por el plugin")
        self.assertTrue(len(self.bot.sent_messages) > 0, "El bot debe haber enviado una respuesta")

    def test_telegram_unknown_command(self):
        """Verifica que comandos no manejados por plugins retornen False."""
        mock_msg = {"chat": {"id": 12345678}, "text": "/comando_inexistente"}
        handled = self.manager.dispatch_telegram_command("/comando_inexistente", [], mock_msg, self.bot)
        self.assertFalse(handled, "Comandos no registrados deben devolver False")

    def test_telegram_fault_isolation(self):
        """Verifica que excepciones en handlers de plugins no tiren el bot."""
        class FailingPlugin:
            def on_telegram_command(self, cmd, args, message, bot):
                raise RuntimeError("Fallo deliberado en plugin")

        self.manager._instances["failing_test"] = FailingPlugin()
        mock_msg = {"chat": {"id": 12345678}, "text": "/fail"}
        try:
            handled = self.manager.dispatch_telegram_command("/fail", [], mock_msg, self.bot)
            self.assertTrue(handled, "Debe atrapar el error y notificar al usuario")
        except Exception as e:
            self.fail(f"dispatch_telegram_command no debe propagar excepciones: {e}")
        finally:
            del self.manager._instances["failing_test"]


if __name__ == "__main__":
    unittest.main()
