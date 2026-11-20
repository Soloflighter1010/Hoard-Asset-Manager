"""The website's bookmark pages, each with the bookmark itself as a link to drag to the bookmarks bar, made from the
same code as in Hoard, so the two can't drift apart:

    site/save-for-hoard.html   Save for Hoard, for Payhip (PAYHIP_SAVER in hoard/web/library.js)
    site/send-to-hoard.html    Send to Hoard, the page you're on to Hoard as a hoard:// link (SEND_TO_HOARD in
                               hoard/web/shared.js, issue #413)

They're on the website because a link can't be dragged out of Hoard's own window into another browser: Hoard opens
these pages in the person's usual browser instead.

    python3 scripts/save_for_hoard.py          checks each page carries Hoard's bookmark as it is
    python3 scripts/save_for_hoard.py --write  writes them into the pages

Standard library only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parent.parent
WEB, SITE = REPO / "hoard" / "web", REPO / "site"
# (the page, the link's id in it, the script the code is in, the code's name there)
BOOKMARKS = (("save-for-hoard.html", "saver", "library.js", "PAYHIP_SAVER"),
             ("send-to-hoard.html", "sender", "shared.js", "SEND_TO_HOARD"))
APP, PAGE = WEB / "library.js", SITE / "save-for-hoard.html"   # (Save for Hoard's, as before)


def bookmark(script: str = "library.js", name: str = "PAYHIP_SAVER") -> str:
    """A bookmark's address, as Hoard makes it: "javascript:void " and the code, as encodeURIComponent writes it."""
    app = (WEB / script).read_text("utf-8")
    code = app.split(f"const {name} = String.raw`", 1)[1].split("`;", 1)[0]
    return "javascript:void " + quote(code, safe="-_.!~*'()")


def link(link_id: str) -> re.Pattern:
    """A page's bookmark link."""
    return re.compile(r'(<a class="bookmarklet" id="' + link_id + r'" href=")([^"]*)(")')


def main(argv: list[str]) -> int:
    """Fill each bookmark page's link from the bookmark's source: every page is checked for its link first, so --write
    writes all of them or none."""
    filled = []
    for page_name, link_id, script, name in BOOKMARKS:
        page_file = SITE / page_name
        page, found = page_file.read_text("utf-8"), link(link_id)
        if len(found.findall(page)) != 1:
            print(f"{page_name}: no bookmark link (<a class=\"bookmarklet\" id=\"{link_id}\" href=...>) to fill")
            return 1
        filled.append((page_file, page, found.sub(lambda m: m.group(1) + bookmark(script, name) + m.group(3), page)))
    stale = [page_file for page_file, page, new in filled if new != page]
    if stale and "--write" in argv:
        for page_file, page, new in filled:
            if new != page:
                page_file.write_text(new, "utf-8")
        return 0
    if stale:
        names = ", ".join(f.name for f in stale)
        print(f"{names} {'doesn' if len(stale) == 1 else 'don'}'t carry Hoard's bookmark as it is now. "
              "Run python3 scripts/save_for_hoard.py --write.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
