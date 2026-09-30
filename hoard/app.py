"""Hoard as a desktop app: its own window, no command prompt, one copy at a time, and a clean quit.

Hoard.exe (the installed app), and `python -m hoard` without a command, start here. The window shows Hoard's pages,
served by Hoard's local server to this computer only; closing it stops the server and any store browser.

If the window can't open (no WebView2 on this PC), Hoard says so and opens in your browser instead, with a
Quit Hoard button in Settings, and stops by itself once no Hoard page has been open for a few minutes.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__
from .paths import data_dir

re_local = re.compile(r"^http://127\.0\.0\.1:\d{1,5}/")
IDLE_MINUTES = 5          # browser mode: stop this long after the last Hoard page closed
LOG_LIMIT = 20 * 1024 * 1024   # one launch's log: past this, it carries on in a new file (-part2, -part3...)


def has_console() -> bool:
    """Is there a console to print to? Not in the installed app, or when started with pythonw."""
    return sys.stdout is not None and not getattr(sys, "frozen", False)


class LaunchLog:
    """Where print() goes when there's no console: this launch's own log file, carried on in a new one (-part2...)
    if a very long run makes it larger than LOG_LIMIT, so no single file grows without end."""
    encoding, errors = "utf-8", "replace"

    def __init__(self, path: Path):
        self.first, self.part = path, 1
        self.fh = open(path, "a", encoding="utf-8", errors="replace", buffering=1)

    def write(self, text: str) -> int:
        n = self.fh.write(text)
        if self.fh.tell() > LOG_LIMIT:
            self.part += 1
            self.fh.close()
            self.fh = open(self.first.with_name(f"{self.first.stem}-part{self.part}.log"), "a", encoding="utf-8",
                           errors="replace", buffering=1)
        return n

    def flush(self) -> None:
        self.fh.flush()

    def close(self) -> None:
        self.fh.close()

    def isatty(self) -> bool:
        return False


def log_to_file() -> Path:
    """No console: whatever Hoard would print goes to this launch's own log, logs/hoard-<date>_<time>.log in its
    app-data folder. Logs are kept for 30 days (the newest 10 however old): older ones are deleted now."""
    from . import paths
    folder = paths.logs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    paths.tidy_logs()
    stamp, n = time.strftime('%Y-%m-%d_%H-%M-%S'), 1
    path = folder / f"hoard-{stamp}.log"
    while path.exists():   # started more than once within a second
        n += 1
        path = folder / f"hoard-{stamp}-{n}.log"
    sys.stdout = sys.stderr = LaunchLog(path)
    paths.current_log = path
    print(f"--- Hoard {__version__}, started {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return path


def message(text: str, title: str = "Hoard") -> None:
    """Tell the person something when there's no window yet: a message box on Windows, otherwise the log."""
    print(f"{title}: {text}")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)   # MB_ICONINFORMATION
        except Exception:
            pass


class InstanceLock:
    """Held while Hoard runs, so there's only ever one copy per user. It's the operating system's lock on a file:
    it goes away with the process, even after a crash, so a leftover file never blocks starting."""

    def __init__(self, path: Path):
        self.path, self.fh = path, None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            fh.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self.fh = fh
        return True

    def release(self) -> None:
        if self.fh:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.fh.seek(0)
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            self.fh.close()
            self.fh = None


def local_request(url: str, body: dict | None = None, timeout: float = 20, key: str | None = None):
    """A request to Hoard's own server on this computer, and nowhere else (anything that isn't
    http://127.0.0.1:<port>/ is refused), with that server's access key when given. Store traffic goes through
    egress.py; this is only Hoard talking to itself."""
    from .safety import ACCESS_HEADER
    if not re_local.match(url):
        raise ValueError("only Hoard's own server on this computer")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if key:
        headers[ACCESS_HEADER] = key
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    return urllib.request.urlopen(req, timeout=timeout)


def running_file() -> Path:
    return data_dir() / "running.json"


def show_running_copy(wait_s: float = 10.0) -> bool:
    """Ask the Hoard that's already running to bring its window to the front. It proves this request comes from
    another Hoard of the same user with the token it wrote in its private app-data folder."""
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            info = json.loads(running_file().read_text("utf-8"))
            url, token = info.get("url"), info.get("token")
            if isinstance(url, str) and url.startswith("http://127.0.0.1:") and isinstance(token, str):
                with local_request(url + "api/show", {"token": token}, timeout=3) as r:
                    if r.status == 200:
                        return True
        except (OSError, ValueError):
            pass
        time.sleep(0.5)   # it may still be starting
    return False


def token_matches(given, expected: str | None) -> bool:
    return bool(expected) and isinstance(given, str) and hmac.compare_digest(given, expected)


def window_available() -> bool:
    try:
        __import__("webview")
        return True
    except Exception:
        return False


def run_app(cfg: dict, config_path: Path | None, browser: bool = False) -> int:
    """Start Hoard for the person at the computer: its window (or the browser), until it's closed or quit."""
    from .server import serve
    lock = InstanceLock(data_dir() / "running.lock")
    if not lock.acquire():   # (before the log: a second copy only brings the first to the front, and keeps no log)
        if show_running_copy():
            return 0
        message("Hoard is already running, but isn't answering. Close it (or restart your computer) and open it again.")
        return 1
    log_path = log_to_file() if not has_console() else None
    from . import diagnostics
    diagnostics.install_exception_hooks()

    token = secrets.token_urlsafe(24)
    ready, state = threading.Event(), {}

    def on_ready(url, srv):
        state.update(url=url, srv=srv)
        srv.show_token = token
        ready.set()

    threading.Thread(target=serve, kwargs=dict(cfg=cfg, port=0, open_browser=False, config_path=config_path,
                                               on_ready=on_ready), daemon=True, name="server").start()
    try:
        if not ready.wait(30):
            message("Hoard's local server didn't start." + (f" Details are in {log_path}." if log_path else ""))
            return 1
        url, srv = state["url"], state["srv"]
        from . import updater
        updater.tidy()
        srv.updates.check_in_background()
        srv.start_schedule()
        from .safety import write_file_safely
        write_file_safely(running_file(), json.dumps({"url": url, "token": token, "pid": os.getpid()}))
        if os.name == "posix":
            os.chmod(running_file(), 0o600)
        opened = False
        if not browser and window_available():
            try:
                open_window(srv)
                opened = True
            except Exception as e:   # typically: no WebView2 on this PC
                print(f"The window couldn't open ({type(e).__name__}: {e}); using the browser instead.")
                message("Hoard's window couldn't open on this PC, so Hoard opens in your web browser instead.\n\n"
                        "To quit Hoard, choose Settings, then Quit Hoard.")
        if not opened:
            run_in_browser(srv)
        return 0
    finally:
        quit_cleanly(state.get("srv"))
        try:
            running_file().unlink(missing_ok=True)
        except OSError:
            pass
        lock.release()
        if state.get("srv") is not None:   # an update Hoard quit for: its installer runs now that Hoard has stopped
            from . import updater
            updater.finish(state["srv"].updates)


DEFAULT_SIZE, MIN_SIZE = (1440, 920), (900, 600)


def place_file() -> Path:
    return data_dir() / "window-place.json"


def _screens(webview) -> list[tuple[int, int, int, int]]:
    """Each screen's x, y, width and height (in the same units as the window's), or [] when they can't be read."""
    try:
        return [(int(s.x), int(s.y), int(s.width), int(s.height)) for s in webview.screens][:16]
    except Exception:
        return []


def window_place(screens: list[tuple[int, int, int, int]]) -> dict:
    """Where the window opens (issue #16): its size and place when it was last closed, and maximized if it was.
    A place that's no longer on any screen (a screen unplugged, or its resolution lowered) isn't used, so the
    window never opens out of sight; it opens centred instead, no bigger than the screen."""
    from .safety import DataFileError, read_json_file
    try:
        raw = read_json_file(place_file(), 64 * 1024) if place_file().exists() else {}
    except (DataFileError, OSError, ValueError, RecursionError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}

    def number(key, low, high):
        v = raw.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) and low <= v <= high else None

    width, height = number("width", MIN_SIZE[0], 16384) or DEFAULT_SIZE[0], number("height", MIN_SIZE[1], 16384) or DEFAULT_SIZE[1]
    x, y = number("x", -32768, 32768), number("y", -32768, 32768)
    place = {"width": width, "height": height, "maximized": raw.get("maximized") is True}
    # the screen the title bar is on: enough of it showing to take hold of (120 by 40)
    home = next((s for s in screens if x is not None and y is not None
                 and min(x + width, s[0] + s[2]) - max(x, s[0]) >= 120 and s[1] <= y <= s[1] + s[3] - 40), None)
    if home:
        place.update(x=x, y=y)
    fit = home or (max(screens, key=lambda s: s[2] * s[3]) if screens else None)
    if fit:   # never bigger than the screen it's on (the minimum size still stands)
        place["width"] = max(MIN_SIZE[0], min(place["width"], fit[2]))
        place["height"] = max(MIN_SIZE[1], min(place["height"], fit[3]))
    return place


class PlaceKeeper:
    """Follows the window's size and place from its events, to save when it closes. Only a normal window's are
    kept, so a maximized or minimized one comes back to where it was before. (Nothing here asks the window for its
    size: on macOS that waits for the main thread, which is the one closing it.)"""

    def __init__(self, place: dict):
        self.place = dict(place)
        self.minimized = False

    def watch(self, window) -> None:
        events = getattr(window, "events", None)
        if events is None:
            return
        events.resized += self.resized
        events.moved += self.moved
        events.maximized += self.maximized
        events.minimized += self.minimize
        events.restored += self.restored

    def resized(self, width, height):
        if not (self.place["maximized"] or self.minimized) and width >= MIN_SIZE[0] // 2 and height >= MIN_SIZE[1] // 2:
            self.place.update(width=int(width), height=int(height))

    def moved(self, x, y):
        if not (self.place["maximized"] or self.minimized) and -10000 < x < 32768 and -10000 < y < 32768:
            self.place.update(x=int(x), y=int(y))   # (a minimized window on Windows is "at" -32000)

    def maximized(self):
        self.place["maximized"], self.minimized = True, False

    def minimize(self):
        self.minimized = True

    def restored(self):
        self.place["maximized"], self.minimized = False, False

    def save(self) -> None:
        from .safety import write_file_safely
        keep = {k: self.place[k] for k in ("width", "height", "x", "y", "maximized") if k in self.place}
        try:
            write_file_safely(place_file(), json.dumps(keep))
        except OSError as e:
            print(f"Couldn't save the window's size and place: {e}")


def open_window(srv) -> None:
    """Hoard's own window, opened with a one-time link to its page, where it was last time. Blocks until it's
    closed."""
    import webview
    try:
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # store pages open in your browser, not in Hoard
        webview.settings["ALLOW_DOWNLOADS"] = False
    except Exception:
        pass
    keeper = PlaceKeeper(window_place(_screens(webview)))
    window = webview.create_window("Hoard", srv.entry_url(), min_size=MIN_SIZE, background_color="#221c17",
                                   text_select=True, **keeper.place)
    keeper.watch(window)
    leaving = threading.Event()   # set once Hoard is really quitting: the window may close then

    def show():
        window.show()
        window.restore()
        window.on_top = True    # to the front, without staying there
        window.on_top = False

    def quit_app():
        leaving.set()
        window.destroy()

    def closing():
        """The window's close button. Runs on the window's own thread and decides at once: anything that touches
        the window (hiding it, asking the page) happens on another thread, or it would wait for itself."""
        if leaving.is_set():
            return True
        decision = close_decision(srv)
        if decision == "quit":
            leaving.set()
            return True
        if decision == "background":
            threading.Thread(target=window.hide, daemon=True).start()
        else:   # something's running: the page asks what to do (stop it first, the background, or now)
            threading.Thread(target=window.evaluate_js, args=("window.dispatchEvent(new Event('hoard-close'))",),
                             daemon=True).start()
        return False

    srv.show_window = show
    srv.hide_window = window.hide
    srv.quit_app = quit_app
    window.events.closing += closing
    storage = data_dir() / "window"
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=str(storage))
    keeper.save()   # once it's closed (and only when it opened)


def run_in_browser(srv) -> None:
    """No window: open Hoard in the web browser, and run until Quit Hoard, or until no Hoard page has been open
    for IDLE_MINUTES (every open page checks in once a minute). Each time it's opened, it's with a new one-time
    link: a browser's command line can be read by other accounts on some systems, so it never carries the key."""
    stop = threading.Event()
    srv.quit_app = stop.set
    srv.show_window = lambda: webbrowser.open(srv.entry_url())
    webbrowser.open(srv.entry_url())
    while not stop.wait(15):
        idle = time.time() - getattr(srv, "last_seen", time.time())
        if idle > IDLE_MINUTES * 60 and not srv.jobs.state.get("running"):
            print("No Hoard page has been open for a while, so Hoard stopped.")
            break


def close_decision(srv) -> str:
    """What closing Hoard's window does: "background" (it's hidden, and Hoard carries on: you chose that in
    Settings), "ask" (something is running or waiting its turn: the page asks whether to stop it first, carry on in
    the background, or close at once), or "quit"."""
    if srv.cfg.get("close_to_background"):
        return "background"
    if srv.jobs.state.get("running") or srv.jobs.state.get("queue"):
        return "ask"
    return "quit"


def quit_when_done(srv, patience: float = 120.0) -> None:
    """Close Hoard once what's running has stopped: what's waiting is taken off the queue, and a download or sync is
    stopped (its browser ended if it has stopped answering); anything else (a refresh, a sign-in) is let finish.
    After patience seconds, Hoard closes anyway, ending any store browser still open."""
    srv.jobs.clear_queue()
    srv.jobs.cancel()
    deadline = time.monotonic() + patience
    while srv.jobs.state.get("running") and time.monotonic() < deadline:
        time.sleep(0.25)
    if srv.jobs.state.get("running"):
        from .browser import end_browsers
        end_browsers()
    if srv.quit_app:
        srv.quit_app()


def quit_now(srv) -> None:
    """Close Hoard at once, whatever it's doing: for when waiting doesn't help. What's waiting is dropped, a
    download is stopped where it is (a half-downloaded file resumes next time, where the store allows), and every
    store browser is ended."""
    from .browser import end_browsers
    srv.jobs.clear_queue()
    srv.jobs.cancel()
    end_browsers()
    if srv.quit_app:
        srv.quit_app()


def quit_cleanly(srv) -> None:
    """Stop a running download (it resumes next time), then the server. Store browsers close with Hoard."""
    if srv is None:
        return
    try:
        srv.jobs.cancel()
        for _ in range(20):   # up to ~5 s for the file being written to finish
            if not srv.jobs.state.get("running"):
                break
            time.sleep(0.25)
        srv.shutdown()
        srv.server_close()
    except Exception as e:
        print(f"While quitting: {type(e).__name__}: {e}")


def self_test() -> int:
    """For the build: can this copy of Hoard find its pages, fonts and words, serve them, and reach Playwright's
    driver? Prints what it checked; returns 0 when everything's there."""
    import tempfile
    from .paths import WEB
    problems, checks = [], []

    def check(name, ok, detail=""):
        checks.append(name)
        print(("ok      " if ok else "MISSING ") + name + (f"  ({detail})" if detail and not ok else ""))
        if not ok:
            problems.append(name)

    check("pages", (WEB / "library.html").is_file() and (WEB / "downloads.html").is_file(), str(WEB))
    check("fonts", len(list((WEB / "fonts").glob("*.woff2"))) >= 3)
    from .marks import WORDS
    check("recovery words", len(WORDS) == 2048)
    try:
        from playwright._impl._driver import compute_driver_executable
        node, cli = compute_driver_executable()
        check("Playwright's driver", Path(node).is_file() and Path(cli).is_file(), f"{node}, {cli}")
    except Exception as e:
        check("Playwright's driver", False, repr(e))
    check("window support (pywebview)", window_available() or sys.platform != "win32")
    os.environ.setdefault("HOARD_DATA_DIR", tempfile.mkdtemp(prefix="hoard-self-test-"))
    from .config import load_config
    from .server import AppServer
    srv = AppServer(("127.0.0.1", 0), load_config(), lan=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_port}"
        for path in ("/", "/downloads", "/fonts/DelaGothicOne-Regular.woff2", "/api/status", "/api/setup"):
            try:
                with local_request(base + path, key=srv.key) as r:
                    check("serves " + path, r.status == 200 and len(r.read()) > 0)
            except OSError as e:
                check("serves " + path, False, repr(e))
    finally:
        srv.shutdown()
        srv.server_close()
    print(f"Hoard {__version__} self-test: {len(checks) - len(problems)} of {len(checks)} ok")
    return 1 if problems else 0
