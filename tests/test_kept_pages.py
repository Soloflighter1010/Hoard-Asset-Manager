"""A store page a read couldn't use, kept for a support report (hoard/kept_pages.py): its shape and never its words,
kept when a read fails on the page or comes back empty, gone once the store reads fine or you sign out, and put in
Create report's file with its start in the preview."""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hoard import config, diagnostics, jobs, library, kept_pages  # noqa: E402

PAGE = """<!doctype html><html lang="ja"><head><title>kitsu_fan's library</title><style>.a{color:red}</style>
<script>window.token = "tok_secret_123";</script>
<script type="application/json" data-page="app">{"props": {"user": {"email": "me@example.com", "id": 4242},
"results": [{"name": "Fox Ears", "creator": "Kitsu Studio", "price": 1500}]}}</script>
</head><body><!-- for kitsu_fan -->
<div class="library-card card-42" id="item-98765" data-testid="library-card" data-product-id="98765" title="Fox Ears">
<a href="https://booth.pm/ja/items/98765?ref=lib#top"><img src="https://booth.pximg.net/c/72x72/i/98765/fox.jpg"
 srcset="https://booth.pximg.net/a/1.jpg 1x, https://booth.pximg.net/a/2.jpg 2x" alt="Fox Ears"></a>
<a href="https://kitsu-shop.example.com/b/fox-ears">ショップ</a><a href="mailto:me@example.com">me</a>
<span>Kitsu Studio · ¥1,500 · キツネ耳</span><input name="license" value="ABCD-1234-EFGH">
<button type="button" style="background:url(https://example.com/me.png)">ダウンロード</button>
</div></body></html>"""
SECRETS = ("kitsu", "Fox", "Ears", "Kitsu", "Studio", "1500", "1,500", "98765", "4242", "me@example.com", "example",
           "tok_secret", "ABCD", "キツネ", "ショップ", "ダウンロード", "lib#top", "me.png")


class ItsShape(IsolatedTestCase):

    def test_no_word_of_it_is_kept(self):
        shaped = kept_pages.shape(PAGE)
        for word in SECRETS:
            with self.subTest(word=word):
                self.assertNotIn(word, shaped)

    def test_its_structure_is(self):
        """What a reader looks for: the tags, their classes and ids (digits aside), the store's own attributes, the
        store's site and the words of its addresses' paths, the JSON's keys."""
        shaped = kept_pages.shape(PAGE)
        for kept in ('<div class="library-card card-00" id="item-00000" data-testid="library-card"',
                     'href="https://booth.pm/ja/items/00000?ref=xxx"', 'src="https://booth.pximg.net/c/00x00/x/00000/xxx.xxx"',
                     '<script type="application/json" data-page="app">{"props": {"user": {"email": "xx@xxxxxxx.xxx", "id": 0}',
                     '"name": "xxx xxxx"', '<input name="license" value="xxxx-0000-xxxx">', '<button type="button"',
                     'href="mailto:x"', "<!doctype html>", '<html lang="ja">'):
            with self.subTest(kept=kept):
                self.assertIn(kept, shaped)
        self.assertNotIn("<!--", shaped, "comments left out")
        self.assertIn("/* its script */", shaped)
        self.assertIn("/* its style */", shaped)

    def test_another_site_is_blanked(self):
        """A creator's own shop site would say whose shop you bought from."""
        self.assertEqual(kept_pages.address("https://kitsu-shop.example.com/b/fox-ears?x=1"), "https://xxxxx-xxxx.xxxxxxx.xxx/b/xxx-xxxx?x=0")
        self.assertEqual(kept_pages.address("https://kitsu.payhip.com/b/AbC12"), "https://xxxxx.payhip.com/b/xxx00",
                         "a creator's shop on a store: the store's part kept, whose shop it is blanked")
        self.assertEqual(kept_pages.address("https://accounts.booth.pm/library"), "https://accounts.booth.pm/library")
        self.assertEqual(kept_pages.address("https://booth.pm/x?eyJhbGciOiJIUzI1NiJ9abc&page=2&sortBy=new"),
                         f"https://booth.pm/x?{kept_pages.blank('eyJhbGciOiJIUzI1NiJ9abc')}&page=0&sortBy=xxx",
                         "a query's name kept only when it's a name (a token isn't)")
        self.assertEqual(kept_pages.address("javascript:alert(1)"), "javascript:x")

    def test_the_shops_you_bought_from_arent_named(self):
        """Booth's library links each purchase's shop (<shop>.booth.pm): which shops, with the count of items, would
        say what you bought."""
        shaped = kept_pages.shape((REPO / "tests" / "data" / "stores" / "booth" / "library.html").read_text("utf-8"))
        self.assertNotRegex(shaped, r"shop\d+\.booth\.pm")
        self.assertIn(".booth.pm", shaped, "that it's a shop on Booth is still said")

    def test_json_in_an_attribute(self):
        """Inertia (Gumroad) can put the whole page's data in data-page: its JSON is blanked like a script's."""
        page = ('<div id="app" data-page="{&quot;props&quot;:{&quot;user&quot;:{&quot;email&quot;:&quot;alice.smith@'
                'example.com&quot;,&quot;name&quot;:&quot;Alice Smith&quot;},&quot;alice.smith@example.com&quot;:1}}">'
                '</div><script data-page="app" type="application/json">{"props": {}}</script>')
        shaped = kept_pages.shape(page)
        for word in ("alice", "Alice", "Smith", "example"):
            self.assertNotIn(word, shaped)
        self.assertIn('"email": "xxxxx.xxxxx@xxxxxxx.xxx"', shaped.replace("&quot;", '"'), "its keys kept")
        self.assertIn('data-page="app"', shaped, "a plain name in a structural attribute kept")
        shaped = kept_pages.shape((REPO / "tests" / "data" / "stores" / "gumroad" / "wishlist.html").read_text("utf-8"))
        for word in ("Winter", "snowcap", "Snow Cap", "Mochi", "mochi"):
            self.assertNotIn(word, shaped)

    def test_a_structural_attribute_holding_words(self):
        shaped = kept_pages.shape('<div class="card" id="kitsu.fan@example.com" data-testid="Fox Ears キツネ">x</div>')
        self.assertNotIn("kitsu", shaped)
        self.assertNotIn("Fox", shaped)
        self.assertIn('class="card"', shaped)

    def test_a_page_too_long_is_cut(self):
        with mock.patch.object(kept_pages, "MAX_PAGE", 100):
            shaped = kept_pages.shape("<p>" + "word " * 500 + "</p>")
        self.assertLess(len(shaped), 200)
        self.assertIn("cut here", shaped)

    def test_broken_markup_is_read_all_the_same(self):
        shaped = kept_pages.shape("<div class='a'><p>Fox Ears<span title=\"Kitsu\">x</div></body>")
        self.assertNotIn("Fox", shaped)
        self.assertNotIn("Kitsu", shaped)


class Kept(IsolatedTestCase):
    def setUp(self):
        for store in ("booth", "gumroad"):
            kept_pages.forget(store)

    def test_kept_found_and_forgotten(self):
        kept_pages.keep("booth", PAGE, "layout", "https://accounts.booth.pm/library?page=2", {"items": 0})
        [(info, page)] = kept_pages.kept("booth")
        self.assertEqual((info["store"], info["problem"], info["address"], info["found"]),
                         ("booth", "layout", "https://accounts.booth.pm/library?page=0", {"items": 0}))
        self.assertNotIn("Fox", page, "only its shape is ever written")
        self.assertEqual(kept_pages.kept("gumroad"), [])
        kept_pages.forget("booth")
        self.assertEqual(kept_pages.kept(), [])

    def test_never_a_file_outside_its_folder(self):
        for name in ("../config", "booth/../x", "", "BOOTH"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                kept_pages.keep(name, PAGE, "layout")
        self.assertEqual(kept_pages.kept("../library"), [])

    def test_the_page_is_read_again_in_its_browser(self):
        page = mock.MagicMock()
        page.content.return_value = PAGE
        page.url = "https://accounts.booth.pm/library"
        page.evaluate.return_value = {"cards": []}
        ctx = mock.MagicMock()
        ctx.new_page.return_value = page
        cfg = config.load_config()
        with mock.patch("hoard.browser.settle"):
            self.assertTrue(kept_pages.capture(ctx, cfg, "booth", "empty"))
        page.goto.assert_called_once()
        self.assertEqual(page.goto.call_args[0][0], "https://accounts.booth.pm/library")
        page.close.assert_called_once()
        [(info, _page)] = kept_pages.kept("booth")
        self.assertEqual((info["problem"], info["found"]["items"]), ("empty", 0))
        self.assertFalse(kept_pages.capture(ctx, cfg, "booth", "signin"), "not for a sign-in, a block or the network")
        self.assertFalse(kept_pages.capture(None, cfg, "booth", "layout"))

    def test_not_after_the_browser_stopped_answering(self):
        """Reading the page again would only wait on it too (new_page and the reader's script have no time limit)."""
        ctx = mock.MagicMock()
        for error in (RuntimeError("Target page, context or browser has been closed"),
                      type("TimeoutError", (Exception,), {})("Timeout 30000ms exceeded")):
            with self.subTest(error=str(error)):
                self.assertFalse(kept_pages.capture(ctx, config.load_config(), "booth", "layout", error))
        ctx.new_page.assert_not_called()

    def test_a_reader_that_failed_isnt_run_again(self):
        page = mock.MagicMock()
        page.content.return_value = PAGE
        page.url = "https://accounts.booth.pm/library"
        ctx = mock.MagicMock()
        ctx.new_page.return_value = page
        with mock.patch("hoard.browser.settle"):
            self.assertTrue(kept_pages.capture(ctx, config.load_config(), "booth", "layout", RuntimeError("no cards")))
        page.evaluate.assert_not_called()
        page.set_default_timeout.assert_called_once_with(kept_pages.CAPTURE_SECONDS * 1000)
        [(info, _page)] = kept_pages.kept("booth")
        self.assertEqual(info["found"], {"reader": "failed on this page"})

    def test_a_page_that_wont_load_keeps_nothing(self):
        page = mock.MagicMock()
        page.goto.side_effect = RuntimeError("Timeout 30000ms exceeded")
        ctx = mock.MagicMock()
        ctx.new_page.return_value = page
        self.assertFalse(kept_pages.capture(ctx, config.load_config(), "booth", "layout"))
        self.assertEqual(kept_pages.kept("booth"), [])
        page.close.assert_called_once()


class InTheReport(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        patch = mock.patch.object(diagnostics, "support_report_dir", return_value=self.tmp / "reports")
        patch.start()
        self.addCleanup(patch.stop)
        for store in ("booth", "gumroad"):
            kept_pages.forget(store)
        self.cfg = {**config.load_config(), "root": str(self.tmp / "downloads")}
        self.lib = library.Library(self.tmp / "library.json")

    def report(self, **context):
        made = diagnostics.create_support_report(self.cfg, self.lib, context=context)
        with zipfile.ZipFile(made["path"]) as z:
            return made, {name: z.read(name).decode("utf-8") for name in z.namelist()}

    def test_the_stores_page_is_in_its_report(self):
        kept_pages.keep("booth", PAGE, "layout", "https://accounts.booth.pm/library", {"items": 0})
        kept_pages.keep("gumroad", "<p>Other</p>", "empty", "https://gumroad.com/library", {"page_data": False})
        made, files = self.report(source="store", store="booth", error="Couldn't read the library")
        self.assertIn("store-page-booth.html", files)
        self.assertNotIn("store-page-gumroad.html", files, "the report's store's page alone")
        self.assertIn("Store page: booth", files["report.txt"])
        self.assertIn("the reader found 0 items", files["report.txt"])
        self.assertEqual(json.loads(files["report.json"])["store_pages"][0]["file"], "store-page-booth.html")
        self.assertIn("How store-page-booth.html begins:", made["preview"])
        for name, text in files.items():
            for word in ("Fox Ears", "Kitsu Studio", "me@example.com", "98765"):
                self.assertNotIn(word, text, name)

    def test_every_stores_page_in_one_made_from_the_bar(self):
        kept_pages.keep("booth", PAGE, "layout")
        kept_pages.keep("gumroad", "<p>Other</p>", "empty")
        _made, files = self.report(source="bar")
        self.assertTrue({"store-page-booth.html", "store-page-gumroad.html"} <= set(files))

    def test_none_kept_none_in_it(self):
        _made, files = self.report(source="store", store="booth")
        self.assertFalse([n for n in files if n.startswith("store-page-")])
        self.assertNotIn("Store page:", files["report.txt"])


class NoBrowser:
    """Playwright, stood in for: the stores here are read by stand-ins."""
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


class Window:
    def close(self):
        pass


class WhenAReadFails(IsolatedTestCase):
    """A refresh keeps the store's page when its read fails on the page or comes back empty; not for a sign-in, a
    block or the network; and forgets it when the store reads fine, or you sign out."""

    def setUp(self):
        kept_pages.forget("booth")
        self.lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        self.lib.replace_store("booth", [library.item("booth", "1", name="Item 1", creator="Kitsu")])
        self.job = jobs.Jobs(config.load_config(), self.lib)
        self.kept = []

    def refresh(self, fetch):
        def capture(ctx, cfg, store, problem, error=None):
            self.kept.append((store, problem))
            kept_pages.keep(store, PAGE, problem)
            return True
        with mock.patch.multiple(jobs, reachable=lambda store, timeout=5.0: True, _playwright=lambda: NoBrowser,
                                 launch=lambda *a, **k: Window(), cache_images=lambda *a, **k: 0), \
                mock.patch.dict(jobs.FETCHERS, {"booth": fetch}), mock.patch("hoard.downloader.build_catalog", lambda *a: None), \
                mock.patch.object(library, "store_tags_from_pages", lambda *a, **k: None), \
                mock.patch.object(kept_pages, "capture", capture):
            self.job._refresh(["booth"])

    def test_a_page_the_reader_didnt_know(self):
        def fails(ctx, cfg, progress):
            raise RuntimeError("no library cards on the page")
        self.refresh(fails)
        self.assertEqual(self.kept, [("booth", "layout")])
        self.assertEqual(len(kept_pages.kept("booth")), 1)

    def test_one_that_came_back_empty(self):
        self.refresh(lambda ctx, cfg, progress: [])
        self.assertEqual(self.kept, [("booth", "empty")])

    def test_not_a_sign_in(self):
        from hoard.common import NotLoggedIn

        def signed_out(ctx, cfg, progress):
            raise NotLoggedIn("Not signed in to Booth")
        self.refresh(signed_out)
        self.assertEqual(self.kept, [])

    def test_gone_once_it_reads_fine(self):
        kept_pages.keep("booth", PAGE, "layout")
        self.refresh(lambda ctx, cfg, progress: [library.item("booth", "1", name="Item 1", creator="Kitsu")])
        self.assertEqual(kept_pages.kept("booth"), [])

    def test_gone_when_you_sign_out(self):
        kept_pages.keep("booth", PAGE, "layout")
        with mock.patch.object(jobs, "_playwright", lambda: NoBrowser):
            self.job._logout(["booth"])   # (no saved sign-in: the page goes all the same)
        self.assertEqual(kept_pages.kept("booth"), [])
