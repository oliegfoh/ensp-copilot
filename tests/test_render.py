import pathlib
import unittest

from ensp_copilot.render import render_svg
from ensp_copilot.topo import parse_topo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "fixtures" / "demo.topo"


class TestRender(unittest.TestCase):
    def setUp(self):
        self.svg = render_svg(parse_topo(DEMO))

    def test_is_svg(self):
        self.assertTrue(self.svg.startswith("<svg"))
        self.assertTrue(self.svg.rstrip().endswith("</svg>"))

    def test_contains_every_device(self):
        for name in ("R1", "R2", "R3", "R4", "R5", "R6", "R7"):
            self.assertIn(name, self.svg)

    def test_contains_links_and_legend(self):
        self.assertEqual(self.svg.count("<line"), 9)
        self.assertIn("可 CLI 操作", self.svg)

    def test_manageable_nodes_are_solid(self):
        # demo.topo has 7 routers, all with a console -> no dashed (GUI-only) nodes
        self.assertNotIn("stroke-dasharray", self.svg)
        self.assertIn("7 台可 CLI 操作", self.svg)

    def test_gui_only_nodes_are_dashed(self):
        topo = parse_topo(DEMO)
        cloud = topo.devices[0].__class__(
            id="fake", name="CLOUD1", model="Cloud", port=0,
            cx=0, cy=0, category="cloud", has_cli=False,
        )
        topo.devices.append(cloud)
        self.assertIn("stroke-dasharray", render_svg(topo))


if __name__ == "__main__":
    unittest.main()
