"""Build the release: python scripts/build_release.py [--tag vX.Y.Z]

Writes dist/Hoard-<version>.zip (Hoard to run from any folder), dist/RELEASE_NOTES.md (that version's
changelog section) and dist/SHA256SUMS.txt. Only the files listed here go into the zip, so nothing personal
can slip in. The same input always gives a byte-identical zip.
"""
from __future__ import annotations

import argparse
import hashlib
import py_compile
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
NAME = "Hoard"
# Next to the program: launchers, the locked requirements, and the documents people should have with it.
TOP_FILES = ("Hoard.bat", "Setup.bat", "run.sh", "setup.sh", "requirements.txt", "README.md", "CHANGELOG.md",
             "LICENSE", "TERMS.md", "PRIVACY.md", "COPYRIGHT.md", "SECURITY.md", "AI-DISCLOSURE.md")
# The program: every Python module, both pages and the bundled fonts with their licenses.
PACKAGE_PATTERNS = ("hoard/*.py", "hoard/web/*.html", "hoard/web/fonts/*.woff2", "hoard/web/fonts/*.txt",
                    "hoard/web/fonts/README.md")


def version() -> str:
    """The version in hoard/__init__.py."""
    m = re.search(r'__version__ = "([^"]+)"', (REPO / "hoard" / "__init__.py").read_text("utf-8"))
    if not m:
        sys.exit("No __version__ in hoard/__init__.py")
    return m.group(1)


def add(zf: zipfile.ZipFile, src: Path, arcname: str) -> None:
    """Add a file to a zip with a fixed date and the right permissions, so identical input gives an identical zip."""
    info = zipfile.ZipInfo(arcname, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED if src.suffix == ".woff2" else zipfile.ZIP_DEFLATED
    info.external_attr = (0o755 if src.suffix == ".sh" else 0o644) << 16
    zf.writestr(info, src.read_bytes())


def release_notes(ver: str) -> str:
    """The CHANGELOG.md section for ver, used as the release's notes."""
    text = (REPO / "CHANGELOG.md").read_text("utf-8")
    m = re.search(rf"^## {re.escape(ver)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        sys.exit(f"CHANGELOG.md has no '## {ver}' section")
    return m.group(1).strip() + "\n"


def main() -> None:
    """Check the version, compile the Python, and build the zip, release notes and checksums in dist/."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", help="the git tag being released; must match the version")
    args = ap.parse_args()
    ver = version()
    if args.tag and args.tag.lstrip("v") != ver:
        sys.exit(f"Tag {args.tag} doesn't match version {ver}")
    files = [REPO / f for f in TOP_FILES]
    files += sorted({p for pattern in PACKAGE_PATTERNS for p in REPO.glob(pattern)})
    for f in files:
        if not f.is_file():
            sys.exit(f"Missing {f.relative_to(REPO)}")
        if f.suffix == ".py":
            py_compile.compile(str(f), doraise=True)
        if f.suffix == ".bat" and b"\r\n" not in f.read_bytes():
            sys.exit(f"{f.name} needs Windows (CRLF) line endings")
    notes = release_notes(ver)
    DIST.mkdir(exist_ok=True)
    out = DIST / f"{NAME}-{ver}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            add(zf, f, f"{NAME}/{f.relative_to(REPO).as_posix()}")
    (DIST / "RELEASE_NOTES.md").write_text(notes, "utf-8")
    sums = [f"{hashlib.sha256(out.read_bytes()).hexdigest()}  {out.name}"]
    (DIST / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", "utf-8")
    print(f"{out.relative_to(REPO)}  ({out.stat().st_size // 1024} KB, {len(files)} files)")
    print(f"Version {ver}. Release notes and checksums are in dist/.")


if __name__ == "__main__":
    main()
