# 🗺️ Mapa de Ruta y Futuras Funcionalidades (Roadmap)

Este documento centraliza la planificación de nuevas características, mejoras y ampliaciones del proyecto, organizado por versiones e hitos.

---

## 🎯 Estado Actual: `v1.0.0` (Lanzamiento Estable)
- [x] Doble motor de extracción (**yt-dlp** + **Cobalt v11**).
- [x] Proveedor de PO Token unificado (`potprovider` / `bgutil`).
- [x] Motor JavaScript **Deno** integrado en contenedor Docker.
- [x] Descarga de playlists completas en formato `.zip` con barra de progreso detallada.
- [x] Recorte de video por tiempo de inicio y fin (*trimming*).
- [x] Extracción de audio en múltiples bitrates MP3 (128, 192, 256, 320 kbps).
- [x] Protección de acceso por HTTP Basic Auth y políticas anti-indexación (`X-Robots-Tag`).
- [x] Plantillas de proxy inverso para HestiaCP con soporte SSL Let's Encrypt.
- [x] Limpieza automática programada de archivos descargados.
- [x] Control de versiones (`CHANGELOG.md`) e insignia `v1.0.0` en la interfaz.

---

## 🚀 Próximas Versiones Planificadas

### 📌 Versión 1.1.0 — Gestión de Disco, Limpieza de Emergencia y Nuevas Redes
- [ ] **Limpieza de Descargas a Demanda y Protección de Espacio en Disco:**
  - **Botón "Limpiar descargas ahora":** Permite al administrador forzar el borrado inmediato de archivos finalizados o temporales huérfanos.
  - **Limpieza de emergencia automática:** Monitoreo del almacenamiento del VPS (si el disco supera el 85% de uso o queda menos de 2 GB disponibles, se purgan automáticamente las descargas más antiguas).
- [ ] **Soporte de Plataformas de Video y Redes Sociales:**
  - **YouTube Shorts:** Detección automática y descarga optimizada en formato vertical.
  - **Instagram:** Descarga de Reels y publicaciones de video.
  - **Facebook:** Descarga de videos públicos y Reels.
  - **Twitch & Kick:** Soporte para clips y transmisiones grabadas (VODs).
- [ ] **Historial Reciente de Descargas:**
  - Lista desplegable de archivos listos para descargar sin reprocesar mientras no hayan expirado.

---

### 📌 Versión 1.2.0 — Plataformas de Música (Deezer & Spotify)
- [ ] **Integración de Deezer:**
  - Descarga de canciones, álbumes y playlists.
  - **Soporte ARL:** Configuración de token ARL para descargas en calidad alta (320 kbps MP3 / FLAC sin pérdida).
  - Modo alternativo sin ARL (calidad estándar 128 kbps).
  - Incrustación automática de metadatos completos y carátula en alta resolución.
- [ ] **Integración de Spotify:**
  - Reconocimiento de URLs de canciones, álbumes y playlists de Spotify.
  - Emparejamiento de audio y descarga directa con metadatos y portada original.

---

### 📌 Versión 1.3.0 — Panel de Administración y Actualización de Motores
- [ ] **Panel de Control para Administrador (`/admin`):**
  - Acceso restringido para gestión del servidor y diagnóstico.
  - **Actualizador de Motores:**
    - Botón para actualizar `yt-dlp` a la última versión.
    - Botón para actualizar/recargar la imagen de `Cobalt`.
    - Indicadores de salud de `potprovider`, `Cobalt` y espacio libre en disco.
- [ ] **Panel de Configuración Dinámica (Settings UI):**
  - Modificar tiempos de retención de descargas y umbrales de disco sin tocar `.env` por terminal.
  - Cargar o renovar cookies de YouTube (`cookies.txt`) y ARL de Deezer directamente desde la web.

---

### 📌 Versión 1.4.0 — Personalización y Experiencia Visual
- [ ] **Customización de la Interfaz:**
  - Selector de temas visuales (Dark Mode moderno, OLED Black, Light Mode, Cyberpunk).
  - Posibilidad de personalizar el título del sitio, logotipo y colores de acento desde el panel de administración.
- [ ] **Subtítulos y Formatos Avanzados:**
  - Selector de formatos adicionales de video (MKV, WebM, MP4) y audio (FLAC, M4A, Opus, WAV).
  - Opción para incrustar o descargar subtítulos en formato `.srt` / `.vtt`.

---

### 📌 Versión 2.0.0 — Multi-Usuario, Cola de Descargas y Cloud Sync
- [ ] **Sistema Multi-Usuario con Roles:**
  - Usuarios individuales con contraseña propia (Admin / Usuario estándar).
  - Límites de cuota por usuario.
- [ ] **Cola de Descargas Simultáneas:**
  - Posibilidad de pegar múltiples enlaces a la vez y ver el progreso en paralelo.
- [ ] **Sincronización en la Nube:**
  - Enviar descargas directamente a Google Drive, Nextcloud, Dropbox o FTP sin pasar por el dispositivo local.
