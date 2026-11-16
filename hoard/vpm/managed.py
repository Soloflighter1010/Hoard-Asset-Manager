"""Baselines for files Hoard actually imported; never adopt pre-existing project files."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from ..safety import DataFileError, read_json_file, write_file_safely

FILE = "ProjectSettings/Hoard/managed-assets.json"
HASH = re.compile(r"[0-9a-f]{64}")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_file(project: Path, relative: str) -> Path | None:
    if not isinstance(relative, str) or not relative.startswith("Assets/") or "\\" in relative:
        return None
    parts = relative.split("/")
    if any(p in ("", ".", "..") or ":" in p for p in parts):
        return None
    path = project
    for part in parts:
        path = path / part
        if path.is_symlink():
            return None
    return path


def manifest_path(project: Path) -> Path:
    path = project
    for part in FILE.split("/"):
        path = path / part
        if path.is_symlink():
            raise ValueError("The managed asset record must stay inside the project.")
    return path


def load(project: Path) -> dict:
    try:
        raw = read_json_file(manifest_path(project), 16 << 20)
    except (DataFileError, OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("files"), dict):
        return {}
    out = {}
    for guid, entry in list(raw["files"].items())[:50000]:
        if not isinstance(guid, str) or not re.fullmatch(r"[0-9a-f]{32}", guid) or not isinstance(entry, dict):
            continue
        if safe_file(project, entry.get("path")) is None:
            continue
        if not all(isinstance(entry.get(k), str) and HASH.fullmatch(entry[k]) for k in ("sha256", "meta_sha256")):
            continue
        out[guid] = {k: entry[k] for k in ("path", "sha256", "meta_sha256")}
        if isinstance(entry.get("source"), str):
            out[guid]["source"] = entry["source"][:400]
    return out


def record(project: Path, files: dict, source: str = "") -> None:
    if not files:
        return
    records = load(project)
    records.update({guid: {**entry, "source": source[:400]} for guid, entry in files.items()})
    write_file_safely(manifest_path(project), json.dumps({"version": 1, "files": records}, indent=1))


def unchanged(project: Path, entry: dict) -> bool:
    path = safe_file(project, entry.get("path"))
    if path is None:
        return False
    meta = Path(str(path) + ".meta")
    try:
        return (path.is_file() and not meta.is_symlink() and meta.is_file()
                and digest(path) == entry.get("sha256") and digest(meta) == entry.get("meta_sha256"))
    except OSError:
        return False
