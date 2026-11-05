import unittest

from ensp_copilot.safety import (
    diff_baseline, is_dangerous, is_readonly, validate_plan,
)


class TestSafety(unittest.TestCase):
    def test_readonly_prefix(self):
        self.assertTrue(is_readonly("display ip interface brief"))
        self.assertTrue(is_readonly("  ping -c 2 10.0.0.2"))
        self.assertFalse(is_readonly("system-view"))
        self.assertFalse(is_readonly("interface GigabitEthernet0/0/0"))

    def test_dangerous(self):
        self.assertTrue(is_dangerous("reset saved-configuration"))
        self.assertTrue(is_dangerous("save"))
        self.assertTrue(is_dangerous("undo interface LoopBack0"))
        self.assertFalse(is_dangerous("display clock"))

    def test_write_blocked_by_default(self):
        problems = validate_plan({"R1": ["system-view"]}, {"R1", "R2"})
        self.assertTrue(any("write command blocked" in p for p in problems))

    def test_write_allowed_but_dangerous_needs_confirmation(self):
        problems = validate_plan({"R1": ["save"]}, {"R1"},
                                 allow_write=True, confirmed=False)
        self.assertTrue(any("dangerous" in p for p in problems))
        self.assertEqual(validate_plan({"R1": ["save"]}, {"R1"},
                                       allow_write=True, confirmed=True), [])

    def test_unknown_device(self):
        problems = validate_plan({"R9": ["display clock"]}, {"R1"})
        self.assertTrue(any("unknown device" in p for p in problems))

    def test_readonly_plan_is_clean(self):
        self.assertEqual(
            validate_plan({"R1": ["display version", "ping -c 2 2.2.2.2"]}, {"R1"}),
            [],
        )

    def test_diff_baseline(self):
        diff = diff_baseline("sysname R1\n#", "sysname R1\nbgp 65001")
        self.assertIn("+ bgp 65001", diff)
        self.assertIn("- #", diff)


if __name__ == "__main__":
    unittest.main()
