"""Parse Huawei eNSP ``.topo`` files into devices, links and canvas layout.

The format is plain XML but is not documented by Huawei. Everything here was
reverse-engineered from real files. See ``docs/topo-format.md``.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
from dataclasses import dataclass, field

# (regex on lowercased model, category, provides a CLI)
MODEL_RULES = (
    (r"cloud|hub", "cloud", False),
    (r"server|client", "server", False),
    (r"usg|firewall|fw", "firewall", True),
    (r"^s\d|switch|s5700|s3700", "switch", True),
    (r"^ap|^ac|wlan", "wireless", True),
    (r"^pc|vpc", "pc", True),
    (r"router|^ar\d|^ne\d|^ce\d", "router", True),
)

CATEGORY_LABELS = {
    "router": "路由器",
    "switch": "交换机",
    "firewall": "防火墙",
    "wireless": "无线设备",
    "pc": "终端",
    "server": "服务器/客户端",
    "cloud": "云/透传",
    "unknown": "未识别",
}

_ATTR = re.compile(r'([\w]+)="([^"]*)"')


def classify_model(model: str) -> tuple[str, bool]:
    """Return (category, has_cli). Unknown models are treated as non-manageable."""
    text = (model or "").strip().lower()
    for pattern, category, has_cli in MODEL_RULES:
        if re.search(pattern, text):
            return category, has_cli
    return "unknown", False


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    model: str
    port: int
    cx: float
    cy: float
    mac: str = ""
    category: str = "unknown"
    has_cli: bool = False

    @property
    def manageable(self) -> bool:
        """A device is manageable only if a console port is exposed and a CLI exists."""
        return self.port > 0 and self.has_cli

    @property
    def label(self) -> str:
        return CATEGORY_LABELS.get(self.category, "未识别")


@dataclass(frozen=True)
class Link:
    src_id: str
    dst_id: str
    src_if: int = 0
    dst_if: int = 0
    line_name: str = ""


@dataclass
class Topology:
    path: pathlib.Path
    version: str = ""
    devices: list[Device] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    shapes: list[dict] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)

    @property
    def manageable_devices(self) -> list[Device]:
        return [d for d in self.devices if d.manageable]

    @property
    def by_name(self) -> dict[str, Device]:
        return {d.name: d for d in self.devices}

    def fingerprint(self) -> str:
        """Stable identity: guards against the user opening a different .topo."""
        key = "|".join(
            f"{d.name}:{d.model}" for d in sorted(self.devices, key=lambda x: x.name)
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _attrs(fragment: str) -> dict[str, str]:
    return dict(_ATTR.findall(fragment))


def parse_topo(path) -> Topology:
    path = pathlib.Path(path)
    text = path.read_text("utf-8", errors="replace")
    topo = Topology(path=path)

    m = re.search(r"<topo\s+([^>]*)>", text)
    if m:
        topo.version = _attrs(m.group(1)).get("version", "")

    for tag in re.findall(r"<dev\s+[^>]*>", text):
        a = _attrs(tag)
        if "id" not in a:
            continue
        category, has_cli = classify_model(a.get("model", ""))
        topo.devices.append(Device(
            id=a["id"],
            name=a.get("name", "?"),
            model=a.get("model", "?"),
            port=int(a.get("com_port", "0") or 0),
            cx=float(a.get("cx", "0") or 0),
            cy=float(a.get("cy", "0") or 0),
            mac=a.get("system_mac", ""),
            category=category,
            has_cli=has_cli,
        ))

    for m in re.finditer(r"<line\s+([^>]*)>(.*?)</line>", text, re.S):
        a, body = _attrs(m.group(1)), m.group(2)
        pair = re.search(r"<interfacePair\s+([^>]*)/?>", body)
        p = _attrs(pair.group(1)) if pair else {}
        topo.links.append(Link(
            src_id=a.get("srcDeviceID", ""),
            dst_id=a.get("destDeviceID", ""),
            src_if=int(p.get("srcIndex", "0") or 0),
            dst_if=int(p.get("tarIndex", "0") or 0),
            line_name=p.get("lineName", ""),
        ))

    topo.shapes = [_attrs(t) for t in re.findall(r"<shape\s+[^>]*/?>", text)]
    topo.tips = re.findall(r'<txttip[^>]*\scontent="([^"]*)"', text)
    return topo
