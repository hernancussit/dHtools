import unittest
import socket
import threading
import time
import urllib.parse
from unittest.mock import patch, MagicMock

from core.proxy_bridge import (
    start_proxy_bridge,
    stop_proxy_bridge,
    is_proxy_bridge_running,
    create_outgoing_connection,
    _handle_client_connection
)
import core.proxy_bridge

class TestProxyBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start_proxy_bridge()
        time.sleep(0.3)
        _, port = core.proxy_bridge.get_proxy_bridge_address()
        cls.test_port = port

    @classmethod
    def tearDownClass(cls):
        pass

    def test_bridge_is_running(self):
        self.assertTrue(is_proxy_bridge_running())

    def test_direct_outgoing_connection(self):
        # Test direct socket creation when proxy_url is None
        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            s = create_outgoing_connection("example.com", 443, proxy_url=None)
            self.assertIsNotNone(s)
            mock_conn.assert_called_with(("example.com", 443), timeout=20.0)

    def test_socks5_outgoing_connection(self):
        # Test SOCKS5 outgoing socket setup
        with patch("socks.socksocket") as mock_socksocket:
            mock_s = MagicMock()
            mock_socksocket.return_value = mock_s
            s = create_outgoing_connection(
                "example.com", 443,
                proxy_url="socks5h://user:secret@proxy.local:1080"
            )
            mock_s.set_proxy.assert_called_once()
            args, kwargs = mock_s.set_proxy.call_args
            self.assertEqual(kwargs.get("addr"), "proxy.local")
            self.assertEqual(kwargs.get("port"), 1080)
            self.assertEqual(kwargs.get("username"), "user")
            self.assertEqual(kwargs.get("password"), "secret")
            self.assertTrue(kwargs.get("rdns"))
            mock_s.connect.assert_called_with(("example.com", 443))

    def test_http_outgoing_connection(self):
        # Test HTTP proxy CONNECT request negotiation
        with patch("socket.create_connection") as mock_conn:
            mock_s = MagicMock()
            mock_conn.return_value = mock_s
            mock_s.recv.return_value = b"HTTP/1.1 200 Connection Established\r\n\r\n"

            s = create_outgoing_connection(
                "example.com", 443,
                proxy_url="http://user:secret@httpproxy.local:8080"
            )
            mock_conn.assert_called_with(("httpproxy.local", 8080), timeout=20.0)
            mock_s.sendall.assert_called_once()
            sent = mock_s.sendall.call_args[0][0]
            self.assertIn(b"CONNECT example.com:443 HTTP/1.1", sent)
            self.assertIn(b"Proxy-Authorization: Basic", sent)

    def test_bridge_connect_flow(self):
        client, server_side = socket.socketpair()
        try:
            with patch("core.proxy_bridge.create_outgoing_connection") as mock_out:
                fake_remote = MagicMock()
                # Simulate remote closing immediately after establishment
                fake_remote.recv.return_value = b""
                mock_out.return_value = fake_remote

                client.sendall(b"CONNECT api.instagram.com:443 HTTP/1.1\r\nHost: api.instagram.com:443\r\n\r\n")
                t = threading.Thread(
                    target=_handle_client_connection,
                    args=(server_side, ("127.0.0.1", 12345)),
                    daemon=True
                )
                t.start()

                resp = client.recv(1024)
                self.assertIn(b"200 Connection Established", resp)
                mock_out.assert_called_once()
                args, _ = mock_out.call_args
                self.assertEqual(args[0], "api.instagram.com")
                self.assertEqual(args[1], 443)
                t.join(timeout=1.0)
        finally:
            client.close()
            server_side.close()

if __name__ == "__main__":
    unittest.main()
