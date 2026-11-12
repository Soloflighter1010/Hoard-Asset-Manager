"""Make Hoard-update.json: what the Tauri and Nuitka build's window updates from (Tauri's updater's own manifest).

    python scripts/update_manifest.py FOLDER TAG > Hoard-update.json

FOLDER holds each system's part, as .github/workflows/release.yml's "Sign the updates" writes it: one line for
each name Tauri's updater looks a system up by (windows-x86_64, darwin-aarch64, linux-x86_64-deb, ...), with the
release's file for it and that file's signature, tab-separated. The manifest gives each its address on the release
TAG, and the version from hoard/__init__.py. Hoard (hoard/updater.py) chooses the release; its window
(shell/src/main.rs) installs the file for its system only if it matches its signature.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOWNLOADS = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/download/"
SYSTEM = re.compile(r"(windows|darwin|linux)-(x86_64|aarch64)(-(nsis|app|appimage|deb))?")
FILE = re.compile(r"Hoard-[A-Za-z0-9_.+-]+\.(exe|app\.tar\.gz|AppImage|deb)")   # (x86_64: the AppImage's)
TAG = re.compile(r"[A-Za-z0-9._-]+")


def version() -> str:
    """Hoard's version, as hoard/__init__.py has it."""
    text = (REPO / "hoard" / "__init__.py").read_text("utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def manifest(folder: Path, tag: str, when: datetime | None = None) -> dict:
    """The manifest from each system's part; refuses anything that isn't a system, a release file and a signature."""
    if not TAG.fullmatch(tag):
        raise ValueError(f"not a release tag: {tag!r}")
    platforms = {}
    for part in sorted(folder.glob("*.tsv")):
        for line in part.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            system, name, signature = line.split("\t")
            if not SYSTEM.fullmatch(system) or not FILE.fullmatch(name) or not re.fullmatch(r"[A-Za-z0-9+/=]{40,}", signature):
                raise ValueError(f"not a system, a release file and its signature: {line[:120]!r}")
            if system in platforms:
                raise ValueError(f"{system} is listed twice")
            platforms[system] = {"signature": signature, "url": DOWNLOADS + tag + "/" + name}
    if not platforms:
        raise ValueError(f"no system's part in {folder}")
    v = version()
    return {"version": v, "notes": f"Hoard {v}: what's new is on its release page.",
            "pub_date": (when or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"), "platforms": platforms}


def main(argv: list[str]) -> int:
    """Write the manifest to standard output."""
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    print(json.dumps(manifest(Path(argv[0]), argv[1]), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
