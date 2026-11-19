"""The Local sync folder (issue #388): a folder on this computer whose contents are added to Local by themselves.

- Each folder put in it is listed where it is (as Add to Local's "list it where it is"); each file put in it directly
  is copied into Local. Each is a tile of its own.
- A file over 100 MB, or a folder over 1 GB, isn't added: Hoard says which, and why (Settings, under Local sync
  folder), and doesn't measure it again until it changes.
- It must be on a drive of this computer: a network share or a NAS is refused, as is a drive that doesn't answer
  (#368: a linked folder on a NAS that went away stopped the library loading).
- Hoard looks at it as it starts and every few minutes while it runs (a scheduled task), reading only what's new:
  what's in Local already, and what was too big before and hasn't changed, isn't read again.
- Something taken out of the folder marks its tile ("not in the sync folder any more"). It's taken out of Local only
  when you say so (Remove from Local), with its tags and its places in sets kept until then.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import reach
from .paths import data_dir, on_network

MAX_FILE = 100 * 1024 * 1024        # a file bigger than this isn't added
MAX_FOLDER = 1024 * 1024 * 1024     # nor a folder bigger than this
EVERY = 120                         # seconds between looks while Hoard runs
STATE = "local-sync.json"           # in Hoard's own folder: what was too big (and why), and the last look


def check_folder(cfg: dict, value: str) -> Path:
    """The sync folder you chose, checked: a folder on this computer that answers, not inside one of Hoard's library
    folders (nor holding one). Raises ValueError saying why it can't be."""
    from . import libraries
    from .config import root_dir
    from .local import local_dir
    p = Path(os.path.expandvars(str(value or "").strip())).expanduser()
    if not p.is_absolute():
        raise ValueError("Choose the sync folder by its full path.")
    if on_network(p):
        raise ValueError("The sync folder has to be on a drive of this computer, not a network share or a NAS.")
    if reach.away([str(p)], 3):
        raise ValueError(f"That drive doesn't answer just now: {p.anchor or p}")
    if not p.is_dir():
        raise ValueError("That folder isn't there.")
    if _inside(p, data_dir()) or _inside(data_dir(), p):   # (its sign-ins and settings would be added to Local)
        raise ValueError("The sync folder can't be Hoard's own folder, nor hold it.")
    for lib in [*libraries.roots(cfg, root_dir(cfg)), local_dir(root_dir(cfg))]:
        if _inside(p, lib) or _inside(lib, p):
            raise ValueError("The sync folder can't be inside your downloads or library folders, nor hold one.")
    return p


def _inside(a: Path, b: Path) -> bool:
    """Is a the same folder as b, or inside it?"""
    try:
        a, b = Path(a).resolve(), Path(b).resolve()
    except OSError:
        return False
    return a == b or b in a.parents


def _load() -> dict:
    """What the last looks found: {"skipped": {path: [mtime_ns, size, why]}, "last": {...}}."""
    try:
        raw = json.loads((data_dir() / STATE).read_text("utf-8"))
        return raw if isinstance(raw, dict) and isinstance(raw.get("skipped"), dict) else {"skipped": {}}
    except (OSError, ValueError):
        return {"skipped": {}}


def _save(state: dict) -> None:
    """Keep what the last looks found."""
    from .safety import write_file_safely
    write_file_safely(data_dir() / STATE, json.dumps(state, ensure_ascii=False))


def _folder_size(folder: str, stop_at: int) -> int:
    """A folder's size in bytes, without following links; it stops counting once past stop_at."""
    total = 0
    for top, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(top, d))]
        for n in names:
            try:
                total += os.stat(os.path.join(top, n), follow_symlinks=False).st_size
            except OSError:
                continue
            if total > stop_at:
                return total
    return total


def scan(cfg: dict, root: Path) -> dict:
    """One look at the sync folder: what's new added, what's too big noted, what's gone marked.
    {"added": [names], "skipped": [{"name", "why"}], "gone": n, "error": why it couldn't be looked at, or None}."""
    from . import local
    from .downloader import Manifest, build_catalog
    out = {"added": [], "skipped": [], "gone": 0, "error": None}
    value = str(cfg.get("local_sync") or "").strip()
    if not value:
        return out
    folder = Path(value)
    state = _load()
    if on_network(folder) or reach.away([value], 3) or not folder.is_dir():
        out["error"] = f"The sync folder isn't there, or its drive doesn't answer: {folder}"
        _save({**state, "last": {"added": [], "gone": 0, "error": out["error"]}})   # (Settings says so)
        return out
    skipped_before, skipped = state.get("skipped") or {}, {}
    have = local.added_sources(root)
    for entry in sorted(os.scandir(folder), key=lambda e: e.name.lower()):
        if entry.name.startswith(".") or entry.name.lower() in local.SKIP or entry.is_symlink():
            continue
        try:
            where = str(Path(entry.path).resolve())
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if where in have or entry.path in have:
            continue
        stamp = [st.st_mtime_ns, st.st_size]
        before = skipped_before.get(where)
        if isinstance(before, list) and before[:2] == stamp:   # (too big before, and not changed since: not read again)
            skipped[where] = before
            continue
        is_file = entry.is_file(follow_symlinks=False)
        if is_file and st.st_size > MAX_FILE:
            skipped[where] = [*stamp, "It's over 100 MB."]
            continue
        if not is_file and _folder_size(entry.path, MAX_FOLDER) > MAX_FOLDER:
            skipped[where] = [*stamp, "It's over 1 GB."]
            continue
        try:
            local.add(cfg, root, entry.path, copy=is_file, catalog=False)
            out["added"].append(entry.name)
        except (ValueError, OSError) as e:
            skipped[where] = [*stamp, str(e)]
    manifest, changed = Manifest(local.local_dir(root)), False
    for rec in manifest.assets.values():   # what came from the sync folder and has gone from it, marked (not removed)
        source = rec.get("source") or rec.get("location") if isinstance(rec, dict) else None
        if not source or not _inside(Path(source), folder):
            continue
        gone = not os.path.exists(source)
        out["gone"] += gone
        if bool(rec.get("sync_gone")) != gone:
            if gone:
                rec["sync_gone"] = True
            else:
                rec.pop("sync_gone", None)
            changed = True
    if changed:
        manifest.save()
    if out["added"] or changed:
        build_catalog(cfg, root)
    out["skipped"] = [{"name": Path(k).name, "why": v[2]} for k, v in skipped.items()]
    _save({"skipped": skipped, "last": {"added": out["added"][-50:], "gone": out["gone"], "error": out["error"]}})
    return out


def tick(srv) -> dict | None:
    """The scheduled look (as Hoard starts, then every EVERY seconds): skipped while a job is using Local, so the two
    never write its records at once."""
    if not str(srv.cfg.get("local_sync") or "").strip():
        return None
    if not srv.jobs.busy.acquire(blocking=False):
        return None
    try:
        from .config import root_dir
        done = scan(srv.cfg, root_dir(srv.cfg))
    finally:
        srv.jobs.busy.release()
        srv.jobs.kick()
    if done["added"] or done["gone"]:
        srv.forget_index()
    return done


def view(cfg: dict) -> dict:
    """For Settings: the sync folder, what wasn't added and why, and what the last look said."""
    state = _load()
    return {"folder": str(cfg.get("local_sync") or ""),
            "skipped": [{"name": Path(k).name, "why": v[2]} for k, v in (state.get("skipped") or {}).items()
                        if isinstance(v, list) and len(v) > 2][:200],
            "last": state.get("last") or {}}
