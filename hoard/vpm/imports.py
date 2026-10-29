"""What Hoard put in a project from your library (issue #155), written into the project so it goes where the project
goes (another computer, version control):

- ProjectSettings/Hoard/imports.json: the list Hoard for Unity keeps of what was imported through it (ImportLog.cs),
  {"format": "hoard-unity-imports", "version": 1, "imports": [{"store", "name", "creator", "file", "imported_at"}]}.
  Hoard adds one entry for each product it puts in, marked "via": "hoard", with what it added ("added": the folders
  under Assets, or Packages/<name>), so Hoard for Unity knows the product is in the project and shows where.
- NOTE_NAME, beside Assets: the same, for you to read. Hoard only adds to it, a section each time; Unity ignores it.

Nothing here stops products going in: a list that can't be written is logged and left.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ..safety import DataFileError, read_json_file, write_file_safely
from .logbook import Warn

LOG_FILE = ("ProjectSettings", "Hoard", "imports.json")
NOTE_NAME = "Hoard imports.md"
MAX_LOG = 16 * 1024 * 1024        # as Hoard for Unity reads it
MAX_ADDED = 40                    # folders listed for one product

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+!|~])")


def _text(value, limit=300) -> str:
    """A name as written into the list: one line, at most limit characters."""
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _md(value) -> str:
    """Text for the Markdown list, with nothing in it read as Markdown (a name like "[Asset] *Hoodie*")."""
    return _MD_SPECIAL.sub(r"\\\1", _text(value))


def _code(path) -> str:
    """A path as Markdown code, its backticks swapped for quotes."""
    return "`" + _text(path, 400).replace("`", "'") + "`"


def entries(results: list[dict], when: str) -> list[dict]:
    """imports.json's entries for what went in (not what failed)."""
    out = []
    for r in results:
        if r.get("why"):
            continue
        e = {"store": _text(r.get("store")), "name": _text(r.get("name")), "creator": _text(r.get("creator")),
             "file": _text(r.get("file")), "imported_at": when, "via": "hoard",
             "added": [_text(a, 400) for a in (r.get("added") or [])[:MAX_ADDED]]}
        if r.get("package"):
            e["package"] = _text(r["package"], 214)
        if r.get("already_there") or r.get("in_the_way"):
            e["left"] = int(r.get("already_there") or 0) + int(r.get("in_the_way") or 0)
        out.append(e)
    return out


def _add_to_log(project: Path, new: list[dict]) -> None:
    """Add imports to the project's own record of what Hoard put in it (ProjectSettings/Hoard/imports.json)."""
    path = project.joinpath(*LOG_FILE)
    have: list = []
    if path.exists():
        try:
            doc = read_json_file(path, MAX_LOG)
            if not isinstance(doc, dict) or not isinstance(doc.get("imports"), list):
                raise DataFileError("not Hoard for Unity's list")
            have = doc["imports"]
        except (OSError, DataFileError, ValueError):
            # kept beside it, not written over, as Hoard for Unity does: the project's history isn't lost to one bad edit
            path.replace(path.with_name(path.name + ".unreadable-" + time.strftime("%Y%m%d%H%M%S", time.gmtime())))
            have = []
    path.parent.mkdir(parents=True, exist_ok=True)
    write_file_safely(path, json.dumps({"format": "hoard-unity-imports", "version": 1, "imports": have + new},
                                       indent=2, ensure_ascii=False) + "\n")


WHAT_PACKAGE = {"added": "Added", "updated": "Replaced an older copy with this version", "already-there":
                "The project already had this version or a newer one, so it was left as it was",
                "already-installed": "The project already has it from a repository, so it was left as it was"}


def section(results: list[dict], when_text: str) -> str:
    """One time's section of the list: each product, what it added, and what was left as it was or failed."""
    lines = [f"## {when_text}", ""]
    for r in results:
        by = f", by {_md(r['creator'])}" if r.get("creator") else ""
        store = f" ({_md(r['store'])})" if r.get("store") else ""
        lines.append(f"**{_md(r.get('name'))}**{by}{store}: {_code(r.get('label') or r.get('file'))}")
        if r.get("why"):
            lines.append(f"- Not put in: {_md(r['why'])}")
        elif r.get("package"):
            lines.append(f"- {WHAT_PACKAGE.get(r.get('result'), 'Added')}: the package {_code(r['package'])}, in "
                         f"{_code('Packages/' + r['package'])}")
        else:
            added = r.get("added") or []
            if added:
                lines.append("- Added: " + ", ".join(_code(a) for a in added[:MAX_ADDED]) +
                             (f" and {len(added) - MAX_ADDED} more" if len(added) > MAX_ADDED else ""))
            left = int(r.get("already_there") or 0) + int(r.get("in_the_way") or 0)
            if left:
                lines.append(f"- {left:,} of its assets were already in the project (or something else was where they "
                             f"go), so they were left as they were")
            if not added and not left:
                lines.append("- Nothing in it to add")
        lines.append("")
    return "\n".join(lines)


NOTE_HEAD = ("# What Hoard put in this project\n\n"
             "Hoard adds to this list each time it puts products from your library in this project. Hoard for Unity "
             "shows the same under each product, with a button to select what it added. This file is only for you to "
             "read: Unity doesn't use it, and deleting it changes nothing.\n\n")


def note(project, results: list[dict], log=None) -> None:
    """Add what just went into the project to both lists."""
    if not results:
        return
    project = Path(project)
    now = time.gmtime()
    try:
        _add_to_log(project, entries(results, time.strftime("%Y-%m-%dT%H:%M:%SZ", now)))
    except OSError as e:
        if log:
            log(Warn(f"Couldn't add them to the project's list of imports ({e})"))
    path = project / NOTE_NAME
    try:
        before = path.read_text("utf-8") if path.is_file() else ""
        if len(before) > MAX_LOG:   # (not likely: start again rather than grow without end)
            path.replace(path.with_name(path.stem + time.strftime(" %Y%m%d%H%M%S", now) + path.suffix))
            before = ""
        write_file_safely(path, (before or NOTE_HEAD) + section(results, time.strftime("%d %b %Y, %H:%M (UTC)", now)))
    except OSError as e:
        if log:
            log(Warn(f"Couldn't write {NOTE_NAME} ({e})"))
