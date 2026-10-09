"""The website's bar and footer, the same on every page (site/*.html, the What's new page and the docs), as the app
has them: the logo, the pages as tabs, GitHub and a gold Download; the mark, the links and the small print.

    python3 scripts/site_chrome.py          checks site/*.html carry them as written here
    python3 scripts/site_chrome.py --write  writes them into site/*.html

A page in a folder (the docs, in docs/) gets the same, its links one folder up. Standard library only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GITHUB = "https://github.com/Soloflighter1010/Hoard-Asset-Manager"
LOGO = """<svg viewBox="0 0 226 64" role="img" aria-label="Hoard, home"><g class="boxes" transform="translate(0 0) scale(1.0)">
  <rect x="5" y="30" width="27" height="27" rx="7" fill="#56D1DC" style="stroke: var(--cave)" stroke-width="3" transform="rotate(-9 18.5 43.5)"/>
  <rect x="31" y="31" width="27" height="27" rx="7" fill="#FF8AD8" style="stroke: var(--cave)" stroke-width="3" transform="rotate(7 44.5 44.5)"/>
  <rect x="17.5" y="8" width="28" height="28" rx="7" fill="#F0B429" style="stroke: var(--cave)" stroke-width="3" transform="rotate(-4 31.5 22)"/>
  <path d="M38 13.5 l1.6 3.9 3.9 1.6 -3.9 1.6 -1.6 3.9 -1.6 -3.9 -3.9 -1.6 3.9 -1.6z" fill="#FFF8E6"/>
</g><g class="word"><path transform="translate(74.00 47.00) scale(0.04400 -0.04400)" d="M430 0Q436 147 436 271Q436 315 414.5 341.0Q393 367 360 367Q325 367 300.5 333.0Q276 299 276 240L275 242Q275 79 279 0H40Q48 144 48 390Q48 636 40 780H278L279 472L278 419Q302 489 349.5 522.5Q397 556 457 556Q517 556 561.0 529.5Q605 503 627.5 458.0Q650 413 650 357V213Q650 80 655 0Z"/><path transform="translate(103.70 47.00) scale(0.04400 -0.04400)" d="M30 275Q30 400 110.5 478.0Q191 556 362 556Q477 556 554.5 518.5Q632 481 669.0 417.5Q706 354 706 275Q706 146 620.5 68.0Q535 -10 362 -10Q191 -10 110.5 68.5Q30 147 30 275ZM495 274Q495 323 463.0 354.5Q431 386 366 386Q301 386 271.0 355.0Q241 324 241 274Q241 222 271.0 191.0Q301 160 366 160Q431 160 463.0 191.0Q495 222 495 274Z"/><path transform="translate(135.20 47.00) scale(0.04400 -0.04400)" d="M681 166Q681 132 689.0 118.0Q697 104 721 98L717 4Q685 -1 661.5 -3.0Q638 -5 599 -5Q513 -5 485.0 33.5Q457 72 457 132V157Q428 75 372.5 35.0Q317 -5 231 -5Q131 -5 80.5 35.0Q30 75 30 154Q30 219 73.0 256.0Q116 293 206 307Q130 361 54 401Q114 477 191.0 516.5Q268 556 378 556Q532 556 606.5 489.5Q681 423 681 285ZM239 312Q299 319 389 319Q426 319 441.0 328.0Q456 337 456 351Q456 363 441.0 371.5Q426 380 399 380Q348 380 309.0 363.0Q270 346 239 312ZM457 236V262Q433 250 404.0 243.5Q375 237 334 231L298 225Q242 214 242 187Q242 158 294 158Q350 158 395.0 179.5Q440 201 457 236Z"/><path transform="translate(166.93 47.00) scale(0.04400 -0.04400)" d="M272 398Q314 549 481 549Q510 549 537 545L505 321Q433 348 387 348Q330 348 303.0 314.0Q276 280 276 223V224L275 158Q275 87 279 0H40Q48 144 48 272Q48 400 40 546Q106 543 141 543Q178 543 242 546Z"/><path transform="translate(191.44 47.00) scale(0.04400 -0.04400)" d="M688 389Q688 188 694 0H468L471 120Q442 53 387.0 21.5Q332 -10 257 -10Q192 -10 140.0 27.0Q88 64 59.0 127.5Q30 191 30 267Q30 342 59.0 408.5Q88 475 140.5 515.5Q193 556 260 556Q338 556 393.5 523.5Q449 491 476 423Q476 480 472 606Q468 728 468 778H694Q688 592 688 389ZM473 273Q473 326 442.0 351.0Q411 376 364 376Q319 376 288.5 347.5Q258 319 258 273Q258 222 286.0 190.0Q314 158 362 158Q411 158 442.0 185.5Q473 213 473 273Z"/></g></svg>"""
MARK = """<svg viewBox="0 0 64 64" aria-hidden="true" width="22" height="22"><g transform="translate(0 0) scale(1.0)">
  <rect x="5" y="30" width="27" height="27" rx="7" fill="#56D1DC" style="stroke: var(--cave)" stroke-width="3" transform="rotate(-9 18.5 43.5)"/>
  <rect x="31" y="31" width="27" height="27" rx="7" fill="#FF8AD8" style="stroke: var(--cave)" stroke-width="3" transform="rotate(7 44.5 44.5)"/>
  <rect x="17.5" y="8" width="28" height="28" rx="7" fill="#F0B429" style="stroke: var(--cave)" stroke-width="3" transform="rotate(-4 31.5 22)"/>
  <path d="M38 13.5 l1.6 3.9 3.9 1.6 -3.9 1.6 -1.6 3.9 -1.6 -3.9 -3.9 -1.6 3.9 -1.6z" fill="#FFF8E6"/>
</g></svg>"""
TABS = [("./", "Home"), ("how-it-works.html", "How it works"), ("trust.html", "Trust"), ("./#unity", "Unity"),
        ("docs/", "Docs"), ("changelog.html", "What's new"), ("testers.html", "Testers")]
FOOT_LINKS = [("docs/", "Docs"), ("how-it-works.html", "How it works"), ("changelog.html", "What's new"),
              ("testers.html", "Testers"), ("credits.html", "Picture credits"), (f"{GITHUB}/issues", "Report a problem"),
              (f"{GITHUB}/blob/main/PRIVACY.md", "Privacy"), ("vcc/", "VCC listing"), ("trust.html", "How you can trust Hoard"),
              ("ai.html", "AI disclosure"), (GITHUB, "GitHub")]
# which tab each page is (the rest are none, or are in docs/)
CURRENT = {"index.html": "./", "how-it-works.html": "how-it-works.html", "trust.html": "trust.html",
           "testers.html": "testers.html", "changelog.html": "changelog.html"}


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
    """A page of site/ with the bar and footer as written here."""
    page, n1 = re.subn(r'<header class="bar">.*?</header>', lambda m: header(CURRENT.get(name)), page, count=1, flags=re.S)
    page, n2 = re.subn(r'<footer class="foot">.*?</footer>', lambda m: footer(), page, count=1, flags=re.S)
    if n1 != 1 or n2 != 1:
        raise ValueError(f"{name}: no bar or footer to replace")
    return page


def main(argv: list[str]) -> int:
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
