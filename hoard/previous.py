"""Previous versions (Downloads): when a download replaces a file (a creator's update), the file it replaces is kept.

The old file goes to "_Previous versions/<when>/<its name>" in the folder it's in (the product's own folder, or the
subfolder of it a file is in), beside the new one: on the same drive (so keeping it is a rename, not a copy), and found
by anyone who opens the folder. How many are kept for
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
from pathlib import Path, PurePosixPath

FOLDER = "_Previous versions"
STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{6}(?:-\d+)?")
MAX_KEEP = 10

_keep = 1   # set from the settings (set_keep) by the server and the command line


def set_keep(n) -> None:
    """How many previous versions to keep of each file (keep_previous); 1 for anything that isn't a number."""
    global _keep
    _keep = max(0, min(MAX_KEEP, n)) if isinstance(n, int) and not isinstance(n, bool) else 1


def keeping() -> int:
    """How many previous versions are kept of each file."""
    return _keep


def _plain_file(p: Path) -> os.stat_result | None:
    """A file's details when it's a plain file (not a link or a folder), else None."""
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


def _places(folder: Path, files=()) -> list[str]:
    """The folders in a product folder where its files' previous versions are: beside each file (the product folder
    itself, and each subfolder a file is in: a Gumroad product's "Textures/body.png"), as paths from it ("" for it)."""
    out = {""}
    for f in files or ():
        parts = PurePosixPath(str(f).replace("\\", "/")).parent.parts if f else ()
        # plain folder names only: no "..", no drive or root ("C:", "/"), and never a previous versions folder
        if parts and all(p not in ("", ".", "..", FOLDER) and ":" not in p and "/" not in p for p in parts):
            out.add("/".join(parts))
    return sorted(out)


def _here(folder: Path, sub: str) -> Path | None:
    """The folder sub (from _places) in the product folder, when it's a real folder all the way down (no links)."""
    here = folder
    for part in sub.split("/") if sub else ():
        here = here / part
        if here.is_symlink() or not here.is_dir():
            return None
    return here


def listed(folder: Path, files=()) -> list[dict]:
    """A product folder's previous versions, newest first: [{"stamp", "file", "size", "path"}]. files: the product's
    files, as paths in its folder, for those kept beside a file in a subfolder ("file" is then its path, such as
    "Textures/body.png"); "path" is where the version is, from the product folder."""
    out = []
    for sub in _places(folder, files):
        try:
            here = _here(folder, sub)
            base = here / FOLDER if here is not None else None
            if base is None or base.is_symlink() or not base.is_dir():
                continue
            for d in base.iterdir():
                if not STAMP.fullmatch(d.name) or d.is_symlink() or not d.is_dir():
                    continue
                for f in d.iterdir():
                    st = _plain_file(f)
                    if st is not None:
                        name = f"{sub}/{f.name}" if sub else f.name
                        out.append({"stamp": d.name, "file": name, "size": st.st_size,
                                    "path": f"{sub + '/' if sub else ''}{FOLDER}/{d.name}/{f.name}"})
        except OSError:
            continue
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


def restore(folder: Path, stamp: str, name: str, files=()) -> dict:
    """Put a previous version back as the current file. stamp and name: one listed(folder, files) gives (in a
    subfolder, name is its path: "Textures/body.png"); only one of those is ever touched, never a path made from
    what was asked. The current one (if any) is kept as a previous version first, so this can be undone. Returns
    {"size": the restored file's size, "kept": where the current one went}. Raises ValueError for a version that
    isn't there."""
    v = next((v for v in listed(folder, files) if v["stamp"] == stamp and v["file"] == name), None)
    sub = v["file"].rpartition("/")[0] if v else ""
    here = _here(folder, sub) if v else None
    old = here / FOLDER / v["stamp"] / v["file"].rpartition("/")[2] if here is not None else None
    if old is None or _plain_file(old) is None:
        raise ValueError("That version isn't there.")
    current = here / old.name
    kept = keep(current, max(_keep, 1) + 1) if _plain_file(current) else None   # (one more, so the restored one's spot is free)
    os.replace(old, current)
    tidy(here)
    if kept is not None:
        prune(here, old.name, max(_keep, 1))
    return {"size": current.stat().st_size, "kept": str(kept) if kept else None}


def delete_all(folder: Path, files=()) -> int:
    """Delete a product folder's previous versions (with its downloaded files), beside each of its files. Returns
    how many files went."""
    n = len(listed(folder, files))
    for sub in _places(folder, files):
        here = _here(folder, sub)
        if here is not None and (here / FOLDER).is_dir() and not (here / FOLDER).is_symlink():
            shutil.rmtree(here / FOLDER, ignore_errors=True)
    return n


def size(folder: Path, files=()) -> int:
    """How much space the previous versions in a product's folder take."""
    return sum(v["size"] for v in listed(folder, files))
