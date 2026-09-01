# ⚡ dHtools - Suite Multimedia & Extractor Universal

[![Release](https://img.shields.io/badge/Release-v1.0.0--stable-blue.svg)](https://github.com/hernancussit/dHtools)
[![Python](https://img.shields.io/badge/Python-3.11+-yellow.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**dHtools** es una plataforma web autohospedable y de alto rendimiento diseñada para la descarga, conversión, recorte y sincronización en la nube de contenido multimedia desde múltiples plataformas (**YouTube, Spotify, Deezer, TikTok, Instagram, Twitter/X, Twitch, Facebook y más**).

Está diseñada para ejecutarse en tu propio servidor VPS o máquina local con **Docker Compose**, ofreciendo una interfaz moderna y reactiva con gestión multiusuario, blindaje de seguridad, panel de administración completo, selector de canal de actualizaciones (`main` vs `dev`) y rollback automático en 1 clic.

---

## 🚀 Características Principales

### 🎯 Extracción Multiplataforma Inteligente
- **Motor en Cascada Automático:** Combina automáticamente **yt-dlp**, **Cobalt v11 Oficial** y el motor de streaming de audio **Deezer/Spotify** con fallback transparente.
- **Calidades de Video Ultra HD:** Descarga en 4K (2160p), 2K (1440p), Full HD (1080p), 720p y 480p con selección de contenedor (`MP4` / `MKV`) y subtítulos incrustados.
- **Suite de Audio Hi-Fi:** Extracción directa con carátulas en alta resolución y metadatos ID3 automáticos en calidades `128 kbps`, `192 kbps`, `256 kbps` y `320 kbps (CBR MP3)`.
- **Playlists & Álbumes:** Detección automática y desglose de listas de reproducción con seguimiento ítem por ítem en tiempo real, priorización interactiva (⬆️/⬇️) y descarga agrupada en carpetas virtuales o archivo `.zip`.
- **Recorte Preciso por Tiempo (Trimming):** Permite recortar fragmentos exactos de audio o video indicando tiempos de inicio y fin (`HH:MM:SS` o segundos) sin recodificación innecesaria.
- **Cola de Descargas Asíncrona:** Procesamiento secuencial sin saturar la CPU o la memoria RAM del servidor.

### 🛡️ Blindaje de Seguridad Integral
- **Protección contra Fuerza Bruta:** Bloqueo temporal automático por IP tras 5 intentos fallidos con retraso progresivo (*tarpit*).
- **Prevención de RCE e Inyecciones de Shell:** Sanitización estricta de URLs (`validate_media_url`) y ejecución sin `shell=True`.
- **Protección contra Path Traversal:** Verificación canónica de rutas (`safe_download_path`) en todos los endpoints de archivo.
- **Cabeceras HTTP de Seguridad:** Inyección de `Content-Security-Policy`, `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff` y `Referrer-Policy`.
- **Evasión de Bloqueos de YouTube:** Deno integrado para resolución de desafíos JS y microservicio `potprovider` para generación continua de Proof-of-Origin Tokens.

### ⚙️ Panel de Administración & Gestión
- **Sistema de Actualizaciones en 1 Clic:** Comprobador de versiones contra GitHub y actualizador en caliente desde el panel web.
- **Selector de Canales:** Alterná entre la rama estable (`main`) y la rama de desarrollo (`dev`) directamente desde la interfaz.
- **Rollback Seguro:** Restauración inmediata a la versión anterior con un solo clic si algo falla.
- **Gestión Multiusuario:** Creación de usuarios con roles `Admin` y `Downloader`, cambio de contraseñas, suspensión de cuentas y purga selectiva de descargas por usuario.
- **Sincronización en la Nube (Cloud Sync):** Exportación automática a Nextcloud/ownCloud vía **WebDAV**, canales/grupos de **Telegram Bot** y servidores **FTP**.
- **Monitoreo en Tiempo Real:** Métricas en vivo del uso de CPU, RAM del proyecto vs VPS total y espacio en disco con purga automática configurable.

---

## 📦 Puesta en Marcha Rápida (Docker Compose)

### 1. Clonar el repositorio
```bash
git clone https://github.com/hernancussit/dHtools.git
cd dHtools
```

### 2. Configurar variables de entorno
```bash
cp .env.example .env
nano .env
```
*Definí tus credenciales de acceso (`APP_USERNAME` y `APP_PASSWORD`) y tu clave secreta de sesión.*

### 3. Iniciar los contenedores
```bash
docker compose up -d --build
```

La aplicación estará lista en `http://localhost:5000` (o `http://TU_IP_VPS:5000`).

---

## 🌐 Publicación con Dominio & SSL (Nginx / HestiaCP / Cloudflare)

Si utilizas **HestiaCP** u otro panel con Nginx:

1. Añade el dominio o subdominio en tu panel con certificado SSL Let's Encrypt.
2. Copia las plantillas incluidas en `hestiacp-templates/` al directorio de plantillas de Nginx:
   ```bash
   cp hestiacp-templates/dhtools-proxy.tpl  /usr/local/hestia/data/templates/web/nginx/
   cp hestiacp-templates/dhtools-proxy.stpl /usr/local/hestia/data/templates/web/nginx/
   ```
3. Asigna la plantilla `dhtools-proxy` al dominio y recarga Nginx:
   ```bash
   systemctl reload nginx
   ```

---

## 🌿 Canales de Actualización

| Canal | Rama Git | Descripción |
|---|---|---|
| **🟢 Estable** | `main` | Versiones probadas y listas para producción en cualquier VPS. |
| **🧪 Desarrollo** | `dev` | Nuevas funciones experimentales y mejoras previas al lanzamiento. |

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT.

