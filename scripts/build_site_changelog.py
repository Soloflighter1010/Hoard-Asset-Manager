"""Build the website's changelog timeline (site/changelog.html) from CHANGELOG.md.

Run on deploy by build-listing.yml, so the page always matches the changelog; nothing generated is kept in the
repository. The changelog is turned into HTML by hoard/changelog.py (also What's new in the app), which says what
part of Markdown it uses; betas are told apart by hoard/versions.py.

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
try:   # (run as a script, the repository isn't on the path yet; imported by the tests, it already is)
    from hoard.changelog import blocks, inline, is_beta, releases  # noqa: F401  (shared with What's new in the app)
except ImportError:
    sys.path.insert(0, str(REPO))
    from hoard.changelog import blocks, inline, is_beta, releases  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_chrome import footer, header  # noqa: E402  (the bar and footer every page has)
REPO_URL = "https://github.com/Soloflighter1010/Hoard-Asset-Manager"
VERSION = re.compile(r"\d+\.\d+\.\d+")


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
    for n, (version, lines) in enumerate([r for r in releases(markdown) if not is_beta(r[0])]):
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
    built = ' This page is built from <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/CHANGELOG.md">CHANGELOG.md</a>.'
    return (TEMPLATE.replace("{header}", header("changelog.html")).replace("{footer}", footer(built))
            .replace("{releases}", "\n".join(cards)))


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
  {header}

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

  {footer}
  <script src="site.js" defer></script>
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
