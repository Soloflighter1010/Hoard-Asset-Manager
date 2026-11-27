"""Try Hoard on the website (issue #394, scripts/build_site_demo.py and site/demo/demo.js): the demo built from the
app's pages, run in a browser. It starts at the pretend sign-in; then the library, a product's details and a set show;
changes (a tag, a mark, a set) last until the tab is closed; sets come in by their code, their short link and their
file, and from the website's set viewer; what needs Hoard on your computer says so; and no request goes anywhere but
the website, the stores' image hosts and (for a short link's set) Hoard's share server."""
from __future__ import annotations

import base64
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from tests.isolation import IsolatedTestCase

REPO = Path(__file__).resolve().parent.parent
SHARE = "https://hoard-share.furryup.link"
IMAGE_HOSTS = ("https://jinxxy-c.jinxxy-cdn.com/", "https://public-files.gumroad.com/", "https://booth.pximg.net/",
               "https://images.payhip.com/", "https://img.itch.zone/")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class Quiet(http.server.SimpleHTTPRequestHandler):
    """The website's files, served without a line for each."""

    def log_message(self, *args):
        pass


class TryHoard(IsolatedTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                pw.chromium.launch().close()
        except Exception:
            raise unittest.SkipTest("no Playwright browser here")
        cls.root = Path(tempfile.mkdtemp(prefix="hoard-site-demo-"))
        env = {k: v for k, v in os.environ.items() if k not in ("HOARD_DATA_DIR", "HOARD_VCC_DIR")}
        done = subprocess.run([sys.executable, str(REPO / "scripts" / "build_site_demo.py"), str(cls.root / "demo")],
                              capture_output=True, text=True, timeout=900, env=env, cwd=str(REPO))
        if done.returncode:
            shutil.rmtree(cls.root, ignore_errors=True)
            raise AssertionError(f"The demo didn't build:\n{done.stdout}\n{done.stderr}")
        shutil.copy2(REPO / "site" / "set.html", cls.root / "set.html")
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(cls.root)))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        cls.data = json.loads(cls.root.joinpath("demo", "index.html").read_text("utf-8")
                              .split('<script type="application/json" id="demo-data">', 1)[1].split("</script>", 1)[0])

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.addCleanup(self.pw.stop)
        self.browser = self.pw.chromium.launch()
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 900})
        self.asked, self.errors, self.locked = [], [], {}
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.page.route("**/*", self.answer)

    def answer(self, route):
        """The network, as the page sees it: the website, the stores' pictures, and the share server's locked sets;
        anything else is noted and refused."""
        url = route.request.url
        self.asked.append(url)
        if url.startswith(self.base):
            return route.continue_()
        if url.startswith(IMAGE_HOSTS):
            return route.fulfill(status=200, content_type="image/png", body=PNG)
        if url.startswith(SHARE + "/v1/sets/") and url.rsplit("/", 1)[1] in self.locked:
            return route.fulfill(status=200, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"},
                                 body=json.dumps({"data": self.locked[url.rsplit("/", 1)[1]], "expires": 1999999999}))
        return route.abort()

    def elsewhere(self) -> list[str]:
        """What the page asked for that isn't the website, a store's picture or the share server."""
        return [u for u in self.asked if not u.startswith((self.base, SHARE + "/v1/sets/") + IMAGE_HOSTS)]

    def signed_in(self, address="/demo/"):
        """The demo, past its pretend sign-in, with the library shown."""
        self.page.goto(self.base + address)
        self.page.locator(".demo-go").click()
        self.page.locator(".slot").first.wait_for(timeout=15000)

    def evaluate(self, script, arg=None):
        """What a script in the page gives back."""
        return self.page.evaluate(script, arg)

    def code(self) -> str:
        """A set's code, as Hoard shares one: a product in the demo's library, and one that isn't."""
        from hoard import sets   # (in this test's own data folder: IsolatedTestCase)
        owned = next(p for p in self.data["products"] if p["place"] == "library")
        got, _ = sets.share_code({"name": "Party night", "note": "Shared with you", "items": ["a", "b"], "products": {
            "a": {"store": owned["store"], "id": owned["id"], "name": owned["name"], "creator": owned["creator"],
                  "url": owned["url"], "thumbnail": owned["thumbnail"]},
            "b": {"store": "booth", "id": "123456", "name": "Someone's Jacket", "creator": "A Shop",
                  "url": "https://booth.pm/en/items/123456", "thumbnail": "https://booth.pximg.net/c/x.jpg"}}})
        return got

    def sets_named(self) -> list[str]:
        """The Sets tab's sets, by name, as the stand-in has them."""
        return self.evaluate("fetch('/api/sets').then(r => r.json()).then(d => d.sets.map(s => s.name))")

    def test_sign_in_library_details_and_a_set(self):
        self.page.goto(self.base + "/demo/")
        self.assertTrue(self.page.locator(".demo-cover").is_visible(), "it starts at the pretend sign-in")
        self.assertEqual(self.page.locator(".demo-store input[type=email]").evaluate_all("xs => xs.map(x => x.value)"),
                         ["demo@jinxxy.example", "demo@gumroad.example"], "the demo's accounts, filled in")
        self.page.locator(".demo-go").click()
        self.page.locator(".slot").first.wait_for(timeout=15000)
        owned = [p for p in self.data["products"] if p["place"] == "library"]
        self.assertEqual(self.page.locator(".slot").count(), len(owned), "the library: every product listed")
        self.page.locator(".slot").first.click()
        self.page.locator("#detail").wait_for(timeout=10000)
        self.assertIn(self.page.locator("#detail h2, #detail .d-name").first.text_content().strip(), {p["name"] for p in owned})
        self.page.keyboard.press("Escape")
        self.page.locator('#storeSeg [data-store="Sets"]').click()
        self.page.locator("[data-setopen]").first.click()
        self.page.get_by_text("Spooky night").first.wait_for(timeout=10000)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.elsewhere(), [], "nothing leaves the browser but the stores' pictures")
        self.assertTrue(any(u.startswith(IMAGE_HOSTS) for u in self.asked), "the pictures, from the stores themselves")

    def test_changes_last_until_the_tab_is_closed(self):
        self.signed_in()
        key = self.data["answers"]["/api/library"]["items"][0]["tag_key"]
        self.evaluate("""key => Promise.all([
            fetch('/api/tags', {method: 'POST', body: JSON.stringify({action: 'assign', keys: [key], add: ['Favourite']})}),
            fetch('/api/marks', {method: 'POST', body: JSON.stringify({kind: 'archived', on: true, keys: [key]})}),
            fetch('/api/sets', {method: 'POST', body: JSON.stringify({action: 'create', name: 'Mine', items: [key]})})])""", key)
        self.page.reload()
        self.page.locator(".slot").first.wait_for(timeout=15000)
        item = self.evaluate("key => fetch('/api/library').then(r => r.json()).then(d => d.items.find(i => i.tag_key === key))", key)
        self.assertEqual((item["tags"], item["mark"]), (["favourite"], "archived"), "kept for the tab, past a reload")
        self.assertIn("Mine", self.sets_named())
        fresh = self.browser.new_page()   # (another tab: a demo of its own)
        fresh.route("**/*", self.answer)
        fresh.goto(self.base + "/demo/")
        self.assertTrue(fresh.locator(".demo-cover").is_visible(), "a new tab starts afresh")

    def test_a_shared_set_from_the_set_viewer(self):
        code = self.code()
        self.page.goto(self.base + "/demo/#import=" + code)
        self.assertEqual(self.evaluate("location.hash"), "", "taken out of the address before the app reads it")
        self.page.locator(".demo-go").click()
        box = self.page.locator("dialog[open] input:visible").first
        box.wait_for(timeout=15000)
        self.assertEqual(box.input_value(), code, "offered as Add a shared set does: nothing's added until it's said")
        self.page.keyboard.press("Enter")
        self.page.get_by_text("Added the shared set.").wait_for(timeout=10000)
        party = self.evaluate("fetch('/api/sets').then(r => r.json()).then(d => d.sets.find(s => s.name === 'Party night'))")
        self.assertEqual([i["owned"] for i in party["items"]], [True, False], "what's in the library is yours")
        self.assertTrue(party["from_link"], "kept apart from your own, its photos shown when you ask, as in Hoard")
        self.assertEqual(self.elsewhere(), [])

    def test_a_short_link_and_a_file(self):
        self.signed_in()
        # the set locked as Hoard locks one for a short link (AES-GCM, by its key), here with the browser's own crypto
        key, self.locked["AbCdEf1234"] = self.evaluate("""async code => {
            const b64u = b => btoa(String.fromCharCode(...b)).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
            const key = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
            const k = await crypto.subtle.importKey('raw', key, 'AES-GCM', false, ['encrypt']);
            const locked = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv,
              additionalData: new TextEncoder().encode('Hoard set S1') }, k, new TextEncoder().encode(code)));
            const all = new Uint8Array(12 + locked.length); all.set(iv); all.set(locked, 12);
            return [b64u(key), b64u(all)]; }""", self.code())
        self.evaluate(f"() => {{ addSharedSet({json.dumps(f'{self.base}/set.html#S1.AbCdEf1234.{key}')}); }}")
        self.page.locator("dialog[open] input:visible").first.wait_for(timeout=10000)
        self.page.keyboard.press("Enter")
        self.page.get_by_text("Added the shared set.").wait_for(timeout=10000)
        self.assertIn(SHARE + "/v1/sets/AbCdEf1234", self.asked, "the locked set, from the share server")
        self.assertFalse(any(key in u for u in self.asked), "its key is never sent anywhere")
        doc = {"format": "hoard-set", "version": 1, "set": {"name": "From a file", "kind": "wishlist", "items": ["x"],
               "products": {"x": {"store": "gumroad", "name": "A hat", "creator": "Someone"}}}}
        made = self.evaluate("doc => fetch('/api/sets', {method: 'POST', body: JSON.stringify({action: 'import-json', file: doc})}).then(r => r.json())", doc)
        self.assertTrue(made["ok"])
        self.assertEqual(self.sets_named()[-2:], ["Party night", "From a file"])

    def test_what_needs_hoard_says_so(self):
        self.signed_in()
        got = self.evaluate("fetch('/api/download', {method: 'POST', body: '{}'}).then(r => r.status)")
        self.assertEqual(got, 409)
        self.assertIn("needs Hoard on your computer", self.page.locator(".demo-note").text_content())
        self.assertEqual(self.page.locator(".demo-note a").get_attribute("href"), "/#download")

    def test_a_set_shows_in_downloads_too(self):
        """Downloads keeps its own list of the sets: one made, renamed or deleted shows there as in the Library."""
        self.signed_in()
        key = self.data["answers"]["/api/assets"]["assets"][0]["tag_key"]
        made = self.evaluate("key => fetch('/api/sets', {method: 'POST', body: JSON.stringify({action: 'create', name: 'Mine', items: [key]})}).then(r => r.json())", key)
        downloads = lambda: {s["id"]: s for s in self.evaluate("fetch('/api/assets').then(r => r.json()).then(d => d.sets)")}  # noqa: E731
        self.assertEqual((downloads()[made["made"]]["name"], downloads()[made["made"]]["items"]), ("Mine", [key]))
        self.evaluate("id => fetch('/api/sets', {method: 'POST', body: JSON.stringify({action: 'rename', id, name: 'Ours'})})", made["made"])
        self.assertEqual(downloads()[made["made"]]["name"], "Ours")
        spooky = next(s["id"] for s in self.data["answers"]["/api/sets"]["sets"] if s["name"] == "Spooky night")
        self.evaluate("id => fetch('/api/sets', {method: 'POST', body: JSON.stringify({action: 'delete', id})})", spooky)
        self.assertNotIn(spooky, downloads())

    def test_a_tab_opened_in_a_new_tab(self):
        """Ctrl+click on a tab opens the demo's own page in a new tab, and the tab goes on working as one here."""
        self.signed_in()
        tab = self.page.locator("nav.apptabs a", has_text="Downloads")
        with self.page.context.expect_page() as opened:
            tab.click(modifiers=["Control"])
        self.assertTrue(opened.value.url.endswith("/demo/downloads"), opened.value.url)
        opened.value.close()
        self.page.wait_for_timeout(100)
        self.assertEqual(tab.get_attribute("href"), "/downloads", "its own address, back")
        tab.click()
        self.page.wait_for_function("document.querySelector('.apptabs a[aria-current]')?.textContent === 'Downloads'")
        self.assertTrue(self.page.url.endswith("/demo/downloads"))
        self.assertEqual(self.evaluate("performance.getEntriesByType('navigation').length"), 1, "in the page, not loaded again")

    def test_a_damaged_code_says_so(self):
        self.signed_in()
        got = self.evaluate("fetch('/api/sets', {method: 'POST', body: JSON.stringify({action: 'import', code: 'H1.abc$'})}).then(r => r.json())")
        self.assertEqual(got["error"], "That set code is damaged, or cut short: copy all of it, and try again.")
        twice = self.code()
        self.evaluate("code => fetch('/api/sets', {method: 'POST', body: JSON.stringify({action: 'import', code})})", twice)
        party = self.evaluate("fetch('/api/sets').then(r => r.json()).then(d => d.sets.find(s => s.name === 'Party night'))")
        self.assertEqual(len(party["items"]), len({i["key"] for i in party["items"]}), "each product once")

    def test_the_policy(self):
        html = self.root.joinpath("demo", "index.html").read_text("utf-8")
        policy = html.split('http-equiv="Content-Security-Policy" content="', 1)[1].split('"', 1)[0]
        self.assertIn(f"connect-src {SHARE};", policy, "nothing fetched but a short link's set")
        self.assertNotIn("unsafe-eval", policy)
        self.assertNotIn("hoard-demo-", html, "the build's own folder is never shown")
        self.signed_in()
        self.assertEqual([e for e in self.errors if "Content Security Policy" in e], [], "everything it runs is allowed")


class ShownPaths(IsolatedTestCase):
    """The build's own folder is never in the demo: on Windows, a Mac (whose /var is /private/var) or Linux."""

    def test_every_form_of_it(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_site_demo", REPO / "scripts" / "build_site_demo.py")
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        windows = "C:\\Users\\Someone\\AppData\\Local\\Temp\\hoard-demo-ab12"
        got = demo.homed({"path": windows + "\\Unity\\My Avatar\\Assets", "said": f"Couldn't read {windows}\\x.zip: denied",
                          windows + "\\Hoard": [1, "/var/folders/q/hoard-demo-cd34/Hoard/Jinxxy"]},
                         [windows, "/var/folders/q/hoard-demo-cd34", "/private/var/folders/q/hoard-demo-cd34"])
        self.assertEqual(got, {"path": "C:/Users/You/Unity/My Avatar/Assets", "said": "Couldn't read C:/Users/You/x.zip: denied",
                               "C:/Users/You/Hoard": [1, "C:/Users/You/Hoard/Jinxxy"]})
        self.assertEqual(demo.homed("/private/var/folders/q/hoard-demo-cd34/Hoard", ["/var/folders/q/hoard-demo-cd34",
                                    "/private/var/folders/q/hoard-demo-cd34"]), "C:/Users/You/Hoard")
        self.assertFalse(any("hoard-demo-" in t for t in demo.texts(got)))


if __name__ == "__main__":
    unittest.main()
