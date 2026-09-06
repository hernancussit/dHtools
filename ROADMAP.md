# 🗺️ Mapa de Ruta y Futuras Funcionalidades (Roadmap)

Este documento centraliza la planificación de nuevas características, mejoras y ampliaciones del proyecto **dHtools**, organizado por versiones e hitos de desarrollo.

---

## 🎯 Versión Estable Actual: `v1.4.0`
- [x] **🛡️ Respaldo Residencial de Último Recurso (Tier 4 / Residential Failsafe):**
  - **Cascada Inteligente de 4 Niveles:** Activación automática del proxy SOCKS5 residencial ante bloqueos `UNPLAYABLE` o degradación forzada a 360p en YouTube.
  - **Protección de Red Residencial:** Más del 90% del tráfico y descargas pesadas permanecen en el VPS; el nodo residencial sólo interviene en caso de contingencia.
  - **Telemetría RTT en Tiempo Real:** Medición de latencia de ping TCP directa en milisegundos y botón de prueba end-to-end desde el panel Admin.
- [x] **🤖 Asistente de Telegram: Entrega Robusta y Envío Web Bajo Demanda:**
  - **Corrección de Entrega al 100%:** Trazabilidad estricta de `job_id` y fallback transparente a `sendDocument` ante cualquier incompatibilidad de códec.
  - **Privacidad de Descargas Web:** Supresión del envío automático de descargas web al chat de administración.
  - **Botón "✈️ Telegram" en la Web:** Envío en 1 clic de cualquier archivo desde "Mis Descargas" con control de tamaño y notificación de cuota.
- [x] **🤖 Asistente Interactivo Bidireccional de Telegram (Telegram Bot Hub & Remote Assistant):**
  - **Solicitud de Nuevas Descargas desde el Chat:** Envío directo de cualquier enlace compatible con botones en línea táctiles (*Inline Keyboards*) para elegir resoluciones (`1080p`, `720p`, `480p`) o calidades de audio (`MP3 320k`, `FLAC`).
  - **Monitoreo Dinámico de Progreso:** Mensajes editados en vivo con porcentaje, velocidad y barra de progreso.
  - **Entrega Inteligente:** Archivos multimedia directos en el chat (hasta 50 MB) o botones con enlace web seguro.
  - **Vinculación Segura (Telegram Connect):** Tokens temporales de un solo uso desde el perfil web con aislamiento de usuario y control de cuotas.
  - **Comandos Interactivos:** `/descargas`, `/cola`, `/cuota`, `/ayuda`, `/desvincular`.
- [x] **☁️ Hub de Conectores Cloud con Presets Privados:**
  - Perfiles de almacenamiento personalizados por usuario (Nextcloud/ownCloud vía **WebDAV**, servidores **FTP** y webhooks) con aislamiento total de credenciales.
  - Herramienta de prueba de conexión en 1 clic para validar accesos antes de guardar.
- [x] **🛡️ Blindaje de Seguridad & Privacidad:**
  - Ofuscación de campos sensibles en el panel administrativo (`type="password"` en Tokens de Telegram, Chat IDs, contraseñas WebDAV y FTP).
  - Visibilidad condicional inteligente de botones en la interfaz de usuario.
- [x] **⚡ Evasión de Restricciones SABR de YouTube (Full HD 1080p Restablecido):**
  - Cascada multi-cliente combinada (`web_music`, `web`, `mweb`, `web_embedded`) que elude el bloqueo de streams forzados SABR en YouTube.
  - Puente nativo con **Deno** para resolución de desafíos JavaScript (JS challenges).
  - Estabilización del microservicio `pot-provider` (Proof-of-Origin Token) en Docker Compose v2 garantizando disponibilidad continua del puerto 4416.
- [x] **🏷️ Versionado Consciente de Rama (`-main` / `-dev`):**
  - Detección e inyección unificada de la rama activa de Git en el panel principal (`index.html`), panel administrativo (`admin.html`) y la wiki técnica (`wiki.html`).

---

## 🎯 Versión `v1.5.0` — Fortalecimiento de Motores, Conectores Cloud Avanzados & Taller Multimedia

### 🚀 Optimización y Fortalecimiento del Motor Cobalt (`cobalt-api`)
- [x] **Sincronización Automática de Cookies para Cobalt (`COOKIE_PATH`):**
  - Conversión automatizada del archivo `cookies.txt` (formato Netscape subido al panel Admin) a `cobalt_cookies.json` montado en el contenedor `cobalt-api`, eliminando el bloqueo `error.api.youtube.login` en IPs de datacenter.
- [x] **Enrutamiento Inteligente Especializado por Plataforma:**
  - Derivación prioritaria inmediata a **Cobalt** para redes sociales (**TikTok, Instagram Reels, Twitter/X, Reddit, Pinterest, SoundCloud, Vimeo, Facebook, Bilibili**), obteniendo descargas ultra-rápidas directas desde CDN.
  - Derivación optimizada a **yt-dlp** para **YouTube** aprovechando la suite de PO Tokens, Deno y clientes especializados (`web_music`), evitando reintentos fallidos en Cobalt si no hay cookies autenticadas.
- [x] **Payload Enriquecido y Manejo de Formatos en Cobalt:**
  - Soporte de selección de contenedor (`mp4`, `webm`, `mkv`), formatos de audio (`mp3`, `ogg`, `wav`, `opus`), extracción de audio completo en TikTok (`tiktokFullAudio`) y resolución de selectores de elementos múltiples (`picker`).
- [ ] **Soporte de Proxy Residencial / HTTP Proxy en Cobalt (`HTTP_PROXY`):**
  - Variable de entorno configurable en Docker y panel Admin para enrutar las consultas de Cobalt a través de un proxy residencial o nodo túnel hogareño (Tailscale/WireGuard), eludiendo verificaciones antibot de forma transparente.
- [ ] **Generador de Sesiones YouTube (`YOUTUBE_SESSION_SERVER`):**
  - Evaluación y despliegue del generador de sesiones de BotGuard para Cobalt v11, posibilitando descargas sin necesidad de asociar cuentas personales de Google.

### ☁️ Conectores Cloud Principales & Offload
- [x] **Conector Universal de Almacenamiento S3 (AWS S3, MinIO, Cloudflare R2, Backblaze B2, Wasabi):**
  - Módulo modular desacoplado (`core/cloud_sync.py`) con soporte nativo de streaming multipart (`TransferConfig`) para archivos masivos (>5 GB) sin saturar memoria RAM.
  - Verificación en vivo (`head_bucket`) desde el panel Admin y Presets Privados de usuario con diagnóstico amigable de permisos y credenciales.
- [x] **Modo de Sincronización "Subir y Mover" (Offload):**
  - Opción para subir el archivo terminado a la nube y eliminarlo del disco del VPS inmediatamente, reduciendo el consumo de almacenamiento en servidores pequeños.
  - Protección de borrado condicional estricto: el archivo local solo se remueve si la transferencia cloud fue 100% exitosa; si falla, se preserva y se alerta en el registro.
  - Persistencia de metadatos en `downloads_meta.json` e indicador visual `☁️ En la nube` en el historial de descargas.
- [ ] **Integración Directa con Proveedores Cloud Principales (OAuth2):**
  - **Google Drive:** Autenticación OAuth2 / Service Account con soporte para carpetas específicas y Unidades Compartidas (*Shared Drives*).
  - **Microsoft OneDrive / SharePoint:** Conexión con cuentas personales de Microsoft y cuentas educativas / corporativas de Microsoft 365.
  - **Dropbox:** Conexión vía API oficial para subida automática de archivos y creación de carpetas de colección.

### 🎬 Taller Multimedia, Conversor de Formatos & Edición (Media Studio)
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
