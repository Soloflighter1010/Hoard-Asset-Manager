"""Sets (hoard/sets.py): products you group to use together, listed in catalog.json for Hoard for Unity."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hoard import downloader, sets
from hoard.tags import tag_key

RUSK, HOODIE = tag_key("Booth", "Rusk"), tag_key("Booth", "Hoodie for Rusk")


class Store(unittest.TestCase):
    def setUp(self):
        self.store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")

    def test_make_change_and_delete(self):
        made = self.store.change({"action": "create", "name": "Rusk, winter", "items": [RUSK, HOODIE, RUSK]})["made"]
        self.assertEqual(self.store.load()["sets"], [{"id": made, "name": "Rusk, winter", "items": [RUSK, HOODIE]}])
        self.store.change({"action": "rename", "id": made, "name": "Rusk winter"})
        self.store.change({"action": "remove", "id": made, "items": [RUSK]})
        self.store.change({"action": "add", "id": made, "items": [RUSK, "not a key!", HOODIE]})
        self.assertEqual(self.store.load()["sets"][0], {"id": made, "name": "Rusk winter", "items": [HOODIE, RUSK]})
        self.store.change({"action": "delete", "id": made})
        self.assertEqual(self.store.load()["sets"], [])

    def test_what_cant_be_done(self):
        for body in ({"action": "create", "name": "  "}, {"action": "rename", "id": "nope", "name": "x"},
                     {"action": "explode", "id": "x"}, {"action": "create", "name": 7}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.store.change(body)

    def test_a_damaged_file(self):
        self.store.path.write_text('{"sets": [{"id": "ab", "name": "\\u202eevil", "items": ["booth:rusk", 4]}, '
                                   '{"id": "../x", "name": "y"}, "nope"]}', "utf-8")
        self.assertEqual(self.store.load()["sets"], [{"id": "ab", "name": "evil", "items": ["booth:rusk"]}])
        self.store.path.write_text("{not json", "utf-8")
        self.assertEqual(self.store.load(), {"sets": []})


class InTheCatalog(unittest.TestCase):
    def test_sets_by_their_products_folders(self):
        tmp = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        root = tmp / "dl"
        for key, creator, name in (("1", "Kitsu", "Rusk"), ("2", "Mochi", "Hoodie for Rusk")):
            folder = root / "Booth" / creator / name
            folder.mkdir(parents=True)
            (folder / "p.unitypackage").write_bytes(b"x")
            man = downloader.Manifest(root / "Booth")
            rec = man.record(key, creator, name)
            rec.update(name=name, creator=creator)
            rec["files"]["f"] = {"path": "p.unitypackage", "size": 1}
            man.save()
        sets.SetStore().change({"action": "create", "name": "Rusk, winter", "items": [HOODIE, RUSK, tag_key("Booth", "Gone")]})
        sets.SetStore().change({"action": "create", "name": "Empty", "items": []})
        downloader.build_catalog({"root": str(root), "tags": {}}, root)
        cat = json.loads((root / "catalog.json").read_text("utf-8"))
        self.assertEqual(cat["sets"], [{"name": "Rusk, winter", "items": ["Booth/Mochi/Hoodie for Rusk", "Booth/Kitsu/Rusk"]}],
                         "products it doesn't have, and sets with none, are left out")


try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Page(unittest.TestCase):
    def test_make_a_set_and_show_it(self):
        import threading
        from playwright.sync_api import sync_playwright
        from hoard import config, server
        tmp = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        root = tmp / "dl"
        for key, creator, name in (("1", "Kitsu", "Rusk"), ("2", "Mochi", "Hoodie for Rusk"), ("3", "Mochi", "Skirt")):
            folder = root / "Booth" / creator / name
            folder.mkdir(parents=True)
            (folder / "p.unitypackage").write_bytes(b"x")
            man = downloader.Manifest(root / "Booth")
            rec = man.record(key, creator, name)
            rec.update(name=name, creator=creator)
            rec["files"]["f"] = {"path": "p.unitypackage", "size": 1}
            man.save()
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.click("nav.apptabs a[href='/downloads']")
            page.click("#selectBtn")
            page.locator('#grid .slot[aria-label^="Rusk"]').click()
            page.locator('#grid .slot[aria-label^="Hoodie for Rusk"]').click()
            self.assertFalse(page.locator("#bulkSetTo").is_visible(), "no sets yet: nothing to add to")
            page.click("#bulkNewSet")   # a set made of what's selected
            page.fill("dialog[open] #askName", "Rusk, winter")
            page.locator("dialog[open] button", has_text="OK").click()
            page.get_by_text("Made the set Rusk, winter, with 2 products in it.").wait_for()
            page.locator("#bulkSetTo").wait_for()
            self.assertEqual(page.locator("#bulkSetTo option").all_inner_texts(), ["Choose a set", "Rusk, winter"])
            page.click("#bulkDone")
            page.locator("#sets .chip", has_text="Rusk, winter").click()
            page.wait_for_function("() => document.querySelectorAll('#grid .slot').length === 2")
            self.assertIn("set=", page.url)
            page.locator('#grid .slot[aria-label^="Hoodie for Rusk"]').click()
            self.assertIn("Rusk, winter", page.locator("#detail .chips", has_text="Rusk, winter").inner_text())
            page.locator("#detail [data-act='unset']").click()
            page.wait_for_function("() => document.querySelectorAll('#grid .slot').length === 1")
            browser.close()
        [s] = sets.SetStore().load()["sets"]
        self.assertEqual((s["name"], s["items"]), ("Rusk, winter", [RUSK]))


if __name__ == "__main__":
    unittest.main()
