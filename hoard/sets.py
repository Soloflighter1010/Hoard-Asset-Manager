"""Sets (Downloads, and Hoard for Unity's Import set): products you group to use together, such as an avatar, its
outfits and hair, and the shaders they need.

Kept in sets.json in Hoard's app-data folder: {"sets": [{"id", "name", "items": [product key, ...]}]}, a product
known by the same key your tags use (tags.tag_key), so a set keeps its products whichever store or library folder
they're in. catalog.json lists each set by its products' folders, for Hoard for Unity. Every change re-reads the file
under a lock.
"""
from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path

from .paths import data_dir
from .safety import DataFileError, clean_text, read_json_file, write_file_safely
from .tags import TAG_KEY_RX

MAX_SETS = 200
MAX_ITEMS = 500
NAME_LENGTH = 60

_lock = threading.Lock()


def sets_file() -> Path:
    return data_dir() / "sets.json"


def clean_name(value) -> str:
    return clean_text(value, NAME_LENGTH) if isinstance(value, str) else ""


class SetStore:
    def __init__(self, path: Path | None = None):
        self.path = path or sets_file()

    @staticmethod
    def sanitize(raw) -> dict:
        out = {"sets": []}
        seen = set()
        for s in (raw.get("sets") if isinstance(raw, dict) and isinstance(raw.get("sets"), list) else [])[:MAX_SETS]:
            if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not s["id"].isalnum() or len(s["id"]) > 16:
                continue
            name = clean_name(s.get("name"))
            if not name or s["id"] in seen:
                continue
            seen.add(s["id"])
            items = []
            for k in s.get("items") if isinstance(s.get("items"), list) else []:
                if isinstance(k, str) and TAG_KEY_RX.match(k) and k not in items:
                    items.append(k)
            out["sets"].append({"id": s["id"], "name": name, "items": items[:MAX_ITEMS]})
        return out

    def load(self) -> dict:
        try:
            raw = read_json_file(self.path) if self.path.is_file() else {}
        except (DataFileError, OSError):
            raw = {}
        return self.sanitize(raw)

    def _save(self, data: dict) -> None:
        write_file_safely(self.path, json.dumps({"version": 1, **data}, ensure_ascii=False, indent=1))

    def change(self, body: dict) -> dict:
        """One change, from the page: {"action": "create", "name", "items"?}, {"action": "rename", "id", "name"},
        {"action": "delete", "id"}, {"action": "add" or "remove", "id", "items"}. Returns the sets after it, and the
        new set's id for "create". Raises ValueError for one that can't be made."""
        action = body.get("action")
        with _lock:
            data = self.load()
            sets = data["sets"]
            items = [k for k in body.get("items", []) if isinstance(k, str) and TAG_KEY_RX.match(k)] \
                if isinstance(body.get("items"), list) else []
            made = None
            if action == "create":
                name = clean_name(body.get("name"))
                if not name:
                    raise ValueError("Give the set a name.")
                if len(sets) >= MAX_SETS:
                    raise ValueError(f"Hoard keeps up to {MAX_SETS} sets.")
                made = secrets.token_hex(4)
                sets.append({"id": made, "name": name, "items": list(dict.fromkeys(items))[:MAX_ITEMS]})
            else:
                s = next((s for s in sets if s["id"] == body.get("id")), None)
                if s is None:
                    raise ValueError("That set isn't there anymore.")
                if action == "rename":
                    name = clean_name(body.get("name"))
                    if not name:
                        raise ValueError("Give the set a name.")
                    s["name"] = name
                elif action == "delete":
                    sets.remove(s)
                elif action == "add":
                    s["items"] = list(dict.fromkeys(s["items"] + items))
                    if len(s["items"]) > MAX_ITEMS:
                        raise ValueError(f"A set holds up to {MAX_ITEMS} products.")
                elif action == "remove":
                    s["items"] = [k for k in s["items"] if k not in items]
                else:
                    raise ValueError("Unknown change.")
            self._save(data)
        return {**data, **({"made": made} if made else {})}


def for_catalog(catalog: list[dict], data: dict | None = None) -> list[dict]:
    """The sets as catalog.json lists them: [{"name", "items": [folder, ...]}], each product by its catalog folder
    (every copy of it, on every store), only products the catalog has, and only sets with any."""
    from .tags import tag_key
    data = data if data is not None else SetStore().load()
    folders: dict[str, list[str]] = {}
    for e in catalog:
        folders.setdefault(tag_key(e["store"], e["name"]), []).append(e["folder"])
    out = []
    for s in data["sets"]:
        items = [f for k in s["items"] for f in folders.get(k, [])]
        if items:
            out.append({"name": s["name"], "items": items})
    return out
