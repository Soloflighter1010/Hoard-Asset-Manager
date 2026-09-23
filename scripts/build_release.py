#!/usr/bin/env python3
"""
Build the release zips into dist/.

    python scripts/build_release.py              build from the working tree
    python scripts/build_release.py --tag v1.0.0 also check the tag matches both tools' versions

Only the files listed below go into a zip, so personal data (config.json, sign-ins, downloads,
library.json) can never end up in a release even if it's sitting in the folder.
"""
from __future__ import annotations

import argparse
import hashlib
import py_compile
import re
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
TOOLS = {
    "HoardDownloader": {
        "version_file": "asset_dl.py",
        "files": ["asset_dl.py", "asset_browser.py", "browser.html", "config.example.json", "requirements.txt",
                  "README.md", "Setup.bat", "Hoard Downloader.bat", "setup.sh", "run.sh"],
    },
    "Hoard": {
        "version_file": "library.py",
        "files": ["library.py", "library.html", "config.example.json", "requirements.txt",
                  "README.md", "Setup.bat", "Hoard.bat", "setup.sh", "run.sh"],
    },
}
BUNDLE = "Hoard-Bundle"
# Shipped with each tool so users have the license, terms and policies alongside the program.
DOCS = ("LICENSE", "TERMS.md", "PRIVACY.md", "COPYRIGHT.md", "SECURITY.md", "AI-DISCLOSURE.md")
# The pages' typefaces and their licenses, so the tools look right offline. Each tool's zip gets a copy in
# its own fonts/ folder; the bundle keeps one shared copy, which both tools find one folder up.
FONTS = ("DelaGothicOne-Regular.woff2", "ZenMaruGothic-Medium.woff2", "ZenMaruGothic-Bold.woff2",
         "DelaGothicOne-OFL.txt", "ZenMaruGothic-OFL.txt", "README.md")


def version_of(path: Path) -> str:
    """The __version__ string in a tool's main file."""
    m = re.search(r'^__version__ = "([^"]+)"', path.read_text("utf-8"), re.M)
    if not m:
        sys.exit(f"No __version__ in {path}")
    return m.group(1)


def add(zf: zipfile.ZipFile, src: Path, arcname: str) -> None:
    """Add a file to a zip with a fixed date and the right permissions, so identical input gives an identical zip."""
    info = zipfile.ZipInfo(arcname, date_time=(2026, 1, 1, 0, 0, 0))  # stable zips for identical input
    info.compress_type = zipfile.ZIP_STORED if src.suffix == ".woff2" else zipfile.ZIP_DEFLATED
    info.external_attr = (0o755 if src.suffix == ".sh" else 0o644) << 16
    zf.writestr(info, src.read_bytes())


def release_notes(version: str) -> str:
    """The CHANGELOG.md section for version, used as the release's notes."""
    text = (REPO / "CHANGELOG.md").read_text("utf-8")
    m = re.search(rf"^## {re.escape(version)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        sys.exit(f"CHANGELOG.md has no '## {version}' section")
    return m.group(1).strip() + "\n"


def main() -> None:
    """Check the versions, compile the Python and build the zips, release notes and checksums in dist/."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", help="release tag, e.g. v1.0.0")
    args = ap.parse_args()

    versions = {name: version_of(REPO / name / t["version_file"]) for name, t in TOOLS.items()}
    if len(set(versions.values())) != 1:
        sys.exit(f"Tool versions differ: {versions}")
    version = next(iter(versions.values()))
    if args.tag and args.tag.lstrip("v") != version:
        sys.exit(f"Tag {args.tag} doesn't match version {version}")

    scratch = Path(tempfile.mkdtemp())
    for doc in DOCS:
        if not (REPO / doc).exists():
            sys.exit(f"Missing {doc}")
    for font in FONTS:
        if not (REPO / "fonts" / font).exists():
            sys.exit(f"Missing fonts/{font}")
    for name, t in TOOLS.items():
        for f in t["files"]:
            path = REPO / name / f
            if not path.exists():
                sys.exit(f"Missing {path}")
            if path.suffix == ".py":
                py_compile.compile(str(path), doraise=True, cfile=str(scratch / f"{name}-{f}c"))
            if path.suffix == ".bat" and b"\r\n" not in path.read_bytes():
                sys.exit(f"{path} needs Windows (CRLF) line endings")

    DIST.mkdir(exist_ok=True)
    built = []
    for name, t in TOOLS.items():
        out = DIST / f"{name}-{version}.zip"
        with zipfile.ZipFile(out, "w") as zf:
            for f in t["files"]:
                add(zf, REPO / name / f, f"{name}/{f}")
            for doc in DOCS:
                add(zf, REPO / doc, f"{name}/{doc}")
            for font in FONTS:
                add(zf, REPO / "fonts" / font, f"{name}/fonts/{font}")
        built.append(out)
    out = DIST / f"{BUNDLE}-{version}.zip"
    with zipfile.ZipFile(out, "w") as zf:
        for name, t in TOOLS.items():
            for f in t["files"]:
                add(zf, REPO / name / f, f"{BUNDLE}/{name}/{f}")
        for f in ("README.md", "CHANGELOG.md", *DOCS):
            add(zf, REPO / f, f"{BUNDLE}/{f}")
        for font in FONTS:
            add(zf, REPO / "fonts" / font, f"{BUNDLE}/fonts/{font}")
    built.append(out)

    (DIST / "RELEASE_NOTES.md").write_text(release_notes(version), "utf-8")
    sums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in built)
    (DIST / "SHA256SUMS.txt").write_text(sums, "utf-8")
    for p in built:
        print(f"{p.relative_to(REPO)}  ({p.stat().st_size // 1024} KB)")
    print(f"Version {version}. Release notes and checksums are in dist/.")


if __name__ == "__main__":
    main()
