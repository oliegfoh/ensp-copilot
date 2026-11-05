"""Raw TCP transport for an eNSP device console.

eNSP_Client exposes each started device's serial console as a plain TCP
character stream on 127.0.0.1:<com_port>. No telnetlib (removed in 3.13),
no paramiko, no SSH, no Cloud device, no management IP.
"""
from __future__ import annotations

import re
import socket
import time

HOST = "127.0.0.1"
VRP_ERROR_RE = re.compile(r"Error:|Unrecognized|Wrong parameter|Incomplete", re.I)
PROMPT_RE = re.compile(r"^\s*([<\[][^>\]\r\n]+[>\]])\s*$", re.M)


def drain(sock: socket.socket, seconds: float = 1.2) -> str:
    """Collect output until quiet for a while. VRP pushes async logs mid-reply."""
    buf = b""
    end = time.time() + seconds
    sock.settimeout(0.25)
    while time.time() < end:
        try:
            chunk = sock.recv(8192)
            if chunk:
                buf += chunk
                end = time.time() + 0.35
        except socket.timeout:
            pass
        except OSError:
            break
    return buf.decode("gbk", errors="replace")


def clean(text: str) -> str:
    """Strip blank lines and bare prompt lines; keep everything else."""
    lines = []
    for line in text.replace("\r", "").split("\n"):
        stripped = line.strip()
        if not stripped or re.fullmatch(r"[<\[].*[>\]]", stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def has_vrp_error(text: str) -> bool:
    return bool(VRP_ERROR_RE.search(text))


class Console:
    def __init__(self, port: int, host: str = HOST, timeout: float = 4.0):
        self.port = port
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(0.25)

    def raw(self, payload: bytes, wait: float = 1.0) -> str:
        """Send exact bytes. Needed for Y/N prompts where a leading CRLF breaks input."""
        self.sock.sendall(payload)
        return drain(self.sock, wait)

    def send(self, cmd: str, wait: float = 1.2) -> str:
        return self.raw(("\r\n" + cmd + "\r\n").encode(), wait)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def probe(port: int, host: str = HOST, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def to_user_view(con: Console) -> None:
    """eNSP keeps the CLI view across console sessions; normalize to user view.

    Only send 'quit' when a bracketed (system/interface) prompt was actually
    seen -- 'quit' at user view would drop the connection.
    """
    for _ in range(6):
        raw = con.send("", wait=0.6).replace("\r", "")
        prompts = PROMPT_RE.findall(raw)
        if not prompts or prompts[-1].startswith("<"):
            return
        con.send("quit", wait=0.5)


def prepare(con: Console) -> str:
    to_user_view(con)
    banner = clean(con.send("", wait=0.8))
    con.send("screen-length 0 temporary", wait=0.8)
    return banner


def run_on(dev, commands: list[str], wait: float = 1.2) -> tuple[str, list[tuple[str, str]]]:
    """Run commands on one device. Caller is responsible for safety checks."""
    with Console(dev.port) as con:
        banner = prepare(con)
        results = [(cmd, clean(con.send(cmd, wait=wait))) for cmd in commands]
    return banner, results


def save_config(port: int) -> str:
    """Interactive `save`: VRP asks [Y/N] then optionally for a filename."""
    with Console(port) as con:
        to_user_view(con)
        parts = [
            con.raw(b"save\r\n", 1.2),
            con.raw(b"y\r\n", 1.0),
            con.raw(b"\r\n", 3.5),
        ]
        time.sleep(2.0)
    return "".join(parts)
