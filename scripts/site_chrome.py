"""The website's bar and footer, the same on every page (site/*.html, the What's new page and the docs), as the app
has them: the logo, the pages as tabs, GitHub and a gold Download; the mark, the links and the small print.

    python3 scripts/site_chrome.py          checks site/*.html carry them as written here
    python3 scripts/site_chrome.py --write  writes them into site/*.html

A page in a folder (the docs, in docs/) gets the same, its links one folder up. Every page also asks for the
site's fonts with its stylesheet (preloads). Standard library only (and hoard/heap.py, which is too).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GITHUB = "https://github.com/Soloflighter1010/Hoard-Asset-Manager"
sys.path.insert(0, str(REPO))
from hoard import heap  # noqa: E402   (the Heap, Hoard's logo: issue #280)

LOGO = ('<svg viewBox="0 0 226 64" role="img" aria-label="Hoard, home"><g class="boxes heap">\n'
        f'{heap.boxes_svg(heap.FULL, line_style="stroke: var(--cave)", indent="  ")}\n</g><g class="word">{heap.word()}</g></svg>')
MARK = ('<svg viewBox="0 0 64 64" aria-hidden="true" width="22" height="22"><g class="boxes heap">\n'
        f'{heap.boxes_svg(heap.FULL, line_style="stroke: var(--cave)", indent="  ")}\n</g></svg>')
DISCORD = "https://discord.gg/psNsAGj75Q"   # Hoard's Discord server (issue #204)
COMPARE = "docs/Hoard-and-Other-Tools.html"   # Hoard with the Creator Companion, ALCOM and KonoAsset (issue #293)
TABS = [("./", "Home"), ("how-it-works.html", "How it works"), (COMPARE, "Compare"), ("trust.html", "Trust"), ("./#unity", "Unity"),
        ("docs/", "Docs"), ("changelog.html", "What's new"), ("testers.html", "Testers")]
FOOT_LINKS = [("docs/", "Docs"), ("how-it-works.html", "How it works"), (COMPARE, "Hoard and other tools"), ("changelog.html", "What's new"),
              ("testers.html", "Testers"), ("credits.html", "Picture credits"), (f"{GITHUB}/issues", "Report a problem"),
              (f"{GITHUB}/blob/main/PRIVACY.md", "Privacy"), (f"{GITHUB}/blob/main/TERMS.md", "Terms"),
              ("vcc/", "VCC listing"), ("trust.html", "How you can trust Hoard"),
              ("stores.html", "For stores"),
              ("ai.html", "AI disclosure"), ("acknowledgements.html", "Acknowledgements"), ("press.html", "Press kit"),
              (DISCORD, "Discord"), (GITHUB, "GitHub")]
# which tab each page is (the rest are none, or are in docs/)
CURRENT = {"index.html": "./", "how-it-works.html": "how-it-works.html", "trust.html": "trust.html",
           "testers.html": "testers.html", "changelog.html": "changelog.html"}


# The fonts every page uses, asked for with the page instead of once its stylesheet has arrived (Lighthouse, on a
# phone: the page, then styles.css, then each font, 0.7 s before any text could show in them).
FONTS = ("DelaGothicOne-Regular", "ZenMaruGothic-Medium", "ZenMaruGothic-Bold")


def preloads(up: str = "") -> str:
    """The <link rel="preload"> lines for the fonts, for a page that many folders down (up: "" or "../")."""
    return "".join(f'  <link rel="preload" href="{up}fonts/{f}.woff2" as="font" type="font/woff2" crossorigin>\n'
                   for f in FONTS)


def _href(h: str, up: str) -> str:
    """A link on the site, from a page that many folders down (up: "" or "../")."""
    if not up or re.match(r"https?:", h):
        return h
    return up + (h[2:] if h.startswith("./") else h)


def header(current: str | None = None, up: str = "") -> str:
    """The bar, with the tab for the page you're on marked (current: its href in TABS)."""
    mark = ' aria-current="page"'
    tabs = "\n".join(f'      <a href="{_href(h, up)}"{mark if h == current else ""}>{t}</a>' for h, t in TABS)
    return f"""<header class="bar">
    <a class="brand" href="{_href('./', up)}">{LOGO}</a>
    <nav class="apptabs" aria-label="Site">
{tabs}
    </nav>
    <div class="bar-tools">
      <a class="ghost" href="{GITHUB}">GitHub</a>
      <a class="primary" href="{_href('./#download', up)}">Download</a>
    </div>
  </header>"""


def footer(extra: str = "", up: str = "") -> str:
    """The footer; extra: a sentence of the page's own (where it's built from), in the small print."""
    links = "\n".join(f'      <a href="{_href(h, up)}">{t}</a>' for h, t in FOOT_LINKS)
    return f"""<footer class="foot">
    <div class="foot-brand">{MARK}<span>Hoard</span></div>
    <nav class="foot-links" aria-label="About Hoard">
{links}
    </nav>
    <p class="foot-note">Free and open source under the MIT license. Made by <a href="https://x.com/SoloFlighter101" rel="noopener">@SoloFlighter101</a>.{extra}
      Not affiliated with VRChat, Booth, Gumroad, Jinxxy, Payhip or itch.io.</p>
  </footer>"""


def apply(page: str, name: str) -> str:
    """A page of site/ with the bar, footer and font preloads as written here."""
    page, n1 = re.subn(r'<header class="bar">.*?</header>', lambda m: header(CURRENT.get(name)), page, count=1, flags=re.S)
    page, n2 = re.subn(r'<footer class="foot">.*?</footer>', lambda m: footer(), page, count=1, flags=re.S)
    page, n3 = re.subn(r'(?:  <link rel="preload" href="[^"]*" as="font"[^>]*>\n)*(  <link rel="stylesheet" href="styles\.css">)',
                       lambda m: preloads() + m.group(1), page, count=1)
    if n1 != 1 or n2 != 1 or n3 != 1:
        raise ValueError(f"{name}: no bar, footer or stylesheet to place them by")
    return page


def main(argv: list[str]) -> int:
    """Check every page's bar and footer are the site's, or write them with --write. 1 when any isn't."""
    wrong = []
    for p in sorted((REPO / "site").glob("*.html")):
        text = p.read_text("utf-8")
        new = apply(text, p.name)
        if new != text:
            if "--write" in argv:
                p.write_text(new, "utf-8")
            else:
                wrong.append(p.name)
    if wrong:
        print("Not the site's bar and footer: " + ", ".join(wrong) + ". Run python3 scripts/site_chrome.py --write.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
