"""Issue #262: Hoard keeps to Jinxxy's limit of 120 requests a minute (hoard/pace.py), however many products there
are: the requests its pages make themselves, and Hoard's own page loads and downloads."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoard import egress, pace  # noqa: E402


class Clock:
    """A clock that only moves when Hoard waits."""
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


def worst_minute(times, per=60.0):
    """The most requests sent in any minute."""
    times = sorted(times)
    return max((sum(1 for t in times[i:] if t < start + per) for i, start in enumerate(times)), default=0)


class KeepingToJinxxysLimit(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.window = pace.Window(120, 60, clock=self.clock, sleep=self.clock.sleep)
        patch = mock.patch.object(pace, "JINXXY", self.window)
        patch.start()
        self.addCleanup(patch.stop)
        quiet = mock.patch.object(pace, "tick")
        quiet.start()
        self.addCleanup(quiet.stop)

    def test_never_more_than_120_a_minute(self):
        sent = []
        for _ in range(500):   # a library of 500 products, read as fast as it's let
            pace.sending("https://api.jinxxy.com/api/v1/products")
            sent.append(self.clock.now)
        self.assertLessEqual(worst_minute(sent), 120)
        self.assertGreaterEqual(sent[-1] - sent[0], 4 * 60 - 1, "it waited, and only as long as it had to")
        self.assertLess(sent[-1] - sent[0], 4 * 60 + 5)

    def test_a_page_and_what_it_asks_for(self):
        """Before a page of Jinxxy's, room for what it asks for itself; the browser's requests are counted too."""
        handlers = {}
        ctx = SimpleNamespace(on=lambda kind, fn: handlers.setdefault(kind, fn))
        pace.count_requests(ctx)
        sent = []
        for _ in range(40):   # 40 product pages, each asking Jinxxy for 20 things itself
            pace.before("https://jinxxy.com/market/product/123")
            for _ in range(20):
                handlers["request"](SimpleNamespace(url="https://api.jinxxy.com/api/v1/x"))
                sent.append(self.clock.now)
            handlers["request"](SimpleNamespace(url="https://jinxxy-c.jinxxy-cdn.com/pic.png"))   # (its pictures: not counted)
        self.assertLessEqual(worst_minute(sent), 120)
        self.assertEqual(len(sent), 800)

    def test_only_jinxxys_own_sites(self):
        self.assertTrue(pace.jinxxy_host("https://jinxxy.com/my/inventory"))
        self.assertTrue(pace.jinxxy_host("https://api.jinxxy.com/x"))
        for other in ("https://jinxxy-c.jinxxy-cdn.com/a.png", "https://notjinxxy.com/", "https://booth.pm/ja/items/1",
                      "https://jinxxy.com.evil.example/"):
            self.assertFalse(pace.jinxxy_host(other), other)
        for _ in range(200):
            pace.before("https://booth.pm/ja/items/1")
            pace.sending("https://gumroad.com/library")
        self.assertEqual(self.clock.now, 1000.0, "other stores never wait")

    def test_waiting_says_so(self):
        """A long wait says why, now and then (which also lets Stop stop it)."""
        said = []
        with mock.patch.object(pace, "tick", said.append):
            for _ in range(121):
                pace.sending("https://jinxxy.com/x")
        self.assertTrue(said and all("120 requests a minute" in s for s in said))

    def test_hoards_own_requests_are_paced(self):
        """Every hop egress sends (a download, a read) goes through pace."""
        got = []
        with mock.patch.object(pace, "sending", got.append), \
                mock.patch("requests.Session.get", return_value=SimpleNamespace(is_redirect=False, status_code=200)):
            egress._send(egress.session(), egress.session(), "https://jinxxy.com/files/a.zip", ("jinxxy.com",))
        self.assertEqual(got, ["https://jinxxy.com/files/a.zip"])


if __name__ == "__main__":
    unittest.main()
