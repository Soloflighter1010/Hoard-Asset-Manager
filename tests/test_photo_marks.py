"""Issue #346: what's in a set's photo, marked: the set's owner puts a numbered mark where each product is on one of the
set's photos; Hoard's set page and the shared set viewer show each mark, with the product on pointing at it, and a
numbered list beside the photo. Places are kept as 0 to 1000 of the photo's width and height, so they line up at
any size; they travel in the set's share code by place, so a short link holds them, and the share server never reads
them (they're in the locked code)."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase
from hoard import config, library, server, sets
from hoard.tags import tag_key

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _pw:
        _pw.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

SITE = Path(__file__).resolve().parent.parent / "site"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
HAT, HAIR, MINE = tag_key("booth", "Straw Hat"), tag_key("booth", "Long Hair"), tag_key("local", "My Edit")
PHOTO, OTHER = "https://i.imgur.com/rusk.png", "https://i.gyazo.com/other.png"
PRODUCTS = {HAT: {"store": "booth", "name": "Straw Hat", "creator": "Mochi", "url": "https://booth.pm/ja/items/6",
                  "thumbnail": "https://booth.pximg.net/c/72x72/hat.png"},
            HAIR: {"store": "booth", "name": "Long Hair", "creator": "Kitsu", "url": "https://booth.pm/ja/items/7"},
            MINE: {"store": "local", "name": "My Edit"}}


class Kept(IsolatedTestCase):
    def setUp(self):
        self.store = sets.SetStore(Path(tempfile.mkdtemp()) / "sets.json")
        self.sid = self.store.change({"action": "create", "name": "Rusk", "items": [HAT, HAIR, MINE],
                                      "photos": [PHOTO, OTHER]}, PRODUCTS.get)["made"]

    def marks(self):
        return next(s for s in self.store.load()["sets"] if s["id"] == self.sid).get("marks", {})

    def test_checked_as_theyre_kept(self):
        self.store.change({"action": "marks", "id": self.sid, "photo": PHOTO,
                           "marks": [[HAT, 120, 80], [HAIR, 500, 1000], [HAT, 1, 1], ["booth:gone", 5, 5], [MINE, 1001, 3],
                                     [MINE, 3.5, 3], [MINE, True, 3], "nope"]})
        self.assertEqual(self.marks(), {PHOTO: [[HAT, 120, 80], [HAIR, 500, 1000]]},
                         "each product once, only the set's, each place a whole number from 0 to 1000")
        with self.assertRaises(ValueError):
            self.store.change({"action": "marks", "id": self.sid, "photo": "https://i.imgur.com/notthere.png", "marks": []})
        with self.assertRaises(ValueError):
            self.store.change({"action": "marks", "id": self.sid, "photo": PHOTO, "marks": [[HAT, 1, 1]] * 31})
        self.store.change({"action": "marks", "id": self.sid, "photo": OTHER, "marks": [[MINE, 300, 300]]})
        self.store.change({"action": "remove", "id": self.sid, "items": [HAIR]})
        self.assertEqual(self.marks(), {PHOTO: [[HAT, 120, 80]], OTHER: [[MINE, 300, 300]]}, "a product taken out: its marks go")
        self.store.change({"action": "photos", "id": self.sid, "photos": [OTHER]})
        self.assertEqual(self.marks(), {OTHER: [[MINE, 300, 300]]}, "a photo taken out: its marks go")
        self.store.change({"action": "marks", "id": self.sid, "photo": OTHER, "marks": []})
        self.assertEqual(self.marks(), {}, "none left: nothing kept")

    def test_a_hidden_products_mark_stays_while_its_locked(self):
        """While the hidden library is locked, the page never has a hidden product's marks: saving the photo's marks
        from it keeps that product's as they were (one it sends for it anyway changes nothing)."""
        self.store.change({"action": "marks", "id": self.sid, "photo": PHOTO, "marks": [[HAT, 120, 80], [HAIR, 500, 500]]})
        self.store.change({"action": "marks", "id": self.sid, "photo": PHOTO, "marks": [[HAT, 200, 90], [HAIR, 1, 1]]},
                          kept={HAIR})
        self.assertEqual(self.marks(), {PHOTO: [[HAIR, 500, 500], [HAT, 200, 90]]})
        self.store.change({"action": "marks", "id": self.sid, "photo": PHOTO, "marks": []}, kept={HAIR})
        self.assertEqual(self.marks(), {PHOTO: [[HAIR, 500, 500]]}, "taking every mark off leaves the hidden one")

    def test_shared_by_place_and_read_back(self):
        self.store.change({"action": "marks", "id": self.sid, "photo": OTHER, "marks": [[HAIR, 900, 100], [MINE, 10, 10], [HAT, 0, 0]]})
        s = next(s for s in self.store.load()["sets"] if s["id"] == self.sid)
        code, count = sets.share_code(s)
        self.assertEqual(count, 2, "your own (Local) isn't shared")
        got = sets.from_code(code)
        self.assertEqual(got["marks"], {OTHER: [[HAIR, 900, 100], [HAT, 0, 0]]}, "and nor is its mark")
        made = self.store.change({"action": "import", "code": code})["made"]
        self.assertEqual(next(x for x in self.store.load()["sets"] if x["id"] == made)["marks"], got["marks"], "kept as added")

    def test_a_code_from_anyone_is_checked(self):
        """Marks in a code are by place: a place that isn't a photo or a product of the code, a place on the photo out of
        0 to 1000, or anything not a whole number, is left out; a photo or product the code has that Hoard won't take
        doesn't move the others' marks onto the wrong one."""
        raw = {"v": 1, "n": "Mixed", "i": [["nowhere", "", "Bad"], ["booth", "6", "Straw Hat"], ["booth", "7", "Long Hair"]],
               "p": ["https://evil.example/x.png", PHOTO],
               "m": [[1, 1, 10, 20], [1, 2, 30, 40], [0, 1, 5, 5], [1, 0, 5, 5], [1, 2, 99, 99], [1, 1, 2000, 3], [9, 1, 1, 1],
                     [1, 1.5, 1, 1], "x", [1, 2]]}
        import zlib
        packer = zlib.compressobj(9, zlib.DEFLATED, -15)
        code = sets.CODE_PREFIX + sets._b64(packer.compress(json.dumps(raw).encode()) + packer.flush())
        got = sets.from_code(code)
        self.assertEqual(got["photos"], [PHOTO])
        self.assertEqual(got["marks"], {PHOTO: [[HAT, 10, 20], [HAIR, 30, 40]]})

    def test_split_parts_keep_their_own_marks(self):
        self.store.change({"action": "marks", "id": self.sid, "photo": PHOTO, "marks": [[HAT, 1, 2], [HAIR, 3, 4]]})
        made = self.store.split(self.sid, [[HAT], [HAIR]])["made"]
        parts = [next(s for s in self.store.load()["sets"] if s["id"] == m) for m in made]
        self.assertEqual([p.get("marks") for p in parts], [{PHOTO: [[HAT, 1, 2]]}, {PHOTO: [[HAIR, 3, 4]]}])


class InHoard(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        sets.SetStore().path.unlink(missing_ok=True)
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"), "setup_done": True,
                                                      "ui": {"toured": True}}, lan=False)
        with self.srv.lib.lock:   # (in memory only)
            self.srv.lib.data["items"] = [library.item("booth", "6", name="Straw Hat", creator="Mochi", url="https://booth.pm/ja/items/6")]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.sid = sets.SetStore().change({"action": "create", "name": "Rusk", "items": [HAT, HAIR], "photos": [PHOTO]},
                                          PRODUCTS.get)["made"]

    def get(self, path):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=20)
        conn.request("GET", path, headers={"X-Hoard-Key": self.srv.key})
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def test_a_sets_own_photo_and_only_that(self):
        asked = []
        fetch = lambda url, referer, hosts=None: asked.append((url, referer, hosts)) or (PNG, "image/png")   # noqa: E731
        with mock.patch.object(server, "fetch_picture", fetch):
            self.assertEqual(self.get(f"/setphoto/{self.sid}/0?p={server.pic_for(PHOTO)}"), (200, PNG))
            self.assertEqual(self.get(f"/setphoto/{self.sid}/0?p=000000000000")[0], 404, "the address of another photo")
            self.assertEqual(self.get(f"/setphoto/{self.sid}/1?p={server.pic_for(PHOTO)}")[0], 404)
            self.assertEqual(self.get(f"/setphoto/nope/0?p={server.pic_for(PHOTO)}")[0], 404)
        self.assertEqual(asked, [(PHOTO, "https://i.imgur.com/", sets.PHOTO_HOSTS)],
                         "fetched from its photo site only, and a redirect only to a photo site")

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_someone_elses_sets_photos_only_when_asked(self):
        """A set added from someone else's link: its photos are on sites that person chose, so Hoard asks them for the
        photos only once you choose Show the photo (asking tells the site someone's looking)."""
        code, _ = sets.share_code(next(s for s in sets.SetStore().load()["sets"] if s["id"] == self.sid), PRODUCTS.get)
        theirs = sets.SetStore().change({"action": "import", "code": code})["made"]
        asked = []
        fetch = lambda url, referer, hosts=None: asked.append(url) or (PNG, "image/png")   # noqa: E731
        with mock.patch.object(server, "fetch_picture", fetch), sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(self.srv.entry_url())
            page.locator("#grid .slot").first.wait_for()
            page.click('#storeSeg [data-store="Sets"]')
            page.locator(f'#setView .settile[data-setopen="{theirs}"]').click()
            held = page.locator(".setphotos-held")
            held.wait_for()
            self.assertIn("i.imgur.com", held.inner_text())
            self.assertEqual(page.locator(".setphoto img").count(), 0)
            page.wait_for_timeout(300)
            self.assertNotIn(PHOTO, asked, "nothing asked of the photo site yet")
            held.locator("[data-setx=showphotos]").click()
            page.locator(".setphoto-pic > img").wait_for()
            page.wait_for_function("() => document.querySelector('.setphoto-pic > img').complete")
            self.assertIn(PHOTO, asked)
            page.click('#storeSeg [data-store="Sets"]')
            page.locator(f'#setView .settile[data-setopen="{self.sid}"]').click()
            page.locator(".setphoto-pic > img").wait_for()   # (your own set's: shown as it opens)
            browser.close()

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_marked_shown_and_changed_by_keyboard(self):
        sets.SetStore().change({"action": "marks", "id": self.sid, "photo": PHOTO, "marks": [[HAIR, 250, 750]]})
        with mock.patch.object(server, "fetch_picture", lambda url, referer, hosts=None: (PNG, "image/png")), sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.locator("#grid .slot").first.wait_for()
            page.click('#storeSeg [data-store="Sets"]')
            page.locator(f'#setView .settile[data-setopen="{self.sid}"]').click()
            page.locator(".setphoto .pmark").first.wait_for()
            mark = page.locator(".setphoto .pmark")
            self.assertEqual((mark.inner_text().split("\n")[0], mark.get_attribute("aria-label")), ("1", "1: Long Hair, on Booth"))
            self.assertEqual(mark.get_attribute("style"), "left:25%;top:75%", "a share of the photo's size")
            self.assertEqual(mark.get_attribute("href"), "https://booth.pm/ja/items/7")
            self.assertEqual(page.locator(".setphoto .pmarks li .pname b").all_inner_texts(), ["Long Hair"])
            # the editor: placed by keyboard (in the middle), moved with the arrow keys, saved
            page.click("[data-setx=markphoto]")
            dlg = page.locator("dialog.pmark-dlg")
            dlg.wait_for()
            dlg.locator(f'[data-pm-place="{HAT}"]').focus()
            page.keyboard.press("Enter")
            hat = dlg.locator(f'.pmark[data-pmark="{HAT}"]')
            hat.wait_for()
            self.assertEqual(page.evaluate("document.activeElement.dataset.pmark"), HAT, "the new mark has the focus")
            page.keyboard.press("ArrowRight")
            page.keyboard.press("Shift+ArrowUp")
            self.assertEqual(hat.get_attribute("style"), "left:51%;top:45%")
            self.assertIn("Straw Hat is marked.", dlg.locator(".pm-status").inner_text())
            dlg.locator(f'.pmark[data-pmark="{HAIR}"]').focus()
            page.keyboard.press("Delete")
            self.assertEqual(dlg.locator(f'.pmark[data-pmark="{HAIR}"]').count(), 0)
            # and one placed by pointing at the photo
            dlg.locator(f'[data-pm-place="{HAIR}"]').click()
            box = dlg.locator(".pm-edit > img").bounding_box()
            page.mouse.click(box["x"] + box["width"] * 0.9, box["y"] + box["height"] * 0.2)
            dlg.locator("button[value=yes]").click()
            page.locator(".toast", has_text="Saved what's marked on the photo.").wait_for()
            browser.close()
        (marks,) = sets.SetStore().load()["sets"][0]["marks"].values()
        self.assertEqual(marks[0], [HAT, 510, 450])
        self.assertEqual(marks[1][0], HAIR)
        self.assertAlmostEqual(marks[1][1], 900, delta=8)
        self.assertAlmostEqual(marks[1][2], 200, delta=8)
        self.assertEqual(errors, [])

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_a_mark_with_no_link_and_the_tile_it_opens(self):
        """A product of your own has no store page: its mark is still reached by keyboard (Enter opens it, as a click
        does). A mark opens its product's tile on this page: a Library product's, else its download's (a product in
        both is found on either page)."""
        sid = sets.SetStore().change({"action": "create", "name": "Mine", "items": [HAT, MINE], "photos": [PHOTO]},
                                     PRODUCTS.get)["made"]
        sets.SetStore().change({"action": "marks", "id": sid, "photo": PHOTO, "marks": [[MINE, 500, 500]]})
        with mock.patch.object(server, "fetch_picture", lambda url, referer, hosts=None: (PNG, "image/png")), sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(self.srv.entry_url())
            page.locator("#grid .slot").first.wait_for()
            page.click('#storeSeg [data-store="Sets"]')
            page.locator(f'#setView .settile[data-setopen="{sid}"]').click()
            mark = page.locator(f'.setphoto .pmark[data-pmark="{MINE}"]')
            mark.wait_for()
            self.assertEqual((mark.get_attribute("tabindex"), mark.get_attribute("role"), mark.get_attribute("href")), ("0", "button", None))
            page.evaluate("""key => { const s = SETS.sets.find(x => x.id === state.set), row = s.items.find(i => i.key === key);
              row.lib = 'not-on-this-page'; row.download = 99;   // (as on Downloads: in the library too, its tile a download's)
              const t = document.createElement('div'); t.className = 'slot'; t.dataset.id = '99';
              t.addEventListener('click', () => { window.__opened = true; }); document.querySelector('#grid').appendChild(t); }""", MINE)
            mark.focus()
            page.keyboard.press("Enter")
            page.wait_for_function("() => window.__opened === true")
            browser.close()


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class TheViewer(IsolatedTestCase):
    def test_marked_photos_in_a_shared_set(self):
        code = sets.share_code({"name": "Rusk", "items": [HAT, HAIR], "products": PRODUCTS, "photos": [PHOTO, OTHER],
                                "marks": {PHOTO: [[HAIR, 100, 900], [HAT, 600, 200]]}})[0]
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})

            def serve(route):
                url = route.request.url
                if url.startswith("https://hoard.furryup.link/"):
                    name = url.split("hoard.furryup.link/", 1)[1].split("#")[0].split("?")[0]
                    kind = {"html": "text/html", "js": "text/javascript", "css": "text/css"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
                    return route.fulfill(path=str(SITE / name), content_type=kind) if (SITE / name).is_file() else route.fulfill(status=404)
                return route.fulfill(body=PNG, content_type="image/png")
            page.route("**/*", serve)
            page.goto(sets.share_link(code))
            page.locator("#setView").wait_for()
            marked = page.locator("#setPhotos li.sv-marked")
            self.assertEqual(marked.count(), 1, "the photo with marks; the other as it was")
            marks = marked.locator(".sv-pmark")
            self.assertEqual([marks.nth(n).get_attribute("aria-label") for n in range(2)], ["1: Long Hair, on Booth", "2: Straw Hat, on Booth"])
            self.assertEqual(marks.nth(1).get_attribute("style"), "left:60%;top:20%")
            self.assertEqual(marks.nth(1).get_attribute("href"), "https://booth.pm/ja/items/6")
            self.assertEqual(marked.locator(".sv-pmarks .sv-text b").all_inner_texts(), ["Long Hair", "Straw Hat"])
            marks.nth(1).focus()
            self.assertTrue(marks.nth(1).locator(".sv-pcard").is_visible(), "focused: its product")
            self.assertEqual(page.locator("#setPhotos > ul > li:not(.sv-marked) img").count(), 1)
            browser.close()


if __name__ == "__main__":
    unittest.main()
