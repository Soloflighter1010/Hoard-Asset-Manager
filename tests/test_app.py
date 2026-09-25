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


class ArchiveHideRemove(unittest.TestCase):
    """Your archive, hidden and removed choices, and the hidden library's PIN."""

    def store(self):
        from hoard import marks
        return marks.MarkStore(Path(tempfile.mkdtemp()) / "marks.json")

    def test_choices_persist_and_validate(self):
        st = self.store()
        st.change("archived", {"booth:rusk", "bad key!"}, True)
        st.change("removed", {"payhip:pollution"}, True)
        again = type(st)(st.path).load()
        self.assertEqual((again["archived"], again["removed"]), ({"booth:rusk"}, {"payhip:pollution"}))
        st.change("unarchived", {"booth:rusk"}, True)
        self.assertEqual(st.load()["archived"], set(), "moving back out of the archive undoes archiving")
        with self.assertRaises(Exception):
            st.change("hidden", {"booth:rusk"}, True)   # no PIN yet

    def test_pin(self):
        from hoard import marks
        st = self.store()
        st.set_pin("4821")
        raw = st.path.read_text()
        self.assertNotIn("4821", raw)
        self.assertIn("scrypt" if "scrypt" in raw else '"n"', raw)
        st.check_pin("4821")
        for _ in range(marks.FREE_TRIES):
            with self.assertRaises(marks.PinError):
                st.check_pin("0000")
        with self.assertRaises(marks.PinError) as waiting:
            type(st)(st.path).check_pin("4821")   # the wait survives a restart, and applies to the right PIN too
        self.assertIn("Try again in", str(waiting.exception))
        with self.assertRaises(marks.PinError):
            st.set_pin("9999", current="0000")

    def test_forgotten_pin_deletes_never_reveals(self):
        st = self.store()
        st.set_pin("4821")
        st.change("hidden", {"booth:secret"}, True)
        self.assertEqual(st.forget_hidden(), {"booth:secret"})
        data = st.load()
        self.assertEqual((data["hidden"], data["pin"]), (set(), None))

    def test_editing_the_file_drops_the_pin(self):
        st = self.store()
        st.set_pin("4821")
        raw = json.loads(st.path.read_text())
        raw["hidden"] = ["booth:x"]
        st.path.write_text(json.dumps(raw))
        self.assertIsNone(st.load()["pin"], "an edited file can't keep a PIN someone else chose")

    def test_the_server_keeps_hidden_items_private(self):
        from hoard import marks, tags
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        lib = srv.lib
        with lib.lock:
            lib.data["items"] = [library.item("booth", "1", name="Secret Suit"), library.item("booth", "2", name="Plain Hat")]
            lib.save()
        secret = tags.tag_key("booth", "Secret Suit")
        st = marks.MarkStore()
        st.set_pin("4821")
        st.change("hidden", {secret}, True)
        try:
            def call(method, path, body=None, cookie=None):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
                headers = {"Content-Type": "application/json"} if body is not None else {}
                if cookie:
                    headers["Cookie"] = cookie
                c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return r.status, data, r.getheader("Set-Cookie")
            _, locked, _ = call("GET", "/api/library")
            self.assertEqual([i["name"] for i in locked["items"]], ["Plain Hat"])
            self.assertEqual(call("POST", "/api/marks", {"kind": "hidden", "keys": [secret], "on": False})[0], 403)
            self.assertEqual(call("POST", "/api/unlock", {"pin": "0000"})[0], 403)
            status, _, cookie = call("POST", "/api/unlock", {"pin": "4821"})
            self.assertEqual(status, 200)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            _, unlocked, _ = call("GET", "/api/library", cookie=cookie.split(";")[0])
            self.assertEqual(sorted(i["name"] for i in unlocked["items"]), ["Plain Hat", "Secret Suit"])
            self.assertEqual(len(call("GET", "/api/library")[1]["items"]), 1, "other browsers stay locked")
            call("POST", "/api/lock", {})
            self.assertEqual(len(call("GET", "/api/library", cookie=cookie.split(";")[0])[1]["items"]), 1, "Lock now locks")
            self.assertEqual(call("POST", "/api/purge", {"keys": [secret]})[1].get("deleted"), 0, "only removed items can be purged")
        finally:
            marks.MarkStore().path.unlink(missing_ok=True)
            srv.shutdown()
            srv.server_close()

    def test_removed_products_arent_downloaded(self):
        from hoard import marks, tags
        st = marks.MarkStore()
        st.change("removed", {tags.tag_key("payhip", "Someone Else's Pack")}, True)
        try:
            report = downloader.Report()
            self.assertTrue(downloader.removed_product("payhip", "Someone Else's Pack", report))
            self.assertFalse(downloader.removed_product("payhip", "My Pack", report))
            self.assertIn("removed from your library", report.skipped[0])
        finally:
            st.path.unlink(missing_ok=True)

    def test_found_payhip_shops_survive_only_if_valid(self):
        p = Path(tempfile.mkdtemp()) / "library.json"
        lib = library.Library(p)
        lib.data["stores"]["payhip"] = {"count": 0, "found_shops": ["https://good.store", "http://10.0.0.1", "https://xn--pypal-4ve.store"]}
        lib.save()
        self.assertEqual(library.Library(p).data["stores"]["payhip"]["found_shops"], ["https://good.store"])


class RecoveryPhrase(unittest.TestCase):
    """A forgotten PIN is reset with 6 recovery words, and hidden items stay hidden."""

    def store(self):
        from hoard import marks
        return marks.MarkStore(Path(tempfile.mkdtemp()) / "marks.json")

    def test_the_word_list_is_the_bip39_list(self):
        import hashlib
        from hoard import marks
        text = (REPO / "hoard" / "recovery_words.txt").read_bytes()
        self.assertEqual(hashlib.sha256(text).hexdigest(), "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda")
        self.assertEqual(len(set(marks.WORDS)), 2048)
        self.assertEqual(len({w[:4] for w in marks.WORDS}), 2048, "every word is unique in its first four letters")

    def test_phrases(self):
        from hoard import marks
        st = self.store()
        phrase = st.set_pin("4821")
        words = phrase.split()
        self.assertEqual(len(words), 6)
        self.assertTrue(all(w in marks.WORDS for w in words))
        on_disk = st.path.read_text()
        self.assertNotIn(phrase, on_disk)
        self.assertIsNone(st.set_pin("1111", current="4821"), "changing the PIN never shows the phrase again")
        self.assertNotEqual(self.store().set_pin("4821"), phrase, "each phrase is new")

    def test_reading_what_people_type(self):
        from hoard import marks
        words = ["abandon", "zoo", "legal", "winner", "thank", "year"]
        for typed in ("abandon zoo legal winner thank year", "1. Abandon, 2. ZOO, 3. lega 4 winn 5 thank 6 year\n",
                      "  abandon\tzoo legal\nwinner thank year  "):
            self.assertEqual(marks.read_phrase(typed), words, typed)
        with self.assertRaises(marks.PinError) as typo:
            marks.read_phrase("abandon zoo legal winner thank yaer")
        self.assertIn("Word 6 (yaer)", str(typo.exception))
        with self.assertRaises(marks.PinError) as short:
            marks.read_phrase("abandon zoo legal")
        self.assertIn("all 6", str(short.exception))

    def test_recover(self):
        from hoard import marks
        st = self.store()
        phrase = st.set_pin("4821")
        st.change("hidden", {"booth:secret"}, True)
        wrong = "abandon ability able about above absent"
        if wrong.split() == phrase.split():   # (a 1 in 2048^6 chance)
            wrong = "zoo zoo zoo zoo zoo zoo"
        with self.assertRaises(marks.PinError):
            st.recover(wrong, "7777")
        self.assertEqual(st.load()["failures"], 1, "wrong phrases count toward the lockout")
        with self.assertRaises(marks.PinError):
            st.recover("abandon zoo legal winner thank yaer", "7777")
        self.assertEqual(st.load()["failures"], 1, "a typo is pointed out without counting as a wrong try")
        st.recover(phrase.upper(), "7777")
        st.check_pin("7777")
        self.assertEqual(st.load()["hidden"], {"booth:secret"}, "hidden items stay hidden")
        self.assertEqual(st.load()["failures"], 0)

    def test_lockout_covers_phrases(self):
        from hoard import marks
        st = self.store()
        phrase = st.set_pin("4821")
        for _ in range(marks.FREE_TRIES):
            with self.assertRaises(marks.PinError):
                st.check_pin("0000")
        with self.assertRaises(marks.PinError) as waiting:
            st.recover(phrase, "7777")
        self.assertIn("Try again in", str(waiting.exception), "the phrase can't be used to get around the wait")

    def test_edited_or_forgotten(self):
        st = self.store()
        st.set_pin("4821")
        raw = json.loads(st.path.read_text())
        raw["hidden"] = ["booth:x"]
        st.path.write_text(json.dumps(raw))
        self.assertIsNone(st.load()["recovery"], "an edited file keeps no phrase")
        st2 = self.store()
        st2.set_pin("4821")
        st2.forget_hidden()
        self.assertIsNone(st2.load()["recovery"])

    def test_endpoints(self):
        from hoard import marks
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def call(path, body, cookie=None):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=30)
                headers = {"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})}
                c.request("POST", path, body=json.dumps(body), headers=headers)
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return r.status, data, (r.getheader("Set-Cookie") or "").split(";")[0]
            status, first, _ = call("/api/pin", {"pin": "4821"})
            self.assertEqual(len(first["recovery"].split()), 6)
            self.assertNotIn("recovery", call("/api/pin", {"pin": "1234", "current": "4821"})[1])
            self.assertEqual(call("/api/pin/phrase", {})[0], 403, "a new phrase needs unlocking")
            _, _, cookie = call("/api/unlock", {"pin": "1234"})
            status, newer, _ = call("/api/pin/phrase", {}, cookie)
            self.assertEqual((status, len(newer["recovery"].split())), (200, 6))
            self.assertEqual(call("/api/pin/recover", {"phrase": first["recovery"], "pin": "5555"})[0], 403, "the old phrase stopped working")
            self.assertEqual(call("/api/pin/recover", {"phrase": newer["recovery"], "pin": "5555"})[0], 200)
            self.assertFalse(srv.unlocks, "recovering locks every browser")
        finally:
            marks.MarkStore().path.unlink(missing_ok=True)
            srv.shutdown()
            srv.server_close()


class Sync(unittest.TestCase):
    """Sync reads what you own, then downloads anything new, as one job that Stop can end."""

    def test_reads_then_downloads(self):
        order = []
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        job._refresh = lambda stores, skip_imported=False: order.append(("read", tuple(stores), skip_imported))
        job._download = lambda stores, only: order.append(("download", tuple(stores)))
        done = threading.Event()
        job.on_download_done = done.set
        self.assertTrue(job.start("sync", ["booth", "jinxxy"]))
        for _ in range(100):
            if not job.state["running"]:
                break
            time.sleep(0.05)
        self.assertEqual(order, [("read", ("booth", "jinxxy"), True), ("download", ("booth", "jinxxy"))],
                         "pages you imported by hand aren't overwritten")
        self.assertFalse(job.state["sync"])

    def test_stop_between_reading_and_downloading(self):
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        downloaded = []
        job._refresh = lambda stores, skip_imported=False: (job.state.update(running=True, task="refresh"), job.cancel())
        job._download = lambda stores, only: downloaded.append(stores)
        job._sync(["booth"])
        self.assertEqual(downloaded, [])
        self.assertTrue(job.state["message"].startswith("Stopped"))


class UpdatingOverAnOldInstall(unittest.TestCase):
    """Python reuses compiled copies whose file date and size haven't changed; an update copied over an old
    install (with its old dates) must still run the new code."""

    def test_new_version_runs(self):
        import re
        import shutil
        import subprocess
        tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO / "hoard", tmp / "hoard", ignore=shutil.ignore_patterns("__pycache__"))
        init = tmp / "hoard" / "__init__.py"
        text = init.read_text("utf-8")
        fixed = 1767225600

        def install(version):
            init.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', text), "utf-8")
            os.utime(init, (fixed, fixed))
            return subprocess.run([sys.executable, "-m", "hoard", "--version"], cwd=tmp, capture_output=True,
                                  text=True, timeout=60, env={**os.environ, "PYTHONDONTWRITEBYTECODE": ""}).stdout.strip()
        self.assertEqual(install("9.8.7"), "Hoard 9.8.7")
        self.assertEqual(install("9.8.8"), "Hoard 9.8.8", "the old compiled copy was noticed and cleared")

    def test_zip_dates_come_from_the_release(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_release", REPO / "scripts" / "build_release.py")
        build = importlib.util.module_from_spec(spec)
        saved = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "1800000000"
        try:
            spec.loader.exec_module(build)
            self.assertEqual(build.build_date()[:3], (2027, 1, 15))
        finally:
            if saved is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = saved
        self.assertNotIn("date_time=(2026, 1, 1", (REPO / "scripts" / "build_release.py").read_text())
        for launcher in ("Hoard.bat", "run.sh"):
            self.assertIn("PYTHONDONTWRITEBYTECODE", (REPO / launcher).read_text(), launcher)


class PayhipBotCheck(unittest.TestCase):
    """A Payhip refresh in a visible window waits while you complete the store's check, instead of giving up."""

    def test_waits_then_carries_on(self):
        from hoard import browser

        class Page:
            url, waits = "https://payhip.com/Shop/b-account", 0
            def wait_for_timeout(self, ms): Page.waits += 1
        saved = browser.goto, browser.still_checking
        calls = []

        def goto(page, url):
            calls.append(url)
            if len(calls) == 1:
                raise browser.Blocked("bot check")
        browser.goto = goto
        browser.still_checking = lambda page: Page.waits < 3
        try:
            said = []
            browser.goto_past_check(Page(), "https://payhip.com/Shop/b-account", 30, said.append)
            self.assertIn("Complete the check", said[0])
            self.assertEqual(Page.waits, 3)
            browser.still_checking = lambda page: True
            calls.clear()
            with self.assertRaises(browser.Blocked):   # never completed: gives up after the wait
                browser.goto_past_check(Page(), "https://payhip.com/Shop/b-account", 0.01)
            calls.clear()
            with self.assertRaises(browser.Blocked):   # invisible browser: nobody to complete it, so no waiting
                browser.goto_past_check(Page(), "https://payhip.com/Shop/b-account", 0)
        finally:
            browser.goto, browser.still_checking = saved


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
