"""The press kit's logos (site/press.html): Hoard's logo and its mark, as the website's bar draws them, made into
files of their own, each colour written out (the site's take them from its stylesheet), for dark backgrounds and
for light ones, as SVG and as PNG with a see-through background.

    python3 scripts/make_press_kit.py      writes site/img/press/hoard-*.svg and .png

Run it after the logo changes (scripts/site_chrome.py has it); the files are kept in the repository. The press kit's
download, with these and the screenshots, is made when the site is built (scripts/build_press_kit.py). Needs
Playwright (as the tests do) for the PNGs.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_chrome import LOGO, MARK, REPO  # noqa: E402

OUT = REPO / "site" / "img" / "press"
DARK, LIGHT = "#211C18", "#F4EDE3"   # the site's cave and bone: its background and its words, in the dark theme
# name: (the SVG, the outline round its boxes (the background it's on), the word's colour, width of its PNG)
LOGOS = {
    "hoard-logo-on-dark": (LOGO, DARK, LIGHT, 1800),
    "hoard-logo-on-light": (LOGO, "#FFFFFF", DARK, 1800),
    "hoard-mark": (MARK, DARK, None, 1024),
}


def standalone(svg: str, outline: str, word: str | None) -> str:
    """The logo as a file of its own: the outline and the word's colour written in, and no label or size of the
    page's."""
    svg = svg.replace('style="stroke: var(--cave)"', f'stroke="{outline}"')
    svg = svg.replace('<g class="word">', f'<g fill="{word}">') if word else svg
    svg = re.sub(r"<svg [^>]*>", lambda m: re.sub(r' (?:role|aria-label|aria-hidden|width|height)="[^"]*"', "", m[0]),
                 svg, count=1)   # (the page's label and size: the <svg> tag's own, not its boxes')
    svg = re.sub(r'<g class="boxes"', "<g", svg)
    return svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1) + "\n"


def main() -> int:
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for name, (svg, outline, word, width) in LOGOS.items():
            text = standalone(svg, outline, word)
            (OUT / f"{name}.svg").write_text(text, "utf-8")
            box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text)
            height = round(width * float(box[2]) / float(box[1]))
            page.set_viewport_size({"width": width, "height": height})
            page.set_content(f'<body style="margin:0;background:transparent">'
                             f'{text.replace("<svg ", f"<svg width={width} height={height} ", 1)}</body>')
            page.locator("svg").screenshot(path=str(OUT / f"{name}.png"), omit_background=True)
            print(f"{name}: {width} × {height}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
