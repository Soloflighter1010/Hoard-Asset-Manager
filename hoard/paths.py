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
