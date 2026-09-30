"""Write packaging/flatpak/python3-deps.json: the Flatpak's Python packages, as flatpak-builder sources.

A Flatpak is built without network access, so every file it installs is listed in the manifest with where to get
it and its SHA-256. This reads the exact versions and hashes locked in requirements-flatpak.txt, asks PyPI where
each file is, and picks one per package: a wheel for Linux x86_64 and CPython 3.12 (the GNOME runtime's), a wheel
for any platform, or the source. Only files whose hash is in the lock file are used.

    python scripts/flatpak_deps.py            (after regenerating requirements-flatpak.txt; see its .in file)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "requirements-flatpak.txt"
OUT = REPO / "packaging" / "flatpak" / "python3-deps.json"
PYTHON = "cp312"


def locked(text: str) -> dict[str, tuple[str, set[str]]]:
    """name -> (version, allowed sha256 hashes), from a pip-compile style lock file."""
    out: dict[str, tuple[str, set[str]]] = {}
    for block in re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text):
        m = re.match(r"([A-Za-z0-9_.-]+)==([^\s\\;]+)", block)
        if m:
            out[m.group(1).lower()] = (m.group(2), set(re.findall(r"--hash=sha256:([0-9a-f]{64})", block)))
    return out


def rank(filename: str) -> int | None:
    """How good a file is for the Flatpak (lower is better), or None when it can't be used there."""
    if filename.endswith((".tar.gz", ".zip")):
        return 3                                   # the source: built by pip in the SDK
    if not filename.endswith(".whl"):
        return None
    _name, *_rest, py, abi, plat = filename[:-4].split("-")
    if plat == "any":
        return 1 if py.startswith("py3") or py == "py2.py3" else None
    if "x86_64" not in plat or not ("manylinux" in plat):
        return None
    if PYTHON in py.split(".") or abi == "abi3" or py.startswith("py3"):
        return 0
    return None


def choose(name: str, version: str, hashes: set[str]) -> dict:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as r:
        files = json.load(r)["urls"]
    usable = [(rank(f["filename"]), f) for f in files if f["digests"]["sha256"] in hashes]
    usable = [(n, f) for n, f in usable if n is not None]
    if not usable:
        sys.exit(f"{name} {version}: no file for Linux x86_64 / {PYTHON} whose hash is in {LOCK.name}")
    best = min(usable, key=lambda t: t[0])[1]
    return {"type": "file", "url": best["url"], "sha256": best["digests"]["sha256"]}


def main() -> None:
    deps = locked(LOCK.read_text("utf-8"))
    sources = [choose(name, version, hashes) for name, (version, hashes) in sorted(deps.items())]
    module = {
        "name": "python3-deps",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --verbose --exists-action=i --no-index --find-links=\"file://${PWD}\" "
            "--prefix=${FLATPAK_DEST} --no-build-isolation " + " ".join(sorted(deps)),
        ],
        "sources": sources,
    }
    OUT.write_text(json.dumps(module, indent=2) + "\n", "utf-8")
    print(f"Wrote {OUT.relative_to(REPO)}: {len(sources)} packages")


if __name__ == "__main__":
    main()
