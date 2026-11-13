"""The browsers Hoard's store window can be (hoard/browser.py): Edge and Chrome by name; Brave, Vivaldi, Opera and
Opera GX where their installers put them; another Chromium browser by its program; and Hoard's own. Settings saves
the choice, the setup assistant offers those installed, and a backup never carries a program's path. Each sign-in
keeps the browser it was made with; Force stop ends a browser whatever it's doing; a browser that won't open a tab
when asked has one opened from a tab that's open."""
from __future__ import annotations

import os
import plistlib
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hoard import backup, browser, config, server, setup  # noqa: E402


def program(path: Path) -> Path:
    """A program at path (a file that can be run)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class FindingThem(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_on_windows_where_their_installers_put_them(self):
        local, pf = self.tmp / "Local", self.tmp / "Program Files"
        env = {"LOCALAPPDATA": str(local), "ProgramFiles": str(pf), "ProgramFiles(x86)": str(self.tmp / "x86")}
        brave = program(pf / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe")
        vivaldi = program(local / "Vivaldi" / "Application" / "vivaldi.exe")
        opera = program(local / "Programs" / "Opera" / "opera.exe")
        program(local / "Programs" / "Opera" / "launcher.exe")
        gx = program(local / "Programs" / "Opera GX" / "opera.exe")
        with mock.patch.object(sys, "platform", "win32"), mock.patch.dict(os.environ, env):
            self.assertEqual(browser.channel_path("brave"), str(brave))
            self.assertEqual(browser.channel_path("vivaldi"), str(vivaldi))
            self.assertEqual(browser.channel_path("opera"), str(opera), "opera.exe itself, not its launcher")
            self.assertEqual(browser.channel_path("opera_gx"), str(gx))
            self.assertIsNone(browser.channel_path("chrome"))
            self.assertIsNone(browser.channel_path("nothing-like-it"))

    def test_on_a_mac_in_applications(self):
        def app(name, program_name):
            inside = program(self.tmp / "Applications" / f"{name}.app" / "Contents" / "MacOS" / program_name)
            (inside.parent.parent / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": program_name}))
            return inside
        brave, gx = app("Brave Browser", "Brave Browser"), app("Opera GX", "Opera")
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(Path, "home", lambda: self.tmp):
            self.assertEqual(browser.channel_path("brave"), str(brave), "in your own Applications too")
            self.assertEqual(browser.channel_path("opera_gx"), str(gx))
            self.assertIsNone(browser.channel_path("vivaldi"))

    def test_on_linux_by_their_commands(self):
        found = {"brave-browser-stable": "/usr/bin/brave-browser-stable", "vivaldi": "/usr/bin/vivaldi"}
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(browser.shutil, "which", found.get):
            self.assertEqual(browser.channel_path("brave"), "/usr/bin/brave-browser-stable")
            self.assertEqual(browser.channel_path("vivaldi"), "/usr/bin/vivaldi")
            self.assertIsNone(browser.channel_path("opera_gx"), "there's no Opera GX for Linux")

    def test_what_hoard_starts(self):
        """The one you chose, when it's there; otherwise Hoard's own."""
        with mock.patch.object(browser, "channel_installed", lambda channel, cfg=None: channel == "brave"):
            self.assertEqual(browser.use_channel({"browser_channel": "brave"}), "brave")
            self.assertEqual(browser.use_channel({"browser_channel": "vivaldi"}), "chromium")


@unittest.skipIf(os.name == "nt", "a program here is a file that can be run (on Windows, its .exe)")
class ChosenByItsProgram(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_a_program(self):
        thorium = program(self.tmp / "thorium-browser")
        self.assertEqual(browser.custom_program(str(thorium)), str(thorium))
        self.assertEqual(browser.custom_program(f'"{thorium}"'), str(thorium), "pasted with its quotes")
        cfg = {"browser_channel": "custom", "browser_path": str(thorium)}
        self.assertEqual(browser.use_channel(cfg), "custom")
        self.assertEqual(browser.browser_name("custom", cfg), "Thorium Browser")

    def test_a_macs_app(self):
        app = self.tmp / "Arc.app"
        inside = program(app / "Contents" / "MacOS" / "Arc")
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Arc"}))
        self.assertEqual(browser.custom_program(str(app)), str(inside), "the program inside it")
        self.assertEqual(browser.browser_name("custom", {"browser_path": str(app)}), "Arc")

    def test_what_isnt_one(self):
        plain = self.tmp / "notes.txt"
        plain.write_text("x")
        for value in ("", "thorium", str(self.tmp / "missing"), str(plain), str(self.tmp), "x" * 1001,
                      str(program(self.tmp / "firefox")), str(program(self.tmp / "Firefox Developer Edition")),
                      str(program(self.tmp / "librewolf"))):
            with self.subTest(value=value[:60]):
                self.assertIsNone(browser.custom_program(value))
        cfg = {"browser_channel": "custom", "browser_path": str(self.tmp / "missing")}
        self.assertEqual(browser.use_channel(cfg), "chromium", "nothing there: Hoard's own")
        self.assertEqual(browser.browser_name("custom", cfg), "The browser you chose")


class StartingThem(IsolatedTestCase):
    """Edge and Chrome are started by name, the rest of the family by their program."""

    def launched(self, cfg, fail=None):
        seen = {}

        def start(**kwargs):
            seen.update(kwargs)
            if fail:
                raise fail
            return mock.MagicMock()
        p = mock.Mock()
        p.chromium.launch_persistent_context.side_effect = start
        with mock.patch.object(browser, "_key_args", lambda cfg: []), mock.patch.object(browser, "_track"):
            browser._launch(p, cfg, Path(tempfile.mkdtemp()), headless=True)
        return seen

    def test_by_name_or_by_program(self):
        with mock.patch.object(browser, "channel_path", lambda channel, cfg=None: f"/opt/{channel}/{channel}"):
            got = self.launched({"browser_channel": "brave"})
            self.assertEqual(got["executable_path"], "/opt/brave/brave")
            self.assertNotIn("channel", got)
            got = self.launched({"browser_channel": "msedge"})
            self.assertEqual(got["channel"], "msedge")
            self.assertNotIn("executable_path", got)
        self.assertEqual(self.launched({"browser_channel": "chromium"})["channel"], "chromium")

    def test_one_that_cant_be_started_says_so(self):
        with mock.patch.object(browser, "channel_path", lambda channel, cfg=None: "/opt/opera/opera"), \
                self.assertRaisesRegex(RuntimeError, "Opera couldn't be started for Hoard .*Choose another browser in Settings"):
            self.launched({"browser_channel": "opera"}, fail=Exception("Browser closed.\nmore"))


class ARealOne(IsolatedTestCase):
    """Playwright's own Chromium, chosen by its program as another browser would be: Hoard's window starts on it,
    with a store's profile, and reads a page."""

    def test_started_by_its_program(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                chromium = p.chromium.executable_path
                if not Path(chromium).is_file():
                    self.skipTest("Playwright's Chromium isn't installed")
                cfg = {**config.load_config(), "browser_channel": "custom", "browser_path": chromium,
                       "allow_unprotected_signins": True}
                self.assertEqual(browser.use_channel(cfg), "custom")
                ctx = browser._launch(p, cfg, Path(tempfile.mkdtemp()), headless=True)
                try:
                    page = ctx.new_page()
                    page.set_content("<title>Hoard</title>")
                    self.assertEqual(page.title(), "Hoard")
                finally:
                    ctx.close()
        except ImportError:
            self.skipTest("Playwright isn't installed")


class SettingsAndSetup(IsolatedTestCase):
    def setUp(self):
        self.cfg = config.load_config()

    def test_the_choices(self):
        for choice in ("brave", "vivaldi", "opera", "opera_gx", "custom", "msedge", "chrome", "chromium", ""):
            self.assertEqual(server.apply_settings(self.cfg, {"browser_channel": choice}), {"browser_channel": choice})
        with self.assertRaisesRegex(ValueError, "Unknown browser"):
            server.apply_settings(self.cfg, {"browser_channel": "firefox"})

    @unittest.skipIf(os.name == "nt", "a program here is a file that can be run")
    def test_another_browsers_program(self):
        tmp = Path(tempfile.mkdtemp())
        thorium = program(tmp / "thorium")
        self.assertEqual(server.apply_settings(self.cfg, {"browser_path": f" {thorium} "}), {"browser_path": str(thorium)})
        self.assertEqual(server.apply_settings(self.cfg, {"browser_path": ""}), {"browser_path": ""}, "none")
        with self.assertRaisesRegex(ValueError, "built on Chromium"):
            server.apply_settings(self.cfg, {"browser_path": str(program(tmp / "firefox"))})
        with self.assertRaisesRegex(ValueError, "isn't a browser's program"):
            server.apply_settings(self.cfg, {"browser_path": str(tmp / "missing")})
        shown = server.public_settings({**self.cfg, "browser_channel": "custom", "browser_path": str(thorium)})
        self.assertEqual((shown["browser_path"], shown["browser_name"], shown["browsers"]["custom"]),
                         (str(thorium), "Thorium", "custom"))

    def test_a_backup_never_carries_a_program(self):
        self.assertIn("browser_channel", backup.SETTINGS)
        self.assertNotIn("browser_path", backup.SETTINGS, "a program is chosen on its own computer, in Settings")

    def test_the_setup_assistant_offers_those_installed(self):
        cfg = {**self.cfg, "browser_channel": "vivaldi"}
        with mock.patch.object(setup, "channel_installed", lambda channel, cfg=None: channel in ("msedge", "vivaldi")):
            st = setup.browser_status(cfg)
        self.assertEqual((st["channel"], st["name"], st["ready"]), ("vivaldi", "Vivaldi", True))
        self.assertEqual(st["found"], ["msedge", "vivaldi"])
        self.assertEqual(st["names"], {"msedge": "Microsoft Edge", "vivaldi": "Vivaldi"})


class SignInsKeepTheirBrowser(IsolatedTestCase):
    """A store's sign-in is a browser's own folder, and another browser can't always use it: Hoard reads and signs
    out of it with the browser it was made with, and signing in again moves it to the one chosen now."""

    def setUp(self):
        self.cfg = {**config.load_config(), "allow_unprotected_signins": True}
        self.installed = {"msedge", "vivaldi"}
        patch = mock.patch.object(browser, "channel_installed", lambda channel, cfg=None: channel in self.installed)
        patch.start()
        self.addCleanup(patch.stop)
        target = browser.profile_dir(self.cfg, "booth")   # (the class shares one data folder: each test starts afresh)
        browser._remove_tree(target) if target.exists() else None
        browser._made_with_file(self.cfg, "booth").unlink(missing_ok=True)
        target.mkdir(parents=True)
        self.edge, self.vivaldi = {**self.cfg, "browser_channel": "msedge"}, {**self.cfg, "browser_channel": "vivaldi"}

    def test_its_browser_is_noted_and_kept(self):
        browser.check_saved_signin(self.edge, "booth")   # (signed in with Edge)
        self.assertEqual(browser.signin_browser(self.cfg, "booth"), {"channel": "msedge"})
        self.assertEqual(browser.for_signin(self.vivaldi, "booth")["browser_channel"], "msedge", "Vivaldi chosen since")
        self.assertEqual(browser.made_with_another(self.vivaldi, "booth"), "Microsoft Edge")
        self.assertIsNone(browser.made_with_another(self.edge, "booth"))
        self.installed.discard("msedge")
        self.assertIs(browser.for_signin(self.vivaldi, "booth"), self.vivaldi, "Edge taken away: the one chosen now")

    def test_one_chosen_by_its_program(self):
        thorium = program(Path(tempfile.mkdtemp()) / "thorium")
        with mock.patch.object(browser, "channel_installed", lambda channel, cfg=None: channel != "custom" or
                               browser.custom_program((cfg or {}).get("browser_path")) is not None):
            browser.note_signin_browser({**self.cfg, "browser_channel": "custom", "browser_path": str(thorium)}, "booth")
            got = browser.for_signin(self.vivaldi, "booth")
            self.assertEqual((got["browser_channel"], got["browser_path"]), ("custom", str(thorium)))
            thorium.unlink()
            self.assertIs(browser.for_signin(self.vivaldi, "booth"), self.vivaldi, "its program gone: the one chosen now")

    def test_one_not_noted_is_opened_as_before(self):
        self.assertIs(browser.for_signin(self.vivaldi, "booth"), self.vivaldi)
        browser._made_with_file(self.cfg, "booth").write_text("{not json")
        self.assertIsNone(browser.signin_browser(self.cfg, "booth"))
        browser._made_with_file(self.cfg, "booth").write_text('{"channel": "firefox"}')
        self.assertIsNone(browser.signin_browser(self.cfg, "booth"), "never a browser Hoard can't start")

    def test_its_browser_reads_it_and_signs_out_of_it(self):
        browser.note_signin_browser(self.edge, "booth")
        started = []

        def launch(p, cfg, profile, headless, timeout=None):
            started.append(cfg["browser_channel"])
            raise RuntimeError("not started in this test")
        with mock.patch.object(browser, "_launch", launch), mock.patch.object(browser, "_migrate_old_signins"):
            with self.assertRaises(RuntimeError):
                browser.launch_context(None, self.vivaldi, True, "booth")
            said = browser.sign_out(None, self.vivaldi, "booth", online=True)
        self.assertEqual(started, ["msedge", "msedge"], "read, then signed out, with Edge")
        self.assertIn("Couldn't sign out on Booth's side", said)
        self.assertFalse(browser.profile_dir(self.cfg, "booth").exists())
        self.assertFalse(browser._made_with_file(self.cfg, "booth").exists(), "nothing left of it")


@unittest.skipIf(os.name == "nt", "a stand-in browser here is a shell script")
class ForceStop(IsolatedTestCase):
    """Force stop ends a store's browser whatever it's doing: one still starting (Playwright hands a browser over only
    once its first tab is open), and one that stays on its folder after Hoard has let go of it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def process(self, script: str) -> int:
        """A stand-in for a browser, its number written where the test can find it: ended when the test ends."""
        made = program(self.tmp / f"stand-in-{len(list(self.tmp.iterdir()))}")
        made.write_text(f"#!/bin/sh\necho $$ > {made}.pid\n{script}\n")
        return made

    def ended(self, pid: int, within: float = 10.0) -> bool:
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
                if Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z":   # (ended, not yet tidied away)
                    return True
            except (ProcessLookupError, FileNotFoundError):
                return True
            time.sleep(0.1)
        return False

    def kill_later(self, pid: int) -> None:
        def kill():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.addCleanup(kill)

    def test_a_browser_still_starting(self):
        never = self.process("exec sleep 300")   # never answers Playwright: it waits for its first tab
        cfg = {**config.load_config(), "browser_channel": "custom", "browser_path": str(never),
               "allow_unprotected_signins": True}
        got, done = {}, threading.Event()

        def job():
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    began = time.monotonic()
                    try:
                        browser._launch(p, cfg, self.tmp / "profile", headless=True)
                    except Exception as e:
                        got["error"], got["after"] = str(e), time.monotonic() - began
            except Exception as e:
                got.setdefault("error", str(e))
            done.set()
        threading.Thread(target=job, daemon=True).start()
        pid_file = Path(f"{never}.pid")
        for _ in range(200):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            time.sleep(0.05)
        else:
            self.fail("the stand-in never started")
        self.kill_later(int(pid_file.read_text()))
        self.assertEqual(browser.end_browsers(), 1, "its driver ended")
        self.assertTrue(done.wait(30), "the launch gave up at once, not after Playwright's 3 minutes")
        self.assertLess(got["after"], 20)
        self.assertEqual(browser._starting, {})

    def left_behind(self, script: str):
        stand_in = self.process(script)
        proc = subprocess.Popen([str(stand_in)], start_new_session=True)
        self.addCleanup(proc.wait)
        self.kill_later(proc.pid)
        profile = self.tmp / "profile"
        profile.mkdir(exist_ok=True)
        os.symlink(f"{socket.gethostname()}-{proc.pid}", profile / "SingletonLock")   # as Chromium marks its folder
        return proc, profile

    def test_a_browser_left_on_its_folder(self):
        proc, profile = self.left_behind("exec sleep 300")
        self.assertTrue(browser._profile_in_use(profile))
        browser.end_left_behind([profile], grace=0.2)
        self.assertTrue(self.ended(proc.pid), "asked to quit, it did")

    def test_one_that_wont_quit_when_asked(self):
        proc, profile = self.left_behind("trap '' TERM\nwhile true; do sleep 0.1; done")
        began = time.monotonic()
        browser.end_left_behind([profile], grace=0.2)
        self.assertTrue(self.ended(proc.pid, within=2), "made to, 3 seconds after it was asked")
        self.assertLess(time.monotonic() - began, 10)

    def test_one_started_on_the_folder_since_is_left_alone(self):
        """After Force stop, a new task may open the same store's folder before the old browser's clean-up looks at
        it: only the browser that was there is ended."""
        proc, profile = self.left_behind("exec sleep 300")
        browser.end_left_behind([(profile, proc.pid + 100000)], grace=0.2)   # (the one that was there: gone since)
        self.assertFalse(self.ended(proc.pid, within=0.5), "the browser on it now is another's")
        browser.end_left_behind([(profile, proc.pid)], grace=0.2)
        self.assertTrue(self.ended(proc.pid))

    def test_signing_out_ends_one_left_on_it(self):
        cfg = {**config.load_config(), "allow_unprotected_signins": True}
        proc = subprocess.Popen([str(self.process("exec sleep 300"))], start_new_session=True)
        self.addCleanup(proc.wait)
        self.kill_later(proc.pid)
        target = browser.profile_dir(cfg, "gumroad")
        target.mkdir(parents=True, exist_ok=True)
        os.symlink(f"{socket.gethostname()}-{proc.pid}", target / "SingletonLock")
        with mock.patch.object(browser, "_end_store_session", return_value=False):
            browser.sign_out(None, cfg, "gumroad", online=True)
        self.assertTrue(self.ended(proc.pid))
        self.assertFalse(target.exists())


class ABrowserThatWontOpenATab(IsolatedTestCase):
    """Some browsers won't open a tab when Hoard asks for one (Vivaldi was seen to: "Failed to open a new tab"):
    Hoard opens it from a tab that's open, as a link that opens in a new tab would, or says what to do."""

    def test_a_tab_opened_from_one_open(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright isn't installed")
        with sync_playwright() as p:
            if not Path(p.chromium.executable_path).is_file():
                self.skipTest("Playwright's Chromium isn't installed")
            ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), headless=True)
            try:
                def refuse(*args, **kwargs):
                    raise Exception("Protocol error (Target.createTarget): Failed to open a new tab")
                ctx.new_page = refuse
                browser._tabs_from_a_tab(ctx, "Vivaldi")
                tab = ctx.new_page()
                tab.set_content("<title>Hoard</title>")
                self.assertEqual(tab.title(), "Hoard")
                self.assertEqual(len(ctx.pages), 2, "a tab of its own, beside the first")
                for page in list(ctx.pages):
                    page.close()
                with self.assertRaisesRegex(RuntimeError, "Vivaldi wouldn't open a tab for Hoard .*Choose another browser"):
                    ctx.new_page()
            finally:
                ctx.close()

    def test_any_other_problem_is_said_as_it_was(self):
        ctx = mock.MagicMock()
        ctx.new_page.side_effect = RuntimeError("Target closed")
        browser._tabs_from_a_tab(ctx, "Vivaldi")
        with self.assertRaisesRegex(RuntimeError, "^Target closed$"):
            ctx.new_page()


if __name__ == "__main__":
    unittest.main()
