"""The Local sync folder (hoard/localsync.py, issue #388): what's put in it is added to Local by itself (folders listed
where they are, files copied in), what's too big is said and not read again, what's taken out is marked, not removed;
and it's never a network drive or inside the library."""
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import threading

from tests.isolation import IsolatedTestCase

from hoard import config, local, localsync
from hoard.downloader import Manifest


class SyncFolder(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "Downloads"
        self.root.mkdir()
        self.cfg = {**config.load_config(), "root": str(self.root)}
        sync = self.sync = self.tmp / "Sync"
        (sync / "Hoodie").mkdir(parents=True)
        (sync / "Hoodie" / "hoodie.unitypackage").write_bytes(b"package")
        (sync / "tex.png").write_bytes(b"\x89PNG")
        with open(sync / "big.bin", "wb") as f:   # (sparse: as big as it says, without the disk it'd take)
            f.truncate(localsync.MAX_FILE + 1)
        (sync / "Huge").mkdir()
        with open(sync / "Huge" / "part.bin", "wb") as f:
            f.truncate(localsync.MAX_FOLDER + 1)
        (sync / ".DS_Store").write_bytes(b"x")
        self.cfg["local_sync"] = str(localsync.check_folder(self.cfg, str(sync)))

    def records(self) -> dict:
        return {rec["name"]: rec for rec in Manifest(local.local_dir(self.root)).assets.values()}

    def test_added_by_themselves_and_not_read_twice(self):
        done = localsync.scan(self.cfg, self.root)
        self.assertEqual(sorted(done["added"]), ["Hoodie", "tex.png"])
        self.assertEqual(sorted((x["name"], x["why"]) for x in done["skipped"]),
                         [("Huge", "It's over 1 GB."), ("big.bin", "It's over 100 MB.")])
        recs = self.records()
        self.assertEqual(recs["Hoodie"]["location"], str(self.sync / "Hoodie"), "a folder: listed where it is")
        self.assertNotIn("location", recs["tex"], "a file: copied in")
        with mock.patch.object(localsync, "_folder_size", side_effect=AssertionError("measured again")):
            again = localsync.scan(self.cfg, self.root)
        self.assertEqual(again["added"], [])
        self.assertEqual(len(again["skipped"]), 2, "still said, without being measured again")
        self.assertEqual(len(self.records()), 2, "nothing added twice")
        self.assertEqual(len(localsync.view(self.cfg)["skipped"]), 2)

    def test_a_listings_stale_times_dont_make_it_measure_again(self):
        """On Windows a folder's listing keeps its entries' times as they were, and NTFS brings them up to date late:
        what was too big is judged by the thing itself, so it isn't measured again for a listing's stale copy."""
        real = localsync.os.scandir
        ticks = iter(range(10 ** 6))

        class Stale:
            """A listing's entry whose stat() is a different, made-up time each time it's asked."""
            def __init__(self, e):
                self._e, self.name, self.path = e, e.name, e.path

            def stat(self, follow_symlinks=True):
                st = self._e.stat(follow_symlinks=follow_symlinks)
                return type("S", (), {"st_mtime_ns": next(ticks), "st_size": st.st_size, "st_mode": st.st_mode})()

            def __getattr__(self, name):
                return getattr(self._e, name)

        def listing(p):
            """The sync folder's own listing, stale; any other (os.walk's, in measuring) as it is."""
            return [Stale(e) for e in real(p)] if str(p) == str(self.sync) else real(p)
        with mock.patch.object(localsync.os, "scandir", listing):
            localsync.scan(self.cfg, self.root)
            with mock.patch.object(localsync, "_folder_size", side_effect=AssertionError("measured again")):
                self.assertEqual(len(localsync.scan(self.cfg, self.root)["skipped"]), 2)

    def test_taken_out_is_marked_not_removed(self):
        localsync.scan(self.cfg, self.root)
        shutil.rmtree(self.sync / "Hoodie")
        done = localsync.scan(self.cfg, self.root)
        self.assertEqual(done["gone"], 1)
        recs = self.records()
        self.assertTrue(recs["Hoodie"].get("sync_gone"), "marked")
        self.assertIn("tex", recs, "the rest as they were")
        (self.sync / "Hoodie").mkdir()
        (self.sync / "Hoodie" / "hoodie.unitypackage").write_bytes(b"package")
        localsync.scan(self.cfg, self.root)
        self.assertNotIn("sync_gone", self.records()["Hoodie"], "back again: the mark goes")

    def test_only_a_folder_on_this_computer_outside_the_library(self):
        with self.assertRaisesRegex(ValueError, "full path"):
            localsync.check_folder(self.cfg, "Sync")
        with mock.patch.object(localsync, "on_network", lambda p: True):
            with self.assertRaisesRegex(ValueError, "network share or a NAS"):
                localsync.check_folder(self.cfg, str(self.sync))
        with mock.patch.object(localsync.reach, "away", lambda folders, wait=0: set(folders)):
            with self.assertRaisesRegex(ValueError, "doesn't answer"):
                localsync.check_folder(self.cfg, str(self.sync))
        with self.assertRaisesRegex(ValueError, "isn't there"):
            localsync.check_folder(self.cfg, str(self.root / "Inside"))
        (self.root / "Inside").mkdir()
        with self.assertRaisesRegex(ValueError, "inside your downloads"):
            localsync.check_folder(self.cfg, str(self.root / "Inside"))
        with self.assertRaisesRegex(ValueError, "inside your downloads"):
            localsync.check_folder(self.cfg, str(self.tmp))   # (holding the downloads folder)
        from hoard.paths import data_dir
        data_dir().mkdir(parents=True, exist_ok=True)
        with self.assertRaisesRegex(ValueError, "Hoard's own folder"):
            localsync.check_folder(self.cfg, str(data_dir()))
        with self.assertRaisesRegex(ValueError, "Hoard's own folder"):
            localsync.check_folder(self.cfg, str(data_dir().parent))

    def test_never_while_a_job_uses_local(self):
        busy = threading.Lock()
        busy.acquire()
        srv = SimpleNamespace(cfg=self.cfg, jobs=SimpleNamespace(busy=busy, kick=lambda: None), forget_index=lambda: None)
        self.assertIsNone(localsync.tick(srv))
        self.assertEqual(self.records(), {})
        busy.release()
        self.assertEqual(sorted(localsync.tick(srv)["added"]), ["Hoodie", "tex.png"])
