"""The website's Acknowledgements page (site/acknowledgements.html), from hoard/credits.json, the list the app shows in
Settings (issue #227): everything Hoard uses or ships, with its license, by where it's used.

    python3 scripts/build_acknowledgements.py          checks the page says what credits.json does
    python3 scripts/build_acknowledgements.py --write  writes it again

The page's bar and footer are the site's (scripts/site_chrome.py). Standard library only.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_chrome  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "site" / "acknowledgements.html"
WHERE = {"all": "Every copy of Hoard", "windows": "The Windows app", "mac": "The Mac app", "linux": "The Flatpak",
         "build": "Only to build the apps"}
DESCRIPTION = "Everything Hoard uses or ships, from the browser it drives to the fonts it shows, with each one's license."


def where(value: str) -> str:
    """Where a credit is used, in words (its "in": all, windows, mac, linux, build)."""
    parts = value.split()
    return "Every copy of Hoard" if "all" in parts else ", ".join(WHERE[p] for p in parts)


def render() -> str:
    """The Acknowledgements page, from credits.json."""
    credits = json.loads((REPO / "hoard" / "credits.json").read_text("utf-8"))
    groups = []
    for g in credits["groups"]:
        rows = "\n".join(
            f'          <li><a href="{html.escape(i["url"])}">{html.escape(i["name"])}</a>'
            f' <span class="lic">{html.escape(i["license"])}</span> <span class="where">{html.escape(where(i["in"]))}</span></li>'
            for i in g["items"])
        groups.append(f"""      <section class="acks" aria-labelledby="ack{len(groups)}">
        <h2 id="ack{len(groups)}">{html.escape(g["title"])}</h2>
        <ul>
{rows}
        </ul>
      </section>""")
    body = "\n".join(groups)
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acknowledgements</title>
  <meta name="description" content="{DESCRIPTION}">
  <meta property="og:site_name" content="Hoard">
  <meta property="og:title" content="Acknowledgements">
  <meta property="og:description" content="{DESCRIPTION}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://hoard.furryup.link/acknowledgements.html">
  <meta property="og:image" content="https://hoard.furryup.link/img/social-credits.jpg">
  <meta property="og:image:type" content="image/jpeg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Hoard's logo, beside a shelf of tiles in each store's colour">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="theme-color" content="#F0B429">
  <meta name="color-scheme" content="dark light">
  <link rel="icon" href="favicon.ico">
{site_chrome.preloads()}  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div class="glow" aria-hidden="true"><div class="glow-in"></div></div>
  <a class="skip" href="#main">Skip to the page</a>
  {site_chrome.header()}

  <main id="main">
    <section class="page-head">
      <h1>Acknowledgements</h1>
      <p class="lede">Hoard is built on other people's work. Here's everything it uses or ships, with each one's
        license. The app lists the same in Settings, with each license's text.</p>
    </section>

{body}

    <section class="page-foot">
      <p>Hoard itself is under the <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/LICENSE">MIT
        license</a>. Its name and logo: <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/COPYRIGHT.md">COPYRIGHT.md</a>.</p>
    </section>
  </main>

  {site_chrome.footer()}
  <script src="site.js" defer></script>
</body>
</html>
"""
    return page


def main(argv: list[str]) -> int:
    """Check the page is up to date, or write it with --write. 1 when it's out of date."""
    page = render()
    if "--write" in argv:
        PAGE.write_text(page, "utf-8")
        return 0
    if not PAGE.is_file() or PAGE.read_text("utf-8") != page:
        print("site/acknowledgements.html isn't what hoard/credits.json says. Run python3 scripts/build_acknowledgements.py --write.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
