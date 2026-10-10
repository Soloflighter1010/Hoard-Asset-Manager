"""Backup and restore (Settings, Backup): what you've set up in Hoard, in one file, to keep or to move to another
computer.

A backup holds your settings (the downloads folder and other library folders as places, used only where they exist),
your tags, sets, archive and removed choices, and your library list, without its download links. Hidden products,
with the PIN and recovery words that hide them (as their slow hashes, never the words), go in only while the hidden
library is unlocked: a backup made while it's locked leaves them out, so the file never names them.

It never holds your store sign-ins, your itch.io key, the key Hoard seals its records with, or anything downloaded:
sign in to your stores again on the new computer, and copy the downloads folder yourself.

Restoring checks everything in the file the way Hoard checks what you change in Settings, saves a backup of how
things were first (so a restore can be undone), and replaces your settings, tags, sets and choices with the
backup's. The library list fills in only stores that have nothing listed yet: a store already read here is newer.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import __version__
from .paths import documents_dir

FORMAT = {"format": "hoard-backup", "version": 1}
MAX_BYTES = 64 * 1024 * 1024
SETTINGS = ("browser_channel", "offline_images", "check_for_updates", "beta_updates", "close_to_taskbar",
            "notify_found", "routine_hours", "download_retries", "keep_previous", "new_days", "display",
            "request_delay", "payhip_shops", "stores")
ITEM_FIELDS = ("store", "id", "name", "creator", "creator_url", "thumbnail", "url", "variants", "archived", "gift",
               "added")   # not download_url or files: those are links to download what you bought


class BackupError(ValueError):
    """A file that isn't a Hoard backup, or one Hoard can't use."""


def backups_dir() -> Path:
    """Where backups go: a folder in Documents, outside Hoard's own, so uninstalling Hoard leaves them."""
    return documents_dir() / "Hoard backups"


def make(cfg: dict, settings: dict, lib, unlocked: bool) -> dict:
    """The backup, as a document. settings: what Settings shows (server.public_settings)."""
    from .marks import MarkStore
    from .sets import SetStore
    from .tags import TagStore
    from . import libraries
    from .config import root_dir
    marks = MarkStore().load()
    items, stores = lib.snapshot()
    chosen = {"archived": sorted(marks["archived"]), "unarchived": sorted(marks["unarchived"]),
              "removed": sorted(marks["removed"])}
    if unlocked and marks.get("pin"):
        chosen.update(hidden=sorted(marks["hidden"]), pin=marks["pin"], recovery=marks["recovery"])
    return {
        **FORMAT, "made": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "hoard": __version__,
        "settings": {**{k: settings[k] for k in SETTINGS if k in settings}, "root": str(root_dir(cfg)),
                     "library_folders": [str(f) for f in libraries.other_folders(cfg)]},
        "tags": TagStore().load(),
        "sets": SetStore().load()["sets"],
        "marks": chosen,
        "library": {"items": [{k: i.get(k) for k in ITEM_FIELDS} for i in items],
                    "stores": {s: {k: v for k, v in info.items() if k in ("count", "updated", "first_read", "source")}
                               for s, info in stores.items()}},
    }


def save(doc: dict, folder: Path | None = None, label: str = "") -> Path:
    """Write a backup to a new file (never over another) and return where it went."""
    from .safety import write_file_safely
    folder = folder or backups_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"Hoard backup {time.strftime('%Y-%m-%d %H%M')}{label}"
    path, n = folder / f"{stem}.json", 2
    while path.exists():
        path, n = folder / f"{stem} ({n}).json", n + 1
    write_file_safely(path, json.dumps(doc, ensure_ascii=False, indent=1))
    return path


def read(data: bytes | str) -> dict:
    """A backup file's contents, checked to be one. Raises BackupError."""
    if len(data) > MAX_BYTES:
        raise BackupError("That file is far larger than a Hoard backup.")
    try:
        doc = json.loads(data)
    except (ValueError, RecursionError, UnicodeDecodeError):
        raise BackupError("That isn't a Hoard backup (it can't be read as one).") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT["format"]:
        raise BackupError("That isn't a Hoard backup.")
    if not isinstance(doc.get("version"), int) or doc["version"] > FORMAT["version"]:
        raise BackupError("That backup was made by a newer Hoard. Update Hoard, then restore it.")
    return doc


def summary(doc: dict) -> dict:
    """What a backup holds, counted, for the page to ask about before restoring it."""
    from .sets import SetStore
    from .tags import TagStore
    marks = doc.get("marks") if isinstance(doc.get("marks"), dict) else {}
    lib = doc.get("library") if isinstance(doc.get("library"), dict) else {}
    return {
        "made": doc.get("made") if isinstance(doc.get("made"), str) else None,
        "hoard": doc.get("hoard") if isinstance(doc.get("hoard"), str) else None,
        "tags": len(TagStore.sanitize(doc.get("tags"))["tags"]),
        "sets": len(SetStore.sanitize({"sets": doc.get("sets")})["sets"]),
        "items": len(lib.get("items")) if isinstance(lib.get("items"), list) else 0,
        "hidden": isinstance(marks.get("hidden"), list) and isinstance(marks.get("pin"), dict),
        "settings": isinstance(doc.get("settings"), dict),
    }


def restore(doc: dict, cfg: dict, lib, apply_settings, add_folder) -> dict:
    """Put a backup's contents in place. apply_settings(cfg, change) checks settings as Settings does (raising
    ValueError), returning the change to make; add_folder(path) adds a library folder (raising ValueError). Returns
    {"settings": [what was taken], "skipped": [what wasn't, and why], "items": library items added}."""
    from .config import deep_merge
    from .marks import KINDS, MarkStore, _SCRYPT
    from .sets import SetStore
    from .tags import TAG_KEY_RX, TagStore
    report = {"settings": [], "skipped": [], "items": 0}
    given = doc.get("settings") if isinstance(doc.get("settings"), dict) else {}
    for key in SETTINGS:
        if key not in given:
            continue
        try:
            deep_merge(cfg, apply_settings(cfg, {key: given[key]}))
            report["settings"].append(key)
        except (ValueError, TypeError, AttributeError):
            report["skipped"].append(f"the setting {key}, which isn't one this Hoard can use")
    root = given.get("root")
    if isinstance(root, str) and root:
        if Path(root).is_dir():
            deep_merge(cfg, apply_settings(cfg, {"root": root}))
            report["settings"].append("root")
        else:
            report["skipped"].append(f"the downloads folder {root[:200]}, which isn't on this computer")
    for folder in given.get("library_folders") if isinstance(given.get("library_folders"), list) else []:
        try:
            add_folder(str(folder)[:1000])
        except ValueError as e:
            report["skipped"].append(f"the library folder {str(folder)[:200]} ({e})")
    from . import sets as _sets, tags as _tags
    if isinstance(doc.get("tags"), dict):
        with _tags._tag_lock:
            TagStore()._save(TagStore.sanitize(doc["tags"]))
    if isinstance(doc.get("sets"), list):
        with _sets._lock:
            SetStore()._save(SetStore.sanitize({"sets": doc["sets"]}))
    marks = doc.get("marks") if isinstance(doc.get("marks"), dict) else {}
    with MarkStore._lock:
        ms = MarkStore()
        now = ms.load()
        for kind in KINDS:
            if kind == "hidden" and not isinstance(marks.get("pin"), dict):
                continue   # a backup made while locked: the hidden library here stays as it is
            values = marks.get(kind) if isinstance(marks.get(kind), list) else []
            now[kind] = {v for v in values if isinstance(v, str) and TAG_KEY_RX.match(v)}
        for field in ("pin", "recovery"):
            h = marks.get(field)
            if (isinstance(h, dict) and isinstance(h.get("salt"), str) and isinstance(h.get("hash"), str)
                    and all(h.get(k) == v for k, v in _SCRYPT.items())):
                now[field] = h
        ms._save(now)
    lib_doc = doc.get("library") if isinstance(doc.get("library"), dict) else {}
    clean = lib.sanitize({"items": lib_doc.get("items") if isinstance(lib_doc.get("items"), list) else [],
                          "stores": lib_doc.get("stores") if isinstance(lib_doc.get("stores"), dict) else {}})
    have, _ = lib.snapshot()
    listed = {i["store"] for i in have}
    for store_name in sorted({i["store"] for i in clean["items"]} - listed):
        mine = [i for i in clean["items"] if i["store"] == store_name]
        lib.merge_store(store_name, mine)
        report["items"] += len(mine)
    return report
