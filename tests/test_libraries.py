"""Library folders on other drives: read as one library, kept up to date where each product is, moved between them,
and left alone (not downloaded again) while a drive is away. See hoard/libraries.py."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import config, downloader, downloads, libraries, safety, server  # noqa: E402
from hoard.safety import ACCESS_HEADER  # noqa: E402
from hoard.tags import tag_key  # noqa: E402


def product(base: Path, store: str, key: str, creator: str, name: str, files: dict[str, bytes], picture: bool = True):
    """A downloaded product in a library folder, as a sync leaves it: its files, picture and sealed record."""
    man = downloader.Manifest(base / store)
    rec = man.record(key, creator, name)
    folder = base / store / rec["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    for n, (rel, data) in enumerate(files.items(), 1):
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
        rec["files"][f"f{n}"] = {"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if picture:
        (folder / "_thumbnail.png").write_bytes(b"\x89PNG picture")
    rec.update(url=f"https://booth.pm/en/items/{key}" if store == "Booth" else None)
    man.save()
    return folder


class LibraryFolders(unittest.TestCase):

    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root, self.drive = self.base / "Hoard", self.base / "Drive E" / "Hoard"
        self.root.mkdir()
        self.drive.mkdir(parents=True)
        self.cfg = {**config.load_config(), "root": str(self.root), "library_folders": [str(self.drive)]}
        self.addCleanup(lambda: libraries._seen_file().unlink(missing_ok=True))
        self.addCleanup(downloader.integrity_file().unlink, missing_ok=True)
        product(self.root, "Booth", "111", "Kitsu Studio", "Rusk", {"rusk.unitypackage": b"pkg"})
        self.anko = product(self.drive, "Booth", "222", "Kitsu Studio", "Anko",
                            {"anko.unitypackage": b"anko", "Textures/body.png": b"png!"})

    def catalog(self):
        downloader.build_catalog(self.cfg, self.root)
        return json.loads((self.root / "catalog.json").read_text("utf-8"))

    def test_an_unusable_entry_takes_no_place(self):
        """The first 10 entries were taken before the unusable ones were left out, so a good 11th one was dropped."""
        good = [self.base / f"Drive {n}" for n in range(libraries.MAX_FOLDERS)]
        cfg = {**self.cfg, "library_folders": ["relative/path", str(self.root)] + [str(g) for g in good]}
        self.assertEqual(libraries.other_folders(cfg), good)

    def test_folders_noted_at_once_are_both_kept(self):
        """Two catalog builds noting different folders at the same time: each wrote over the other's."""
        import threading as th
        folders = [self.base / f"F{n}" for n in range(8)]
        workers = [th.Thread(target=libraries.remember, args=(f, "Booth", [f"k{n}"])) for n, f in enumerate(folders)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        seen = libraries._load_seen()
        self.assertEqual(sorted(seen), sorted(str(f) for f in folders))

    def test_read_as_one_library(self):
        cat = self.catalog()
        self.assertEqual(cat["version"], 4, "a newer format: older Hoard for Unity asks to be updated")
        self.assertEqual(safety.check_seal(cat, self.root / "catalog.json"), "sealed")
        by_name = {e["name"]: e for e in cat["assets"]}
        self.assertNotIn("library", by_name["Rusk"])
        self.assertEqual((by_name["Anko"]["library"], by_name["Anko"]["folder"]), (str(self.drive), "Booth/Kitsu Studio/Anko"))
        self.assertEqual(downloader.validate_catalog_entry(by_name["Anko"]), [])
        self.assertTrue((self.anko / "asset.json").is_file(), "its asset.json is beside it, on its own drive")
        index = downloads.build_index(self.root, cat["assets"], libraries.roots(self.cfg))
        a = next(x for x in index["assets"] if x["name"] == "Anko")
        self.assertEqual((a["folder"], a["library"], a["abs_folder"]), ("@1/Booth/Kitsu Studio/Anko", 1, str(self.anko)))
        self.assertEqual(a["thumb"], "@1/Booth/Kitsu Studio/Anko/_thumbnail.png")
        self.assertEqual(server.open_target(self.cfg, "@1/Booth/Kitsu Studio/Anko/anko.unitypackage"), self.anko / "anko.unitypackage")
        self.assertIsNone(server.open_target(self.cfg, "@2/Booth/x"), "not one of your folders")
        self.assertIsNone(server.open_target(self.cfg, "@1/../../etc"))
        # one folder only: the catalog stays as older readers know it
        only = {**self.cfg, "library_folders": []}
        downloader.build_catalog(only, self.root)
        cat = json.loads((self.root / "catalog.json").read_text("utf-8"))
        self.assertEqual((cat["version"], [e["name"] for e in cat["assets"]]), (3, ["Rusk"]))

    def test_a_folder_must_be_one_of_its_own(self):
        for bad, why in ((self.root / "Inside", "inside the downloads folder"), (self.base, "around the downloads folder"),
                         (self.drive, "already one"), (self.drive / "Sub", "inside another"),
                         (self.base / "nowhere", "not there"), ("Relative/Folder", "not a full path")):
            if isinstance(bad, Path) and "nowhere" not in str(bad):
                bad.mkdir(parents=True, exist_ok=True)
            with self.subTest(why), self.assertRaises(ValueError):
                libraries.check_new_folder(self.cfg, str(bad))
        other = self.base / "Drive F"
        other.mkdir()
        self.assertEqual(libraries.check_new_folder(self.cfg, str(other)), other)
        cfg = {**self.cfg, "library_folders": [str(self.drive), str(self.root / "x"), "relative", str(self.drive / "y")]}
        self.assertEqual(libraries.other_folders(cfg), [self.drive], "config.json's can't overlap either")

    def test_a_sync_keeps_a_product_where_it_is(self):
        man = downloader.StoreRecords(self.cfg, self.root, "Booth")
        anko = man.record("222", "Kitsu Studio", "Anko")
        self.assertEqual(man.folder_of(anko), self.anko, "updated on its own drive")
        new = man.record("333", "Kitsu Studio", "Mochi")
        self.assertEqual(man.folder_of(new), self.root / "Booth" / "Kitsu Studio" / "Mochi", "new: the downloads folder")
        new["files"]["f1"] = {"path": "mochi.zip", "size": 1}
        anko["last_synced"] = "now"
        man.save_changes()
        self.assertIn("333", downloader.Manifest(self.root / "Booth").assets)
        self.assertEqual(downloader.Manifest(self.drive / "Booth").assets["222"]["last_synced"], "now")
        self.assertNotIn("222", downloader.Manifest(self.root / "Booth").assets)

    def test_a_drive_that_isnt_connected_is_left_alone(self):
        self.catalog()   # Hoard has seen what the drive holds
        away = self.base / "Drive E (unplugged)"
        self.drive.parent.rename(away)
        self.addCleanup(lambda: away.rename(self.drive.parent) if away.exists() else None)
        cat = self.catalog()
        self.assertEqual([e["name"] for e in cat["assets"]], ["Rusk"], "not listed while it's away...")
        report = downloader.Report()
        man = downloader.StoreRecords(self.cfg, self.root, "Booth")
        self.assertTrue(man.away("222", "Booth: Anko", report), "...and not downloaded again into the downloads folder")
        self.assertIn("isn't connected", report.skipped[0])
        self.assertFalse(man.away("111", "Booth: Rusk", report))
        result = downloader.check_integrity(self.root, others=libraries.other_folders(self.cfg))
        self.assertEqual((result["away"], result["missing"]), ([str(self.drive)], []), "the check says so, not missing")
        self.assertIn("isn't connected", downloader.integrity_summary(result))
        self.assertFalse(libraries.view(self.cfg)[1]["available"])

    def test_checks_and_deleting_cover_every_folder(self):
        (self.anko / "anko.unitypackage").write_bytes(b"ANKO")   # changed behind Hoard's back
        result = downloader.check_integrity(self.root, others=libraries.other_folders(self.cfg))
        self.assertEqual((result["products"], result["changed"]), (2, ["Anko (Booth): anko.unitypackage"]))
        done = downloader.delete_downloaded_files(self.cfg, self.root, {tag_key("Booth", "Anko")})
        self.assertEqual(done["files"], 3, "its two files and its picture")
        self.assertFalse(self.anko.exists())
        copy = downloader.make_editable_copy({**self.cfg, "edits_root": str(self.base / "Edits")}, self.root,
                                             tag_key("Booth", "Rusk"))
        self.assertEqual(copy["files"], 1)

    def test_moving_a_product_to_another_drive_and_back(self):
        rusk = self.root / "Booth" / "Kitsu Studio" / "Rusk"
        (rusk / "my notes.txt").write_text("mine")   # of your own: it stays
        done = downloader.move_product(self.cfg, self.root, tag_key("Booth", "Rusk"), 1)
        moved = self.drive / "Booth" / "Kitsu Studio" / "Rusk"
        self.assertEqual((done["files"], done["to"]), (1, str(moved)))
        self.assertEqual((moved / "rusk.unitypackage").read_bytes(), b"pkg")
        self.assertTrue((moved / "_thumbnail.png").is_file(), "its picture goes with it")
        self.assertEqual(sorted(p.name for p in rusk.iterdir()), ["my notes.txt"], "the originals went; yours stayed")
        self.assertNotIn("111", downloader.Manifest(self.root / "Booth").assets)
        self.assertEqual(downloader.Manifest(self.drive / "Booth").assets["111"]["folder"], "Kitsu Studio/Rusk")
        self.assertEqual({e["name"]: e.get("library") for e in self.catalog()["assets"]}["Rusk"], str(self.drive))
        downloader.move_product(self.cfg, self.root, tag_key("Booth", "Rusk"), 0)
        self.assertEqual((rusk / "rusk.unitypackage").read_bytes(), b"pkg", "and back")
        self.assertFalse(moved.exists())
        with self.assertRaises(ValueError):
            downloader.move_product(self.cfg, self.root, tag_key("Booth", "Rusk"), 0)   # already there
        with self.assertRaises(ValueError):
            downloader.move_product(self.cfg, self.root, tag_key("Booth", "Rusk"), 5)   # not a folder of yours

    def test_a_move_that_goes_wrong_leaves_it_where_it_was(self):
        (self.anko / "Textures" / "body.png").write_bytes(b"PNG!")   # same size, different contents
        with self.assertRaises(ValueError):
            downloader.move_product(self.cfg, self.root, tag_key("Booth", "Anko"), 0)
        self.assertTrue((self.anko / "anko.unitypackage").is_file())
        self.assertIn("222", downloader.Manifest(self.drive / "Booth").assets)
        self.assertFalse((self.root / "Booth" / "Kitsu Studio" / "Anko").exists(), "what was copied went again")
        self.assertNotIn("222", downloader.Manifest(self.root / "Booth").assets)


class Server(unittest.TestCase):
    """Settings add and forget library folders; Downloads moves a product, as a job; pictures are served from every
    library folder, named by its number, never by a path from the request."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root, self.drive = self.base / "Hoard", self.base / "Drive E"
        self.root.mkdir()
        self.drive.mkdir()
        self.addCleanup(lambda: libraries._seen_file().unlink(missing_ok=True))
        product(self.root, "Booth", "111", "Kitsu Studio", "Rusk", {"rusk.unitypackage": b"pkg"})
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.root), "setup_done": True},
                                    lan=False)
        self.srv.config_path = self.base / "config.json"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=30)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Content-Type": "application/json", ACCESS_HEADER: self.srv.key})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, (json.loads(data) if data and r.getheader("Content-Type", "").startswith("application/json") else data)

    def test_add_move_serve_and_forget(self):
        status, got = self.call("POST", "/api/libraries/add", {"path": str(self.root / "Booth")})
        self.assertEqual(status, 400, "inside the downloads folder")
        status, got = self.call("POST", "/api/libraries/add", {"path": str(self.drive)})
        self.assertEqual(status, 200, got)
        self.assertEqual([f["path"] for f in got["libraries"]], [str(self.root), str(self.drive)])
        self.assertEqual(json.loads((self.base / "config.json").read_text("utf-8"))["library_folders"], [str(self.drive)])
        status, got = self.call("POST", "/api/move", {"key": tag_key("Booth", "Rusk"), "to": 1})
        self.assertEqual(status, 200, got)
        for _ in range(100):
            if not self.srv.jobs.state["running"]:
                break
            time.sleep(0.05)
        self.assertEqual(self.srv.jobs.history[-1]["outcome"], "done", self.srv.jobs.history[-1]["message"])
        self.assertTrue((self.drive / "Booth" / "Kitsu Studio" / "Rusk" / "rusk.unitypackage").is_file())
        status, assets = self.call("GET", "/api/assets?rescan=1")
        (a,) = assets["assets"]
        self.assertEqual((a["folder"], a["library"]), ("@1/Booth/Kitsu Studio/Rusk", 1))
        status, picture = self.call("GET", "/files/" + a["thumb"].replace(" ", "%20"))
        self.assertEqual((status, picture), (200, b"\x89PNG picture"), "served from the other drive")
        for bad in ("/files/@9/Booth/x.png", "/files/@1/../Hoard/Booth/Kitsu%20Studio/Rusk/_thumbnail.png",
                    "/files/@x/a.png"):
            self.assertEqual(self.call("GET", bad)[0], 404, bad)
        status, got = self.call("POST", "/api/libraries/remove", {"n": 1})
        self.assertEqual((status, len(got["libraries"])), (200, 1))
        self.assertTrue((self.drive / "Booth" / "Kitsu Studio" / "Rusk" / "rusk.unitypackage").is_file(), "files stay")
        status, assets = self.call("GET", "/api/assets?rescan=1")
        self.assertEqual(assets["assets"], [], "and leave the library until it's added again")

    def test_the_pages(self):
        """Settings adds a library folder in one step and lists every folder; each gets a tab in Downloads, with its
        count; a product's details say where it's kept and move it, and so does the selection bar for several."""
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.launch()
        except Exception:   # no Playwright browser here
            self.skipTest("needs Playwright's Chromium (python -m playwright install chromium)")
        self.addCleanup(pw.stop)
        self.addCleanup(browser.close)
        page = browser.new_page(viewport={"width": 1300, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{self.srv.url}downloads#key={self.srv.key}")
        page.get_by_text("Rusk").first.wait_for()
        self.assertTrue(page.locator("#drives").is_hidden(), "no folder tabs with only the downloads folder")
        page.click("#settingsBtn")
        page.locator("#setLibs .librow").get_by_text("Downloads folder").wait_for()
        self.assertEqual(page.locator("#setLibs .librow").count(), 1)
        self.assertIn("1 product", page.locator("#setLibs .librow").inner_text())
        page.fill("#libPath", str(self.root / "Booth"))
        page.click("#libAdd")
        page.get_by_text("inside it, or around it").wait_for()
        self.srv.pick_path = lambda kind, start: str(self.drive)   # as Hoard's window does: one step
        page.reload()
        page.get_by_text("Rusk").first.wait_for()
        page.click("#settingsBtn")
        page.click("#libPick")
        name = libraries.label(self.drive)   # "Drive E", or "Drive E (C:)" on Windows
        page.get_by_text(f"Added {name}: nothing downloaded there yet. It has a tab in Downloads.").wait_for()
        page.locator("#setLibs .librow").get_by_text(str(self.drive)).wait_for()
        page.click("#settingsBtn")
        page.locator("#drives [data-lib='1']").wait_for()
        self.assertEqual([" ".join(t.split()) for t in page.locator("#drives [data-lib]").all_inner_texts()],
                         ["Downloads folder 1", f"{name} 0"])
        page.click("#drives [data-lib='1']")
        page.wait_for_function("() => document.querySelectorAll('.slot').length === 0")
        page.click("#drives [data-lib='1']")   # chosen again: every folder
        page.locator(".slot").first.click()
        page.get_by_text("Kept in Downloads folder").first.wait_for()
        page.click("[data-act=move]")
        page.click("#askDialog button[value=yes]")
        moved = self.drive / "Booth" / "Kitsu Studio" / "Rusk" / "rusk.unitypackage"
        for _ in range(100):
            if moved.is_file():
                break
            time.sleep(0.1)
        self.assertTrue(moved.is_file())
        page.wait_for_function("() => DATA.assets.length === 1 && DATA.assets[0].library === 1")
        page.click("#drives [data-lib='1']")
        page.locator(".slot").first.wait_for()
        page.click("#drives [data-lib='1']")
        # several at once, from the selection bar: back to the downloads folder
        page.click("#selectBtn")
        page.locator("#bulkMoveWrap").wait_for()
        page.locator(".slot").first.click()
        page.select_option("#bulkMoveTo", "0")
        page.click("#bulkMove")
        page.click("#askDialog button[value=yes]")
        back = self.root / "Booth" / "Kitsu Studio" / "Rusk" / "rusk.unitypackage"
        for _ in range(100):
            if back.is_file() and not moved.exists():
                break
            time.sleep(0.1)
        self.assertTrue(back.is_file() and not moved.exists())
        page.wait_for_function("() => DATA.assets.length === 1 && DATA.assets[0].library === 0", timeout=20000)
        page.click("#settingsBtn")
        page.click("[data-lib-remove='1']")
        page.click("#askDialog button[value=yes]")
        page.get_by_text(f"{name} is no longer part of your library.").wait_for()
        page.wait_for_function("() => document.querySelector('#drives').hidden")
        self.assertEqual(errors, [])
        page.close()

if __name__ == "__main__":
    unittest.main()
