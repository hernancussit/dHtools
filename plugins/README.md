# 🧩 Directorio de Plugins de dHtools [EXPERIMENTAL]

> [!WARNING]
> **Estado de la Característica:** El sistema de plugins de **dHtools** se encuentra en fase **EXPERIMENTAL**.
> Las interfaces y ganchos (hooks) están sujetos a mejoras e iteraciones continuas.

Este directorio permite agregar extensiones, bots secundarios, integraciones de mensajería (Telegram, Discord, WhatsApp, Webhooks) y automatizaciones privadas **sin modificar el código fuente de dHtools** y **sin exponer código privado en Git ni GitHub**.

---

## 🔒 Aislamiento en Git

Por configuración predeterminada en `.gitignore`, **todas las carpetas que crees dentro de `plugins/` son ignoradas por Git** (excepto la plantilla oficial `template_example/` y este archivo `README.md`).

Esto significa que puedes:
1. Crear tus propios plugins en `plugins/<tu_solucion>/`.
2. Guardar archivos de configuración privados (`config.json`, tokens de bots, claves de API).
3. Hacer `git pull` o cambiar entre ramas (`main` / `dev`) sin riesgo alguno de conflicto ni sobreescritura.

---

## 📁 Estructura Mínima de un Plugin

```text
plugins/
└── mi_plugin/
    ├── plugin.json        # Metadatos del plugin (nombre, versión, enabled)
    └── plugin.py          # Código Python con la clase Plugin y sus hooks
```

Revisa la carpeta [`plugins/template_example/`](template_example/) para ver un ejemplo funcional completo y consulta la guía detallada en [`docs/PLUGIN_DEV_GUIDE.md`](../docs/PLUGIN_DEV_GUIDE.md).
