"""The press kit's download (press.html, "Download the press kit"): a zip of Hoard's logos (site/img/press/, from
scripts/make_press_kit.py), every screenshot the site shows, full size, in dark and light, and the page's words (what
Hoard is, the facts, what it does, who to ask) as text.

    python3 scripts/build_press_kit.py SITE_FOLDER     writes SITE_FOLDER/press/hoard-press-kit.zip

Run on deploy by build-listing.yml, after the site is copied: nothing generated is kept in the repository, so the
zip always has the screenshots and words the site has. Standard library only.
"""
from __future__ import annotations

import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
SECTIONS = ("about", "facts", "features", "contact")   # press.html's sections that are words, in this order
SHOT = re.compile(r"[a-z-]+-(?:dark|light)\.webp")       # a screenshot, full size (not its -800 or -1200 copies)


class Words(HTMLParser):
    """The text of press.html's word sections: headings, paragraphs, the facts as "Name: value", and list items."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.inside, self.depth, self.line = None, 0, ""

    def handle_starttag(self, tag, attrs):
        """Note when a word section starts, and a new line at each block in it."""
        if tag == "section" and dict(attrs).get("id") in SECTIONS:
            self.inside, self.depth = dict(attrs)["id"], 0
        if not self.inside:
            return
        if tag == "section":
            self.depth += 1
        if tag in ("h2", "h3", "p", "dt", "li"):
            self.end()
        if tag == "dd":
            self.line += ": "

    def handle_endtag(self, tag):
        """End the line at the end of a block, underlining headings."""
        if not self.inside:
            return
        if tag in ("h2", "h3", "p", "dd", "li"):
            self.end(underline="=" if tag == "h2" else "")
        if tag == "section":
            self.depth -= 1
            if not self.depth:
                self.end()
                self.lines.append("")
                self.inside = None

    def handle_data(self, data):
        """Add text inside a word section to the line."""
        if self.inside:
            self.line += data

    def end(self, underline: str = "") -> None:
        """Finish the line being read (with an underline under a heading)."""
        text = " ".join(self.line.split())
        if text:
            self.lines.append(text)
            if underline:
                self.lines.append(underline * len(text))
        self.line = ""


def about_text(page: str) -> str:
    """The press kit's about.txt, from press.html's word sections."""
    words = Words()
    words.feed(page)
    return "Hoard press kit\nhttps://hoard.furryup.link/press.html\n\n" + "\n".join(words.lines).strip() + "\n"


def build(out_site: Path) -> Path:
    """The zip, in out_site/press/: logos/, screenshots/ and About Hoard.txt."""
    zipped = out_site / "press" / "hoard-press-kit.zip"
    zipped.parent.mkdir(parents=True, exist_ok=True)
    shots = sorted(p for p in (SITE / "img").glob("*.webp") if SHOT.fullmatch(p.name))
    logos = sorted((SITE / "img" / "press").glob("hoard-*.*"))
    if not shots or not logos:
        raise SystemExit("No screenshots or logos to put in the press kit")
    with zipfile.ZipFile(zipped, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("hoard-press-kit/About Hoard.txt", about_text((SITE / "press.html").read_text("utf-8")))
        for p in logos:
            z.write(p, f"hoard-press-kit/logos/{p.name}")
        for p in shots:   # (webp is already small: kept as it is)
            z.write(p, f"hoard-press-kit/screenshots/{p.name}", compress_type=zipfile.ZIP_STORED)
    return zipped


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(build(Path(sys.argv[1])))
