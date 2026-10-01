"""Projects: the Unity projects that use your assets, and their credits lists (issue #86).

Hoard for Unity (0.4.0 and newer) writes a report into projects/ in Hoard's app-data folder each time a project's
window settles: the project's name and folder, every product it uses (all of it, or part, or only according to its
import log), and its credits settings. Hoard lists them in Projects, shows which products have updates and which
projects use each download, and makes the same credits list the Unity window makes (Credits.cs, ported here).

The reports are written by another program, so every field is checked as if it came from anywhere: text is
cleaned, stores must be known, paths must be plain, links must lead to the product's own store, and sizes are capped.
"""
from __future__ import annotations

import re
from pathlib import Path

from .downloader import STORE_DIRS
from .paths import data_dir
from .safety import DataFileError, clean_text, read_json_file, store_link, valid_rel

MAX_PROJECTS = 200
MAX_ASSETS = 5000
MAX_ADDED = 500
STATUSES = ("yes", "partly", "imported")
STYLES = ("List", "Markdown", "ByCreator")
ID = re.compile(r"^[0-9a-f]{16}$")
STORE_LABELS = {"Itch": "itch.io"}


def projects_dir() -> Path:
    return data_dir() / "projects"


def _text(v, limit: int) -> str:
    return clean_text(v, limit) if isinstance(v, str) else ""


def _link(url, store: str | None = None) -> str | None:
    """A store link the catalog would keep (the product's own store), or for an entry written in by hand (store
    None), any plain https address, as the Unity window checks it."""
    if not isinstance(url, str) or len(url) > 500:
        return None
    if store is not None:
        return store_link(store.lower(), url)
    if not url.startswith("https://") or any(c.isspace() or c in "()<>" or ord(c) < 32 for c in url) or "@" in url.split("/")[2]:
        return None
    return url


def read_project(path: Path) -> dict | None:
    """One report, checked, or None when it isn't one."""
    if not ID.match(path.stem):
        return None
    try:
        raw = read_json_file(path, 4 * 1024 * 1024)
    except (DataFileError, OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("format") != "hoard-project" or raw.get("version") != 1:
        return None
    stores = set(STORE_DIRS.values())
    assets = []
    for a in (raw.get("assets") if isinstance(raw.get("assets"), list) else [])[:MAX_ASSETS]:
        if not isinstance(a, dict) or a.get("store") not in stores or a.get("status") not in STATUSES:
            continue
        name, folder = _text(a.get("name"), 300), a.get("folder")
        if not name or not valid_rel(folder):
            continue
        assets.append({"store": a["store"], "name": name, "creator": _text(a.get("creator"), 200),
                       "folder": folder, "url": _link(a.get("url"), a["store"]), "status": a["status"]})
    c = raw.get("credits") if isinstance(raw.get("credits"), dict) else {}
    added = []
    for e in (c.get("added") if isinstance(c.get("added"), list) else [])[:MAX_ADDED]:
        if isinstance(e, dict) and _text(e.get("name"), 300):
            added.append({"store": "", "name": _text(e["name"], 300), "creator": _text(e.get("creator"), 200),
                          "url": _link(e.get("url")), "added": True})
    left_out = [k for k in (c.get("left_out") if isinstance(c.get("left_out"), list) else [])[:MAX_ASSETS]
                if isinstance(k, str) and len(k) <= 400]
    updated = raw.get("updated") if isinstance(raw.get("updated"), str) and len(raw["updated"]) <= 40 else None
    return {"id": path.stem, "name": _text(raw.get("name"), 200) or "A Unity project", "path": _text(raw.get("path"), 1000),
            "unity": _text(raw.get("unity"), 40), "updated": updated, "assets": assets,
            "credits": {"title": _text(c.get("title"), 100) if isinstance(c.get("title"), str) else "Assets used",
                        "style": c.get("style") if c.get("style") in STYLES else "List",
                        "left_out": left_out, "added": added}}


def read_all() -> list[dict]:
    """Every project's report, most recently opened first."""
    folder = projects_dir()
    try:
        files = sorted(folder.glob("*.json"))[:MAX_PROJECTS * 2]
    except OSError:
        return []
    found = [p for p in (read_project(f) for f in files) if p]
    found.sort(key=lambda p: p["updated"] or "", reverse=True)
    return found[:MAX_PROJECTS]


def forget(project_id: str) -> bool:
    """Take a project out of Projects (its report is deleted; opening the project in Unity again brings it back)."""
    if not isinstance(project_id, str) or not ID.match(project_id):
        return False
    try:
        (projects_dir() / f"{project_id}.json").unlink()
        return True
    except OSError:
        return False


# ---- the credits list, as the Unity window makes it (Credits.cs)

def _who(e: dict) -> str:
    return e["creator"] or "Unknown creator"


def _md(s: str) -> str:
    return "".join("\\" + c if c in "\\`*_{}[]()<>#+-.!|~" else c for c in s)


def credit_entries(project: dict) -> list[dict]:
    """What the list credits: the products all in the project (issue #79), and the ones written in by hand, without
    the ones left out, one per product, sorted by creator then name."""
    left = {k.casefold() for k in project["credits"]["left_out"]}
    seen, out = set(), []
    found = [a for a in project["assets"] if a["status"] == "yes"] + project["credits"]["added"]
    for e in found:
        key = f"{e['store']}/{e['name']}".casefold()
        if key in seen or key in left:
            continue
        seen.add(key)
        out.append(e)
    out.sort(key=lambda e: (_who(e).casefold(), e["name"].casefold()))
    return out


def credits_text(project: dict, style: str | None = None) -> str:
    """The list, ready to paste, in one of the Unity window's styles (its own choice unless one is given)."""
    style = style if style in STYLES else project["credits"]["style"]
    title, entries = project["credits"]["title"], credit_entries(project)
    md = style == "Markdown"
    lines = [("## " + _md(title)) if md else title] if title else []
    if not entries:
        return "\n".join(lines + (["", "_None yet._"] if md else ["None yet."])) + "\n"
    if md:
        lines.append("")
    if style == "ByCreator":
        groups: dict[str, list[str]] = {}
        for e in entries:
            groups.setdefault(_who(e), []).append(e["name"])
        lines += [f"{who}: {', '.join(names)}" for who, names in groups.items()]
        return "\n".join(lines) + "\n"
    for e in entries:
        store = STORE_LABELS.get(e["store"], e["store"])
        if md:
            name = f"[{_md(e['name'])}]({e['url']})" if e.get("url") else _md(e["name"])
            line = f"- {name} by {_md(_who(e))}" + (f" ({_md(store)})" if store else "")
        else:
            line = f"- {e['name']} by {_who(e)}" + (f" ({store})" if store else "") + (f" {e['url']}" if e.get("url") else "")
        lines.append(line)
    return "\n".join(lines) + "\n"


def view(projects: list[dict], index: dict, updates: dict) -> list[dict]:
    """Projects for the page: each product with its download (if it's on disk here) and whether it has an update,
    and the credits list in every style."""
    by_folder = {a["folder"]: a for a in index.get("assets", [])}
    out = []
    for p in projects:
        assets = []
        for a in p["assets"]:
            d = by_folder.get(a["folder"])
            assets.append({**a, "download": d["id"] if d else None,
                           "update": bool(d and d.get("tag_key") in updates)})
        out.append({**p, "assets": assets, "credits_text": {s: credits_text(p, s) for s in STYLES},
                    "counts": {s: sum(1 for a in p["assets"] if a["status"] == s) for s in STATUSES}})
    return out


def used_in(projects: list[dict]) -> dict[str, list[str]]:
    """For each download's folder, the names of the projects that use it."""
    found: dict[str, list[str]] = {}
    for p in projects:
        for a in p["assets"]:
            found.setdefault(a["folder"], []).append(p["name"])
    return found
