"""Global follow-stream: agent activity notices + bytes from every device.

No eNSP required. The GUI follows the device currently being driven without
opening a second console socket, so these tests guard that contract.
"""
import json
import queue
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from ensp_copilot import server
from ensp_copilot.session import Session, SessionManager


class TestActiveEvent(unittest.TestCase):
    def test_event_shape(self):
        ev = server.active_event("lab", "R3", "display clock", source="agent", client="abc")
        self.assertEqual(ev["type"], "active")
        self.assertEqual(ev["topo"], "lab")
        self.assertEqual(ev["device"], "R3")
        self.assertEqual(ev["command"], "display clock")
        self.assertEqual(ev["client"], "abc")

    def test_emit_bytes_shape(self):
        # emit_bytes feeds the same Hub; verify the payload is valid JSON
        sub = server.ACTIVE.subscribe()
        try:
            server.emit_bytes("R1", "<R1>")
            payload = json.loads(sub.get(timeout=2))
        finally:
            server.ACTIVE.unsubscribe(sub)
        self.assertEqual(payload, {"type": "bytes", "device": "R1", "text": "<R1>"})


class TestActiveSSE(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_sse_delivers_announce_to_all_open_windows(self):
        url = f"http://127.0.0.1:{self.port}/events/active"
        results = [queue.Queue(), queue.Queue()]

        def reader(idx):
            try:
                with urllib.request.urlopen(url, timeout=8) as f:
                    for line in f:
                        text = line.decode("utf-8", "replace").strip()
                        if text.startswith("data:"):
                            results[idx].put(json.loads(text[5:]))
                            return
            except Exception as exc:
                results[idx].put({"error": str(exc)})

        threads = [threading.Thread(target=reader, args=(i,), daemon=True) for i in (0, 1)]
        for t in threads:
            t.start()
        deadline = time.time() + 4
        while server.ACTIVE.subscribers < 2 and time.time() < deadline:
            time.sleep(0.02)
        server.announce("demo", "R3", "display clock", source="agent")
        for i in (0, 1):
            data = results[i].get(timeout=5)
            self.assertNotIn("error", data)
            self.assertEqual(data["device"], "R3")
            self.assertEqual(data["client"], "")
            self.assertEqual(data["source"], "agent")


class TestByteMirror(unittest.TestCase):
    def test_manager_mirrors_every_session_byte_to_sink(self):
        got, ready = [], threading.Event()
        manager = SessionManager(sink=lambda name, text: (got.append((name, text)), ready.set()))
        session = Session(device=None, sock=None)  # no real socket needed
        manager._attach_forwarder("R3", session)
        try:
            session.hub.publish(b"<R3>")
            self.assertTrue(ready.wait(2), "sink was not called")
            self.assertIn(("R3", "<R3>"), got)
        finally:
            session.running = False


if __name__ == "__main__":
    unittest.main()
