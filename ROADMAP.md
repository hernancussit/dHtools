# 🗺️ Mapa de Ruta y Futuras Funcionalidades (Roadmap)

Este documento centraliza la planificación de nuevas características, mejoras y ampliaciones del proyecto **dHtools**, organizado por versiones e hitos de desarrollo.

---

## 🎯 Versión Actual: `v1.1.0` (Estable)
- [x] **Motor en Cascada Inteligente:** Integración de **yt-dlp**, **Cobalt v11** y motor musical especializado (**Deezer / Spotify**) con conmutación por error transparente (*fallback*).
- [x] **Suite de Audio Hi-Fi:** Extracción directa con carátulas en alta resolución y metadatos ID3 automáticos en calidades `128 kbps`, `192 kbps`, `256 kbps` y `320 kbps (CBR MP3)`.
- [x] **Playlists y Colecciones:** Agrupación automática en carpetas virtuales, descarga individual o empaquetado directo en `.zip`.
- [x] **Seguridad & Blindaje:** Protección contra fuerza bruta con tarpit, validación estricta de URLs contra RCE y resolución de rutas segura contra *Path Traversal*.
- [x] **Evasión Antibot Automática:** Integración de `pot-provider` (PoTokens) y runtime `Deno` para resolución de desafíos JavaScript sin requerir inicio de sesión obligatorio.
- [x] **Panel de Administración Web:** Gestión de usuarios con roles (`admin` / `downloader`), actualización de motores en 1 clic, selector de canales (`main` vs `dev`) y rollback instantáneo.
- [x] **Sincronización en la Nube (Cloud Sync):** Exportación automática a Nextcloud (WebDAV), FTP, Telegram Bot y Webhooks HTTP.
- [x] **Gestor Seguro de Cookies:** Carga y validación previa obligatoria de `cookies.txt` en formato Netscape para videos restringidos (+18 / miembros).
- [x] **Configuraciones de Proxy Universales:** Plantillas listas para Nginx, HestiaCP, cPanel/Apache y Caddy en `proxy-configs/`.

---

## 🚀 Próximo Hito: `v1.2.0` (En Planificación)
- [ ] **Aceleración por Hardware (GPU Encoding):**
  - Soporte opcional para codificación acelerada por hardware mediante NVIDIA NVENC, Intel QuickSync y VAAPI en Docker para acelerar uniones de video 4K y conversiones de formato.
- [ ] **Descargas Programadas (Cron / Time Scheduler):**
  - Posibilidad de programar descargas pesadas en horarios de menor consumo de red (ej. de madrugada).
- [ ] **Notificaciones Web Push Nativas:**
  - Envío de notificaciones directas al navegador / PWA cuando una descarga o lote extenso finalice en segundo plano.
- [ ] **Límite de Ancho de Banda Configurable:**
  - Opción para restringir la velocidad máxima de descarga de `yt-dlp` desde el Panel de Administración para no saturar conexiones domésticas o VPS compartidos.

---

## 🔮 Futuras Ampliaciones (`v1.3.0+`)
- [ ] **Buscador Multimedia Integrado:**
  - Buscador directo en la interfaz para encontrar canciones y videos sin necesidad de copiar y pegar enlaces externos.
- [ ] **Reproductor Web Integrado:**
  - Vista previa y reproducción directa de audio y video desde la sección "Mis Descargas" antes de bajar el archivo a la PC.
- [ ] **Soporte para Plugins Comunitarios:**
  - Arquitectura modular para permitir a la comunidad añadir extractores o destinos de sincronización en la nube personalizados.

---

## 💬 Sugerencias y Nuevas Ideas
Si deseas proponer una nueva funcionalidad, abre una solicitud estructurada en la pestaña de [Issues](https://github.com/hernancussit/dHtools/issues/new?template=feature_request.md).
