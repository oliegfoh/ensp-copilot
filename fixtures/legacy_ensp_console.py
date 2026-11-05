#!/usr/bin/env python3
"""eNSP Console over TCP helper. Pure stdlib (Python 3.13 has no telnetlib).

Reads device name / model / com_port from a .topo XML, then talks to each
device over the raw TCP console exposed by eNSP_Client.

Examples:
  python ensp_console.py --list
  python ensp_console.py --check
  python ensp_console.py --cmd "display ip interface brief" --all
  python ensp_console.py --cmd "display version" --devices R1,R3 --log out.txt
  python ensp_console.py --file commands.txt --devices R1 --allow-write
"""
import argparse
import json
import pathlib
import re
import socket
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_TOPO = pathlib.Path(__file__).resolve().parent.parent / "topologies" / "dual-as-dual-flow.topo"
HOST = "127.0.0.1"
READONLY_PREFIX = ("display", "ping", "tracert", "screen-length", "quit", "?", "show")


def parse_topo(path):
    text = pathlib.Path(path).read_text("utf-8", errors="replace")
    devs = []
    for tag in re.findall(r"<dev\s+[^>]*>", text):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
        if "id" not in attrs:
            continue
        devs.append({
            "name": attrs.get("name", "?"),
            "model": attrs.get("model", "?"),
            "port": int(attrs.get("com_port", "0")),
            "id": attrs["id"],
        })
    return devs


def drain(sock, seconds=1.2):
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
    return buf.decode("gbk", errors="replace")


def clean(out):
    lines = []
    for line in out.replace("\r", "").split("\n"):
        t = line.strip()
        if not t:
            continue
        if re.fullmatch(r"[<\[].*[>\]]", t):
            continue
        lines.append(t)
    return "\n".join(lines)


class Console:
    def __init__(self, port, timeout=4):
        self.sock = socket.create_connection((HOST, port), timeout=timeout)
        self.sock.settimeout(0.25)

    def send(self, cmd, wait=1.2):
        self.sock.sendall(("\r\n" + cmd + "\r\n").encode())
        return drain(self.sock, wait)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def probe(port):
    try:
        with socket.create_connection((HOST, port), timeout=1.0):
            return True
    except OSError:
        return False


def to_user_view(con):
    """eNSP keeps the CLI view across console sessions; normalize to user view."""
    for _ in range(6):
        raw = con.send("", wait=0.6).replace("\r", "")
        prompts = re.findall(r"^\s*([<\[][^>\]\r\n]+[>\]])\s*$", raw, re.M)
        if not prompts or prompts[-1].startswith("<"):
            return
        con.send("quit", wait=0.5)


def run_on(dev, commands, allow_write, wait):
    for cmd in commands:
        if not allow_write and not cmd.strip().lower().startswith(READONLY_PREFIX):
            raise PermissionError("non-readonly command blocked: " + cmd)
    con = Console(dev["port"])
    to_user_view(con)
    banner = clean(con.send("", wait=0.8))
    con.send("screen-length 0 temporary", wait=0.8)
    results = []
    for cmd in commands:
        results.append((cmd, clean(con.send(cmd, wait=wait))))
    con.close()
    return banner, results


def main():
    ap = argparse.ArgumentParser(description="eNSP Console over TCP helper")
    ap.add_argument("--topo", default=DEFAULT_TOPO)
    ap.add_argument("--list", action="store_true", help="list devices and ports")
    ap.add_argument("--probe", action="store_true", help="probe console ports")
    ap.add_argument("--check", action="store_true", help="verify every device is reachable")
    ap.add_argument("--cmd", action="append", default=[], help="command to run (repeatable)")
    ap.add_argument("--file", help="file with one command per line")
    ap.add_argument("--devices", help="comma-separated device names")
    ap.add_argument("--all", action="store_true", help="target every device")
    ap.add_argument("--allow-write", action="store_true", help="permit non-readonly commands")
    ap.add_argument("--wait", type=float, default=1.2, help="seconds to collect each reply")
    ap.add_argument("--log", help="append full session transcript to this file")
    ap.add_argument("--plan", help="JSON file: {device: [commands]} applied per device")
    args = ap.parse_args()

    devs = parse_topo(args.topo)
    devs = [d for d in devs if d["port"] > 0]

    if args.list or args.probe:
        for d in devs:
            state = ("OK" if probe(d["port"]) else "DOWN") if args.probe else ""
            print(f'{d["name"]:<8} {d["model"]:<10} 127.0.0.1:{d["port"]:<6} {state}')
        return

    if args.check:
        ok = 0
        for d in devs:
            try:
                banner, res = run_on(d, ["display current-configuration | include sysname",
                                         "display version | include VRP"], True, args.wait)
                joined = " ".join(x[1] for x in res)
                good = bool(joined.strip()) or bool(banner.strip())
                ok += good
                print(f'{"OK" if good else "FAIL":<5} {d["name"]:<8} :{d["port"]:<6} '
                      f'prompt={banner[:40]!r} reply={joined[:110]!r}')
            except Exception as exc:
                print(f'FAIL  {d["name"]:<8} :{d["port"]:<6} {type(exc).__name__}: {exc}')
        print(f"\nreachable: {ok}/{len(devs)}")
        return

    if args.plan:
        plan = json.loads(pathlib.Path(args.plan).read_text("utf-8"))
        by_name = {d["name"]: d for d in devs}
        unknown = set(plan) - set(by_name)
        if unknown:
            ap.error("unknown device(s) in plan: " + ", ".join(sorted(unknown)))
        transcript, all_ok = [], True
        for name, cmds in plan.items():
            d = by_name[name]
            print(f'\n===== {name} ({HOST}:{d["port"]}) =====')
            try:
                _, results = run_on(d, cmds, args.allow_write, args.wait)
                for cmd, out in results:
                    print(f'> {cmd}\n{out}')
                    transcript.append(f'===== {name} =====\n> {cmd}\n{out}\n')
                    if re.search(r"Error:|Unrecognized|Wrong parameter|Incomplete", out, re.I):
                        all_ok = False
            except Exception as exc:
                all_ok = False
                print(f'ERROR: {type(exc).__name__}: {exc}')
                transcript.append(f'===== {name} =====\nERROR: {exc}\n')
        if args.log:
            pathlib.Path(args.log).write_text("\n".join(transcript), encoding="utf-8")
        status = "all OK" if all_ok else "ERRORS DETECTED"
        print(f"\nplan applied to {len(plan)} devices: {status}")
        return

    commands = list(args.cmd)
    if args.file:
        commands += [l.strip() for l in pathlib.Path(args.file).read_text(
            "utf-8", errors="replace").splitlines() if l.strip() and not l.startswith("#")]
    if not commands:
        ap.error("nothing to do: use --list / --probe / --check / --cmd / --file")

    targets = devs
    if args.devices and not args.all:
        wanted = {x.strip() for x in args.devices.split(",")}
        targets = [d for d in devs if d["name"] in wanted]
        missing = wanted - {d["name"] for d in devs}
        if missing:
            ap.error("unknown device(s): " + ", ".join(sorted(missing)))
    if not args.all and not args.devices:
        ap.error("specify --all or --devices")

    transcript = []
    for d in targets:
        print(f'\n===== {d["name"]} ({HOST}:{d["port"]}) =====')
        try:
            _, results = run_on(d, commands, args.allow_write, args.wait)
            for cmd, out in results:
                print(f'> {cmd}\n{out}')
                transcript.append(f'===== {d["name"]} =====\n> {cmd}\n{out}\n')
        except Exception as exc:
            print(f'ERROR: {type(exc).__name__}: {exc}')
            transcript.append(f'===== {d["name"]} =====\nERROR: {exc}\n')

    if args.log:
        pathlib.Path(args.log).write_text("\n".join(transcript), encoding="utf-8")
        print(f"\ntranscript written to {args.log}")


if __name__ == "__main__":
    main()
