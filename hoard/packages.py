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

import contextlib
import errno
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
from .safety import clean_text, safe_name

MAX_ENTRIES = 500_000
MAX_PATHNAME = 4096
MAX_UNPACKED = 64 << 30          # 64 GiB, far beyond any real package: a gzip bomb stops here
MAX_PREVIEW = 512 * 1024         # Unity's previews are 128x128 pictures, a few KB each
MAX_ITEMS = 50_000               # assets listed for one package (a page can't show more usefully)
MAX_ZIP_MEMBERS = 50_000
MAX_ZIP_PACKAGES = 50            # .unitypackage files read inside one .zip
KEEP = 40                        # files whose insides are kept in the cache
MAX_PREVIEW_BYTES = 64 << 20     # previews kept for one file (a big real package's are a few MB); past it, none
MAX_CACHE = 512 << 20            # what's kept in the cache in all: the least recently looked at go first
GUID = re.compile(r"[0-9a-f]{32}")
CACHE_ID = re.compile(r"[0-9a-f]{32}")
PREVIEW_NAME = re.compile(r"(\d{1,2})-([0-9a-f]{32})\.png")
PNG = b"\x89PNG\r\n\x1a\n"
FORMAT = 1
KINDS = (".unitypackage", ".zip")


class NotAPackage(ValueError):
    """A file that isn't what its name says (a damaged download, or something else named .unitypackage)."""


def can_look_inside(name: str) -> bool:
    """Can Look inside read this file (a .unitypackage or a .zip)?"""
    return name.lower().endswith(KINDS)


# ----------------------------------------------------------------------------- a .unitypackage, from a stream

def _read_exactly(stream, n: int) -> bytes:
    """n bytes of the stream, raising NotAPackage when it ends first."""
    data = stream.read(n)
    if len(data) != n:
        raise NotAPackage("the package ends partway")
    return data


def _skip(stream, n: int) -> None:
    """Move past n bytes of the stream, a megabyte at a time."""
    while n > 0:
        got = stream.read(min(n, 1 << 20))
        if not got:
            raise NotAPackage("the package ends partway")
        n -= len(got)


def _field(h: bytes, at: int, length: int) -> str:
    """A text field of a tar header, up to its first zero byte."""
    raw = h[at:at + length]
    return raw[:raw.index(0)].decode("utf-8", "replace") if 0 in raw else raw.decode("utf-8", "replace")


def _octal(h: bytes, at: int, length: int) -> int:
    """A number field of a tar header (octal); 0 when blank, -1 when it isn't a number."""
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


def read_unitypackage(stream, on_preview=None, refs: set | None = None, on_asset=None) -> dict:
    """What a .unitypackage holds, from a stream of its (gzipped) bytes: {GUID: {"path", "size" (None for a folder),
    "preview" (has one)}}. on_preview(guid, png bytes) gets each preview that's a real PNG of a sensible size, and
    returns False for one it doesn't keep (that asset then has no preview). refs,
    when given, gets every GUID the package's text assets name (its own among them). on_asset(guid, "asset" or
    "asset.meta", size, stream), when given, is offered each asset's bytes (Extract): it reads exactly size of them
    and returns True, or returns False to pass them by. Raises NotAPackage for anything that isn't one."""
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
            elif part in ("asset", "asset.meta") and kind in ("0", "\x00"):
                if part == "asset":
                    assets.setdefault(guid, {"size": None, "preview": False})["size"] = size
                if on_asset is not None and on_asset(guid, part, size, gz):
                    _skip(gz, pad)
                elif part == "asset" and refs is not None:
                    _scan(gz, size, refs)
                    _skip(gz, pad)
                else:
                    _skip(gz, size + pad)
            elif part == "preview.png" and 8 <= size <= MAX_PREVIEW and on_preview is not None:
                data = _read_exactly(gz, size)
                _skip(gz, pad)
                if data.startswith(PNG) and on_preview(guid, data) is not False:
                    assets.setdefault(guid, {"size": None, "preview": False})["preview"] = True
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
                name = member_name(info)
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
    """Where what Look inside read is kept, so a second look is quick."""
    return data_dir() / "cache" / "inside"


def cache_id(path: Path, st: os.stat_result) -> str:
    """One file as it is now: a changed or moved file is read again."""
    return hashlib.sha256(f"{path}\0{st.st_size}\0{st.st_mtime_ns}".encode("utf-8", "surrogateescape")).hexdigest()[:32]


def _load(folder: Path) -> dict | None:
    """What Look inside read of a file before (its inside.json), when it's still the format Hoard reads; None
    otherwise."""
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


def _prune(keep: int = KEEP, max_bytes: int = MAX_CACHE) -> None:
    """Keep the KEEP files looked at most recently, and no more than max_bytes of them (the newest is always kept)."""
    try:
        folders = [f for f in cache_dir().iterdir() if f.is_dir() and not f.is_symlink() and CACHE_ID.fullmatch(f.name)]
    except OSError:
        return
    def used(f: Path) -> float:
        """When a kept look was last used (its inside.json's time)."""
        try:
            return (f / "inside.json").stat().st_mtime
        except OSError:
            return 0.0
    def size(f: Path) -> int:
        """How much a kept look takes on disk."""
        try:
            return sum(e.stat(follow_symlinks=False).st_size for e in os.scandir(f))
        except OSError:
            return 0
    total = 0
    for n, f in enumerate(sorted(folders, key=used, reverse=True)):
        total += size(f) if n < keep else 0
        if n >= keep or (n and total > max_bytes):
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
        kept = [0]

        def keep(n: int, guid: str, data: bytes) -> bool:
            """Keep one preview picture, while there's room for it (MAX_PREVIEW_BYTES in all)."""
            if kept[0] + len(data) > MAX_PREVIEW_BYTES:
                return False   # a package with far more previews than any real one: the rest go without
            (work / f"{n}-{guid}.png").write_bytes(data)
            kept[0] += len(data)
            return True
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


# ----------------------------------------------------------------------------- taking files out (Look inside, Extract)

ROOM_TO_SPARE = 256 << 20        # what extracting leaves free on the disk it writes to, at least
CHUNK = 1 << 20


def _new_file_mode() -> int:
    """The permissions a new file gets here (0o666 less the umask): what extracted files are given, as a copy's are,
    not mkstemp's owner-only 0o600 (issue #176). Read once, as the module loads."""
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


FILE_MODE = _new_file_mode()


class CantExtract(ValueError):
    """Why nothing more could be taken out (the disk is full, a link was planted where it writes), in words for the
    page."""


class _Skip(Exception):
    """One file, or folder, that couldn't be written: it's left out, with why, and the rest carry on (issue #174)."""

    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


class _Done(Exception):
    """Every chosen file is out: the rest of the package needn't be read (issue #182)."""


def member_name(info: zipfile.ZipInfo) -> str:
    """A zip member's name as Look inside lists it (read_zip) and Extract finds it again: one spelling for both."""
    return clean_text(zip_name(info), 1000) or "(no name)"


def out_parts(path: str) -> list[str] | None:
    """A path from inside a package or zip as the folders and name it's written at, each a name that's safe on every
    system (safety.safe_name); None for one that climbs out ("..") or has nothing in it. An absolute path, or one
    with a drive, is taken as a path inside the folder it's written to."""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts or len(parts) > 64:
        return None
    return [safe_name(p, 120) for p in parts]


def _drain(stream, size: int) -> None:
    """size bytes of stream read and dropped: what a file left out takes up, so a package's reader stays in step."""
    while size > 0:
        chunk = stream.read(min(size, CHUNK))
        if not chunk:
            raise NotAPackage("the package ends partway")
        size -= len(chunk)


class Writer:
    """Files written under one folder Hoard has just made: each where its path says (out_parts), only inside the
    folder, never through a link, and only while there's room. A name already taken gets " (2)"; a file and its
    .meta are given names together, so they always pair (issue #172). One that can't be written is left out
    (_Skip); a full disk stops it all (CantExtract)."""

    def __init__(self, dest: Path):
        self.dest = dest
        self.room = shutil.disk_usage(dest).free - ROOM_TO_SPARE
        self.taken: set[str] = set()
        self.files = self.bytes = 0

    def _failed(self, e: OSError, path: Path) -> Exception:
        """What an error writing path means: the disk's (nothing more can be written), or that one file's."""
        if e.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", None), errno.EROFS):
            return CantExtract(f"Couldn't write in {self.dest}: {e.strerror or e}.")
        if e.errno == errno.ENAMETOOLONG or getattr(e, "winerror", None) == 206 or (os.name == "nt" and len(str(path)) >= 260):
            return _Skip("its path is too long for this system")
        print(f"Couldn't write {path}: {e}", flush=True)   # (the system's own words, for the log; the page's are fixed)
        return _Skip("it couldn't be written")

    def _inside(self, folder: Path) -> None:
        """folder (under dest) made a level at a time, never through a link: a folder that's a link already (planted
        there, or made by something else since) stops it all before anything is made where it leads. A file where a
        folder should be (two names made the same by safe_name, or by a system that ignores case) leaves out what
        would go in it."""
        here = self.dest
        for part in folder.relative_to(self.dest).parts:
            here = here / part
            if os.path.islink(here):
                raise CantExtract("A path in it leads outside the folder it's taken out to, so it wasn't.")
            try:
                here.mkdir()
            except FileExistsError:
                if os.path.islink(here):
                    raise CantExtract("A path in it leads outside the folder it's taken out to, so it wasn't.") from None
                if not here.is_dir():
                    raise _Skip("a file of the same name is in the way") from None
            except OSError as e:
                raise self._failed(e, here) from e

    def folder(self, parts: list[str]) -> None:
        """Make a folder of the package (an asset that's a folder), inside where it's taken out to."""
        self._inside(self.dest.joinpath(*parts))

    def _free(self, path: Path) -> bool:
        """Is nothing at this path yet, nor taken by another file of this extraction?"""
        return str(path).casefold() not in self.taken and not os.path.lexists(path)

    def place(self, parts: list[str], meta: bool = False) -> tuple[Path, Path | None]:
        """Where a file goes, and with meta where its .meta goes beside it: a name free for both, "name (2).ext" if
        the one its path says is taken, kept for them."""
        target = self.dest.joinpath(*parts)
        stem, suffix, n = target.stem, target.suffix, 2
        pair = lambda p: p.with_name(p.name + ".meta") if meta else None  # noqa: E731
        while not (self._free(target) and (not meta or self._free(pair(target)))):
            target, n = target.with_name(f"{stem} ({n}){suffix}"), n + 1
        for p in (target, pair(target)):
            if p is not None:
                self.taken.add(str(p).casefold())
        self._inside(target.parent)
        return target, pair(target)

    def exactly(self, parts: list[str]) -> Path:
        """Where a file goes that only works under the name its path says (a folder's .meta, issue #173): kept for
        it, or left out if that name is taken."""
        target = self.dest.joinpath(*parts)
        if not self._free(target):
            raise _Skip("a file of the same name is in the way")
        self.taken.add(str(target).casefold())
        self._inside(target.parent)
        return target

    def write(self, target: Path, stream, size: int) -> None:
        """size bytes from stream at target (from place): written beside it, given a new file's permissions, then put
        in its place. All size bytes are read even when the file can't be written, so a package's reader stays in
        step with the package."""
        if size > self.room:
            raise CantExtract("There isn't room for it on that disk.")
        try:
            fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".extracting-")
        except OSError as e:
            _drain(stream, size)
            raise self._failed(e, target) from e
        failed = None
        try:
            with os.fdopen(fd, "wb") as out:
                left = size
                while left > 0:
                    chunk = stream.read(min(left, CHUNK))   # (a damaged package's errors are its own)
                    if not chunk:
                        raise NotAPackage("the package ends partway")
                    left -= len(chunk)
                    if failed is None:
                        try:
                            out.write(chunk)
                        except OSError as e:
                            failed = e
            if failed is None:
                if os.name != "nt":
                    os.chmod(tmp, FILE_MODE)
                os.replace(tmp, target)
        except OSError as e:   # (closing, or putting it in place)
            failed = e
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        if failed is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise self._failed(failed, target)
        self.room -= size
        self.files, self.bytes = self.files + 1, self.bytes + size


def chosen(items: list[dict], picks: set, n: int, every: bool) -> dict[str, dict]:
    """A package's assets that were chosen (Look inside's picks: "p:<n>:<path>" a file, "d:<n>:<path>" a folder and
    everything in it), or all of them: {guid: item}."""
    files = {p.split(":", 2)[2] for p in picks if p.startswith(f"p:{n}:")}
    folders = tuple(p.split(":", 2)[2] for p in picks if p.startswith(f"d:{n}:"))
    return {i["guid"]: i for i in items
            if every or i["path"] in files or any(i["path"] == f or i["path"].startswith(f + "/") for f in folders)}


def _take(stream, want: dict[str, dict], writer: Writer, under: list[str], metas: bool, skipped: list, label: str = "") -> None:
    """The chosen assets of one package (chosen()), out of its stream, each at its path in the project, under under;
    with metas, each one's .meta beside it, a folder's too (issue #173). One that can't be written is added to
    skipped as (label + its path, why), and the rest carry on. Reading stops once every chosen file is out."""
    paths = {g: out_parts(i["path"]) for g, i in want.items()}
    left_out: set[str] = set()

    def leave(g: str, why: str) -> None:
        """Leave an asset out, noting why, once."""
        if g not in left_out:
            left_out.add(g)
            skipped.append((label + want[g]["path"], why))
    for g in want:
        if paths[g] is None:   # ("..", or nothing in it: never written, and said, issue #174)
            leave(g, "its path leads outside the folder")
    for g in sorted((g for g, i in want.items() if i["size"] is None and paths[g]), key=lambda g: len(paths[g])):
        try:   # (folders first, so a chosen empty one is there too)
            writer.folder(under + paths[g])
        except _Skip as e:
            leave(g, e.why)
    todo = {(g, "asset") for g, i in want.items() if i["size"] is not None and g not in left_out}
    if metas:
        todo |= {(g, "asset.meta") for g in want if g not in left_out}
    spots: dict[str, tuple] = {}

    def spot(g: str) -> tuple[Path | None, Path | None]:
        """Where a chosen asset and its .meta go: kept for both at the first sight of either, so they pair."""
        if g not in spots:
            parts = under + paths[g]
            try:
                spots[g] = ((None, writer.exactly(parts[:-1] + [parts[-1] + ".meta"])) if want[g]["size"] is None
                            else writer.place(parts, metas))
            except _Skip as e:
                spots[g] = e
        if isinstance(spots[g], _Skip):
            raise spots[g]
        return spots[g]

    def on_asset(guid: str, part: str, size: int, gz) -> bool:
        """One part of an asset as the package's stream reaches it (its file, or its .meta): written where it goes when
        it's chosen; True when it was taken."""
        if (guid, part) not in todo:
            return False
        todo.discard((guid, part))
        try:
            target, meta = spot(guid)
        except _Skip as e:
            leave(guid, e.why)
            if not todo:
                raise _Done from None
            return False
        try:
            writer.write(meta if part == "asset.meta" else target, gz, size)
        except _Skip as e:
            leave(guid, e.why)
        if not todo:
            raise _Done
        return True
    if not todo:
        return
    try:
        read_unitypackage(stream, on_asset=on_asset)
    except _Done:
        pass


def extract(path: Path, dest: Path, picks: list[str], metas: bool = False) -> dict:
    """Look inside's Extract: the chosen files (picks, as chosen() reads them, and "z:<name>" a file of a zip as it
    is), or every one ("all"), out of a downloaded .unitypackage or .zip, into dest (a folder Hoard has just made).
    A package's assets go where their paths say (Assets/...); a zip's files where theirs do, and the assets of a
    package in a zip in a folder named after it, where it is in the zip (issue #175). A file that can't be written
    is left out, with why, and the rest still come out (issue #174). Returns {"files", "bytes", "skipped": [(name,
    why)]}. Raises CantExtract when nothing more could be written, or NotAPackage for a file that can't be read."""
    listing = look_inside(path)
    if listing.get("error"):
        raise CantExtract(listing["error"])
    picks_set, every = set(picks), "all" in picks
    writer, skipped = Writer(dest), []
    try:
        if listing["kind"] == "unitypackage":
            want = chosen(listing["items"], picks_set, 0, every)
            if not want:
                raise CantExtract("Choose what to take out first.")
            with open(path, "rb") as fh:
                _take(fh, want, writer, [], metas, skipped)
        else:
            with zipfile.ZipFile(path) as zf:
                by_name: dict[str, list] = {}   # (the members Look inside listed, by the names it gave them, issue #182)
                for info in zf.infolist()[:MAX_ZIP_MEMBERS]:
                    if not info.is_dir():
                        by_name.setdefault(member_name(info), []).append(info)
                plain = ([(n, i) for n, infos in by_name.items() for i in infos] if every
                         else [(p[2:], by_name[p[2:]][0]) for p in dict.fromkeys(picks) if p.startswith("z:") and p[2:] in by_name])
                jobs, seen = [], {}
                for n, pkg in enumerate(listing["packages"]):   # (the k-th package of a name is its k-th member)
                    k = seen[pkg["name"]] = seen.get(pkg["name"], -1) + 1
                    want = chosen(pkg["items"], picks_set, n, False)
                    if want and k < len(by_name.get(pkg["name"], [])):
                        jobs.append((pkg["name"], by_name[pkg["name"]][k], want))
                if not plain and not jobs:
                    raise CantExtract("Choose what to take out first.")
                unreadable = (NotAPackage, zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, zlib.error, EOFError)
                for name, info in plain:
                    parts = out_parts(name)
                    if info.flag_bits & 0x1:
                        skipped.append((name, "locked with a password"))
                    elif parts is None:
                        skipped.append((name, "its name leads outside the folder"))
                    else:
                        try:
                            target, _ = writer.place(parts)
                            with zf.open(info) as member:
                                writer.write(target, member, info.file_size)
                        except _Skip as e:
                            skipped.append((name, e.why))
                        except unreadable:   # one damaged file: the rest still come out
                            skipped.append((name, "couldn't be read"))
                folders: set[str] = set()
                for name, info, want in jobs:
                    if info.flag_bits & 0x1:
                        skipped.append((name, "locked with a password"))
                        continue
                    under = out_parts(name[:-len(".unitypackage")] if name.lower().endswith(".unitypackage") else name)
                    if under is None:
                        skipped.append((name, "its name leads outside the folder"))
                        continue
                    base, n = under[-1], 2   # (two packages of the same name, in the same place: one folder each)
                    while "/".join(under).casefold() in folders:
                        under, n = under[:-1] + [f"{base} ({n})"], n + 1
                    folders.add("/".join(under).casefold())
                    try:
                        with zf.open(info) as member:
                            _take(member, want, writer, under, metas, skipped, label=name + ": ")
                    except unreadable:
                        skipped.append((name, "couldn't be read"))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as e:   # (the zip itself, not one file in it)
        raise NotAPackage("not a zip, or a damaged one") from e
    return {"files": writer.files, "bytes": writer.bytes, "skipped": skipped}


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
