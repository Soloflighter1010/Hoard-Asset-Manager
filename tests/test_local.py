"""Issue #80: Local, your own packages beside what you bought: copied into Hoard, or listed where they are."""
from __future__ import annotations

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

from hoard import config, downloader, downloads, local, server  # noqa: E402
from hoard.safety import ACCESS_HEADER  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _pw:
        _pw.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False


def tree(folder: Path) -> dict:
    """Every file under folder, with its contents: to show nothing in it changed."""
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


class LocalItems(unittest.TestCase):

    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()   # (Windows: the long form, as Hoard resolves it, not RUNNER~1)
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "Hoard"
        self.root.mkdir()
        self.src = self.base / "My Textures"
        (self.src / "Skins").mkdir(parents=True)
        (self.src / "Textures.unitypackage").write_bytes(b"pkg")
        (self.src / "Skins" / "skin.png").write_bytes(b"png!")
        (self.src / "Thumbs.db").write_bytes(b"clutter")
        self.cfg = {**config.load_config(), "root": str(self.root)}
        self.addCleanup(downloader.integrity_file().unlink, missing_ok=True)

    def catalog(self):
        return downloader.collect_catalog(self.cfg, self.root)[0]

    def test_a_copy_is_hoards(self):
        rec = local.add(self.cfg, self.root, str(self.src), note="A commission", copy=True)
        copy = self.root / "Local" / "You" / "My Textures"
        self.assertEqual(sorted(f["path"] for f in rec["files"].values()), ["Skins/skin.png", "Textures.unitypackage"])
        self.assertEqual((copy / "Skins" / "skin.png").read_bytes(), b"png!")
        self.assertTrue(all(len(f["sha256"]) == 64 for f in rec["files"].values()), "checked like a download")
        [entry] = self.catalog()
        self.assertEqual((entry["store"], entry["folder"], entry["note"]), ("Local", "Local/You/My Textures", "A commission"))
        self.assertNotIn("location", entry)
        (self.src / "Textures.unitypackage").write_bytes(b"changed")   # the original, changed later
        self.assertEqual((copy / "Textures.unitypackage").read_bytes(), b"pkg")
        (copy / "Skins" / "skin.png").write_bytes(b"evil")
        os.utime(copy / "Skins" / "skin.png", ns=(0, 1))
        self.assertEqual(len(downloader.check_integrity(self.root)["changed"]), 1, "a changed copy is noticed")
        done = local.remove(self.cfg, self.root, next(iter(downloader.Manifest(self.root / "Local").assets)))
        self.assertEqual(done, {"deleted": 2, "listed": False})
        self.assertFalse((self.root / "Local" / "You").exists())
        self.assertTrue((self.src / "Skins" / "skin.png").exists(), "your original is never touched")

    def test_listed_where_it_is_is_never_written(self):
        before = tree(self.src)
        rec = local.add(self.cfg, self.root, str(self.src), name="Working Folder", copy=False)
        self.assertEqual(rec["location"], str(self.src))
        [entry] = self.catalog()
        self.assertEqual((entry["store"], entry["location"]), ("Local", str(self.src)))
        downloader.build_catalog(self.cfg, self.root)
        index = downloads.build_index(self.root, self.catalog())
        [a] = index["assets"]
        self.assertEqual((a["linked"], a["missing"], len(a["files"])), (True, 0, 2))
        # its picture: a copy in Hoard's own folder, since only pictures in the downloads folder are shown
        self.assertEqual(a["thumb"], a["folder"] + "/_thumbnail.png")
        self.assertEqual((self.root / a["thumb"]).read_bytes(), b"png!")
        self.assertEqual(server.open_target(self.cfg, a["folder"]), self.src)
        self.assertEqual(server.open_target(self.cfg, a["folder"] + "/Skins/skin.png"), self.src / "Skins" / "skin.png")
        self.assertEqual(downloader.check_integrity(self.root)["files"], 0, "the routine checks leave it alone")
        self.assertEqual(downloader.delete_downloaded_files(self.cfg, self.root, {a["tag_key"]})["files"], 0)
        downloader.make_editable_copy({**self.cfg, "edits_root": str(self.base / "Edits")}, self.root, a["tag_key"])
        self.assertEqual(tree(self.src), before, "nothing in your folder was written, moved or deleted")
        (self.src / "new.txt").write_text("added later")
        key = next(iter(downloader.Manifest(self.root / "Local").assets))
        self.assertEqual(len(local.rescan(self.cfg, self.root, key)["files"]), 3)
        self.assertEqual(local.remove(self.cfg, self.root, key), {"deleted": 0, "listed": True})
        self.assertEqual(sorted(tree(self.src)), sorted(before) + ["new.txt"])
        self.assertFalse((self.root / "Local" / "_linked").exists(), "its picture goes with it")
        self.assertEqual(self.catalog(), [])

    def test_a_preview_picture_comes_first_and_a_rescan_follows_it(self):
        (self.src / "Preview.jpg").write_bytes(b"jpg!")
        local.add(self.cfg, self.root, str(self.src), copy=False)
        key = next(iter(downloader.Manifest(self.root / "Local").assets))
        own = self.root / "Local" / "_linked" / key
        self.assertEqual([p.name for p in own.glob("_thumbnail.*")], ["_thumbnail.jpg"])
        (self.src / "Preview.jpg").unlink()
        local.rescan(self.cfg, self.root, key)
        self.assertEqual([p.name for p in own.glob("_thumbnail.*")], ["_thumbnail.png"], "the picture it had is gone, so another")

    def test_only_a_manifest_hoard_sealed_names_a_folder(self):
        local.add(self.cfg, self.root, str(self.src), copy=False)
        mpath = self.root / "Local" / "_manifest.json"
        raw = json.loads(mpath.read_text("utf-8"))
        for rec in raw["assets"].values():
            rec["location"] = str(self.base)   # somewhere else, written by something other than Hoard
        mpath.write_text(json.dumps(raw), "utf-8")
        self.assertTrue(all("location" not in e for e in self.catalog()))
        booth = self.root / "Booth"
        booth.mkdir()
        (booth / "_manifest.json").write_text(json.dumps({"assets": {"1": {"name": "X", "creator": "Y", "folder": "Y/X",
                                                          "location": str(self.src), "files": {}}}}), "utf-8")
        self.assertNotIn("location", downloader.Manifest(booth).assets["1"], "only Local items have a place of their own")

    def test_what_can_be_added(self):
        for path, copy, why in (("", True, "Enter"), ("relative/path", True, "full path"), (str(self.base / "nope"), True, "Nothing"),
                                (str(self.root), True, "already inside"), (str(self.src / "Textures.unitypackage"), False, "choose its folder")):
            with self.assertRaises(ValueError) as e:
                local.add(self.cfg, self.root, path, copy=copy)
            self.assertIn(why, str(e.exception), path)
        rec = local.add(self.cfg, self.root, str(self.src / "Textures.unitypackage"), copy=True)
        self.assertEqual((rec["name"], [f["path"] for f in rec["files"].values()]), ("Textures", ["Textures.unitypackage"]))

    @unittest.skipIf(sys.platform == "win32", "symlinks need extra rights on Windows")
    def test_links_are_left_out(self):
        secret = self.base / "secret"
        secret.mkdir()
        (secret / "key.txt").write_text("secret")
        os.symlink(secret, self.src / "Linked Folder")
        os.symlink(secret / "key.txt", self.src / "key.txt")
        rec = local.add(self.cfg, self.root, str(self.src), copy=True)
        self.assertEqual(sorted(f["path"] for f in rec["files"].values()), ["Skins/skin.png", "Textures.unitypackage"])
        os.symlink(self.src, self.base / "Shortcut")
        with self.assertRaises(ValueError):
            local.add(self.cfg, self.root, str(self.base / "Shortcut"), copy=False)

    def test_the_server(self):
        srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def call(path, body):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
            c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key})
            r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
            return r.status, data
        self.assertEqual(call("/api/local/add", {"path": "nope"})[0], 400, "a path that can't be used is said straight away")
        status, data = call("/api/local/add", {"path": str(self.src), "copy": False})
        self.assertEqual((status, data.get("queued")), (200, False))
        for _ in range(100):
            if not srv.jobs.state["running"] and self.catalog():
                break
            time.sleep(0.1)
        [entry] = self.catalog()
        self.assertIs(srv.cfg["local_copy"], False, "the choice is offered next time")
        self.assertEqual(call("/api/local/remove", {"folder": entry["folder"]})[0], 400, "not without confirming")
        self.assertEqual(call("/api/local/remove", {"folder": "Booth/x", "confirm": True})[0], 404)
        self.assertEqual(call("/api/local/remove", {"folder": entry["folder"], "confirm": True}), (200, {"ok": True, "deleted": 0, "listed": True}))
        self.assertTrue(self.src.exists())


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class LocalPage(unittest.TestCase):

    def test_add_your_own(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        root, src = base / "Hoard", base / "Commission Kit"
        root.mkdir()
        src.mkdir()
        (src / "Kit.unitypackage").write_bytes(b"pkg")
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1300, "height": 860})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.entry_url())
            page.click("nav.apptabs a[href='/downloads#store=Local']")
            page.wait_for_url("**/downloads#store=Local")
            page.locator("#stores [data-store='Local'][aria-checked='true']").wait_for()
            page.click("#localAdd")
            page.locator("#localPanel.win:not([hidden])").wait_for()
            self.assertTrue(page.locator("#localCopy").is_checked(), "copying is offered first")
            page.fill("#localPath", str(src))
            page.fill("#localNote", "A commission")
            page.check("#localLink")
            page.click("#localGo")
            page.locator("#grid .slot", has_text="Commission Kit").wait_for(timeout=20000)
            page.locator("#grid .slot", has_text="Commission Kit").click()
            page.get_by_text("Listed where it is").wait_for()
            page.get_by_text("For A commission.").wait_for()
            page.once("dialog", lambda d: d.accept())
            page.locator("[data-act='local-remove']").click()
            page.get_by_text("Took Commission Kit out of Local").wait_for()
            self.assertTrue((src / "Kit.unitypackage").exists())
            self.assertEqual(errors, [])
            browser.close()


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Browse(unittest.TestCase):
    """Typing a full path to a folder was the hardest part of setting Hoard up. In Hoard's own window, Browse opens
    the system's folder (or file) picker; in a web browser, where there's no way to ask for one, it isn't shown."""

    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        (base / "Hoard").mkdir()
        self.src = base / "Commission Kit"
        self.src.mkdir()
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(base / "Hoard"), "setup_done": True},
                                    lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def test_browse(self):
        asked = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1300, "height": 860})
            page.goto(self.srv.entry_url())
            page.goto(self.srv.url + "downloads")
            page.click("#localAdd")
            page.locator("#localPanel.win:not([hidden])").wait_for()
            self.assertTrue(page.locator("#localBrowseFolder").is_hidden(), "a web browser has no picker to offer")
            self.srv.pick_path = lambda kind, start: asked.append(kind) or str(self.src)   # as Hoard's window does
            page.reload()
            page.click("#localAdd")
            page.click("#localBrowseFolder")
            page.wait_for_function("() => document.querySelector('#localPath').value !== ''")
            self.assertEqual(page.locator("#localPath").input_value(), str(self.src))
            page.check("#localLink")
            page.click("#localBrowseFile")
            page.wait_for_timeout(300)
            self.assertTrue(page.locator("#localCopy").is_checked(), "a single file is copied in")
            self.assertEqual(asked, ["folder", "file"])
            page.keyboard.press("Escape")
            page.click("#settingsBtn")
            page.locator("#setRootBrowse").wait_for()
            self.assertTrue(page.locator("#setRootBrowse").is_visible())
            browser.close()

    def test_local_is_a_place_of_its_own(self):
        """Local, in the bar, opened Downloads with Downloads still highlighted. Now the bar, the heading and the
        window's title say Local, and go back to Downloads with it."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1300, "height": 860})
            page.goto(self.srv.entry_url())
            page.goto(self.srv.url + "downloads")
            page.click('.apptabs a[href="/downloads#store=Local"]')
            page.wait_for_function("() => document.title === 'Hoard: Local'")
            self.assertEqual(page.get_attribute('.apptabs a[href="/downloads#store=Local"]', "aria-current"), "page")
            self.assertIsNone(page.get_attribute('.apptabs a[href="/downloads"]', "aria-current"))
            page.click('#stores [data-store=""]')
            page.wait_for_function("() => document.title === 'Hoard: Downloads'")
            self.assertEqual(page.get_attribute('.apptabs a[href="/downloads"]', "aria-current"), "page")
            browser.close()

    def test_no_picker_says_so(self):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=20)
        c.request("POST", "/api/pick", body=json.dumps({"kind": "folder"}),
                  headers={"Content-Type": "application/json", ACCESS_HEADER: self.srv.key})
        r = c.getresponse()
        self.assertEqual(r.status, 409)
        self.assertIn("Type the path", json.loads(r.read())["error"])
        c.close()

if __name__ == "__main__":
    unittest.main()
