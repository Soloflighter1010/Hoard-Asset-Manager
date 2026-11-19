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


def in_flatpak() -> bool:
    """Is this Hoard the Flatpak (packaging/flatpak), running in its sandbox?"""
    return bool(os.environ.get("FLATPAK_ID")) or Path("/.flatpak-info").exists()


def base_dir() -> Path:
    """Hoard's private folder where it starts out, in this user account's app data (HOARD_DATA_DIR moves it: tests,
    portable use). Its location.json says where you moved its folders to, if you did (issue #385)."""
    if os.environ.get("HOARD_DATA_DIR"):
        return Path(os.environ["HOARD_DATA_DIR"]).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif in_flatpak():
        # The Flatpak sets XDG_DATA_HOME to its own folder (~/.var/app/...); Hoard keeps using the one every Linux
        # Hoard uses (it can see your home folder), so your library carries over and Hoard for Unity finds it.
        base = Path(os.environ.get("HOST_XDG_DATA_HOME") or Path.home() / ".local" / "share")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Hoard"


# ---- where you moved Hoard's folders to (issue #385): location.json in base_dir(), {"data", "logs", "backups",
# "reports", "vcc": an absolute path}. Read once (Hoard's own folder and logs move only as Hoard starts), kept in step
# when one that can change while Hoard runs is changed.
POINTER = "location.json"
PENDING = "move-pending.json"   # a move of Hoard's own folder, its logs or its sign-ins, made as Hoard next starts
PLACES = ("data", "logs", "backups", "reports", "vcc")
_moved: tuple[Path, dict] | None = None   # (the base folder it was read from, what it says)
FIXED = ("data", "logs")                  # where these are is decided once a run (placed())
_fixed: dict = {}                         # {(base, place, path): whether it was there}


def moved() -> dict:
    """Where you moved Hoard's folders to: {place: path}, only those you moved."""
    global _moved
    base = base_dir()
    if _moved is None or _moved[0] != base:
        import json
        try:
            raw = json.loads((base / POINTER).read_text("utf-8"))
        except (OSError, ValueError):
            raw = {}
        _moved = (base, {k: v for k, v in raw.items() if k in PLACES and isinstance(v, str) and Path(v).is_absolute()}
                  if isinstance(raw, dict) else {})
    return _moved[1]


def set_moved(place: str, path: str | None) -> None:
    """Note that a folder is somewhere else now (None: back where it started)."""
    import json
    from .safety import write_file_safely
    now = {**moved()}
    if path:
        now[place] = str(path)
    else:
        now.pop(place, None)
    base_dir().mkdir(parents=True, exist_ok=True)
    write_file_safely(base_dir() / POINTER, json.dumps(now, indent=1, ensure_ascii=False))
    global _moved
    _moved = (base_dir(), now)
    _fixed.clear()


def placed(place: str) -> Path | None:
    """Where a folder you moved is now (one that's there), else None. For Hoard's own folder and its logs, whether
    it's there is looked at once a run: one on a drive that's away isn't swapped in part way through."""
    value = moved().get(place)
    if not value:
        return None
    if place not in FIXED:
        return Path(value) if Path(value).is_dir() else None
    key = (base_dir(), place, value)
    if key not in _fixed:
        _fixed[key] = Path(value).is_dir()
    return Path(value) if _fixed[key] else None


def data_dir() -> Path:
    """Hoard's private folder: base_dir(), or where you moved it to (issue #385)."""
    return placed("data") or base_dir()


def on_network(path) -> bool:
    """Is this folder on a network share or a network drive (where Hoard's own data, its sign-ins and a sync folder
    can't go: issues #385, #388)? Windows: a \\server path or a mapped network drive; elsewhere: a folder whose mount is a
    network file system (NFS, SMB, AFP, WebDAV, SSHFS...)."""
    p = Path(path)
    text = os.fspath(path)   # (as given: a Windows path object would turn a POSIX path's / into \\)
    if text.startswith(("\\\\", "//")):
        return True
    if sys.platform == "win32":
        try:
            import ctypes
            return ctypes.windll.kernel32.GetDriveTypeW(str(p.anchor)) == 4   # DRIVE_REMOTE
        except Exception:
            return False
    try:
        real = os.path.realpath(text)
    except OSError:
        return False
    best, kind = "", ""
    for mount, fs in _mounts():
        if (real == mount or real.startswith(mount.rstrip("/") + "/")) and len(mount) >= len(best):
            best, kind = mount, fs
    return kind.lower() in NETWORK_FS or kind.lower().startswith(("fuse.sshfs", "fuse.rclone", "nfs"))


NETWORK_FS = {"nfs", "nfs4", "cifs", "smb", "smb2", "smb3", "smbfs", "afpfs", "webdav", "davfs", "fuse.sshfs", "sshfs",
              "9p", "afs", "ncpfs", "glusterfs", "ceph", "fuse.rclone"}


def _mounts() -> list[tuple[str, str]]:
    """(mount point, file system type) for each mount: /proc/mounts on Linux, `mount` on macOS."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/mounts", encoding="utf-8") as f:
                return [(parts[1].replace("\\040", " "), parts[2]) for parts in (line.split() for line in f) if len(parts) > 2]
        except OSError:
            return []
    if sys.platform == "darwin":
        import re
        import subprocess
        try:
            out = subprocess.run(["/sbin/mount"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        return [(m.group(1), m.group(2)) for m in re.finditer(r" on (.+?) \(([^,)]+)", out)]
    return []


LOG_DAYS = 30        # a launch's log is kept this many days...
LOG_KEEP = 10        # ...and the newest few are kept however old they are
current_log: Path | None = None   # this launch's log, when Hoard runs without a console (app.log_to_file)


def logs_dir() -> Path:
    """Where Hoard keeps its logs: in its own folder, or where you moved them to (issue #385)."""
    return placed("logs") or data_dir() / "logs"


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
