import queue
import unittest

from ensp_copilot.session import Hub, collect


class TestHub(unittest.TestCase):
    def test_broadcast_to_all_subscribers(self):
        hub = Hub()
        a, b = hub.subscribe(), hub.subscribe()
        self.assertEqual(hub.subscribers, 2)
        hub.publish(b"hello")
        self.assertEqual(a.get_nowait(), b"hello")
        self.assertEqual(b.get_nowait(), b"hello")

    def test_unsubscribe(self):
        hub = Hub()
        a, b = hub.subscribe(), hub.subscribe()
        hub.unsubscribe(a)
        hub.publish(b"x")
        self.assertTrue(a.empty())
        self.assertEqual(b.get_nowait(), b"x")

    def test_publish_without_subscribers_is_noop(self):
        Hub().publish(b"nothing")

    def test_collect(self):
        hub = Hub()
        q = hub.subscribe()
        hub.publish(b"<R1>display clock\r\n")
        hub.publish(b"2026-11-05\r\n")
        output = collect(q, seconds=0.5)
        self.assertIn("display clock", output)
        self.assertIn("2026-11-05", output)


if __name__ == "__main__":
    unittest.main()
