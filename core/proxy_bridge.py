"""dHtools Proxy Bridge
Servidor proxy HTTP interno y dinámico para componentes locales (como Cobalt).
Enruta las conexiones salientes a través del Proxy de Red configurado en el panel de dHtools
(SOCKS5, SOCKS5h, SOCKS4, HTTP, HTTPS) o de forma directa si el proxy está desactivado.
"""

import os
import socket
import select
import threading
import urllib.parse
import base64
import logging
from typing import Optional, Tuple

try:
    import socks
except ImportError:
    socks = None

logger = logging.getLogger("ProxyBridge")

_SERVER_THREAD: Optional[threading.Thread] = None
_SERVER_SOCKET: Optional[socket.socket] = None
_STOP_EVENT = threading.Event()
_SERVER_LOCK = threading.Lock()
_ACTIVE_PORT: int = 8899
_ACTIVE_HOST: str = "0.0.0.0"


def create_outgoing_connection(
    target_host: str,
    target_port: int,
    proxy_url: Optional[str] = None,
    timeout: float = 20.0
) -> socket.socket:
    """Crea una conexión socket hacia (target_host, target_port).
    Si proxy_url está definido, enruta la conexión a través del proxy especificado
    (soportando socks5, socks5h, socks4, socks4a, http, https).
    Si proxy_url es None o vacío, conecta directamente por la interfaz local.
    """
    proxy_url = (proxy_url or "").strip()
    if not proxy_url:
        return socket.create_connection((target_host, target_port), timeout=timeout)

    parsed = urllib.parse.urlsplit(proxy_url)
    scheme = (parsed.scheme or "http").lower()
    p_host = parsed.hostname
    p_port = parsed.port or (1080 if "socks" in scheme else 8080)
    username = urllib.parse.unquote(parsed.username) if parsed.username else None
    password = urllib.parse.unquote(parsed.password) if parsed.password else None

    if "socks" in scheme:
        if socks is None:
            raise RuntimeError("PySocks no está instalado en el entorno. Requerido para túneles SOCKS.")
        s = socks.socksocket()
        s.settimeout(timeout)
        socks_type = socks.SOCKS5 if "socks5" in scheme else socks.SOCKS4
        # Remote DNS resolution for socks5h and socks4a
        rdns = True if ("h" in scheme or "socks4a" in scheme or "socks5" in scheme) else False
        s.set_proxy(
            proxy_type=socks_type,
            addr=p_host,
            port=p_port,
            rdns=rdns,
            username=username,
            password=password
        )
        s.connect((target_host, target_port))
        return s
    else:
        # Upstream HTTP / HTTPS proxy
        s = socket.create_connection((p_host, p_port), timeout=timeout)
        req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n"
        if username and password:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            req += f"Proxy-Authorization: Basic {token}\r\n"
        req += "User-Agent: dHtools-ProxyBridge/1.0\r\nProxy-Connection: Keep-Alive\r\n\r\n"
        s.sendall(req.encode("latin1"))

        resp = b""
        s.settimeout(timeout)
        while b"\r\n\r\n" not in resp:
            chunk = s.recv(4096)
            if not chunk:
                break
            resp += chunk
            if len(resp) > 65536:
                break

        status_line = resp.split(b"\r\n", 1)[0]
        if not (b" 200" in status_line):
            s.close()
            raise RuntimeError(f"El proxy HTTP superior rechazó la conexión CONNECT: {status_line.decode('latin1', errors='replace')}")
        return s


def _handle_client_connection(client_sock: socket.socket, client_addr: Tuple[str, int]):
    remote_sock: Optional[socket.socket] = None
    try:
        client_sock.settimeout(15.0)
        initial_data = b""
        while b"\r\n\r\n" not in initial_data:
            chunk = client_sock.recv(4096)
            if not chunk:
                break
            initial_data += chunk
            if len(initial_data) > 65536:
                break

        if not initial_data:
            return

        header_part = initial_data.split(b"\r\n\r\n", 1)[0]
        lines = header_part.split(b"\r\n")
        req_line = lines[0].decode("latin1", errors="replace")
        parts = req_line.split()
        if len(parts) < 2:
            return

        method, target = parts[0].upper(), parts[1]

        # Obtener dinámicamente la configuración actual del proxy desde el panel
        from core.utils import get_download_proxy_config
        proxy_cfg = get_download_proxy_config()
        proxy_mode = proxy_cfg.get("mode", "disabled")
        proxy_url = proxy_cfg.get("url", "").strip() if (proxy_mode in ("always", "failsafe") and proxy_cfg.get("url")) else None

        if method == "CONNECT":
            # Formato típico: target = "www.instagram.com:443" o "[2001:...]:443"
            if ":" in target:
                host, port_str = target.rsplit(":", 1)
                port = int(port_str)
            else:
                host = target
                port = 443

            try:
                remote_sock = create_outgoing_connection(host, port, proxy_url=proxy_url, timeout=20.0)
            except Exception as e:
                client_sock.sendall(f"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\nProxy Bridge Error: {str(e)}".encode("latin1"))
                return

            client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\nProxy-Agent: dHtools-ProxyBridge/1.0\r\n\r\n")
        else:
            # Petición HTTP simple: método GET/POST/HEAD con URL absoluta o relativa
            parsed = urllib.parse.urlsplit(target)
            host = parsed.hostname or client_sock.getsockname()[0]
            port = parsed.port or 80
            path = parsed.path or "/"
            if parsed.query:
                path += f"?{parsed.query}"

            try:
                remote_sock = create_outgoing_connection(host, port, proxy_url=proxy_url, timeout=20.0)
            except Exception as e:
                client_sock.sendall(f"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\nProxy Bridge Error: {str(e)}".encode("latin1"))
                return

            new_req_line = f"{method} {path} HTTP/1.1\r\n"
            rest_of_headers = b"\r\n".join(lines[1:]) + b"\r\n\r\n"
            body = initial_data.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in initial_data else b""
            remote_sock.sendall(new_req_line.encode("latin1") + rest_of_headers + body)

        # Túnel bidireccional de bytes sin bloqueo
        client_sock.setblocking(False)
        remote_sock.setblocking(False)
        sockets = [client_sock, remote_sock]

        while not _STOP_EVENT.is_set():
            rlist, _, xlist = select.select(sockets, [], sockets, 30.0)
            if xlist or not rlist:
                break
            for s in rlist:
                other = remote_sock if s is client_sock else client_sock
                try:
                    data = s.recv(32768)
                except Exception:
                    data = None
                if not data:
                    return
                try:
                    other.sendall(data)
                except Exception:
                    return

    except Exception as e:
        logger.debug(f"[ProxyBridge] Error atendiendo conexión {client_addr}: {e}")
    finally:
        for s in (client_sock, remote_sock):
            if s:
                try:
                    s.close()
                except Exception:
                    pass


def _server_worker(host: str, port: int):
    global _SERVER_SOCKET
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
        srv.listen(128)
        srv.settimeout(1.0)
        _SERVER_SOCKET = srv
        logger.info(f"[ProxyBridge] Servidor activo escuchando en {host}:{port}")
    except Exception as e:
        logger.error(f"[ProxyBridge] No se pudo iniciar el bridge en {host}:{port}: {e}")
        srv.close()
        return

    while not _STOP_EVENT.is_set():
        try:
            client_conn, client_addr = srv.accept()
            t = threading.Thread(
                target=_handle_client_connection,
                args=(client_conn, client_addr),
                daemon=True,
                name=f"ProxyBridgeWorker-{client_addr[1]}"
            )
            t.start()
        except socket.timeout:
            continue
        except Exception as e:
            if not _STOP_EVENT.is_set():
                logger.debug(f"[ProxyBridge] Exception en loop principal: {e}")
            break

    try:
        srv.close()
    except Exception:
        pass
    _SERVER_SOCKET = None
    logger.info("[ProxyBridge] Servidor finalizado.")


def start_proxy_bridge(host: Optional[str] = None, port: Optional[int] = None):
    """Inicia el servidor puente de proxy en segundo plano si no está iniciado."""
    global _SERVER_THREAD, _ACTIVE_HOST, _ACTIVE_PORT
    with _SERVER_LOCK:
        if _SERVER_THREAD and _SERVER_THREAD.is_alive():
            return

        _STOP_EVENT.clear()
        _ACTIVE_HOST = host or os.environ.get("PROXY_BRIDGE_HOST", "0.0.0.0")
        _ACTIVE_PORT = port or int(os.environ.get("PROXY_BRIDGE_PORT", "8899"))

        _SERVER_THREAD = threading.Thread(
            target=_server_worker,
            args=(_ACTIVE_HOST, _ACTIVE_PORT),
            daemon=True,
            name="ProxyBridgeServer"
        )
        _SERVER_THREAD.start()


def stop_proxy_bridge():
    """Detiene el servidor puente."""
    global _SERVER_THREAD
    with _SERVER_LOCK:
        _STOP_EVENT.set()
        if _SERVER_THREAD:
            _SERVER_THREAD.join(timeout=3.0)
            _SERVER_THREAD = None


def is_proxy_bridge_running() -> bool:
    return bool(_SERVER_THREAD and _SERVER_THREAD.is_alive())


def get_proxy_bridge_address() -> Tuple[str, int]:
    return _ACTIVE_HOST, _ACTIVE_PORT
