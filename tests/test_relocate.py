"""Changing where Hoard's folders are (hoard/relocate.py, issue #385): what each change would do, said first; Hoard's
own folder and its logs moved only as Hoard starts, checked before the old copy goes; never onto a network drive."""
import json
import os
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.isolation import IsolatedTestCase

from hoard import config, paths, relocate


class Moving(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(self.tmp / "AppData" / "Hoard")})   # (one of its own)
        env.start()
        self.addCleanup(env.stop)
        self.base = paths.base_dir()
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "config.json").write_text("{}")
        (self.base / "tags.json").write_text('{"x": 1}')
        (self.base / "sign-ins" / "booth").mkdir(parents=True)
        (self.base / "sign-ins" / "booth" / "Cookies").write_bytes(b"c" * 100)
        docs = mock.patch.object(paths, "documents_dir", lambda: self.tmp / "Documents")
        docs.start()
        self.addCleanup(docs.stop)
        import hoard.backup
        import hoard.diagnostics
        for module in (hoard.backup, hoard.diagnostics):
            p = mock.patch.object(module, "documents_dir", lambda: self.tmp / "Documents")
            p.start()
            self.addCleanup(p.stop)

    def srv(self):
        ran = []
        return SimpleNamespace(cfg={**config.load_config(), "root": str(self.tmp / "Downloads")}, ran=ran,
                               vpm=SimpleNamespace(settings=mock.Mock(side_effect=RuntimeError("no Projects")), forget=lambda: None),
                               save_settings=lambda: None, forget_index=lambda: None,
                               start_worker=lambda name, fn, *a: (ran.append(name), fn(*a)),
                               jobs=SimpleNamespace(state={"running": False, "queue": []}))

    def test_what_each_would_do_said_first(self):
        srv = self.srv()
        with self.assertRaisesRegex(ValueError, "full path"):
            relocate.plan(srv, "backups", "relative/folder")
        with self.assertRaisesRegex(ValueError, "already"):
            relocate.plan(srv, "data", str(self.base))
        with self.assertRaisesRegex(ValueError, "into itself"):
            relocate.plan(srv, "data", str(self.base / "inside"))
        with mock.patch.object(relocate, "on_network", lambda p: True):
            with self.assertRaisesRegex(ValueError, "network drive"):
                relocate.plan(srv, "data", str(self.tmp / "Elsewhere"))
            self.assertIn("network drive", relocate.plan(srv, "backups", str(self.tmp / "B"))["warning"], "a warning only")
        with self.assertRaisesRegex(ValueError, "your own user folder"):
            relocate.plan(srv, "signins", "/srv/elsewhere" if os.name != "nt" else "D:\\elsewhere")
        full = self.tmp / "Full"
        full.mkdir()
        (full / "x").write_text("x")
        with self.assertRaisesRegex(ValueError, "new folder, or an empty one"):
            relocate.plan(srv, "data", str(full))
        with self.assertRaisesRegex(ValueError, "isn't one of Hoard's folders"):
            relocate.plan(srv, "vcc", str(full))   # (Projects' settings can't be read: its folders aren't offered)
        srv.vpm.settings = lambda: SimpleNamespace(folder=str(self.tmp / "vcc"), default_project_path=lambda: None,
                                                   project_backup_path=lambda: None)
        with self.assertRaisesRegex(ValueError, "Creator Companion folder"):
            relocate.plan(srv, "vcc", str(full))
        (full / "settings.json").write_text("{}")
        self.assertEqual(relocate.plan(srv, "vcc", str(full))["how"], "point")
        p = relocate.plan(srv, "data", str(self.tmp / "Hoard data"))
        self.assertEqual((p["how"], p["files"]), ("move-later", 3))
        self.assertEqual(relocate.plan(srv, "downloads", str(self.tmp / "New downloads"))["how"], "library")

    def test_hoard_s_own_folder_moves_as_it_starts(self):
        srv = self.srv()
        to = self.tmp / "Hoard data"
        self.assertEqual(relocate.change(srv, "data", str(to)), {"how": "move-later", "to": str(to), "restart": True})
        self.assertEqual(paths.data_dir(), self.base, "nothing moved while Hoard runs")
        said = relocate.finish_pending(say=lambda s: None)
        self.assertIn("Moved", said)
        self.assertEqual(paths.data_dir(), to)
        self.assertEqual((to / "tags.json").read_text(), '{"x": 1}')
        self.assertEqual((to / "sign-ins" / "booth" / "Cookies").read_bytes(), b"c" * 100)
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["location.json"], "only the note of where it went")
        self.assertFalse((self.tmp / "Hoard data.part").exists())
        # and back where it started
        relocate.change(srv, "data", None)
        relocate.finish_pending(say=lambda s: None)
        self.assertEqual(paths.data_dir(), self.base)
        self.assertEqual((self.base / "tags.json").read_text(), '{"x": 1}')
        self.assertFalse(to.exists() and any(to.iterdir()))

    def test_never_while_another_hoard_runs(self):
        from hoard.app import InstanceLock
        srv = self.srv()
        to = self.tmp / "Hoard data"
        relocate.change(srv, "data", str(to))
        running = InstanceLock(self.base / "running.lock")
        self.assertTrue(running.acquire())
        try:
            self.assertIsNone(relocate.finish_pending(say=lambda s: None), "it waits")
            self.assertEqual(paths.data_dir(), self.base)
            self.assertTrue((self.base / paths.PENDING).is_file(), "still asked for")
        finally:
            running.release()
        self.assertIn("Moved", relocate.finish_pending(say=lambda s: None))
        self.assertEqual(paths.data_dir(), to)

    def test_an_old_copy_that_won_t_go_leaves_the_new_place_in_use(self):
        srv = self.srv()
        to = self.tmp / "Hoard data"
        relocate.change(srv, "data", str(to))
        real = Path.unlink

        def stuck(p, *a, **k):
            """tags.json can't be deleted (open elsewhere, say)."""
            if p.name == "tags.json":
                raise PermissionError("in use")
            return real(p, *a, **k)
        with mock.patch.object(Path, "unlink", stuck):
            said = relocate.finish_pending(say=lambda s: None)
        self.assertIn("1 old file couldn't be deleted", said)
        self.assertEqual(paths.data_dir(), to, "the copy is checked, so it's the one used")
        self.assertEqual((to / "tags.json").read_text(), '{"x": 1}')

    def test_a_move_that_can_t_be_made_leaves_it_where_it_was(self):
        to = self.tmp / "Taken"
        (paths.base_dir() / paths.PENDING).write_text(json.dumps({"what": "data", "to": str(to)}))
        to.mkdir()
        (to / "theirs.txt").write_text("not Hoard's")
        said = relocate.finish_pending(say=lambda s: None)
        self.assertIn("still where it was", said)
        self.assertEqual(paths.data_dir(), self.base)
        self.assertTrue((self.base / "tags.json").is_file())
        self.assertEqual((to / "theirs.txt").read_text(), "not Hoard's")
        self.assertIn("still where it was", json.loads((self.base / "move-failed.json").read_text())["said"])
        self.assertFalse((self.base / paths.PENDING).exists(), "tried once")

    def test_backups_used_and_moved_now(self):
        from hoard.backup import backups_dir
        srv = self.srv()
        old = backups_dir()
        old.mkdir(parents=True)
        (old / "a.hoard-backup").write_text("a")
        to = self.tmp / "Backups elsewhere"
        done = relocate.change(srv, "backups", str(to), move=True)
        self.assertEqual((done["how"], done["moving"]), ("move-now", True))
        self.assertEqual(backups_dir(), to)
        self.assertEqual((to / "a.hoard-backup").read_text(), "a")
        self.assertFalse((old / "a.hoard-backup").exists())
        relocate.change(srv, "backups", None)
        self.assertEqual(backups_dir(), old)

    def test_the_downloads_folder_keeps_the_old_one_as_a_library(self):
        srv = self.srv()
        old = Path(srv.cfg["root"])
        old.mkdir(parents=True)
        (old / "Booth").mkdir()
        done = relocate.change(srv, "downloads", str(self.tmp / "New downloads"))
        self.assertEqual(srv.cfg["root"], str(self.tmp / "New downloads"))
        self.assertIn(str(old), srv.cfg["library_folders"], "what's there is still found")
        self.assertEqual(done["kept"], str(old))


class OnTheNetwork(IsolatedTestCase):
    def test_network_shares(self):
        self.assertTrue(paths.on_network("//server/share/Hoard"))
        self.assertTrue(paths.on_network("\\\\server\\share\\Hoard"))
        with mock.patch.object(paths, "_mounts", lambda: [("/", "ext4"), ("/mnt/nas", "cifs"), ("/mnt/nas/local", "ext4")]), \
                mock.patch("os.path.realpath", lambda p: p), mock.patch.object(paths.sys, "platform", "linux"):
            self.assertTrue(paths.on_network("/mnt/nas/Hoard"))
            self.assertFalse(paths.on_network("/mnt/nas/local/Hoard"), "the closest mount decides")
            self.assertFalse(paths.on_network("/home/me/Hoard"))
            self.assertFalse(paths.on_network("/mnt/nasty"), "not a mount it's only named like")
