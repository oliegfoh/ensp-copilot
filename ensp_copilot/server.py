"""Local web server: topology cards, self-check, live console stream.

Zero third-party dependencies (stdlib http.server + SSE instead of WebSocket).
Run:  python -m ensp_copilot.server --port 8765
Then open http://127.0.0.1:8765 on the SAME host as eNSP.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import queue
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import env, safety
from .render import render_svg
from .session import SessionManager
from .topo import parse_topo

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
TOPO_DIR = ROOT / "topologies"
PLAN_DIR = ROOT / "plans"

TOPOLOGIES: dict = {}
MANAGER = SessionManager()
LOCK = threading.Lock()


def load_topologies(directory: pathlib.Path) -> dict:
    result = {}
    for path in sorted(directory.glob("*.topo")):
        try:
            result[path.stem] = parse_topo(path)
        except Exception as exc:  # keep going; one broken file must not kill the UI
            print(f"[warn] cannot parse {path.name}: {exc}")
    return result


def _get_topo(name: str):
    return TOPOLOGIES.get(name)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if "/events" not in (self.path or ""):
            print("[http] " + fmt % args)

    def _send(self, body: bytes, content_type: str, code: int = 200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", code)

    def do_GET(self):
        parsed = urlparse(self.path)
        path, q = parsed.path, parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            file = WEB / "index.html"
            self._send(file.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/topologies":
            self._json([
                {
                    "name": name,
                    "path": str(t.path),
                    "fingerprint": t.fingerprint(),
                    "devices": len(t.devices),
                    "links": len(t.links),
                    "manageable": len(t.manageable_devices),
                    "preview": f"/api/render?topo={name}",
                }
                for name, t in TOPOLOGIES.items()
            ])
        elif path == "/api/render":
            name = q.get("topo", [""])[0]
            t = _get_topo(name)
            if not t:
                return self._json({"error": "unknown topology"}, 404)
            self._send(render_svg(t).encode("utf-8"), "image/svg+xml; charset=utf-8")
        elif path == "/api/status":
            name = q.get("topo", [""])[0]
            t = _get_topo(name)
            if not t:
                return self._json({"error": "unknown topology"}, 404)
            report = env.check(t, q.get("fingerprint", [""])[0], handshake=False)
            self._json(report.as_dict())
        elif path == "/api/plans":
            self._json(sorted(p.stem for p in PLAN_DIR.glob("*.json")))
        elif path == "/api/plan":
            name = q.get("name", [""])[0]
            file = PLAN_DIR / f"{name}.json"
            if not file.is_file():
                return self._json({"error": "unknown plan"}, 404)
            self._json(safety.load_plan(file))
        elif path == "/events":
            self._stream(q)
        else:
            self._json({"error": "not found"}, 404)

    def _stream(self, q):
        name, device = q.get("topo", [""])[0], q.get("device", [""])[0]
        t = _get_topo(name)
        dev = t.by_name.get(device) if t else None
        if not dev or not dev.manageable:
            return self._json({"error": "unknown or non-manageable device"}, 404)
        try:
            sub = MANAGER.subscribe(dev)
        except OSError as exc:
            return self._json({"error": f"console unavailable: {exc}"}, 503)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                try:
                    data = sub.get(timeout=10)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                else:
                    payload = json.dumps(
                        {"device": device, "text": data.decode("gbk", errors="replace")},
                        ensure_ascii=False,
                    )
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            MANAGER.unsubscribe(dev, sub)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "invalid JSON"}, 400)
        if urlparse(self.path).path == "/api/command":
            return self._command(body)
        if urlparse(self.path).path == "/api/plan":
            return self._apply_plan(body)
        return self._json({"error": "not found"}, 404)

    def _command(self, body):
        t = _get_topo(body.get("topo", ""))
        dev = t.by_name.get(body.get("device", "")) if t else None
        cmd = body.get("command", "")
        if not dev or not dev.manageable:
            return self._json({"error": "unknown or non-manageable device"}, 404)
        problems = safety.validate_plan(
            {dev.name: [cmd]}, set(t.by_name),
            allow_write=bool(body.get("allow_write")),
            confirmed=bool(body.get("confirmed")),
        )
        if problems:
            return self._json({"problems": problems}, 403)
        try:
            with LOCK:
                output = MANAGER.get(dev).execute(cmd, wait=float(body.get("wait", 1.2)))
            return self._json({
                "device": dev.name, "command": cmd, "output": output,
                "error": bool(re.search(r"Error:|Unrecognized|Wrong parameter", output)),
            })
        except OSError as exc:
            return self._json({"error": str(exc)}, 503)

    def _apply_plan(self, body):
        t = _get_topo(body.get("topo", ""))
        if not t:
            return self._json({"error": "unknown topology"}, 404)
        file = PLAN_DIR / f"{body.get('name','')}.json"
        if not file.is_file():
            return self._json({"error": "unknown plan"}, 404)
        plan = safety.load_plan(file)
        problems = safety.validate_plan(
            plan, set(t.by_name),
            allow_write=bool(body.get("allow_write")),
            confirmed=bool(body.get("confirmed")),
        )
        if problems:
            return self._json({"problems": problems}, 403)
        results = {}
        with LOCK:
            for name, commands in plan.items():
                dev = t.by_name[name]
                session = MANAGER.get(dev)
                results[name] = [(c, session.execute(c, wait=1.2)) for c in commands]
        return self._json({"applied": results})


def main():
    ap = argparse.ArgumentParser(description="ensp-copilot local server")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--topo-dir", type=pathlib.Path, default=TOPO_DIR)
    args = ap.parse_args()
    global TOPOLOGIES, PLAN_DIR
    TOPOLOGIES = load_topologies(args.topo_dir)
    PLAN_DIR = ROOT / "plans"
    print(f"loaded {len(TOPOLOGIES)} topologies, serving http://127.0.0.1:{args.port}")
    print("requires eNSP running on THIS host with devices started")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        MANAGER.close_all()
        server.server_close()


if __name__ == "__main__":
    main()
