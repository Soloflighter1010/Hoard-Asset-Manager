"""Presets: a project to start from, kept to use again. A template, a Unity version, the VPM packages to add, and the
products from your library to put in: "my avatar base", say, with its shaders, tools and outfits.

Kept in vpm-presets.json in Hoard's own folder. A preset can be written out as an ALCOM template (.alcomtemplate,
in the Creator Companion folder's vrc-get/templates), so ALCOM makes the same project: its packages, and those of its
products that are plain .unitypackage files (ALCOM can't open one inside a .zip, so those are left out of it).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path

from ..paths import data_dir
from ..safety import DataFileError, clean_text, read_json_file, safe_join, write_file_safely
from . import templates
from .manifest import valid_name
from .version import VersionError, VersionRange

FILE = "vpm-presets.json"
MAX_PRESETS = 200
MAX_PRODUCTS = 200
MAX_PACKAGES = 200
ID = re.compile(r"[0-9a-f]{32}")
KINDS = ("unitypackage", "vpm", "vpm-folder")
_lock = threading.RLock()


class PresetError(ValueError):
    """A preset that can't be kept as it is, in words to show."""


def _path() -> Path:
    return data_dir() / FILE


def load() -> list[dict]:
    try:
        raw = read_json_file(_path(), 8 << 20)
    except (FileNotFoundError, DataFileError, OSError):
        return []
    out = []
    for p in (raw.get("presets") if isinstance(raw, dict) and isinstance(raw.get("presets"), list) else [])[:MAX_PRESETS]:
        try:
            out.append(check(p, keep_id=True))
        except PresetError:
            continue
    return out


def check(raw, keep_id: bool = False) -> dict:
    """A preset as kept: everything checked, nothing else."""
    if not isinstance(raw, dict):
        raise PresetError("That isn't a preset.")
    name = clean_text(raw.get("name"), 100)
    if not name:
        raise PresetError("Give the preset a name.")
    template = raw.get("template")
    if not isinstance(template, str) or not templates.TEMPLATE_ID.fullmatch(template):
        raise PresetError("Choose a template for the preset.")
    unity = raw.get("unity") if isinstance(raw.get("unity"), str) and len(raw["unity"]) <= 40 else None
    packages = {}
    for pkg, text in (raw.get("packages") or {}).items() if isinstance(raw.get("packages"), dict) else ():
        if not valid_name(pkg) or len(packages) >= MAX_PACKAGES:
            continue
        try:
            packages[pkg] = str(VersionRange.parse(text))
        except VersionError:
            raise PresetError(f"The version asked for {pkg} can't be read.") from None
    products = []
    for p in (raw.get("products") or [])[:MAX_PRODUCTS] if isinstance(raw.get("products"), list) else []:
        if not isinstance(p, dict) or p.get("kind") not in KINDS or not isinstance(p.get("key"), str) or len(p["key"]) > 400:
            continue
        member = p.get("member") if isinstance(p.get("member"), str) and len(p["member"]) <= 1000 else None
        products.append({"key": p["key"], "kind": p["kind"], "file": str(p.get("file") or "")[:1000], "member": member,
                         "label": clean_text(p.get("label"), 300), "product": clean_text(p.get("product"), 300)})
    pid = raw.get("id") if keep_id and isinstance(raw.get("id"), str) and ID.fullmatch(raw["id"]) else uuid.uuid4().hex
    return {"id": pid, "name": name, "template": template, "unity": unity, "packages": packages, "products": products}


def save(raw: dict) -> dict:
    """Keep a preset (a new one, or one changed: the same id)."""
    with _lock:
        keep = load()
        existing = raw.get("id") if isinstance(raw.get("id"), str) and any(p["id"] == raw.get("id") for p in keep) else None
        preset = check(raw, keep_id=bool(existing))
        keep = [p for p in keep if p["id"] != preset["id"]]
        if len(keep) >= MAX_PRESETS:
            raise PresetError(f"Hoard keeps up to {MAX_PRESETS} presets.")
        keep.append(preset)
        keep.sort(key=lambda p: p["name"].casefold())
        write_file_safely(_path(), json.dumps({"format": "hoard-presets", "version": 1, "presets": keep}, indent=1,
                                              ensure_ascii=False))
        return preset


def delete(preset_id: str) -> bool:
    with _lock:
        keep = load()
        left = [p for p in keep if p["id"] != preset_id]
        if len(left) == len(keep):
            return False
        write_file_safely(_path(), json.dumps({"format": "hoard-presets", "version": 1, "presets": left}, indent=1,
                                              ensure_ascii=False))
        return True


def export_alcom(preset: dict, assets_by_key: dict, vcc_folder: Path) -> dict:
    """Write the preset as an ALCOM template: {"path", "left_out": products ALCOM can't take}."""
    files, left_out = [], []
    for p in preset["products"]:
        a = assets_by_key.get(p["key"])
        path = safe_join(Path(a["abs_folder"]), p["file"]) if a and p["kind"] == "unitypackage" and not p.get("member") else None
        if path is None or not path.is_file():
            left_out.append(p["label"] or p["product"] or p["file"])
            continue
        files.append(str(path))
    data = templates.write_alcomtemplate(preset["name"], preset["template"],
                                         {k: VersionRange.parse(v) for k, v in preset["packages"].items()}, files,
                                         template_id=templates.USER_PREFIX + preset["id"])
    folder = vcc_folder / "vrc-get" / "templates"
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^0-9A-Za-z_-]+", "-", preset["name"]).strip("-")[:60] or "preset"
    out = folder / f"hoard-{slug}-{preset['id'][:8]}.alcomtemplate"
    write_file_safely(out, data)
    return {"path": str(out), "left_out": left_out}
