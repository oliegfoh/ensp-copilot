"""One TCP console per device, with tee broadcast.

HARD CONSTRAINT: eNSP allows exactly ONE connection to each device console.
A live-view window must never open its own socket -- it subscribes to the Hub
owned by the single Session. The executor and the UI therefore see the very
same byte stream.
"""
from __future__ import annotations

import queue
import socket
import threading
import time
from dataclasses import dataclass, field

from .console import HOST, PROMPT_RE


class Hub:
    """Fan-out raw bytes to any number of subscribers. Pure in-memory, testable."""

    def __init__(self):
        self._subs: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=4096)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    def publish(self, data: bytes) -> None:
        with self._lock:
            targets = list(self._subs)
        for q in targets:
            try:
                q.put_nowait(data)
            except queue.Full:
                pass

    @property
    def subscribers(self) -> int:
        with self._lock:
            return len(self._subs)


def collect(q: queue.Queue, seconds: float = 1.2) -> str:
    """Collect bytes from a subscriber until the stream goes quiet."""
    buf = b""
    end = time.time() + seconds
    while time.time() < end:
        try:
            buf += q.get(timeout=0.25)
            end = time.time() + 0.35
        except queue.Empty:
            pass
    return buf.decode("gbk", errors="replace")


@dataclass
class Session:
    device: object
    sock: socket.socket
    hub: Hub = field(default_factory=Hub)
    write_lock: threading.Lock = field(default_factory=threading.Lock)
    running: bool = True
    _thread: threading.Thread | None = None

    def start(self) -> "Session":
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return self

    def _reader(self) -> None:
        self.sock.settimeout(0.25)
        while self.running:
            try:
                data = self.sock.recv(4096)
                if data:
                    self.hub.publish(data)
                elif data == b"":
                    break
            except socket.timeout:
                continue
            except OSError:
                break

    def raw(self, payload: bytes, wait: float = 1.2) -> str:
        with self.write_lock:
            q = self.hub.subscribe()
            try:
                self.sock.sendall(payload)
                return collect(q, wait)
            finally:
                self.hub.unsubscribe(q)

    def prepare(self) -> str:
        """Warm up a freshly opened console.

        eNSP emits a prompt (sometimes a few handshake bytes) right after a TCP
        connection is accepted. Without this warm-up the FIRST command gets
        swallowed and its "reply" is only that prompt -- a false positive that
        looks exactly like a working device. Also normalises the CLI to user
        view and disables paging. All bytes still reach live subscribers.
        """
        banner = ""
        for _ in range(6):
            raw = self.raw(b"\r\n", wait=0.6)
            banner += raw
            prompts = PROMPT_RE.findall(raw.replace("\r", ""))
            if not prompts or prompts[-1].startswith("<"):
                break
            self.raw(b"quit\r\n", wait=0.5)
        self.raw(b"screen-length 0 temporary\r\n", wait=0.6)
        return banner

    def execute(self, cmd: str, wait: float = 1.2) -> str:
        return self.raw(("\r\n" + cmd + "\r\n").encode(), wait)

    def close(self) -> None:
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass


class SessionManager:
    """Lazily create and own exactly one Session per device.

    ``sink`` is an optional callback ``(device_name, text)`` that receives every
    byte from EVERY session. It lets the GUI follow whatever device the agent
    is currently driving without opening a second socket or re-subscribing
    (which would lose bytes). The live window and the executor stay on the
    same stream.
    """

    def __init__(self, host: str = HOST, sink=None):
        self.host = host
        self.sink = sink
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, device) -> Session:
        with self._lock:
            session = self._sessions.get(device.name)
            if session and session.running:
                return session
            sock = socket.create_connection((self.host, device.port), timeout=4)
            session = Session(device=device, sock=sock).start()
            session.prepare()
            self._sessions[device.name] = session
        # Attach outside the lock. Warm-up bytes are deliberately not mirrored:
        # they are handshake noise, not commands the user asked to watch.
        if self.sink:
            self._attach_forwarder(device.name, session)
        return session

    def _attach_forwarder(self, name: str, session: Session) -> None:
        q = session.hub.subscribe()

        def pump():
            while session.running:
                try:
                    data = q.get(timeout=0.4)
                except queue.Empty:
                    continue
                try:
                    self.sink(name, data.decode("gbk", errors="replace"))
                except Exception:
                    pass  # a broken UI sink must never take down the console

        threading.Thread(target=pump, daemon=True, name=f"tee-{name}").start()

    def subscribe(self, device) -> queue.Queue:
        return self.get(device).hub.subscribe()

    def unsubscribe(self, device, q: queue.Queue) -> None:
        self.get(device).hub.unsubscribe(q)

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.close()
