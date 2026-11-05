"""Environment self-check before any command is sent to a device.

Never trust com_port from the .topo alone: eNSP may reassign ports when the
file is opened. Always verify with a real port scan plus a CLI handshake.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .console import HOST, clean, probe, run_on
from .topo import Topology


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    topo: str
    checks: list[Check] = field(default_factory=list)
    fingerprint_expected: str = ""
    fingerprint_actual: str = ""
    reachable: list[str] = field(default_factory=list)
    prompts: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def as_dict(self) -> dict:
        return {
            "topo": self.topo,
            "ready": self.ready,
            "fingerprint_expected": self.fingerprint_expected,
            "fingerprint_actual": self.fingerprint_actual,
            "reachable": self.reachable,
            "prompts": self.prompts,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail}
                       for c in self.checks],
        }


def check(
    topo: Topology,
    expected_fingerprint: str = "",
    host: str = HOST,
    handshake: bool = True,
) -> Report:
    report = Report(
        topo=str(topo.path),
        fingerprint_expected=expected_fingerprint,
        fingerprint_actual=topo.fingerprint(),
    )
    report.checks.append(Check(
        "topo 解析", bool(topo.devices),
        f"{len(topo.devices)} 台设备 / {len(topo.links)} 条链路",
    ))

    managed = topo.manageable_devices
    report.checks.append(Check(
        "存在可操作设备", bool(managed),
        f"{len(managed)} 台具备 console + CLI",
    ))

    if expected_fingerprint:
        match = expected_fingerprint == topo.fingerprint()
        report.checks.append(Check(
            "拓扑指纹匹配", match,
            "一致" if match else f"期望 {expected_fingerprint}，实际 {topo.fingerprint()} —— 可能打开了别的方案",
        ))

    live = []
    for d in managed:
        if probe(d.port, host=host):
            live.append(d.name)
        else:
            report.checks.append(Check(
                f"{d.name} 端口监听", False,
                f"{host}:{d.port} 未监听 —— 设备是否已启动？",
            ))
    if live:
        report.checks.append(Check(
            "端口监听", len(live) == len(managed),
            f"{len(live)}/{len(managed)} 台在线: {', '.join(live)}",
        ))
    report.reachable = live

    if handshake:
        for d in managed:
            if d.name not in live:
                continue
            try:
                _, results = run_on(
                    d, ["display current-configuration | include sysname"], wait=1.2
                )
                text = clean(results[0][1])
                report.prompts[d.name] = text[:120]
                report.checks.append(Check(
                    f"{d.name} CLI 握手", bool(text), text[:80] or "无回显",
                ))
            except OSError as exc:
                report.checks.append(Check(
                    f"{d.name} CLI 握手", False, str(exc),
                ))
    else:
        report.checks.append(Check("CLI 握手", True, "已跳过（离线模式）"))

    return report
