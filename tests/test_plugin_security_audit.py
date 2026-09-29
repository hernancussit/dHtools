"""
Test suite de auditoría y verificación de seguridad para plugins de dHtools
(Google Drive, Dropbox, Microsoft OneDrive).

Verifica:
1. Prevención de exposición de credenciales y secretos en el DOM/HTML (settings.html).
2. Prevención de IDOR y destrucción de archivos ajenos vía Safe Offload.
3. Prevención de Path Traversal en resolución de credenciales locales.
4. Cumplimiento de autenticación estricta (eliminación total del fallback inseguro a 'admin').
5. Protección contra manipulación de state y suplantación en flujos OAuth2.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import base64
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask
from core.plugin_manager import PluginManager
from plugins.google_drive import drive_client
from core.state import JOBS, JOBS_LOCK


class TestPluginSecurityAudit(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="dhtools_sec_audit_")
        self.app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
        self.app.config["TESTING"] = True
        self.app.secret_key = "audit_super_secret_key"
        self.manager = PluginManager()
        self.manager.init_app(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # =========================================================================
    # 1. PREVENCIÓN DE EXPOSICIÓN DE SECRETOS EN TEMPLATES HTML
    # =========================================================================

    def test_dropbox_app_secret_not_exposed_in_html(self):
        """Verifica que app_secret nunca se envíe en texto plano en el HTML de settings de Dropbox."""
        instance = self.manager._instances.get("dropbox")
        self.assertIsNotNone(instance)

        secret_value = "SUPER_SECRET_DROPBOX_KEY_XYZ999"
        instance.save_user_config("alice", {
            "enabled": True,
            "oauth": {
                "app_key": "alice_app_key",
                "app_secret": secret_value
            }
        })

        with self.client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["role"] = "downloader"

        resp = self.client.get("/plugin/dropbox/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(secret_value.encode(), resp.data, "app_secret nunca debe filtrarse en el DOM/HTML")
        self.assertIn(b'value=""', resp.data)

    def test_onedrive_client_secret_not_exposed_in_html(self):
        """Verifica que client_secret nunca se envíe en texto plano en el HTML de settings de OneDrive."""
        instance = self.manager._instances.get("onedrive")
        self.assertIsNotNone(instance)

        secret_value = "AZURE_ONEDRIVE_CLIENT_SECRET_TOPSECRET"
        instance.save_user_config("alice", {
            "enabled": True,
            "oauth": {
                "client_id": "alice_azure_id",
                "client_secret": secret_value
            }
        })

        with self.client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["role"] = "downloader"

        resp = self.client.get("/plugin/onedrive/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(secret_value.encode(), resp.data, "client_secret nunca debe filtrarse en el DOM/HTML")
        self.assertIn(b'value=""', resp.data)

    def test_google_drive_client_secret_not_exposed_in_html(self):
        """Verifica que client_secret de Google Drive se enmascare antes de renderizar la plantilla."""
        instance = self.manager._instances.get("google_drive")
        self.assertIsNotNone(instance)

        secret_value = "GOOGLE_OAUTH_CLIENT_SECRET_MASKED"
        instance.save_user_config("alice", {
            "enabled": True,
            "oauth": {
                "client_id": "google_client_id_123",
                "client_secret": secret_value
            }
        })

        with self.client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["role"] = "downloader"

        resp = self.client.get("/plugin/google_drive/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(secret_value.encode(), resp.data, "Google client_secret no debe exponerse en el HTML")

    # =========================================================================
    # 2. PREVENCIÓN DE IDOR Y DESTRUCCIÓN DE ARCHIVOS AJENOS (SAFE OFFLOAD)
    # =========================================================================

    def test_dropbox_idor_prevention_on_upload_job(self):
        """Un usuario 'bob' no debe poder transferir ni borrar un archivo perteneciente a 'alice'."""
        instance = self.manager._instances.get("dropbox")
        self.assertIsNotNone(instance)

        dummy_file = os.path.join(self.test_dir, "alice_private_file.mp4")
        with open(dummy_file, "w") as f:
            f.write("Alice private data")

        job_id = "job_sec_dropbox_1"
        with JOBS_LOCK:
            JOBS[job_id] = {
                "owner": "alice",
                "filepath": dummy_file,
                "filename": "alice_private_file.mp4",
                "status": "finished"
            }

        # Bob intenta subir el job de Alice
        ok, res = instance.upload_job_for_user(job_id=job_id, username="bob")
        self.assertFalse(ok)
        self.assertEqual(res.get("status_code"), 403)
        self.assertIn("No tienes permiso", res.get("error", ""))

        # El archivo local DEBE permanecer intacto (Safe Offload ajeno bloqueado)
        self.assertTrue(os.path.exists(dummy_file), "El archivo de Alice no debe borrarse por acciones de Bob")

    def test_onedrive_idor_prevention_on_upload_job(self):
        """Un usuario 'bob' no debe poder transferir ni borrar en OneDrive un archivo de 'alice'."""
        instance = self.manager._instances.get("onedrive")
        self.assertIsNotNone(instance)

        dummy_file = os.path.join(self.test_dir, "alice_onedrive_doc.mp4")
        with open(dummy_file, "w") as f:
            f.write("Alice confidential video")

        job_id = "job_sec_onedrive_1"
        with JOBS_LOCK:
            JOBS[job_id] = {
                "owner": "alice",
                "filepath": dummy_file,
                "filename": "alice_onedrive_doc.mp4",
                "status": "finished"
            }

        ok, res = instance.upload_job_for_user(job_id=job_id, username="bob")
        self.assertFalse(ok)
        self.assertEqual(res.get("status_code"), 403)
        self.assertIn("No tienes permiso", res.get("error", ""))
        self.assertTrue(os.path.exists(dummy_file), "El archivo físico no debe destruirse")

    def test_google_drive_idor_prevention_on_upload_job(self):
        """Un usuario 'bob' no debe poder transferir un archivo perteneciente a 'alice' en Google Drive."""
        instance = self.manager._instances.get("google_drive")
        self.assertIsNotNone(instance)

        dummy_file = os.path.join(self.test_dir, "alice_gdrive_video.mp4")
        with open(dummy_file, "w") as f:
            f.write("Alice private GDrive data")

        job_id = "job_sec_gdrive_1"
        with JOBS_LOCK:
            JOBS[job_id] = {
                "owner": "alice",
                "filepath": dummy_file,
                "filename": "alice_gdrive_video.mp4",
                "status": "finished"
            }

        # Asegurar config habilitada para bob para llegar al chequeo de propiedad
        instance.save_user_config("bob", {"enabled": True})

        ok, res = instance.upload_job_for_user(job_id=job_id, username="bob", is_admin=False)
        self.assertFalse(ok)
        self.assertEqual(res.get("status_code"), 403)
        self.assertIn("No tienes permiso", res.get("error", ""))
        self.assertTrue(os.path.exists(dummy_file))

    # =========================================================================
    # 3. PREVENCIÓN DE PATH TRAVERSAL EN GOOGLE DRIVE CLIENT
    # =========================================================================

    def test_drive_client_resolve_path_blocks_directory_traversal(self):
        """drive_client._resolve_path debe rechazar intentos de ../ y rutas fuera del directorio base."""
        base_dir = os.path.join(self.test_dir, "plugin_base")
        os.makedirs(base_dir, exist_ok=True)

        # Intentos de traversal relativo deben retornar cadena vacía (rechazados)
        self.assertEqual(drive_client._resolve_path("../../../../etc/passwd", base_dir), "")
        self.assertEqual(drive_client._resolve_path("..\\..\\admin\\token.json", base_dir), "")
        self.assertEqual(drive_client._resolve_path("C:\\Windows\\System32\\cmd.exe", base_dir), "")

        # Archivo legítimo dentro de base_dir debe resolverse dentro de base_dir
        valid_resolved = drive_client._resolve_path("service_account.json", base_dir)
        self.assertEqual(valid_resolved, os.path.join(base_dir, "service_account.json"))

    # =========================================================================
    # 4. EXIGENCIA DE AUTENTICACIÓN ESTRICTA (SIN FALLBACK A 'admin')
    # =========================================================================

    def test_unauthenticated_api_requests_rejected_with_401(self):
        """Todas las APIs de plugins deben retornar 401 si no hay sesión iniciada."""
        # 1. Dropbox API
        res_db = self.client.post("/plugin/dropbox/api/settings", json={"enabled": True})
        self.assertEqual(res_db.status_code, 401)
        self.assertFalse(res_db.get_json()["success"])

        res_db_up = self.client.post("/plugin/dropbox/api/upload/job_123")
        self.assertEqual(res_db_up.status_code, 401)

        # 2. OneDrive API
        res_od = self.client.post("/plugin/onedrive/api/settings", json={"enabled": True})
        self.assertEqual(res_od.status_code, 401)
        self.assertFalse(res_od.get_json()["success"])

        res_od_up = self.client.post("/plugin/onedrive/api/upload/job_123")
        self.assertEqual(res_od_up.status_code, 401)

        # 3. Google Drive API
        res_gd = self.client.post("/plugin/google_drive/api/save", json={"enabled": True})
        self.assertEqual(res_gd.status_code, 401)
        self.assertFalse(res_gd.get_json()["success"])

        res_gd_up = self.client.post("/plugin/google_drive/api/upload-job", json={"job_id": "job_123"})
        self.assertEqual(res_gd_up.status_code, 401)

    def test_unauthenticated_settings_views_redirect_to_login(self):
        """Las vistas de configuración de plugins deben redirigir a /login si no hay usuario."""
        for endpoint in ["/plugin/dropbox/settings", "/plugin/onedrive/settings", "/plugin/google_drive/settings"]:
            resp = self.client.get(endpoint)
            self.assertEqual(resp.status_code, 302, f"{endpoint} debe redirigir si no está autenticado")
            self.assertIn("login", resp.location.lower(), f"{endpoint} debe redirigir a login")

    # =========================================================================
    # 5. PROTECCIÓN CONTRA SUPLANTACIÓN EN CALLBACKS OAUTH2
    # =========================================================================

    def test_dropbox_oauth_callback_rejects_user_spoofing(self):
        """Si un usuario autenticado 'alice' recibe un callback con state de 'bob', debe ser rechazado."""
        with self.client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["role"] = "downloader"

        # State generado maliciosamente para bob
        tampered_state = base64.urlsafe_b64encode(json.dumps({"u": "bob", "t": int(time.time()), "p": "dropbox"}).encode()).decode()

        resp = self.client.get(f"/plugin/dropbox/auth/callback?code=mock_code_123&state={tampered_state}")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=", resp.location)
        import urllib.parse
        self.assertIn("seguridad", urllib.parse.unquote(resp.location).lower())

    def test_onedrive_oauth_callback_rejects_user_spoofing(self):
        """Si un usuario autenticado 'alice' recibe un callback con state de 'bob', debe ser rechazado en OneDrive."""
        with self.client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["role"] = "downloader"

        tampered_state = base64.urlsafe_b64encode(json.dumps({"u": "bob", "t": int(time.time()), "p": "onedrive"}).encode()).decode()

        resp = self.client.get(f"/plugin/onedrive/auth/callback?code=mock_code_123&state={tampered_state}")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=", resp.location)
        self.assertIn("seguridad", resp.location.lower())


if __name__ == "__main__":
    unittest.main()
