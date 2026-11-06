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


class TestSessionPrepare(unittest.TestCase):
    """A fresh eNSP console swallows the first command unless warmed up."""

    def test_prepare_wakes_cli_and_disables_paging(self):
        from unittest.mock import patch
        from ensp_copilot.session import Session

        session = Session(device=None, sock=None)
        sent = []

        def fake_raw(payload, wait=1.2):
            sent.append(payload)
            return "\r\n<R1-LAB>"

        with patch.object(session, "raw", side_effect=fake_raw):
            session.prepare()
        blob = b"".join(sent)
        self.assertEqual(sent[0], b"\r\n")
        self.assertIn(b"screen-length 0 temporary", blob)
        self.assertNotIn(b"quit", blob)  # already in user view

    def test_prepare_exits_system_view(self):
        from unittest.mock import patch
        from ensp_copilot.session import Session

        session = Session(device=None, sock=None)
        replies = ["\r\n[R1-LAB]", "\r\n", "\r\n<R1-LAB>"]
        sent = []

        def fake_raw(payload, wait=1.2):
            sent.append(payload)
            return replies.pop(0) if replies else "\r\n<R1-LAB>"

        with patch.object(session, "raw", side_effect=fake_raw):
            session.prepare()
        self.assertIn(b"quit\r\n", b"".join(sent))


if __name__ == "__main__":
    unittest.main()
