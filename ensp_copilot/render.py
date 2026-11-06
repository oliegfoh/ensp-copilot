"""Render a .topo into a standalone SVG preview (offline, no eNSP needed).

Shape encodes device category; stroke style encodes whether the agent can
operate it (solid = CLI manageable, dashed grey = GUI-only / no console).
``dark=True`` produces a palette that matches the GUI's dark theme.
"""
from __future__ import annotations

from html import escape

from .topo import Topology

WIDTH, HEIGHT, PAD = 680, 300, 34

LIGHT = {
    "bg": "#FFFFFF", "fill": "#E6F1FB", "dimfill": "#F1EFE8",
    "stroke": "#185FA5", "text": "#0C447C", "muted": "#888780",
    "dash": "#B4B2A9",
}
DARK = {
    "bg": "#1a1f2a", "fill": "#2a3350", "dimfill": "#242936",
    "stroke": "#8fa8ff", "text": "#dce3f7", "muted": "#98a3b8",
    "dash": "#5a6478",
}


def _scaled(topo: Topology):
    xs = [d.cx for d in topo.devices] or [0]
    ys = [d.cy for d in topo.devices] or [0]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    sx = (WIDTH - 2 * PAD) / max(x1 - x0, 1)
    sy = (HEIGHT - 2 * PAD - 30) / max(y1 - y0, 1)
    s = min(sx, sy, 1.4)
    return {d.id: (PAD + (d.cx - x0) * s, PAD + (d.cy - y0) * s) for d in topo.devices}


def _shape(d, x: float, y: float, p: dict) -> str:
    """Return SVG markup for one device node."""
    solid = d.manageable
    stroke = p["stroke"] if solid else p["dash"]
    fill = p["fill"] if solid else p["dimfill"]
    dash = "" if solid else ' stroke-dasharray="3 3"'
    common = f'fill="{fill}" stroke="{stroke}" stroke-width="1"{dash}'
    cat = d.category
    if cat == "router":
        body = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" {common}/>'
    elif cat == "switch":
        body = f'<rect x="{x-13:.1f}" y="{y-9:.1f}" width="26" height="18" rx="3" {common}/>'
    elif cat == "firewall":
        pts = f"{x:.1f},{y-12:.1f} {x+12:.1f},{y-6:.1f} {x+12:.1f},{y+6:.1f} {x:.1f},{y+12:.1f} {x-12:.1f},{y+6:.1f} {x-12:.1f},{y-6:.1f}"
        body = f'<polygon points="{pts}" {common}/>'
    elif cat == "wireless":
        body = f'<polygon points="{x:.1f},{y-12:.1f} {x+12:.1f},{y+9:.1f} {x-12:.1f},{y+9:.1f}" {common}/>'
    elif cat == "pc":
        body = f'<rect x="{x-9:.1f}" y="{y-9:.1f}" width="18" height="18" rx="2" {common}/>'
    elif cat == "server":
        body = f'<rect x="{x-8:.1f}" y="{y-14:.1f}" width="16" height="28" rx="2" {common}/>'
    elif cat == "cloud":
        body = (f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="16" ry="10" {common}/>'
                f'<circle cx="{x-8:.1f}" cy="{y-5:.1f}" r="7" {common}/>')
    else:
        body = f'<polygon points="{x:.1f},{y-11:.1f} {x+11:.1f},{y:.1f} {x:.1f},{y+11:.1f} {x-11:.1f},{y:.1f}" {common}/>'
    label_color = p["text"] if solid else p["muted"]
    title = (f'<title>{escape(d.name)} · {escape(d.model)} · {escape(d.label)}'
             f' · console {d.port if d.port else "n/a"}</title>')
    text = (f'<text x="{x:.1f}" y="{y+26:.1f}" text-anchor="middle" '
            f'font-size="11" fill="{label_color}">{escape(d.name)}</text>')
    return f"<g>{title}{body}{text}</g>"


def render_svg(topo: Topology, dark: bool = False) -> str:
    p = DARK if dark else LIGHT
    pos = _scaled(topo)
    by_id = {d.id: d for d in topo.devices}
    parts = [
        f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" width="100%" role="img" '
        'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{escape(topo.path.stem)}</title>",
        f"<desc>{len(topo.devices)} devices, {len(topo.links)} links</desc>",
        f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{p["bg"]}" rx="8"/>',
    ]
    for link in topo.links:
        if link.src_id in pos and link.dst_id in pos:
            x1, y1 = pos[link.src_id]
            x2, y2 = pos[link.dst_id]
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                         f'y2="{y2:.1f}" stroke="{p["stroke"]}" stroke-width="1"/>')
    for d in topo.devices:
        x, y = pos[d.id]
        parts.append(_shape(d, x, y, p))
    manage = len(topo.manageable_devices)
    parts.append(
        f'<text x="{PAD}" y="{HEIGHT-12}" font-size="11" fill="{p["muted"]}">'
        f'{len(topo.devices)} 台设备 · {len(topo.links)} 条链路 · '
        f'{manage} 台可 CLI 操作（实线） · 虚线灰显为 GUI 专用</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
