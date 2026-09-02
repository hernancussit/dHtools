# 🗺️ Mapa de Ruta y Futuras Funcionalidades (Roadmap)

Este documento centraliza la planificación de nuevas características, mejoras y ampliaciones del proyecto **dHtools**, organizado por versiones e hitos de desarrollo.

---

## 🎯 Versión Estable Actual: `v1.1.1`
- [x] **Parche Crítico de Seguridad (v1.1.1):** Hashing de contraseñas con PBKDF2-SHA256, retiro del volumen SSH de Docker, protección contra *open redirect* y aislamiento de descargas por usuario.
- [x] **Motor en Cascada Inteligente:** Integración de **yt-dlp**, **Cobalt v11** y motor musical especializado (**Deezer / Spotify**) con conmutación por error transparente (*fallback*).
- [x] **Suite de Audio Hi-Fi:** Extracción directa con carátulas en alta resolución y metadatos ID3 automáticos en calidades `128 kbps`, `192 kbps`, `256 kbps` y `320 kbps (CBR MP3)`.
- [x] **Playlists y Colecciones:** Agrupación automática en carpetas virtuales, descarga individual o empaquetado directo en `.zip`.
- [x] **Evasión Antibot Automática:** Integración de `pot-provider` (PoTokens) y runtime `Deno` para resolución de desafíos JavaScript sin requerir inicio de sesión obligatorio.
- [x] **Panel de Administración Web:** Gestión de usuarios con roles (`admin` / `downloader`), actualización de motores en 1 clic, selector de canales (`main` vs `dev`) y rollback instantáneo.
- [x] **Gestor Seguro de Cookies:** Carga y validación previa obligatoria de `cookies.txt` en formato Netscape para videos restringidos (+18 / miembros).
- [x] **Configuraciones de Proxy Universales:** Plantillas listas para Nginx, HestiaCP, cPanel/Apache y Caddy en `proxy-configs/`.

---

## 🎯 Versión `v1.2.0` (En desarrollo activo en rama `dev`)
- [x] **Arquitectura Modular (Flask Blueprints):** Monolito desacoplado al 100% en módulos independientes (`core/` y `routes/`).
- [x] **Workers en Segundo Plano (Gunicorn WSGI):** Inicialización de hilos concurrentes compatible con servidores de producción.
- [x] **Homogeneización de Motores:** Badges `● Online` con indicador de latencia en milisegundos en tiempo real y auto-actualizador de Deno JS.
- [x] **Unificación de Descargas en Lote:** Conmutador interactivo `[ 🔗 Enlace Único | 📋 Descarga en Lote ]` integrado en Modo Fácil y Modo Avanzado con todas las resoluciones y formatos.
- [x] 🚨 **Optimización Integral de Navegabilidad y Layout Móvil (Smartphones / WebApp):**
  - Auditoría y ajuste de diseño responsivo para celulares en todas las vistas (`index.html`, `admin.html`, `login.html`, `wiki.html`).
  - Navegación en celulares en cuadrícula compacta 2x2, cabecera de bajo perfil y eliminación de desplazamientos horizontales accidentales (`overflow-x: hidden`).
  - Tarjetas y paneles adaptados con padding ergonómico para pantallas estrechas (320px a 480px).
- [x] **Visualización Enriquecida en la Cola de Descargas:**
  - Priorización del título/nombre del video o canción en negrita en lugar de la URL sin procesar.
  - Subtítulo con URL secundaria pequeña y atenuada en pantallas de escritorio, ocultándose automáticamente en celulares (`.queue-url-sub`).
  - Propagación inmediata de metadatos de inspección desde el cliente a la API para mostrar el título desde el segundo cero.
- [x] **Favicon e Identidad de Pestaña:** Integración del favicon oficial (`favicon.svg` y `favicon.ico`) en todas las plantillas web (`index.html`, `admin.html`, `login.html`, `wiki.html`) y endpoint directo `/favicon.ico`.
- [x] **Descarga Estricta de Fragmentos Recortados (Trimming Optimization):**
  - Registro informativo en tiempo real (`format_seconds`) con aviso explícito al usuario en consola.
  - Descarga estricta por secciones temporales activas (`download_ranges` con forzado de keyframes y pre-seeking), evitando la transferencia innecesaria de archivos completos.
- [x] **Sistema de Cuentas con Correo Electrónico & Servidor SMTP:**
  - Soporte de servidor SMTP configurable en el panel de administración (TLS/SSL) con prueba de envío en vivo (`/api/admin/smtp-test`).
  - Registro y edición de direcciones de email por usuario en la administración (`users.json`).
- [x] **Recuperación Segura de Contraseñas:**
  - Tokens temporales de un solo uso de 1 hora de duración para recuperación de accesos.
  - Flujo completo con modal "¿Olvidaste tu contraseña?" y formulario de cambio de clave con token (`/api/auth/reset-password`).
- [x] **Autenticación de Dos Factores (2FA / TOTP Opcional):**
  - Motor criptográfico puro en Python bajo el estándar RFC 6238 compatible con Google Authenticator, Microsoft Authenticator, Authy, Aegis, Bitwarden, etc.
  - Asistente de configuración con clave Base32, URL `otpauth://`, código QR dinámico y 8 códigos de respaldo (*backup recovery codes*).
  - Flujo de inicio de sesión en dos pasos y panel de gestión para activar o desactivar 2FA en cualquier momento.
- [x] **Control de Cuotas de Almacenamiento & Auditoría de Sesiones Activas:**
  - Asignación de cuotas de almacenamiento en disco por usuario (ej. 5 GB, 10 GB o ilimitada) con bloqueo preventivo y amigable al superar el límite.
  - Barra de progreso de cuota en vivo en el perfil del usuario.
  - Monitor de telemetría de sesiones web activas en tiempo real (IP, dispositivo, navegador, última actividad) con revocación remota instantánea desde la administración.

---

## 🎯 Versión `v1.3.0` — Conectores Cloud con Presets Privados por Usuario (Cloud Storage Hub)
- [ ] **Gestor de Presets de Nube Personales:**
  - Cada usuario podrá registrar y almacenar múltiples perfiles/presets de almacenamiento (ej. *"Mi Google Drive Personal"*, *"FTP de Trabajo"*, *"OneDrive Backup"*, *"Canal Telegram"*).
  - Selector rápido de destino en la interfaz de descargas para enviar archivos terminados al preset elegido con 1 clic.
- [ ] **Privacidad y Aislamiento Estricto de Credenciales:**
  - Aislamiento total de credenciales por usuario: ningún usuario podrá ver, editar ni utilizar los accesos a la nube configurados por otro.
  - Cifrado seguro de tokens OAuth2, contraseñas de FTP y claves de API en el servidor.
- [ ] **Herramienta de Prueba de Conexión en 1 Clic:**
  - Validación de conectividad y permisos de escritura en la nube antes de guardar cualquier preset.
- [ ] **Integración Directa con Proveedores Principales:**
  - **Google Drive:** Autenticación OAuth2 / Service Account con soporte para carpetas específicas y Unidades Compartidas (*Shared Drives*).
  - **Microsoft OneDrive / SharePoint:** Conexión con cuentas personales de Microsoft y cuentas educativas / corporativas de Microsoft 365.
  - **Dropbox:** Conexión vía API oficial para subida automática de archivos y creación de carpetas de colección.
  - **Amazon S3 / MinIO / Backblaze B2 / Cloudflare R2:** Conector universal para buckets compatibles con S3.
  - **Nextcloud / WebDAV & Servidores FTP:** Integración mejorada con compatibilidad para estructuras de carpetas anidadas.
  - **Telegram Bot Uploader:** Envío automático de archivos y colecciones como mensajes multimedia directos.
- [ ] **Modo de Sincronización "Subir y Mover" (Offload):**
  - Opción para subir el archivo terminado a la nube y eliminarlo del disco del VPS inmediatamente, reduciendo el consumo de almacenamiento en servidores pequeños.

---

## 🎯 Versión `v1.4.0` — Taller Multimedia, Conversor de Formatos & Edición (Media Studio)
- [ ] **Conversor Universal de Formatos (Video & Audio):**
  - **Video:** `MP4` (H.264 / H.265), `MKV`, `WebM` (VP9 / AV1), `AVI`, `MOV` y generación de **GIFs animados** a partir de fragmentos de video.
  - **Audio:** `MP3` (320/256/192/128 kbps CBR/VBR), `FLAC` (Hi-Res sin pérdida), `WAV`, `AAC`, `M4A`, `Opus` y `OGG`.
- [ ] **Compresor Inteligente para Redes Sociales:**
  - Perfiles predefinidos de reducción de peso con preservación visual de calidad (*CRF Rate Control*) para compartir archivos fácilmente por WhatsApp, Telegram o Discord (ej. "Comprimir a menos de 25 MB").
- [ ] **Editor y Recortador Visual Integrado:**
  - Línea de tiempo interactiva (*timeline*) para recortar inicios y finales de videos y canciones antes o después de la descarga.
  - **Extractor de Pistas:** Separar la pista de audio o extraer subtítulos de videos existentes sin recodificar.
  - **Unión de Archivos (Merge / Concatenación):** Combinar múltiples pistas o videos en un único archivo continuo.
- [ ] **Normalizador de Potencia Acústica (EBU R128):**
  - Nivelación automática de volumen para que todas las canciones de un álbum o lista suenen con la misma intensidad sonora sin saturación.

---

## 🎯 Versión `v2.0.0` — Experiencia de Usuario, Búsqueda, Scheduler & Aceleración GPU
- [ ] **Buscador Multimedia Integrado:**
  - Búsqueda directa de videos y canciones dentro de la interfaz sin necesidad de abrir plataformas externas para copiar enlaces.
- [ ] **Reproductor Web Integrado con Cola de Reproducción:**
  - Reproductor nativo de audio y video para previsualizar y reproducir archivos multimedia directamente desde la sección "Mis Descargas".
- [ ] **Descargas Programadas (Task Scheduler / Cron):**
  - Programación de descargas masivas o playlists extensas en horarios nocturnos de bajo consumo de red.
- [ ] **Notificaciones Web Push Nativas:**
  - Alertas automáticas en navegador y móviles cuando las tareas en segundo plano finalicen.
- [ ] **Aceleración por Hardware (GPU Encoding):**
  - Soporte opcional para codificación por GPU (NVIDIA NVENC, Intel QuickSync y VAAPI) dentro de Docker.

---

## 💬 Sugerencias y Nuevas Ideas
Si deseas proponer una nueva funcionalidad, abre una solicitud estructurada en la pestaña de [Issues](https://github.com/hernancussit/dHtools/issues/new?template=feature_request.md).
