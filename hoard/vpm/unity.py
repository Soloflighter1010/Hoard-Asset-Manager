"""Unity editors: finding the ones installed, telling whether a project is open in one, and opening it.

Editors are found as ALCOM finds them, from Unity Hub's own records: the folder Hub installs to (and the one you
chose in Hub's settings), Hub's editors-v2.json (editors you located by hand), plus the ones the Creator Companion
lists in vcc.liteDb. A project is open while Unity holds Temp/UnityLockFile locked.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .version import UnityVersion

FOLDER_NAME = re.compile(r"\d+\.\d+\.\d+[abfpcx]\d+(c\d+)?(-.*)?")


def _hub_user_data() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "UnityHub"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "UnityHub"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "unityhub"


def _hub_install_folder() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMFILES") or "C:\\Program Files") / "Unity" / "Hub" / "Editor"
    if sys.platform == "darwin":
        return Path("/Applications/Unity/Hub/Editor")
    return Path.home() / "Unity" / "Hub" / "Editor"


def _global_config() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("ALLUSERSPROFILE") or "C:\\ProgramData") / "Unity" / "config"
    if sys.platform == "darwin":
        return Path("/Library/Application Support/Unity/config")
    return Path("/usr/share/unity3d/config")


def editor_in(folder: Path) -> Path:
    """The editor program in one of Hub's version folders."""
    if sys.platform == "win32":
        return folder / "Editor" / "Unity.exe"
    if sys.platform == "darwin":
        return folder / "Unity.app"
    return folder / "Editor" / "Unity"


def _read(path: Path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.loads(f.read(1 << 20))
    except (OSError, ValueError):
        return None


def _secondary_folder() -> Path | None:
    chosen = _read(_hub_user_data() / "secondaryInstallPath.json")
    if isinstance(chosen, str) and chosen:
        return Path(chosen)
    for path in (_hub_user_data() / "settings.json", _global_config() / "services-config.json", _hub_user_data() / "Settings"):
        raw = _read(path)
        if isinstance(raw, dict) and isinstance(raw.get("machineWideSecondaryInstallLocation"), str) \
                and raw["machineWideSecondaryInstallLocation"]:
            return Path(raw["machineWideSecondaryInstallLocation"])
    return None


def _in_folder(folder: Path) -> list[tuple[UnityVersion, Path]]:
    found = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return found
    for e in entries:
        if not FOLDER_NAME.fullmatch(e.name):
            continue
        exe = editor_in(Path(e.path))
        version = UnityVersion.parse(e.name)   # ("2022.3.22f1-x86_64" too: what follows a dash is left out)
        if version is not None and exe.exists():
            found.append((version, exe))
    return found


def find_editors(database: list[dict] | None = None) -> list[dict]:
    """Every Unity editor found: [{"version", "path"}], newest first, one per path."""
    found: list[tuple[UnityVersion, Path]] = []
    hub = _hub_install_folder()
    found += _in_folder(hub)
    second = _secondary_folder()
    if second is not None and second != hub:
        found += _in_folder(second)
    located = _read(_hub_user_data() / "editors-v2.json")
    for entry in (located.get("data") if isinstance(located, dict) and isinstance(located.get("data"), list) else []):
        if not isinstance(entry, dict):
            continue
        version = UnityVersion.parse(entry.get("version"))
        where = entry.get("location")
        for loc in ([where] if isinstance(where, str) else where if isinstance(where, list) else []):
            if version is not None and isinstance(loc, str) and Path(loc).exists():
                found.append((version, Path(loc)))
    for doc in database or []:
        version, where = UnityVersion.parse(doc.get("Version")), doc.get("Path")
        if version is not None and isinstance(where, str) and Path(where).exists():
            found.append((version, Path(where)))
    seen, out = set(), []
    for version, path in sorted(found, key=lambda x: x[0], reverse=True):
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            out.append({"version": str(version), "path": str(path)})
    return out


def editor_for(version: UnityVersion | None, editors: list[dict]) -> dict | None:
    """The editor for a project's Unity version: the same version (China's c-releases count as the same)."""
    if version is None:
        return None
    return next((e for e in editors if UnityVersion.parse(e["version"]) == version), None)


# ---- is it open?

def project_open_in_unity(project: Path) -> bool:
    """Whether Unity has the project open: it holds Temp/UnityLockFile locked while it does."""
    lock = Path(project) / "Temp" / "UnityLockFile"
    if not lock.is_file():
        return False
    if sys.platform == "win32":
        try:
            fh = open(lock, "a+b")
        except PermissionError:
            return True       # (Unity opens it without sharing it)
        except OSError:
            return False
        try:
            import msvcrt
            fh.seek(0)
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            return False
        finally:
            fh.close()
    import fcntl
    try:
        fh = open(lock, "rb")
    except OSError:
        return False
    try:
        try:
            fcntl.lockf(fh.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.lockf(fh.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        fh.close()


# ---- opening it

def program(editor: Path) -> Path:
    """The program to start for an editor (on a Mac, the one inside Unity.app)."""
    editor = Path(editor)
    if sys.platform == "darwin" and editor.suffix == ".app":
        return editor / "Contents" / "MacOS" / "Unity"
    return editor


def open_project(editor: Path, project: Path, extra_args: list[str] | None = None) -> None:
    """Start Unity on the project, on its own: closing Hoard doesn't close Unity."""
    exe = program(editor)
    if not exe.is_file():
        raise FileNotFoundError(f"Unity isn't at {exe} any more.")
    args = [str(exe), "-projectPath", str(project), *(extra_args or [])]
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "close_fds": True, "cwd": str(project)}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)
