"""The Flatpak's AppStream metainfo, checked, with this version's release listed: software centres show the newest
<release> as the version you have, so every build needs this version at the top.

    python scripts/flatpak_metainfo.py --check                 # is the file well-formed, with one <releases>?
    python scripts/flatpak_metainfo.py --out PATH [--date D]   # the file, with __version__ added if it isn't listed

The Flatpak's build (packaging/flatpak/io.github.soloflighter1010.Hoard.yml) runs it with --out, so a release
doesn't need the metainfo edited by hand, and the release workflow runs --check before building anything. A beta (3.0.0-beta.1) is listed as type="development". The release's
summary is the first sentence of its CHANGELOG.md section. The file in the repository is never changed by this.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
METAINFO = REPO / "packaging" / "flatpak" / "io.github.soloflighter1010.Hoard.metainfo.xml"


class Broken(Exception):
    """The metainfo isn't something a software centre can read: what's wrong, and where."""


def version() -> str:
    return re.search(r'__version__ = "([^"]+)"', (REPO / "hoard" / "__init__.py").read_text("utf-8")).group(1)


def check(text: str) -> ET.Element:
    """The parsed metainfo, or Broken saying what's wrong."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise Broken(f"{e}. It isn't well-formed XML: check that every "
                     "tag is closed, and that new <release> entries go inside the one <releases>.") from None
    if root.tag != "component":
        raise Broken("its root should be <component>")
    if len(root.findall("releases")) != 1:
        raise Broken(f"it has {len(root.findall('releases'))} <releases> sections; it needs exactly one")
    for r in root.find("releases"):
        if r.tag != "release" or not r.get("version") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.get("date") or ""):
            raise Broken(f"every entry in <releases> needs to be a <release> with a version and a date (YYYY-MM-DD), "
                         f"not {ET.tostring(r, 'unicode').strip()[:80]}")
    return root


def summary(ver: str) -> str:
    """The first sentence of the version's CHANGELOG.md section, as plain text; or a line saying where the notes are."""
    try:
        text = (REPO / "CHANGELOG.md").read_text("utf-8")
    except OSError:
        text = ""
    m = re.search(rf"^## {re.escape(ver)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    para = ""
    for line in (m.group(1) if m else "").splitlines():
        line = line.strip()
        if not line and para:
            break
        if line and not line.startswith(("#", "-", "*", "<!--")):
            para += " " + line
    para = re.sub(r"\*\*|`|\[([^\]]*)\]\([^)]*\)", lambda x: x.group(1) or "", para).strip()
    first = re.split(r"(?<=[.!?])\s", para, maxsplit=1)[0][:300]
    return first or f"Hoard {ver}: see its release notes on GitHub."


def with_release(text: str, ver: str, date: str) -> str:
    """The metainfo with ver listed first in <releases>, unless it's listed already."""
    root = check(text)
    if any(r.get("version") == ver for r in root.find("releases")):
        return text
    m = re.search(r"^([ \t]*)<releases>[ \t]*\n", text, re.M)
    indent = m.group(1) + "  "
    beta = ' type="development"' if "-" in ver else ""
    entry = (f'{indent}<release version="{html.escape(ver)}" date="{date}"{beta}>\n'
             f"{indent}  <description>\n{indent}    <p>{html.escape(summary(ver), quote=False)}</p>\n"
             f"{indent}  </description>\n{indent}</release>\n")
    out = text[:m.end()] + entry + text[m.end():]
    check(out)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only check the file")
    ap.add_argument("--out", help="write the metainfo, with this version listed, here")
    ap.add_argument("--date", default="", help="the release's date (YYYY-MM-DD); today if left out")
    args = ap.parse_args(argv)
    text = METAINFO.read_text("utf-8")
    try:
        check(text)
        if args.check or not args.out:
            print(f"{METAINFO.relative_to(REPO)} is fine")
            return 0
        epoch = os.environ.get("SOURCE_DATE_EPOCH", "")
        date = args.date or time.strftime("%Y-%m-%d", time.gmtime(int(epoch) if epoch.isdigit() else None))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(with_release(text, version(), date), "utf-8")
        print(f"{out}: Hoard {version()}")
        return 0
    except Broken as e:
        print(f"::error file=packaging/flatpak/{METAINFO.name}::{METAINFO.name}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
