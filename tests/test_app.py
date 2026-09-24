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


class SigningOut(unittest.TestCase):
    """Signing out of a store forgets what that account owns, so the next account never sees it."""

    def test_clear_store(self):
        tmp = Path(tempfile.mkdtemp())
        lib = library.Library(tmp / "library.json")
        lib.data["items"] = [library.item("jinxxy", "a", name="Paw Suit", thumbnail="https://cdn.jinxxy.com/a.png"),
                             library.item("booth", "1", name="Rusk")]
        lib.data["stores"] = {"jinxxy": {"count": 1}, "booth": {"count": 1}}
        lib.save()
        import hashlib
        library.THUMB_DIR.mkdir(parents=True, exist_ok=True)
        cached = library.THUMB_DIR / (hashlib.sha1(b"https://cdn.jinxxy.com/a.png").hexdigest() + ".png")
        cached.write_bytes(b"png")
        self.assertEqual(lib.clear_store("jinxxy", "Signed out."), 1)
        self.assertEqual([i["store"] for i in library.Library(tmp / "library.json").data["items"]], ["booth"])
        self.assertFalse(cached.exists(), "the cached picture shows what was bought, so it goes too")
        self.assertEqual(lib.data["stores"]["jinxxy"]["count"], 0)

    def test_sign_out_job_clears_the_list(self):
        tmp = Path(tempfile.mkdtemp())
        lib = library.Library(tmp / "library.json")
        lib.data["items"] = [library.item("gumroad", "x", name="Hoodie")]
        lib.data["stores"] = {"gumroad": {"count": 1}}
        job = jobs.Jobs(config.load_config(), lib)
        saved = jobs.sign_out, jobs._playwright
        jobs.sign_out = lambda p, cfg, store: "Gumroad: deleted the saved sign-in (3 cookies, plus the store's site data)."

        class NoBrowser:
            def __enter__(self): return None
            def __exit__(self, *a): return False
        jobs._playwright = lambda: NoBrowser
        try:
            job._logout(["gumroad"])
        finally:
            jobs.sign_out, jobs._playwright = saved
        self.assertEqual(lib.data["items"], [])
        self.assertIn("Removed 1 items", lib.data["stores"]["gumroad"]["error"])
        self.assertIn("downloaded files are still on disk", lib.data["stores"]["gumroad"]["error"])


class JinxxyBanners(unittest.TestCase):
    """Copies of Jinxxy's default banner saved as product pictures by older versions are removed."""

    def test_repeated_pictures_are_forgotten(self):
        store = Path(tempfile.mkdtemp()) / "Jinxxy"
        for creator, product, data in (("A", "One", b"BANNER"), ("B", "Two", b"BANNER"), ("C", "Three", b"REAL")):
            (store / creator / product).mkdir(parents=True)
            (store / creator / product / "_thumbnail.png").write_bytes(data)
        self.assertEqual(downloader.forget_repeated_thumbnails(store), 2)
        self.assertEqual(sorted(p.parent.name for p in store.rglob("_thumbnail.png")), ["Three"])


class PayhipShops(unittest.TestCase):
    """Payhip keeps purchases per shop; the shops you list are the only extra sites Hoard trusts for Payhip."""

    def tearDown(self):
        config.apply_store_sites(config.load_config())

    def test_addresses(self):
        good = {"myshop.store": "https://myshop.store", "https://myshop.store/b-account": "https://myshop.store",
                "payhip.com/MyShop": "https://payhip.com/MyShop", "https://payhip.com/MyShop/b-account": "https://payhip.com/MyShop"}
        for given, kept in good.items():
            self.assertEqual(config.clean_payhip_shop(given), kept, given)
        for bad in ("http://localhost", "https://127.0.0.1", "https://[::1]/", "https://user@shop.example", "payhip.com",
                    "https://payhip.com/a/b", "shop", "javascript:alert(1)", "https://shop.example:8443", ""):
            self.assertIsNone(config.clean_payhip_shop(bad), bad)

    def test_only_listed_shops_count_as_payhip(self):
        from hoard import safety
        cfg = config.load_config()
        cfg["payhip"]["shops"] = ["myshop.store"]
        config.apply_store_sites(cfg)
        self.assertTrue(safety.store_link("payhip", "https://myshop.store/b-account/digital/x"))
        self.assertIsNone(safety.store_link("payhip", "https://myshop.store.evil.example/"))
        self.assertIsNone(safety.store_link("booth", "https://myshop.store/"), "a Payhip shop never counts for another store")
        cfg["payhip"]["shops"] = []
        config.apply_store_sites(cfg)
        self.assertIsNone(safety.store_link("payhip", "https://myshop.store/b-account/digital/x"), "removed means removed")

    def test_settings(self):
        cfg = config.load_config()
        change = server.apply_settings(cfg, {"payhip_shops": ["myshop.store", "https://myshop.store/b-account", "payhip.com/Two"]})
        self.assertEqual(change["payhip"]["shops"], ["https://myshop.store", "https://payhip.com/Two"])
        with self.assertRaises(ValueError):
            server.apply_settings(cfg, {"payhip_shops": ["http://192.168.1.5"]})
        both = server.apply_settings(cfg, {"payhip_shops": ["a.store"], "stores": {"payhip": {"enabled": False}}})
        self.assertEqual(both["payhip"], {"shops": ["https://a.store"], "enabled": False})


class ComingFrom1x(unittest.TestCase):
    """Bringing over a 1.x library list and downloads folder, without overwriting anything."""

    def test_migrate(self):
        from hoard import setup
        old = Path(tempfile.mkdtemp())
        (old / "Hoard").mkdir()
        (old / "HoardDownloader" / "downloads").mkdir(parents=True)
        (old / "HoardDownloader" / "asset_dl.py").write_text("# 1.x")
        (old / "HoardDownloader" / "config.json").write_text(json.dumps({"root": "downloads", "booth": {"enabled": False}}))
        (old / "Hoard" / "library.json").write_text(json.dumps({"items": [
            {"store": "booth", "id": "1", "name": "Rusk", "url": "https://booth.pm/ja/items/1"}], "stores": {}}))
        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        config_file = Path(tempfile.mkdtemp()) / "config.json"
        cfg = config.load_config(config_file)
        said = setup.migrate_from(cfg, old / "Hoard", config_file, lib)
        self.assertIn("1 item)", said)
        self.assertEqual([i["name"] for i in lib.data["items"]], ["Rusk"])
        moved = config.load_config(config_file)
        self.assertEqual(Path(moved["root"]), (old / "HoardDownloader" / "downloads").resolve())
        self.assertFalse(moved["booth"]["enabled"])
        self.assertIn("already has a library list", setup.migrate_from(cfg, old, config_file, lib), "nothing is overwritten")
        self.assertIn("no folder", setup.migrate_from(cfg, old / "missing", config_file, lib))


class SetupAssistant(unittest.TestCase):
    """What the onboarding assistant relies on."""

    def test_links_from_emails(self):
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        self.assertIn("Start signing in", job.open_link("https://accounts.booth.pm/confirm"))
        job.state.update(running=True, task="login", store="booth")
        self.assertIn("isn't on Booth's own site", job.open_link("https://booth.pm.login-check.example/"))
        self.assertIn("isn't on Booth's own site", job.open_link("http://accounts.booth.pm/confirm"))
        self.assertIn("isn't on Booth's own site", job.open_link("https://app.gumroad.com/confirm"))
        self.assertIsNone(job.open_link("https://accounts.booth.pm/users/confirmation?token=x"))
        self.assertEqual(job.pending_link, "https://accounts.booth.pm/users/confirmation?token=x")

    def test_missing_browser_is_explained(self):
        from hoard import setup
        self.assertIn("Set up Hoard", setup.browser_problem(RuntimeError(
            "BrowserType.launch: Executable doesn't exist at /x/chrome\nPlease run: playwright install")))
        self.assertIn("isn't installed", setup.browser_problem(RuntimeError('Chromium distribution "msedge" is not found at /x')))
        self.assertIsNone(setup.browser_problem(RuntimeError("net::ERR_TIMED_OUT")))

    def test_status(self):
        from hoard import browser, setup
        cfg = {**config.load_config(), "profile_dir": tempfile.mkdtemp()}
        st = setup.setup_status(cfg)
        self.assertEqual(set(st), {"done", "browser", "stores", "payhip_shops", "root", "default_root"})
        self.assertFalse(st["stores"]["booth"]["signed_in"])
        db = browser.profile_dir(cfg, "booth") / "Default" / "Network" / "Cookies"
        db.parent.mkdir(parents=True)
        import sqlite3
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE cookies (host_key TEXT, encrypted_value BLOB, value TEXT)")
        con.execute("INSERT INTO cookies VALUES ('.booth.pm', x'7631', '')")
        con.commit(); con.close()
        self.assertTrue(setup.signed_in(cfg, "booth"))

    def test_endpoints(self):
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def call(method, path, body=None):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
                c.request(method, path, body=json.dumps(body) if body is not None else None,
                          headers={"Content-Type": "application/json"} if body is not None else {})
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return r.status, data
            status, st = call("GET", "/api/setup")
            self.assertEqual(status, 200)
            self.assertIn("browser", st)
            self.assertEqual(call("POST", "/api/signin-link", {"url": "https://accounts.booth.pm/x"})[0], 400)
            self.assertEqual(call("POST", "/api/setup/migrate", {"folder": "relative/folder"})[0], 400)
            self.assertEqual(call("POST", "/api/setup/done", {"done": True})[0], 200)
            self.assertTrue(srv.cfg["setup_done"])
        finally:
            srv.shutdown()
            srv.server_close()


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
