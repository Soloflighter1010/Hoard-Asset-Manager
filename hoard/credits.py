"""Acknowledgements (issue #227): everything Hoard uses or ships, with its license, for Settings and the website.

The list is credits.json, beside this file. Each library's license text is read from its own package's details,
installed with it (the apps copy them in: packaging/hoard.spec), and the fonts' and the Projects templates' from the
files Hoard ships with them. tests/test_credits.py checks that every package the lock files pin is in the list.
"""
from __future__ import annotations

import functools
import json
import re
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent
LICENSE_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE)[^/]*$", re.I)
MAX_TEXT = 200_000


@functools.lru_cache(maxsize=1)
def load() -> dict:
    """credits.json, as it's shipped."""
    return json.loads((HERE / "credits.json").read_text("utf-8"))


def items() -> list[dict]:
    """Every credit, from every group, in order."""
    return [i for g in load()["groups"] for i in g["items"]]


def _shipped_text(rel: str) -> str | None:
    """A license file Hoard ships ("hoard/web/fonts/...", relative to the repository, or to the app's own folder)."""
    for path in (HERE.parent / rel, HERE / rel.removeprefix("hoard/")):
        try:
            if path.is_file():
                return path.read_text("utf-8", errors="replace")[:MAX_TEXT]
        except OSError:
            pass
    return None


def _package_text(package: str) -> str | None:
    """A package's license, from its own details: its license files, or the license its details spell out."""
    try:
        dist = metadata.distribution(package)
    except metadata.PackageNotFoundError:
        return None
    texts = []
    for f in dist.files or []:
        if LICENSE_FILE.search(str(f).replace("\\", "/")) and ".dist-info" in str(f):
            try:
                texts.append(f.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError):
                pass
    if not texts:
        spelled = dist.metadata.get("License") or ""
        if len(spelled) > 200:   # (some put the whole text there, not just its name)
            texts.append(spelled)
    return "\n\n".join(texts)[:MAX_TEXT] or None


def license_text(name: str) -> str | None:
    """The license text of the credit named name, or None where Hoard has none to show (its link has it)."""
    item = next((i for i in items() if i["name"] == name), None)
    if item is None:
        return None
    if item.get("text"):
        return _shipped_text(item["text"])
    return _package_text(item["package"]) if item.get("package") else None


def view() -> dict:
    """For Settings: the groups and their credits, each saying whether its license text can be shown."""
    return {"groups": [{"title": g["title"], "items": [
        {"name": i["name"], "license": i["license"], "url": i["url"], "in": i["in"],
         "text": bool(i.get("text") or i.get("package"))} for i in g["items"]]} for g in load()["groups"]]}
