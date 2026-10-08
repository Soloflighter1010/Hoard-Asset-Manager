"""Disk space (Downloads, Disk space): the same file kept more than once, across products and library folders.

Read from the fingerprints the integrity check keeps in each store's _manifest.json (sha256, with the file's size and
modification time when it was read): nothing is read or hashed here, and a file whose fingerprint is missing or out
of date is only counted, so the page can say a check would find more. Writes nothing.
"""
from __future__ import annotations

import os
import stat as _stat
from pathlib import Path

from .libraries import available
from .downloader import STORE_DIRS, Manifest, UnsafePath, rel_to_path
from .tags import tag_key

MIN_SIZE = 1024 * 1024   # smaller files (a readme, a licence, a preview picture) are left out: little to gain
MAX_GROUPS = 2000


def copies(roots: list[Path], hidden: frozenset | set = frozenset(), min_size: int = MIN_SIZE) -> dict:
    """Files kept more than once. roots: every library folder, the downloads folder first (libraries.roots); a copy
    names its folder by its number there, as the Downloads page does. hidden: products (by tag_key) to leave out,
    while the hidden library is locked.

    Returns {"groups": [{"size", "copies": [{"library", "folder", "file", "store", "name"}]}], biggest saving first,
    "unchecked": files of at least min_size with no up-to-date fingerprint}."""
    by_hash: dict[str, list[dict]] = {}
    unchecked = 0
    for n, base in enumerate(roots):
        if not available(base):
            continue   # a library folder whose drive isn't connected
        for store in STORE_DIRS.values():
            sdir = base / store
            if not (sdir / "_manifest.json").is_file():
                continue
            for rec in Manifest(sdir).assets.values():
                if not rec.get("files") or rec.get("location"):
                    continue   # (a Local item listed where it is: your own folder, not Hoard's space)
                if tag_key(store, rec.get("name") or "") in hidden:
                    continue
                try:
                    folder = rel_to_path(sdir, rec["folder"])
                except (UnsafePath, KeyError, TypeError):
                    continue
                for f in rec["files"].values():
                    try:
                        st = os.stat(rel_to_path(folder, f.get("path")), follow_symlinks=False)
                    except (UnsafePath, OSError, TypeError):
                        continue
                    if not _stat.S_ISREG(st.st_mode) or st.st_size < min_size:
                        continue
                    digest = f.get("sha256")
                    if not (isinstance(digest, str) and len(digest) == 64 and f.get("mtime_ns") == st.st_mtime_ns
                            and f.get("size") in (None, st.st_size)):
                        unchecked += 1
                        continue
                    by_hash.setdefault(digest, []).append({
                        "library": n, "folder": f"{store}/{rec['folder']}", "file": f["path"], "store": store,
                        "name": rec.get("name") or "", "size": st.st_size})
    groups = []
    for found in by_hash.values():
        if len(found) < 2:
            continue
        size = found[0]["size"]
        groups.append({"size": size, "copies": [{k: c[k] for k in ("library", "folder", "file", "store", "name")} for c in found]})
    groups.sort(key=lambda g: -g["size"] * (len(g["copies"]) - 1))
    return {"groups": groups[:MAX_GROUPS], "unchecked": unchecked}
