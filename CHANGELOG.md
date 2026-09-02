# Registro de Cambios (Changelog)

Todos los cambios notables en este proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [1.2.0-dev] - En desarrollo (Rama dev)

### 🏗️ Arquitectura Modular (Flask Blueprints)
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
