"""A store browser that closes by itself, or stops answering, part way through a sync. In 2.9.1 one that closed
failed every product after it (258 of them, each in a second), and one that stopped answering held the job, and
every job after it, for ever: Stop couldn't reach it."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import browser, common, config, downloader, jobs, library  # noqa: E402

downloader.RETRY_WAITS = (0.0, 0.0, 0.0)

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _p.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

IDS = ["111", "222", "333"]


OPENED: list = []


def _jinxxy(route):
    """A stand-in for jinxxy.com: an inventory of three items, each with one file to download."""
    u = route.request.url
    OPENED.append(u)
    for i in IDS:
        if u.endswith(f"/my/inventory/{i}"):
            return route.fulfill(status=200, content_type="text/html", body=(
                f'<html><head><title>Item {i} | Jinxxy</title></head><body><main><h1>Item {i}</h1>'
                f'<a href="https://jinxxy.com/Kitsu">Kitsu</a><div><span>file{i}.unitypackage</span>'
                f'<a href="https://jinxxy.com/dl/{i}">Download</a></div></main></body></html>'))
        if u.endswith(f"/dl/{i}"):
            return route.fulfill(status=200, body=b"x" * 50_000, headers={
                "Content-Type": "application/octet-stream", "Content-Disposition": f"attachment; filename=file{i}.unitypackage"})
    if u.rstrip("/").endswith("/my/inventory"):
        return route.fulfill(status=200, content_type="text/html", body="<html><body><main>" + "".join(
            f'<a href="https://jinxxy.com/my/inventory/{i}">Item {i}</a>' for i in IDS) + "</main></body></html>")
    return route.fulfill(status=404, body="")


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class ABrowserThatCloses(unittest.TestCase):
    """Jinxxy's tab, or its whole browser, closing by itself: the product it was on is tried again in a new one,
    and the rest carry on."""

    def sync(self, trouble, targets=None):
        """Run sync_jinxxy against the stand-in site. trouble(ctx, page, url) is called as each item opens."""
        OPENED.clear()
        root = Path(tempfile.mkdtemp())
        cfg = {**config.load_config(), "root": str(root), "request_delay": 0}
        cfg["jinxxy"] = {**cfg["jinxxy"], "save_thumbnails": False}
        report = downloader.Report(retries=1)
        said, launched = [], []
        with sync_playwright() as p:
            def launch(*_a, **_k):
                ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), headless=True, accept_downloads=True)
                ctx.route("https://jinxxy.com/**", _jinxxy)
                launched.append(ctx)
                return ctx

            @contextlib.contextmanager
            def playwright():
                yield p
            real_item = downloader._jinxxy_item

            def item(ctx, page, url, *rest, **kw):
                trouble(ctx, page, url)
                return real_item(ctx, page, url, *rest, **kw)
            found = lambda page, rx, inv, got: [got.setdefault(f"https://jinxxy.com/my/inventory/{i}", None) for i in IDS] and []  # noqa: E731
            args = SimpleNamespace(dry_run=False, headed=False, only=None, keys=None, store="jinxxy", targets=targets or {})
            with mock.patch.object(downloader, "_playwright", lambda: playwright), \
                    mock.patch.object(downloader, "launch_context", launch), \
                    mock.patch.object(downloader, "settle", lambda page, ms=800: page.wait_for_timeout(50)), \
                    mock.patch.object(downloader, "_scan_inventory", found), \
                    mock.patch.object(downloader, "_jinxxy_item", item), \
                    common.capture_log(said.append):
                try:
                    downloader.sync_jinxxy(cfg, root, args, report)
                except RuntimeError as e:
                    report.gave_up = str(e)
            for ctx in launched:
                with contextlib.suppress(Exception):
                    ctx.close()
        return report, [str(x) for x in said if not isinstance(x, common.Progress)], len(launched)

    def test_a_tab_that_closes_is_opened_again(self):
        closed = []

        def trouble(ctx, page, url):
            if url.endswith("222") and not closed:
                closed.append(url)
                page.close()   # as if something closed Hoard's tab
        report, said, launched = self.sync(trouble)
        self.assertEqual(report.failed, [])
        self.assertEqual(len(report.new_files), 3, "every product downloaded, the one it closed on included")
        self.assertEqual(launched, 1, "the same browser, a new tab")
        self.assertTrue(any("tab closed by itself" in line for line in said), said)

    def test_a_browser_that_closes_is_started_again(self):
        closed = []

        def trouble(ctx, page, url):
            if url.endswith("111") and not closed:
                closed.append(url)
                ctx.close()   # as if the browser had ended
        report, said, launched = self.sync(trouble)
        self.assertEqual(report.failed, [])
        self.assertEqual(len(report.new_files), 3)
        self.assertEqual(launched, 2, "started again, once")
        self.assertTrue(any("browser closed by itself" in line for line in said), said)

    def test_one_that_keeps_closing_is_left_for_next_time(self):
        """Not one failure per product: after a few tries, one explanation."""
        report, said, launched = self.sync(lambda ctx, page, url: page.close())
        self.assertIn("closed by itself", getattr(report, "gave_up", ""))
        self.assertLessEqual(len(report.failed), 2)
        self.assertLessEqual(launched, downloader.REOPENS + 1)


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class StraightToTheItem(ABrowserThatCloses):
    """Downloading one product (or a few) opens just those: in 2.9.1 it opened every item in the inventory, one
    page after another, and only kept the one whose name matched."""

    def test_only_the_chosen_items_page_is_opened(self):
        chosen = {"jinxxy": [{"key": "jinxxy:222", "store": "jinxxy", "name": "Item 222", "creator": "Kitsu",
                              "url": "https://jinxxy.com/my/inventory/222"}]}
        report, said, _ = self.sync(lambda ctx, page, url: None, targets=chosen)
        self.assertEqual(report.new_files, ["Jinxxy: Kitsu / Item 222 / file222.unitypackage"])
        pages = [u for u in OPENED if "/my/inventory" in u]
        self.assertEqual(pages, ["https://jinxxy.com/my/inventory/222"], "not the inventory, nor any other item")
        self.assertIn("Jinxxy: 1 chosen item", said)

    # (the tests of a browser that closes aren't run again here)
    test_a_tab_that_closes_is_opened_again = test_a_browser_that_closes_is_started_again = None
    test_one_that_keeps_closing_is_left_for_next_time = None


class ChoosingProducts(unittest.TestCase):
    """Which products a download of chosen ones can go straight to, from the library."""
    LIB = [
        {"key": "jinxxy:1", "store": "jinxxy", "name": "Tail Ball", "creator": "Fr Boi", "url": "https://jinxxy.com/my/inventory/1"},
        {"key": "jinxxy:2", "store": "jinxxy", "name": "Emission Masks", "creator": "Fr Boi", "url": "https://jinxxy.com/my/inventory/2"},
        {"key": "gumroad:9", "store": "gumroad", "name": "Cat Eye Texture", "creator": "Pine Link",
         "url": "https://app.gumroad.com/d/abc", "download_url": "https://app.gumroad.com/d/abc", "id": "9"},
        {"key": "booth:5", "store": "booth", "name": "Rusk", "creator": "Kitsu", "url": "https://booth.pm/items/5"},
    ]

    def targets(self, stores, only=None, keys=None, items=None):
        return downloader.direct_targets(self.LIB, stores, only, keys, items)

    def test_by_library_item(self):
        got = self.targets(["jinxxy"], items=["jinxxy:2"])
        self.assertEqual([i["key"] for i in got["jinxxy"]], ["jinxxy:2"])

    def test_by_tag_key_from_downloads(self):
        from hoard.tags import tag_key
        got = self.targets(["jinxxy", "gumroad"], keys=[tag_key("jinxxy", "Tail Ball"), tag_key("gumroad", "Cat Eye Texture")])
        self.assertEqual([i["key"] for i in got["jinxxy"]], ["jinxxy:1"])
        self.assertEqual([i["key"] for i in got["gumroad"]], ["gumroad:9"])

    def test_by_name(self):
        self.assertEqual([i["key"] for i in self.targets(["jinxxy"], only="emission")["jinxxy"]], ["jinxxy:2"])

    def test_read_in_full_when_it_can_not_go_straight_there(self):
        from hoard.tags import tag_key
        self.assertEqual(self.targets(["jinxxy"]), {}, "nothing chosen: a whole sync")
        self.assertEqual(self.targets(["booth"], items=["booth:5"]), {}, "Booth's files are only on its library pages")
        self.assertEqual(self.targets(["jinxxy"], keys=[tag_key("jinxxy", "Tail Ball"), tag_key("jinxxy", "Not In The Library")]), {},
                         "a chosen product the library doesn't have")
        no_link = [dict(self.LIB[0], url="https://example.com/x")]
        self.assertEqual(downloader.direct_targets(no_link, ["jinxxy"], None, None, ["jinxxy:1"]), {}, "only the store's own pages")

    def test_gumroad_opens_only_the_chosen_download_page(self):
        opened = []

        class Store:
            def library(self):
                raise AssertionError("the whole library was read")

            def page(self, url, params=None):
                opened.append(url)
                return {"props": {}}   # no files: noted as skipped, which is enough to see where it went
        report = downloader.Report()
        args = SimpleNamespace(dry_run=False, only=None, keys=None, targets=self.targets(["gumroad"], items=["gumroad:9"]))
        downloader._sync_gumroad_purchases(config.load_config(), Store(), Path(tempfile.mkdtemp()),
                                           downloader.Manifest(Path(tempfile.mkdtemp())), args, report)
        self.assertEqual(opened, ["https://app.gumroad.com/d/abc"])
        self.assertIn("Cat Eye Texture", report.skipped[0])

    def test_the_library_page_names_the_item(self):
        """The server passes the chosen library item on to the job."""
        from hoard import server
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": tempfile.mkdtemp()}, lan=False)
        self.addCleanup(srv.server_close)
        seen = {}
        with mock.patch.object(srv.jobs, "start", lambda task, stores, **kw: seen.update(task=task, **kw) or "started"):
            threading.Thread(target=srv.handle_request, daemon=True).start()
            import json
            import urllib.request
            from hoard.safety import ACCESS_HEADER
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/api/download", method="POST",
                                         data=json.dumps({"stores": ["jinxxy"], "only": "Tail Ball", "item": "jinxxy:1"}).encode(),
                                         headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key,
                                                  "Origin": f"http://127.0.0.1:{srv.server_port}"})
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertIn(r.status, (200, 202))
        self.assertEqual((seen["task"], seen["items"]), ("download", ["jinxxy:1"]))


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class ABrowserThatStopsAnswering(unittest.TestCase):

    def test_ending_the_browser_frees_what_waits_on_it(self):
        """A script that never finishes stands in for a browser that stopped answering: the call waiting on it has
        no time limit. Ending the browser makes it fail at once, and closing it afterwards doesn't wait either."""
        got, done = {}, threading.Event()

        def job():
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), headless=True)
                browser._track(ctx)
                got["ctx"] = ctx
                began = time.monotonic()
                try:
                    ctx.pages[0].evaluate("new Promise(() => {})")
                except Exception as e:
                    got["error"], got["after"] = str(e), time.monotonic() - began
                ctx.close()
            done.set()
        threading.Thread(target=job, daemon=True).start()
        for _ in range(200):
            if "ctx" in got:
                break
            time.sleep(0.05)
        time.sleep(1)
        self.assertEqual(browser.end_browsers(), 1)
        self.assertTrue(done.wait(20), "the job finished")
        self.assertIn("closed", got.get("error", ""))
        self.assertLess(got["after"], 15)
        self.assertEqual(browser.end_browsers(), 0, "nothing left to end")

    def test_a_driver_that_has_ended_is_left_alone(self):
        """Its process number may belong to another program by now: that's never ended in its place."""
        proc = SimpleNamespace(pid=4321, returncode=0)
        ctx = SimpleNamespace(_impl_obj=SimpleNamespace(_connection=SimpleNamespace(_transport=SimpleNamespace(_proc=proc))))
        self.assertIsNone(browser._driver_pid(ctx))
        proc.returncode = None
        self.assertEqual(browser._driver_pid(ctx), 4321)


class StuckJobs(unittest.TestCase):
    """What Stop does when a job doesn't stop, and what a job that goes quiet leaves in hoard.log."""

    def setUp(self):
        self.job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.job.history = []
        where = Path(tempfile.mkdtemp()) / "tasks.json"
        patch = mock.patch.object(jobs, "tasks_file", lambda: where)
        patch.start()
        self.addCleanup(patch.stop)

    def run_until(self, event, timeout=10):
        for _ in range(int(timeout / 0.05)):
            if event():
                return True
            time.sleep(0.05)
        return False

    def test_stop_ends_a_browser_that_stopped_answering(self):
        freed = threading.Event()

        def waits_on_a_frozen_browser(stores, only, keys=None, check=False, **_kw):
            self.job._set(task="download", message="downloading Big.zip")
            freed.wait(30)   # what a call waiting on a browser that stopped answering does
            raise RuntimeError("Page.evaluate: Connection closed while reading from the driver")
        ended = []
        out = io.StringIO()
        with mock.patch.object(self.job, "_download", waits_on_a_frozen_browser), \
                mock.patch.object(jobs, "FORCE_AFTER", 0.5), \
                mock.patch.object(jobs, "end_browsers", lambda: ended.append(1) or freed.set() or 1), \
                contextlib.redirect_stdout(out):
            self.job.start("download", ["jinxxy"])
            self.assertTrue(self.run_until(lambda: self.job.state["message"] == "downloading Big.zip"))
            self.assertTrue(self.job.cancel())
            self.assertTrue(self.run_until(lambda: not self.job.state["running"]), "the job finished")
        self.assertEqual(ended, [1], "the store's browser was ended")
        self.assertIn("Stop hadn't taken effect", out.getvalue())
        self.assertIn("waits_on_a_frozen_browser", out.getvalue(), "hoard.log says where it was waiting")

    def test_a_job_that_stops_in_time_is_left_alone(self):
        def stops(stores, only, keys=None, check=False, **_kw):
            self.job._set(task="download")
            for _ in range(200):
                if self.job.stop.is_set():
                    return
                time.sleep(0.02)
        ended = []
        with mock.patch.object(self.job, "_download", stops), mock.patch.object(jobs, "FORCE_AFTER", 1.0), \
                mock.patch.object(jobs, "end_browsers", lambda: ended.append(1)):
            self.job.start("download", ["booth"])
            self.assertTrue(self.run_until(lambda: self.job.state["task"] == "download"))
            self.assertTrue(self.job.cancel())
            self.assertTrue(self.run_until(lambda: not self.job.state["running"]))
            time.sleep(1.5)
        self.assertEqual(ended, [], "nothing ended when Stop worked by itself")

    def test_a_quiet_job_says_where_it_is(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def quiet(stores, only, keys=None, check=False, **_kw):
            self.job._set(task="download", message="opening Item 222")
            release.wait(20)
        out = io.StringIO()
        real_watch = self.job._watch
        with mock.patch.object(self.job, "_download", quiet), mock.patch.object(jobs, "STUCK_AFTER", 0.5), \
                mock.patch.object(self.job, "_watch", lambda job_id: real_watch(job_id, every=0.1)), \
                contextlib.redirect_stdout(out):
            self.job.start("download", ["jinxxy"])
            self.assertTrue(self.run_until(lambda: "No progress" in out.getvalue()))
            self.assertIn("No progress", self.job.state["message"])
            self.assertIn("opening Item 222", self.job.state["message"], "and what it last said")
            release.set()
            self.assertTrue(self.run_until(lambda: not self.job.state["running"]))
        self.assertIn("in quiet", out.getvalue(), "the stack names where it waited")
        self.assertEqual(out.getvalue().count("No progress"), 1, "said once")


if __name__ == "__main__":
    unittest.main()
