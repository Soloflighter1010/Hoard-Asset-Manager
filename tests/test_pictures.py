"""Issue #406: products' pictures on their tiles, never blank or flickering. A picture that didn't load (its store slow,
or saying no for a moment) is asked for again, its placeholder showing meanwhile; a picture that has loaded is put
back as it was when the grid is drawn again; and a picture an image host sends without saying it's one is known by its
first bytes, never an SVG."""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase
from hoard import config, library, server

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _pw:
        _pw.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


class Kinds(IsolatedTestCase):
    def test_a_picture_known_by_its_bytes(self):
        self.assertEqual(library.picture_type(PNG), "image/png")
        self.assertEqual(library.picture_type(b"\xff\xd8\xff\xe0rest"), "image/jpeg")
        self.assertEqual(library.picture_type(b"GIF89a..."), "image/gif")
        self.assertEqual(library.picture_type(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertEqual(library.picture_type(b"\x00\x00\x00\x1cftypavif"), "image/avif")
        for not_one in (b"<svg onload=alert(1)/>", b"<?xml version='1.0'?><svg/>", b"", b"<html>"):
            self.assertIsNone(library.picture_type(not_one), not_one)

    def test_one_sent_without_its_type_is_kept_and_an_svg_never(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = mock.Mock()
            lib.thumbnail_for.return_value = ("https://img.example/a", "https://booth.pm/")
            with mock.patch.object(library, "THUMB_DIR", Path(tmp)), \
                    mock.patch.object(library, "fetch_public", return_value=(PNG, "application/octet-stream")):
                self.assertEqual(library.fetch_thumbnail("booth:1", lib), (PNG, "image/png"))
            self.assertEqual([p.suffix for p in Path(tmp).iterdir()], [".png"])
            lib.thumbnail_for.return_value = ("https://img.example/b", "https://booth.pm/")
            with mock.patch.object(library, "THUMB_DIR", Path(tmp)), \
                    mock.patch.object(library, "fetch_public", return_value=(b"<svg onload=alert(1)/>", "application/octet-stream")):
                self.assertIsNone(library.fetch_thumbnail("booth:2", lib))
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_the_same_picture_asked_for_at_once_is_fetched_once(self):
        calls = []

        def slow(url, headers, max_bytes, hosts=None):
            calls.append(url)
            time.sleep(0.3)
            return PNG, "image/png"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(library, "THUMB_DIR", Path(tmp)), \
                mock.patch.object(library, "fetch_public", slow):
            got = []
            threads = [threading.Thread(target=lambda: got.append(library.fetch_picture("https://img.example/c", "https://booth.pm/")))
                       for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(calls, ["https://img.example/c"])
        self.assertEqual(got, [(PNG, "image/png")] * 5)
        self.assertEqual(library._FETCHING, {}, "nothing left behind")


class OnTheTiles(IsolatedTestCase):
    def setUp(self):
        if not BROWSER:
            self.skipTest("no Playwright browser here")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"), "setup_done": True,
                                                      "ui": {"toured": True}}, lan=False)
        with self.srv.lib.lock:   # (in memory only)
            self.srv.lib.data["items"] = [
                library.item("booth", "1", name="Rusk", creator="Kitsu", thumbnail="https://booth.pximg.net/rusk.png"),
                library.item("booth", "2", name="Mochi Hat", creator="Mochi", thumbnail="https://booth.pximg.net/hat.png")]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def test_a_picture_that_didnt_load_is_asked_for_again(self):
        asked = []

        def fetch(key, lib):
            asked.append(key)
            return None if asked.count(key) == 1 else (PNG, "image/png")   # (the store said no, the first time)
        with mock.patch.object(server, "fetch_thumbnail", fetch), sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(self.srv.entry_url())
            tile = page.locator('#grid .slot[data-key="booth:1"]')
            tile.locator(".ph").wait_for()   # its placeholder while it waits
            tile.locator("img").wait_for(timeout=10000)
            page.wait_for_function("() => document.querySelector('#grid .slot[data-key=\"booth:1\"] img').naturalWidth === 1")
            self.assertEqual(tile.locator(".ph").count(), 0, "the picture in its placeholder's place")
            browser.close()
        self.assertGreaterEqual(asked.count("booth:1"), 2)

    def test_a_picture_isnt_drawn_again_when_the_grid_is(self):
        with mock.patch.object(server, "fetch_thumbnail", lambda key, lib: (PNG, "image/png")), sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => [...document.querySelectorAll('#grid .slot img')].length === 2 && "
                                   "[...document.querySelectorAll('#grid .slot img')].every(i => i.complete && i.naturalWidth === 1)")
            self.assertEqual(page.locator("#grid .slot img.loading").count(), 0)
            page.evaluate("() => { window.pics = [...document.querySelectorAll('#grid .slot img')]; render(); }")
            self.assertTrue(page.evaluate("() => [...document.querySelectorAll('#grid .slot img')].every((i, n) => i === window.pics[n])"),
                            "the same pictures, already drawn, in the new tiles")
            self.assertEqual(page.locator("#grid .slot").count(), 2)
            browser.close()


class ForHoardForUnity(IsolatedTestCase):
    """Issue #407: Hoard for Unity shows PNG, JPEG and GIF pictures only. A store's WebP or AVIF picture gets a PNG (or
    JPEG) copy beside it, made by Hoard's page, which can read those; a store's picture is asked for in a kind Unity
    reads first, and one sent untyped is known by its bytes."""

    def setUp(self):
        from hoard import downloader
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.folder = self.tmp / "dl" / "Booth" / "Kitsu" / "Rusk"
        self.folder.mkdir(parents=True)
        (self.folder / "rusk.zip").write_bytes(b"zip")
        (self.folder / "_thumbnail.webp").write_bytes(PNG)   # (a PNG inside: Chromium reads a picture by its bytes)
        man = downloader.Manifest(self.tmp / "dl" / "Booth")
        rec = man.record("1", "Kitsu", "Rusk")
        rec.update(name="Rusk", creator="Kitsu", url="https://booth.pm/ja/items/1")
        rec["files"]["f1"] = {"path": "rusk.zip", "size": 3}
        man.save()
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"), "setup_done": True,
                                                      "ui": {"toured": True}}, lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def post(self, body):
        import http.client
        import json
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=20)
        conn.request("POST", "/api/unity-picture", json.dumps(body),
                     {"X-Hoard-Key": self.srv.key, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.srv.server_address[1]}"})
        r = conn.getresponse()
        data = json.loads(r.read() or b"{}")
        conn.close()
        return r.status, data

    def test_a_copy_beside_it_once_and_nowhere_else(self):
        import base64
        png = "data:image/png;base64," + base64.b64encode(PNG).decode()
        thumb = "Booth/Kitsu/Rusk/_thumbnail.webp"
        for wrong in ("Booth/Kitsu/Rusk/rusk.zip", "Booth/Kitsu/Rusk/../../../../etc/_thumbnail.webp", "../_thumbnail.webp",
                      "Booth/Kitsu/Other/_thumbnail.webp", ""):
            self.assertEqual(self.post({"thumb": wrong, "png": png})[0], 400, wrong)
        self.assertEqual(self.post({"thumb": thumb, "png": "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode()})[0], 400)
        self.assertEqual(self.post({"thumb": thumb, "png": png}), (200, {"ok": True, "made": True}))
        self.assertEqual((self.folder / "_thumbnail.png").read_bytes(), PNG)
        (self.folder / "_thumbnail.png").write_bytes(b"mine")
        self.assertEqual(self.post({"thumb": thumb, "png": png}), (200, {"ok": True, "made": False}), "never over one that's there")
        self.assertEqual((self.folder / "_thumbnail.png").read_bytes(), b"mine")

    def test_the_page_makes_it(self):
        if not BROWSER:
            self.skipTest("no Playwright browser here")
        made = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.on("request", lambda r: made.append(r.url) if r.url.endswith("/api/unity-picture") else None)
            page.goto(self.srv.entry_url())
            page.locator("nav.apptabs a[href='/downloads']").wait_for()
            page.click("nav.apptabs a[href='/downloads']")
            page.locator("#grid .slot[data-id]").first.wait_for()
            deadline = time.time() + 15
            while not (self.folder / "_thumbnail.png").exists() and time.time() < deadline:
                time.sleep(0.1)
            page.reload()   # (drawn again: it isn't made twice)
            page.locator("#grid .slot[data-id]").first.wait_for()
            time.sleep(1)
            browser.close()
        self.assertEqual(len(made), 1)
        self.assertTrue((self.folder / "_thumbnail.png").read_bytes().startswith(b"\x89PNG"))

    def test_a_stores_picture_asked_for_as_unity_reads_it(self):
        from hoard import downloader
        asked = []

        def fetch(url, headers, max_bytes, timeout=20, hosts=None):
            asked.append(headers.get("Accept", ""))
            return PNG, "application/octet-stream"
        folder = self.tmp / "new"
        folder.mkdir()
        with mock.patch.object(downloader, "fetch_public", fetch):
            downloader.save_thumbnail("https://booth.pximg.net/a", folder, "https://booth.pm/")
        self.assertTrue(asked[0].startswith("image/png,image/jpeg,image/gif"))
        self.assertEqual([p.name for p in folder.iterdir()], ["_thumbnail.png"])
