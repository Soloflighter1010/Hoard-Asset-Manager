"""Local items listed where they are, on a drive or a network share (a NAS) that doesn't answer: Hoard looks at each
folder once, all at once, with a short wait, and lists the rest of the library without waiting on them (issue #368; #366 was the
rescue for a library that stopped). Nothing here waits on a real network share: one is played by a folder whose look
never answers, and anything else that would read from it is caught."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hoard import config, downloader, downloads, local, needs, reach, server, storage  # noqa: E402

LINKED = 64   # as many as the library that stopped had


class _Unplugged:
    """A NAS that's switched off: a look at its folders gets no answer (until the test ends), and anything else that
    reads from it is noted (and fails at once, so a test that reads from it fails rather than waits)."""

    def __init__(self, test, nas: Path):
        self.nas, self.touched, self.release = str(nas), [], threading.Event()
        real_there, real_stat, real_lstat = reach._there, os.stat, os.lstat

        def on_nas(p) -> bool:
            try:
                return not isinstance(p, int) and os.fspath(p).startswith(self.nas)
            except TypeError:
                return False

        def there(folder):
            if on_nas(folder):
                self.release.wait(30)
                return "away"
            return real_there(folder)

        def stat(p, *a, **k):
            if on_nas(p):
                self.touched.append(os.fspath(p))
                raise TimeoutError("the share didn't answer")
            return real_stat(p, *a, **k)

        def lstat(p, *a, **k):
            if on_nas(p):
                self.touched.append(os.fspath(p))
                raise TimeoutError("the share didn't answer")
            return real_lstat(p, *a, **k)

        test.addCleanup(self.release.set)
        self.patches = [mock.patch.object(reach, "_there", there), mock.patch.object(os, "stat", stat),
                        mock.patch.object(os, "lstat", lstat), mock.patch.object(reach, "WAIT", 0.3)]
        for p in self.patches:
            p.start()
            test.addCleanup(p.stop)

    def plug_in(self) -> None:
        """Switched on again."""
        self.release.set()
        for p in self.patches:
            p.stop()


class AwayFolders(IsolatedTestCase):

    def setUp(self):
        reach.forget()
        self.addCleanup(reach.forget)
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "Hoard"
        self.root.mkdir()
        share = Path(tempfile.mkdtemp()).resolve()   # (somewhere of its own: not beside the downloads folder)
        self.addCleanup(shutil.rmtree, share, True)
        self.nas = share / "NAS"
        self.cfg = {**config.load_config(), "root": str(self.root)}
        self.addCleanup(storage.remove, downloader.integrity_file(), missing_ok=True)

    def link_many(self, n: int = LINKED) -> list[dict]:
        recs = []
        for i in range(n):
            src = self.nas / f"Outfit {i:02d}"
            src.mkdir(parents=True)
            (src / "Outfit.unitypackage").write_bytes(b"pkg")
            recs.append(local.add(self.cfg, self.root, str(src), copy=False, catalog=False))
        mine = self.base / "Mine"
        mine.mkdir()
        (mine / "Mine.unitypackage").write_bytes(b"mine")
        local.add(self.cfg, self.root, str(mine), copy=True)   # one copied in, on a drive that's connected
        return recs

    def catalog(self):
        return downloader.collect_catalog(self.cfg, self.root)[0]

    # ---------------------------------------------------------------------------- the look

    def test_a_folder_that_doesnt_answer_is_away_and_isnt_waited_on_again(self):
        self.nas.mkdir()
        _Unplugged(self, self.nas)
        t = time.monotonic()
        self.assertEqual(reach.away([str(self.nas)]), {str(self.nas)})
        self.assertLess(time.monotonic() - t, 2, "waited only the short wait")
        t = time.monotonic()
        self.assertEqual(reach.away([str(self.nas)]), {str(self.nas)}, "still waiting: still away")
        self.assertLess(time.monotonic() - t, 0.2, "and not waited on again")

    def test_waited_out_once_is_away_at_once_however_little_the_clock_moved(self):
        """Windows' clock moves in steps of about 16 ms: a second ask just after the first had waited it out could
        read as less than the wait since, and wait again."""
        self.nas.mkdir()
        _Unplugged(self, self.nas)
        with mock.patch.object(reach, "_now", lambda: 1000.0):   # (a clock that doesn't move at all)
            self.assertEqual(reach.away([str(self.nas)]), {str(self.nas)})
            t = time.monotonic()
            self.assertEqual(reach.away([str(self.nas)]), {str(self.nas)})
            self.assertLess(time.monotonic() - t, 0.1, "not waited on again")

    def test_folders_that_answer_arent_away(self):
        gone = self.base / "Not here"
        self.assertEqual(reach.away([str(self.base), str(gone)]), set(), "there, or not there, on a drive that answers")
        self.assertFalse(reach.is_away(str(self.base)))
        self.assertFalse(reach.is_away(None))

    def test_a_slow_no_is_away_and_a_slow_yes_is_there(self):
        slow = {str(self.base / "slow no"): "gone", str(self.base / "slow yes"): "there"}

        def there(folder):
            time.sleep(0.3)
            return slow[folder]
        with mock.patch.object(reach, "_there", there), mock.patch.object(reach, "WAIT", 0.1):
            self.assertEqual(reach.away(slow, wait=0.05), set(slow), "neither answered in time")
            time.sleep(0.5)   # (both have answered now)
            self.assertEqual(reach.away(slow, wait=0.05), {str(self.base / "slow no")},
                             "one that took that long to say no is on a drive that doesn't answer")

    def test_each_folder_is_looked_at_once_side_by_side(self):
        folders = [str(self.base / f"f{i}") for i in range(20)]
        looked, lock = [], threading.Lock()

        def there(folder):
            with lock:
                looked.append(folder)
            time.sleep(0.2)
            return "gone"
        with mock.patch.object(reach, "_there", there):
            t = time.monotonic()
            reach.away(folders + folders, wait=2)
            self.assertLess(time.monotonic() - t, 1.5, "side by side, not one after another")
        self.assertEqual(sorted(looked), sorted(folders), "each once")

    def test_no_more_than_so_many_looks_at_once(self):
        for _ in range(200):   # (looks another test started have finished)
            if not reach._looking:
                break
            time.sleep(0.02)
        nas = self.nas
        nas.mkdir()
        unplugged = _Unplugged(self, nas)
        many = [str(nas / f"f{i}") for i in range(reach.MOST * 3)]
        self.assertEqual(reach.away(many), set(many))
        self.assertEqual(reach._looking, reach.MOST, "the rest wait their turn (and are away meanwhile)")
        self.assertEqual(reach.away(many, wait=0), set(many), "still away, and not asked about again")
        unplugged.release.set()
        for _ in range(200):
            if not reach._looking:
                break
            time.sleep(0.02)
        self.assertEqual(reach._looking, 0, "each looked at in turn, and the threads gone")

    def test_a_drive_that_isnt_there_is_away_however_fast_it_says_so(self):
        folder = os.path.join(os.path.abspath(os.sep), "Volumes", "Unplugged", "Outfits")
        with mock.patch.object(reach.os.path, "isdir", lambda p: False):
            self.assertEqual(reach._there(folder), "away", "an unplugged drive (E:\\ on Windows)")
        anchor = Path(folder).anchor
        with mock.patch.object(reach.os.path, "isdir", lambda p: p == anchor):
            self.assertEqual(reach._there(folder), "gone", "a folder that's gone from a drive that's there")

    # ---------------------------------------------------------------------------- what reads the library

    def test_the_library_is_listed_without_waiting_on_them(self):
        self.link_many()
        catalog = self.catalog()
        nas = _Unplugged(self, self.nas)
        t = time.monotonic()
        index = downloads.build_index(self.root, catalog)
        self.assertLess(time.monotonic() - t, 5, "a few seconds at most, not a wait for each")
        self.assertEqual(nas.touched, [], "nothing on the share was looked at")
        linked = [a for a in index["assets"] if a["linked"]]
        self.assertEqual(len(linked), LINKED, "each still listed: not taken for deleted")
        self.assertTrue(all(a["away"] and not a["folder_gone"] for a in linked))
        self.assertTrue(all(f["missing"] and f["size"] is None for a in linked for f in a["files"]))
        [mine] = [a for a in index["assets"] if not a["linked"]]
        self.assertFalse(mine["away"])
        self.assertEqual(mine["files"][0]["size"], 4, "the rest of the library as it is")
        problems = downloads.problems(index["assets"])
        self.assertEqual([p["kind"] for each in problems.values() for p in each], ["away"] * LINKED,
                         "each marked as on a drive that isn't connected, nothing else")

    def test_back_again_they_read_as_before(self):
        self.link_many(3)
        catalog = self.catalog()
        nas = _Unplugged(self, self.nas)
        self.assertTrue(all(a["away"] for a in downloads.build_index(self.root, catalog)["assets"] if a["linked"]))
        nas.plug_in()
        for _ in range(100):   # (the looks that were waiting answer now)
            if not reach._asking:
                break
            time.sleep(0.02)
        with mock.patch.object(reach, "KEEP", 0):   # (what it said while off is forgotten after a while)
            index = downloads.build_index(self.root, catalog)
        self.assertTrue(all(not a["away"] and a["files"][0]["size"] == 3 for a in index["assets"] if a["linked"]))

    def test_what_each_product_needs_isnt_read_from_them(self):
        self.link_many(4)
        catalog = self.catalog()
        index = needs.NeedsIndex(self.base / "needs.json")
        index.files["elsewhere"] = {}   # (something was read before)
        nas = _Unplugged(self, self.nas)
        needs.add_to_catalog(self.root, catalog, index)
        self.assertEqual(nas.touched, [])
        assets = downloads.build_index(self.root, catalog)["assets"]
        kept = needs._kept(assets, needs.package_files(assets))
        self.assertEqual(len([p for p in kept if p.startswith(str(self.nas))]), 4,
                         "what was read of their packages is kept for when they're back")

    def test_adding_more_doesnt_wait_on_them(self):
        self.link_many(8)
        copied = self.nas / "Copied in"
        copied.mkdir()
        (copied / "Hat.unitypackage").write_bytes(b"hat")
        local.add(self.cfg, self.root, str(copied), copy=True, catalog=False)   # (copied from it, while it was on)
        nas = _Unplugged(self, self.nas)
        t = time.monotonic()
        added = local.added_sources(self.root)
        self.assertLess(time.monotonic() - t, 5)
        self.assertEqual(nas.touched, [])
        self.assertEqual(len([a for a in added if a.startswith(str(self.nas))]), 9, "taken as they were recorded")

    def test_a_rescan_says_its_drive_isnt_connected(self):
        [rec] = self.link_many(1)
        nas = _Unplugged(self, self.nas)
        with self.assertRaisesRegex(ValueError, "isn't connected now"):
            local.rescan(self.cfg, self.root, rec["folder"].split("/")[1])
        self.assertEqual(nas.touched, [])

    def test_open_folder_and_its_files_arent_asked_for(self):
        [rec] = self.link_many(1)
        nas = _Unplugged(self, self.nas)
        self.assertIsNone(server.open_target(self.cfg, f"Local/{rec['folder']}"))
        self.assertIsNone(server.open_target(self.cfg, f"Local/{rec['folder']}/Outfit.unitypackage"))
        self.assertEqual(nas.touched, [])

    def test_the_list_is_built_again_once_a_drive_is_back(self):
        self.link_many(2)
        nas = _Unplugged(self, self.nas)
        srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)
        self.addCleanup(srv.server_close)
        t = time.monotonic()
        self.assertTrue(all(a["away"] for a in srv.index()["assets"] if a["linked"]))
        self.assertIs(srv.index(), srv.index(), "kept while the drive is away")
        self.assertLess(time.monotonic() - t, 5, "and never waited on again")
        nas.plug_in()
        for _ in range(100):   # (the looks that were waiting answer now)
            if not reach._asking:
                break
            time.sleep(0.02)
        with mock.patch.object(reach, "KEEP", 5):
            time.sleep(0.1)
            reach.forget()    # (what it said while it was off is forgotten after a while)
            t = time.monotonic()
            srv.index(stale_ok=True)   # (as the library page asks: without waiting, so the answer is known next time)
            srv.index(stale_ok=True)   # (built again behind it)
            self.assertLess(time.monotonic() - t, 1, "the library page isn't kept waiting")
            for _ in range(100):
                back = [a for a in srv.index(stale_ok=True)["assets"] if a["linked"]]
                if back and not any(a["away"] for a in back):
                    break
                time.sleep(0.05)
        self.assertTrue(back and all(not a["away"] and a["files"][0]["size"] == 3 for a in back), "built again")
