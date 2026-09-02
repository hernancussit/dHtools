# 🛡️ Política de Seguridad (Security Policy)

## Versiones Soportadas

Actualmente se proporciona soporte de seguridad y parches para las siguientes versiones:

| Versión | Soportada |
|---|---|
| `v1.1.x` | :white_check_mark: |
| `v1.0.x` | :white_check_mark: |
| `dev` | :white_check_mark: |
| `< 1.0.0` | :x: |

---

## Reportar una Vulnerabilidad

La seguridad de los usuarios y servidores que autohospedan **dHtools** es una prioridad absoluta.

Si descubres una vulnerabilidad de seguridad (por ejemplo: inyección de comandos, omisión de autenticación, cross-site scripting, path traversal o fuga de datos):

1. **NO abras un Issue público en GitHub.**
2. Envía un reporte detallado con los pasos para reproducir la vulnerabilidad a través de la pestaña de [GitHub Security Advisories](https://github.com/hernancussit/dHtools/security/advisories/new) o contactando directamente al autor.
3. Incluye:
   - Descripción de la vulnerabilidad.
   - Pasos detallados para reproducirla (o código de prueba de concepto).
   - Impacto potencial en el servidor VPS o navegador.

---

## Compromiso de Respuesta
- Confirmación de recepción del reporte en un plazo menor a **48 horas**.
- Evaluación y parche correctivo en la rama `dev` y posterior release estable en `main`.
- Reconocimiento público en las notas de la versión (si el reportante así lo desea).
