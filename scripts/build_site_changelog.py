"""Build the website's changelog timeline (site/changelog.html) from CHANGELOG.md.

Run on deploy by build-listing.yml, so the page always matches the changelog; nothing generated is kept in the
repository. CHANGELOG.md uses a small part of Markdown: "## <version>" for each release, "### " for a heading inside
one, paragraphs, "- " lists (nested by two spaces, with continuation lines indented), **bold**, `code` and
[links](https://...). Everything is escaped first, so nothing in the changelog becomes markup of its own.

    python3 scripts/build_site_changelog.py OUT.html [--dates DATES.json]

DATES.json, if given, maps release tags to when they were published ({"v2.11.1": "2026-10-01T...", ...}), as
`gh release list --json tagName,publishedAt` gives them; releases not in it are shown without a date.
Standard library only.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/Soloflighter1010/Hoard-Asset-Manager"
VERSION = re.compile(r"\d+\.\d+\.\d+")


def inline(text: str) -> str:
    """One line of changelog text as HTML: escaped, with `code`, **bold** (around code too), [links](https://...)
    and bare https addresses as links, as GitHub shows them."""
    if text.count("`") % 2:   # an unmatched backtick: leave the line's backticks as they are
        parts = [text]
    else:
        parts = text.split("`")
    codes = [f"<code>{html.escape(p)}</code>" for p in parts[1::2]]
    # Code is set aside (as \x00n\x00, which can't be in the text) while the rest is escaped and marked up.
    rest = "".join(html.escape(p.replace("\x00", ""), quote=True) + (f"\x00{n}\x00" if n < len(codes) else "")
                   for n, p in enumerate(parts[0::2]))
    rest = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rest)
    rest = re.sub(r"\[([^\]]+)\]\((https://[^)\s\"<>\x00]+)\)", r'<a href="\2">\1</a>', rest)
    rest = re.sub(r'(?<![="\w>])(https://[^\s<>"\x00]*[^\s<>"\x00.,;:!?)])', r'<a href="\1">\1</a>', rest)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], rest)


def blocks(lines: list[str]) -> str:
    """A release's lines as HTML: paragraphs, headings and nested lists."""
    out: list[str] = []
    para: list[str] = []
    stack: list[int] = []        # the indent of each open list
    item: list[str] | None = None  # the text of the list item being read

    def flush_para():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    def flush_item():
        nonlocal item
        if item is not None:
            out.append(inline(" ".join(item)))
            item = None

    def close_lists(to: int = -1):
        flush_item()
        while stack and stack[-1] > to:
            stack.pop()
            out.append("</li></ul>")

    for raw in lines:
        line = raw.rstrip()
        bullet = re.match(r"^( *)- (.*)$", line)
        if not line.strip():
            flush_para()
            continue
        if bullet:
            flush_para()
            indent, text = len(bullet.group(1)), bullet.group(2)
            if stack and indent > stack[-1]:      # a list inside the item being read
                flush_item()
                out.append("<ul>")
                stack.append(indent)
            else:
                close_lists(indent)
                if stack and stack[-1] == indent:
                    out.append("</li>")
                else:
                    out.append("<ul>")
                    stack.append(indent)
            out.append("<li>")
            item = [text.strip()]
            continue
        if item is not None and line.startswith(" "):   # an item's next line
            item.append(line.strip())
            continue
        close_lists()
        heading = re.match(r"^#{3,6} (.*)$", line)
        if heading:
            flush_para()
            out.append(f"<h4>{inline(heading.group(1).strip())}</h4>")
        else:
            para.append(line.strip())
    flush_para()
    close_lists()
    return "\n".join(out)


def releases(markdown: str) -> list[tuple[str, list[str]]]:
    """(version, its lines) for each "## " section, newest first, as the changelog lists them."""
    found, current = [], None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = (line[3:].strip(), [])
            found.append(current)
        elif current:
            current[1].append(line)
    return found


def when(stamp: str | None) -> tuple[str, str] | None:
    """(ISO date, "October 1, 2026") from a published-at timestamp, or None."""
    try:
        d = date.fromisoformat(str(stamp)[:10])
    except ValueError:
        return None
    return d.isoformat(), f"{d.strftime('%B')} {d.day}, {d.year}"


def page(markdown: str, dates: dict[str, str]) -> str:
    cards = []
    # A beta's notes (## 3.1.0-beta.1) are for testers, on its GitHub release: What's new shows releases only
    for n, (version, lines) in enumerate([r for r in releases(markdown) if "-beta." not in r[0]]):
        plain = VERSION.fullmatch(version)
        anchor = "v" + re.sub(r"[^0-9A-Za-z]+", "-", version).strip("-")
        dated = when(dates.get(f"v{version}")) if plain else None
        stamp = f'<time datetime="{dated[0]}">{dated[1]}</time>' if dated else ""
        badge = '<span class="latest-badge">Latest</span>' if n == 0 else ""
        link = (f'<a class="small" href="{REPO_URL}/releases/tag/v{html.escape(version)}">Release on GitHub</a>'
                if plain else "")
        cards.append(f"""      <li class="release" id="{anchor}">
        <article>
          <header><h2><a href="#{anchor}">{html.escape(version)}</a></h2>{badge}{stamp}</header>
{blocks(lines)}
          {link}
        </article>
      </li>""")
    return TEMPLATE.replace("{releases}", "\n".join(cards))


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>What's new in Hoard</title>
  <meta name="description" content="Every Hoard release, newest first: what changed, what was fixed, and when.">
  <meta property="og:site_name" content="Hoard">
  <meta property="og:title" content="What's new in Hoard">
  <meta property="og:description" content="Every Hoard release, newest first: what changed, what was fixed, and when.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://soloflighter1010.github.io/Hoard-Asset-Manager/changelog.html">
  <meta property="og:image" content="https://soloflighter1010.github.io/Hoard-Asset-Manager/img/social.jpg">
  <meta property="og:image:type" content="image/jpeg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Hoard's library: VRChat assets from Booth, Gumroad and Payhip as tiles, with tags and creators beside them">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="theme-color" content="#211C18">
  <meta name="color-scheme" content="dark light">
  <link rel="icon" href="favicon.ico">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div class="glow" aria-hidden="true"><div class="glow-in"></div></div>
  <a class="skip" href="#main">Skip to the page</a>
  <header class="bar">
    <a class="brand" href="./"><img src="img/mark.svg" alt="" width="32" height="32"><span>hoard</span></a>
    <nav aria-label="Site">
      <a href="./#features">What it does</a>
      <a href="how-it-works.html">How it works</a>
      <a href="trust.html">Trust</a>
      <a href="./#download">Download</a>
      <a href="changelog.html" aria-current="page">What's new</a>
      <a href="testers.html">Testers</a>
      <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/wiki">Help</a>
      <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager">GitHub</a>
    </nav>
  </header>

  <main id="main">
    <section class="page-head">
      <h1>What's new</h1>
      <p class="lede">Every release of Hoard, newest first. The same notes come with each
        <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases">release on GitHub</a>.</p>
    </section>
    <ol class="timeline">
{releases}
    </ol>
  </main>

  <footer class="foot">
    <p><img src="img/mark.svg" alt="" width="20" height="20"> Hoard is free and open source under the MIT license.</p>
    <p class="small">Built from <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/CHANGELOG.md">CHANGELOG.md</a>.</p>
    <p><a href="./">Home</a> · <a href="trust.html">How you can trust Hoard</a> · <a href="ai.html">AI disclosure</a></p>
  </footer>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print("usage: build_site_changelog.py OUT.html [--dates DATES.json]", file=sys.stderr)
        return 2
    dates: dict[str, str] = {}
    if "--dates" in argv:
        raw = json.loads(Path(argv[argv.index("--dates") + 1]).read_text("utf-8") or "[]")
        rows = raw if isinstance(raw, list) else [{"tagName": k, "publishedAt": v} for k, v in raw.items()]
        dates = {r["tagName"]: r["publishedAt"] for r in rows if isinstance(r, dict) and r.get("publishedAt")}
    Path(argv[0]).write_text(page((REPO / "CHANGELOG.md").read_text("utf-8"), dates), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
