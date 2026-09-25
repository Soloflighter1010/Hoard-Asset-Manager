"""Build the Unity package's release files: python scripts/build_vpm.py [--tag unity-vX.Y.Z]

Writes into dist/vpm/, as VRChat's template-package release does: soloflighter.hoard-<version>.zip (for VCC,
package.json at its root), soloflighter.hoard-<version>.unitypackage (for projects without VCC), package.json and
RELEASE_NOTES.md. The VCC listing itself is built from the releases by VRChat's package-list-action
(.github/workflows/build-listing.yml). The same files always build the same zip and .unitypackage.

    --write-metas   create any missing .meta files (GUIDs come from each file's path, so they never change)
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from build_release import build_date  # noqa: E402

PACKAGE = REPO / "Packages" / "soloflighter.hoard"
DIST = REPO / "dist" / "vpm"
LISTING_URL = json.loads((REPO / "source.json").read_text("utf-8"))["url"]
ALLOWED = {".cs", ".asmdef", ".json", ".md", ".meta"}

META = {
    "folder": "folderAsset: yes\nDefaultImporter:\n",
    ".cs": "MonoImporter:\n  externalObjects: {}\n  serializedVersion: 2\n  defaultReferences: []\n  executionOrder: 0\n  icon: {instanceID: 0}\n",
    ".asmdef": "AssemblyDefinitionImporter:\n  externalObjects: {}\n",
    "package.json": "PackageManifestImporter:\n  externalObjects: {}\n",
    ".json": "TextScriptImporter:\n  externalObjects: {}\n",
    ".md": "TextScriptImporter:\n  externalObjects: {}\n",
}


def meta_guid(path: Path) -> str:
    """A fixed GUID for a file or folder in the package, from its path: it never changes between releases."""
    return hashlib.md5(("soloflighter.hoard/" + path.relative_to(PACKAGE).as_posix()).encode()).hexdigest()


def meta_text(path: Path) -> str:
    kind = "folder" if path.is_dir() else ("package.json" if path.name == "package.json" else path.suffix)
    body = META[kind]
    if not body.startswith("folderAsset") and "userData" not in body:
        body += "  userData: \n  assetBundleName: \n  assetBundleVariant: \n"
    elif body.startswith("folderAsset"):
        body += "  externalObjects: {}\n  userData: \n  assetBundleName: \n  assetBundleVariant: \n"
    return f"fileFormatVersion: 2\nguid: {meta_guid(path)}\n{body}"


def contents() -> list[Path]:
    """Every file and folder in the package except .meta files, in a fixed order."""
    return sorted(p for p in PACKAGE.rglob("*") if p.suffix != ".meta")


def check(write_metas: bool) -> dict:
    """Check the package is complete and plain; returns its package.json."""
    problems = []
    manifest = json.loads((PACKAGE / "package.json").read_text("utf-8"))
    if manifest.get("name") != PACKAGE.name:
        problems.append(f"package.json name should be {PACKAGE.name}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
        problems.append("package.json version should be like 1.2.3")
    for field in ("displayName", "unity", "description", "author"):
        if not manifest.get(field):
            problems.append(f"package.json needs {field}")
    guids = {}
    for p in contents():
        if p.is_file() and p.suffix not in ALLOWED:
            problems.append(f"{p.relative_to(PACKAGE)} isn't a kind of file this package ships")
        meta = p.with_name(p.name + ".meta")
        if not meta.exists():
            if write_metas:
                meta.write_text(meta_text(p), "utf-8")
            else:
                problems.append(f"{p.relative_to(PACKAGE)} has no .meta file (run with --write-metas)")
                continue
        guid = re.search(r"^guid: ([0-9a-f]{32})$", meta.read_text("utf-8"), re.M)
        if not guid:
            problems.append(f"{meta.relative_to(PACKAGE)} has no GUID")
        elif guid.group(1) in guids:
            problems.append(f"{meta.relative_to(PACKAGE)} repeats the GUID of {guids[guid.group(1)]}")
        else:
            guids[guid.group(1)] = meta.relative_to(PACKAGE)
    for meta in PACKAGE.rglob("*.meta"):
        if not meta.with_name(meta.name[:-5]).exists():
            problems.append(f"{meta.relative_to(PACKAGE)} belongs to nothing")
    if problems:
        sys.exit("The package isn't ready:\n  " + "\n  ".join(problems))
    return manifest


def build_zip(version: str, date: tuple) -> Path:
    """The package for VCC: its folder's contents, package.json at the zip's root."""
    out = DIST / f"soloflighter.hoard-{version}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(PACKAGE.rglob("*")):
            if p.is_file():
                info = zipfile.ZipInfo(p.relative_to(PACKAGE).as_posix(), date_time=date)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, p.read_bytes())
    return out


def build_unitypackage(version: str, date: tuple) -> Path:
    """The package as a .unitypackage, for projects without VCC: a gzipped tar with a folder per asset, named by its
    GUID, holding "asset" (files only), "asset.meta" and "pathname" (where it goes: Packages/soloflighter.hoard/...)."""
    out = DIST / f"soloflighter.hoard-{version}.unitypackage"
    mtime = int(time.mktime(date + (0, 0, -1)))
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        def add(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode, info.uid, info.gid = len(data), mtime, 0o644, 0, 0
            tar.addfile(info, io.BytesIO(data))
        for p in contents():
            meta = p.with_name(p.name + ".meta").read_bytes()
            guid = re.search(rb"^guid: ([0-9a-f]{32})$", meta, re.M).group(1).decode()
            if p.is_file():
                add(f"{guid}/asset", p.read_bytes())
            add(f"{guid}/asset.meta", meta)
            add(f"{guid}/pathname", f"Packages/{PACKAGE.name}/{p.relative_to(PACKAGE).as_posix()}".encode("utf-8"))
    with open(out, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=mtime, filename="") as gz:
        gz.write(raw.getvalue())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", help="the git tag being released (unity-vX.Y.Z); must match package.json")
    ap.add_argument("--write-metas", action="store_true")
    args = ap.parse_args()
    manifest = check(args.write_metas)
    version = manifest["version"]
    if args.tag and args.tag != f"unity-v{version}":
        sys.exit(f"Tag {args.tag} doesn't match package.json version {version} (expected unity-v{version})")
    DIST.mkdir(parents=True, exist_ok=True)
    date = build_date(p for p in PACKAGE.rglob("*") if p.is_file())
    built = [build_zip(version, date), build_unitypackage(version, date)]
    (DIST / "package.json").write_bytes((PACKAGE / "package.json").read_bytes())
    (DIST / "RELEASE_NOTES.md").write_text(release_notes(version), "utf-8")
    for f in built:
        print(f"{f.relative_to(REPO)}  ({f.stat().st_size // 1024} KB)  sha256 {hashlib.sha256(f.read_bytes()).hexdigest()[:16]}...")


def release_notes(version: str) -> str:
    text = (PACKAGE / "CHANGELOG.md").read_text("utf-8")
    m = re.search(rf"^## {re.escape(version)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        sys.exit(f"Packages/soloflighter.hoard/CHANGELOG.md has no '## {version}' section")
    return (m.group(1).strip() + f"\n\n**Add it to VCC:** {LISTING_URL} (or use the Add to VCC button on "
            f"{LISTING_URL.rsplit('/', 1)[0]}/).\nWithout VCC: import the .unitypackage below into your project.\n")


if __name__ == "__main__":
    main()
