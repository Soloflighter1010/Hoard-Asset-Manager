"""Bring in a KonoAsset library (issue #305), so someone switching from KonoAsset doesn't start over.

KonoAsset (https://github.com/siloneco/KonoAsset, MIT) keeps everything in its data folder (its Settings say where):

- metadata/avatars.json, avatarWearables.json, worldObjects.json and otherAssets.json: {"version": 3, "data": [...]}.
  Version 2 is the same without an asset's dependencies; version 1 is a bare list, without memos, with a picture's
  path instead of its file name.
- data/<asset id>/: each asset's files.
- images/: their pictures.

An asset is {"id", "description": {"name", "creator", "imageFilename", "tags", "memo", "boothItemId", "dependencies",
"createdAt", "publishedAt"}}; a wearable has a "category" and the "supportedAvatars" it fits, and a world object or
another asset a "category".

Hoard only reads that folder: nothing in it is written, moved or deleted, and KonoAsset needn't be running, or
installed. An asset whose BOOTH item is in your library is matched to that product; the rest become Local products
listed where they are (their files left in KonoAsset's data/<id>/, as Local's "left where it is"), with their
pictures. Its tags, its category and the avatars a wearable fits become your tags; its memo becomes the product's note
(issue #304), with what it needs listed after it. A note you've written already is never replaced. What's been
brought in is remembered (konoasset.json in Hoard's app-data folder), so bringing in again adds only what's new.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .common import log
from .paths import data_dir
from .safety import MAX_CHOSEN_PICTURE, DataFileError, clean_text, read_json_file, write_file_safely
from .tags import TAG_LIMITS, TagStore, clean_note, clean_tag, tag_key

FILES = (("avatars.json", "avatar"), ("avatarWearables.json", "wearable"), ("worldObjects.json", "world"),
         ("otherAssets.json", "other"))
TYPES = {"avatar": "avatar", "world": "world"}   # what Hoard calls a product of KonoAsset's kind (issue #223), when it's sure
MAX_ASSETS = 20000
MAX_FILE = 64 * 1024 * 1024
ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
PICTURE = re.compile(r"^[^/\\:*?\"<>|\x00-\x1f]{1,200}\.(png|jpe?g|webp)\Z", re.I)


def remembered_file() -> Path:
    """What's been brought in: konoasset.json in Hoard's app-data folder, {KonoAsset's id: Hoard's product key}."""
    return data_dir() / "konoasset.json"


def remembered() -> dict:
    """The KonoAsset assets brought in before, and the products they became."""
    try:
        raw = read_json_file(remembered_file(), 8 * 1024 * 1024)
    except (OSError, DataFileError):
        return {}
    done = raw.get("brought_in") if isinstance(raw, dict) else None
    return {k.lower(): v for k, v in done.items() if isinstance(k, str) and ID.match(k) and isinstance(v, str)} if isinstance(done, dict) else {}


def _remember(done: dict) -> None:
    """Keep what's been brought in (konoasset.json), for next time."""
    write_file_safely(remembered_file(), json.dumps({"version": 1, "brought_in": done}, indent=1, sort_keys=True))


def check_folder(path: str) -> Path:
    """KonoAsset's data folder, as typed or picked: the one with metadata/ in it (its metadata folder is taken to mean
    the one above). Raises ValueError saying what's wrong."""
    text = str(path or "").strip().strip('"')
    if not text:
        raise ValueError("Choose KonoAsset's data folder.")
    folder = Path(os.path.expandvars(text)).expanduser()
    if not folder.is_absolute():
        raise ValueError("Enter the full path to KonoAsset's data folder.")
    folder = Path(os.path.normpath(folder))
    if folder.name.lower() == "metadata" and not (folder / "metadata").is_dir():
        folder = folder.parent
    if os.path.islink(folder) or not folder.is_dir():
        raise ValueError("There's no folder there. Check the path.")
    meta = folder / "metadata"
    if not meta.is_dir() or meta.is_symlink() or not any((meta / name).is_file() for name, _kind in FILES):
        raise ValueError("That isn't KonoAsset's data folder: it has no metadata folder with KonoAsset's lists in it. "
                         "KonoAsset's Settings say where its data folder is.")
    return folder


def _entry(raw, kind: str) -> dict | None:
    """One asset, checked, in Hoard's terms; None when it can't be read."""
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not ID.match(raw["id"]):
        return None
    d = raw.get("description")
    if not isinstance(d, dict):
        return None
    name = clean_text(d.get("name"), 300) if isinstance(d.get("name"), str) else ""
    if not name:
        return None
    booth = d.get("boothItemId")
    booth = str(booth) if isinstance(booth, int) and not isinstance(booth, bool) and 0 < booth < 10 ** 12 else None
    picture = d.get("imageFilename") if isinstance(d.get("imageFilename"), str) else None
    if not picture and isinstance(d.get("imagePath"), str):   # version 1: the picture's whole path
        picture = re.split(r"[/\\]", d["imagePath"])[-1]
    tags = [t for t in (clean_tag(v) for v in (d.get("tags") if isinstance(d.get("tags"), list) else [])[:100]) if t]
    category = clean_tag(raw.get("category")) if isinstance(raw.get("category"), str) else ""
    avatars = [t for t in (clean_tag(v) for v in (raw.get("supportedAvatars") if isinstance(raw.get("supportedAvatars"), list) else [])[:100]) if t]
    needs = [v.lower() for v in (d.get("dependencies") if isinstance(d.get("dependencies"), list) else [])[:100]
             if isinstance(v, str) and ID.match(v)]
    return {"id": raw["id"].lower(), "kind": kind, "name": name,
            "creator": clean_text(d.get("creator"), 200) if isinstance(d.get("creator"), str) else "",
            "tags": list(dict.fromkeys([*tags, *([category] if category else []), *avatars])),
            "memo": clean_note(d.get("memo")) if isinstance(d.get("memo"), str) else "",
            "booth": booth, "needs": needs,
            "picture": picture if picture and PICTURE.match(picture) else None}


def read(folder: Path) -> list[dict]:
    """Every asset in KonoAsset's lists, in any of its versions, checked (what can't be read is left out)."""
    out, seen = [], set()
    for name, kind in FILES:
        path = folder / "metadata" / name
        if not path.is_file() or path.is_symlink():
            continue
        try:
            raw = read_json_file(path, MAX_FILE)
        except (OSError, DataFileError) as e:
            raise ValueError(f"KonoAsset's {name} can't be read ({e}).") from None
        if isinstance(raw, dict) and raw.get("version") in (2, 3) and isinstance(raw.get("data"), list):
            items = raw["data"]
        elif isinstance(raw, list):   # version 1
            items = raw
        else:
            raise ValueError(f"KonoAsset's {name} is in a shape Hoard doesn't know. Is KonoAsset newer than this Hoard?")
        for item in items:
            e = _entry(item, kind)
            if e and e["id"] not in seen:
                seen.add(e["id"])
                out.append(e)
            if len(out) >= MAX_ASSETS:
                return out
    return out


def _files_of(folder: Path, asset: dict) -> Path | None:
    """The folder with an asset's files, when it's there and has something in it (never through a link)."""
    where = folder / "data" / asset["id"]
    try:
        if where.is_symlink() or not where.is_dir():
            return None
        with os.scandir(where) as it:
            return where if any(True for _e in it) else None
    except OSError:
        return None


def _note(asset: dict, names: dict, booth_link: bool) -> str:
    """The note an asset brings: its memo, then what it needs (KonoAsset's dependencies, by name), then (for one that
    becomes a Local product) its BOOTH page."""
    parts = [asset["memo"]] if asset["memo"] else []
    needs = [names[i] for i in asset["needs"] if i in names]
    if needs:
        parts.append("Needs: " + ", ".join(needs))
    if booth_link and asset["booth"]:
        parts.append(f"BOOTH: https://booth.pm/ja/items/{asset['booth']}")
    return clean_note("\n\n".join(parts))


def plan(folder: Path, library_items: list[dict]) -> dict:
    """What bringing in would do, changing nothing: the assets matched to products in your library (by their BOOTH
    item), those that become Local products, those left out (no files, and nothing in your library), those brought in
    before, and the tags and notes that come with them."""
    assets = read(folder)
    done = remembered()
    by_booth = {str(i.get("id")): i for i in library_items if i.get("store") == "booth" and i.get("id") and i.get("name")}
    names = {a["id"]: a["name"] for a in assets}
    yours = set(TagStore().load()["tags"])
    out = {"total": len(assets), "matched": [], "local": [], "left_out": [], "before": 0, "tags": set(), "notes": 0}
    for a in assets:
        if a["id"] in done:
            out["before"] += 1
            continue
        product = by_booth.get(a["booth"]) if a["booth"] else None
        if product:
            out["matched"].append({**a, "key": tag_key("booth", product["name"]), "product": product["name"]})
        elif _files_of(folder, a):
            out["local"].append({**a, "key": tag_key("local", a["name"])})
        else:
            out["left_out"].append(a)
            continue
        out["tags"].update(a["tags"])
        out["notes"] += bool(_note(a, names, not product))
    out["new_tags"] = len(out["tags"] - yours)
    out["names"] = names
    return out


def summary(p: dict) -> dict:
    """What plan() found, for the page: counts, and the names of what's left out."""
    return {"total": p["total"], "matched": len(p["matched"]), "local": len(p["local"]), "before": p["before"],
            "left_out": len(p["left_out"]), "left_out_names": [a["name"] for a in p["left_out"][:20]],
            "tags": len(p["tags"]), "new_tags": p["new_tags"], "notes": p["notes"]}


def _picture(cfg: dict, root: Path, folder: Path, asset: dict, key: str) -> None:
    """A Local product's picture: KonoAsset's own, kept as the one you chose (local.choose_picture), so its tile and
    Hoard for Unity show it. A picture that can't be read is skipped."""
    import base64
    from . import local
    if not asset["picture"]:
        return
    path = folder / "images" / asset["picture"]
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CHOSEN_PICTURE:
            return
        data = path.read_bytes()
    except OSError:
        return
    try:
        local.choose_picture(cfg, root, key, base64.b64encode(data).decode())
    except (ValueError, OSError) as e:   # (a WebP, which Hoard for Unity can't show, or one too large: its own is kept)
        log(f"KonoAsset: {asset['name']}'s picture wasn't kept ({e})")


def bring_in(cfg: dict, root: Path, folder: Path, library_items: list[dict], say=None, stop=None) -> dict:
    """Bring in what plan() says. Returns what was done: {"matched", "local", "tags", "notes", "left_out": [names]}."""
    from . import local
    from .downloader import build_catalog
    say = say or (lambda line: None)
    p = plan(folder, library_items)
    done = remembered()
    store = TagStore()
    have = store.load()
    changes, result = [], {"matched": 0, "local": 0, "tags": 0, "notes": 0, "left_out": [a["name"] for a in p["left_out"]]}
    todo = [(a, False) for a in p["matched"]] + [(a, True) for a in p["local"]]
    for n, (a, is_local) in enumerate(todo, 1):
        if stop is not None and stop.is_set():
            break
        say(f"Bringing in {n:,} of {len(todo):,} from KonoAsset: {a['name']}")
        key = a["key"]
        if is_local:
            try:
                rec = local.add(cfg, root, str(_files_of(folder, a) or ""), a["name"], a["creator"], "", copy=False,
                                catalog=False)
            except (ValueError, OSError) as e:
                log(f"KonoAsset: {a['name']} wasn't brought in ({e})")
                result["left_out"].append(a["name"])
                continue
            _picture(cfg, root, folder, a, rec["key"])
            key = tag_key("local", rec["name"])
            result["local"] += 1
        else:
            result["matched"] += 1
        tags = a["tags"][:TAG_LIMITS["per_item"]]
        for i in range(0, len(tags), 20):
            changes.append({"action": "assign", "keys": [key], "add": tags[i:i + 20]})
        result["tags"] += len(tags)
        note = _note(a, p["names"], is_local)
        if note and not have["notes"].get(key):   # (a note you've written stays)
            changes.append({"action": "note", "keys": [key], "note": note})
            result["notes"] += 1
        if TYPES.get(a["kind"]) and key not in have["types"]:
            changes.append({"action": "set-type", "keys": [key], "type": TYPES[a["kind"]]})
        done[a["id"]] = key
    if changes:
        store.change_all(changes)
    _remember(done)
    if result["local"]:
        build_catalog(cfg, root)
    log(f"KonoAsset: brought in {result['matched']} matched and {result['local']} Local products from {folder}")
    return result
