"""Hoard's Gumroad page (soloflighter.gumroad.com/l/hoardvrc): the website's front page, as one file Gumroad can serve.

    python3 scripts/build_gumroad_page.py      builds gumroad/landing.html from gumroad/landing.src.html

The page is the front page's own pieces, taken from site/ each time: its stylesheet (the sections the front page
uses, its fonts inlined), the logo, the 11 tiles, the 11 screenshots of the tour, Hoard for Unity and the footer. The
template holds what's the Gumroad page's own: its bar, the hero, What is Hoard? (the product's cover, as the video
can't be served from there), Get Hoard with Gumroad's buy buttons, and Safe by design. So run it again after changing
the front page, and the Gumroad page follows.

Gumroad serves a page whole, from one file, sandboxed: so the screenshots go in as data addresses, made smaller here
(site/img's 1200-wide copies, shrunk and saved again), each twice, for dark and light (a data address can't go in a
srcset: its comma splits it). It checks what Gumroad will refuse: more than 500,000 characters, more than 25 pictures,
or a data address in a srcset. Then, with the Gumroad CLI (github.com/antiwork/gumroad-cli):

    gumroad products page preview knkwuq gumroad/landing.html --json --no-input --non-interactive
    gumroad products page publish knkwuq gumroad/landing.html --json --no-input --non-interactive

The preview runs Gumroad's own sanitizer without publishing; its sanitization_report should be empty. Needs Pillow
(promo/requirements.txt).
"""
from __future__ import annotations

import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
SRC = REPO / "gumroad" / "landing.src.html"
OUT = REPO / "gumroad" / "landing.html"
BASE = "https://hoard.furryup.link/"

LIMIT_CHARS = 500_000   # Gumroad's cap on a page
LIMIT_IMAGES = 25       # the most pictures Gumroad reviews on a page

# The hero's screenshot, and the tour's: (width, WebP quality). Small enough that all of them fit Gumroad's cap.
HERO = (780, 48)
TOUR = (500, 38)

# The stylesheet's sections that style other pages than the front, left out (each starts with this comment)
OTHER_PAGES = (
    "/* Pages other than the front", "/* Testers", "/* Picture credits", "/* What's new", "/* How it works",
    "/* How you can trust", "/* Acknowledgements", "/* ---------- the docs", "/* On a phone, a docs table",
    "/* For stores", "/* On a phone, each store", "/* Not found", "/* Save for Hoard", "/* The set viewer",
    "/* a photo with", "/* the products as tiles", "/* An Adult set", "/* Make a set here", "/* What Hoard does that",
    "/* Press kit",
)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def screenshot(name: str, theme: str, size: tuple[int, int]) -> str:
    """A screenshot from site/img, shrunk to its width here and saved again as WebP: its data address's base64."""
    width, quality = size
    im = Image.open(SITE / "img" / f"{name}-{theme}-1200.webp").convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=6)
    return b64(buf.getvalue())


def absolute(html: str) -> str:
    """The site's links, made absolute, each opening in a new tab: the page is on Gumroad, not the site."""
    def fix(m: re.Match) -> str:
        tag, href = m.group(0), m.group(1)
        if href.startswith("#"):
            return tag
        if not re.match(r"[a-z]+:", href):
            tag = tag.replace(f'href="{href}"', f'href="{BASE}{href.removeprefix("./")}"')
        if "target=" not in tag:
            tag = tag[:-1] + ' target="_blank" rel="noopener">'
        return tag
    return re.sub(r'<a\b[^>]*\bhref="([^"]*)"[^>]*>', fix, html)


def stylesheet() -> str:
    """site/styles.css: the sections the front page uses, its fonts inlined, without comments or indents."""
    lines = (SITE / "styles.css").read_text(encoding="utf-8").split("\n")
    starts = [i for i, line in enumerate(lines) if line.startswith("/* ")]
    skip = {i for i in starts if lines[i].startswith(OTHER_PAGES)}
    missing = [t for t in OTHER_PAGES if not any(lines[i].startswith(t) for i in starts)]
    if missing:
        sys.exit(f"styles.css has no section starting {missing[0]!r} any more: update OTHER_PAGES")
    kept = lines[:starts[0]]
    for n, i in enumerate(starts):
        if i not in skip:
            kept += lines[i:starts[n + 1] if n + 1 < len(starts) else len(lines)]
    css = "\n".join(kept)
    for font in re.findall(r"url\(fonts/([\w-]+\.woff2)\)", css):
        css = css.replace(f"url(fonts/{font})", f"url(data:font/woff2;base64,{b64((SITE / 'fonts' / font).read_bytes())})")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = re.sub(r"\s*\n\s*", "\n", css)
    css = re.sub(r"[ \t]{2,}", " ", css)
    if re.search(r"url\((?!data:)", css):
        sys.exit("styles.css points at a file the Gumroad page can't serve: " + re.search(r"url\((?!data:)[^)]*", css)[0])
    return css


def piece(index: str, pattern: str, name: str) -> str:
    m = re.search(pattern, index, re.DOTALL)
    if not m:
        sys.exit(f"site/index.html: couldn't find {name}")
    return m.group(1)


def main() -> None:
    index = (SITE / "index.html").read_text(encoding="utf-8")
    page = SRC.read_text(encoding="utf-8")

    def tour_shot(m: re.Match) -> str:
        name, alt = m.group(1), m.group(2)
        return "".join(
            f'<img class="{theme}-shot" src="data:image/webp;base64,{screenshot(name, theme, TOUR)}" '
            f'width="{TOUR[0]}" height="{round(TOUR[0] * 950 / 1600)}" loading="lazy" alt="{alt}">'
            for theme in ("dark", "light"))

    gallery = piece(index, r'(<div class="gallery">.*?</div>)\s*<p class="small">Products shown', "the tour's gallery")
    gallery = re.sub(r'<picture>\s*<source srcset="img/([\w-]+)-light-800\.webp[^>]*>\s*<img [^>]*alt="([^"]*)">\s*</picture>',
                     tour_shot, gallery)
    if "img/" in gallery:
        sys.exit("site/index.html: a screenshot in the tour isn't a <picture> this understands")

    pieces = {
        "CSS": stylesheet(),
        "BRAND_SVG": piece(index, r'<a class="brand" href="\./">(.*?)</a>', "the logo"),
        "TILES": piece(index, r'(<div class="tiles">.*?</div>\s*)<p class="small langs">', "the tiles"),
        "GALLERY": gallery,
        "UNITY": absolute(piece(index, r'(<section id="unity".*?</section>)', "Hoard for Unity")),
        "FOOTER": absolute(piece(index, r'(<footer class="foot">.*?</footer>)', "the footer")),
    }
    for key, value in pieces.items():
        page = page.replace("{{" + key + "}}", value)
    page = re.sub(r"\{\{IMG_([\w-]+)-(dark|light)\}\}", lambda m: screenshot(m.group(1), m.group(2), HERO), page)
    left = re.findall(r"\{\{\w+\}\}", page)
    if left:
        sys.exit(f"gumroad/landing.src.html: nothing fills {left[0]}")

    # What Gumroad refuses
    images = len(re.findall(r"<img\b", page))
    problems = []
    if len(page) > LIMIT_CHARS:
        problems.append(f"{len(page):,} characters, over Gumroad's {LIMIT_CHARS:,}: make HERO or TOUR smaller")
    if images > LIMIT_IMAGES:
        problems.append(f"{images} pictures, over the {LIMIT_IMAGES} Gumroad reviews")
    if re.search(r'srcset="data:', page):
        problems.append("a data address in a srcset, which Gumroad can't review")
    if problems:
        sys.exit("gumroad/landing.html wasn't written:\n  " + "\n  ".join(problems))

    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT.relative_to(REPO)}: {len(page):,} characters (of {LIMIT_CHARS:,}), {images} pictures (of {LIMIT_IMAGES})")


if __name__ == "__main__":
    main()
