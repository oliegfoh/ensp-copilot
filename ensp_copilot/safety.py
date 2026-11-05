"""Guardrails: read-only by default, plan validation, dangerous-command gate."""
from __future__ import annotations

import json
import pathlib
import re

READONLY_PREFIX = (
    "display", "ping", "tracert", "screen-length", "quit", "return", "?", "show",
)
DANGEROUS_PATTERNS = (
    r"^\s*reset\s+saved-configuration",
    r"^\s*reboot\b",
    r"^\s*format\b",
    r"^\s*delete\b",
    r"^\s*undo\s+",
    r"^\s*save\b",
    r"^\s*startup\s+saved-configuration",
)


def is_readonly(cmd: str) -> bool:
    return cmd.strip().lower().startswith(READONLY_PREFIX)


def is_dangerous(cmd: str) -> bool:
    return any(re.search(p, cmd, re.I) for p in DANGEROUS_PATTERNS)


def load_plan(path) -> dict[str, list[str]]:
    data = json.loads(pathlib.Path(path).read_text("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("plan must be a JSON object: {device: [commands]}")
    return {str(k): [str(c) for c in v] for k, v in data.items()}


def validate_plan(
    plan: dict[str, list[str]],
    known_devices: set[str],
    allow_write: bool = False,
    confirmed: bool = False,
) -> list[str]:
    """Return a list of problems. Empty list means the plan is safe to execute."""
    problems: list[str] = []
    unknown = set(plan) - known_devices
    if unknown:
        problems.append("unknown device(s): " + ", ".join(sorted(unknown)))
    for device, commands in plan.items():
        if not commands:
            problems.append(f"{device}: empty command list")
        for cmd in commands:
            if not is_readonly(cmd):
                if not allow_write:
                    problems.append(f"{device}: write command blocked -> {cmd}")
                elif is_dangerous(cmd) and not confirmed:
                    problems.append(f"{device}: dangerous command needs confirmation -> {cmd}")
    return problems


def baseline_commands() -> list[str]:
    """Export before mutating anything, so a rollback is always possible."""
    return ["display current-configuration"]


def diff_baseline(before: str, after: str) -> list[str]:
    """Cheap line-level diff between two `display current-configuration` outputs."""
    old = set(before.splitlines())
    new = set(after.splitlines())
    return sorted(f"- {x}" for x in old - new) + sorted(f"+ {x}" for x in new - old)
