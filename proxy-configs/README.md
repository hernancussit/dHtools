# 🌐 Guía de Configuración de Proxy Inverso para dHtools

Esta carpeta contiene plantillas y configuraciones listas para producción para publicar **dHtools** detrás de cualquier servidor web o panel de control con soporte SSL/TLS, WebSockets y streaming en tiempo real.

---

## 📁 Estructura de Configuraciones

| Archivo / Carpeta | Plataforma / Panel | Descripción |
|---|---|---|
| [`nginx-universal.conf`](nginx-universal.conf) | **Nginx Universal** (Ubuntu / Debian / CentOS / aaPanel / CloudPanel) | Configuración completa lista para pegar en `/etc/nginx/sites-available/` o tu panel. |
| [`hestiacp/`](hestiacp/) | **HestiaCP** | Plantillas `.tpl` y `.stpl` nativas de HestiaCP. |
| [`cpanel-apache.conf`](cpanel-apache.conf) | **cPanel / WHM / Apache** | Reglas `.htaccess` o directivas `VirtualHost` con `mod_proxy` y `mod_rewrite`. |
| [`caddy-Caddyfile`](caddy-Caddyfile) | **Caddy Server** | Configuración de 5 líneas con SSL automático de Let's Encrypt. |

---

## 1. 🐧 Nginx Universal (Cualquier Servidor Linux / CloudPanel / aaPanel)

1. Copia el contenido de [`nginx-universal.conf`](nginx-universal.conf) en un archivo de sitio:
   ```bash
   sudo nano /etc/nginx/sites-available/dhtools.conf
   ```
2. Reemplaza `tu-dominio.com` con tu dominio real y ajusta las rutas de tus certificados SSL.
3. Habilita el sitio y recarga Nginx:
   ```bash
   sudo ln -s /etc/nginx/sites-available/dhtools.conf /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

---

## 2. 🛡️ HestiaCP

1. Copia las plantillas al directorio oficial de plantillas Nginx de HestiaCP:
   ```bash
   cp proxy-configs/hestiacp/dhtools-proxy.tpl  /usr/local/hestia/data/templates/web/nginx/
   cp proxy-configs/hestiacp/dhtools-proxy.stpl /usr/local/hestia/data/templates/web/nginx/
   ```
2. En el panel de HestiaCP, edita tu dominio web:
   - **Plantilla de Proxy Nginx:** Selecciona `dhtools-proxy`.
   - **Soporte SSL:** Asegúrate de tener habilitado *Let's Encrypt SSL*.
3. Guarda los cambios o ejecuta:
   ```bash
   v-change-web-domain-proxy-tpl admin tu-dominio.com dhtools-proxy
   systemctl reload nginx
   ```

---

## 3. 💼 cPanel / WHM (Apache mod_proxy)

### Método A: Archivo `.htaccess` (Más rápido)
Copia las directivas de [`cpanel-apache.conf`](cpanel-apache.conf) dentro del archivo `.htaccess` en la raíz `public_html` del subdominio o dominio asignado.

### Método B: Directivas VirtualHost en WHM
En **WHM ➔ Service Configuration ➔ Apache Configuration ➔ Include Editor ➔ Pre VirtualHost**, agrega la configuración de proxy inverso hacia `http://127.0.0.1:5000/`.

---

## 4. 🚀 Caddy Server (SSL Automático en 1 minuto)

Si usas **Caddy**, añade el bloque a tu `/etc/caddy/Caddyfile`:
```caddy
tu-dominio.com {
    reverse_proxy 127.0.0.1:5000
    header X-Robots-Tag "noindex, nofollow, noarchive, nosnippet"
}
```
Recarga Caddy:
```bash
sudo systemctl reload caddy
```

---

## ☁️ Cloudflare (Recomendación Adicional)
Si utilizas **Cloudflare Proxy (Nube Naranja)**:
- En **SSL/TLS**: Configura el modo en **Full (Strict)**.
- En **WebSockets**: Asegúrate de que estén habilitados en *Network ➔ WebSockets*.
