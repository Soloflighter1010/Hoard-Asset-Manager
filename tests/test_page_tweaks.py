"""Small things on both pages (4.0): the details' picture is shorter until clicked, Settings has a row of its parts,
Downloads lists a product's files right after what you can do with them, and a long message stays up longer."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from hoard import config, downloader, server

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Tweaks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        from tests.test_pages import picture
        cls.tmp = Path(tempfile.mkdtemp())
        cls.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(cls.tmp / "data")})
        cls.env.start()
        root = cls.tmp / "dl"
        folder = root / "Booth" / "Kitsu" / "Rusk"
        folder.mkdir(parents=True)
        (folder / "Rusk.unitypackage").write_bytes(b"x")
        (folder / "_thumbnail.png").write_bytes(picture(1, size=200))
        man = downloader.Manifest(root / "Booth")
        rec = man.record("1", "Kitsu", "Rusk")
        rec.update(name="Rusk", creator="Kitsu")
        rec["files"]["f"] = {"path": "Rusk.unitypackage", "size": 1}
        man.save()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.env.stop()
        __import__("shutil").rmtree(cls.tmp, True)

    def downloads(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 820})
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        page.click("nav.apptabs a[href='/downloads']")
        page.locator("#grid .slot").first.wait_for()
        return page

    def test_the_picture_is_shorter_until_clicked(self):
        page = self.downloads()
        page.click("#grid .slot")
        art = page.locator("#detail .d-art")
        art.locator("img").wait_for()
        small = art.bounding_box()
        self.assertLess(small["height"], small["width"] * 0.8, "shorter than it is wide")
        self.assertTrue(page.locator("#detail [data-act='open']").first.is_visible(), "the buttons show without scrolling")
        art.click()
        page.wait_for_timeout(400)
        big = art.bounding_box()
        self.assertAlmostEqual(big["height"], big["width"], delta=2)
        names = page.locator("#detail h3").all_inner_texts()
        self.assertTrue(names[0].startswith("Files"), names)

    def test_settings_jumps_to_its_parts(self):
        page = self.downloads()
        page.click("#settingsBtn")
        jumps = page.locator(".setjump button")
        self.assertEqual(jumps.count(), 8)
        page.locator("#setStores input").first.wait_for()   # the stores' boxes are where they were (drawn once Settings loads)
        page.click("[data-jump='part-help']")
        page.wait_for_timeout(800)
        self.assertTrue(page.locator("#part-help").is_visible())
        box, bar = page.locator("#part-help").bounding_box(), page.locator(".setjump").bounding_box()
        self.assertGreaterEqual(box["y"], bar["y"] + bar["height"] - 1, "not under the row")

    def test_the_set_picker_looks_like_the_other_dropdowns(self):
        """It was the browser's own grey dropdown, taller than the Add button beside it, in larger text."""
        page = self.downloads()
        page.click("#grid .slot")
        pick, add = page.locator("#setPick"), page.locator("#detail [data-act='toset']")
        pick.wait_for()
        look = "e => { const c = getComputedStyle(e); return [c.appearance, c.height, c.fontSize]; }"
        appearance, height, size = pick.evaluate(look)
        self.assertEqual(appearance, "none", "the app's own arrow, not the system's")
        self.assertEqual(height, add.evaluate(look)[1], "as tall as Add")
        self.assertEqual(size, add.evaluate(look)[2], "the same size text as Add")

    def test_a_long_message_stays_longer(self):
        page = self.downloads()
        page.evaluate("toast('A short one.')")
        page.wait_for_timeout(2600)
        self.assertNotIn("show", page.locator("#toast").get_attribute("class") or "")
        page.evaluate("toast('x'.repeat(120))")
        page.wait_for_timeout(2600)
        self.assertIn("show", page.locator("#toast").get_attribute("class"))


if __name__ == "__main__":
    unittest.main()
