<p align="center">
  <img src="static/icons/brand_horizontal.png" alt="dHtools Logo" width="340" style="border-radius: 14px; box-shadow: 0 0 25px rgba(56, 189, 248, 0.35);">
</p>

<h1 align="center">⚡ dHtools - Suite Multimedia & Extractor Universal</h1>

<p align="center">
  <a href="https://github.com/hernancussit/dHtools"><img src="https://img.shields.io/badge/Release-v1.5.0--stable-blue.svg" alt="Release"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11+-yellow.svg" alt="Python"></a>
  <a href="https://docker.com"><img src="https://img.shields.io/badge/Docker-Compose-2496ED.svg" alt="Docker"></a>
  <a href="https://cafecito.app/henu_45"><img src="https://img.shields.io/badge/Cafecito-Invitame_uno-00A8FF.svg?logo=coffeescript&logoColor=white" alt="Cafecito"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License"></a>
</p>

<div align="center">
  <a href="https://cafecito.app/henu_45" target="_blank" rel="noopener noreferrer">
    <img src="https://cdn.cafecito.app/imgs/buttons/button_5.png" alt="Invitame un café en cafecito.app" height="40" style="border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); margin: 6px 0 16px;" />
  </a>
</div>

**dHtools** es una suite web autohospedable y de alto rendimiento diseñada para la extracción, conversión, recorte y sincronización en la nube de contenido multimedia desde múltiples plataformas (**YouTube, Spotify, Deezer, TikTok, Instagram, Twitter/X, Twitch, Facebook y más**).

Está construida sobre una **arquitectura modular de Flask Blueprints**, pensada para desplegarse fácilmente en tu propio servidor VPS o máquina local con **Docker Compose**. Cuenta con un **sistema desacoplado y extensible de plugins**, una **API REST completa para automatización**, interfaz moderna y reactiva con optimización móvil táctil, gestión multiusuario con historial detallado de descargas y exportación CSV, autenticación de dos factores (2FA / TOTP), cuotas de disco, túnel residencial contra bloqueos, almacenamiento S3/Cloud con modo Offload, asistente de Telegram autónomo, selector de canal de actualizaciones (`main` vs `dev`) y rollback automático en 1 clic.

---

## 🚀 Características Principales

### 🎯 Extracción Multiplataforma Inteligente
- **Motor en Cascada Inteligente (4 Niveles):** Combina de manera transparente **Cobalt v11 Oficial**, **SpotDL / Deezer nativo**, **yt-dlp core** y un **Túnel Residencial de Contingencia (Tier 4 / Failsafe)**.
- **Evasión Antibot & Tokens PO:** Microservicio `pot-provider` estabilizado junto al runtime `Deno` para resolver desafíos JavaScript y generar tokens Proof-of-Origin automáticos.
- **Selector Inteligente de Proxy de Descargas (SOCKS5 / MikroTik / HTTP):** Control de enrutamiento con 3 modalidades configurables desde el panel de administración:
  - 🛡️ **Directo (Desactivado):** Operación a máxima velocidad del VPS sin intermediarios.
  - ⚡ **Respaldo Automático (Failsafe) [Recomendado]:** Evasión reactiva automática si YouTube o cualquier servicio bloquea la IP del datacenter o estrangula la calidad SABR a 360p, protegiendo el consumo del enlace residencial.
  - 🌐 **Proxy Global:** Enrutamiento obligatorio del 100% de las extracciones y descargas multimedia a través del proxy configurado.
  - 🔬 **Telemetría y Diagnóstico en Vivo:** Medición de latencia HTTP, ping TCP (RTT) y prueba canary directa contra YouTube mostrando la IP pública detectada y el ISP.
- **Calidades de Video Ultra HD:** Descargas en 4K (2160p), 2K (1440p), Full HD (1080p), 720p y 480p con selección de contenedor (`MP4` / `MKV`) y subtítulos incrustados.
- **Suite de Audio Hi-Fi:** Extracción directa con carátulas en alta resolución y metadatos ID3 automáticos en calidades `128 kbps`, `192 kbps`, `256 kbps` y `320 kbps (CBR MP3)`.
- **Playlists, Álbumes & Protección Anti-Mixes:** Detección de listas con inspección ítem por ítem, reordenamiento interactivo y descarga agrupada (ZIP o virtual). Incorpora casilla de verificación de seguridad para enlaces de YouTube, evitando descargas masivas accidentales al pegar URLs con listas automáticas o radios (`&list=RD...` / `&start_radio=1`).
- **Recorte Preciso por Tiempo (Trimming):** Descarga estricta por rangos temporales (`download_ranges`) indicando inicio y fin (`HH:MM:SS`), transfiriendo únicamente los minutos deseados sin descargar archivos completos a disco.
- **Doble Consola Interactiva:** Terminal de actividad en tiempo real tanto en **Modo Fácil** como en **Modo Avanzado** para ver el estado de cada proceso, conversiones FFmpeg y eventos en vivo.
- **Descargas Unificadas en Lote:** Conmutador directo `[ 🔗 Enlace Único | 📋 Descarga en Lote ]` integrado en ambos modos.

### 🔌 Ecosistema Modular de Plugins (Plugin Architecture)
- **Arquitectura Desacoplada y Segura:** Motor de plugins en `core/plugin_manager.py` con manifiesto `plugin.json`, herencia de `BasePlugin`, slots de interfaz dinámicos y aislamiento por paquetes.
- **Proveedores Cloud Oficiales (Bundled):** Integración nativa con **Google Drive** (OAuth2/Service Account con subida por chunks de 10 MB), **Microsoft OneDrive / SharePoint** (Microsoft Graph API) y **Dropbox** (`upload_session` por bloques de 8 MB).
- **RAM-Safe & Safe Offload:** Streaming en bloques para no saturar memoria en servidores pequeños y liberación de disco local tras sincronización exitosa.
- **Actualizaciones desde GitHub & Plantilla para Devs:** Actualización de plugins desde la web y plantilla oficial documentada en `plugins/template_example/` junto con la guía técnica en `docs/PLUGIN_DEV_GUIDE.md`.

### ⚡ API REST Integral & Automatización
- **Control Programático Completo:** Inspección de URLs (`/api/info`), encolado con parámetros avanzados (`/api/download`), cancelación (`/api/jobs/cancel`) y telemetría en tiempo real (`/api/jobs`).
- **Historial de Auditoría & Exportación CSV:** Consulta de descargas activas, tamaño y fechas precisas de ejecución por usuario para administradores en `/api/admin/users/<username>/downloads` con soporte de exportación a archivo `.csv`.
- **Integración Universal:** Conectable fácilmente con scripts en Python/Bash, bots de Discord/Telegram, Home Assistant y flujos de n8n.

### 🛡️ Blindaje de Seguridad & Control de Accesos
- **Autenticación en Dos Factores (2FA / TOTP Opcional):** Estándar RFC 6238 compatible con Google Authenticator, Microsoft Authenticator, Authy, Bitwarden, etc., con QR dinámico y 8 códigos de recuperación.
- **Gestión Multiusuario & Roles:** Roles independientes (`Admin` y `Downloader`), cambio de credenciales, suspensión y purga selectiva.
- **Control Estricto de Cuotas de Disco:** Asignación de cuotas máximas de almacenamiento por usuario con medidor en vivo y bloqueo preventivo.
- **Auditoría de Sesiones Activas:** Monitor en tiempo real de sesiones conectadas (IP, dispositivo, navegador, última actividad) con revocación remota instantánea.
- **Servidor SMTP & Recuperación de Contraseñas:** Envío de correos seguros con tokens de un solo uso con 1 hora de validez para restablecer credenciales.
- **Prevención de Ataques Web:** Sanitización rigurosa de URLs (`validate_media_url`), ejecución de comandos segura sin `shell=True`, validación de rutas canónicas contra Path Traversal (`safe_download_path`) y protección por tarpit contra fuerza bruta.

### ☁️ Conectores Cloud Avanzados & Modo Offload
- **Soporte Universal de Almacenamiento:** Compatible con **Amazon S3, MinIO, Cloudflare R2, Backblaze B2, Wasabi, WebDAV** (Nextcloud / ownCloud) y **servidores FTP**.
- **Modo Offload ("Subir y Mover"):** Ahorro extremo de almacenamiento en servidores VPS pequeños; tras una subida exitosa a la nube, el archivo local se libera manteniendo el registro en "Mis Descargas" con la etiqueta `☁️ En la nube`.
- **Presets Privados por Usuario:** Cada usuario puede configurar y almacenar sus propios destinos de almacenamiento con prueba de conectividad en vivo.

### 📱 Experiencia Móvil & Diseño Adaptativo
- **Navegación Móvil Ergonómica:** Barra de navegación inferior permanente (`Bottom Nav Bar`), menú lateral deslizable (*Drawer*) y barra superior compacta optimizada para pantallas táctiles.
- **4 Temas Visuales:** Selector interactivo de paletas: `Cyberpunk`, `OLED Pure Black`, `Emerald` y `Light`.
- **PWA Ready:** Instalable como aplicación web progresiva en Android, iOS y PC de escritorio con manifiesto y suite completa de íconos.

### 🤖 Asistente Autónomo de Telegram
- **Despliegue Self-Hosted:** Conexión directa mediante `@BotFather` configurando tu propio bot token en el panel de administración.
- **Comandos & Lenguaje Natural:** Envío de enlaces para descarga interactiva con botones táctiles en línea, comandos `/descargas`, `/cola`, `/cuota`, `/ayuda` y soporte conversacional.
- **Privacidad Total & Filtro Anti-Mixes:** Cada usuario vinculado mediante token temporal accede exclusivamente a sus propios archivos. Los enlaces con mixes o radios de YouTube se filtran automáticamente para descargar únicamente el video solicitado.
- **Entrega Inmediata:** Despacho directo del archivo al chat para tamaños de hasta 50 MB con fallback transparente a aviso web para archivos mayores.

---

## 🔌 Ecosistema Extensible de Plugins (Plugin Architecture)

**dHtools** cuenta con un gestor modular de plugins (`core/plugin_manager.py`) que permite expandir las capacidades del sistema sin modificar el núcleo de la aplicación. Los plugins pueden añadir nuevos proveedores de almacenamiento en la nube, registrar rutas HTTP independientes, inyectar componentes en la interfaz web y reaccionar al ciclo de vida de las descargas.

### 📦 Plugins Oficiales Incluidos (Bundled):
- 📁 **Google Drive Cloud Sync (`plugins/google_drive`):**
  - Autenticación flexible mediante **OAuth2 interactivo** (pantalla de consentimiento web oficial) o mediante **Cuentas de Servicio (Service Account JSON)**.
  - Subida fragmentada por bloques de 10 MB (*chunked resumable upload*) con protección contra desbordamiento de memoria RAM (*RAM-Safe*).
  - Selector interactivo de carpetas de destino por usuario y modo **Safe Offload**.
- ☁️ **Microsoft OneDrive & SharePoint (`plugins/onedrive`):**
  - Autenticación mediante **Microsoft Graph API**.
  - Compatible con cuentas personales (**OneDrive Personal**) y corporativas o institucionales (**Microsoft 365 / SharePoint**).
  - Sesiones de subida resumables (*Upload Session*) para archivos de cualquier tamaño sin saturar el servidor.
- 📦 **Dropbox Cloud Sync (`plugins/dropbox`):**
  - Integración con la API oficial v2 de Dropbox mediante tokens de acceso o aplicaciones con *Refresh Tokens*.
  - Transferencia eficiente por bloques de 8 MB (`upload_session`) y generación opcional de enlaces de descarga compartidos (*Shared Links*).

### 🛠️ ¿Cómo crear tu propio plugin?
Cualquier desarrollador puede crear una extensión para dHtools de forma muy sencilla:
1. Crea una carpeta dentro de `plugins/tu_plugin/`.
2. Define el manifiesto `plugin.json` indicando nombre, versión, autor, permisos y slots de interfaz donde participará el plugin.
3. Hereda de la clase base `BasePlugin` en `plugin.py` e implementa los métodos que necesites:
   - `on_download_complete(...)`: Ejecutar acciones tras finalizar descargas (transcodificación, avisos webhooks, copia a NAS, etc.).
   - Protocolo de Almacenamiento: `upload_file_for_user(...)`, `test_connection(...)` para sumar nuevos servicios cloud (Mega, pCloud, Telegram Storage, Web3, etc.).
   - Blueprint Flask dedicado montado automáticamente bajo `/plugin/<id>/`.
4. Dispones de un ejemplo funcional y comentado en [`plugins/template_example/`](plugins/template_example/) y una guía paso a paso completa en [`docs/PLUGIN_DEV_GUIDE.md`](docs/PLUGIN_DEV_GUIDE.md).

---

## ⚡ API REST & Automatización Programática

**dHtools** expone una API REST moderna para automatizar descargas, consultar el estado de la cola en tiempo real, listar archivos y orquestar flujos de trabajo externos.

### 📑 Endpoints Principales:

| Método | Endpoint | Descripción | Parámetros Clave |
|---|---|---|---|
| `POST` | `/api/info` | Inspecciona URLs multimedia y extrae metadatos en vivo sin descargar. | `{"url": "...", "playlist": false}` |
| `POST` | `/api/download` | Encola una descarga unitaria o masiva. | `url`, `quality`, `video_format`, `subtitles`, `playlist`, `start_time`, `end_time`, `user_cloud_sync` |
| `GET` | `/api/jobs` | Retorna el estado en tiempo real de todas las tareas activas y en cola. | Progreso (`%`), velocidad, ETA, título, estado (`downloading`, `finished`, `failed`). |
| `POST` | `/api/jobs/cancel` | Cancela una descarga activa o pendiente en la cola. | `{"job_id": "..."}` |
| `GET` | `/api/downloads` | Lista los archivos descargados disponibles en el almacenamiento del usuario. | Nombre de archivo, tamaño formateado, fecha y metadatos. |
| `DELETE` | `/api/downloads/<filename>` | Elimina un archivo descargado del almacenamiento del usuario. | Nombre del archivo a eliminar. |
| `GET` | `/api/admin/users/<username>/downloads` | *(Admin)* Historial completo de descargas por usuario con timestamps precisos. | Consulta JSON o descarga directa con `?export=csv`. |
| `DELETE` | `/api/admin/users/<username>/downloads` | *(Admin)* Elimina registros seleccionados del historial o purga descargas de un usuario. | `{"filenames": [...]}` o `{"clear_all": true}` |

### 💡 Ejemplos Rápido de Uso con `curl`:

**1. Inspeccionar un enlace:**
```bash
curl -X POST http://tu-servidor:5000/api/info \
  -H "Content-Type: application/json" \
  -b "session=TU_COOKIE_DE_SESION" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "playlist": false}'
```

**2. Encolar una descarga en MP4 1080p con recorte de tiempo:**
```bash
curl -X POST http://tu-servidor:5000/api/download \
  -H "Content-Type: application/json" \
  -b "session=TU_COOKIE_DE_SESION" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "quality": "1080p",
    "video_format": "mp4",
    "playlist": false,
    "start_time": "00:00:15",
    "end_time": "00:01:30"
  }'
```

**3. Consultar telemetría y porcentaje de descarga en vivo:**
```bash
curl -X GET http://tu-servidor:5000/api/jobs \
  -b "session=TU_COOKIE_DE_SESION"
```

---

## 📦 Puesta en Marcha Rápida (Docker Compose)

### 1. Clonar el repositorio
```bash
git clone https://github.com/hernancussit/dHtools.git
cd dHtools
```

### 2. Configurar variables de entorno
```bash
cp .env.example .env
nano .env
```
*Definí tus credenciales de acceso (`APP_USERNAME` y `APP_PASSWORD`) y tu clave secreta de sesión.*

### 3. Iniciar los contenedores
```bash
docker compose up -d --build
```

La aplicación estará lista en `http://localhost:5000` (o `http://TU_IP_VPS:5000`).

---

## 🌐 Publicación con Dominio & SSL (Proxy Inverso)

Para publicar **dHtools** bajo tu propio dominio con HTTPS, dispones de configuraciones listas en la carpeta [`proxy-configs/`](proxy-configs/):

### 1. 🐧 Nginx Universal (Cualquier Servidor Linux / CloudPanel / aaPanel)
Utiliza la plantilla [`proxy-configs/nginx-universal.conf`](proxy-configs/nginx-universal.conf) en tu bloque de servidor:
```bash
sudo cp proxy-configs/nginx-universal.conf /etc/nginx/sites-available/dhtools.conf
# Edita tu dominio y certificados en el archivo y luego recarga:
sudo systemctl reload nginx
```

### 2. 🛡️ HestiaCP
Copia las plantillas oficiales de HestiaCP y aplícalas a tu dominio:
```bash
cp proxy-configs/hestiacp/dhtools-proxy.tpl  /usr/local/hestia/data/templates/web/nginx/
cp proxy-configs/hestiacp/dhtools-proxy.stpl /usr/local/hestia/data/templates/web/nginx/
systemctl reload nginx
```
*Luego selecciona la plantilla `dhtools-proxy` desde la configuración web del dominio en el panel de HestiaCP.*

### 3. 💼 cPanel / WHM (Apache mod_proxy)
Copia las reglas de [`proxy-configs/cpanel-apache.conf`](proxy-configs/cpanel-apache.conf) en el archivo `.htaccess` de la raíz web de tu dominio.

### 4. 🚀 Caddy Server
Añade a tu `Caddyfile` (configuración de [`proxy-configs/caddy-Caddyfile`](proxy-configs/caddy-Caddyfile)):
```caddy
tu-dominio.com {
    reverse_proxy 127.0.0.1:5000
}
```

*Consulta la guía detallada en [`proxy-configs/README.md`](proxy-configs/README.md).*

---

## 🍪 Configuración de Cookies de YouTube (Opcional / Avanzado)

**dHtools** cuenta con evasión antibot automática (`pot-provider` + Deno + Cobalt) y funciona **sin cookies** para el 95% de las descargas públicas. Sin embargo, si deseas descargar **videos con restricción de edad (+18)**, **contenido para miembros del canal** o **listas privadas**, puedes suministrar un archivo `cookies.txt`.

### ⚠️ Reglas Críticas de Seguridad y Operación:
> [!WARNING]
> 1. **Usá SIEMPRE una cuenta secundaria (desechable):** NUNCA exportes cookies de tu cuenta de Google/YouTube principal. La actividad constante de descargas desde una IP de servidor puede gatillar bloqueos temporales o suspensiones de cuenta por parte de Google.
> 2. **NO utilices esa sesión en tu navegador tras exportarla:** Una vez descargado el `cookies.txt`, no navegues con esa cuenta en tu navegador ni cierres sesión manualmente. El uso continuo en el navegador rota los tokens criptográficos de sesión de Google e invalida las cookies exportadas de inmediato.

### 📥 Paso a Paso: Cómo extraer tu `cookies.txt`
1. Abre una ventana de incógnito en tu navegador (Chrome, Firefox, Brave o Edge).
2. Entra a [YouTube](https://www.youtube.com) e inicia sesión con tu **cuenta secundaria**.
3. Instala una extensión de exportación de cookies en formato Netscape estándar:
   - **Recomendada:** [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Código abierto, segura y sin servidores externos).
   - **Alternativa:** [Cookie-Editor](https://cookie-editor.com/) (Abrir en YouTube ➔ *Export* ➔ *Export as Netscape*).
4. Estando en la pestaña de YouTube, abre la extensión y haz clic en **"Export"** o **"Descargar cookies.txt"**.
5. Guarda el archivo `.txt` en tu computadora.

### 🚀 Cómo instalarlo en dHtools
- **Desde la Web (Recomendado):**  
  Ingresa al **Panel de Administración (`/admin`)** ➔ pestaña **"⚙️ Parámetros & Cookies"** ➔ haz clic en **"Seleccionar nuevo cookies.txt"** ➔ presiona **"🚀 Validar y Guardar"**. El sistema validará automáticamente las cookies contra YouTube antes de guardarlas en el servidor.
- **Vía Terminal / Docker:**  
  Copia el archivo generado en la raíz del proyecto como `cookies.txt` y reinicia el contenedor (`docker compose restart dhtools`).


---

## 🌿 Canales de Actualización

| Canal | Rama Git | Descripción |
|---|---|---|
| **🟢 Estable** | `main` | Versiones probadas y listas para producción en cualquier VPS. |
| **🧪 Desarrollo** | `dev` | Nuevas funciones experimentales y mejoras previas al lanzamiento. |

---

## ☕ Apoyá el Proyecto

Si **dHtools** te resulta útil para gestionar tus descargas multimedia y administrar tu servidor, podés invitarme un cafecito para apoyar el desarrollo continuo y mantenimiento de nuevas funciones:

<div align="center">
  <a href="https://cafecito.app/henu_45" target="_blank" rel="noopener noreferrer">
    <img src="https://cdn.cafecito.app/imgs/buttons/button_5.png" alt="Invitame un café en cafecito.app" height="48" style="border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);" />
  </a>
  <p><b>¡Muchas gracias por apoyar el software independiente y de código libre!</b></p>
</div>

---

## 👤 Autor y Créditos

- **Creador y Desarrollador:** [Hernán Cussit](https://github.com/hernancussit)
- **Estudio / Servicios:** [Servicios Informáticos LT](https://serviciosinformaticoslt.com)
- **Contacto en Telegram:** [@henu_45](https://t.me/henu_45)
- **Donaciones:** [cafecito.app/henu_45](https://cafecito.app/henu_45)

---

## 📄 Licencia

Este proyecto está bajo la Licencia [MIT](LICENSE).

