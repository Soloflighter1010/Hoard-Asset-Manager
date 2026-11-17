"""Forget linked Local assets from Hoard's records while its desktop app is closed."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hoard.app import InstanceLock
from hoard.config import root_dir
from hoard.paths import data_dir, store_python
from hoard.safety import _canonical, _is_link, write_file_safely


def local_path(path: Path) -> Path:
    """Reject network drives and filesystem redirects before opening metadata."""
    path = path.absolute()
    if os.name == "nt":
        from ctypes import windll
        if path.drive.startswith(("\\", "/")) or windll.kernel32.GetDriveTypeW(path.anchor) not in (2, 3, 6):
            raise ValueError(f"Choose a local metadata folder instead of {path.anchor}")
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            break
        if _is_link(info):
            raise ValueError(f"Metadata path uses a filesystem link: {part}")
    return path


def read_record(path: Path, *, desktop=False):
    """Read a bounded metadata file and keep its exact bytes for the backup."""
    path = local_path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None, None
    if not stat.S_ISREG(info.st_mode) or info.st_size > 256 << 20:
        raise ValueError(f"Expected a regular Hoard metadata file: {path}")
    original = desktop_bytes(path) if desktop else path.read_bytes()
    value = json.loads(original)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return original, value


def desktop_bytes(path: Path) -> bytes:
    """Read the actual desktop profile when Store Python redirects AppData."""
    if not store_python():
        return path.read_bytes()
    command = "[Convert]::ToBase64String([IO.File]::ReadAllBytes($env:HOARD_RESCUE_READ_PATH))"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            env={**os.environ, "HOARD_RESCUE_READ_PATH": str(path)}, capture_output=True,
                            check=True, timeout=10)
    return base64.b64decode(result.stdout.strip(), validate=True)


def signed_record(value, key):
    """Use the desktop profile's key and Hoard's existing JSON seal format."""
    body = {name: item for name, item in value.items() if name != "integrity"}
    return {**body, "integrity": {"alg": "HMAC-SHA256",
                                 "key_id": hashlib.sha256(key).hexdigest()[:16],
                                 "mac": hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()}}


def plan(root: Path):
    """Remove linked records by their saved fields, treating source paths as text."""
    changes = {}
    manifest = root / "Local" / "_manifest.json"
    original, raw = read_record(manifest)
    removed = 0
    if raw is not None:
        assets = raw.get("assets")
        if not isinstance(assets, dict):
            raise ValueError(f"Invalid Local asset records in {manifest}")
        kept = {key: entry for key, entry in assets.items()
                if not (isinstance(entry, dict) and entry.get("location"))}
        removed = len(assets) - len(kept)
        if removed:
            changes[manifest] = original, {**raw, "assets": kept}

    catalog = root / "catalog.json"
    original, raw = read_record(catalog)
    if raw is not None:
        assets = raw.get("assets")
        if not isinstance(assets, list) or any(not isinstance(entry, dict) for entry in assets):
            raise ValueError(f"Invalid catalog asset records in {catalog}")
        kept = [entry for entry in assets if not (entry.get("store") == "Local" and entry.get("location"))]
        if len(kept) != len(assets):
            folders = {entry.get("folder") for entry in kept}
            raw["assets"] = kept
            if isinstance(raw.get("sets"), list):
                for group in raw["sets"]:
                    group["items"] = [folder for folder in group["items"] if folder in folders]
                raw["sets"] = [group for group in raw["sets"] if group["items"]]
            changes[catalog] = original, raw
    return removed, changes


def rescue(roots, apply=False):
    """Back up all affected records before atomically replacing individual files."""
    removed, changes = 0, {}
    for root in dict.fromkeys(local_path(root) for root in roots):
        count, edits = plan(root)
        removed += count
        changes.update(edits)
    print(f"{removed} linked Local entries in manifests, {len(changes)} metadata files to update.")
    if not apply or not changes:
        return
    replacements = {}
    key = None
    for path, (original, updated) in changes.items():
        info = updated.get("integrity")
        if info is not None:
            # Re-seal only data already authenticated by this Hoard installation.
            if key is None:
                key = bytes.fromhex(desktop_bytes(local_path(data_dir() / "integrity.key")).decode("ascii").strip())
            expected = signed_record(json.loads(original), key)["integrity"]
            if len(key) != 32 or not isinstance(info, dict) or info.get("key_id") != expected["key_id"] or not hmac.compare_digest(str(info.get("mac")), expected["mac"]):
                raise ValueError(f"Cannot authenticate {path}. Use the original Hoard profile and integrity key.")
            updated = signed_record(updated, key)
        replacements[path] = json.dumps(updated, ensure_ascii=False, indent=2)
    for path, (original, _) in changes.items():
        if path.read_bytes() != original:
            raise ValueError(f"{path} changed during inspection. Close Hoard and retry.")
    for path, (original, _) in changes.items():
        with tempfile.NamedTemporaryFile(mode="wb", prefix=path.name + ".before-rescue-",
                                         dir=path.parent, delete=False) as backup:
            backup.write(original)
            backup.flush()
            os.fsync(backup.fileno())
            print(f"Backup: {backup.name}")
    for path, payload in replacements.items():
        write_file_safely(path, payload, root=path.parent)
    print("Rescue complete. Start Hoard again.")


def main():
    """Preview by default and acquire Hoard's instance lock before applying."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", help="Local Hoard downloads folder. Repeat for other folders.")
    parser.add_argument("--apply", action="store_true", help="Back up and remove the linked records shown by preview.")
    args = parser.parse_args()
    try:
        roots = args.root
        if roots is None:
            _, cfg = read_record(data_dir() / "config.json", desktop=True)
            if cfg is None:
                raise ValueError("Hoard settings were not found. Pass --root with your downloads folder.")
            roots = [root_dir(cfg)]
            extras = cfg.get("library_folders")
            if isinstance(extras, list):
                roots.extend(Path(value) for value in extras if isinstance(value, str) and value)
        if not args.apply:
            rescue(roots)
            return 0
        lock = InstanceLock(local_path(data_dir() / "running.lock"))
        if not lock.acquire():
            raise ValueError("Quit Hoard completely before applying the rescue, including the tray icon.")
        try:
            rescue(roots, apply=True)
        finally:
            lock.release()
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        print(f"Rescue stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
