"""The website's Picture credits (site/credits.html): every product the screenshots show, with its picture, who made
it, and where to get it, from the products folder the screenshots were made from (scripts/screenshots.py).

    python3 scripts/build_picture_credits.py PRODUCTS_FOLDER

Each product's link is its public store page, when products.json has one (scripts/export_screenshot_products.py only
keeps those); else a search for it on its store, or its creator's shop. Never a purchase receipt or an account page:
a link that isn't a product's public page is left out (export_screenshot_products.public_link). The pictures go in
site/img/credits/ (WebP, 240 pixels square, shown at 120), numbered in the list's order. Needs Pillow.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from export_screenshot_products import public_link  # noqa: E402

PAGE = REPO / "site" / "credits.html"
PICTURES = REPO / "site" / "img" / "credits"
LABELS = {"booth": "Booth", "gumroad": "Gumroad", "jinxxy": "Jinxxy", "payhip": "Payhip", "itch": "itch.io"}
SEARCHES = {"booth": "https://booth.pm/en/search/{0}", "gumroad": "https://gumroad.com/discover?query={0}",
            "jinxxy": "https://jinxxy.com/market/browse?search_query={0}", "itch": "https://itch.io/search?q={0}"}
# a creator's own shop, for a product whose page is only in your account (Payhip's): by its creator's name
SHOPS = {"3Rr0r_418": "https://3rr0r418.store"}


def link(p: dict) -> tuple[str, str] | None:
    """Where to get a product, and what the link says: its public page, else its store's search for it."""
    page = public_link(p["store"], p.get("url")) if p.get("url") else None
    if page:
        return page, f"Get it on {LABELS[p['store']]}"
    if p.get("creator") in SHOPS:
        return SHOPS[p["creator"]], "The creator's shop"
    if p["store"] in SEARCHES:
        return SEARCHES[p["store"]].format(quote(p["name"][:100])), f"Find it on {LABELS[p['store']]}"
    return None


def entries(folder: Path) -> list[dict]:
    """The products, by creator and then name, each once."""
    items = json.loads((folder / "products.json").read_text("utf-8"))
    seen, out = set(), []
    for p in sorted(items, key=lambda p: (str(p.get("creator") or "").casefold(), str(p.get("name") or "").casefold())):
        key = (p["store"], p["name"])
        if key in seen or p["store"] not in LABELS or not (folder / p["image"]).is_file():
            continue
        seen.add(key)
        out.append(p)
    return out


def main(argv: list[str]) -> int:
    """Write the credits' list into site/credits.html, and each product's picture beside it."""
    from PIL import Image, ImageOps
    if not argv:
        sys.exit(__doc__)
    folder = Path(argv[0])
    found = entries(folder)
    PICTURES.mkdir(parents=True, exist_ok=True)
    for old in PICTURES.glob("*.webp"):
        old.unlink()
    rows = []
    for n, p in enumerate(found, 1):
        with Image.open(folder / p["image"]) as im:
            im.seek(0)
            ImageOps.fit(im.convert("RGB"), (240, 240), Image.LANCZOS).save(PICTURES / f"{n:02d}.webp", quality=80, method=6)
        where = link(p)
        a = f'\n            <a href="{html.escape(where[0])}" rel="noopener">{where[1]}</a>' if where else ""
        rows.append(f'''        <li class="credit {p["store"]}">
          <img src="img/credits/{n:02d}.webp" width="120" height="120" loading="lazy" alt="">
          <div><strong>{html.escape(p["name"])}</strong>
            <span>by {html.escape(p.get("creator") or "Unknown creator")} · <span class="store">{LABELS[p["store"]]}</span></span>{a}</div>
        </li>''')
    page = PAGE.read_text("utf-8")
    start = page.index('<ul class="credits">') + len('<ul class="credits">')
    end = page.index("</ul>", start)
    PAGE.write_text(page[:start] + "\n" + "\n".join(rows) + "\n      " + page[end:], "utf-8")
    print(f"{len(rows)} products credited in {PAGE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
