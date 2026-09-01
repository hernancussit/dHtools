# Registro de Cambios (Changelog)

Todos los cambios notables en este proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

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
- **Automatización y Mantenimiento:**
  - Limpieza automática periódica de descargas expiradas en `downloads/`.
  - Botón de actualización de `yt-dlp` a demanda en la interfaz y actualización automática en segundo plano.
- **Infraestructura y Producción:**
  - Plantillas de Nginx optimizadas para **HestiaCP** con soporte SSL de Let's Encrypt (`hestiacp-templates/`).
  - Despliegue empaquetado con Docker Compose.
