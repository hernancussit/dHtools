# 🗺️ Mapa de Ruta y Futuras Funcionalidades (Roadmap)

Este documento centraliza la planificación de nuevas características, mejoras y ampliaciones del proyecto, organizado por versiones e hitos de desarrollo.

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

## 🎯 Versión `v1.1.0` (Completado)
- [x] **Limpieza de Descargas a Demanda y Protección de Espacio en Disco:**
  - [x] **Botón "Limpiar":** Forzar el borrado inmediato de archivos finalizados o huérfanos.
  - [x] **Monitoreo de disco:** Widget visual en la interfaz con porcentaje y espacio libre real del VPS.
  - [x] **Limpieza de emergencia automática:** Purga automática en segundo plano si el disco supera el 85% o quedan <2 GB.
- [x] **Soporte de Plataformas de Video y Redes Sociales:**
  - [x] **YouTube Shorts:** Detección automática y descarga optimizada.
  - [x] **Instagram, Facebook, Twitch, Kick, TikTok, X:** Reconocimiento de URLs e insignia en preview.
- [x] **Historial Reciente de Descargas:**
  - [x] Panel desplegable para re-descargar archivos generados en el servidor sin reprocesar.


---

## 🎯 Versión `v1.2.0` (Completado)
- [x] **Integración de Deezer:**
  - [x] Descarga de canciones, álbumes y playlists con metadatos.
  - [x] **Campo ARL en la interfaz con persistencia en localStorage:** Para descargas en máxima calidad (FLAC / 320 kbps).
  - [x] **Fallback automático inteligente:** Descarga sin ARL garantizada ante token inválido o no ingresado.
- [x] **Integración de Spotify:**
  - [x] Reconocimiento de URLs de canciones de Spotify y extracción de metadatos.
  - [x] Emparejamiento de audio y descarga en MP3.
- [x] **Incrustación de ID3 y Carátulas:**
  - [x] Portada en alta resolución incrustada y metadatos ID3 completos (Título, Artista, Álbum).


---

### 📌 Versión 1.3.0 — Panel de Control y Configuración Web Integral (`/admin`)
*Panel centralizado con interfaz visual para administrar todos los componentes del sistema sin tocar la terminal:*

- [ ] **Centro de Motores, APIs y Servicios:**
  - **Monitoreo de Componentes:** Diagnóstico en vivo de los microservicios (`yt-downloader`, `pot-provider`, `cobalt-api`, motor Deno y FFmpeg).
  - **Actualizador de Motores:** Botones de 1 clic para actualizar `yt-dlp` a la última versión o refrescar la imagen de `Cobalt`.
  - **Gestor de APIs y Credenciales:** Interfaz para cargar, validar y renovar tokens (ARL de Deezer, Spotify API credentials, `cookies.txt` de YouTube).
- [ ] **Gestión de Usuarios (Administración Manual):**
  - Creación, edición, cambio de contraseñas y desactivación de usuarios autorizados desde la web.
  - Roles de usuario: `Administrador` (acceso a configuración y herramientas) vs `Descargador` (solo interfaz de descargas).
  - *Arquitectura lista para admitir registro público o sistema de invitaciones en versiones futuras.*
- [ ] **Gestión Dinámica de Parámetros:**
  - Configuración de retención de descargas (`CLEANUP_AFTER_HOURS`), umbrales de alerta de disco y motor predeterminado.
  - Visor de logs y diagnósticos del sistema en tiempo real.

---

### 📌 Versión 1.4.0 — Personalización y Experiencia Visual
- [ ] **Customización de la Interfaz:**
  - Selector de temas visuales (Dark Mode moderno, OLED Black, Light Mode, Cyberpunk).
  - Posibilidad de personalizar el título del sitio, logotipo y colores de acento desde el panel de administración.
- [ ] **Subtítulos y Formatos Avanzados:**
  - Selector de formatos adicionales de video (MKV, WebM, MP4) y audio (FLAC, M4A, Opus, WAV).
  - Opción para incrustar o descargar subtítulos en formato `.srt` / `.vtt`.

---

### 📌 Versión 2.0.0 — Cola de Descargas y Cloud Sync
- [ ] **Cola de Descargas Simultáneas:**
  - Posibilidad de pegar múltiples enlaces a la vez y ver el progreso en paralelo.
- [ ] **Sincronización en la Nube:**
  - Enviar descargas directamente a Google Drive, Nextcloud, Dropbox o FTP sin pasar por el dispositivo local.
- [ ] **Sistema de Registro Abierto / Invitaciones (Opcional):**
  - Registro de usuarios con confirmación o invitaciones privadas con cuotas de descarga.
