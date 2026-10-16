"""Changing a project's packages: working out what an add, upgrade, removal or repair means, then doing it.

This is vrc-get's resolver (ALCOM's), followed step for step so a project ends up as ALCOM would leave it:

- collect(): starting from what's asked for, adds each package's dependencies (the newest version that suits, for
  the project's Unity, stable over prerelease unless prereleases are wanted), noting which packages a newer one
  replaces ("legacyPackages") and where two packages ask for versions of a third that can't both be met.
- add(), remove(), repair() turn a request into Changes: what's installed, what's removed and why (asked for,
  replaced, no longer used by anything), the conflicts, and the old files a package says to take away
  ("legacyFolders"/"legacyFiles"). Nothing is touched until apply().
- apply() downloads (or takes from the cache) every package, checks each against its repository's SHA-256, unpacks
  it beside the project, then swaps the folders in and saves vpm-manifest.json. If anything fails partway, the
  swapped folders are put back.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from ..common import log, tick
from . import fetch
from .manifest import unity_compatible
from .project import UnityProject
from .repos import Collection, Info, Selector
from .version import ALLOW, DENY, MINIMUM, DependencyRange, Version, VersionRange, allow_or_minimum

MAX_UNPACKED = 8 << 30        # a package that would unpack to more than this isn't a real one
MAX_MEMBERS = 200_000


class ResolveError(Exception):
    """A change that can't be made, in words to show; missing holds packages no repository has."""

    def __init__(self, message: str, missing: dict | None = None):
        super().__init__(message)
        self.missing = missing or {}


class _Missing(dict):
    def add(self, name: str, r: VersionRange) -> None:
        self[name] = r.intersect(self[name]) if name in self else r

    def error(self) -> ResolveError:
        names = ", ".join(f"{n} ({r})" for n, r in sorted(self.items()))
        return ResolveError(f"No repository has a version of these packages that fits: {names}.", dict(self))


# ---- working out which packages (package_resolution.rs)

class _Dep:
    __slots__ = ("using", "current", "requirements", "dependencies", "modern", "legacy", "allow_pre", "touched")

    def __init__(self):
        self.using: Info | None = None
        self.current: Version | None = None
        self.requirements: dict[str, VersionRange] = {}   # who asks for it ("" for the project itself) -> range
        self.dependencies: set[str] = set()
        self.modern: set[str] = set()                     # packages that replace it
        self.legacy: list[str] = []                       # packages it replaces
        self.allow_pre = False
        self.touched = False

    @property
    def is_legacy(self) -> bool:
        return bool(self.modern)

    def using_info(self, version: Version, dependencies) -> None:
        self.allow_pre |= version.is_pre
        self.current = version
        self.dependencies = set(dependencies)


class _Context:
    def __init__(self, allow_prerelease: bool, packages: list[Info]):
        self.allow_prerelease = allow_prerelease
        self.queue = list(packages)
        self.forced = len(packages)
        self.deps: dict[str, _Dep] = {}
        self.unlocked: set[str] = set()
        for p in self.queue:
            self.dep(p.name).allow_pre = True
        self.deps[""] = _Dep()

    def dep(self, name: str) -> _Dep:
        if name not in self.deps:
            self.deps[name] = _Dep()
        return self.deps[name]

    def next(self):
        if not self.queue:
            return None
        force = self.forced > 0
        self.forced = max(0, self.forced - 1)
        return self.queue.pop(), force

    def pending(self, name: str) -> Info | None:
        return next((p for p in self.queue if p.name == name), None)

    def add_pending(self, p: Info) -> None:
        self.queue = [q for q in self.queue if q.name != p.name]
        self.queue.append(p)

    def add_root(self, name: str, r: VersionRange, allow_pre: bool) -> None:
        self.deps[""].requirements[name] = r
        d = _Dep()
        d.requirements[""] = r
        d.allow_pre = allow_pre
        self.deps[name] = d

    def add_locked(self, name: str, version: Version, deps: dict, env: Collection) -> None:
        info = self.dep(name)
        info.using_info(version, deps.keys())
        found = env.find(name, Selector.specific(version))
        if found is not None:
            info.legacy = list(found.package.legacy_packages)
            for legacy in found.package.legacy_packages:
                self.dep(legacy).modern.add(name)
        for dep, r in deps.items():
            self.dep(dep).requirements[name] = r

    def add_unlocked(self, manifest) -> None:
        info = self.dep(manifest.name)
        info.using_info(manifest.version, manifest.dependencies.keys())
        info.legacy = list(manifest.legacy_packages)
        for legacy in manifest.legacy_packages:
            self.dep(legacy).modern.add(manifest.name)
        for dep, r in manifest.dependencies.items():
            self.dep(dep).requirements[manifest.name] = r

    def add_package(self, p: Info, force: bool) -> bool:
        entry = self.dep(p.name)
        if entry.is_legacy or (not force and p.name in self.unlocked):
            return False
        entry.touched = True
        entry.current, entry.using = p.version, p
        old_deps, entry.dependencies = entry.dependencies, set(p.package.dependencies)
        old_legacy, entry.legacy = entry.legacy, list(p.package.legacy_packages)
        for dep in old_deps:
            self.dep(dep).requirements.pop(p.name, None)
            self.dep(dep).touched = True
        for dep, r in p.package.dependencies.items():
            self.dep(dep).requirements[p.name] = r
            self.dep(dep).touched = True
        for dep in old_legacy:
            self.dep(dep).modern.discard(p.name)
            self.dep(dep).touched = True
        for legacy in p.package.legacy_packages:
            self.dep(legacy).modern.add(p.name)
            self.dep(legacy).touched = True
        return True

    def should_add(self, name: str, r: VersionRange) -> bool:
        entry = self.dep(name)
        if entry.is_legacy or name in self.unlocked:
            return False
        accept = allow_or_minimum(entry.allow_pre or self.allow_prerelease)
        pending = self.pending(name)
        if pending is not None:
            return not r.match_pre(pending.version, accept)
        return not (entry.current is not None and r.match_pre(entry.current, accept))

    def result(self):
        conflicts: dict[str, list[str]] = {}
        for name, info in self.deps.items():
            if info.is_legacy or not info.touched or info.current is None:
                continue
            accept = allow_or_minimum(info.allow_pre or self.allow_prerelease)
            against = [src for src, r in info.requirements.items()
                       if src in self.deps and not self.deps[src].is_legacy and not r.match_pre(info.current, accept)]
            if against and (info.using is not None or any(self.deps[s].using is not None for s in against)):
                conflicts.setdefault(name, []).extend(against)
        legacy = [n for n, info in self.deps.items() if info.is_legacy]
        new = [info.using for info in self.deps.values() if not info.is_legacy and info.using is not None]
        return new, conflicts, legacy


def collect(dependencies, locked, unlocked, get_locked, unity, env: Collection, packages: list[Info],
            allow_prerelease: bool, missing: _Missing):
    """What installing packages means: (packages to install, conflicts {package: [who it conflicts with]},
    packages now replaced)."""
    ctx = _Context(allow_prerelease, packages)
    for name, dep in dependencies:
        single = dep.single_version()
        if single is not None:
            allow_pre, least = single.is_pre, single
            was = get_locked(name)
            if was is not None:
                allow_pre |= was[1].is_pre
                if was[1] < least:
                    least = was[1]
            r = VersionRange.same_or_later(least)
        else:
            r = dep.as_range()
            allow_pre = r.contains_pre()
        ctx.add_root(name, r, allow_pre)
    for name, version, deps in locked:
        ctx.add_locked(name, version, deps, env)
    for folder_name, manifest in unlocked:
        ctx.unlocked.add(folder_name)
        if manifest is not None:
            ctx.unlocked.add(manifest.name)
            ctx.add_unlocked(manifest)
    while (item := ctx.next()) is not None:
        x, force = item
        if not ctx.add_package(x, force):
            continue
        for dep, r in x.package.dependencies.items():
            if not ctx.should_add(dep, r):
                continue

            def find(u, accept, dep=dep, r=r):
                return env.find(dep, Selector.range(u, r, accept))
            if allow_prerelease:
                tries = ((unity, ALLOW), (None, ALLOW))
            elif x.version.is_pre:
                tries = ((unity, DENY), (unity, MINIMUM), (unity, ALLOW), (None, DENY), (None, MINIMUM), (None, ALLOW))
            else:
                tries = ((unity, DENY), (unity, MINIMUM), (None, DENY), (None, MINIMUM))
            found = next((f for u, a in tries if (f := find(u, a)) is not None), None)
            if found is not None:
                ctx.add_pending(found)
            else:
                missing.add(dep, r)
    return ctx.result()


# ---- what a change means (pending_project_changes.rs)

REQUESTED, LEGACY, UNUSED = "requested", "legacy", "unused"


class Install:
    __slots__ = ("package", "add_to_locked", "to_dependencies")

    def __init__(self, package: Info | None = None, add_to_locked: bool = False,
                 to_dependencies: DependencyRange | None = None):
        self.package, self.add_to_locked, self.to_dependencies = package, add_to_locked, to_dependencies


class Remove:
    __slots__ = ("reason",)

    def __init__(self, reason: str):
        self.reason = reason


class Conflict:
    __slots__ = ("packages", "unity", "unlocked")

    def __init__(self):
        self.packages: list[str] = []
        self.unity = False
        self.unlocked: list[str] = []


class Changes:
    """What a request would do to a project: package changes, conflicts, and legacy files and folders to delete."""

    def __init__(self):
        self.packages: dict[str, Install | Remove] = {}
        self.conflicts: dict[str, Conflict] = {}
        self.legacy_files: list[tuple[str, str]] = []     # (path in the project, the package that replaces it)
        self.legacy_folders: list[tuple[str, str]] = []

    # building

    def add_to_dependencies(self, name: str, r: DependencyRange) -> None:
        c = self.packages.get(name)
        if c is None:
            self.packages[name] = Install(to_dependencies=r)
        elif isinstance(c, Install) and c.to_dependencies is None:
            c.to_dependencies = r

    def install(self, p: Info, add_to_locked: bool = True, replace: bool = False) -> None:
        c = self.packages.get(p.name)
        if c is None:
            self.packages[p.name] = Install(p, add_to_locked)
        elif isinstance(c, Install) and (c.package is None or replace):
            c.package, c.add_to_locked = p, add_to_locked

    def remove(self, name: str, reason: str) -> None:
        if name not in self.packages:
            self.packages[name] = Remove(reason)

    def conflict(self, name: str) -> Conflict:
        return self.conflicts.setdefault(name, Conflict())

    def dependencies_for(self, name: str) -> DependencyRange | None:
        c = self.packages.get(name)
        return c.to_dependencies if isinstance(c, Install) else None

    def installing(self, name: str) -> Info | None:
        c = self.packages.get(name)
        return c.package if isinstance(c, Install) and c.add_to_locked else None

    def all_installing(self) -> list[Info]:
        return [c.package for c in self.packages.values() if isinstance(c, Install) and c.add_to_locked and c.package]

    def finish(self, project: UnityProject) -> "Changes":
        installs = self.all_installing()
        if project.unity is not None:
            for p in installs:
                if not unity_compatible(p.package, project.unity):
                    self.conflict(p.name).unity = True
        self._sweep(project)
        self.legacy_files, self.legacy_folders = legacy_assets(project, installs)
        return self

    def _sweep(self, project: UnityProject) -> None:
        """Mark packages nothing uses any more (a dependency of one being removed or replaced) for removal."""
        def mark(entry, deps_of):
            seen, queue = set(entry), list(entry)
            while queue:
                for d in deps_of(queue.pop()):
                    if d not in seen:
                        seen.add(d)
                        queue.append(d)
            return seen

        def locked_deps(name):
            return project.locked[name][1].keys() if name in project.locked else ()
        entry = [n for n, c in self.packages.items()
                 if n in project.locked and (isinstance(c, Remove) or (isinstance(c, Install) and c.add_to_locked))]
        removable = mark(entry, locked_deps)
        if not removable:
            return
        installing = [n for n, c in self.packages.items() if isinstance(c, Install)]
        roots = [d for _, p in project.unlocked if p is not None for d in p.dependencies]
        roots += [n for n in project.dependencies if not isinstance(self.packages.get(n), Remove)]
        roots += installing

        def using_deps(name):
            c = self.packages.get(name)
            if isinstance(c, Install) and c.package is not None:
                return c.package.package.dependencies.keys()
            return locked_deps(name)
        using = mark(roots, using_deps)
        for name in project.locked:
            if name not in using and name in removable and name not in self.packages:
                self.packages[name] = Remove(UNUSED)

    # reading

    def view(self) -> dict:
        """For the page: each change, conflict and legacy path."""
        out = {"install": [], "remove": [], "conflicts": [], "legacy": [p for p, _ in self.legacy_folders + self.legacy_files]}
        for name, c in sorted(self.packages.items()):
            if isinstance(c, Install) and c.package is not None:
                out["install"].append({"name": name, "label": c.package.package.label(),
                                       "version": str(c.package.version), "from": _source(c.package)})
            elif isinstance(c, Remove):
                out["remove"].append({"name": name, "reason": c.reason})
        for name, c in sorted(self.conflicts.items()):
            out["conflicts"].append({"name": name, "with": sorted(set(c.packages)), "unity": c.unity,
                                     "unlocked": sorted(set(c.unlocked))})
        return out

    def empty(self) -> bool:
        return not any(isinstance(c, Remove) or (isinstance(c, Install) and c.package) for c in self.packages.values())


def _source(p: Info) -> str:
    return p.repo.label() if p.repo is not None else "your package folder"


# ---- requests (add_package.rs, remove_package.rs, resolve.rs)

INSTALL, UPGRADE, DOWNGRADE, AUTO = "install", "upgrade", "downgrade", "auto"


def add(project: UnityProject, env: Collection, packages: list[Info], operation: str = AUTO,
        allow_prerelease: bool = False) -> Changes:
    """Install these versions (or upgrade or downgrade to them), with whatever they need."""
    changes, adding = Changes(), []

    def keep_newer(p: Info) -> None:
        was = project.locked.get(p.name)
        if was is None or was[0] < p.version:
            adding.append(p)

    def to_dependencies(p: Info) -> None:
        current = project.dependencies.get(p.name)
        single = current.single_version() if current else None
        if current is None or single is None or single < p.version:
            changes.add_to_dependencies(p.name, DependencyRange.version(p.version))
        keep_newer(p)

    def downgrade(p: Info) -> None:
        current = project.dependencies.get(p.name)
        if current is not None and not current.matches(p.version):
            changes.add_to_dependencies(p.name, DependencyRange.version(p.version))
        adding.append(p)

    for p in packages:
        was = project.locked.get(p.name)
        if operation == INSTALL:
            to_dependencies(p)
        elif operation == UPGRADE:
            if was is None:
                raise ResolveError(f"{p.name} isn't installed, so it can't be upgraded.")
            keep_newer(p)
        elif operation == DOWNGRADE:
            if was is None:
                raise ResolveError(f"{p.name} isn't installed, so it can't be downgraded.")
            if was[0] < p.version:
                raise ResolveError(f"{p.name} {was[0]} is older than {p.version}.")
            downgrade(p)
        elif was is None:
            to_dependencies(p)
        elif was[0] < p.version:
            keep_newer(p)
        elif was[0] == p.version:
            adding.append(p)   # the same version again: reinstalled
        else:
            downgrade(p)
    if not adding:
        return changes
    missing = _Missing()
    new, conflicts, legacy = collect(
        [(n, changes.dependencies_for(n) or r) for n, r in project.dependencies.items()],
        project.locked_info(), project.unlocked, lambda n: _locked(project, n), project.unity, env, adding,
        allow_prerelease, missing)
    if missing:
        raise missing.error()
    for p in new:
        changes.install(p)
        for folder_name, unlocked in project.unlocked:
            if folder_name == p.name or (unlocked is not None and unlocked.name == p.name):
                changes.conflict(p.name).unlocked.append(folder_name)
    for name, against in conflicts.items():
        changes.conflict(name).packages.extend(against)
    for name in legacy:
        if name in project.locked:
            changes.remove(name, LEGACY)
    return changes.finish(project)


def _locked(project: UnityProject, name: str):
    if name not in project.locked:
        return None
    version, deps = project.locked[name]
    return (name, version, deps)


def remove(project: UnityProject, names: list[str]) -> Changes:
    """Remove these packages (and whatever only they used)."""
    absent = [n for n in names if n not in project.locked]
    if absent:
        raise ResolveError(f"These packages aren't installed: {', '.join(absent)}.")
    changes, removing = Changes(), set(names)
    may_conflict = set(removing)
    for p in project.all_installed():
        if p.name not in removing:
            may_conflict -= set(p.legacy_packages)
    for name, _version, deps in project.all_packages():
        if name in removing:
            continue
        for gone in may_conflict:
            if gone in deps:
                changes.conflict(gone).packages.append(name)
    for n in names:
        changes.remove(n, REQUESTED)
    return changes.finish(project)


def needs_repair(project: UnityProject) -> bool:
    """Whether what's installed differs from what the manifest says (a package folder missing, or another
    version), or something asked for isn't there: ALCOM's "Resolve" (should_resolve)."""
    present = set()
    for name, (version, _deps) in project.locked.items():
        have = project.installed.get(name)
        if have is None or have.version != version:
            return True
        present.add(name)
        present.update(have.legacy_packages)
    for _, p in project.unlocked:
        if p is not None:
            present.update(p.legacy_packages)
            present.add(p.name)
    if any(n not in present for n in project.dependencies):
        return True
    return any(d not in present for _, p in project.unlocked if p is not None for d in p.dependencies)


def repair(project: UnityProject, env: Collection) -> Changes:
    """Install what the manifest says, as ALCOM's Resolve does: every locked version, anything asked for that
    isn't locked yet, and what the project's own package folders need."""
    changes, missing = Changes(), _Missing()
    for name, version, _deps in project.locked_info():
        found = env.find(name, Selector.specific(version))
        if found is not None:
            changes.install(found, add_to_locked=False)
        else:
            missing.add(name, VersionRange.specific(version))
    _repair_dependencies(project, env, changes, missing)
    _repair_unlocked(project, env, changes, missing)
    if missing:
        raise missing.error()
    return changes.finish(project)


def _repair_dependencies(project, env, changes: Changes, missing: _Missing) -> None:
    to_install, names = [], set()
    for name, dep in project.dependencies.items():
        if name in project.locked:
            continue
        r = dep.as_range()
        found = env.find(name, Selector.range(project.unity, r, allow_or_minimum(r.contains_pre())))
        if found is not None:
            to_install.append(found)
        else:
            missing.add(name, r)
        names.add(name)
    if not to_install:
        return
    new, conflicts, _legacy = collect(
        list(project.dependencies.items()), project.locked_info(), project.unlocked, lambda n: _locked(project, n),
        project.unity, env, to_install, any(p.version.is_pre for p in to_install), missing)
    for p in new:
        changes.install(p, replace=True)
        if p.name in names:
            changes.add_to_dependencies(p.name, DependencyRange.version(p.version))
    for name, against in conflicts.items():
        changes.conflict(name).packages.extend(against)


def _repair_unlocked(project, env, changes: Changes, missing: _Missing) -> None:
    own = [p for _, p in project.unlocked if p is not None]
    if not own:
        return
    own_names = {p.name for p in own}
    wanted: dict[str, list[tuple[VersionRange, bool]]] = {}
    for p in own:
        for dep, r in p.dependencies.items():
            if dep not in project.locked and changes.installing(dep) is None and dep not in own_names:
                wanted.setdefault(dep, []).append((r, p.version.is_pre))
    if not wanted:
        return
    virtual = {n: (n, v, d) for n, v, d in project.locked_info()}
    for p in changes.all_installing():
        virtual[p.name] = (p.name, p.version, p.package.dependencies)
    found_all = []
    for name, entries in wanted.items():
        ranges = [r for r, _ in entries]
        found = env.find(name, Selector.all_of(project.unity, ranges, allow_or_minimum(any(pre for _, pre in entries))))
        if found is not None:
            found_all.append(found)
        else:
            joined = ranges[0]
            for r in ranges[1:]:
                joined = joined.intersect(r)
            missing.add(name, joined)
    new, conflicts, _legacy = collect(
        list(project.dependencies.items()), list(virtual.values()), project.unlocked, virtual.get, project.unity, env,
        found_all, any(p.version.is_pre for p in found_all), missing)
    for p in new:
        changes.install(p, replace=True)
    for name, against in conflicts.items():
        changes.conflict(name).packages.extend(against)


# ---- old files a package replaces (find_legacy_assets.rs)

def _inside(project: Path, rel: str) -> Path | None:
    """A path a package names in the project, if it's a plain one under Assets or Packages that really is inside the
    project once links are followed."""
    rel = rel.replace("\\", "/")
    parts = PurePosixPath(rel).parts
    if not parts or parts[0] not in ("Assets", "Packages") or rel.startswith("/") or ":" in rel \
            or any(p in ("", ".", "..") for p in rel.split("/")):
        return None
    path = project.joinpath(*parts)
    try:
        real, root = path.resolve(), project.resolve()
    except OSError:
        return None
    return path if real != root and root in real.parents else None


def _meta_guid(meta: Path) -> str | None:
    try:
        with open(meta, "r", encoding="utf-8", errors="replace") as f:
            for _ in range(50):
                line = f.readline()
                if not line:
                    break
                if line.startswith("guid: "):
                    return line[6:].strip().lower()
    except OSError:
        pass
    return None


def legacy_assets(project: UnityProject, installs: list[Info]):
    """The files and folders these packages replace that are in the project: ([(path, by)], [(path, by)])."""
    wanted = []   # (package, path, guid, is_file)
    for p in installs:
        before = project.installed.get(p.name)
        for is_file, entries in ((False, p.package.legacy_folders), (True, p.package.legacy_files)):
            old = (before.legacy_files if is_file else before.legacy_folders) if before else {}
            for path, guid in entries.items():
                if path not in old:
                    wanted.append((p.name, path, (guid or "").strip().lower() or None, is_file))
    files, folders, by_guid = {}, {}, {}
    for name, rel, guid, is_file in wanted:
        path = _inside(project.folder, rel)
        if path is not None and (path.is_file() if is_file else path.is_dir()) and (
                rel.replace("\\", "/") != "Assets/UdonSharp" or not guid
                or _meta_guid(Path(str(path) + ".meta")) in (None, guid)):
            (files if is_file else folders)[rel.replace("\\", "/")] = name
        elif guid:
            by_guid[guid] = (name, is_file)
    if by_guid:
        assets = project.folder / "Assets"
        for root, dirs, names in os.walk(assets):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
            for n in names:
                if not n.endswith(".meta"):
                    continue
                guid = _meta_guid(Path(root) / n)
                if guid in by_guid:
                    target = Path(root) / n[:-5]
                    name, is_file = by_guid[guid]
                    if (target.is_file() if is_file else target.is_dir()):
                        rel = target.relative_to(project.folder).as_posix()
                        (files if is_file else folders)[rel] = name
                        del by_guid[guid]
            if not by_guid:
                break
    return sorted(files.items()), sorted(folders.items())


# ---- doing it

def cache_paths(vcc_folder: Path, p: Info) -> tuple[Path, Path]:
    """Where a package's zip is kept, as vrc-get keeps it: Repos/<name>/vrc-get-<name>-<version>.zip, beside its
    SHA-256."""
    zip_path = vcc_folder / "Repos" / p.name / f"vrc-get-{p.name}-{p.version}.zip"
    return zip_path, zip_path.with_name(zip_path.name + ".sha256")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def package_zip(vcc_folder: Path, p: Info) -> Path:
    """The package's zip: from the cache when it's there and matches, else downloaded (and checked against the
    repository's SHA-256)."""
    zip_path, sha_path = cache_paths(vcc_folder, p)
    expected = p.package.zip_sha256
    try:
        noted = sha_path.read_text("utf-8", errors="replace")[:64].lower()
        if zip_path.is_file() and (expected is None or noted == expected) and _sha256(zip_path) == noted:
            return zip_path
    except OSError:
        pass
    if not p.package.url:
        raise ResolveError(f"The repository doesn't say where to download {p.name} {p.version} from.")
    # a repository's own headers (a key, say) go only to its own host; a package's, to where it's downloaded from
    same_host = p.repo is not None and p.repo.url and urlsplit(p.repo.url).hostname == urlsplit(p.package.url).hostname
    headers = {**(p.repo.headers if same_host else {}), **p.package.headers}
    log(f"Downloading the package {p.package.label()} {p.version}")

    def progress(got, whole):
        tick(f"{p.package.label()}: {got // 1024} KB" + (f" of {whole // 1024} KB" if whole else ""))
    try:
        got = fetch.download(p.package.url, zip_path, headers, progress=progress)
    except fetch.FetchError as e:
        raise ResolveError(f"{p.package.label()} {p.version} couldn't be downloaded: {e}.") from None
    if expected is not None and got != expected:
        zip_path.unlink(missing_ok=True)
        raise ResolveError(f"The download of {p.package.label()} {p.version} isn't the file its repository "
                           "describes (its SHA-256 differs), so it wasn't installed. The repository may be broken "
                           "or tampered with.")
    sha_path.write_text(f"{got} {zip_path.name}\n", "utf-8")
    return zip_path


def _member_path(name: str) -> PurePosixPath | None:
    name = name.replace("\\", "/")
    if name.startswith("/") or ":" in name or "\0" in name:
        return None
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return PurePosixPath(*parts)


def unzip(zip_path: Path, dest: Path) -> None:
    """Unpack a package's zip into dest, refusing names that would land outside it and anything far larger than a
    real package."""
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_UNPACKED:
            raise ResolveError(f"{zip_path.name} is larger than any real package.")
        dest.mkdir(parents=True, exist_ok=True)
        for m in members:
            rel = _member_path(m.filename)
            if rel is None:
                raise ResolveError(f"{zip_path.name} has a file named to land outside its folder: {m.filename[:120]}")
            out = dest.joinpath(*rel.parts)
            if m.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)


def _copy_folder(src: Path, dest: Path) -> None:
    def ignore(folder, names):
        return [n for n in names if os.path.islink(os.path.join(folder, n))]
    shutil.copytree(src, dest, ignore=ignore)


def _rmtree(path: Path) -> None:
    def retry(func, p, _exc):   # Windows: read-only files (git checkouts) can't be deleted until made writable
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path, onerror=retry)


def apply(project: UnityProject, changes: Changes, vcc_folder: Path) -> None:
    """Make the changes: unpack every package beside the project first, then swap folders and save the manifest,
    putting things back if that fails partway. Legacy files go last."""
    installs = [c.package for c in changes.packages.values() if isinstance(c, Install) and c.package]
    removes = [n for n, c in changes.packages.items() if isinstance(c, Remove)]
    out_of_the_way = [p.name for p in installs] + removes
    for c in changes.conflicts.values():
        out_of_the_way += c.unlocked
    base = project.folder / "Temp" / "vrc-get" / str(uuid.uuid4())
    staged, aside = base / "install", base / "remove"
    packages = project.folder / "Packages"
    moved_in, moved_out = [], []
    try:
        staged.mkdir(parents=True)
        aside.mkdir(parents=True)
        for p in installs:
            if p.repo is not None:
                zip_path = package_zip(vcc_folder, p)
                log(f"Unpacking the package {p.package.label()} {p.version}")
                unzip(zip_path, staged / p.name)
            else:
                log(f"Copying the package {p.package.label()} {p.version} from {p.folder}")
                _copy_folder(p.folder, staged / p.name)
        packages.mkdir(exist_ok=True)
        for name in dict.fromkeys(out_of_the_way):
            if (packages / name).exists() or (packages / name).is_symlink():
                os.replace(packages / name, aside / name)
                moved_out.append(name)
        for p in installs:
            os.replace(staged / p.name, packages / p.name)
            moved_in.append(p.name)
        for name, c in changes.packages.items():
            if isinstance(c, Install):
                if c.package is not None and c.add_to_locked:
                    project.add_locked(name, c.package.version, c.package.package.dependencies)
                if c.to_dependencies is not None:
                    project.add_dependency(name, c.to_dependencies)
        project.remove(removes)
        project.save()
    except BaseException:
        for name in moved_in:
            try:
                os.replace(packages / name, staged / name)
            except OSError:
                pass
        for name in moved_out:
            try:
                os.replace(aside / name, packages / name)
            except OSError:
                pass
        raise
    finally:
        _rmtree(base)
        for leftover in (project.folder / "Temp" / "vrc-get", project.folder / "Temp"):
            try:
                leftover.rmdir()   # (only when empty: Unity keeps its own things in Temp while it's open)
            except OSError:
                pass
    for rel, _by in changes.legacy_files:
        path = _inside(project.folder, rel)
        if path is not None:
            for p in (path, Path(str(path) + ".meta")):
                try:
                    p.unlink()
                except OSError:
                    pass
    for rel, _by in changes.legacy_folders:
        path = _inside(project.folder, rel)
        if path is not None:
            _rmtree(path)
            try:
                Path(str(path) + ".meta").unlink()
            except OSError:
                pass
