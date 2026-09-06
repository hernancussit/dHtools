# Registro de Cambios (Changelog)

Todos los cambios notables en este proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [1.5.0] - 2026-09-06

### 🚀 Lanzamiento Oficial Estable v1.5.0

### 🎨 Identidad de Marca Oficial & Rediseño de Experiencia de Usuario
- **Suite Completa de Marca y Logotipo (`static/icons/`):**
  - Incorporación del avatar y logotipo oficial de alta fidelidad con el monograma `dH`, rayos de neón y ondas de sonido cyberpunk.
  - Banner horizontal panorámico de alta definición (`brand_horizontal.png`) integrado en la barra lateral del dashboard y panel administrativo, con tipografía nítida para *"MULTIMEDIA SUITE"* en cian eléctrico de alto contraste.
  - Generación de favicons de alta densidad (`favicon.png`, `favicon.ico` multi-capa 16/32/48/64px), íconos para iOS (`apple-touch-icon.png`) y PWA (`icon-192.png`, `icon-512.png`).
  - Actualización del manifiesto de aplicación web progresiva (`static/manifest.json`).
- **Página Dedicada "Acerca de" (`/about` & `/acerca-de`):**
  - Módulo de contribución y donaciones integrado con **Cafecito.app** (`cafecito.app/henu_45`) con botón interactivo y código QR dinámico para escanear desde dispositivos móviles.
  - Ficha de autor y créditos de desarrollo (Hernán Cussit / Servicios Informáticos LT).
  - Tarjeta independiente y modular para el Asistente de Telegram self-hosted.
  - Resumen visual de arquitectura de microservicios y licencia libre MIT.
- **Rediseño Móvil Ergonómico (`templates/index.html`):**
  - Barra de navegación inferior fija y permanente (`Bottom Nav Bar`) accesible en cualquier sección de la app para navegación táctil con una sola mano.
  - Menú lateral desplegable (*Off-canvas drawer*) con perfil de usuario y control de cuota de disco.
  - Cabecera compacta (*Topbar*) con selector rápido de temas y contador en vivo de descargas en cola.
- **Doble Consola Interactiva en Tiempo Real (`templates/index.html`):**
  - Incorporación de la terminal de actividad en tiempo real dentro del **Modo Fácil**, permitiendo visualizar inspección de enlaces, progreso de descarga, y eventos de transcodificación FFmpeg sin alternar al Modo Avanzado.

### 📚 Wiki Técnica, Mitigación Antibot & Troubleshooting Empírico (`templates/wiki.html`)
- **Sección 11: Túnel Universal & Proxies Residenciales (SOCKS5 / MikroTik RouterOS):**
  - Documentación de la arquitectura de mitigación de bloqueos por ASN de datacenters.
  - Integración con RouterOS (`/ip socks`) y túneles WireGuard con telemetría de latencia TCP (RTT en milisegundos).
- **Sección 12: Guía Exhaustiva de Solución de Problemas (Troubleshooting):**
  - Paso a paso para resolver `Sign in to confirm you're not a bot` y `UNPLAYABLE` mediante exportación Netscape sin invalidación de tokens de sesión.
  - Evasión de bloqueos SABR forzados a 360p en YouTube mediante cascada multi-cliente (`web_music`, `web`, `mweb`).
  - Resolución de límites de 50 MB en Telegram y fallback transparente a documento.
  - Manejo eficiente de memoria RAM en descargas masivas y subidas cloud mediante streaming chunked.
- **Acceso Público:** Desbloqueo de acceso libre para `/wiki` y `/about` sin requerir autenticación previa.

### 🤖 Asistente de Telegram: Aislamiento Estricto y Reconocimiento Natural (`core/telegram_bot.py`)
- **Aislamiento Estricto de Descargas por Usuario:**
  - Corrección de visibilidad en `/descargas`: cada usuario vinculado a Telegram accede estricta y exclusivamente a sus propios archivos, eliminando cualquier fuga cruzada de descargas entre usuarios o administradores.
  - Validación de seguridad en callbacks (`send:<id>`) impidiendo descargas no autorizadas.
- **Reconocimiento de Lenguaje Natural:** Detección de intenciones conversacionales ("mis descargas", "estado de cola", "mi cuota de espacio", "ayuda") sin obligar al uso de comandos de barra.

### ⚡ Optimización y Fortalecimiento del Motor Cobalt v11
- **Sincronización Automática de Cookies Netscape a JSON de Cobalt (`core/utils.py`, `core/config.py`):**
  - Conversión inteligente de `cookies.txt` (formato Netscape) agrupando dominios de YouTube, Instagram, Twitter/X y Reddit en la estructura nativa requerida por Cobalt v11 (`{ "youtube": ["NAME=VALUE; ..."] }`).
  - Montaje de volumen persistente con permisos de escritura (`rw`) en `docker-compose.yml` (`./cobalt_cookies.json:/cookies.json`) y variable `COOKIE_PATH`, permitiendo a Cobalt persistir actualizaciones y cabeceras `Set-Cookie`.
  - Integración en el flujo de subida y eliminación de cookies del panel de administración (`routes/admin.py`).
- **Enrutamiento Inteligente por Plataforma (Smart Cascade Routing en `core/downloader.py`):**
  - Derivación directa como Nivel 1 prioritario para plataformas sociales nativas: TikTok, Instagram, Twitter / X (`x.com` y `twitter.com`), Reddit, SoundCloud, Vimeo, Facebook, Twitch, etc., logrando descargas directas desde CDN en milisegundos sin marcas de agua.
  - Detección selectiva para YouTube y YouTube Shorts: verificación en milisegundos de cookies autenticadas (`SID`, `HSID`, `LOGIN_INFO`). Si no hay sesión válida para la IP del servidor, se omite el error garantizado de inicio de sesión de Cobalt y se deriva de inmediato a `yt-dlp` (con PO Token Provider y Deno), eliminando latencia innecesaria.
- **Payload Enriquecido y Soporte de Formatos (`core/downloader.py`):**
  - Mapeo de contenedor de salida (`youtubeVideoContainer`: `mp4`, `webm`, `mkv`), formatos de audio de alta fidelidad (`mp3`, `ogg`, `wav`, `opus`) y bitrates (`128k` a `320k`).
  - Activación de `tiktokFullAudio` para pistas completas de TikTok y extracción de nombres reales vía cabecera `Content-Disposition`.
  - Resolución inteligente de respuestas tipo `picker` para carruseles y galerías multi-ítem seleccionando el stream de video de mayor calidad.
  - Traducción y mapeo amigable de errores de la API de Cobalt (`COBALT_ERROR_TRANSLATIONS`).
- **Telemetría y Estado en Panel Admin (`routes/admin.py` & `templates/admin.html`):**
  - Nuevo indicador de estado de cookies de Cobalt en vivo en la tarjeta de motor (`/api/admin/cobalt-status`), indicando la presencia de cookies activas y de sesión de YouTube.
- **Cancelación Inmediata y Notificaciones Telegram:**
  - Chequeo cooperativo de cancelación del trabajo durante el streaming de chunks en `run_download_cobalt`.
  - Notificaciones de progreso periódicas al bot interactivo de Telegram durante la transferencia desde CDN.

### ☁️ Conectores Cloud Avanzados (S3 / MinIO / R2) & Modo Offload Seguro
- **Módulo Universal de Sincronización en la Nube (`core/cloud_sync.py`):**
  - Desacoplamiento completo de las transferencias a la nube desde `core/downloader.py` hacia una arquitectura modular y escalable.
  - Conector para buckets compatibles con S3 (**Amazon S3, MinIO, Cloudflare R2, Backblaze B2, Wasabi**) con `boto3` y streaming multipart (`TransferConfig` con fragmentos de 10 MB) para archivos gigantes sin saturar memoria RAM.
  - Métodos de prueba interactivos (`test_s3_connection` vía `head_bucket`) con manejo contextual de errores (403 AccessDenied, 404 NoSuchBucket, etc.).
- **Modo Offload ("Subir y Mover" / Ahorro Extremo de Disco):**
  - Mecanismo seguro de transferencia y liberación de espacio en disco del VPS: el archivo local solo se elimina si la subida cloud fue exitosa en al menos un destino (`successful_destinations`).
  - Preservación de metadatos en `downloads_meta.json` marcando el archivo como `offloaded: true` con la lista de destinos remotos.
  - Distintivo visual `☁️ En la nube` en el historial de "Mis Descargas" (`templates/index.html` y `routes/ui.py`).
  - Eliminación unificada: el usuario puede borrar registros offloaded desde la interfaz sin provocar errores de archivo inexistente.
- **Presets de Usuario & Panel Administrativo (`templates/index.html`, `templates/admin.html`, `routes/admin.py`):**
  - Soporte de almacenamiento de tipo `s3` en perfiles privados por usuario con prueba de conectividad en vivo.
  - Configuración administrativa de S3/MinIO/R2 a nivel de servidor en el panel `/admin`.

## [1.4.0] - 2026-09-05

### 🚀 Lanzamiento Estable v1.4.0

### 🛡️ Respaldo Residencial de Último Recurso (Tier 4 / Residential Failsafe)
- **Cascada Inteligente de 4 Niveles (`core/downloader.py`):**
  - Incorporación del **Nivel 4 (Respaldo Residencial)**: activado de manera autónoma únicamente cuando los niveles del VPS fallan ante bloqueos antibot de YouTube (`UNPLAYABLE`, `bot verification required`, o degradación forzada a 360p en descargas HD solicitadas a 1080p).
  - Preservación estricta de los recursos de la red residencial: más del 90% de las descargas y el tráfico pesado continúan cursándose por la infraestructura directa del VPS.
  - Soporte para proxy SOCKS5/SOCKS5h con resolución DNS en destino para eludir inconsistencias geográficas y de CDN.
- **Sonda de Diagnóstico y Telemetría RTT en Tiempo Real (`routes/admin.py` & `templates/admin.html`):**
  - Métrica de Round-Trip Time (RTT) directa vía ping TCP (`socket`) en milisegundos para evaluar con precisión la latencia del túnel al enlace residencial de respaldo.
  - Prueba de extracción end-to-end con YouTube para validar el funcionamiento del proxy antes de que ocurra una falla real en producción.

### 🤖 Asistente de Telegram: Corrección de Entrega y Envío Selectivo
- **Solución al Bug de Entrega de Archivos (`core/downloader.py` & `core/telegram_bot.py`):**
  - Garantía de trazabilidad de `job_id` en las estructuras internas de trabajo encoladas (`enqueue_job`), asegurando que las notificaciones de finalización al 100% encuentren el mensaje activo y despachen el archivo multimedia sin interrupciones.
  - Fallback automático en `send_media`: ante cualquier rechazo por códec o contenedor en la API de Telegram con `sendVideo` o `sendAudio`, el sistema rebobina el archivo y reintenta de forma transparente como `sendDocument`.
- **Aislamiento de Descargas Web:**
  - Supresión definitiva de la difusión automática de descargas del panel web al chat del administrador. Las descargas web permanecen de forma privada y exclusiva en la plataforma web.
- **Envío a Telegram Bajo Demanda en "Mis Descargas" (`routes/ui.py` & `templates/index.html`):**
  - Botón interactivo **"✈️ Telegram"** en cada tarjeta de archivo y colección/carpeta para enviar cualquier descarga directamente al chat de Telegram del usuario en 1 clic.
  - Manejo automático de límites: transferencia directa si el archivo es $\le 50$ MB; mensaje explicativo con enlace web seguro si el archivo supera el límite de bots de Telegram.

## [1.3.0] - 2026-09-02

### 🚀 Lanzamiento Estable v1.3.0

### 🤖 Asistente Interactivo de Telegram (Telegram Bot Hub)
- **Motor Long-Polling Autónomo (`core/telegram_bot.py`):**
  - Worker continuo de segundo plano en Python nativo (`requests`) que consulta la API de Telegram sin requerir webhooks ni certificados SSL dedicados.
  - Comandos interactivos: `/start`, `/vincular <token>`, `/desvincular`, `/descargas`, `/cola`, `/cuota`, `/ayuda`.
  - **Solicitud de Nuevas Descargas desde el Chat:** Envío directo de cualquier enlace con inspección previa y menú táctil en línea (*Inline Keyboards*) para elegir resoluciones (`1080p`, `720p`, `480p`) o audio (`MP3 320k`, `MP3 192k`, `FLAC`).
  - **Monitoreo Dinámico de Progreso:** Barra visual de porcentaje y velocidad que se actualiza periódicamente editando el mensaje en el chat.
  - **Entrega Inteligente:** Envío automático del archivo al chat para tamaños de hasta 50 MB, o generación de enlace seguro para archivos mayores.
  - **Vinculación Segura (Telegram Connect):** Generación de tokens de emparejamiento temporales desde el perfil web con aislamiento de archivos por usuario y control de cuotas.

### ☁️ Hub de Conectores Cloud con Presets Privados por Usuario
- **Gestor de Presets en Servidor (`core/utils.py` & `routes/api.py`):**
  - Almacenamiento seguro de múltiples perfiles de almacenamiento por usuario en `users.json` (`/api/user/cloud-presets`).
  - Selector rápido de presets en el Modo Avanzado de descargas con carga automática de credenciales.
  - Herramienta de prueba de conexión en 1 clic para WebDAV y FTP (`/api/user/cloud-presets/test`).

### ⚡ Evasión de Restricciones SABR de YouTube (Full HD 1080p Restablecido)
- **Cascada Multi-Cliente Dinámica (`core/downloader.py`):**
  - Incorporación de lista combinada `["web_music", "web", "mweb", "web_embedded"]` que elude el bloqueo de streams forzados SABR de YouTube, recuperando la descarga en Full HD 1080p (`1920x1080`), 720p y 480p.
  - Generación continua de tokens Proof-of-Origin (PO Tokens) con el microservicio `pot-provider` estabilizado bajo Docker Compose v2.
  - Inyección de PO Token Provider tanto en la fase de inspección de metadatos como en la descarga real (`core/utils.py`).

### 🛡️ Seguridad, Privacidad y Versionado Consciente
- **Protección de Datos Sensibles en Panel Admin:**
  - Ofuscación mediante `type="password"` de campos confidenciales: Bot Token de Telegram, Default Chat ID, Contraseña WebDAV y Contraseña FTP.
- **Leyenda de Versión Dinámica:**
  - Inyección unificada del identificador de rama git (`-main` / `-dev`) en la barra superior de `index.html`, `admin.html` y `wiki.html`.
- **Visibilidad Condicional de Controles:**
  - Ocultación dinámica del botón de Telegram en la barra lateral cuando el bot no está activo.

## [1.2.0] - 2026-09-02

### 🚀 Lanzamiento Estable v1.2.0
- **100% Modularización del Monolito:**
  - Desacoplado `app.py` en capas funcionales independientes y mantenibles:
    - `core/config.py`: Gestión centralizada de variables de entorno, resolución de rutas y clave secreta de sesión persistente.
    - `core/state.py`: Estructuras de memoria compartida, bloqueos de concurrencia reentrantes (`JOBS_LOCK`, `QUEUE_LOCK`, `BATCH_LOCK`) y estado del worker.
    - `core/utils.py`: Utilidades de sistema, formateo de bytes/velocidad, sanitización canónica de nombres de archivo y validación estricta de URLs.
    - `core/downloader.py`: Motor unificado de descargas (yt-dlp, Cobalt, Deezer, Spotify) y workers de segundo plano.
    - `routes/auth.py`: Autenticación, protección perimetral de rutas, hashing PBKDF2 y limitador de intentos por IP.
    - `routes/admin.py`: Panel de administración, diagnósticos de salud, gestión de usuarios multirrol y sincronización.
    - `routes/ui.py`: Rutas de la interfaz web, descarga de archivos personales y soporte PWA (`manifest`, `sw.js`).
    - `routes/api.py`: API de descarga, monitor de estado en vivo, encolamiento y cancelación de trabajos.
- **Workers en Segundo Plano con Compatibilidad Gunicorn:**
  - Inicialización incondicional de hilos de trabajo (`background_queue_worker`, `cleanup_loop`, `auto_update_loop`) en la carga del módulo `app`, garantizando compatibilidad total con servidores WSGI de producción.
- **Homogeneización de Motores y Monitor de Latencias en Milisegundos:**
  - Unificación visual de los 3 motores (`yt-dlp`, `Cobalt` y `Deno`) con badge uniforme `● Online` y medición de latencia en ms en tiempo real.
  - Implementación de comprobación remota y auto-actualización vía `deno upgrade` para Deno JS desde el panel administrativo.
  - Botón "Refrescar Datos" que sincroniza simultáneamente el estado de todos los motores y métricas del sistema.
- **Unificación de Descargas en Lote en Modo Fácil y Avanzado (Opción C):**
  - Conmutador interactivo `[ 🔗 Enlace Único | 📋 Descarga en Lote ]` integrado directamente en Modo Fácil y Modo Avanzado.
  - Procesamiento de lotes con presets rápidos en Modo Fácil y con personalización completa en Modo Avanzado (resoluciones hasta 4K, contenedores MP4/MKV/WebM, subtítulos, motor Cobalt/yt-dlp y sincronización a la nube).
  - Monitor global de progreso de lotes con descarga directa en `.zip` y barra lateral simplificada.
- **Favicon Oficial Multiplataforma & Endpoint Directo:**
  - Creación e integración de `favicon.svg` y `favicon.ico` con la identidad oficial (relámpago estilizado con gradiente cian a coral sobre fondo oscuro).
  - Enlazado en todas las plantillas web (`index.html`, `admin.html`, `login.html`, `wiki.html`) y ruta dedicada `/favicon.ico`.
- **Optimización de Navegación Móvil y Cola Enriquecida:**
  - Eliminación de desbordes horizontales accidentales (`overflow-x: hidden`) y compactación de la navegación en móviles (cuadrícula 2x2).
  - Presentación enriquecida en la cola destacando el título real del contenido en negrita y ocultando URLs secundarias en pantallas móviles.
  - Propagación de títulos pre-inspeccionados a la API para visualización inmediata desde el segundo cero.
- **Optimización de Recorte Temporal (Trimming) con Feedback en Vivo:**
  - Inyección de avisos en consola informando el rango exacto de recorte solicitado (`HH:MM:SS` / `MM:SS`) y confirmando la transferencia estricta de segmentos sin descargar el video completo.
- **Configuración de Servidor SMTP & Alertas por Correo:**
  - Módulo nativo `send_system_email` con soporte STARTTLS y SSL/TLS para proveedores como Gmail, Outlook o SMTP privados.
  - Tarjeta de administración para configurar servidor, puerto, credenciales y prueba de envío en vivo (`/api/admin/smtp-test`).
- **Gestión de Cuentas con Email & Recuperación de Contraseñas:**
  - Campo de correo electrónico integrado en la creación y administración de usuarios (`users.json`).
  - Flujo de recuperación de contraseñas olvidadas mediante tokens seguros de un solo uso (1 hora) con enlace directo desde `/login`.
- **Autenticación de Dos Factores (2FA / TOTP Opcional):**
  - Motor de generación y verificación RFC 6238 implementado en Python nativo sin dependencias externas.
  - Asistente de configuración con clave Base32, URL `otpauth://`, código QR dinámico y 8 códigos de respaldo (*backup recovery codes*).
  - Verificación en dos pasos en pantalla de login (`step="2fa"`) y modal de gestión de seguridad en el perfil.
- **Control de Cuotas de Almacenamiento & Auditoría de Sesiones Activas:**
  - Asignación de cuota máxima de disco por cuenta (`quota_gb`) con validación preventiva en descargas individuales y por lotes.
  - Widget con barra de progreso de almacenamiento en el panel lateral de usuario.
  - Registro y telemetría de sesiones web activas en tiempo real con capacidad de revocación remota instantánea desde la administración.

---

## [1.1.1] - 2026-09-01

### 🛡️ Parche Crítico de Seguridad (Security Hardening)
- **🔒 Eliminación del Volumen SSH del Contenedor:**
  - Retirado el montaje `- ~/.ssh:/root/.ssh:ro` de `docker-compose.yml`. El actualizador de Git ahora utiliza exclusivamente HTTPS público sin exponer claves privadas del host.
- **🔑 Generación Criptográfica y Persistente de `FLASK_SECRET_KEY`:**
  - Eliminado el valor fallback estático. El servidor genera automáticamente un secreto aleatorio de 32 bytes (`.flask_secret`) en el primer inicio si no se define en `.env`.
- **🔐 Fortalecimiento de Hash de Contraseñas (PBKDF2-SHA256):**
  - Reemplazado el algoritmo SHA-256 con sal fija por `werkzeug.security` (`pbkdf2:sha256:600000`) con sal aleatoria única por usuario y migración transparente automática al iniciar sesión.
- **🛡️ Control Estricto de Propietario en `/api/files/<job_id>`:**
  - Verificación de propiedad por usuario (`current_user`) impidiendo que usuarios con rol `downloader` accedan a descargas de otros usuarios mediante IDs de trabajo conocidos.
- **🚫 Mitigación contra Redirección Abierta (*Open Redirect*):**
  - Validación canónica de `next_url` en `/login` bloqueando URLs relativas a protocolo (`//malicious.com`) o destinos con `netloc` externo.
- **⚙️ Limpieza de Variables de Entorno en Cobalt:**
  - Desvinculada la variable `YOUTUBE_SESSION_SERVER` huérfana de Cobalt en `docker-compose.yml`.

---

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

### 🚀 Lanzamiento Público Oficial Estable (dHtools)
Consolidación integral de la plataforma de descarga y extracción multimedia en su primera versión pública de código abierto:

- **⚡ Arquitectura de Triple Motor de Extracción:**
  - Cascada inteligente y tolerante a fallos: motor nativo `yt-dlp` (Python) con fallback automático al microservicio oficial `Cobalt v11` en contenedor dedicado.
  - Integración nativa para plataformas de streaming musical (**Deezer y Spotify** con soporte de token ARL y metadatos completos).
  - Soporte de resoluciones desde 144p hasta 4K (2160p), 60 FPS, HDR y extracción de audio en MP3, M4A, Opus y FLAC.
- **🦕 Entorno JavaScript Deno & PoToken Provider:**
  - Microservicio Bgutil PoToken integrado para eludir bloqueos de streaming de YouTube.
  - Runtime Deno JS embebido en el contenedor para resolución de desafíos de firma JavaScript.
- **📋 Gestión Avanzada de Playlists y Cola en Segundo Plano:**
  - Encolado visual ítem por ítem con monitoreo de progreso en tiempo real y badges de estado.
  - Control de prioridades (⬆️/⬇️) y cancelación inmediata por socket y aborto en yt-dlp.
  - Entrega flexible de listas de reproducción: empaquetado automático en archivos `.zip` o carpetas individuales organizadas.
- **🛡️ Blindaje de Seguridad Integral:**
  - Protección contra ataques de fuerza bruta en `/login` mediante limitador temporal por IP (`429 Too Many Requests`) y tarpit exponencial.
  - Validación estricta de URLs (`validate_media_url`) contra inyección de comandos de shell (RCE) y protocolos no seguros.
  - Verificación canónica de rutas (`safe_download_path`) impidiendo ataques de *Path Traversal*.
  - Cabeceras HTTP de seguridad (`Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`) y cookies `HttpOnly`/`SameSite=Lax`.
- **⚙️ Panel de Administración, Diagnóstico y Multi-Usuario:**
  - Monitoreo en tiempo real de recursos del servidor: uso de RAM (Proyecto vs VPS Total), espacio en disco y alertas de emergencia.
  - Gestión de usuarios multirrol (`admin` y `downloader`) con cuotas y aislamiento de descargas.
  - Actualizador y Rollback en 1 clic con selección de canal (`main` vs `dev`).
  - Sincronización en la nube mediante protocolo WebDAV / Nextcloud.
- **📱 Experiencia de Usuario & PWA:**
  - Interfaz moderna con tema oscuro, glassmorphism y diseño 100% responsivo para móviles y escritorio.
  - Soporte como Aplicación Web Progresiva (PWA) instalable con Service Worker y funcionamiento offline de interfaz.
