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
    <a class="brand" href="./"><svg viewBox="0 0 226 64" role="img" aria-label="Hoard, home"><g class="boxes" transform="translate(0 0) scale(1.0)">
  <rect x="5" y="30" width="27" height="27" rx="7" fill="#56D1DC" style="stroke: var(--cave)" stroke-width="3" transform="rotate(-9 18.5 43.5)"/>
  <rect x="31" y="31" width="27" height="27" rx="7" fill="#FF8AD8" style="stroke: var(--cave)" stroke-width="3" transform="rotate(7 44.5 44.5)"/>
  <rect x="17.5" y="8" width="28" height="28" rx="7" fill="#F0B429" style="stroke: var(--cave)" stroke-width="3" transform="rotate(-4 31.5 22)"/>
  <path d="M38 13.5 l1.6 3.9 3.9 1.6 -3.9 1.6 -1.6 3.9 -1.6 -3.9 -3.9 -1.6 3.9 -1.6z" fill="#FFF8E6"/>
</g><g class="word"><path transform="translate(74.00 47.00) scale(0.04400 -0.04400)" d="M430 0Q436 147 436 271Q436 315 414.5 341.0Q393 367 360 367Q325 367 300.5 333.0Q276 299 276 240L275 242Q275 79 279 0H40Q48 144 48 390Q48 636 40 780H278L279 472L278 419Q302 489 349.5 522.5Q397 556 457 556Q517 556 561.0 529.5Q605 503 627.5 458.0Q650 413 650 357V213Q650 80 655 0Z"/><path transform="translate(103.70 47.00) scale(0.04400 -0.04400)" d="M30 275Q30 400 110.5 478.0Q191 556 362 556Q477 556 554.5 518.5Q632 481 669.0 417.5Q706 354 706 275Q706 146 620.5 68.0Q535 -10 362 -10Q191 -10 110.5 68.5Q30 147 30 275ZM495 274Q495 323 463.0 354.5Q431 386 366 386Q301 386 271.0 355.0Q241 324 241 274Q241 222 271.0 191.0Q301 160 366 160Q431 160 463.0 191.0Q495 222 495 274Z"/><path transform="translate(135.20 47.00) scale(0.04400 -0.04400)" d="M681 166Q681 132 689.0 118.0Q697 104 721 98L717 4Q685 -1 661.5 -3.0Q638 -5 599 -5Q513 -5 485.0 33.5Q457 72 457 132V157Q428 75 372.5 35.0Q317 -5 231 -5Q131 -5 80.5 35.0Q30 75 30 154Q30 219 73.0 256.0Q116 293 206 307Q130 361 54 401Q114 477 191.0 516.5Q268 556 378 556Q532 556 606.5 489.5Q681 423 681 285ZM239 312Q299 319 389 319Q426 319 441.0 328.0Q456 337 456 351Q456 363 441.0 371.5Q426 380 399 380Q348 380 309.0 363.0Q270 346 239 312ZM457 236V262Q433 250 404.0 243.5Q375 237 334 231L298 225Q242 214 242 187Q242 158 294 158Q350 158 395.0 179.5Q440 201 457 236Z"/><path transform="translate(166.93 47.00) scale(0.04400 -0.04400)" d="M272 398Q314 549 481 549Q510 549 537 545L505 321Q433 348 387 348Q330 348 303.0 314.0Q276 280 276 223V224L275 158Q275 87 279 0H40Q48 144 48 272Q48 400 40 546Q106 543 141 543Q178 543 242 546Z"/><path transform="translate(191.44 47.00) scale(0.04400 -0.04400)" d="M688 389Q688 188 694 0H468L471 120Q442 53 387.0 21.5Q332 -10 257 -10Q192 -10 140.0 27.0Q88 64 59.0 127.5Q30 191 30 267Q30 342 59.0 408.5Q88 475 140.5 515.5Q193 556 260 556Q338 556 393.5 523.5Q449 491 476 423Q476 480 472 606Q468 728 468 778H694Q688 592 688 389ZM473 273Q473 326 442.0 351.0Q411 376 364 376Q319 376 288.5 347.5Q258 319 258 273Q258 222 286.0 190.0Q314 158 362 158Q411 158 442.0 185.5Q473 213 473 273Z"/></g></svg></a>
    <nav class="apptabs" aria-label="Site">
      <a href="./">Home</a>
      <a href="how-it-works.html">How it works</a>
      <a href="trust.html">Trust</a>
      <a href="./#unity">Unity</a>
      <a href="changelog.html" aria-current="page">What's new</a>
      <a href="testers.html">Testers</a>
    </nav>
    <div class="bar-tools">
      <a class="ghost" href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/wiki">Help</a>
      <a class="ghost" href="https://github.com/Soloflighter1010/Hoard-Asset-Manager">GitHub</a>
      <a class="primary" href="./#download">Download</a>
    </div>
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
    <div class="foot-brand"><svg viewBox="0 0 64 64" aria-hidden="true" width="22" height="22"><g transform="translate(0 0) scale(1.0)">
  <rect x="5" y="30" width="27" height="27" rx="7" fill="#56D1DC" style="stroke: var(--cave)" stroke-width="3" transform="rotate(-9 18.5 43.5)"/>
  <rect x="31" y="31" width="27" height="27" rx="7" fill="#FF8AD8" style="stroke: var(--cave)" stroke-width="3" transform="rotate(7 44.5 44.5)"/>
  <rect x="17.5" y="8" width="28" height="28" rx="7" fill="#F0B429" style="stroke: var(--cave)" stroke-width="3" transform="rotate(-4 31.5 22)"/>
  <path d="M38 13.5 l1.6 3.9 3.9 1.6 -3.9 1.6 -1.6 3.9 -1.6 -3.9 -3.9 -1.6 3.9 -1.6z" fill="#FFF8E6"/>
</g></svg><span>Hoard</span></div>
    <nav class="foot-links" aria-label="About Hoard">
      <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/wiki">Help</a>
      <a href="how-it-works.html">How it works</a>
      <a href="changelog.html">What's new</a>
      <a href="testers.html">Testers</a>
      <a href="credits.html">Picture credits</a>
      <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues">Report a problem</a>
      <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/PRIVACY.md">Privacy</a>
      <a href="vcc/">VCC listing</a>
      <a href="trust.html">How you can trust Hoard</a>
      <a href="ai.html">AI disclosure</a>
      <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager">GitHub</a>
    </nav>
    <p class="foot-note">Free and open source under the MIT license. Made by <a href="https://x.com/SoloFlighter101" rel="noopener">@SoloFlighter101</a>. This page is built from <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/CHANGELOG.md">CHANGELOG.md</a>.
      Not affiliated with VRChat, Booth, Gumroad, Jinxxy, Payhip or itch.io.</p>
  </footer>
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
