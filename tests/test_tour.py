"""The tour: offered once in the Library, then walked through on your own items, from the Library on to Downloads,
each step that asks you to try something going on once you have; and from Settings, any time."""
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import config, downloader, library, server  # noqa: E402
from tests.browsing import menu  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False

NAMES = (("1", "Boots"), ("2", "Hoodie"), ("3", "Rusk"), ("4", "Skirt"))


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Tour(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(self.tmp.name) / "data")})
        env.start()
        self.addCleanup(env.stop)
        self.root = Path(self.tmp.name) / "dl"
        self.pw = sync_playwright().start()
        self.addCleanup(self.pw.stop)
        self.browser = self.pw.chromium.launch()
        self.addCleanup(self.browser.close)

    def serve(self, downloaded=True):
        root = self.root
        for key, name in NAMES if downloaded else ():
            folder = root / "Booth" / "Kitsu" / name
            folder.mkdir(parents=True)
            (folder / f"{name}.unitypackage").write_bytes(b"x")
            man = downloader.Manifest(root / "Booth")
            rec = man.record(key, "Kitsu", name)
            rec.update(name=name, creator="Kitsu")
            rec["files"]["f"] = {"path": f"{name}.unitypackage", "size": 1}
            man.save()
        root.mkdir(parents=True, exist_ok=True)
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True, "ui": {}}, lan=False)
        with self.srv.lib.lock:   # in memory only
            self.srv.lib.data["items"] = [library.item("booth", k, name=n, creator="Kitsu", url=f"https://booth.pm/ja/items/{k}")
                                          for k, n in NAMES]
            self.srv.lib.data["stores"]["booth"] = {"count": 4, "error": None}
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def open(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 860})
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        page.locator("#grid .slot").first.wait_for()
        return page

    def title(self, page, text):
        page.locator(".tour-card #tourTitle", has_text=text).wait_for(timeout=5000)

    def nxt(self, page):
        page.click('.tour-card [data-tour="next"]')

    def picked(self, page):
        return page.locator(".tour-card #tourBody strong").inner_text()

    def test_offered_then_walked_through(self):
        self.serve()
        page = self.open()
        note = page.locator("#tourNote")
        note.wait_for()
        note.get_by_role("button", name="Take the tour").click()
        self.title(page, "A quick tour of Hoard")
        self.assertIn("4 items from Booth", page.locator("#tourBody").inner_text(), "your own library")
        self.assertFalse(note.is_visible())
        self.nxt(page)
        self.title(page, "Your stores")
        page.wait_for_function("""() => {   // the ring round the store tabs (once it's moved there)
            const r = document.querySelector(".tour-ring").getBoundingClientRect(), t = $("#storeSeg").getBoundingClientRect();
            return Math.abs(r.left + 6 - t.left) < 2 && Math.abs(r.width - 12 - t.width) < 2; }""", timeout=3000)
        self.nxt(page)
        self.title(page, "Search")
        page.fill("#q", self.picked(page))
        self.title(page, "Open one")   # typing went on by itself
        self.assertEqual(page.input_value("#q"), "", "and the search is cleared for the next step")
        name = self.picked(page)
        page.locator("#grid .slot", has_text=name).click()
        self.title(page, "Its details")
        self.nxt(page)
        self.title(page, "Choose several")
        page.locator("#grid .slot").nth(0).click(modifiers=["Control"])
        page.locator("#grid .slot").nth(1).click(modifiers=["Control"])
        self.title(page, "Do it to all of them")
        self.nxt(page)
        self.assertFalse(page.locator("#bulk").is_visible(), "let go of them")
        self.title(page, "Archive, Removed and Hidden")
        self.nxt(page)
        self.title(page, "Sync")
        self.nxt(page)
        self.title(page, "On to your downloads")
        page.click('.apptabs a[href="/downloads"]')   # on to the other page: the tour carries on there
        self.title(page, "Your downloads")
        self.assertIn("4 products", page.locator("#tourBody").inner_text())
        self.assertFalse(page.locator('.tour-card [data-tour="back"]').is_visible(), "no Back to the other page")
        self.nxt(page)
        self.title(page, "Open one")
        name = self.picked(page)
        page.locator("#grid .slot", has_text=name).click()
        self.title(page, "Look inside")
        page.locator('#detail [data-act="inside"]').click()
        self.title(page, "Search inside")
        self.nxt(page)
        self.assertTrue(page.locator("#insideWin").is_hidden(), "closed on the way out")
        self.title(page, "What it needs")   # (the sample's packages aren't read yet: it says Hoard reads them)
        page.screenshot(path=os.environ.get("TOUR_SHOT", os.devnull + ".png") if os.environ.get("TOUR_SHOT") else None) if os.environ.get("TOUR_SHOT") else None
        self.nxt(page)
        self.title(page, "Tags")
        page.fill("#tagInput", "tour-tag")
        page.locator('#detail [data-act="addtyped"]').click()
        self.title(page, "Sets and Wishlists")
        page.click('#stores [data-store="Sets"]')   # opened: its wishlists and Mix and match are shown there
        self.title(page, re.compile(r"^Wishlists$"))   # (not "Sets and Wishlists", which has_text would match too)
        self.nxt(page)
        self.title(page, "Mix and match")
        self.nxt(page)
        page.wait_for_function("() => !inSets()")   # back to every store on the way out
        self.title(page, "Updates")
        self.nxt(page)
        self.title(page, "Disk space")
        page.click('#views [data-view="space"]')
        self.title(page, "Free some room")
        self.nxt(page)
        page.wait_for_function("() => state.view === 'downloads'")
        for step in ("Local", "Projects", "Tasks", "Menu"):   # (the Menu: Tags, Rescan and Settings)
            self.title(page, step)
            self.nxt(page)
        self.title(page, "That's the tour")
        self.nxt(page)
        page.get_by_text("Take the tour again any time, from Settings.").wait_for()
        self.assertEqual(page.locator(".tour-card").count(), 0)
        self.assertTrue(self.srv.cfg["ui"]["toured"], "offered no more")
        self.assertEqual(self.errors, [])
        page.close()
        page = self.open()
        page.wait_for_timeout(500)
        self.assertFalse(page.locator("#tourNote").is_visible(), "not offered again")
        page.close()

    def test_not_now_and_from_settings(self):
        self.serve()
        page = self.open()
        page.locator("#tourNote").get_by_role("button", name="Not now").click()
        self.assertFalse(page.locator("#tourNote").is_visible())
        page.wait_for_function("() => !uiPending")
        self.assertTrue(self.srv.cfg["ui"]["toured"])
        menu(page, "#settingsBtn")
        page.click("#tourAgain")
        self.title(page, "A quick tour of Hoard")
        self.assertTrue(page.locator("#settingsPanel").is_hidden())
        self.nxt(page)
        self.title(page, "Your stores")
        page.click('.tour-card [data-tour="back"]')
        self.title(page, "A quick tour of Hoard")
        page.click('.tour-card [data-tour="end"]')
        self.assertEqual(page.locator(".tour-card").count(), 0)
        self.assertEqual(page.locator(".tour-ring").count(), 0)
        page.goto(self.srv.entry_url().replace("/#", "/downloads#", 1))   # and from Downloads' Settings: in the Library
        page.locator("#grid .slot").first.wait_for()
        menu(page, "#settingsBtn")
        page.click("#tourAgain")
        self.title(page, "A quick tour of Hoard")
        self.assertEqual(self.errors, [])
        page.close()

    def test_nothing_downloaded_yet(self):
        """Steps about what you don't have yet are passed by, and the tour says what Downloads will hold."""
        self.serve(downloaded=False)
        page = self.open()
        page.locator("#tourNote").get_by_role("button", name="Take the tour").click()
        self.title(page, "A quick tour of Hoard")
        page.evaluate("tourShow(TOUR.steps.findIndex(s => s.id === 'to-downloads'), 1)")
        self.nxt(page)
        self.title(page, "Your downloads")
        self.assertIn("Nothing's downloaded yet", page.locator("#tourBody").inner_text())
        self.assertTrue(page.locator(".tour-card").evaluate("c => c.classList.contains('middle')"), "nothing to point at")
        self.nxt(page)
        self.title(page, "Sets")   # no item to open, look inside or tag
        self.assertEqual(self.errors, [])
        page.close()

    def test_slow_enough_to_follow(self):
        """Issue #265: between steps the ring moves to what's next (slowly enough to follow) and the card shows a moment
        later, once it's there; with Reduce motion, at once."""
        self.serve()
        page = self.open()
        page.evaluate("tourStart(TOUR.steps.findIndex(s => s.id === 'stores'))")
        self.title(page, "")
        self.assertFalse(page.evaluate("document.querySelector('.tour-card').classList.contains('tour-wait')"), "the first: at once")
        self.assertGreaterEqual(page.evaluate("parseFloat(getComputedStyle(document.querySelector('.tour-ring')).transitionDuration)"), .5)
        self.nxt(page)
        self.assertTrue(page.evaluate("document.querySelector('.tour-card').classList.contains('tour-wait')"), "the card waits")
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.tour-card')).opacity"), "0")
        page.wait_for_function("() => !document.querySelector('.tour-card.tour-wait')", timeout=3000)
        page.evaluate("document.body.classList.add('less-motion')")   # (Settings' Reduce motion)
        self.nxt(page)
        self.assertFalse(page.evaluate("document.querySelector('.tour-card').classList.contains('tour-wait')"), "Reduce motion: at once")
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.tour-ring')).transitionDuration"), "0s")
        self.assertEqual(self.errors, [])
        page.close()

    def test_on_screen_at_the_largest_text_size(self):
        """Text size zooms the whole page: the card and its ring were placed by the window's pixels, so at 130% and up
        they landed past the target, the card off the window's edge."""
        inside = """sel => { const r = document.querySelector(sel).getBoundingClientRect();
            return r.left >= 0 && r.top >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1; }"""
        self.serve()
        page = self.open()
        page.evaluate("applyDisplay({ ...DATA.display, text_size: 150 })")
        for step in ("stores", "search", "sync", "views"):
            page.evaluate("id => TOUR.i < 0 ? tourStart(TOUR.steps.findIndex(s => s.id === id)) : tourShow(TOUR.steps.findIndex(s => s.id === id), 1)", step)
            page.wait_for_function("() => !document.querySelector('.tour-card.tour-wait')")   # (the ring moves there,
            page.wait_for_timeout(800)                                                         # then the card: #265)
            self.assertTrue(page.evaluate(inside, ".tour-card"), f"{step}: the card on screen")
            ring, target = page.evaluate("""id => [document.querySelector('.tour-ring').getBoundingClientRect(),
                tourTarget(TOUR.steps.find(s => s.id === id))[0].getBoundingClientRect()].map(r => [r.left, r.top])""", step)
            self.assertLess(abs(ring[0] + 6 - target[0]), 3, f"{step}: the ring round its part")
            self.assertLess(abs(ring[1] + 6 - target[1]), 4, step)
        page.close()


if __name__ == "__main__":
    unittest.main()
