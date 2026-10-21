"""Your library in your projects: what in a downloaded product can go into a project, and putting it there.

A product's files can hold:
- .unitypackage files, on their own or inside a .zip: placed into the project's Assets as Unity's import would
  (unitypackage.py), leaving anything already in the project as it is.
- a VPM package: a .zip with package.json at its top (or in one folder at its top, or such a .zip inside the
  product's .zip), as creators sell tools on Booth. It goes into Packages/<its name> as the project's own package,
  and the packages it asks for come from your repositories when the project is put right (resolve.repair).
- a folder with package.json (a package of your own in Local).

What a product needs from elsewhere (needs.py: lilToon, Modular Avatar and the other tools Hoard knows by GUID) is
offered as the VPM package that provides it, from that tool's own repository.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path

from ..packages import zip_name
from ..safety import safe_join
from . import unitypackage
from .manifest import Package
from .resolve import MAX_MEMBERS, MAX_UNPACKED, ResolveError, _member_path, _rmtree
from .version import Version

MAX_INNER_ZIP = 512 << 20
MAX_ZIP_LISTED = 50_000

# The tools needs.py knows, as VPM packages: (package, its repository, the repository's name)
TOOL_PACKAGES = {
    "liltoon": ("jp.lilxyzw.liltoon", "https://lilxyzw.github.io/vpm-repos/vpm.json", "lilxyzw"),
    "poiyomi": ("com.poiyomi.toon", "https://poiyomi.github.io/vpm/index.json", "Poiyomi's VPM Repo"),
    "modular-avatar": ("nadena.dev.modular-avatar", "https://vpm.nadena.dev/vpm.json", "bd_"),
    "ndmf": ("nadena.dev.ndmf", "https://vpm.nadena.dev/vpm.json", "bd_"),
    "vrcfury": ("com.vrcfury.vrcfury", "https://vcc.vrcfury.com", "VRCFury Repo"),
    "avatar-optimizer": ("com.anatawa12.avatar-optimizer", "https://vpm.anatawa12.com/vpm.json", "anatawa12"),
    "vrchat-sdk": ("com.vrchat.avatars", None, None),   # VRChat's own repository, always there
}


def _package_in_zip(zf: zipfile.ZipFile) -> tuple[str, Package] | None:
    """A VPM package in a zip: (the folder its package.json is in, "" for the top; the package), or None."""
    infos = zf.infolist()[:MAX_ZIP_LISTED]
    names = {i.filename.replace("\\", "/"): i for i in infos}
    tops = {n.split("/")[0] for n in names if n.strip("/")}
    for prefix in [""] + ([next(iter(tops)) + "/"] if len(tops) == 1 else []):
        info = names.get(prefix + "package.json")
        if info is None or info.file_size > (1 << 20) or info.flag_bits & 0x1:
            continue
        try:
            raw = json.loads(zf.read(info).decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, RuntimeError, OSError):
            continue
        p = Package.parse(raw, loose=True)
        if p is not None:
            return prefix, p
    return None


def contents(asset: dict) -> list[dict]:
    """What in a downloaded product (an asset as the Downloads index has it) can go into a project:
    [{"kind": "unitypackage" or "vpm", "file", "member", "label", "package", "version"}]."""
    folder = Path(asset["abs_folder"])
    out = []
    if asset.get("linked") or asset.get("store") == "Local":
        try:
            raw = json.loads((folder / "package.json").read_text("utf-8-sig")) if (folder / "package.json").is_file() else None
        except (OSError, ValueError):
            raw = None
        p = Package.parse(raw, loose=True) if raw else None
        if p is not None:
            return [{"kind": "vpm-folder", "file": "", "member": None, "label": p.label(), "package": p.name,
                     "version": str(p.version)}]
    for f in asset.get("files") or []:
        if f.get("missing"):
            continue
        rel = f["path"]
        path = safe_join(folder, rel)
        if path is None:
            continue
        lower = rel.lower()
        if lower.endswith(".unitypackage"):
            out.append({"kind": "unitypackage", "file": rel, "member": None, "label": Path(rel).name})
        elif lower.endswith(".zip"):
            out += _zip_contents(path, rel)
    return out


def _zip_contents(path: Path, rel: str) -> list[dict]:
    out = []
    try:
        with zipfile.ZipFile(path) as zf:
            found = _package_in_zip(zf)
            if found is not None:
                _prefix, p = found
                return [{"kind": "vpm", "file": rel, "member": None, "label": p.label(), "package": p.name,
                         "version": str(p.version)}]
            for info in zf.infolist()[:MAX_ZIP_LISTED]:
                name = zip_name(info)
                if info.is_dir() or info.flag_bits & 0x1:
                    continue
                if name.lower().endswith(".unitypackage"):
                    out.append({"kind": "unitypackage", "file": rel, "member": info.filename, "label": Path(name).name})
                elif name.lower().endswith(".zip") and info.file_size <= MAX_INNER_ZIP:
                    try:
                        with zipfile.ZipFile(io.BytesIO(zf.read(info))) as inner:
                            found = _package_in_zip(inner)
                    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError):
                        found = None
                    if found is not None:
                        out.append({"kind": "vpm", "file": rel, "member": info.filename, "label": found[1].label(),
                                    "package": found[1].name, "version": str(found[1].version)})
    except (zipfile.BadZipFile, OSError, NotImplementedError, RuntimeError):
        pass
    return out


def _extract(zf: zipfile.ZipFile, prefix: str, dest: Path) -> None:
    infos = [i for i in zf.infolist() if i.filename.replace("\\", "/").startswith(prefix)]
    if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_UNPACKED:
        raise ResolveError("That package is larger than any real one.")
    dest.mkdir(parents=True)
    for i in infos:
        rel = _member_path(i.filename.replace("\\", "/")[len(prefix):])
        if rel is None:
            if i.filename.replace("\\", "/")[len(prefix):].strip("/"):
                raise ResolveError(f"The package has a file named to land outside its folder: {i.filename[:120]}")
            continue
        out = dest.joinpath(*rel.parts)
        if i.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(i) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)


def _install_package(project: Path, source, kind: str, locked: set) -> str:
    """Put a VPM package from the library into Packages/<name>: what happened, in a word."""
    with source() as (zf, prefix, p):
        if p.name in locked:
            return "already-installed"       # installed from a repository: that copy stays
        target = project / "Packages" / p.name
        if target.exists():
            try:
                have = Package.parse(json.loads((target / "package.json").read_text("utf-8-sig")), loose=True)
            except (OSError, ValueError):
                have = None
            if have is not None and have.version >= p.version:
                return "already-there"
        staged = project / "Packages" / f".hoard-{uuid.uuid4().hex}"
        try:
            if kind == "vpm-folder":
                shutil.copytree(prefix, staged, ignore=lambda d, names: [n for n in names if os.path.islink(os.path.join(d, n))])
            else:
                _extract(zf, prefix, staged)
            if target.exists():
                aside = project / "Packages" / f".hoard-old-{uuid.uuid4().hex}"
                os.replace(target, aside)
                os.replace(staged, target)
                _rmtree(aside)
                return "updated"
            os.replace(staged, target)
            return "added"
        finally:
            if staged.exists():
                _rmtree(staged)


class _Source:
    """Opens a VPM package from the library: (the zip or None, the prefix or folder, its package)."""

    def __init__(self, path: Path, member: str | None, kind: str):
        self.path, self.member, self.kind = path, member, kind
        self._open = []

    def __call__(self):
        return self

    def __enter__(self):
        if self.kind == "vpm-folder":
            p = Package.parse(json.loads((self.path / "package.json").read_text("utf-8-sig")), loose=True)
            if p is None:
                raise ResolveError("That folder's package.json isn't a package's.")
            return None, self.path, p
        zf = zipfile.ZipFile(self.path)
        self._open.append(zf)
        if self.member is not None:
            info = zf.getinfo(self.member)
            if info.file_size > MAX_INNER_ZIP:
                raise ResolveError("That package is larger than any real one.")
            zf = zipfile.ZipFile(io.BytesIO(zf.read(info)))
            self._open.append(zf)
        found = _package_in_zip(zf)
        if found is None:
            raise ResolveError(f"{self.path.name} doesn't hold a VPM package any more.")
        return zf, found[0], found[1]

    def __exit__(self, *exc):
        for zf in reversed(self._open):
            zf.close()
        self._open.clear()


def apply(project: Path, picks: list[tuple[dict, dict]], new_project: bool, locked: set | None = None, log=None) -> dict:
    """Put the chosen contents of library products into a project: picks is [(asset, a contents() entry)]. In a
    project that already has things (not new_project), nothing already there is replaced. Returns counts and, for
    each product, what happened."""
    project = Path(project)
    existing = None if new_project else unitypackage.project_guids(project)
    done = {"placed": 0, "already_there": 0, "in_the_way": 0, "packages": [], "failed": [], "each": []}
    for asset, entry in picks:
        folder = Path(asset["abs_folder"])
        label = f"{asset['name']}: {entry.get('label') or entry['file']}"
        one = {"store": asset.get("store"), "name": asset.get("name"), "creator": asset.get("creator"),
               "file": Path(entry.get("member") or entry["file"]).name, "label": entry.get("label") or entry["file"],
               "added": []}   # what this product put in, for the project's list of imports (imports.py)
        done["each"].append(one)
        try:
            if entry["kind"] == "unitypackage":
                path = safe_join(folder, entry["file"])
                if path is None:
                    raise ResolveError("its file isn't in its folder")
                if log:
                    log(f"Putting {label} in the project")
                r = unitypackage.place_file(project, path, entry.get("member"), existing)
                done["placed"] += r.placed
                done["already_there"] += r.skipped_same
                done["in_the_way"] += r.skipped_taken
                one.update(placed=r.placed, already_there=r.skipped_same, in_the_way=r.skipped_taken,
                           added=sorted(set(r.paths)))
            else:
                path = folder if entry["kind"] == "vpm-folder" else safe_join(folder, entry["file"])
                if path is None:
                    raise ResolveError("its file isn't in its folder")
                if log:
                    log(f"Adding the package {label}")
                what = _install_package(project, _Source(path, entry.get("member"), entry["kind"]), entry["kind"],
                                        locked or set())
                done["packages"].append({"name": entry.get("package"), "label": entry.get("label"), "result": what})
                one.update(package=entry.get("package"), result=what,
                           added=[f"Packages/{entry['package']}"] if entry.get("package") and what in ("added", "updated") else [])
        except (OSError, ResolveError, unitypackage.NotAPackage, zipfile.BadZipFile, KeyError, ValueError) as e:
            done["failed"].append({"what": label, "why": str(e) or e.__class__.__name__})
            one["why"] = str(e) or e.__class__.__name__
    return done


def suggested_packages(needs: list[str]) -> list[dict]:
    """The VPM packages for tools a product needs (needs.py's tool keys)."""
    out = []
    for key in needs:
        if key in TOOL_PACKAGES:
            name, repo, repo_name = TOOL_PACKAGES[key]
            out.append({"tool": key, "package": name, "repo": repo, "repo_name": repo_name})
    return out


def newer(a: str, b: str) -> bool:
    va, vb = Version.maybe(a), Version.maybe(b)
    return bool(va and vb and va > vb)
