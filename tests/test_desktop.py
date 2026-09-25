"""Hoard as a desktop app (hoard/app.py): its window, one copy at a time, quitting, and the browser fallback.
pywebview is replaced by a stand-in that records what Hoard asks of the window."""
from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import app, config  # noqa: E402


class FakeWindow:
    def __init__(self, title, url, **kw):
        self.title, self.url, self.kw = title, url, kw
        self.shown, self.closed = 0, threading.Event()
        self.on_top = False

    def restore(self): pass
    def show(self): self.shown += 1
    def destroy(self): self.closed.set()


def fake_webview(fail=False):
    mod = types.ModuleType("webview")
    mod.settings = {}
    mod.windows = []

    def create_window(title, url, **kw):
        w = FakeWindow(title, url, **kw)
        mod.windows.append(w)
        return w

    def start(**kw):
        if fail:
            raise RuntimeError("WebView2 is not installed")
        mod.start_kw = kw
        mod.windows[-1].closed.wait(30)
    mod.create_window, mod.start = create_window, start
    return mod


def post(url, path, body):
    host, port = url.split("//")[1].strip("/").split(":")
    c = http.client.HTTPConnection(host, int(port), timeout=10)
    c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
    r = c.getresponse()
    r.read()
    c.close()
    return r.status


class DesktopApp(unittest.TestCase):

    def setUp(self):
        self.saved = sys.modules.get("webview"), app.message, app.webbrowser.open, app.has_console
        app.message = lambda text, title="Hoard": self.messages.append(text)
        app.webbrowser.open = lambda url: self.opened.append(url)
        app.has_console = lambda: True
        self.messages, self.opened = [], []
        app.running_file().unlink(missing_ok=True)

    def tearDown(self):
        webview, app.message, app.webbrowser.open, app.has_console = self.saved
        if webview is None:
            sys.modules.pop("webview", None)
        else:
            sys.modules["webview"] = webview

    def start(self, **kw):
        result = {}
        t = threading.Thread(target=lambda: result.update(code=app.run_app(config.load_config(), None, **kw)), daemon=True)
        t.start()
        for _ in range(100):
            if app.running_file().exists():
                break
            time.sleep(0.1)
        return t, result, json.loads(app.running_file().read_text())

    def test_window_one_copy_and_quit(self):
        sys.modules["webview"] = wv = fake_webview()
        t, result, info = self.start()
        window = wv.windows[0]
        self.assertEqual((window.title, window.url), ("Hoard", info["url"]))
        self.assertTrue(wv.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"], "store pages open in the browser, not in Hoard")
        self.assertEqual(wv.start_kw["private_mode"], False)
        # a second copy: it asks this one to come to the front, and ends
        self.assertEqual(app.run_app(config.load_config(), None), 0)
        self.assertEqual(window.shown, 1)
        self.assertEqual(post(info["url"], "/api/show", {"token": "guess"}), 403, "only another Hoard can ask")
        # Quit Hoard
        self.assertEqual(post(info["url"], "/api/quit", {}), 200)
        t.join(15)
        self.assertEqual(result.get("code"), 0)
        self.assertFalse(app.running_file().exists(), "tidied up")
        lock = app.InstanceLock(app.data_dir() / "running.lock")
        self.assertTrue(lock.acquire(), "the next start isn't blocked")
        lock.release()

    def test_no_window_support_uses_the_browser(self):
        sys.modules["webview"] = fake_webview(fail=True)
        saved = app.IDLE_MINUTES
        app.IDLE_MINUTES = 0.02      # about a second
        try:
            t, result, info = self.start()
            t.join(40)
        finally:
            app.IDLE_MINUTES = saved
        self.assertEqual(self.opened, [info["url"]])
        self.assertTrue(any("browser" in m for m in self.messages))
        self.assertEqual(result.get("code"), 0, "stopped by itself once no page was open")

    def test_log_instead_of_a_console(self):
        saved = sys.stdout, sys.stderr
        try:
            path = app.log_to_file()
            print("hello from a test")
        finally:
            sys.stdout.close()
            sys.stdout, sys.stderr = saved
        self.assertIn("hello from a test", path.read_text("utf-8"))
        self.assertEqual(path.parent, app.data_dir() / "logs")

    def test_self_test(self):
        self.assertEqual(app.self_test(), 0)


class Packaging(unittest.TestCase):
    """The Windows app's build: PyInstaller spec, installer, locked dependencies, icon and workflows."""

    def test_spec_and_entry_points(self):
        spec = (REPO / "packaging" / "hoard.spec").read_text()
        for needed in ('"hoard" / "web"', "recovery_words.txt", 'collect_data_files("playwright")',
                       'program(app, "Hoard", console=False)', 'program(cli, "hoard-cli", console=True)'):
            self.assertIn(needed, spec)
        self.assertIn("from hoard.cli import main", (REPO / "packaging" / "hoard_app.py").read_text())
        self.assertIn("from hoard.cli import main", (REPO / "packaging" / "hoard_cli.py").read_text())

    def test_installer(self):
        iss = (REPO / "packaging" / "hoard.iss").read_text()
        for needed in ("AppId={{E17FA814-69F9-5056-A999-C60F80574E31}", "PrivilegesRequired=lowest",
                       'Type: filesandordirs; Name: "{app}\\_internal"', "CloseApplications=force", "Source: \"..\\dist\\Hoard\\*\"",
                       "UsePreviousAppDir=yes"):
            self.assertIn(needed, iss, "the installer keeps its safe settings")
        self.assertNotIn("{localappdata}\\Hoard", iss, "never touches Hoard's own data folder")

    def test_app_dependencies_are_locked_and_match(self):
        import re
        app_lock = (REPO / "requirements-app.txt").read_text()
        blocks = [b for b in re.split(r"\n(?=[A-Za-z0-9_.-]+==)", app_lock) if re.match(r"[A-Za-z0-9_.-]+==", b)]
        self.assertTrue(blocks and all("--hash=sha256:" in b for b in blocks))
        pins = lambda text: dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", text, re.M))
        app, source = pins(app_lock), pins((REPO / "requirements.txt").read_text())
        for name in ("pywebview", "pyinstaller", "pythonnet"):
            self.assertIn(name, app)
        for name, version in source.items():
            self.assertEqual(app.get(name), version, f"{name}: the app and a source install use the same version")

    def test_icon(self):
        import struct
        ico = (REPO / "packaging" / "hoard.ico").read_bytes()
        count = struct.unpack("<H", ico[4:6])[0]
        sizes = {ico[6 + 16 * n] or 256 for n in range(count)}
        self.assertTrue({16, 32, 48, 256} <= sizes, sizes)

    def test_workflows(self):
        release = (REPO / ".github" / "workflows" / "release.yml").read_text()
        check = (REPO / ".github" / "workflows" / "check.yml").read_text()
        self.assertIn("needs: release", release)
        for wf in (release, check):
            self.assertIn("hoard-cli.exe self-test", wf)
            self.assertIn("--require-hashes -r requirements-app.txt", wf)

    def test_launcher_leaves_no_console(self):
        bat = (REPO / "Hoard.bat").read_text()
        self.assertIn('start "" ".venv\\Scripts\\pythonw.exe" -m hoard', bat)

    def test_packaged_app_skips_the_source_check(self):
        main = (REPO / "hoard" / "__main__.py").read_text()
        self.assertIn('getattr(sys, "frozen", False)', main)
        self.assertIn("_init.is_file()", main)


if __name__ == "__main__":
    unittest.main()
