# 🧩 Guía de Desarrollo de Plugins para dHtools [EXPERIMENTAL]

> [!WARNING]
> ### ⚠️ Estado de la Característica: EXPERIMENTAL
> La arquitectura de plugins de **dHtools** se encuentra en fase **EXPERIMENTAL**.
> Todos los módulos y desarrollos deben implementarse asumiendo posibles ampliaciones de API en futuras versiones.

Esta guía está diseñada para permitirte desarrollar extensiones, automatizaciones privadas, conectores y **servicios de mensajería independientes (como un segundo Bot de Telegram, Discord o WhatsApp)** sin tocar el código fuente principal de dHtools ni subir código confidencial a Git o GitHub.

---

## 🔒 1. Aislamiento Estricto en Git

Para proteger tu privacidad e infraestructura:
* La carpeta `plugins/` está configurada en `.gitignore` para ignorar **automáticamente** cualquier carpeta de plugin privada que agregues (`plugins/*`).
* Las únicas excepciones rastreadas en Git son `plugins/template_example/`, `plugins/README.md` y `plugins/.gitkeep`.
* Si creas `plugins/mi_bot_privado/`, Git lo ignorará por completo. Podrás hacer `git pull` de actualizaciones oficiales de `main` o `dev` sin ningún conflicto.
* Además, los archivos dentro de `plugins/` se montan automáticamente en el contenedor Docker (`.:/app`), por lo que tus plugins están disponibles en caliente.

---

## 📁 2. Estructura de un Plugin

Cada plugin debe residir en su propio subdirectorio dentro de `plugins/`:

```text
plugins/
└── mi_bot_privado/
    ├── plugin.json          # Metadatos obligatorios y activación
    ├── plugin.py            # Código Python principal (Clase Plugin)
    ├── config.json          # (Recomendado) Tus tokens y credenciales privadas
    └── handlers.py          # (Opcional) Módulos auxiliares de tu plugin
```

### El archivo `plugin.json` (Manifiesto)
```json
{
  "id": "mi_bot_privado",
  "name": "Mi Bot Notificador [EXPERIMENTAL]",
  "version": "1.0.0",
  "author": "Tu Nombre",
  "description": "Segundo bot de Telegram para alertas privadas en canal.",
  "icon": "🤖",
  "status": "experimental",
  "enabled": true
}
```
*Si `"enabled": false`, el PluginManager descubrirá el plugin pero no lo cargará en memoria.*

---

## ⚙️ 3. El Contrato del Plugin (`plugin.py`)

El gestor de dHtools busca una clase llamada `Plugin` en `plugin.py`. Todos los métodos son **opcionales**; sólo implementas los que necesites.

```python
import os
import json
import logging
import threading
from flask import Blueprint, jsonify

logger = logging.getLogger("dhtools.plugins.mi_bot")

class Plugin:
    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.metadata = metadata or {}
        self.plugin_id = self.metadata.get("id")
        self.name = self.metadata.get("name")
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

    def register_routes(self, app):
        """(Opcional) Registra endpoints web bajo /plugin/<plugin_id>/"""
        bp = Blueprint(f"plugin_{self.plugin_id}", __name__)
        @bp.route(f"/plugin/{self.plugin_id}/ping")
        def ping():
            return jsonify({"status": "ok", "plugin": self.name})
        app.register_blueprint(bp)

    def on_startup(self, app, context):
        """(Opcional) Se ejecuta al arrancar el servidor en un hilo daemon."""
        logger.info(f"[EXPERIMENTAL] Iniciando servicios de {self.name}")

    def on_download_complete(self, job_data):
        """(Opcional) Se ejecuta cuando CUALQUIER descarga finaliza con éxito."""
        pass

    def on_download_error(self, job_data, error=None):
        """(Opcional) Se ejecuta cuando una descarga falla."""
        pass
```

---

## 🤖 4. Caso de Uso: Segundo Bot de Telegram en Paralelo

Para tener un segundo bot de Telegram (o alertador de Discord/WhatsApp) corriendo de forma autónoma sin interferir con el bot principal de dHtools:

```python
import os
import json
import threading
import telebot

class Plugin:
    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.bot = None

        # Cargar configuración privada (tokens, IDs de chat)
        cfg_path = os.path.join(self.plugin_dir, "config.json")
        self.config = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)

    def on_startup(self, app, context):
        token = self.config.get("telegram_token")
        if not token:
            return

        # 1. Instanciar el segundo bot con su propio token independiente
        self.bot = telebot.TeleBot(token)

        # 2. Registrar comandos propios
        @self.bot.message_handler(commands=['start', 'ping'])
        def handle_start(message):
            self.bot.reply_to(message, "🤖 Segundo bot [EXPERIMENTAL] activo y conectado a dHtools!")

        @self.bot.message_handler(commands=['descargar'])
        def handle_download(message):
            parts = message.text.split(maxsplit=1)
            if len(parts) > 1:
                url = parts[1].strip()
                # 3. Solicitar la descarga al Core de dHtools
                res = self.manager.enqueue_download(url=url, quality="best", owner="plugin_bot")
                if res.get("success"):
                    self.bot.reply_to(message, f"✅ Encolado en dHtools con ID: {res['job_id']}")
                else:
                    self.bot.reply_to(message, f"❌ Error: {res.get('error')}")

        # 4. Lanzar polling en un hilo daemon para no bloquear Flask
        def _poll():
            self.bot.infinity_polling()

        threading.Thread(target=_poll, daemon=True, name="SecondTelegramBotThread").start()

    def on_download_complete(self, job_data):
        """Notificar a un canal privado de Telegram cuando termine una descarga"""
        chat_id = self.config.get("alert_chat_id")
        if not self.bot or not chat_id:
            return

        title = job_data.get("title") or job_data.get("filename")
        filesize_mb = round(os.path.getsize(job_data.get("filepath", "")) / (1024 * 1024), 2)
        
        msg = f"🎉 *¡Descarga Finalizada!*\n\n📁 *Título:* {title}\n💾 *Peso:* {filesize_mb} MB"
        self.bot.send_message(chat_id, msg, parse_mode="Markdown")
```

---

## 🛠️ 5. API del PluginManager disponible para tu Plugin

Desde `self.manager` puedes acceder a métodos seguros del core:

| Método | Descripción |
|---|---|
| `self.manager.enqueue_download(url, quality="best", format_type="video", owner="admin", title="", extra_params=None)` | Solicita una nueva descarga al core de dHtools (se procesará con Cobalt, yt-dlp, PO Token y túnel residencial según corresponda). Retorna `{"success": True, "job_id": "..."}`. |
| `self.manager.plugins_dir` | Ruta absoluta a la carpeta `/plugins`. |
| `self.manager.get_all_plugins()` | Lista de plugins instalados y sus estados. |

---

## 📋 6. DIRECTIVA MAESTRA (Prompt para tu Nuevo Chat)

> [!TIP]
> **Copia y pega el siguiente bloque como PRIMER MENSAJE en tu nuevo chat de IA.**
> Esto le dará todo el contexto arquitectónico necesario sin que tengas que explicar dHtools desde cero.

```markdown
Hola. Necesito desarrollar un plugin privado para una plataforma multimedia autohospedable llamada **dHtools** (construida sobre Python 3.11, Flask y Docker Compose).

El proyecto cuenta con una arquitectura de plugins en estado **[EXPERIMENTAL]** y totalmente desacoplada del core.

### ⚠️ Reglas estrictas de desarrollo:
1. **Todo el código debe estar encapsulado dentro de la carpeta:** `plugins/<nombre_de_mi_plugin>/`.
2. **NO debes modificar ningún archivo existente fuera de mi carpeta de plugin** (ni app.py, ni core/, ni templates/).
3. La carpeta contiene:
   - `plugin.json`: Manifiesto con `id`, `name`, `version`, `author`, `description`, `"status": "experimental"`, `"enabled": true`.
   - `plugin.py`: Clase `Plugin` con constructor `__init__(self, manager=None, metadata=None)`.
   - `config.json`: Archivo local para mis credenciales y tokens privados (ignorado por Git).

### 🧩 Ganchos (Hooks) disponibles que puedo implementar en mi clase `Plugin`:
- `register_routes(self, app)`: Registrar un Blueprint Flask bajo el prefijo `/plugin/<mi_plugin_id>/`.
- `on_startup(self, app, context)`: Inicializar clientes, conexiones o hilos daemon en segundo plano (`threading.Thread(daemon=True)`).
- `on_download_complete(self, job_data)`: Recibe metadatos de descargas completadas (`job_id`, `title`, `filepath`, `filename`, `owner`, `url`, `format_type`, `quality`).
- `on_download_error(self, job_data, error=None)`: Notificación de descargas fallidas.
- Para solicitar descargas a dHtools: `self.manager.enqueue_download(url=..., quality="best", owner=...)`.

### 🎯 Objetivo específico de este plugin:
[AQUÍ DESCRIBES TU IDEA: Por ejemplo: "Quiero implementar un segundo bot de Telegram que escuche en el token X, acepte el comando /subir y envíe los archivos terminados a mi canal privado con ID Y"].

Por favor, procedé a diseñar y estructurar los archivos necesarios (`plugin.json`, `plugin.py`, `config.json`) para este plugin.
```
