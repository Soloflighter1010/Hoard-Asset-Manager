"""The Heap (hoard/heap.py) in every file that carries Hoard's logo as text (issues #277, #280): the app's pages (the
bar's logo, the splashes and the browser tab's icon), the brand files, and the website's mark. The website's bar and
footer take it from scripts/site_chrome.py, the press kit's files from scripts/make_press_kit.py, the social cards
from scripts/make_social_cards.py and the apps' icons from scripts/make_icons.py.

    python3 scripts/heap_files.py           checks each has the Heap as hoard/heap.py draws it (1 when one doesn't)
    python3 scripts/heap_files.py --write   writes it into them

Standard library only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from hoard import heap  # noqa: E402

PAGE_LINE = "stroke: var(--cave)"   # in the app, the boxes' outline is the page's own background
LIGHT, DARK = "#F4EDE3", heap.CAVE   # the words of the logo on dark, and on light


def _group(live: bool) -> str:
    """The heap's boxes as the pages have them (live: the page draws its own heap there once it knows your stores)."""
    return (f'<g class="boxes heap"{" data-live" if live else ""}>\n'
            f'{heap.boxes_svg(heap.FULL, line_style=PAGE_LINE, indent="  ")}\n</g>')


def app_page(text: str, name: str) -> str:
    """One of the app's pages with the Heap: its bar's logo, its splashes, its footer's mark, and its icon in the
    browser's tab. (An empty library draws its own, with your stores: shared.js's heapMarkup.)"""
    text, bars = re.subn(r'(<a class="brand" href="/"><svg viewBox="0 0 226 64" role="img" aria-label="Hoard">)(.*?)(<g class="word">)',
                         lambda m: m[1] + _group(True) + m[3], text, count=1, flags=re.S)
    text, splashes = re.subn(r'(<div id="(splash|pjSplash)" class="splash"[^>]*>\s*<div class="splash-in">\s*'
                             r'<svg viewBox="0 0 64 64" aria-hidden="true">)(.*?)(\s*</svg>)',
                             lambda m: m[1] + "\n" + _group(m[2] == "pjSplash") + m[4], text, flags=re.S)
    text, feet = re.subn(r'(<div class="foot-brand"><svg viewBox="0 0 64 64" aria-hidden="true">)(.*?)(</svg>)',
                         lambda m: m[1] + _group(True) + m[3], text, flags=re.S)
    icon = f'<link rel="icon" href="data:image/svg+xml,{quote(heap.mark())}">'
    text, icons = re.subn(r'<link rel="icon" href="data:image/svg\+xml,[^"]*">', lambda m: icon, text, count=1)
    if bars != 1 or icons != 1 or not splashes or feet > 1:
        raise ValueError(f"{name}: no logo, splash or icon to put the Heap in")
    return text


# the files that are the logo, and what each holds
FILES = {
    "brand/mark.svg": lambda: heap.mark(label="Hoard"),
    "brand/logo-dark.svg": lambda: heap.logo(words=LIGHT),
    "brand/logo-light.svg": lambda: heap.logo(words=DARK),
    "site/img/mark.svg": lambda: heap.mark(label="Hoard"),
}
PAGES = ("hoard/web/library.html", "hoard/web/downloads.html")


def wanted() -> dict[str, str]:
    """Every file, as it should be."""
    out = {name: make() for name, make in FILES.items()}
    for name in PAGES:
        out[name] = app_page((REPO / name).read_text("utf-8"), name)
    return out


def main(argv: list[str]) -> int:
    """Check the files have the Heap, or write it into them with --write."""
    wrong = []
    for name, text in wanted().items():
        p = REPO / name
        if not p.exists() or p.read_text("utf-8") != text:
            if "--write" in argv:
                p.write_text(text, "utf-8")
            else:
                wrong.append(name)
    if wrong:
        print("Not the Heap as hoard/heap.py draws it: " + ", ".join(wrong) + ". Run python3 scripts/heap_files.py --write.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
