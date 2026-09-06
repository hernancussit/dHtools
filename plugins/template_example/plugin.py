"""
[EXPERIMENTAL] Plugin de Plantilla de Referencia para dHtools
Este archivo ilustra cómo construir un plugin completo:
1. Registro de rutas Flask (Blueprint).
2. Hooks de ciclo de vida (arranque, descarga completada, descarga fallida).
3. Hilo en segundo plano (daemon) para servicios independientes (ej. segundo Bot de Telegram).
4. Invocación de descargas a través de la API del PluginManager.
"""

import os
import time
import logging
import threading
from flask import Blueprint, jsonify, render_template_string

logger = logging.getLogger("dhtools.plugins.template_example")


class Plugin:
    """
    [EXPERIMENTAL] Clase principal del plugin.
    El PluginManager busca una clase llamada 'Plugin' o '<Id>Plugin'.
    """
    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.metadata = metadata or {}
        self.plugin_id = self.metadata.get("id", "template_example")
        self.name = self.metadata.get("name", "Plugin de Ejemplo")
        self.version = self.metadata.get("version", "1.0.0")
        self._running = False
        logger.info(f"[EXPERIMENTAL] Instanciando {self.name} v{self.version}")

    def register_routes(self, app):
        """
        Registra rutas web y endpoints API propios bajo /plugin/<plugin_id>/.
        """
        bp = Blueprint(f"plugin_{self.plugin_id}", __name__)

        @bp.route(f"/plugin/{self.plugin_id}/status")
        def plugin_status():
            return jsonify({
                "status": "ok",
                "experimental": True,
                "plugin_id": self.plugin_id,
                "name": self.name,
                "version": self.version,
                "active_threads": threading.active_count(),
                "message": "El plugin de plantilla experimental está funcionando correctamente."
            })

        @bp.route(f"/plugin/{self.plugin_id}/test-download", methods=["POST"])
        def test_download():
            # Demostración: solicitar una descarga al motor de dHtools
            if self.manager:
                res = self.manager.enqueue_download(
                    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    quality="best",
                    owner="admin",
                    title="Prueba desde Plugin Experimental"
                )
                return jsonify(res)
            return jsonify({"error": "PluginManager no disponible"}), 500

        app.register_blueprint(bp)
        logger.info(f"Rutas registradas bajo el prefijo /plugin/{self.plugin_id}/")

    def get_ui_nav_item(self):
        """
        (Opcional) Retorna un diccionario para inyectar un enlace en la barra de navegación.
        """
        return {
            "title": "Plantilla",
            "url": f"/plugin/{self.plugin_id}/status",
            "icon": "🧪",
            "badge": "EXP"
        }

    def on_startup(self, app, context):
        """
        Hook ejecutado al arrancar el servidor web (dentro de un hilo daemon).
        Ideal para iniciar un segundo bot de Telegram, cliente de Discord o listener.
        """
        logger.info(f"[EXPERIMENTAL] {self.name}: Ejecutando on_startup.")
        self._running = True

        # Ejemplo: Lanzar un hilo en segundo plano
        def _background_worker():
            logger.info(f"[EXPERIMENTAL] {self.name}: Hilo en segundo plano iniciado.")
            # AQUÍ ES DONDE INICIARÍAS TU SEGUNDO BOT DE TELEGRAM:
            # import telebot
            # bot = telebot.TeleBot("TU_OTRO_TOKEN_AQUI")
            # @bot.message_handler(commands=['ayuda'])
            # def send_help(msg):
            #     bot.reply_to(msg, "Hola desde el segundo bot experimental!")
            # bot.infinity_polling()
            while self._running:
                time.sleep(60)

        threading.Thread(target=_background_worker, daemon=True, name=f"worker-{self.plugin_id}").start()

    def on_download_complete(self, job_data):
        """
        Hook ejecutado cada vez que dHtools completa una descarga exitosamente.
        job_data contiene: job_id, title, filepath, filename, owner, url, format_type, quality, etc.
        """
        title = job_data.get("title") or job_data.get("filename", "desconocido")
        filepath = job_data.get("filepath", "")
        owner = job_data.get("owner", "admin")
        filesize = os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 0

        logger.info(
            f"[EXPERIMENTAL] {self.name} -> Descarga completada detectada: "
            f"'{title}' ({filesize} bytes) por usuario '{owner}'"
        )
        # AQUÍ PUEDES:
        # 1. Enviar el archivo a tu canal o chat de Telegram privado con tu segundo bot.
        # 2. Notificar por Discord, WhatsApp o Webhook.
        # 3. Mover o copiar el archivo a una ruta específica fuera de dHtools.

    def on_download_error(self, job_data, error=None):
        """
        Hook ejecutado si una descarga falla.
        """
        job_id = job_data.get("job_id") or job_data.get("id")
        logger.warning(f"[EXPERIMENTAL] {self.name} -> Fallo en descarga {job_id}: {error}")
