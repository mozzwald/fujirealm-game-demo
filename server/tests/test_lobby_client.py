import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from server.lobby_client import LobbyConfig, LobbyPublisher


class _LobbyHandler(BaseHTTPRequestHandler):
    responses = {}
    requests = []

    def _send(self, code):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_GET(self):
        self.__class__.requests.append(("GET", self.path, None))
        self._send(self.__class__.responses.get(("GET", self.path), 200))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        payload = json.loads(body.decode("utf-8")) if body else None
        self.__class__.requests.append(("POST", self.path, payload))
        self._send(self.__class__.responses.get(("POST", self.path), 200))

    def do_DELETE(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        payload = json.loads(body.decode("utf-8")) if body else None
        self.__class__.requests.append(("DELETE", self.path, payload))
        self._send(self.__class__.responses.get(("DELETE", self.path), 200))

    def log_message(self, format, *args):
        return


class LobbyClientTest(unittest.TestCase):
    def setUp(self):
        _LobbyHandler.requests = []
        _LobbyHandler.responses = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _LobbyHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.errors = []
        self.config = LobbyConfig(
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            game="FujiRealm Demo",
            creator_id=0x3022,
            app_id=0x02,
            server="The Realm",
            region="us",
            server_url="tcp://fujinet.online:9010",
            max_players=32,
            client_platform="atari",
            client_url="TNFS://tnfs.fujinet.online/ATARI/netgames/fujirealm.xex",
            timeout=0.2,
        )
        self.publisher = LobbyPublisher(self.config, self.errors.append)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_payload_contains_expected_fields(self):
        payload = self.config.payload(4, "online")
        self.assertEqual(payload["game"], "FujiRealm Demo")
        self.assertEqual(payload["appkey"], 0x02)
        self.assertEqual(payload["serverurl"], "tcp://fujinet.online:9010")
        self.assertEqual(payload["curplayers"], 4)
        self.assertEqual(payload["clients"][0]["platform"], "atari")

    def test_publish_posts_server_payload(self):
        self.assertTrue(self.publisher.publish(2, "online"))
        method, path, payload = _LobbyHandler.requests[-1]
        self.assertEqual((method, path), ("POST", "/server"))
        self.assertEqual(payload["appkey"], 0x02)
        self.assertEqual(payload["curplayers"], 2)
        self.assertEqual(payload["status"], "online")

    def test_delete_posts_serverurl(self):
        self.assertTrue(self.publisher.delete())
        method, path, payload = _LobbyHandler.requests[-1]
        self.assertEqual((method, path), ("DELETE", "/server"))
        self.assertEqual(payload, {"serverurl": "tcp://fujinet.online:9010"})

    def test_probe_version_hits_health_endpoint(self):
        self.assertTrue(self.publisher.probe_version())
        self.assertEqual(_LobbyHandler.requests[-1], ("GET", "/version", None))

    def test_publish_http_error_is_nonfatal(self):
        _LobbyHandler.responses[("POST", "/server")] = 500
        self.assertFalse(self.publisher.publish(1, "online"))
        self.assertTrue(self.errors)

    def test_publish_http_error_logs_response_body(self):
        _LobbyHandler.responses[("POST", "/server")] = 400
        self.assertFalse(self.publisher.publish(1, "online"))
        self.assertTrue(self.errors)
        self.assertIn("body=", self.errors[-1])


if __name__ == "__main__":
    unittest.main()
