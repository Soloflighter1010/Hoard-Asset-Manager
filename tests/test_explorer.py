"""Hoard's Local sync folder in Windows' File Explorer (hoard/explorer.py, issue #410): its icon, put on and taken off
as it was; Hoard's right-click options, for this account only and in its language; what the menu asks for, checked,
and done (a file copied into the sync folder, never over one; a folder added to Local); a second start handing that
to the Hoard that's running; and Hoard's page at Local, saying what it did. Windows itself is a stand-in here (its
file attributes and registry): the real calls are in explorer.Windows."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.isolation import IsolatedTestCase
from hoard import config, explorer, localsync

READONLY, HIDDEN, SYSTEM = explorer.FILE_ATTRIBUTE_READONLY, explorer.FILE_ATTRIBUTE_HIDDEN, explorer.FILE_ATTRIBUTE_SYSTEM


class _Key:
    """A registry key opened by the stand-in (a context manager, as winreg's are)."""

    def __init__(self, reg, path):
        self.reg, self.path = reg, path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeRegistry:
    """The parts of winreg Hoard uses, over a dict of keys (named without regard to case, as the registry's are)."""
    HKEY_CURRENT_USER, REG_SZ, KEY_ALL_ACCESS = "HKCU", 1, 0xF003F

    def __init__(self):
        self.keys: dict[str, dict] = {}

    def _name(self, root, path):
        return f"{root}\\{path}".lower()

    def CreateKey(self, root, path):
        parts = path.split("\\")
        for n in range(1, len(parts) + 1):
            self.keys.setdefault(self._name(root, "\\".join(parts[:n])), {})
        return _Key(self, self._name(root, path))

    def OpenKey(self, root, path, reserved=0, access=0):
        name = self._name(root, path)
        if name not in self.keys:
            raise FileNotFoundError(path)
        return _Key(self, name)

    def SetValueEx(self, key, name, reserved, kind, value):
        self.keys[key.path][name] = value

    def DeleteValue(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(name)
        del self.keys[key.path][name]

    def _children(self, name):
        return sorted(k for k in self.keys if k.startswith(name + "\\") and "\\" not in k[len(name) + 1:])

    def EnumKey(self, key, index):
        children = self._children(key.path)
        if index >= len(children):
            raise OSError("no more")
        return children[index][len(key.path) + 1:]

    def DeleteKey(self, root, path):
        name = self._name(root, path)
        if name not in self.keys:
            raise FileNotFoundError(path)
        if self._children(name):
            raise PermissionError("it has keys under it")
        del self.keys[name]

    def value(self, path, name):
        """(For the tests.) A value, or None."""
        return self.keys.get(self._name("HKCU", path), {}).get(name)


class FakeWindows(explorer.Windows):
    """Windows, as far as Hoard asks it: files' attributes, Explorer told, the registry, and its language."""

    def __init__(self, language="en-US"):
        self.attrs: dict[str, int] = {}
        self.reg = FakeRegistry()
        self.told: list[str] = []
        self.language = language

    def attributes(self, path):
        p = Path(path)
        return self.attrs.get(str(p), 0x10 if p.is_dir() else 0x80) if p.exists() else None

    def set_attributes(self, path, value):
        self.attrs[str(Path(path))] = value

    def changed(self, folder):
        self.told.append(str(folder))

    def registry(self):
        return self.reg

    def long_path(self, path):
        return str(path).replace("HOARDS~1", "Hoard sync")   # (a short name, written out as Explorer shows it)

    def ui_language(self):
        return self.language


class TheIcon(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.folder = self.tmp / "Sync"
        self.folder.mkdir()
        self.win = FakeWindows()

    def test_on_and_off_as_it_was(self):
        self.assertTrue(explorer.mark(self.folder, self.win))
        ini, icon = self.folder / "desktop.ini", self.folder / ".hoard-folder.ico"
        self.assertTrue(ini.read_text("utf-8").startswith(explorer.MARK))
        self.assertIn("IconResource=.hoard-folder.ico,0", ini.read_text("utf-8"))
        self.assertEqual(icon.read_bytes(), explorer.ICON_SOURCE.read_bytes())
        self.assertEqual(self.win.attrs[str(ini)], HIDDEN | SYSTEM)
        self.assertEqual(self.win.attrs[str(icon)], HIDDEN | SYSTEM)
        self.assertTrue(self.win.attrs[str(self.folder)] & READONLY, "Explorer reads it only on a read-only folder")
        self.assertEqual(self.win.told, [str(self.folder)], "shown at once")
        self.assertTrue(explorer.mark(self.folder, self.win), "again: written over, as Hoard's")
        self.assertIn(explorer.READONLY_WAS + "0", ini.read_text("utf-8"), "still: it wasn't read-only before Hoard")
        self.assertTrue(explorer.unmark(self.folder, self.win))
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), [])
        self.assertFalse(self.win.attrs[str(self.folder)] & READONLY, "as it was")

    def test_a_folder_read_only_before_stays_so(self):
        self.win.attrs[str(self.folder)] = 0x10 | READONLY
        self.assertTrue(explorer.mark(self.folder, self.win))
        self.assertTrue(explorer.unmark(self.folder, self.win))
        self.assertTrue(self.win.attrs[str(self.folder)] & READONLY)

    def test_someone_elses_desktop_ini_is_left(self):
        theirs = "[.ShellClassInfo]\r\nIconResource=C:\\theirs.ico,0\r\n"
        (self.folder / "desktop.ini").write_text(theirs, encoding="utf-8", newline="")
        self.assertFalse(explorer.mark(self.folder, self.win))
        self.assertFalse(explorer.unmark(self.folder, self.win))
        self.assertEqual((self.folder / "desktop.ini").read_bytes(), theirs.encode())
        self.assertFalse((self.folder / ".hoard-folder.ico").exists())
        self.assertNotIn(str(self.folder), self.win.attrs)

    def test_never_through_a_link(self):
        if not hasattr(os, "symlink"):
            self.skipTest("no symlinks here")
        elsewhere = self.tmp / "Elsewhere"
        elsewhere.mkdir()
        try:
            (self.tmp / "Linked").symlink_to(elsewhere, target_is_directory=True)
            (self.folder / "desktop.ini").symlink_to(self.tmp / "planted.ini")
        except OSError:
            self.skipTest("needs symlinks")
        self.assertFalse(explorer.mark(self.tmp / "Linked", self.win))
        self.assertFalse(explorer.mark(self.folder, self.win), "a desktop.ini that's a link isn't Hoard's")
        self.assertFalse((self.tmp / "planted.ini").exists())

    def test_the_sync_folders_look_leaves_them_out(self):
        explorer.mark(self.folder, self.win)
        (self.folder / "tex.png").write_bytes(b"\x89PNG")
        root = self.tmp / "Downloads"
        root.mkdir()
        cfg = {**config.load_config(), "root": str(root)}
        cfg["local_sync"] = str(localsync.check_folder(cfg, str(self.folder)))
        self.assertEqual(localsync.scan(cfg, root)["added"], ["tex.png"], "never desktop.ini or Hoard's icon")


class TheMenu(IsolatedTestCase):
    EXE = r"C:\Users\you\AppData\Local\Hoard\Hoard.exe"
    SYNC = r"D:\Hoard sync"

    def test_for_this_account_in_its_language(self):
        win = FakeWindows()
        self.assertTrue(explorer.register(self.EXE, self.SYNC, win, "ja"))
        add = r"Software\Classes\*\shell\Hoard.Add"
        self.assertEqual(win.reg.value(add, "MUIVerb"), "Hoardに追加")
        self.assertEqual(win.reg.value(add + r"\command", ""), f'"{self.EXE}" --hoard-add "%1"')
        self.assertIsNone(win.reg.value(add, "AppliesTo"), "on any file")
        self.assertEqual(win.reg.value(add, "Icon"), f'"{self.EXE}",0')
        sync = r"Software\Classes\Directory\Background\shell\Hoard.SyncNow"
        self.assertEqual(win.reg.value(sync, "AppliesTo"), f'System.ItemPathDisplay:="{self.SYNC}"', "the sync folder's only")
        self.assertEqual(win.reg.value(sync + r"\command", ""), f'"{self.EXE}" --hoard-sync-now "%V"', "with the folder")
        self.assertTrue(all(k.startswith("hkcu\\") for k in win.reg.keys), "this account's, never the whole computer's")
        explorer.unregister(win)
        self.assertEqual([k for k in win.reg.keys if "hoard." in k], [], "every key, and what's under it")

    def test_by_the_name_explorer_shows(self):
        win = FakeWindows()
        self.assertTrue(explorer.register(self.EXE, r"D:\HOARDS~1", win))
        self.assertEqual(win.reg.value(r"Software\Classes\Directory\shell\Hoard.SyncNow", "AppliesTo"),
                         'System.ItemPathDisplay:="D:\\Hoard sync"', "a short (8.3) name written out long")

    def test_a_quote_in_a_path_is_never_written(self):
        win = FakeWindows()
        self.assertFalse(explorer.register('C:\\Hoard" --evil "', self.SYNC, win))
        self.assertFalse(explorer.register(self.EXE, 'D:\\a" OR "', win))
        self.assertEqual(win.reg.keys, {})

    def test_the_language_is_hoards_or_windows(self):
        win = FakeWindows("ko-KR")
        self.assertEqual(explorer.language({"display": {"language": "ja"}}, win), "ja")
        self.assertEqual(explorer.language({"display": {"language": "system"}}, win), "ko")
        self.assertEqual(explorer.language({}, FakeWindows("de-DE")), "en")


class Applying(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.a, self.b = self.tmp / "A", self.tmp / "B"
        self.a.mkdir()
        self.b.mkdir()
        self.win = FakeWindows()
        self.exe = str(self.tmp / "Hoard.exe")

    def test_what_settings_say(self):
        cfg = {"local_sync": str(self.a)}
        self.assertEqual(explorer.apply(cfg, self.exe, win=self.win), {"icon": True, "menu": True})
        self.assertEqual(self.win.reg.value(explorer.NOTE_KEY, "SyncFolder"), str(self.a), "noted for the uninstaller")
        cfg["local_sync"] = str(self.b)   # another sync folder: the icon moves
        self.assertEqual(explorer.apply(cfg, self.exe, str(self.a), self.win), {"icon": True, "menu": True})
        self.assertFalse((self.a / "desktop.ini").exists())
        self.assertTrue((self.b / "desktop.ini").exists())
        self.assertEqual(self.win.reg.value(explorer.NOTE_KEY, "SyncFolder"), str(self.b))
        self.assertEqual(explorer.apply(cfg, None, win=self.win), {"icon": True, "menu": False})
        self.assertNotEqual([k for k in self.win.reg.keys if "hoard." in k], [],
                            "a Hoard without its window knows no program: it leaves the menu as it is")
        cfg["explorer"] = False   # Settings: not in File Explorer
        self.assertEqual(explorer.apply(cfg, self.exe, win=self.win), {"icon": False, "menu": False})
        self.assertFalse((self.b / "desktop.ini").exists())
        self.assertEqual([k for k in self.win.reg.keys if "hoard" in k], [], "nothing of Hoard's left")
        cfg.update(explorer=True, local_sync="")   # the sync folder off
        explorer.apply(cfg, self.exe, str(self.b), self.win)
        self.assertEqual([k for k in self.win.reg.keys if "hoard" in k], [])

    def test_off_windows_the_file_managers_have_it(self):
        from hoard import filemanagers
        asked = []
        cfg = {"local_sync": str(self.a)}
        with mock.patch.object(explorer, "here", lambda: False), \
                mock.patch.object(explorer, "Windows", side_effect=AssertionError("never asked")), \
                mock.patch.object(filemanagers, "apply", lambda *a: asked.append(a) or {"icon": True, "menu": False}):
            self.assertEqual(explorer.apply(cfg, self.exe, "was"), {"icon": True, "menu": False})
        self.assertEqual(asked, [(cfg, self.exe, "was")], "issue #411: Finder's, or Linux's file managers'")
        self.assertEqual(list(self.a.iterdir()), [], "nothing of Windows'")

    def test_which_file_manager(self):
        from hoard import filemanagers
        with mock.patch.object(explorer, "here", lambda: True):
            self.assertEqual(explorer.where(), "explorer")
        with mock.patch.object(explorer, "here", lambda: False), mock.patch.object(filemanagers, "kind", lambda: "finder"):
            self.assertEqual(explorer.where(), "finder")
        with mock.patch.object(explorer, "here", lambda: False), mock.patch.object(filemanagers, "kind", lambda: None):
            self.assertIsNone(explorer.where())


class WhatTheMenuAsks(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root, self.sync = self.tmp / "Downloads", self.tmp / "Sync"
        self.root.mkdir()
        self.sync.mkdir()
        self.started, self.looked = [], []
        self.srv = SimpleNamespace(
            cfg={**config.load_config(), "root": str(self.root), "local_sync": str(self.sync)},
            start_worker=lambda name, target, *args: self.looked.append(name),
            jobs=SimpleNamespace(start=lambda task, stores, **k: self.started.append(k["local"]) or "started"))

    def test_checked(self):
        mine = str(self.tmp / "hat.png")
        given = [{"do": "add", "path": mine}, {"do": "sync"}, {"do": "local"}, {"do": "add", "path": "hat.png"},
                 {"do": "add", "path": 7}, {"do": "add", "path": mine + "\x00.exe"}, {"do": "rm -rf"}, "add",
                 {"do": "add", "path": "x" * 1001}, {"do": "sync", "path": str(self.sync)}, {"do": "sync", "path": "Sync"}]
        self.assertEqual(explorer.actions(given), [{"do": "add", "path": mine}, {"do": "sync"}, {"do": "local"},
                                                   {"do": "sync", "path": str(self.sync)}])
        self.assertEqual(len(explorer.actions([{"do": "sync"}] * 50)), explorer.MAX_ACTIONS)
        self.assertEqual(explorer.actions("add"), [])

    def test_a_file_is_copied_into_the_sync_folder_never_over_one(self):
        hat = self.tmp / "hat.png"
        hat.write_bytes(b"\x89PNG one")
        self.assertEqual(explorer.add(self.srv, str(hat)), {"said": "copied", "name": "hat.png"})
        hat.write_bytes(b"\x89PNG two")
        self.assertEqual(explorer.add(self.srv, str(hat)), {"said": "copied", "name": "hat (2).png"})
        self.assertEqual((self.sync / "hat.png").read_bytes(), b"\x89PNG one", "the first left as it was")
        self.assertEqual((self.sync / "hat (2).png").read_bytes(), b"\x89PNG two")
        self.assertEqual(self.looked, ["Look at the Local sync folder"] * 2, "and Hoard looks at once")
        self.assertEqual(explorer.add(self.srv, str(self.sync / "hat.png")), {"said": "there", "name": "hat.png"})
        self.assertEqual(explorer.add(self.srv, str(self.sync)), {"said": "there", "name": "Sync"})
        self.assertEqual(explorer.add(self.srv, str(self.tmp / "gone.png")), {"said": "gone", "name": "gone.png"})
        self.assertEqual(self.started, [])

    def test_only_what_add_to_local_takes(self):
        downloaded = self.root / "Booth" / "Kitsu" / "Rusk" / "rusk.zip"
        downloaded.parent.mkdir(parents=True)
        downloaded.write_bytes(b"zip")
        got = explorer.add(self.srv, str(downloaded))
        self.assertEqual(got["said"], "refused", "already in Hoard's downloads folder")
        self.assertIn("downloads folder", got["why"])
        if hasattr(os, "symlink"):
            try:
                (self.tmp / "link.png").symlink_to(downloaded)
            except OSError:
                pass
            else:
                self.assertEqual(explorer.add(self.srv, str(self.tmp / "link.png"))["said"], "refused", "a link")
        self.assertEqual(list(self.sync.iterdir()), [], "nothing copied")
        self.assertEqual(self.started, [])

    def test_one_too_big_is_said(self):
        big = self.tmp / "big.bin"
        with open(big, "wb") as f:   # (sparse: as big as it says, without the disk)
            f.truncate(localsync.MAX_FILE + 1)
        self.assertEqual(explorer.add(self.srv, str(big))["said"], "big")
        self.assertEqual(list(self.sync.iterdir()), [])

    def test_a_folder_is_listed_in_local_where_it_is(self):
        outfit = self.tmp / "Outfit"
        outfit.mkdir()
        (outfit / "outfit.unitypackage").write_bytes(b"package")
        self.assertEqual(explorer.add(self.srv, str(outfit)), {"said": "adding", "name": "Outfit"})
        self.assertEqual(self.started[0]["path"], str(outfit))
        self.assertFalse(self.started[0]["copy"], "listed where it is")
        self.assertEqual(explorer.add(self.srv, str(self.root)), {"said": "refused", "name": "Downloads",
                                                                   "why": mock.ANY}, "Add to Local's own checks")
        self.assertEqual(len(self.started), 1)

    def test_with_no_sync_folder_a_file_is_copied_into_local(self):
        self.srv.cfg["local_sync"] = ""
        hat = self.tmp / "hat.png"
        hat.write_bytes(b"\x89PNG")
        self.assertEqual(explorer.add(self.srv, str(hat)), {"said": "adding", "name": "hat.png"})
        self.assertTrue(self.started[0]["copy"])
        self.assertEqual(explorer.do(self.srv, {"do": "sync"}), {"said": "no-sync"})
        self.srv.cfg["local_sync"] = str(self.sync)
        self.assertEqual(explorer.do(self.srv, {"do": "sync"}), {"said": "looking"})
        self.assertEqual(explorer.do(self.srv, {"do": "sync", "path": str(self.sync)}), {"said": "looking"})
        self.assertEqual(explorer.do(self.srv, {"do": "sync", "path": str(self.root)}), {"said": "not-sync"},
                         "chosen on another folder (if Explorer showed it there)")
        self.assertIsNone(explorer.do(self.srv, {"do": "local"}))

    def test_never_half_a_file(self):
        """The copy is made under a hidden name the sync folder's look leaves out, then put in place whole; one that
        couldn't be made leaves nothing behind."""
        hat = self.tmp / "hat.png"
        hat.write_bytes(b"\x89PNG" * 1000)
        seen = []
        real = explorer.shutil.copyfileobj

        def copying(r, w, *a):
            seen.append(sorted(p.name for p in self.sync.iterdir()))
            return real(r, w, *a)
        with mock.patch.object(explorer.shutil, "copyfileobj", copying):
            self.assertEqual(explorer.add(self.srv, str(hat))["said"], "copied")
        self.assertEqual(len(seen[0]), 1)
        self.assertTrue(seen[0][0].startswith("."), "only a hidden name while it's copied")
        self.assertEqual([p.name for p in self.sync.iterdir()], ["hat.png"], "then in place, and nothing else")

        def failing(r, w, *a):
            w.write(b"half")
            raise OSError("the disk is full")
        with mock.patch.object(explorer.shutil, "copyfileobj", failing), self.assertRaises(OSError):
            explorer.add(self.srv, str(hat))
        self.assertEqual([p.name for p in self.sync.iterdir()], ["hat.png"], "nothing left of it")

    def test_where_a_drive_cant_link(self):
        hat = self.tmp / "hat.png"
        hat.write_bytes(b"\x89PNG")
        (self.sync / "hat.png").write_bytes(b"theirs")
        with mock.patch.object(explorer.os, "link", side_effect=PermissionError("FAT")):
            self.assertEqual(explorer.add(self.srv, str(hat)), {"said": "copied", "name": "hat (2).png"})
        self.assertEqual((self.sync / "hat.png").read_bytes(), b"theirs")
        self.assertEqual(sorted(p.name for p in self.sync.iterdir()), ["hat (2).png", "hat.png"])


class FromASecondStart(IsolatedTestCase):
    """A second start (Explorer runs Hoard once for each file) hands what it was started for to the Hoard that's
    running, over its signed /api/show; that Hoard does it, and its page is given what it did."""

    def setUp(self):
        from hoard import server
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "dl").mkdir()
        (self.tmp / "Sync").mkdir()
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"), "setup_done": True,
                                                      "local_sync": str(self.tmp / "Sync")}, lan=False)
        self.shown = []
        self.srv.show_window = lambda: self.shown.append(True)
        self.srv.show_token = "pass-of-this-run"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def post(self, body):
        req = urllib.request.Request(self.srv.url + "api/show", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, {}

    def test_done_and_said(self):
        hat = self.tmp / "hat.png"
        hat.write_bytes(b"\x89PNG")
        actions = [{"do": "add", "path": str(hat)}, {"do": "local"}]
        self.assertEqual(self.post({"token": "a guess", "actions": actions})[0], 403, "only another Hoard can ask")
        self.assertFalse((self.tmp / "Sync" / "hat.png").exists())
        with mock.patch.object(self.srv, "start_worker"):
            self.assertEqual(self.post({"token": "pass-of-this-run", "actions": actions}), (200, {"ok": True}))
            deadline = time.monotonic() + 10
            while not self.srv.link_waiting() and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertEqual(self.srv.take_open(), {"do": "local", "said": [{"said": "copied", "name": "hat.png"}]})
        self.assertTrue((self.tmp / "Sync" / "hat.png").exists())
        self.assertEqual(self.shown, [True], "Hoard comes to the front")

    def test_a_file_that_cant_be_copied_is_said_and_the_rest_carry_on(self):
        hat, ears = self.tmp / "hat.png", self.tmp / "ears.png"
        hat.write_bytes(b"\x89PNG")
        ears.write_bytes(b"\x89PNG")
        real = explorer._copy_new

        def copy(source, folder):
            if source.name == "hat.png":
                raise PermissionError("in use")
            return real(source, folder)
        with mock.patch.object(explorer, "_copy_new", copy), mock.patch.object(self.srv, "start_worker"):
            self.srv.explorer_do([{"do": "add", "path": str(hat)}, {"do": "add", "path": str(ears)}])
            deadline = time.monotonic() + 10
            while not self.srv.link_waiting() and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertEqual(self.srv.take_open()["said"], [{"said": "failed", "name": "hat.png"},
                                                        {"said": "copied", "name": "ears.png"}])


    def test_each_start_adds_to_what_the_page_is_told(self):
        """Explorer starts Hoard once for each file chosen: what each did is told together, not only the last."""
        hat, ears = self.tmp / "hat.png", self.tmp / "ears.png"
        hat.write_bytes(b"\x89PNG")
        ears.write_bytes(b"\x89PNG")
        with mock.patch.object(self.srv, "start_worker"):
            for one in (hat, ears):
                self.srv.explorer_do([{"do": "add", "path": str(one)}])
                deadline = time.monotonic() + 10
                while not (self.srv._link and len(self.srv._link["said"]) == [hat, ears].index(one) + 1) \
                        and time.monotonic() < deadline:
                    time.sleep(0.05)
        self.assertEqual([x["name"] for x in self.srv.take_open()["said"]], ["hat.png", "ears.png"])


class InSettings(IsolatedTestCase):
    def setUp(self):
        from hoard import server
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "dl").mkdir()
        (self.tmp / "Sync").mkdir()
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"), "setup_done": True},
                                    lan=False, config_path=self.tmp / "config.json")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def post(self, body):
        from hoard.safety import ACCESS_HEADER
        req = urllib.request.Request(self.srv.url + "api/local/sync", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", ACCESS_HEADER: self.srv.key,
                                              "Origin": self.srv.url.rstrip("/")})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def test_the_switch_and_the_folder(self):
        applied = []
        with mock.patch.object(explorer, "apply", lambda cfg, exe, was=None, win=None: applied.append(
                (cfg.get("local_sync"), cfg.get("explorer"), was)) or {"icon": True, "menu": False}), \
                mock.patch.object(explorer, "here", lambda: True), mock.patch.object(localsync, "tick"):
            got = self.post({})
            self.assertEqual(got["explorer"], {"here": True, "kind": "explorer", "on": True, "icon": False, "menu": False})
            self.assertEqual(applied, [], "only a change applies it")
            got = self.post({"folder": str(self.tmp / "Sync")})
            kept = self.srv.cfg["local_sync"]   # (as check_folder keeps it)
            self.assertEqual(Path(kept).resolve(), (self.tmp / "Sync").resolve())
            self.assertEqual(applied[-1], (kept, True, ""))
            self.assertTrue(got["explorer"]["icon"])
            got = self.post({"explorer": False})
            self.assertEqual(applied[-1], (kept, False, kept))
            self.assertFalse(got["explorer"]["on"])
        self.assertFalse(config.load_config(self.tmp / "config.json")["explorer"], "kept")


class OnThePage(IsolatedTestCase):
    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                pw.chromium.launch().close()
        except Exception:
            self.skipTest("no Playwright browser here")
        from hoard import server
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "dl").mkdir()
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"), "setup_done": True,
                                                      "ui": {"toured": True}}, lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def test_local_and_what_was_done(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.locator("nav.apptabs a[href='/downloads']").wait_for()
            with self.srv._link_lock:   # (as explorer_do leaves it)
                self.srv._link = {"do": "local", "said": [{"said": "copied", "name": "hat.png"}, {"said": "looking"},
                                                          {"said": "never heard of", "name": "x"}, "words"]}
            page.get_by_text("hat.png is in the sync folder: Hoard adds it to Local. Hoard is looking at the sync folder.").wait_for(timeout=10000)
            self.assertEqual(page.evaluate("location.pathname + location.hash"), "/downloads#store=Local")
            self.assertEqual(errors, [])
            browser.close()

    def test_the_switch_names_the_file_manager(self):
        from playwright.sync_api import sync_playwright
        shown = """[...document.querySelectorAll('#syncExplorerRow [data-fm]')].filter(e => !e.hidden)
                   .map(e => e.dataset.fm + ':' + e.textContent.replace(/\\s+/g, ' ').trim())"""
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(self.srv.entry_url())
            page.locator("nav.apptabs a[href='/downloads']").wait_for()
            page.evaluate("showSyncFolder({ folder: '', skipped: [], last: {}, explorer: { here: false, on: true } })")
            self.assertTrue(page.evaluate("document.querySelector('#syncExplorerRow').hidden"))
            page.evaluate("showSyncFolder({ folder: 'D:\\\\Sync', skipped: [], last: {}, explorer: { here: true, on: false, icon: false } })")
            self.assertFalse(page.evaluate("document.querySelector('#syncExplorerRow').hidden"))
            self.assertFalse(page.evaluate("document.querySelector('#syncExplorer').checked"))
            self.assertEqual(page.evaluate(shown), [   # (an older Hoard's answer, with no kind: Windows')
                "explorer:Show it in File Explorer: Hoard's icon on the folder, and Add to Hoard when you right-click a file or folder",
                "explorer:On Windows 11, Hoard's options are under Show more options."])
            for kind, words, refused in (
                    ("finder", ["finder:Show it in Finder: Hoard's icon on the folder, and Add to Hoard in Quick Actions when "
                                "you right-click a file or folder", "finder:In Finder, Hoard's options are under Quick Actions."],
                     "macOS didn't let Hoard put its icon on this folder (it has a custom icon of its own, or the folder "
                     "can't be changed)."),
                    ("files", ["files:Show it in your file manager: Hoard's icon on the folder, and Add to Hoard when you "
                               "right-click a file or folder", "files:GNOME Files has Hoard's options under Scripts; Dolphin "
                               "and Nemo show them with their own."],
                     "Hoard couldn't put its icon on this folder (it has a custom icon of its own, or the folder can't be "
                     "changed).")):
                page.evaluate("k => showSyncFolder({ folder: '/home/me/Sync', skipped: [], last: {}, "
                              "explorer: { here: true, kind: k, on: true, icon: false } })", kind)
                self.assertEqual(page.evaluate(shown), words)
                self.assertEqual(page.locator("#syncMsg").text_content(), refused)
            page.evaluate("showSyncFolder({ folder: '/home/me/Sync', skipped: [], last: {}, "
                          "explorer: { here: true, kind: 'files', on: true, icon: true, cant: ['gvfs'] } })")
            self.assertEqual(page.locator("#syncMsg").text_content(),
                             "In the Flatpak, GNOME Files and Nemo can't show Hoard's icon on the folder; Dolphin can.")
            page.evaluate("showSyncFolder({ folder: '/home/me/Sync', skipped: [], last: {}, "
                          "explorer: { here: true, kind: 'files', on: true, icon: true, menu: true } })")
            self.assertEqual(page.locator("#syncMsg").text_content(), "")
            browser.close()
