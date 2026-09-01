# Registro de Cambios (Changelog)

Todos los cambios notables en este proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

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
