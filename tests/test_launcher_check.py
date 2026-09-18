import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from scripts.launcher_check import port_is_free, verify_file, wait_for_url


class _HealthyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args):
        pass


class LauncherCheckTests(unittest.TestCase):
    def test_model_integrity_requires_expected_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.bin"
            path.write_bytes(b"model")
            expected = hashlib.sha256(b"model").hexdigest()
            verify_file(path, expected, "test model")
            with self.assertRaises(RuntimeError):
                verify_file(path, "0" * 64, "test model")

    def test_port_check_detects_an_active_listener(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.assertFalse(port_is_free("127.0.0.1", port))
        self.assertTrue(port_is_free("127.0.0.1", port))

    def test_wait_for_url_requires_an_http_success(self):
        server = HTTPServer(("127.0.0.1", 0), _HealthyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertTrue(wait_for_url(f"http://127.0.0.1:{server.server_port}/", 1))
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
