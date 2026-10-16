"""Backing up a project, as ALCOM does: a .zip of the project without what Unity makes again by itself (Library,
Temp, Logs, obj), named for the project and the time, in the Creator Companion's backup folder (settings.json's
projectBackupPath, else Documents/ALCOM/Backups as ALCOM chooses it). Packages from repositories can be left out
too: they're downloaded again when the project's opened in Hoard, ALCOM or the Creator Companion.
"""
from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path

from ..common import tick

SKIPPED_TOP = {"library", "logs", "obj", "temp"}


def default_folder() -> Path:
    return Path.home() / "ALCOM" / "Backups"


def files(project: Path, leave_out_packages: set[str] = frozenset()):
    """Every file to back up, as (path, its name in the zip), skipping links."""
    project = Path(project)
    skip_packages = {n.lower() for n in leave_out_packages}
    for root, dirs, names in os.walk(project):
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
            for full, name in files(project, leave_out_packages):
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
