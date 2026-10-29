"""Wishlists (issue #158; hoard/wishlists.py, kept as sets of the kind "wishlist" in hoard/sets.py): read from the
stores' own lists, or from pages saved from your own browser, each product with its price, and a price that changed
shown with what it was. The saved pages in tests/data/wishlists are made up, shaped like each store's."""
import contextlib
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import library, sets, wishlists
from hoard.tags import tag_key

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False

PAGES = Path(__file__).parent / "data" / "wishlists"


def saved(*names):
    return [(n, (PAGES / n).read_text("utf-8")) for n in names]


class Prices(unittest.TestCase):
    def test_as_the_stores_show_them(self):
        for text, amount, currency in (("1,000 JPY", 1000, "JPY"), ("15.00 - 50.00 USD", 15, "USD"), ("$22.46+", 22.46, "USD"),
                                       ("¥1,200", 1200, "JPY"), ("〜 800円", 800, "JPY"), ("€9.99", 9.99, "EUR"), ("Free", 0, "")):
            with self.subTest(text=text):
                p = wishlists.parse_price(text)
                self.assertEqual((p["amount"], p["currency"], p["text"]), (amount, currency, text))
        for text in ("", "Sold out", None, 7):
            self.assertIsNone(wishlists.parse_price(text))

    def test_gumroads_cents(self):
        self.assertEqual(wishlists.cents_price(1250, "usd"), {"text": "12.50 USD", "amount": 12.5, "currency": "USD"})
        self.assertEqual(wishlists.cents_price(1500, "jpy")["text"], "1,500 JPY", "yen have no cents")
        self.assertEqual(wishlists.cents_price(2000, "eur", True)["text"], "20.00 EUR+", "pay what you want, from")
        self.assertIsNone(wishlists.cents_price(True, "usd"))


def product(name, price, store="booth", **more):
    return {"store": store, "name": name, "creator": "Kitsu", "url": f"https://booth.pm/items/{abs(hash(name)) % 10000}",
            "price": wishlists.parse_price(price), **more}


class Kept(unittest.TestCase):
    def setUp(self):
        self.store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")

    def test_read_again_and_again(self):
        first = self.store.put_wishlists([{"store": "booth", "list": "Loved items", "products": [
            product("Fox Hoodie", "1,500 JPY"), product("Mochi Boots", "800 JPY"), product("Fox Hoodie", "1,500 JPY")]}],
            when="2026-10-01T10:00:00Z")
        (w,) = first["sets"]
        self.assertEqual((w["name"], w["kind"], w["source"], w["read"]),
                         ("Booth: Loved items", "wishlist", {"store": "booth", "list": "Loved items"}, "2026-10-01T10:00:00Z"))
        self.assertEqual(w["items"], [tag_key("booth", "Fox Hoodie"), tag_key("booth", "Mochi Boots")], "once each, in order")
        self.assertEqual(w["products"][tag_key("booth", "Fox Hoodie")]["price"]["amount"], 1500)
        self.store.change({"action": "rename", "id": w["id"], "name": "Booth wants"})
        again = self.store.put_wishlists([{"store": "booth", "list": "Loved items", "products": [
            product("Fox Hoodie", "1,200 JPY"), product("Rusk", "3,000 JPY")]}])
        (w,) = again["sets"]
        self.assertEqual(w["name"], "Booth wants", "a name you gave it stays")
        self.assertEqual(w["items"], [tag_key("booth", "Fox Hoodie"), tag_key("booth", "Rusk")], "as the store's list is now")
        hoodie = w["products"][tag_key("booth", "Fox Hoodie")]
        self.assertEqual((hoodie["price"]["text"], hoodie["was"]["text"]), ("1,200 JPY", "1,500 JPY"))
        self.assertEqual(again["cheaper"], [("Booth wants", "Fox Hoodie", "1,500 JPY", "1,200 JPY")])
        w = self.store.put_wishlists([{"store": "booth", "list": "Loved items", "products": [product("Fox Hoodie", "1,200 JPY")]}])["sets"][0]
        self.assertEqual(w["products"][tag_key("booth", "Fox Hoodie")]["was"]["text"], "1,500 JPY", "kept until it changes again")

    def test_each_list_its_own(self):
        done = self.store.put_wishlists([
            {"store": "jinxxy", "list": "Likes", "products": [product("Fox Ears", "10.00 USD", "jinxxy"),
                                                              product("Snowflakes", "5.00 USD", "gumroad")]},
            {"store": "gumroad", "list": "Winter", "products": [product("Snow Cap", "12.50 USD", "gumroad")]},
            {"store": "nowhere", "list": "x", "products": []}])
        self.assertEqual([s["name"] for s in done["sets"]], ["Jinxxy: Likes", "Gumroad: Winter"])
        self.assertIn(tag_key("gumroad", "Snowflakes"), done["sets"][0]["items"], "a product Jinxxy lists from another store")

    def test_not_in_hoard_for_unitys_sets(self):
        self.store.put_wishlists([{"store": "booth", "list": "Loved items", "products": [product("Rusk", "3,000 JPY")]}])
        made = self.store.change({"action": "create", "name": "Rusk", "items": [tag_key("booth", "Rusk")]})["made"]
        self.assertTrue(made)
        catalog = [{"store": "Booth", "name": "Rusk", "folder": "Booth/Kitsu/Rusk"}]
        self.assertEqual(sets.for_catalog(catalog, self.store.load()), [{"name": "Rusk", "items": ["Booth/Kitsu/Rusk"]}])

    def test_a_damaged_price_is_dropped(self):
        self.store.path.write_text(json.dumps({"sets": [{"id": "ab", "name": "W", "kind": "wishlist", "items": ["booth:rusk"],
            "source": {"store": "booth", "list": "<b>x</b>" * 30, "evil": 1}, "read": "yesterday",
            "products": {"booth:rusk": {"store": "booth", "name": "Rusk", "price": {"text": "1 JPY", "amount": "1"},
                                        "was": {"text": "2 JPY", "amount": 2, "currency": "JPY"}}}}]}), "utf-8")
        (w,) = self.store.load()["sets"]
        self.assertNotIn("read", w)
        self.assertNotIn("price", w["products"]["booth:rusk"])
        self.assertEqual(w["products"]["booth:rusk"]["was"]["amount"], 2.0)
        self.assertEqual(set(w["source"]), {"store", "list"})
        self.assertLessEqual(len(w["source"]["list"]), 60)

    def test_your_own(self):
        made = self.store.change({"action": "create", "name": "Birthday", "kind": "wishlist", "items": []})["made"]
        self.assertEqual(self.store.load()["sets"][0], {"id": made, "name": "Birthday", "items": [], "kind": "wishlist"})


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class JinxxyElsewhere(unittest.TestCase):
    """A Jinxxy list can send you to a product on a site that isn't one of the stores: it keeps that page as its link,
    instead of showing No store link; one on a store Hoard knows is that store's, as before."""

    def test_kept_as_its_link(self):
        got = wishlists.jinxxy_products([
            {"url": "https://ko-fi.com/s/abc123?ref=jinxxy#top", "name": "Fox Tail", "creator": "Kitsu", "price": "5.00 USD"},
            {"url": "https://snowy.gumroad.com/l/flakes?ref=jinxxy", "name": "Flakes", "creator": "Snowy"},
            {"url": "https://jinxxy.com/kitsu/FoxEars", "name": "Fox Ears", "creator": "Kitsu"}])
        tail, flakes, ears = got
        self.assertEqual((tail["store"], tail.get("url"), tail["elsewhere"]), ("jinxxy", None, "https://ko-fi.com/s/abc123?ref=jinxxy"))
        self.assertEqual((flakes["store"], flakes["url"], flakes.get("elsewhere")), ("gumroad", "https://snowy.gumroad.com/l/flakes", None))
        self.assertEqual((ears["store"], ears["url"], ears.get("elsewhere")), ("jinxxy", "https://jinxxy.com/kitsu/FoxEars", None))
        kept = sets.clean_product(tail)
        self.assertEqual(kept["elsewhere"], "https://ko-fi.com/s/abc123?ref=jinxxy")

    def test_only_a_public_https_page(self):
        for bad in ("http://ko-fi.com/s/abc", "https://user:pw@ko-fi.com/s/abc", "https://ko-fi.com:8443/s/abc",
                    "https://127.0.0.1/s/abc", "https://localhost/s/abc", "https://printer.local/x", "https://[::1]/x",
                    "javascript:alert(1)", "https://" + "a" * 700 + ".com/"):
            with self.subTest(bad=bad):
                self.assertIsNone(sets.outside_link(bad))
                self.assertNotIn("elsewhere", sets.clean_product({"store": "jinxxy", "name": "X", "elsewhere": bad}))

    def test_never_shared(self):
        """A shared set's viewer opens only the stores' own pages: a page elsewhere stays in Hoard."""
        s = {"name": "Likes", "items": ["jinxxy:fox tail"],
             "products": {"jinxxy:fox tail": {"store": "jinxxy", "name": "Fox Tail", "elsewhere": "https://ko-fi.com/s/abc123"}}}
        code, count = sets.share_code(s)
        self.assertEqual(count, 1)
        self.assertNotIn("ko-fi", json.dumps(sets.from_code(code)))


class SavedPages(unittest.TestCase):
    def test_each_stores_page(self):
        got = {r["filename"]: r for r in wishlists.from_saved_pages(saved("booth.html", "gumroad.html", "jinxxy-likes.html", "payhip.html"))}
        (booth,) = got["booth.html"]["lists"]
        self.assertEqual((booth["store"], booth["list"]), ("booth", "Loved items"))
        self.assertEqual([(p["name"], p["creator"], p["price"]["text"], p["url"]) for p in booth["products"]],
                         [("Fox Hoodie【5 avatars】", "Kitsu Studio", "1,500 JPY", "https://booth.pm/en/items/1001"),
                          ("Mochi Boots", "Mochi Works", "800 JPY", "https://booth.pm/en/items/1002")],
                         "not the recently viewed items above them, nor a picture's Loading...")
        self.assertTrue(booth["products"][0]["thumbnail"].endswith("/one_base_resized.jpg"), "the picture shown")
        (gum,) = got["gumroad.html"]["lists"]
        self.assertEqual(gum["list"], "Winter")
        self.assertEqual([(p["name"], p["url"], p["price"]["text"]) for p in gum["products"]],
                         [("Snow Cap", "https://mochi.gumroad.com/l/snowcap", "12.50 USD"),
                          ("Mittens", "https://kitsu.gumroad.com/l/mittens", "20.00 EUR+"),
                          ("Yuki Hair", "https://shiro.gumroad.com/l/yuki", "1,500 JPY")])
        (likes,) = got["jinxxy-likes.html"]["lists"]
        self.assertEqual(likes["list"], "Likes", "a page saved as HTML only: its own address from its canonical link")
        self.assertEqual([(p["store"], p["name"], p["url"]) for p in likes["products"]],
                         [("jinxxy", "Fox Ears", "https://jinxxy.com/kitsu/FoxEars"),
                          ("jinxxy", "Paw Grab", "https://jinxxy.com/kitsu/PawGrab"),
                          ("jinxxy", "Tail Wag", "https://jinxxy.com/kitsu/TailWag"),
                          ("gumroad", "Snowflakes", "https://snowy.gumroad.com/l/flakes")])
        self.assertEqual(likes["products"][0]["creator"], "kitsu")
        self.assertIn("foxears.png", likes["products"][0]["thumbnail"], "its picture, not its creator's")
        # issue #212: a product shown by its video: the video's still, or (none given) no picture rather than the video
        self.assertTrue(likes["products"][1]["thumbnail"].endswith("/pawgrab-still.png"))
        self.assertNotIn("thumbnail", likes["products"][2])
        (pay,) = got["payhip.html"]["lists"]
        self.assertEqual((pay["list"], pay["products"][0]["name"], pay["products"][0]["price"]["amount"]), ("citrus.example: Summer", "Citrus Hat", 5.0))

    def test_a_product_shown_by_a_video_gets_its_pages_picture(self):
        """Issue #212: a product whose first picture is a video (Jinxxy's IK Grab) had no picture, so its tile showed its
        initials and its wishlist's cover a gap. Its public page gives one (Open Graph), which Hoard takes instead."""
        page = ('<meta property="og:title" content="Tail Wag"><meta property="og:image" '
                'content="https://jinxxy-c.jinxxy-cdn.com/cdn-cgi/image/format=auto/aaa/3/tailwag.webp">'
                '<video src="https://jinxxy-c.jinxxy-cdn.com/aaa/3/tailwag.mp4"></video>')
        asked = []

        def fetch(url, hosts):
            asked.append(url)
            return (page, "text/html") if url.endswith("/TailWag") else None
        items = [{"store": "jinxxy", "name": "Tail Wag", "url": "https://jinxxy.com/kitsu/TailWag"},
                 {"store": "jinxxy", "name": "Video Only", "url": "https://jinxxy.com/kitsu/Gone", "thumbnail": "https://jinxxy-c.jinxxy-cdn.com/a/b.mp4"},
                 {"store": "jinxxy", "name": "Has One", "url": "https://jinxxy.com/kitsu/Has", "thumbnail": "https://jinxxy-c.jinxxy-cdn.com/a/has.png"},
                 {"store": "jinxxy", "name": "Elsewhere", "elsewhere": "https://ko-fi.com/s/x"}]
        self.assertEqual(wishlists.pictures_from_pages(items, fetch), 1)
        self.assertEqual(items[0]["thumbnail"], "https://jinxxy-c.jinxxy-cdn.com/cdn-cgi/image/format=auto/aaa/3/tailwag.webp")
        self.assertTrue(sets.product_picture("jinxxy", items[0]["thumbnail"]), "from Jinxxy's own picture host, so it shows")
        self.assertEqual(items[1]["thumbnail"], "https://jinxxy-c.jinxxy-cdn.com/a/b.mp4", "a page that can't be read: left as it was")
        self.assertEqual(asked, ["https://jinxxy.com/kitsu/TailWag", "https://jinxxy.com/kitsu/Gone"], "only those without a picture")
        self.assertEqual(wishlists.pictures_from_pages([dict(items[0], thumbnail=None)] * 3, fetch, limit=2), 2)
        self.assertIsNone(wishlists.product("jinxxy", "Clip", thumbnail="https://jinxxy-c.jinxxy-cdn.com/a/clip.MP4?x=1").get("thumbnail"))
        self.assertIsNone(library.item("jinxxy", "9", name="Clip", thumbnail="https://jinxxy-c.jinxxy-cdn.com/a/clip.webm")["thumbnail"])

    def test_the_tags_creators_give_their_products(self):
        """Issue #206: the tags a product's creator gave it on its store's page: Booth's item JSON (and its category),
        Jinxxy's page data and itch.io's Tags row, kept as Hoard keeps tags. Gumroad's and Payhip's pages show none."""
        booth = {"name": "Fox Tail", "price": "¥ 600", "shop": {"name": "Kitsu"}, "images": [],
                 "tags": [{"name": "VRChat"}, {"name": "しっぽ"}, {"name": "VRChat"}, {"name": "#Fox, Tail"}],
                 "category": {"name": "3D Accessories", "parent": {"name": "3D Models"}}}
        jinxxy = ('<meta property="og:title" content="Fox Ears"><script>self.__next_f.push([1,"{\\"product\\":'
                  '{\\"name\\":\\"Fox Ears\\",\\"tags\\":[\\"furry\\",\\"face_tracking\\",\\"Quest\\"]}}"])</script>')
        itch = ('<meta property="og:title" content="Tail Pack"><table><tr><td>Category</td><td><a href="/x">Assets</a></td></tr>'
                '<tr><td>Tags</td><td><a href="https://itch.io/game-assets/tag-3d">3D</a>, <a href="/t">Low-poly</a>, '
                '<a href="/t">Tails &amp; Ears</a></td></tr></table>')
        pages = {"https://booth.pm/en/items/77.json": (json.dumps(booth), "application/json"),
                 "https://jinxxy.com/kitsu/FoxEars": (jinxxy, "text/html"),
                 "https://kitsu.itch.io/tail-pack": (itch, "text/html"),
                 "https://kitsu.gumroad.com/l/hat": ('<meta property="og:title" content="Hat">', "text/html")}
        fetch = lambda url, hosts: pages.get(url)   # noqa: E731
        got = {link: wishlists.from_product_page(link, fetch)["store_tags"] for link in
               ("https://booth.pm/en/items/77", "https://jinxxy.com/kitsu/FoxEars", "https://kitsu.itch.io/tail-pack",
                "https://kitsu.gumroad.com/l/hat")}
        self.assertEqual(got, {"https://booth.pm/en/items/77": ["vrchat", "しっぽ", "fox tail", "3d accessories", "3d models"],
                               "https://jinxxy.com/kitsu/FoxEars": ["furry", "face_tracking", "quest"],
                               "https://kitsu.itch.io/tail-pack": ["3d", "low-poly", "tails & ears"],
                               "https://kitsu.gumroad.com/l/hat": []})
        self.assertEqual(len(wishlists.store_tags_in("booth", {"tags": [{"name": f"t{n}"} for n in range(80)]})), 30, "30 at most")
        self.assertEqual(wishlists.store_tags_in("jinxxy", '"tags":[not json]'), [])

    def test_what_isnt_a_wishlist(self):
        (r,) = wishlists.from_saved_pages([("library.html", "<!-- saved from url=(0035)https://accounts.booth.pm/library -->"
                                                            "<html><body>Library</body></html>")])
        self.assertIn("isn't a wishlist page", r["error"])

    def test_a_page_saved_as_html_only_names_its_address(self):
        """An HTML-only save has no "saved from" line, so its <link rel="canonical"> says where it's from; a page full
        of half-made <link tags is read as quickly (CodeQL: a pattern for it that could take quadratic time)."""
        self.assertEqual(wishlists._canonical('<link rel="icon" href="https://x/i.png"><link rel="canonical" '
                                              'href="https://jinxxy.com/my/likes?page=2">'), "https://jinxxy.com/my/likes?page=2")
        self.assertEqual(wishlists._canonical('<link href="https://gumroad.com/wishlists/abc" rel="canonical">'),
                         "https://gumroad.com/wishlists/abc")
        self.assertEqual(wishlists._canonical('<link rel="canonical" href="http://x">'), "", "https only")
        start = time.monotonic()
        wishlists._canonical("<link" * 100_000)
        wishlists._canonical('<link=rel="canonical"' * 50_000)
        self.assertLess(time.monotonic() - start, 1.0)

    def test_a_long_list_saved_a_page_at_a_time(self):
        one = {"store": "booth", "list": "Loved items", "url": "u", "products": [product("A", "1 JPY"), product("B", "2 JPY")]}
        two = {"store": "booth", "list": "Loved items", "url": "u", "products": [product("B", "2 JPY"), product("C", "3 JPY")]}
        (both,) = wishlists.merge_lists([one, two])
        self.assertEqual([p["name"] for p in both["products"]], ["A", "B", "C"])


class BoothLinks(unittest.TestCase):
    def test_an_items_english_page(self):
        """A Booth item's link that names no language (booth.pm/items/<id>, as 4.4.0 and the 5.0 betas kept a loved
        item's) doesn't open the item for everyone: it's its English page, kept, shared and shown. One that names
        a language, or is on its shop's own address, stays as it is."""
        for given, kept in (("https://booth.pm/items/7", "https://booth.pm/en/items/7"),
                            ("https://booth.pm/ja/items/7", "https://booth.pm/ja/items/7"),
                            ("https://booth.pm/en/items/7", "https://booth.pm/en/items/7"),
                            ("https://kitsu.booth.pm/items/7", "https://kitsu.booth.pm/items/7")):
            self.assertEqual(sets.product_link("booth", given), kept, given)
        stored = sets.SetStore.sanitize({"sets": [{"id": "ab", "name": "W", "kind": "wishlist", "items": ["booth:rusk"],
                                                   "source": {"store": "booth", "list": "Loved items"},
                                                   "products": {"booth:rusk": {"store": "booth", "name": "Rusk",
                                                                               "url": "https://booth.pm/items/7"}}}]})
        self.assertEqual(stored["sets"][0]["products"]["booth:rusk"]["url"], "https://booth.pm/en/items/7", "one kept from before")


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class BoothPages(unittest.TestCase):
    """Booth's loved items, 20 to a page: its page numbers are drawn by its script (an address with ?page=2 shows the
    first page again, so Hoard read only the first 20), and Hoard turns the pages with Booth's own arrow."""
    PAGE = """<html><body><main>
<div><button class="charcoal-tag-item" data-state="default"><span>all</span></button>
<button class="charcoal-tag-item" data-state="inactive"><span>uncategorized</span></button></div>
<div class="grid" id="grid"></div><div id="pager"></div>
<script>
const TOTAL = 45, PER = 20; let cur = 1;
function draw() {
  let h = '';
  for (let i = (cur - 1) * PER + 1; i <= Math.min(TOTAL, cur * PER); i++)
    h += `<div class="item-card-wrapper"><div class="pt-8"><a href="https://booth.pm/en/items/${5000 + i}"><span class="break-all">Item ${i}</span></a>` +
         `<a href="https://kitsu.booth.pm/"><div>Kitsu</div></a><div class="flex"><div>${i * 100} JPY</div></div></div></div>`;
  document.getElementById('grid').innerHTML = h;
  const pages = Math.ceil(TOTAL / PER);
  document.getElementById('pager').innerHTML = [...Array(pages).keys()].map(k =>
    `<div class="${k + 1 === cur ? 'text-primary400' : 'cursor-pointer'}">${k + 1}</div>`).join('') +
    (cur < pages ? '<div class="cursor-pointer flex"><pixiv-icon name="24/ArrowOpenRight">&gt;</pixiv-icon></div>' : '');
}
document.addEventListener('click', e => {   // a page is read a moment after it's chosen, and the address stays the same
  const a = e.target.closest('.cursor-pointer');
  if (a) setTimeout(() => { cur = a.querySelector('pixiv-icon') ? cur + 1 : +a.textContent; draw(); }, 300);
});
draw();
</script></main></body></html>"""

    def test_every_page_is_read(self):
        import re
        from playwright.sync_api import sync_playwright
        asked, said = [], []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()

            def route(r):
                if r.request.url.startswith(wishlists.BOOTH_WISHES):
                    asked.append(r.request.url)
                    r.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.PAGE)
                else:
                    r.abort()
            ctx.route("**/*", route)
            lists = wishlists.read_booth(ctx, {"request_delay": 0}, said.append)
            browser.close()
        (loved,) = lists
        self.assertEqual(loved["list"], "Loved items")
        self.assertEqual([x["name"] for x in loved["products"]], [f"Item {i}" for i in range(1, 46)], "all three pages, in order")
        self.assertTrue(all(re.fullmatch(r"https://booth\.pm/en/items/50\d\d", x["url"]) for x in loved["products"]))
        self.assertEqual(loved["products"][44]["price"]["amount"], 4500)
        self.assertIn("page 3: 45 items", said[-1])
        self.assertNotIn("page=", " ".join(asked), "the pages are turned, not asked for by address")


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class InHoard(unittest.TestCase):
    def setUp(self):
        from hoard import config, library, server
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        offline = mock.patch.object(wishlists, "read_store_page", lambda url, hosts: None)   # (no store's page is read)
        offline.start()
        self.addCleanup(offline.stop)
        (tmp / "dl").mkdir()
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(tmp / "dl"), "setup_done": True,
                                                      "ui": {"toured": True}}, lan=False)
        with self.srv.lib.lock:   # Mochi Boots is yours already
            self.srv.lib.data["items"] = [library.item("booth", "1002", name="Mochi Boots", creator="Mochi Works",
                                                       url="https://booth.pm/ja/items/1002")]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def api(self, path, body=None):
        import urllib.error
        import urllib.request
        from hoard.safety import ACCESS_HEADER
        req = urllib.request.Request(self.srv.entry_url().split("/#")[0] + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", ACCESS_HEADER: self.srv.key})
        try:
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {"status": e.code, **json.loads(e.read() or b"{}")}

    def test_import_and_show(self):
        got = self.api("/api/wishlists/import", {"files": [{"filename": n, "content": c} for n, c in saved("booth.html", "gumroad.html")]
                                                 + [{"filename": "notes.html", "content": "<p>hello</p>"}]})
        self.assertEqual(got["lists"], 2)
        self.assertIn("isn't a wishlist page", got["pages"][2]["error"])
        wish = next(s for s in got["sets"] if s["name"] == "Booth: Loved items")
        self.assertEqual((wish["kind"], wish["source"]), ("wishlist", {"store": "booth", "list": "Loved items"}))
        boots = next(i for i in wish["items"] if i["name"] == "Mochi Boots")
        self.assertTrue(boots["owned"], "yours already: in your library")
        # read again, cheaper: what it was shows
        page = (PAGES / "booth.html").read_text("utf-8").replace("1,500 JPY", "1,200 JPY")
        self.api("/api/wishlists/import", {"files": [{"filename": "booth.html", "content": page}]})
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.goto(self.srv.entry_url().split("/#")[0] + "/#store=Sets")
            page.locator(".wish-h").wait_for()
            tile = page.locator(".settile", has_text="Booth: Loved items")
            self.assertIn("1 yours already", tile.inner_text())
            self.assertIn("1 cheaper than before", tile.inner_text())
            self.assertEqual(page.locator(".settile", has_text="Gumroad: Winter").count(), 1)
            tile.click()
            page.locator(".sethead").wait_for()
            self.assertIn("Your wishlist from Booth (Loved items)", page.locator(".sethead").inner_text())
            hoodie = page.locator(".slot.ext", has_text="Fox Hoodie")
            self.assertEqual(hoodie.locator(".price.down").inner_text(), "1,200 JPY")
            self.assertEqual(" ".join(hoodie.locator(".was").inner_text().split()), "was 1,500 JPY", "struck through, read as was")
            self.assertEqual(page.locator('details[data-fold="wish-yours"] .nm-t').all_inner_texts(), ["Mochi Boots"],
                             "yours: under Yours already")
            self.assertEqual(page.locator(".slot.wanted", has_text="Mochi Boots").count(), 0, "not one to buy")
            browser.close()
        self.assertEqual(errors, [])

    def test_groups_tags_prices_and_links(self):
        """A wishlist open: what isn't yours yet and what is, in two groups that fold away (and stay folded), in the
        page's sort; the filters beside it are its own: its suggested tags, from the words its names share, your tags
        on what you have, and its creators; a price range above it narrows it down too, in one currency; and
        products are added by their links."""
        from hoard import server
        from hoard.tags import tag_key
        sets.SetStore().put_wishlists([{"store": "booth", "list": "Loved items", "url": "u", "products": [
            product("Fox Hoodie", "1,200 JPY"), product("Fox Ears", "800 JPY", creator="Ash Atelier"),
            product("Wolf Hoodie", "3,000 JPY"), product("Mochi Boots", "500 JPY", id_="1002"),
            product("Snow Cap", "12.50 USD", "gumroad", creator="")]}])
        self.api("/api/tags", {"action": "assign", "keys": [tag_key("booth", "Mochi Boots")], "add": ["boots"]})
        page_json = json.dumps({"name": "Fox Tail", "price": "¥ 600", "shop": {"name": "Mochi Works"}, "images": []})
        from playwright.sync_api import sync_playwright
        with mock.patch.object(server, "read_store_page", lambda url, hosts: (page_json, "application/json")), sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.goto(self.srv.entry_url().split("/#")[0] + "/#store=Sets")
            self.assertIn("Sets and Wishlists", page.locator('#storeSeg [data-store="Sets"]').inner_text())
            page.locator(".settile", has_text="Booth: Loved items").wait_for()
            self.assertEqual(page.locator("#count").inner_text(), "0 sets", "a wishlist is counted under Wishlists")
            page.locator(".settile", has_text="Booth: Loved items").click()
            buy, yours = page.locator('details[data-fold="wish-buy"]'), page.locator('details[data-fold="wish-yours"]')
            buy.wait_for()
            self.assertEqual(buy.locator(".slot.ext").count(), 4)
            self.assertEqual(yours.locator(".nm-t").all_inner_texts(), ["Mochi Boots"], "yours already: in its own group")
            self.assertEqual(page.locator("#grid .slot").count(), 0, "a wishlist's products are all in its groups")
            # the page's sort: Recently added keeps the list's own order; Creator, those with none last
            page.select_option("#sort", "added")
            self.assertEqual(buy.locator(".nm-t").all_inner_texts(), ["Fox Hoodie", "Fox Ears", "Wolf Hoodie", "Snow Cap"])
            page.select_option("#sort", "creator")
            self.assertEqual(buy.locator(".nm-t").all_inner_texts(), ["Fox Ears", "Fox Hoodie", "Wolf Hoodie", "Snow Cap"])
            page.select_option("#sort", "name")
            self.assertEqual(buy.locator(".nm-t").all_inner_texts(), ["Fox Ears", "Fox Hoodie", "Snow Cap", "Wolf Hoodie"])
            # its creators, beside it
            self.assertEqual(page.locator("#creators button").evaluate_all("l => l.map(b => b.dataset.creator + ' ' + b.querySelector('.n').textContent)"),
                             ["Ash Atelier 1", "Kitsu 2", "Mochi Works 1"], "its own, with how many (none for one without)")
            page.click('#creators [data-creator="Kitsu"]')
            self.assertEqual(buy.locator(".nm-t").all_inner_texts(), ["Fox Hoodie", "Wolf Hoodie"])
            self.assertEqual(yours.locator(".nm-t").count(), 0, "Mochi Works' boots aren't Kitsu's")
            page.click('#status [data-clear="creator"]')
            self.assertEqual(buy.locator(".slot.ext").count(), 4)
            self.assertEqual(page.locator(".wish-tags").count(), 0, "no tags above it: they're beside it")
            # your tags on what you have
            page.click('#myTags [data-tag="boots"]')
            self.assertEqual(yours.locator(".nm-t").all_inner_texts(), ["Mochi Boots"])
            self.assertEqual(buy.locator(".slot.ext").count(), 0)
            page.click('#myTags [data-tag="boots"]')
            yours.locator("summary").click()
            page.wait_for_function("() => !document.querySelector('details[data-fold=\"wish-yours\"]').open")
            # its suggested tags: words several names share
            tags = page.locator("#tags .chip")
            self.assertIn("hoodie2", tags.evaluate_all("l => l.map(b => b.textContent)"))
            page.click('#tags [data-tag="fox"]')
            self.assertEqual(sorted(buy.locator(".nm-t").all_inner_texts()), ["Fox Ears", "Fox Hoodie"])
            self.assertEqual(page.locator("#creators button").evaluate_all("l => l.map(b => b.dataset.creator + ' ' + b.querySelector('.n').textContent)"),
                             ["Ash Atelier 1", "Kitsu 1"], "the creators of what the tag leaves")
            # a price range, in one of its currencies (the one most of its prices are in, to begin with)
            page.fill('[data-wish="min"]', "1000")
            self.assertEqual(buy.locator(".nm-t").all_inner_texts(), ["Fox Hoodie"])
            self.assertEqual(page.locator("#creators button").evaluate_all("l => l.map(b => b.dataset.creator)"), ["Kitsu"],
                             "beside it, too")
            page.click('[data-setx="wclear"]')
            self.assertEqual(sorted(buy.locator(".nm-t").all_inner_texts()), ["Fox Ears", "Fox Hoodie"], "Clear: the price range")
            page.click('#tags [data-tag="fox"]')
            self.assertEqual(buy.locator(".slot.ext").count(), 4)
            page.select_option('[data-wish="cur"]', "USD")
            page.fill('[data-wish="max"]', "20")
            self.assertEqual(buy.locator(".nm-t").all_inner_texts(), ["Snow Cap"])
            page.click('[data-setx="wclear"]')
            # back to every set: the wishlist goes with it (its groups stayed below the sets, after a filter), and so do
            # the tags chosen in it
            page.click('[data-setx="back"]')
            page.locator(".settile", has_text="Booth: Loved items").wait_for()
            self.assertEqual(page.locator("#setMore .wishgroup, #setMore .wishbar").count(), 0, "nothing of the wishlist left")
            self.assertEqual(page.locator('#status [data-clear="tag"]').count(), 0, "its tag isn't a filter anymore")
            page.locator(".settile", has_text="Booth: Loved items").click()
            buy.wait_for()
            # more to add, found in the browser (issue #187): Nexyy and the stores' own searches, with your words
            page.fill("[data-wishfind]", "fox tail")
            finds = page.locator("[data-findon]").evaluate_all("l => l.map(a => [a.textContent, a.href, a.target])")
            self.assertEqual([f[0] for f in finds], ["Nexyy", "Booth", "Gumroad", "Jinxxy", "itch.io"])
            self.assertEqual(finds[0][1:], ["https://nexyy.com/browse?q=fox%20tail", "_blank"])
            self.assertEqual(finds[3][1], "https://jinxxy.com/market/browse?search=fox%20tail")
            # added by its link: the one Nexyy gave (its ?ref=nexyy left off)
            page.click('[data-setx="addlinks"]')
            page.fill("#addLinks", "https://booth.pm/en/items/4242?ref=nexyy")
            page.locator("dialog.ask button[value=yes]").click()
            buy.locator(".slot.ext", has_text="Fox Tail").wait_for()
            self.assertEqual(buy.locator(".slot.ext", has_text="Fox Tail").locator(".ext-price .price").inner_text(), "¥ 600",
                             "its price, as a badge")
            # taken off again: a button that says so, and asked first (issue #213)
            tail = buy.locator(".slot.ext", has_text="Fox Tail")
            self.assertEqual(tail.locator(".ext-out").get_attribute("aria-label"), "Take Fox Tail off this wishlist")
            tail.locator(".ext-out").click()
            sure = page.locator("dialog.ask[open]")
            self.assertIn("Take Fox Tail off this wishlist?", sure.inner_text())
            sure.locator('button[value="no"]').click()
            self.assertEqual(tail.count(), 1, "Cancel: still on it")
            tail.locator(".ext-out").click()
            sure.locator('button[value="yes"]').click()
            tail.wait_for(state="detached")
            # folded stays folded, next time too
            page.reload()
            page.locator('details[data-fold="wish-buy"]').wait_for()
            self.assertFalse(page.locator('details[data-fold="wish-yours"]').evaluate("d => d.open"))
            browser.close()
        self.assertEqual(errors, [])

    def test_a_wishlists_filters_are_its_own(self):
        """The filters beside a wishlist count its products under its own price range, never the last one's; and a
        tag chosen elsewhere doesn't carry into it, even coming back to it after a reload on a set (issue #180)."""
        sets.SetStore().put_wishlists([
            {"store": "booth", "list": "Loved items", "url": "u", "products": [
                product("Fox Hoodie", "1,200 JPY"), product("Fox Ears", "800 JPY", creator="Ash Atelier"),
                product("Wolf Hoodie", "3,000 JPY"), product("Snow Cap", "500 JPY")]},
            {"store": "gumroad", "list": "Winter", "url": "w", "products": [
                product("Scarf", "12.00 USD", "gumroad", creator="Snow Co"), product("Mittens", "8.00 USD", "gumroad", creator="Snow Co")]}])
        made = sets.SetStore().change({"action": "create", "name": "Rusk, winter", "items": ["booth:rusk"]},
                                      lambda key: {"store": "booth", "name": "Rusk", "creator": "Kitsu", "url": "https://booth.pm/ja/items/1"})["made"]
        ids = {s["name"]: s["id"] for s in sets.SetStore().load()["sets"]}
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            base = self.srv.entry_url().split("/#")[0]
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.goto(base + "/#store=Sets")
            page.locator(".settile", has_text="Booth: Loved items").click()
            page.locator('details[data-fold="wish-buy"]').wait_for()
            page.fill('[data-wish="min"]', "1000")
            page.click('[data-setx="back"]')
            page.locator(".settile", has_text="Gumroad: Winter").click()
            page.locator('details[data-fold="wish-buy"] .nm-t', has_text="Scarf").wait_for()
            self.assertEqual(page.locator("#creators button").evaluate_all("l => l.map(b => b.dataset.creator + ' ' + b.querySelector('.n').textContent)"),
                             ["Snow Co 2"], "its own creators, not none for the last one's price range")
            # a tag chosen on a set, the page reloaded there, then Back to a wishlist: the tag stays with the set
            page.goto(base + f"/#store=Sets&set={ids['Booth: Loved items']}")
            page.locator('details[data-fold="wish-buy"]').wait_for()
            page.goto(base + f"/#store=Sets&set={made}&tags=fox")
            page.reload()
            page.locator(".sethead h2", has_text="Rusk, winter").wait_for()
            page.go_back()
            page.locator(".sethead h2", has_text="Booth: Loved items").wait_for()
            buy = page.locator('details[data-fold="wish-buy"]')
            buy.locator(".nm-t", has_text="Wolf Hoodie").wait_for()
            self.assertEqual(buy.locator(".slot.ext").count(), 4)
            self.assertEqual(page.locator('#status [data-clear="tag"]').count(), 0)
            browser.close()
        self.assertEqual(errors, [])

    def test_a_product_on_another_site_links_there(self):
        """A Jinxxy list's product on a site that isn't one of the stores: Buy on that site, to its page, not No
        store link."""
        sets.SetStore().put_wishlists([{"store": "jinxxy", "list": "Likes", "url": "u", "products": wishlists.jinxxy_products([
            {"url": "https://ko-fi.com/s/abc123", "name": "Fox Tail", "creator": "Kitsu", "price": "5.00 USD"},
            {"url": "https://jinxxy.com/kitsu/FoxEars", "name": "Fox Ears", "creator": "Kitsu", "price": "3.00 USD"}])}])
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.goto(self.srv.entry_url().split("/#")[0] + "/#store=Sets")
            page.locator(".settile", has_text="Jinxxy: Likes").click()
            tail = page.locator(".slot.ext", has_text="Fox Tail")
            tail.wait_for()
            self.assertEqual(tail.locator(".ext-main").get_attribute("href"), "https://ko-fi.com/s/abc123")
            self.assertIn("Buy on ko-fi.com", tail.locator(".ext-what").inner_text())
            self.assertIn("ko-fi.com", tail.locator(".cr").inner_text())
            self.assertIn("Buy on Jinxxy", page.locator(".slot.ext", has_text="Fox Ears").locator(".ext-what").inner_text())
            self.assertEqual(page.locator(".ext-what", has_text="No store link").count(), 0)
            browser.close()
        self.assertEqual(errors, [])

    def test_a_list_read_again_shows_without_opening_it_again(self):
        """Read it again brought a wishlist up to date, but the page kept showing it as it was, until something else
        (making a new list) made it read the sets again. When the read ends, the page reads them again."""
        from hoard import jobs
        first = [{"store": "gumroad", "list": "Winter", "url": "u", "products": [product("Snow Cap", "12.50 USD", "gumroad")]}]
        sets.SetStore().put_wishlists(first)
        again = [{**first[0], "products": first[0]["products"] + [product("Snow Boots", "20 USD", "gumroad")]}]

        class Ctx:
            def close(self):
                pass
        from playwright.sync_api import sync_playwright
        with mock.patch.object(jobs, "reachable", lambda s: True), mock.patch.object(jobs, "launch", lambda *a: Ctx()), \
                mock.patch.object(jobs, "_playwright", lambda: contextlib.nullcontext), \
                mock.patch.dict(wishlists.READERS, {"gumroad": lambda ctx, cfg, progress: time.sleep(1) or again}), \
                sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.goto(self.srv.entry_url().split("/#")[0] + "/#store=Sets")
            page.locator(".settile", has_text="Gumroad: Winter").click()
            page.locator(".slot.ext", has_text="Snow Cap").wait_for()
            self.assertEqual(page.locator(".slot.ext", has_text="Snow Boots").count(), 0)
            page.click("[data-setx=reread]")
            page.locator(".slot.ext", has_text="Snow Boots").wait_for(timeout=15000)   # (no reload, no new list)
            self.assertIn("2 products", page.locator(".sethead").inner_text())
            browser.close()
        self.assertEqual(errors, [])

    def test_read_from_the_stores(self):
        self.assertEqual(self.api("/api/wishlists/read", {"stores": []})["status"], 400)
        lists = [{"store": "gumroad", "list": "Winter", "url": "u", "products": [product("Snow Cap", "12.50 USD", "gumroad")]}]
        from hoard import jobs

        class Ctx:
            def close(self):
                pass
        with mock.patch.object(jobs, "reachable", lambda s: True), mock.patch.object(jobs, "launch", lambda *a: Ctx()), \
                mock.patch.object(jobs, "_playwright", lambda: contextlib.nullcontext), \
                mock.patch.dict(wishlists.READERS, {"gumroad": lambda ctx, cfg, progress: lists,
                                                    "booth": mock.Mock(side_effect=jobs.NotLoggedIn())}):
            self.assertIn(self.api("/api/wishlists/read", {"stores": ["gumroad", "booth"]})["started"], ("started", "queued"))
            for _ in range(200):
                if not self.srv.jobs.state["running"] and self.srv.jobs.history:
                    break
                time.sleep(0.05)
        done = self.srv.jobs.history[0]
        self.assertEqual(done["task"], "wishlists")
        self.assertIn("1 wishlist read, except Booth's", done["message"])
        self.assertIn("Not signed in to Booth", done["message"])
        self.assertEqual([s["name"] for s in sets.SetStore().load()["sets"]], ["Gumroad: Winter"])

    def test_stopped_part_way_keeps_the_lists_read(self):
        """Stop or Force stop while a store's lists were being read (their pictures, say, which wait between pages)
        ended the task as stopped, but the lists already read from the stores before it were thrown away."""
        lists = [{"store": "gumroad", "list": "Winter", "url": "u", "products": [product("Snow Cap", "12.50 USD", "gumroad")]}]
        from hoard import common, jobs

        class Ctx:
            def close(self):
                pass
        with mock.patch.object(jobs, "reachable", lambda s: True), mock.patch.object(jobs, "launch", lambda *a: Ctx()), \
                mock.patch.object(jobs, "_playwright", lambda: contextlib.nullcontext), \
                mock.patch.dict(wishlists.READERS, {"gumroad": lambda ctx, cfg, progress: lists,
                                                    "booth": mock.Mock(side_effect=common.Cancelled())}):
            self.api("/api/wishlists/read", {"stores": ["gumroad", "booth"]})
            for _ in range(200):
                if not self.srv.jobs.state["running"] and self.srv.jobs.history:
                    break
                time.sleep(0.05)
        done = self.srv.jobs.history[0]
        self.assertEqual(done["task"], "wishlists")
        self.assertTrue(done["message"].startswith("Stopped"), done["message"])
        self.assertEqual([s["name"] for s in sets.SetStore().load()["sets"]], ["Gumroad: Winter"], "Gumroad's, kept")


if __name__ == "__main__":
    unittest.main()
