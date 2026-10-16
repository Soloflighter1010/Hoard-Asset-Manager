"""A Unity project as VPM sees it: its Unity version, its packages and its two manifests.

- Packages/vpm-manifest.json: "dependencies" (what you asked for, by range) and "locked" (exactly what's installed,
  with each one's own dependencies). The Creator Companion and ALCOM keep it; so does Hoard, the same way.
- Packages/manifest.json: Unity's own package list. Read only, to tell what kind of project it is.
- Packages/<name>/package.json: what's really there. A package folder that's in "locked" is installed; one that
  isn't is the project's own (copied in by hand, or by Hoard from your library): left alone, but its dependencies
  still count.
- ProjectSettings/ProjectVersion.txt: the Unity version it was last opened in.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..safety import DataFileError
from . import environment
from .manifest import Package, valid_name
from .version import DependencyRange, UnityVersion, Version, VersionError, VersionRange

VPM_MANIFEST = "Packages/vpm-manifest.json"
UPM_MANIFEST = "Packages/manifest.json"
PROJECT_VERSION = "ProjectSettings/ProjectVersion.txt"

# What kind of project it is, numbered as vcc.liteDb numbers them
UNKNOWN, LEGACY_SDK2, LEGACY_WORLDS, LEGACY_AVATARS, UPM_WORLDS, UPM_AVATARS, UPM_STARTER, WORLDS, AVATARS, \
    VPM_STARTER = range(10)
TYPE_NAMES = {UNKNOWN: "Unknown", LEGACY_SDK2: "Legacy SDK2", LEGACY_WORLDS: "Legacy Worlds",
              LEGACY_AVATARS: "Legacy Avatars", UPM_WORLDS: "UPM Worlds", UPM_AVATARS: "UPM Avatars",
              UPM_STARTER: "UPM Starter", WORLDS: "Worlds", AVATARS: "Avatars", VPM_STARTER: "VPM Starter"}


class ProjectError(Exception):
    """A folder that isn't a Unity project this can work with, in words to show."""


def is_project(folder: Path) -> bool:
    return (folder / PROJECT_VERSION).is_file() or ((folder / "Assets").is_dir() and (folder / "ProjectSettings").is_dir())


def read_unity_version(folder: Path) -> tuple[UnityVersion | None, str | None]:
    """The Unity version in ProjectVersion.txt, and its revision (the hash in "2022.3.22f1 (887be4894c44)")."""
    try:
        with open(folder / PROJECT_VERSION, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(64 * 1024)
    except OSError:
        return None, None
    version = revision = None
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "m_EditorVersion":
            version = UnityVersion.parse(value.strip())
        elif key.strip() == "m_EditorVersionWithRevision":
            _, _, rest = value.partition("(")
            revision = rest.partition(")")[0].strip() or None
    return version, revision


class UnityProject:
    """One project's packages, read from disk; change it through resolve.py, then save()."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.manifest_raw: dict = {}
        self.dependencies: dict[str, DependencyRange] = {}
        self.locked: dict[str, tuple[Version, dict[str, VersionRange]]] = {}
        self.upm: dict[str, str] = {}
        self.installed: dict[str, Package] = {}             # Packages/<name> that's in "locked"
        self.unlocked: list[tuple[str, Package | None]] = []   # other package folders: (folder name, its package)
        self.unity: UnityVersion | None = None
        self.revision: str | None = None

    @classmethod
    def load(cls, folder) -> "UnityProject":
        p = cls(Path(folder))
        if not p.folder.is_dir():
            raise ProjectError("That folder isn't there any more.")
        if not is_project(p.folder):
            raise ProjectError("That folder isn't a Unity project.")
        try:
            raw = environment.read_json(p.folder / VPM_MANIFEST, 8 << 20)
            upm = environment.read_json(p.folder / UPM_MANIFEST, 8 << 20)
        except DataFileError as e:
            raise ProjectError(f"The project's package list can't be read: {e}.") from None
        p.manifest_raw = raw if isinstance(raw, dict) else {}
        p._read_manifest()
        deps = upm.get("dependencies") if isinstance(upm, dict) else None
        p.upm = {k: v for k, v in deps.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(deps, dict) else {}
        p._read_packages()
        p.unity, p.revision = read_unity_version(p.folder)
        return p

    def _read_manifest(self) -> None:
        deps = self.manifest_raw.get("dependencies")
        for name, entry in (deps.items() if isinstance(deps, dict) else ()):
            if valid_name(name) and isinstance(entry, dict):
                try:
                    self.dependencies[name] = DependencyRange.parse(entry.get("version"))
                except VersionError:
                    pass
        locked = self.manifest_raw.get("locked")
        for name, entry in (locked.items() if isinstance(locked, dict) else ()):
            if not valid_name(name) or not isinstance(entry, dict):
                continue
            version = Version.maybe(entry.get("version"))
            if version is None:
                continue
            ranges = {}
            for dep, text in (entry.get("dependencies") or {}).items() if isinstance(entry.get("dependencies"), dict) else ():
                r = VersionRange.maybe(text)
                if valid_name(dep) and r is not None:
                    ranges[dep] = r
            self.locked[name] = (version, ranges)

    def _read_packages(self) -> None:
        packages = self.folder / "Packages"
        try:
            entries = sorted(os.scandir(packages), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            try:
                raw = environment.read_json(Path(entry.path) / "package.json", 4 << 20)
            except (DataFileError, OSError):
                raw = None
            pkg = Package.parse(raw, loose=True)
            if pkg is not None and pkg.name == entry.name and entry.name in self.locked:
                self.installed[entry.name] = pkg
            else:
                self.unlocked.append((entry.name, pkg))

    # ---- what kind of project it is

    def project_type(self) -> int:
        if "com.vrchat.avatars" in self.locked:
            return AVATARS
        if "com.vrchat.worlds" in self.locked:
            return WORLDS
        if self.locked or self.dependencies:
            return VPM_STARTER
        if "com.vrchat.avatars" in self.upm:
            return UPM_AVATARS
        if "com.vrchat.worlds" in self.upm:
            return UPM_WORLDS
        if "com.vrchat.base" in self.upm:
            return UPM_STARTER
        plugins = self.folder / "Assets" / "VRCSDK" / "Plugins"
        if (plugins / "VRCSDK2.dll").is_file():
            return LEGACY_SDK2
        if (plugins / "VRCSDK3.dll").is_file():
            return LEGACY_WORLDS
        if (plugins / "VRCSDK3A.dll").is_file():
            return LEGACY_AVATARS
        return UNKNOWN

    # ---- the packages it has

    def locked_info(self):
        """(name, version, its dependencies) for each locked package."""
        return [(n, v, d) for n, (v, d) in self.locked.items()]

    def all_packages(self):
        """Every package in the project, locked or not, as (name, version, dependencies)."""
        out = self.locked_info()
        out += [(p.name, p.version, p.dependencies) for _, p in self.unlocked if p is not None]
        return out

    def all_installed(self) -> list[Package]:
        return list(self.installed.values()) + [p for _, p in self.unlocked if p is not None]

    def unity_running(self) -> bool:
        from .unity import project_open_in_unity
        return project_open_in_unity(self.folder)

    # ---- changing the manifest (resolve.py decides what)

    def add_dependency(self, name: str, r: DependencyRange) -> None:
        self.dependencies[name] = r

    def add_locked(self, name: str, version: Version, deps: dict) -> None:
        self.locked[name] = (version, dict(deps))

    def remove(self, names) -> None:
        for n in names:
            self.locked.pop(n, None)
            self.dependencies.pop(n, None)

    def manifest_json(self) -> dict:
        out = dict(self.manifest_raw)   # anything else in the file stays as it was
        out["dependencies"] = {n: {"version": str(r)} for n, r in self.dependencies.items()}
        locked = {}
        for n, (v, deps) in self.locked.items():
            entry = {"version": str(v)}
            entry["dependencies"] = {d: str(r) for d, r in deps.items()}
            locked[n] = entry
        out["locked"] = locked
        return out

    def save(self) -> None:
        environment.write_json(self.folder / VPM_MANIFEST, self.manifest_json())
        self.manifest_raw = self.manifest_json()


def summary(folder) -> dict:
    """What the project list shows for a project, read quickly: name, Unity version, kind, and whether it's there."""
    folder = Path(folder)
    if not folder.is_dir():
        return {"exists": False, "unity": None, "type": None}
    unity, _ = read_unity_version(folder)
    try:
        kind = UnityProject.load(folder).project_type()
    except ProjectError:
        kind = UNKNOWN
    return {"exists": True, "unity": str(unity) if unity else None, "type": kind}


def dumps_manifest(project: UnityProject) -> str:
    return json.dumps(project.manifest_json(), indent=2)
