"""Issues #311, #337 and #338: which products are for adults (as their store, their tags or you say), their 18+ mark
and blurred pictures, Adult sets, and the set viewer's question to whoever opens one."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from tests.isolation import IsolatedTestCase
from hoard import adult, config, library, server, sets, wishlists
from hoard.marks import MarkStore
from hoard.tags import TagStore, tag_key

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _pw:
        _pw.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
BODY, HAT, MINE = tag_key("booth", "Night Body"), tag_key("booth", "Straw Hat"), tag_key("local", "My Edit")


class WhoSaysSo(IsolatedTestCase):
    def test_your_word_then_the_stores_then_its_tags_and_name(self):
        marks = {"adult": {"booth:hat"}, "not_adult": {"booth:body"}}
        self.assertEqual(adult.why("booth:hat", marks=marks), "you")
        self.assertIsNone(adult.why("booth:body", flagged=True, tags=["r18"], name="Body (NSFW)", marks=marks), "your word wins")
        self.assertEqual(adult.why("booth:x", flagged=True, tags=["r18"]), "store")
        self.assertEqual(adult.why("booth:x", tags=["avatar", "r-18"]), "tags")
        self.assertEqual(adult.why("booth:x", name="[R-18] Night Body"), "tags")
        self.assertIsNone(adult.why("booth:x", name="Straw Hat", tags=["hat", "summer"]))

    def test_tags_and_names_that_say_so(self):
        for tag in ("r18", "r-18", "r-18g", "nsfw", "adult only", "成人向け", "アダルト", "18禁", "19금"):
            self.assertTrue(adult.by_tags([tag]), tag)
        for tag in ("18", "adult", "r180", "nsfwish", "sfw", "", None, 18):
            self.assertFalse(adult.by_tags([tag]), repr(tag))
        for name in ("Body (NSFW)", "[R-18] Outfit", "R18 version", "Outfit 18+", "衣装 18禁", "r-18g pack"):
            self.assertTrue(adult.by_name(name), name)
        for name in ("Straw Hat", "Model R180", "Route 18", "Unsfw", "18 colours", "PBR18K textures"):
            self.assertFalse(adult.by_name(name), name)

    def test_what_a_stores_page_says(self):
        self.assertIs(adult.on_a_page("booth", {"is_adult": True}), True)
        self.assertIs(adult.on_a_page("booth", {"is_adult": False}), False)
        self.assertIs(adult.on_a_page("jinxxy", 'x\\"nsfw\\":true,y'), True)
        self.assertIs(adult.on_a_page("jinxxy", '{"nsfw": false, "name": "nsfw"}'), False)
        self.assertIsNone(adult.on_a_page("gumroad", "<html>"), "a store that doesn't say")

    def test_one_or_the_other(self):
        store = MarkStore()
        store.change("adult", {BODY}, True)
        store.change("not_adult", {BODY}, True)
        self.assertEqual((store.keys("adult"), store.keys("not_adult")), (frozenset(), frozenset({BODY})))
        store.change("adult", {BODY}, True)
        self.assertEqual((store.keys("adult"), store.keys("not_adult")), (frozenset({BODY}), frozenset()))


class ReadFromTheStores(IsolatedTestCase):
    def test_a_products_page(self):
        def booth(url, hosts):
            return json.dumps({"name": "Night Body", "price": "¥1,000", "shop": {"name": "Kitsu"}, "is_adult": True,
                               "tags": [{"name": "VRChat"}]}), "application/json"
        got = wishlists.from_product_page("https://booth.pm/ja/items/5", booth)
        self.assertIs(got["adult"], True)
        self.assertNotIn("adult", wishlists.from_product_page(
            "https://kitsu.gumroad.com/l/hat", lambda url, hosts: ('<meta property="og:title" content="Hat">', "text/html")),
            "Gumroad's page doesn't say")

    def test_the_library_keeps_it_and_asks_once(self):
        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        lib.replace_store("booth", [
            library.item("booth", "5", name="Night Body", url="https://booth.pm/ja/items/5"),
            library.item("booth", "6", name="Straw Hat", url="https://booth.pm/ja/items/6", store_tags=["hat"])])
        asked = []

        def fetch(url, hosts):
            asked.append(url)
            return json.dumps({"name": "x", "is_adult": "/5." in url, "tags": []}), "application/json"
        self.assertEqual(library.store_tags_from_pages(lib, "booth", fetch), 2, "one read before Hoard asked is read once more")
        by = {i["id"]: i for i in lib.data["items"]}
        self.assertEqual((by["5"]["adult"], by["6"]["adult"]), (True, False))
        self.assertEqual(library.store_tags_from_pages(lib, "booth", fetch), 0, "and not again")
        lib.replace_store("booth", [library.item("booth", "5", name="Night Body", url="https://booth.pm/ja/items/5")])
        self.assertIs(lib.data["items"][0]["adult"], True, "kept through a refresh")
        again = library.Library(lib.path)
        self.assertIs(again.data["items"][0]["adult"], True, "and in the file")

    def test_a_wishlists_cards(self):
        from hoard.stores import booth, jinxxy
        got = booth.wish_booth_products([{"id": "5", "name": "Night Body", "url": "https://booth.pm/en/items/5", "adult": True},
                                         {"id": "6", "name": "Straw Hat", "url": "https://booth.pm/en/items/6", "adult": False}])
        self.assertEqual([p.get("adult") for p in got], [True, None])
        self.assertIn("R-?18", booth.wish_BOOTH_JS)
        got = jinxxy.wish_jinxxy_products([{"name": "Night Body", "url": "https://jinxxy.com/Kitsu/body", "adult": True}])
        self.assertIs(got[0]["adult"], True)
        self.assertIs(sets.clean_product({**got[0]})["adult"], True, "a wishlist remembers it")


class AdultSets(IsolatedTestCase):
    def test_a_shared_set_carries_it(self):
        s = {"name": "Night", "items": [BODY, HAT], "products": {
            BODY: {"store": "booth", "id": "5", "name": "Night Body", "adult": True}, HAT: {"store": "booth", "id": "6", "name": "Straw Hat"}}}
        rows = sets.share_rows(s)
        self.assertEqual((rows[0][6], len(rows[1])), (1, 3), "a mark on the adult product; nothing more on the other")
        code, _ = sets.share_code(s)
        back = sets.from_code(code)
        self.assertIs(back["products"][BODY]["adult"], True)
        self.assertNotIn("adult", back["products"][HAT])
        now = lambda key: {"store": "booth", "name": "Straw Hat", "adult": True} if key == HAT else None   # noqa: E731
        self.assertEqual(sets.share_rows(s, now)[1][6], 1, "as Hoard knows it now (you marked it, say)")
        plain = {**s, "items": [HAT]}
        self.assertEqual(len(sets.share_rows(plain)[0]), 3)

    def test_an_older_hoard_reads_the_same_code(self):
        """The mark is a seventh value in a product's row: a Hoard from before it takes the first six."""
        import base64
        import zlib
        code, _ = sets.share_code({"name": "Night", "items": [BODY], "products": {BODY: {"store": "booth", "name": "Night Body", "adult": True}}})
        body = code[len(sets.CODE_PREFIX):]
        doc = json.loads(zlib.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)), -15))
        self.assertEqual((doc["a"], doc["i"][0][:3], doc["i"][0][6]), (1, ["booth", "", "Night Body"], 1))


class InHoard(IsolatedTestCase):
    """The pages' data: each product's adult mark and who says so, and a set's while any product in it is."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        for kept in (MarkStore().path, TagStore().path, sets.SetStore().path):   # (each test from nothing chosen)
            kept.unlink(missing_ok=True)
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"), "setup_done": True,
                                                      "ui": {"toured": True}}, lan=False)
        with self.srv.lib.lock:   # (in memory only)
            self.srv.lib.data["items"] = [
                library.item("booth", "5", name="Night Body", creator="Kitsu", url="https://booth.pm/ja/items/5", adult=True,
                             thumbnail="https://booth.pximg.net/c/72x72/body.png"),
                library.item("booth", "6", name="Straw Hat", creator="Mochi", url="https://booth.pm/ja/items/6", store_tags=["hat"]),
                library.item("booth", "7", name="Lace Set", creator="Mochi", url="https://booth.pm/ja/items/7", store_tags=["r-18"])]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def call(self, method, path, body=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=20)
        headers = {"X-Hoard-Key": self.srv.key, "Origin": f"http://127.0.0.1:{self.srv.server_address[1]}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, json.loads(data) if data else None

    def test_each_product_and_who_says_so(self):
        items = {i["name"]: i for i in self.call("GET", "/api/library")[1]["items"]}
        self.assertEqual({n: (i["adult"], i["adult_from"]) for n, i in items.items()},
                         {"Night Body": (True, "store"), "Straw Hat": (False, None), "Lace Set": (True, "tags")})
        hat, body = items["Straw Hat"]["tag_key"], items["Night Body"]["tag_key"]
        self.assertEqual(self.call("POST", "/api/marks", {"kind": "adult", "keys": [hat], "on": True})[0], 200)
        self.assertEqual(self.call("POST", "/api/marks", {"kind": "not_adult", "keys": [body], "on": True})[0], 200)
        items = {i["name"]: i for i in self.call("GET", "/api/library")[1]["items"]}
        self.assertEqual((items["Straw Hat"]["adult_from"], items["Night Body"]["adult"], items["Night Body"]["not_adult"]),
                         ("you", False, True), "your word wins, both ways")
        TagStore().change({"action": "assign", "keys": [hat], "add": ["nsfw"]})
        self.call("POST", "/api/marks", {"kind": "adult", "keys": [hat], "on": False})
        self.assertEqual({i["name"]: i for i in self.call("GET", "/api/library")[1]["items"]}["Straw Hat"]["adult_from"], "tags",
                         "a tag of your own says so too")

    def test_a_set_is_adult_while_a_product_in_it_is(self):
        store = sets.SetStore()
        made = store.change({"action": "create", "name": "Night", "items": [BODY, HAT]})["sets"][-1]["id"]
        shown = lambda: next(s for s in self.call("GET", "/api/sets")[1]["sets"] if s["id"] == made)   # noqa: E731
        self.assertTrue(shown()["adult"])
        self.assertEqual([r["adult"] for r in shown()["items"]], [True, False])
        shared = self.call("POST", "/api/sets", {"action": "share", "id": made})[1]
        self.assertIs(sets.from_code(shared["code"])["products"][BODY]["adult"], True, "its link says so")
        store.change({"action": "remove", "id": made, "items": [BODY]})
        self.assertFalse(shown()["adult"], "the last one out: no longer an Adult set")
        self.call("POST", "/api/marks", {"kind": "adult", "keys": [HAT], "on": True})
        self.assertTrue(shown()["adult"], "you marked one in it")

    def test_blurring_is_a_setting(self):
        self.assertTrue(server.display_settings({})["blur_adult"], "on unless you turn it off")
        self.assertFalse(server.display_settings({"display": {"blur_adult": False}})["blur_adult"])
        self.assertEqual(server.apply_settings(self.srv.cfg, {"display": {"blur_adult": False}})["display"]["blur_adult"], False)

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_on_the_pages(self):
        """An adult product's tile says so, carries an 18+ mark, and its picture is blurred until you choose to see
        them; its details say who says so and take your own word; an Adult set is marked as its products are."""
        import hashlib
        library.THUMB_DIR.mkdir(parents=True, exist_ok=True)
        (library.THUMB_DIR / (hashlib.sha1(b"https://booth.pximg.net/c/72x72/body.png").hexdigest() + ".png")).write_bytes(PNG)
        made = sets.SetStore().change({"action": "create", "name": "Night", "items": [BODY, HAT]})["sets"][-1]["id"]
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            tile = lambda name: page.locator("#grid .slot", has_text=name)   # noqa: E731
            tile("Night Body").wait_for()
            self.assertIn("adult", tile("Night Body").get_attribute("class"))
            self.assertIn("for adults (18+)", tile("Night Body").get_attribute("aria-label"))
            self.assertEqual(tile("Night Body").locator(".adult-mark").inner_text(), "18+")
            self.assertEqual(tile("Straw Hat").locator(".adult-mark").count(), 0)
            blurred = "() => getComputedStyle(document.querySelector('#grid .slot.adult .art img')).filter"
            self.assertIn("blur", page.evaluate(blurred))
            tile("Night Body").click()
            page.locator("#detail .d-adult", has_text="its store says so").wait_for()
            art = page.locator("#detail .d-art.adult")
            self.assertIn("blur", art.locator("img").evaluate("e => getComputedStyle(e).filter"))
            art.click()
            self.assertEqual(art.locator("img").evaluate("e => getComputedStyle(e).filter"), "none", "a click shows it")
            page.evaluate("applyDisplay({ ...DATA.display, blur_adult: false })")
            self.assertEqual(page.evaluate(blurred), "none", "Settings: shown")
            page.evaluate("applyDisplay({ ...DATA.display, blur_adult: true })")
            page.locator("#detail [data-adult-mark]", has_text="It isn't for adults").click()
            page.locator(".toast", has_text="Marked as not for adults.").wait_for()
            self.assertNotIn("adult", tile("Night Body").get_attribute("class"))
            tile("Straw Hat").click()
            page.locator("#detail [data-adult-mark]", has_text="Mark as 18+").click()
            page.locator(".toast", has_text="Marked as 18+.").wait_for()
            page.locator("#detail .d-adult", has_text="you marked it").wait_for()
            self.assertEqual(MarkStore().keys("adult"), frozenset({HAT}))
            page.click('#storeSeg [data-store="Sets"]')
            night = page.locator(f'#setView .settile[data-setopen="{made}"]')
            night.wait_for()
            self.assertIn("adult", night.get_attribute("class"))
            self.assertEqual(night.locator(".adult-mark").inner_text(), "18+")
            night.click()
            page.locator(".sethead.adult .set-adult", has_text="asks its viewer's age first").wait_for()
            self.assertEqual(page.locator("#setView .slot.ext.adult, #grid .slot.adult").count(), 1, "the hat, in the set")
            self.assertEqual(errors, [])
            browser.close()


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class TheViewerAsks(IsolatedTestCase):
    """Issue #337: an Adult set's link asks whether its viewer is 18 or older before showing it, and keeps the answer
    (one word, in a cookie for that page) so it isn't asked again. Hoard never asks for ID."""

    def test_the_question_and_its_answers(self):
        site = Path(__file__).resolve().parent.parent / "site"
        adult_set = sets.share_link(sets.share_code({"name": "Night", "photos": ["https://i.imgur.com/a.png"], "items": [BODY, HAT], "products": {
            BODY: {"store": "booth", "name": "Night Body", "url": "https://booth.pm/ja/items/5", "adult": True},
            HAT: {"store": "booth", "name": "Straw Hat", "url": "https://booth.pm/ja/items/6"}}})[0])
        all_adult = sets.share_link(sets.share_code({"name": "Late", "items": [BODY], "products": {
            BODY: {"store": "booth", "name": "Night Body", "adult": True}}})[0])
        plain = sets.share_link(sets.share_code({"name": "Summer", "items": [HAT], "products": {HAT: {"store": "booth", "name": "Straw Hat"}}})[0])
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context()
            page = ctx.new_page()

            def serve(route):
                url = route.request.url
                if url.startswith("https://hoard.furryup.link/"):
                    name = url.split("hoard.furryup.link/", 1)[1].split("#")[0].split("?")[0]
                    kind = {"html": "text/html", "js": "text/javascript", "css": "text/css"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
                    return route.fulfill(path=str(site / name), content_type=kind) if (site / name).is_file() else route.fulfill(status=404)
                return route.fulfill(body=PNG, content_type="image/png")
            page.route("**/*", serve)
            names = lambda: page.locator(".sv-text b").all_inner_texts()   # noqa: E731
            page.goto(plain)
            page.locator("#setView").wait_for()
            self.assertTrue(page.locator("#setAge").is_hidden(), "a set with nothing for adults asks nothing")
            self.assertEqual(ctx.cookies(), [])
            page.goto(adult_set)   # (another set in the same page: the viewer reads it again by itself)
            page.locator("#setAge").wait_for()
            self.assertTrue(page.locator("#setView").is_hidden(), "nothing shown before the answer")
            self.assertEqual(names(), [])
            page.click("#ageNo")
            page.locator("#setView").wait_for()
            self.assertEqual(names(), ["Straw Hat"], "under 18: without the products for adults")
            self.assertTrue(page.locator("#setPhotos").is_hidden(), "or the sharer's photos")
            self.assertIn("1 product for adults isn't shown", page.locator("#setAgeNote").inner_text())
            (cookie,) = ctx.cookies()
            self.assertEqual((cookie["name"], cookie["value"], cookie["path"], cookie["secure"]), ("hoard_age", "minor", "/set.html", True))
            self.assertGreater(cookie["expires"], __import__("time").time() + 300 * 86400, "for a year")
            page.goto(all_adult)
            page.locator("#setProblem").wait_for()
            self.assertIn("for adults", page.locator("#setProblemWhy").inner_text())
            page.click("#ageAgain")   # the answer forgotten, and asked again
            page.locator("#setAge").wait_for()
            self.assertEqual(ctx.cookies(), [])
            page.click("#ageYes")
            page.locator("#setView").wait_for()
            self.assertEqual(names(), ["Night Body"])
            page.goto(adult_set)
            page.locator(".sv-text b", has_text="Straw Hat").wait_for()   # (not asked again)
            self.assertEqual(names(), ["Night Body", "Straw Hat"])
            self.assertEqual(page.locator(".sv-item .adult-mark").count(), 1)
            self.assertFalse(page.locator("#setPhotos").is_hidden())
            self.assertEqual(ctx.cookies()[0]["value"], "adult")
            browser.close()

    def test_the_policy_says_what_the_cookie_is(self):
        root = Path(__file__).resolve().parent.parent
        policy = (root / "PRIVACY.md").read_text("utf-8")
        self.assertIn("## The set viewer's age question", policy)
        for said in ("`hoard_age`", "`adult` or `minor`", "one year", "Hoard never asks for ID"):
            self.assertIn(said, policy)
        page = (root / "site" / "set.html").read_text("utf-8")
        self.assertIn("PRIVACY.md#the-set-viewers-age-question", page)
        self.assertIn("Hoard never asks for ID", page)
        js = (root / "site" / "set.js").read_text("utf-8")
        self.assertIn("hoard_age", js)
        self.assertNotIn("fetch(", js.split("An Adult set asks", 1)[1].split("function forAge", 1)[0], "the answer goes nowhere")


if __name__ == "__main__":
    unittest.main()
