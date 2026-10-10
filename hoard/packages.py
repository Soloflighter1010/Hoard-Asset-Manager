"""Inside a download (Downloads, Look inside): what a .unitypackage holds, and what a .zip holds, packages included.

A .unitypackage is a gzipped tar with a folder per asset, named by its GUID, holding "pathname" (where the asset goes
in a project), "asset" (the file itself; a folder has none), "asset.meta" and, for many assets, "preview.png" (the
picture Unity shows for it). This reads the names, the sizes and the previews, straight from the package: nothing is
extracted, imported or run. A .zip is listed from its directory, and each .unitypackage in it read the same way,
straight out of the zip.

A download is a file anyone could have made, so what it claims is checked before it's acted on, as Hoard for Unity's
UnityPackageReader.cs does: only names and previews are ever read into memory, each with a limit checked before
anything is set aside for it, and a package that would unpack to more than any real one does is refused rather than
read to the end.

What was read is kept in Hoard's cache (cache/inside/), one folder per file as it was (its path, size and time), so a
second look is instant; the least recently looked at go once there are more than KEEP of them.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
import zlib
from pathlib import Path

from .paths import data_dir
from .safety import clean_text

MAX_ENTRIES = 500_000
MAX_PATHNAME = 4096
MAX_UNPACKED = 64 << 30          # 64 GiB, far beyond any real package: a gzip bomb stops here
MAX_PREVIEW = 512 * 1024         # Unity's previews are 128x128 pictures, a few KB each
MAX_ITEMS = 50_000               # assets listed for one package (a page can't show more usefully)
MAX_ZIP_MEMBERS = 50_000
MAX_ZIP_PACKAGES = 50            # .unitypackage files read inside one .zip
KEEP = 40                        # files whose insides are kept in the cache
GUID = re.compile(r"[0-9a-f]{32}")
CACHE_ID = re.compile(r"[0-9a-f]{32}")
PREVIEW_NAME = re.compile(r"(\d{1,2})-([0-9a-f]{32})\.png")
PNG = b"\x89PNG\r\n\x1a\n"
FORMAT = 1
KINDS = (".unitypackage", ".zip")


class NotAPackage(ValueError):
    """A file that isn't what its name says (a damaged download, or something else named .unitypackage)."""


def can_look_inside(name: str) -> bool:
    return name.lower().endswith(KINDS)


# ----------------------------------------------------------------------------- a .unitypackage, from a stream

def _read_exactly(stream, n: int) -> bytes:
    data = stream.read(n)
    if len(data) != n:
        raise NotAPackage("the package ends partway")
    return data


def _skip(stream, n: int) -> None:
    while n > 0:
        got = stream.read(min(n, 1 << 20))
        if not got:
            raise NotAPackage("the package ends partway")
        n -= len(got)


def _field(h: bytes, at: int, length: int) -> str:
    raw = h[at:at + length]
    return raw[:raw.index(0)].decode("utf-8", "replace") if 0 in raw else raw.decode("utf-8", "replace")


def _octal(h: bytes, at: int, length: int) -> int:
    s = _field(h, at, length).strip(" \x00")
    if not s:
        return 0
    try:
        return int(s, 8)
    except ValueError:
        return -1


REF = re.compile(rb"guid: ([0-9a-f]{32})")
MAX_SCAN = 64 << 20              # a text asset (a material, a prefab) larger than this isn't looked through
MAX_REFS = 20_000                # GUIDs noted as named by one package


def _scan(gz, size: int, refs: set) -> None:
    """Go through one asset's bytes, noting every GUID it names if it's a text asset (Unity's YAML: a material names
    its shader's GUID, a prefab each component's script's), else just passing over it."""
    head = gz.read(min(size, 1 << 16))
    if len(head) != min(size, 1 << 16):
        raise NotAPackage("the package ends partway")
    left = size - len(head)
    if not head.startswith(b"%YAML") or size > MAX_SCAN:
        _skip(gz, left)
        return
    tail = b""
    chunk = head
    while True:
        block = tail + chunk
        for m in REF.finditer(block):
            if len(refs) < MAX_REFS:
                refs.add(m.group(1).decode())
        tail = block[-48:]          # a GUID cut in two by a chunk's end is found in the next
        if left <= 0:
            return
        chunk = gz.read(min(left, 1 << 20))
        if not chunk:
            raise NotAPackage("the package ends partway")
        left -= len(chunk)


def read_unitypackage(stream, on_preview=None, refs: set | None = None) -> dict:
    """What a .unitypackage holds, from a stream of its (gzipped) bytes: {GUID: {"path", "size" (None for a folder),
    "preview" (has one)}}. on_preview(guid, png bytes) gets each preview that's a real PNG of a sensible size. refs,
    when given, gets every GUID the package's text assets name (its own among them). Raises NotAPackage for anything
    that isn't one."""
    assets: dict[str, dict] = {}
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
                break                                                    # the end of the archive
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
            if kind == "L":                                              # a long name for the next entry
                if size > MAX_PATHNAME:
                    raise NotAPackage("not a Unity package")
                long_name = _read_exactly(gz, size).decode("utf-8", "replace").rstrip("\x00")
                _skip(gz, pad)
                continue
            parts = name.replace("\\", "/").lstrip("./").split("/")
            guid = parts[0] if len(parts) == 2 and GUID.fullmatch(parts[0]) else None
            part = parts[1] if guid else None
            if part == "pathname" and size <= MAX_PATHNAME:
                path = _read_exactly(gz, size).decode("utf-8", "replace").split("\n")[0].strip()
                _skip(gz, pad)
                if path:
                    assets.setdefault(guid, {"size": None, "preview": False})["path"] = path
            elif part == "asset" and kind in ("0", "\x00"):
                assets.setdefault(guid, {"size": None, "preview": False})["size"] = size
                if refs is not None:
                    _scan(gz, size, refs)
                    _skip(gz, pad)
                else:
                    _skip(gz, size + pad)
            elif part == "preview.png" and 8 <= size <= MAX_PREVIEW and on_preview is not None:
                data = _read_exactly(gz, size)
                _skip(gz, pad)
                if data.startswith(PNG):
                    assets.setdefault(guid, {"size": None, "preview": False})["preview"] = True
                    on_preview(guid, data)
            else:
                if part == "preview.png" and 8 <= size <= MAX_PREVIEW:
                    assets.setdefault(guid, {"size": None, "preview": False})["preview"] = True
                _skip(gz, size + pad)
        else:
            raise NotAPackage("the package has more entries than any real one")
    except (OSError, EOFError, zlib.error) as e:   # gzip's own: not gzip at all, or damaged partway
        raise NotAPackage("not a Unity package, or a damaged one") from e
    return {g: a for g, a in assets.items() if a.get("path")}


def _items(assets: dict) -> list[dict]:
    """A package's assets for the page, by their path: [{"path", "size" (None: a folder), "guid", "preview"}]."""
    out = [{"path": clean_text(a["path"], 1000), "size": a["size"], "guid": g, "preview": a["preview"]}
           for g, a in assets.items()]
    out = [i for i in out if i["path"]]
    out.sort(key=lambda i: i["path"].casefold())
    return out[:MAX_ITEMS]


# ----------------------------------------------------------------------------- a .zip

def zip_name(info: zipfile.ZipInfo) -> str:
    """A zip member's name as its maker wrote it. A zip that doesn't say its names are UTF-8 (flag bit 11) is read as
    code page 437 by Python; most made on a Japanese computer are really Shift-JIS (cp932), and many others UTF-8."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        raw = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename
    for codec in ("utf-8", "cp932"):
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            pass
    return info.filename


def read_zip(path: Path, on_preview=None) -> dict:
    """A .zip's files, and what each .unitypackage in it holds: {"files": [{"name", "size", "package" (its number in
    "packages", or None), "locked"}], "packages": [{"name", "items", "error"}], "more": files left out}."""
    files, packages = [], []
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            for info in infos[:MAX_ZIP_MEMBERS]:
                if info.is_dir():
                    continue
                name = clean_text(zip_name(info), 1000) or "(no name)"
                locked = bool(info.flag_bits & 0x1)
                entry = {"name": name, "size": info.file_size, "package": None, "locked": locked}
                if name.lower().endswith(".unitypackage") and len(packages) < MAX_ZIP_PACKAGES:
                    n = len(packages)
                    entry["package"] = n
                    pkg = {"name": name, "items": [], "error": None}
                    if locked:
                        pkg["error"] = "This zip is locked with a password, so what's in this package can't be read."
                    else:
                        try:
                            with zf.open(info) as member:
                                pkg["items"] = _items(read_unitypackage(
                                    member, None if on_preview is None else lambda g, d, n=n: on_preview(n, g, d)))
                        except (NotAPackage, zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, zlib.error) as e:
                            pkg["error"] = _why(e)
                    packages.append(pkg)
                files.append(entry)
            more = max(0, len(infos) - MAX_ZIP_MEMBERS)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, NotImplementedError) as e:
        raise NotAPackage("not a zip, or a damaged one") from e
    files.sort(key=lambda f: f["name"].casefold())
    return {"files": files, "packages": packages, "more": more}


def _why(e: BaseException) -> str:
    """Why a file couldn't be read, as the page says it (a sentence of its own, so it can be translated whole)."""
    if isinstance(e, NotAPackage):
        said = str(e)
        if "larger" in said or "more entries" in said:
            return "It's larger than any real Unity package, so it wasn't read to the end."
        if "empty" in said:
            return "The file is empty."
        return "It isn't a zip, or it's damaged." if "zip" in said else "It isn't a Unity package, or it's damaged."
    if isinstance(e, NotImplementedError):
        return "It's packed in a way Hoard can't read (an unusual kind of compression)."
    if isinstance(e, RuntimeError) and "password" in str(e).lower():
        return "This zip is locked with a password, so what's in this package can't be read."
    return "It couldn't be read: it may be damaged."


# ----------------------------------------------------------------------------- the cache, and the page's view

def cache_dir() -> Path:
    return data_dir() / "cache" / "inside"


def cache_id(path: Path, st: os.stat_result) -> str:
    """One file as it is now: a changed or moved file is read again."""
    return hashlib.sha256(f"{path}\0{st.st_size}\0{st.st_mtime_ns}".encode("utf-8", "surrogateescape")).hexdigest()[:32]


def _load(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / "inside.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("kind") not in ("unitypackage", "zip"):
        return None
    try:
        os.utime(folder / "inside.json")   # (recently looked at: kept longest)
    except OSError:
        pass
    return data


def _prune(keep: int = KEEP) -> None:
    try:
        folders = [f for f in cache_dir().iterdir() if f.is_dir() and not f.is_symlink() and CACHE_ID.fullmatch(f.name)]
    except OSError:
        return
    def used(f: Path) -> float:
        try:
            return (f / "inside.json").stat().st_mtime
        except OSError:
            return 0.0
    for f in sorted(folders, key=used, reverse=True)[keep:]:
        shutil.rmtree(f, ignore_errors=True)


def look_inside(path: Path) -> dict:
    """What's inside a downloaded .unitypackage or .zip, for the page: {"id", "kind": "unitypackage", "items"} or
    {"id", "kind": "zip", "files", "packages", "more"}; with "error" instead when it can't be read. Previews are
    kept with it, and served by preview()."""
    st = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(st.st_mode):
        raise NotAPackage("not a plain file")
    cid = cache_id(path, st)
    here = cache_dir() / cid
    found = _load(here)
    if found is not None:
        return {**found, "id": cid}
    cache_dir().mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".reading-", dir=cache_dir()))
    try:
        def keep(n: int, guid: str, data: bytes) -> None:
            (work / f"{n}-{guid}.png").write_bytes(data)
        kind = "zip" if path.name.lower().endswith(".zip") else "unitypackage"
        result: dict = {"format": FORMAT, "kind": kind, "read": time.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            with open(path, "rb") as fh:
                if kind == "zip":
                    result.update(read_zip(path, keep))
                else:
                    result["items"] = _items(read_unitypackage(fh, lambda g, d: keep(0, g, d)))
        except NotAPackage as e:
            result["error"] = _why(e)
        (work / "inside.json").write_text(json.dumps(result, ensure_ascii=False), "utf-8")
        try:
            os.replace(work, here)
        except OSError:          # read at the same time by another request: theirs is as good
            pass
        _prune()
        return {**result, "id": cid}
    finally:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)


def preview(cid: str, name: str) -> bytes | None:
    """A preview kept with what was read (look_inside), by the names the page was given; None for anything else."""
    if not CACHE_ID.fullmatch(cid or "") or not PREVIEW_NAME.fullmatch(name or ""):
        return None
    base = os.path.realpath(cache_dir())
    path = os.path.realpath(os.path.join(base, cid, name))
    if not path.startswith(base + os.sep):   # (and inside the cache, wherever a link might lead)
        return None
    try:
        st = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_PREVIEW:
            return None
        with open(path, "rb") as fh:
            data = fh.read(MAX_PREVIEW + 1)
    except OSError:
        return None
    return data if data.startswith(PNG) and len(data) <= MAX_PREVIEW else None
