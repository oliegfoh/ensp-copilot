"""HTTP-level tests for .topo upload and device discovery.

No eNSP required: only static topology files and a local in-process server.
"""
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from ensp_copilot import server
from ensp_copilot.topo import parse_topo

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO = ROOT / "fixtures" / "demo.topo"


class TestTopoUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.orig_dir, cls.orig_topo = server.TOPO_DIR, server.TOPOLOGIES
        server.TOPO_DIR = pathlib.Path(cls.tmp.name)
        server.TOPOLOGIES = {"demo": parse_topo(DEMO)}
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.TOPO_DIR, server.TOPOLOGIES = cls.orig_dir, cls.orig_topo
        cls.tmp.cleanup()

    def call(self, path, payload=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        if payload is None:
            req = urllib.request.Request(url)
        else:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as f:
            return f.status, json.loads(f.read())

    def test_upload_parses_inventory_and_sanitises_name(self):
        content = DEMO.read_text("utf-8", errors="replace")
        status, data = self.call("/api/upload",
                                 {"name": "../My Lab!.topo", "content": content})
        self.assertEqual(status, 200)
        self.assertEqual(data["name"], "My-Lab")
        self.assertGreater(len(data["rows"]), 0)
        self.assertIn("name", data["rows"][0])
        self.assertIn("manageable", data["rows"][0])
        self.assertTrue((pathlib.Path(self.tmp.name) / "My-Lab.topo").is_file())

    def test_devices_endpoint_returns_inventory(self):
        status, data = self.call("/api/devices?topo=demo")
        self.assertEqual(status, 200)
        self.assertEqual(data["name"], "demo")
        self.assertIn("rows", data)
        self.assertEqual(len(data["rows"]), data["devices"])
        self.assertIn("fingerprint", data)

    def test_devices_unknown_topology(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/devices?topo=nope")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 404)

    def test_upload_rejects_non_topo(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/upload",
            data=json.dumps({"name": "x.topo", "content": "hello"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
