"""Previous versions (hoard/previous.py): the file an update replaces is kept, and can be put back."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hoard import downloader, downloads, previous, safety
from hoard.tags import tag_key
from tests import test_libraries as library_folders   # (its fixture; imported as a module, so its tests run once)


def replace(dest: Path, data: bytes) -> None:
    """A download putting a new file in place, as every download does (safety.move_into_place)."""
    part = dest.with_name(dest.name + ".part")
    fh, identity = safety.open_part(part, resume=False)
    with fh:
        fh.write(data)
    safety.move_into_place(part, dest, identity)


class Keeping(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.dir, True)
        self.addCleanup(previous.set_keep, 1)
        self.file = self.dir / "Hoodie.zip"
        self.file.write_bytes(b"v1")

    def test_an_update_keeps_what_it_replaces(self):
        replace(self.file, b"v2")
        self.assertEqual(self.file.read_bytes(), b"v2")
        [v] = previous.listed(self.dir)
        self.assertEqual((v["file"], v["size"]), ("Hoodie.zip", 2))
        self.assertEqual((self.dir / previous.FOLDER / v["stamp"] / "Hoodie.zip").read_bytes(), b"v1")

    def test_only_as_many_as_chosen(self):
        previous.set_keep(2)
        for n, data in enumerate((b"v2", b"v3", b"v4"), 2):
            with mock.patch.object(previous.time, "strftime", return_value=f"2026-10-0{n} 120000"):
                replace(self.file, data)
        self.assertEqual([(v["stamp"], v["size"]) for v in previous.listed(self.dir)],
                         [("2026-10-04 120000", 2), ("2026-10-03 120000", 2)])
        self.assertEqual(sorted(p.name for p in (self.dir / previous.FOLDER).iterdir()),
                         ["2026-10-03 120000", "2026-10-04 120000"], "emptied folders go")

    def test_none_kept(self):
        previous.set_keep(0)
        replace(self.file, b"v2")
        self.assertEqual(previous.listed(self.dir), [])
        self.assertFalse((self.dir / previous.FOLDER).exists())

    def test_files_an_update_replaces_at_once_share_a_folder(self):
        previous.set_keep(2)
        (self.dir / "Hoodie.unitypackage").write_bytes(b"p1")
        with mock.patch.object(previous.time, "strftime", return_value="2026-10-10 120000"):
            replace(self.file, b"v2")
            replace(self.dir / "Hoodie.unitypackage", b"p2")
            replace(self.file, b"v3")   # the same file twice in one second: a folder of its own
        self.assertEqual(sorted((v["stamp"], v["file"]) for v in previous.listed(self.dir)),
                         [("2026-10-10 120000", "Hoodie.unitypackage"), ("2026-10-10 120000", "Hoodie.zip"),
                          ("2026-10-10 120000-2", "Hoodie.zip")])

    def test_a_new_file_or_an_empty_one_isnt_kept(self):
        replace(self.dir / "new.zip", b"x")
        (self.dir / "empty.zip").write_bytes(b"")
        replace(self.dir / "empty.zip", b"x")
        self.assertEqual(previous.listed(self.dir), [])

    def test_restore_and_undo(self):
        replace(self.file, b"v2")
        [v] = previous.listed(self.dir)
        previous.restore(self.dir, v["stamp"], "Hoodie.zip")
        self.assertEqual(self.file.read_bytes(), b"v1")
        [kept] = previous.listed(self.dir)
        self.assertEqual((self.dir / previous.FOLDER / kept["stamp"] / "Hoodie.zip").read_bytes(), b"v2", "kept, to undo")
        previous.restore(self.dir, kept["stamp"], "Hoodie.zip")
        self.assertEqual(self.file.read_bytes(), b"v2")

    def test_restore_only_whats_there(self):
        replace(self.file, b"v2")
        [v] = previous.listed(self.dir)
        for stamp, name in ((v["stamp"], "../Hoodie.zip"), ("../..", "Hoodie.zip"), (v["stamp"], "other.zip"),
                            ("2026-01-01 000000", "Hoodie.zip")):
            with self.subTest(stamp=stamp, name=name), self.assertRaises(ValueError):
                previous.restore(self.dir, stamp, name)
        self.assertEqual(self.file.read_bytes(), b"v2")


class WithTheRecords(unittest.TestCase):
    """Restoring updates the product's record; deleting and moving a product take its previous versions too."""
    catalog = library_folders.LibraryFolders.catalog

    def setUp(self):
        library_folders.LibraryFolders.setUp(self)   # (its folders, not its tests)
        self.addCleanup(previous.set_keep, 1)
        self.rusk = self.root / "Booth" / "Kitsu Studio" / "Rusk"
        replace(self.rusk / "rusk.unitypackage", b"pkg v2")   # an update, recorded as a download records it
        man = downloader.Manifest(self.root / "Booth")
        files = man.assets["111"]["files"]
        files[next(iter(files))] = {"path": "rusk.unitypackage", "size": 6}
        man.save()

    def test_restoring_updates_the_record(self):
        downloader.check_integrity(self.root, others=[self.drive])   # fingerprints the new file
        [v] = previous.listed(self.rusk)
        downloader.restore_previous(self.cfg, self.root, self.rusk, v["stamp"], "rusk.unitypackage")
        self.assertEqual((self.rusk / "rusk.unitypackage").read_bytes(), b"pkg")
        f = next(iter(downloader.Manifest(self.root / "Booth").assets["111"]["files"].values()))
        self.assertEqual(f["size"], 3)
        self.assertNotIn("sha256", f)
        result = downloader.check_integrity(self.root, others=[self.drive])
        self.assertEqual(result["changed"], [], "the restored file is taken as it is, not called changed")

    def test_not_a_download_of_hoards(self):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        with self.assertRaises(ValueError):
            downloader.restore_previous(self.cfg, self.root, elsewhere, "2026-10-10 120000", "x.zip")

    def test_in_the_downloads_index(self):
        cat = self.catalog()
        idx = downloads.build_index(self.root, cat["assets"], [self.root, self.drive])
        rusk = next(a for a in idx["assets"] if a["name"] == "Rusk")
        self.assertEqual([v["file"] for v in rusk["previous"]], ["rusk.unitypackage"])
        self.assertEqual([f["path"] for f in rusk["files"]], ["rusk.unitypackage"], "not among its files")

    def test_moved_with_it(self):
        downloader.move_product(self.cfg, self.root, tag_key("Booth", "Rusk"), 1)
        moved = self.drive / "Booth" / "Kitsu Studio" / "Rusk"
        self.assertEqual([v["file"] for v in previous.listed(moved)], ["rusk.unitypackage"])
        self.assertFalse((self.rusk / previous.FOLDER).exists(), "nothing left behind")

    def test_deleted_with_it(self):
        done = downloader.delete_downloaded_files(self.cfg, self.root, {tag_key("Booth", "Rusk")})
        self.assertEqual(done["files"], 3, "its file, its picture and its previous version")
        self.assertFalse(self.rusk.exists())


class Setting(unittest.TestCase):
    def test_choices(self):
        from hoard import config, server
        cfg = config.load_config()
        self.assertEqual(server.public_settings(cfg)["keep_previous"], 1)
        self.assertEqual(server.apply_settings(cfg, {"keep_previous": 3}), {"keep_previous": 3})
        for bad in (4, -1, True, "2", 99):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                server.apply_settings(cfg, {"keep_previous": bad})
        self.assertEqual(server.keep_previous({"keep_previous": "lots"}), 1)


try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Page(unittest.TestCase):
    def test_restore_from_downloads(self):
        import threading
        from playwright.sync_api import sync_playwright
        from hoard import config, server
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        root = tmp / "dl"
        folder = root / "Booth" / "Kitsu" / "Hoodie"
        folder.mkdir(parents=True)
        (folder / "Hoodie.zip").write_bytes(b"v1")
        man = downloader.Manifest(root / "Booth")
        rec = man.record("1", "Kitsu", "Hoodie")
        rec.update(name="Hoodie", creator="Kitsu")
        rec["files"]["f"] = {"path": "Hoodie.zip", "size": 2}
        man.save()
        replace(folder / "Hoodie.zip", b"v2!")
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
            page.click("#grid .slot")
            page.locator("#detail [data-act='restore']").click()
            page.locator("dialog[open] button", has_text="Restore").click()
            page.get_by_text("Put back Hoodie.zip.").wait_for()
            browser.close()
        self.assertEqual((folder / "Hoodie.zip").read_bytes(), b"v1")
        self.assertEqual([v["size"] for v in previous.listed(folder)], [3], "the one it replaced is kept")


if __name__ == "__main__":
    unittest.main()
