"""Downloads, Disk space, From more than one store: a product you have from several stores, each downloaded; keep
one store's copy and remove the others, which leave your library (so syncing doesn't download them again) and
have their downloaded files deleted."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import config, downloader, library, server  # noqa: E402
from hoard.marks import MarkStore  # noqa: E402
from hoard.tags import tag_key  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False

# (store folder, id, name): Rusk on Booth and Gumroad, Hoodie on Booth and Jinxxy, Skirt on Booth only
OWNED = (("Booth", "1", "Rusk"), ("Gumroad", "g1", "Rusk"), ("Booth", "2", "Hoodie"), ("Jinxxy", "j2", "Hoodie"),
         ("Booth", "3", "Skirt"))


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Duplicates(unittest.TestCase):
    owned = OWNED

    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(self.tmp.name) / "data")})
        env.start()
        self.addCleanup(env.stop)
        self.root = root = Path(self.tmp.name) / "dl"
        self.files = {}
        items = []
        for store, key, name in self.owned:
            man = downloader.Manifest(root / store)
            rec = man.record(key, "Kitsu", name)
            rec.update(name=name, creator="Kitsu")
            folder = root / store / rec["folder"]
            folder.mkdir(parents=True)
            (folder / f"{name}.unitypackage").write_bytes(b"x" * 2048)
            rec["files"]["f"] = {"path": f"{name}.unitypackage", "size": 2048}
            man.save()
            self.files[(store, name)] = folder / f"{name}.unitypackage"
            items.append(library.item(store.lower(), key, name=name, creator="Kitsu"))
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        with self.srv.lib.lock:   # in memory only
            self.srv.lib.data["items"] = items
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.pw = sync_playwright().start()
        self.addCleanup(self.pw.stop)
        self.browser = self.pw.chromium.launch()
        self.addCleanup(self.browser.close)

    def open(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        page.click("nav.apptabs a[href='/downloads']")
        page.locator("#grid .slot").first.wait_for()
        page.click('#views [data-view="space"]')
        page.locator("[data-space=dupes]").wait_for()
        return page

    def test_keep_one_stores_copy(self):
        page = self.open()
        self.assertIn("2", page.locator("[data-space=dupes]").inner_text(), "Rusk and Hoodie: Skirt is only on Booth")
        page.click("[data-space=dupes]")
        rows = page.locator(".dupelist li")
        self.assertEqual(rows.count(), 2)
        self.assertEqual(sorted(page.eval_on_selector_all("#grid .slot .nm", "els => els.map(e => e.textContent)")),
                         ["Hoodie", "Hoodie", "Rusk", "Rusk"], "the grid shows just those")
        go = page.locator("[data-dupe='go']")
        self.assertTrue(go.is_disabled(), "nothing goes until you choose")
        page.select_option("#dupeStore", "Booth")
        page.click("[data-dupe='apply']")   # Booth's copy, in every one
        self.assertIn("Remove 2 copies", go.inner_text())
        page.locator(".dupelist li", has_text="Hoodie").locator("label", has_text="Keep all").click()   # but Hoodie: both
        self.assertIn("Remove 1 copy", go.inner_text())
        go.click()
        self.assertIn("Rusk (Gumroad)", page.locator("#askText").inner_text())
        page.click("#askDialog button.danger")
        page.get_by_text("Removed 1 copy and deleted").wait_for()
        self.assertFalse(self.files[("Gumroad", "Rusk")].exists(), "the copy removed: its files deleted")
        for kept in (("Booth", "Rusk"), ("Booth", "Hoodie"), ("Jinxxy", "Hoodie"), ("Booth", "Skirt")):
            self.assertTrue(self.files[kept].exists(), kept)
        removed = MarkStore().keys("removed")
        self.assertEqual(removed, {tag_key("Gumroad", "Rusk")}, "out of your library: Booth's Rusk stays in it")
        self.assertEqual(self.errors, [])
        page.close()

    def test_a_removed_copy_isnt_downloaded_again(self):
        MarkStore().change("removed", [tag_key("Gumroad", "Rusk")], True)
        report = downloader.Report()
        self.assertTrue(downloader.removed_product("gumroad", "Rusk", report), "a sync skips it")
        self.assertFalse(downloader.removed_product("booth", "Rusk", report), "the copy kept is downloaded as ever")
        self.assertIn("removed from your library, so not downloaded", report.skipped[0])
        MarkStore().change("removed", [tag_key("Gumroad", "Rusk")], False)   # Restore, in the Library
        self.assertFalse(downloader.removed_product("gumroad", "Rusk", downloader.Report()), "added back: downloaded again")


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class OneKeyTwoProducts(Duplicates):
    """Removing goes by product key, which leaves numbers and (labels) out: Booth's "Hair Pack 1" and "Hair Pack 2"
    share one. Choosing to keep Booth's Hair Pack 1 deleted both of Booth's, the one kept included, with Gumroad's."""
    owned = (("Booth", "1", "Hair Pack 1"), ("Booth", "2", "Hair Pack 2"), ("Gumroad", "g1", "Hair Pack 1"))

    test_keep_one_stores_copy = test_a_removed_copy_isnt_downloaded_again = None

    def test_the_copy_kept_and_another_product_stay(self):
        page = self.open()
        page.click("[data-space=dupes]")
        rows = page.locator(".dupelist li")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.locator("input[type=radio]").count(), 3, "Booth's and Gumroad's Hair Pack 1, and Keep all")
        self.assertNotIn("Hair Pack 2", rows.inner_text(), "not a copy: the Library keeps them apart too")
        go = page.locator("[data-dupe='go']")
        page.select_option("#dupeStore", "Gumroad")
        page.click("[data-dupe='apply']")
        self.assertTrue(go.is_disabled(), "Booth's would take Hair Pack 2 with it: it isn't offered")
        page.select_option("#dupeStore", "Booth")
        page.click("[data-dupe='apply']")
        self.assertIn("Remove 1 copy", go.inner_text())
        go.click()
        page.click("#askDialog button.danger")
        page.get_by_text("Removed 1 copy and deleted").wait_for()
        self.assertFalse(self.files[("Gumroad", "Hair Pack 1")].exists())
        self.assertTrue(self.files[("Booth", "Hair Pack 1")].exists(), "the copy kept")
        self.assertTrue(self.files[("Booth", "Hair Pack 2")].exists(), "another product")
        self.assertEqual(MarkStore().keys("removed"), {tag_key("Gumroad", "Hair Pack 1")})
        self.assertEqual(self.errors, [])
        page.close()


if __name__ == "__main__":
    unittest.main()
