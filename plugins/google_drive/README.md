# 📁 Google Drive Cloud Sync — Plugin Oficial Bundled [EXPERIMENTAL]

Plugin oficial de **dHtools** para sincronizar y respaldar descargas directamente en **Google Drive** con soporte para subida resumable por fragmentos de 10 MB (RAM-Safe) y modo Safe Offload ("Subir y Mover").

> [!WARNING]
> **Estado:** Característica **EXPERIMENTAL**. Implementado bajo la arquitectura de plugins desacoplados (`core/plugin_manager.py`).

---

## 🚀 Características Principales

1. **Streaming Resumable en Fragmentos de 10 MB:** Los archivos pesados se transmiten directamente al endpoint de Google Drive sin cargarse completos en la memoria RAM, manteniendo el consumo del servidor habitualmente por debajo de 250 MB.
2. **Doble Modalidad de Autenticación:**
   - **Cuenta de Servicio (Service Account) [Recomendada para VPS y Docker]:** Autenticación desatendida mediante clave JSON sin requerir ventanas de navegador ni renovaciones manuales de sesión.
   - **OAuth 2.0:** Compatible con cuentas personales `@gmail.com` mediante credenciales de cliente OAuth.
3. **Modo Safe Offload ("Subir y Mover"):** Elimina automáticamente el archivo descargado del almacenamiento local del VPS únicamente cuando la subida a Google Drive ha finalizado con éxito.
4. **Soporte para Carpetas y Unidades Compartidas:** Permite definir un `folder_id` específico o subir a carpetas de *Shared Drives* corporativos o educativos.
5. **Telemetría en Tiempo Real:** Emite el porcentaje de subida (`[*] [GoogleDrive] Subiendo: 45%...`) directamente en la consola interactiva de la descarga.

---

## 🛠️ Guía Rápida de Configuración (Cuenta de Servicio)

### Paso 1: Crear la Cuenta de Servicio en Google Cloud
1. Ingresá a la [Consola de Google Cloud](https://console.cloud.google.com/).
2. Creá un nuevo proyecto (ej. `dHtools-Drive`).
3. En el menú lateral, andá a **APIs y servicios** > **Biblioteca**.
4. Buscá **Google Drive API** y hacé clic en **Habilitar**.
5. Andá a **APIs y servicios** > **Credenciales** > **Crear credenciales** > **Cuenta de servicio**.
6. Asignale un nombre (ej. `dhtools-uploader`) y finalizá el asistente.
7. En la lista de cuentas de servicio, hacé clic sobre la cuenta creada, andá a la pestaña **Claves** > **Agregar clave** > **Crear clave nueva** > Seleccioná formato **JSON** y descargá el archivo.

### Paso 2: Compartir tu Carpeta de Google Drive
1. Abrí [Google Drive](https://drive.google.com/).
2. Creá la carpeta donde querés recibir las descargas (ej. `Descargas dHtools`).
3. Hacé clic derecho > **Compartir**.
4. En el campo de personas, pegá el correo de la cuenta de servicio creada en el Paso 1 (termina en `@...iam.gserviceaccount.com`).
5. Asignale rol de **Editor** y desmarcá "Notificar a los usuarios".
6. Copiá el ID de la carpeta desde la barra de direcciones de tu navegador:
   `https://drive.google.com/drive/folders/`**`1A2b3C4d5E6f7G8h9I0j`**

### Paso 3: Configurar en dHtools
1. Ingresá a tu instancia de dHtools en `/plugin/google_drive/settings`.
2. Pegá el contenido del archivo JSON de la clave en el área de texto.
3. Pegá el ID de tu carpeta en **ID de Carpeta Destino**.
4. Hacé clic en **🔌 Probar Conexión con Google Drive**.
5. Al verificar el estado verde, activá el switch y hacé clic en **💾 Guardar Configuración**.

---

## 🔒 Seguridad y Git

El código fuente de este plugin está registrado en el repositorio oficial de dHtools. Sin embargo, por reglas estrictas en `.gitignore`, tus archivos de credenciales:
- `plugins/google_drive/config.json`
- `plugins/google_drive/service_account.json`
- `plugins/google_drive/token.json`

**NUNCA se subirán ni expondrán a Git ni GitHub.**
