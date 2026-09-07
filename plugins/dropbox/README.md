# 📦 Dropbox Cloud Sync para dHtools

Plugin oficial para **dHtools** que permite sincronizar y respaldar descargas multimedia automáticamente o bajo demanda en **Dropbox** mediante su API oficial v2.

---

## 🚀 Características Principales

1. **Subida por Bloques y Streaming (RAM-Safe):**
   * Archivos pequeños (< 4 MB): Subida directa atómica en un único POST.
   * Archivos grandes (>= 4 MB): Sesiones de subida por bloques (`upload_session/start`, `append_v2`, `finish`) en fragmentos de 4 MB.
   * No almacena archivos gigantes en memoria RAM, permitiendo subir videos 4K de varios gigabytes sin sobrecargar el servidor.
2. **Generación de Enlace Compartido (Web Link):**
   * Tras la subida, genera automáticamente un enlace público de visualización o descarga directa que se registra en la base de datos de descargas y en Telegram.
3. **Aislamiento Multi-Usuario Total:**
   * Cada usuario de dHtools mantiene sus credenciales, tokens y carpetas de forma aislada en `plugins/dropbox/users_data/<username>/`.
4. **Modo Safe Offload:**
   * Elimina de forma segura el archivo del servidor VPS una vez confirmada la subida a Dropbox.
5. **Integración con Bot de Telegram:**
   * Añade el botón interactivo `📦 Subir a Dropbox` en las notificaciones del bot.

---

## 🔑 Guía Rápida de Configuración en Dropbox App Console

Para conectar tu Dropbox con dHtools:

1. Ingresa a la consola de desarrolladores: [Dropbox App Console](https://www.dropbox.com/developers/apps).
2. Haz clic en **"Create app"**:
   * **Choose an API:** Selecciona `Scoped access`.
   * **Choose the type of access:** Selecciona `Full Dropbox` (para acceder a la carpeta `/dHtools` o la que elijas).
   * **Name your app:** Escribe un nombre único (ej. `dHtools Sync Hernan`).
3. En la pestaña **Permissions** (Permisos), asegúrate de marcar:
   * `files.content.write` (Escribir archivos en Dropbox)
   * `files.content.read` (Leer metadatos de archivos)
   * `sharing.write` (Crear enlaces compartidos para visualización)
   * `account_info.read` (Consultar cuota y perfil)
   * Haz clic en **Submit** al pie de la página para guardar los permisos.
4. En la pestaña **Settings** (Configuración):
   * Copia tu **App key**.
   * Copia tu **App secret** (haz clic en *Show*).
   * En **OAuth 2 ➔ Redirect URIs**, añade tu URL:
     `https://tu-dominio.com/plugin/dropbox/auth/callback`
5. Pega tu **App Key** y **App Secret** en el panel de dHtools (`/plugin/dropbox/settings`) y haz clic en **"Vincular con Dropbox"**.
