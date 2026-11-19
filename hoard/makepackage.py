"""A Unity package (.unitypackage) made from a Local item without Unity (issue #382; the research is in
docs/UNITYPACKAGE-FROM-LOCAL.md).

A .unitypackage is a gzipped tar with a folder per asset, named by its GUID: "pathname" (where it goes in the
project), "asset" (the file; a folder has none) and "asset.meta" (Unity's meta file: the asset's GUID, and how it's
imported). Hoard reads them already (vpm/unitypackage.py); this writes one.

- A file that has its own .meta beside it (one copied out of a Unity project) keeps it whole: its GUID, so whatever
  refers to it still finds it, and its import settings.
- A file without one gets a .meta Hoard writes: a new GUID and nothing else, which Unity fills in with its default
  import settings on import, as it does for a file dropped into a project. What referred to it by an older GUID
  can't find it; Hoard says how many files got a new GUID.
- Folders get a folder .meta (their own when it's there), so the folder tree goes in as one.
- Left out, and said: files Unity leaves out itself (hidden ones, and those ending in ~), stray .meta files with
  nothing beside them, and a .meta whose GUID another file has already, which gets a new one instead.

Everything goes under Assets/<the item's name>/, as Unity's own export of a folder does.
"""
from __future__ import annotations

import io
import os
import re
import secrets
import tarfile
import time
from pathlib import Path

from .safety import UnsafePath, rel_to_path

GUID_LINE = re.compile(r"^guid:\s*([0-9a-f]{32})\s*$", re.M)
MAX_META = 1 << 20                       # a .meta bigger than this isn't one
BANNED = set('<>:"|?*\\/\0')             # what can't be in the folder name the package puts it in
FILE_META = "fileFormatVersion: 2\nguid: {guid}\n"
FOLDER_META = ("fileFormatVersion: 2\nguid: {guid}\nfolderAsset: yes\nDefaultImporter:\n  externalObjects: {{}}\n"
               "  userData: \n  assetBundleName: \n  assetBundleVariant: \n")


def folder_name(name: str) -> str:
    """The folder under Assets/ the package puts an item in: its name, without what a path can't hold."""
    clean = "".join("_" if c in BANNED or ord(c) < 32 else c for c in str(name or "")).strip().strip(".").strip()
    return clean[:120] or "Local asset"


def _unity_skips(rel: str) -> bool:
    """A file Unity leaves out of a project itself: one whose path has a part starting with "." or ending with "~"."""
    return any(p.startswith(".") or p.endswith("~") for p in rel.split("/"))


def _own_meta(folder: Path, rel: str) -> tuple[bytes, str] | None:
    """A file's (or folder's) own .meta beside it, and its GUID, when it's a real one."""
    try:
        path = rel_to_path(folder, rel + ".meta")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_META:
            return None
        data = path.read_bytes()
    except (UnsafePath, OSError):
        return None
    m = GUID_LINE.search(data.decode("utf-8", "replace"))
    return (data, m.group(1)) if m else None


def _plain(folder: Path, rel: str) -> bool:
    """Is this a file inside the folder (not a link leading out of it)?"""
    try:
        rel_to_path(folder, rel)
        return True
    except UnsafePath:
        return False


def plan(folder: Path, files: list[str]) -> dict:
    """What a package of these files (paths relative to folder, as a Local item's record lists them) would hold:
    {"assets": [(rel, guid, meta bytes, kept)], "folders": [...the same, for each folder], "left_out": [(rel, why)],
    "new_ids": [rels given a new GUID]}. Nothing is written."""
    folder = Path(folder)
    have = set(files)
    used: set[str] = set()
    out = {"assets": [], "folders": [], "left_out": [], "new_ids": []}

    def guid_for(rel: str, is_folder: bool) -> tuple[str, bytes, bool]:
        """(GUID, .meta, kept): its own .meta when it has one whose GUID isn't taken, else a new one."""
        own = _own_meta(folder, rel)
        if own and own[1] not in used:
            used.add(own[1])
            return own[1], own[0], True
        guid = secrets.token_hex(16)
        while guid in used:
            guid = secrets.token_hex(16)
        used.add(guid)
        if own:   # (its GUID is another file's already: two copies of one asset, say)
            out["left_out"].append((rel + ".meta", "its GUID is another file's too, so this one gets a new GUID"))
        return guid, (FOLDER_META if is_folder else FILE_META).format(guid=guid).encode(), False

    wanted = []
    for rel in sorted(files):
        if _unity_skips(rel):
            out["left_out"].append((rel, "Unity leaves out hidden files and those ending in ~"))
        elif rel.lower().endswith(".meta"):
            if rel[:-5] not in have and not (folder / rel[:-5]).is_dir():
                out["left_out"].append((rel, "a .meta file with nothing beside it"))
        elif not _plain(folder, rel):
            out["left_out"].append((rel, "it's a link to somewhere outside its folder"))
        else:
            wanted.append(rel)
    folders = sorted({"/".join(rel.split("/")[:n]) for rel in wanted for n in range(1, rel.count("/") + 1)},
                     key=lambda r: (r.count("/"), r))
    for rel in folders:
        guid, meta, kept = guid_for(rel, True)
        out["folders"].append((rel, guid, meta, kept))
    for rel in wanted:
        guid, meta, kept = guid_for(rel, False)
        out["assets"].append((rel, guid, meta, kept))
        if not kept:
            out["new_ids"].append(rel)
    return out


def _add(tar: tarfile.TarFile, name: str, data: bytes | None = None, path: Path | None = None) -> None:
    """One member of the package, from bytes or from a file, read as it's written (a big file isn't held in memory)."""
    info = tarfile.TarInfo(name)
    info.mtime = int(time.time())
    info.mode = 0o644
    if path is not None:
        info.size = path.stat().st_size
        with path.open("rb") as stream:
            tar.addfile(info, stream)
    else:
        info.size = len(data or b"")
        tar.addfile(info, io.BytesIO(data or b""))


def make(folder: Path, files: list[str], name: str, out: Path) -> dict:
    """Write the package for a Local item's files to out (through out + ".part", so nothing half written is left).
    Returns {"path", "assets", "folders", "kept_ids", "new_ids": [...], "left_out": [(rel, why)]}."""
    folder, out = Path(folder), Path(out)
    p = plan(folder, files)
    if not p["assets"]:
        raise ValueError("There's nothing in it Unity would import.")
    top = "Assets/" + folder_name(name)
    root_guid = secrets.token_hex(16)
    part = out.with_name(out.name + ".part")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(part, "w:gz", format=tarfile.USTAR_FORMAT) as tar:
            _add(tar, f"{root_guid}/pathname", top.encode())
            _add(tar, f"{root_guid}/asset.meta", FOLDER_META.format(guid=root_guid).encode())
            for rel, guid, meta, _ in p["folders"]:
                _add(tar, f"{guid}/pathname", f"{top}/{rel}".encode())
                _add(tar, f"{guid}/asset.meta", meta)
            for rel, guid, meta, _ in p["assets"]:
                _add(tar, f"{guid}/asset", path=rel_to_path(folder, rel))
                _add(tar, f"{guid}/pathname", f"{top}/{rel}".encode())
                _add(tar, f"{guid}/asset.meta", meta)
        os.replace(part, out)
    finally:
        if part.exists():
            part.unlink()
    return {"path": str(out), "assets": len(p["assets"]), "folders": len(p["folders"]) + 1,
            "kept_ids": sum(1 for a in p["assets"] if a[3]), "new_ids": p["new_ids"], "left_out": p["left_out"]}
