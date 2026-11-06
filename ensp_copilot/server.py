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
from .console import clean
from .render import render_svg
from .session import Hub, SessionManager
from .topo import parse_topo

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
TOPO_DIR = ROOT / "topologies"
PLAN_DIR = ROOT / "plans"

TOPOLOGIES: dict = {}
ACTIVE = Hub()          # one global stream: activity notices + bytes of every device
LOCK = threading.Lock()


def active_event(topo: str, device: str, command: str = "",
                 source: str = "agent", client: str = "") -> dict:
    """Tell every open GUI which device is being driven right now."""
    return {"type": "active", "topo": topo, "device": device,
            "command": command, "source": source, "client": client}


def announce(topo: str, device: str, command: str = "",
             source: str = "agent", client: str = "") -> None:
    ACTIVE.publish(json.dumps(active_event(topo, device, command, source, client),
                              ensure_ascii=False).encode("utf-8"))


def emit_bytes(device: str, text: str) -> None:
    ACTIVE.publish(json.dumps({"type": "bytes", "device": device, "text": text},
                              ensure_ascii=False).encode("utf-8"))


MANAGER = SessionManager(sink=emit_bytes)


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


def device_rows(topo) -> list[dict]:
    """Device inventory for the GUI: identity, type and whether we can drive it."""
    return [
        {
            "name": d.name,
            "model": d.model,
            "category": d.category,
            "label": d.label,
            "port": d.port,
            "manageable": d.manageable,
        }
        for d in topo.devices
    ]


def topo_summary(name: str, topo) -> dict:
    return {
        "name": name,
        "fingerprint": topo.fingerprint(),
        "devices": len(topo.devices),
        "links": len(topo.links),
        "manageable": len(topo.manageable_devices),
        "rows": device_rows(topo),
        "preview": f"/api/render?topo={name}",
    }


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
        elif path == "/api/devices":
            name = q.get("topo", [""])[0]
            t = _get_topo(name)
            if not t:
                return self._json({"error": "unknown topology"}, 404)
            self._json(topo_summary(name, t))
        elif path == "/api/render":
            name = q.get("topo", [""])[0]
            t = _get_topo(name)
            if not t:
                return self._json({"error": "unknown topology"}, 404)
            dark = q.get("dark", ["0"])[0].lower() in ("1", "true", "yes")
            self._send(render_svg(t, dark=dark).encode("utf-8"), "image/svg+xml; charset=utf-8",
                       extra={"Cache-Control": "no-store"})
        elif path == "/api/status":
            name = q.get("topo", [""])[0]
            t = _get_topo(name)
            if not t:
                return self._json({"error": "unknown topology"}, 404)
            report = env.check(t, q.get("fingerprint", [""])[0], handshake=False)
            # A listening port is NOT proof the CLI works. Replace the
            # "skipped" placeholder with a real handshake over the SINGLE
            # owned session -- a second socket would kick the live window off.
            report.checks = [c for c in report.checks
                            if not (c.name == "CLI 握手" and "跳过" in c.detail)]
            for dev in t.manageable_devices:
                try:
                    with LOCK:
                        out = MANAGER.get(dev).execute(
                            "display current-configuration | include sysname", wait=1.2)
                    text = clean(out)
                    ok = bool(text) and ("sysname" in text or "<" in out)
                    report.prompts[dev.name] = text[:120]
                    report.checks.append(env.Check(
                        f"{dev.name} CLI 握手", ok,
                        text[:80] or "无有效 VRP 回显 —— 设备可能未启动完成"))
                except OSError as exc:
                    report.checks.append(env.Check(
                        f"{dev.name} CLI 握手", False, str(exc)))
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
        elif path == "/events/active":
            self._stream_active()
        else:
            self._json({"error": "not found"}, 404)

    def _stream_active(self):
        """Single global SSE stream. Never opens a device socket."""
        sub = ACTIVE.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(b": ready\n\n")
            self.wfile.flush()
            while True:
                try:
                    payload = sub.get(timeout=10)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                else:
                    self.wfile.write(b"data: " + payload + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            ACTIVE.unsubscribe(sub)

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
        path = urlparse(self.path).path
        if path == "/api/upload":
            return self._upload(body)
        if path == "/api/command":
            return self._command(body)
        if path == "/api/plan":
            return self._apply_plan(body)
        return self._json({"error": "not found"}, 404)

    def _upload(self, body):
        """Accept a .topo as text, store it, and return the parsed inventory."""
        content = body.get("content", "")
        if not isinstance(content, str):
            return self._json({"error": "上传内容不是文本"}, 400)
        # eNSP 导出的 .topo 偶尔混入 NUL 字节（UTF-16 解码不彻底等），
        # 这里清掉以免 <dev> 被切断导致解析失败。
        if "\x00" in content:
            content = content.replace("\x00", "")
        if "<dev" not in content.lower():
            return self._json({"error": "不是有效的 .topo：缺少 <dev> 标签"}, 400)
        raw = pathlib.Path(str(body.get("name", ""))).stem
        stem = re.sub(r"[^A-Za-z0-9_-]", "-", raw).strip("-")[:64] or "uploaded-topo"
        target = TOPO_DIR / f"{stem}.topo"
        try:
            target.write_text(content, encoding="utf-8")
            topo = parse_topo(target)
        except (OSError, ValueError) as exc:
            return self._json({"error": f"写入或解析失败: {exc}"}, 400)
        if not topo.devices:
            target.unlink(missing_ok=True)
            return self._json({"error": "未解析到任何设备"}, 400)
        TOPOLOGIES[stem] = topo
        print(f"[upload] {stem}: {len(topo.devices)} devices, "
              f"{len(topo.manageable_devices)} manageable")
        return self._json(topo_summary(stem, topo))

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
        # Announce before executing: the GUI switches its view while the bytes
        # still arrive on the global stream, so nothing is lost to a re-subscribe.
        announce(body.get("topo", ""), dev.name, cmd,
                 source=str(body.get("source", "agent")),
                 client=str(body.get("client", "")))
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
                for c in commands:
                    announce(body.get("topo", ""), name, c,
                             source=str(body.get("source", "agent")),
                             client=str(body.get("client", "")))
                    results.setdefault(name, []).append((c, session.execute(c, wait=1.2)))
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
