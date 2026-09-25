"""Hoard's two pages in a real browser: they reach the server only with this run's access key. Skipped when
Playwright's Chromium isn't installed (python -m playwright install chromium); GitHub Actions installs it, so
these run on every change.
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import config, downloader, library, server  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _p.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

THUMB = "https://booth.pximg.net/c/test/rusk.png"
NEEDS_KEY = "Hoard didn't recognise this page"
LOADED = "kind => [...document.images].some(i => i.src.includes(kind) && i.complete && i.naturalWidth === 1)"


def png() -> bytes:
    """A 1x1 PNG, so an image that loaded can be told from one that was refused."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" * 5)) + chunk(b"IEND", b""))


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class AccessKey(unittest.TestCase):
    """S-01: Hoard opens its page with a one-time link, which the page trades for the access key; from then on
    every request carries the key, the pictures included. A page without it gets nothing and says what to do."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        folder = root / "Booth" / "Kitsu Studio" / "Rusk"
        folder.mkdir(parents=True)
        (folder / "rusk.zip").write_bytes(b"zip")
        (folder / "_thumbnail.png").write_bytes(png())
        man = downloader.Manifest(root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Rusk")
        rec.update(name="Rusk", creator="Kitsu Studio", url="https://booth.pm/ja/items/111")
        rec["files"]["f1"] = {"path": "rusk.zip", "size": 3}
        man.save()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True},
                                   lan=False)
        with cls.srv.lib.lock:   # in memory only: the test never writes your library
            cls.srv.lib.data["items"] = [library.item("booth", "111", name="Rusk", creator="Kitsu Studio", thumbnail=THUMB)]
        library.THUMB_DIR.mkdir(parents=True, exist_ok=True)
        cls.cached = library.THUMB_DIR / (hashlib.sha1(THUMB.encode()).hexdigest() + ".png")
        cls.cached.write_bytes(png())   # already cached, so nothing is fetched from the internet
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.cached.unlink(missing_ok=True)
        cls.tmp.cleanup()

    def open(self, url):
        """url in a browser of its own (nothing kept from another test), noting every refused request."""
        page = self.browser.new_page()
        refused = []
        page.on("response", lambda r: refused.append(r.url) if r.status == 401 else None)
        page.goto(url)
        return page, refused

    def test_a_one_time_link_lets_both_pages_in(self):
        page, refused = self.open(self.srv.entry_url())
        page.get_by_text("Rusk").first.wait_for()
        page.wait_for_function(LOADED, arg="/thumb/")
        self.assertNotIn("enter=", page.url, "the link leaves the address straight away")
        self.assertEqual(page.evaluate("localStorage.getItem('hoard-key')"), self.srv.key)
        page.click("nav.apptabs a[href='/downloads']")
        page.wait_for_url("**/downloads**")
        page.get_by_text("Rusk").first.wait_for()
        page.wait_for_function(LOADED, arg="/files/")
        self.assertEqual(refused, [])
        page.close()

    def test_the_address_hoard_serve_prints(self):
        page, refused = self.open(f"{self.srv.url}#key={self.srv.key}")
        page.get_by_text("Rusk").first.wait_for()
        self.assertNotIn("key=", page.url, "the key leaves the address straight away")
        self.assertEqual(refused, [])
        page.close()

    def test_without_the_key_nothing_is_shown(self):
        for url in (self.srv.url, f"{self.srv.url}downloads", f"{self.srv.url}#key=guess"):
            page, refused = self.open(url)
            page.get_by_text(NEEDS_KEY).wait_for()
            self.assertEqual(page.get_by_text("Rusk").count(), 0, url)
            self.assertTrue(refused, url)
            page.close()

    def test_a_used_link_doesnt_work_again(self):
        link = self.srv.entry_url()
        first, _ = self.open(link)
        first.get_by_text("Rusk").first.wait_for()
        first.close()
        again, _ = self.open(link)
        again.get_by_text(NEEDS_KEY).wait_for()
        again.close()


if __name__ == "__main__":
    unittest.main()
