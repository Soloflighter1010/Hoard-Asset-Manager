"""The Save for Hoard bookmark's page on the website (site/save-for-hoard.html): the bookmark itself, a link to
drag to the bookmarks bar, made from the same code as in Hoard (PAYHIP_SAVER in hoard/web/library.html), so the two
can't drift apart. It's on the website because a link can't be dragged out of Hoard's own window into another
browser: Hoard opens this page in the person's usual browser instead.

    python3 scripts/save_for_hoard.py          checks the page carries Hoard's bookmark as it is
    python3 scripts/save_for_hoard.py --write  writes it into the page

Standard library only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "hoard" / "web" / "library.html"
PAGE = REPO / "site" / "save-for-hoard.html"
LINK = re.compile(r'(<a class="bookmarklet" id="saver" href=")([^"]*)(")')


def bookmark() -> str:
    """The bookmark's address, as Hoard makes it: "javascript:void " and the code, as encodeURIComponent writes it."""
    app = APP.read_text("utf-8")
    code = app.split("const PAYHIP_SAVER = String.raw`", 1)[1].split("`;", 1)[0]
    return "javascript:void " + quote(code, safe="-_.!~*'()")


def main(argv: list[str]) -> int:
    page = PAGE.read_text("utf-8")
    if len(LINK.findall(page)) != 1:
        print(f"{PAGE.name}: no bookmark link (<a class=\"bookmarklet\" id=\"saver\" href=...>) to fill")
        return 1
    new = LINK.sub(lambda m: m.group(1) + bookmark() + m.group(3), page)
    if new != page:
        if "--write" in argv:
            PAGE.write_text(new, "utf-8")
            return 0
        print(f"{PAGE.name} doesn't carry Hoard's Save for Hoard bookmark as it is now. Run python3 scripts/save_for_hoard.py --write.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
