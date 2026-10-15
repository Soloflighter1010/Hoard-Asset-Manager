"""Short links for shared sets: the share server (share/worker.mjs), Hoard's side of it (hoard/shortlinks.py and
sets.json's "short"), the page that locks a set and the viewer that unlocks it. Hoard is tested against the real
Worker, run on this computer by share/dev_server.mjs with its sets kept in memory."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import downloader, egress, sets, shortlinks
from hoard.tags import tag_key

REPO = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
RUSK, HOODIE = tag_key("Booth", "Rusk"), tag_key("Booth", "Hoodie for Rusk")
SHORT_LINK = re.compile(r"https://hoard\.furryup\.link/set\.html#S1\.([0-9A-Za-z]{10})\.([A-Za-z0-9_-]{22})")


def share_server(case: unittest.TestCase) -> str:
    """The share Worker, on this computer, for one test class: Hoard's requests go there. Returns its address."""
    if not NODE:
        case.skipTest("needs Node.js")
    proc = subprocess.Popen([NODE, str(REPO / "share" / "dev_server.mjs")], stdout=subprocess.PIPE, text=True)
    case.addClassCleanup(proc.stdout.close)
    case.addClassCleanup(proc.wait, 10)
    case.addClassCleanup(proc.terminate)
    origin = proc.stdout.readline().strip()
    assert origin.startswith("http://127.0.0.1:"), origin
    patch = mock.patch.object(shortlinks, "SERVER", origin)
    patch.start()
    case.addClassCleanup(patch.stop)
    egress._TEST_ORIGINS.add(origin)   # (plain http, on this computer: tests only)
    case.addClassCleanup(egress._TEST_ORIGINS.discard, origin)
    return origin


def a_code(**extra) -> str:
    return sets.share_code({"name": "Rusk, winter", "items": [RUSK], "products": {
        RUSK: {"store": "booth", "name": "Rusk", "creator": "Kitsu", "url": "https://booth.pm/ja/items/1"}}, **extra})[0]


class Worker(unittest.TestCase):
    def test_the_workers_own_tests(self):
        if not NODE:
            self.skipTest("needs Node.js")
        run = subprocess.run([NODE, "--test", str(REPO / "share" / "worker.test.mjs")], capture_output=True, text=True,
                             cwd=REPO, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout[-4000:] + run.stderr[-2000:])

    def test_what_is_deployed(self):
        """The Worker answers only at its own address, keeps nothing in logs, and Hoard and the viewer use that
        address."""
        toml = (REPO / "share" / "wrangler.toml").read_text("utf-8")
        self.assertIn('main = "worker.mjs"', toml)
        self.assertIn("workers_dev = false", toml)
        self.assertIn('pattern = "hoard-share.furryup.link", custom_domain = true', toml)
        self.assertRegex(toml, r"\[observability\]\nenabled = false")
        self.assertEqual(shortlinks.SERVER, "https://hoard-share.furryup.link")
        self.assertIn(f'SHARE_SERVER = "{shortlinks.SERVER}"', (REPO / "site" / "set.js").read_text("utf-8"))
        worker = (REPO / "share" / "worker.mjs").read_text("utf-8")
        self.assertIn('const VIEWER = "https://hoard.furryup.link"', worker)
        self.assertIn(f"const LIFETIME = {shortlinks.LIFETIME_DAYS} * 24 * 60 * 60", worker)
        self.assertNotIn("console.", worker, "nothing is logged")


class Client(unittest.TestCase):
    """hoard/shortlinks.py, against the real Worker."""

    @classmethod
    def setUpClass(cls):
        share_server(cls)

    def test_made_read_updated_and_deleted(self):
        made = shortlinks.make("A" * 60)
        self.assertRegex(made["id"], r"^[0-9A-Za-z]{10}$")
        self.assertRegex(made["token"], r"^[A-Za-z0-9_-]{43}$")
        self.assertAlmostEqual(made["expires"], time.time() + 14 * 86400, delta=120)
        self.assertEqual(shortlinks.fetch(made["id"]), {"data": "A" * 60, "expires": made["expires"]})
        self.assertGreaterEqual(shortlinks.replace(made["id"], made["token"], "B" * 60), made["expires"])
        self.assertEqual(shortlinks.fetch(made["id"])["data"], "B" * 60)
        with self.assertRaisesRegex(shortlinks.ShortLinkError, "another copy of Hoard"):
            shortlinks.replace(made["id"], "x" * 43, "C" * 60)
        with self.assertRaisesRegex(shortlinks.ShortLinkError, "another copy of Hoard"):
            shortlinks.delete(made["id"], "x" * 43)
        shortlinks.delete(made["id"], made["token"])
        with self.assertRaisesRegex(shortlinks.Gone, "14 days"):
            shortlinks.fetch(made["id"])
        shortlinks.delete(made["id"], made["token"])   # (already gone: fine)
        with self.assertRaises(shortlinks.Gone):
            shortlinks.replace(made["id"], made["token"], "C" * 60)

    def test_what_isnt_sent(self):
        for data in ("A" * 41, "A" * 65537, "not base64!" * 5, None):
            with self.subTest(data=str(data)[:20]):
                with self.assertRaisesRegex(shortlinks.ShortLinkError, "too big"):
                    shortlinks.make(data)
        with self.assertRaises(shortlinks.Gone):
            shortlinks.fetch("../../etc")

    def test_when_the_server_cant_be_reached(self):
        with mock.patch.object(shortlinks, "SERVER", "http://127.0.0.1:9"):
            egress._TEST_ORIGINS.add("http://127.0.0.1:9")
            self.addCleanup(egress._TEST_ORIGINS.discard, "http://127.0.0.1:9")
            with self.assertRaisesRegex(shortlinks.ShortLinkError, "Couldn't reach Hoard's share server"):
                shortlinks.make("A" * 60)

    def test_only_https_for_real(self):
        with mock.patch.object(shortlinks, "SERVER", "http://hoard-share.furryup.link"), \
                mock.patch.object(egress.requests.Session, "request", side_effect=AssertionError("sent")):
            with self.assertRaisesRegex(shortlinks.ShortLinkError, "Couldn't reach"):
                shortlinks.fetch("abcdefghij")

    def test_reading_a_link(self):
        sid, key = "abcDEF0123", "k" * 22
        for text in (f"https://hoard.furryup.link/set.html#S1.{sid}.{key}", f"S1.{sid}.{key}", f"  S1.{sid}.\n{key} "):
            self.assertEqual(shortlinks.parse(text), (sid, key))
        for text in (f"S1.{sid}.{key}x", f"S1.{sid[:-1]}.{key}", "H1.abc", "", None, f"S2.{sid}.{key}", "S1." + "x" * 3000):
            self.assertIsNone(shortlinks.parse(text))


class Kept(unittest.TestCase):
    """A set's short link in sets.json: checked as it's read, and gone when it has run out."""

    def setUp(self):
        self.store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")
        rusk = {"store": "booth", "name": "Rusk", "creator": "Kitsu", "url": "https://booth.pm/ja/items/1"}
        self.made = self.store.change({"action": "create", "name": "Rusk", "items": [RUSK]},
                                      lambda key: rusk if key == RUSK else None)["made"]
        self.rec = {"id": "abcDEF0123", "key": "k" * 22, "token": "t" * 43, "expires": int(time.time()) + 3600,
                    "made": "0123456789abcdef"}

    def test_kept_and_forgotten(self):
        self.store.set_short(self.made, self.rec)
        self.assertEqual(self.store.load()["sets"][0]["short"], self.rec)
        self.store.change({"action": "rename", "id": self.made, "name": "Rusk 2"})
        self.assertEqual(self.store.load()["sets"][0]["short"], self.rec, "kept through other changes")
        self.store.set_short(self.made, None)
        self.assertNotIn("short", self.store.load()["sets"][0])
        with self.assertRaises(ValueError):
            self.store.set_short("nope", self.rec)

    def test_only_one_that_makes_sense(self):
        for bad in ({"id": "short"}, {"key": "k" * 21}, {"token": "t" * 42}, {"made": "xyz"}, {"expires": "soon"},
                    {"expires": True}, {"expires": int(time.time()) - 1}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.store.set_short(self.made, {**self.rec, **bad})
                self.assertIsNone(sets.clean_short({**self.rec, **bad}))
        data = json.loads(self.store.path.read_text("utf-8"))
        data["sets"][0]["short"] = {**self.rec, "expires": int(time.time()) - 5}
        self.store.path.write_text(json.dumps(data), "utf-8")
        self.assertNotIn("short", self.store.load()["sets"][0], "run out: forgotten")

    def test_not_in_a_code_nor_taken_from_one(self):
        self.store.set_short(self.made, self.rec)
        s = self.store.load()["sets"][0]
        code = sets.share_code(s)[0]
        self.assertNotIn("short", json.dumps(sets.from_code(code)))
        for part in (self.rec["token"], self.rec["key"], self.rec["id"]):
            self.assertNotIn(part, json.dumps(sets.from_code(code)))
        with self.assertRaisesRegex(ValueError, "Add a shared set, in Hoard 4.3"):
            sets.from_code(f"https://hoard.furryup.link/set.html#S1.{self.rec['id']}.{self.rec['key']}")
        with self.assertRaisesRegex(ValueError, "cut short"):
            sets.from_code(f"https://hoard.furryup.link/set.html#S1.{self.rec['id']}.{self.rec['key'][:-3]}")

    def test_the_mark_of_a_code(self):
        self.assertEqual(sets.code_mark(a_code()), sets.code_mark(a_code()))
        self.assertNotEqual(sets.code_mark(a_code()), sets.code_mark(a_code(note="new")))
        self.assertRegex(sets.code_mark(a_code()), r"^[0-9a-f]{16}$")


class Locking(unittest.TestCase):
    def test_the_page_and_the_viewer_agree(self):
        """Hoard's page locks a set as the viewer unlocks it, with a new nonce each time, and only its key opens it."""
        if not NODE:
            self.skipTest("needs Node.js")
        page = (REPO / "hoard" / "web" / "shared.js").read_text("utf-8")
        viewer = (REPO / "site" / "set.js").read_text("utf-8")
        hoard_part = re.search(r"const LOCKED_AS = .*?\n(?=const canLock)", page, re.S).group(0)
        viewer_part = re.search(r"  const LOCKED_AS = .*?\n(?=  // The code behind a short link)", viewer, re.S).group(0)
        code = sets.share_code({"name": "Ünïcode set 🦊", "note": "x" * 900, "items": [RUSK], "products": {
            RUSK: {"store": "booth", "name": "Rusk ルスク", "creator": "Kitsu"}}})[0]
        script = (f"const hoard = (() => {{ {hoard_part}; return {{ lockSet, unlockSet }}; }})();\n"
                  f"const viewer = (() => {{ {viewer_part}; return {{ unlockSet }}; }})();\n"
                  f"const code = {json.dumps(code)};\n" + r"""
const b64 = bytes => Buffer.from(bytes).toString("base64url");
const key = b64(crypto.getRandomValues(new Uint8Array(16))), other = b64(crypto.getRandomValues(new Uint8Array(16)));
(async () => {
  const a = await hoard.lockSet(code, key), b = await hoard.lockSet(code, key);
  const fails = async f => { try { await f(); return false; } catch (e) { return true; } };
  const bytes = Buffer.from(a, "base64url"); bytes[20] ^= 1;
  process.stdout.write(JSON.stringify({
    viewer: await viewer.unlockSet(a, key) === code, hoard: await hoard.unlockSet(b, key) === code, differ: a !== b,
    size: Buffer.from(a, "base64url").length - Buffer.byteLength(code), plain: a.includes("Rusk"),
    wrongKey: await fails(() => viewer.unlockSet(a, other)), changed: await fails(() => viewer.unlockSet(b64(bytes), key)),
  }));
})();""")
        got = json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True, timeout=60).stdout)
        self.assertEqual(got, {"viewer": True, "hoard": True, "differ": True, "size": 28, "plain": False,
                               "wrongKey": True, "changed": True})

    def test_the_viewer_may_reach_only_the_share_server(self):
        html = (REPO / "site" / "set.html").read_text("utf-8")
        csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
        self.assertIn(f"connect-src {shortlinks.SERVER};", csp)
        self.assertEqual(csp.count("connect-src"), 1)


class EndToEnd(unittest.TestCase):
    """Share, Make a short link, open it in the viewer, update it, add it to Hoard, delete it: the page, Hoard and
    the Worker together."""

    @classmethod
    def setUpClass(cls):
        cls.origin = share_server(cls)

    def setUp(self):
        import threading
        from hoard import config, library, server
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        root = tmp / "dl"
        folder = root / "Booth" / "Kitsu" / "Rusk"   # Rusk is downloaded; the hoodie only owned
        folder.mkdir(parents=True)
        (folder / "p.unitypackage").write_bytes(b"x")
        man = downloader.Manifest(root / "Booth")
        rec = man.record("1", "Kitsu", "Rusk")
        rec.update(name="Rusk", creator="Kitsu")
        rec["files"]["f"] = {"path": "p.unitypackage", "size": 1}
        man.save()
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True,
                                                      "ui": {"toured": True}}, lan=False)
        with self.srv.lib.lock:   # (in memory only)
            self.srv.lib.data["items"] = [
                library.item("booth", "1", name="Rusk", creator="Kitsu", url="https://booth.pm/ja/items/1"),
                library.item("booth", "2", name="Hoodie for Rusk", creator="Mochi", url="https://booth.pm/ja/items/2")]
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

    def viewer(self, browser, asked):
        site = REPO / "site"
        png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                            "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
        page = browser.new_page()

        def serve(route):
            url = route.request.url
            asked.append(url)
            if url.startswith("https://hoard-share.furryup.link/"):   # the share server: the Worker, here
                return route.fulfill(response=route.fetch(url=self.origin + url.split("furryup.link", 1)[1]))
            if url.startswith("https://hoard.furryup.link/"):
                name = url.split("hoard.furryup.link/", 1)[1].split("#")[0].split("?")[0]
                kind = {"html": "text/html", "js": "text/javascript", "css": "text/css"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
                return route.fulfill(path=str(site / name), content_type=kind) if (site / name).is_file() else route.fulfill(status=404)
            return route.fulfill(body=png, content_type="image/png")
        page.route("**/*", serve)
        return page

    def test_a_short_link_from_start_to_end(self):
        from playwright.sync_api import sync_playwright
        made = self.api("/api/sets", {"action": "create", "name": "Rusk, winter", "items": [RUSK, HOODIE]})["made"]
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.click('#storeSeg [data-store="Sets"]')
            page.locator("#setView .settile", has_text="Rusk, winter").click()
            page.click('#setView [data-setx="share"]')
            dialog = page.locator("dialog.share")
            self.assertIn("14 days", dialog.locator(".shortlink").inner_text())
            self.assertEqual(dialog.locator(".shortlink input").count(), 0, "none until it's asked for")
            dialog.get_by_role("button", name="Make a short link").click()
            page.get_by_text("Made a short link. It works until").wait_for()
            link = dialog.locator(".shortlink input").input_value()
            sid, key = SHORT_LINK.fullmatch(link).groups()
            kept = sets.SetStore().load()["sets"][0]["short"]
            self.assertEqual((kept["id"], kept["key"]), (sid, key))
            locked = shortlinks.fetch(sid)["data"]
            self.assertNotIn("Rusk", locked)
            self.assertNotIn(key, locked)
            self.assertIn("It works until", dialog.locator(".shortlink").inner_text())
            dialog.get_by_role("button", name="Close").click()

            # the viewer: fetched by its id, unlocked with its key, which is never sent
            asked = []
            view = self.viewer(browser, asked)
            view.goto(link)
            view.locator("#setView").wait_for()
            self.assertEqual(view.locator("#setName").inner_text(), "Rusk, winter")
            self.assertEqual(view.locator(".sv-item b").all_inner_texts(), ["Rusk", "Hoodie for Rusk"])
            self.assertIn("This short link works until", view.locator("#setWhere").inner_text())
            self.assertIn(f"https://hoard-share.furryup.link/v1/sets/{sid}", asked)
            self.assertFalse(any(key in u or "#" in u for u in asked), "the key never leaves the page")

            # changed since: updated, the same link shows it as it is now
            self.api("/api/sets", {"action": "note", "id": made, "note": "Snowy worlds"})
            page.click('#setView [data-setx="share"]')
            self.assertIn("changed since", dialog.locator(".shortlink").inner_text())
            dialog.get_by_role("button", name="Update the link").click()
            page.get_by_text("Updated the short link.").wait_for()
            self.assertEqual(dialog.locator(".shortlink input").input_value(), link)
            self.assertNotIn("changed since", dialog.locator(".shortlink").inner_text())
            dialog.get_by_role("button", name="Close").click()
            view.reload()
            view.locator("#setNote", has_text="Snowy worlds").wait_for()

            # someone else adds it to their Hoard from the short link
            page.click('#setView [data-setx="back"]')
            page.click('#setView [data-setx="import"]')
            page.fill("dialog[open] #askName", link)
            page.keyboard.press("Enter")
            page.get_by_text("Added the shared set.").wait_for()
            added = sets.SetStore().load()["sets"][1]
            self.assertEqual((added["name"], added["note"], added["items"]), ("Rusk, winter (2)", "Snowy worlds", [RUSK, HOODIE]))
            self.assertNotIn("short", added, "the sharer's link stays the sharer's")

            # deleted, here: the viewer says it's gone
            page.click('#setView [data-setx="back"]')
            page.locator("#setView .settile", has_text="Rusk, winter").first.click()
            page.click('#setView [data-setx="share"]')
            dialog.get_by_role("button", name="Delete the short link").click()
            page.click("#askDialog[open] button[value=yes]")
            page.get_by_text("Deleted the short link.").wait_for()
            self.assertEqual(dialog.locator(".shortlink input").count(), 0)
            self.assertNotIn("short", sets.SetStore().load()["sets"][0])
            with self.assertRaises(shortlinks.Gone):
                shortlinks.fetch(sid)
            view.reload()
            view.locator("#setProblem").wait_for()
            self.assertIn("run out", view.locator("#setProblemWhy").inner_text())
            self.assertEqual(errors, [])
            browser.close()

    def test_the_viewer_says_what_went_wrong(self):
        """An error page on the way (Cloudflare's own, say) is the server being busy, and no answer at all is the
        connection."""
        from playwright.sync_api import sync_playwright
        link = "https://hoard.furryup.link/set.html#S1.abcDEF0123." + "k" * 22
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for answer, said in ((lambda r: r.fulfill(status=503, body="<html>Error 1027</html>", content_type="text/html",
                                                      headers={"Access-Control-Allow-Origin": "https://hoard.furryup.link"}), "busy"),
                                 (lambda r: r.abort(), "Couldn't reach Hoard's share server")):
                page = self.viewer(browser, [])
                page.route("https://hoard-share.furryup.link/**", answer)
                page.goto(link)
                page.locator("#setProblem").wait_for()
                self.assertIn(said, page.locator("#setProblemWhy").inner_text())
                page.close()
            browser.close()

    def test_a_deleted_set_takes_its_short_link_with_it(self):
        made = self.api("/api/sets", {"action": "create", "name": "Rusk", "items": [RUSK]})["made"]
        code = self.api("/api/sets", {"action": "share", "id": made})["code"]
        got = self.api("/api/sets", {"action": "short", "id": made, "code": code, "key": "k" * 22, "data": "A" * 60})
        sid = SHORT_LINK.fullmatch(got["short"]["link"]).group(1)
        self.assertEqual(shortlinks.fetch(sid)["data"], "A" * 60)
        self.assertEqual(self.api("/api/sets", {"action": "delete", "id": made}), {"ok": True, "made": None})
        with self.assertRaises(shortlinks.Gone):
            shortlinks.fetch(sid)

    def test_what_hoard_wont_do(self):
        made = self.api("/api/sets", {"action": "create", "name": "Rusk", "items": [RUSK]})["made"]
        code = self.api("/api/sets", {"action": "share", "id": made})["code"]
        stale = self.api("/api/sets", {"action": "short", "id": made, "code": a_code(note="old"), "key": "k" * 22, "data": "A" * 60})
        self.assertEqual(stale["status"], 409, "only the set as it is now")
        bad = self.api("/api/sets", {"action": "short", "id": made, "code": code, "key": "short", "data": "A" * 60})
        self.assertEqual(bad["status"], 400)
        with mock.patch.object(shortlinks, "SERVER", "http://127.0.0.1:9"):
            egress._TEST_ORIGINS.add("http://127.0.0.1:9")
            self.addCleanup(egress._TEST_ORIGINS.discard, "http://127.0.0.1:9")
            off = self.api("/api/sets", {"action": "short", "id": made, "code": code, "key": "k" * 22, "data": "A" * 60})
            self.assertEqual(off["status"], 502)
            self.assertIn("Couldn't reach Hoard's share server", off["error"])
        self.assertNotIn("short", sets.SetStore().load()["sets"][0])
        gone = self.api("/api/sets", {"action": "open-short", "short": "abcdefghij"})
        self.assertEqual(gone["status"], 404)
        self.assertIn("14 days", gone["error"])


if __name__ == "__main__":
    unittest.main()
