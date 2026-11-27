"""Hoard's Local sync folder in macOS's Finder and Linux's file managers (hoard/filemanagers.py, issue #411): its icon,
put on and taken off without touching another's; Hoard's right-click options, for each file manager that's there and
in its language; the script they run, asking Hoard for what was chosen, or taking them away once Hoard is gone; and
which program it starts (the window's, the AppImage, the Flatpak, a Mac's app). The computer is a stand-in here (gio,
osascript, which programs are installed); the real calls are in filemanagers.System, and RealMac and RealGio run them
where they can."""
from __future__ import annotations

import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase
from hoard import filemanagers, i18n, local
from hoard.explorer import TIP

ICON = filemanagers.ICON_NAME


class FakeSystem(filemanagers.System):
    """The computer, as filemanagers asks it things: GVfs's metadata and Finder's icons kept in dicts, the programs that
    are installed, and a home folder in a test's own folder."""

    def __init__(self, kind, root: Path, programs=("gio",), flatpak=False, env=None):
        super().__init__(kind)
        self.root, self.programs, self.is_flatpak, self.env = root, set(programs), flatpak, dict(env or {})
        self.ran: list[list[str]] = []
        self.metadata: dict[str, str] = {}
        (root / "home").mkdir(parents=True, exist_ok=True)

    def run(self, args, timeout=30):
        self.ran.append(list(args))
        ok = lambda out="": subprocess.CompletedProcess(args, 0, out, "")  # noqa: E731
        if args[:2] == ["gio", "info"]:
            value = self.metadata.get(args[-1])
            return ok(f"uri: file://{args[-1]}\nattributes:\n" + (f"  metadata::custom-icon: {value}\n" if value else ""))
        if args[:3] == ["gio", "set", "--type=unset"]:
            self.metadata.pop(args[3], None)
            return ok()
        if args[:2] == ["gio", "set"]:
            self.metadata[args[2]] = args[4]
            return ok()
        if args[0] == "osascript":
            folder = Path(args[5])
            if len(args) > 6:
                (folder / filemanagers.FINDER_ICON).write_bytes(Path(args[6]).read_bytes())
            else:
                (folder / filemanagers.FINDER_ICON).unlink(missing_ok=True)
            return ok("yes\n")
        return ok()

    def which(self, name):
        return f"/usr/bin/{name}" if name in self.programs else None

    def home(self):
        return self.root / "home"

    def data_home(self):
        return self.home() / ".local" / "share"

    def config_home(self):
        return self.home() / ".config"

    def flatpak(self):
        return self.is_flatpak

    def helper_dir(self):
        return self.root / "data" / "file-manager"

    def environ(self):
        return dict(self.env)

    def finder_print(self, folder):
        icon = folder / filemanagers.FINDER_ICON
        return hashlib.sha256(icon.read_bytes()).hexdigest() if icon.is_file() else None


@unittest.skipIf(os.name == "nt", "Finder's and Linux's file managers (Windows' File Explorer is test_explorer's)")
class Case(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sync = self.tmp / "Sync"
        self.sync.mkdir()

    def system(self, kind="files", **kw):
        return FakeSystem(kind, self.tmp, **kw)


class TheIcon(Case):
    def test_gnome_and_dolphin(self):
        s = self.system(programs=("gio", "dolphin"))
        self.assertEqual(filemanagers.mark(self.sync, s), (True, []))
        icon = self.sync / ICON
        self.assertEqual(icon.read_bytes(), filemanagers.ICON_SOURCE.read_bytes())
        self.assertEqual(s.metadata, {str(self.sync): icon.as_uri()}, "GNOME Files' and Nemo's")
        self.assertEqual((self.sync / ".directory").read_text("utf-8").splitlines(),
                         [filemanagers.MARK, "[Desktop Entry]", f"Icon={icon}", f"Comment={TIP}"], "Dolphin's")
        self.assertTrue(filemanagers.unmark(self.sync, s))
        self.assertEqual(s.metadata, {})
        self.assertEqual(list(self.sync.iterdir()), [], "nothing of Hoard's left")
        self.assertFalse(filemanagers.unmark(self.sync, s), "nothing to take off")

    def test_another_icon_stays(self):
        s = self.system(programs=("gio", "dolphin"))
        (self.sync / ".directory").write_text("[Desktop Entry]\nIcon=folder-music\n", "utf-8")
        self.assertEqual(filemanagers.mark(self.sync, s), (True, []), "GNOME's")
        self.assertEqual((self.sync / ".directory").read_text("utf-8"), "[Desktop Entry]\nIcon=folder-music\n")
        filemanagers.unmark(self.sync, s)
        s.metadata[str(self.sync)] = "file:///home/me/mine.png"
        (self.sync / ".directory").unlink()
        self.assertEqual(filemanagers.mark(self.sync, s), (False, []))
        self.assertEqual(s.metadata, {str(self.sync): "file:///home/me/mine.png"})
        self.assertFalse((self.sync / ".directory").exists(), "Dolphin isn't given Hoard's over GNOME's other one")
        self.assertFalse((self.sync / ICON).exists(), "no picture left for nothing")

    def test_only_where_dolphin_is(self):
        s = self.system()
        self.assertEqual(filemanagers.mark(self.sync, s), (True, []))
        self.assertEqual(sorted(p.name for p in self.sync.iterdir()), [ICON], "no .directory without Dolphin")

    def test_the_picture_deleted(self):
        s = self.system(programs=("gio", "dolphin"))
        filemanagers.mark(self.sync, s)
        (self.sync / ICON).unlink()
        self.assertTrue(filemanagers.unmark(self.sync, s), "what points to it goes too")
        self.assertEqual(s.metadata, {})
        self.assertEqual(list(self.sync.iterdir()), [])

    @unittest.skipIf(os.name == "nt", "who may read a file is Linux's and a Mac's")
    def test_who_may_read_directory(self):
        s = self.system(programs=("dolphin",))
        filemanagers.mark(self.sync, s)
        self.assertEqual((self.sync / ".directory").stat().st_mode & 0o777, 0o644, "anyone, as a new one is")
        filemanagers.unmark(self.sync, s)
        (self.sync / ".directory").write_text("[Dolphin]\nViewMode=1\n", "utf-8")
        (self.sync / ".directory").chmod(0o664)
        filemanagers.mark(self.sync, s)
        self.assertEqual((self.sync / ".directory").stat().st_mode & 0o777, 0o664, "as it was")

    def test_dolphins_own_settings_kept(self):
        s = self.system(programs=("dolphin",))
        before = "[Dolphin]\nTimestamp=2026,11,1,10,0,0\nViewMode=1\n\n[Desktop Entry]\nComment=Mine\n"
        (self.sync / ".directory").write_text(before, "utf-8")
        self.assertEqual(filemanagers.mark(self.sync, s), (True, []))
        lines = (self.sync / ".directory").read_text("utf-8").splitlines()
        self.assertEqual(lines[0], filemanagers.MARK)
        self.assertIn(f"Icon={self.sync / ICON}", lines)
        self.assertIn("Comment=Mine", lines)
        self.assertNotIn(f"Comment={TIP}", lines, "its own tip kept")
        self.assertIn("ViewMode=1", lines)
        filemanagers.unmark(self.sync, s)
        self.assertEqual((self.sync / ".directory").read_text("utf-8"), before)

    def test_dolphin_wrote_it_since(self):
        """Dolphin writes the file again when it keeps a folder's view, and may drop the mark: Hoard's lines are known by
        what they say."""
        s = self.system(programs=("dolphin",))
        filemanagers.mark(self.sync, s)
        text = (self.sync / ".directory").read_text("utf-8").replace(filemanagers.MARK + "\n", "")
        (self.sync / ".directory").write_text(text + "\n[Dolphin]\nViewMode=2\n", "utf-8")
        filemanagers.unmark(self.sync, s)
        self.assertEqual((self.sync / ".directory").read_text("utf-8"), "[Dolphin]\nViewMode=2\n", "its section gone")
        filemanagers.mark(self.sync, s)
        filemanagers.mark(self.sync, s)
        lines = (self.sync / ".directory").read_text("utf-8").splitlines()
        self.assertEqual(lines.count(f"Icon={self.sync / ICON}"), 1, "once, however often")
        self.assertEqual(lines.count(filemanagers.MARK), 1)

    def test_flatpak(self):
        s = self.system(flatpak=True)
        s.config_home().mkdir(parents=True)
        (s.config_home() / "dolphinrc").write_text("", "utf-8")   # (Dolphin's, as the sandbox sees it's there)
        self.assertEqual(filemanagers.mark(self.sync, s), (True, ["gvfs"]), "Dolphin's only, and Settings says so")
        self.assertEqual([a for a in s.ran if a[0] == "gio"], [], "its sandbox keeps it from GVfs")
        self.assertTrue((self.sync / ".directory").is_file())

    def test_never_through_a_link(self):
        if os.name == "nt":
            self.skipTest("links need an administrator on Windows")
        s = self.system()
        outside = self.tmp / "outside.txt"
        outside.write_text("mine", "utf-8")
        (self.sync / ICON).symlink_to(outside)
        (self.sync / ".directory").symlink_to(outside)
        shown, _ = filemanagers.mark(self.sync, s)
        self.assertTrue(shown, "GNOME's")
        self.assertEqual(outside.read_text("utf-8"), "mine")
        self.assertFalse((self.sync / ICON).is_symlink())
        self.assertTrue((self.sync / ".directory").is_symlink(), "not Hoard's to change")
        link = self.tmp / "Linked"
        link.symlink_to(self.sync)
        self.assertEqual(filemanagers.mark(link, s), (False, []), "a sync folder that's a link isn't marked")

    def test_finder(self):
        s = self.system("finder")
        self.assertEqual(filemanagers.mark(self.sync, s), (True, []))
        [call] = s.ran
        self.assertEqual(call[:5], ["osascript", "-l", "JavaScript", "-e", filemanagers.FINDER_SET_ICON])
        self.assertEqual(call[5:], [str(self.sync), str(self.sync / ICON)], "the paths as arguments, never in the script")
        self.assertTrue((self.sync / filemanagers.FINDER_ICON).exists())
        self.assertTrue(filemanagers.unmark(self.sync, s))
        self.assertEqual(s.ran[-1][5:], [str(self.sync)], "taken off")
        self.assertEqual(list(self.sync.iterdir()), [])

    def test_finder_keeps_an_icon_you_put_on_since(self):
        s = self.system("finder")
        filemanagers.mark(self.sync, s)
        (self.sync / filemanagers.FINDER_ICON).write_bytes(b"yours")   # (Get Info, and an icon pasted on)
        self.assertEqual(filemanagers.mark(self.sync, s), (False, []), "not Hoard's to put back")
        self.assertEqual((self.sync / filemanagers.FINDER_ICON).read_bytes(), b"yours")
        self.assertFalse((self.sync / ICON).exists())
        filemanagers.mark(self.sync, s)   # (and it's never taken off)
        filemanagers.unmark(self.sync, s)
        self.assertEqual((self.sync / filemanagers.FINDER_ICON).read_bytes(), b"yours")
        other = self.tmp / "Other"
        other.mkdir()
        filemanagers.mark(other, s)
        (other / filemanagers.FINDER_ICON).write_bytes(b"yours too")
        self.assertTrue(filemanagers.unmark(other, s))
        self.assertEqual((other / filemanagers.FINDER_ICON).read_bytes(), b"yours too", "one you put on since stays")
        self.assertFalse((other / ICON).exists())

    def test_finder_keeps_anothers_icon(self):
        s = self.system("finder")
        (self.sync / filemanagers.FINDER_ICON).write_bytes(b"someone's")
        self.assertEqual(filemanagers.mark(self.sync, s), (False, []))
        self.assertEqual(s.ran, [])
        self.assertFalse(filemanagers.unmark(self.sync, s))
        self.assertEqual((self.sync / filemanagers.FINDER_ICON).read_bytes(), b"someone's")

    def test_the_sync_folder_never_adds_them(self):
        s = self.system()
        filemanagers.mark(self.sync, s)
        (self.sync / filemanagers.FINDER_ICON).write_bytes(b"")
        for entry in self.sync.iterdir():   # (localsync.scan's test for what it leaves out)
            self.assertTrue(entry.name.startswith(".") or entry.name.lower() in local.SKIP, entry.name)


class TheMenu(Case):
    def written(self):
        home = self.tmp / "home"
        return sorted(str(p.relative_to(home)) for p in home.rglob("*") if p.is_file())

    def test_each_file_manager_thats_there(self):
        s = self.system(programs=("nautilus", "dolphin", "nemo"))
        self.assertTrue(filemanagers.register(["/opt/Hoard/hoard"], s))
        self.assertEqual(self.written(), [
            ".local/share/kio/servicemenus/hoard-add.desktop", ".local/share/kio/servicemenus/hoard-folder.desktop",
            ".local/share/nautilus/scripts/Add to Hoard", ".local/share/nautilus/scripts/Open in Hoard",
            ".local/share/nautilus/scripts/Sync with Hoard now",
            ".local/share/nemo/actions/hoard-add.nemo_action", ".local/share/nemo/actions/hoard-open-here.nemo_action",
            ".local/share/nemo/actions/hoard-open.nemo_action", ".local/share/nemo/actions/hoard-sync-here.nemo_action",
            ".local/share/nemo/actions/hoard-sync.nemo_action"])
        helper = s.helper_dir() / filemanagers.HELPER
        data = s.data_home()
        if os.name != "nt":
            for p in (helper, data / "nautilus/scripts/Add to Hoard", data / "kio/servicemenus/hoard-add.desktop"):
                self.assertTrue(os.access(p, os.X_OK), p)
        add = (data / "kio/servicemenus/hoard-add.desktop").read_text("utf-8")
        self.assertIn("MimeType=all/all;", add)
        self.assertIn(f'Exec="{helper}" add %F', add)
        folder = (data / "kio/servicemenus/hoard-folder.desktop").read_text("utf-8")
        self.assertIn("Actions=hoardSync;hoardOpen;", folder)
        self.assertIn(f'Exec="{helper}" sync %f', folder)
        here = (data / "nemo/actions/hoard-sync-here.nemo_action").read_text("utf-8")
        self.assertIn("Selection=none", here)
        self.assertIn(f'Exec="{helper}" sync %P', here)
        script = (data / "nautilus/scripts/Sync with Hoard now").read_text("utf-8")
        self.assertTrue(script.endswith(f'exec {helper} sync "$@"\n') or script.endswith(f"exec '{helper}' sync \"$@\"\n"))

    def test_only_whats_installed(self):
        s = self.system(programs=("dolphin",))
        self.assertTrue(filemanagers.register(["/opt/Hoard/hoard"], s))
        self.assertEqual(self.written(), [".local/share/kio/servicemenus/hoard-add.desktop",
                                          ".local/share/kio/servicemenus/hoard-folder.desktop"])
        self.assertFalse(filemanagers.register(["/opt/Hoard/hoard"], self.system(programs=())), "none there")

    def test_the_flatpak_sees_its_folder(self):
        s = self.system(programs=(), flatpak=True)
        (s.data_home() / "nautilus").mkdir(parents=True)
        self.assertTrue(filemanagers.register(["flatpak", "run", filemanagers.FLATPAK_ID], s))
        self.assertIn(".local/share/nautilus/scripts/Add to Hoard", self.written())
        self.assertNotIn(".local/share/kio/servicemenus/hoard-add.desktop", self.written())

    def test_in_your_language(self):
        s = self.system(programs=("nautilus", "dolphin"))
        filemanagers.register(["/opt/Hoard/hoard"], s, "en")
        filemanagers.register(["/opt/Hoard/hoard"], s, "ja")
        scripts = sorted(p.name for p in (s.data_home() / "nautilus/scripts").iterdir())
        self.assertEqual(scripts, sorted(i18n.say("ja", w) for w in ("Add to Hoard", "Sync with Hoard now", "Open in Hoard")),
                         "the English ones taken away")
        self.assertIn(f"Name={i18n.say('ja', 'Add to Hoard')}",
                      (s.data_home() / "kio/servicemenus/hoard-add.desktop").read_text("utf-8"))

    def test_only_this_hoards_are_taken(self):
        s = self.system(programs=("nautilus",))
        scripts = s.data_home() / "nautilus" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "Mine").write_text("#!/bin/sh\necho mine\n", "utf-8")
        (scripts / "Another Hoard's").write_text(f"#!/bin/sh\n{filemanagers.MARK}\nexec /elsewhere/hoard-files add\n",
                                                 "utf-8")
        (scripts / "Add to Hoard").write_text("#!/bin/sh\necho mine too\n", "utf-8")
        filemanagers.register(["/opt/Hoard/hoard"], s)
        self.assertEqual((scripts / "Add to Hoard").read_text("utf-8"), "#!/bin/sh\necho mine too\n",
                         "the same name: yours, left as it is")
        self.assertIn(filemanagers.MARK, (scripts / "Open in Hoard").read_text("utf-8"))
        filemanagers.unregister(s)
        self.assertEqual(sorted(p.name for p in scripts.iterdir()), ["Add to Hoard", "Another Hoard's", "Mine"])
        self.assertFalse(s.helper_dir().exists())

    def test_a_path_the_menus_cant_quote(self):
        s = self.system(programs=("nautilus", "dolphin", "nemo"))
        with mock.patch.object(FakeSystem, "helper_dir", lambda self: self.root / "100%" / "file-manager"):
            self.assertTrue(filemanagers.register(["/opt/Hoard/hoard"], s))
        self.assertEqual([w for w in self.written() if "nautilus" not in w], [], "GNOME Files' only: a script, quoted")

    def test_quick_actions(self):
        s = self.system("finder")
        self.assertTrue(filemanagers.register(["open", "-n", "-a", "/Applications/Hoard.app", "--args"], s, "ko"))
        services = s.home() / "Library" / "Services"
        self.assertEqual(sorted(p.name for p in services.iterdir()),
                         ["Hoard - Add.workflow", "Hoard - Open.workflow", "Hoard - Sync now.workflow"])
        info = plistlib.loads((services / "Hoard - Add.workflow/Contents/Info.plist").read_bytes())
        [service] = info["NSServices"]
        self.assertEqual(service["NSMenuItem"], {"default": i18n.say("ko", "Add to Hoard")})
        self.assertEqual(service["NSSendFileTypes"], ["public.item"])
        self.assertEqual(service["NSRequiredContext"], {"NSApplicationIdentifier": "com.apple.finder"})
        folder = plistlib.loads((services / "Hoard - Sync now.workflow/Contents/Info.plist").read_bytes())
        self.assertEqual(folder["NSServices"][0]["NSSendFileTypes"], ["public.folder"])
        document = plistlib.loads((services / "Hoard - Add.workflow/Contents/document.wflow").read_bytes())
        parameters = document["actions"][0]["action"]["ActionParameters"]
        self.assertEqual(parameters["inputMethod"], 1, "what's chosen, as arguments")
        self.assertEqual(parameters["COMMAND_STRING"], f'{s.helper_dir() / filemanagers.HELPER} add "$@"')
        self.assertIn([filemanagers.PBS, "-update"], s.ran)
        filemanagers.unregister(s)
        self.assertEqual(list(services.iterdir()), [])
        self.assertFalse(s.helper_dir().exists())


class WhatItStarts(Case):
    def test_the_program(self):
        files, finder = self.system(), self.system("finder")
        self.assertEqual(filemanagers.program("/usr/bin/hoard", files), ["/usr/bin/hoard"])
        self.assertIsNone(filemanagers.program(None, files), "a Hoard started without its window")
        self.assertIsNone(filemanagers.program("hoard", files), "only a full path")
        appimage = self.system(env={"APPIMAGE": "/home/me/Hoard.AppImage"})
        self.assertEqual(filemanagers.program("/tmp/.mount_Hoard/usr/bin/hoard", appimage), ["/home/me/Hoard.AppImage"])
        self.assertEqual(filemanagers.program("/x", self.system(flatpak=True)), ["flatpak", "run", filemanagers.FLATPAK_ID])
        self.assertEqual(filemanagers.program("/Applications/Hoard.app/Contents/MacOS/Hoard", finder),
                         ["open", "-n", "-a", "/Applications/Hoard.app", "--args"], "Finder isn't kept waiting")

    def test_the_check_for_hoard(self):
        self.assertIn(f"flatpak info {filemanagers.FLATPAK_ID}",
                      filemanagers._check(["flatpak", "run", filemanagers.FLATPAK_ID]))
        self.assertEqual(filemanagers._check(["open", "-n", "-a", "/Applications/Hoard.app", "--args"]),
                         "[ -d /Applications/Hoard.app ]")
        self.assertEqual(filemanagers._check(["/opt/My Hoard/hoard"]), "[ -x '/opt/My Hoard/hoard' ]")


@unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "the script is for Finder and Linux's file managers")
class TheScript(Case):
    def setUp(self):
        super().setUp()
        self.program = self.tmp / "my programs" / "hoard"
        self.program.parent.mkdir()
        self.said = self.tmp / "said"
        self.program.write_text(f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done > "{self.said}"\n', "utf-8")
        self.program.chmod(0o755)
        self.s = self.system(programs=("nautilus", "nemo"))
        filemanagers.register([str(self.program)], self.s)
        self.helper = self.s.helper_dir() / filemanagers.HELPER
        self.here = self.sync.resolve()   # (as the shell's $PWD says it: on a Mac, /var is /private/var)

    def run_it(self, *args, cwd=None):
        self.said.unlink(missing_ok=True)
        done = subprocess.run([str(self.helper), *args], cwd=cwd or self.here, capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return self.said.read_text("utf-8").splitlines() if self.said.exists() else None

    def test_what_it_asks_for(self):
        self.assertEqual(self.run_it("add", "/home/me/a b.png", "c.zip", "-n"),
                         ["--hoard-add", "/home/me/a b.png", "--hoard-add", f"{self.here}/c.zip",
                          "--hoard-add", f"{self.here}/-n"], "each chosen, as a full path")
        self.assertIsNone(self.run_it("add"), "nothing chosen: nothing asked")
        self.assertEqual(self.run_it("sync"), ["--hoard-sync-now", str(self.here)], "inside a folder")
        self.assertEqual(self.run_it("sync", "/home/me/Sync"), ["--hoard-sync-now", "/home/me/Sync"])
        self.assertEqual(self.run_it("local", "/home/me/Sync"), ["--hoard-open-local"])

    def test_gone_with_hoard(self):
        scripts = self.s.data_home() / "nautilus" / "scripts"
        (scripts / "Add to Hoard").unlink()
        (scripts / "Add to Hoard").write_text("#!/bin/sh\necho yours\n", "utf-8")   # (yours, there since)
        self.program.unlink()
        self.assertIsNone(self.run_it("add", "/home/me/a.png"))
        self.assertEqual(list(self.s.data_home().rglob("*.nemo_action")), [])
        self.assertEqual([p.name for p in scripts.iterdir()], ["Add to Hoard"], "only Hoard's own")
        self.assertFalse(self.s.helper_dir().exists(), "and the script itself")

    def test_the_flatpak(self):
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        flatpak = bin_ / "flatpak"
        flatpak.write_text(f'#!/bin/sh\n[ "$1" = info ] && exit "$(cat "{self.tmp}/installed")"\n'
                           f'for a in "$@"; do printf "%s\\n" "$a"; done > "{self.said}"\n', "utf-8")
        flatpak.chmod(0o755)
        (self.tmp / "installed").write_text("0", "utf-8")
        filemanagers.register(["flatpak", "run", filemanagers.FLATPAK_ID], self.s)
        with mock.patch.dict(os.environ, {"PATH": f"{bin_}{os.pathsep}{os.environ.get('PATH', '')}"}):
            self.assertEqual(self.run_it("add", "/home/me/a.png"),
                             ["run", filemanagers.FLATPAK_ID, "--hoard-add", "/home/me/a.png"])
            (self.tmp / "installed").write_text("1", "utf-8")   # (Hoard's Flatpak uninstalled, flatpak still there)
            self.assertIsNone(self.run_it("add", "/home/me/a.png"))
        self.assertFalse(self.s.helper_dir().exists(), "its options taken away")
        self.assertEqual(list(self.s.data_home().rglob("*.nemo_action")), [])


class Applying(Case):
    def test_on_and_off(self):
        s = self.system(programs=("gio", "nautilus"))
        cfg = {"local_sync": str(self.sync)}
        self.assertEqual(filemanagers.apply(cfg, "/opt/Hoard/hoard", system=s), {"icon": True, "menu": True})
        self.assertTrue((self.sync / ICON).exists())
        self.assertTrue((s.helper_dir() / filemanagers.HELPER).exists())
        cfg["explorer"] = False
        self.assertEqual(filemanagers.apply(cfg, "/opt/Hoard/hoard", system=s), {"icon": False, "menu": False})
        self.assertEqual(list(self.sync.iterdir()), [])
        self.assertFalse(s.helper_dir().exists())

    def test_another_folder(self):
        s = self.system()
        other = self.tmp / "Other"
        other.mkdir()
        filemanagers.apply({"local_sync": str(self.sync)}, None, system=s)
        got = filemanagers.apply({"local_sync": str(other)}, None, str(self.sync), s)
        self.assertEqual(got, {"icon": True, "menu": False}, "no program to start: the options are left as they are")
        self.assertEqual(list(self.sync.iterdir()), [], "taken off the folder it was")
        self.assertTrue((other / ICON).exists())

    def test_the_flatpak_says_what_it_cant(self):
        s = self.system(flatpak=True)
        self.assertEqual(filemanagers.apply({"local_sync": str(self.sync)}, None, system=s)["cant"], ["gvfs"])

    def test_nowhere_else(self):
        s = self.system(None)
        s.kind = None
        self.assertEqual(filemanagers.apply({"local_sync": str(self.sync)}, "/x", system=s), {"icon": False, "menu": False})
        self.assertEqual(list(self.sync.iterdir()), [])

    def test_the_language(self):
        s = self.system(env={"LANG": "ko_KR.UTF-8"})
        self.assertEqual(filemanagers.language({}, s), "ko")
        self.assertEqual(filemanagers.language({"display": {"language": "ja"}}, s), "ja", "Settings' choice first")
        self.assertEqual(filemanagers.language({}, self.system(env={"LANG": "C"})), "en")


@unittest.skipUnless(sys.platform == "darwin", "a Mac's own Finder")
class RealMac(Case):
    """On a Mac (Check's app job runs these there): Finder's icon call, and Quick Actions that macOS reads."""

    def test_the_icon(self):
        s = filemanagers.System()
        self.assertEqual(filemanagers.mark(self.sync, s), (True, []))
        self.assertTrue((self.sync / filemanagers.FINDER_ICON).exists(), "Finder's Icon\\r")
        kept = filemanagers._finder_prints(s).get(str(self.sync))
        self.assertTrue(kept, "a fingerprint of the icon Hoard put on")
        self.assertEqual(s.finder_print(self.sync), kept, "the same when it's read again")
        done = s.run(["osascript", "-l", "JavaScript", "-e", filemanagers.FINDER_SET_ICON, str(self.sync)])
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "yes"), f"Finder's call to take it off: {done.stderr}")
        self.assertFalse((self.sync / filemanagers.FINDER_ICON).exists(), "taken off by Finder's own call")
        filemanagers.mark(self.sync, s)
        self.assertTrue(filemanagers.unmark(self.sync, s))
        self.assertEqual(list(self.sync.iterdir()), [])

    def test_the_quick_actions_are_read(self):
        s = filemanagers.System()
        with mock.patch.object(filemanagers.System, "home", lambda self_: self.tmp / "home"), \
                mock.patch.object(filemanagers.System, "helper_dir", lambda self_: self.tmp / "data" / "file-manager"):
            self.assertTrue(filemanagers.register(["open", "-n", "-a", "/Applications/Hoard.app", "--args"], s))
            for plist in (self.tmp / "home").rglob("*.plist"):
                done = subprocess.run(["plutil", "-lint", str(plist)], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout)
            for wflow in (self.tmp / "home").rglob("document.wflow"):
                done = subprocess.run(["plutil", "-lint", str(wflow)], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout)
            filemanagers.unregister(s)

    @unittest.skipUnless(os.environ.get("CI"), "in your own account's Services, only on Check's Macs")
    def test_finder_offers_them(self):
        s = filemanagers.System()
        with mock.patch.object(filemanagers.System, "helper_dir", lambda self_: self.tmp / "data" / "file-manager"):
            self.assertTrue(filemanagers.register(["open", "-n", "-a", "/Applications/Hoard.app", "--args"], s))
            try:
                dump = subprocess.run([filemanagers.PBS, "-dump"], capture_output=True, text=True, timeout=60)
                if dump.returncode or not dump.stdout.strip():
                    self.skipTest(f"pbs lists nothing here: {dump.stderr.strip()[:300]}")
                self.assertIn("Sync with Hoard now", dump.stdout)
            finally:
                filemanagers.unregister(s)
        self.assertFalse(any(Path.home().glob("Library/Services/Hoard - *.workflow")))


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("gio"), "GVfs's gio")
class RealGio(Case):
    """GNOME Files' and Nemo's custom icon, set and taken off with the real gio, where GVfs keeps metadata."""

    def test_the_icon(self):
        s = filemanagers.System()
        probe = subprocess.run(["gio", "set", str(self.sync), "metadata::hoard-probe", "1"], capture_output=True)
        if probe.returncode:
            self.skipTest("GVfs keeps no metadata here (no session bus)")
        shown, _ = filemanagers.mark(self.sync, s)
        self.assertTrue(shown)
        self.assertEqual(filemanagers._gvfs_icon(s, self.sync), (self.sync / ICON).as_uri())
        filemanagers.unmark(self.sync, s)
        self.assertIsNone(filemanagers._gvfs_icon(s, self.sync))


if __name__ == "__main__":
    unittest.main()
