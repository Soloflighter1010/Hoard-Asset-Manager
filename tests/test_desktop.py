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
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import app, config  # noqa: E402
from hoard.safety import ACCESS_HEADER  # noqa: E402


class FakeEvent:
    """pywebview's window event: handlers added with +=, called with what the window reports."""
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def set(self, *args):
        """Like pywebview's: True when a handler returned False (for closing: don't close)."""
        return any([h(*args) is False for h in self.handlers])


class FakeWindow:
    def __init__(self, title, url, **kw):
        self.title, self.url, self.kw = title, url, kw
        self.shown, self.hidden, self.closed = 0, 0, threading.Event()
        self.on_top = False
        self.scripts = []
        self.events = types.SimpleNamespace(**{e: FakeEvent() for e in ("resized", "moved", "maximized", "minimized",
                                                                         "restored", "closing")})

    def restore(self): pass
    def show(self): self.shown += 1
    def hide(self): self.hidden += 1
    def evaluate_js(self, script): self.scripts.append(script)

    def close_button(self):
        """The window's own close button (and destroy(), as pywebview's does): closing handlers can say no."""
        if not self.events.closing.set():
            self.closed.set()
    destroy = close_button


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
    mod.screens = [types.SimpleNamespace(x=0, y=0, width=1920, height=1080)]
    return mod


def post(url, path, body, key=None):
    host, port = url.split("#")[0].split("//")[1].strip("/").split(":")
    c = http.client.HTTPConnection(host, int(port), timeout=10)
    c.request("POST", path, body=json.dumps(body),
              headers={"Content-Type": "application/json", **({ACCESS_HEADER: key} if key else {})})
    r = c.getresponse()
    data = r.read()
    c.close()
    return (r.status, json.loads(data or b"{}")) if path == "/api/enter" else r.status


def enter(link):
    """What Hoard's page does with the one-time link it was opened with: trade it for the access key."""
    status, data = post(link, "/api/enter", {"token": link.split("#enter=", 1)[1]})
    return data.get("key") if status == 200 else None


class _Harness(unittest.TestCase):
    """Starts Hoard as the desktop app does, with a stand-in window."""

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


class DesktopApp(_Harness):

    def test_window_one_copy_and_quit(self):
        sys.modules["webview"] = wv = fake_webview()
        t, result, info = self.start()
        window = wv.windows[0]
        self.assertEqual(window.title, "Hoard")
        self.assertTrue(window.url.startswith(info["url"] + "#enter="), "a one-time link, never the key itself")
        key = enter(window.url)
        self.assertTrue(key)
        self.assertIsNone(enter(window.url), "the link works once")
        self.assertTrue(wv.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"], "store pages open in the browser, not in Hoard")
        self.assertEqual(wv.start_kw["private_mode"], False)
        # a second copy: it asks this one to come to the front, and ends
        self.assertEqual(app.run_app(config.load_config(), None), 0)
        self.assertEqual(window.shown, 1)
        self.assertEqual(post(info["url"], "/api/show", {"token": "guess"}), 403, "only another Hoard can ask")
        # Quit Hoard: only the page, which has the key, can
        self.assertEqual(post(info["url"], "/api/quit", {}), 401)
        self.assertEqual(post(info["url"], "/api/quit", {}, key), 200)
        t.join(15)
        self.assertEqual(result.get("code"), 0)
        self.assertFalse(app.running_file().exists(), "tidied up")
        lock = app.InstanceLock(app.data_dir() / "running.lock")
        self.assertTrue(lock.acquire(), "the next start isn't blocked")
        lock.release()

    def test_the_window_opens_where_it_was(self):
        """Issue #16: the window's size and place are kept when it closes, and it opens there next time, maximized
        if it was; a place no longer on any screen isn't used, so the window never opens out of sight."""
        app.place_file().unlink(missing_ok=True)
        self.addCleanup(app.place_file().unlink, missing_ok=True)

        def run(wv, then):
            sys.modules["webview"] = wv
            t, result, info = self.start()
            window = wv.windows[-1]
            then(window)
            key = enter(window.url)
            self.assertEqual(post(info["url"], "/api/quit", {}, key), 200)
            t.join(15)
            return window.kw

        def moved_about(w):
            w.events.resized.set(1200, 800)
            w.events.moved.set(300, 120)
        kw = run(fake_webview(), moved_about)
        self.assertEqual((kw["width"], kw["height"], kw["maximized"]), (1440, 920, False), "the first time: the usual size")
        self.assertNotIn("x", kw, "centred")
        self.assertEqual(kw["min_size"], (900, 600))

        def maximized_and_minimized(w):
            w.events.maximized.set()
            w.events.resized.set(1920, 1040)   # maximized: not its own size
            w.events.minimized.set()
            w.events.moved.set(-32000, -32000)   # minimized, on Windows
            w.events.maximized.set()   # and back, maximized
        kw = run(fake_webview(), maximized_and_minimized)
        self.assertEqual((kw["width"], kw["height"], kw["x"], kw["y"], kw["maximized"]), (1200, 800, 300, 120, False))
        kw = run(fake_webview(), lambda w: w.events.restored.set())
        self.assertEqual((kw["width"], kw["height"], kw["x"], kw["y"], kw["maximized"]), (1200, 800, 300, 120, True),
                         "maximized, and restores to where it was")

        # that screen's gone: a smaller one, somewhere else
        wv = fake_webview()
        wv.screens = [types.SimpleNamespace(x=-1280, y=0, width=1280, height=720)]
        kw = run(wv, lambda w: None)
        self.assertNotIn("x", kw, "not out of sight")
        self.assertEqual((kw["width"], kw["height"]), (1200, 720), "no bigger than the screen")

    def test_where_the_window_goes_from_a_damaged_or_odd_file(self):
        path = app.place_file()
        self.addCleanup(path.unlink, missing_ok=True)
        screens = [(0, 0, 1920, 1080), (1920, 0, 2560, 1440)]
        for text, expect in [
                ("{not json", {"width": 1440, "height": 920, "maximized": False}),
                ('{"width": "wide", "height": true, "x": 5, "y": 5, "maximized": 1}', {"width": 1440, "height": 920, "x": 5, "y": 5, "maximized": False}),
                ('{"width": 50, "height": 99999, "x": 2000, "y": 10}', {"width": 1440, "height": 920, "x": 2000, "y": 10, "maximized": False}),
                ('{"width": 1000, "height": 700, "x": -900, "y": 10}', {"width": 1000, "height": 700, "maximized": False}),   # 100 px of title bar showing
                ('[1, 2]', {"width": 1440, "height": 920, "maximized": False})]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            self.assertEqual(app.window_place(screens), expect, text)
        self.assertEqual(app.window_place([]), {"width": 1440, "height": 920, "maximized": False}, "no screens known: as it was")

    def test_no_window_support_uses_the_browser(self):
        sys.modules["webview"] = fake_webview(fail=True)
        saved = app.IDLE_MINUTES
        app.IDLE_MINUTES = 0.02      # about a second
        try:
            t, result, info = self.start()
            t.join(40)
        finally:
            app.IDLE_MINUTES = saved
        self.assertEqual(len(self.opened), 1)
        self.assertTrue(self.opened[0].startswith(info["url"] + "#enter="), "a one-time link, never the key itself")
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
        # The stand-in, as the tests run from requirements.txt, which has no pywebview. The built app's own
        # self-test (hoard-cli.exe self-test, in both workflows) checks the real one.
        sys.modules["webview"] = fake_webview()
        self.assertEqual(app.self_test(), 0)


class ClosingTheWindow(_Harness):
    """What closing Hoard's window does: quit when nothing's running; while something is, ask (stop it first, carry
    on in the background, or close at once); and with Keep Hoard running, hide the window and carry on."""

    def test_decisions(self):
        srv = types.SimpleNamespace(cfg={}, jobs=types.SimpleNamespace(state={"running": False, "queue": []}))
        self.assertEqual(app.close_decision(srv), "quit")
        srv.jobs.state["running"] = True
        self.assertEqual(app.close_decision(srv), "ask")
        srv.jobs.state.update(running=False, queue=[{"id": "q1"}])
        self.assertEqual(app.close_decision(srv), "ask", "something waiting its turn counts too")
        srv.cfg["close_to_background"] = True
        self.assertEqual(app.close_decision(srv), "background")

    def test_close_button(self):
        decided = []
        sys.modules["webview"] = wv = fake_webview()
        saved = app.close_decision
        app.close_decision = lambda srv: decided[-1]
        self.addCleanup(setattr, app, "close_decision", saved)
        t, result, info = self.start()
        window = wv.windows[0]
        key = enter(window.url)
        decided.append("ask")
        window.close_button()
        time.sleep(0.3)
        self.assertFalse(window.closed.is_set(), "not closed: the page asks first")
        self.assertEqual(window.scripts, ["window.dispatchEvent(new Event('hoard-close'))"])
        decided.append("background")
        window.close_button()
        time.sleep(0.3)
        self.assertFalse(window.closed.is_set())
        self.assertEqual(window.hidden, 1, "hidden: Hoard carries on")
        self.assertEqual(app.run_app(config.load_config(), None), 0, "opening Hoard again...")
        self.assertEqual(window.shown, 1, "...brings the window back")
        decided.append("background")
        self.assertEqual(post(info["url"], "/api/quit", {}, key), 200, "Quit Hoard still quits")
        t.join(15)
        self.assertTrue(window.closed.is_set())
        self.assertEqual(result.get("code"), 0)

    def test_choices_while_working(self):
        from hoard import server as server_mod
        sys.modules["webview"] = wv = fake_webview()
        made = []
        real = server_mod.AppServer.__init__

        def remember(self_, *a, **k):
            real(self_, *a, **k)
            made.append(self_)
        with unittest.mock.patch.object(server_mod.AppServer, "__init__", remember):
            t, result, info = self.start()
        srv, window = made[-1], wv.windows[0]
        key = enter(window.url)
        release = threading.Event()
        self.addCleanup(release.set)

        def working(stores, only, keys=None, check=False, **_kw):
            srv.jobs._set(task="download", message="downloading Big.zip")
            while not srv.jobs.stop.is_set() and not release.is_set():
                time.sleep(0.05)
        with unittest.mock.patch.object(srv.jobs, "_download", working):
            srv.jobs.start("download", ["booth"])
            srv.jobs.start("download", ["gumroad"])   # waiting its turn
            for _ in range(50):
                if srv.jobs.state.get("task") == "download":
                    break
                time.sleep(0.05)
            self.assertEqual(post(info["url"], "/api/quit", {}, key), 409, "busy: the page asks what to do")
            self.assertEqual(post(info["url"], "/api/app/close", {"how": "background"}, key), 200)
            time.sleep(0.5)
            self.assertEqual(window.hidden, 1)
            self.assertFalse(window.closed.is_set())
            self.assertEqual(post(info["url"], "/api/app/close", {"how": "sideways"}, key), 400)
            self.assertEqual(post(info["url"], "/api/app/close", {"how": "wait"}, key), 200)
            t.join(15)
        self.assertTrue(window.closed.is_set(), "closed once the download had stopped")
        self.assertEqual(srv.jobs.state["queue"], [], "what was waiting was taken off the queue")
        self.assertFalse(srv.jobs.state["running"], "the download was stopped")

    def test_close_now_ends_the_browsers(self):
        srv = types.SimpleNamespace(jobs=types.SimpleNamespace(clear_queue=lambda: None, cancel=lambda: True), calls=[])
        srv.quit_app = lambda: srv.calls.append("quit")
        from hoard import browser
        with unittest.mock.patch.object(browser, "end_browsers", lambda: srv.calls.append("ended") or 1):
            app.quit_now(srv)
        self.assertEqual(srv.calls, ["ended", "quit"])

    def test_waiting_gives_up_after_a_while(self):
        """A job that won't stop (a sign-in waiting for you) doesn't keep Hoard open for ever."""
        srv = types.SimpleNamespace(jobs=types.SimpleNamespace(clear_queue=lambda: None, cancel=lambda: False,
                                                               state={"running": True}), calls=[])
        srv.quit_app = lambda: srv.calls.append("quit")
        began = time.monotonic()
        from hoard import browser
        with unittest.mock.patch.object(browser, "end_browsers", lambda: srv.calls.append("ended") or 1):
            app.quit_when_done(srv, patience=0.5)
        self.assertEqual(srv.calls, ["ended", "quit"], "its browser ended, then Hoard closed")
        self.assertLess(time.monotonic() - began, 3)


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
                       "DisableDirPage=yes", "UsePreviousAppDir=no"):
            self.assertIn(needed, iss, "the installer keeps its safe settings")
        self.assertIn("DefaultDirName={autopf}\\Hoard", iss, "always in the user's own programs folder (issue #21)")
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
