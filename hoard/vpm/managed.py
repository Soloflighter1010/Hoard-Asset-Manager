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
    resolved, root = path.resolve(), project.resolve()
    return path if root in resolved.parents else None


def manifest_path(project: Path) -> Path:
    path = project
    for part in FILE.split("/"):
        path = path / part
        if path.is_symlink():
            raise ValueError("The managed asset record must stay inside the project.")
    if project.resolve() not in path.resolve().parents:
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


def _workspace(project: Path) -> Path:
    path = project
    for part in ("Library", ".hoard-managed-update"):
        path = path / part
        if path.is_symlink():
            raise ValueError("The update workspace must stay inside the project.")
    if project.resolve() not in path.resolve().parents:
        raise ValueError("The update workspace must stay inside the project.")
    return path


def recover(project: Path) -> bool:
    """Roll back an interrupted update, refusing to overwrite edits made after interruption."""
    import shutil
    root = _workspace(project)
    journal = root / "journal.json"
    if not journal.exists():
        return False
    if journal.is_symlink():
        raise ValueError("The update journal cannot be a link.")
    raw = read_json_file(journal, 32 << 20)
    if raw.get("phase") == "committed":
        shutil.rmtree(root)
        return True
    before, after, paths = raw["before"], raw["after"], raw["paths"]
    checked = []
    for guid, rel in paths.items():
        if not re.fullmatch(r"[0-9a-f]{32}", guid):
            raise ValueError("Invalid managed update journal.")
        path = safe_file(project, rel)
        if path is None:
            raise ValueError("An update path changed; recovery needs attention.")
        for suffix, field in (("", "sha256"), (".meta", "meta_sha256")):
            target = Path(str(path) + suffix)
            backup = root / (guid + (".asset" if not suffix else ".meta"))
            if backup.is_symlink() or digest(backup) != before[guid][field]:
                raise ValueError("An update backup changed; recovery needs attention.")
            if target.is_symlink() or not target.is_file() or digest(target) not in (before[guid][field], after[guid][field]):
                raise ValueError("A project file changed after interruption; recovery left it untouched.")
            checked.append((target, backup))
    for target, backup in checked:
        write_file_safely(target, backup.read_bytes())
    write_file_safely(manifest_path(project), json.dumps({"version": 1, "files": before}, indent=1))
    shutil.rmtree(root)
    return True


def replace_unchanged(project: Path, entries: dict, source: str) -> dict:
    """Replace only unchanged files imported from this product. Keep local edits and unmatched assets."""
    import os
    import shutil
    recover(project)
    before = load(project)
    from .unitypackage import project_guids
    present = project_guids(project)
    if any(entry["file"] is not None and guid not in present for guid, entry in entries.items()):
        raise ValueError("This asset update adds files not in the project. Import it manually to review the new assets first.")
    after = dict(before)
    paths = {}
    skipped = 0
    for guid, entry in entries.items():
        old = before.get(guid)
        if not source or entry["file"] is None or present.get(guid) != entry["path"] or (old and old.get("source") not in (None, "", source)):
            skipped += 1
            continue
        from .unitypackage import META_GUID
        match = META_GUID.search(entry["meta"])
        if match is None or match.group(1).decode() != guid:
            raise ValueError("The updated asset metadata has a different GUID.")
        fresh = {"path": entry["path"], "source": source, "sha256": digest(entry["file"]),
                 "meta_sha256": hashlib.sha256(entry["meta"]).hexdigest()}
        # Exact agreement with the selected package is evidence for an older import;
        # a matching GUID or path on its own is never enough to adopt a file.
        if unchanged(project, fresh):
            after[guid] = fresh
            continue
        if not old or old.get("source") != source or old["path"] != entry["path"] or not unchanged(project, old):
            skipped += 1
            continue
        after[guid] = fresh
        paths[guid] = old["path"]
    if not paths:
        if after != before:
            write_file_safely(manifest_path(project), json.dumps({"version": 1, "files": after}, indent=1))
        return {"updated": 0, "skipped": skipped}
    root = _workspace(project)
    if root.exists():
        raise ValueError("An unfinished update workspace needs attention.")
    root.mkdir(parents=True)
    journal = {"phase": "prepared", "before": before, "after": after, "paths": paths}
    prepared = False
    try:
        for guid, rel in paths.items():
            path = safe_file(project, rel)
            if path is None or not unchanged(project, before[guid]):
                raise ValueError("A project file changed before the update; nothing was replaced.")
            shutil.copyfile(path, root / (guid + ".asset"))
            shutil.copyfile(Path(str(path) + ".meta"), root / (guid + ".meta"))
            shutil.copyfile(entries[guid]["file"], root / (guid + ".newasset"))
            (root / (guid + ".newmeta")).write_bytes(entries[guid]["meta"])
        write_file_safely(root / "journal.json", json.dumps(journal))
        prepared = True
        for guid, rel in paths.items():
            path = safe_file(project, rel)
            if path is None or not unchanged(project, before[guid]):
                raise ValueError("A project file changed during the update.")
            os.replace(root / (guid + ".newasset"), path)
            os.replace(root / (guid + ".newmeta"), Path(str(path) + ".meta"))
        write_file_safely(manifest_path(project), json.dumps({"version": 1, "files": after}, indent=1))
        write_file_safely(root / "journal.json", json.dumps({**journal, "phase": "committed"}))
    except BaseException:
        if prepared:
            recover(project)
        else:
            shutil.rmtree(root)
        raise
    shutil.rmtree(root)
    return {"updated": len(paths), "skipped": skipped}


def update_file(project: Path, file: Path, source: str, member: str | None = None) -> dict:
    """Read a downloaded Unity package, then update tracked unchanged files while Unity is closed."""
    from contextlib import ExitStack
    import tempfile
    import zipfile
    from .project import UnityProject
    from . import unitypackage
    project = Path(project)
    if UnityProject.load(project).unity_running():
        raise ValueError("Close Unity before updating this project's assets.")
    library = _workspace(project).parent
    library.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hoard-managed-stage-", dir=library) as folder, ExitStack() as stack:
        if member is None:
            stream = stack.enter_context(open(file, "rb"))
        else:
            archive = stack.enter_context(zipfile.ZipFile(file))
            stream = stack.enter_context(archive.open(member))
        entries = unitypackage._entries(stream, Path(folder))
        if UnityProject.load(project).unity_running():
            raise ValueError("Close Unity before updating this project's assets.")
        return replace_unchanged(project, entries, source)
