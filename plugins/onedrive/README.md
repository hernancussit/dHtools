# ☁️ Microsoft OneDrive & SharePoint Cloud Sync para dHtools

Plugin oficial para **dHtools** que permite sincronizar y respaldar descargas multimedia automáticamente o bajo demanda en **Microsoft OneDrive** (cuentas personales `@outlook.com`, `@hotmail.com`) y **SharePoint / Microsoft 365** (cuentas de trabajo o educativas).

---

## 🚀 Características Principales

1. **Streaming Resumable por Fragmentos (RAM-Safe):**
   * Emplea sesiones de subida por bloques (`createUploadSession`) en fragmentos de 3.2 MB (múltiplo de 320 KiB requerido por Microsoft Graph).
   * No almacena archivos gigantes en memoria RAM, permitiendo subir videos 4K de varios gigabytes de forma fluida y estable.
2. **Aislamiento Multi-Usuario Total:**
   * Cada usuario de dHtools mantiene sus credenciales, tokens y carpetas de forma independiente en `plugins/onedrive/users_data/<username>/`.
   * Los administradores pueden preconfigurar un `client_id` y `client_secret` base para que los usuarios estándar solo hagan clic en "Conectar con Microsoft".
3. **Modo Safe Offload:**
   * Si se activa, elimina el archivo del disco del servidor VPS una vez confirmada la subida a OneDrive, registrando el enlace en la base de datos de descargas.
4. **Integración con Bot de Telegram:**
   * Añade automáticamente el botón interactivo `☁️ Subir a Microsoft OneDrive` en las notificaciones del bot.

---

## 🔑 Guía Rápida de Configuración en Azure / Microsoft Entra ID

Para conectar tu OneDrive con dHtools necesitas registrar una aplicación gratuita en Microsoft:

1. Ingresa en [Azure Portal — App Registrations](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
2. Haz clic en **"Nuevo registro"** (*New registration*):
   * **Nombre:** `dHtools OneDrive Sync` (o el que prefieras).
   * **Tipos de cuenta admitidos:** Selecciona *"Cuentas en cualquier directorio organizativo y cuentas Microsoft personales (por ejemplo, Skype, Xbox)"* si deseas admitir todo tipo de cuentas (`common`).
   * **URI de redirección:** Selecciona plataforma **Web** y coloca tu URL:
     `https://tu-dominio.com/plugin/onedrive/auth/callback`
3. Haz clic en **Registrar**.
4. Copia el **Id. de aplicación (cliente)** (*Application / Client ID*).
5. En el menú lateral ve a **Certificados y secretos** (*Certificates & secrets*) ➔ **Nuevo secreto de cliente** (*New client secret*):
   * Descripción: `dHtools`
   * Copia el **Valor** del secreto inmediatamente (solo se muestra una vez).
6. En el menú lateral ve a **Permisos de API** (*API permissions*) ➔ **Agregar un permiso** ➔ **Microsoft Graph** ➔ **Permisos delegados**:
   * `Files.ReadWrite` (Permite leer y escribir en OneDrive)
   * `offline_access` (Permite mantener la sesión activa sin reconectar)
   * `User.Read` (Lectura básica del perfil)
7. Pega tu **Client ID** y **Client Secret** en el panel de ajustes de dHtools (`/plugin/onedrive/settings`) y haz clic en **"Vincular con Microsoft"**.
