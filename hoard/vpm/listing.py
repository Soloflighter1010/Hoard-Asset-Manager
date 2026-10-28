"""The list of projects: the Creator Companion's and ALCOM's, with what Hoard notes about each.

The list itself is theirs: settings.json's "userProjects", which both copy into vcc.liteDb when they start (and,
when a newer Creator Companion has dropped that key, vcc.liteDb alone). Hoard adds and removes projects there, so
the three programs keep one list. When the key is missing, Hoard writes it whole (every project vcc.liteDb has, and
the change), as ALCOM does, so neither program loses a project.

What only Hoard keeps (favourites, when you last opened a project from Hoard, and the products from your library you
put in it) is in vpm-projects.json in Hoard's own folder.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from ..paths import data_dir
from ..safety import DataFileError, clean_text, read_json_file, write_file_safely
from . import environment
from .project import TYPE_NAMES, UNKNOWN, summary

STATE = "vpm-projects.json"
MAX_PRELOADED = 500
MAX_PROJECT_TAGS = 12   # a project's tags (issue #190), and its folder: Hoard's own, never the Creator Companion's
_lock = threading.RLock()


def _key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


# ---- Hoard's own notes

def _state_path() -> Path:
    return data_dir() / STATE


def load_state() -> dict:
    try:
        raw = read_json_file(_state_path(), 16 << 20)
    except FileNotFoundError:
        return {"projects": {}}
    except (DataFileError, OSError):
        return {"projects": {}}
    projects = raw.get("projects") if isinstance(raw, dict) else None
    return {**(raw if isinstance(raw, dict) else {}), "projects": projects if isinstance(projects, dict) else {}}


def save_state(state: dict) -> None:
    import json
    write_file_safely(_state_path(), json.dumps(state, indent=1, ensure_ascii=False))


def backup_prefs() -> dict:
    """How the backups panel decides which backups are old, and where old ones were last moved to."""
    from . import backup
    raw = load_state().get("backups")
    raw = raw if isinstance(raw, dict) else {}
    keep = raw.get("keep") if raw.get("keep") in backup.KEEP_CHOICES else 3
    days = raw.get("days") if raw.get("days") in backup.DAYS_CHOICES else 30
    moved = raw.get("moved_to") if isinstance(raw.get("moved_to"), str) and Path(raw["moved_to"]).is_absolute() else ""
    return {"keep": keep, "days": days, "moved_to": moved}


def set_backup_prefs(**changes) -> dict:
    with _lock:
        state = load_state()
        state["backups"] = {**backup_prefs(), **changes}
        save_state(state)
        return backup_prefs()


def note(path: str, **changes) -> dict:
    """Change what Hoard notes about a project (favourite, opened, preloaded, ...), returning it."""
    with _lock:
        state = load_state()
        entry = state["projects"].setdefault(_key(path), {})
        entry["path"] = path
        for k, v in changes.items():
            if v is None:
                entry.pop(k, None)
            else:
                entry[k] = v
        if isinstance(entry.get("preloaded"), list):
            entry["preloaded"] = entry["preloaded"][-MAX_PRELOADED:]
        save_state(state)
        return entry


def organize(path: str, folder=None, tags=None) -> dict:
    """Issue #190: the folder a project is kept in on Hoard's list, and its tags, as you name them (ALCOM and the
    Creator Companion have only a favourite). folder: a name, or "" for none; tags: words, as tags are kept."""
    from ..tags import clean_tag
    changes: dict = {}
    if folder is not None:
        name = clean_text(folder if isinstance(folder, str) else "", 60)
        changes["folder"] = name or None
    if tags is not None:
        kept = list(dict.fromkeys(t for t in (clean_tag(x) for x in (tags if isinstance(tags, list) else [])[:40]) if t))
        changes["tags"] = kept[:MAX_PROJECT_TAGS] or None
    return note(path, **changes)


def forget(path: str) -> None:
    """Forget what Hoard noted about a project (a deleted one): its favourite, what was put in it, ..."""
    with _lock:
        state = load_state()
        if state["projects"].pop(_key(path), None) is not None:
            save_state(state)


def add_preloaded(path: str, items: list[dict]) -> None:
    """Note products from the library that went into a project (for its credits and the page)."""
    with _lock:
        state = load_state()
        entry = state["projects"].setdefault(_key(path), {"path": path})
        have = entry.get("preloaded") if isinstance(entry.get("preloaded"), list) else []
        known = {(i.get("tag_key"), i.get("file")) for i in have if isinstance(i, dict)}
        for i in items:
            if (i.get("tag_key"), i.get("file")) not in known:
                have.append({**i, "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
        entry["preloaded"] = have[-MAX_PRELOADED:]
        save_state(state)


# ---- the shared list

def shared_paths(settings: environment.Settings | None = None) -> tuple[list[str], dict[str, dict]]:
    """(the projects, in their order; vcc.liteDb's record of each, by path)."""
    settings = settings or environment.Settings.load()
    db = environment.database(settings.folder)
    records = {_key(d["Path"]): d for d in db["projects"] if isinstance(d.get("Path"), str)}
    listed = settings.user_projects()
    if listed is None:
        listed = [d["Path"] for d in db["projects"] if isinstance(d.get("Path"), str)]
    return listed, records


def projects(progress=None) -> list[dict]:
    """Every project for the page: name, folder, Unity, kind, favourite, when made and opened, whether the folder is
    still there; most recently opened first. progress(how many there are) gives a function to call with how many
    are read (issue #200: Projects' splash counts them)."""
    try:
        settings = environment.Settings.load()
    except DataFileError as e:
        raise environment.DataFileError(f"The Creator Companion's settings can't be read ({e}).") from None
    listed, records = shared_paths(settings)
    state = load_state()["projects"]
    out, seen = [], set()
    tick = progress(len(listed)) if progress else None
    for n, path in enumerate(listed, 1):
        if tick:
            tick(n)
        k = _key(path)
        if k in seen:
            continue
        seen.add(k)
        record, mine = records.get(k, {}), state.get(k, {})
        info = summary(path)
        kind = info["type"] if info["type"] is not None else record.get("Type", UNKNOWN)
        opened = max(_ms(record.get("LastModified")), _iso_ms(mine.get("opened")))
        out.append({
            "path": path, "name": clean_text(Path(path).name, 200) or path,
            "exists": info["exists"], "unity": info["unity"] or (record.get("UnityVersion") if isinstance(record.get("UnityVersion"), str) else None),
            "type": kind, "type_name": TYPE_NAMES.get(kind, "Unknown"),
            "favorite": bool(mine["favorite"]) if "favorite" in mine else record.get("Favorite") is True,
            "created": _ms(record.get("CreatedAt")) or None, "opened": opened or None,
            "preloaded": len(mine.get("preloaded") or []),
            "folder": clean_text(mine.get("folder") if isinstance(mine.get("folder"), str) else "", 60) or None,   # (#190)
            "tags": [t for t in mine.get("tags") or [] if isinstance(t, str)][:MAX_PROJECT_TAGS] if isinstance(mine.get("tags"), list) else [],
        })
    out.sort(key=lambda p: (p["opened"] or 0), reverse=True)
    return out


def _ms(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _iso_ms(value) -> int:
    if not isinstance(value, str):
        return 0
    try:
        return int(time.mktime(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")) * 1000)
    except (ValueError, OverflowError):
        return 0


def add(path: str) -> None:
    """List a project (first, as ALCOM adds them)."""
    with _lock:
        settings = environment.Settings.load()
        listed, _ = shared_paths(settings)
        listed = [p for p in listed if _key(p) != _key(path)]
        settings.set_projects([path] + listed)
        settings.save()


def remove(path: str) -> bool:
    """Take a project off the list (its folder is left alone)."""
    with _lock:
        settings = environment.Settings.load()
        listed, _ = shared_paths(settings)
        kept = [p for p in listed if _key(p) != _key(path)]
        if len(kept) == len(listed):
            return False
        settings.set_projects(kept)
        settings.save()
        return True


def is_listed(path: str) -> bool:
    return find(path) is not None


def find(path: str) -> str | None:
    """The list's own copy of a project's path (the one in settings.json), or None when it isn't on the list."""
    listed, _ = shared_paths()
    return next((p for p in listed if _key(p) == _key(path)), None)
