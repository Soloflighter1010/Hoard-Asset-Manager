"""Backing up a project, as ALCOM does: a .zip of the project without what Unity makes again by itself (Library,
Temp, Logs, obj), named for the project and the time, in the Creator Companion's backup folder (settings.json's
projectBackupPath, else Documents/ALCOM/Backups as ALCOM chooses it). Packages from repositories can be left out
too: they're downloaded again when the project's opened in Hoard, ALCOM or the Creator Companion.

And keeping them in hand: every backup in the folder (and in the folder old ones were moved to), with which are old
(past the newest few of each project, and older than some days), how much room the drive has left, and deleting or
moving the ones you choose. Only zips named as a backup is (<project>-<date>T<time>.zip, as ALCOM and Hoard name
them), directly in those two folders, are ever listed, deleted or moved.
"""
from __future__ import annotations

import os
import re
import shutil
import time
import zipfile
from pathlib import Path

from ..common import tick

NAME = re.compile(r"^(?P<project>.+)-(?P<when>\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d)\.zip$")
KEEP_CHOICES = (1, 2, 3, 5, 10)        # the newest of each project that are never old
DAYS_CHOICES = (7, 14, 30, 90, 180, 365)
LOW_SHARE, LOW_BYTES = 0.10, 10 << 30   # a drive with less than 10% or 10 GB free is low on room
MAX_LISTED = 5000

SKIPPED_TOP = {"library", "logs", "obj", "temp"}


def default_folder() -> Path:
    """Where ALCOM keeps project backups unless told otherwise."""
    return Path.home() / "ALCOM" / "Backups"


def files(project: Path, leave_out_packages: set[str] = frozenset(), skip: Path | None = None):
    """Every file to back up, as (path, its name in the zip), skipping links, and the folder skip (the backups
    folder, should it be inside the project: a backup never takes in itself or the backups before it)."""
    project = Path(project)
    skip_packages = {n.lower() for n in leave_out_packages}
    skip_real = os.path.normcase(os.path.realpath(skip)) if skip else None
    for root, dirs, names in os.walk(project):
        if skip_real:
            dirs[:] = [d for d in dirs if os.path.normcase(os.path.realpath(os.path.join(root, d))) != skip_real]
        rel_root = os.path.relpath(root, project)
        parts = [] if rel_root == "." else rel_root.replace(os.sep, "/").split("/")
        if not parts:
            dirs[:] = [d for d in dirs if d.lower() not in SKIPPED_TOP and not d.lower().startswith("library")]
        elif len(parts) == 1 and parts[0].lower() == "packages":
            dirs[:] = [d for d in dirs if d.lower() not in skip_packages]
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for n in names:
            full = os.path.join(root, n)
            if os.path.islink(full):
                continue
            yield full, "/".join(parts + [n])


def back_up(project: Path, folder: Path, leave_out_packages: set[str] = frozenset(), fast: bool = True) -> Path:
    """Write the backup, returning its path. A failure leaves no half-made zip behind."""
    project = Path(project)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{project.name}-{time.strftime('%Y-%m-%dT%H-%M-%S')}.zip"
    part = out.with_name(out.name + ".part")
    count, said = 0, 0.0
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=1 if fast else 9, allowZip64=True) as zf:
            for full, name in files(project, leave_out_packages, skip=folder):
                try:
                    zf.write(full, name)
                except (OSError, ValueError):
                    continue   # (a file that went, or one Unity holds open; the rest are still backed up)
                count += 1
                if time.monotonic() - said > 0.5:
                    said = time.monotonic()
                    tick(f"Backing up {project.name}: {count} files")
        os.replace(part, out)
    finally:
        if part.exists():
            part.unlink()
    return out


def found(folder: Path) -> list[dict]:
    """The backups directly in folder, newest first: {path, name, project, when (ISO), size}."""
    out = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return out
    for e in entries[:MAX_LISTED * 4]:
        m = NAME.match(e.name)
        try:
            if not m or e.is_symlink() or not e.is_file():
                continue
            size = e.stat().st_size
        except OSError:
            continue
        when = m.group("when")
        out.append({"path": e.path, "name": e.name, "project": m.group("project"), "size": size,
                    "when": f"{when[:10]}T{when[11:].replace('-', ':')}"})
    out.sort(key=lambda b: b["when"], reverse=True)
    return out[:MAX_LISTED]


def mark_old(backups: list[dict], keep: int, days: int, now: float | None = None) -> list[dict]:
    """Mark each backup old or not (b["old"]): past the newest `keep` of its project, and more than `days` old."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime((now or time.time()) - days * 86400))
    seen: dict[str, int] = {}
    for b in sorted(backups, key=lambda b: b["when"], reverse=True):
        n = seen[b["project"].lower()] = seen.get(b["project"].lower(), 0) + 1
        b["old"] = n > keep and b["when"] < cutoff
    return backups


def room(folder: Path) -> dict:
    """How much room the drive the folder is on has: {free, total, low}, or {} when it can't be told."""
    probe = Path(folder)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return {}
    return {"free": usage.free, "total": usage.total,
            "low": usage.free < LOW_BYTES or usage.free < usage.total * LOW_SHARE}


def overview(folder: Path, moved_to: Path | None, keep: int, days: int) -> dict:
    """Everything the backups panel shows."""
    here = mark_old(found(folder), keep, days)
    away = found(moved_to) if moved_to and Path(moved_to).is_dir() and not _same(moved_to, folder) else []
    old = [b for b in here if b["old"]]
    return {"folder": str(folder), "moved_to": str(moved_to) if moved_to else "", "keep": keep, "days": days,
            "room": room(folder), "backups": here, "moved": away,
            "old_count": len(old), "old_size": sum(b["size"] for b in old),
            "size": sum(b["size"] for b in here)}


def _same(a: Path, b: Path) -> bool:
    """Whether two paths are the same folder (links and case followed)."""
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except OSError:
        return False


def chosen(paths, folders: list[Path]) -> list[Path]:
    """The backups paths names, each checked to be one: a zip named as a backup, directly in one of folders, not a
    link. Anything else raises ValueError, so a page can never have Hoard delete or move another file."""
    out = []
    homes = [os.path.normcase(os.path.realpath(f)) for f in folders if f]
    for raw in paths if isinstance(paths, list) else []:
        p = Path(str(raw)[:2000])
        if (not p.is_absolute() or not NAME.match(p.name) or p.is_symlink() or not p.is_file()
                or os.path.normcase(os.path.realpath(p.parent)) not in homes):
            raise ValueError(f"{p.name} isn't one of your project backups.")
        out.append(p)
    return out


def delete(paths: list[Path]) -> tuple[int, int]:
    """Delete these backups (already checked by chosen()). Returns (how many, bytes freed)."""
    count = freed = 0
    for p in paths:
        try:
            size = p.stat().st_size
            p.unlink()
        except OSError:
            continue
        count += 1
        freed += size
    return count, freed


def move(paths: list[Path], to: Path, stop=lambda: False) -> tuple[int, int, list[str]]:
    """Move these backups (already checked) to another folder, a drive with more room say: each is copied, checked
    by size, and only then deleted where it was. A backup already there under its name is left as it is. Returns
    (how many moved, bytes freed, problems)."""
    to.mkdir(parents=True, exist_ok=True)
    count = freed = 0
    problems = []
    for i, p in enumerate(paths, 1):
        if stop():
            break
        target = to / p.name
        if target.exists():
            problems.append(f"{p.name}: there's one by that name there already")
            continue
        part = target.with_name(target.name + ".part")
        tick(f"Moving {p.name} ({i} of {len(paths)})")
        try:
            shutil.copyfile(p, part)
            size = p.stat().st_size
            if part.stat().st_size != size:
                raise OSError("the copy isn't the same size")
            os.replace(part, target)
            p.unlink()
        except OSError as e:
            problems.append(f"{p.name}: {e.strerror or e}")
            continue
        finally:
            if part.exists():
                part.unlink()
        count += 1
        freed += size
    return count, freed, problems
