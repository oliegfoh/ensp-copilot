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

from .console import HOST


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

    def execute(self, cmd: str, wait: float = 1.2) -> str:
        return self.raw(("\r\n" + cmd + "\r\n").encode(), wait)

    def close(self) -> None:
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass


class SessionManager:
    """Lazily create and own exactly one Session per device."""

    def __init__(self, host: str = HOST):
        self.host = host
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, device) -> Session:
        with self._lock:
            session = self._sessions.get(device.name)
            if session and session.running:
                return session
            sock = socket.create_connection((self.host, device.port), timeout=4)
            session = Session(device=device, sock=sock).start()
            self._sessions[device.name] = session
            return session

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
