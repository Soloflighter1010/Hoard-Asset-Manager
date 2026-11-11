"""Quick refresh (issue #300): each library and list read only as far as its first 2 pages, or its first 50 products,
whichever comes first, and what it didn't reach kept as it was. The stores here are stand-ins: made-up pages and
answers, shaped like each store's."""
import os
import tempfile
import types
import unittest
from tests.isolation import IsolatedTestCase
from pathlib import Path
from unittest import mock


from hoard import common, config, itch, jobs, library, sets, wishlists  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False

QUICK = {"_quick": True}


class TheRule(IsolatedTestCase):
    def test_two_pages_or_fifty_products_whichever_comes_first(self):
        self.assertEqual((common.QUICK_PAGES, common.QUICK_ITEMS), (2, 50))
        self.assertFalse(common.quick_done({}, 40, 5000), "a full refresh reads on")
        self.assertFalse(common.quick_done(QUICK, 1, 49))
        self.assertTrue(common.quick_done(QUICK, 2, 3), "two pages, however few on them")
        self.assertTrue(common.quick_done(QUICK, 1, 50), "fifty products, on however few pages")


class Gumroad(IsolatedTestCase):
    def read(self, per, total, cfg, archived=False):
        """Gumroad's library as gumroad_cards reads it, per a page: the cards it gives, and the pages asked for."""
        asked = []

        def read_props(params):
            asked.append(params)
            start = (params["page"] - 1) * per
            return {"results": [{"id": i} for i in range(start, min(total, start + per))],
                    "pagination": {"pages": -(-total // per)}}
        return list(library.gumroad_cards(read_props, archived, 0, None, cfg)), asked

    def test_the_start_of_the_library(self):
        cards, asked = self.read(30, 200, QUICK)
        self.assertEqual((len(cards), len(asked)), (50, 2), "fifty, before the second page was done")
        self.assertEqual([c["id"] for c in cards], list(range(50)), "the newest first, as the store has them")
        cards, asked = self.read(10, 200, QUICK)
        self.assertEqual((len(cards), len(asked)), (20, 2), "two pages, when they hold fewer than fifty")
        cards, asked = self.read(100, 200, QUICK)
        self.assertEqual((len(cards), len(asked)), (50, 1))
        cards, asked = self.read(30, 200, {})
        self.assertEqual((len(cards), len(asked)), (200, 7), "a full refresh reads all of it")

    def test_the_archived_ones_are_a_list_of_their_own(self):
        cards, asked = self.read(30, 200, QUICK, archived=True)
        self.assertEqual(len(cards), 100)
        self.assertEqual([("show_archived_only" in p) for p in asked], [False, False, True, True])


class Booth(IsolatedTestCase):
    class Page:
        """Booth's library and gifts: per cards a page, total in each."""

        def __init__(self, per, total):
            self.url, self.per, self.total, self.asked = "", per, total, []

        def wait_for_timeout(self, ms):
            pass

        def evaluate(self, js):
            path, _, n = self.url.partition("?page=")
            start = (int(n) - 1) * self.per
            kind = "gift" if path.endswith("/gifts") else "own"
            return [{"id": f"{kind}{i}", "name": f"Item {i}", "creator": "Kitsu", "creator_url": "", "thumbnail": "",
                     "url": "", "order_url": "", "files": []}
                    for i in range(start, min(self.total[kind], start + self.per))]

    def read(self, per, total, cfg):
        page = self.Page(per, total)

        def goto(p, url):
            p.url = url
            p.asked.append(url)
        with mock.patch.object(library, "goto", goto), mock.patch.object(library, "has_password_field", lambda p: False):
            cards = library.booth_cards(page, {"booth": {"include_gifts": True, "include_free": False}, **cfg}, 0)
        return [b["id"] for b, _gift, _base in cards], page.asked

    def test_each_listing_from_its_start(self):
        ids, asked = self.read(20, {"own": 45, "gift": 5}, QUICK)
        self.assertEqual(ids, [f"own{i}" for i in range(40)] + [f"gift{i}" for i in range(5)])
        self.assertEqual([u.rsplit("/", 1)[-1] for u in asked], ["library?page=1", "library?page=2", "gifts?page=1", "gifts?page=2"])
        ids, asked = self.read(60, {"own": 200, "gift": 0}, QUICK)
        self.assertEqual(len([i for i in ids if i.startswith("own")]), 50, "fifty of the sixty on its first page")
        self.assertEqual(asked[0].rsplit("/", 1)[-1], "library?page=1")
        self.assertNotIn("library?page=2", " ".join(asked))
        ids, _ = self.read(20, {"own": 45, "gift": 5}, {})
        self.assertEqual(len(ids), 50, "a full refresh: all 45 and the 5 gifts")


class Jinxxy(IsolatedTestCase):
    def test_the_inventory_stops_scrolling_at_fifty(self):
        page = types.SimpleNamespace(get_by_role=lambda *a, **k: types.SimpleNamespace(count=lambda: 0),
                                     mouse=types.SimpleNamespace(wheel=lambda x, y: None), wait_for_timeout=lambda ms: None)
        shown = []

        def read():
            shown.append(min(12 * (len(shown) + 1), 130))
            return shown[-1]
        library.scroll_inventory(page, read, most=50)
        self.assertEqual(shown[-1], 60, "it stops once fifty are shown")
        shown.clear()
        library.scroll_inventory(page, read)
        self.assertEqual(shown[-1], 130, "and a full refresh scrolls to the end")


class Payhip(IsolatedTestCase):
    def read(self, per, total, cfg):
        """One shop's library, per cards a page; the cards read and the pages visited."""
        page = types.SimpleNamespace(url="", visits=[])

        def visit(p, url, wait, progress):
            p.url = url
            p.visits.append(url)

        def evaluate(js):
            n = int(page.url.partition("?page=")[2] or 1)
            start = (n - 1) * per
            more = start + per < total
            return {"shop": "Mochi", "next": f"https://payhip.com/Mochi/b-account?page={n + 1}" if more else None,
                    "cards": [{"id": f"p{i}"} for i in range(start, min(total, start + per))]}
        page.evaluate = evaluate
        with mock.patch.object(library, "goto_past_check", visit), mock.patch.object(library, "settle", lambda *a, **k: None), \
                mock.patch.object(library, "has_password_field", lambda p: False):
            cards = library.read_payhip_shop(page, "https://payhip.com/Mochi", {**config.load_config(), "request_delay": 0, **cfg}, lambda m: None)
        return cards, page.visits

    def test_each_shop_from_its_start(self):
        cards, visits = self.read(15, 100, QUICK)
        self.assertEqual((len(cards), len(visits)), (30, 2))
        cards, visits = self.read(40, 100, QUICK)
        self.assertEqual((len(cards), len(visits)), (50, 2))
        cards, visits = self.read(60, 100, QUICK)
        self.assertEqual((len(cards), len(visits)), (50, 1))
        cards, visits = self.read(15, 100, {})
        self.assertEqual((len(cards), len(visits)), (100, 7))


class Itch(IsolatedTestCase):
    def test_its_api_from_the_start(self):
        for per, cfg, want in ((50, QUICK, (50, 1)), (20, QUICK, (40, 2)), (20, {}, (130, 7))):
            asked = []

            def call(sess, path, **q):
                asked.append(q["page"])
                start = (q["page"] - 1) * per
                return {"per_page": per, "owned_keys": [{"id": i, "game": {"id": i}} for i in range(start, min(130, start + per))]}
            with mock.patch.object(itch, "call", call):
                keys = itch.owned_keys(None, 0, lambda m: None, cfg)
            self.assertEqual((len(keys), len(asked)), want, (per, cfg))


NAMES = ["", "Rusk", "Mochi", "Anko", "Yuzu", "Kinako", "Matcha", "Sakura", "Ume", "Kuromitsu"]   # (a product's key is its name)


def product(n, store="booth"):
    return {"store": store, "name": NAMES[n], "creator": "Kitsu", "url": f"https://booth.pm/en/items/{5000 + n}",
            "price": wishlists.parse_price(f"{n * 100} JPY")}


class Wishlists(IsolatedTestCase):
    def setUp(self):
        self.store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")
        self.store.put_wishlists([{"store": "booth", "list": "Loved items", "products": [product(n) for n in range(1, 6)]}])

    def names(self):
        (w,) = self.store.load()["sets"]
        return [w["products"][k]["name"] for k in w["items"]]

    def test_a_list_read_partly_keeps_what_it_didnt_reach(self):
        self.store.put_wishlists([{"store": "booth", "list": "Loved items", "partial": True,
                                   "products": [product(9), product(2)]}])
        self.assertEqual(self.names(), ["Kuromitsu", "Mochi", "Rusk", "Anko", "Yuzu", "Kinako"],
                         "the new one first, as the store has it, then the rest as they were")
        self.store.put_wishlists([{"store": "booth", "list": "Loved items", "products": [product(9), product(2)]}])
        self.assertEqual(self.names(), ["Kuromitsu", "Mochi"], "a list read to its end holds what it does now")

    def test_one_list_asked_for(self):
        """Issue #331: a quick refresh of one wishlist names it to its store's reader, by the name the wishlist keeps."""
        self.assertTrue(wishlists.wanted({}, "Anything"), "every list, when none is named")
        self.assertTrue(wishlists.wanted({"_only_list": "Winter"}, "Winter"))
        self.assertTrue(wishlists.wanted({"_only_list": "Winter"}, " Winter\u200b"), "as the wishlist keeps it")
        self.assertFalse(wishlists.wanted({"_only_list": "Winter"}, "Summer"))

    def test_one_jinxxy_list_past_the_start_of_the_index(self):
        """A quick refresh of one Jinxxy list of yours reads the index of your lists to its end to find it (it may be
        past a quick refresh's 2 pages), and reads only that list."""
        from hoard.stores import jinxxy
        index, pages, seen = wishlists.JX_LISTS, {}, []
        for n in range(1, 5):
            pages[index if n == 1 else f"{index}?page={n}"] = {
                "cards": [], "lists": [{"url": f"https://jinxxy.com/my/lists/{n}", "name": f"List {n}"}],
                "next": f"{index}?page={n + 1}" if n < 4 else None}
            pages[f"https://jinxxy.com/my/lists/{n}"] = {"cards": [], "lists": [], "next": None}

        class Page:
            url = ""

            def evaluate(self, js, url):
                return pages[self.url]

            def close(self):
                pass

        def goto(page, url):
            seen.append(url)
            page.url = url
        ctx = type("Ctx", (), {"new_page": lambda self: Page()})()
        with mock.patch.object(wishlists, "goto", goto), mock.patch.object(wishlists, "settle", lambda *a: None), \
                mock.patch.object(wishlists, "_signed_in", lambda *a: None), mock.patch.object(wishlists.time, "sleep", lambda s: None):
            got = jinxxy.wish_read_jinxxy(ctx, {"_quick": True, "_only_list": "List 4", "request_delay": 0}, lambda m: None)
        self.assertEqual([x["list"] for x in got], ["List 4"])
        self.assertEqual(seen[-1], "https://jinxxy.com/my/lists/4", "only that list read")

    def test_payhips_lists_cut_at_fifty(self):
        cards = [{"id": f"c{i}", "name": f"Item {i}", "url": f"https://payhip.com/b/c{i}", "list": "Wishlist"} for i in range(70)]
        with mock.patch.object(wishlists, "payhip_products", lambda cs: list(cs)):
            (quick,) = wishlists._payhip_lists(cards, "https://payhip.com/Mochi", "u", True)
            (full,) = wishlists._payhip_lists(cards, "https://payhip.com/Mochi", "u")
        self.assertEqual((len(quick["products"]), quick.get("partial")), (50, True))
        self.assertEqual((len(full["products"]), full.get("partial")), (70, None))

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_booths_loved_items_two_pages(self):
        from playwright.sync_api import sync_playwright
        from tests.test_wishlists import BoothPages
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()

            def route(r):
                if r.request.url.startswith(wishlists.BOOTH_WISHES):
                    r.fulfill(status=200, content_type="text/html; charset=utf-8", body=BoothPages.PAGE)
                else:
                    r.abort()
            ctx.route("**/*", route)
            (loved,) = wishlists.read_booth(ctx, {"request_delay": 0, **QUICK}, lambda m: None)
            browser.close()
        self.assertEqual([x["name"] for x in loved["products"]], [f"Item {i}" for i in range(1, 41)], "two pages of three")
        self.assertIs(loved.get("partial"), True)

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_booths_one_list(self):
        """Issue #331: asked for Loved items alone, Booth's reader reads it and goes no further; asked for a list of
        your own, it doesn't read Loved items first."""
        from playwright.sync_api import sync_playwright
        from tests.test_wishlists import BoothPages
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            asked = []

            def route(r):
                asked.append(r.request.url)
                if r.request.url.startswith(wishlists.BOOTH_WISHES):
                    r.fulfill(status=200, content_type="text/html; charset=utf-8", body=BoothPages.PAGE)
                else:
                    r.abort()
            ctx.route("**/*", route)
            lists = wishlists.read_booth(ctx, {"request_delay": 0, **QUICK, "_only_list": "Loved items"}, lambda m: None)
            self.assertEqual([x["list"] for x in lists], ["Loved items"])
            pages = len(asked)
            lists = wishlists.read_booth(ctx, {"request_delay": 0, **QUICK, "_only_list": "Not there"}, lambda m: None)
            browser.close()
        self.assertEqual(lists, [])
        self.assertEqual(len(asked) - pages, 1, "only the page that lists your lists")


class NoBrowser:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


class Window:
    def close(self):
        pass


class TheTask(IsolatedTestCase):
    def setUp(self):
        self.lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        self.lib.replace_store("booth", [library.item("booth", n, name=f"Item {n}", creator="Kitsu") for n in ("1", "2", "3")])
        self.job = jobs.Jobs(config.load_config(), self.lib)
        self.told = []

    def fetch(self, ctx, run_cfg, progress):
        self.told.append(run_cfg.get("_quick"))
        return [library.item("booth", "1", name="Item 1 (new name)", creator="Kitsu"), library.item("booth", "9", name="Item 9", creator="Kitsu")]

    def refresh(self, quick):
        tags = []
        with mock.patch.multiple(jobs, reachable=lambda store, timeout=5.0: True, _playwright=lambda: NoBrowser,
                                 launch=lambda *a, **k: Window(), cache_images=lambda *a, **k: 0), \
                mock.patch.dict(jobs.FETCHERS, {"booth": self.fetch}), mock.patch("hoard.downloader.build_catalog", lambda *a: None), \
                mock.patch.object(library, "store_tags_from_pages", lambda *a, **k: tags.append(a[1])):
            self.job._refresh(["booth"], quick=quick)
        return sorted(i["name"] for i in self.lib.data["items"] if i["store"] == "booth"), tags

    def test_what_a_quick_refresh_didnt_reach_is_kept(self):
        names, tags = self.refresh(True)
        self.assertEqual(names, ["Item 1 (new name)", "Item 2", "Item 3", "Item 9"])
        self.assertEqual(self.told, [True], "the reader was told")
        self.assertEqual(tags, [], "no products' pages read for their tags")
        self.assertEqual(self.lib.data["stores"]["booth"]["count"], 4)
        self.assertEqual(self.job.state["task"], "quick-refresh")
        names, tags = self.refresh(False)
        self.assertEqual(names, ["Item 1 (new name)", "Item 9"], "a full refresh drops what's gone")
        self.assertEqual(tags, ["booth"])

    def test_then_the_wishlists_you_keep(self):
        """Only the stores you already read wishlists from: a quick refresh never starts reading a store's lists."""
        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HOARD_DATA_DIR": tmp}):
            sets.SetStore().put_wishlists([{"store": "booth", "list": "Loved items", "products": [product(1)]}])
            asked = []

            def refreshed(stores, skip_imported=False, quick=False):
                asked.append(("refresh", stores, skip_imported, quick))
                self.job._set(message="Library updated")
                return []

            def wished(stores, quick=False):
                asked.append(("wishlists", stores, quick))
                self.job._set(task="wishlists", message="1 wishlist read")
            with mock.patch.object(self.job, "_refresh", refreshed), mock.patch.object(self.job, "_wishlists", wished):
                self.job._quick_refresh(["booth", "gumroad"])
        self.assertEqual(asked, [("refresh", ["booth", "gumroad"], True, True), ("wishlists", ["booth"], True)])
        self.assertEqual(self.job.state["message"], "Library updated. 1 wishlist read")
        self.assertEqual(self.job.state["task"], "quick-refresh")
        self.assertFalse(self.job.state.get("partial"))

    def test_not_the_wishlists_of_a_store_kept_by_importing(self):
        """A store whose library comes from pages you import isn't read by a quick refresh, and nor are its lists."""
        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HOARD_DATA_DIR": tmp}):
            sets.SetStore().put_wishlists([{"store": "booth", "list": "Loved items", "products": [product(1)]}])
            self.lib.data["stores"].setdefault("booth", {})["source"] = "import"
            asked = []
            with mock.patch.object(self.job, "_refresh", lambda *a, **k: self.job._set(message="Library updated") or []), \
                    mock.patch.object(self.job, "_wishlists", lambda *a, **k: asked.append(a)):
                self.job._quick_refresh(["booth"])
        self.assertEqual(asked, [])

    def test_a_refresh_that_failed_goes_no_further(self):
        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HOARD_DATA_DIR": tmp}):
            sets.SetStore().put_wishlists([{"store": "booth", "list": "Loved items", "products": [product(1)]}])
            asked = []
            with mock.patch.object(self.job, "_refresh", lambda *a, **k: self.job._set(error="You're offline.") or ["booth"]), \
                    mock.patch.object(self.job, "_wishlists", lambda *a, **k: asked.append(a)):
                self.job._quick_refresh(["booth"])
        self.assertEqual(asked, [])

    def test_the_task_has_its_name(self):
        self.assertEqual(jobs.describe_job("quick-refresh", ["booth", "gumroad"]), "Quick refresh: Booth, Gumroad")
        self.assertIn("quick-refresh", jobs.WATCHED)


if __name__ == "__main__":
    unittest.main()
