"""Tests for Hoard as one app: settings, downloading with progress and Stop, and moving over from 1.x.

Run from the repository root:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import http.client
import json
import os
import re
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

from hoard import cli, common, config, downloader, jobs, library, paths, server, tags  # noqa: E402
downloader.RETRY_WAITS = (0.0, 0.0, 0.0)   # failed downloads are still tried again, without the wait
from hoard.safety import ACCESS_HEADER, header_safe  # noqa: E402


class Settings(unittest.TestCase):
    """What the Settings panel may change, and how."""

    def test_valid_changes(self):
        cfg = config.load_config()
        folder = tempfile.mkdtemp()
        change = server.apply_settings(cfg, {"root": folder, "offline_images": False, "browser_channel": "msedge",
                                             "request_delay": 2, "stores": {"booth": {"enabled": False, "include_gifts": False}}})
        self.assertEqual(change["root"], folder)
        self.assertEqual(change["booth"], {"enabled": False, "include_gifts": False})
        self.assertEqual(server.apply_settings(cfg, {"root": ""})["root"], "")  # back to the default folder

    def test_refusals(self):
        cfg = config.load_config()
        for bad in ({"root": "relative/folder"}, {"root": __file__}, {"browser_channel": "firefox"},
                    {"request_delay": 0}, {"request_delay": "fast"}, {"stores": {"evilstore": {"enabled": True}}}):
            with self.assertRaises(ValueError, msg=bad):
                server.apply_settings(cfg, bad)
        # options that don't belong to a store are ignored rather than written
        self.assertEqual(server.apply_settings(cfg, {"stores": {"payhip": {"include_gifts": True, "enabled": True}}}),
                         {"payhip": {"enabled": True}})

    def test_itch_game_builds(self):
        cfg = config.load_config()
        self.assertTrue(server.public_settings(cfg)["stores"]["itch"]["skip_game_builds"], "skipped unless you want them")
        self.assertEqual(server.apply_settings(cfg, {"stores": {"itch": {"skip_game_builds": False}}}),
                         {"itch": {"skip_game_builds": False}})
        self.assertEqual(server.apply_settings(cfg, {"stores": {"booth": {"skip_game_builds": False}}}), {"booth": {}})

    def test_a_new_store_waits_to_be_turned_on(self):
        """itch.io came in 2.5.0: an install set up before then keeps the stores it chose; a new one starts with all."""
        folder = Path(tempfile.mkdtemp())
        (folder / "config.json").write_text(json.dumps({"setup_done": True, "booth": {"enabled": True}}), "utf-8")
        self.assertFalse(config.load_config(folder / "config.json")["itch"]["enabled"])
        (folder / "config.json").write_text(json.dumps({"setup_done": True, "itch": {"enabled": True}}), "utf-8")
        self.assertTrue(config.load_config(folder / "config.json")["itch"]["enabled"], "once you've chosen, your choice")
        (folder / "config.json").write_text(json.dumps({"setup_done": False}), "utf-8")
        self.assertTrue(config.load_config(folder / "config.json")["itch"]["enabled"], "setting up, it's offered like the rest")
        self.assertTrue(config.load_config(folder / "missing.json")["itch"]["enabled"])

    def test_default_downloads_folder(self):
        self.assertEqual(config.root_dir({"root": ""}), paths.default_downloads())
        self.assertTrue(str(paths.default_downloads()).endswith("Hoard"))

    def test_actions_only_from_this_computer_as_json(self):
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            c.request("POST", "/api/settings", body="root=C:/x", headers={"Content-Type": "application/x-www-form-urlencoded"})
            r = c.getresponse(); r.read(); c.close()
            self.assertEqual(r.status, 403)
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            c.request("GET", "/api/settings", headers={"Host": "evil.example"})
            r = c.getresponse(); r.read(); c.close()
            self.assertEqual(r.status, 403)
        finally:
            srv.shutdown()
            srv.server_close()


class EmptyLibrary(unittest.TestCase):
    """B-01 (2.3.1 review): once nothing is downloaded any more, catalog.json and tags.json say so, instead of going
    on listing what's gone (the Unity window shows what catalog.json lists)."""

    def test_the_catalog_empties_with_the_downloads(self):
        from hoard import safety
        root = Path(tempfile.mkdtemp())
        folder = root / "Booth" / "Kitsu Studio" / "Rusk"
        folder.mkdir(parents=True)
        (folder / "rusk.zip").write_bytes(b"zip")
        man = downloader.Manifest(root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Rusk")
        rec.update(name="Rusk", creator="Kitsu Studio", url="https://booth.pm/ja/items/111")
        rec["files"]["f1"] = {"path": "rusk.zip", "size": 3}
        man.save()
        cfg = config.load_config()
        downloader.build_catalog(cfg, root)
        self.assertEqual(len(json.loads((root / "catalog.json").read_text("utf-8"))["assets"]), 1)
        shutil.rmtree(root / "Booth")   # every download deleted by hand
        downloader.build_catalog(cfg, root)
        catalog = json.loads((root / "catalog.json").read_text("utf-8"))
        tag_index = json.loads((root / "tags.json").read_text("utf-8"))
        self.assertEqual((catalog["assets"], tag_index["total_assets"], tag_index["tags"]), ([], 0, {}))
        self.assertEqual(safety.check_seal(catalog, root / "catalog.json"), "sealed")

    def test_a_new_folder_is_left_as_it_is(self):
        root = Path(tempfile.mkdtemp())
        downloader.build_catalog(config.load_config(), root)
        self.assertEqual(list(root.iterdir()), [])


class DeletingRemovedDownloads(unittest.TestCase):
    """Issue #81: removing something from the Library left its download in Downloads. Its downloaded files can now be
    deleted too, after you confirm: only a removed product's, only the files Hoard downloaded, never through a link."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        folder = self.root / "Booth" / "Kitsu Studio" / "Rusk"
        (folder / "Textures").mkdir(parents=True)
        (folder / "rusk.unitypackage").write_bytes(b"pkg")
        (folder / "Textures" / "body.png").write_bytes(b"png!")
        (folder / "_thumbnail.png").write_bytes(b"t")
        man = downloader.Manifest(self.root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Rusk")
        rec["files"] = {"f1": {"path": "rusk.unitypackage", "size": 3}, "f2": {"path": "Textures/body.png", "size": 4}}
        other = man.record("222", "Kitsu Studio", "Anko")
        (self.root / "Booth" / "Kitsu Studio" / "Anko").mkdir()
        (self.root / "Booth" / "Kitsu Studio" / "Anko" / "anko.zip").write_bytes(b"zip")
        other["files"] = {"f1": {"path": "anko.zip", "size": 3}}
        man.save()
        self.folder = folder
        from hoard import tags
        self.key = tags.tag_key("Booth", "Rusk")

    def test_only_its_downloaded_files_go(self):
        mine = self.folder / "Textures" / "body-edited.png"   # something of your own, in the same folder
        mine.write_bytes(b"mine")
        done = downloader.delete_downloaded_files(config.load_config(), self.root, {self.key})
        self.assertEqual((done["products"], done["files"], done["bytes"]), (1, 3, 8))
        self.assertTrue(mine.exists(), "your own files stay")
        self.assertFalse((self.folder / "rusk.unitypackage").exists())
        self.assertEqual(done["kept"], ["Booth/Kitsu Studio/Rusk"])
        self.assertTrue((self.root / "Booth" / "Kitsu Studio" / "Anko" / "anko.zip").exists(), "other products stay")
        records = downloader.Manifest(self.root / "Booth").assets
        self.assertEqual(records["111"]["files"], {}, "the record no longer lists them")
        self.assertEqual(records["111"]["folder"], "Kitsu Studio/Rusk")
        catalog = json.loads((self.root / "catalog.json").read_text("utf-8"))
        self.assertEqual([a["name"] for a in catalog["assets"]], ["Anko"])

    def test_an_emptied_folder_goes(self):
        downloader.delete_downloaded_files(config.load_config(), self.root, {self.key})
        self.assertFalse(self.folder.exists())
        self.assertTrue((self.root / "Booth" / "Kitsu Studio").is_dir(), "the creator's folder still has Anko")

    @unittest.skipIf(sys.platform == "win32", "symlinks need extra rights on Windows")
    def test_never_through_a_link(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "precious.txt").write_bytes(b"keep")
        (self.folder / "rusk.unitypackage").unlink()
        os.symlink(outside / "precious.txt", self.folder / "rusk.unitypackage")
        shutil.rmtree(self.folder / "Textures")
        os.symlink(outside, self.folder / "Textures")
        (outside / "body.png").write_bytes(b"also")
        downloader.delete_downloaded_files(config.load_config(), self.root, {self.key})
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["body.png", "precious.txt"])

    def test_the_server_deletes_only_when_confirmed(self):
        """Any download's files can be deleted, removed from your library or not (it stays in your library, to
        download again), but only when confirmed, never a hidden one while the hidden library is locked, and not
        while a job runs (it waits its turn)."""
        from hoard import marks
        cfg = {**config.load_config(), "root": str(self.root)}
        srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(marks.MarkStore().path.unlink, missing_ok=True)
        try:
            def call(body):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
                c.request("POST", "/api/delete-files", body=json.dumps(body),
                          headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key})
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return r.status, data
            self.assertEqual(call({"keys": [self.key]})[0], 400, "not confirmed")
            self.assertEqual(call({"keys": [], "confirm": True})[0], 400, "nothing chosen")
            marks.MarkStore().set_pin("4821")
            marks.MarkStore().change("hidden", {self.key}, True)
            self.assertEqual(call({"keys": [self.key], "confirm": True})[0], 403, "hidden, while it's locked")
            marks.MarkStore().change("hidden", {self.key}, False)
            self.assertTrue((self.folder / "rusk.unitypackage").exists(), "nothing deleted so far")
            self.assertTrue(srv.jobs.busy.acquire(timeout=5))   # a job is running...
            try:
                status, done = call({"keys": [self.key], "confirm": True})
                self.assertEqual((status, done.get("queued")), (200, True), "...so it waits its turn")
                self.assertEqual(call({"keys": [self.key], "confirm": True})[0], 409, "once")
                self.assertTrue((self.folder / "rusk.unitypackage").exists(), "nothing deleted while that job runs")
            finally:
                srv.jobs.busy.release()
                srv.jobs.kick()
            for _ in range(100):
                if not srv.jobs.state["running"] and not srv.jobs.state["queue"]:
                    break
                time.sleep(0.05)
            self.assertFalse(self.folder.exists())
            self.assertEqual((srv.jobs.history[-1]["task"], srv.jobs.history[-1]["outcome"]), ("delete-files", "done"))
            self.assertNotIn(self.key, MarkStore_removed(), "it's still in your library, not removed")
            self.assertIn("Deleted 3 files of Rusk", srv.jobs.history[-1]["message"])
            (self.folder).mkdir(parents=True)
            (self.folder / "rusk.unitypackage").write_bytes(b"pkg")
            status, done = call({"keys": [self.key], "confirm": True})
            self.assertEqual((status, done["files"]), (200, 0), "at once when nothing runs")
        finally:
            srv.shutdown()
            srv.server_close()


def MarkStore_removed():
    from hoard import marks
    return marks.MarkStore().load()["removed"]


class EditableCopies(unittest.TestCase):
    """Issue #82: files changed in the downloads folder are replaced by the next sync, and an edited file can't be
    told from a tampered one. An editable copy goes to a folder of its own that Hoard never checks or replaces;
    only files still as Hoard downloaded them are copied, so a changed one isn't passed on as the store's."""

    def setUp(self):
        from hoard import tags
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "Hoard"
        folder = self.root / "Booth" / "Kitsu Studio" / "Rusk"
        (folder / "Textures").mkdir(parents=True)
        (folder / "rusk.unitypackage").write_bytes(b"pkg")
        (folder / "Textures" / "body.png").write_bytes(b"png!")
        man = downloader.Manifest(self.root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Rusk")
        rec["files"] = {"f1": {"path": "rusk.unitypackage", "size": 3}, "f2": {"path": "Textures/body.png", "size": 4}}
        man.save()
        self.folder, self.key = folder, tags.tag_key("Booth", "Rusk")
        self.cfg = {**config.load_config(), "root": str(self.root)}

    def test_a_copy_beside_the_downloads(self):
        done = downloader.make_editable_copy(self.cfg, self.root, self.key)
        copy = self.base / "Hoard Edits" / "Booth" / "Kitsu Studio" / "Rusk"
        self.assertEqual((Path(done["folder"]), done["files"], done["bytes"], done["skipped"]), (copy, 2, 7, []))
        self.assertEqual((copy / "Textures" / "body.png").read_bytes(), b"png!")
        self.assertIn("never checks, updates or replaces", (copy / "_EDITABLE COPY - read me.txt").read_text("utf-8"))
        (copy / "Textures" / "body.png").write_bytes(b"edited")   # yours to change; the original stays
        self.assertEqual((self.folder / "Textures" / "body.png").read_bytes(), b"png!")
        again = downloader.make_editable_copy(self.cfg, self.root, self.key)
        self.assertEqual(Path(again["folder"]).name, "Rusk (2)", "an earlier copy is never written over")
        self.assertEqual((copy / "Textures" / "body.png").read_bytes(), b"edited")

    def test_a_changed_file_is_left_out(self):
        (self.folder / "Textures" / "body.png").write_bytes(b"something else")
        done = downloader.make_editable_copy(self.cfg, self.root, self.key)
        self.assertEqual(done["skipped"], [("Textures/body.png", "changed since Hoard downloaded it")])
        self.assertFalse((Path(done["folder"]) / "Textures" / "body.png").exists())
        self.assertIn("Textures/body.png", (Path(done["folder"]) / "_EDITABLE COPY - read me.txt").read_text("utf-8"))

    @unittest.skipIf(sys.platform == "win32", "symlinks need extra rights on Windows")
    def test_never_through_a_link(self):
        secret = self.base / "secret.txt"
        secret.write_bytes(b"pkg")   # the same size as the file it stands in for
        (self.folder / "rusk.unitypackage").unlink()
        os.symlink(secret, self.folder / "rusk.unitypackage")
        done = downloader.make_editable_copy(self.cfg, self.root, self.key)   # a record leading outside isn't read
        self.assertFalse((Path(done["folder"]) / "rusk.unitypackage").exists())
        inside = self.folder / "inside.bin"   # and a link to somewhere inside isn't followed either
        inside.write_bytes(b"png!")
        (self.folder / "Textures" / "body.png").unlink()
        os.symlink(inside, self.folder / "Textures" / "body.png")
        done = downloader.make_editable_copy(self.cfg, self.root, self.key)
        self.assertEqual(done["skipped"], [("Textures/body.png", "missing, or not a plain file")])

    def test_never_inside_the_downloads(self):
        with self.assertRaises(ValueError):
            downloader.make_editable_copy({**self.cfg, "edits_root": str(self.root / "Edits")}, self.root, self.key)
        with self.assertRaises(ValueError):
            downloader.make_editable_copy(self.cfg, self.root, "booth:nothing")
        chosen = self.base / "Mine"
        done = downloader.make_editable_copy({**self.cfg, "edits_root": str(chosen)}, self.root, self.key)
        self.assertEqual(Path(done["folder"]), chosen / "Booth" / "Kitsu Studio" / "Rusk")

    def test_the_server_makes_one(self):
        srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
            c.request("POST", "/api/edit-copy", body=json.dumps({"key": self.key}),
                      headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key})
            r = c.getresponse(); data = json.loads(r.read()); c.close()
            self.assertEqual((r.status, data["files"], data["skipped"]), (200, 2, []))
            self.assertTrue(Path(data["folder"]).is_dir())
        finally:
            srv.shutdown()
            srv.server_close()


class RoutineChecks(unittest.TestCase):
    """Issue #83: you couldn't tell when (or whether) Hoard checked your downloads. A check now runs on a schedule (a
    week by default) or when you ask: every recorded file is there, the size it was downloaded at, and has the same
    SHA-256 as when first checked; Downloads says when it last ran and what it found."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.folder = self.root / "Booth" / "Kitsu Studio" / "Rusk"
        self.folder.mkdir(parents=True)
        (self.folder / "rusk.unitypackage").write_bytes(b"pkg")
        (self.folder / "body.png").write_bytes(b"png!")
        man = downloader.Manifest(self.root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Rusk")
        rec["files"] = {"f1": {"path": "rusk.unitypackage", "size": 3}, "f2": {"path": "body.png", "size": 4},
                        "f3": {"path": "gone.zip", "size": 9}}
        man.save()
        self.addCleanup(downloader.integrity_file().unlink, missing_ok=True)

    def test_it_finds_changed_and_missing_files(self):
        first = downloader.check_integrity(self.root)
        self.assertEqual((first["files"], first["fine"], first["changed"]), (3, 2, []))
        self.assertEqual(first["missing"], ["Rusk (Booth): gone.zip"])
        rec = downloader.Manifest(self.root / "Booth").assets["111"]["files"]
        self.assertEqual(len(rec["f2"]["sha256"]), 64, "the fingerprint is kept in the record")
        png = self.folder / "body.png"
        png.write_bytes(b"evil")   # the same size, different content
        os.utime(png, ns=(png.stat().st_atime_ns, png.stat().st_mtime_ns + 5_000_000_000))
        again = downloader.check_integrity(self.root)
        self.assertEqual(again["changed"], ["Rusk (Booth): body.png"])
        self.assertIn("1 changed since Hoard downloaded it, 1 missing", downloader.integrity_summary(again))
        self.assertEqual(downloader.last_integrity()["changed"], ["Rusk (Booth): body.png"])

    def test_an_unchanged_file_isnt_read_again(self):
        downloader.check_integrity(self.root)
        from unittest import mock
        with mock.patch.object(downloader, "open_under", side_effect=AssertionError("read again")):
            r = downloader.check_integrity(self.root)
        self.assertEqual(r["fine"], 2)

    def test_stop_ends_it(self):
        stop = threading.Event(); stop.set()
        r = downloader.check_integrity(self.root, stop=stop)
        self.assertFalse(r["complete"])
        self.assertTrue(downloader.integrity_summary(r).startswith("Stopped"))

    def test_a_new_file_waits_for_the_next_check(self):
        """Issue #113: a file downloaded since the last check counts as fine without being read; the next check
        takes its fingerprint."""
        from unittest import mock
        man = downloader.Manifest(self.root / "Booth")
        for f in man.assets["111"]["files"].values():
            f["downloaded_at"] = "2026-10-04T12:00:00+00:00"
        man.save()
        with mock.patch.object(downloader, "open_under", side_effect=AssertionError("read")):
            r = downloader.check_integrity(self.root, fresh_since="2026-10-01T00:00:00+00:00")
        self.assertEqual(r["fine"], 2, "both files there were downloaded since then")
        r = downloader.check_integrity(self.root)   # and the next one reads them
        self.assertEqual(r["fine"], 2)

    def test_the_setting_and_the_page(self):
        cfg = {**config.load_config(), "root": str(self.root)}
        self.assertEqual(server.public_settings(cfg)["routine_hours"], 0, "off until you choose: it reads your stores")
        self.assertEqual(server.apply_settings(cfg, {"routine_hours": 720}), {"routine_hours": 720})
        for bad in (2, True, "24", 30):
            with self.assertRaises(ValueError):
                server.apply_settings(cfg, {"routine_hours": bad})
        self.assertEqual(server.integrity_view(cfg), {"every_hours": 0, "checked": None})
        downloader.check_integrity(self.root)
        view = server.integrity_view(cfg)
        self.assertEqual((view["files"], view["fine"], view["missing"], view["changed"]), (3, 2, 1, 0))
        self.assertNotIn("Rusk", json.dumps(view), "names stay in Tasks, where hidden ones are masked")


class RealJobs(unittest.TestCase):
    """The tasks added in 3.0, run by the real job runner, not a stand-in. ("Check now" once failed to start at all:
    its function had lost its name, and the runner it had taken was never let go, so every task after it waited.)"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(downloader.integrity_file().unlink, missing_ok=True)
        self.cfg = {**config.load_config(), "root": str(self.root)}
        self.jobs = jobs.Jobs(self.cfg, library.Library(self.root / "library.json"))
        self.addCleanup(mock_tasks_file(self.root).stop)

    def run_job(self, task, **kw):
        self.assertEqual(self.jobs.start(task, [], **kw), "started")
        for _ in range(200):
            if not self.jobs.state["running"]:
                break
            time.sleep(0.05)
        self.assertTrue(self.jobs.busy.acquire(timeout=5), "the runner is let go after the job")
        self.jobs.busy.release()
        return self.jobs.history[-1]

    def test_check_downloads(self):
        done = self.run_job("verify")
        self.assertEqual(done["outcome"], "done", done["message"])
        self.assertIsNotNone(downloader.last_integrity())

    def test_add_to_local(self):
        own = self.root.parent / (self.root.name + "-own")
        own.mkdir()
        self.addCleanup(shutil.rmtree, own, True)
        (own / "pack.unitypackage").write_bytes(b"pkg")
        done = self.run_job("add-local", local={"path": str(own), "copy": False})
        self.assertEqual(done["outcome"], "done", done["message"])
        self.assertIn("Added", done["message"])

    def sync_with(self, fetchers, online=True):
        """A Sync of Booth and Gumroad through the real runner, each store read by fetchers[store]. Returns the
        finished job and whether downloading was tried."""
        import contextlib
        import types
        from unittest import mock
        from hoard.common import NotLoggedIn

        def not_signed_in(ctx, cfg, say):
            raise NotLoggedIn("not signed in")
        window = types.SimpleNamespace(close=lambda: None)
        tried = []
        with mock.patch.object(jobs, "reachable", lambda store: online), \
                mock.patch.object(jobs, "_playwright", lambda: (lambda: contextlib.nullcontext(None))), \
                mock.patch.object(jobs, "launch", lambda *a: window), \
                mock.patch.dict(jobs.FETCHERS, {s: fetchers.get(s, not_signed_in) for s in ("booth", "gumroad")}), \
                mock.patch.object(self.jobs, "_download", lambda *a, **k: tried.append(a) or self.jobs._set(message="Done: 0 new, 0 updated.")):
            self.assertEqual(self.jobs.start("sync", ["booth", "gumroad"]), "started")
            for _ in range(200):
                if not self.jobs.state["running"]:
                    break
                time.sleep(0.05)
        return self.jobs.history[-1], bool(tried)

    def test_a_sync_that_read_no_store_failed(self):
        """A Sync where every store failed said Done, in green. Now it fails, says which stores, and doesn't try to
        download from them."""
        done, downloaded = self.sync_with({})
        self.assertEqual(done["outcome"], "failed")
        self.assertIn("Couldn't read Booth and Gumroad", done["message"])
        self.assertFalse(downloaded)

    def test_a_sync_that_read_some_stores_is_partly_done(self):
        item = {"key": "booth:1", "store": "booth", "name": "Hat", "creator": "Someone", "url": "https://booth.pm/en/items/1"}
        done, downloaded = self.sync_with({"booth": lambda ctx, cfg, say: [item]})
        self.assertTrue(downloaded, "what could be read is still downloaded")
        self.assertEqual(done["outcome"], "partial")
        self.assertIn("Couldn't read Gumroad", done["message"])
        self.assertNotIn("Booth", done["message"].split("Couldn't read")[1])

    def test_a_sync_offline_failed(self):
        done, downloaded = self.sync_with({}, online=False)
        self.assertEqual(done["outcome"], "failed")
        self.assertIn("offline", done["message"])
        self.assertFalse(downloaded)

    def test_a_job_that_cant_start_lets_the_runner_go(self):
        from unittest import mock
        with mock.patch.object(self.jobs, "_start", side_effect=RuntimeError("broken")):
            with self.assertRaises(RuntimeError):
                self.jobs.start("verify", [])
        self.assertFalse(self.jobs.state["running"])
        self.assertTrue(self.jobs.busy.acquire(blocking=False), "not held by the job that never started")
        self.jobs.busy.release()


def mock_tasks_file(root):
    from unittest import mock
    patch = mock.patch.object(jobs, "tasks_file", lambda: root / "tasks.json")
    patch.start()
    return patch


class ManifestSaves(unittest.TestCase):
    """P-08 (2.3.1 review): while downloading, a store's manifest is written at most every SAVE_EVERY seconds, not
    after every file and every product; each sync still ends by saving everything, however it ends."""

    def test_checkpoints_are_spaced_out(self):
        man = downloader.Manifest(Path(tempfile.mkdtemp()) / "Booth")
        on_disk = lambda: set(json.loads(man.path.read_text("utf-8"))["assets"])  # noqa: E731
        man.record("1", "Kitsu", "One")
        man.checkpoint()
        self.assertEqual(on_disk(), {"1"}, "the first change is saved straight away")
        man.record("2", "Kitsu", "Two")
        man.checkpoint()
        self.assertEqual(on_disk(), {"1"}, "not again within SAVE_EVERY seconds")
        man._saved_at -= downloader.SAVE_EVERY   # as if that long had passed
        man.checkpoint()
        self.assertEqual(on_disk(), {"1", "2"})

    def test_an_unused_store_gets_no_manifest(self):
        """A manifest is how a sync tells a store you use from one you don't (see cmd_sync)."""
        man = downloader.Manifest(Path(tempfile.mkdtemp()) / "Jinxxy")
        man.checkpoint()
        man.save_changes()
        self.assertFalse(man.path.exists())


class LibraryLookups(unittest.TestCase):
    """P-05/P-06 (2.3.1 review): a picture is found without going through the whole library, and a page's copy of
    the library is a snapshot, not a JSON round trip of all of it."""

    def test_pictures_are_found_and_follow_changes(self):
        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        with lib.lock:
            lib.data["items"] = [library.item("booth", str(n), name=f"Item {n}", thumbnail=f"https://img.example/{n}.png")
                                 for n in range(3)] + [library.item("booth", "plain", name="No Picture")]
        self.assertEqual(lib.thumbnail_for("booth:2"), ("https://img.example/2.png", library.STORES["booth"]["referer"]))
        self.assertIsNone(lib.thumbnail_for("booth:plain"))
        self.assertIsNone(lib.thumbnail_for("booth:nothing"))
        lib.merge_store("booth", [library.item("booth", "2", name="Item 2", thumbnail="https://img.example/new.png")])
        self.assertEqual(lib.thumbnail_for("booth:2")[0], "https://img.example/new.png", "a change is seen straight away")
        lib.forget_products({library.tag_key("booth", "Item 2")})
        self.assertIsNone(lib.thumbnail_for("booth:2"))

    def test_a_snapshot_stays_as_it_was(self):
        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        lib.replace_store("booth", [library.item("booth", "1", name="One")])
        items, stores = lib.snapshot()
        lib.replace_store("booth", [])
        lib.set_error("booth", "changed since")
        self.assertEqual([i["key"] for i in items], ["booth:1"])
        self.assertIsNone(stores["booth"]["error"])


class Downloading(unittest.TestCase):
    """A download job reports progress, stops cleanly, and still rebuilds the catalog."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.cfg = {**config.load_config(), "root": str(self.root)}
        self.saved = downloader.sync_booth, downloader.reachable, downloader.build_catalog
        self.catalog_built = threading.Event()
        downloader.reachable = lambda store, timeout=5.0: True
        downloader.build_catalog = lambda cfg, root: self.catalog_built.set()

    def tearDown(self):
        downloader.sync_booth, downloader.reachable, downloader.build_catalog = self.saved

    def run_job(self, job, stop_after=None, timeout=20):
        done = threading.Event()
        job.on_download_done = done.set
        self.assertTrue(job.start("download", ["booth"]))
        if stop_after:
            time.sleep(stop_after)
            self.assertTrue(job.cancel())
        self.assertTrue(done.wait(timeout))
        for _ in range(50):   # the runner frees itself just after the callback
            if not job.state["running"]:
                break
            time.sleep(0.05)

    def test_progress_and_summary(self):
        def pretend(cfg, root, args, report):
            for i in range(3):
                common.log(f"Booth: file {i}")
            report.new_assets.append("Booth: Thing")
        downloader.sync_booth = pretend
        job = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.run_job(job)
        self.assertIn("Booth: file 2", job.state["log"])
        self.assertEqual(job.state["report"]["new_assets"], 1)
        self.assertTrue(self.catalog_built.is_set())

    def test_stop(self):
        def slow(cfg, root, args, report):
            for i in range(200):
                common.log(f"Booth: file {i}")
                time.sleep(0.05)
        downloader.sync_booth = slow
        job = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.run_job(job, stop_after=0.5)
        self.assertTrue(job.state["message"].startswith("Stopped"))
        self.assertLess(len(job.state["log"]), 60, "it stopped early")
        self.assertTrue(self.catalog_built.is_set(), "what did download is still catalogued")
        self.assertFalse(job.state["running"])
        self.assertFalse(job.cancel(), "nothing left to stop")

    def test_stop_reaches_the_job_whoever_else_is_logging(self):
        """Log messages reach every listener, from any thread. Stop has to end the job itself, not whichever
        thread happened to log next (on Windows CI, another test's leftover thread took the Stop, and the job ran on
        to 'Done')."""
        def slow(cfg, root, args, report):
            for i in range(200):
                common.log(f"Booth: file {i}")
                time.sleep(0.05)
        downloader.sync_booth = slow
        chatter_on, stolen = threading.Event(), []

        def chatter():
            while not chatter_on.is_set():
                try:
                    common.log("elsewhere")
                except BaseException as e:   # noqa: B036 - what the job's Stop would raise in the wrong thread
                    stolen.append(type(e).__name__)
                time.sleep(0.002)
        other = threading.Thread(target=chatter, daemon=True)
        other.start()
        self.addCleanup(chatter_on.set)
        job = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.run_job(job, stop_after=0.5)
        chatter_on.set()
        other.join(5)
        self.assertEqual(stolen, [], "Stop was raised in another thread")
        self.assertTrue(job.state["message"].startswith("Stopped"), job.state["message"])
        self.assertLess(len([line for line in job.state["log"] if line.startswith("Booth")]), 60, "it stopped early")

    def test_stopped_is_never_overwritten_by_stopping(self):
        """Stop said "Stopping" after telling the job to stop: a job that stopped in between ended up saying
        "Stopping", and Tasks listed it as done instead of stopped."""
        job = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        job.state.update(running=True, task="download")
        seen = []

        class Watched(threading.Event):
            def set(self):
                seen.append(job.state["message"])
                super().set()
        job.stop = Watched()
        self.assertTrue(job.cancel())
        self.assertEqual(seen, ["Stopping"], "said before the job can see it")

    def test_one_job_at_a_time(self):
        """A second job waits its turn (issue #49): it's queued, and runs once the first has finished."""
        started = threading.Event()
        release = threading.Event()

        def waits(cfg, root, args, report):
            started.set()
            release.wait(10)
        downloader.sync_booth = waits
        job = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        done = threading.Event()
        job.on_download_done = done.set
        self.assertEqual(job.start("download", ["booth"]), "started")
        started.wait(5)
        self.assertEqual(job.start("download", ["booth"], only="Rusk"), "queued", "a second job waits its turn")
        self.assertEqual([q["label"] for q in job.state["queue"]], ['Download: Booth ("Rusk")'])
        release.set()
        done.wait(10)


class JobQueue(unittest.TestCase):
    """Issue #49: jobs started while another runs wait in a queue, in order, and can be taken off it; finished
    jobs are kept for the Tasks tab."""

    def setUp(self):
        from unittest import mock
        self.job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.job.history = []
        self.ran, self.gates = [], {}

        def fake(stores, only, keys=None, check=False, **_kw):
            self.ran.append(only)
            self.job._set(message=f"working on {only}")
            gate = self.gates.get(only)
            if gate:
                gate.wait(10)
            if only == "boom":
                raise RuntimeError("the store went away")
        patch = mock.patch.object(self.job, "_download", fake)
        patch.start()
        self.addCleanup(patch.stop)
        where = Path(tempfile.mkdtemp()) / "tasks.json"
        saving = mock.patch.object(jobs, "tasks_file", lambda: where)
        saving.start()
        self.addCleanup(saving.stop)

    def wait_idle(self):
        for _ in range(200):
            if not self.job.state["running"] and not self.job.state["queue"]:
                return
            time.sleep(0.02)
        self.fail("the queue never finished")

    def test_in_order_and_removable(self):
        self.gates["a"] = threading.Event()
        self.assertEqual(self.job.start("download", ["booth"], only="a"), "started")
        self.assertEqual(self.job.start("download", ["booth"], only="b"), "queued")
        self.assertEqual(self.job.start("download", ["booth"], only="c"), "queued")
        self.assertEqual(self.job.start("download", ["gumroad"], only="d"), "queued")
        self.assertIsNone(self.job.start("download", ["booth"], only="c"), "the same job isn't queued twice")
        self.assertIsNone(self.job.start("download", ["booth"], only="e", queue=False), "not queued when asked not to")
        waiting = self.job.state["queue"]
        self.assertEqual([q["label"] for q in waiting], ['Download: Booth ("b")', 'Download: Booth ("c")',
                                                         'Download: Gumroad ("d")'])
        self.assertTrue(self.job.remove(waiting[1]["id"]))
        self.assertFalse(self.job.remove(waiting[1]["id"]), "already gone")
        self.gates["a"].set()
        self.wait_idle()
        self.assertEqual(self.ran, ["a", "b", "d"])

    def test_the_task_log(self):
        self.job.start("download", ["booth"], only="ok")
        self.job.start("download", ["booth"], only="boom")
        self.wait_idle()
        newest, oldest = self.job.tasks()["history"]
        self.assertEqual((oldest["outcome"], newest["outcome"]), ("done", "failed"))
        self.assertIn("working on ok", oldest["log"])
        self.assertIn("the store went away", newest["message"])
        self.assertTrue(newest["started"] <= newest["ended"])
        again = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.assertEqual([h["outcome"] for h in again.history], ["done", "failed"], "kept in tasks.json")

    def test_a_scheduled_sync_never_queues(self):
        self.gates["a"] = threading.Event()
        self.job.start("download", ["booth"], only="a")
        self.assertIsNone(self.job.start("sync", ["booth"], scheduled=True, queue=False))
        self.gates["a"].set()
        self.wait_idle()

    def test_the_runner_let_go_by_something_else(self):
        """Something that holds the runner without being a job (resealing the catalog at startup) starts what
        queued meanwhile when it lets go."""
        self.job.busy.acquire()
        self.assertEqual(self.job.start("download", ["booth"], only="x"), "queued")
        self.job.busy.release()
        self.job.kick()
        self.wait_idle()
        self.assertEqual(self.ran, ["x"])


class Retries(unittest.TestCase):
    """Issue #19: a file download that fails is tried again (download_retries more times) before it counts as
    failed, unless trying again can't help."""

    def report(self, retries=2):
        return downloader.Report(retries=retries)

    def test_tried_again_until_it_works(self):
        calls, waits = [], []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("connection reset")
            return "got it"
        self.assertEqual(downloader.with_retries(self.report(), "a.zip", flaky, sleep=waits.append), "got it")
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(waits), 2)

    def test_gives_up_after_the_last_try(self):
        calls = []

        def broken():
            calls.append(1)
            raise TimeoutError("timed out")
        with self.assertRaises(TimeoutError):
            downloader.with_retries(self.report(1), "a.zip", broken, sleep=lambda s: None)
        self.assertEqual(len(calls), 2)
        calls.clear()
        with self.assertRaises(TimeoutError):
            downloader.with_retries(self.report(0), "a.zip", broken, sleep=lambda s: None)
        self.assertEqual(len(calls), 1, "0: not tried again")

    def test_not_when_trying_again_cant_help(self):
        import requests
        from hoard import egress
        gone = requests.HTTPError("404 Not Found", response=mock_response(404))
        busy = requests.HTTPError("503", response=mock_response(503))
        for e, again in ((gone, False), (common.NotLoggedIn("signed out"), False),
                         (egress.UnsafeRequest("refused"), False), (busy, True), (ConnectionError(), True)):
            calls = []

            def fails(e=e):
                calls.append(1)
                raise e
            with self.assertRaises(type(e)):
                downloader.with_retries(self.report(), "a.zip", fails, sleep=lambda s: None)
            self.assertEqual(len(calls), 3 if again else 1, repr(e))

    def test_the_setting(self):
        self.assertEqual(config.DEFAULT_CONFIG["download_retries"], 2)
        for value, n in ((0, 0), (5, 5), (9, 2), ("3", 2), (True, 2)):
            self.assertEqual(downloader.download_retries({"download_retries": value}), n)

    def test_a_file_host_having_a_bad_moment(self):
        """itch.io's file host answers 503 once: the file is fetched on the next try, and nothing failed."""
        from unittest import mock
        _ItchStandIn.start()
        self.addCleanup(_ItchStandIn.stop)
        cfg = _ItchStandIn.use(self)
        root = Path(tempfile.mkdtemp())
        _ItchStandIn.fail_next = 1
        import types
        report = downloader.Report(retries=2)
        with mock.patch.object(downloader, "save_thumbnail", lambda *a, **k: None):
            downloader.sync_itch(cfg, root, types.SimpleNamespace(headed=False, only=None, dry_run=False), report)
        self.assertEqual(report.failed, [])
        self.assertEqual(_ItchStandIn.fail_next, 0)
        self.assertTrue((root / "Itch" / "Kitsu Studio" / "Paw Suit" / "PawSuit_v1.2.unitypackage").is_file())


def mock_response(status):
    from unittest import mock
    return mock.Mock(status_code=status)


class RecentlyAdded(unittest.TestCase):
    """Issue #18: when each item first appeared in the library, for Recently added and the New badge."""

    def setUp(self):
        self.lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")

    def test_a_stores_first_read_isnt_new(self):
        self.lib.replace_store("booth", [library.item("booth", "1", name="Rusk")])
        (rusk,) = self.lib.data["items"]
        first = self.lib.data["stores"]["booth"]["first_read"]
        self.assertEqual(rusk["added"], first, "dated, but not after the first read: not new")
        time.sleep(1.1)
        self.lib.replace_store("booth", [library.item("booth", "1", name="Rusk"), library.item("booth", "2", name="Mochi")])
        rusk, mochi = self.lib.data["items"]
        self.assertEqual(rusk["added"], first, "an item seen before keeps its time")
        self.assertGreater(mochi["added"], self.lib.data["stores"]["booth"]["first_read"])
        again = library.Library(self.lib.path)
        self.assertEqual([i["added"] for i in again.data["items"]], [rusk["added"], mochi["added"]], "kept in library.json")
        self.assertEqual(again.data["stores"]["booth"]["first_read"], first)

    def test_a_library_from_before_times_were_kept(self):
        """Items listed before this version have no time; anything that appears from then on is new."""
        self.lib.data["items"] = [library.item("booth", "1", name="Rusk")]
        self.lib.data["stores"]["booth"] = {"count": 1, "error": None, "source": "refresh"}
        self.lib.replace_store("booth", [library.item("booth", "1", name="Rusk"), library.item("booth", "2", name="Mochi")])
        rusk, mochi = self.lib.data["items"]
        self.assertIsNone(rusk["added"])
        self.assertEqual(self.lib.data["stores"]["booth"]["first_read"], "")
        self.assertTrue(mochi["added"])

    def test_bad_times_are_dropped(self):
        for bad in ("yesterday", "2026-01-01", "<script>", 12345):
            self.assertIsNone(library.item("booth", "1", name="Rusk", added=bad)["added"])
        self.assertEqual(library.item("booth", "1", added="2026-09-30T10:00:00+00:00")["added"], "2026-09-30T10:00:00+00:00")

    def test_new_in_the_library_page(self):
        cfg = {**config.load_config(), "new_days": 7}
        srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            old = "2020-01-01T00:00:00+00:00"
            with srv.lib.lock:
                srv.lib.data["stores"]["booth"] = {"count": 3, "error": None, "source": "refresh", "first_read": old}
                srv.lib.data["items"] = [library.item("booth", "1", name="Old", added=old),
                                         library.item("booth", "2", name="Fresh", added=common.now_iso()),
                                         library.item("booth", "3", name="Undated")]

            def library_page():
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
                c.request("GET", "/api/library", headers={ACCESS_HEADER: srv.key})
                data = json.loads(c.getresponse().read()); c.close()
                return {i["name"]: i["new"] for i in data["items"]}
            self.assertEqual(library_page(), {"Old": False, "Fresh": True, "Undated": False})
            srv.cfg["new_days"] = 0
            self.assertEqual(library_page(), {"Old": False, "Fresh": False, "Undated": False}, "0: nothing is marked")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_the_setting(self):
        cfg = config.load_config()
        self.assertEqual(server.apply_settings(cfg, {"new_days": 14}), {"new_days": 14})
        for bad in (2, "7", True):
            with self.assertRaises(ValueError):
                server.apply_settings(cfg, {"new_days": bad})


class SigningOut(unittest.TestCase):
    """Signing out of a store forgets what that account owns, so the next account never sees it."""

    def test_clear_store(self):
        tmp = Path(tempfile.mkdtemp())
        lib = library.Library(tmp / "library.json")
        lib.data["items"] = [library.item("jinxxy", "a", name="Paw Suit", thumbnail="https://cdn.jinxxy.com/a.png"),
                             library.item("booth", "1", name="Rusk")]
        lib.data["stores"] = {"jinxxy": {"count": 1}, "booth": {"count": 1}}
        lib.save()
        import hashlib
        library.THUMB_DIR.mkdir(parents=True, exist_ok=True)
        cached = library.THUMB_DIR / (hashlib.sha1(b"https://cdn.jinxxy.com/a.png").hexdigest() + ".png")
        cached.write_bytes(b"png")
        self.assertEqual(lib.clear_store("jinxxy", "Signed out."), 1)
        self.assertEqual([i["store"] for i in library.Library(tmp / "library.json").data["items"]], ["booth"])
        self.assertFalse(cached.exists(), "the cached picture shows what was bought, so it goes too")
        self.assertEqual(lib.data["stores"]["jinxxy"]["count"], 0)

    def test_sign_out_job_clears_the_list(self):
        tmp = Path(tempfile.mkdtemp())
        lib = library.Library(tmp / "library.json")
        lib.data["items"] = [library.item("gumroad", "x", name="Hoodie")]
        lib.data["stores"] = {"gumroad": {"count": 1}}
        job = jobs.Jobs(config.load_config(), lib)
        saved = jobs.sign_out, jobs._playwright
        jobs.sign_out = lambda p, cfg, store: "Gumroad: deleted the saved sign-in (3 cookies, plus the store's site data)."

        class NoBrowser:
            def __enter__(self): return None
            def __exit__(self, *a): return False
        jobs._playwright = lambda: NoBrowser
        try:
            job._logout(["gumroad"])
        finally:
            jobs.sign_out, jobs._playwright = saved
        self.assertEqual(lib.data["items"], [])
        self.assertIn("Removed 1 items", lib.data["stores"]["gumroad"]["error"])
        self.assertIn("downloaded files are still on disk", lib.data["stores"]["gumroad"]["error"])


class JinxxyBanners(unittest.TestCase):
    """Copies of Jinxxy's default banner saved as product pictures by older versions are removed."""

    def test_repeated_pictures_are_forgotten(self):
        store = Path(tempfile.mkdtemp()) / "Jinxxy"
        for creator, product, data in (("A", "One", b"BANNER"), ("B", "Two", b"BANNER"), ("C", "Three", b"REAL")):
            (store / creator / product).mkdir(parents=True)
            (store / creator / product / "_thumbnail.png").write_bytes(data)
        self.assertEqual(downloader.forget_repeated_thumbnails(store), 2)
        self.assertEqual(sorted(p.parent.name for p in store.rglob("_thumbnail.png")), ["Three"])


class PayhipShops(unittest.TestCase):
    """Payhip keeps purchases per shop; the shops you list are the only extra sites Hoard trusts for Payhip."""

    def tearDown(self):
        config.apply_store_sites(config.load_config())

    def test_addresses(self):
        good = {"myshop.store": "https://myshop.store", "https://myshop.store/b-account": "https://myshop.store",
                "payhip.com/MyShop": "https://payhip.com/MyShop", "https://payhip.com/MyShop/b-account": "https://payhip.com/MyShop"}
        for given, kept in good.items():
            self.assertEqual(config.clean_payhip_shop(given), kept, given)
        for bad in ("http://localhost", "https://127.0.0.1", "https://[::1]/", "https://user@shop.example", "payhip.com",
                    "https://payhip.com/a/b", "shop", "javascript:alert(1)", "https://shop.example:8443", ""):
            self.assertIsNone(config.clean_payhip_shop(bad), bad)

    def test_only_listed_shops_count_as_payhip(self):
        from hoard import safety
        cfg = config.load_config()
        cfg["payhip"]["shops"] = ["myshop.store"]
        config.apply_store_sites(cfg)
        self.assertTrue(safety.store_link("payhip", "https://myshop.store/b-account/digital/x"))
        self.assertIsNone(safety.store_link("payhip", "https://myshop.store.evil.example/"))
        self.assertIsNone(safety.store_link("booth", "https://myshop.store/"), "a Payhip shop never counts for another store")
        cfg["payhip"]["shops"] = []
        config.apply_store_sites(cfg)
        self.assertIsNone(safety.store_link("payhip", "https://myshop.store/b-account/digital/x"), "removed means removed")

    def test_settings(self):
        cfg = config.load_config()
        change = server.apply_settings(cfg, {"payhip_shops": ["myshop.store", "https://myshop.store/b-account", "payhip.com/Two"]})
        self.assertEqual(change["payhip"]["shops"], ["https://myshop.store", "https://payhip.com/Two"])
        with self.assertRaises(ValueError):
            server.apply_settings(cfg, {"payhip_shops": ["http://192.168.1.5"]})
        both = server.apply_settings(cfg, {"payhip_shops": ["a.store"], "stores": {"payhip": {"enabled": False}}})
        self.assertEqual(both["payhip"], {"shops": ["https://a.store"], "enabled": False})


class ArchiveHideRemove(unittest.TestCase):
    """Your archive, hidden and removed choices, and the hidden library's PIN."""

    def store(self):
        from hoard import marks
        return marks.MarkStore(Path(tempfile.mkdtemp()) / "marks.json")

    def test_choices_persist_and_validate(self):
        st = self.store()
        st.change("archived", {"booth:rusk", "bad key!"}, True)
        st.change("removed", {"payhip:pollution"}, True)
        again = type(st)(st.path).load()
        self.assertEqual((again["archived"], again["removed"]), ({"booth:rusk"}, {"payhip:pollution"}))
        st.change("unarchived", {"booth:rusk"}, True)
        self.assertEqual(st.load()["archived"], set(), "moving back out of the archive undoes archiving")
        with self.assertRaises(Exception):
            st.change("hidden", {"booth:rusk"}, True)   # no PIN yet

    def test_pin(self):
        from hoard import marks
        st = self.store()
        st.set_pin("4821")
        raw = st.path.read_text()
        # the PIN isn't kept as any value in the file (a hash or salt can hold "4821" by chance: checking the raw
        # text for it failed a few times in every 1,000 runs, as in CI on PR #38)
        def values(x):
            return [v for y in x.values() for v in values(y)] if isinstance(x, dict) else \
                   [v for y in x for v in values(y)] if isinstance(x, list) else [str(x)]
        self.assertNotIn("4821", values(json.loads(raw)))
        self.assertNotIn('"4821"', raw)
        self.assertIn("scrypt" if "scrypt" in raw else '"n"', raw)
        st.check_pin("4821")
        for _ in range(marks.FREE_TRIES):
            with self.assertRaises(marks.PinError):
                st.check_pin("0000")
        with self.assertRaises(marks.PinError) as waiting:
            type(st)(st.path).check_pin("4821")   # the wait survives a restart, and applies to the right PIN too
        self.assertIn("Try again in", str(waiting.exception))
        with self.assertRaises(marks.PinError):
            st.set_pin("9999", current="0000")

    def test_forgotten_pin_deletes_never_reveals(self):
        st = self.store()
        st.set_pin("4821")
        st.change("hidden", {"booth:secret"}, True)
        self.assertEqual(st.forget_hidden(), {"booth:secret"})
        data = st.load()
        self.assertEqual((data["hidden"], data["pin"]), (set(), None))

    def test_editing_the_file_drops_the_pin(self):
        st = self.store()
        st.set_pin("4821")
        raw = json.loads(st.path.read_text())
        raw["hidden"] = ["booth:x"]
        st.path.write_text(json.dumps(raw))
        self.assertIsNone(st.load()["pin"], "an edited file can't keep a PIN someone else chose")

    def test_the_server_keeps_hidden_items_private(self):
        from hoard import marks, tags
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        lib = srv.lib
        with lib.lock:
            lib.data["items"] = [library.item("booth", "1", name="Secret Suit"), library.item("booth", "2", name="Plain Hat")]
            lib.save()
        secret = tags.tag_key("booth", "Secret Suit")
        st = marks.MarkStore()
        st.set_pin("4821")
        st.change("hidden", {secret}, True)
        try:
            def call(method, path, body=None, cookie=None):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
                headers = {**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: srv.key}
                if cookie:
                    headers["Cookie"] = cookie
                c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return r.status, data, r.getheader("Set-Cookie")
            _, locked, _ = call("GET", "/api/library")
            self.assertEqual([i["name"] for i in locked["items"]], ["Plain Hat"])
            self.assertEqual(call("POST", "/api/marks", {"kind": "hidden", "keys": [secret], "on": False})[0], 403)
            self.assertEqual(call("POST", "/api/unlock", {"pin": "0000"})[0], 403)
            status, _, cookie = call("POST", "/api/unlock", {"pin": "4821"})
            self.assertEqual(status, 200)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            _, unlocked, _ = call("GET", "/api/library", cookie=cookie.split(";")[0])
            self.assertEqual(sorted(i["name"] for i in unlocked["items"]), ["Plain Hat", "Secret Suit"])
            self.assertEqual(len(call("GET", "/api/library")[1]["items"]), 1, "other browsers stay locked")
            call("POST", "/api/lock", {})
            self.assertEqual(len(call("GET", "/api/library", cookie=cookie.split(";")[0])[1]["items"]), 1, "Lock now locks")
            self.assertEqual(call("POST", "/api/purge", {"keys": [secret]})[1].get("deleted"), 0, "only removed items can be purged")
        finally:
            marks.MarkStore().path.unlink(missing_ok=True)
            srv.shutdown()
            srv.server_close()

    def test_downloads_carry_the_librarys_marks(self):
        """Issue #29: the Downloads page gets each download's mark from the Library (archived by you or by the
        store, removed, hidden), and a hidden one's download only while this browser is unlocked."""
        from unittest import mock
        from hoard import marks, tags
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with srv.lib.lock:
            srv.lib.data["items"] = [library.item("gumroad", "g1", name="Store Archived", archived=True),
                                     library.item("gumroad", "g2", name="Moved Back", archived=True)]
        names = ["Secret Suit", "Old Hat", "Store Archived", "Moved Back", "Gone Pack", "Plain Hat"]
        key = {n: tags.tag_key("gumroad" if n in ("Store Archived", "Moved Back") else "booth", n) for n in names}
        index = {"root": "x", "assets": [{"id": i, "name": n, "store": "gumroad" if n in ("Store Archived", "Moved Back") else "booth",
                                          "tag_key": key[n], "suggested": [], "also_in": []} for i, n in enumerate(names)]}
        st = marks.MarkStore()
        st.set_pin("4821")
        st.change("hidden", {key["Secret Suit"]}, True)
        st.change("archived", {key["Old Hat"]}, True)
        st.change("unarchived", {key["Moved Back"]}, True)
        st.change("removed", {key["Gone Pack"]}, True)
        try:
            def call(method, path, body=None, cookie=None):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
                headers = {**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: srv.key,
                           **({"Cookie": cookie} if cookie else {})}
                c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return data, r.getheader("Set-Cookie")
            with mock.patch.object(srv, "index", lambda rescan=False, stale_ok=False: index), \
                    mock.patch.object(srv.lib, "save"):
                locked = call("GET", "/api/assets")[0]
                self.assertEqual({a["name"]: a["mark"] for a in locked["assets"]},
                                 {"Old Hat": "archived", "Store Archived": "archived", "Moved Back": None,
                                  "Gone Pack": "removed", "Plain Hat": None})
                self.assertEqual(locked["privacy"], {"pin_set": True, "unlocked": False})
                cookie = call("POST", "/api/unlock", {"pin": "4821"})[1].split(";")[0]
                unlocked = call("GET", "/api/assets", cookie=cookie)[0]
                self.assertEqual({a["name"]: a["mark"] for a in unlocked["assets"]}["Secret Suit"], "hidden")
                self.assertTrue(unlocked["privacy"]["unlocked"])
        finally:
            marks.MarkStore().path.unlink(missing_ok=True)
            srv.shutdown()
            srv.server_close()

    def test_removed_products_arent_downloaded(self):
        from hoard import marks, tags
        st = marks.MarkStore()
        st.change("removed", {tags.tag_key("payhip", "Someone Else's Pack")}, True)
        try:
            report = downloader.Report()
            self.assertTrue(downloader.removed_product("payhip", "Someone Else's Pack", report))
            self.assertFalse(downloader.removed_product("payhip", "My Pack", report))
            self.assertIn("removed from your library", report.skipped[0])
        finally:
            st.path.unlink(missing_ok=True)

    def test_found_payhip_shops_survive_only_if_valid(self):
        p = Path(tempfile.mkdtemp()) / "library.json"
        lib = library.Library(p)
        lib.data["stores"]["payhip"] = {"count": 0, "found_shops": ["https://good.store", "http://10.0.0.1", "https://xn--pypal-4ve.store"]}
        lib.save()
        self.assertEqual(library.Library(p).data["stores"]["payhip"]["found_shops"], ["https://good.store"])


class RecoveryPhrase(unittest.TestCase):
    """A forgotten PIN is reset with 6 recovery words, and hidden items stay hidden."""

    def store(self):
        from hoard import marks
        return marks.MarkStore(Path(tempfile.mkdtemp()) / "marks.json")

    def test_the_word_list_is_the_bip39_list(self):
        import hashlib
        from hoard import marks
        text = (REPO / "hoard" / "recovery_words.txt").read_bytes().replace(b"\r\n", b"\n")   # as on any checkout
        self.assertEqual(hashlib.sha256(text).hexdigest(), "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda")
        self.assertEqual(len(set(marks.WORDS)), 2048)
        self.assertEqual(len({w[:4] for w in marks.WORDS}), 2048, "every word is unique in its first four letters")

    def test_phrases(self):
        from hoard import marks
        st = self.store()
        phrase = st.set_pin("4821")
        words = phrase.split()
        self.assertEqual(len(words), 6)
        self.assertTrue(all(w in marks.WORDS for w in words))
        on_disk = st.path.read_text()
        self.assertNotIn(phrase, on_disk)
        self.assertIsNone(st.set_pin("1111", current="4821"), "changing the PIN never shows the phrase again")
        self.assertNotEqual(self.store().set_pin("4821"), phrase, "each phrase is new")

    def test_reading_what_people_type(self):
        from hoard import marks
        words = ["abandon", "zoo", "legal", "winner", "thank", "year"]
        for typed in ("abandon zoo legal winner thank year", "1. Abandon, 2. ZOO, 3. lega 4 winn 5 thank 6 year\n",
                      "  abandon\tzoo legal\nwinner thank year  "):
            self.assertEqual(marks.read_phrase(typed), words, typed)
        with self.assertRaises(marks.PinError) as typo:
            marks.read_phrase("abandon zoo legal winner thank yaer")
        self.assertIn("Word 6 (yaer)", str(typo.exception))
        with self.assertRaises(marks.PinError) as short:
            marks.read_phrase("abandon zoo legal")
        self.assertIn("all 6", str(short.exception))

    def test_recover(self):
        from hoard import marks
        st = self.store()
        phrase = st.set_pin("4821")
        st.change("hidden", {"booth:secret"}, True)
        wrong = "abandon ability able about above absent"
        if wrong.split() == phrase.split():   # (a 1 in 2048^6 chance)
            wrong = "zoo zoo zoo zoo zoo zoo"
        with self.assertRaises(marks.PinError):
            st.recover(wrong, "7777")
        self.assertEqual(st.load()["failures"], 1, "wrong phrases count toward the lockout")
        with self.assertRaises(marks.PinError):
            st.recover("abandon zoo legal winner thank yaer", "7777")
        self.assertEqual(st.load()["failures"], 1, "a typo is pointed out without counting as a wrong try")
        st.recover(phrase.upper(), "7777")
        st.check_pin("7777")
        self.assertEqual(st.load()["hidden"], {"booth:secret"}, "hidden items stay hidden")
        self.assertEqual(st.load()["failures"], 0)

    def test_lockout_covers_phrases(self):
        from hoard import marks
        st = self.store()
        phrase = st.set_pin("4821")
        for _ in range(marks.FREE_TRIES):
            with self.assertRaises(marks.PinError):
                st.check_pin("0000")
        with self.assertRaises(marks.PinError) as waiting:
            st.recover(phrase, "7777")
        self.assertIn("Try again in", str(waiting.exception), "the phrase can't be used to get around the wait")

    def test_edited_or_forgotten(self):
        st = self.store()
        st.set_pin("4821")
        raw = json.loads(st.path.read_text())
        raw["hidden"] = ["booth:x"]
        st.path.write_text(json.dumps(raw))
        self.assertIsNone(st.load()["recovery"], "an edited file keeps no phrase")
        st2 = self.store()
        st2.set_pin("4821")
        st2.forget_hidden()
        self.assertIsNone(st2.load()["recovery"])

    def test_endpoints(self):
        from hoard import marks
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def call(path, body, cookie=None):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=30)
                headers = {"Content-Type": "application/json", ACCESS_HEADER: srv.key, **({"Cookie": cookie} if cookie else {})}
                c.request("POST", path, body=json.dumps(body), headers=headers)
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return r.status, data, (r.getheader("Set-Cookie") or "").split(";")[0]
            status, first, _ = call("/api/pin", {"pin": "4821"})
            self.assertEqual(len(first["recovery"].split()), 6)
            self.assertNotIn("recovery", call("/api/pin", {"pin": "1234", "current": "4821"})[1])
            self.assertEqual(call("/api/pin/phrase", {})[0], 403, "a new phrase needs unlocking")
            _, _, cookie = call("/api/unlock", {"pin": "1234"})
            status, newer, _ = call("/api/pin/phrase", {}, cookie)
            self.assertEqual((status, len(newer["recovery"].split())), (200, 6))
            self.assertEqual(call("/api/pin/recover", {"phrase": first["recovery"], "pin": "5555"})[0], 403, "the old phrase stopped working")
            self.assertEqual(call("/api/pin/recover", {"phrase": newer["recovery"], "pin": "5555"})[0], 200)
            self.assertFalse(srv.unlocks, "recovering locks every browser")
        finally:
            marks.MarkStore().path.unlink(missing_ok=True)
            srv.shutdown()
            srv.server_close()


class Sync(unittest.TestCase):
    """Sync reads what you own, then downloads anything new, as one job that Stop can end."""

    def test_reads_then_downloads(self):
        order = []
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        job._refresh = lambda stores, skip_imported=False: order.append(("read", tuple(stores), skip_imported))
        job._download = lambda stores, only: order.append(("download", tuple(stores)))
        done = threading.Event()
        job.on_download_done = done.set
        self.assertTrue(job.start("sync", ["booth", "jinxxy"]))
        for _ in range(100):
            if not job.state["running"]:
                break
            time.sleep(0.05)
        self.assertEqual(order, [("read", ("booth", "jinxxy"), True), ("download", ("booth", "jinxxy"))],
                         "pages you imported by hand aren't overwritten")
        self.assertFalse(job.state["sync"])

    def test_stop_between_reading_and_downloading(self):
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        downloaded = []
        job._refresh = lambda stores, skip_imported=False: (job.state.update(running=True, task="refresh"), job.cancel())
        job._download = lambda stores, only: downloaded.append(stores)
        job._sync(["booth"])
        self.assertEqual(downloaded, [])
        self.assertTrue(job.state["message"].startswith("Stopped"))


class UpdatingOverAnOldInstall(unittest.TestCase):
    """Python reuses compiled copies whose file date and size haven't changed; an update copied over an old
    install (with its old dates) must still run the new code."""

    def test_new_version_runs(self):
        import re
        import shutil
        import subprocess
        tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO / "hoard", tmp / "hoard", ignore=shutil.ignore_patterns("__pycache__"))
        init = tmp / "hoard" / "__init__.py"
        text = init.read_text("utf-8")
        fixed = 1767225600

        def install(version):
            init.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', text), "utf-8")
            os.utime(init, (fixed, fixed))
            return subprocess.run([sys.executable, "-m", "hoard", "--version"], cwd=tmp, capture_output=True,
                                  text=True, timeout=60, env={**os.environ, "PYTHONDONTWRITEBYTECODE": ""}).stdout.strip()
        self.assertEqual(install("9.8.7"), "Hoard 9.8.7")
        self.assertEqual(install("9.8.8"), "Hoard 9.8.8", "the old compiled copy was noticed and cleared")

    def test_zip_dates_come_from_the_release(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_release", REPO / "scripts" / "build_release.py")
        build = importlib.util.module_from_spec(spec)
        saved = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "1800000000"
        try:
            spec.loader.exec_module(build)
            self.assertEqual(build.build_date()[:3], (2027, 1, 15))
        finally:
            if saved is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = saved
        self.assertNotIn("date_time=(2026, 1, 1", (REPO / "scripts" / "build_release.py").read_text())
        for launcher in ("Hoard.bat", "run.sh"):
            self.assertIn("PYTHONDONTWRITEBYTECODE", (REPO / launcher).read_text(), launcher)


class PayhipBotCheck(unittest.TestCase):
    """A Payhip refresh in a visible window waits while you complete the store's check, instead of giving up."""

    def test_waits_then_carries_on(self):
        from hoard import browser

        class Page:
            url, waits = "https://payhip.com/Shop/b-account", 0
            def wait_for_timeout(self, ms): Page.waits += 1
        saved = browser.goto, browser.still_checking
        calls = []

        def goto(page, url):
            calls.append(url)
            if len(calls) == 1:
                raise browser.Blocked("bot check")
        browser.goto = goto
        browser.still_checking = lambda page: Page.waits < 3
        try:
            said = []
            browser.goto_past_check(Page(), "https://payhip.com/Shop/b-account", 30, said.append)
            self.assertIn("Complete the check", said[0])
            self.assertEqual(Page.waits, 3)
            browser.still_checking = lambda page: True
            calls.clear()
            with self.assertRaises(browser.Blocked):   # never completed: gives up after the wait
                browser.goto_past_check(Page(), "https://payhip.com/Shop/b-account", 0.01)
            calls.clear()
            with self.assertRaises(browser.Blocked):   # invisible browser: nobody to complete it, so no waiting
                browser.goto_past_check(Page(), "https://payhip.com/Shop/b-account", 0)
        finally:
            browser.goto, browser.still_checking = saved


class ComingFrom1x(unittest.TestCase):
    """Bringing over a 1.x library list and downloads folder, without overwriting anything."""

    def test_migrate(self):
        from hoard import setup
        old = Path(tempfile.mkdtemp())
        (old / "Hoard").mkdir()
        (old / "HoardDownloader" / "downloads").mkdir(parents=True)
        (old / "HoardDownloader" / "asset_dl.py").write_text("# 1.x")
        (old / "HoardDownloader" / "config.json").write_text(json.dumps({"root": "downloads", "booth": {"enabled": False}}))
        (old / "Hoard" / "library.json").write_text(json.dumps({"items": [
            {"store": "booth", "id": "1", "name": "Rusk", "url": "https://booth.pm/ja/items/1"}], "stores": {}}))
        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        config_file = Path(tempfile.mkdtemp()) / "config.json"
        cfg = config.load_config(config_file)
        said = setup.migrate_from(cfg, old / "Hoard", config_file, lib)
        self.assertIn("1 item)", said)
        self.assertEqual([i["name"] for i in lib.data["items"]], ["Rusk"])
        moved = config.load_config(config_file)
        self.assertEqual(Path(moved["root"]), (old / "HoardDownloader" / "downloads").resolve())
        self.assertFalse(moved["booth"]["enabled"])
        self.assertIn("already has a library list", setup.migrate_from(cfg, old, config_file, lib), "nothing is overwritten")
        self.assertIn("no folder", setup.migrate_from(cfg, old / "missing", config_file, lib))


class DeletedSignIns(unittest.TestCase):
    """Issue #31: a store's sign-in folder deleted while Hoard was closed counts as signing out of it: its list
    goes, as with Sign out, and the downloaded files stay. Imported lists, itch.io's (an API key) and sign-ins an
    older version kept in one shared profile are left alone."""

    def setUp(self):
        from unittest import mock
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = {**config.load_config(), "root": str(self.tmp / "downloads")}
        self.signins = self.tmp / "sign-ins"
        for patch in (mock.patch.object(jobs, "signins_root", lambda cfg: self.signins),
                      mock.patch.object(jobs, "profile_dir", lambda cfg, store: self.signins / store),
                      mock.patch.object(jobs, "old_signins_waiting", lambda cfg: self.waiting)):
            patch.start()
            self.addCleanup(patch.stop)
        self.waiting = False
        self.lib = library.Library(self.tmp / "library.json")
        self.lib.replace_store("gumroad", [library.item("gumroad", "1", name="Suit")])
        self.lib.replace_store("jinxxy", [library.item("jinxxy", "2", name="Hat")])
        self.lib.merge_store("booth", [library.item("booth", "3", name="Imported")])
        self.lib.replace_store("itch", [library.item("itch", "4", name="Tool")])
        (self.signins / "jinxxy").mkdir(parents=True)   # still signed in to Jinxxy

    def names(self):
        return sorted(i["name"] for i in library.Library(self.lib.path).data["items"])

    def test_a_deleted_sign_in_is_a_sign_out(self):
        self.assertEqual(jobs.forget_deleted_signins(self.cfg, self.lib), ["gumroad"])
        self.assertEqual(self.names(), ["Hat", "Imported", "Tool"])
        note = self.lib.data["stores"]["gumroad"]
        self.assertEqual(note["count"], 0)
        self.assertIn("sign-in for Gumroad was deleted", note["error"])
        self.assertIn("1 items", note["error"])
        self.assertEqual(jobs.forget_deleted_signins(self.cfg, self.lib), [], "once")

    def test_every_sign_in_deleted(self):
        shutil.rmtree(self.signins)
        self.assertEqual(sorted(jobs.forget_deleted_signins(self.cfg, self.lib)), ["gumroad", "jinxxy"])
        self.assertEqual(self.names(), ["Imported", "Tool"])

    def test_sign_ins_on_a_drive_thats_not_plugged_in(self):
        """Sign-ins kept elsewhere (advanced_signin_location) with that whole folder missing: the drive may just be
        unplugged, so nothing is removed. A store's own folder missing there still counts as signing out."""
        cfg = {**self.cfg, "advanced_signin_location": True, "profile_dir": str(self.signins)}
        shutil.rmtree(self.signins)
        self.assertEqual(jobs.forget_deleted_signins(cfg, self.lib), [])
        self.assertEqual(self.names(), ["Hat", "Imported", "Suit", "Tool"])
        (self.signins / "jinxxy").mkdir(parents=True)   # plugged in again: Gumroad's sign-in isn't on it
        self.assertEqual(jobs.forget_deleted_signins(cfg, self.lib), ["gumroad"])

    def test_what_counts_as_old_sign_ins(self):
        from unittest import mock
        from hoard import browser
        root = self.tmp / "real" / "sign-ins"
        with mock.patch.object(browser, "signins_root", lambda cfg: root), \
                mock.patch.object(browser, "LEGACY_PROFILE", self.tmp / "none" / ".browser-profile"):
            self.assertFalse(browser.old_signins_waiting(self.cfg), "no sign-ins at all")
            (root / "gumroad").mkdir(parents=True)
            self.assertFalse(browser.old_signins_waiting(self.cfg), "one folder per store: nothing to split")
            (root / "Local State").write_text("{}")
            self.assertTrue(browser.old_signins_waiting(self.cfg), "1.2 to 1.5: one shared profile")
            (root / "Local State").unlink()
            (root.parent / "sign-ins.old").mkdir()
            self.assertTrue(browser.old_signins_waiting(self.cfg), "a move that stopped part-way")

    def test_old_shared_sign_ins_still_to_split(self):
        self.waiting = True
        self.assertEqual(jobs.forget_deleted_signins(self.cfg, self.lib), [])
        self.assertEqual(self.names(), ["Hat", "Imported", "Suit", "Tool"])


class SetupAssistant(unittest.TestCase):
    """What the onboarding assistant relies on."""

    def test_links_from_emails(self):
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.assertIn("Start signing in", job.open_link("https://accounts.booth.pm/confirm"))
        job.state.update(running=True, task="login", store="booth")
        self.assertIn("isn't on Booth's own site", job.open_link("https://booth.pm.login-check.example/"))
        self.assertIn("isn't on Booth's own site", job.open_link("http://accounts.booth.pm/confirm"))
        self.assertIn("isn't on Booth's own site", job.open_link("https://app.gumroad.com/confirm"))
        self.assertIsNone(job.open_link("https://accounts.booth.pm/users/confirmation?token=x"))
        self.assertEqual(job.pending_link, "https://accounts.booth.pm/users/confirmation?token=x")

    def test_signing_in_starts_the_chosen_browser_and_names_it(self):
        """Issue #20: the browser chosen in Settings is the one a sign-in starts. The job says which one, and says
        when Hoard's own stands in for a chosen browser that isn't installed."""
        import contextlib
        import io
        from unittest import mock
        started = []

        class Window:
            pages = []

            def close(self):
                pass

        def launch(p, cfg, headless, store):
            from hoard.browser import use_channel
            started.append(use_channel(cfg))
            return Window()

        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        for installed, choice, used, name in (({"chrome", "msedge"}, "chrome", "chrome", "Google Chrome"),
                                              ({"chrome", "msedge"}, "msedge", "msedge", "Microsoft Edge"),
                                              ({"msedge"}, "chrome", "chromium", "Hoard's own browser")):
            with self.subTest(choice=choice, installed=sorted(installed)):
                job = jobs.Jobs({**config.load_config(), "browser_channel": choice, "automated_sign_in": True}, lib)
                said, out = [], io.StringIO()
                with mock.patch("hoard.browser.channel_installed", lambda channel: channel in installed), \
                        mock.patch.object(jobs, "reachable", lambda store: True), \
                        mock.patch.object(jobs, "_playwright", lambda: contextlib.nullcontext), \
                        mock.patch.object(jobs, "launch", launch), \
                        mock.patch.object(jobs, "open_sign_in_pages", lambda ctx, cfg, store: None), \
                        mock.patch.object(jobs, "check_saved_signin", lambda cfg, store: None), \
                        mock.patch.object(job, "_refresh", lambda stores: None), \
                        mock.patch.object(job, "_set", lambda **kw: said.append(kw.get("message", ""))), \
                        contextlib.redirect_stdout(out):
                    job._login_then_refresh(["gumroad"])
                self.assertEqual(started[-1], used)
                self.assertIn(f"in the {name} window", " ".join(said))
                self.assertIn(f"Signing in to Gumroad with {name}", out.getvalue())
                self.assertEqual("isn't installed" in out.getvalue(), used != choice)

    def plain_sign_in(self, store="gumroad", cfg_extra=None, after_exit_in_use=0, link=None, installed=True, installs=None):
        """Sign in with the browser's own window (issue #21), against a stand-in for starting programs. Returns what
        was started, the messages, and whether the store was refreshed."""
        import contextlib
        import io
        import types
        from unittest import mock
        from hoard import browser
        tmp = Path(tempfile.mkdtemp())
        program = tmp / "chromium"
        program.write_text("")
        cfg = {**config.load_config(), "browser_channel": "chromium", "allow_unprotected_signins": True,
               **(cfg_extra or {})}
        started, said, refreshed = [], [], []
        state = {"polls": 0, "in_use": after_exit_in_use}

        class Proc:
            def poll(self):
                state["polls"] += 1
                if state["polls"] == 2 and link:
                    job.pending_link = link   # pasted while the window is open
                return None if state["polls"] < 4 else 0

        def popen(args, **kw):
            started.append(args)
            return Proc()

        def in_use(profile):
            if state["in_use"] > 0:
                state["in_use"] -= 1
                return True
            return False

        p = types.SimpleNamespace(chromium=types.SimpleNamespace(executable_path=str(program)))
        lib = library.Library(tmp / "library.json")
        job = jobs.Jobs(cfg, lib)
        with mock.patch.object(jobs, "reachable", lambda store: True), \
                mock.patch.object(jobs, "_playwright", lambda: (lambda: contextlib.nullcontext(p))), \
                mock.patch.object(jobs, "SignInWindow", lambda *a, **k: browser.SignInWindow(*a, popen=popen, **k)), \
                mock.patch.object(browser, "_profile_in_use", in_use), \
                mock.patch.object(browser, "profile_dir", lambda cfg, store: tmp / "sign-ins" / store), \
                mock.patch.object(browser, "_migrate_old_signins", lambda p, cfg: None), \
                mock.patch.object(jobs, "check_saved_signin", lambda cfg, store: None), \
                mock.patch.object(jobs, "own_browser_installed", lambda: installed), \
                mock.patch.object(job, "_install_browser", installs or (lambda stores: None)), \
                mock.patch.object(jobs.time, "sleep", lambda s: None), \
                mock.patch.object(job, "_refresh", lambda stores: refreshed.append(stores)), \
                mock.patch.object(job, "_set", lambda **kw: said.append(kw.get("message", ""))), \
                contextlib.redirect_stdout(io.StringIO()):
            job._login_then_refresh([store])
        return started, said, refreshed, tmp / "sign-ins" / store, str(program)

    def test_signing_in_in_the_browsers_own_window(self):
        """Issue #21: Google, Discord and X refuse to sign in from a browser another program drives. So a sign-in
        opens the browser as itself, on the store's own profile (so its sign-in is saved where Hoard reads it, with
        the same protection), and nothing else: no automation, no remote control."""
        from hoard.browser import ProfileLock
        started, said, refreshed, profile, program = self.plain_sign_in()
        first = started[0]
        self.assertEqual(first[0], program, "the chosen browser's own program")
        self.assertIn(f"--user-data-dir={profile}", first, "the store's own profile")
        self.assertIn(library.STORES["gumroad"]["login"], first, "at the store's sign-in page")
        for flag in first:
            self.assertFalse(re.search(r"automation|remote-debugging|headless|webdriver", flag), flag)
        if sys.platform.startswith("linux"):   # (Windows and macOS always use their own keyring)
            self.assertIn("--password-store=basic", first, "the same protection Hoard's own window uses (here, as chosen)")
        self.assertTrue(any("Sign in to Gumroad in the" in m for m in said))
        self.assertEqual(refreshed, [["gumroad"]], "then the store is read, as before")
        lock = ProfileLock(profile)
        lock.acquire()   # (raises ProfileBusy if the sign-in was never let go)
        lock.release()

    def test_hoards_browser_is_installed_on_the_way(self):
        """A tester's report: signing in with Hoard's own browser before it was downloaded failed twice ("Open
        Settings, choose Set up Hoard again"). Now the sign-in downloads it first, then carries on."""
        installed = []
        started, said, refreshed, profile, program = self.plain_sign_in(
            installed=False, installs=lambda stores: installed.append(stores))
        self.assertEqual(installed, [["gumroad"]])
        self.assertTrue(started, "then the sign-in window opens")
        self.assertEqual(refreshed, [["gumroad"]])
        installed.clear()
        self.plain_sign_in(installs=lambda stores: installed.append(stores))
        self.assertEqual(installed, [], "not when it's there already")

    def test_payhip_without_shops_says_what_next_rather_than_failing(self):
        """A tester's report, "Payhip wouldn't login": the sign-in worked, but reading Payhip straight after, with no
        shops added, failed with "add your shops", so it looked like the sign-in had failed."""
        started, said, refreshed, profile, program = self.plain_sign_in(
            "payhip", {"payhip": {**config.load_config()["payhip"], "shops": []}})
        self.assertEqual(refreshed, [], "nothing to read yet")
        self.assertIn(library.PAYHIP_SIGNED_IN_NO_SHOPS, said)
        self.assertTrue(library.PAYHIP_SIGNED_IN_NO_SHOPS.startswith("Signed in to Payhip."))

    def test_waiting_while_the_browser_still_has_the_profile(self):
        """The program Hoard started can end while the window stays open: another window already had the profile and
        took over, or (on a Mac) the window closed but the browser didn't quit. Hoard waits for the profile itself."""
        started, said, refreshed, profile, program = self.plain_sign_in(after_exit_in_use=3)
        self.assertEqual(refreshed, [["gumroad"]])

    def test_a_link_from_an_email_opens_in_the_sign_in_window(self):
        link = "https://app.gumroad.com/confirm?token=x"
        started, said, refreshed, profile, program = self.plain_sign_in(link=link)
        self.assertEqual(len(started), 2)
        self.assertEqual(started[1][-1], link)
        self.assertIn(f"--user-data-dir={profile}", started[1], "the same profile, so the open window takes it")
        self.assertTrue(any("Opened the link from your email" in m for m in said))

    def test_payhip_opens_every_shop(self):
        shops = ["https://shop-one.store", "https://payhip.com/ShopTwo"]
        started, said, refreshed, profile, program = self.plain_sign_in(
            "payhip", {"payhip": {**config.load_config()["payhip"], "shops": shops}})
        self.assertEqual(started[0][-2:], [s + "/b-account" for s in shops])
        self.assertTrue(any("one tab per shop" in m for m in said))

    def test_without_chromiums_own_sandbox_only_where_it_cant_start(self):
        """Hoard's window always runs without Chromium's own sandbox (Playwright's default). A plain window keeps it,
        except on Linux where it can't start: in the Flatpak, as root, or for Playwright's Chromium on a system that
        stops programs without an AppArmor profile using it (Ubuntu 23.10 and later)."""
        from unittest import mock
        from hoard import browser
        restricted = {"on": False}
        real_read = Path.read_text

        def read_text(self, *a, **k):
            if self.as_posix() == "/proc/sys/kernel/apparmor_restrict_unprivileged_userns":   # (on Windows too)
                return "1\n" if restricted["on"] else "0\n"
            return real_read(self, *a, **k)
        with mock.patch.object(browser.sys, "platform", "linux"), mock.patch.object(Path, "read_text", read_text), \
                mock.patch("hoard.paths.in_flatpak", lambda: False), mock.patch.object(browser.os, "geteuid", lambda: 1000, create=True):
            self.assertFalse(browser._without_sandbox("chromium"))
            restricted["on"] = True
            self.assertTrue(browser._without_sandbox("chromium"))
            self.assertFalse(browser._without_sandbox("chrome"), "an installed browser brings its own profile")
            with mock.patch.object(browser.os, "geteuid", lambda: 0, create=True):
                self.assertTrue(browser._without_sandbox("chrome"), "as root")
            with mock.patch("hoard.paths.in_flatpak", lambda: True):
                self.assertTrue(browser._without_sandbox("chrome"), "in the Flatpak")
        for other in ("win32", "darwin"):
            with mock.patch.object(browser.sys, "platform", other):
                self.assertFalse(browser._without_sandbox("chromium"), other)

    def test_on_windows_the_sandbox_may_read_hoards_browser(self):
        """Chromium's own log on Windows: "Sandbox cannot access executable" (Playwright's Chromium, downloaded into
        AppData, doesn't let the sandbox's groups read it), and its network service died: nothing loaded. A plain
        window of Hoard's own browser first lets them read its folder, as an installer does; if that fails, it
        starts without the sandbox rather than not work."""
        from unittest import mock
        from hoard import browser
        ran = []

        def icacls(ok):
            def run(args, **kw):
                ran.append(args)
                return mock.Mock(returncode=0 if ok else 5)
            return run
        program = str(Path(tempfile.mkdtemp()) / "chrome-win64" / "chrome.exe")
        with mock.patch.object(browser.os, "name", "nt"), mock.patch.object(browser.subprocess, "run", icacls(True)):
            self.assertTrue(browser._let_sandbox_read(program))
        self.assertEqual([a[0] for a in ran], ["icacls", "icacls"])
        self.assertEqual({a[1] for a in ran}, {os.path.dirname(program)}, "the browser's own folder, nothing else")
        self.assertEqual(sorted(a[3] for a in ran), ["*S-1-15-2-1:(OI)(CI)(RX)", "*S-1-15-2-2:(OI)(CI)(RX)"],
                         "read and run only, for the sandbox's two groups")
        with mock.patch.object(browser.os, "name", "nt"), mock.patch.object(browser.subprocess, "run", icacls(False)):
            self.assertFalse(browser._let_sandbox_read(program))
        with mock.patch.object(browser.os, "name", "posix"):
            self.assertTrue(browser._let_sandbox_read(program), "nothing to do elsewhere")

    def test_a_profile_in_use(self):
        """How Hoard tells the browser still has a profile open: Chromium's own lock in it."""
        import os as _os
        from hoard import browser
        d = Path(tempfile.mkdtemp())
        self.assertFalse(browser._profile_in_use(d))
        if _os.name == "nt":
            (d / "lockfile").write_text("")
            self.assertFalse(browser._profile_in_use(d), "left behind by a browser that has ended")
        else:
            _os.symlink("host-1234", d / "SingletonLock")
            self.assertTrue(browser._profile_in_use(d))

    def test_a_chosen_browser_thats_missing(self):
        """Settings named Edge or Chrome, which isn't installed: setup offers Hoard's own browser, and once it's
        installed that's the one used and shown as ready (it kept saying the chosen one "isn't installed")."""
        from unittest import mock
        from hoard import browser, setup
        cfg = {**config.load_config(), "browser_channel": "chrome"}
        with mock.patch.object(browser, "channel_installed", lambda channel: False), \
                mock.patch.object(setup, "channel_installed", lambda channel: False):
            self.assertEqual(browser.use_channel(cfg), "chromium")
            with mock.patch.object(setup, "own_browser_installed", lambda: False):
                st = setup.browser_status(cfg)
                self.assertEqual((st["ready"], st["can_install"]), (False, True))
                self.assertIn("Google Chrome isn't installed", st["note"])
            with mock.patch.object(setup, "own_browser_installed", lambda: True):
                st = setup.browser_status(cfg)
                self.assertEqual((st["ready"], st["name"]), (True, "Hoard's own browser"))
        with mock.patch.object(browser, "channel_installed", lambda channel: True), \
                mock.patch.object(setup, "channel_installed", lambda channel: True):
            self.assertEqual(browser.use_channel(cfg), "chrome", "installed: the one you chose")
            self.assertEqual(setup.browser_status(cfg)["name"], "Google Chrome")

    def test_one_browser_folder(self):
        """Installing and launching use the same folder, one outside Hoard's program folder: packaged as an app,
        Playwright looked in the program folder when launching, so an installed browser was never found."""
        from unittest import mock
        from hoard import browser
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
            browser.use_browsers_folder()
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(browser.browsers_folder()))
            self.assertEqual(browser.browsers_folder().name, "ms-playwright")
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/somewhere/you/chose"
            browser.use_browsers_folder()
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], "/somewhere/you/chose", "yours is kept")

    def test_missing_browser_is_explained(self):
        from hoard import setup
        self.assertIn("Set up Hoard", setup.browser_problem(RuntimeError(
            "BrowserType.launch: Executable doesn't exist at /x/chrome\nPlease run: playwright install")))
        self.assertIn("isn't installed", setup.browser_problem(RuntimeError('Chromium distribution "msedge" is not found at /x')))
        self.assertIsNone(setup.browser_problem(RuntimeError("net::ERR_TIMED_OUT")))

    def test_status(self):
        from unittest import mock
        from hoard import browser, setup
        cfg = {**config.load_config(), "profile_dir": tempfile.mkdtemp()}
        signins = Path(tempfile.mkdtemp()) / "sign-ins"   # its own, not one another test signed in to
        patch = mock.patch.object(browser, "signins_root", lambda cfg: signins)
        patch.start()
        self.addCleanup(patch.stop)
        st = setup.setup_status(cfg)
        self.assertEqual(set(st), {"done", "browser", "stores", "payhip_shops", "root", "default_root"})
        self.assertFalse(st["stores"]["booth"]["signed_in"])
        db = browser.profile_dir(cfg, "booth") / "Default" / "Network" / "Cookies"
        db.parent.mkdir(parents=True)
        import sqlite3
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE cookies (host_key TEXT, encrypted_value BLOB, value TEXT)")
        con.execute("INSERT INTO cookies VALUES ('.booth.pm', x'7631', '')")
        con.commit(); con.close()
        self.assertTrue(setup.signed_in(cfg, "booth"))

    def test_status_while_a_browser_has_the_sign_in_open(self):
        """Issue #34: on Windows, a browser keeps its cookie database to itself while it's open (signing in, or
        reading the store), so copying it fails with PermissionError. That took /api/setup down with it every
        second of a sign-in. Now the last answer stands until the browser closes."""
        from unittest import mock
        from hoard import browser, setup
        cfg = {**config.load_config(), "advanced_signin_location": True, "profile_dir": tempfile.mkdtemp()}
        db = browser.profile_dir(cfg, "gumroad") / "Default" / "Network" / "Cookies"
        db.parent.mkdir(parents=True)
        import sqlite3
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE cookies (host_key TEXT, encrypted_value BLOB, value TEXT)")
        con.execute("INSERT INTO cookies VALUES ('.gumroad.com', x'7631', '')")
        con.commit(); con.close()
        setup._last_signed_in.pop("gumroad", None)
        denied = PermissionError(13, "Permission denied", str(db))
        with mock.patch.object(browser.shutil, "copyfile", side_effect=denied):
            with self.assertRaises(browser.CookiesInUse):
                browser._cookie_hosts(browser.profile_dir(cfg, "gumroad"))
            self.assertFalse(setup.signed_in(cfg, "gumroad"), "no answer yet: not signed in")
            st = setup.setup_status(cfg)   # no exception: the assistant gets its answer
            self.assertFalse(st["stores"]["gumroad"]["signed_in"])
        self.assertTrue(setup.signed_in(cfg, "gumroad"))
        with mock.patch.object(browser.shutil, "copyfile", side_effect=denied):
            self.assertTrue(setup.signed_in(cfg, "gumroad"), "the last answer stands while the browser is open")

    def test_endpoints(self):
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def call(method, path, body=None):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
                c.request(method, path, body=json.dumps(body) if body is not None else None,
                          headers={**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: srv.key})
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return r.status, data
            status, st = call("GET", "/api/setup")
            self.assertEqual(status, 200)
            self.assertIn("browser", st)
            self.assertEqual(call("POST", "/api/signin-link", {"url": "https://accounts.booth.pm/x"})[0], 400)
            self.assertEqual(call("POST", "/api/setup/migrate", {"folder": "relative/folder"})[0], 400)
            self.assertEqual(call("POST", "/api/setup/done", {"done": True})[0], 200)
            self.assertTrue(srv.cfg["setup_done"])
        finally:
            srv.shutdown()
            srv.server_close()


class _ItchStandIn:
    """A stand-in api.itch.io and file host, on this computer. It records the Authorization header of every request."""

    KEY = "GoodKey1234567890abcdef"
    DATA = {5550001: b"PAW" * 1000}
    seen: list = []
    uploads: list = []
    fail_next = 0

    @classmethod
    def start(cls):
        import hashlib
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import parse_qs, urlparse
        stand_in = cls

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, status, body=b"", ctype="application/json", headers=None):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():   # a Location made from the request: checked like Hoard's own
                    self.send_header(header_safe(k), header_safe(v))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                u = urlparse(self.path)
                stand_in.seen.append((self.server.server_port, u.path, self.headers.get("Authorization")))
                if self.server is stand_in.files:
                    if stand_in.fail_next:   # a file host having a bad moment (issue #19)
                        stand_in.fail_next -= 1
                        return self.send(503, b"busy", "text/plain")
                    data = stand_in.DATA.get(int(u.path.rsplit("/", 1)[-1]), b"")
                    return self.send(200, data, "application/octet-stream")
                if self.headers.get("Authorization") != f"Bearer {stand_in.KEY}":
                    return self.send(403, json.dumps({"errors": ["invalid key"]}).encode())
                q = parse_qs(u.query)
                if u.path == "/profile":
                    body = {"user": {"username": "buyer", "display_name": "Buyer"}}
                elif u.path == "/profile/owned-keys":
                    body = {"page": 1, "per_page": 50, "owned_keys": [] if q.get("page") != ["1"] else [
                        {"id": 77, "game_id": 1001, "game": {"id": 1001, "title": "Paw Suit", "url": "https://kitsu.itch.io/paw-suit",
                                                            "cover_url": "https://img.itch.zone/paw.png",
                                                            "user": {"display_name": "Kitsu Studio", "url": "https://kitsu.itch.io"}}}]}
                elif u.path == "/games/1001/uploads" and q.get("download_key_id") == ["77"]:
                    body = {"uploads": [dict(x, md5_hash=hashlib.md5(stand_in.DATA.get(x["id"], b"")).hexdigest()
                                             if x["id"] in stand_in.DATA else None) for x in stand_in.uploads]}
                elif u.path.startswith("/uploads/") and u.path.endswith("/download") and q.get("uuid"):
                    upload = u.path.split("/")[2]
                    return self.send(302, headers={"Location": f"http://localhost:{stand_in.files.server_port}/f/{upload}"})
                else:
                    return self.send(404, b"{}")
                self.send(200, json.dumps(body).encode())

        cls.api, cls.files = ThreadingHTTPServer(("127.0.0.1", 0), Handler), ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        for srv in (cls.api, cls.files):
            threading.Thread(target=srv.serve_forever, daemon=True).start()

    @classmethod
    def stop(cls):
        for srv in (cls.api, cls.files):
            srv.shutdown()
            srv.server_close()

    @classmethod
    def use(cls, test):
        """Point Hoard's itch.io code at the stand-ins for one test, with the key kept."""
        from unittest import mock
        from hoard import egress, itch, vault
        cls.seen.clear()
        cls.uploads = [{"id": 5550001, "filename": "PawSuit_v1.2.unitypackage", "size": 3000, "storage": "hosted", "traits": []},
                       {"id": 5550002, "filename": "PawSuit-Demo-Windows.zip", "size": 9, "storage": "hosted", "traits": ["p_windows"]},
                       {"id": 5550003, "filename": "Textures", "storage": "external"}]
        api = f"http://127.0.0.1:{cls.api.server_port}"
        egress._TEST_ORIGINS.update({api, f"http://localhost:{cls.files.server_port}"})
        test.addCleanup(egress._TEST_ORIGINS.clear)
        patcher = mock.patch.object(itch, "API", api)
        patcher.start()
        test.addCleanup(patcher.stop)
        cfg = {**config.load_config(), "request_delay": 0, "allow_unprotected_signins": True}
        vault.save_key(cfg, "itch", cls.KEY)
        test.addCleanup(lambda: vault.forget_key(cfg, "itch"))
        return cfg


class ItchKeys(unittest.TestCase):
    """The itch.io API key: kept with the operating system's protection, never in config.json, and deleted on sign-out."""

    def test_kept_and_forgotten(self):
        from hoard import vault
        cfg = {**config.load_config(), "allow_unprotected_signins": True}
        self.assertIsNone(vault.clean_key("not a key!"))
        self.assertEqual(vault.clean_key('  "GoodKey1234567890abcdef"\n'), "GoodKey1234567890abcdef")
        vault.save_key(cfg, "itch", "GoodKey1234567890abcdef")
        self.assertEqual(vault.load_key(cfg, "itch"), "GoodKey1234567890abcdef")
        self.assertNotIn("GoodKey", json.dumps(cfg))
        if os.name == "posix":
            self.assertEqual(os.stat(paths.data_dir() / "keys" / "itch.key").st_mode & 0o777, 0o600)
        else:   # encrypted by the Windows account: the file isn't the key
            self.assertNotIn(b"GoodKey", (paths.data_dir() / "keys" / "itch.dpapi").read_bytes())
        self.assertTrue(vault.forget_key(cfg, "itch"))
        self.assertIsNone(vault.load_key(cfg, "itch"))
        self.assertFalse(vault.forget_key(cfg, "itch"))

    @unittest.skipUnless(sys.platform.startswith("linux"), "the Linux keyring rule")
    def test_no_keyring_no_key(self):
        from unittest import mock
        from hoard import browser, vault
        with mock.patch.object(vault, "linux_keyring", lambda: None):
            with self.assertRaises(browser.SigninsUnprotected):
                vault.save_key(config.load_config(), "itch", "GoodKey1234567890abcdef")
            self.assertIsNone(vault.load_key(config.load_config(), "itch"))

    def test_the_library_page_doesnt_ask_the_keyring_every_time(self):
        """The Library page asks whether there's an itch.io key, and how sign-ins are protected, on every load. That
        started secret-tool (or security on a Mac) and gdbus each time, and a locked keyring could ask to be
        unlocked again and again. The answers are remembered, and saving or forgetting the key updates them."""
        from unittest import mock
        from hoard import browser, vault
        reads = []
        with mock.patch.object(vault, "_held", {}), \
                mock.patch.object(vault, "load_key", lambda cfg, name: reads.append(name) or None):
            for _ in range(5):
                self.assertFalse(vault.has_key({}, "itch"))
            self.assertEqual(reads, ["itch"], "read once")
            vault._held["itch"] = True   # (what save_key sets)
            self.assertTrue(vault.has_key({}, "itch"))
        asked = []
        with mock.patch.object(browser.sys, "platform", "linux"), mock.patch.object(browser, "_keyring_seen", None), \
                mock.patch.object(browser, "_dbus_names", lambda: asked.append(1) or {"org.freedesktop.secrets"}):
            for _ in range(5):
                self.assertEqual(browser.linux_keyring(), "gnome-libsecret")
            self.assertEqual(len(asked), 1, "the session bus asked once")
            with mock.patch.object(browser.time, "monotonic", lambda: browser._keyring_seen[0] + 61):
                browser.linux_keyring()
            self.assertEqual(len(asked), 2, "and again after a minute")

    def test_the_keychain_gets_only_a_key(self):
        """On a Mac the key goes to the Keychain as a line of `security -i`'s commands, inside quotes: so nothing but
        a key's own characters ever reaches it (a quote could end the command and start another)."""
        import types
        from unittest import mock
        from hoard import vault
        calls = []

        def run(cmd, stdin=""):
            calls.append((cmd, stdin))
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(vault.sys, "platform", "darwin"), mock.patch.object(vault, "_run", run):
            for bad in ('GoodKey1234567890"\ndelete-keychain', "GoodKey1234567890 abc", "short"):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    vault.save_key(config.load_config(), "itch", bad)
            self.assertEqual(calls, [], "nothing was run")
            vault.save_key(config.load_config(), "itch", "GoodKey1234567890abcdef")
        (cmd, stdin), = calls
        self.assertEqual(cmd, ["security", "-i"])
        self.assertIn('-w "GoodKey1234567890abcdef"', stdin)
        self.assertNotIn("GoodKey", " ".join(cmd), "never on a command line")

    @unittest.skipUnless(sys.platform.startswith("linux"), "the Linux keyring")
    def test_the_keyring_gets_it_on_stdin(self):
        """Through secret-tool, with the key on stdin: never on a command line, which other accounts can read."""
        from unittest import mock
        from hoard import vault
        calls = []

        def run(cmd, stdin=""):
            calls.append((cmd, stdin))
            return types.SimpleNamespace(returncode=0, stdout="GoodKey1234567890abcdef\n", stderr="")
        import types
        with mock.patch.object(vault, "linux_keyring", lambda: "gnome-libsecret"), \
                mock.patch.object(vault.shutil, "which", lambda name: "/usr/bin/" + name), mock.patch.object(vault, "_run", run):
            vault.save_key(config.load_config(), "itch", "GoodKey1234567890abcdef")
            self.assertEqual(vault.load_key(config.load_config(), "itch"), "GoodKey1234567890abcdef")
        self.assertEqual(calls[0][0][:2], ["secret-tool", "store"])
        self.assertEqual(calls[0][1], "GoodKey1234567890abcdef")
        self.assertFalse(any("GoodKey" in " ".join(cmd) for cmd, _stdin in calls))


class ItchAPI(unittest.TestCase):
    """itch.io through its API, against a stand-in: the library, the files, and where the key goes."""

    @classmethod
    def setUpClass(cls):
        _ItchStandIn.start()

    @classmethod
    def tearDownClass(cls):
        _ItchStandIn.stop()

    def sync(self, cfg, root):
        import types
        report = downloader.Report()
        downloader.sync_itch(cfg, root, types.SimpleNamespace(headed=False, only=None, dry_run=False), report)
        return report

    def test_the_library(self):
        cfg = _ItchStandIn.use(self)
        (i,) = library.fetch_itch(None, cfg, lambda m: None)
        self.assertEqual((i["key"], i["name"], i["creator"], i["url"], i["download_url"]),
                         ("itch:1001", "Paw Suit", "Kitsu Studio", "https://kitsu.itch.io/paw-suit", None))

    def test_downloads_and_where_the_key_goes(self):
        from unittest import mock
        cfg = _ItchStandIn.use(self)
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(downloader, "save_thumbnail", lambda *a, **k: None):
            report = self.sync(cfg, root)
            self.assertEqual(report.failed, [])
            folder = root / "Itch" / "Kitsu Studio" / "Paw Suit"
            self.assertEqual((folder / "PawSuit_v1.2.unitypackage").read_bytes(), b"PAW" * 1000)
            self.assertFalse((folder / "PawSuit-Demo-Windows.zip").exists(), "a game build, skipped")
            skipped = " ".join(report.skipped)
            self.assertIn("a game build for Windows", skipped)
            self.assertIn("kept on another website", skipped)
            api, files = _ItchStandIn.api.server_port, _ItchStandIn.files.server_port
            self.assertTrue(all(auth == f"Bearer {_ItchStandIn.KEY}" for port, _p, auth in _ItchStandIn.seen if port == api))
            self.assertEqual([auth for port, _p, auth in _ItchStandIn.seen if port == files], [None], "the file host never gets the key")
            _ItchStandIn.seen.clear()
            self.assertEqual(self.sync(cfg, root).new_files, [], "nothing again while itch.io shows the same file")
            _ItchStandIn.DATA[5550001] = b"PAW2" * 1000   # the creator updates it
            _ItchStandIn.uploads[0]["filename"] = "PawSuit_v1.3.unitypackage"
            try:
                report = self.sync(cfg, root)
            finally:
                _ItchStandIn.DATA[5550001] = b"PAW" * 1000
            self.assertEqual(len(report.updated), 1)
            self.assertEqual((folder / "PawSuit_v1.3.unitypackage").read_bytes(), b"PAW2" * 1000)
            cfg["itch"] = {**cfg["itch"], "skip_game_builds": False}
            _ItchStandIn.DATA[5550002] = b"DEMO"
            try:
                self.sync(cfg, root)
            finally:
                del _ItchStandIn.DATA[5550002]
            self.assertTrue((folder / "PawSuit-Demo-Windows.zip").is_file(), "game builds when you want them")
        manifest = (root / "Itch" / "_manifest.json").read_text("utf-8")
        self.assertNotIn(_ItchStandIn.KEY, manifest)
        catalog, _tags = downloader.collect_catalog(config.load_config(), root)
        self.assertEqual(downloader.validate_catalog_entry(catalog[0]), [])

    def test_checking_for_updates_and_updating(self):
        """Issue #26: a check reads itch.io without downloading anything, and lists what the creator changed on
        what you've downloaded; a file deleted here isn't an update; updating downloads just those files, and the
        list is cleared once they're saved."""
        import types
        from unittest import mock
        from hoard import tags
        from hoard.asset_updates import AssetUpdates
        cfg = _ItchStandIn.use(self)
        root = Path(tempfile.mkdtemp())
        updates = AssetUpdates(Path(tempfile.mkdtemp()) / "asset-updates.json")
        key = tags.tag_key("itch", "Paw Suit")
        folder = root / "Itch" / "Kitsu Studio" / "Paw Suit"

        def run(dry_run, keys=None):
            report = downloader.Report()
            args = types.SimpleNamespace(headed=False, only=None, dry_run=dry_run, keys=keys)
            downloader.sync_itch(cfg, root, args, report)
            report.stores_done.append("itch")
            if dry_run:
                updates.record_check(report.stores_done, keys, report.available)
            else:
                updates.after_download(report.got, report.failed)
            return report

        with mock.patch.object(downloader, "save_thumbnail", lambda *a, **k: None):
            self.assertEqual(run(True).available, [], "never downloaded: that's Download new, not an update")
            run(False)
            self.assertEqual(run(True).available, [], "up to date")
            self.assertEqual(updates.load()["items"], {})

            (folder / "PawSuit_v1.2.unitypackage").unlink()   # deleted here, unchanged on itch.io
            self.assertEqual(run(True).available, [], "deleted here isn't an update")
            run(False)

            _ItchStandIn.DATA[5550001] = b"PAW2" * 1000   # the creator updates it
            _ItchStandIn.uploads[0]["filename"] = "PawSuit_v1.3.unitypackage"
            try:
                found = run(True).available
                self.assertEqual([(a["key"], a["file"], a["kind"]) for a in found],
                                 [(key, "PawSuit_v1.3.unitypackage", "changed")])
                self.assertFalse((folder / "PawSuit_v1.3.unitypackage").exists(), "a check downloads nothing")
                self.assertEqual(updates.load()["items"][key]["files"], [{"file": "PawSuit_v1.3.unitypackage", "kind": "changed"}])
                self.assertIn("itch", updates.load()["checked"])
                self.assertEqual(run(False, keys={"itch:someotherthing"}).got, set(), "only the products asked for")
                self.assertIn(key, updates.load()["items"], "still to update")
                run(False, keys={key})
                self.assertEqual((folder / "PawSuit_v1.3.unitypackage").read_bytes(), b"PAW2" * 1000)
                self.assertEqual(updates.load()["items"], {}, "updated, so off the list")
            finally:
                _ItchStandIn.DATA[5550001] = b"PAW" * 1000

    def test_a_file_that_doesnt_match_its_checksum(self):
        from unittest import mock
        cfg = _ItchStandIn.use(self)
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(downloader, "save_thumbnail", lambda *a, **k: None), \
                mock.patch.object(downloader, "md5_of", lambda path: "0" * 32):
            report = self.sync(cfg, root)
        self.assertIn("didn't match itch.io's checksum", report.failed[0])
        self.assertFalse((root / "Itch" / "Kitsu Studio" / "Paw Suit" / "PawSuit_v1.2.unitypackage").exists())

    def test_a_refused_key(self):
        from hoard import itch, vault
        cfg = _ItchStandIn.use(self)
        vault.save_key(cfg, "itch", "WrongKey1234567890abcdef")
        with self.assertRaises(itch.KeyRefused):
            library.fetch_itch(None, cfg, lambda m: None)
        vault.forget_key(cfg, "itch")
        with self.assertRaises(common.NotLoggedIn):
            self.sync(cfg, Path(tempfile.mkdtemp()))

    def test_signing_in_and_out(self):
        """The page's key goes to POST /api/itch-key: checked with itch.io, kept, and the library read, no browser."""
        from unittest import mock
        from hoard import vault
        cfg = _ItchStandIn.use(self)
        vault.forget_key(cfg, "itch")
        srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        srv.lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        srv.jobs.lib = srv.lib
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def post(path, body):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
            c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key})
            r = c.getresponse()
            data = json.loads(r.read() or b"{}")
            c.close()
            return r.status, data
        self.assertEqual(post("/api/itch-key", {"key": "short"})[0], 400)
        self.assertEqual(post("/api/itch-key", {"key": "WrongKey1234567890abcdef"})[0], 400)
        self.assertIsNone(vault.load_key(cfg, "itch"), "a refused key isn't kept")
        self.assertEqual(post("/api/login", {"stores": ["itch"]})[0], 400, "no browser sign-in for itch.io")
        with mock.patch.object(jobs, "reachable", lambda store, timeout=5.0: True), \
                mock.patch.object(jobs, "launch", lambda *a, **k: self.fail("a browser was opened")):
            status, said = post("/api/itch-key", {"key": _ItchStandIn.KEY})
            self.assertEqual((status, said["user"]), (200, "Buyer"))
            for _ in range(200):
                if not srv.jobs.state["running"] and srv.lib.data["items"]:
                    break
                time.sleep(0.05)
        self.assertEqual(vault.load_key(cfg, "itch"), _ItchStandIn.KEY)
        self.assertEqual([i["key"] for i in srv.lib.data["items"]], ["itch:1001"])
        from hoard import browser
        said = browser.sign_out(None, cfg, "itch")
        self.assertIn("deleted the saved API key", said)
        self.assertIsNone(vault.load_key(cfg, "itch"))


class PayhipIsListedOnly(unittest.TestCase):
    """Hoard reads Payhip and never downloads from it: a sync leaves it out, however it's asked."""

    def test_syncing_leaves_payhip_out(self):
        import types
        from unittest import mock
        synced = []
        pretend = {f"sync_{s}": (lambda s: lambda cfg, root, args, report: synced.append(s))(s) for s in library.DOWNLOADABLE}
        cfg = {**config.load_config(), "root": tempfile.mkdtemp()}
        with mock.patch.multiple(downloader, reachable=lambda store, timeout=5.0: True, build_catalog=lambda cfg, root: None,
                                 **pretend):
            for asked in ("all", ["payhip", "booth"], ["payhip"]):
                downloader.cmd_sync(cfg, types.SimpleNamespace(store=asked, dry_run=False, only=None, headed=False))
        self.assertEqual(synced, ["booth", "gumroad", "jinxxy", "itch", "booth"])
        self.assertFalse(hasattr(downloader, "sync_payhip"))

    def test_refreshing_without_shops_opens_no_window(self):
        """With no shop listed there's nothing to read, so no window opens just to say so; importing is suggested."""
        from unittest import mock
        cfg = config.load_config()
        cfg["payhip"] = {**cfg["payhip"], "shops": []}
        job = jobs.Jobs(cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))

        class NoBrowser:
            def __enter__(self):
                return None

            def __exit__(self, *a):
                return False

        def launch(*a, **k):
            raise AssertionError("a browser window was opened")
        with mock.patch.multiple(jobs, reachable=lambda store, timeout=5.0: True, _playwright=lambda: NoBrowser, launch=launch):
            job._refresh(["payhip"])
        self.assertIn("Import each shop's saved library pages", job.lib.data["stores"]["payhip"]["error"])

    def test_nothing_that_downloads_takes_payhip(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["sync", "--store", "payhip"])
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        done = []
        job.on_download_done = lambda: done.append(True)
        job._download(["payhip"], None)
        self.assertIn("download it from Payhip yourself", job.state["message"])
        self.assertEqual(done, [True], "the downloads view is still told the job ended")
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            c.request("POST", "/api/download", body=json.dumps({"stores": ["payhip"]}),
                      headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key})
            r = c.getresponse()
            said = json.loads(r.read())
            c.close()
            self.assertEqual(r.status, 400)
            self.assertIn("doesn't download from it", said["error"])
            self.assertFalse(srv.jobs.state["running"])
        finally:
            srv.shutdown()
            srv.server_close()


class ImportingPages(unittest.TestCase):
    """The import endpoint: saved pages a batch at a time, each with its own result. A Payhip shop a page names is
    only added once you've confirmed it; test_readers reads real pages, and test_pages goes through the Library."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        cfg = {**config.load_config(), "offline_images": False}
        cfg["payhip"] = {**cfg["payhip"], "shops": []}
        self.srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False, config_path=self.tmp / "config.json")
        self.srv.lib = library.Library(self.tmp / "library.json")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        config.apply_store_sites(config.load_config())

    def post(self, body):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=20)
        c.request("POST", "/api/import", body=json.dumps(body),
                  headers={"Content-Type": "application/json", ACCESS_HEADER: self.srv.key})
        r = c.getresponse()
        data = json.loads(r.read() or b"{}")
        c.close()
        return r.status, data

    @staticmethod
    def pretend(cfg, pages, store, trust):
        """import_saved_pages without a browser: shop pages need their shop trusted, itch pages are read, the rest fail."""
        results = []
        for name, text in pages:
            if name.startswith("shop"):
                if "https://testshop.store" not in trust:
                    results.append({"filename": name, "confirm_shop": "https://testshop.store"})
                    continue
                cfg["payhip"]["shops"] = ["https://testshop.store"]
                results.append({"filename": name, "store": "payhip", "items": [library.item("payhip", "testshop.store-" + text, name=text)]})
            elif name.startswith("itch"):
                results.append({"filename": name, "store": "itch", "items": [library.item("itch", "kitsu/" + text, name=text)]})
            else:
                results.append({"filename": name, "error": "couldn't tell which store this page is from"})
        return results

    def test_each_page_gets_its_own_result(self):
        from unittest import mock
        with mock.patch.object(server, "import_saved_pages", self.pretend):
            status, got = self.post({"files": [{"filename": "shop 1.mhtml", "content": "One"},
                                               {"filename": "itch library.html", "content": "paw-suit"},
                                               {"filename": "notes.html", "content": "hello"}]})
            self.assertEqual(status, 200)
            self.assertEqual([r.get("count", r.get("confirm_shop", r.get("error"))) for r in got["results"]],
                             ["https://testshop.store", 1, "couldn't tell which store this page is from"])
            self.assertEqual(got["totals"], {"itch": {"label": "itch.io", "total": 1}})
            self.assertEqual(got["added_shops"], [])
            self.assertFalse((self.tmp / "config.json").exists(), "nothing confirmed, so no shop added")
            status, got = self.post({"files": [{"filename": "shop 1.mhtml", "content": "One"}],
                                     "trust_shops": ["https://testshop.store"]})
        self.assertEqual((got["results"][0]["count"], got["added_shops"]), (1, ["https://testshop.store"]))
        self.assertEqual(json.loads((self.tmp / "config.json").read_text("utf-8"))["payhip"]["shops"], ["https://testshop.store"])
        self.assertEqual(sorted(i["key"] for i in self.srv.lib.data["items"]), ["itch:kitsu/paw-suit", "payhip:testshop.store-One"])
        self.assertEqual(self.srv.lib.data["stores"]["itch"]["source"], "import")

    def test_what_isnt_a_batch_of_pages(self):
        for body in ({}, {"files": []}, {"files": "page"}, {"files": [{"filename": "a.mhtml"}]}, {"files": [{"content": 5}]},
                     {"files": [{"filename": "p.mhtml", "content": ""}] * (server.MAX_IMPORT_FILES + 1)}):
            self.assertEqual(self.post(body)[0], 400, body)


class ImportCommand(unittest.TestCase):
    """hoard-cli import: files and folders of saved pages, a batch at a time, with a line for each page that wasn't
    imported."""

    def test_files_and_folders(self):
        import contextlib
        import io
        import types
        from unittest import mock
        tmp = Path(tempfile.mkdtemp())
        (tmp / "pages" / "more").mkdir(parents=True)
        for rel in ("pages/a.mhtml", "pages/more/b.html", "pages/notes.txt", "c.mht"):
            (tmp / rel).write_text("page " + rel, "utf-8")
        batches = []

        def pretend(cfg, pages, store, trust, progress):
            batches.append([name for name, _text in pages])
            for n, (name, _text) in enumerate(pages, 1):
                progress(n, len(pages), name)
            return [{"filename": name, "confirm_shop": "https://testshop.store"} if name == "c.mht"
                    else {"filename": name, "store": "booth", "items": [library.item("booth", name, name=name)]}
                    for name, _text in pages]
        out = io.StringIO()
        with mock.patch.object(cli, "import_saved_pages", pretend), mock.patch.object(cli, "LIBRARY_FILE", tmp / "library.json"), \
                contextlib.redirect_stdout(out):
            code = cli.cmd_import(config.load_config(), types.SimpleNamespace(
                paths=[tmp / "pages", tmp / "c.mht"], store=None, trust_shop=None, config=tmp / "config.json"), batch=2)
        self.assertEqual(batches, [["a.mhtml", "b.html"], ["c.mht"]], "folders searched, other files left alone")
        said = out.getvalue()
        self.assertIn("Reading b.html (2 of 3)", said)
        self.assertIn("Imported 2 Booth items", said)
        self.assertIn("--trust-shop testshop.store", said)
        self.assertEqual(code, 1, "a page wasn't imported, and a script can tell")
        self.assertEqual(len(library.Library(tmp / "library.json").data["items"]), 2)

    def test_a_shop_must_be_a_shop(self):
        import types
        with self.assertRaises(SystemExit) as stopped:
            cli.cmd_import(config.load_config(), types.SimpleNamespace(paths=[], store=None, trust_shop=["http://192.168.1.5"],
                                                                        config=None))
        self.assertIn("isn't a Payhip shop", str(stopped.exception))


class StoreTables(unittest.TestCase):
    """Every list of stores, in the app, its pages and Hoard for Unity, names the same stores, so a store can't be
    half added, or half taken away."""

    def test_the_same_stores_everywhere(self):
        import re
        from hoard import browser, downloads, net, safety, tags
        stores = set(library.STORES)
        for name, table in (("browser.STORE_SITES", browser.STORE_SITES), ("browser.STORE_ORIGINS", browser.STORE_ORIGINS),
                            ("browser.STORE_ACCOUNT_PAGES", browser.STORE_ACCOUNT_PAGES), ("net.STORE_HOSTS", net.STORE_HOSTS),
                            ("safety.STORE_LINK_SITES", safety.STORE_LINK_SITES), ("library.FETCHERS", library.FETCHERS),
                            ("downloader.STORE_DIRS", {s: d for s, d in downloader.STORE_DIRS.items() if s != "local"})):
            self.assertEqual(set(table), stores, name)
        self.assertEqual(downloader.STORE_DIRS["local"], "Local", "your own packages (issue #80): a folder, not a store")
        self.assertTrue(tags.TAG_KEY_RX.match("local:thing"), "and tagged like the rest")
        for s in stores:
            self.assertIn(s, config.DEFAULT_CONFIG)
            self.assertTrue(tags.TAG_KEY_RX.match(f"{s}:thing"), s)
            self.assertEqual(downloader.STORE_DIRS[s].lower(), s, "a store's folder is its name: records find their store by it")
        self.assertEqual(set(downloads.STORES), set(downloader.STORE_DIRS.values()))
        self.assertTrue(set(library.DOWNLOADABLE) <= stores and set(library.IMPORTABLE) <= stores)
        self.assertNotIn("payhip", library.DOWNLOADABLE)
        web = REPO / "hoard" / "web"
        for page in ("library.html", "downloads.html"):
            html = (web / page).read_text("utf-8")
            for const in ("STORE_SITES", "STORE_NAMES"):
                keys = set(re.findall(r"(\w+):", re.search(rf"const {const} = \{{(.*?)\}};", html).group(1)))
                self.assertEqual(keys, stores, f"{page}: {const}")
            # the standard colours, in the page's :root (dark) and its light theme; the colour-blind set (issue #112) too
            standard = "\n".join(re.findall(r"^\s*:root \{.*?\n\s*\}", html, re.M | re.S))
            colourblind = "\n".join(re.findall(r':root\[data-colours="colourblind"\] \{[^}]*\}', html))
            for s in stores:
                self.assertEqual(len(re.findall(rf"--{s}: #[0-9A-Fa-f]{{6}};", standard)), 2, f"{page}: {s}'s colour, in both themes")
                self.assertEqual(len(re.findall(rf"--{s}: #[0-9A-Fa-f]{{6}};", colourblind)), 2, f"{page}: {s}'s colour-blind colour, in both themes")
                self.assertIn(f".{s} {{ --c: var(--{s}); }}", html, page)
        order = re.search(r"const STORE_ORDER = \[(.*?)\];", (web / "library.html").read_text("utf-8")).group(1)
        self.assertEqual(re.findall(r'"(\w+)"', order), list(library.STORES))
        self.assertEqual(set(re.findall(r'data-store="(\w+)"', (web / "downloads.html").read_text("utf-8"))),
                         set(downloader.STORE_DIRS.values()))
        unity = REPO / "Packages" / "soloflighter.hoard" / "Editor"
        catalog = (unity / "Core" / "Catalog.cs").read_text("utf-8")
        self.assertEqual(set(re.findall(r'"(\w+)"', re.search(r"Stores = \{(.*?)\};", catalog).group(1))),
                         set(downloader.STORE_DIRS.values()))
        self.assertEqual(dict(re.findall(r'\{ "(\w+)", "([\w.]+)" \}', catalog)),
                         {downloader.STORE_DIRS[s]: safety.STORE_LINK_SITES[s][0] for s in stores})
        window = (unity / "HoardWindow.cs").read_text("utf-8")
        self.assertEqual(re.findall(r'"(\w+)"', re.search(r"StoreNames = \{(.*?)\};", window).group(1)),
                         [downloader.STORE_DIRS[s] for s in library.STORES] + ["Local"])   # your own (issue #80)


class CommandLine(unittest.TestCase):
    """Every command still exists."""

    def test_commands(self):
        import contextlib
        import io
        for cmd in ("login", "logout", "refresh", "import", "sync", "tags", "verify", "migrate", "debug", "probe"):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                cli.main([cmd, "--help"])
            self.assertIn("usage", out.getvalue().lower(), cmd)


class CatalogSeal(unittest.TestCase):
    """The Unity window reads catalog.json: when it isn't sealed with this install's key, Hoard seals it again."""

    def setUp(self):
        from hoard import safety
        self.safety = safety
        self.root = Path(tempfile.mkdtemp())
        self.cfg = {**config.load_config(), "root": str(self.root)}

    def catalog(self, key: bytes | None = None, text: str | None = None) -> Path:
        path = self.root / "catalog.json"
        if text is not None:
            path.write_text(text, "utf-8")
            return path
        saved = self.safety._integrity_key
        if key is not None:
            self.safety._integrity_key = key
        try:
            path.write_text(json.dumps(self.safety.seal({"format": "hoard-catalog", "version": 3, "assets": []})), "utf-8")
        finally:
            self.safety._integrity_key = saved
        return path

    def status(self) -> str:
        return self.safety.check_seal(json.loads((self.root / "catalog.json").read_text("utf-8")))

    def test_sealed_elsewhere_is_sealed_again(self):
        self.catalog(bytes(range(32)))   # another key: another computer, or Hoard on Store Python
        self.assertEqual(self.status(), "foreign")
        self.assertEqual(downloader.reseal_catalog(self.cfg, self.root), "foreign")
        self.assertEqual(self.status(), "sealed")

    def test_already_sealed_is_left_alone(self):
        path = self.catalog()
        before = path.stat().st_mtime_ns
        self.assertIsNone(downloader.reseal_catalog(self.cfg, self.root))
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_unreadable_or_missing(self):
        self.catalog(text="{not json")
        self.assertEqual(downloader.reseal_catalog(self.cfg, self.root), "unreadable")
        self.assertEqual(self.status(), "sealed")
        (self.root / "catalog.json").unlink()
        self.assertIsNone(downloader.reseal_catalog(self.cfg, self.root))

    def test_at_startup(self):
        self.catalog(bytes(range(32)))
        ready = threading.Event()
        state = {}
        threading.Thread(target=server.serve, daemon=True, kwargs=dict(
            cfg=self.cfg, port=0, open_browser=False,
            on_ready=lambda url, srv: (state.update(srv=srv), ready.set()))).start()
        self.assertTrue(ready.wait(20))
        try:
            for _ in range(100):
                if self.status() == "sealed":
                    break
                time.sleep(0.1)
            self.assertEqual(self.status(), "sealed", "opening Hoard seals the catalog again")
        finally:
            state["srv"].shutdown()
            state["srv"].server_close()

    def test_not_while_a_job_runs(self):
        self.catalog(bytes(range(32)))
        srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)
        try:
            srv.jobs.busy.acquire()
            server.reseal_in_background(srv, self.cfg)
            self.assertEqual(self.status(), "foreign", "a running job rebuilds the catalog itself")
            srv.jobs.busy.release()
            server.reseal_in_background(srv, self.cfg)
            self.assertEqual(self.status(), "sealed")
        finally:
            srv.server_close()

    def test_a_sealed_catalog_never_holds_up_a_job(self):
        """Starting Hoard with a catalog that's fine doesn't take the job lock at all, so the first thing chosen
        after starting never finds Hoard "busy"."""
        from unittest import mock
        self.catalog(bytes(range(32)))
        first = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)
        server.reseal_in_background(first, self.cfg)   # sealed with this computer's key now
        first.server_close()
        self.assertEqual(self.status(), "sealed")
        srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)
        try:
            with mock.patch.object(srv.jobs, "busy", mock.Mock(**{"acquire.side_effect": AssertionError("took the job lock")})):
                server.reseal_in_background(srv, self.cfg)
        finally:
            srv.server_close()

    def test_store_python_is_recognised(self):
        from unittest import mock
        store = r"C:\Users\sam\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe"
        org = r"C:\Users\sam\AppData\Local\Programs\Python\Python312\python.exe"
        with mock.patch.object(paths.sys, "platform", "win32"):
            with mock.patch.object(paths.sys, "executable", store):
                self.assertTrue(paths.store_python())
            with mock.patch.object(paths.sys, "executable", org), mock.patch.object(paths.sys, "prefix", org), \
                 mock.patch.object(paths.sys, "base_prefix", org):
                self.assertFalse(paths.store_python())
        with mock.patch.object(paths.sys, "platform", "linux"), mock.patch.object(paths.sys, "executable", store):
            self.assertFalse(paths.store_python())


class CopiesStack(unittest.TestCase):
    """Issue #111: copies of one product stack by their picture's hash, byte for byte, not by name: in beta 4's first
    build, "Hair Pack 1" and "Hair Pack 2" by one creator stacked into one tile."""

    def test_the_same_picture_stacks(self):
        import hashlib
        from unittest import mock
        def pic(n):
            return f"https://booth.pximg.net/p{n}.png"
        pictures = {0: b"rusk", 1: b"rusk", 2: b"hair 1", 3: b"hair 2", 4: b"banner", 5: b"banner"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(library, "THUMB_DIR", Path(tmp)):
            for n, data in pictures.items():
                (Path(tmp) / (hashlib.sha1(pic(n).encode()).hexdigest() + ".png")).write_bytes(data)
            items = [library.item("booth", str(n), name=name, creator=creator, thumbnail=pic(n)) for n, (name, creator) in
                     enumerate([("Rusk v1", "Kitsu"), ("Rusk v2", "Kitsu"), ("Hair Pack 1", "Kitsu"), ("Hair Pack 2", "Kitsu"),
                                ("Fox", "Kitsu"), ("Wolf", "Someone Else"), ("Unsaved", "Kitsu")])]
            keys = [e["stack_key"] for e in library.enrich(items, {})]
            self.assertTrue(keys[0] and keys[0] == keys[1], "two copies, one picture")
            self.assertNotEqual(keys[2], keys[3], "two products, two pictures, however alike their names")
            self.assertEqual(keys[4:], ["", "", ""], "a picture two creators share is a stand-in; an unsaved one stacks nothing")
            (Path(tmp) / (hashlib.sha1(pic(1).encode()).hexdigest() + ".png")).write_bytes(b"rusk, updated")
            keys = [e["stack_key"] for e in library.enrich(items, {})]
            self.assertNotEqual(keys[0], keys[1], "a picture that changes is read again")


class TagMatching(unittest.TestCase):
    """Matching tags go through a word index (review finding P-04), with exactly name_has_word's answers."""

    def test_same_answers(self):
        import random
        from hoard.tags import TagMatcher, name_has_word
        rng = random.Random(7)
        parts = ["fox", "foxes", "foxs", "foxess", "box", "boxes", "Fox", "FoxEars", "fox-ears", "fox ears", "ear",
                 "v-roid", "3d", "3D", "model", "models", "ラスク", "ﾗｽｸ", "Kemonomimi", "cat's", "v2", "_", "-", "【", "】",
                 "x", "xs", "xes", "es", "s"]
        words = ["fox", "box", "ear", "fox ears", "v-roid", "3d model", "3d", "model", "ラスク", "kemono", "fox-", "-x",
                 "Fox", "x", "es", "s", "cat's", "ﾗｽｸ", "fox ear"]
        tags = {f"t{n}": {"match": w} for n, w in enumerate(words)} | {"plain": {"match": None}}
        matcher = TagMatcher(tags)
        names = [" ".join(rng.choice(parts) for _ in range(rng.randint(1, 6))) for _ in range(2000)]
        names += ["".join(rng.choice(parts) for _ in range(rng.randint(1, 4))) for _ in range(1000)]
        for name in names:
            want = {t for t, i in tags.items() if i["match"] and name_has_word(name, i["match"])}
            self.assertEqual(matcher.tags(name), want, name)

    def test_big_library(self):
        import random
        from hoard.tags import TagMatcher, TagStore
        rng = random.Random(3)
        vocab = [f"word{n}" for n in range(3000)]
        data = {"items": {}, "excluded": {}, "hidden": [],
                "tags": {f"tag{n}": {"match": vocab[n * 7 % 3000]} for n in range(300)}}
        names = [" ".join(rng.choice(vocab) for _ in range(5)) for _ in range(20000)]
        start = time.time()
        matcher = TagMatcher(data["tags"])
        for n, name in enumerate(names):
            TagStore.tags_for(data, f"Booth/{n}", name, matcher)
        self.assertLess(time.time() - start, 5, "20,000 names with 300 matching tags (every tag on every name: ~30 s)")


class CheckingForUpdates(unittest.TestCase):
    """Issue #26: the check-updates job runs the downloader as a dry run, keeps what it found, and says so; a store
    it couldn't read keeps what an earlier check found for it."""

    def test_the_job(self):
        from unittest import mock
        from hoard import asset_updates
        path = Path(tempfile.mkdtemp()) / "asset-updates.json"
        seen = []

        def cmd_sync(cfg, args):
            seen.append((args.dry_run, args.keys))
            report = downloader.Report()
            report.stores_done.append("booth")   # Gumroad couldn't be read
            report.failed.append("Gumroad: not signed in")
            report.available += [{"store": "booth", "key": "booth:rusk", "name": "Rusk", "creator": "K", "file": "v2.zip", "kind": "new"},
                                 {"store": "booth", "key": "booth:rusk", "name": "Rusk", "creator": "K", "file": "tex.zip", "kind": "changed"}]
            return report
        store = asset_updates.AssetUpdates(path)
        store.record_check(["gumroad"], None, [{"store": "gumroad", "key": "gumroad:suit", "name": "Suit", "creator": "M",
                                                 "file": "suit.zip", "kind": "changed"}])
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        with mock.patch.object(asset_updates, "updates_file", lambda: path), \
                mock.patch("hoard.downloader.cmd_sync", cmd_sync):
            job._download(["booth", "gumroad", "payhip"], None, check=True)
        self.assertEqual(seen, [(True, None)], "a dry run: nothing is downloaded")
        self.assertEqual(job.state["report"]["updates"], 1)
        self.assertEqual(job.state["message"], "Checked: 1 item has updates (2 in all). Couldn't check Gumroad.")
        items = store.load()["items"]
        self.assertEqual([f["file"] for f in items["booth:rusk"]["files"]], ["v2.zip", "tex.zip"])
        self.assertIn("gumroad:suit", items, "kept: Gumroad couldn't be checked this time")
        self.assertEqual(sorted(store.load()["checked"]), ["booth", "gumroad"])

    def test_what_a_damaged_file_gives(self):
        from hoard.asset_updates import AssetUpdates
        path = Path(tempfile.mkdtemp()) / "asset-updates.json"
        path.write_text('{"items": {"booth:x": {"store": "nowhere", "files": [{"file": "a"}]}, '
                        '"booth:y": {"store": "booth", "files": [{"file": "b", "kind": "odd"}]}}, "checked": [1]}')
        self.assertEqual(AssetUpdates(path).load(), {"checked": {}, "items": {
            "booth:y": {"store": "booth", "name": "", "creator": "", "files": [{"file": "b", "kind": "new"}]}}})
        path.write_text("{not json")
        self.assertEqual(AssetUpdates(path).load(), AssetUpdates.empty())


class DeletedFromDisk(unittest.TestCase):
    """Issue #24: a download whose files were all deleted from disk leaves the Downloads page on the next rescan,
    and the library offers it again. One with only some files gone stays, marked as missing them."""

    def test_rescan_after_deleting(self):
        from hoard.downloads import build_index
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for folder, names in (("booth/Rusk", ["rusk.zip"]), ("booth/Pollution", ["a.unitypackage", "b.zip"])):
            (root / folder).mkdir(parents=True)
            for n in names:
                (root / folder / n).write_bytes(b"x" * 10)
        catalog = [{"store": "booth", "name": "Rusk", "creator": "Maker", "folder": "booth/Rusk", "files": ["rusk.zip"]},
                   {"store": "booth", "name": "Pollution", "creator": "Maker", "folder": "booth/Pollution",
                    "files": ["a.unitypackage", "b.zip"]}]
        before = build_index(root, catalog)
        self.assertEqual([a["name"] for a in before["assets"]], ["Rusk", "Pollution"])
        self.assertEqual(before["gone"], 0)

        shutil.rmtree(root / "booth/Rusk")               # deleted the whole folder
        (root / "booth/Pollution" / "b.zip").unlink()    # and one file of another
        after = build_index(root, catalog)
        self.assertEqual([a["name"] for a in after["assets"]], ["Pollution"], "Rusk is no longer shown")
        self.assertEqual(after["gone"], 1)
        pollution = after["assets"][0]
        self.assertEqual((pollution["id"], pollution["missing"]), (1, 1), "ids stay the catalog's")

        (root / "booth/Rusk").mkdir()                    # the folder is there, but empty: still gone
        self.assertEqual(build_index(root, catalog)["gone"], 1)


class DownloadsIndex(unittest.TestCase):
    """The downloads index is rebuilt outside its lock (review finding P-07): downloads never wait for it."""

    def setUp(self):
        from unittest import mock
        self.builds, self.started, self.release = 0, threading.Event(), threading.Event()
        self.release.set()

        def slow_build(root, catalog, libraries=None):
            self.builds += 1
            self.started.set()
            self.release.wait(10)
            return {"root": str(root), "assets": [{"id": self.builds, "tag_key": f"k{self.builds}"}], "status": {}}
        self.patches = [mock.patch.object(server, "build_index", slow_build),
                        mock.patch.object(server, "collect_catalog", lambda cfg, root: ([], None))]
        for p in self.patches:
            p.start()
        self.cfg = {**config.load_config(), "root": tempfile.mkdtemp()}
        self.srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)

    def tearDown(self):
        self.release.set()
        self.srv.server_close()
        for p in self.patches:
            p.stop()

    def rebuild_in_background(self):
        self.started.clear()
        self.release.clear()
        t = threading.Thread(target=self.srv.index, daemon=True)
        t.start()
        self.assertTrue(self.started.wait(5))
        return t

    def test_a_download_never_waits_for_a_rebuild(self):
        t = self.rebuild_in_background()
        start = time.time()
        self.srv.forget_index()
        self.assertLess(time.time() - start, 0.2)
        self.release.set()
        t.join(5)

    def test_the_library_page_gets_the_index_as_it_was(self):
        self.srv.index()
        self.srv.forget_index()
        t = self.rebuild_in_background()
        start = time.time()
        self.assertEqual(self.srv.index(stale_ok=True)["assets"][0]["id"], 1)
        self.assertLess(time.time() - start, 0.2)
        self.release.set()
        t.join(5)

    def test_one_rebuild_for_everyone_waiting(self):
        t = self.rebuild_in_background()
        results = []
        others = [threading.Thread(target=lambda: results.append(self.srv.index()["assets"][0]["id"])) for _ in range(5)]
        for o in others:
            o.start()
        time.sleep(0.2)
        self.release.set()
        for o in [t, *others]:
            o.join(5)
        self.assertEqual(self.builds, 1)
        self.assertEqual(results, [1] * 5)

    def test_a_change_during_a_rebuild_is_not_missed(self):
        t = self.rebuild_in_background()
        self.srv.forget_index()   # a download finishes while the index is being rebuilt
        self.release.set()
        t.join(5)
        self.assertEqual(self.srv.index()["assets"][0]["id"], 2, "rebuilt again for the new download")
        self.assertEqual(self.srv.index()["assets"][0]["id"], 2, "and then kept")
        self.assertEqual(self.srv.index(rescan=True)["assets"][0]["id"], 3, "a rescan always rebuilds")

    def test_a_failed_rebuild_never_leaves_anyone_waiting(self):
        from unittest import mock
        with mock.patch.object(server, "build_index", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.srv.index()
        self.assertEqual(self.srv.index()["assets"][0]["id"], 1)


class CompressedLists(unittest.TestCase):
    """The library and downloads lists are gzipped for a browser that accepts it, when they're large."""

    def setUp(self):
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": tempfile.mkdtemp(),
                                                       "setup_done": True}, lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, path, gzip_ok=True):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=30)
        headers = {"X-Hoard-Key": self.srv.key, "Cookie": f"hoard_key={self.srv.key}"}
        if gzip_ok:
            headers["Accept-Encoding"] = "gzip, deflate, br"
        c.request("GET", path, headers=headers)
        r = c.getresponse()
        return r, r.read()

    def test_large_lists(self):
        import gzip
        with self.srv.lib.lock:
            self.srv.lib.data["items"] = [library.item("booth", str(n), name=f"Item {n}", creator="Kitsu")
                                          for n in range(2000)]
        r, body = self.get("/api/library")
        self.assertEqual(r.getheader("Content-Encoding"), "gzip")
        self.assertEqual(len(json.loads(gzip.decompress(body))["items"]), 2000)
        r, body = self.get("/api/library", gzip_ok=False)
        self.assertIsNone(r.getheader("Content-Encoding"), "only when the browser accepts it")
        self.assertEqual(len(json.loads(body)["items"]), 2000)

    def test_small_replies_are_sent_as_they_are(self):
        r, body = self.get("/api/library")
        self.assertIsNone(r.getheader("Content-Encoding"))
        r, body = self.get("/api/status")
        self.assertIsNone(r.getheader("Content-Encoding"))


if __name__ == "__main__":
    unittest.main()


class RoutineCheck(unittest.TestCase):
    """Issue #113: one routine check, on a schedule, that reads your stores, checks your downloads and checks for
    updates, then asks which of what it found to download. Issue #110: anything you start goes first."""

    def setUp(self):
        from unittest import mock
        self.cfg = {**config.load_config(), "setup_done": True, "routine_hours": 24}
        self.started = []
        self.fake = mock.Mock(state={"running": False})
        self.fake.start = lambda task, stores, **kw: self.started.append((task, stores, kw)) or "started"
        self.schedule = jobs.Schedule(self.cfg, self.fake)
        self.schedule.not_before = 0
        jobs._routine_file().unlink(missing_ok=True)
        self.addCleanup(jobs._routine_file().unlink, missing_ok=True)
        patch = mock.patch.object(jobs, "reachable", lambda store: True)
        patch.start()
        self.addCleanup(patch.stop)

    def test_due_after_the_interval_from_the_last_one(self):
        now = time.time()
        self.assertTrue(self.schedule.tick(now))
        (task, stores, kw), = self.started
        self.assertEqual((task, kw), ("routine", {"scheduled": True, "queue": False}))
        self.assertNotIn("payhip", stores, "Payhip needs you there for its bot check")
        self.assertIn("booth", stores)
        jobs.save_routine(last=time.time())   # what the check itself does as it starts
        self.assertFalse(self.schedule.due(now + 23 * 3600))
        self.assertTrue(self.schedule.due(time.time() + 24 * 3600 + 1))

    def test_when_it_waits(self):
        now = time.time()
        for change, why in (({"routine_hours": 0}, "off"), ({"setup_done": False}, "before setup is done")):
            with self.subTest(why):
                self.assertFalse(jobs.Schedule({**self.cfg, **change}, self.fake).due(now + 3600), why)
        self.fake.state["running"] = True
        self.assertFalse(self.schedule.due(now), "another job is running")
        self.fake.state["running"] = False
        self.assertFalse(jobs.Schedule(self.cfg, self.fake).due(now), "not straight after Hoard starts")

    def test_the_two_old_settings_become_one(self):
        old = {k: v for k, v in self.cfg.items() if k != "routine_hours"}
        self.assertEqual(jobs.routine_hours({**old, "auto_sync_hours": 12}), 12, "a sync you turned on keeps its hours")
        self.assertEqual(jobs.routine_hours({**old, "auto_sync_hours": 0, "integrity_check_days": 30}), 0,
                         "off until you choose: it reads your stores, which the check of your downloads never did")
        self.assertEqual(jobs.routine_hours({**old, "routine_hours": None}), 0)
        self.assertEqual(jobs.routine_hours({**old, "routine_hours": 5}), 0, "not a choice")
        self.assertEqual(jobs.routine_hours({**old, "routine_hours": 168}), 168, "your choice")

    def test_offline_it_tries_again_later(self):
        from unittest import mock
        now = time.time()
        with mock.patch.object(jobs, "reachable", lambda store: False):
            self.assertFalse(self.schedule.tick(now))
        self.assertEqual(self.started, [])
        self.assertEqual(self.schedule.not_before, now + jobs.OFFLINE_RETRY)
        self.assertEqual(jobs.routine_record()["last"], 0, "a check that never started isn't counted")

    def wait_idle(self, runner):
        for _ in range(200):
            if not runner.state["running"] and runner.busy.acquire(blocking=False):
                runner.busy.release()
                return
            time.sleep(0.02)

    def test_it_reads_checks_and_asks(self):
        """It reads the stores, checks the downloads (new files not read yet), checks for updates, downloads nothing,
        and keeps how much it found for the pages to ask about."""
        from unittest import mock
        runner = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        runner.find_choices = lambda: {"new": 2, "updates": 1}
        steps = []
        with mock.patch.object(runner, "_refresh", lambda stores, **k: steps.append(("refresh", stores)) or []), \
                mock.patch.object(runner, "_verify", lambda stores, fresh=False: steps.append(("verify", fresh)) or "All 3 files are fine."), \
                mock.patch.object(runner, "_download", lambda stores, only, keys=None, check=False, **k: steps.append(("download", check))):
            self.assertEqual(runner.start("routine", ["booth", "gumroad"], scheduled=True), "started")
            self.wait_idle(runner)
        self.assertEqual(steps, [("refresh", ["booth", "gumroad"]), ("verify", True), ("download", True)],
                         "checking for updates only: nothing is downloaded")
        found = jobs.routine_record()["found"]
        self.assertEqual((found["new"], found["updates"]), (2, 1))
        self.assertIn("choose what to download", runner.history[-1]["message"])
        self.assertAlmostEqual(jobs.routine_record()["last"], time.time(), delta=5)
        jobs.save_routine(found=None)   # you looked
        self.assertIsNone(jobs.routine_record()["found"])

    def test_yours_go_first(self):
        """Issue #110: an automatic job running makes way for one you start, and carries on after it."""
        from unittest import mock
        runner = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        runner.history = []
        order, release = [], threading.Event()

        def refresh(stores, **_k):
            order.append("routine")
            for _ in range(200):   # an automatic check, reading the stores; Stop is noticed between steps
                if runner.stop.is_set() or release.is_set():
                    return []
                time.sleep(0.02)
            return []
        with mock.patch.object(runner, "_refresh", refresh), \
                mock.patch.object(runner, "_verify", lambda stores, fresh=False: "fine"), \
                mock.patch.object(runner, "_download", lambda stores, only, keys=None, check=False, **k: order.append(("download", check))):
            self.assertEqual(runner.start("routine", ["booth"], scheduled=True), "started")
            for _ in range(100):
                if order:
                    break
                time.sleep(0.02)
            self.assertEqual(runner.start("download", ["gumroad"], only="Mochi"), "queued")
            release.set()
            for _ in range(300):
                if len(order) >= 4 and not runner.state["running"]:
                    break
                time.sleep(0.02)
        self.assertEqual(order[:2], ["routine", ("download", False)], "yours, straight after it made way")
        self.assertEqual(order[2:], ["routine", ("download", True)], "then the automatic check, again")
        made_way = runner.history[0]
        self.assertEqual(made_way["outcome"], "stopped")
        self.assertTrue(made_way["message"].startswith("Made way for your task"), made_way["message"])

    def test_yours_wait_ahead_of_automatic_ones(self):
        from unittest import mock
        runner = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        gate = threading.Event()
        self.addCleanup(gate.set)
        with mock.patch.object(runner, "_download", lambda *a, **k: gate.wait(5)), \
                mock.patch.object(runner, "_refresh", lambda stores, **k: []), \
                mock.patch.object(runner, "_verify", lambda stores, fresh=False: "fine"):   # never the real stores
            runner.start("download", ["booth"], only="A")
            runner._queue.append({"task": "routine", "stores": ["booth"], "scheduled": True, "id": "q99", "label": "x", "queued": ""})
            runner.start("download", ["gumroad"], only="B")
            self.assertEqual([q["task"] for q in runner._queue], ["download", "routine"])
            gate.set()
            self.wait_idle(runner)

    def test_any_sync_counts(self):
        """A sync you start resets the clock too, and the job says whether it started by itself."""
        from unittest import mock
        runner = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        checked = threading.Event()   # the job waits here, so it can be looked at while it runs
        with mock.patch.object(runner, "_refresh", lambda *a, **k: checked.wait(10) and []), \
                mock.patch.object(runner, "_download"):
            self.assertTrue(runner.start("sync", ["booth"], scheduled=True))
            self.assertTrue(runner.state["scheduled"])
            checked.set()
            for _ in range(100):
                if not runner.state["running"] and runner.busy.acquire(blocking=False):
                    runner.busy.release()
                    break
                time.sleep(0.02)
        self.assertAlmostEqual(jobs.last_sync(), time.time(), delta=5)
        self.assertFalse(runner.state["scheduled"])

    def test_settings(self):
        cfg = config.load_config()
        change = server.apply_settings(cfg, {"display": {"text_size": 130, "pause_animations": 1, "reduce_motion": 0}})
        self.assertEqual(change, {"display": {"text_size": 130, "pause_animations": True, "reduce_motion": False}})
        for bad in (99, "130", True):
            with self.assertRaises(ValueError):
                server.apply_settings(cfg, {"display": {"text_size": bad}})
        # issue #112: the glow, and store colours you can tell apart, or choose
        change = server.apply_settings(cfg, {"display": {"glow": 0, "colours": "custom",
                                                         "custom_colours": {"booth": "#AABBCC", "itch": "#00ff00"}}})
        self.assertEqual(change, {"display": {"glow": False, "colours": "custom",
                                              "custom_colours": {"booth": "#aabbcc", "itch": "#00ff00"}}})
        for bad in ({"colours": "rainbow"}, {"custom_colours": {"booth": "red"}}, {"custom_colours": {"steam": "#000000"}},
                    {"custom_colours": {"booth": "#000000;x"}}, {"custom_colours": ["#000000"]}):
            with self.assertRaises(ValueError, msg=bad):
                server.apply_settings(cfg, {"display": bad})
        self.assertEqual({k: v for k, v in server.display_settings({}).items() if k in ("glow", "colours", "custom_colours")},
                         {"glow": True, "colours": "standard", "custom_colours": {}}, "the glow is on, standard colours")
        odd = server.display_settings({"display": {"glow": "no", "colours": 3, "custom_colours": {"booth": "url(x)", "gumroad": "#123456"}}})
        self.assertEqual((odd["glow"], odd["colours"], odd["custom_colours"]), (True, "standard", {"gumroad": "#123456"}))
        shown = server.public_settings({**cfg, "display": {"text_size": 7}, "routine_hours": 3})
        self.assertEqual((shown["display"]["text_size"], shown["routine_hours"]), (100, 0), "damaged values read as defaults")


class DownloadChoices(unittest.TestCase):
    """Issue #107: what Download new and Update all would get, to untick first; products always skipped, left out
    of every download and sync, unless chosen by name. Issue #106: several products chosen at once, as one job."""

    def setUp(self):
        from unittest import mock
        from hoard.asset_updates import AssetUpdates
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "download_skip": []}, lan=False)
        with self.srv.lib.lock:   # in memory only
            self.srv.lib.data["items"] = [
                library.item("booth", "1", name="Rusk", creator="Kitsu Studio"),
                library.item("gumroad", "2", name="Mochi", creator="Kitsu Studio"),
                library.item("gumroad", "3", name="Mochi", creator="Kitsu Studio"),   # a second copy: listed once
                library.item("gumroad", "4", name="Fox Base", creator="Someone"),
                library.item("payhip", "5", name="Paw Pack", creator="Someone")]   # listed, never downloaded
        on_disk = [{"tag_key": tags.tag_key("gumroad", "Fox Base"), "id": 1}]
        for patch in (mock.patch.object(self.srv, "index", lambda **_kw: {"assets": on_disk}),
                      mock.patch.object(server, "save_config")):
            patch.start()
            self.addCleanup(patch.stop)
        where = Path(tempfile.mkdtemp()) / "updates.json"
        AssetUpdates(where).save({"checked": {}, "items": {tags.tag_key("gumroad", "Fox Base"): {
            "store": "gumroad", "name": "Fox Base", "creator": "Someone", "files": [{"file": "Fox 1.1.zip", "kind": "changed"}]}}})
        real = server.AssetUpdates
        patch = mock.patch.object(server, "AssetUpdates", lambda: real(where))
        patch.start()
        self.addCleanup(patch.stop)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=20)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: self.srv.key})
        r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
        return r.status, data

    def test_what_would_download(self):
        status, c = self.call("GET", "/api/download-choices")
        self.assertEqual(status, 200)
        self.assertEqual([(e["store"], e["name"]) for e in c["new"]], [("booth", "Rusk"), ("gumroad", "Mochi")],
                         "nothing on disk yet, each product once; Payhip left out")
        self.assertEqual([(e["name"], e["files"]) for e in c["updates"]], [("Fox Base", 1)])
        self.assertEqual(c["skipped"], [])

    def test_always_skip(self):
        mochi = tags.tag_key("gumroad", "Mochi")
        self.assertEqual(self.call("POST", "/api/download-skip", {"keys": [mochi]}), (200, {"ok": True, "skipped": 1}))
        self.assertEqual(self.srv.cfg["download_skip"], [mochi])
        c = self.call("GET", "/api/download-choices")[1]
        self.assertEqual([e["name"] for e in c["new"]], ["Rusk"])
        self.assertEqual([(e["name"], e["creator"]) for e in c["skipped"]], [("Mochi", "Kitsu Studio")])
        self.assertEqual(jobs.download_skip(self.srv.cfg), {mochi})
        self.assertEqual(self.call("POST", "/api/download-skip", {"keys": [mochi], "skip": False})[1]["skipped"], 0)
        self.assertEqual(self.call("POST", "/api/download-skip", {"keys": ["no store"]})[0], 400)
        self.assertEqual(jobs.download_skip({"download_skip": ["booth:a", 7, "", "x" * 500]}), {"booth:a"})

    def test_skipping_in_a_download(self):
        from types import SimpleNamespace
        skip = {tags.tag_key("gumroad", "Mochi")}
        args = SimpleNamespace(only=None, keys=None, skip=skip)
        self.assertTrue(downloader.skip_product(args, "gumroad", "Mochi", "Kitsu Studio"))
        self.assertFalse(downloader.skip_product(args, "gumroad", "Fox Base", "Someone"))
        chosen = SimpleNamespace(only=None, keys=skip, skip=skip)   # chosen by name: downloaded all the same
        self.assertFalse(downloader.skip_product(chosen, "gumroad", "Mochi", "Kitsu Studio"))
        from unittest import mock
        seen = []
        self.srv.cfg["download_skip"] = sorted(skip)
        with mock.patch.object(downloader, "cmd_sync", lambda cfg, a: seen.append(a) or downloader.Report()):
            self.srv.jobs._download(["gumroad"], None)
            self.srv.jobs._download(["gumroad", "booth"], None, keys=["booth:rusk", "gumroad:mochi"])
        self.assertEqual(seen[0].skip, skip, "a download of everything new leaves it out")
        self.assertIsNone(seen[1].skip, "products chosen now are downloaded")
        self.assertEqual(seen[1].keys, {"booth:rusk", "gumroad:mochi"}, "several stores' products, as one job (#106)")


class TasksAPI(unittest.TestCase):
    """The Tasks window's server side: GET /api/tasks, taking jobs off the queue, and hidden products' names kept
    out of job logs while the hidden library is locked."""

    def setUp(self):
        from unittest import mock
        self.srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        self.srv.jobs.history = []   # only this test's
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.gate = threading.Event()
        self.addCleanup(self.gate.set)

        def fake(stores, only, keys=None, check=False, **_kw):
            self.srv.jobs._set(message=f"[Booth] Kitsu Studio / {only}", log=[f"    saved: {only}.zip"])
            self.gate.wait(10)
        patch = mock.patch.object(self.srv.jobs, "_download", fake)
        patch.start()
        self.addCleanup(patch.stop)
        where = Path(tempfile.mkdtemp()) / "tasks.json"
        saving = mock.patch.object(jobs, "tasks_file", lambda: where)
        saving.start()
        self.addCleanup(saving.stop)

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=20)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: self.srv.key})
        r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
        return r.status, data

    def test_queue_and_tasks(self):
        self.assertEqual(self.call("POST", "/api/download", {"stores": ["booth"], "only": "Rusk"}), (202, {"ok": True, "queued": False}))
        status, answer = self.call("POST", "/api/download", {"stores": ["gumroad"], "only": "Mochi"})
        self.assertEqual((status, answer), (202, {"ok": True, "queued": True}))
        self.assertEqual(self.call("POST", "/api/download", {"stores": ["gumroad"], "only": "Mochi"})[0], 409, "already waiting")
        status, tasks = self.call("GET", "/api/tasks")
        self.assertEqual(tasks["current"]["label"], 'Download: Booth ("Rusk")')
        self.assertEqual([q["label"] for q in tasks["queue"]], ['Download: Gumroad ("Mochi")'])
        self.assertEqual(self.call("POST", "/api/queue/remove", {"id": tasks["queue"][0]["id"]}), (200, {"ok": True}))
        self.gate.set()
        for _ in range(100):
            if not self.srv.jobs.state["running"]:
                break
            time.sleep(0.05)
        history = self.call("GET", "/api/tasks")[1]["history"]
        self.assertEqual([h["label"] for h in history], ['Download: Booth ("Rusk")'])
        self.assertEqual(self.call("POST", "/api/tasks/clear", {}), (200, {"ok": True}))
        self.assertEqual(self.call("GET", "/api/tasks")[1]["history"], [])

    def test_hidden_names_stay_out_of_job_logs(self):
        from hoard import marks, tags
        store = marks.MarkStore(Path(tempfile.mkdtemp()) / "marks.json")
        store.set_pin("4821")
        from unittest import mock
        patch = mock.patch.object(server, "MarkStore", lambda: store)
        patch.start()
        self.addCleanup(patch.stop)
        with self.srv.lib.lock:
            self.srv.lib.data["items"] = [library.item("booth", "1", name="Secret Suit", creator="Kitsu Studio")]
        store.change("hidden", {tags.tag_key("booth", "Secret Suit")}, True)
        self.srv.jobs.start("download", ["booth"], only="Secret Suit")
        for _ in range(100):
            if "Secret Suit" in (self.srv.jobs.state.get("message") or ""):
                break
            time.sleep(0.02)
        job = self.call("GET", "/api/status")[1]["job"]
        self.assertNotIn("Secret Suit", json.dumps(job))
        self.assertIn("a hidden item", job["message"])
        current = self.call("GET", "/api/tasks")[1]["current"]
        self.assertNotIn("Secret Suit", json.dumps(current["log"]) + current["message"])


class PageLayout(unittest.TestCase):
    """How you left the pages (windows' places, the sidebar, tile sizes) is kept in config.json: the pages' own
    storage goes with the server's address, which is new each time Hoard starts."""

    def test_only_what_makes_sense_is_kept(self):
        cfg = config.load_config()
        change = server.apply_settings(cfg, {"ui": {
            "windows": {"tagPanel": {"x": 120, "y": 80.5, "w": 500, "h": True, "z": 9}, "evil": {"x": 1},
                        "stores": {"x": 99999}},
            "sections": {"creators": False, "your-tags": True, "x" * 60: False, "suggested": "no"},
            "side_folded": True, "tile_size": 200, "dl_tile_size": 9000, "other": 1}})
        self.assertEqual(change["ui"], {"windows": {"tagPanel": {"x": 120, "y": 80.5, "w": 500}, "stores": {}},
                                        "sections": {"creators": False, "your-tags": True},
                                        "side_folded": True, "tile_size": 200})
        config.deep_merge(cfg, change)
        config.deep_merge(cfg, server.apply_settings(cfg, {"ui": {"windows": {"stores": {"x": 10, "y": 20}}}}))
        shown = server.ui_settings(cfg)
        self.assertEqual(shown["windows"], {"tagPanel": {"x": 120, "y": 80.5, "w": 500}, "stores": {"x": 10, "y": 20}},
                         "one window's move doesn't forget the others")
        self.assertEqual(server.ui_settings({"ui": "junk"}), {"windows": {}, "sections": {}})
        self.assertNotIn("ui", [k for k in server.JOB_SETTINGS], "saved even while a job runs")
