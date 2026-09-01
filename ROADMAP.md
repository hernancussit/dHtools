# 🗺️ Mapa de Ruta y Futuras Funcionalidades (Roadmap)

Este documento detalla las ideas, mejoras y nuevas funcionalidades planificadas para las próximas versiones del proyecto.

---

## 🎯 Estado Actual: `v1.0.0` (Completado)
- [x] Doble motor de extracción (`yt-dlp` + `Cobalt`).
- [x] Proveedor de PO Token unificado (`potprovider`).
- [x] Motor Deno integrado para resolver desafíos JS de YouTube.
- [x] Descarga de playlists completas en `.zip`.
- [x] Recorte de tramos de video (*trim* de inicio y fin).
- [x] Extracción de audio en múltiples calidades MP3.
- [x] Protección por Basic Auth y políticas anti-indexación.
- [x] Plantillas de proxy para HestiaCP + SSL Let's Encrypt.
- [x] Limpieza automática de archivos antiguos.

---

## 🚀 Próximas Versiones Planificadas

### 📌 Versión 1.1.0 — Experiencia de Usuario y Gestión de Formatos
- [ ] **Historial de Descargas Recientes:**
  - Panel colapsable que muestra las últimas descargas generadas en el servidor para volver a descargarlas sin reprocesar.
- [ ] **Soporte de Más Formatos de Audio y Video:**
  - Opciones de audio sin pérdida / alternativos: FLAC, M4A, AAC, Opus, WAV.
  - Opciones de contenedor de video: MKV, WebM y MP4 original.
- [ ] **Descarga de Subtítulos y Metadatos:**
  - Opción para descargar subtítulos en formato `.srt` / `.vtt` (manuales o autogenerados).
  - Incrustar carátula/miniatura y etiquetas ID3 en archivos de audio MP3.
- [ ] **Insignia de Versión en la Interfaz:**
  - Mostrar la versión actual de la aplicación en el footer con enlace al Changelog.

---

### 📌 Versión 1.2.0 — Descargas Avanzadas y Automatización
- [ ] **Cola de Descargas Simultáneas:**
  - Posibilidad de encolar múltiples enlaces a la vez y ver el progreso individual de cada uno.
- [ ] **Soporte Multi-Plataforma Ampliado:**
  - Habilitar descarga desde otras redes soportadas por yt-dlp y Cobalt (TikTok, Instagram Reels, Twitter/X, SoundCloud, Facebook Video, Twitch Clips).
- [ ] **Notificaciones de Descarga Finalizada:**
  - Notificaciones nativas del navegador (Web Notifications API).
  - Opción de webhook / bot de Telegram o Discord que avise cuando una descarga larga o playlist termine.

---

### 📌 Versión 1.3.0 — Integración en la Nube y Almacenamiento
- [ ] **Subida Directa a la Nube:**
  - Botón para enviar el archivo descargado directamente a **Google Drive**, **Nextcloud**, **Dropbox** o servidor **FTP / S3** sin tener que bajarlo a tu dispositivo local.
- [ ] **Marcador / Bookmarklet o Extensión de Navegador:**
  - Botón en la barra de marcadores del navegador que permita enviar el video actual de YouTube a tu sitio con 1 solo clic.

---

### 📌 Versión 2.0.0 — Multi-Usuario y API Externa
- [ ] **Panel de Administración y Cuentas de Usuario:**
  - Sistema de login con sesiones/tokens (JWT) en lugar de Basic Auth global.
  - Roles de usuario (Admin vs Usuario común) con cuotas de descarga o límites de almacenamiento.
- [ ] **API REST Pública / Privada:**
  - Endpoints con autenticación por `API Key` para integrar descargas desde scripts, bots o aplicaciones externas.
