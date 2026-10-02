"""Downloads that stop coming in: the store stops sending a file part way through, without hanging up. Before, a
browser download that did this held up its job for ever (and every job queued after it), and Stop couldn't reach it."""
from __future__ import annotations

import http.server
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import common, config, downloader, egress, jobs, library, safety  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _p.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

SIZE = 400_000
STALLS_AT = 300_000   # more than one piece of the file (egress reads it 256 KiB at a time)


class _Store(http.server.BaseHTTPRequestHandler):
    """/stall sends a little of the file, then nothing (until the test ends); /slow sends it in pieces, a moment
    apart; /good sends it all at once. A Range request gets the rest, for resuming."""
    release = threading.Event()

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            body = b"<!doctype html><title>store</title><p>files</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/files":   # a product page as Jinxxy's are now: each file a plain link
            body = b'<!doctype html><title>item</title><div><span>file.bin</span><a href="/late">Download</a></div>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/late":   # a file the store takes a while to start sending
            self.release.wait(8)
        start = int(self.headers.get("Range", "bytes=0-")[6:].rstrip("-") or 0)
        self.send_response(206 if start else 200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", "attachment; filename=file.bin")
        self.send_header("Content-Length", str(SIZE - start))
        if start:
            self.send_header("Content-Range", f"bytes {start}-{SIZE - 1}/{SIZE}")
        self.end_headers()
        try:
            if self.path == "/stall" and not start:
                self.wfile.write(b"x" * STALLS_AT)
                self.wfile.flush()
                self.release.wait(30)
            elif self.path == "/slow":
                for i in range(start, SIZE, SIZE // 8):
                    self.wfile.write(b"x" * min(SIZE // 8, SIZE - i))
                    self.wfile.flush()
                    time.sleep(0.3)
            else:
                self.wfile.write(b"x" * (SIZE - start))
        except OSError:
            pass


def _serve():
    _Store.release = threading.Event()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Store)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


class DirectDownloads(unittest.TestCase):
    """Gumroad, itch.io and Booth's direct route: a store that stops sending is given up on (the part that came is
    kept, and resumed); progress is reported as the file comes in, and Stop is noticed part way through a file."""

    def setUp(self):
        self.srv, self.origin = _serve()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.addCleanup(_Store.release.set)
        egress._TEST_ORIGINS.clear()
        egress._TEST_ORIGINS.add(self.origin)
        self.addCleanup(egress._TEST_ORIGINS.clear)
        self.dest = Path(tempfile.mkdtemp()) / "file.bin"

    def get(self, path, **kw):
        return egress.download(egress.session(), f"{self.origin}{path}", self.dest, ["127.0.0.1"], **kw)

    def test_a_stalled_download_is_given_up_on_and_resumed(self):
        began = time.monotonic()
        with mock.patch.object(egress, "STALL_SECONDS", 1), self.assertRaises(Exception):
            self.get("/stall")
        self.assertLess(time.monotonic() - began, 10, "not waited on for ever")
        self.assertFalse(self.dest.exists())
        self.assertGreaterEqual(self.dest.with_name("file.bin.part").stat().st_size, 256 * 1024, "what came is kept")
        self.assertEqual(self.get("/stall"), SIZE, "and the rest is fetched next time")

    def test_progress_and_stop_part_way(self):
        seen = []
        with mock.patch.object(egress, "PROGRESS_EVERY", 0):
            self.assertEqual(self.get("/slow", progress=lambda got, whole: seen.append((got, whole))), SIZE)
        self.assertTrue(seen and seen[-1][1] == SIZE and seen[0][0] < SIZE, seen)

        self.dest.unlink()

        def stop(got, whole):
            raise common.Cancelled()
        with mock.patch.object(egress, "PROGRESS_EVERY", 0), self.assertRaises(common.Cancelled):
            self.get("/slow", progress=stop)
        self.assertFalse(self.dest.exists())
        self.assertLess(self.dest.with_name("file.bin.part").stat().st_size, SIZE, "stopped part way")

    def test_the_app_shows_progress(self):
        said = []
        with common.capture_log(said.append):
            downloader.downloading("Rusk.unitypackage")(3 * 1024 * 1024, 10 * 1024 * 1024)
        self.assertEqual(said, ["    downloading Rusk.unitypackage: 3.0 MB of 10.0 MB (30%)"])
        self.assertIsInstance(said[0], common.Progress)
        self.assertEqual(said[0].transfer, {"file": "Rusk.unitypackage", "got": 3 * 1024 * 1024,
                                            "total": 10 * 1024 * 1024, "speed": None, "eta": None})

    def test_speed_and_time_left(self):
        now = [100.0]
        said = []
        report = downloader.Transfer("Big.zip", clock=lambda: now[0])
        mb = 1024 * 1024
        with common.capture_log(said.append):
            report(0, 100 * mb)
            now[0] += 1
            report(4 * mb, 100 * mb)    # 4 MB/s
            now[0] += 1
            report(6 * mb, 100 * mb)    # 2 MB/s just now: smoothed, not jumping straight there
        self.assertEqual(said[1].transfer["speed"], 4 * mb)
        self.assertEqual(said[1].transfer["eta"], 24)
        self.assertEqual(said[2].transfer["speed"], round(0.3 * 2 * mb + 0.7 * 4 * mb))
        self.assertEqual(str(said[2]), "    downloading Big.zip: 6.0 MB of 100.0 MB (6%), 3.4 MB/s, 28 s left")
        self.assertEqual(downloader.duration(4000), "1 h 7 min")


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class BrowserDownloads(unittest.TestCase):
    """Jinxxy, and Booth when it turns away direct downloads: the file comes through the browser, where saving it
    used to wait with no time limit."""

    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.ctx = cls.pw.chromium.launch_persistent_context(tempfile.mkdtemp(), headless=True, accept_downloads=True)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.close()
        cls.pw.stop()

    def setUp(self):
        self.srv, self.origin = _serve()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.addCleanup(_Store.release.set)
        self.page = self.ctx.new_page()
        self.addCleanup(self.page.close)
        self.page.goto(self.origin + "/")
        self.folder = Path(tempfile.mkdtemp())

    def fetch(self, path, stall=1.0):
        with mock.patch.object(egress, "STALL_SECONDS", stall):
            return downloader.booth_browser_download(self.page, self.origin + path, self.folder, "file.bin", "1", 20)

    def test_a_finished_download_is_saved(self):
        self.assertEqual(self.fetch("/good"), ("file.bin", SIZE))
        self.assertEqual((self.folder / "file.bin").stat().st_size, SIZE)

    def test_a_slow_download_that_keeps_coming_is_waited_for(self):
        self.assertEqual(self.fetch("/slow", stall=1.5), ("file.bin", SIZE))

    def test_a_stalled_download_is_cancelled(self):
        began = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "stalled"):
            self.fetch("/stall")
        self.assertLess(time.monotonic() - began, 15, "not waited on for ever")
        self.assertEqual([p.name for p in self.folder.iterdir()], [], "nothing half-saved left behind")

    def test_stop_cancels_a_browser_download(self):
        def sink(msg):
            if isinstance(msg, common.Progress):
                raise common.Cancelled()
        began = time.monotonic()
        with common.capture_log(sink), mock.patch.object(egress, "PROGRESS_EVERY", 0.5), \
                self.assertRaises(common.Cancelled):
            self.fetch("/stall", stall=60)
        self.assertLess(time.monotonic() - began, 15, "stopped at once, not after the stall")

    def test_a_download_that_fails_is_reported(self):
        """The store hangs up part way: the browser gives up on the file, and saving it says so."""
        started = []
        self.page.on("download", lambda d: started.append(d))
        self.page.evaluate(downloader.BOOTH_CLICK_JS, self.origin + "/stall")
        for _ in range(100):
            if started:
                break
            self.page.wait_for_timeout(100)
        dl = started[0]
        self.page.wait_for_timeout(500)
        dl.cancel()   # as if the connection dropped
        downloader.wait_for_browser_download(dl, "file.bin", stall_s=30)   # ends at once, not after the stall
        with self.assertRaisesRegex(Exception, "cancel"):
            safety.save_browser_download(dl, self.folder, "file.bin")

    def test_stop_reaches_a_file_link_that_is_slow_to_start(self):
        """Clicking a file's link used to wait for the page to finish navigating, which a link that turns into a
        download may never do (Jinxxy's, since its new item pages): the job sat there, and Stop couldn't reach it.
        Now the click returns at once, and the wait for the download says how long it's been, which Stop hears."""
        self.page.goto(self.origin + "/files")
        [button] = self.page.evaluate(downloader.DOWNLOAD_BUTTONS_JS, {"allowAll": False, "hosts": ["127\\.0\\.0\\.1"]})

        def sink(msg):
            if "waiting for the download to start" in msg:
                raise common.Cancelled()
        began = time.monotonic()
        with common.capture_log(sink), self.assertRaises(common.Cancelled):
            downloader.click_download(self.ctx, self.page, button["idx"], 20)
        self.assertLess(time.monotonic() - began, 7.5, "Stop was heard before the store answered")


class StoppingAJob(unittest.TestCase):
    """Progress while a file downloads is shown, but not kept (in the job's log or the Tasks tab); and Stop is
    noticed on it, so a job can be stopped part way through a file."""

    def test_progress_is_shown_and_stop_is_noticed(self):
        cfg = {**config.load_config(), "root": tempfile.mkdtemp()}
        job = jobs.Jobs(cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        job.history = []
        where = Path(tempfile.mkdtemp()) / "tasks.json"
        ticking = threading.Event()

        def one_long_file(cfg, root, args, report):
            common.log("    downloading: Big.zip")
            for i in range(400):
                common.tick(f"    downloading Big.zip: {i} MB")
                ticking.set()
                time.sleep(0.05)
        done = threading.Event()
        job.on_download_done = done.set
        with mock.patch.object(downloader, "sync_booth", one_long_file), \
                mock.patch.object(downloader, "reachable", lambda store, timeout=5.0: True), \
                mock.patch.object(downloader, "build_catalog", lambda cfg, root: None), \
                mock.patch.object(jobs, "tasks_file", lambda: where):
            self.assertEqual(job.start("download", ["booth"]), "started")
            self.assertTrue(ticking.wait(10))
            time.sleep(0.2)
            self.assertRegex(job.state["message"], r"downloading Big\.zip: \d+ MB")
            self.assertTrue(job.cancel())
            self.assertTrue(done.wait(10), "stopped part way through the file")
            for _ in range(100):
                if not job.state["running"]:
                    break
                time.sleep(0.05)
        self.assertFalse(job.state["running"])
        self.assertTrue(job.state["message"].startswith("Stopped"))
        kept = job.history[-1]["log"] + job.state["log"]
        self.assertIn("    downloading: Big.zip", kept)
        self.assertFalse([line for line in kept if "MB" in line], "progress isn't kept")
        self.assertIsNone(job.state["transfer"], "and the bar goes when the job does")

    def test_the_numbers_come_and_go_with_the_file(self):
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        seen = []

        def one_file(cfg, root, args, report):
            common.log("    downloading: Secret Thing.zip")
            downloader.Transfer("Secret Thing.zip")(1000, 4000)
            seen.append(dict(job.state["transfer"]))
            seen.append(job.tasks()["current"]["transfer"])
            common.log("    saved: Secret Thing.zip")
            seen.append(job.state["transfer"])
        done = threading.Event()
        job.on_download_done = done.set
        with mock.patch.object(downloader, "sync_booth", one_file), \
                mock.patch.object(downloader, "reachable", lambda store, timeout=5.0: True), \
                mock.patch.object(downloader, "build_catalog", lambda cfg, root: None), \
                mock.patch.object(jobs, "tasks_file", lambda: Path(tempfile.mkdtemp()) / "tasks.json"):
            job.start("download", ["booth"])
            self.assertTrue(done.wait(10))
        self.assertEqual(seen[0], {"file": "Secret Thing.zip", "got": 1000, "total": 4000, "speed": None, "eta": None})
        self.assertEqual(seen[1], seen[0], "Tasks has it too")
        self.assertIsNone(seen[2], "gone once the file is done")
        from hoard import server
        masked = server.public_job({"transfer": seen[0]}, ["Secret Thing"])
        self.assertEqual(masked["transfer"]["file"], "a hidden item.zip", "a hidden product's name stays hidden")


if __name__ == "__main__":
    unittest.main()
