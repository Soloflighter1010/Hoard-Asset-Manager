"""Build the Unity package for VCC: python scripts/build_vpm.py [--tag unity-vX.Y.Z] [--listing old-index.json]

Writes dist/vpm/soloflighter.hoard-<version>.zip (the package, package.json at its root), dist/vpm/index.json
(the VCC listing, keeping every earlier version from --listing) and dist/vpm/index.html (a page with an
"Add to VCC" button). The same commit always builds the same zip.

    --write-metas   create any missing .meta files (GUIDs come from each file's path, so they never change)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from build_release import build_date  # noqa: E402

PACKAGE = REPO / "unity" / "soloflighter.hoard"
DIST = REPO / "dist" / "vpm"
GITHUB = "Soloflighter1010/Hoard-Asset-Manager"
LISTING_URL = "https://soloflighter1010.github.io/Hoard-Asset-Manager/vpm/index.json"
LISTING = {"name": "SoloFlighter", "id": "soloflighter.vpm", "author": "SoloFlighter", "url": LISTING_URL}
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


def build_zip(version: str) -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / f"soloflighter.hoard-{version}.zip"
    date = build_date(p for p in PACKAGE.rglob("*") if p.is_file())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(PACKAGE.rglob("*")):
            if p.is_file():
                info = zipfile.ZipInfo(p.relative_to(PACKAGE).as_posix(), date_time=date)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, p.read_bytes())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", help="the git tag being released (unity-vX.Y.Z); must match package.json")
    ap.add_argument("--listing", type=Path, help="the current VCC listing (index.json), so earlier versions are kept")
    ap.add_argument("--write-metas", action="store_true")
    args = ap.parse_args()
    manifest = check(args.write_metas)
    version = manifest["version"]
    if args.tag and args.tag != f"unity-v{version}":
        sys.exit(f"Tag {args.tag} doesn't match package.json version {version} (expected unity-v{version})")
    zipped = build_zip(version)
    sha = hashlib.sha256(zipped.read_bytes()).hexdigest()
    listing = json.loads(args.listing.read_text("utf-8")) if args.listing and args.listing.exists() else {}
    listing = {**LISTING, "packages": listing.get("packages") or {}}
    versions = listing["packages"].setdefault(manifest["name"], {}).setdefault("versions", {})
    old = versions.get(version)
    if old and old.get("zipSHA256") != sha:
        sys.exit(f"Version {version} is already published with different contents. Raise the version in package.json.")
    versions[version] = {**manifest, "url": f"https://github.com/{GITHUB}/releases/download/unity-v{version}/{zipped.name}",
                         "zipSHA256": sha}
    (DIST / "index.json").write_text(json.dumps(listing, indent=2, ensure_ascii=False) + "\n", "utf-8")
    (DIST / "index.html").write_text(PAGE.replace("{LISTING_URL}", LISTING_URL), "utf-8")
    (DIST / "RELEASE_NOTES.md").write_text(release_notes(version), "utf-8")
    print(f"{zipped.relative_to(REPO)}  ({zipped.stat().st_size // 1024} KB)  sha256 {sha[:16]}...")
    print(f"Listing: {len(versions)} version(s) of {manifest['name']} in dist/vpm/index.json")


def release_notes(version: str) -> str:
    text = (PACKAGE / "CHANGELOG.md").read_text("utf-8")
    m = re.search(rf"^## {re.escape(version)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        sys.exit(f"unity/soloflighter.hoard/CHANGELOG.md has no '## {version}' section")
    return m.group(1).strip() + f"\n\nAdd it to VCC: {LISTING_URL}\n"


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SoloFlighter's VRChat packages</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 20px;background:#221c17;color:#f2e9dc}
a.button{display:inline-block;padding:10px 18px;border-radius:10px;background:#f0b429;color:#221c17;font-weight:700;text-decoration:none}
code{background:#3a3029;padding:2px 6px;border-radius:5px;word-break:break-all}</style></head>
<body><h1>SoloFlighter's VRChat packages</h1>
<p><strong>Hoard for Unity</strong>: the VRChat assets you've downloaded with Hoard, inside Unity.</p>
<p><a class="button" href="vcc://vpm/addRepo?url={LISTING_URL}">Add to VCC</a></p>
<p>Or, in the VRChat Creator Companion: <em>Settings</em>, then <em>Packages</em>, then <em>Add Repository</em>, and paste:<br>
<code>{LISTING_URL}</code></p>
</body></html>
"""

if __name__ == "__main__":
    main()
