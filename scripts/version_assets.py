"""Give the website's stylesheets and scripts a version in every page's links (styles.css?v=<its hash>), so a browser
never shows a new page with the stylesheet it kept from before (issue #312: the front page's new video, with last
deploy's styles.css still kept for up to 10 minutes by GitHub Pages' caching, came out at its full 1920 x 1080).

    python3 scripts/version_assets.py SITE_FOLDER

Run on deploy (build-listing.yml), last, once every page is in SITE_FOLDER: each page's links to a .css or .js file of
the site's own (a relative address, with no ? or # in it yet) get the first 10 hex digits of that file's SHA-256. A
link to a file that isn't there is left as it is. Standard library only.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

LINK = re.compile(r'(?P<attr>\b(?:href|src))="(?P<addr>(?![a-z][a-z0-9+.-]*:|/|#)[^"?#]+\.(?:css|js))"', re.I)


def version(site: Path, page: Path, addr: str, known: dict) -> str | None:
    """The version for one of a page's links: its file's hash, when the file is the site's own and there."""
    target = (page.parent / addr).resolve()
    try:
        target.relative_to(site)
    except ValueError:
        return None
    if target not in known:
        known[target] = hashlib.sha256(target.read_bytes()).hexdigest()[:10] if target.is_file() else None
    return known[target]


def stamp(site: Path) -> int:
    """Version every page's links in the site folder. Returns how many links were changed."""
    site, known, changed = site.resolve(), {}, 0
    for page in sorted(site.rglob("*.html")):
        text = page.read_text("utf-8")

        def with_version(m: re.Match) -> str:
            """One link, with its file's version when it has one."""
            nonlocal changed
            v = version(site, page, m["addr"], known)
            if not v:
                return m[0]
            changed += 1
            return f'{m["attr"]}="{m["addr"]}?v={v}"'
        new = LINK.sub(with_version, text)
        if new != text:
            page.write_text(new, "utf-8")
    return changed


def main(argv: list[str]) -> int:
    """Version the links in the folder given."""
    if len(argv) != 1 or not Path(argv[0]).is_dir():
        print(__doc__)
        return 2
    print(f"Versioned {stamp(Path(argv[0]))} links to the site's stylesheets and scripts.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
