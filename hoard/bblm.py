"""Bring in a BB's Library Manager library (issue #416), so someone switching from it doesn't start over.

BB's Library Manager (BBLM, https://github.com/BunBnnuy/BBLM) keeps its library in a root folder you choose, one folder
for each product:

    <root>/<id>/meta.json        its name, the page it came from, its tags, whether it's for adults...
    <root>/<id>/thumbnail.png    its picture (500 x 500)
    <root>/<id>/...              its files (a .zip, as downloaded)

meta.json is {"id", "name", "originUrl", "files": [its file names], "thumbnail": "thumbnail.png" or null,
"importedAt", "tags": [...], "isAdult", "downloadStatus" ("pending" while it's still downloading)}. A BOOTH product is
known by the item in its originUrl (/items/<number>). BBLM also keeps .blm-index.json in the root, a cache Hoard
doesn't need.

Hoard only reads that folder: nothing in it is written, moved or deleted, and BBLM needn't be running, or installed.
A product whose BOOTH item is in your library is matched to that product; the rest become Local products listed where
they are, with their pictures, and the page they came from as their store page (Local's tabs go by it). Its tags
become your tags, and one BBLM marks for adults is marked 18+. A product still downloading in BBLM is left out. What's
been brought in is remembered (bblm.json in Hoard's app-data folder), so bringing in again adds only what's new.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from . import storage
from .common import log
from .marks import MarkStore
from .paths import data_dir
from .safety import MAX_CHOSEN_PICTURE, DataFileError, clean_text
from .storage import read_document as read_json_file, write_document as write_file_safely
from .tags import TAG_LIMITS, TagStore, clean_tag, tag_key

MAX_PRODUCTS = 20000
MAX_META = 1024 * 1024
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")   # a product's folder, as BBLM names it (store.slug, 8549623...)
BOOTH_HOSTS = re.compile(r"^(?:[a-z0-9-]+\.)?booth\.pm\Z")


def remembered_file() -> Path:
    """What's been brought in: bblm.json in Hoard's app-data folder, {BBLM's id: Hoard's product key}."""
    return data_dir() / "bblm.json"


def remembered() -> dict:
    """The BBLM products brought in before, and the products they became."""
    try:
        raw = read_json_file(remembered_file(), 8 * 1024 * 1024)
    except (OSError, DataFileError):
        return {}
    done = raw.get("brought_in") if isinstance(raw, dict) else None
    return {k: v for k, v in done.items() if isinstance(k, str) and ID.match(k) and isinstance(v, str)} if isinstance(done, dict) else {}


def _remember(done: dict) -> None:
    """Keep what's been brought in (bblm.json), for next time."""
    write_file_safely(remembered_file(), json.dumps({"version": 1, "brought_in": done}, indent=1, sort_keys=True))


def _products(folder: Path) -> list[Path]:
    """The folders in BBLM's root with a meta.json in them (never through a link), at most MAX_PRODUCTS."""
    out = []
    try:
        with os.scandir(folder) as it:
            for e in it:
                if len(out) >= MAX_PRODUCTS:
                    break
                if ID.match(e.name) and e.is_dir(follow_symlinks=False):
                    meta = Path(e.path) / "meta.json"
                    if meta.is_file() and not meta.is_symlink():
                        out.append(Path(e.path))
    except OSError:
        return []
    return sorted(out, key=lambda p: p.name)


def check_folder(path: str) -> Path:
    """BBLM's root folder, as typed or picked: the one with its products' folders in it (one product's folder is taken
    to mean the one above). Raises ValueError saying what's wrong."""
    text = str(path or "").strip().strip('"')
    if not text:
        raise ValueError("Choose BB's Library Manager's root folder.")
    folder = Path(os.path.expandvars(text)).expanduser()
    if not folder.is_absolute():
        raise ValueError("Enter the full path to BB's Library Manager's root folder.")
    folder = Path(os.path.normpath(folder))
    if os.path.islink(folder) or not folder.is_dir():
        raise ValueError("There's no folder there. Check the path.")
    if (folder / "meta.json").is_file() and not _products(folder):   # one product's folder: its root is above it
        folder = folder.parent
    if not _products(folder):
        raise ValueError("That isn't BB's Library Manager's root folder: there are no products in it with a meta.json. "
                         "Its Settings say where its root folder is.")
    return folder


def booth_item(url: str) -> str | None:
    """The BOOTH item a product came from (booth.pm/<lang>/items/<number>, or a shop's own <shop>.booth.pm/items/...)."""
    try:
        u = urlparse(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not BOOTH_HOSTS.match((u.hostname or "").lower()):
        return None
    m = re.search(r"/items/(\d{1,12})(?:/|\Z)", u.path)
    return m.group(1) if m else None


def _entry(where: Path) -> dict | None:
    """One product, checked, in Hoard's terms; None when it can't be read or is still downloading."""
    try:
        raw = read_json_file(where / "meta.json", MAX_META)
    except (OSError, DataFileError):
        return None
    if not isinstance(raw, dict) or raw.get("downloadStatus") == "pending":
        return None
    name = clean_text(raw.get("name"), 300) if isinstance(raw.get("name"), str) else ""
    origin = raw.get("originUrl") if isinstance(raw.get("originUrl"), str) and len(raw["originUrl"]) <= 2000 else ""
    tags = [t for t in (clean_tag(v) for v in (raw.get("tags") if isinstance(raw.get("tags"), list) else [])[:100]
                        if isinstance(v, str)) if t]
    picture = raw.get("thumbnail") if raw.get("thumbnail") == "thumbnail.png" else None
    return {"id": where.name, "name": name or where.name, "link": origin.strip(), "booth": booth_item(origin),
            "tags": list(dict.fromkeys(tags)), "adult": raw.get("isAdult") is True, "picture": picture, "where": where}


def read(folder: Path) -> list[dict]:
    """Every product in BBLM's root folder, checked (what can't be read, or is still downloading, is left out)."""
    return [e for e in (_entry(p) for p in _products(folder)) if e]


def _has_files(product: dict) -> bool:
    """Whether a product's folder has anything in it but BBLM's own meta.json and picture."""
    try:
        with os.scandir(product["where"]) as it:
            return any(e.name not in ("meta.json", "thumbnail.png", "thumbnail_raw.tmp") for e in it)
    except OSError:
        return False


def plan(folder: Path, library_items: list[dict]) -> dict:
    """What bringing in would do, changing nothing: the products matched to products in your library (by their BOOTH
    item), those that become Local products, those left out (no files, and nothing in your library), those brought in
    before, and the tags and 18+ marks that come with them."""
    products = read(folder)
    done = remembered()
    by_booth = {str(i.get("id")): i for i in library_items if i.get("store") == "booth" and i.get("id") and i.get("name")}
    yours = set(TagStore().load()["tags"])
    out = {"total": len(products), "matched": [], "local": [], "left_out": [], "before": 0, "tags": set(), "adult": 0}
    for p in products:
        if p["id"] in done:
            out["before"] += 1
            continue
        product = by_booth.get(p["booth"]) if p["booth"] else None
        if product:
            out["matched"].append({**p, "key": tag_key("booth", product["name"], product.get("id")), "product": product["name"]})
        elif _has_files(p):
            out["local"].append({**p, "key": tag_key("local", p["name"])})
        else:
            out["left_out"].append(p)
            continue
        out["tags"].update(p["tags"])
        out["adult"] += p["adult"]
    out["new_tags"] = len(out["tags"] - yours)
    return out


def summary(p: dict) -> dict:
    """What plan() found, for the page: counts, and the names of what's left out."""
    return {"total": p["total"], "matched": len(p["matched"]), "local": len(p["local"]), "before": p["before"],
            "left_out": len(p["left_out"]), "left_out_names": [a["name"] for a in p["left_out"][:20]],
            "tags": len(p["tags"]), "new_tags": p["new_tags"], "adult": p["adult"]}


def _picture(cfg: dict, root: Path, product: dict, key: str) -> None:
    """A Local product's picture: BBLM's own thumbnail.png, kept as the one you chose (local.choose_picture), so its
    tile and Hoard for Unity show it. A picture that can't be read is skipped."""
    import base64
    from . import local
    if not product["picture"]:
        return
    path = product["where"] / product["picture"]
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CHOSEN_PICTURE:
            return
        data = path.read_bytes()
    except OSError:
        return
    try:
        local.choose_picture(cfg, root, key, base64.b64encode(data).decode())
    except (ValueError, OSError) as e:
        log(f"BBLM: {product['name']}'s picture wasn't kept ({e})")


def bring_in(cfg: dict, root: Path, folder: Path, library_items: list[dict], say=None, stop=None) -> dict:
    """Commit one import together, restoring metadata and companion files on failure."""
    with storage.import_transaction():
        return _bring_in(cfg, root, folder, library_items, say, stop)


def _bring_in(cfg: dict, root: Path, folder: Path, library_items: list[dict], say=None, stop=None) -> dict:
    """Bring in what plan() says. Returns what was done: {"matched", "local", "tags", "adult", "left_out": [names]}."""
    from . import local
    from .downloader import build_catalog
    say = say or (lambda line: None)
    p = plan(folder, library_items)
    done = remembered()
    changes, adult = [], set()
    result = {"matched": 0, "local": 0, "tags": 0, "adult": 0, "left_out": [a["name"] for a in p["left_out"]]}
    todo = [(a, False) for a in p["matched"]] + [(a, True) for a in p["local"]]
    for n, (a, is_local) in enumerate(todo, 1):
        if stop is not None and stop.is_set():
            raise InterruptedError("The import from BB's Library Manager stopped; no products or tags were changed.")
        say(f"Bringing in {n:,} of {len(todo):,} from BB's Library Manager: {a['name']}")
        key = a["key"]
        if is_local:
            try:
                rec = local.add(cfg, root, str(a["where"]), a["name"], "", "", copy=False, catalog=False)
            except (ValueError, OSError) as e:
                log(f"BBLM: {a['name']} wasn't brought in ({e})")
                result["left_out"].append(a["name"])
                continue
            _picture(cfg, root, a, rec["key"])
            if a["link"]:   # (the page it came from, when it's a product's page on a store: its tab in Local)
                try:
                    rec = local.edit(cfg, root, rec["key"], link=a["link"], build=False)
                except ValueError:
                    pass
            key = tag_key("local", rec["name"], rec.get("key"))
            result["local"] += 1
        else:
            result["matched"] += 1
        tags = a["tags"][:TAG_LIMITS["per_item"]]
        for i in range(0, len(tags), 20):
            changes.append({"action": "assign", "keys": [key], "add": tags[i:i + 20]})
        result["tags"] += len(tags)
        if a["adult"]:
            adult.add(key)
        done[a["id"]] = key
    if changes:
        TagStore().change_all(changes)
    if adult:
        MarkStore().change("adult", adult, True)
        result["adult"] = len(adult)
    _remember(done)
    if result["local"]:
        build_catalog(cfg, root)
    log(f"BBLM: brought in {result['matched']} matched and {result['local']} Local products from {folder}")
    return result
