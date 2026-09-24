"""The downloads view: what's on disk, with files, sizes, images and matches across stores."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from .paths import HERE
from .safety import DataFileError, read_json_file, safe_join, store_link
from .tags import TagStore, tag_key, tag_overview


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


PREVIEW_HINT = re.compile(r"preview|thumb|cover|icon|promo|banner", re.I)


VERSION_RX = re.compile(r"\bv?\d+(?:\.\d+)*\b", re.I)


# ----------------------------------------------------------------------------- index

def _norm(s: str) -> str:
    """A name reduced to letters and digits, without version numbers, for matching across stores."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\W_]+", "", VERSION_RX.sub(" ", s))


def _same_creator(a: str, b: str) -> bool:
    """True when two creator names are probably the same creator (or one is unknown)."""
    na, nb = _norm(a), _norm(b)
    if "unknowncreator" in (na, nb):
        return True
    return bool(na and nb and (na == nb or na in nb or nb in na))


def _thumbnail(folder: Path, files: list[str]) -> str | None:
    """_thumbnail.* saved by the downloader, else a preview-looking image, else any image."""
    try:
        for p in sorted(folder.glob("_thumbnail.*")):
            if p.suffix.lower() in IMAGE_EXT:
                return p.name
    except OSError:
        pass
    images = [f for f in files if Path(f).suffix.lower() in IMAGE_EXT]
    for f in images:
        if PREVIEW_HINT.search(Path(f).stem):
            return f
    return images[0] if images else None


STORES = ("Booth", "Gumroad", "Jinxxy", "Payhip")


def library_status(root: Path) -> dict:
    """What's actually under root, plus other places downloads might be, for troubleshooting."""
    stores = {}
    for store in STORES:
        m = root / store / "_manifest.json"
        count = 0
        if m.exists():
            try:
                data = read_json_file(m, 64 * 1024 * 1024)   # the same size-limited reader as everywhere else
                assets = data.get("assets") if isinstance(data, dict) else None
                count = sum(1 for a in assets.values() if isinstance(a, dict) and isinstance(a.get("files"), dict)
                            and a["files"]) if isinstance(assets, dict) else -1
            except (DataFileError, ValueError, OSError, RecursionError):
                count = -1
        stores[store] = {"manifest": str(m), "found": m.exists(), "assets": count}
    def subdirs(d: Path) -> list[Path]:
        try:
            return [p for p in d.iterdir() if p.is_dir()][:200]
        except OSError:
            return []

    # the default folder, the parent, siblings, and subfolders of root
    candidates = [HERE / "downloads", root.parent, *subdirs(root.parent), *subdirs(root)]
    elsewhere = []
    for c in candidates:
        try:
            if c.resolve() != root.resolve() and any((c / s / "_manifest.json").exists() for s in STORES):
                elsewhere.append(str(c))
        except OSError:
            pass
    return {"root_exists": root.is_dir(), "stores": stores, "elsewhere": elsewhere}


def build_index(root: Path, catalog: list[dict]) -> dict:

    """The data behind the page: every downloaded asset with its files, sizes, image and matches."""
    assets = []
    for i, e in enumerate(catalog):
        folder = safe_join(root, e["folder"])
        if folder is None:  # a folder that would lead outside the downloads isn't shown
            continue
        files, total, missing, newest = [], 0, 0, 0.0
        for rel in e.get("files", []):
            try:
                target = safe_join(folder, rel)
                if target is None:
                    continue
                st = target.stat()
                total += st.st_size
                newest = max(newest, st.st_mtime)
                files.append({"path": rel, "size": st.st_size})
            except OSError:
                missing += 1
                files.append({"path": rel, "size": None, "missing": True})
        thumb = _thumbnail(folder, e.get("files", []))
        assets.append({
            "id": i,
            "store": e["store"],
            "name": e["name"],
            "creator": e["creator"],
            "variants": e.get("variants"),
            "url": store_link(e["store"], e.get("url")),
            "folder": e["folder"],
            "abs_folder": str(folder),
            "tag_key": tag_key(e["store"], e["name"]),
            "tags": [],
            "suggested": e.get("suggested_tags", []),
            "types": sorted({Path(f).suffix.lower().lstrip(".") for f in e.get("files", []) if Path(f).suffix}),
            "files": files,
            "size": total,
            "missing": missing,
            "added": e.get("added"),
            "modified": newest or None,
            "thumb": f"{e['folder']}/{thumb}" if thumb else None,
            "also_in": [],
        })

    # The same product bought on both stores: flag it, never merge it.
    by_name: dict[str, list] = {}
    for a in assets:
        by_name.setdefault(_norm(a["name"]), []).append(a)
    for group in by_name.values():
        if len({a["store"] for a in group}) < 2:
            continue
        for a in group:
            a["also_in"] = [{"id": b["id"], "store": b["store"]} for b in group
                            if b["store"] != a["store"] and _same_creator(a["creator"], b["creator"])]

    return {"root": str(root), "assets": assets, "status": library_status(root)}


def with_tags(index: dict) -> dict:
    """The index with your current tags on every asset, read fresh so a change shows straight away."""
    data = TagStore().load()
    by_id = {a["id"]: a for a in index["assets"]}
    assets = []
    for a in index["assets"]:
        mine = TagStore.tags_for(data, a["tag_key"], a["name"])
        assets.append({**a, "tags": mine,
                       "suggested": [t for t in a["suggested"]
                                     if t not in mine and t not in data["tags"] and t not in data["hidden"]],
                       "copy_keys": [by_id[o["id"]]["tag_key"] for o in a["also_in"] if o["id"] in by_id]})
    return {**index, "assets": assets, "tagset": tag_overview(data, assets)}


def reveal(p: Path) -> str:
    """Show a folder, or a file within its folder, in Explorer, Finder or the file manager."""
    if sys.platform == "win32":
        if p.is_dir():
            os.startfile(str(p))  # noqa: S606 - opens a folder inside the download root
        else:
            subprocess.Popen(f'explorer /select,"{p}"')
        return "Explorer"
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(p)] if p.is_file() else ["open", str(p)])
        return "Finder"
    subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])
    return "your file manager"


def print_status(root: Path, count: int, config_path: Path | None) -> None:
    """Print which folder is being browsed and what's in it, with hints when nothing is found."""
    st = library_status(root)
    print(f"Library folder: {root}" + ("" if st["root_exists"] else "   <- this folder doesn't exist"))
    for store, info in st["stores"].items():
        state = (f"{info['assets']} assets" if info["assets"] >= 0 else "manifest unreadable") if info["found"] \
            else "no downloads here"
        print(f"  {store:<8} {state}")
    if count == 0:
        where = f"`root` in {config_path}" if config_path and Path(config_path).exists() \
            else f"no config.json was found{f' at {config_path}' if config_path else ''}, so the default folder is used"
        print(f"\nNo downloaded assets found. Check the library folder above ({where}).")
        for other in st["elsewhere"]:
            print(f"  Downloads exist in: {other}  - set \"root\" to this folder in config.json")
