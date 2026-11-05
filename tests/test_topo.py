import pathlib
import unittest

from ensp_copilot.topo import classify_model, parse_topo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "fixtures" / "demo.topo"


class TestTopo(unittest.TestCase):
    def setUp(self):
        self.topo = parse_topo(DEMO)

    def test_device_and_link_counts(self):
        self.assertEqual(len(self.topo.devices), 7)
        self.assertEqual(len(self.topo.links), 9)

    def test_com_port_is_not_sequential(self):
        ports = self.topo.by_name
        self.assertEqual(ports["R1"].port, 2006)
        self.assertEqual(ports["R2"].port, 2000)
        self.assertNotEqual(ports["R1"].port - ports["R2"].port, 1)

    def test_all_devices_manageable(self):
        self.assertEqual(len(self.topo.manageable_devices), 7)
        self.assertTrue(all(d.category == "router" for d in self.topo.devices))

    def test_fingerprint_is_stable(self):
        self.assertEqual(self.topo.fingerprint(), parse_topo(DEMO).fingerprint())
        self.assertEqual(len(self.topo.fingerprint()), 12)

    def test_fingerprint_changes_with_devices(self):
        other = parse_topo(DEMO)
        other.devices = other.devices[:-1]
        self.assertNotEqual(self.topo.fingerprint(), other.fingerprint())

    def test_classify(self):
        self.assertEqual(classify_model("Router"), ("router", True))
        self.assertEqual(classify_model("AR1220"), ("router", True))
        self.assertEqual(classify_model("Cloud"), ("cloud", False))
        self.assertEqual(classify_model("Server"), ("server", False))
        self.assertEqual(classify_model("S5700"), ("switch", True))
        self.assertEqual(classify_model("mystery-box"), ("unknown", False))

    def test_version(self):
        self.assertTrue(self.topo.version)


if __name__ == "__main__":
    unittest.main()
