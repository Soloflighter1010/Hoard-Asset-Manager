"""Library folders: Hoard's downloads folder, and any others you add (another drive, an external disk).

The downloads folder (Settings: Downloads folder) is where new downloads go. Each other library folder is laid out
the same way, a folder per store with its own sealed _manifest.json, and Hoard reads them all as one library: the
Downloads page, catalog.json (and so Hoard for Unity), the routine checks, and syncing. A product already in one of
your folders is kept up to date where it is; you can move one to another of your folders (move_product).

A folder on a drive that isn't connected is left alone, not taken as emptied: what Hoard last saw in it is kept in
library_folders.json in Hoard's app-data folder, so a sync never downloads those products again into the downloads
folder while their drive is away.

Folders are named in config.json ("library_folders", full paths) and in Settings. One can't be inside another, or
contain one, or be (or be inside) Hoard's own app-data folder or the editable copies' folder.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import edits_dir, root_dir
from .paths import data_dir
from .safety import DataFileError, read_json_file, write_file_safely

MAX_FOLDERS = 10   # other library folders, besides the downloads folder


def _plain(value) -> Path | None:
    """A folder as config.json names it, as a full path written the system's way; None when it isn't one."""
    text = str(value or "").strip()
    if not text or len(text) > 1000 or "\x00" in text:
        return None
    path = Path(os.path.expandvars(text)).expanduser()
    if not path.is_absolute():
        return None
    return Path(os.path.normpath(str(path)))


def _same_or_inside(a: Path, b: Path) -> bool:
    """Is a the same folder as b, or inside it? (Compared as written, and as resolved where they exist.)"""
    pairs = [(a, b)]
    try:
        pairs.append((a.resolve(), b.resolve()))
    except OSError:
        pass
    for x, y in pairs:
        x, y = Path(os.path.normcase(str(x))), Path(os.path.normcase(str(y)))
        if x == y or y in x.parents:
            return True
    return False


def other_folders(cfg: dict) -> list[Path]:
    """The library folders besides the downloads folder, as config.json names them, in order. Any that couldn't be
    one (not a full path, the downloads folder itself, inside or around another) is left out."""
    root = root_dir(cfg)
    kept: list[Path] = []
    for value in (cfg.get("library_folders") or [])[:MAX_FOLDERS] if isinstance(cfg.get("library_folders"), list) else []:
        path = _plain(value)
        if path is None or _same_or_inside(path, root) or _same_or_inside(root, path):
            continue
        if any(_same_or_inside(path, k) or _same_or_inside(k, path) for k in kept):
            continue
        kept.append(path)
    return kept


def roots(cfg: dict, root: Path | None = None) -> list[Path]:
    """Every library folder: the downloads folder (or root) first, then the others."""
    return [root if root is not None else root_dir(cfg)] + other_folders(cfg)


def available(folder: Path) -> bool:
    """Is a library folder there to read (its drive connected), and a real folder rather than a link to one?"""
    try:
        return folder.is_dir() and not folder.is_symlink()
    except OSError:
        return False


def check_new_folder(cfg: dict, value) -> Path:
    """A folder you want to add as a library folder, checked. Raises ValueError saying what's wrong."""
    path = _plain(value)
    if path is None:
        raise ValueError("Choose the folder as a full path, such as E:\\VRChat\\Hoard.")
    if not path.is_dir():
        raise ValueError("That folder isn't there. Connect its drive, or create the folder, then add it.")
    if path.is_symlink():
        raise ValueError("That's a shortcut (a link). Choose the folder it leads to.")
    root = root_dir(cfg)
    if _same_or_inside(path, root) or _same_or_inside(root, path):
        raise ValueError("That's the downloads folder, or inside it, or around it. Choose a folder of its own.")
    for other in other_folders(cfg):
        if _same_or_inside(path, other) or _same_or_inside(other, path):
            raise ValueError(f"That's already a library folder, or inside or around one ({other}).")
    for own, what in ((data_dir(), "Hoard's own app-data folder"), (edits_dir(cfg), "where editable copies go")):
        if _same_or_inside(path, own) or _same_or_inside(own, path):
            raise ValueError(f"That's {what}, or inside or around it. Choose another folder.")
    if len(other_folders(cfg)) >= MAX_FOLDERS:
        raise ValueError(f"Hoard keeps up to {MAX_FOLDERS} other library folders.")
    return path


def address(cfg: dict, folder: Path) -> int | None:
    """Which library folder this is, as the pages name it: 0 for the downloads folder, 1, 2... for the others in
    order; None when it isn't one of them."""
    for n, r in enumerate(roots(cfg)):
        if _same_or_inside(folder, r) and _same_or_inside(r, folder):
            return n
    return None


def resolve(cfg: dict, place: str) -> tuple[Path, str] | None:
    """A place as the pages name it, "Booth/Creator/Name/file" in the downloads folder or "@2/Booth/..." in the second
    other library folder, as (that library folder, the path inside it); None for a library folder that isn't one."""
    place = str(place or "")
    if not place.startswith("@"):
        return root_dir(cfg), place
    number, _, rest = place[1:].partition("/")
    folders = roots(cfg)
    if not number.isdigit() or not 1 <= int(number) < len(folders):
        return None
    return folders[int(number)], rest


def free_space(folder: Path) -> int | None:
    """Bytes free on a library folder's drive, or None when it can't be told (its drive isn't connected)."""
    import shutil
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return None


# ----------------------------------------------------------------------------- what each folder held, last seen

def _seen_file() -> Path:
    return data_dir() / "library_folders.json"


def _load_seen() -> dict:
    try:
        raw = read_json_file(_seen_file()) if _seen_file().is_file() else {}
    except (DataFileError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def remember(folder: Path, store_dir: str, keys) -> None:
    """Note which products a library folder holds for a store, as just read from it."""
    keys = sorted(str(k) for k in keys)[:100000]
    seen = _load_seen()
    entry = seen.setdefault(str(folder), {})
    if not isinstance(entry, dict):
        entry = seen[str(folder)] = {}
    if entry.get(store_dir) == keys:
        return
    entry[store_dir] = keys
    try:
        write_file_safely(_seen_file(), json.dumps(seen, ensure_ascii=False))
    except OSError:
        pass   # only a precaution for when the drive is away


def away(cfg: dict, store_dir: str) -> dict[str, Path]:
    """Products of a store last seen in a library folder whose drive isn't connected now: key -> that folder. A sync
    leaves these alone rather than downloading them again into the downloads folder."""
    seen = _load_seen()
    out: dict[str, Path] = {}
    for folder in other_folders(cfg):
        if available(folder):
            continue
        keys = (seen.get(str(folder)) or {}).get(store_dir) if isinstance(seen.get(str(folder)), dict) else None
        for key in keys if isinstance(keys, list) else []:
            out.setdefault(str(key), folder)
    return out


def label(folder: Path, main: bool = False) -> str:
    """A library folder's short name, for its tab: "Downloads folder", or the folder's name with its drive ("Hoard
    (E:)" on Windows), or on a Mac or Linux the drive's name it's on ("Hoard (Backup)" for /Volumes/Backup/Hoard)."""
    if main:
        return "Downloads folder"
    name = folder.name or str(folder)
    if folder.drive:
        return f"{name} ({folder.drive})"
    parts = folder.parts
    for mount in ("Volumes", "media", "mnt", "run"):   # /Volumes/<drive>, /media/<you>/<drive>, /run/media/<you>/<drive>
        if mount in parts[:3]:
            rest = parts[parts.index(mount) + 1:]
            rest = rest[1:] if mount in ("media", "run") and len(rest) > 2 else rest
            rest = rest[1:] if mount == "run" and rest and rest[0] == "media" else rest
            if len(rest) > 1:
                return f"{name} ({rest[0]})"
    return name


def view(cfg: dict) -> list[dict]:
    """The library folders, for the pages: each one's number, path, short name (label), whether its drive is
    connected, and the space free on it. The downloads folder is number 0."""
    out = []
    for n, folder in enumerate(roots(cfg)):
        there = available(folder)
        out.append({"n": n, "path": str(folder), "label": label(folder, n == 0), "main": n == 0, "available": there,
                    "free": free_space(folder) if there else None})
    names = [f["label"] for f in out]
    for f in out:   # two folders with the same name: their paths tell them apart
        if names.count(f["label"]) > 1 and not f["main"]:
            f["label"] = " / ".join(Path(f["path"]).parts[-2:])
    return out
