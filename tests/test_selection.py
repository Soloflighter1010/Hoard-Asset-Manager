"""Selecting several items (both pages): a tile's tick box, Ctrl/Cmd-click and Shift-click, Ctrl+A and Esc, Select for
touch screens, and what to do with them: the bar's menus, and the same menu on a right-click."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import config, downloader, library, server  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Selecting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(cls.tmp.name) / "data")})
        cls.env.start()
        root = Path(cls.tmp.name) / "dl"
        for key, name in (("1", "Boots"), ("2", "Hoodie"), ("3", "Rusk"), ("4", "Skirt")):
            folder = root / "Booth" / "Kitsu" / name
            folder.mkdir(parents=True)
            (folder / f"{name}.unitypackage").write_bytes(b"x")
            man = downloader.Manifest(root / "Booth")
            rec = man.record(key, "Kitsu", name)
            rec.update(name=name, creator="Kitsu")
            rec["files"]["f"] = {"path": f"{name}.unitypackage", "size": 1}
            man.save()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        with cls.srv.lib.lock:   # the Library page's list (in memory only)
            cls.srv.lib.data["items"] = [library.item("booth", k, name=n, creator="Kitsu", url=f"https://booth.pm/ja/items/{k}")
                                         for k, n in (("1", "Boots"), ("2", "Hoodie"), ("3", "Rusk"), ("4", "Skirt"))]
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
        cls.tmp.cleanup()

    def open(self, downloads=True):
        page = self.browser.new_page(viewport={"width": 1280, "height": 820})
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        if downloads:
            page.click("nav.apptabs a[href='/downloads']")
        page.locator("#grid .slot").first.wait_for()
        return page

    def chosen(self, page):
        return page.evaluate("chosenItems().map(a => a.name).sort()")

    def tearDown(self):
        self.assertEqual(getattr(self, "errors", []), [])

    def test_ctrl_and_shift_click(self):
        page = self.open()
        slots = page.locator("#grid .slot")
        slots.nth(0).click(modifiers=["Control"])
        self.assertTrue(page.locator("#bulk").is_visible(), "the bar, as soon as something's chosen")
        self.assertFalse(page.locator("#detail").is_visible(), "Ctrl-click chooses: it doesn't open")
        slots.nth(2).click(modifiers=["Shift"])
        self.assertEqual(page.locator("#bulkCount").inner_text(), "3 selected", "Shift-click: everything between")
        slots.nth(1).click(modifiers=["Control"])
        self.assertEqual(page.locator("#bulkCount").inner_text(), "2 selected", "Ctrl-click again: taken out")
        slots.nth(3).locator(".tick").click()
        self.assertEqual(page.locator("#bulkCount").inner_text(), "3 selected", "the tick box too")
        slots.nth(1).click()
        page.locator("#detail .d-name", has_text="Hoodie").wait_for()   # a plain click still opens it
        page.keyboard.press("Escape")   # (closes the details first)
        page.keyboard.press("Escape")
        self.assertFalse(page.locator("#bulk").is_visible(), "Esc: nothing chosen")
        page.close()

    def test_ctrl_a_and_select_all(self):
        page = self.open()
        page.locator("#grid .slot").first.focus()
        page.keyboard.press("Control+a")
        self.assertEqual(page.locator("#bulkCount").inner_text(), "4 selected")
        page.click("#bulkDone")
        self.assertFalse(page.locator("#bulk").is_visible())
        page.click("#selectBtn")   # Select (touch screens): every tap chooses
        page.locator("#grid .slot").nth(1).click()
        self.assertEqual(self.chosen(page), ["Hoodie"])
        page.click("#bulkAll")
        self.assertEqual(page.locator("#bulkCount").inner_text(), "4 selected")
        page.close()

    def test_right_click_menu(self):
        page = self.open()
        slots = page.locator("#grid .slot")
        slots.nth(0).click(modifiers=["Control"])
        slots.nth(1).click(modifiers=["Control"])
        slots.nth(1).click(button="right")   # on a chosen tile: the selection stays
        menu = page.locator(".selmenu")
        self.assertEqual(page.locator("#bulkCount").inner_text(), "2 selected")
        self.assertEqual(menu.locator(".selmenu-h").all_inner_texts(), ["Tags", "Sets", "More"], "every group of the bar")
        page.keyboard.press("Escape")
        self.assertEqual(menu.count(), 0)
        slots.nth(3).click(button="right")   # on one not chosen: just that one, as file managers do
        self.assertEqual(self.chosen(page), ["Skirt"])
        page.keyboard.press("Escape")
        slots.nth(2).focus()   # the keyboard's way: the menu key
        page.keyboard.press("Shift+F10")
        self.assertEqual(page.evaluate("document.activeElement.textContent"), "Add a tag...", "the first item has the focus")
        page.keyboard.press("ArrowDown")
        self.assertEqual(page.evaluate("document.activeElement.textContent"), "Remove a tag...")
        page.close()

    def test_tag_from_the_menu(self):
        page = self.open()
        page.locator("#grid .slot").nth(0).click(modifiers=["Control"])
        page.locator("#grid .slot").nth(3).click(modifiers=["Control"])
        page.click("#bulkActs [data-group='Tags']")
        page.locator(".selmenu [role=menuitem]", has_text="Add a tag...").click()
        page.fill("dialog[open] #askName", "boots-and-skirts")
        page.locator("dialog[open] button", has_text="OK").click()
        page.get_by_text("Added #boots-and-skirts to 2 items.").wait_for()
        tagged = page.evaluate("DATA.assets.filter(a => a.tags.includes('boots-and-skirts')).map(a => a.name).sort()")
        self.assertEqual(tagged, ["Boots", "Skirt"])
        page.close()

    def test_the_library_page(self):
        page = self.open(downloads=False)
        page.locator("#grid .slot").first.click(modifiers=["Control"])
        self.assertEqual(page.locator("#bulkActs [data-main]").all_inner_texts(), ["Download"], "its main action")
        page.click("#bulkActs [data-group='More']")
        self.assertEqual(page.locator(".selmenu [role=menuitem]").all_inner_texts(),
                         ["Archive", "Hide", "Remove", "Delete downloaded files"])
        page.close()


if __name__ == "__main__":
    unittest.main()
