"""Store readers against stand-in pages, in a real browser. Skipped when Playwright's Chromium isn't installed
(python -m playwright install chromium); GitHub Actions installs it, so these run on every change.

Each page copies the layout that broke a real reader, so the same mistake can't come back.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import config, downloader, library  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _p.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

# Jinxxy, as a new account sees it (September 2026): a sidebar headed "Navigation" whose "Profile" link points
# at your own account, and product pages whose share image is Jinxxy's default banner.
HEAD = ('<head><meta charset="utf-8"><title>Jinxxy</title><meta property="og:image" content="https://jinxxy.com/og-default.png">'
        '<meta property="og:title" content="Jinxxy"></head>')
TOP = ('<header><a href="/"><img src="https://jinxxy.com/logo.png" width="100" height="40" alt="Jinxxy"></a>'
       '<button aria-label="Account menu"><img src="https://cdn.jinxxy.com/me.png" width="32" height="32"></button></header>')
SIDE = ('<aside><h2>Navigation</h2><nav><a href="/buyer123">Profile</a><a href="/my/likes">Likes</a><a href="/my/lists">Lists</a>'
        '<a href="/my/inventory">Inventory</a><a href="/market">Marketplace</a><a href="/leaderboard">Leaderboard</a></nav></aside>')


def card(i, name, creator):
    return (f'<div class="card"><a href="/my/inventory/item{i}"><img src="https://cdn.jinxxy.com/p{i}.png" width="220" height="220"></a>'
            f'<h3>{name}</h3><a href="/{creator.lower().replace(" ", "")}">{creator}</a></div>')


def inventory(cards):
    return f'<html>{HEAD}<body>{TOP}<div>{SIDE}<main><h1>Inventory</h1><div class="grid">{"".join(cards)}</div></main></div></body></html>'


ITEM = f'''<html>{HEAD}<body>{TOP}<div>{SIDE}<main>
  <h2><button aria-label="Back">&larr;</button> Product Details</h2>
  <section><img src="https://cdn.jinxxy.com/paw.png" width="300" height="300">
    <div><h2>Paw Suit - Furality Ultra</h2><a href="/hyroe"><img src="https://cdn.jinxxy.com/avatar.png" width="36" height="36"> Hyroe</a>
      <h3>Support Info</h3></div></section>
  <section><h2>My Review</h2></section>
  <section><h2>Instructions from the creator...</h2><img src="https://cdn.jinxxy.com/thank-you.png" width="900" height="400"></section>
</main></div></body></html>'''


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Jinxxy(unittest.TestCase):

    def page(self, html):
        self.pw = sync_playwright().start()
        self.addCleanup(self.pw.stop)
        browser = self.pw.chromium.launch()
        self.addCleanup(browser.close)
        pg = browser.new_page(viewport={"width": 1400, "height": 950})
        pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
                 if "cdn." not in r.request.url and not r.request.url.endswith(".png")
                 else r.fulfill(status=200, content_type="image/png", body=b"\x89PNG\r\n\x1a\n"))
        pg.goto("https://jinxxy.com/my/inventory/item1" if html is ITEM else "https://jinxxy.com/my/inventory")
        return pg

    def cards(self, cards):
        return self.page(inventory(cards)).evaluate(library.JX_CARDS_JS, config.DEFAULT_CONFIG["jinxxy"]["item_link_pattern"])

    def test_a_single_item_is_read_right(self):
        """With one item, the old reader took the whole page as its card: name "Navigation", creator your own profile."""
        (c,) = self.cards([card(1, "Paw Suit - Furality Ultra", "Hyroe")])
        self.assertEqual((c["name"], c["creator"]), ("Paw Suit - Furality Ultra", "Hyroe"))
        self.assertTrue(c["thumbnail"].endswith("/p1.png"))

    def test_several_items_are_read_right(self):
        got = self.cards([card(1, "Paw Suit", "Hyroe"), card(2, "Protogen Visor", "Kitsu Studio"), card(3, "Cozy Hoodie", "Nova")])
        self.assertEqual([(c["name"], c["creator"]) for c in got],
                         [("Paw Suit", "Hyroe"), ("Protogen Visor", "Kitsu Studio"), ("Cozy Hoodie", "Nova")])

    def test_product_page(self):
        """The downloader's reader: the product's own title, creator and picture, not the page's share banner."""
        info = self.page(ITEM).evaluate(downloader.JX_INFO_JS)
        self.assertEqual((info["name"], info["creator"]), ("Paw Suit - Furality Ultra", "Hyroe"))
        self.assertTrue(info["thumbnail"].endswith("/paw.png"), info["thumbnail"])


if __name__ == "__main__":
    unittest.main()
