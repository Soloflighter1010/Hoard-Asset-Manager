"""Where Hoard keeps things.

The program itself may sit somewhere you can't write to, such as an installed app. Everything Hoard saves
for you (settings, your library list, sign-ins, tags, cached images) lives in its private app-data folder
instead, and downloads go to the folder you choose.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
WEB = PACKAGE / "web"   # the pages, and their fonts


def data_dir() -> Path:
    """Hoard's private folder in this user account's app data. HOARD_DATA_DIR moves it (tests, portable use)."""
    if os.environ.get("HOARD_DATA_DIR"):
        return Path(os.environ["HOARD_DATA_DIR"]).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Hoard"


LOG_DAYS = 30        # a launch's log is kept this many days...
LOG_KEEP = 10        # ...and the newest few are kept however old they are
current_log: Path | None = None   # this launch's log, when Hoard runs without a console (app.log_to_file)


def logs_dir() -> Path:
    return data_dir() / "logs"


def log_files() -> list[Path]:
    """Hoard's logs, newest first: one per launch (hoard-<date>_<time>.log, and -part2... for a very long run), and
    the single log of versions before 2.9.2 (hoard.log, hoard.old.log) until it's 30 days old."""
    found = []
    try:
        for p in logs_dir().iterdir():
            if p.suffix == ".log" and (p.name.startswith("hoard-") or p.name in ("hoard.log", "hoard.old.log")):
                try:
                    found.append((p.stat().st_mtime, p))
                except OSError:
                    pass
    except OSError:
        return []
    return [p for _, p in sorted(found, key=lambda t: (t[0], t[1].name), reverse=True)]   # (same time: by name)


def tidy_logs(now: float | None = None) -> int:
    """Delete logs more than LOG_DAYS old, keeping the newest LOG_KEEP whatever their age. Returns how many went."""
    import time
    now = time.time() if now is None else now
    gone = 0
    for p in log_files()[LOG_KEEP:]:
        try:
            if now - p.stat().st_mtime > LOG_DAYS * 86400:
                p.unlink()
                gone += 1
        except OSError:
            pass
    return gone


def store_python() -> bool:
    """Is this Hoard running on Microsoft Store Python? Windows keeps a Store app's AppData separately (its writes
    go to a private copy under AppData\\Local\\Packages), so that Hoard has its own settings and sealing key,
    apart from the installed Hoard app and the Unity window."""
    if sys.platform != "win32":
        return False
    where = f"{sys.executable} {sys.prefix} {getattr(sys, 'base_prefix', '')}"
    return "PythonSoftwareFoundation.Python" in where or "\\WindowsApps\\" in where


STORE_PYTHON_NOTE = ("This Hoard is running on Microsoft Store Python. Windows keeps its files apart from the installed "
                     "Hoard app's (a private copy of AppData), so its settings, sign-ins and sealing key are separate, "
                     "and the Unity window may call its catalog 'sealed elsewhere'. Use the installed Hoard app, or "
                     "Python from python.org, to share one set.")


DATA = data_dir()
HERE = DATA                                    # relative paths in settings are taken from here
CONFIG_FILE = DATA / "config.json"
LIBRARY_FILE = DATA / "library.json"
THUMB_DIR = DATA / "cache" / "thumbs"
DEBUG_DIR = DATA / "debug"
PROBE_DIR = DATA / "debug" / "jinxxy"


def documents_dir() -> Path:
    """Your Documents folder (on Windows, wherever it really is, OneDrive included)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # 5: My Documents
                return Path(buf.value)
        except (OSError, AttributeError):
            pass
    docs = Path.home() / "Documents"
    return docs if docs.is_dir() else Path.home()


def default_downloads() -> Path:
    """Where downloads go unless you choose somewhere else: a Hoard folder in Documents."""
    return documents_dir() / "Hoard"
