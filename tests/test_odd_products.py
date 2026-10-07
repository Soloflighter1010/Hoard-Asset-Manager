"""Products whose files aren't where Hoard usually finds them: a Gumroad product that is only pictures in its
download page (no files listed), and Booth's free items, which the library lists without any files (they're on the
item's own page)."""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import common, config, downloader  # noqa: E402

downloader.RETRY_WAITS = (0.0, 0.0, 0.0)

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _p.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40


def rich(*nodes):
    """Gumroad's download page content, as its page data has it (September 2026): no files, a page of rich text."""
    return {"content_items": [], "rich_content_pages": [{"id": "p1", "description": {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "PNG's:"}]}, *nodes]}}]}


def image(src):
    return {"type": "image", "attrs": {"src": src, "link": None}}


class GumroadPictures(unittest.TestCase):

    def test_the_pictures_are_found(self):
        content = rich(image("https://public-files.gumroad.com/aaa"), {"type": "paragraph"},
                       image("https://public-files.gumroad.com/bbb"), image("https://public-files.gumroad.com/aaa"),
                       image("https://example.com/tracker.png"), image("http://public-files.gumroad.com/ccc"))
        self.assertEqual(downloader.gumroad_page_images(content),
                         ["https://public-files.gumroad.com/aaa", "https://public-files.gumroad.com/bbb"],
                         "in page order, once each, and only Gumroad's own, over https")

    def save(self, content, bodies, rec=None, dry_run=False, folder=None):
        folder = folder or Path(tempfile.mkdtemp())
        rec = rec if rec is not None else {"files": {}}
        report = downloader.Report()

        def download(sess, url, dest, sites, desc="", progress=None):
            self.assertEqual(list(sess.cookies), [], "public pictures: no sign-in sent")
            self.assertEqual(sites, ["public-files.gumroad.com"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(bodies[url])
            return len(bodies[url])
        with mock.patch.object(downloader.egress, "download", download):
            got = downloader._gumroad_page_images(SimpleNamespace(sess=None), content, rec, folder, "Cookie NovaBeast",
                                                  "iamu", mock.Mock(), SimpleNamespace(dry_run=dry_run), report)
        return got, folder, rec, report

    def test_a_product_that_is_only_pictures_is_downloaded(self):
        a, b = "https://public-files.gumroad.com/5o5ov7r6mw22", "https://public-files.gumroad.com/tge0p6li7z1a"
        got, folder, rec, report = self.save(rich(image(a), image(b)), {a: PNG, b: JPEG})
        self.assertTrue(got)
        saved = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
        self.assertEqual(saved, ["Page images/01 5o5ov7r6mw22.png", "Page images/02 tge0p6li7z1a.jpg"],
                         "named by their place on the page, typed by what they are")
        self.assertEqual(len(report.new_files), 2)
        # the next sync: already there, nothing downloaded again
        got, _folder, rec, report = self.save(rich(image(a), image(b)), {}, rec=rec, folder=folder)
        self.assertEqual(report.new_files, [])

    def test_something_that_is_not_a_picture_is_not_kept(self):
        a = "https://public-files.gumroad.com/zzz"
        got, folder, rec, report = self.save(rich(image(a)), {a: b"<html>not a picture</html>"})
        self.assertFalse(got)
        self.assertEqual([p for p in folder.rglob("*") if p.is_file()], [])
        self.assertIn("not a picture", report.skipped[0])

    def test_checking_for_updates_lists_them(self):
        a = "https://public-files.gumroad.com/aaa"
        with mock.patch.object(downloader, "would_get") as would:
            self.save(rich(image(a)), {}, dry_run=True)
        self.assertEqual(would.call_count, 1)

    def test_only_when_there_are_no_files(self):
        """Pictures beside real files are the creator's previews and instructions: not downloaded."""
        content = rich(image("https://public-files.gumroad.com/aaa"))
        content["content_items"] = [{"type": "file", "id": "f1", "file_name": "Hoodie", "extension": "unitypackage",
                                     "download_url": "/r/x/f1", "file_size": 3}]
        page = {"props": {"content": content, "purchase": {"product_id": "p"}, "token": "t"}}
        store = SimpleNamespace(sess=None, page=lambda url, params=None: page, file_url=lambda *a: "https://app.gumroad.com/f1")
        with mock.patch.object(downloader.egress, "download", lambda sess, url, dest, *a, **k: dest.parent.mkdir(parents=True, exist_ok=True) or dest.write_bytes(b"abc") or 3), \
                mock.patch.object(downloader, "_gumroad_page_images") as pictures:
            root = Path(tempfile.mkdtemp())
            downloader._sync_gumroad_purchases(config.load_config(), store, root / "Gumroad",
                                               downloader.StoreRecords(config.load_config(), root, "Gumroad"),
                                               SimpleNamespace(dry_run=False, only=None, keys=None, targets={"gumroad": [
                                                   {"name": "Hoodie", "creator": "Mochi", "id": "1",
                                                    "download_url": "https://app.gumroad.com/d/x"}]}),
                                               downloader.Report())
        pictures.assert_not_called()


FREE_ITEM = """<!doctype html><html><head><meta charset="utf-8"><title>Toothless Dance - BOOTH</title></head><body>
<main><h1>Toothless Dance Animation [Free Emote]</h1><p>Ver1.2 update: new loop.</p>
<div class="variation-item"><div class="variation-name">Toothless_Dance_v1.2.zip</div>
  <a class="btn primary" href="https://booth.pm/downloadables/5501">Free download</a></div>
<div class="variation-item"><div class="variation-name">Laggy Bear</div>
  <div class="js-download-button" data-href="https://booth.pm/downloadables/5502" data-label="Download"></div>
  <div class="js-download-button" data-href="https://booth.pm/downloadables/5502?browse=1" data-label="Open in Browser"></div>
  <a href="https://booth.pm/downloadables/5502/deeplink?client=booth-library-manager">Open in BOOTH Library</a></div>
<a href="https://example.com/downloadables/9999">Not Booth</a>
</main></body></html>"""


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class BoothFreeItems(unittest.TestCase):

    def test_the_item_page_lists_the_files(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=FREE_ITEM)
                       if "items/7666744" in r.request.url else r.abort())
            with mock.patch.object(downloader, "settle", lambda page, ms=800: None):
                files = downloader.booth_item_files(page, "https://booth.pm/en/items/7666744")
            browser.close()
        self.assertEqual(files, [{"name": "Toothless_Dance_v1.2.zip", "url": "https://booth.pm/downloadables/5501"},
                                 {"name": "", "url": "https://booth.pm/downloadables/5502"}],
                         "each file once: not the app's deeplink, not 'open in browser', not another site; no name "
                         "where the page shows none (the download's own name is used then)")


class BoothFreeItemsInASync(unittest.TestCase):
    """A free item (no files in the library) gets its files from its page, and downloads like any other."""

    def test_a_free_item_is_downloaded(self):
        root = Path(tempfile.mkdtemp())
        cfg = {**config.load_config(), "root": str(root), "request_delay": 0}
        cfg["booth"] = {**cfg["booth"], "save_thumbnails": False}
        free = {"id": "7666744", "name": "Deluxe Getaway Emote", "creator": "Dgabage Warehouse", "files": [],
                "url": "https://booth.pm/en/items/7666744", "thumbnail": "", "gift": False}
        opened = []

        def item_files(page, url):
            opened.append(url)
            return [{"name": "Getaway.zip", "url": "https://booth.pm/downloadables/5503"}]

        def fetch(page, sess, f, folder, fid, route, timeout_s, name_for=lambda n: n):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "Getaway.zip").write_bytes(b"zip")
            return "Getaway.zip", 3
        ctx = mock.MagicMock()
        ctx.pages = [mock.MagicMock()]
        report = downloader.Report()
        args = SimpleNamespace(dry_run=False, headed=False, only=None, keys=None, store="booth", targets={})
        with mock.patch.object(downloader, "_playwright", lambda: (lambda: contextlib.nullcontext(None))), \
                mock.patch.object(downloader, "launch_context", lambda *a, **k: ctx), \
                mock.patch.object(downloader, "booth_library", lambda page, cfg: [free]), \
                mock.patch.object(downloader, "session_from_context", lambda *a: mock.MagicMock()), \
                mock.patch.object(downloader, "booth_item_files", item_files), \
                mock.patch.object(downloader, "booth_fetch", fetch):
            downloader.sync_booth(cfg, root, args, report)
        self.assertEqual(opened, ["https://booth.pm/en/items/7666744"])
        self.assertEqual(report.new_files, ["Booth: Dgabage Warehouse / Deluxe Getaway Emote / Getaway.zip"])
        self.assertEqual(report.skipped, [])


class BoothNewFileInAProductYouHave(unittest.TestCase):
    """A file new to a Booth product you already have is a new file, not an update; one replacing a file is one."""

    def test_new_and_updated(self):
        root = Path(tempfile.mkdtemp())
        cfg = {**config.load_config(), "root": str(root), "request_delay": 0}
        cfg["booth"] = {**cfg["booth"], "save_thumbnails": False}
        item = {"id": "77", "name": "Rusk", "creator": "Mochi", "url": "https://booth.pm/en/items/77", "thumbnail": "",
                "gift": False, "files": [{"name": "Rusk.zip", "url": "https://booth.pm/downloadables/1"},
                                         {"name": "Rusk Quest.zip", "url": "https://booth.pm/downloadables/2"}]}

        def fetch(page, sess, f, folder, fid, route, timeout_s, name_for=lambda n: n):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f["name"]).write_bytes(b"zip")
            return f["name"], 3
        ctx = mock.MagicMock()
        ctx.pages = [mock.MagicMock()]

        def run():
            report = downloader.Report()
            args = SimpleNamespace(dry_run=False, headed=False, only=None, keys=None, store="booth", targets={})
            with mock.patch.object(downloader, "_playwright", lambda: (lambda: contextlib.nullcontext(None))), \
                    mock.patch.object(downloader, "launch_context", lambda *a, **k: ctx), \
                    mock.patch.object(downloader, "booth_library", lambda page, cfg: [item]), \
                    mock.patch.object(downloader, "session_from_context", lambda *a: mock.MagicMock()), \
                    mock.patch.object(downloader, "booth_fetch", fetch):
                downloader.sync_booth(cfg, root, args, report)
            return report
        first = dict(item, files=item["files"][:1])
        item, keep = first, item
        self.assertEqual(len(run().new_files), 1)
        item = keep   # the creator added a Quest file
        report = run()
        self.assertEqual(report.updated, [], "a file new to the product isn't an update")
        self.assertEqual(report.new_files, ["Booth: Mochi / Rusk / Rusk Quest.zip"])


class BoothDirectRoute(unittest.TestCase):
    """Booth's direct downloads: a dropped connection is tried again the same way (it resumes); Booth turning one
    away sends that file through the browser, and twice running, the rest of the run."""

    def fetch(self, route, fail):
        def location(sess, url):
            raise fail
        folder = Path(tempfile.mkdtemp())
        with mock.patch.object(downloader, "booth_file_location", location), \
                mock.patch.object(downloader, "booth_browser_download", lambda *a, **k: ("x.zip", 1)) as browser, \
                common.capture_log(lambda line: None):
            return downloader.booth_fetch(None, None, {"url": "https://booth.pm/downloadables/1", "name": "x"}, folder,
                                          "1", route, 1)

    def test_a_dropped_connection_is_not_booth_turning_it_away(self):
        import requests
        route = {"direct": True}
        with self.assertRaises(requests.ConnectionError):
            self.fetch(route, requests.ConnectionError("reset"))
        self.assertTrue(route["direct"])

    def test_turned_away_twice_running(self):
        route = {"direct": True}
        self.assertEqual(self.fetch(route, RuntimeError("403")), ("x.zip", 1))
        self.assertTrue(route["direct"], "once: only that file goes through the browser")
        self.fetch(route, RuntimeError("403"))
        self.assertFalse(route["direct"])


class GumroadChosenPurchasePicture(unittest.TestCase):
    """A Gumroad purchase downloaded from the Library gets its picture, from the library's listing."""

    def test_picture(self):
        content = {"content_items": [{"type": "file", "id": "f1", "file_name": "Hoodie", "extension": "zip",
                                      "download_url": "/r/x/f1", "file_size": 3}]}
        page = {"props": {"content": content, "purchase": {"product_id": "p"}, "token": "t"}}
        store = SimpleNamespace(sess=None, page=lambda url, params=None: page, file_url=lambda *a: "https://app.gumroad.com/f1")
        saved = []
        with mock.patch.object(downloader.egress, "download", lambda sess, url, dest, *a, **k: dest.parent.mkdir(parents=True, exist_ok=True) or dest.write_bytes(b"abc") or 3), \
                mock.patch.object(downloader, "save_thumbnail", lambda url, folder, *a: saved.append(url)), \
                common.capture_log(lambda line: None):
            root = Path(tempfile.mkdtemp())
            downloader._sync_gumroad_purchases(config.load_config(), store, root / "Gumroad",
                                               downloader.StoreRecords(config.load_config(), root, "Gumroad"),
                                               SimpleNamespace(dry_run=False, only=None, keys=None, targets={"gumroad": [
                                                   {"name": "Hoodie", "creator": "Mochi", "id": "1",
                                                    "thumbnail": "https://public-files.gumroad.com/pic",
                                                    "download_url": "https://app.gumroad.com/d/x"}]}),
                                               downloader.Report())
        self.assertEqual(saved, ["https://public-files.gumroad.com/pic"])


if __name__ == "__main__":
    unittest.main()
