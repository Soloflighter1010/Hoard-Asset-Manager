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
from unittest import mock

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

@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class DownloadButtons(unittest.TestCase):

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


# itch.io's library (itch.io/my-purchases), laid out the way itch.io lays out its game grids: a cell per project with
# the project's id, a picture that loads as you scroll (data-lazy_src; older grids use a background picture), the
# title, the creator, and a Download button leading to the project's download page. Around it: your own profile in
# the header, and projects you don't own in the footer and in a recommendation.
def itch_cell(game_id, creator, slug, title, key=None, picture="lazy"):
    thumb = (f'<img class="lazy_loaded" data-lazy_src="https://img.itch.zone/{slug}.png" '
             'src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="315" height="250">' if picture == "lazy"
             else f'<div class="game_thumb" data-background_image="https://img.itch.zone/{slug}.jpg"></div>')
    download = f'<a class="button download_btn" href="https://{creator}.itch.io/{slug}/download/{key}">Download</a>' if key else ""
    return (f'<div class="game_cell has_cover lazy_images" data-game_id="{game_id}">'
            f'<a class="thumb_link game_link" href="https://{creator}.itch.io/{slug}">{thumb}</a>'
            f'<div class="game_cell_data"><div class="game_title"><a class="title game_link" href="https://{creator}.itch.io/{slug}">'
            f'{title}</a></div><div class="game_author"><a href="https://{creator}.itch.io">{creator.replace("-", " ").title()}</a>'
            f'</div>{download}</div></div>')


def itch_library(cells, extra=""):
    return ('<html><head><meta charset="utf-8"><title>My purchases - itch.io</title></head><body>'
            '<div class="header_widget"><header><a href="https://itch.io/">itch.io</a><a href="https://itch.io/my-purchases">Library</a>'
            '<a href="https://buyer.itch.io"><img src="https://img.itch.zone/me.png" width="24" height="24">buyer</a></header></div>'
            '<div class="main wrapper"><div class="inner_column"><h2>My purchases</h2>'
            f'<div class="game_grid_widget base_widget user_game_grid">{"".join(cells)}</div>{extra}</div></div>'
            '<footer><a href="https://itch.io/docs">Docs</a><a href="https://featured.itch.io/staff-pick">Staff pick</a></footer>'
            '</body></html>')


# A project's download page: a row per file, one marked as a Windows build, one kept on another website, and the itch
# app's own links, which aren't files.
ITCH_DOWNLOAD = '''<html><head><meta charset="utf-8"><title>Download Paw Suit by Kitsu</title></head><body>
<header><a href="https://itch.io/app">Download the itch app</a></header>
<div class="main wrapper"><h2>Download Paw Suit</h2>
<div class="upload_list_widget base_widget">
  <div class="upload"><div class="info_column"><div class="upload_name"><strong class="name" title="PawSuit_v1.2.unitypackage">PawSuit_v1.2.unitypackage</strong>
    <span class="file_size"><span>48 MB</span></span></div><div class="upload_date">Jan 5, 2026</div></div>
    <a href="#" class="button download_btn" data-upload_id="5550001">Download</a></div>
  <div class="upload"><div class="info_column"><div class="upload_name"><strong class="name" title="PawSuit-Demo-Windows.zip">PawSuit-Demo-Windows.zip</strong>
    <span class="file_size"><span>210 MB</span></span><span class="download_platforms"><span title="Download for Windows" class="icon icon-windows8"></span></span></div></div>
    <a href="#" class="button download_btn" data-upload_id="5550002">Download</a></div>
  <div class="upload"><div class="info_column"><div class="upload_name"><strong class="name" title="Textures (Google Drive)">Textures (Google Drive)</strong></div></div>
    <a href="https://drive.google.com/file/d/abc/view" class="button download_btn" data-upload_id="5550003">Download</a></div>
</div>
<p>Also through <a class="button" href="https://itch.io/app">the itch app: Download</a></p>
</div></body></html>'''


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Itch(unittest.TestCase):

    def page_at(self, url, html):
        pw = sync_playwright().start()
        self.addCleanup(pw.stop)
        browser = pw.chromium.launch()
        self.addCleanup(browser.close)
        pg = browser.new_page()
        pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
                 if r.request.url.split("?")[0].rstrip("/") == url.rstrip("/") else r.abort())
        pg.goto(url)
        return pg

    def read(self, html):
        return self.page_at(library.ITCH_LIBRARY, html).evaluate(library.ITCH_JS)

    def test_the_library(self):
        got = self.read(itch_library([
            itch_cell(1001, "kitsu", "paw-suit", "Paw Suit", key="AbCdEf1234567890"),
            itch_cell(1002, "nova-works", "cozy-hoodie", "Cozy Hoodie", key="Zz9Yy8Xx7", picture="background"),
            itch_cell(1003, "kitsu", "protogen-visor", "Protogen Visor", key="Qq1Ww2Ee3"),
        ], extra=itch_cell(9999, "someone", "recommended-game", "You might like this")))
        cards = {c["id"]: c for c in got["cards"]}
        self.assertEqual(sorted(cards), ["kitsu/paw-suit", "kitsu/protogen-visor", "nova-works/cozy-hoodie"],
                         "only projects with a download page: never the recommendation, the footer or your own profile")
        paw = cards["kitsu/paw-suit"]
        self.assertEqual((paw["name"], paw["creator"], paw["creator_url"], paw["url"], paw["download_url"]),
                         ("Paw Suit", "Kitsu", "https://kitsu.itch.io", "https://kitsu.itch.io/paw-suit",
                          "https://kitsu.itch.io/paw-suit/download/AbCdEf1234567890"))
        self.assertEqual(paw["thumbnail"], "https://img.itch.zone/paw-suit.png", "the picture waiting to load, not its placeholder")
        hoodie = cards["nova-works/cozy-hoodie"]
        self.assertEqual((hoodie["creator"], hoodie["thumbnail"]), ("Nova Works", "https://img.itch.zone/cozy-hoodie.jpg"))
        self.assertIsNone(got["next"])
        items = [library.itch_item(c) for c in got["cards"]]
        self.assertTrue(all(i["key"].startswith("itch:") and i["download_url"] and i["url"] for i in items), items)

    def test_a_single_purchase(self):
        """With one project, its card is the whole page: the name, creator and picture are still the project's."""
        (c,) = self.read(itch_library([itch_cell(1001, "kitsu", "paw-suit", "Paw Suit", key="AbCdEf1234567890")]))["cards"]
        self.assertEqual((c["name"], c["creator"], c["thumbnail"]), ("Paw Suit", "Kitsu", "https://img.itch.zone/paw-suit.png"))

    def test_a_layout_without_download_buttons(self):
        """Should the library stop showing Download buttons, the cards itch.io marks with an id still list what you own."""
        got = self.read(itch_library([itch_cell(1001, "kitsu", "paw-suit", "Paw Suit"), itch_cell(1002, "nova", "hoodie", "Hoodie")]))
        self.assertEqual(sorted((c["id"], c["download_url"]) for c in got["cards"]), [("kitsu/paw-suit", ""), ("nova/hoodie", "")])

    def test_the_next_page(self):
        got = self.read(itch_library([itch_cell(1001, "kitsu", "paw-suit", "Paw Suit", key="AbCdEf1234567890")],
                                     extra='<div class="pager"><a class="next_page" href="/my-purchases?page=2">Next page</a></div>'))
        self.assertEqual(got["next"], "https://itch.io/my-purchases?page=2")

    def test_a_download_page(self):
        pg = self.page_at("https://kitsu.itch.io/paw-suit/download/AbCdEf1234567890", ITCH_DOWNLOAD)
        files = pg.evaluate(downloader.ITCH_UPLOADS_JS)
        self.assertEqual([(f["upload_id"], f["name"], f["size"], f["systems"], f["elsewhere"]) for f in files],
                         [("5550001", "PawSuit_v1.2.unitypackage", "48 MB", [], False),
                          ("5550002", "PawSuit-Demo-Windows.zip", "210 MB", ["Windows"], False),
                          ("5550003", "Textures (Google Drive)", "", [], True)],
                         "every file, and never the itch app's own links")
        for f in files:   # each file's own button is the one tagged for clicking
            self.assertEqual(pg.locator(f'[data-adl-idx="{f["idx"]}"]').first.get_attribute("data-upload_id"), f["upload_id"])


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class ItchSync(unittest.TestCase):
    """A whole itch.io sync in a real browser, against a stand-in itch.io: the library read, the download page
    opened, and a file's Download button clicked and what it downloads saved, the way itch.io's pages hand it over
    (the button leads the browser to the file's address, which answers with the file as an attachment)."""

    def test_sync(self):
        import types
        root = Path(tempfile.mkdtemp())
        cfg = {**config.load_config(), "request_delay": 0, "browser_channel": "chromium", "allow_unprotected_signins": True,
               "advanced_signin_location": True, "profile_dir": str(Path(tempfile.mkdtemp()) / "sign-ins")}
        cfg["itch"] = {**cfg["itch"], "save_thumbnails": False}
        shelf = itch_library([itch_cell(1001, "kitsu", "paw-suit", "Paw Suit", key="AbCdEf1234567890")])
        clicks = ("<script>document.addEventListener('click', e => { const b = e.target.closest('[data-upload_id]'); "
                  "if (!b) return; e.preventDefault(); location.href = 'https://files.example/' + b.dataset.upload_id; });</script>")
        page = ITCH_DOWNLOAD.replace("</body>", clicks + "</body>")

        def serve(route):
            url = route.request.url
            if url.startswith(library.ITCH_LIBRARY):
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=shelf)
            elif url.startswith("https://kitsu.itch.io/paw-suit/download/"):
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=page)
            elif url.startswith("https://files.example/5550001"):
                route.fulfill(status=200, body=b"PAW" * 1000, headers={
                    "Content-Type": "application/octet-stream", "Content-Disposition": 'attachment; filename="PawSuit_v1.2.unitypackage"'})
            else:
                route.abort()
        real_launch = downloader.launch_context

        def launch(p, cfg, headless, store):
            ctx = real_launch(p, cfg, True, store)
            ctx.route("**/*", serve)
            return ctx
        report = downloader.Report()
        with mock.patch.object(downloader, "launch_context", launch):
            downloader.sync_itch(cfg, root, types.SimpleNamespace(headed=False, only=None, dry_run=False), report)
        self.assertEqual(report.failed, [])
        self.assertEqual((root / "Itch" / "Kitsu" / "Paw Suit" / "PawSuit_v1.2.unitypackage").read_bytes(), b"PAW" * 1000)
        self.assertEqual(report.new_assets, ["itch.io: Kitsu / Paw Suit"])
        self.assertIn("a game build for Windows", " ".join(report.skipped))


def mhtml(page_html: str, url: str) -> str:
    """A page saved as "Webpage, Single File", as Chrome and Edge save one."""
    return ("From: <Saved by Blink>\r\nSnapshot-Content-Location: " + url + "\r\nSubject: Saved\r\n"
            "MIME-Version: 1.0\r\nContent-Type: multipart/related; type=\"text/html\"; boundary=\"B\"\r\n\r\n--B\r\n"
            "Content-Type: text/html\r\nContent-Location: " + url + "\r\n\r\n" + page_html + "\r\n--B--\r\n")


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class ImportingSeveralPages(unittest.TestCase):
    """Bulk import: pages from several stores, and several pages of one shop, read together in one offline browser,
    each with its own result. A page that can't be read doesn't stop the rest."""

    def tearDown(self):
        config.apply_store_sites(config.load_config())

    def test_a_mixed_batch(self):
        cfg = config.load_config()
        cfg["payhip"]["shops"] = ["https://testshop.store"]
        config.apply_store_sites(cfg)
        pages = [("Dashboard - Test Shop.mhtml", mhtml(PAYHIP_SHOP, "https://testshop.store/b-account")),
                 ("Dashboard - Test Shop (2).mhtml", mhtml(PAYHIP_SHOP.replace("aB1", "eF3").replace("cD2", "gH4"),
                                                           "https://testshop.store/b-account?page=2")),
                 ("My purchases - itch.io.html", "<!-- saved from url=(0028)https://itch.io/my-purchases -->\n"
                  + itch_library([itch_cell(1001, "kitsu", "paw-suit", "Paw Suit", key="AbCdEf1234567890")])),
                 ("Other Shop.mhtml", mhtml(PAYHIP_SHOP.replace("testshop.store", "othershop.store"),
                                            "https://othershop.store/b-account")),
                 ("notes.html", "<html><body><p>Just notes</p></body></html>"),
                 ("broken.mhtml", 'Content-Type: multipart/related; boundary="B"\r\n\r\n--B\r\nContent-Type: text/plain\r\n\r\n'
                                  "no page in here\r\n--B--\r\n")]
        launched, real = [], library._playwright

        def counted():
            start = real()
            return lambda: (launched.append(True), start())[1]
        with mock.patch.object(library, "_playwright", counted):
            results = library.import_saved_pages(cfg, pages)
        self.assertEqual(len(launched), 1, "one browser reads every page")
        self.assertEqual([r["filename"] for r in results], [name for name, _text in pages], "a result for every page, in order")
        found = {r["filename"]: r for r in results}
        self.assertEqual([len(found[n]["items"]) for n in ("Dashboard - Test Shop.mhtml", "Dashboard - Test Shop (2).mhtml")], [2, 2])
        self.assertEqual([i["key"] for i in found["My purchases - itch.io.html"]["items"]], ["itch:kitsu/paw-suit"])
        self.assertEqual(found["Other Shop.mhtml"], {"filename": "Other Shop.mhtml", "confirm_shop": "https://othershop.store"})
        self.assertIn("couldn't tell which store", found["notes.html"]["error"])
        self.assertIn("no web page inside", found["broken.mhtml"]["error"])
        self.assertEqual(cfg["payhip"]["shops"], ["https://testshop.store"], "nothing added before you confirm")
        (again,) = library.import_saved_pages(cfg, [pages[3]], trust_shops=["othershop.store"])
        self.assertEqual((again["store"], len(again["items"])), ("payhip", 2))
        self.assertEqual(cfg["payhip"]["shops"], ["https://testshop.store", "https://othershop.store"])
        self.assertTrue(all(i["url"].startswith("https://othershop.store/b-account/digital/") for i in again["items"]),
                        "its links count once the shop is yours")


if __name__ == "__main__":
    unittest.main()
