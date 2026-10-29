"""The Creator Companion's folder, shared with ALCOM: its settings.json, its project list and its Unity editors.

Both programs keep their state in VRChatCreatorCompanion in the user's local app data (Windows) or data home (Linux
and macOS, as ALCOM does). Hoard reads and writes the same files, so a project or repository added in any of the
three shows in the others:

- settings.json: repositories, package folders, the default project and backup folders, and (still, for now) the
  list of projects, "userProjects". Hoard changes only the keys it means to and keeps everything else as it was.
- vcc.liteDb: the projects again, with when each was made and opened and whether it's a favourite, and the Unity
  editors. Hoard only reads it (litedb.py). Both programs copy settings.json's list into it when they start, so a
  project Hoard adds is one they add too.

HOARD_VCC_DIR moves the folder (the tests use it, so they never touch a real one).
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from ..paths import in_flatpak
from ..safety import DataFileError, write_file_safely
from . import litedb

SETTINGS = "settings.json"
SETTINGS_BACKUP = "vrc-get/vcc-settings-backup.json"   # ALCOM's copy, read when settings.json is missing
VRC_GET_SETTINGS = "vrc-get/settings.json"
DATABASE = "vcc.liteDb"
MAX_SETTINGS = 16 << 20
_lock = threading.RLock()


def vcc_dir() -> Path:
    """The Creator Companion's folder (ALCOM's too): VRChatCreatorCompanion in your local app data, or HOARD_VCC_DIR."""
    if os.environ.get("HOARD_VCC_DIR"):
        return Path(os.environ["HOARD_VCC_DIR"]).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif in_flatpak():
        base = Path(os.environ.get("HOST_XDG_DATA_HOME") or Path.home() / ".local" / "share")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "VRChatCreatorCompanion"


def read_json(path: Path, limit: int = MAX_SETTINGS):
    """A JSON file the Creator Companion or ALCOM wrote (which may start with a byte-order mark), or None if it isn't
    there. Raises DataFileError for one too large or not JSON."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return None
    if size > limit:
        raise DataFileError(f"{path.name} is unexpectedly large")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    if not raw.strip(b"\x00 \t\r\n"):
        return None   # blank (a crash can leave one full of zeros): as if it weren't there
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError) as e:
        raise DataFileError(f"{path.name} is damaged ({e.__class__.__name__})") from None


def write_json(path: Path, data) -> None:
    """Write JSON as the Creator Companion and ALCOM do: indented two spaces, with the system's line endings."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if sys.platform == "win32":
        text = text.replace("\n", "\r\n")
    write_file_safely(path, text)


def _paths(value) -> list[str]:
    """The paths in a list from settings.json, anything that isn't one left out."""
    return [p for p in value if isinstance(p, str) and p] if isinstance(value, list) else []


class Settings:
    """settings.json, as it is on disk (every key kept), with what Hoard reads from it."""

    def __init__(self, raw: dict | None = None, folder: Path | None = None):
        self.raw = raw if isinstance(raw, dict) else {}
        self.folder = folder or vcc_dir()

    @classmethod
    def load(cls, folder: Path | None = None) -> "Settings":
        """settings.json (or ALCOM's backup of it, when it's missing); raises DataFileError when it isn't the Creator
        Companion's."""
        folder = folder or vcc_dir()
        raw = read_json(folder / SETTINGS)
        if raw is None:
            backup = read_json(folder / SETTINGS_BACKUP)
            if isinstance(backup, dict):
                backup.pop("userProjects", None)   # (ALCOM takes the list from vcc.liteDb in this case too)
                raw = backup
        if raw is not None and not isinstance(raw, dict):
            raise DataFileError("settings.json isn't the Creator Companion's settings")
        return cls(raw, folder)

    def save(self) -> None:
        """Write settings.json, and ALCOM's backup of it if it keeps one."""
        with _lock:
            write_json(self.folder / SETTINGS, self.raw)
            if (self.folder / SETTINGS_BACKUP).is_file():   # keep ALCOM's copy in step, as ALCOM does
                write_json(self.folder / SETTINGS_BACKUP, self.raw)

    # ---- what's in it

    def user_projects(self) -> list[str] | None:
        """The projects listed here, or None when the key is missing (newer Creator Companions may drop it, leaving
        vcc.liteDb the only list)."""
        return _paths(self.raw["userProjects"]) if isinstance(self.raw.get("userProjects"), list) else None

    def user_repos(self) -> list[dict]:
        """The repositories you've added."""
        repos = self.raw.get("userRepos")
        return [r for r in repos if isinstance(r, dict) and isinstance(r.get("localPath"), str)] if isinstance(repos, list) else []

    def user_package_folders(self) -> list[str]:
        """The package folders you've added."""
        return _paths(self.raw.get("userPackageFolders"))

    def show_prerelease(self) -> bool:
        """Do you want prerelease packages shown and chosen?"""
        return self.raw.get("showPrereleasePackages") is True

    def default_project_path(self) -> str | None:
        """Where new projects go, if you've chosen."""
        v = self.raw.get("defaultProjectPath")
        return v if isinstance(v, str) and v else None

    def project_backup_path(self) -> str | None:
        """Where project backups go, if you've chosen."""
        v = self.raw.get("projectBackupPath")
        return v if isinstance(v, str) and v else None

    def unity_hub(self) -> str:
        """Where Unity Hub is, if the Creator Companion knows."""
        v = self.raw.get("pathToUnityHub")
        return v if isinstance(v, str) else ""

    def unity_editors(self) -> list[str]:
        """Editors the Creator Companion was told about (older versions kept them here)."""
        return _paths(self.raw.get("unityEditors"))

    # ---- changing it

    def set_projects(self, paths: list[str]) -> None:
        """The project list (userProjects), each once."""
        self.raw["userProjects"] = list(dict.fromkeys(paths))

    def add_repo(self, entry: dict) -> None:
        """Add a repository to your list."""
        repos = self.raw.get("userRepos") if isinstance(self.raw.get("userRepos"), list) else []
        repos.append(entry)
        self.raw["userRepos"] = repos

    def remove_repos(self, local_paths: set[str]) -> list[dict]:
        """Take these repositories (by their kept file) off your list; returns the ones taken off."""
        repos = self.raw.get("userRepos") if isinstance(self.raw.get("userRepos"), list) else []
        gone = [r for r in repos if isinstance(r, dict) and r.get("localPath") in local_paths]
        self.raw["userRepos"] = [r for r in repos if r not in gone]
        return gone

    def set_package_folders(self, folders: list[str]) -> None:
        """Your package folders, each once."""
        self.raw["userPackageFolders"] = list(dict.fromkeys(folders))

    def set(self, key: str, value) -> None:
        """Change one setting."""
        self.raw[key] = value


def vrc_get_settings(folder: Path | None = None) -> dict:
    """ALCOM's own settings (vrc-get/settings.json): whether to leave out VRChat's official or curated
    repository."""
    try:
        raw = read_json((folder or vcc_dir()) / VRC_GET_SETTINGS)
    except (DataFileError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def database(folder: Path | None = None) -> dict[str, list[dict]]:
    """vcc.liteDb's projects and Unity editors, or empty lists when it isn't there or can't be read."""
    try:
        return litedb.read((folder or vcc_dir()) / DATABASE, ("projects", "unityVersions"))
    except (OSError, litedb.DatabaseError, DataFileError):
        return {"projects": [], "unityVersions": []}
