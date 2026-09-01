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

## 🎯 Versión `v1.3.0` (Completado)
*Panel centralizado con interfaz visual para administrar todos los componentes del sistema sin tocar la terminal:*

- [x] **Centro de Motores, APIs y Servicios:**
  - [x] **Monitoreo de Componentes:** Diagnóstico en vivo de los microservicios (`yt-downloader`, `pot-provider`, `cobalt-api`, motor Deno y FFmpeg).
  - [x] **Actualizador de Motores:** Botón para actualizar `yt-dlp` a la última versión con reinicio automático.
  - [x] **Gestor de Cookies:** Interfaz web para visualizar y cargar `cookies.txt` de YouTube sin SSH.
- [x] **Gestión de Usuarios (Administración Manual):**
  - [x] Creación, edición de contraseñas y eliminación de usuarios autorizados desde la web.
  - [x] Roles de usuario: `admin` (acceso a configuración y herramientas) vs `downloader` (solo interfaz de descargas).
- [x] **Gestión Dinámica de Parámetros:**
  - [x] Configuración de retención de descargas (`CLEANUP_AFTER_HOURS`), umbrales de alerta de disco y motor predeterminado persistidos en `config.json`.


---

## 🎯 Versión `v1.4.0` (Completado)
- [x] **Customización de la Interfaz:**
  - [x] Selector de temas visuales (Cyberpunk Midnight, OLED Black, Emerald Forest, Light Modern).
  - [x] Personalización del título del sitio, subtítulo y tema predeterminado desde `/admin`.
- [x] **Subtítulos y Formatos Avanzados:**
  - [x] Selector de formatos adicionales de video (`MP4`, `MKV`, `WebM`) y audio (`MP3`, `FLAC`, `M4A`, `Opus`, `WAV`).
  - [x] Opción para incrustar o descargar subtítulos en formato `.srt` / `.vtt`.


---

## 🎯 Versión `v2.0.0` (Completado)
- [x] **Cola de Descargas Simultáneas (Multi-Enlace / Batch Queue):**
  - [x] Interfaz de pegado múltiple de URLs con procesamiento concurrente en segundo plano.
  - [x] Panel de cola en tiempo real con monitoreo por elemento y empaquetador automático `.zip` (`GET /api/batch-download-zip/<batch_id>`).
- [x] **Sincronización en la Nube (Cloud Sync):**
  - [x] Módulo configurable para Nextcloud / WebDAV, FTP, Telegram Bot Uploader y Webhooks HTTP.
  - [x] Pestaña de administración web con formularios y pruebas de conectividad en vivo.

---

## 🎯 Versión `v2.1.0` (Completado)
- [x] **Rediseño Visual & Layout Amplio (2 Columnas):**
  - [x] Aprovechamiento total del ancho de pantalla con layout fluido responsivo.
- [x] **Soporte PWA (Progressive Web App):**
  - [x] `manifest.json`, Service Worker `sw.js` y botón de instalación rápida para móviles y PC.
- [x] **Privacidad Estricta de Descargas por Usuario:**
  - [x] Filtrado por propietario (`username`), eliminación personal de archivos y liberación de espacio.
- [x] **Controles Exclusivos para Administradores:**
  - [x] Ocultamiento de herramientas críticas para usuarios `downloader`.
- [x] **Verificador de Actualizaciones de Motores & Diagnóstico de Memoria RAM:**
  - [x] Comprobador en tiempo real contra PyPI y métricas de RAM en vivo.

---

## 🎯 Versión `v2.2.0` (Completado)
- [x] **Cierre de Sesión (Logout):**
  - [x] Botón "🚪 Salir" en la barra de navegación de todas las vistas con invalidación de credenciales HTTP Basic.
- [x] **Administración Avanzada de Usuarios en Panel `/admin`:**
  - [x] Formulario de registro y creación de nuevos usuarios con rol y estado.
  - [x] **Suspensión / Reactivación:** Pausar acceso de usuarios con bloqueo inmediato (`POST /api/admin/users/<username>/toggle-status`).
  - [x] **Limpieza de Descargas por Usuario:** Eliminación de archivos pertenecientes exclusivamente al usuario seleccionado (`POST /api/admin/users/<username>/clean-downloads`).
  - [x] Modificación de credenciales y borrado definitivo con purga de archivos.
- [x] **Mantenimiento y Actualizador de Cobalt Oficial:**
  - [x] Tarjeta de estado de Cobalt API con versión activa y plataformas soportadas.
  - [x] Comprobador de versiones contra GitHub Releases (`imputnet/cobalt`).
  - [x] Verificación de salud y actualización (`POST /api/admin/update-cobalt`).

---

## 🎯 Versión `v2.3.0` (Completado)
- [x] **Rediseño con Barra Lateral (Sidebar Dashboard):**
  - [x] Panel `/admin` rediseñado con navegación lateral fija y área de contenido fluida sin necesidad de scroll.
- [x] **Corrección de Columnas en Tablas:**
  - [x] Badges y estados con `white-space: nowrap` y puntos alineados sin quiebre de línea.
- [x] **Instalación PWA desde Pantalla de Acceso (`/login`):**
  - [x] Botón interactivo "📲 Instalar App" presente en el formulario de login.




