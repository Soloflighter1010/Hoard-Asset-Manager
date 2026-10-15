"""Local: your own packages, textures and materials, beside what you bought (issue #80).

A Local item is a folder (or a single file) you add from this computer. You choose, each time, whether Hoard copies
it into its own Local folder (inside the downloads folder) or lists it where it is:

- A copy is Hoard's, like a download: the routine checks cover it, and an editable copy can be made of it.
- An item listed where it is stays yours: Hoard reads it but never writes, moves or deletes anything there, and the
  routine checks leave it alone, since it's your working folder. Rescan picks up files you've added or removed.
  For its tile, a copy of one of its pictures is kept in Hoard's own Local folder (see keep_picture).
  Only a manifest Hoard sealed on this computer can name such a folder (see clean_manifest).

You can choose an item's picture (choose_picture): it's kept in Hoard's app-data folder (local-pictures/) and copied
as the item's _thumbnail.<ext> in Hoard's own folder for it, which the pages and Hoard for Unity show first.

Either way it's in Downloads (the Local tab), tagged and searched like the rest, and in catalog.json, so Hoard for
Unity can import it. Records are kept in Local/_manifest.json, as each store's are.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
from pathlib import Path

from .common import log
from .downloader import Manifest, STORE_DIRS, build_catalog, record_folder, valid_location
from .downloads import IMAGE_EXT, PREVIEW_HINT
from .paths import data_dir
from .safety import UnsafePath, _is_link, chosen_picture, clean_text, open_under, rel_to_path, write_file_safely

LOCAL = STORE_DIRS["local"]
MAX_FILES = 20000
MAX_PICTURE = 20 * 1024 * 1024   # bytes: a bigger image isn't copied for the picture
SKIP = {".ds_store", "thumbs.db", "desktop.ini", "_manifest.json", "asset.json"}   # system clutter, and Hoard's own


def local_dir(root: Path) -> Path:
    return root / LOCAL


def pictures_dir() -> Path:
    return data_dir() / "local-pictures"


def chosen_folders(root: Path) -> set[str]:
    """The catalog folders ("Local/...") of the items you chose a picture for."""
    try:
        keys = {f.stem for f in pictures_dir().iterdir()} if pictures_dir().is_dir() else set()
    except OSError:
        return set()
    if not keys or not (local_dir(root) / "_manifest.json").is_file():
        return set()
    return {f"{LOCAL}/{rec.get('folder')}" for key, rec in Manifest(local_dir(root)).assets.items() if key in keys}


def _chosen(key: str) -> Path | None:
    """The picture you chose for an item, if you did."""
    if not re.fullmatch(r"local-[0-9a-f]{12}", key or ""):
        return None
    for ext in (".png", ".jpg", ".webp"):
        f = pictures_dir() / (key + ext)
        if f.is_file() and not f.is_symlink():
            return f
    return None


def walk(source: Path) -> list[str]:
    """The files under source, as /-separated paths, without following links (a link is left out, as is anything
    that isn't a plain file) and without system clutter. Raises ValueError when there are too many."""
    found: list[str] = []
    for top, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(top, d)))
        for name in sorted(files):
            if name.lower() in SKIP:
                continue
            full = os.path.join(top, name)
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError:
                continue
            if _is_link(st) or not stat.S_ISREG(st.st_mode):
                continue
            found.append(os.path.relpath(full, source).replace(os.sep, "/"))
            if len(found) > MAX_FILES:
                raise ValueError(f"That has more than {MAX_FILES:,} files. Add the folders inside it one at a time.")
    return found


def check_source(root: Path, path: str, copy: bool, around_ok: bool = False) -> Path:
    """The folder or file you typed, as a full path that's really there. Raises ValueError saying what's wrong.
    around_ok: a folder with Hoard's downloads folder inside it is fine (a folder of folders: split leaves that one
    out); added whole, it isn't: every download, Local itself too, would come into Local again."""
    text = str(path or "").strip().strip('"')
    if not text:
        raise ValueError("Enter the folder or file to add.")
    source = Path(os.path.expandvars(text)).expanduser()
    if not source.is_absolute():
        raise ValueError("Enter the full path, such as D:\\Packages\\My Textures.")
    source = Path(os.path.normpath(source))
    if os.path.islink(source):
        raise ValueError("That's a shortcut (a link). Choose the folder it leads to.")
    if not source.exists():
        raise ValueError("Nothing is there. Check the path.")
    inside = root.resolve()
    if source.resolve() == inside or inside in source.resolve().parents:
        raise ValueError("That's already inside Hoard's downloads folder.")
    if not around_ok and source.resolve() in inside.parents:
        raise ValueError("Hoard's downloads folder is inside that folder, so it would add everything Hoard has "
                         "downloaded. Choose the folder with your own things in it, or add each folder inside it "
                         "(Folders inside it).")
    if not copy and not source.is_dir():
        raise ValueError("To list something where it is, choose its folder. A single file can be copied in.")
    if not valid_location(str(source)):
        raise ValueError("Hoard can't use that path.")
    return source


MAX_SPLIT = 500   # packages one folder of folders can add at once (issue #109)
DEPTHS = (1, 2, 3)


def split(root: Path, path: str, depth: int, copy: bool) -> dict:
    """Issue #109: the packages in a folder of folders. Each folder depth levels down is one package, named for
    itself; from two levels down, the folder above it is who made it (a Creator/Product layout). Files in the
    folders above are left out, and counted in "loose". Links are never followed. Raises ValueError."""
    if depth not in DEPTHS or isinstance(depth, bool):
        raise ValueError("Choose how many levels down each package is.")
    source = check_source(root, path, copy, around_ok=True)
    if not source.is_dir():
        raise ValueError("To add each folder inside as its own package, choose a folder.")
    level, loose, inside = [source], 0, root.resolve()
    for _ in range(depth):
        below = []
        for folder in level:
            try:
                entries = sorted(os.scandir(folder), key=lambda e: e.name.lower())
            except OSError:
                continue
            for e in entries:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    here = Path(e.path).resolve()
                    if here != inside and here not in inside.parents:   # never Hoard's own downloads folder
                        below.append(Path(e.path))
                elif e.is_file(follow_symlinks=False) and e.name.lower() not in SKIP:
                    loose += 1
        level = below
        if len(level) > MAX_SPLIT:
            raise ValueError(f"That's more than {MAX_SPLIT} packages. Add the folders inside it one at a time.")
    if not level:
        raise ValueError(f"There are no folders {'inside it' if depth == 1 else f'{depth} levels down'}.")
    have = added_sources(root)
    return {"packages": [{"path": str(f), "rel": f.relative_to(source).as_posix(), "name": clean_text(f.name, 300) or "Untitled",
                          "creator": clean_text(f.parent.name, 200) if depth >= 2 else "",
                          "added": str(f.resolve()) in have} for f in level],
            "loose": loose}


def added_sources(root: Path) -> set[str]:
    """The folders and files already in Local, as added (copied in, or listed where they are), so adding a folder
    of folders again only adds what's new (issue #109). Packages added before Hoard kept this aren't known."""
    sdir = local_dir(root)
    if not (sdir / "_manifest.json").is_file():
        return set()
    out = set()
    for rec in Manifest(sdir).assets.values():
        where = isinstance(rec, dict) and (rec.get("source") or rec.get("location"))
        if where:
            try:   # as split() compares it: resolved (a mapped drive, a junction or a link to the same folder)
                out.add(str(Path(str(where)).resolve()))
            except (OSError, RuntimeError, ValueError):
                out.add(str(where))
    return out


def add(cfg: dict, root: Path, path: str, name: str = "", creator: str = "", note: str = "", copy: bool = True,
        progress=None, catalog: bool = True) -> dict:
    """Add a folder or file to Local: copied into Hoard's Local folder, or listed where it is. Returns the record.
    Raises ValueError with a plain explanation."""
    say = progress or (lambda line: None)
    source = check_source(root, path, copy)
    single = source.is_file()
    files = [source.name] if single else walk(source)
    if not files:
        raise ValueError("There are no files in that folder.")
    name = clean_text(name, 300) or clean_text(source.stem if single else source.name, 300) or "Untitled"
    creator = clean_text(creator, 200) or "You"
    sdir = local_dir(root)
    sdir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(sdir)
    key = "local-" + secrets.token_hex(6)
    rec = manifest.record(key, creator, name)
    rec.update(name=name, creator=creator, note=clean_text(note, 300) or None, url=None,
               source=str(source.resolve()))   # where it came from: adding a folder of folders again skips it (#109)
    base = source.parent if single else source
    if copy:
        dest = rel_to_path(sdir, rec["folder"])
        dest.mkdir(parents=True, exist_ok=True)
        for n, rel in enumerate(files, 1):
            say(f"Copying {n:,} of {len(files):,}: {rel}")
            digest, target = hashlib.sha256(), None
            try:   # a name Hoard won't use (Preview?.png) leaves out that file, not the rest: they're kept, and recorded
                target = rel_to_path(dest, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                with open_under(base, rel) as src, open(target, "xb") as out:
                    for block in iter(lambda: src.read(1024 * 1024), b""):
                        digest.update(block)
                        out.write(block)
            except (UnsafePath, OSError, ValueError) as e:
                log(f"Local: left out {rel} ({e})")
                if target is not None:
                    target.unlink(missing_ok=True)
                continue
            st = os.stat(target)
            rec["files"][f"f{n}"] = {"path": rel, "size": st.st_size, "sha256": digest.hexdigest(), "mtime_ns": st.st_mtime_ns}
    else:
        rec["folder"], rec["location"] = f"_linked/{key}", str(source)
        rec["files"] = _listing(source, files)
        keep_picture(sdir, rec, source, key)
    if not rec["files"]:
        manifest.assets.pop(key, None)
        raise ValueError("None of those files could be read.")
    manifest.save()
    if catalog:   # (several added together build it once, at the end)
        build_catalog(cfg, root)
    n = len(rec["files"])
    log(f"Local: added {name} ({n:,} {'file' if n == 1 else 'files'}, {'copied in' if copy else 'listed where it is'})")
    return rec


def keep_picture(sdir: Path, rec: dict, source: Path, key: str = "") -> None:
    """An item listed where it is: a copy of one of its pictures in Hoard's Local folder, as _thumbnail.<ext>, for its
    tile. Pictures are only shown from inside the downloads folder, so the folder itself (yours, anywhere on this
    computer) is never served. The one you chose comes first (choose_picture), then one named like a preview, then
    any. Nothing in your folder is written; a picture that can't be read is skipped."""
    try:
        dest = rel_to_path(sdir, rec["folder"])
    except UnsafePath:
        return
    chosen = _chosen(key)
    if chosen:   # (choose_picture put it there: put back if it's gone)
        if not any(dest.glob("_thumbnail.*")):
            try:
                write_file_safely(dest / ("_thumbnail" + chosen.suffix), chosen.read_bytes(), root=sdir)
            except OSError:
                pass
        return
    images = [f["path"] for f in rec.get("files", {}).values() if Path(f["path"]).suffix.lower() in IMAGE_EXT
              and (f.get("size") or 0) <= MAX_PICTURE]
    images.sort(key=lambda rel: (not PREVIEW_HINT.search(Path(rel).stem), rel.count("/"), rel.lower()))
    for old in dest.glob("_thumbnail.*") if dest.is_dir() else []:
        old.unlink(missing_ok=True)
    for rel in images[:5]:
        try:
            with open_under(source, rel) as fh:   # never through a link out of your folder
                data = fh.read(MAX_PICTURE + 1)
        except (UnsafePath, OSError):
            continue
        if not data or len(data) > MAX_PICTURE:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        write_file_safely(dest / ("_thumbnail" + Path(rel).suffix.lower()), data, root=sdir)
        return


def _own_thumbnails(dest: Path, rec: dict) -> list[Path]:
    """The _thumbnail.* files Hoard keeps in an item's folder: never one of the item's own files."""
    mine = {str(f.get("path", "")).lower() for f in rec.get("files", {}).values()} if not rec.get("location") else set()
    try:
        found = list(dest.glob("_thumbnail.*")) if dest.is_dir() and not dest.is_symlink() else []
    except OSError:
        return []
    return [f for f in found if f.name.lower() not in mine and f.is_file() and not f.is_symlink()]


def choose_picture(cfg: dict, root: Path, key: str, image) -> None:
    """Your own picture for an item's tile (safety.chosen_picture's image), or None to go back to one of its own.
    Copied as _thumbnail.<ext> into Hoard's folder for it: an item's copy in Local, or Local/_linked/... for one listed
    where it is, so nothing of yours is written. Raises ValueError with a plain explanation."""
    sdir = local_dir(root)
    rec = find(Manifest(sdir), key)
    if not re.fullmatch(r"local-[0-9a-f]{12}", key):
        raise ValueError("That isn't in Local any more.")
    try:
        dest = rel_to_path(sdir, rec["folder"])
    except UnsafePath:
        raise ValueError("Its folder can't be used any more.") from None
    if not rec.get("location") and not dest.is_dir():
        raise ValueError("Its folder isn't there any more.")
    if not rec.get("location") and any(str(f.get("path", "")).lower().startswith("_thumbnail.")
                                       for f in rec.get("files", {}).values()):
        raise ValueError("It has a _thumbnail picture of its own, which is the one shown. Change that file instead.")
    picture = chosen_picture(image) if image is not None else None
    if picture and picture[1] == "webp":   # (Hoard for Unity shows PNG and JPEG pictures)
        raise ValueError("Choose a PNG or JPEG picture.")
    for old in [*pictures_dir().glob(key + ".*"), *_own_thumbnails(dest, rec)]:
        old.unlink(missing_ok=True)
    if picture:
        data, kind = picture
        pictures_dir().mkdir(parents=True, exist_ok=True)
        write_file_safely(pictures_dir() / f"{key}.{kind}", data)
        write_file_safely(dest / f"_thumbnail.{kind}", data, root=sdir)
    elif rec.get("location"):   # one of its own pictures again, as when it was added
        try:
            keep_picture(sdir, rec, record_folder(sdir, rec), key)
        except UnsafePath:
            pass
    log(f"Local: {'chose a picture for' if picture else 'took the chosen picture off'} {rec.get('name')}")


def _forget_picture(sdir: Path, rec: dict) -> None:
    """Remove the copy keep_picture made (with the asset.json Hoard keeps beside it), and its folder
    (Local/_linked/...) once that's empty."""
    try:
        dest = rel_to_path(sdir, rec["folder"])
    except UnsafePath:
        return
    for old in [*dest.glob("_thumbnail.*"), dest / "asset.json"] if dest.is_dir() and not dest.is_symlink() else []:
        if old.is_file() and not old.is_symlink():
            old.unlink(missing_ok=True)
    for d in (dest, dest.parent):
        if d != sdir and sdir in d.parents:
            try:
                d.rmdir()   # only when empty
            except OSError:
                pass


def _listing(folder: Path, files: list[str]) -> dict:
    out = {}
    for n, rel in enumerate(files, 1):
        try:
            out[f"f{n}"] = {"path": rel, "size": os.stat(rel_to_path(folder, rel), follow_symlinks=False).st_size}
        except (UnsafePath, OSError):
            continue
    return out


def find(manifest: Manifest, key: str) -> dict:
    rec = manifest.assets.get(key) if isinstance(key, str) else None
    if rec is None:
        raise ValueError("That isn't in Local any more.")
    return rec


def rescan(cfg: dict, root: Path, key: str) -> dict:
    """An item listed where it is: read its folder again, so files you added show and ones you removed go."""
    manifest = Manifest(local_dir(root))
    rec = find(manifest, key)
    if not rec.get("location"):
        raise ValueError("Only items listed where they are can be rescanned: a copy in Hoard only changes when you add it again.")
    try:
        folder = record_folder(local_dir(root), rec)
    except UnsafePath:
        raise ValueError("Its folder can't be used any more.") from None
    if not folder.is_dir():
        raise ValueError(f"Its folder isn't there any more: {folder}")
    rec["files"] = _listing(folder, walk(folder))
    keep_picture(local_dir(root), rec, folder, key)
    manifest.save()
    build_catalog(cfg, root)
    return rec


def remove(cfg: dict, root: Path, key: str) -> dict:
    """Take an item out of Local. A copy's files (only the ones Hoard copied) are deleted with it, and its folder when
    that leaves it empty; an item listed where it is is only forgotten: nothing in your folder is touched."""
    sdir = local_dir(root)
    manifest = Manifest(sdir)
    rec = find(manifest, key)
    deleted = 0
    if not rec.get("location"):
        try:
            folder = rel_to_path(sdir, rec["folder"])
        except UnsafePath:
            folder = None
        if folder is not None:
            dirs = set()
            for old in _own_thumbnails(folder, rec):   # a picture you chose for it
                old.unlink(missing_ok=True)
            for rel in [f.get("path") for f in rec.get("files", {}).values()] + ["asset.json"]:   # (Hoard's, beside them)
                try:
                    target = rel_to_path(folder, rel)
                    st = os.stat(target, follow_symlinks=False)
                except (UnsafePath, OSError):
                    continue
                if _is_link(st) or not stat.S_ISREG(st.st_mode):
                    continue
                try:
                    os.unlink(target)
                    deleted += rel != "asset.json"
                except OSError:
                    continue
                dirs.update(target.parents)
            for d in sorted((d for d in dirs | {folder, folder.parent} if d != sdir and sdir in d.parents),
                            key=lambda d: len(d.parts), reverse=True):
                try:
                    d.rmdir()   # only when empty
                except OSError:
                    pass
    else:
        _forget_picture(sdir, rec)
    for old in pictures_dir().glob(key + ".*") if re.fullmatch(r"local-[0-9a-f]{12}", key) else []:
        old.unlink(missing_ok=True)
    manifest.assets.pop(key)
    manifest.save()
    build_catalog(cfg, root)
    return {"deleted": deleted, "listed": bool(rec.get("location"))}


def by_folder(root: Path, folder: str) -> tuple[str, dict] | None:
    """The Local item a catalog folder ("Local/...") names, as (key, record), or None."""
    if not isinstance(folder, str) or not folder.startswith(LOCAL + "/"):
        return None
    sdir = local_dir(root)
    if not (sdir / "_manifest.json").is_file():
        return None
    rest = folder[len(LOCAL) + 1:]
    for key, rec in Manifest(sdir).assets.items():
        if rec.get("folder") == rest:
            return key, rec
    return None
