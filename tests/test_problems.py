"""Issue #334: an error mark on a product's tile when something is wrong with it: files missing on disk, files the
check of the downloads found changed, a download of it that didn't finish, or a Local product's folder that's gone.
Said on hover and in the tile's spoken label; listed, with what to do, in its details; and Downloads' Problems view
lists them all."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from tests.isolation import IsolatedTestCase
from hoard import asset_updates, config, downloader, downloads, library, server, storage
from hoard.tags import tag_key

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _pw:
        _pw.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

RUSK, ANKO = tag_key("booth", "Rusk"), tag_key("booth", "Anko")


def product(root: Path, key: str, name: str, files: dict) -> Path:
    """A product downloaded from Booth into root: its files on disk, and its record."""
    folder = root / "Booth" / "Kitsu Studio" / name
    folder.mkdir(parents=True, exist_ok=True)
    man = downloader.Manifest(root / "Booth")
    rec = man.record(key, "Kitsu Studio", name)
    rec.update(name=name, creator="Kitsu Studio", url=f"https://booth.pm/ja/items/{key}")
    for n, (rel, data) in enumerate(files.items()):
        (folder / rel).write_bytes(data)
        rec["files"][f"f{n}"] = {"path": rel, "size": len(data)}
    man.save()
    return folder


class WhatsWrong(IsolatedTestCase):
    def test_each_kind_by_product(self):
        assets = [{"tag_key": RUSK, "missing": 2}, {"tag_key": ANKO, "missing": 0},
                  {"tag_key": "local:my edit", "missing": 3, "folder_gone": True}]
        checked = {"problems": [{"kind": "changed", "store": "booth", "name": "Anko", "path": "a"},
                                {"kind": "changed", "store": "booth", "name": "Anko", "path": "b"},
                                {"kind": "missing", "store": "booth", "name": "Rusk", "path": "c"}]}
        failed = {RUSK: {"store": "booth", "why": "rusk.zip: timed out", "at": "2026-11-11T10:00:00+00:00"}}
        self.assertEqual(downloads.problems(assets, checked, failed), {
            RUSK: [{"kind": "missing", "n": 2}, {"kind": "failed", "why": "rusk.zip: timed out", "at": "2026-11-11T10:00:00+00:00"}],
            ANKO: [{"kind": "changed", "n": 2}],
            "local:my edit": [{"kind": "folder"}]})
        self.assertEqual(downloads.problems([{"tag_key": RUSK, "missing": 0}]), {}, "nothing wrong: not in it")

    def test_a_local_folder_thats_gone_is_still_shown(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        own = base / "My Edit"
        own.mkdir()
        (own / "edit.unitypackage").write_bytes(b"pkg")
        catalog = [{"store": "Local", "name": "My Edit", "creator": "Me", "folder": "Local/_linked/My Edit",
                    "files": ["edit.unitypackage"], "location": str(own)},
                   {"store": "Booth", "name": "Rusk", "creator": "Kitsu Studio", "folder": "Booth/Kitsu Studio/Rusk",
                    "files": ["rusk.zip"]}]
        index = downloads.build_index(base / "dl", catalog)
        self.assertEqual([(a["name"], a["folder_gone"]) for a in index["assets"]], [("My Edit", False)],
                         "a download with every file gone isn't one any more (issue #24)")
        shutil.rmtree(own)
        (mine,) = downloads.build_index(base / "dl", catalog)["assets"]
        self.assertEqual((mine["name"], mine["folder_gone"], mine["missing"]), ("My Edit", True, 1),
                         "a Local folder that's gone is shown, saying so")


class DownloadsThatDidntFinish(IsolatedTestCase):
    def setUp(self):
        self.store = asset_updates.AssetUpdates(Path(tempfile.mkdtemp()) / "asset-updates.json")

    def test_kept_until_a_download_of_it_goes_through(self):
        report = downloader.Report()
        report.failed_product("booth", "Rusk", "Booth: Rusk / f1 - timed out", "rusk.zip: timed out")
        self.assertEqual(report.failed, ["Booth: Rusk / f1 - timed out"], "in the task's report, as before")
        self.store.after_download(set(), report.failed, set(), report.failed_keys)
        kept = self.store.load()["failed"]
        self.assertEqual((list(kept), kept[RUSK]["why"], kept[RUSK]["store"]), ([RUSK], "rusk.zip: timed out", "booth"))
        self.assertTrue(kept[RUSK]["at"])
        self.store.after_download({RUSK}, ["Booth: Rusk / f2 - gone"], {(RUSK, "f1")}, {RUSK: {"store": "booth", "why": "f2: gone"}})
        self.assertEqual(self.store.load()["failed"][RUSK]["why"], "f2: gone", "a file saved, another failed: still wrong")
        self.store.after_download({ANKO}, [], {(ANKO, "f1")}, {})
        self.assertIn(RUSK, self.store.load()["failed"], "another product's download says nothing of it")
        self.store.after_download({RUSK}, [], {(RUSK, "f2")}, {})
        self.assertEqual(self.store.load()["failed"], {}, "downloaded with nothing failing: fine")

    def test_forgotten_once_its_files_are_deleted(self):
        """Delete downloaded files (a removed product's): what didn't finish of its download isn't wrong any more."""
        self.store.after_download(set(), ["x"], set(), {RUSK: {"store": "booth", "why": "rusk.zip: timed out"},
                                                         ANKO: {"store": "booth", "why": "anko.zip: gone"}})
        self.store.forget_failed({RUSK, "booth:not-there"})
        self.assertEqual(list(self.store.load()["failed"]), [ANKO])

    def test_whats_kept_is_checked(self):
        self.store.path.write_text(json.dumps({"failed": {
            RUSK: {"store": "booth", "why": "x" * 900, "at": "2026"}, "nope": {"store": "nowhere"}, "": {"store": "booth"},
            "booth:y": "not a dict"}}), "utf-8")
        failed = self.store.load()["failed"]
        self.assertEqual(list(failed), [RUSK])
        self.assertEqual(len(failed[RUSK]["why"]), 300)


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class OnTheTiles(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        root = self.tmp / "dl"
        product(root, "111", "Rusk", {"rusk.unitypackage": b"pkg", "readme.txt": b"hi"})
        product(root, "222", "Anko", {"anko.unitypackage": b"anko"})
        product(root, "333", "Mochi", {"mochi.unitypackage": b"mochi"})
        cfg = {**config.load_config(), "root": str(root), "setup_done": True, "ui": {"toured": True}}
        downloader.build_catalog(cfg, root)
        (root / "Booth" / "Kitsu Studio" / "Rusk" / "readme.txt").unlink()   # a file gone from disk
        updates = asset_updates.AssetUpdates()
        self.addCleanup(storage.remove, updates.path, missing_ok=True)
        updates.after_download(set(), ["x"], set(), {ANKO: {"store": "booth", "why": "anko.unitypackage: timed out"}})
        self.srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        with self.srv.lib.lock:   # (in memory only)
            self.srv.lib.data["items"] = [library.item("booth", k, name=n, creator="Kitsu Studio", url=f"https://booth.pm/ja/items/{k}")
                                          for k, n in (("111", "Rusk"), ("222", "Anko"), ("333", "Mochi"))]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def test_marked_said_and_listed(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.locator("#grid .slot").first.wait_for()
            tile = lambda name: page.locator("#grid .slot", has=page.locator(".nm, .nm-t", has_text=name))   # noqa: E731
            # the Library's tiles
            tile("Mochi").wait_for()
            self.assertEqual(tile("Mochi").locator(".problem-mark").count(), 0, "nothing wrong: no mark")
            self.assertEqual(tile("Rusk").locator(".problem-mark").get_attribute("title"), "1 file is missing on disk.")
            self.assertEqual(tile("Rusk").locator(".problem-mark").evaluate("e => e.getBoundingClientRect().width"), 30,
                             "big enough to see on a tile")
            self.assertIn("1 file is missing on disk", tile("Rusk").get_attribute("aria-label"))
            self.assertIn("Its last download didn't finish", tile("Anko").get_attribute("aria-label"))
            # Downloads: the same, a Problems view of them, and what to do in a product's details
            page.click("nav.apptabs a[href='/downloads']")
            page.locator('#views [data-view="problems"]').wait_for()
            self.assertIn("2", page.locator('#views [data-view="problems"]').inner_text())
            page.click('#views [data-view="problems"]')
            page.wait_for_function("() => document.querySelectorAll('#grid .slot').length === 2")
            self.assertEqual(sorted(page.locator("#grid .slot .nm-t, #grid .slot .nm").all_inner_texts()), ["Anko", "Rusk"])
            tile("Anko").click()
            page.locator("#detail .d-problems li").first.wait_for()
            self.assertIn("Its last download didn't finish (anko.unitypackage: timed out). Download it again.",
                          page.locator("#detail .d-problems").inner_text())
            tile("Rusk").click()
            page.locator("#detail .d-problems li", has_text="1 file is missing on disk. Download it again").wait_for()
            browser.close()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
