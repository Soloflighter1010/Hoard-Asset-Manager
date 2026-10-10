"""Previous versions (Downloads): when a download replaces a file (a creator's update), the file it replaces is kept.

The old file goes to "_Previous versions/<when>/<its name>" in the product's own folder, beside the new one: on the
same drive (so keeping it is a rename, not a copy), and found by anyone who opens the folder. How many are kept for
each file is a setting (keep_previous, 1 unless you choose otherwise; 0 keeps none); older ones are deleted. Restore
puts a previous version back, keeping the one it replaces the same way, so a restore can be undone.

Hoard's records list the files it downloaded, not these: the integrity check, Disk space and Hoard for Unity only see
the current files. Deleting a product's downloaded files deletes its previous versions too, and moving it to another
library folder moves them with it.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import time
from pathlib import Path

FOLDER = "_Previous versions"
STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{6}(?:-\d+)?")
MAX_KEEP = 10

_keep = 1   # set from the settings (set_keep) by the server and the command line


def set_keep(n) -> None:
    global _keep
    _keep = max(0, min(MAX_KEEP, n)) if isinstance(n, int) and not isinstance(n, bool) else 1


def keeping() -> int:
    return _keep


def _plain_file(p: Path) -> os.stat_result | None:
    try:
        st = os.stat(p, follow_symlinks=False)
    except OSError:
        return None
    return st if stat.S_ISREG(st.st_mode) else None


def _stamp_for(base: Path, name: str) -> Path:
    """The folder for a file replaced now: the files an update replaces at once share one."""
    stamp = time.strftime("%Y-%m-%d %H%M%S")
    folder, n = base / stamp, 2
    while os.path.lexists(folder / name):
        folder, n = base / f"{stamp}-{n}", n + 1
    return folder


def keep(dest: Path, keep_n: int | None = None) -> Path | None:
    """dest is about to be replaced: move it to the product's previous versions, if any are kept and it's a plain,
    non-empty file. Returns where it went (or None). Never raises: a file that can't be kept is replaced as before."""
    n = _keep if keep_n is None else keep_n
    st = _plain_file(dest)
    if n <= 0 or st is None or st.st_size == 0 or dest.parent.name == FOLDER or FOLDER in dest.parts:
        return None
    try:
        base = dest.parent / FOLDER
        if base.is_symlink():
            return None
        where = _stamp_for(base, dest.name)
        where.mkdir(parents=True, exist_ok=True)
        if where.is_symlink():
            return None
        kept = where / dest.name
        os.replace(dest, kept)
        prune(dest.parent, dest.name, n)
        return kept
    except OSError:
        return None


def listed(folder: Path) -> list[dict]:
    """A product folder's previous versions, newest first: [{"stamp", "file", "size"}]."""
    base = folder / FOLDER
    out = []
    try:
        if base.is_symlink() or not base.is_dir():
            return []
        for d in base.iterdir():
            if not STAMP.fullmatch(d.name) or d.is_symlink() or not d.is_dir():
                continue
            for f in d.iterdir():
                st = _plain_file(f)
                if st is not None:
                    out.append({"stamp": d.name, "file": f.name, "size": st.st_size})
    except OSError:
        return []
    out.sort(key=lambda v: (v["stamp"], v["file"]), reverse=True)
    return out


def prune(folder: Path, name: str, n: int | None = None) -> int:
    """Keep the newest n previous versions of one file; delete the rest (and folders left empty). Returns how many
    were deleted."""
    n = _keep if n is None else n
    gone = 0
    for v in [v for v in listed(folder) if v["file"] == name][n:]:
        try:
            (folder / FOLDER / v["stamp"] / v["file"]).unlink()
            gone += 1
        except OSError:
            pass
    tidy(folder)
    return gone


def tidy(folder: Path) -> None:
    """Remove empty version folders, and the previous versions folder itself once it's empty."""
    base = folder / FOLDER
    try:
        if base.is_symlink() or not base.is_dir():
            return
        for d in base.iterdir():
            if STAMP.fullmatch(d.name) and d.is_dir() and not d.is_symlink() and not any(d.iterdir()):
                d.rmdir()
        if not any(base.iterdir()):
            base.rmdir()
    except OSError:
        pass


def restore(folder: Path, stamp: str, name: str) -> dict:
    """Put a previous version back as the current file. The current one (if any) is kept as a previous version
    first, so this can be undone. Returns {"size": the restored file's size, "kept": where the current one went}.
    Raises ValueError for a version that isn't there."""
    if not STAMP.fullmatch(stamp or ""):
        raise ValueError("That version isn't there.")
    base = folder / FOLDER
    version = next((d for d in base.iterdir() if d.name == stamp and d.is_dir() and not d.is_symlink()), None) \
        if base.is_dir() and not base.is_symlink() else None
    old = next((f for f in version.iterdir() if f.name == name), None) if version else None
    if old is None or _plain_file(old) is None:
        raise ValueError("That version isn't there.")
    current = folder / old.name
    kept = keep(current, max(_keep, 1) + 1) if _plain_file(current) else None   # (one more, so the restored one's spot is free)
    os.replace(old, current)
    tidy(folder)
    if kept is not None:
        prune(folder, old.name, max(_keep, 1))
    return {"size": current.stat().st_size, "kept": str(kept) if kept else None}


def delete_all(folder: Path) -> int:
    """Delete a product folder's previous versions (with its downloaded files). Returns how many files went."""
    n = len(listed(folder))
    base = folder / FOLDER
    if base.is_dir() and not base.is_symlink():
        shutil.rmtree(base, ignore_errors=True)
    return n


def size(folder: Path) -> int:
    return sum(v["size"] for v in listed(folder))
