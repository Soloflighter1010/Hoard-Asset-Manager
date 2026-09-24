"""Tests for Hoard as one app: settings, downloading with progress and Stop, and moving over from 1.x.

Run from the repository root:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import cli, common, config, downloader, jobs, library, paths, server  # noqa: E402


class Settings(unittest.TestCase):
    """What the Settings panel may change, and how."""

    def test_valid_changes(self):
        cfg = config.load_config()
        folder = tempfile.mkdtemp()
        change = server.apply_settings(cfg, {"root": folder, "offline_images": False, "browser_channel": "msedge",
                                             "request_delay": 2, "stores": {"booth": {"enabled": False, "include_gifts": False}}})
        self.assertEqual(change["root"], folder)
        self.assertEqual(change["booth"], {"enabled": False, "include_gifts": False})
        self.assertEqual(server.apply_settings(cfg, {"root": ""})["root"], "")  # back to the default folder

    def test_refusals(self):
        cfg = config.load_config()
        for bad in ({"root": "relative/folder"}, {"root": __file__}, {"browser_channel": "firefox"},
                    {"request_delay": 0}, {"request_delay": "fast"}, {"stores": {"evilstore": {"enabled": True}}}):
            with self.assertRaises(ValueError, msg=bad):
                server.apply_settings(cfg, bad)
        # options that don't belong to a store are ignored rather than written
        self.assertEqual(server.apply_settings(cfg, {"stores": {"payhip": {"include_gifts": True, "enabled": True}}}),
                         {"payhip": {"enabled": True}})

    def test_default_downloads_folder(self):
        self.assertEqual(config.root_dir({"root": ""}), paths.default_downloads())
        self.assertTrue(str(paths.default_downloads()).endswith("Hoard"))

    def test_actions_only_from_this_computer_as_json(self):
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            c.request("POST", "/api/settings", body="root=C:/x", headers={"Content-Type": "application/x-www-form-urlencoded"})
            r = c.getresponse(); r.read(); c.close()
            self.assertEqual(r.status, 403)
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            c.request("GET", "/api/settings", headers={"Host": "evil.example"})
            r = c.getresponse(); r.read(); c.close()
            self.assertEqual(r.status, 403)
        finally:
            srv.shutdown()
            srv.server_close()


class Downloading(unittest.TestCase):
    """A download job reports progress, stops cleanly, and still rebuilds the catalog."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.cfg = {**config.load_config(), "root": str(self.root)}
        self.saved = downloader.sync_booth, downloader.reachable, downloader.build_catalog
        self.catalog_built = threading.Event()
        downloader.reachable = lambda store, timeout=5.0: True
        downloader.build_catalog = lambda cfg, root: self.catalog_built.set()

    def tearDown(self):
        downloader.sync_booth, downloader.reachable, downloader.build_catalog = self.saved

    def run_job(self, job, stop_after=None, timeout=20):
        done = threading.Event()
        job.on_download_done = done.set
        self.assertTrue(job.start("download", ["booth"]))
        if stop_after:
            time.sleep(stop_after)
            self.assertTrue(job.cancel())
        self.assertTrue(done.wait(timeout))
        for _ in range(50):   # the runner frees itself just after the callback
            if not job.state["running"]:
                break
            time.sleep(0.05)

    def test_progress_and_summary(self):
        def pretend(cfg, root, args, report):
            for i in range(3):
                common.log(f"Booth: file {i}")
            report.new_assets.append("Booth: Thing")
        downloader.sync_booth = pretend
        job = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.run_job(job)
        self.assertIn("Booth: file 2", job.state["log"])
        self.assertEqual(job.state["report"]["new_assets"], 1)
        self.assertTrue(self.catalog_built.is_set())

    def test_stop(self):
        def slow(cfg, root, args, report):
            for i in range(200):
                common.log(f"Booth: file {i}")
                time.sleep(0.05)
        downloader.sync_booth = slow
        job = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.run_job(job, stop_after=0.5)
        self.assertTrue(job.state["message"].startswith("Stopped"))
        self.assertLess(len(job.state["log"]), 60, "it stopped early")
        self.assertTrue(self.catalog_built.is_set(), "what did download is still catalogued")
        self.assertFalse(job.state["running"])
        self.assertFalse(job.cancel(), "nothing left to stop")

    def test_one_job_at_a_time(self):
        started = threading.Event()
        release = threading.Event()

        def waits(cfg, root, args, report):
            started.set()
            release.wait(10)
        downloader.sync_booth = waits
        job = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        done = threading.Event()
        job.on_download_done = done.set
        self.assertTrue(job.start("download", ["booth"]))
        started.wait(5)
        self.assertFalse(job.start("refresh", ["booth"]), "a second job must wait")
        release.set()
        done.wait(10)


class ComingFrom1x(unittest.TestCase):
    """`migrate` brings over a 1.x library list and downloads folder, without overwriting anything."""

    def test_migrate(self):
        old = Path(tempfile.mkdtemp())
        (old / "Hoard").mkdir()
        (old / "HoardDownloader" / "downloads").mkdir(parents=True)
        (old / "HoardDownloader" / "asset_dl.py").write_text("# 1.x")
        (old / "HoardDownloader" / "config.json").write_text(json.dumps({"root": "downloads", "booth": {"enabled": False}}))
        (old / "Hoard" / "library.json").write_text(json.dumps({"items": [
            {"store": "booth", "id": "1", "name": "Rusk", "url": "https://booth.pm/ja/items/1"}], "stores": {}}))
        library_file = Path(tempfile.mkdtemp()) / "library.json"
        config_file = Path(tempfile.mkdtemp()) / "config.json"
        cfg = config.load_config(config_file)
        saved = cli.LIBRARY_FILE
        cli.LIBRARY_FILE = library_file
        try:
            cli.cmd_migrate(cfg, old / "Hoard", config_file)
        finally:
            cli.LIBRARY_FILE = saved
        self.assertEqual([i["name"] for i in library.Library(library_file).data["items"]], ["Rusk"])
        moved = config.load_config(config_file)
        self.assertEqual(Path(moved["root"]), (old / "HoardDownloader" / "downloads").resolve())
        self.assertFalse(moved["booth"]["enabled"])


class CommandLine(unittest.TestCase):
    """Every command still exists."""

    def test_commands(self):
        import contextlib
        import io
        for cmd in ("login", "logout", "refresh", "import", "sync", "tags", "verify", "migrate", "debug", "probe"):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                cli.main([cmd, "--help"])
            self.assertIn("usage", out.getvalue().lower(), cmd)


if __name__ == "__main__":
    unittest.main()
