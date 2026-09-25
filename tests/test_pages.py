"""Hoard's two pages in a real browser: they reach the server only with this run's access key. Skipped when
Playwright's Chromium isn't installed (python -m playwright install chromium); GitHub Actions installs it, so
these run on every change.
"""
from __future__ import annotations

import hashlib
import json
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

    def test_an_update_is_offered(self):
        """A newer version from the last check shows in the footer and in Settings; this copy (not the installed
        app) links to the release instead of offering to install it."""
        self.srv.updates.state["latest"] = {"version": "99.0.0", "url": "https://github.com/Soloflighter1010/"
                                            "Hoard-Asset-Manager/releases/tag/v99.0.0", "notes": "", "published": "",
                                            "has_installer": True}
        self.addCleanup(self.srv.updates.state.update, latest=None)
        page, refused = self.open(self.srv.entry_url())
        page.get_by_role("button", name="Update to 99.0.0").wait_for()
        page.click("#updateNote")
        page.get_by_text("Hoard 99.0.0 is available").wait_for()
        self.assertTrue(page.locator("#updInstall").is_hidden(), "only the installed app installs it")
        self.assertTrue(page.locator("#updLink").is_visible())
        self.assertFalse(page.locator("#setUpdates").is_checked(), "automatic checks are off unless turned on")
        self.assertEqual(refused, [])
        page.close()

    def test_a_used_link_doesnt_work_again(self):
        link = self.srv.entry_url()
        first, _ = self.open(link)
        first.get_by_text("Rusk").first.wait_for()
        first.close()
        again, _ = self.open(link)
        again.get_by_text(NEEDS_KEY).wait_for()
        again.close()


def shop_page(*codes):
    """A Payhip shop's own library page (testshop.store/b-account)."""
    return ('<html><head><meta charset="utf-8"><title>Dashboard - Test Shop</title></head><body><header>'
            '<a class="logo-link" href="https://testshop.store/b-account">Test Shop</a></header><div class="grid-list">'
            + "".join(f'<div class="grid-item"><img src="https://images.payhip.com/{c}.gif" width="200" height="200">'
                      f'<h4 class="product-name"><a href="https://testshop.store/b-account/digital/{c}">Product {c}</a></h4></div>'
                      for c in codes) + '</div></body></html>')


def mhtml(page_html: str, url: str) -> bytes:
    """A page saved as "Webpage, Single File"."""
    return ("From: <Saved by Blink>\r\nSnapshot-Content-Location: " + url + "\r\nMIME-Version: 1.0\r\n"
            'Content-Type: multipart/related; type="text/html"; boundary="B"\r\n\r\n--B\r\nContent-Type: text/html\r\n'
            "Content-Location: " + url + "\r\n\r\n" + page_html + "\r\n--B--\r\n").encode()


ITCH_SAVED = ('<!-- saved from url=(0028)https://itch.io/my-purchases -->\n<html><body><div class="game_grid_widget">'
              '<div class="game_cell" data-game_id="1001"><a class="title game_link" href="https://kitsu.itch.io/paw-suit">Paw Suit</a>'
              '<div class="game_author"><a href="https://kitsu.itch.io">Kitsu</a></div>'
              '<a class="button" href="https://kitsu.itch.io/paw-suit/download/AbCdEf1234567890">Download</a></div></div></body></html>')


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class ImportingFromTheLibrary(unittest.TestCase):
    """Import pages, in the Stores panel: several saved pages at once, a new Payhip shop's pages confirmed with one
    question, and what came of every page shown at the end."""

    def test_several_pages_at_once(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = {**config.load_config(), "root": str(tmp / "downloads"), "setup_done": True, "offline_images": False}
        cfg["payhip"] = {**cfg["payhip"], "shops": []}
        srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False, config_path=tmp / "config.json")
        srv.lib = library.Library(tmp / "library.json")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: config.apply_store_sites(config.load_config()))
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        pw = sync_playwright().start()
        self.addCleanup(pw.stop)
        browser = pw.chromium.launch()
        self.addCleanup(browser.close)
        page = browser.new_page()
        asked = []
        page.on("dialog", lambda d: (asked.append(d.message), d.accept()))
        page.goto(srv.entry_url())
        page.locator("#storesBtn").click()
        page.locator("#importPages").wait_for()
        page.set_input_files("#importFile", [
            {"name": "Dashboard - Test Shop.mhtml", "mimeType": "multipart/related",
             "buffer": mhtml(shop_page("aB1", "cD2"), "https://testshop.store/b-account")},
            {"name": "Dashboard - Test Shop (2).mhtml", "mimeType": "multipart/related",
             "buffer": mhtml(shop_page("eF3"), "https://testshop.store/b-account?page=2")},
            {"name": "My purchases - itch.io.html", "mimeType": "text/html", "buffer": ITCH_SAVED.encode()},
            {"name": "notes.html", "mimeType": "text/html", "buffer": b"<html><body>notes</body></html>"},
            {"name": "readme.txt", "mimeType": "text/plain", "buffer": b"not a page"},
        ])
        page.locator("#impClose").wait_for(state="visible", timeout=90000)
        said, problems = page.locator("#impMessage").inner_text(), page.locator("#impProblems").inner_text()
        self.assertEqual(len(asked), 1, "one question for the new shop, for both its pages")
        self.assertIn("2 pages are from a Payhip shop", asked[0])
        self.assertIn("testshop.store", asked[0])
        for part in ("3 Payhip items", "1 itch.io item", "from 3 pages", "Added testshop.store to your Payhip shops"):
            self.assertIn(part, said)
        self.assertIn("notes.html: couldn't tell which store", problems)
        self.assertIn("1 file isn't a saved page", problems)
        self.assertEqual(json.loads((tmp / "config.json").read_text("utf-8"))["payhip"]["shops"], ["https://testshop.store"])
        page.get_by_text("Product eF3").first.wait_for()   # in the library straight away
        self.assertEqual(sorted(i["key"] for i in srv.lib.data["items"]),
                         ["itch:1001", "payhip:testshop.store:aB1", "payhip:testshop.store:cD2", "payhip:testshop.store:eF3"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class HighlightsAndAccessibility(unittest.TestCase):
    """The open item stays marked, things you own twice have striped spines, and the Accessibility settings
    apply to the page: text size, reduced motion, and animated pictures paused as stills."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": cls.tmp.name, "setup_done": True},
                                   lan=False)
        with cls.srv.lib.lock:   # in memory only
            cls.srv.lib.data["items"] = [
                library.item("booth", "111", name="Rusk", creator="Kitsu Studio", thumbnail=THUMB),
                library.item("gumroad", "abc", name="Rusk", creator="Kitsu Studio"),
                library.item("booth", "222", name="Mochi", creator="Kitsu Studio")]
        library.THUMB_DIR.mkdir(parents=True, exist_ok=True)
        cls.cached = library.THUMB_DIR / (hashlib.sha1(THUMB.encode()).hexdigest() + ".png")
        cls.cached.write_bytes(png())
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

    def setUp(self):
        self.srv.cfg["display"] = {"text_size": 100, "pause_animations": False, "reduce_motion": False}

    def open(self):
        page = self.browser.new_page()
        page.goto(self.srv.entry_url())
        page.get_by_text("Mochi").first.wait_for()
        return page

    def test_the_open_item_is_marked(self):
        page = self.open()
        mochi = page.locator(".slot", has_text="Mochi")
        mochi.click()
        page.locator("#detail.open").wait_for()
        self.assertEqual(mochi.get_attribute("aria-current"), "true")
        self.assertEqual(page.locator('.slot[aria-current="true"]').count(), 1)
        page.locator(".slot", has_text="Rusk").first.click()
        self.assertIsNone(mochi.get_attribute("aria-current"), "only the one that's open")
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.querySelector('.slot[aria-current]')")
        page.close()

    def test_owned_twice_is_striped(self):
        page = self.open()
        rusk = page.locator(".slot", has_text="Rusk")
        self.assertEqual(rusk.count(), 2)
        for i in range(2):
            self.assertIn("dup", rusk.nth(i).locator(".notch").get_attribute("class"))
            self.assertIn("also on", rusk.nth(i).get_attribute("aria-label"))
        self.assertNotIn("dup", page.locator(".slot", has_text="Mochi").locator(".notch").get_attribute("class"))
        page.close()

    def test_display_settings(self):
        self.srv.cfg["display"] = {"text_size": 130, "pause_animations": True, "reduce_motion": True}
        page = self.open()
        self.assertEqual(page.evaluate("document.documentElement.style.zoom"), "1.3")
        self.assertTrue(page.evaluate("document.body.classList.contains('less-motion')"))
        page.wait_for_function("() => !!document.querySelector('.slot canvas.still')")
        self.assertEqual(page.locator(".slot img").count(), 0, "every picture is a still")
        # turned off from Settings: the pictures move again, straight away
        from playwright.sync_api import expect
        page.click("#settingsBtn")
        # uncheck() reads the box straight away, so wait for Settings to have filled it in first
        expect(page.locator("#setPause")).to_be_checked()
        page.locator("#setPause").uncheck()
        page.locator("#setMotion").uncheck()
        page.select_option("#setTextSize", "100")
        page.click("#setSave")
        page.wait_for_function("() => !document.querySelector('canvas.still')")
        self.assertEqual(page.evaluate("document.documentElement.style.zoom"), "")
        self.assertFalse(page.evaluate("document.body.classList.contains('less-motion')"))
        self.assertEqual(self.srv.cfg["display"], {"text_size": 100, "pause_animations": False, "reduce_motion": False})
        page.close()
