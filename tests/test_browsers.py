"""The browsers Hoard's store window can be (hoard/browser.py): Edge and Chrome by name; Brave, Vivaldi, Opera and
Opera GX where their installers put them; another Chromium browser by its program; and Hoard's own. Settings saves
the choice, the setup assistant offers those installed, and a backup never carries a program's path."""
from __future__ import annotations

import os
import plistlib
import stat
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
