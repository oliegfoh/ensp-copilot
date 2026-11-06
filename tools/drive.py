"""Drive eNSP devices through the local copilot API.

Why a dedicated script instead of ad-hoc curl:
  - eNSP allows ONE console socket per device. The copilot server already owns
    that socket, so we MUST go through /api/command (never open our own).
  - The very FIRST command sent to a freshly created session tends to be
    swallowed (only the prompt comes back). We send a harmless `return` warm-up
    before the real commands so nothing important is lost.

Usage:
  python tools/drive.py verify_ip [topo]
  python tools/drive.py run <plan.json> [--allow-write] [--confirmed] [--topo test]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"

# Interface-index -> physical port name, recovered from the .topo link GUIDs.
# Confirmed earlier: GE0/0/0..GE0/0/3 map to link indices 2..5 on each router.
PORTS = ["GE0/0/0", "GE0/0/1", "GE0/0/2", "GE0/0/3"]


def cmd(topo, device, command, allow_write=False, confirmed=False, wait=1.6):
    body = json.dumps({
        "topo": topo, "device": device, "command": command,
        "allow_write": allow_write, "confirmed": confirmed, "wait": wait,
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/command", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}"}
    except Exception as e:  # network / timeout
        return {"error": str(e)}


def run_plan(topo, plan, allow_write=False, confirmed=False):
    """plan: {device: [commands]}. Warm-up each device once, then run commands."""
    results = {}
    for device, commands in plan.items():
        outs = []
        # warm-up: absorb the first-command swallow
        cmd(topo, device, "return", wait=0.8)
        for c in commands:
            r = cmd(topo, device, c, allow_write=allow_write, confirmed=confirmed)
            outs.append({"command": c,
                         "output": r.get("output", ""),
                         "error": r.get("error", False),
                         "err": r.get("error", "")})
        results[device] = outs
    return results


def verify_ip(topo="test"):
    plan = {f"R{i}": ["display current-configuration | include ip address"]
            for i in range(1, 8)}
    res = run_plan(topo, plan)
    print(f"=== Step-1 IP config on {topo} (running-config) ===")
    for dev, outs in res.items():
        out = outs[0]["output"] if outs else ""
        lines = [l.strip() for l in out.splitlines()
                 if "ip address" in l or "interface" in l.lower()]
        print(f"\n[{dev}]")
        if not lines:
            print("  (no ip address lines found)")
        for l in lines:
            print("  " + l)


def save_all(topo="test"):
    """Checkpoint: write running-config to startup on every router.

    VRP `save` is interactive ([Y/N]). The copilot's executable wraps every
    command with a leading \\r\\n, which the [Y/N] prompt reads as an empty
    (invalid) answer; the trailing `Y` then confirms. Harmless but noisy.
    """
    print(f"=== save running-config -> startup on {topo} ===")
    for i in range(1, 8):
        dev = f"R{i}"
        cmd(topo, dev, "return", wait=0.8)  # warm-up: absorb first-command swallow
        r1 = cmd(topo, dev, "save", allow_write=True, confirmed=True, wait=2.5)
        r2 = cmd(topo, dev, "Y", allow_write=True, wait=3.0)
        ok = "Now saving" in (r1.get("output", "") + r2.get("output", ""))
        print(f"  [{dev}] {'OK' if ok else 'CHECK'}: "
              f"{r2.get('output','')[-90:].strip()!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["verify_ip", "run", "save_all"])
    ap.add_argument("arg", nargs="?", default="test")
    ap.add_argument("--topo", default="test")
    ap.add_argument("--allow-write", action="store_true")
    ap.add_argument("--confirmed", action="store_true")
    args = ap.parse_args()

    if args.action == "verify_ip":
        verify_ip(args.topo)
    elif args.action == "run":
        plan_path = Path(args.arg)
        plan = json.loads(plan_path.read_text("utf-8"))
        res = run_plan(args.topo, plan,
                       allow_write=args.allow_write, confirmed=args.confirmed)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.action == "save_all":
        save_all(args.topo)


if __name__ == "__main__":
    main()
