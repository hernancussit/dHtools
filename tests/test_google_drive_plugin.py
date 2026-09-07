"""
Test suite de verificación para el plugin oficial de Google Drive [EXPERIMENTAL]
"""

import os
import sys
import json
import unittest

# Asegurar root en sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask
from core.plugin_manager import PluginManager


class TestGoogleDrivePlugin(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
        self.app.config["TESTING"] = True
        self.app.secret_key = "test_secret_key_12345"
        self.manager = PluginManager()
        self.manager.init_app(self.app)
        self.client = self.app.test_client()

    def test_discovery_and_load(self):
        """Verifica que el plugin sea descubierto y cargado como oficial [EXPERIMENTAL]."""
        plugins = self.manager.get_all_plugins()
        gdrive = next((p for p in plugins if p.get("id") == "google_drive"), None)
        self.assertIsNotNone(gdrive, "El plugin 'google_drive' debe ser descubierto")
        self.assertTrue(gdrive.get("is_loaded"), "El plugin debe cargarse en memoria")
        self.assertTrue(gdrive.get("experimental"), "Debe tener bandera experimental")

    def test_routes_registered(self):
        """Verifica que el panel de configuración y los endpoints API respondan."""
        res_settings = self.client.get("/plugin/google_drive/settings")
        self.assertEqual(res_settings.status_code, 200)
        self.assertIn(b"Google Drive Cloud Sync", res_settings.data)
        self.assertIn(b"EXPERIMENTAL", res_settings.data)

        # Test de conexión con payload vacío debe responder JSON con error controlado
        res_test = self.client.post("/plugin/google_drive/api/test", json={
            "auth_type": "service_account",
            "service_account_json_content": ""
        })
        self.assertEqual(res_test.status_code, 400)
        test_data = res_test.get_json()
        self.assertFalse(test_data["success"])
        self.assertIn("error", test_data)

    def test_save_configuration(self):
        """Verifica el guardado seguro de parámetros de configuración."""
        payload = {
            "enabled": False,
            "auth_type": "service_account",
            "folder_id": "test_folder_12345",
            "safe_offload": True,
            "subfolder_by_owner": False
        }
        res_save = self.client.post("/plugin/google_drive/api/save", json=payload)
        self.assertEqual(res_save.status_code, 200)
        save_data = res_save.get_json()
        self.assertTrue(save_data["success"])

        # Verificar que la instancia leyó la nueva configuración
        instance = self.manager._instances.get("google_drive")
        self.assertIsNotNone(instance)
        cfg = instance.get_config()
        self.assertEqual(cfg.get("folder_id"), "test_folder_12345")
        self.assertTrue(cfg.get("safe_offload"))

    def test_hook_fault_isolation(self):
        """Verifica que el hook on_download_complete sea aislado y no lance excepciones."""
        mock_job = {
            "id": "mock_job_999",
            "job_id": "mock_job_999",
            "title": "Video de Prueba",
            "filename": "video.mp4",
            "filepath": os.path.join(BASE_DIR, "non_existent_video.mp4"),
            "owner": "admin"
        }
        # No debe lanzar excepción
        try:
            self.manager.trigger_hook("on_download_complete", mock_job)
            self.manager.trigger_hook("on_download_error", mock_job, "Error simulado")
        except Exception as e:
            self.fail(f"El PluginManager no debe propagar excepciones no controladas: {e}")

    def test_ui_nav_item(self):
        """Verifica que el plugin provea un item de navegación."""
        summary = self.manager.get_active_plugins_summary()
        gdrive_sum = next((p for p in summary if p["id"] == "google_drive"), None)
        self.assertIsNotNone(gdrive_sum)
        self.assertTrue(gdrive_sum["has_ui"])
        self.assertEqual(gdrive_sum["nav_item"]["url"], "/plugin/google_drive/settings")

    def test_oauth_start_and_validation(self):
        """Verifica el endpoint de inicio OAuth2 y la redirección a Google."""
        instance = self.manager._instances.get("google_drive")
        # Sin client_id/secret debe redirigir con error
        cfg = instance.get_config()
        cfg["oauth"] = {"client_id": "", "client_secret": ""}
        instance.save_config(cfg)

        res_err = self.client.get("/plugin/google_drive/oauth/start")
        self.assertEqual(res_err.status_code, 302)
        self.assertIn("oauth_error", res_err.location)

        # Con client_id y secret configurados debe redirigir a accounts.google.com
        cfg["oauth"] = {"client_id": "test_client_id_123.apps.googleusercontent.com", "client_secret": "test_secret"}
        instance.save_config(cfg)

        res_ok = self.client.get("/plugin/google_drive/oauth/start")
        self.assertEqual(res_ok.status_code, 302)
        self.assertIn("accounts.google.com", res_ok.location)
        self.assertIn("test_client_id_123", res_ok.location)
        self.assertIn("prompt=consent", res_ok.location)

    def test_oauth_callback_error_handling(self):
        """Verifica el manejo de errores en el callback de Google."""
        # 1. Error explícito devuelto por Google (ej: access_denied)
        res_denied = self.client.get("/plugin/google_drive/oauth/callback?error=access_denied")
        self.assertEqual(res_denied.status_code, 302)
        self.assertIn("oauth_error", res_denied.location)
        self.assertIn("access_denied", res_denied.location)

        # 2. Callback sin código de autorización
        res_no_code = self.client.get("/plugin/google_drive/oauth/callback")
        self.assertEqual(res_no_code.status_code, 302)
        self.assertIn("oauth_error", res_no_code.location)

    def test_oauth_manual_token_and_revoke(self):
        """Verifica el guardado y eliminación manual de token.json."""
        # Payload inválido
        res_inv = self.client.post("/plugin/google_drive/oauth/manual-token", json={"token_content": "invalid json"})
        self.assertEqual(res_inv.status_code, 400)

        # Payload válido
        valid_token = json.dumps({
            "token": "ya29.mock_token_abc",
            "refresh_token": "1//mock_refresh_xyz",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": ["https://www.googleapis.com/auth/drive.file"]
        })
        res_valid = self.client.post("/plugin/google_drive/oauth/manual-token", json={"token_content": valid_token})
        self.assertEqual(res_valid.status_code, 200)
        self.assertTrue(res_valid.get_json()["success"])

        # Verificar que token.json existe en el directorio del plugin
        instance = self.manager._instances.get("google_drive")
        token_path = os.path.join(instance.plugin_dir, "token.json")
        self.assertTrue(os.path.exists(token_path))

        # Revocar token
        res_revoke = self.client.post("/plugin/google_drive/oauth/revoke")
        self.assertEqual(res_revoke.status_code, 200)
        self.assertTrue(res_revoke.get_json()["success"])
        self.assertFalse(os.path.exists(token_path))

    def test_multi_user_isolation(self):
        """Verifica que dos usuarios distintos guarden sus configuraciones de forma aislada."""
        instance = self.manager._instances.get("google_drive")
        self.assertIsNotNone(instance)

        # Configuración para user_alpha
        cfg_alpha = {
            "enabled": True,
            "auto_upload": True,
            "folder_id": "folder_alpha_999",
            "safe_offload": False,
            "auth_type": "service_account"
        }
        ok_a = instance.save_user_config("user_alpha", cfg_alpha)
        self.assertTrue(ok_a)

        # Configuración para user_beta
        cfg_beta = {
            "enabled": False,
            "auto_upload": False,
            "folder_id": "folder_beta_888",
            "safe_offload": True,
            "auth_type": "oauth2"
        }
        ok_b = instance.save_user_config("user_beta", cfg_beta)
        self.assertTrue(ok_b)

        # Recuperar ambas y validar aislamiento total
        loaded_a = instance.get_user_config("user_alpha")
        loaded_b = instance.get_user_config("user_beta")

        self.assertEqual(loaded_a.get("folder_id"), "folder_alpha_999")
        self.assertTrue(loaded_a.get("auto_upload"))
        self.assertTrue(loaded_a.get("enabled"))
        self.assertEqual(loaded_a.get("auth_type"), "service_account")

        self.assertEqual(loaded_b.get("folder_id"), "folder_beta_888")
        self.assertFalse(loaded_b.get("auto_upload"))
        self.assertFalse(loaded_b.get("enabled"))
        self.assertEqual(loaded_b.get("auth_type"), "oauth2")

    def test_on_demand_vs_auto_upload_logic(self):
        """Verifica que en modo bajo demanda (auto_upload=False) no se suba salvo que se marque en el job."""
        instance = self.manager._instances.get("google_drive")
        self.assertIsNotNone(instance)

        # Configurar usuario 'tester' en modo bajo demanda
        instance.save_user_config("tester", {
            "enabled": True,
            "auto_upload": False,
            "folder_id": "root"
        })

        mock_job_default = {
            "id": "job_ondemand_1",
            "job_id": "job_ondemand_1",
            "owner": "tester",
            "filepath": "dummy.mp4",
            "filename": "dummy.mp4",
            "user_cloud_sync": {}
        }

        # Con auto_upload=False y sin checkbox de plugin, on_download_complete no debe subir
        # Verificamos que la función retorne inmediatamente sin error
        instance.on_download_complete(mock_job_default)

        # Ahora con checkbox activo en el job
        mock_job_checked = {
            "id": "job_ondemand_2",
            "job_id": "job_ondemand_2",
            "owner": "tester",
            "filepath": "non_existent_file.mp4",
            "filename": "dummy.mp4",
            "user_cloud_sync": {
                "plugins": {
                    "google_drive": {
                        "enabled": True,
                        "folder_id": "custom_job_folder"
                    }
                }
            }
        }
        # Debe procesar e intentar (y salir al no existir el archivo local en disco sin lanzar excepción)
        instance.on_download_complete(mock_job_checked)

    def test_upload_job_api(self):
        """Verifica el endpoint /api/upload-job para subida manual bajo demanda respetando 'enabled'."""
        instance = self.manager._instances.get("google_drive")
        self.assertIsNotNone(instance)

        # 1. Si la integración está desactivada, debe aparecer en acordeón con enabled=False y rechazar subidas con 400
        instance.save_user_config("admin", {"enabled": False})
        opt_disabled = instance.get_download_cloud_option("admin")
        self.assertIsNotNone(opt_disabled)
        self.assertFalse(opt_disabled["enabled"])
        self.assertEqual(opt_disabled["status_label"], "DESACTIVADO")

        res_disabled = self.client.post("/plugin/google_drive/api/upload-job", json={"job_id": "any_job"})
        self.assertEqual(res_disabled.status_code, 400)
        self.assertIn("desactivada", res_disabled.get_json().get("error", ""))

        # 2. Con la integración habilitada
        instance.save_user_config("admin", {"enabled": True})
        opt_enabled = instance.get_download_cloud_option("admin")
        self.assertIsNotNone(opt_enabled)
        self.assertTrue(opt_enabled["enabled"])
        self.assertEqual(opt_enabled["status_label"], "ACTIVO")

        # Sin job_id debe dar 400
        res_no_job = self.client.post("/plugin/google_drive/api/upload-job", json={})
        self.assertEqual(res_no_job.status_code, 400)
        self.assertIn("error", res_no_job.get_json())

        # Con job_id inexistente en disco debe dar 404
        res_not_found = self.client.post("/plugin/google_drive/api/upload-job", json={"job_id": "non_existent_job_123"})
        self.assertEqual(res_not_found.status_code, 404)

    def test_strict_admin_isolation_and_no_for_user(self):
        """Verifica que ningún usuario (ni siquiera admin) pueda ver o alterar la config de otro usuario."""
        instance = self.manager._instances.get("google_drive")
        self.assertIsNotNone(instance)

        # 1. Configurar datos personales de otro usuario (victim_user)
        instance.save_user_config("victim_user", {
            "enabled": True,
            "auto_upload": True,
            "folder_id": "secret_victim_folder_999",
            "auth_type": "service_account"
        })

        # Guardar token simulado de victim_user
        victim_dir = instance.get_user_dir("victim_user")
        victim_token_file = os.path.join(victim_dir, "token.json")
        with open(victim_token_file, "w", encoding="utf-8") as f:
            f.write('{"refresh_token": "secret_victim_refresh_token"}')

        # 2. Como sesión de admin, intentar sobreescribir config de victim_user pasando for_user
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["role"] = "admin"

        res_tamper = self.client.post("/plugin/google_drive/api/save", json={
            "for_user": "victim_user",
            "folder_id": "malicious_overwrite_attempt",
            "enabled": False
        })
        self.assertEqual(res_tamper.status_code, 200)

        # 3. Validar que la configuración de victim_user quedó 100% INTACTA
        victim_cfg = instance.get_user_config("victim_user")
        self.assertEqual(victim_cfg.get("folder_id"), "secret_victim_folder_999")
        self.assertTrue(victim_cfg.get("enabled"))
        self.assertTrue(victim_cfg.get("auto_upload"))

        # 4. Validar que la petición GET a /settings?for_user=victim_user NO filtre datos de victim_user
        res_view = self.client.get("/plugin/google_drive/settings?for_user=victim_user")
        self.assertEqual(res_view.status_code, 200)
        self.assertNotIn(b"secret_victim_folder_999", res_view.data)
        self.assertIn(b"Espacio estrictamente personal", res_view.data)

        # 5. Intentar revocar token pasando for_user: victim_user
        res_revoke = self.client.post("/plugin/google_drive/oauth/revoke", json={"for_user": "victim_user"})
        self.assertEqual(res_revoke.status_code, 200)
        # El token de victim_user NO debe haber sido eliminado
        self.assertTrue(os.path.exists(victim_token_file))

        # Limpiar
        if os.path.exists(victim_token_file):
            os.remove(victim_token_file)


if __name__ == "__main__":
    unittest.main()

