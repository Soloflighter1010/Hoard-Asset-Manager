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


# Booth's library, as served in September 2026: each file's buttons are drawn from placeholders with the address in
# data-href. "Download" is the file; "Open in Browser" (?browse=1) and "Other Downloads" (the Library Manager app)
# are other routes to the same file.
def booth_item(item_id, files):
    rows = "".join(
        f'<div class="mt-16"><div class="min-w-0"><div class="text-14">{name}</div></div><div class="flex gap-8">'
        + (f'<div class="js-download-button" data-href="https://booth.pm/downloadables/{fid}?browse=1" data-label="Open in Browser" data-test="browsable"></div>' if browse else "")
        + f'<div class="js-download-button" data-href="https://booth.pm/downloadables/{fid}" data-label="Download" data-test="downloadable"></div>'
        f'<div class="js-download-button" data-label="Other Downloads" data-test="other-downloads-button" data-dropdown-items=\'[{{"deeplinkDownloadableUrl":"https://booth.pm/downloadables/{fid}/deeplink?client=booth-library-manager"}}]\'></div>'
        '</div></div>' for fid, name, browse in files)
    return (f'<div class="bg-white p-16"><div class="flex"><a href="https://booth.pm/en/items/{item_id}"><img src="https://booth.pximg.net/{item_id}.jpg" width="80" height="80"></a>'
            f'<div><a href="https://booth.pm/en/items/{item_id}"><div class="font-bold">Item {item_id}</div></a>'
            f'<a href="https://shop{item_id}.booth.pm/"><div class="text-14 text-text-gray600">Shop {item_id}</div></a></div></div>{rows}</div>')


BOOTH_2026 = ('<html><head><meta charset="utf-8"></head><body><main>'
              + booth_item(111, [(501, "Avatar.unitypackage", False), (502, "Manual.pdf", True)])
              + booth_item(222, [(601, "Textures.zip", False)]) + '</main></body></html>')

# A Payhip shop's own library page (September 2026), on the shop's own domain.
PAYHIP_SHOP = ('<html><head><meta charset="utf-8"><title>Dashboard - Test Shop</title></head><body>'
               '<header><a class="logo-link" href="https://testshop.store/b-account">Test Shop</a>'
               '<a href="https://testshop.store/b-account/settings">Settings</a></header><h1>Your Products</h1><div class="grid-list">'
               + "".join(f'<div class="grid-item"><div class="product-card-wrapper"><div class="card__media"><img src="https://images.payhip.com/{c}.gif" width="200" height="200"></div>'
                         f'<h4 class="card__heading product-name"><a href="https://testshop.store/b-account/digital/{c}">Product {c}</a></h4>'
                         f'<div class="card-meta">September 11, 2026</div></div></div>' for c in ("aB1", "cD2"))
               + '</div></body></html>')


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class BoothAndPayhip(unittest.TestCase):

    def page_at(self, url, html):
        pw = sync_playwright().start()
        self.addCleanup(pw.stop)
        browser = pw.chromium.launch()
        self.addCleanup(browser.close)
        pg = browser.new_page()
        pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
                 if r.request.url.split("?")[0].rstrip("/") == url else r.abort())
        pg.goto(url)
        return pg

    def test_booth_files_come_from_the_download_placeholders(self):
        """With Booth's 2026 markup the old reader found every item but no files, so nothing could download."""
        pg = self.page_at("https://accounts.booth.pm/library", BOOTH_2026)
        for js in (library.BOOTH_JS, downloader.BOOTH_JS):
            items = {i["id"]: i for i in pg.evaluate(js)}
            self.assertEqual(sorted(items), ["111", "222"])
            self.assertEqual([(f["name"], f["url"]) for f in items["111"]["files"]],
                             [("Avatar.unitypackage", "https://booth.pm/downloadables/501"),
                              ("Manual.pdf", "https://booth.pm/downloadables/502")])  # no preview or app duplicates
            self.assertEqual(len(items["222"]["files"]), 1)

    def test_payhip_shop_library(self):
        pg = self.page_at("https://testshop.store/b-account", PAYHIP_SHOP)
        cards = pg.evaluate(library.PAYHIP_SHOP_JS)["cards"]
        self.assertEqual([(c["name"], c["creator"], c["url"]) for c in cards],
                         [("Product aB1", "Test Shop", "https://testshop.store/b-account/digital/aB1"),
                          ("Product cD2", "Test Shop", "https://testshop.store/b-account/digital/cD2")])
        self.assertEqual(cards[0]["creator_url"], "https://testshop.store")

    def test_importing_a_shop_page_needs_your_say_so(self):
        """A shop named inside an imported file is only trusted once you confirm its exact address (audit H-07)."""
        mhtml = ("From: <Saved by Blink>\r\nSnapshot-Content-Location: https://testshop.store/b-account\r\nSubject: Dashboard\r\n"
                 "MIME-Version: 1.0\r\nContent-Type: multipart/related; type=\"text/html\"; boundary=\"B\"\r\n\r\n--B\r\n"
                 "Content-Type: text/html\r\nContent-Location: https://testshop.store/b-account\r\n\r\n" + PAYHIP_SHOP + "\r\n--B--\r\n")
        cfg = config.load_config()
        cfg["payhip"]["shops"] = []
        config.apply_store_sites(cfg)
        with self.assertRaises(config.NewShop) as asked:
            library.import_saved_page(cfg, "auto", "Dashboard.mhtml", mhtml)
        self.assertEqual(asked.exception.shop, "https://testshop.store")
        self.assertEqual(cfg["payhip"]["shops"], [], "nothing is trusted before you confirm")
        with self.assertRaises(config.NewShop):
            library.import_saved_page(cfg, "auto", "Dashboard.mhtml", mhtml, trust_shop="https://other.store")
        store, items = library.import_saved_page(cfg, "auto", "Dashboard.mhtml", mhtml, trust_shop="https://testshop.store")
        self.assertEqual((store, cfg["payhip"]["shops"]), ("payhip", ["https://testshop.store"]))
        self.assertEqual(len(items), 2)
        config.apply_store_sites(config.load_config())

    def test_imported_pages_run_nothing(self):
        """Event handlers in an imported page never run (audit H-06): scripts are off and handlers are stripped."""
        hostile = ('<html><head><title>untouched</title></head><body><img src="x" onerror="document.title=\'ran\'">'
                   '<svg><animate onbegin="document.title=\'ran\'" attributeName="x" dur="1s"/></svg>'
                   '<a href="javascript:document.title=\'ran\'">x</a><iframe srcdoc="<script>parent.document.title=1</script>"></iframe></body></html>')
        from hoard import safety
        self.assertNotIn("onerror", safety.inert_html(hostile))
        self.assertNotIn("javascript:", safety.inert_html(hostile))
        pw = sync_playwright().start()
        self.addCleanup(pw.stop)
        browser = pw.chromium.launch()
        self.addCleanup(browser.close)
        for html_text in (hostile, safety.inert_html(hostile)):   # scripts off even for the unstripped page
            page = safety.offline_page(browser)
            page.set_content(html_text, wait_until="domcontentloaded")
            page.wait_for_timeout(600)
            self.assertEqual(page.title(), "untouched")

# A Payhip product page (September 2026): each file's own button, its name in a box beside it, a "Reset download
# credits" link that must never be clicked, and a second content page that isn't showing.
PAYHIP_PRODUCT = """<html><head><meta charset="utf-8"></head><body><main>
<div class="page" style="display:block"><div class="file-row"><input class="js-file-row-input-name" value="Avatar_v1.2">
  <a href="#!" class="btn js-reset-download-credits-button">Reset download credits</a>
  <button class="file-download-button js-file-download-button" data-file-id="aaa">Download</button></div></div>
<div class="page" style="display:none"><div class="file-row"><input class="js-file-row-input-name" value="Textures">
  <a href="#!" class="btn js-reset-download-credits-button">Reset download credits</a>
  <button class="file-download-button js-file-download-button" data-file-id="bbb">Download</button></div></div>
<a href="#!">How to download</a></main></body></html>"""


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class PayhipProductPage(unittest.TestCase):

    def test_only_the_file_buttons(self):
        pw = sync_playwright().start()
        self.addCleanup(pw.stop)
        browser = pw.chromium.launch()
        self.addCleanup(browser.close)
        pg = browser.new_page()
        pg.set_content(PAYHIP_PRODUCT)
        found = pg.evaluate(downloader.DOWNLOAD_BUTTONS_JS, {"allowAll": False, "hosts": ["payhip\\.com"]})
        self.assertEqual([f["label"] for f in found], ["Avatar_v1.2", "Textures"], "both files, the hidden page's too")
        classes = [pg.locator(f'[data-adl-idx="{f["idx"]}"]').first.get_attribute("class") for f in found]
        self.assertTrue(all("js-file-download-button" in c for c in classes), "never the reset-credits links")

    def test_class_names_dont_hide_a_download_button(self):
        """Utility class names can contain any word ("review", "limit"): only what a button says counts."""
        pw = sync_playwright().start()
        self.addCleanup(pw.stop)
        browser = pw.chromium.launch()
        self.addCleanup(browser.close)
        pg = browser.new_page()
        pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body=(
            '<main><button class="btn review-card line-limit hover:archive-glow">Download</button>'
            '<button class="btn">Reset download limit</button></main>')))
        pg.goto("https://jinxxy.com/my/inventory/abc")
        found = pg.evaluate(downloader.DOWNLOAD_BUTTONS_JS, {"allowAll": False, "hosts": ["jinxxy\\.com"]})
        self.assertEqual(len(found), 1, "the download button, and not the reset one")
        self.assertEqual(pg.locator(f'[data-adl-idx="{found[0]["idx"]}"]').first.inner_text(), "Download")


if __name__ == "__main__":
    unittest.main()
