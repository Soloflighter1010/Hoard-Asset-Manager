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
from unittest import mock
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

    def test_settings_say_which_browser_signs_in(self):
        """Issue #20: Settings says which browser Hoard really signs in with. A chosen browser that isn't installed
        is stood in for by Hoard's own, and that used to happen without a word."""
        from hoard import browser as hb
        self.addCleanup(self.srv.cfg.update, browser_channel=self.srv.cfg.get("browser_channel", ""))
        with mock.patch.object(server, "save_config"), \
                mock.patch.object(hb, "channel_installed", lambda channel: channel == "msedge"):
            page, refused = self.open(self.srv.entry_url())
            page.get_by_text("Rusk").first.wait_for()
            for url in (None, f"{self.srv.url}downloads"):
                if url:
                    page.goto(url)
                    page.get_by_text("Rusk").first.wait_for()
                page.click("#settingsBtn")
                page.locator("#settingsPanel:not([hidden])").wait_for()
                page.select_option("#setBrowser", "chrome")
                self.assertEqual(page.locator("#browserInUse").inner_text(),
                                 "Google Chrome isn't installed on this computer, so Hoard signs in with its own browser.")
                page.select_option("#setBrowser", "msedge")
                self.assertEqual(page.locator("#browserInUse").inner_text(), "Hoard signs in with Microsoft Edge.")
                page.select_option("#setBrowser", "chromium")
                self.assertEqual(page.locator("#browserInUse").inner_text(), "Hoard signs in with Hoard's own browser.")
                page.locator("#settingsPanel .win-extra", has_text="Saved").wait_for()   # saved as it's chosen
                for _ in range(50):
                    if self.srv.cfg["browser_channel"] == "chromium":
                        break
                    page.wait_for_timeout(100)
                self.assertEqual(self.srv.cfg["browser_channel"], "chromium", "the choice is saved")
                page.locator("#settingsPanel .win-x").click()
                self.srv.cfg["browser_channel"] = ""
    def test_the_downloads_page_has_the_librarys_views(self):
        """Issue #29: archiving an item in the Library moves its download to the Downloads page's Archive view,
        as in the Library, instead of leaving no way to tell it apart."""
        from hoard import marks, tags
        st, rusk = marks.MarkStore(), tags.tag_key("booth", "Rusk")
        page, refused = self.open(self.srv.entry_url())
        page.get_by_text("Rusk").first.wait_for()
        st.change("archived", {rusk}, True)   # as the Library's Archive button does
        self.addCleanup(st.change, "archived", {rusk}, False)
        page.goto(f"{self.srv.url}downloads")
        page.locator("#views [data-view='archive']").wait_for()
        self.assertEqual(page.locator("#views [data-view]").all_inner_texts(), ["Downloads\n0", "Updates\n0", "Archive\n1"])
        self.assertEqual(page.locator("#grid .slot").count(), 0, "not among the other downloads")
        self.assertEqual(page.locator("#creators li").count(), 0, "nor counted under its creator here")
        self.assertIn("1 thing, ", page.locator("#totals").inner_text())
        self.assertIn("archived, removed or hidden", page.locator("#empty").inner_text())
        page.click("#views [data-view='archive']")
        page.locator("#grid .slot").first.wait_for()
        self.assertIn("Rusk", page.locator("#grid .slot").first.get_attribute("aria-label"))
        self.assertEqual(page.locator("#count").inner_text(), "1 thing archived")
        self.assertIn("view=archive", page.evaluate("location.hash"))
        page.reload()
        page.locator("#grid .slot").first.wait_for()
        self.assertEqual(page.locator("#views [aria-checked='true']").inner_text(), "Archive\n1", "kept on reload")
        self.assertEqual(refused, [])

    def test_updates_view_and_updating_one(self):
        """Issue #26: what a check for updates found shows in the Downloads page's Updates view, on the card and in
        the details, with Update (just that product) and Check for updates; the Library's details link to it."""
        from hoard import tags
        from hoard.asset_updates import AssetUpdates
        rusk = tags.tag_key("booth", "Rusk")
        store = AssetUpdates()
        store.record_check(["booth"], None, [{"store": "booth", "key": rusk, "name": "Rusk", "creator": "Kitsu Studio",
                                              "file": "Rusk_v2.zip", "kind": "new"}])
        self.addCleanup(store.path.unlink, missing_ok=True)
        started = []

        def start(task, stores, skip_imported=False, only=None, scheduled=False, keys=None, **_kw):
            started.append((task, stores, keys))
            return True
        with mock.patch.object(self.srv.jobs, "start", side_effect=start):
            page, refused = self.open(self.srv.entry_url())
            page.get_by_text("Rusk").first.click()
            page.get_by_role("link", name="Update available").wait_for()
            page.goto(f"{self.srv.url}downloads")
            page.locator("#views [data-view='updates']").wait_for()
            self.assertEqual(page.locator("#views [data-view='updates']").inner_text(), "Updates\n1")
            page.click("#views [data-view='updates']")
            self.assertIn("1 download has newer files", page.locator("#viewBar").inner_text())
            self.assertIn("Last checked", page.locator("#viewBar").inner_text())
            page.locator("#grid .slot .flag.upd").wait_for()
            page.click("#grid .slot")
            self.assertIn("Rusk_v2.zip", page.locator("#detail .update").inner_text())
            page.click("#detail [data-act='update-one']")
            page.wait_for_function("() => !document.querySelector('#dlPanel').hidden")
            page.click("#detail [data-act='check-one']")
            for _ in range(50):
                if len(started) >= 2:
                    break
                page.wait_for_timeout(100)
            page.click("#viewBar [data-upd='check']")
            for _ in range(50):
                if len(started) >= 3:
                    break
                page.wait_for_timeout(100)
        self.assertEqual(started, [("download", ["booth"], [rusk]), ("check-updates", ["booth"], [rusk]),
                                   ("check-updates", list(server.STORES), None)])
        self.assertEqual(refused, [])

    def test_downloaded_or_not_yet(self):
        """Issue #17: in the Library, what's on disk is marked on its card and in its label, and Downloaded / Not
        downloaded yet filter the library, with counts, kept in the address like the other filters."""
        with self.srv.lib.lock:
            before = list(self.srv.lib.data["items"])
            self.srv.lib.data["items"] = before + [library.item("gumroad", "zz", name="Mochi", creator="Kitsu Studio")]
        self.addCleanup(lambda: self.srv.lib.data.update(items=before))
        page, refused = self.open(self.srv.entry_url())
        page.get_by_text("Mochi").first.wait_for()
        rusk, mochi = page.locator(".slot", has_text="Rusk"), page.locator(".slot", has_text="Mochi")
        self.assertEqual(rusk.locator(".ondisk-mark").count(), 1)
        self.assertEqual(mochi.locator(".ondisk-mark").count(), 0)
        self.assertIn(", downloaded", rusk.get_attribute("aria-label"))
        self.assertNotIn("downloaded", mochi.get_attribute("aria-label"))
        self.assertEqual(page.locator("#disk [data-disk]").all_inner_texts(), ["Downloaded1", "Not downloaded yet1"])

        page.click("#disk [data-disk='no']")
        self.assertEqual(page.locator("#grid .slot .nm-t").all_inner_texts(), ["Mochi"])
        self.assertEqual(page.locator("#disk [data-disk='no']").get_attribute("aria-pressed"), "true")
        self.assertIn("Not downloaded yet", page.locator("#status").inner_text())
        self.assertIn("downloaded=no", page.url)
        page.reload()
        page.get_by_text("Mochi").first.wait_for()
        self.assertEqual(page.locator("#grid .slot .nm-t").all_inner_texts(), ["Mochi"], "kept in the address")
        page.click("#disk [data-disk='yes']")
        self.assertEqual(page.locator("#grid .slot .nm-t").all_inner_texts(), ["Rusk"])
        page.click("#status [data-clear='disk']")
        self.assertEqual(sorted(page.locator("#grid .slot .nm-t").all_inner_texts()), ["Mochi", "Rusk"])
        self.assertEqual(refused, [])

    def test_the_downloads_page_has_the_update_setting(self):
        """Issue #28: Check for updates is in the Downloads page's Settings too, and saving it there keeps it."""
        from playwright.sync_api import expect
        self.addCleanup(self.srv.cfg.update, check_for_updates=bool(self.srv.cfg.get("check_for_updates")))
        self.srv.cfg["check_for_updates"] = False
        with mock.patch.object(server, "save_config"):   # the test never writes your settings
            page, refused = self.open(self.srv.entry_url())
            page.get_by_text("Rusk").first.wait_for()
            page.goto(f"{self.srv.url}downloads")
            page.get_by_text("Rusk").first.wait_for()
            page.click("#settingsBtn")
            page.locator("#setUpdates").wait_for()
            page.get_by_text("You have Hoard").wait_for()   # its status, as on the Library page
            expect(page.locator("#setUpdates")).not_to_be_checked()
            page.locator("#setUpdates").check()
            page.locator("#settingsPanel .win-extra", has_text="Saved").wait_for()   # saved as it's changed
            self.assertTrue(self.srv.cfg["check_for_updates"])
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


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class LargeLibrary(unittest.TestCase):
    """Only the cards near the screen are drawn (review finding P-02), and nothing else notices."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": cls.tmp.name, "setup_done": True},
                                   lan=False)
        with cls.srv.lib.lock:   # in memory only
            cls.srv.lib.data["items"] = [library.item("booth", str(n), name=f"Item {n:04d}", creator=f"Creator {n % 40}")
                                         for n in range(1000)]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def open(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(self.srv.entry_url())
        page.locator(".slot").first.wait_for()
        return page

    @staticmethod
    def drawn(page) -> int:
        return page.locator("#grid .slot").count()

    def scroll_until(self, page, at_least: int):
        for _ in range(100):
            if self.drawn(page) >= at_least:
                return
            page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            page.wait_for_timeout(50)
        self.fail(f"only {self.drawn(page)} cards drawn after scrolling")

    def wait_for(self, page, ok):
        for _ in range(100):
            if ok(self.drawn(page)):
                return
            page.wait_for_timeout(50)
        self.fail(f"{self.drawn(page)} cards drawn")

    def test_only_what_is_near_the_screen_is_drawn(self):
        page = self.open()
        page.wait_for_timeout(300)
        self.assertLessEqual(self.drawn(page), 240, "a batch or two, not all 1,000")
        self.scroll_until(page, 1000)
        self.assertEqual(self.drawn(page), 1000, "scrolling draws them all")
        page.close()

    def test_search_and_a_redraw(self):
        page = self.open()
        page.fill("#q", "Item 0999")   # (waited for from here: Hoard's policy won't let a page evaluate strings)
        self.wait_for(page, lambda n: n == 1)
        page.fill("#q", "")
        self.wait_for(page, lambda n: n >= 120)
        self.scroll_until(page, 480)
        before = self.drawn(page)
        page.evaluate("render()")   # what a tag change or a finished job does
        self.assertGreaterEqual(self.drawn(page), before, "a redraw doesn't jump back to the top")
        page.close()

    def test_the_downloads_page_too(self):
        from unittest import mock
        catalog = [{"store": "Booth", "name": f"Item {n:04d}", "creator": f"Creator {n % 40}",
                    "folder": f"Creator {n % 40}/Item {n:04d}", "files": []} for n in range(1000)]
        with mock.patch.object(server, "collect_catalog", lambda cfg, root: (catalog, None)):
            self.srv.forget_index()
            page = self.open()
            page.goto(self.srv.url + "downloads")
            page.locator("#grid .slot").first.wait_for()
            page.wait_for_timeout(300)
            self.assertLessEqual(self.drawn(page), 240)
            self.scroll_until(page, 1000)
            self.assertEqual(self.drawn(page), 1000)
            page.close()

    def test_select_all_marks_cards_drawn_later(self):
        page = self.open()
        page.click("#selectBtn")
        page.click("#bulkAll")
        self.assertEqual(page.locator("#bulkCount").inner_text(), "1000 selected")
        self.scroll_until(page, 600)
        self.assertEqual(page.locator('#grid .slot:not([aria-pressed="true"])').count(), 0)
        page.close()


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

    SAMPLE_SPLASH = """window.__splash = 0;   // how visible the splash got, sampled as the page loads
        setInterval(() => { const e = document.getElementById("splash");
                            if (e) window.__splash = Math.max(window.__splash, +getComputedStyle(e).opacity); }, 25);"""

    def test_the_splash_screen(self):
        """Issue #50: the logo shows while the window's first page reads your library, for at least a moment, then
        goes; later pages only show it when reading takes a while; and it goes even when reading fails."""
        import time
        page = self.browser.new_page()
        page.add_init_script(self.SAMPLE_SPLASH)
        began = time.monotonic()
        page.goto(self.srv.entry_url())
        self.assertIn("first", page.locator("#splash").get_attribute("class") or "")
        page.get_by_text("Mochi").first.wait_for(state="attached")
        page.locator("#splash").wait_for(state="detached")
        self.assertGreater(time.monotonic() - began, 1.1, "on screen for a moment, not a flicker")
        self.assertEqual(page.evaluate("window.__splash"), 1)
        page.get_by_text("Mochi").first.click()   # nothing in the way once it's gone

        # a later page (the same window): not straight away; only once reading takes a while
        page.goto(f"{self.srv.url}downloads")
        self.assertNotIn("first", page.locator("#splash").get_attribute("class") or "")
        page.locator("#splash").wait_for(state="detached")

        def slow(route):
            time.sleep(1.0)
            route.continue_()
        page.route("**/api/library*", slow)
        page.goto(f"{self.srv.url}")
        page.locator("#splash").wait_for(state="detached", timeout=10000)
        self.assertEqual(page.evaluate("window.__splash"), 1, "shown while reading took a while")
        page.close()

        page = self.browser.new_page()   # a new window whose library can't be read
        page.route("**/api/library*", lambda route: route.abort())
        page.goto(self.srv.entry_url())
        page.locator("#splash").wait_for(state="detached", timeout=10000)
        page.close()

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

    def test_locking_closes_a_hidden_items_details(self):
        """Issue #23: locking the hidden library closes the open hidden item's details and empties them."""
        from hoard import marks
        store = marks.MarkStore()
        self.addCleanup(store.path.unlink, missing_ok=True)
        store.set_pin("2468")
        mochi = next(i for i in self.srv.lib.data["items"] if i["name"] == "Mochi")
        store.change("hidden", {library.tag_key(mochi["store"], mochi["name"])}, True)
        page = self.browser.new_page()
        page.goto(self.srv.entry_url())
        page.get_by_text("Rusk").first.wait_for()
        page.click('#views [data-view="hidden"]')
        page.fill("#pinInput", "2468")
        page.click("#pinOk")
        page.locator(".slot", has_text="Mochi").click()
        page.locator("#detail.open").wait_for()
        page.click('#viewBar [data-privacy="lock"]')
        page.get_by_text("Hidden items locked.").wait_for()
        self.assertEqual(page.locator("#detail.open").count(), 0, "the details closed with the lock")
        self.assertNotIn("Mochi", page.locator("#detail").inner_html(), "and nothing of the item is left in them")
        self.assertEqual(page.get_by_text("Mochi").count(), 0)
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
        page.select_option("#setTextSize", "100")   # each saved as it's changed
        page.wait_for_function("() => !document.querySelector('canvas.still')")
        page.wait_for_function("() => document.documentElement.style.zoom === ''")
        self.assertEqual(page.evaluate("document.documentElement.style.zoom"), "")
        self.assertFalse(page.evaluate("document.body.classList.contains('less-motion')"))
        self.assertEqual(self.srv.cfg["display"], {"text_size": 100, "pause_animations": False, "reduce_motion": False})
        page.close()


    def test_the_largest_text_still_fits_the_window(self):
        """Issue #48: at the Largest text size, Settings (and everything else sized to the window) grew taller and
        wider than the window, so you couldn't scroll to Save to make the text smaller again."""
        from unittest import mock
        fits = """() => {
          const out = [];
          for (const el of document.querySelectorAll("#settingsPanel, .side")) {
            if (el.hidden || getComputedStyle(el).display === "none") continue;
            el.scrollTop = el.scrollHeight;   // as far down as it goes
            const r = el.getBoundingClientRect();
            if (r.bottom > innerHeight + 1 || r.right > innerWidth + 1) out.push(`${el.id || el.className}: ${Math.round(r.right)}x${Math.round(r.bottom)}`);
          }
          const x = document.querySelector("#settingsPanel .win-x").getBoundingClientRect();   // it can be closed
          if (x.bottom > innerHeight + 1 || x.right > innerWidth + 1) out.push(`close at ${Math.round(x.right)}x${Math.round(x.bottom)}`);
          const body = document.querySelector("#settingsPanel .win-body");
          body.scrollTop = body.scrollHeight;   // and scrolled to the end, its last line shows
          const end = document.querySelector("#setupAgain").getBoundingClientRect();
          if (end.bottom > innerHeight + 1) out.push(`the end of Settings at ${Math.round(end.bottom)}`);
          return out;
        }"""
        with mock.patch.object(server, "save_config"):
            page = self.open()
            page.set_viewport_size({"width": 1000, "height": 640})
            page.click("#settingsBtn")
            page.wait_for_function("() => document.querySelector('#setTextSize').value === '100'")
            page.select_option("#setTextSize", "150")   # saved and applied as it's chosen
            page.wait_for_function("() => document.documentElement.style.zoom === '1.5'")
            for where in ("library", "downloads"):
                if where == "downloads":
                    page.goto(f"{self.srv.url}downloads")
                    page.wait_for_function("() => document.documentElement.style.zoom === '1.5'")
                if page.locator("#settingsPanel").is_hidden():
                    page.click("#settingsBtn")
                page.locator("#setTextSize").wait_for()
                self.assertEqual(page.evaluate(fits), [], where)
            page.select_option("#setTextSize", "100")   # and the text size can be put back from there
            page.wait_for_function("() => document.documentElement.style.zoom === ''")
            page.close()

@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class SetupAssistant(unittest.TestCase):
    """Issue #34: a sign-in started from the setup assistant keeps going if the assistant is closed, and the
    library page has to pick it up; before, nothing watched it any more and the item counts stayed at 0."""

    def test_closing_the_assistant_during_a_sign_in(self):
        """Run again from Settings (the first time through, it can't be closed: see the next test)."""
        import time
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": tmp.name, "setup_done": True},
                               lan=False)
        done = threading.Event()

        def sign_in(task, stores, **_kw):   # stands in for the sign-in window and the reading after it
            def run():
                srv.jobs.state.update(running=True, task="login", store=stores[0], message="Waiting for you to sign in")
                done.wait(20)
                srv.lib.replace_store(stores[0], [library.item(stores[0], f"k{i}", name=f"Thing {i}", creator="Kitsu")
                                                  for i in range(4)])
                srv.jobs.state.update(running=False, task=None, message="Library updated")
            threading.Thread(target=run, daemon=True).start()
            return True

        with srv.lib.lock:
            srv.lib.data["items"], srv.lib.data["stores"] = [], {}
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with sync_playwright() as p, mock.patch.object(srv.jobs, "start", side_effect=sign_in), \
                mock.patch.object(srv.lib, "save"):   # in memory only, as elsewhere here
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(srv.entry_url())
            page.wait_for_function("() => typeof openSetup === 'function' && document.readyState === 'complete'")
            page.evaluate("openSetup()")   # Set up Hoard, from Settings
            page.locator("#setup:not([hidden])").wait_for()
            for _ in range(8):   # each step saves on the way out: wait for the next one before going on
                if page.locator('#setupBody [data-signin="gumroad"]').count():
                    break
                title = page.locator("#setupTitle").inner_text()
                page.click("#setupNext")
                page.wait_for_function("t => document.querySelector('#setupTitle').textContent !== t", arg=title)
            page.click('#setupBody [data-signin="gumroad"]')
            page.wait_for_function("() => /sign in/i.test(document.querySelector('#signinProgress').textContent)")
            page.keyboard.press("Escape")   # closed while the sign-in is still going
            self.assertTrue(page.locator("#setup").is_hidden())
            time.sleep(1.5)
            done.set()
            page.locator("#storeSeg", has_text="Gumroad").wait_for(timeout=10000)
            self.assertIn("4", page.locator('#storeSeg [data-store="gumroad"]').inner_text())
            self.assertEqual(page.locator(".slot").count(), 4)
            browser.close()


    def test_the_first_time_it_goes_through_to_the_end(self):
        """Issue #21: the first time Hoard starts, the assistant can't be skipped or closed; a step that isn't done
        holds you there (no browser, no store picked), and going on without a sign-in asks first."""
        from hoard import setup
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": tmp.name, "setup_done": False},
                               lan=False)
        with srv.lib.lock:   # a first start: nothing in the library yet, so the assistant opens by itself
            srv.lib.data["items"], srv.lib.data["stores"] = [], {}
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        ready = {"value": False}
        status = lambda cfg: {"channel": "chromium", "name": "Hoard's browser", "ready": ready["value"],  # noqa: E731
                              "can_install": not ready["value"], "note": ""}
        with sync_playwright() as p, mock.patch.object(setup, "browser_status", status), \
                mock.patch.object(server, "save_config"), mock.patch.object(setup, "signed_in", lambda cfg, s: False):
            browser = p.chromium.launch()
            page = browser.new_page()
            asked = []

            def answer(d):
                asked.append(d.message)
                d.accept() if len(asked) > 1 else d.dismiss()
            page.on("dialog", answer)
            page.goto(srv.entry_url())
            page.locator("#setup:not([hidden])").wait_for()
            self.assertTrue(page.locator("#setupSkip").is_hidden(), "no Skip the first time")
            page.keyboard.press("Escape")
            self.assertTrue(page.locator("#setup").is_visible(), "and Escape doesn't close it")
            page.click("#setupNext")   # welcome
            page.locator("#setupTitle", has_text="The browser Hoard signs in with").wait_for()
            page.click("#setupNext")
            page.get_by_text("Install Hoard's browser first").wait_for()
            self.assertIn("browser", page.locator("#setupTitle").inner_text(), "held on the step")
            ready["value"] = True
            page.evaluate("setupStatus()")
            page.click("#setupNext")   # browser, now ready
            page.locator("#setupTitle", has_text="Used Hoard before?").wait_for()
            page.click("#setupNext")
            page.locator("#setupTitle", has_text="Which stores").wait_for()
            for box in page.locator("#setupBody [data-pick]").all():
                box.uncheck()
            page.click("#setupNext")
            page.get_by_text("Pick at least one store").wait_for()
            page.check('#setupBody [data-pick="gumroad"]')
            page.click("#setupNext")
            page.locator("#setupTitle", has_text="Sign in to your stores").wait_for()
            page.click("#setupNext")   # nobody signed in: asked, and "no" stays
            page.wait_for_timeout(300)
            self.assertEqual(len(asked), 1)
            self.assertIn("haven't signed in to any store", asked[0])
            self.assertIn("Sign in to your stores", page.locator("#setupTitle").inner_text())
            page.click("#setupNext")   # "yes" goes on
            page.locator("#setupTitle", has_text="Where should downloads go?").wait_for()
            browser.close()



@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class WindowsTabsAndTasks(unittest.TestCase):
    """The 2.9 layout: Tags, Stores, Settings and Tasks as floating windows that stay open side by side, Settings
    saved as they change, a sidebar that folds, store folder tabs, the Tasks window (issue #49's queue included),
    and New with Recently added (issue #18)."""

    @classmethod
    def setUpClass(cls):
        from hoard import common, jobs
        cls.tmp = tempfile.TemporaryDirectory()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": cls.tmp.name, "setup_done": True},
                                   lan=False)
        old = "2025-01-01T00:00:00+00:00"
        with cls.srv.lib.lock:   # in memory only
            cls.srv.lib.data["items"] = [
                library.item("booth", "1", name="Rusk", creator="Kitsu Studio", added=old),
                library.item("gumroad", "2", name="Mochi", creator="Mochi Works", added=common.now_iso()),
                library.item("booth", "3", name="Anko", creator="Kitsu Studio", added=old)]
            for s in ("booth", "gumroad"):
                cls.srv.lib.data["stores"][s] = {"count": 1, "error": None, "source": "refresh", "first_read": "2024-01-01T00:00:00+00:00",
                                                 "updated": common.now_iso()}
        cls.srv.jobs.history = [{"id": "j1", "task": "sync", "label": "Sync: Booth", "stores": ["booth"],
                                 "started": "2026-09-30T09:00:00+00:00", "ended": "2026-09-30T09:02:00+00:00",
                                 "outcome": "failed", "message": "Stopped: Booth went away", "report": None,
                                 "log": ["Reading Booth", "Booth went away"]}]
        cls.jobs_file = mock_patch(jobs, "tasks_file", lambda: Path(cls.tmp.name) / "tasks.json")
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.jobs_file.stop()
        cls.tmp.cleanup()

    def setUp(self):
        # The last test's job may still be finishing after its page has moved on; one of these tests' jobs would
        # then wait behind it. Start each test with nothing running and nothing waiting.
        jobs = self.srv.jobs
        self.assertTrue(jobs.busy.acquire(timeout=30), "the last test's job didn't finish")
        jobs.busy.release()
        self.assertEqual(jobs.state["queue"], [])

    def open(self, ctx=None):
        page = ctx.new_page() if ctx else self.browser.new_page(viewport={"width": 1400, "height": 860})
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.srv.entry_url())
        page.locator(".slot", has_text="Mochi").wait_for()
        return page

    def test_windows_stay_open_move_and_remember(self):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 860})
        page = self.open(ctx)
        for button, win in (("#settingsBtn", "#settingsPanel"), ("#storesBtn", "#stores"), ("#tagsBtn", "#tagPanel")):
            page.click(button)
            page.locator(win + ".win:not([hidden])").wait_for()
        page.mouse.click(700, 500)   # a click on the page no longer closes them
        for win in ("#settingsPanel", "#stores", "#tagPanel"):
            self.assertTrue(page.locator(win).is_visible(), win)
        bar = page.locator("#tagPanel .win-bar").bounding_box()
        page.mouse.move(bar["x"] + 40, bar["y"] + 12)
        page.mouse.down()
        page.mouse.move(bar["x"] - 300, bar["y"] + 160, steps=6)
        page.mouse.up()
        moved = page.locator("#tagPanel").bounding_box()
        self.assertLess(abs(moved["x"] - (bar["x"] - 340)), 4)
        for _ in range(40):   # kept in Hoard's settings (a moment after it's let go)
            if (self.srv.cfg.get("ui") or {}).get("windows", {}).get("tagPanel"):
                break
            page.wait_for_timeout(100)
        self.assertEqual(self.srv.cfg["ui"]["windows"]["tagPanel"]["x"], round(moved["x"]))
        page.keyboard.press("Escape")   # the one in front
        self.assertTrue(page.locator("#tagPanel").is_hidden())
        self.assertTrue(page.locator("#stores").is_visible())
        page.reload()
        page.locator(".slot", has_text="Mochi").wait_for()
        page.click("#tagsBtn")
        again = page.locator("#tagPanel").bounding_box()
        self.assertLess(abs(again["x"] - moved["x"]) + abs(again["y"] - moved["y"]), 4, "opens where it was left")
        self.assertEqual(self.errors, [])
        ctx.close()

    def test_settings_save_as_they_change(self):
        from unittest import mock
        self.addCleanup(self.srv.cfg.update, new_days=self.srv.cfg.get("new_days", 7), download_retries=self.srv.cfg.get("download_retries", 2))
        with mock.patch.object(server, "save_config"):
            page = self.open()
            page.click("#settingsBtn")
            page.wait_for_function("() => document.querySelector('#setNewDays').value === '7'")
            self.assertEqual(page.locator("#setSave").count(), 0, "there's nothing to save")
            page.select_option("#setNewDays", "14")
            page.select_option("#setRetries", "0")
            page.locator("#settingsPanel .win-extra", has_text="Saved").wait_for()
            for _ in range(50):
                if self.srv.cfg.get("download_retries") == 0:
                    break
                page.wait_for_timeout(100)
            self.assertEqual((self.srv.cfg["new_days"], self.srv.cfg["download_retries"]), (14, 0))
            # a setting a running job reads is put back while it runs, and the others still save
            self.srv.jobs.state["running"] = True
            try:
                page.fill("#setRoot", "/somewhere/else")
                page.locator("#setRoot").press("Tab")
                page.get_by_text("can't change while Hoard is refreshing").wait_for()
                page.wait_for_function("() => document.querySelector('#setRoot').value !== '/somewhere/else'")
                page.select_option("#setNewDays", "3")
                for _ in range(50):
                    if self.srv.cfg.get("new_days") == 3:
                        break
                    page.wait_for_timeout(100)
                self.assertEqual(self.srv.cfg["new_days"], 3)
            finally:
                self.srv.jobs.state["running"] = False
            page.close()

    def test_the_sidebar_folds(self):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 860})
        page = self.open(ctx)
        page.click("#sideFold")
        self.assertTrue(page.evaluate("document.body.classList.contains('side-folded')"))
        self.assertTrue(page.locator("#creatorFind").is_hidden())
        creators = page.locator(".sec-toggle", has_text="Creators")
        page.click("#sideFold")
        creators.click()
        self.assertTrue(page.locator("#creatorFind").is_hidden(), "a section folds on its own")
        page.reload()   # straight away: what just changed is sent as the page is left
        page.locator(".slot", has_text="Mochi").wait_for()
        self.assertTrue(page.locator("#creatorFind").is_hidden(), "and stays folded")
        self.assertFalse(page.evaluate("document.body.classList.contains('side-folded')"))
        ctx.close()

    def test_folder_tabs(self):
        page = self.open()
        tab = lambda s: page.locator(f'#storeSeg [data-store="{s}"]').bounding_box()
        self.assertGreater(tab("")["height"], tab("booth")["height"], "the tab shown is raised")
        page.click('#storeSeg [data-store="booth"]')
        page.wait_for_timeout(250)
        self.assertGreater(tab("booth")["height"], tab("")["height"])
        page.close()

    def test_hovering_a_tab_moves_nothing_else(self):
        """A tab rises a little when the pointer's on it, but only the tab: in 2.9.0 the whole row grew with it, and
        the page under it bounced up and down as the pointer went along the tabs."""
        page = self.open()
        where = lambda: page.evaluate("() => [document.querySelector('.shelf').offsetHeight, "   # noqa: E731
                                      "Math.round(document.querySelector('.slot').getBoundingClientRect().top)]")
        page.mouse.move(700, 700)
        page.wait_for_timeout(300)
        still = where()
        for s in ("booth", "gumroad", ""):
            before = page.locator(f'#storeSeg [data-store="{s}"]').bounding_box()
            page.hover(f'#storeSeg [data-store="{s}"]')
            page.wait_for_timeout(300)   # the rise has finished
            self.assertEqual(where(), still, f"hovering {s or 'Everything'}")
            if s:
                self.assertGreater(page.locator(f'#storeSeg [data-store="{s}"]').bounding_box()["height"], before["height"],
                                   "the tab itself still rises")
        page.close()

    def test_the_glow_follows_the_store(self):
        """No colour bar on the selected tab: the page glows from the bottom in the store's colour instead, and for
        Everything the stores you're signed in to drift through it."""
        page = self.open()
        glow = lambda: page.evaluate("() => [document.querySelector('#glow').classList.contains('flow'), "
                                     "document.querySelector('#glow .glow-in').style.backgroundImage]")
        flowing, image = glow()
        self.assertTrue(flowing, "Everything: the stores' colours drift")
        self.assertIn("--booth", image)
        self.assertIn("--gumroad", image)
        page.click('#storeSeg [data-store="gumroad"]')
        flowing, image = glow()
        self.assertFalse(flowing)
        self.assertIn("--gumroad", image)
        self.assertNotIn("--booth", image)
        self.assertEqual(page.evaluate("""() => getComputedStyle(document.querySelector('#storeSeg [aria-checked="true"]'), '::after').display"""),
                         "none", "no bar on the tab")
        page.close()

    def test_new_and_recently_added(self):
        page = self.open()
        mochi = page.locator(".slot", has_text="Mochi")
        self.assertEqual(mochi.locator(".badge.new").count(), 1)
        self.assertEqual(page.locator(".slot", has_text="Rusk").locator(".badge.new").count(), 0)
        page.select_option("#sort", "added")
        self.assertEqual(page.locator(".slot .nm-t").first.inner_text(), "Mochi", "the newest first")
        page.click("[data-fresh]")
        self.assertEqual(page.locator(".slot").count(), 1)
        page.close()

    def test_the_tasks_window(self):
        from unittest import mock
        gate = threading.Event()
        self.addCleanup(gate.set)

        def fake(stores, only, keys=None, check=False, **_kw):
            self.srv.jobs._set(message=f"working on {only}")
            gate.wait(20)
        with mock.patch.object(self.srv.jobs, "_download", fake):
            self.srv.jobs.start("download", ["booth"], only="first")
            self.srv.jobs.start("download", ["booth"], only="second")
            self.srv.jobs.start("download", ["gumroad"], only="third")
            page = self.open()
            page.click("#tasksTab")
            page.get_by_text('Download: Booth ("first")').wait_for()
            page.locator("#tasksBody .task-msg", has_text="working on first").wait_for()
            waiting = page.locator("#tasksBody .tasklist .task")
            self.assertEqual(waiting.count(), 2)
            self.assertEqual(page.locator("#tasksCount").inner_text(), "3")
            waiting.nth(1).locator("[data-task=remove]").click()
            page.wait_for_function("() => document.querySelectorAll('#tasksBody .tasklist .task').length === 1")
            page.get_by_text("Stopped: Booth went away").wait_for(state="attached")   # a finished one, from before
            self.assertTrue(page.locator("#job").is_visible(), "what's running shows on the shelf")
            gate.set()
            page.get_by_text("Nothing is running.").wait_for(timeout=15000)
            page.close()

    def test_a_file_downloading_shows_its_progress_speed_and_time_left(self):
        from unittest import mock
        gate = threading.Event()
        self.addCleanup(gate.set)
        mb = 1024 * 1024

        def fake(stores, only, keys=None, check=False, **_kw):
            self.srv.jobs._set(task="download", message="    downloading Rusk.unitypackage: 20.0 MB of 80.0 MB (25%)",
                               transfer={"file": "Rusk.unitypackage", "got": 20 * mb, "total": 80 * mb,
                                         "speed": 2 * mb, "eta": 30})
            gate.wait(20)
        with mock.patch.object(self.srv.jobs, "_download", fake):
            self.srv.jobs.start("download", ["booth"], only="Rusk")
            page = self.open()
            bar = page.locator("#dlXfer .xfer-bar")
            bar.wait_for(timeout=10000)
            self.assertEqual(bar.get_attribute("aria-valuenow"), "25")
            self.assertEqual(page.locator("#dlXfer .xfer-file").inner_text(), "Rusk.unitypackage")
            self.assertEqual(page.locator("#dlXfer .xfer-stats").inner_text().split(),
                             "25% 20.0 MB of 80.0 MB · 2.0 MB/s · 30 s left".split())
            self.assertTrue(page.locator("#dlMessage").is_hidden(), "the bar says it all")
            self.srv.jobs.state["transfer"] = {"file": "Rusk.unitypackage", "got": 60 * mb, "total": 80 * mb,
                                               "speed": 4 * mb, "eta": 5}
            page.wait_for_function("() => document.querySelector('#dlXfer .xfer-bar').getAttribute('aria-valuenow') === '75'")
            page.locator("#dlXfer .xfer-stats", has_text="5 s left").wait_for()
            page.click("#tasksTab")
            page.locator("#tasksBody .xfer .xfer-stats", has_text="4.0 MB/s").wait_for()
            # a browser download: no size known, so the bar just says it's going
            self.srv.jobs.state["transfer"] = {"file": "Anko.zip", "got": 3 * mb, "total": None, "speed": mb, "eta": None}
            page.locator("#dlXfer .xfer-bar.unknown").wait_for()
            page.locator("#dlXfer .xfer-stats", has_text="3.0 MB so far · 1.0 MB/s").wait_for()
            gate.set()
            page.locator("#dlXfer").wait_for(state="hidden", timeout=15000)
            self.assertEqual(self.errors, [])
            page.close()

    def test_closing_while_working_asks_first(self):
        """2.9.2: closing Hoard's window while something runs asks: stop it first, carry on in the background (only
        in Hoard's own window), or close at once; Keep Hoard running is a setting, there too."""
        from unittest import mock
        gate = threading.Event()
        self.addCleanup(gate.set)
        hidden, closed = [], []
        self.addCleanup(setattr, self.srv, "hide_window", None)
        self.addCleanup(setattr, self.srv, "quit_app", None)
        self.addCleanup(self.srv.cfg.update, close_to_background=bool(self.srv.cfg.get("close_to_background")))
        self.srv.hide_window, self.srv.quit_app = (lambda: hidden.append(1)), (lambda: closed.append(1))
        with mock.patch.object(self.srv.jobs, "_download", lambda *a, **k: gate.wait(20)), \
                mock.patch.object(server, "save_config"):
            self.srv.jobs.start("download", ["booth"], only="Rusk")
            self.srv.jobs.start("download", ["gumroad"])
            page = self.open()
            page.evaluate("() => window.dispatchEvent(new Event('hoard-close'))")   # what the window's close button does
            dialog = page.locator("#closeDialog")
            dialog.wait_for()
            self.assertIn('Download: Booth ("Rusk") is running, and 1 more is waiting', page.locator("#closeWhat").inner_text())
            dialog.locator("[data-close='cancel']").click()
            self.assertTrue(dialog.is_hidden())
            page.evaluate("() => window.dispatchEvent(new Event('hoard-close'))")
            dialog.locator("[data-close='background']").click()
            for _ in range(40):
                if hidden:
                    break
                page.wait_for_timeout(100)
            self.assertEqual(hidden, [1], "the window hid; Hoard carries on")
            self.assertEqual(closed, [])
            # Quit Hoard in Settings asks the same, while it's working
            page.click("#settingsBtn")
            page.locator("#backgroundRow").wait_for(state="visible")   # the setting, in Hoard's own window
            page.check("#setBackground")
            for _ in range(40):
                if self.srv.cfg.get("close_to_background"):
                    break
                page.wait_for_timeout(100)
            self.assertTrue(self.srv.cfg.get("close_to_background"), "saved as it changed")
            page.click("#quitHoard")
            dialog.wait_for()
            self.srv.jobs.clear_queue()
            gate.set()
            page.close()
        self.assertEqual(self.errors, [])

    def test_a_job_started_while_another_runs_waits(self):
        from unittest import mock
        gate = threading.Event()
        self.addCleanup(gate.set)
        with mock.patch.object(self.srv.jobs, "_download", lambda *a, **k: gate.wait(20)):
            self.srv.jobs.start("download", ["booth"], only="busy")
            page = self.open()
            page.locator('.slot', has_text="Rusk").click()
            page.click("#detail [data-act=download]")
            page.get_by_text("Queued: it starts when what's running now is done").wait_for()
            gate.set()
            page.close()


def mock_patch(target, name, value):
    from unittest import mock
    patcher = mock.patch.object(target, name, value)
    patcher.start()
    return patcher
