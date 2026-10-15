"""Sets (hoard/sets.py): products you group to use together, listed in catalog.json for Hoard for Unity."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import downloader, sets
from hoard.tags import tag_key

RUSK, HOODIE = tag_key("Booth", "Rusk"), tag_key("Booth", "Hoodie for Rusk")


class Store(unittest.TestCase):
    def setUp(self):
        self.store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")

    def test_make_change_and_delete(self):
        made = self.store.change({"action": "create", "name": "Rusk, winter", "items": [RUSK, HOODIE, RUSK]})["made"]
        self.assertEqual(self.store.load()["sets"], [{"id": made, "name": "Rusk, winter", "items": [RUSK, HOODIE]}])
        self.store.change({"action": "rename", "id": made, "name": "Rusk winter"})
        self.store.change({"action": "remove", "id": made, "items": [RUSK]})
        self.store.change({"action": "add", "id": made, "items": [RUSK, "not a key!", HOODIE]})
        self.assertEqual(self.store.load()["sets"][0], {"id": made, "name": "Rusk winter", "items": [HOODIE, RUSK]})
        self.store.change({"action": "delete", "id": made})
        self.assertEqual(self.store.load()["sets"], [])

    def test_what_cant_be_done(self):
        for body in ({"action": "create", "name": "  "}, {"action": "rename", "id": "nope", "name": "x"},
                     {"action": "explode", "id": "x"}, {"action": "create", "name": 7}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.store.change(body)

    def test_a_damaged_file(self):
        self.store.path.write_text('{"sets": [{"id": "ab", "name": "\\u202eevil", "items": ["booth:rusk", 4]}, '
                                   '{"id": "../x", "name": "y"}, "nope"]}', "utf-8")
        self.assertEqual(self.store.load()["sets"], [{"id": "ab", "name": "evil", "items": ["booth:rusk"]}])
        self.store.path.write_text("{not json", "utf-8")
        self.assertEqual(self.store.load(), {"sets": []})


BOOTH_PIC = "https://booth.pximg.net/c/300x300_a2_g5/11d082f4/i/1/03e2fc69_base_resized.jpg"


def _png(w: int, h: int) -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"\xc8\x78\x3c" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


PNG_4x3 = _png(40, 30)
SHARED = {"name": "Rusk, winter", "note": "For snowy worlds.\nHair: the short one.", "photos": ["https://i.imgur.com/abc.png"],
          "items": [RUSK, HOODIE, "local:mypants"],
          "products": {RUSK: {"store": "booth", "id": "1", "name": "Rusk", "creator": "Kitsu", "url": "https://booth.pm/ja/items/1",
                              "thumbnail": BOOTH_PIC},
                       HOODIE: {"store": "booth", "name": "Hoodie for Rusk", "creator": "Mochi"},
                       "local:mypants": {"store": "local", "name": "My Pants"}}}


def packed(doc: dict) -> str:
    """A code, packed by hand: what someone could make without Hoard."""
    import base64
    import zlib
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = c.compress(json.dumps(doc).encode()) + c.flush()
    return sets.CODE_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


class Pictures(unittest.TestCase):
    """A picture you choose for a set's tile: checked by what it is, a new file each time, gone with its set."""

    def setUp(self):
        self.store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")
        __import__("shutil").rmtree(sets.pictures_dir(), True)

    def test_choose_change_and_take_off(self):
        import base64
        png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 30).decode()
        made = self.store.change({"action": "create", "name": "Rusk"})["made"]
        self.store.change({"action": "picture", "id": made, "image": png})
        first = sets.picture_file(self.store.load()["sets"][0])
        self.assertEqual((first.parent, first.suffix), (sets.pictures_dir(), ".png"))
        self.store.change({"action": "picture", "id": made, "image": png})
        second = sets.picture_file(self.store.load()["sets"][0])
        self.assertNotEqual(first, second, "a new name, so a page never shows the old one")
        self.assertEqual(list(sets.pictures_dir().iterdir()), [second], "the one it replaced is gone")
        for bad in ("data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode(),
                    "data:image/png;base64,!!!", "x" * (800 * 1024), 12):
            with self.assertRaises(ValueError):
                self.store.change({"action": "picture", "id": made, "image": bad})
        self.assertEqual(sets.picture_file(self.store.load()["sets"][0]), second, "a picture refused changes nothing")
        self.store.change({"action": "picture", "id": made, "image": None})
        self.assertNotIn("picture", self.store.load()["sets"][0])
        self.assertEqual(list(sets.pictures_dir().iterdir()), [])
        self.store.change({"action": "picture", "id": made, "image": png})
        self.store.change({"action": "delete", "id": made})
        self.assertEqual(list(sets.pictures_dir().iterdir()), [], "deleting a set deletes its picture")

    def test_a_picture_name_from_a_file_is_checked(self):
        raw = {"sets": [{"id": "a1", "name": "x", "items": [], "picture": "../../etc/passwd"},
                        {"id": "b2", "name": "y", "items": [], "picture": "0123abcd.png"}]}
        clean = sets.SetStore.sanitize(raw)["sets"]
        self.assertNotIn("picture", clean[0])
        self.assertEqual(clean[1]["picture"], "0123abcd.png")
        self.assertIsNone(sets.picture_file(clean[1]), "named, but not there: none (a backup brings the set, not its picture)")


class Sharing(unittest.TestCase):
    """A set shared as a code: the set itself, in a link to the viewer on Hoard's website, never uploaded."""

    def test_there_and_back(self):
        code, n = sets.share_code(SHARED)
        self.assertEqual(n, 2, "your own (Local) products aren't shared")
        self.assertNotIn("pants", json.dumps(sets.from_code(code)).lower())
        for given in (code, sets.share_link(code), f"  {code[:20]}\n{code[20:]} ", "Look: " + sets.share_link(code)):
            got = sets.from_code(given)
            self.assertEqual((got["name"], got["note"], got["photos"], got["items"]),
                             ("Rusk, winter", SHARED["note"], SHARED["photos"], [RUSK, HOODIE]))
            self.assertEqual(got["products"][RUSK]["thumbnail"], BOOTH_PIC)
            self.assertEqual(got["products"][RUSK]["url"], "https://booth.pm/ja/items/1")
        self.assertTrue(sets.share_link(code).startswith("https://hoard.furryup.link/set.html#H1."))

    def test_what_a_code_cant_bring(self):
        """A code is from anyone: every part is checked as Hoard's own file is."""
        got = sets.from_code(packed({"v": 1, "n": "\u202eevil", "p": ["https://evil.example/x.png", "http://i.imgur.com/a.png",
                                                                       "https://i.imgur.com/ok.png"], "i": [
            ["booth", "1", "Rusk", "Kitsu", "javascript:alert(1)", "https://evil.example/pic.jpg"],
            ["booth", "2", "Hoodie", "Mochi", "https://booth.pm.evil.example/items/2", "https://public-files.gumroad.com/x"],
            ["local", "", "Mine"], ["nowhere", "", "Thing"], ["booth", "3", ""], "not a row", [7, 8]]}))
        self.assertEqual(got["name"], "evil")
        self.assertEqual(got["photos"], ["https://i.imgur.com/ok.png"], "photos only from the photo sites, https only")
        self.assertEqual(got["items"], [tag_key("booth", "Rusk"), tag_key("booth", "Hoodie")])
        for p in got["products"].values():
            self.assertNotIn("url", p, "a store page only on the store's own site")
            self.assertNotIn("thumbnail", p, "a picture only from the store's own image host")
        for bad in ("", "nonsense", "H1.", "H1.!!!!", "H1." + "A" * 400, packed({"v": 2, "i": []}), packed({"v": 1, "i": []}),
                    sets.CODE_PREFIX + "x" * (sets.MAX_CODE + 1), None, 7):
            with self.subTest(bad=str(bad)[:30]), self.assertRaises(ValueError):
                sets.from_code(bad)

    def test_a_code_that_unpacks_to_too_much(self):
        """A small code that unpacks to gigabytes (a "zip bomb") is refused before it's all unpacked."""
        import base64
        import zlib
        c = zlib.compressobj(9, zlib.DEFLATED, -15)
        raw = c.compress(b'{"v":1,"i":[],"n":"' + b"a" * (64 << 20)) + c.flush()
        code = sets.CODE_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")
        self.assertLess(len(code), 200_000)
        with self.assertRaises(ValueError):
            sets.from_code(code)

    def test_added_with_its_products(self):
        store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")
        made = store.change({"action": "import", "code": sets.share_code(SHARED)[0]})["made"]
        again = store.change({"action": "import", "code": sets.share_code(SHARED)[0]})["made"]
        mine = {s["id"]: s for s in store.load()["sets"]}
        self.assertEqual(mine[made]["name"], "Rusk, winter")
        self.assertEqual(mine[again]["name"], "Rusk, winter (2)", "a set of yours keeps its name")
        self.assertEqual(mine[made]["products"][RUSK]["creator"], "Kitsu")
        self.assertEqual(mine[made]["photos"], ["https://i.imgur.com/abc.png"])

    def test_note_and_photos(self):
        store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")
        made = store.change({"action": "create", "name": "x", "items": [RUSK]},
                            details=lambda k: {"store": "booth", "name": "Rusk", "url": "https://booth.pm/ja/items/1"})["made"]
        self.assertEqual(store.load()["sets"][0]["products"][RUSK]["url"], "https://booth.pm/ja/items/1", "what it is, kept")
        store.change({"action": "note", "id": made, "note": "line one\r\n\u202eline two"})
        self.assertEqual(store.load()["sets"][0]["note"], "line one\nline two")
        store.change({"action": "photos", "id": made, "photos": ["https://i.gyazo.com/a.png"]})
        for bad in (["https://evil.example/a.png"], ["https://i.imgur.com/a.png"] * 9, ["javascript:alert(1)"]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                store.change({"action": "photos", "id": made, "photos": bad})
        self.assertEqual(store.load()["sets"][0]["photos"], ["https://i.gyazo.com/a.png"])

    def test_the_viewer_checks_as_hoard_does(self):
        """The viewer (site/set.js) and its page's Content-Security-Policy allow the same hosts Hoard does."""
        import re
        site = Path(__file__).resolve().parent.parent / "site"
        js = (site / "set.js").read_text("utf-8")
        def js_list(name):
            return set(re.findall(r'"([a-z0-9.-]+\.[a-z]+)"', re.search(name + r" = (.*?);", js, re.S).group(1)))
        self.assertEqual(js_list("PHOTO_HOSTS"), set(sets.PHOTO_HOSTS))
        self.assertEqual(js_list("STORE_IMAGE_HOSTS"), {h for hs in sets.STORE_IMAGE_HOSTS.values() for h in hs})
        self.assertIn('"H1."', js)
        self.assertNotIn("innerHTML", js, "nothing from a code becomes page markup")
        html = (site / "set.html").read_text("utf-8")
        csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
        img = re.search(r"img-src ([^;]+)", csp).group(1).split()
        self.assertEqual(set(img) - {"'self'"}, {"https://" + h for h in set(sets.PHOTO_HOSTS) |
                                                 {h for hs in sets.STORE_IMAGE_HOSTS.values() for h in hs}})
        self.assertIn("script-src 'self'", csp)
        self.assertIn("default-src 'none'", csp)


# Links a product in a set can have: its public page, or its creator's. Never one of the buyer's own (a Gumroad
# purchase's download page opens its files for whoever has the link). Hoard 4.2.0 shared those: here, none is kept.
LINKS = [("gumroad", "https://gumroad.com/d/38f42c7471ed9fd07cfad9261e7fce75", None),
         ("gumroad", "https://app.gumroad.com/d/abc", None), ("gumroad", "https://app.gumroad.com/library", None),
         ("gumroad", "https://kitsu.gumroad.com/l/rusk?ref=1#x", "https://kitsu.gumroad.com/l/rusk"),
         ("gumroad", "https://gumroad.com/l/rusk", "https://gumroad.com/l/rusk"),
         ("gumroad", "https://kitsu.gumroad.com/", "https://kitsu.gumroad.com"), ("gumroad", "https://kitsu.gumroad.com/p/x", None),
         ("jinxxy", "https://jinxxy.com/my/inventory/3973499687230506857", None),
         ("jinxxy", "https://jinxxy.com/Kitsu/rusk", "https://jinxxy.com/Kitsu/rusk"),
         ("jinxxy", "https://jinxxy.com/Kitsu", "https://jinxxy.com/Kitsu"), ("jinxxy", "https://jinxxy.com/Kitsu/products", None),
         ("jinxxy", "https://jinxxy.com/market/browse", None), ("jinxxy", "https://jinxxy.com/a/b/c", None),
         ("booth", "https://booth.pm/ja/items/12345", "https://booth.pm/ja/items/12345"),
         ("booth", "https://kitsu.booth.pm/items/12345", "https://kitsu.booth.pm/items/12345"),
         ("booth", "https://kitsu.booth.pm/", "https://kitsu.booth.pm"),
         ("booth", "https://accounts.booth.pm/library", None), ("booth", "https://accounts.booth.pm/orders/1", None),
         ("payhip", "https://payhip.com/b/AbC12", "https://payhip.com/b/AbC12"), ("payhip", "https://payhip.com/b-account", None),
         ("itch", "https://kitsu.itch.io/rusk", "https://kitsu.itch.io/rusk"),
         ("itch", "https://kitsu.itch.io/rusk/download/SECRETKEY", None), ("itch", "https://itch.io/my-purchases", None),
         ("booth", "https://booth.pm.evil.example/items/1", None), ("gumroad", "http://kitsu.gumroad.com/l/a", None),
         ("gumroad", "https://user@kitsu.gumroad.com/l/a", None), ("local", "https://kitsu.gumroad.com/l/a", None)]


class PublicPagesOnly(unittest.TestCase):
    def test_only_a_public_page(self):
        for store, url, want in LINKS:
            with self.subTest(url=url):
                self.assertEqual(sets.product_link(store, url), want)

    def test_the_viewer_agrees(self):
        """site/set.js checks a link as product_link does, so a link shared from 4.2.0 doesn't show one of the
        sharer's own pages."""
        import re
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("needs Node.js")
        js = (Path(__file__).resolve().parent.parent / "site" / "set.js").read_text("utf-8")
        fn = re.search(r"  const NOT_A_SHOP.*?\n  }\n", js, re.S).group(0)
        script = fn + "\nconst cases = " + json.dumps([[s, u] for s, u, _ in LINKS]) + \
            ";\nprocess.stdout.write(JSON.stringify(cases.map(([s, u]) => storePage(s, u) || null)));"
        got = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(got, [want for _, _, want in LINKS])

    def test_a_set_never_shares_your_own_pages(self):
        """What a set remembers from 4.2.0 is checked again: a Gumroad download page goes, and what Hoard knows of the
        product now (its public page, else its creator's) is shared instead."""
        store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")
        store.path.write_text(json.dumps({"sets": [{"id": "a1", "name": "Rusk", "items": [RUSK, "gumroad:ears", "jinxxy:tail"],
            "products": {"gumroad:ears": {"store": "gumroad", "name": "Ears", "url": "https://gumroad.com/d/38f42c7471ed9fd07cfad9261e7fce75"},
                         "jinxxy:tail": {"store": "jinxxy", "name": "Tail", "url": "https://jinxxy.com/my/inventory/123",
                                         "thumbnail": "https://jinxxy-c.jinxxy-cdn.com/cdn-cgi/image/width=512/a/1.png"}}}]}))
        s = store.load()["sets"][0]
        self.assertNotIn("url", s["products"]["gumroad:ears"])
        self.assertNotIn("url", s["products"]["jinxxy:tail"])
        self.assertTrue(s["products"]["jinxxy:tail"]["thumbnail"].startswith("https://jinxxy-c.jinxxy-cdn.com/"), "Jinxxy's pictures")
        now = {"gumroad:ears": {"store": "gumroad", "name": "Ears", "url": "https://kitsu.gumroad.com/l/ears"}}
        code, n = sets.share_code(s, now.get)
        self.assertEqual(n, 2, "(Rusk: nothing known of it, so it isn't in it)")
        self.assertNotIn("/d/", json.dumps(sets.from_code(code)))
        self.assertEqual(sets.from_code(code)["products"]["gumroad:ears"]["url"], "https://kitsu.gumroad.com/l/ears")

    def test_its_own_page_once_known(self):
        """A product added before a refresh found its own page is remembered with its creator's; shared after it,
        it has its own."""
        s = {"name": "s", "items": ["gumroad:ears"], "products": {"gumroad:ears": {
            "store": "gumroad", "name": "Ears", "creator": "Kitsu", "url": "https://kitsu.gumroad.com"}}}
        code = sets.share_code(s)[0]
        self.assertEqual(sets.from_code(code)["products"]["gumroad:ears"]["url"], "https://kitsu.gumroad.com")
        now = {"gumroad:ears": {"store": "gumroad", "name": "Ears", "url": "https://kitsu.gumroad.com/l/ears"}}
        code = sets.share_code(s, now.get)[0]
        got = sets.from_code(code)["products"]["gumroad:ears"]
        self.assertEqual((got["url"], got["creator"]), ("https://kitsu.gumroad.com/l/ears", "Kitsu"))


class PhotoPages(unittest.TestCase):
    """A photo's page on a photo site (imgur.com/<id>, as people copy it) is read for the picture it shows."""

    def test_the_picture_a_page_shows(self):
        page = ('<head><meta name="twitter:image" content="https://i.imgur.com/fOJAk3Lh.jpg">'
                '<meta property="og:image:width" content="600">'
                '<meta data-react-helmet="true" property="og:image" content="https://i.imgur.com/fOJAk3L.jpeg?fb"></head>')
        self.assertEqual(sets.picture_on_page(page), "https://i.imgur.com/fOJAk3L.jpeg", "og:image, in full: not ?fb's crop")
        self.assertEqual(sets.picture_on_page(page.replace('property="og:image"', 'property="og:title"')),
                         "https://i.imgur.com/fOJAk3Lh.jpg", "else twitter:image")
        self.assertEqual(sets.picture_on_page("<meta content='https://preview.redd.it/abc123.jpeg?width=640&amp;s=x' "
                                              "property='og:image'>"), "https://i.redd.it/abc123.jpeg", "Reddit's own picture")
        self.assertIsNone(sets.picture_on_page('<meta property="og:image" content="https://evil.example/a.png">'),
                          "only from the photo sites the viewer shows")
        self.assertIsNone(sets.picture_on_page("<p>no picture</p>"))
        self.assertIsNone(sets.picture_on_page(None))

    def test_which_links_are_pages(self):
        for url, want in (("https://imgur.com/fOJAk3L", True), ("https://www.reddit.com/r/vrchat/comments/x/y/", True),
                          ("https://bsky.app/profile/a.bsky.social/post/3k", True), ("https://gyazo.com/abc", True),
                          ("https://i.imgur.com/fOJAk3L.jpeg", False), ("https://evil.example/a", False),
                          ("http://imgur.com/fOJAk3L", False), ("https://imgur.com.evil.example/x", False)):
            self.assertEqual(bool(sets.photo_page(url)), want, url)

    def test_from_a_page(self):
        asked = []

        def fetch(url):
            asked.append(url)
            return {"https://gyazo.com/abc": '<meta property="og:image" content="https://i.gyazo.com/abc.png">'}.get(url)
        self.assertEqual(sets.photo_from_page("https://gyazo.com/abc", fetch), "https://i.gyazo.com/abc.png")
        self.assertEqual(sets.photo_from_page("https://imgur.com/fOJAk3L", fetch), "https://i.imgur.com/fOJAk3L.jpeg",
                         "an Imgur picture's page that can't be read is still its picture")
        with self.assertRaisesRegex(ValueError, "couldn't find a picture"):
            sets.photo_from_page("https://imgur.com/a/album", fetch)
        with self.assertRaisesRegex(ValueError, "photo site Hoard knows"):
            sets.photo_from_page("https://evil.example/a", fetch)
        self.assertEqual(asked, ["https://gyazo.com/abc", "https://imgur.com/fOJAk3L", "https://imgur.com/a/album"],
                         "only the photo site's own page is asked for")


class InTheCatalog(unittest.TestCase):
    def test_sets_by_their_products_folders(self):
        tmp = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        root = tmp / "dl"
        for key, creator, name in (("1", "Kitsu", "Rusk"), ("2", "Mochi", "Hoodie for Rusk")):
            folder = root / "Booth" / creator / name
            folder.mkdir(parents=True)
            (folder / "p.unitypackage").write_bytes(b"x")
            man = downloader.Manifest(root / "Booth")
            rec = man.record(key, creator, name)
            rec.update(name=name, creator=creator)
            rec["files"]["f"] = {"path": "p.unitypackage", "size": 1}
            man.save()
        sets.SetStore().change({"action": "create", "name": "Rusk, winter", "items": [HOODIE, RUSK, tag_key("Booth", "Gone")]})
        sets.SetStore().change({"action": "create", "name": "Empty", "items": []})
        downloader.build_catalog({"root": str(root), "tags": {}}, root)
        cat = json.loads((root / "catalog.json").read_text("utf-8"))
        self.assertEqual(cat["sets"], [{"name": "Rusk, winter", "items": ["Booth/Mochi/Hoodie for Rusk", "Booth/Kitsu/Rusk"]}],
                         "products it doesn't have, and sets with none, are left out")


try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Page(unittest.TestCase):
    def test_make_a_set_and_show_it(self):
        import threading
        from playwright.sync_api import sync_playwright
        from hoard import config, server
        tmp = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        root = tmp / "dl"
        for key, creator, name in (("1", "Kitsu", "Rusk"), ("2", "Mochi", "Hoodie for Rusk"), ("3", "Mochi", "Skirt")):
            folder = root / "Booth" / creator / name
            folder.mkdir(parents=True)
            (folder / "p.unitypackage").write_bytes(b"x")
            man = downloader.Manifest(root / "Booth")
            rec = man.record(key, creator, name)
            rec.update(name=name, creator=creator)
            rec["files"]["f"] = {"path": "p.unitypackage", "size": 1}
            man.save()
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.click("nav.apptabs a[href='/downloads']")
            page.click("#selectBtn")
            page.locator('#grid .slot[aria-label^="Rusk"]').click()
            page.locator('#grid .slot[aria-label^="Hoodie for Rusk"]').click()
            page.click("#bulkActs [data-group='Sets']")
            self.assertEqual(page.locator(".selmenu [role=menuitem]").all_inner_texts(), ["New set from these..."],
                             "no sets yet: nothing to add to")
            page.locator(".selmenu [role=menuitem]").first.click()   # a set made of what's selected
            page.fill("dialog[open] #askName", "Rusk, winter")
            page.locator("dialog[open] button", has_text="OK").click()
            page.get_by_text("Made the set Rusk, winter, with 2 products in it.").wait_for()
            page.click("#bulkActs [data-group='Sets']")
            self.assertEqual(page.locator(".selmenu [role=menuitem]").all_inner_texts(),
                             ["New set from these...", "Add to Rusk, winter"])
            page.keyboard.press("Escape")
            page.click("#bulkDone")
            page.click('#stores [data-store="Sets"]')
            page.locator("#setView .settile", has_text="Rusk, winter").click()
            page.wait_for_function("() => document.querySelectorAll('#grid .slot').length === 2")
            self.assertIn("set=", page.url)
            page.locator('#grid .slot[aria-label^="Hoodie for Rusk"]').click()
            self.assertIn("Rusk, winter", page.locator("#detail .chips", has_text="Rusk, winter").inner_text())
            page.locator("#detail [data-act='unset']").click()
            page.wait_for_function("() => document.querySelectorAll('#grid .slot').length === 1")
            browser.close()
        [s] = sets.SetStore().load()["sets"]
        self.assertEqual((s["name"], s["items"]), ("Rusk, winter", [RUSK]))



@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Tab(unittest.TestCase):
    """The Sets tab: sets of any products, downloaded or not, yours or not yet; shared, and added from a share."""

    def setUp(self):
        import threading
        from hoard import config, library, server
        from hoard.marks import MarkStore
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
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
                library.item("booth", "2", name="Hoodie for Rusk", creator="Mochi", url="https://booth.pm/ja/items/2"),
                library.item("booth", "3", name="Secret Thing", creator="Shy", url="https://booth.pm/ja/items/3")]
        MarkStore().set_pin("2468")
        MarkStore().change("hidden", [tag_key("booth", "Secret Thing")], True)
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

    def test_hidden_products_stay_out_while_locked(self):
        secret = tag_key("booth", "Secret Thing")
        made = sets.SetStore().change({"action": "create", "name": "s", "items": [RUSK, secret]})["made"]
        view = self.api("/api/sets")
        self.assertEqual([i["key"] for i in view["sets"][0]["items"]], [RUSK])
        self.assertTrue(view["hidden_left_out"])
        self.assertNotIn("Secret", json.dumps(view))
        shared = self.api("/api/sets", {"action": "share", "id": made})
        self.assertEqual((shared["count"], shared["left_out"]), (1, 1))
        self.assertNotIn("Secret", json.dumps(sets.from_code(shared["code"])), "never in a code, locked or not")
        self.assertNotIn(secret, self.api("/api/library")["sets"][0]["items"])
        self.assertEqual(self.api("/api/sets", {"action": "add", "id": made, "items": [secret]}).get("ok"), True)
        self.assertEqual(sets.SetStore().load()["sets"][0]["items"], [RUSK, secret], "nor taken out, while locked")

    def test_a_photo_from_its_page(self):
        made = self.api("/api/sets", {"action": "create", "name": "Rusk", "items": [RUSK]})["made"]
        page = '<meta property="og:image" content="https://i.imgur.com/fOJAk3L.jpeg?fb">'
        from hoard import server
        with mock.patch.object(server, "read_photo_page", lambda url: page if url == "https://imgur.com/fOJAk3L" else None):
            self.assertEqual(self.api("/api/sets", {"action": "photos", "id": made, "photos": ["https://imgur.com/fOJAk3L"]}).get("ok"), True)
            self.assertEqual(sets.SetStore().load()["sets"][0]["photos"], ["https://i.imgur.com/fOJAk3L.jpeg"], "its picture")
            bad = self.api("/api/sets", {"action": "photos", "id": made, "photos": ["https://i.imgur.com/fOJAk3L.jpeg",
                                                                                   "https://gyazo.com/nothing"]})
        self.assertEqual(bad["status"], 400)
        self.assertIn("couldn't find a picture", bad["error"])
        self.assertEqual(sets.SetStore().load()["sets"][0]["photos"], ["https://i.imgur.com/fOJAk3L.jpeg"], "unchanged")

    def test_make_share_and_add_a_set(self):
        from playwright.sync_api import sync_playwright
        code = sets.share_code({"name": "Fox outfit", "items": ["jinxxy:foxears", RUSK], "products": {
            "jinxxy:foxears": {"store": "jinxxy", "name": "Fox Ears", "creator": "Tails", "url": "https://jinxxy.com/tails/foxears"},
            RUSK: {"store": "booth", "name": "Rusk", "creator": "Kitsu", "url": "https://booth.pm/ja/items/1"}}})[0]
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.locator("#grid .slot").first.wait_for()
            # in the Library: one downloaded and one not, made a set of, from the right-click menu; Enter names it
            page.locator('#grid .slot[aria-label^="Rusk"]').click(modifiers=["Control"])
            page.locator('#grid .slot[aria-label^="Hoodie for Rusk"]').click(modifiers=["Control"])
            page.locator('#grid .slot[aria-label^="Rusk"]').click(button="right")
            page.get_by_role("menuitem", name="New set from these...").click()
            page.fill("dialog[open] #askName", "Rusk, winter")
            page.keyboard.press("Enter")
            page.get_by_text("Made the set Rusk, winter, with 2 products in it.").wait_for()
            page.keyboard.press("Escape")
            # the Sets tab, beside the stores: each set a big tile; opened, a folder of its products
            page.click('#storeSeg [data-store="Sets"]')
            tile = page.locator("#setView .settile", has_text="Rusk, winter")
            self.assertIn("2 products, 1 downloaded, 1 to download", tile.inner_text())
            self.assertEqual(page.locator("#grid .slot").count(), 0, "every set's tile, and nothing else")
            tile.click()
            page.wait_for_function("() => document.querySelectorAll('#grid .slot').length === 2")   # both are yours
            self.assertIn("store=Sets&set=", page.url)
            self.assertEqual(page.locator("#setMore .slot").count(), 0)
            # shared: the link holds the set
            page.click('#setView [data-setx="share"]')
            link = page.locator("dialog.share input").input_value()
            self.assertTrue(link.startswith("https://hoard.furryup.link/set.html#H1."))
            self.assertEqual(sets.from_code(link)["items"], [RUSK, HOODIE])
            page.locator("dialog.share button", has_text="Close").click()
            # its own picture, on its tile and in its folder
            with page.expect_file_chooser() as chosen:
                page.click('#setView [data-setx="picture"]')
            chosen.value.set_files(files=[{"name": "fox.png", "mimeType": "image/png", "buffer": PNG_4x3}])
            page.get_by_text("Its tile shows that picture now.").wait_for()
            cover = page.locator("#setView .sethead .art img")
            self.assertRegex(cover.get_attribute("src"), r"^/setcover/[0-9a-f]+/[0-9a-f]{8}\.(png|jpg)\?k=")
            page.wait_for_function("() => document.querySelector('#setView .sethead .art img').naturalWidth === 40")
            # added from someone else's: it opens, and what isn't yours says where to buy it
            page.click('#setView [data-setx="back"]')
            page.click('#setView [data-setx="import"]')
            page.fill("dialog[open] #askName", sets.share_link(code))
            page.keyboard.press("Enter")
            page.get_by_text("Added the shared set.").wait_for()
            page.locator("#setView h2", has_text="Fox outfit").wait_for()
            self.assertIn("1 to buy", page.locator("#setView .sethead").inner_text())
            ears = page.locator("#setMore .slot", has_text="Fox Ears")
            self.assertIn("Not yours yet", page.locator("#setMore").inner_text())
            self.assertEqual(ears.locator("a").get_attribute("href"), "https://jinxxy.com/tails/foxears")
            self.assertIn("Buy on Jinxxy", ears.inner_text())
            # a note and a photo, kept with the set and shared with it
            self.assertIsNotNone(page.locator("#setView details.setextra").get_attribute("open"), "open to begin with")
            page.fill("#setView [data-setnote]", "Cozy fox look")
            page.click('#setView [data-setx="note"]')
            page.get_by_text("Saved the note.").wait_for()
            page.click('#setView [data-setx="photo"]')
            page.fill("dialog[open] #askName", "https://evil.example/a.png")
            page.keyboard.press("Enter")
            page.get_by_text("isn't a link to a picture on a photo site").wait_for()
            # in Downloads, the same set: what's downloaded as its tiles, the rest after them
            page.click("nav.apptabs a[href='/downloads']")
            page.click('#stores [data-store="Sets"]')
            page.locator("#setView .settile", has_text="Rusk, winter").click()
            page.wait_for_function("() => document.querySelectorAll('#grid .slot').length === 1")
            hoodie = page.locator("#setMore .slot", has_text="Hoodie for Rusk")
            self.assertIn("In your library, not downloaded", page.locator("#setMore").inner_text())
            hoodie.locator("a").click()   # to it in the Library
            page.locator("#detail.open", has_text="Hoodie for Rusk").wait_for()
            # sets are chosen and right-clicked as products are: Select, Ctrl, and what can be done to them
            page.click('#storeSeg [data-store="Sets"]')
            page.locator("#setView .settile", has_text="Rusk, winter").click(button="right")
            self.assertEqual(page.locator(".selmenu [role=menuitem]").all_inner_texts(),
                             ["Open", "Share...", "Download the 1 not downloaded", "Choose a picture...", "Rename", "Delete"])
            page.keyboard.press("Escape")
            page.locator("#setView .settile", has_text="Fox outfit").click(modifiers=["Control"])
            self.assertEqual(page.locator("#bulkCount").inner_text(), "2 selected")
            self.assertEqual(page.locator("#grid .slot").count(), 0, "still every set's tile: none opened")
            page.click("#bulkActs [data-group='Sets']")
            page.get_by_role("menuitem", name="Delete these sets").click()
            page.click("#askDialog[open] button[value=yes]")
            page.locator("#setView .settile").first.wait_for(state="detached")
            self.assertEqual(errors, [])
            browser.close()
        self.assertEqual(sets.SetStore().load()["sets"], [], "both deleted, from the menu")

    def test_the_viewer(self):
        """The set viewer (site/set.html), with its pictures served here: no network, no Hoard."""
        from playwright.sync_api import sync_playwright
        site = Path(__file__).resolve().parent.parent / "site"
        png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                            "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
        code = sets.share_code({"name": "Rusk, winter", "note": "Snowy worlds", "photos": ["https://i.imgur.com/a.png"],
                                "items": [RUSK, "booth:x"], "products": {
            RUSK: {"store": "booth", "name": "Rusk", "creator": "Kitsu", "url": "https://booth.pm/ja/items/1", "thumbnail": BOOTH_PIC},
            "booth:x": {"store": "booth", "name": "<b>x</b>", "creator": "Mochi"}}})[0]
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            asked = []

            def serve(route):
                url = route.request.url
                asked.append(url)
                if url.startswith("https://hoard.furryup.link/"):
                    name = url.split("hoard.furryup.link/", 1)[1].split("#")[0].split("?")[0]
                    kind = {"html": "text/html", "js": "text/javascript", "css": "text/css"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
                    return route.fulfill(path=str(site / name), content_type=kind) if (site / name).is_file() else route.fulfill(status=404)
                return route.fulfill(body=png, content_type="image/png")
            page.route("**/*", serve)
            page.goto(sets.share_link(code))
            page.locator("#setView").wait_for()
            self.assertEqual(page.locator("#setName").inner_text(), "Rusk, winter")
            self.assertEqual(page.locator(".sv-text b").all_inner_texts(), ["Rusk", "<b>x</b>"], "names as text")
            self.assertEqual(page.locator(".sv-item .ph b").all_inner_texts(), ["BX"], "no picture: its initials, as Hoard's tiles")
            self.assertEqual(page.locator(".sv-item .notch.booth").count(), 2, "and each its store's spine")
            self.assertEqual(page.locator(".sv-item a").get_attribute("href"), "https://booth.pm/ja/items/1")
            self.assertIn("Snowy worlds", page.locator("#setNote").inner_text())
            page.wait_for_function("() => [...document.querySelectorAll('.sv-item img, #setPhotos img')].every(i => i.complete && i.naturalWidth)")
            pictures = sorted(u for u in asked if not u.startswith("https://hoard.furryup.link/"))
            self.assertEqual(pictures, sorted([BOOTH_PIC, "https://i.imgur.com/a.png"]), "only the store's and the photo site's")
            self.assertFalse(any("#" in u or "H1." in u for u in asked), "the set never leaves the page")
            page.goto("https://hoard.furryup.link/set.html#H1.broken")   # (a new code: the viewer reads it again)
            page.locator("#setProblem").wait_for()
            self.assertIn("damaged", page.locator("#setProblemWhy").inner_text())
            browser.close()

if __name__ == "__main__":
    unittest.main()
