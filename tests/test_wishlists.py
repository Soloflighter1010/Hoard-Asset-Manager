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

from hoard import sets, wishlists
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
class SavedPages(unittest.TestCase):
    def test_each_stores_page(self):
        got = {r["filename"]: r for r in wishlists.from_saved_pages(saved("booth.html", "gumroad.html", "jinxxy-likes.html", "payhip.html"))}
        (booth,) = got["booth.html"]["lists"]
        self.assertEqual((booth["store"], booth["list"]), ("booth", "Loved items"))
        self.assertEqual([(p["name"], p["creator"], p["price"]["text"], p["url"]) for p in booth["products"]],
                         [("Fox Hoodie【5 avatars】", "Kitsu Studio", "1,500 JPY", "https://booth.pm/items/1001"),
                          ("Mochi Boots", "Mochi Works", "800 JPY", "https://booth.pm/items/1002")],
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
                          ("gumroad", "Snowflakes", "https://snowy.gumroad.com/l/flakes")])
        self.assertEqual(likes["products"][0]["creator"], "kitsu")
        self.assertIn("foxears.png", likes["products"][0]["thumbnail"], "its picture, not its creator's")
        (pay,) = got["payhip.html"]["lists"]
        self.assertEqual((pay["list"], pay["products"][0]["name"], pay["products"][0]["price"]["amount"]), ("citrus.example: Summer", "Citrus Hat", 5.0))

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


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class InHoard(unittest.TestCase):
    def setUp(self):
        from hoard import config, library, server
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
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
            self.assertEqual(page.locator(".slot.ext", has_text="Mochi Boots").count(), 0, "yours: a tile in the library, not one to buy")
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


if __name__ == "__main__":
    unittest.main()
