# 🗺️ Mapa de Ruta y Futuras Funcionalidades (Roadmap)

Este documento centraliza la planificación de nuevas características, mejoras y ampliaciones del proyecto **dHtools**, organizado por versiones e hitos de desarrollo.

---

## 🎯 Versión Estable Actual: `v1.5.0`
- [x] **🎨 Identidad de Marca Oficial & Rediseño de Experiencia de Usuario:**
  - **Suite Completa de Marca (`static/icons/`):** Logotipo oficial cyberpunk `dH`, banner horizontal `brand_horizontal.png` de alta definición con tipografía cian de alto contraste, favicons multicapa y PWA manifest.
  - **Página "Acerca de" (`/about` & `/acerca-de`):** Integración con [Cafecito.app](https://cafecito.app/henu_45) (botón interactivo y QR dinámico), créditos de autor (Hernán Cussit / Servicios Informáticos LT) y tarjeta modular desacoplada del Bot de Telegram.
  - **Navegación Móvil Ergonómica:** Barra de navegación inferior permanente (`Bottom Nav Bar`), menú lateral deslizable (*Drawer*) y topbar táctil con contador de cola.
  - **Doble Consola Interactiva:** Terminal de actividad en tiempo real visible tanto en **Modo Fácil** como en **Modo Avanzado**.
- [x] **⚡ Optimización y Fortalecimiento del Motor Cobalt v11:**
  - **Sincronización Automática de Cookies:** Transformación instantánea de `cookies.txt` (Netscape) a `cobalt_cookies.json` con volumen montado `rw`, mitigando bloqueos `error.api.youtube.login`.
  - **Enrutamiento Inteligente por Plataforma:** Prioridad inmediata a Cobalt para redes sociales (TikTok, Instagram, Twitter/X, Reddit, SoundCloud, etc.) y derivación directa a `yt-dlp` (con PO Token Provider y Deno) para YouTube.
  - **Payload Enriquecido:** Contenedores (`mp4`, `webm`, `mkv`), audio hi-fi (`mp3`, `ogg`, `wav`, `opus`), `tiktokFullAudio` y resolución automática de respuestas `picker` multi-ítem.
- [x] **☁️ Conectores Cloud Universales & Modo Offload:**
  - **Soporte S3 Universal:** Compatibilidad nativa con AWS S3, MinIO, Cloudflare R2, Backblaze B2 y Wasabi mediante streaming multipart (`TransferConfig`).
  - **Modo Offload ("Subir y Mover"):** Liberación inmediata de espacio en disco del VPS tras subida exitosa con protección estricta contra pérdidas y persistencia en `downloads_meta.json`.
  - **Presets Privados por Usuario:** Aislamiento total de credenciales WebDAV, FTP y S3 con test de conexión en 1 clic.
- [x] **🤖 Asistente Autónomo de Telegram:**
  - **Aislamiento Estricto por Usuario:** Cada usuario accede exclusivamente a sus propias descargas en `/descargas`.
  - **Reconocimiento de Lenguaje Natural:** Consultas conversacionales de descargas, estado de cola y cuotas.
- [x] **📚 Wiki Técnica & Troubleshooting Empírico:**
  - **Sección 11:** Túnel Universal & Proxies Residenciales (SOCKS5 / MikroTik RouterOS) con telemetría RTT.
  - **Sección 12:** Guía de mitigación antibot, Netscape cookies sin invalidación, SABR bypass y límites de 50 MB en Telegram.
  - **Acceso Público:** Libre visualización de `/wiki` y `/about` sin login forzado.

---

## 🎯 Versión `v1.6.0` — Taller Multimedia & Conectores Cloud Directos

### 🎬 Taller Multimedia, Conversor de Formatos & Edición (Media Studio)
- [x] **Conversor Universal de Formatos (Video & Audio):**
  - **Video:** `MP4` (H.264 / AAC), `MKV`, `WebM` (VP9 / Opus), `AVI` y generación de **GIFs animados** de alta calidad a partir de fragmentos de video.
  - **Audio:** `MP3` (320/256/192/128 kbps CBR), `FLAC` (Hi-Res sin pérdida), `WAV` (PCM), `AAC`, `M4A`, `Opus` y `OGG Vorbis`.
- [x] **Compresor Inteligente para Redes Sociales:**
  - Perfiles predefinidos de reducción de peso con optimización automática para compartir por **WhatsApp Estándar** (< 16 MB), **WhatsApp HD** (1080p < 25 MB) y **Discord / Telegram** (< 25 MB).
- [x] **Editor y Recortador Visual Integrado:**
  - [x] **Recorte Temporal Milimétrico:** Recorte de inicio y fin (`start_time` / `end_time`) directo sin recompresión innecesaria (`-c copy`).
  - [x] **Extractor de Pistas:** Extracción directa de la pista de audio (MP3 320 kbps) a partir de cualquier archivo de video.
  - [x] **Línea de Tiempo Interactiva (*Timeline Scrubber*):** Reproductor visual HTML5 integrado con barra de rango interactiva, posicionador playhead, botones de marcado rápido (`[ Fijar Inicio`, `Fijar Fin ]`), prueba de selección (`▶️ Probar`) y reset en 1 clic.
  - [x] **Unión de Archivos (Merge / Concatenación):** Herramienta dedicada para seleccionar dos o más archivos de audio o video, reordenarlos en cola con botones ⬆️ / ⬇️ / ✕ y fusionarlos en un archivo único continuo vía FFmpeg Concat.
- [x] **Normalizador de Potencia Acústica (EBU R128):**
  - Nivelación automática de sonoridad a **-14 LUFS** (estándar EBU R128 / ITU-R BS.1770) con filtro acústico `loudnorm` para eliminar desniveles de volumen sin saturación ni clipping.

### ☁️ Integración Directa con Proveedores Cloud Principales
- [x] **Google Drive [EXPERIMENTAL]:** Implementado como **Plugin Oficial Bundled** (`plugins/google_drive/`) con soporte para Service Account, OAuth2, streaming resumable por bloques de 10 MB (RAM-Safe), selector de carpetas y modo Safe Offload.
- [ ] **Modularización de Conectores Cloud (v1.6.0+):** Extracción planificada de los conectores S3, WebDAV y FTP hacia plugins oficiales independientes (`plugins/s3_storage`, `plugins/webdav_storage`, etc.) una vez estabilizado el ecosistema del Plugin Manager.
- [x] **Microsoft OneDrive / SharePoint:** Implementado como **Plugin Oficial Bundled** (`plugins/onedrive/`) con soporte para cuentas personales y M365/SharePoint mediante Microsoft Graph API, streaming resumable por fragmentos (RAM-Safe), selector de carpetas y modo Safe Offload.
- [x] **Dropbox:** Implementado como **Plugin Oficial Bundled** (`plugins/dropbox/`) con soporte para API v2 oficial, sesiones de subida por bloques (`upload_session`, RAM-Safe), enlaces compartidos automáticos, selector de carpetas y modo Safe Offload.


---

## 🎯 Versión `v2.0.0` — Experiencia de Usuario, Búsqueda, Scheduler & Aceleración GPU
- [x] **Buscador Multimedia Integrado:**
  - Búsqueda directa de videos y canciones dentro de la interfaz sin necesidad de abrir plataformas externas para copiar enlaces.
  - Multiplataforma: soporte nativo simultáneo para YouTube (`ytsearch`), Deezer (API oficial con previews de audio de 30s en alta calidad) y SoundCloud (`scsearch`).
  - Filtros por plataforma (`all`, `youtube`, `deezer`, `soundcloud`) e intercalado balanceado de resultados.
  - Descargas directas en 1 clic (Video MP4 / Audio MP3) o precarga directa en Modo Avanzado.
  - Modal y reproductor interactivo de previsualización multimedia: inspección de videos (YouTube) y canciones (Deezer/SoundCloud) antes de descargar, con soporte para adelantar/retroceder temporalmente (scrubber continuo + botones ±5s), pantalla completa y descarga directa desde el propio visor.
- [x] **Reproductor Web Integrado con Cola de Reproducción:**
  - Reproductor nativo persistente para audio y video directamente desde la sección "Mis Archivos" (Mis Descargas) y Estudio Multimedia.
  - Barra flotante cyberpunk de reproducción continua (mini-player) acoplada dinámicamente en desktop y sobre la barra de navegación móvil.
  - Ecualizador visual interactivo animado, scrubber de línea de tiempo milimétrico y control de volumen con persistencia en `localStorage`.
  - Ventana modal y visor desacoplado para reproducción de video con soporte de Picture-in-Picture (PiP) y pantalla completa.
  - Cajón deslizable de cola de reproducción (*Queue Drawer*) con reordenamiento de pistas (⬆️ / ⬇️), eliminación individual, mezcla aleatoria (`🔀 Mezclar`) y vaciado en 1 clic.
  - Reproducción continua por lotes: botón `▶️ Reproducir Todo` en colecciones/carpetas para encolar playlists completas.
  - Integración con la API MediaSession del navegador para control desde pantalla de bloqueo y teclas multimedia del teclado/sistema operativo.
- [ ] **Descargas Programadas (Task Scheduler / Cron):**
  - Programación de descargas masivas o playlists extensas en horarios de bajo consumo de red (despriorizado según preferencias).
- [x] **Notificaciones Web Push Nativas (PWA / Service Worker):**
  - Alertas automáticas en navegador y dispositivos móviles cuando finalizan descargas individuales, lotes masivos, listas de reproducción o trabajos del Estudio Multimedia.
  - Centro de control de notificaciones en la pestaña **Ajustes**: indicador de estado de permisos en tiempo real, activación en 1 clic, botón de prueba instantánea y preferencias granulares (descargas, estudio, solo en segundo plano, alertas sonoras).
  - Integración nativa con Service Worker (`static/sw.js`) con soporte de clics directos para enfocar la pestaña activa o navegar a la sección relevante.
- [ ] **Aceleración por Hardware (GPU Encoding):**
  - Soporte opcional para codificación por GPU (NVIDIA NVENC, Intel QuickSync y VAAPI) dentro de Docker.

---

## 💬 Sugerencias y Nuevas Ideas
Si deseas proponer una nueva funcionalidad, abre una solicitud estructurada en la pestaña de [Issues](https://github.com/hernancussit/dHtools/issues/new?template=feature_request.md).
