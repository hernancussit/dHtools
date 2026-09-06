# 🧩 Guía y Referencia Oficial del SDK de Plugins para dHtools [EXPERIMENTAL]

> [!WARNING]
> ### ⚠️ Estado de la Característica: EXPERIMENTAL
> La arquitectura de plugins y extensiones de **dHtools** se encuentra en fase **EXPERIMENTAL**.
> Todos los módulos y desarrollos deben implementarse asumiendo posibles ampliaciones de API en futuras versiones, manteniendo retrocompatibilidad y aislamiento estricto.

Esta guía constituye la **especificación técnica completa del SDK de Plugins de dHtools**. Permite diseñar, programar e integrar extensiones, automatizaciones privadas, conectores de almacenamiento en la nube (**Google Drive, OneDrive, Dropbox, Nextcloud, Box**) y **servicios de mensajería independientes (segundo bot de Telegram, Discord, webhooks)** sin modificar una sola línea del código fuente del núcleo (`core/`, `app.py`, `templates/`) ni exponer credenciales privadas al control de versiones.

---

## 📑 Tabla de Contenidos
1. [Aislamiento Estricto y Control de Versiones](#-1-aislamiento-estricto-y-control-de-versiones)
2. [Estructura de Carpetas y Manifiesto (`plugin.json`)](#-2-estructura-de-carpetas-y-manifiesto-pluginjson)
3. [Ciclo de Vida y Contrato de la Clase `Plugin` (`plugin.py`)](#-3-ciclo-de-vida-y-contrato-de-la-clase-plugin-pluginpy)
4. [Referencia Exhaustiva de Métodos y Hooks de la Clase `Plugin`](#-4-referencia-exhaustiva-de-métodos-y-hooks-de-la-clase-plugin)
5. [Referencia Exhaustiva de la API del SDK (`self.manager`)](#-5-referencia-exhaustiva-de-la-api-del-sdk-selfmanager)
6. [Protocolo Oficial de Proveedores de Almacenamiento en la Nube (Cloud Storage)](#-6-protocolo-oficial-de-proveedores-de-almacenamiento-en-la-nube-cloud-storage)
7. [Protocolo de Integración con el Bot Oficial de Telegram](#-7-protocolo-de-integración-con-el-bot-oficial-de-telegram)
8. [Protocolo de Inyección en la Interfaz Web y Navegación](#-8-protocolo-de-inyección-en-la-interfaz-web-y-navegación)
9. [Diccionario de Datos y Payloads Normalizados](#-9-diccionario-de-datos-y-payloads-normalizados)
10. [Ejemplo Completo: Plugin de Almacenamiento (OneDrive / Cloud)](#-10-ejemplo-completo-plugin-de-almacenamiento-onedrive--cloud)
11. [Ejemplo Completo: Segundo Bot Autónomo (Notificador / Asistente)](#-11-ejemplo-completo-segundo-bot-autónomo-notificador--asistente)
12. [Actualizaciones Automáticas de Plugins vía GitHub](#-12-actualizaciones-automáticas-de-plugins-vía-github)
13. [Directiva Maestra (Master Prompt para Nuevos Chats de IA)](#-13-directiva-maestra-master-prompt-para-nuevos-chats-de-ia)

---

## 🔒 1. Aislamiento Estricto y Control de Versiones

Para garantizar máxima privacidad, soberanía de datos y actualizaciones sin fricción:
* La carpeta `plugins/` en la raíz del repositorio está configurada en `.gitignore` para ignorar automáticamente cualquier subcarpeta de plugin privada (`plugins/*`).
* Las únicas rutas rastreadas en Git son `plugins/template_example/`, `plugins/README.md` y `plugins/.gitkeep`.
* Si creas `plugins/mi_extension/`, Git lo ignorará por completo. Podrás hacer `git pull origin dev` o `main` sin conflictos de mezcla (*merge conflicts*).
* Los archivos dentro de `plugins/` se montan automáticamente en el contenedor Docker en producción (`.:/app`), permitiendo recargar extensiones en caliente sin reconstruir la imagen.

---

## 📁 2. Estructura de Carpetas y Manifiesto (`plugin.json`)

Cada plugin reside en su propio subdirectorio dentro de `plugins/<plugin_id>/`:

```text
plugins/
└── mi_extension/
    ├── plugin.json          # Manifiesto obligatorio con metadatos y activación
    ├── plugin.py            # Clase principal Plugin (Hooks y lógica)
    ├── config.json          # (Opcional/Privado) Credenciales y tokens del plugin
    ├── static/              # (Opcional) CSS, JS e imágenes propias
    ├── templates/           # (Opcional) Plantillas Jinja2 propias
    └── core/                # (Opcional) Módulos y controladores auxiliares
```

### Esquema del Manifiesto `plugin.json`
```json
{
  "id": "mi_extension",
  "name": "Mi Extensión Cloud [EXPERIMENTAL]",
  "version": "1.0.0",
  "author": "Tu Nombre / Empresa",
  "description": "Descripción clara de las capacidades que añade la extensión.",
  "icon": "☁️",
  "status": "experimental",
  "enabled": true,
  "repository": "https://github.com/tu-usuario/mi-plugin",
  "branch": "main",
  "settings_url": "/plugin/mi_extension/settings"
}
```

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id` | `string` | **Sí** | Identificador único en minúsculas y snake_case (coincide con el nombre de la carpeta). |
| `name` | `string` | **Sí** | Nombre legible para humanos en paneles e interfaces. |
| `version` | `string` | **Sí** | Versión SemVer (ej. `"1.0.0"`). |
| `author` | `string` | No | Autor o equipo creador. |
| `description` | `string` | No | Resumen de funcionalidades para el panel de administración. |
| `icon` | `string` | No | Emoji o icono identificador (ej. `"📁"`, `"☁️"`, `"🤖"`). |
| `status` | `string` | No | `"experimental"` o `"stable"`. |
| `enabled` | `bool` | **Sí** | Si es `false`, el sistema descubre la carpeta pero no la carga en memoria. |
| `repository` | `string` | No | URL del repositorio de GitHub (ej. `"https://github.com/user/repo"` o `"user/repo"`). Permite comprobación y actualización en 1 clic desde el Panel de Admin. |
| `branch` | `string` | No | Rama de Git a rastrear para actualizaciones (por defecto `"main"`). |
| `settings_url` | `string` | No | Ruta web absoluta hacia la página de ajustes o dashboard del plugin. |

---

## ⚙️ 3. Ciclo de Vida y Contrato de la Clase `Plugin` (`plugin.py`)

El gestor `PluginManager` busca en `plugin.py` una clase llamada `Plugin` o `<Id_capitalizado>Plugin`.
Todos los métodos son **opcionales**; implementa únicamente aquellos necesarios para tu caso de uso.

```python
class Plugin:
    def __init__(self, manager=None, metadata=None):
        self.manager = manager                # Instancia de PluginManager (SDK de dHtools)
        self.metadata = metadata or {}        # Metadatos leídos de plugin.json
        self.plugin_id = self.metadata.get("id", "mi_extension")
        self.name = self.metadata.get("name", "Mi Extensión")
```

---

## 📖 4. Referencia Exhaustiva de Métodos y Hooks de la Clase `Plugin`

### 1. `register_routes(self, app)`
* **Propósito:** Registrar rutas web, endpoints REST o páginas HTML servidas por Flask.
* **Cuándo se ejecuta:** Al inicializar la aplicación Flask.
* **Parámetros:**
  * `app`: Objeto `Flask` principal de la aplicación.
* **Convención:** Registrar un `Blueprint` con prefijo `/plugin/<plugin_id>/`.
```python
def register_routes(self, app):
    from flask import Blueprint, jsonify
    bp = Blueprint(f"plugin_{self.plugin_id}", __name__)
    
    @bp.route(f"/plugin/{self.plugin_id}/status")
    def status():
        return jsonify({"status": "ok", "active": True})
        
    app.register_blueprint(bp)
```

---

### 2. `on_startup(self, app, context)`
* **Propósito:** Inicializar conexiones, clientes externos, servicios daemon o trabajadores en segundo plano.
* **Cuándo se ejecuta:** Al arrancar los hilos de fondo del servidor web (invocado dentro de un hilo secundario protegido).
* **Parámetros:**
  * `app`: Objeto `Flask`.
  * `context`: Diccionario con variables de entorno del servidor (`"app"`, `"plugins_dir"`, etc.).
```python
def on_startup(self, app, context):
    import threading
    def worker():
        # Tu bucle de escucha o polling aquí
        pass
    threading.Thread(target=worker, daemon=True, name=f"{self.plugin_id}_worker").start()
```

---

### 3. `on_download_complete(self, job_data)`
* **Propósito:** Reaccionar de forma reactiva cada vez que dHtools finaliza una descarga con éxito en disco.
* **Cuándo se ejecuta:** Al completarse cualquier descarga vía motor nativo, yt-dlp o Cobalt.
* **Parámetros:**
  * `job_data`: Diccionario normalizado con todos los metadatos del archivo y la tarea (ver sección [Diccionario de Datos](#-9-diccionario-de-datos-y-payloads-normalizados)).
```python
def on_download_complete(self, job_data: dict):
    job_id = job_data.get("job_id")
    filepath = job_data.get("filepath")
    owner = job_data.get("owner")
    # Subir a la nube, notificar a un webhook o mover el archivo
```

---

### 4. `on_download_error(self, job_data, error=None)`
* **Propósito:** Recibir alertas cuando una descarga falla o se aborta.
* **Parámetros:**
  * `job_data`: Diccionario con la información del trabajo que falló.
  * `error`: Mensaje o excepción capturada (string o Exception).
```python
def on_download_error(self, job_data: dict, error=None):
    job_id = job_data.get("job_id")
    # Registrar métricas o alertar al administrador
```

---

### 5. `get_admin_cloud_panel(self, config=None) -> Dict[str, Any]`
* **Propósito:** Inyectar una tarjeta informativa o panel de control en la pestaña **Cloud Sync** de `/admin`.
* **Retorno esperado:**
```python
def get_admin_cloud_panel(self, config=None):
    return {
        "id": self.plugin_id,
        "title": "Microsoft OneDrive",
        "icon": "☁️",
        "badge": "EXP",
        "settings_url": f"/plugin/{self.plugin_id}/settings",
        "html_content": "<p>Conector de almacenamiento empresarial.</p>"
    }
```

---

### 6. `get_download_cloud_option(self, username=None) -> Dict[str, Any]`
* **Propósito:** Inyectar el proveedor en el acordeón de almacenamiento en la nube de la web de descargas y en los presets de usuario.
* **Parámetros:**
  * `username` (`str`, opcional): Usuario autenticado consultando la vista.
* **Retorno esperado:**
```python
def get_download_cloud_option(self, username=None):
    is_active = self.is_user_enabled(username)
    return {
        "id": self.plugin_id,
        "name": "Microsoft OneDrive",
        "icon": "☁️",
        "enabled": is_active,
        "auto_upload": False,
        "status_label": "ACTIVO" if is_active else "DESACTIVADO",
        "status_badge": "success" if is_active else "danger",
        "description": "Sube el archivo automáticamente a tu cuenta de OneDrive.",
        "fields": [
            {
                "id": "remote_folder",
                "label": "Carpeta de Destino (opcional)",
                "type": "text",
                "placeholder": "/Videos/dHtools"
            }
        ],
        "settings_url": f"/plugin/{self.plugin_id}/settings"
    }
```

---

### 7. `upload_job_for_user(self, job_id, username, progress_callback=None) -> Tuple[bool, Dict[str, Any]]`
* **Propósito:** Contrato estándar para subida manual bajo demanda de descargas existentes, invocable desde la web, la API o el comando `/descargas` de Telegram.
* **Parámetros:**
  * `job_id` (`str`): ID de la descarga en dHtools.
  * `username` (`str`): Usuario dueño de la descarga.
  * `progress_callback` (`callable`, opcional): Función `callback(percent: int, message: str)` para reportar progreso en tiempo real.
* **Retorno esperado:** Tupla `(éxito, resultado)`.
  * Éxito: `(True, {"filename": "video.mp4", "web_link": "https://..."})`
  * Error: `(False, {"error": "Mensaje detallado del error"})`

---

### 8. `upload_file_for_user(self, filepath, username, target_filename=None, progress_callback=None) -> Tuple[bool, Dict[str, Any]]`
* **Propósito:** Contrato oficial del SDK para que un plugin de almacenamiento suba cualquier archivo arbitrario en disco a la nube del usuario especificado (independientemente de si proviene de una descarga de dHtools o si fue generado por otro plugin como reportes, logs, backups, etc.).
* **Parámetros:**
  * `filepath` (`str`): Ruta absoluta al archivo local en disco.
  * `username` (`str`): Usuario dueño de la cuenta de nube receptora.
  * `target_filename` (`str`, opcional): Nombre limpio que tendrá el archivo en la nube (por defecto el nombre en disco).
  * `progress_callback` (`callable`, opcional): Función `callback(percent: int, message: str)`.
* **Retorno esperado:** Tupla `(éxito, resultado)` (`(True, {"filename": "...", "web_link": "..."})` o `(False, {"error": "..."})`).

---

### 9. `get_user_nav_item(self, username=None) -> Dict[str, Any]`
* **Propósito:** Inyectar un botón de acceso directo en el panel de seguridad/herramientas de usuario (sidebar de escritorio) y en el menú lateral móvil (drawer).
* **Retorno esperado:**
```python
def get_user_nav_item(self, username=None):
    return {
        "id": self.plugin_id,
        "title": "OneDrive",
        "full_title": "OneDrive Cloud Sync",
        "icon": "☁️",
        "url": f"/plugin/{self.plugin_id}/settings",
        "enabled": True
    }
```

---

### 9. `get_telegram_commands(self) -> List[Dict[str, str]]`
* **Propósito:** Registrar comandos adicionales que se añaden dinámicamente al menú de `/ayuda` del Bot Oficial de Telegram.
* **Retorno esperado:**
```python
def get_telegram_commands(self):
    return [
        {"command": "/onedrive", "description": "Consultar almacenamiento y estado de OneDrive"}
    ]
```

---

### 10. `on_telegram_command(self, cmd, args, message, bot) -> bool`
* **Propósito:** Interceptar y procesar comandos de Telegram enviados al Bot Oficial.
* **Parámetros:**
  * `cmd` (`str`): Comando recibido en minúsculas (ej. `"/onedrive"`).
  * `args` (`list[str]`): Argumentos que acompañan al comando.
  * `message` (`dict`): Objeto de mensaje de Telegram (con `chat.id`, `from.id`, etc.).
  * `bot` (`TelegramBot`): Instancia del bot oficial con métodos `send_message`, `edit_message`, etc.
* **Retorno:** `True` si el plugin procesó el comando; `False` para delegarlo a otros plugins.

---

### 11. `on_telegram_callback(self, query, data, bot) -> bool`
* **Propósito:** Interceptar y procesar interacciones con botones inline (`callback_query`) en el Bot Oficial.
* **Parámetros:**
  * `query` (`dict`): Objeto de consulta de Telegram.
  * `data` (`str`): Cadena payload asociada al botón presionado.
  * `bot` (`TelegramBot`): Instancia del bot oficial.
* **Retorno:** `True` si el plugin procesó el callback; `False` para delegarlo a otros plugins.

---

## 🛠️ 5. Referencia Exhaustiva de la API del SDK (`self.manager`)

Desde cualquier método de tu clase `Plugin`, puedes acceder a los servicios centrales de dHtools a través de `self.manager`:

```python
# Acceso directo al SDK
pm = self.manager
```

### Métodos Principales de `PluginManager`:

#### 1. `self.manager.enqueue_download(...) -> Dict[str, Any]`
Permite a una extensión ordenar al motor de dHtools la descarga y procesamiento de un video o audio de forma completamente programática (sin peticiones HTTP).
```python
result = self.manager.enqueue_download(
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    quality="1080p",           # "best", "1080p", "720p", "480p", "audio_320", "audio_192", "flac"
    format_type="video",       # "video" o "audio"
    owner="admin",             # Usuario dueño de la descarga
    title="Título Opcional",   # Nombre descriptivo
    extra_params={
        "video_format": "mp4", # "mp4", "mkv", "webm", "mp3", "flac"
        "subtitles": "none",   # "none", "es", "en", "all"
        "engine": "auto",      # "auto", "ytdlp", "cobalt"
        "user_cloud_sync": {   # Opcional: auto-sincronización con nubes
            "plugins": {
                "onedrive": {"enabled": True}
            }
        }
    }
)
# Retorna: {"success": True, "job_id": "...", "url": "..."}
```

#### 2. `self.manager.get_user_cloud_providers(username=None) -> List[Dict[str, Any]]`
Consulta todos los plugins de almacenamiento en la nube disponibles y su estado de activación para el usuario dado.
```python
providers = self.manager.get_user_cloud_providers("hernan")
# Retorna:
# [
#   {"id": "google_drive", "name": "Google Drive", "icon": "📁", "enabled": True, "auto_upload": False, ...},
#   {"id": "onedrive", "name": "Microsoft OneDrive", "icon": "☁️", "enabled": False, ...}
# ]
```

#### 3. `self.manager.upload_job_to_cloud(plugin_id, job_id, username, progress_callback=None) -> Tuple[bool, Dict[str, Any]]`
Despacha la subida de una descarga registrada hacia cualquier plugin de almacenamiento en la nube.
```python
ok, res = self.manager.upload_job_to_cloud("onedrive", "abc12345", "hernan")
if ok:
    print("Enlace generado:", res["web_link"])
else:
    print("Error:", res["error"])
```

#### 4. `self.manager.upload_file_to_cloud(plugin_id, filepath, username, progress_callback=None) -> Tuple[bool, Dict[str, Any]]`
Permite a cualquier plugin auxiliar (ej. `Remote Assist`) subir **cualquier archivo arbitrario en disco** directamente a la nube del usuario (Google Drive, OneDrive, etc.) sin necesidad de implementar clientes OAuth2 propios.
```python
ok, res = self.manager.upload_file_to_cloud("google_drive", "/tmp/reporte_diagnostico.zip", "hernan")
if ok:
    print("Archivo subido:", res["web_link"])
else:
    print("Error:", res["error"])
```

#### 5. `self.manager.get_queue_status(username=None) -> Dict[str, Any]`
Consulta de forma *thread-safe* el estado de las descargas activas y en espera en el servidor.
Si se especifica `username`, filtra únicamente las tareas de ese usuario (imprescindible para bots o asistentes privados multiusuario). Si es `None`, entrega la visión global.
```python
queue_info = self.manager.get_queue_status(username="hernan")
# Retorna:
# {
#   "active_jobs": [
#       {"job_id": "abc1", "title": "Video 1", "status": "downloading", "percent": 55, "speed": "2.4 MB/s", "eta": "00:15", "owner": "hernan"}
#   ],
#   "queued_jobs": [
#       {"job_id": "abc2", "title": "Video 2", "status": "queued", "percent": 0, "owner": "hernan"}
#   ],
#   "total_active": 1,
#   "total_queued": 1,
#   "total": 2
# }
```

#### 6. `self.manager.get_user_nav_items(username=None) -> List[Dict[str, Any]]`
Recolecta todos los botones y enlaces de navegación personal provistos por los plugins para el usuario actual.

#### 7. `self.manager.get_plugin_instance(plugin_id: str) -> Optional[Any]`
Obtiene la instancia viva en memoria de otro plugin cargado para invocar métodos entre extensiones.

#### 8. `self.manager.get_plugin(plugin_id: str) -> Optional[Dict[str, Any]]`
Obtiene los metadatos (`plugin.json`) del plugin solicitado.

#### 9. `self.manager.get_all_plugins() -> Dict[str, Dict[str, Any]]`
Diccionario con todos los plugins descubiertos en el sistema y su estado.

#### 10. `self.manager.plugins_dir -> str`
Ruta absoluta al directorio `/plugins` en el servidor o contenedor.

---

## ☁️ 6. Protocolo Oficial de Proveedores de Almacenamiento en la Nube (Cloud Storage)

Para que tu extensión de nube (**OneDrive**, **Dropbox**, **Nextcloud**, etc.) funcione de forma idéntica a Google Drive sin tocar el Core:

1. **Implementa `get_download_cloud_option(self, username)`**:
   Inyecta la opción en el modal de descarga de la web principal y en los presets de usuario.
2. **Implementa `upload_job_for_user(self, job_id, username, progress_callback)`**:
   Permite subidas bajo demanda desde el botón `/descargas` de Telegram o la API web.
3. **Implementa `get_user_nav_item(self, username)`**:
   Añade el acceso a tus ajustes en el sidebar y drawer web.
4. **Implementa `on_download_complete(self, job_data)`**:
   Sube automáticamente el archivo al finalizar la descarga si el usuario lo activó en `job_data["user_cloud_sync"]["plugins"][self.plugin_id]["enabled"]`.

Al implementar este cuarteto de métodos:
* El Bot de Telegram generará **automáticamente** los botones de alternancia (`☁️ Subir a [Tu Nube]: ✅ SÍ / ⬜ NO`) al inspeccionar URLs.
* El Bot de Telegram incluirá **automáticamente** el botón de subida en `/descargas`.
* La web incluirá el acceso directo en el panel de navegación de usuario.

---

## 🤖 7. Protocolo de Integración con el Bot Oficial de Telegram

Cuando el Bot Oficial recibe mensajes o eventos, los delega de forma segura a los plugins:

### Métodos del objeto `bot`:
* `bot.send_message(chat_id: int, text: str, reply_markup: dict = None, parse_mode: str = "HTML")`
* `bot.edit_message(chat_id: int, message_id: int, text: str, reply_markup: dict = None, parse_mode: str = "HTML")`
* `bot.answer_callback_query(callback_query_id: str, text: str = None, show_alert: bool = False)`

### Ejemplo de Comando Personalizado:
```python
def get_telegram_commands(self):
    return [{"command": "/estado_nube", "description": "Ver cuota de mi nube"}]

def on_telegram_command(self, cmd, args, message, bot):
    if cmd == "/estado_nube":
        chat_id = message.get("chat", {}).get("id")
        bot.send_message(chat_id, "☁️ <b>Cuota de Almacenamiento:</b>\nEspacio disponible: 15.4 GB", parse_mode="HTML")
        return True
    return False
```

---

## 🎨 8. Protocolo de Inyección en la Interfaz Web y Navegación

dHtools dispone de slots seguros donde los plugins pueden renderizarse:
1. **Sidebar de Usuario & Drawer Móvil:** Se alimenta automáticamente de `get_user_nav_item()`.
2. **Acordeón de Descarga Web:** Se alimenta automáticamente de `get_download_cloud_option()`.
3. **Pestaña Cloud Sync en `/admin`:** Se alimenta de `get_admin_cloud_panel()`.

---

## 📦 9. Diccionario de Datos y Payloads Normalizados

### Payload `job_data` recibido en `on_download_complete`:
```python
{
    "job_id": "9f0a2e4b8c1d4e5f",            # ID único de la descarga
    "title": "Documental Naturaleza 4K",      # Título limpio del video o audio
    "url": "https://www.youtube.com/watch?v=...", # URL de origen
    "filepath": "/app/downloads/9f0a2e4b8c1d4e5f_Documental.mp4", # Ruta absoluta al archivo en disco
    "filename": "9f0a2e4b8c1d4e5f_Documental.mp4", # Nombre de archivo en disco
    "owner": "hernan",                        # Usuario que ordenó la descarga
    "format_type": "video",                   # "video" o "audio"
    "quality": "1080p",                       # Calidad solicitada
    "video_format": "mp4",                    # Extensión de salida
    "user_cloud_sync": {                      # Nubes activadas para esta descarga
        "plugins": {
            "onedrive": {"enabled": True},
            "google_drive": {"enabled": False}
        }
    },
    "created_at": 1725650000.0                # Timestamp Unix de creación
}
```

---

## 💡 10. Ejemplo Completo: Plugin de Almacenamiento (OneDrive / Cloud)

`plugins/onedrive/plugin.py`:
```python
import os
import json
import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("dhtools.plugins.onedrive")

class Plugin:
    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.metadata = metadata or {}
        self.plugin_id = self.metadata.get("id", "onedrive")
        self.name = self.metadata.get("name", "Microsoft OneDrive")
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

    def _is_user_enabled(self, username: str) -> bool:
        # Lógica para leer si el usuario configuró su token de OneDrive
        cfg_path = os.path.join(self.plugin_dir, f"{username}_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f).get("enabled", False)
        return False

    def get_download_cloud_option(self, username: Optional[str] = None) -> Dict[str, Any]:
        is_active = self._is_user_enabled(username or "admin")
        return {
            "id": self.plugin_id,
            "name": self.name,
            "icon": "☁️",
            "enabled": is_active,
            "auto_upload": False,
            "status_label": "ACTIVO" if is_active else "DESACTIVADO",
            "description": "Respalda tus descargas en Microsoft OneDrive.",
            "settings_url": f"/plugin/{self.plugin_id}/settings"
        }

    def upload_job_for_user(self, job_id: str, username: str, progress_callback=None) -> Tuple[bool, Dict[str, Any]]:
        if not self._is_user_enabled(username):
            return False, {"error": "OneDrive está desactivado en tus ajustes web."}
        
        # Aquí ejecutas la subida usando la API de Microsoft Graph / OneDrive
        # ...
        return True, {
            "filename": f"{job_id}.mp4",
            "web_link": f"https://onedrive.live.com/view/{job_id}"
        }

    def get_user_nav_item(self, username: Optional[str] = None) -> Dict[str, Any]:
        return {
            "id": self.plugin_id,
            "title": "OneDrive",
            "full_title": "Microsoft OneDrive Cloud Sync",
            "icon": "☁️",
            "url": f"/plugin/{self.plugin_id}/settings"
        }

    def on_download_complete(self, job_data: dict):
        sync = job_data.get("user_cloud_sync", {}).get("plugins", {}).get(self.plugin_id, {})
        if sync.get("enabled"):
            self.upload_job_for_user(job_data["job_id"], job_data.get("owner", "admin"))
```

---

## 🤖 11. Ejemplo Completo: Segundo Bot Autónomo (Notificador / Asistente)

`plugins/segundo_bot/plugin.py`:
```python
import os
import json
import threading
import telebot

class Plugin:
    def __init__(self, manager=None, metadata=None):
        self.manager = manager
        self.bot = None
        self.token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz" # O cargado desde config.json

    def on_startup(self, app, context):
        if not self.token:
            return
        self.bot = telebot.TeleBot(self.token)

        @self.bot.message_handler(commands=['descargar'])
        def handle_dl(msg):
            url = msg.text.replace("/descargar", "").strip()
            # Encolar en dHtools
            res = self.manager.enqueue_download(url=url, quality="best", owner="telegram_user")
            if res.get("success"):
                self.bot.reply_to(msg, f"🚀 Tarea iniciada: ID <code>{res['job_id']}</code>", parse_mode="HTML")
            else:
                self.bot.reply_to(msg, f"❌ Error: {res.get('error')}")

        threading.Thread(target=self.bot.infinity_polling, daemon=True).start()

    def on_download_complete(self, job_data: dict):
        # Enviar archivo al chat cuando termine
        filepath = job_data.get("filepath")
        # if self.bot and os.path.exists(filepath): ...
```

---

---

## 🚀 12. Actualizaciones Automáticas de Plugins vía GitHub

dHtools permite que cualquier plugin (especialmente los desarrollados de manera externa en sus propios repositorios de GitHub, como `Remote Assist` o conectores privados) pueda ser comprobado y actualizado de forma segura y automática desde el **Panel de Administración (`/admin`)**.

### Dos Métodos Soportados de Integración:

1. **Sub-repositorio Git (Recomendado para desarrollo externo):**
   * Puedes clonar tu plugin directamente dentro de la carpeta `plugins/`:
     ```bash
     git clone https://github.com/tu-usuario/remote-assist plugins/remote_assist
     ```
   * dHtools detecta automáticamente la carpeta `.git`, lee el commit local, la rama y consulta los commits remotos sin interferir con el control de versiones del Core (`plugins/*` está en `.gitignore`).

2. **Declaración en `plugin.json` (Para plugins distribuidos como carpetas sin `.git`):**
   * Añade los campos `"repository"` y `"branch"` en tu `plugin.json`:
     ```json
     {
       "id": "remote_assist",
       "name": "Remote Assist",
       "version": "1.0.0",
       "repository": "https://github.com/tu-usuario/remote-assist",
       "branch": "main",
       "enabled": true
     }
     ```
   * dHtools consultará la API de GitHub (`/commits` y `/releases/latest`) para comparar commits y números de versión SemVer. Si se ejecuta una actualización, clonará e inicializará el seguimiento Git en esa carpeta.

### 🛡️ Preservación Automática de Credenciales (`config.json`):
Al pulsar **"Actualizar"** en el Panel de Administración:
1. dHtools respalda en memoria los archivos de configuración privados (`config.json`, `credentials.json`, `token.json`, `data.json`, `.env`).
2. Ejecuta la actualización del código (`git fetch` + `git pull --rebase` o `git reset --hard origin/<branch>`).
3. Restaura automáticamente tus archivos de configuración para que **nunca pierdas tokens ni credenciales**.
4. Recarga el plugin en memoria en caliente sin necesidad de reiniciar el servidor completo.

### 🖥️ Gestión desde el Panel de Administración:
* **Pestaña "Actualizador de Motores":** Incorpora la tarjeta **Actualizaciones de Plugins & Extensiones (GitHub)** junto con yt-dlp, Cobalt y Deno, con botones para *Comprobar Plugins* y *Actualizar Todos*.
* **Pestaña "Extensiones & Plugins":** Cada tarjeta de plugin muestra su repositorio GitHub, su estado de versión respecto a remoto y un botón individual de actualización rápida.

---

## 📋 13. Directiva Maestra (Master Prompt para Nuevos Chats de IA)

> [!TIP]
> **Copia y pega el siguiente bloque como PRIMER MENSAJE en cualquier nuevo chat de IA.**
> Esto le dará al asistente todo el contexto arquitectónico y los contratos del SDK de dHtools para construir extensiones 100% desacopladas.

```markdown
Hola. Necesito desarrollar un plugin privado para una plataforma multimedia autohospedable llamada **dHtools** (construida con Python 3.11, Flask y Docker Compose).

El proyecto cuenta con una arquitectura de plugins totalmente desacoplada del Core mediante el **dHtools Plugin SDK**.

### ⚠️ Reglas estrictas de desarrollo:
1. **Todo el código debe estar encapsulado dentro de la carpeta:** `plugins/<nombre_de_mi_plugin>/`.
2. **NUNCA debes modificar ningún archivo fuera de mi carpeta de plugin** (ni app.py, ni core/, ni templates/).
3. La carpeta contiene:
   - `plugin.json`: Manifiesto con `id`, `name`, `version`, `author`, `description`, `"status": "experimental"`, `"enabled": true`, `"repository": "https://github.com/usuario/repo"` (opcional para actualizaciones automáticas en 1 clic), `"branch": "main"`.
   - `plugin.py`: Clase `Plugin` con constructor `__init__(self, manager=None, metadata=None)`.
   - `config.json`: Archivo local para mis credenciales y tokens privados (ignorado por Git y preservado automáticamente en actualizaciones).

### 🧩 Métodos y Hooks Contractuales disponibles en la clase `Plugin`:
- `register_routes(self, app)`: Registrar Blueprint Flask bajo el prefijo `/plugin/<mi_plugin_id>/`.
- `on_startup(self, app, context)`: Inicializar clientes, workers o hilos daemon (`threading.Thread(daemon=True)`).
- `on_download_complete(self, job_data)`: Recibir metadatos de descargas exitosas (`job_id`, `title`, `filepath`, `filename`, `owner`, `url`, `quality`, `user_cloud_sync`).
- `on_download_error(self, job_data, error=None)`: Notificación de descargas fallidas.
- `get_admin_cloud_panel(self, config=None)`: Inyectar tarjeta en la pestaña Cloud Sync de `/admin`.
- `get_download_cloud_option(self, username=None)`: Inyectar opción en el acordeón de Nube Personal de la web de descargas y presets.
- `upload_job_for_user(self, job_id, username, progress_callback=None)`: Contrato estándar para subida manual bajo demanda. Retorna `(True, {"filename": "...", "web_link": "..."})` o `(False, {"error": "..."})`.
- `get_user_nav_item(self, username=None)`: Inyectar acceso directo en el sidebar de usuario y drawer móvil.
- `get_telegram_commands(self)`: Registrar comandos en el menú `/ayuda` del bot oficial.
- `on_telegram_command(self, cmd, args, message, bot)`: Procesar comandos en el bot de Telegram oficial.
- `on_telegram_callback(self, query, data, bot)`: Manejar callbacks de botones inline en Telegram.

### 🛠️ API disponible a través de `self.manager`:
- `self.manager.enqueue_download(url, quality="best", format_type="video", owner="admin", title="", extra_params=None)`: Solicita descargas al Core de dHtools.
- `self.manager.get_queue_status(username=None)`: Consulta tareas activas y en espera (con soporte de filtro por usuario).
- `self.manager.get_user_cloud_providers(username)`: Consulta de nubes activas del usuario.
- `self.manager.upload_job_to_cloud(plugin_id, job_id, username, progress_callback=None)`: Despacha la subida de una descarga de dHtools hacia la nube.
- `self.manager.upload_file_to_cloud(plugin_id, filepath, username, progress_callback=None)`: Sube cualquier archivo arbitrario en disco a la nube del usuario.
- `self.manager.get_user_nav_items(username)`: Accesos de navegación.
- `self.manager.plugins_dir`: Ruta absoluta al directorio de plugins.

### 🎯 Objetivo específico de este plugin:
[AQUÍ DESCRIBES TU REQUERIMIENTO: Por ejemplo: "Crear un conector de OneDrive con autenticación OAuth2 y subida por streaming resumable"].

Por favor, procedé a diseñar y generar los archivos necesarios (`plugin.json`, `plugin.py`, etc.) respetando rigurosamente estos contratos.
```

