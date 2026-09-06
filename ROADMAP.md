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

### ☁️ Integración Directa con Proveedores Cloud Principales (OAuth2)
- [ ] **Google Drive:** Autenticación OAuth2 / Service Account con soporte para carpetas específicas y Unidades Compartidas (*Shared Drives*).
- [ ] **Microsoft OneDrive / SharePoint:** Conexión con cuentas personales de Microsoft y cuentas educativas / corporativas de Microsoft 365.
- [ ] **Dropbox:** Conexión vía API oficial para subida automática de archivos y creación de carpetas de colección.

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
