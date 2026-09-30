"""Write packaging/flatpak/python3-deps.json: the Flatpak's Python packages, as flatpak-builder sources.

A Flatpak is built without network access, so every file it installs is listed in the manifest with where to get
it and its SHA-256. This reads the exact versions and hashes locked in requirements-flatpak.txt, asks PyPI where
each file is, and picks them: a wheel for any platform, or the source, when there is one; otherwise a Linux x86_64
wheel for each of PYTHONS, so the build doesn't depend on which of them the GNOME runtime has (pip installs the one
that matches). Only files whose hash is in the lock file are used.

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
PYTHONS = ("cp312", "cp313", "cp314")   # the GNOME runtime's Python is one of these


def locked(text: str) -> dict[str, tuple[str, set[str]]]:
    """name -> (version, allowed sha256 hashes), from a pip-compile style lock file."""
    out: dict[str, tuple[str, set[str]]] = {}
    for block in re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text):
        m = re.match(r"([A-Za-z0-9_.-]+)==([^\s\\;]+)", block)
        if m:
            out[m.group(1).lower()] = (m.group(2), set(re.findall(r"--hash=sha256:([0-9a-f]{64})", block)))
    return out


def python_of(filename: str) -> str | None:
    """Which of PYTHONS a Linux x86_64 wheel is for ("abi3": all of them), or None when it's for none of them."""
    if not filename.endswith(".whl"):
        return None
    _name, *_rest, py, abi, plat = filename[:-4].split("-")
    if "x86_64" not in plat or "manylinux" not in plat:
        return None
    if abi == "abi3":
        return "abi3"
    return next((c for c in PYTHONS if c in py.split(".") and abi == c), None)   # (not cp314t, free-threaded)


def rank(filename: str) -> int | None:
    """How good a file is for the Flatpak (lower is better), or None when it can't be used there."""
    if filename.endswith((".tar.gz", ".zip")):
        return 3                                   # the source: built by pip in the SDK
    if not filename.endswith(".whl"):
        return None
    _name, *_rest, py, abi, plat = filename[:-4].split("-")
    if plat == "any":
        return 1 if py.startswith("py3") or py == "py2.py3" else None
    if "x86_64" not in plat or "manylinux" not in plat:
        return None
    if py.startswith("py3") and abi == "none":
        return 0                                   # pure Python, but only published per platform (Playwright)
    return 0 if python_of(filename) else None


def pick(name: str, files: list[dict]) -> list[dict]:
    """The files to list for one package (PyPI's file entries, already limited to the locked hashes)."""
    usable = sorted(((rank(f["filename"]), f["filename"], f) for f in files if rank(f["filename"]) is not None),
                    key=lambda t: t[:2])
    if not usable:
        sys.exit(f"{name}: no file for Linux x86_64 whose hash is in {LOCK.name}")
    compiled = {}
    for _n, filename, f in usable:
        py = python_of(filename)
        if py and not filename.split("-")[-3].startswith("py3"):
            compiled.setdefault(py, f)
    if not compiled:
        return [usable[0][2]]                      # one file does for every Python
    if "abi3" in compiled:
        return [compiled["abi3"]]
    missing = [c for c in PYTHONS if c not in compiled]
    if missing:
        sys.exit(f"{name}: no Linux x86_64 wheel for {', '.join(missing)} whose hash is in {LOCK.name}")
    return [compiled[c] for c in PYTHONS]


def choose(name: str, version: str, hashes: set[str]) -> list[dict]:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as r:
        files = [f for f in json.load(r)["urls"] if f["digests"]["sha256"] in hashes]
    return [{"type": "file", "url": f["url"], "sha256": f["digests"]["sha256"]} for f in pick(name, files)]


def main() -> None:
    deps = locked(LOCK.read_text("utf-8"))
    sources = [s for name, (version, hashes) in sorted(deps.items()) for s in choose(name, version, hashes)]
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
    print(f"Wrote {OUT.relative_to(REPO)}: {len(deps)} packages, {len(sources)} files")


if __name__ == "__main__":
    main()
