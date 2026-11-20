"""hoard:// links (hoard/links.py, issue #396): what each asks for, what's refused, how one reaches the Hoard that's
running, and what Hoard's page does with it (nothing added until you say so)."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from hoard import links, sets, wishlists
from tests.isolation import IsolatedTestCase

SET = {"name": "Fox outfit", "items": ["booth:1"],
       "products": {"booth:1": {"store": "booth", "id": "1", "name": "Rusk", "creator": "Kitsu",
                                "url": "https://booth.pm/ja/items/1"}}}
SHORT = "S1.abcdefghij.abcdefghijklmnopqrstuv"
CATALOGS = {lang: json.loads((Path(__file__).resolve().parent.parent / "hoard" / "web" / "i18n" / f"{lang}.json").read_text("utf-8"))
            for lang in ("ja", "ko")}


def code() -> str:
    return sets.share_code({"name": "Fox outfit", "items": ["booth:1"]},
                           lambda key: SET["products"].get(key))[0]


class Parse(IsolatedTestCase):
    def test_what_each_link_asks_for(self):
        long_code = code()
        for link, asked in [
            ("hoard://", {"do": "show"}), ("hoard:", {"do": "show"}), ("HOARD://open", {"do": "show"}),
            ("hoard:///", {"do": "show"}),
            (f"hoard://set/{SHORT}", {"do": "set", "code": SHORT}),
            (f"hoard://set/{SHORT}/", {"do": "set", "code": SHORT}),   # (a trailing / some programs add)
            (f"hoard://set/{long_code}", {"do": "set", "code": long_code}),
            ("hoard://add?link=https%3A%2F%2Fbooth.pm%2Fja%2Fitems%2F123",
             {"do": "add", "link": "https://booth.pm/ja/items/123"}),
            ("hoard://add?link=https://kitsu.gumroad.com/l/rusk?ref=x",
             {"do": "add", "link": "https://kitsu.gumroad.com/l/rusk"}),   # (its query isn't kept)
            ("hoard://product/booth/123", {"do": "product", "key": "booth:123"}),
            ("hoard://product/Jinxxy/2f6a-c3", {"do": "product", "key": "jinxxy:2f6a-c3"}),
            ("hoard://product/gumroad/NcYk8mDOEeVY0Mb8TsGc3A%3D%3D", {"do": "product", "key": "gumroad:NcYk8mDOEeVY0Mb8TsGc3A=="}),
        ]:
            with self.subTest(link=link):
                self.assertEqual(links.parse(link), asked)

    def test_what_is_refused(self):
        for link in [None, 12, "", "https://hoard.furryup.link/set.html#" + SHORT, "javascript:alert(1)",
                     "hoardx://set/" + SHORT, "hoard://" + "x" * (links.MAX_LINK + 1),
                     "hoard://settings", "hoard://download/booth/1", "hoard://open/extra", "hoard://set",
                     f"hoard://set/{SHORT}/more", "hoard://set/S1.abcdefghij", "hoard://set/H1.not-a-real-code",
                     "hoard://set/../../etc/passwd", "hoard://set/C:%5CUsers%5Cyou",
                     "hoard://add", "hoard://add?link=", "hoard://add?url=https://booth.pm/ja/items/1",
                     "hoard://add?link=https://booth.pm/ja/items/1&link=https://booth.pm/ja/items/2",
                     "hoard://add?link=http://booth.pm/ja/items/1", "hoard://add?link=https://evil.example/items/1",
                     "hoard://add?link=https://gumroad.com/d/abcdef", "hoard://add?link=file:///etc/passwd",
                     "hoard://add?link=https://[x/", "hoard://add?link=https://booth.pm:99999/items/1",
                     "hoard://add/more?link=https://booth.pm/ja/items/1",
                     "hoard://product/booth", "hoard://product/local/x", "hoard://product/steam/1",
                     "hoard://product/booth/1%2F..%2F..", "hoard://product/booth/" + "1" * 201,
                     "hoard://product/booth/1/files"]:
            with self.subTest(link=link):
                with self.assertRaises(links.Refused) as said:
                    links.parse(link)
                for lang in ("ja", "ko"):   # (what the page says: in each language it's in)
                    self.assertIn(str(said.exception), CATALOGS[lang], lang)

    def test_a_damaged_code_says_why(self):
        damaged = code()[:-6]
        with self.assertRaises(links.Refused) as said:
            links.parse("hoard://set/" + damaged)
        self.assertIn("damaged", str(said.exception))

    def test_is_link(self):
        self.assertTrue(links.is_link("hoard://set/x"))
        self.assertTrue(links.is_link("Hoard:open"))
        for text in ("--browser", "https://hoard.furryup.link", "hoard", None, ["hoard://"]):
            self.assertFalse(links.is_link(text), text)

    def test_add_products_by_link_checks_the_same(self):
        """The link an add link names is checked by the same function as a link pasted in Add products by link."""
        self.assertEqual(wishlists.product_page_link("https://booth.pm/ja/items/123"), ("booth", "https://booth.pm/ja/items/123"))
        for bad in ("https://booth.pm/", "https://example.com/items/1", None, "https://[x/items/1", "https://[::1",
                    "https://jinxxy.com/my/wishlist", "https://jinxxy.com/MY/inventory", "https://jinxxy.com/market/new"):
            with self.assertRaises(wishlists.LinkError, msg=bad):
                wishlists.product_page_link(bad)
        self.assertEqual(wishlists.product_page_link("https://jinxxy.com/Kitsu/FoxHat")[0], "jinxxy")


class Running(IsolatedTestCase):
    """A link reaches the Hoard that's running: its server keeps it for its page, once."""

    def setUp(self):
        from hoard import config, server
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(tmp / "dl"), "setup_done": True},
                                    lan=False)
        self.shown = []
        self.srv.show_window = lambda: self.shown.append(True)
        self.srv.show_token = "pass-of-this-run"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = self.srv.url

    def post(self, path, body, key=None):
        import urllib.error
        import urllib.request
        from hoard.safety import ACCESS_HEADER
        headers = {"Content-Type": "application/json", **({ACCESS_HEADER: key} if key else {})}
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def status(self):
        import urllib.request
        from hoard.safety import ACCESS_HEADER
        req = urllib.request.Request(self.base + "api/status", headers={ACCESS_HEADER: self.srv.key})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_the_page_is_given_a_link_once(self):
        """/api/status says one is waiting (whatever part of the page asks it, the link stays), and /api/link gives
        it, once."""
        self.srv.ask_open("hoard://product/booth/1")
        self.assertEqual(self.shown, [True], "Hoard comes to the front")
        self.assertIs(self.status().get("link"), True)
        self.assertIs(self.status().get("link"), True, "still waiting")
        self.assertNotIn("open", self.status())
        self.assertEqual(self.post("api/link", {}, key=self.srv.key), (200, {"open": {"do": "product", "key": "booth:1"}}))
        self.assertNotIn("link", self.status())
        self.assertEqual(self.post("api/link", {}, key=self.srv.key), (200, {"open": None}), "given once")
        self.assertEqual(self.post("api/link", {})[0], 401, "only to Hoard's own page, with its key")

    def test_only_the_latest_waits(self):
        self.srv.ask_open("hoard://product/booth/1")
        self.srv.ask_open("hoard://product/booth/2")
        self.assertEqual(self.srv.take_open(), {"do": "product", "key": "booth:2"})
        self.assertIsNone(self.srv.take_open())

    def test_a_link_that_cant_be_opened_is_said(self):
        self.srv.ask_open("hoard://settings?reset=1")
        said = self.srv.take_open()
        self.assertEqual(said["do"], "error")
        self.assertIn("doesn't know", said["error"])
        self.assertNotIn("reset", said["error"], "the link's own words aren't said back")

    def test_a_link_that_breaks_the_reader_is_said_too(self):
        """Whatever goes wrong reading a link, Hoard carries on and says it couldn't be opened."""
        with mock.patch.object(links, "parse", side_effect=RuntimeError("boom")):
            self.srv.ask_open("hoard://product/booth/1")
        self.assertEqual(self.srv.take_open(), {"do": "error", "error": "That Hoard link couldn't be opened."})

    def test_hoard_alone_only_comes_forward(self):
        self.srv.ask_open("hoard://")
        self.assertEqual(self.shown, [True])
        self.assertIsNone(self.srv.take_open())

    def test_a_second_start_hands_its_link_over(self):
        """The signed request a second start makes (/api/show), with the link it was started with."""
        got = self.post("api/show", {"token": "pass-of-this-run", "open": f"hoard://set/{SHORT}"})
        self.assertEqual(got, (200, {"ok": True}))
        self.assertEqual(self.srv.take_open(), {"do": "set", "code": SHORT})
        self.assertEqual(self.post("api/show", {"token": "not-it", "open": "hoard://product/booth/1"})[0], 403)
        self.assertIsNone(self.srv.take_open(), "nothing from a request without this run's pass")
        self.assertEqual(self.post("api/show", {"token": "pass-of-this-run"}), (200, {"ok": True}))
        self.assertIsNone(self.srv.take_open())
        self.assertEqual(len(self.shown), 2)

    def test_show_running_copy_sends_the_link(self):
        from hoard import app
        sent = []

        class Answer:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        app.running_file().parent.mkdir(parents=True, exist_ok=True)
        app.running_file().write_text(json.dumps({"url": "http://127.0.0.1:9/", "token": "t"}), "utf-8")
        with mock.patch.object(app, "local_request", lambda url, body, timeout: sent.append(body) or Answer()):
            self.assertTrue(app.show_running_copy(1, link="hoard://product/booth/1"))
            self.assertTrue(app.show_running_copy(1, link="--browser"))
            self.assertTrue(app.show_running_copy(1))
        self.assertEqual(sent, [{"open": "hoard://product/booth/1", "token": "t"}, {"token": "t"}, {"token": "t"}])

    def test_the_command_line_takes_a_link_alone(self):
        """A desktop entry's %u (Exec=hoard %u) gives a link as Hoard's only argument; --open gives it too."""
        from hoard import cli
        for argv in (["hoard://product/booth/1"], ["--open", "hoard://product/booth/1"]):
            with self.subTest(argv=argv), mock.patch.object(cli, "run_app", return_value=0) as run, \
                    self.assertRaises(SystemExit):
                cli.main(argv)
            self.assertEqual(run.call_args.kwargs["link"], "hoard://product/booth/1")
        with mock.patch.object(cli, "run_app", return_value=0) as run, self.assertRaises(SystemExit):
            cli.main([])
        self.assertIsNone(run.call_args.kwargs["link"])
        with mock.patch.object(cli, "cmd_sync") as sync, mock.patch("sys.stderr"), self.assertRaises(SystemExit) as said:
            cli.main(["--open", "hoard://product/booth/1", "sync"])   # (not quietly let go: said)
        self.assertEqual(said.exception.code, 2)
        sync.assert_not_called()


class Page(IsolatedTestCase):
    """What Hoard's page does with a link: opens what you'd open yourself, with the link's part in it."""

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
        with self.srv.lib.lock:   # (in memory only)
            self.srv.lib.data["items"] = [library.item("booth", "1", name="Rusk", creator="Kitsu",
                                                       url="https://booth.pm/ja/items/1")]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def test_each_link_in_the_page(self):
        from playwright.sync_api import sync_playwright
        made = sets.SetStore().change({"action": "create", "name": "Want", "items": [], "kind": "wishlist"})["made"]
        added = wishlists.product("booth", "Fox Ears", id_="123", creator="Mochi", url="https://booth.pm/ja/items/123")
        with sync_playwright() as pw, mock.patch.object(wishlists, "from_product_page", return_value=added) as read:
            browser = pw.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.locator(".slot", has_text="Rusk").wait_for()
            # a shared set: Add a shared set..., with its code in the box, and added only once you say so
            self.srv.ask_open("hoard://set/" + code())
            box = page.locator("dialog[open] #askName")
            box.wait_for(timeout=10000)
            self.assertEqual(box.input_value(), code())
            self.srv.ask_open("hoard://product/booth/1")   # (another, while that's open: let go)
            page.wait_for_timeout(5000)
            self.assertEqual(page.locator("dialog[open]").count(), 1)
            self.assertEqual(len(sets.SetStore().load()["sets"]), 1, "nothing added yet")
            page.keyboard.press("Enter")
            page.get_by_text("Added the shared set.").wait_for()
            page.locator("#setView h2", has_text="Fox outfit").wait_for()
            # a product to add: a wishlist chosen, then Add products by link... with the link in it
            self.srv.ask_open("hoard://add?link=https%3A%2F%2Fbooth.pm%2Fja%2Fitems%2F123")
            choice = page.locator("dialog[open]")
            choice.get_by_text("Add to which wishlist?").wait_for(timeout=10000)
            self.assertIn("https://booth.pm/ja/items/123", choice.inner_text())
            choice.get_by_text("Want", exact=True).click()
            field = page.locator("dialog[open] textarea")
            field.wait_for()
            self.assertEqual(field.input_value(), "https://booth.pm/ja/items/123")
            read.assert_not_called()
            page.locator("dialog[open] button", has_text="Add them").click()
            page.get_by_text("Added Fox Ears.").wait_for()
            self.assertEqual(read.call_args.args[0], "https://booth.pm/ja/items/123")
            kept = next(s for s in sets.SetStore().load()["sets"] if s["id"] == made)
            self.assertEqual(len(kept["items"]), 1)
            # a product in the library: its details
            self.srv.ask_open("hoard://product/booth/1")
            page.locator("#detail", has_text="Rusk").wait_for(timeout=10000)
            # one that isn't, and a link Hoard won't open: said; the details that were open close, and the address
            # names no product
            self.srv.ask_open("hoard://product/booth/999")
            page.get_by_text("That product isn't in your library.").wait_for(timeout=10000)
            self.assertFalse(page.evaluate("document.querySelector('#detail').classList.contains('open')"))
            self.assertNotIn("open=", page.evaluate("location.hash"))
            self.srv.ask_open("hoard://download/everything")
            page.get_by_text("Hoard doesn't know what that link asks for.").wait_for(timeout=10000)
            self.assertEqual(errors, [])
            browser.close()


class SendToHoard(IsolatedTestCase):
    """Issue #413: the Send to Hoard bookmark (SEND_TO_HOARD in hoard/web/shared.js), run on each kind of page as a
    browser would run it: a product's page on each store becomes a hoard://add link, and a shared set a hoard://set
    link, each one Hoard itself takes; anywhere else it only says what it works on."""

    PAGES = {   # the page: the link, or None where it only says something
        "https://booth.pm/ja/items/1234567": "hoard://add?link=https%3A%2F%2Fbooth.pm%2Fja%2Fitems%2F1234567",
        "https://kitsu.booth.pm/items/99?ref=x#pics": "hoard://add?link=https%3A%2F%2Fkitsu.booth.pm%2Fitems%2F99",
        "https://kitsu.gumroad.com/l/hat": "hoard://add?link=https%3A%2F%2Fkitsu.gumroad.com%2Fl%2Fhat",
        "https://jinxxy.com/Kitsu/FoxHat": "hoard://add?link=https%3A%2F%2Fjinxxy.com%2FKitsu%2FFoxHat",
        "https://jinxxy.com/my/wishlist": None, "https://jinxxy.com/market/new": None,   # (Jinxxy's own pages, not products)
        "https://payhip.com/b/AbCd1": "hoard://add?link=https%3A%2F%2Fpayhip.com%2Fb%2FAbCd1",
        "https://kitsu.itch.io/fox-hat": "hoard://add?link=https%3A%2F%2Fkitsu.itch.io%2Ffox-hat",
        "https://hoard.furryup.link/set.html#S1.abcdefghij.abcdefghijklmnopqrstuv": "hoard://set/S1.abcdefghij.abcdefghijklmnopqrstuv",
        "https://booth.pm/ja/": None, "https://example.com/items/1": None, "https://hoard.furryup.link/set.html#new": None,
        "https://hoard.furryup.link/set.html#H1." + "a" * 2100: None,   # (too long for a link: copy its code instead)
        "https://hoard.furryup.link/set.html#S1.%E0%A4%A": None,   # (a broken link's code: said, not thrown)
    }


    def test_jinxxys_own_pages_are_hoards(self):
        """The bookmark leaves out the Jinxxy pages Hoard's own check does (wishlists.JINXXY_NOT_CREATORS)."""
        js = (Path(__file__).resolve().parent.parent / "hoard" / "web" / "shared.js").read_text("utf-8")
        listed = re.search(r'const jinxxyOwn = \[([^\]]*)\]', js).group(1)
        self.assertEqual(set(re.findall(r'"([^"]+)"', listed)), set(wishlists.JINXXY_NOT_CREATORS))
    def test_each_kind_of_page(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                pw.chromium.launch().close()
        except Exception:
            self.skipTest("no Playwright browser here")
        code = (Path(__file__).resolve().parent.parent / "hoard" / "web" / "shared.js").read_text("utf-8")
        code = code.split("const SEND_TO_HOARD = String.raw`", 1)[1].split("`;", 1)[0]
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            for href, want in self.PAGES.items():
                got = page.evaluate("""([code, href]) => {   // (its location and alert stood in for)
                    const loc = { href }, said = [];
                    new Function("location", "alert", code)(loc, m => said.push(m));
                    return { href: loc.href, said };
                }""", [code, href])
                with self.subTest(href=href[:80]):
                    if want is None:
                        self.assertEqual(got["href"], href, "it goes nowhere")
                        self.assertTrue(got["said"] and got["said"][0].startswith("Send to Hoard: "))
                        continue
                    self.assertEqual((got["href"], got["said"]), (want, []))
                    asked = links.parse(want)   # (and Hoard takes it, as it would from the browser)
                    self.assertIn(asked["do"], ("add", "set"), asked)
            browser.close()


class Packaging(IsolatedTestCase):
    """Each of Hoard's apps says it opens hoard:// links, and hands one to Hoard."""
    REPO = Path(__file__).resolve().parent.parent

    def test_the_shell_registers_the_scheme(self):
        conf = json.loads((self.REPO / "shell" / "tauri.conf.json").read_text("utf-8"))
        self.assertEqual(conf["plugins"]["deep-link"], {"desktop": {"schemes": ["hoard"]}},
                         "the Windows installer, the Mac app's Info.plist and Linux's desktop entries, from this")
        self.assertIn('tauri-plugin-deep-link = "=2.6.3"', (self.REPO / "shell" / "Cargo.toml").read_text("utf-8"))
        template = (self.REPO / "shell" / conf["bundle"]["linux"]["deb"]["desktopTemplate"]).read_text("utf-8")
        self.assertIn("Exec={{exec}} %u\n", template, "the .deb's and the AppImage's: the link as Hoard's argument")
        self.assertIn("MimeType={{mime_type}}", template)
        main = (self.REPO / "shell" / "src" / "main.rs").read_text("utf-8")
        self.assertIn('"open": start_link()', main, "a link it's started with goes in its hello")
        self.assertIn("RunEvent::Opened", main, "a Mac's")

    def test_the_flatpak(self):
        desktop = (self.REPO / "packaging" / "flatpak" / "io.github.soloflighter1010.Hoard.desktop").read_text("utf-8")
        self.assertIn("Exec=hoard %u", desktop.splitlines())
        self.assertIn("MimeType=x-scheme-handler/hoard;", desktop.splitlines())
        launcher = (self.REPO / "shell" / "flatpak" / "hoard.sh").read_text("utf-8")
        self.assertIn('[hH][oO][aA][rR][dD]:*) exec /app/bin/Hoard "$1"', launcher, "to the window, not the command line")


class Website(IsolatedTestCase):
    """The website's set viewer: Open in Hoard, with the set's own code, where a browser can hand its link over."""

    def viewer(self, page, code_):
        site = Path(__file__).resolve().parent.parent / "site"

        def serve(route):
            name = route.request.url.split("hoard.furryup.link/", 1)[-1].split("#")[0].split("?")[0]
            kind = {"html": "text/html", "js": "text/javascript", "css": "text/css"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
            if route.request.url.startswith("https://hoard.furryup.link/") and (site / name).is_file():
                return route.fulfill(path=str(site / name), content_type=kind)
            return route.fulfill(status=404)
        page.route("**/*", serve)
        page.goto("https://hoard.furryup.link/set.html#" + code_)
        page.locator("#setView").wait_for()

    def test_open_in_hoard(self):
        import random
        import string
        from playwright.sync_api import sync_playwright
        rng = random.Random(396)
        names = {f"booth:{n}": {"store": "booth", "id": str(n), "creator": "Kitsu", "url": f"https://booth.pm/ja/items/{n}",
                                "name": "".join(rng.choice(string.ascii_letters) for _ in range(40))} for n in range(1, 80)}
        big = sets.share_code({"name": "Everything", "items": list(names)}, names.get)[0]
        self.assertGreater(len(big), 2000)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            self.viewer(page, code())
            self.assertEqual(page.get_attribute("#setHoard", "href"), "hoard://set/" + code())
            self.assertTrue(page.locator("#setHoardNote").is_visible(), "what to do with an older Hoard")
            self.assertTrue(page.locator("#setHoardLong").is_hidden())
            page = browser.new_page()
            self.viewer(page, big)
            self.assertTrue(page.locator("#setHoard").is_hidden(), "too long for a browser to hand to Hoard")
            self.assertTrue(page.locator("#setHoardNote").is_hidden())
            self.assertTrue(page.locator("#setHoardLong").is_visible(), "and it says so")
            self.assertIn("primary", page.get_attribute("#setCopy", "class"), "copying the link is the way")
            browser.close()


if __name__ == "__main__":
    unittest.main()
