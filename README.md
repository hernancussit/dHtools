# Descargador de YouTube (yt-dlp + Cobalt + Flask)

Sitio web privado para descargar videos y playlists de YouTube con doble motor de extracción (**yt-dlp** y **Cobalt**), empaquetado en Docker y preparado para funcionar detrás del proxy Nginx de HestiaCP con HTTPS.

---

## Características Principales

- **Doble motor de descarga seleccionable:**
  - **yt-dlp:** Motor principal. Soporta videos individuales en todas las calidades (4K, 1080p, 720p, 480p), extracción de audio en MP3, **recorte de video por tiempo (trimming)** y **descarga de playlists completas en `.zip`**.
  - **Cobalt (v11):** Motor alternativo de alta velocidad para videos y audios individuales.
- **Búsqueda e información:** Vista previa con título, duración y miniatura antes de iniciar la descarga.
- **Progreso en tiempo real:** Barra de porcentaje, velocidad de transferencia del servidor y conteo de videos completados.
- **Evasión de bloqueos de YouTube:**
  - **Deno integrado:** Resuelve los desafíos de JavaScript que YouTube exige para entregar formatos reales.
  - **PO Token Provider unificado (`potprovider`):** Genera Proof-of-Origin Tokens en segundo plano para alimentar tanto a `yt-dlp` como a `Cobalt` (vía `POST /get_pot`).
  - **Soporte de cookies:** Admite `cookies.txt` (formato Netscape) para videos que requieren sesión o verificación anti-bot.
- **Seguridad y Privacidad:**
  - Acceso restringido por HTTP Basic Auth (`APP_USERNAME` / `APP_PASSWORD`).
  - Cabeceras `X-Robots-Tag` y `robots.txt` para evitar indexación en motores de búsqueda.
- **Mantenimiento Automatizado:**
  - Limpieza periódica configurable de archivos descargados en `downloads/`.
  - Botón de actualización de `yt-dlp` en la interfaz + tarea de actualización automática en segundo plano.

---

## 1. Puesta en Marcha Rápida

1. **Configurar las variables de entorno:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Definí tus credenciales (`APP_USERNAME` y `APP_PASSWORD`).*

2. **Iniciar los contenedores con Docker Compose:**
   ```bash
   docker compose up -d --build
   ```

3. **Acceder localmente:**
   Abrí `http://localhost:5000` (o `http://IP_DEL_SERVIDOR:5000`). El navegador solicitará el usuario y contraseña definidos en `.env`.

---

## 2. Arquitectura de Contenedores

El `docker-compose.yml` levanta 3 servicios ligeros y coordinados:

| Servicio | Contenedor | Función | Puerto Interno |
|---|---|---|---|
| `ytsite` | `yt-downloader` | Aplicación web en Flask (Gunicorn) + Deno + yt-dlp | `5000` |
| `potprovider` | `pot-provider` | Proveedor oficial de PO Tokens (`bgutil-ytdlp-pot-provider`) | `4416` |
| `cobalt` | `cobalt-api` | API de Cobalt v11 conectado a `potprovider` para tokens | `9000` |

---

## 3. Publicación con HestiaCP (Puerto 443 / SSL)

1. **Crear el dominio en HestiaCP:**
   - Panel de HestiaCP → **Web** → **Add Web Domain** (ej. `yt.tudominio.com`).
   - Editá el dominio → Pestaña **SSL** → Tildá **Let's Encrypt Support** y guardá.

2. **Instalar la plantilla de proxy inverso:**
   Copiá los templates incluidos en `hestiacp-templates/` al directorio de plantillas de Nginx en tu servidor:
   ```bash
   cp hestiacp-templates/ytsite-proxy.tpl  /usr/local/hestia/data/templates/web/nginx/
   cp hestiacp-templates/ytsite-proxy.stpl /usr/local/hestia/data/templates/web/nginx/
   ```

3. **Asignar la plantilla al dominio:**
   - En HestiaCP → **Web** → **Edit** (del dominio) → en **Web Template** seleccioná `ytsite-proxy` → **Save**.
   - Verificá la configuración de Nginx:
     ```bash
     nginx -t && systemctl reload nginx
     ```

---

## 4. Gestión de Sesión y Cookies (Anti-Bot)

Si YouTube exige iniciar sesión o resolver captchas en tu VPS (*"Sign in to confirm you're not a bot"*):

1. **Exportar cookies:**
   - Usá una extensión de navegador como *"Get cookies.txt LOCALLY"* en Chrome o Firefox.
   - Entrá a YouTube en modo incógnito con una cuenta secundaria y exportá el archivo `cookies.txt` en formato Netscape.
2. **Subir las cookies al proyecto:**
   - Guardá el archivo en `/var/ytsite/cookies.txt`.
   - Reiniciá el contenedor si cambiaste volúmenes:
     ```bash
     docker compose restart ytsite
     ```
   *Nota: `cookies.txt` está montado en modo lectura/escritura para que yt-dlp pueda refrescar las cookies automáticamente.*

---

## 5. Recorte de Video y Opciones de Audio

- **Recorte de Video (Trim):**
  - Exclusivo del motor `yt-dlp` en videos individuales.
  - Podés especificar los campos `Desde` y `Hasta` en formato `HH:MM:SS`, `MM:SS` o segundos (`90`).
  - Utiliza `download_ranges` de yt-dlp para descargar y cortar directamente en los keyframes sin procesar el video entero.
- **Formatos de Audio:**
  - Extrae y convierte a MP3 con FFmpeg al bitrate elegido (128, 192, 256 o 320 kbps).

---

## 6. Limpieza Automática de Descargas

Los archivos descargados se guardan temporalmente en `downloads/`. Un hilo en segundo plano borra automáticamente los archivos que superen el tiempo límite:

```env
CLEANUP_AFTER_HOURS=24
CLEANUP_CHECK_INTERVAL_MINUTES=30
```

- `CLEANUP_AFTER_HOURS`: Cantidad de horas que se conserva un archivo antes de eliminarse (por defecto 24h). Poné `0` para desactivar la limpieza automática.
- `CLEANUP_CHECK_INTERVAL_MINUTES`: Intervalo de revisión del directorio (por defecto 30 min).

---

## 7. Actualización de Motores

- **yt-dlp:**
  - Desde el botón **⟳ Actualizar yt-dlp** en la cabecera del sitio web.
  - O automáticamente en segundo plano según `AUTO_UPDATE_YTDLP=true` y `AUTO_UPDATE_INTERVAL_HOURS=24`.
- **Cobalt:**
  - Para actualizar la imagen de Cobalt a la última versión disponible:
    ```bash
    docker compose pull cobalt && docker compose up -d cobalt
    ```

---

## 8. Diagnóstico y Comandos Útiles

- **Ver estado de los contenedores:**
  ```bash
  docker compose ps
  ```
- **Ver registros en tiempo real:**
  ```bash
  docker compose logs -f ytsite
  docker compose logs -f potprovider
  docker compose logs -f cobalt
  ```
- **Probar extracción manual dentro del contenedor:**
  ```bash
  docker exec yt-downloader yt-dlp -F "https://www.youtube.com/watch?v=VIDEO_ID" --cookies /app/cookies.txt
  ```
