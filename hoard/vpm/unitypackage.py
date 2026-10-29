"""Putting a .unitypackage's assets into a project without Unity: what ALCOM does for a template's packages, and
what Hoard does for the products you preload into a project.

A .unitypackage is a gzipped tar with a folder per asset, named by its GUID: "pathname" (where it goes), "asset"
(the file; a folder has none) and "asset.meta" (which keeps its GUID, so everything that refers to it still finds
it). Placing each asset and its .meta at its pathname is what Unity's own import does when nothing's in the way, so
Unity opens the project as if you'd imported it there.

A package is a file anyone could have made, so it's read as packages.py reads one (names and sizes checked before
anything is set aside for them), its paths must be plain ones under Assets/ or Packages/, and every asset is first
unpacked into the project's Library folder, then moved into place only when the whole package has been read.

Into a project that already has things, nothing already there is replaced: an asset whose GUID the project already
has (perhaps moved, or changed since), or whose path is taken by another, is left out and counted, as the import
window would show it unticked. A new project has nothing to collide with.
"""
from __future__ import annotations

import gzip
import os
import re
import shutil
import uuid
import zipfile
import zlib
from pathlib import Path

from ..packages import GUID, MAX_ENTRIES, MAX_PATHNAME, MAX_UNPACKED, NotAPackage, _field, _octal, _read_exactly, _skip

MAX_META = 1 << 20           # one asset's .meta: a few KB in real packages
MAX_METAS = 256 << 20        # every .meta in one package, held in memory until the package has been read
BANNED = set('<>:"|?*\0')
META_GUID = re.compile(rb"^guid:\s*([0-9a-f]{32})\s*$", re.M)


class ImportResult:
    """What an import did: assets placed, and those skipped because they were there already or something was in the
    way."""
    def __init__(self):
        self.placed = 0
        self.skipped_same = 0        # the project already has that asset (by GUID)
        self.skipped_taken = 0       # another asset is where it would go
        self.paths: list[str] = []   # the top folders it went into, for the page

    def as_dict(self) -> dict:
        """The result, for the page."""
        return {"placed": self.placed, "already_there": self.skipped_same, "in_the_way": self.skipped_taken,
                "folders": sorted(set(self.paths))[:20]}


def _clean_pathname(raw: bytes) -> str:
    """An asset's path in the package, as Unity reads it: its first line, with forward slashes. Raises NotAPackage for
    one that isn't safe to use."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise NotAPackage("an asset's path isn't text") from None
    text = text.split("\n")[0].rstrip("\r")   # Unity cuts a pathname at its first line break (and so does ALCOM)
    if not text or any(c in BANNED for c in text) or text.startswith("/"):
        raise NotAPackage(f"an asset's path can't be used: {text[:100]!r}")
    if any(p in ("", ".", "..") for p in text.split("/")):
        raise NotAPackage(f"an asset's path leads outside the project: {text[:100]!r}")
    return text


def _entries(stream, staging: Path) -> dict:
    """Read the package: {guid: {"path", "meta", "file" (a file in staging, or None for a folder)}}."""
    entries: dict[str, dict] = {}
    metas = 0
    try:
        gz = gzip.GzipFile(fileobj=stream, mode="rb")
        long_name, unpacked = None, 0
        for count in range(MAX_ENTRIES):
            header = gz.read(512)
            if not header:
                if count == 0:
                    raise NotAPackage("the file is empty")
                break
            if len(header) != 512:
                raise NotAPackage("the package ends partway")
            if header == bytes(512):
                break
            name = long_name if long_name is not None else (
                _field(header, 345, 155) + "/" + _field(header, 0, 100)
                if _field(header, 257, 6).startswith("ustar") and _field(header, 345, 155) else _field(header, 0, 100))
            long_name = None
            size, kind = _octal(header, 124, 12), chr(header[156])
            if size < 0:
                raise NotAPackage("not a Unity package")
            pad = (512 - size % 512) % 512
            unpacked += 512 + size + pad
            if unpacked > MAX_UNPACKED:
                raise NotAPackage("the package is larger than any real one")
            if kind == "L":
                if size > MAX_PATHNAME:
                    raise NotAPackage("not a Unity package")
                long_name = _read_exactly(gz, size).decode("utf-8", "replace").rstrip("\x00")
                _skip(gz, pad)
                continue
            parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
            if len(parts) != 2 or not GUID.fullmatch(parts[0]) or kind not in ("0", "\x00"):
                _skip(gz, size + pad)
                continue
            guid, part = parts
            entry = entries.setdefault(guid, {"path": None, "meta": None, "file": None})
            if part == "pathname":
                if size > MAX_PATHNAME or entry["path"] is not None:
                    raise NotAPackage("an asset has more than one path, or one too long")
                entry["path"] = _clean_pathname(_read_exactly(gz, size))
                _skip(gz, pad)
            elif part == "asset.meta":
                if size > MAX_META or entry["meta"] is not None:
                    raise NotAPackage("an asset has more than one .meta, or one larger than any real one")
                metas += size
                if metas > MAX_METAS:
                    raise NotAPackage("the package is larger than any real one")
                entry["meta"] = _read_exactly(gz, size)
                _skip(gz, pad)
            elif part == "asset":
                if entry["file"] is not None:
                    raise NotAPackage("an asset is in the package twice")
                target = staging / guid
                with open(target, "wb") as out:
                    left = size
                    while left:
                        chunk = gz.read(min(left, 1 << 20))
                        if not chunk:
                            raise NotAPackage("the package ends partway")
                        out.write(chunk)
                        left -= len(chunk)
                _skip(gz, pad)
                entry["file"] = target
            else:
                _skip(gz, size + pad)   # preview.png and anything else
        else:
            raise NotAPackage("the package has more entries than any real one")
    except (OSError, EOFError, zlib.error) as e:
        raise NotAPackage("not a Unity package, or a damaged one") from e
    out = {}
    for guid, e in entries.items():
        if e["path"] is None and e["meta"] is None and e["file"] is None:
            continue
        if e["path"] is None or e["meta"] is None:
            raise NotAPackage("an asset in the package has no path or no .meta")
        if not e["path"].startswith(("Assets/", "Packages/")):
            continue   # (as ALCOM: anything else isn't placed)
        out[guid] = e
    return out


def project_guids(project: Path) -> dict[str, str]:
    """Every GUID in the project's Assets and Packages, from its .meta files: {guid: the asset's path}."""
    found = {}
    for top in ("Assets", "Packages"):
        for root, dirs, names in os.walk(project / top):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
            for n in names:
                if not n.endswith(".meta"):
                    continue
                try:
                    with open(os.path.join(root, n), "rb") as f:
                        m = META_GUID.search(f.read(4096))
                except OSError:
                    continue
                if m:
                    found[m.group(1).decode()] = os.path.relpath(os.path.join(root, n[:-5]), project).replace(os.sep, "/")
    return found


def _inside(project: Path, rel: str) -> Path | None:
    """Where an asset's path is in the project, or None when it would land outside it."""
    path = project.joinpath(*rel.split("/"))
    try:
        real, root = path.parent.resolve(), project.resolve()
    except OSError:
        return None
    return path if real == root or root in real.parents else None


def place(project: Path, stream, existing: dict | None = None) -> ImportResult:
    """Put one package's assets into the project. existing (project_guids) means the project already has things:
    nothing already there is replaced. Raises NotAPackage for a file that isn't one (nothing is placed then)."""
    project = Path(project)
    library = project / "Library"
    library.mkdir(parents=True, exist_ok=True)
    staging = library / f".hoard-import-{uuid.uuid4().hex}"
    staging.mkdir()
    result = ImportResult()
    try:
        entries = _entries(stream, staging)
        taken = {p.lower() for p in existing.values()} if existing else set()
        # folders first, so each file's folder (and the folder's own .meta, with its GUID) is there before it
        for guid, e in sorted(entries.items(), key=lambda kv: (kv[1]["file"] is not None, kv[1]["path"])):
            rel = e["path"]
            if existing is not None and (guid in existing or rel.lower() in taken):
                if guid in existing:
                    result.skipped_same += 1
                else:
                    result.skipped_taken += 1
                continue
            path = _inside(project, rel)
            if path is None:
                result.skipped_taken += 1
                continue
            meta = Path(str(path) + ".meta")
            if e["file"] is None:
                path.mkdir(parents=True, exist_ok=True)
            else:
                if path.is_dir():
                    result.skipped_taken += 1
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(e["file"], path)
            meta.write_bytes(e["meta"])
            result.placed += 1
            result.paths.append("/".join(rel.split("/")[:2]))
            if existing is not None:
                existing[guid] = rel
                taken.add(rel.lower())
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return result


def place_file(project: Path, file: Path, member: str | None = None, existing: dict | None = None) -> ImportResult:
    """place() for a .unitypackage on disk, or one inside a .zip (member names it)."""
    if member is None:
        with open(file, "rb") as f:
            return place(project, f, existing)
    try:
        with zipfile.ZipFile(file) as zf:
            info = next((i for i in zf.infolist() if i.filename == member), None)
            if info is None:
                raise NotAPackage(f"{member} isn't in {file.name} any more")
            if info.flag_bits & 0x1:
                raise NotAPackage("the zip is locked with a password")
            with zf.open(info) as f:
                return place(project, f, existing)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as e:
        raise NotAPackage("not a zip, or a damaged one") from e
