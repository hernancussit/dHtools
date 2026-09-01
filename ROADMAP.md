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

---

## 🎯 Versión `v2.4.0` (Completado)
- [x] **Detección y Monitoreo en Vivo de Deno JS:**
  - [x] Corrección de lectura de estado y despliegue de versión en tiempo real (`v2.9.5`).
  - [x] Tarjeta dedicada para Deno JS Runtime en la pestaña de Motores.
- [x] **Herramienta de Diagnóstico Unitario Deno JS:**
  - [x] Endpoint `POST /api/admin/test-deno` y botón interactivo para probar compilación JS y diagnosticar algoritmos de YouTube.

---

## 🎯 Versión `v2.4.1` (Completado)
- [x] **Métricas de Memoria RAM Proyecto vs VPS:**
  - [x] Lectura de cgroups v2 (`/sys/fs/cgroup/memory.current`) para obtener los MB/GB exactos del proyecto.
  - [x] Barra de progreso segmentada de doble color en `/admin` con desglose de consumo del proyecto, resto del VPS y memoria libre.

---

## 🎯 Versión `v2.5.0` (Completado)
- [x] **Barra Lateral en Portal de Descargas (Sidebar Navigation):**
  - [x] Homologación del layout con barra lateral fija y pestañas de navegación fluidas (`Modo Fácil`, `Modo Avanzado`, `Lote`, `Mis Descargas`).
  - [x] Retiro del botón `⟳ yt-dlp` de la página de descargas.
- [x] **⚡ Modo Fácil (Rápido):**
  - [x] Interfaz minimalista con presets de 1 clic (720p, 1080p, MP3 320k, FLAC) y pegado directo.
- [x] **📦 Gestión Interactiva de Playlists:**
  - [x] Selector de elementos por checkboxes con acciones masivas (Todos / Ninguno).
  - [x] Soporte para entrega en archivo `.ZIP` o **Descargas Individuales Progresivas**.

---

## 🎯 Versión `v2.6.0` (Completado)
- [x] **Explorador y Selector de Playlists en Modo Avanzado:**
  - [x] Despliegue de elementos con casillas de verificación, acciones masivas (Todos/Ninguno) y toggle de ZIP vs Individuales.
- [x] **Estrategia de Descarga en Cascada Multimotor (Modo Fácil):**
  - [x] Ejecución secuencial de Cobalt v11 -> Motor Musical -> yt-dlp con PoToken.
  - [x] Tarjeta de diagnóstico de fallos con reporte detallado de cada motor evaluado.
- [x] **Consola de Actividad del Usuario en Modo Avanzado:**
  - [x] Panel de terminal informativo en tiempo real (`#userActivityConsole`), lectura segura y botón de limpieza.

---

## 🎯 Versión `v2.7.0` (Completado)
- [x] **Sistema de Cola en Segundo Plano y Persistencia Server-Side:**
  - [x] Daemon worker continuo en servidor (`background_queue_worker`) con persistencia en `queue_state.json`.
  - [x] Procesamiento secuencial que persiste si se cierra la ventana o navegador.
- [x] **Panel de Gestión de Cola Interactivo:**
  - [x] Reordenamiento de elementos pendientes (`⬆️ Subir`, `⬇️ Bajar`), cancelación individual y vaciado total de la cola.
  - [x] Badge dinámico con contador de pendientes en la barra lateral y monitoreo en vivo de descarga activa.
- [x] **Agrupación de Descargas por Carpetas / Colecciones:**
  - [x] Detección de playlists, álbumes y lotes agrupados dentro de tarjetas desplegables tipo Carpeta.
  - [x] Generación de archivo `.ZIP` bajo demanda para descargar toda la carpeta en un solo clic.
  - [x] Eliminación completa de carpeta y archivos individuales desde la interfaz.

---

## 🎯 Versión `v2.7.1` (Completado)
- [x] **Corrección y Resiliencia en Inspección de Playlists (`/api/info`):**
  - [x] Manejo seguro de `NoneType` en resultados de extracción.
  - [x] Aborto rápido ante errores permanentes (playlist inexistente/privada) para evitar bloqueos por intentos de clientes fallback.
  - [x] Indicador de carga (`⏳ Buscando...`) en la interfaz web.

---

## 🎯 Versión `v2.7.2` (Completado)
- [x] **Corrección de Concurrencia y Prevención de Bloqueos Mutuos (Deadlock):**
  - [x] Restauración de variables globales `JOBS` y `JOBS_LOCK`.
  - [x] Desacoplamiento total de bloqueos de hilos en `background_queue_worker`.
  - [x] Manejador `safeApiPost` en frontend para procesar respuestas de error HTTP de forma transparente sin errores de parseo JSON.

---

## 🎯 Versión `v2.7.3` (Completado)
- [x] **Eliminación de Sobrecarga de Tokens POT en Inspección de Metadatos:**
  - [x] Optimización de `player_client_opts(for_download=False)` para evitar llamadas innecesarias a `potprovider` en consultas planas.
  - [x] Reducción del tiempo de inspección de playlists de >60s a ~2s.

---

## 🎯 Versión `v2.7.4` (Completado)
- [x] **Cerrojos Reentrantes con `threading.RLock`:**
  - [x] Corrección de auto-bloqueo recursivo (*self-deadlock*) en hooks de progreso `append_job_log`.
  - [x] Eliminación de cuelgues durante descargas activas y consultas de estado en vivo.

---

## 🎯 Versión `v2.7.5` (Completado)
- [x] **Agrupación Universal de Playlists de YouTube en Carpetas:**
  - [x] Guardado de metadatos de carpeta (`folder_name` y `group_id`) en descargas individuales y ZIP.
  - [x] Renderizado de colecciones en "Mis Descargas" con acciones de descarga ZIP y eliminación en bloque.
  - [x] Detección automática de playlists sin necesidad de inspección previa.

---

## 🎯 Versión `v2.7.6` (Completado)
- [x] **Cancelación Inmediata de Descargas y Vaciar Cola:**
  - [x] Aborto en tiempo real de sockets y procesos de yt-dlp vía `DownloadCancelled` y `match_filter`.
  - [x] Inclusión del trabajo activo en `cancel_all_queue` para detener descargas en curso.
  - [x] Limpieza de temporales y preservación del estado `cancelled`.















