# Registro de Cambios (Changelog)

Todos los cambios notables en este proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [1.1.0] - 2026-09-01

### 🚀 Lanzamiento Estable v1.1.0
- **📦 Entrega Perfeccionada de Archivos ZIP en Playlists:**
  - Corrección de rutas absolutas en `safe_download_path` para entrega directa de archivos `.zip` desde el monitor y la cola.
  - Optimización de `/api/my-downloads/folder-zip/<group_id>` con compresión bajo demanda sin duplicar zips existentes.
- **🔍 Compatibilidad Total con URLs de Listas de Reproducción:**
  - Soporte de delimitadores estándar (`&list=...`, `&t=...`) en `validate_media_url` manteniendo el blindaje contra inyección de comandos.
- **🍪 Gestor Seguro de Cookies en Panel Admin:**
  - Protección de privacidad eliminando el volcado de texto plano en pantalla y API.
  - Subida y validación obligatoria contra YouTube antes de aplicar cambios en `cookies.txt`.
- **🌐 Plantillas de Proxy Inverso Universales (Nginx, HestiaCP, cPanel, Caddy):**
  - Inclusión de carpeta [`proxy-configs/`](proxy-configs/) con soporte para Nginx Universal, HestiaCP, cPanel y Caddy.
- **🌿 Selector de Rama Git y Actualizador en Vivo:**
  - Soporte completo para alternar entre ramas `main` y `dev` con autenticación SSH en contenedores Docker.
- **🎨 Corrección Visual de Branding:**
  - Unificación de cabecera lateral con ícono único `⚡ dHtools`.

---

## [1.0.0] - 2026-09-01

### 🚀 Primera Versión Pública Oficial Estable
- **🛡️ Blindaje de Seguridad Integral:**
  - **Protección contra Fuerza Bruta:** Bloqueo temporal automático por IP (`429 Too Many Requests`) tras 5 intentos fallidos en `/login` con *tarpit* (retraso exponencial) y registro seguro de IPs cliente.
  - **Prevención de RCE & Command Injection:** Función de validación estricta de URLs (`validate_media_url`) que rechaza metacaracteres peligrosos de shell (`;`, `|`, `` ` ``, `$`, `\n`, `\r`, `<`, `>`, `"`, `'`) y protocolos no seguros, permitiendo parámetros legítimos (`&list=...`). Auditoría completa de `subprocess` sin `shell=True`.
  - **Protección contra Path Traversal:** Verificación canónica de rutas (`safe_download_path`) en descargas y eliminación de archivos.
  - **Cabeceras HTTP de Seguridad:** Inyección automática de `Content-Security-Policy`, `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff` y `Referrer-Policy`.
  - **Hardening de Cookies:** Configuración de cookies con flags `HttpOnly` y `SameSite=Lax`.
- **🔄 Actualizador y Rollback en 1 Clic en el Panel de Administración:**
  - Selector de canales integrado en el Panel Admin: `🟢 Estable (main)` vs `🧪 Desarrollo / Beta (dev)`.
  - Comprobador automático de versiones y commits contra la API pública de GitHub.
  - Actualizador en caliente: `git pull`, actualización de dependencias y reinicio seguro del contenedor.
  - Rollback en 1 clic: Restauración inmediata al commit anterior en caso de fallos.
- **🏷️ Rebranding y Publicación Abierta en GitHub:**
  - Lanzamiento del repositorio público `dHtools` con ramas `main` (estable) y `dev` (desarrollo).
  - Guía de instalación rápida y despliegue con Docker Compose en cualquier VPS.

---

## [2.7.8] - 2026-09-01

### ⚡ Rebranding Oficial del Proyecto a "dHtools"
- **🏷️ Identidad de Marca Unificada:**
  - Renombrado oficial de la plataforma a **dHtools** (Suite Multimedia & Extractor Universal).
  - Actualización del PWA Manifest (`static/manifest.json`), títulos en plantillas HTML (`index.html`, `admin.html`, `login.html`, `wiki.html`), documentación técnica (`README.md`, `WIKI.md`), y User-Agents de sincronización.
  - Mantenimiento íntegro de la URL de producción (`https://yt.serviciosinformaticoslt.com`) y credenciales de usuario.


---

## [2.7.7] - 2026-09-01


### 📋 Visualización y Gestión de Playlists Ítem por Ítem en Cola y Descargas
- **🎵 Encolado Individual de Pistas de Playlists (`/api/playlist-download`):**
  - Al descargar playlists en modo individual, cada video/pista seleccionado se encola como un elemento independiente con su propio índice, título, miniatura, progreso y estado en tiempo real.
- **📊 Monitor de Progreso Ítem por Ítem en la Sección de Descargas:**
  - Nueva tarjeta visual `playlistProgressCard` que muestra la lista completa de pistas de la playlist en curso con badges en vivo (`⏳ En cola`, `⬇️ Descargando`, `✅ Listo`, `❌ Error`, `🚫 Cancelado`) y porcentaje general.
  - Botón de cancelación selectiva por ítem y cancelación global de la playlist en 1 solo clic.
- **🏷️ Identificación de Playlists en la Cola en Segundo Plano:**
  - Cada trabajo en la pestaña "Cola en Segundo Plano" muestra la etiqueta de su carpeta contenedora (`📁 [Nombre Playlist]`), número de orden (`[#1]`, `[#2]`), controles de prioridad (⬆️/⬇️) y botón para quitar de la cola.
- **📁 Agrupación y Persistencia Automática:**
  - Todas las pistas individuales descargadas se agrupan automáticamente bajo la tarjeta de su playlist en "Mis Descargas".

---

## [2.7.6] - 2026-09-01


### 🛑 Cancelación Inmediata de Descargas y Playlists
- **⚡ Aborto Instantáneo en yt-dlp, Cascada y Servidor:**
  - Implementación de `check_cancelled()`, `match_filter` y `progress_hooks` en yt-dlp para interrumpir inmediatamente las conexiones HTTP y los sockets de descarga al recibir una orden de cancelación.
  - Corrección en `cancel_all_queue` para abortar también el trabajo activo en ejecución (`ACTIVE_WORKER_JOB`), impidiendo que continúe descargando pistas restantes en segundo plano.
  - Limpieza automática del directorio temporal de descarga tras la cancelación evitando residuos o archivos corruptos.
  - Protección de estado para no sobreescribir el estado `cancelled` con `error` o `finished`.

---

## [2.7.5] - 2026-09-01


### 📁 Organización y Agrupación de Playlists
- **📁 Agrupación Universal de Playlists de YouTube en Carpetas:**
  - Registro de metadatos de carpeta (`folder_name` y `group_id`) para todos los elementos descargados pertenecientes a playlists de YouTube (tanto en entrega individual como en archivo ZIP).
  - En la sección "Mis Descargas", las playlists aparecen organizadas como tarjetas de Carpeta desplegables con conteo de canciones/videos, tamaño total formateado, botón de descarga completa en ZIP (`📦 Bajar ZIP`) y eliminación de carpeta completa en un solo clic.
  - Detección automática de enlaces de listas de reproducción (`is_playlist_url`) en todos los modos de descarga.
  - Emparejamiento preciso de archivos y metadatos en `/api/recent-downloads` mediante prefijo de trabajo.

---

## [2.7.4] - 2026-09-01


### 🐛 Corrección de Cerrojos Reentrantes
- **🔒 Migración a `threading.RLock` en todos los cerrojos del servidor:**
  - Corrección de bloqueo recursivo (*self-deadlock*) que ocurría cuando los hooks de progreso de descarga (`progress_hooks`) adquirían `JOBS_LOCK` y llamaban a `append_job_log`, paralizando la atención de consultas `/api/status` y solicitudes web.
  - Implementación de cerrojos reentrantes `threading.RLock()` para `JOBS_LOCK`, `QUEUE_LOCK` y `BATCH_LOCK`.

---

## [2.7.3] - 2026-09-01


### ⚡ Rendimiento y Prevención de Sobrecarga
- **🚀 Eliminación de Sobrecarga de Tokens POT en Inspección de Metadatos:**
  - Desactivación del plugin `youtubepot-bgutilhttp` durante la inspección de metadatos (`download=False`).
  - La inspección de listas de reproducción extensas ahora se ejecuta en **1 a 2 segundos** sin saturar el generador de tokens de sesión ni bloquear los hilos del servidor.

---

## [2.7.2] - 2026-09-01


### 🐛 Correcciones Críticas de Concurrencia
- **🔒 Corrección de Bloqueo Mutuo (Deadlock) y Definición Global de `JOBS_LOCK`:**
  - Restauración de `JOBS` y `JOBS_LOCK` a nivel de módulo en `app.py`.
  - Desacoplamiento total de bloqueos (`QUEUE_LOCK` y `JOBS_LOCK`) en el bucle del worker en segundo plano `background_queue_worker` para evitar inversión de jerarquía de locks y timeouts 504/524.
  - Implementación del helper `safeApiPost` en el cliente JavaScript para manejo robusto de respuestas no JSON y estados de error.

---

## [2.7.1] - 2026-09-01


### 🐛 Correcciones y Rendimiento
- **⚡ Optimización y Corrección en Inspección de Playlists (`/api/info`):**
  - Corrección de excepción `TypeError (NoneType is not iterable)` cuando una playlist no existe o no devuelve entradas válidas.
  - Implementación de `is_permanent_error()` en `extract_with_fallback` para abortar inmediatamente ante playlists/videos inexistentes o privados, evitando retardos acumulados de clientes fallback.
  - Adición de `socket_timeout: 10s` y `playlistend: 300` para proteger contra congelamientos en enlaces pesados o caídos.
  - Indicador visual interactivo de carga (`⏳ Buscando...`) en los botones de inspección de la interfaz.

---

## [2.7.0] - 2026-09-01


### ✨ Novedades y Gestión de Descargas
- **⏳ Sistema de Cola en Segundo Plano y Persistencia Server-Side:**
  - Todas las descargas generadas en cualquier modo (Fácil, Avanzado, Lote) se procesan de manera secuencial y ordenada mediante un worker daemon en segundo plano (`background_queue_worker`).
  - Las descargas persisten en el servidor incluso si el usuario cierra la ventana del navegador o apaga su dispositivo.
  - Persistencia del estado de la cola en disco (`/app/queue_state.json`) para reanudar trabajos ante reinicios del contenedor.
- **🎛️ Panel de Gestión de Cola Interactivo:**
  - Nueva pestaña dedicada y contador dinámico en la barra lateral con la cantidad de descargas pendientes.
  - Reordenamiento de prioridad de descargas (`⬆️ Subir`, `⬇️ Bajar`), eliminación de descargas individuales (`🗑️ Quitar`) y vaciado total de la cola (`🛑 Vaciar Cola`).
  - Monitoreo en vivo de la descarga activa y resumen de historial reciente.
- **📁 Agrupación por Carpetas en "Mis Descargas":**
  - Las descargas provenientes de playlists, álbumes (Spotify / Deezer) o lotes múltiples se agrupan automáticamente dentro de tarjetas desplegables de tipo Carpeta/Colección.
  - Descarga masiva de la carpeta completa en un archivo `.ZIP` bajo demanda en un solo clic (`/api/my-downloads/folder-zip/<group_id>`).
  - Eliminación integral de la carpeta completa con liberación automática de espacio en disco (`DELETE /api/my-downloads/folder/<group_id>`).
  - Listado desplegable interno con acciones individuales por archivo (descargar / borrar).

---

## [2.6.0] - 2026-09-01


### ✨ Novedades y Resiliencia
- **🔄 Descargas en Cascada Automática y Diagnóstico Detallado (Modo Fácil):**
  - El Modo Fácil ejecuta una estrategia de cascada inteligente probando todos los motores en secuencia (`Cobalt v11 Oficial` -> `Motor Musical Especializado` -> `yt-dlp PoToken / Multi-Cliente`).
  - En caso de fallo global, se genera y presenta una tarjeta de diagnóstico exhaustiva con el desglose de cada motor probado y la causa exacta del error.
- **📟 Consola de Actividad y Progreso en Tiempo Real (Modo Avanzado):**
  - Bloque de terminal visual informativo en tiempo real (`#userActivityConsole`) que muestra el avance paso a paso, análisis de URL, velocidad de descarga y operaciones FFmpeg.
  - Registro estrictamente privado y acotado a la actividad del usuario autenticado, sin capacidades de ejecución ni exposición de datos sensibles del VPS.
  - Botón interactivo "🧹 Limpiar" para vaciar el historial de la consola.
- **📦 Explorador y Selector de Playlists en Modo Avanzado:**
  - Integración completa del explorador interactivo de listas y álbumes dentro del Modo Avanzado con casillas de selección, acciones masivas (Todos/Ninguno) y conmutador de entrega (ZIP vs Descargas Individuales Progresivas).

---

## [2.5.0] - 2026-09-01


### ✨ Novedades y Mejoras de Interfaz
- **Barra Lateral Fija en Portal de Descargas (Sidebar Layout):**
  - Rediseño integral de la página principal (`templates/index.html`) con barra lateral de navegación izquierda fija y panel de contenido fluido, homologando la experiencia visual del panel de administración.
  - Se eliminó el botón de actualización `⟳ yt-dlp` de la vista de descargas (exclusivo de administradores en `/admin`).
- **⚡ Modo Fácil / Rápido (Descarga en 1 Clic):**
  - Nueva interfaz simplificada: pegado directo de enlace, píldoras de presets rápidos (720p HD, 1080p FHD, Mejor Calidad, MP3 320k, MP3 192k, FLAC) y botón directo de descarga inmediata.
- **📦 Playlists Mejoradas: Selección de Elementos y Descarga Individual vs ZIP:**
  - Explorador interactivo de listas de reproducción y álbumes (YouTube, Spotify, Deezer).
  - Selector de elementos individual por casillas con botones de selección masiva (`Todos`, `Ninguno`) y contador dinámico.
  - Modo de entrega configurable: empaquetado en archivo `.ZIP` o **Descargas Individuales Progresivas** que se registran y procesan como archivos independientes listos para guardar o escuchar en tiempo real.

---

## [2.4.1] - 2026-09-01


### 📊 Métricas y Diagnóstico
- **Monitoreo Detallado de Memoria RAM (Proyecto vs VPS Total):**
  - Lectura en tiempo real del consumo específico de memoria RAM del proyecto mediante cgroups v2 (`/sys/fs/cgroup/memory.current`), cgroups v1 y RSS de procesos.
  - Barra de progreso segmentada de doble color que diferencia el consumo del contenedor respecto al consumo global de otros procesos del VPS y la memoria disponible.
  - Indicador dinámico en tarjeta de diagnóstico con desglose exacto en MB/GB y porcentaje relativo.

---

## [2.4.0] - 2026-09-01


### ✨ Novedades y Diagnóstico
- **Detección y Monitoreo del Motor Deno JS:**
  - Corrección de la clave de disponibilidad en `/api/admin/services-status` y visualización en tiempo real de la versión activa de Deno (`v2.9.5`).
  - Tarjeta dedicada en la pestaña de motores del Panel de Administración para el motor **Deno JS Runtime**.
- **Prueba Unitaria y Diagnóstico de Deno JS:**
  - Nuevo endpoint `POST /api/admin/test-deno` y botón **"🧪 Probar Deno JS"** para evaluar compilación y ejecución de scripts JavaScript, diagnosticar desafíos de YouTube (n-sig / player JS) y analizar errores futuros.

---

## [2.3.1] - 2026-09-01


### 🐛 Correcciones (Fix)
- **Corrección de Mapeo de Calidades de Video en yt-dlp:**
  - Definición explícita de `QUALITY_FORMAT_MAP` e `is_audio_quality` en `app.py`.
  - Se solucionó el error `name 'QUALITY_FORMAT_MAP' is not defined` al solicitar descargas de videos individuales o playlists en resoluciones como 720p, 1080p, 1440p, 2160p y 480p/360p.

---

## [2.3.0] - 2026-09-01


### ✨ Novedades y Mejoras de Interfaz
- **Barra Lateral Fija en Panel de Administración (Sidebar Layout):**
  - Rediseño completo de `/admin` con barra lateral de navegación izquierda fija y panel de contenido fluido a la derecha.
  - Eliminación de la necesidad de scroll vertical en pantallas estándar con visualización compacta y organizada de microservicios, motores, configuración, cloud sync y usuarios.
- **Corrección de Columnas y Badges de Estado en Tablas:**
  - Solución definitiva al quiebre de texto en las columnas `ESTADO`, `ROL` y `FECHA ALTA` de la tabla de usuarios.
  - Badges con `white-space: nowrap`, puntos indicadores (`badge-dot`) alineados y diseño estructurado.
- **Instalación PWA desde Pantalla de Entrada (`/login`):**
  - Incorporación del botón **"📲 Instalar App en este dispositivo"** directamente en la pantalla de inicio de sesión.

---

## [2.2.1] - 2026-09-01


### 🐛 Correcciones y Mejoras
- **Formulario Web de Inicio de Sesión (`/login`):**
  - Implementación de interfaz gráfica web dedicada para el inicio de sesión (`templates/login.html`), eliminando diálogos emergentes de error 500 / 401 en accesos directos desde el navegador.
  - Autenticación híbrida basada en sesiones seguras de Flask (`session`) para el navegador y compatibilidad con `HTTP Basic Auth` para llamadas automáticas a `/api/`.
  - Redirección automática y fluida al inicio de sesión si el usuario no está autenticado, con retorno a la página solicitada tras loguearse (`?next=...`).
  - Gestión visual de avisos de suspensión y cierre de sesión exitoso.

---

## [2.2.0] - 2026-09-01


### ✨ Novedades y Características
- **Cierre de Sesión (Logout):**
  - Botón **"🚪 Salir"** disponible en la barra de navegación de todas las vistas (`/`, `/admin`, `/wiki`).
  - Endpoint `/logout` que invalida las credenciales HTTP Basic Auth en caché y redirige a la pantalla de acceso.
- **Gestión Avanzada de Usuarios en Panel `/admin`:**
  - Registro y creación de nuevos usuarios con rol (`admin` / `downloader`) y estado inicial.
  - **Suspensión de Usuarios:** Posibilidad de pausar/suspender el acceso a cualquier usuario con un clic (`POST /api/admin/users/<username>/toggle-status`).
  - **Limpieza de Descargas por Usuario:** Endpoint `POST /api/admin/users/<username>/clean-downloads` para eliminar todos los archivos descargados pertenecientes a un usuario específico y liberar espacio en el VPS.
  - Modificación de credenciales, roles y eliminación definitiva con purga de archivos asociados.
- **Mantenimiento y Comprobación de Cobalt Oficial (v11):**
  - Módulo en la pestaña de motores para el motor oficial **Cobalt API**.
  - Visualización de la versión activa en ejecución (ej. `v11.7.1`) y plataformas soportadas.
  - Botón **"🔍 Comprobar Cobalt"** que consulta la API oficial de GitHub Releases (`imputnet/cobalt`) y avisa si hay una nueva versión disponible.
  - Botón **"⟳ Verificar / Actualizar Cobalt"** (`POST /api/admin/update-cobalt`) para monitorear la salud del microservicio.

---

## [2.1.0] - 2026-09-01


### ✨ Novedades y Características
- **Rediseño Visual Amplio (Full-Screen 2-Column Dashboard):**
  - Nuevo diseño moderno que aprovecha al máximo el ancho de pantalla en monitores y tablets.
  - Distribución en 2 columnas: panel de configuración y descarga a la izquierda, monitor en vivo y descargas personales a la derecha.
- **Soporte PWA (Progressive Web App):**
  - Aplicación instalable en dispositivos móviles (Android / iOS) y PC con un clic (`manifest.json`, `sw.js` y botón `📲 Instalar App`).
- **Privacidad Estricta de Descargas por Usuario:**
  - El historial de descargas recientes ahora está estrictamente aislado por usuario (`username`).
  - Los usuarios estándar solo ven y gestionan sus propias descargas sin acceso a las de otros.
  - Nuevos endpoints: `DELETE /api/my-downloads/<job_id>` y `POST /api/my-downloads/cleanup` para que cada usuario pueda eliminar sus descargas personales y liberar espacio.
- **Restricción de Herramientas de Administración:**
  - Los botones de actualización de motor (`⟳ yt-dlp`), widget de disco VPS y limpieza total del servidor ahora son exclusivos para el rol `admin`.
- **Verificador de Actualizaciones de Motor en `/admin`:**
  - Botón **"🔍 Comprobar Actualización"** y endpoint `GET /api/admin/check-updates` que consulta PyPI en tiempo real para verificar si existe una nueva versión de `yt-dlp` antes de actualizar.
- **Consumo de Memoria RAM en Tiempo Real:**
  - Medición del uso de memoria RAM total del VPS y proyecto en `GET /api/admin/services-status` y tarjeta interactiva en el panel `/admin`.
- **Subida a la Nube para el Usuario Común:**
  - Acordeón personal en el panel de descargas para enviar archivos a Nextcloud / WebDAV o FTP personal (guardando credenciales privadas en `localStorage`).

---

## [2.0.0] - 2026-09-01

### ✨ Novedades y Características
- **Cola de Descargas Simultáneas Multi-Enlace (Batch Queue):**
  - Nuevo selector de modo en la interfaz: **Enlace Individual** vs **📋 Modo Múltiples Enlaces**.
  - Permite pegar múltiples URLs simultáneas (una por línea) de diferentes plataformas (YouTube, Spotify, Deezer, TikTok, etc.).
  - Panel visual de cola en tiempo real con barras de progreso por archivo y enlaces de descarga independientes.
  - **Empaquetador de Lote:** Botón **"📦 Descargar Todo (.ZIP)"** que comprime automáticamente todas las descargas terminadas del lote.
  - Nuevos endpoints API: `POST /api/batch-download`, `GET /api/batch-status/<batch_id>`, `GET /api/batch-download-zip/<batch_id>`.
- **Módulo de Sincronización en la Nube (Cloud Sync):**
  - Subida y notificación automática de archivos finalizados sin consumir ancho de banda local.
  - **Nextcloud / ownCloud / WebDAV:** Subida directa mediante protocolo WebDAV con autenticación por credenciales o App Token.
  - **Servidor FTP:** Subida automatizada a servidores FTP remotos.
  - **Telegram Bot Uploader:** Envío de audios y videos directamente a chats o canales de Telegram mediante la API de bots.
  - **Webhook HTTP:** Disparo de eventos `POST` JSON con metadatos y enlaces de descarga para integración con servicios externos (n8n, Zapier, Make, etc.).
- **Centro de Control Cloud Sync en `/admin`:**
  - Nueva pestaña **☁️ Sincronización en la Nube** en el panel de administración con formularios dedicados y **botones de prueba de conexión en vivo** para cada servicio.

---

## [1.4.0] - 2026-09-01

### ✨ Novedades y Características
- **Personalización Visual y Selector de Temas:**
  - Selector de 4 temas visuales con persistencia en `localStorage`:
    - 🌌 **Cyberpunk / Midnight Neon** (Degradados azul/púrpura de alta estética).
    - 🖤 **OLED Black** (Negro puro para pantallas OLED y contraste máximo).
    - 🌲 **Emerald Forest** (Verde esmeralda y tonos oscuros naturales).
    - ☀️ **Light Modern** (Tema claro elegante).
  - Selector de tema predeterminado global configurable desde el panel de administración.
  - Personalización de **Título del Sitio** y **Subtítulo** en tiempo real desde `/admin`.
- **Soporte de Formatos de Video y Audio Avanzados:**
  - **Video:** Selector de contenedor de salida: `MP4` (universal), `MKV` (Matroska) y `WebM`.
  - **Audio:** Selector ampliado de formatos: `MP3` (128, 192, 256, 320 kbps), `FLAC` (sin pérdida / Lossless), `M4A` (AAC), `Opus` y `WAV`.
- **Soporte de Subtítulos:**
  - Opciones de subtítulos configurables: Sin subtítulos, Incrustar subtítulos en el video (*embed*) o Descargar archivo `.srt`/`.vtt` independiente.

---

## [1.3.0] - 2026-09-01

### ✨ Novedades y Características
- **Panel de Control y Administración Web (`/admin`):**
  - Interfaz gráfica moderna, oscura y responsiva para gestionar todo el sistema sin terminal.
- **Diagnóstico y Salud de Microservicios en Vivo:**
  - Monitoreo en tiempo real de `yt-downloader` (Flask App), `pot-provider` (bgutil en `:4416`), `cobalt-api` (Cobalt en `:9000`), motor `Deno` y `FFmpeg`.
  - Visualización del uso del disco con barra de progreso interactiva.
- **Centro de Actualización de Motores:**
  - Botón de actualización de `yt-dlp` a demanda con visualizador de logs en tiempo real y auto-reinicio.
  - Botón de diagnóstico de conectividad y extracción para probar los motores en vivo.
- **Gestión Dinámica de Configuración y Cookies:**
  - Modificación de retención de descargas (`CLEANUP_AFTER_HOURS`), umbrales de alerta de disco y motor predeterminado persistidos en `config.json`.
  - Editor y visor de `cookies.txt` de YouTube directamente desde la web (sin SSH/SCP).
- **Gestión de Usuarios con Roles:**
  - Almacenamiento seguro en `users.json` con contraseñas cifradas (SHA-256 + Salt).
  - Creación, modificación de claves, asignación de roles (`admin` vs `downloader`) y eliminación de usuarios autorizados.
  - Protección con `@require_admin` para acceso exclusivo a herramientas de configuración.

---

## [1.2.0] - 2026-09-01

### ✨ Novedades y Características
- **Integración de Plataformas Musicales:**
  - **Deezer con y sin ARL:**
    - Campo en la interfaz para ingresar token ARL de Deezer con persistencia local (`localStorage`).
    - Descarga directa en alta fidelidad (FLAC / 320 kbps) si se proporciona ARL válido.
    - **Fallback automático inteligente:** Si no se ingresa ARL o el token está vencido, se descarga igualmente mediante emparejamiento de audio sin interrumpir al usuario.
    - Soporte para tracks individuales, álbumes y playlists de Deezer.
  - **Spotify:**
    - Detección de canciones de Spotify y extracción de metadatos (Título, Artista, Álbum, Carátula en alta resolución).
    - Emparejamiento de audio y descarga directa.
- **Incrustación Automática de Metadatos y Carátulas ID3:**
  - FFmpeg incrusta automáticamente la portada del álbum en alta resolución y las etiquetas ID3v2 (Título, Artista, Álbum) en los archivos `.mp3` descargados.
- **Insignias de Plataforma:**
  - Insignias interactivas para Deezer y Spotify en la barra superior y tarjeta de vista previa.

---

## [1.1.0] - 2026-08-31

### ✨ Novedades y Características
- **Protección y Monitoreo de Almacenamiento:**
  - Widget en tiempo real del espacio en disco del VPS en la interfaz web (`GET /api/disk-status`).
  - Botón interactivo **"🧹 Limpiar"** para forzar la eliminación de archivos descargados a demanda (`POST /api/cleanup`).
  - **Auto-purga de emergencia:** Activación automática si el disco supera el 85% de uso o si quedan menos de 2 GB libres.
- **Historial de Descargas Recientes:**
  - Sección desplegable en la interfaz con los últimos archivos listos para descargar en el servidor (`GET /api/recent-downloads`), permitiendo re-descargar sin reprocesar.
  - Soporte de re-descarga de archivos incluso tras reinicios del servidor.
- **Soporte Multi-Plataforma y Normalización:**
  - Normalización inteligente de **YouTube Shorts** (`/shorts/` -> visualización y descarga directa).
  - Reconocimiento de plataformas adicionales: **Instagram**, **Facebook**, **Twitch**, **Kick**, **TikTok** y **X/Twitter**.
  - Insignia con el nombre de la plataforma detectada en la tarjeta de previsualización.

---

## [1.0.0] - 2026-08-31

### ✨ Novedades y Características
- **Arquitectura de Doble Motor:**
  - **yt-dlp:** Soporte completo para videos en calidades 4K, 1080p, 720p, 480p, extracción de audio en MP3 (128, 192, 256, 320 kbps), recorte por rango de tiempo (*trimming*) y descarga de playlists completas en `.zip`.
  - **Cobalt (v11):** Integración como motor secundario de alta velocidad para videos y audios individuales.
- **Proveedor Unificado de PO Tokens (`potprovider`):**
  - Implementación con `bgutil-ytdlp-pot-provider` para alimentar de Proof-of-Origin Tokens tanto a `yt-dlp` como a `Cobalt` (vía `POST /get_pot`).
  - Eliminación de dependencias pesadas de Chromium/GUI en servidores VPS.
- **Motor JavaScript Deno:**
  - Integración de Deno dentro de la imagen de Docker para resolver los desafíos de JavaScript que exige YouTube.
- **Seguridad y Privacidad:**
  - Protección de acceso mediante HTTP Basic Auth (`APP_USERNAME` / `APP_PASSWORD`).
  - Cabeceras `X-Robots-Tag` y `robots.txt` para prevenir indexación en motores de búsqueda.
  - Exclusión estricta de credenciales (`.env`) y sesiones (`cookies.txt`) mediante `.gitignore`.
