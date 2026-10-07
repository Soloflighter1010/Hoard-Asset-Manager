"""What a check for updates found (issue #26): for each product already downloaded, the files its store has now
that aren't on disk: new ones, and ones the creator changed.

A check is a dry run of the downloader (nothing is downloaded or written to the downloads folder); what it finds is
kept in asset-updates.json in Hoard's app data, so the Downloads page can show it until the product is updated or
checked again. Updating a product is an ordinary download of just that product.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .common import now_iso
from .library import DOWNLOADABLE
from .paths import data_dir
from .safety import DataFileError, clean_text, read_json_file, write_file_safely

MAX_PRODUCTS = 20000
MAX_FILES = 200
_lock = threading.Lock()


def updates_file() -> Path:
    return data_dir() / "asset-updates.json"


class AssetUpdates:
    """asset-updates.json: {"checked": {store: when}, "items": {tag_key: {store, name, creator, files: [{file, kind}]}}}"""

    def __init__(self, path: Path | None = None):
        self.path = path or updates_file()

    @staticmethod
    def empty() -> dict:
        return {"checked": {}, "items": {}}

    def load(self) -> dict:
        """What was found, cleaned; empty when there's no file or it can't be read (it's only ever a hint)."""
        try:
            raw = read_json_file(self.path, 32 * 1024 * 1024) if self.path.exists() else {}
        except (DataFileError, OSError, ValueError, RecursionError):
            raw = {}
        return self.sanitize(raw)

    @staticmethod
    def sanitize(raw) -> dict:
        out = AssetUpdates.empty()
        if not isinstance(raw, dict):
            return out
        checked = raw.get("checked") if isinstance(raw.get("checked"), dict) else {}
        out["checked"] = {s: clean_text(v, 40) for s, v in checked.items() if s in DOWNLOADABLE and isinstance(v, str)}
        items = raw.get("items") if isinstance(raw.get("items"), dict) else {}
        for key, e in list(items.items())[:MAX_PRODUCTS]:
            if not (isinstance(key, str) and 0 < len(key) <= 400 and isinstance(e, dict) and e.get("store") in DOWNLOADABLE):
                continue
            files = [{"file": clean_text(f.get("file"), 300) or "a file", "kind": "changed" if f.get("kind") == "changed" else "new"}
                     for f in (e.get("files") if isinstance(e.get("files"), list) else [])[:MAX_FILES] if isinstance(f, dict)]
            if files:
                out["items"][key] = {"store": e["store"], "name": clean_text(e.get("name"), 300) or "",
                                     "creator": clean_text(e.get("creator"), 200) or "", "files": files}
        return out

    def save(self, data: dict) -> None:
        write_file_safely(self.path, json.dumps(self.sanitize(data), indent=1, ensure_ascii=False))

    def record_check(self, stores: list[str], keys: set | None, available: list[dict]) -> int:
        """Keep what a check found for these stores (and only these products, when keys are given), replacing what
        an earlier check found for them. Returns how many products have updates, in all."""
        with _lock:
            data = self.load()
            for key in [k for k, e in data["items"].items() if e["store"] in stores and (not keys or k in keys)]:
                del data["items"][key]
            for a in available:
                if a["store"] not in stores or (keys and a["key"] not in keys):
                    continue
                e = data["items"].setdefault(a["key"], {"store": a["store"], "name": a["name"], "creator": a["creator"],
                                                         "files": []})
                if not any(f["file"] == a["file"] for f in e["files"]):
                    e["files"].append({"file": a["file"], "kind": a["kind"]})
            if not keys:
                data["checked"].update({s: now_iso() for s in stores})
            self.save(data)
            return len(data["items"])

    def after_download(self, got: set, failed: list[str], got_files: set | None = None) -> None:
        """Take what came off the list. With got_files ((tag_key, file) saved), each update's files that came are
        taken off it, and the update once none are left: a file left out when choosing, or not reached because the
        run stopped, stays an update. Without it (older callers), a product with files saved and none failing is."""
        with _lock:
            data = self.load()
            changed = False
            for k, e in list(data["items"].items()):
                if k not in got:
                    continue
                left = [f for f in e["files"] if (k, f["file"]) not in got_files] if got_files is not None else e["files"]
                if len(left) == len(e["files"]):
                    # none of its listed files matched what came (a store naming a file differently between
                    # checking and saving): taken off, as before, when nothing of it failed
                    if not any(f"{e['name']} /" in line or f"/ {e['name']} " in line for line in failed):
                        del data["items"][k]
                        changed = True
                    continue
                if len(left) != len(e["files"]):
                    changed = True
                    if left:
                        e["files"] = left
                    else:
                        del data["items"][k]
            if changed:
                self.save(data)
