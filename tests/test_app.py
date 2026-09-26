"""Tests for Hoard as one app: settings, downloading with progress and Stop, and moving over from 1.x.

Run from the repository root:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
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
from hoard.safety import ACCESS_HEADER  # noqa: E402


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

    def test_itch_game_builds(self):
        cfg = config.load_config()
        self.assertTrue(server.public_settings(cfg)["stores"]["itch"]["skip_game_builds"], "skipped unless you want them")
        self.assertEqual(server.apply_settings(cfg, {"stores": {"itch": {"skip_game_builds": False}}}),
                         {"itch": {"skip_game_builds": False}})
        self.assertEqual(server.apply_settings(cfg, {"stores": {"booth": {"skip_game_builds": False}}}), {"booth": {}})

    def test_a_new_store_waits_to_be_turned_on(self):
        """itch.io came in 2.5.0: an install set up before then keeps the stores it chose; a new one starts with all."""
        folder = Path(tempfile.mkdtemp())
        (folder / "config.json").write_text(json.dumps({"setup_done": True, "booth": {"enabled": True}}), "utf-8")
        self.assertFalse(config.load_config(folder / "config.json")["itch"]["enabled"])
        (folder / "config.json").write_text(json.dumps({"setup_done": True, "itch": {"enabled": True}}), "utf-8")
        self.assertTrue(config.load_config(folder / "config.json")["itch"]["enabled"], "once you've chosen, your choice")
        (folder / "config.json").write_text(json.dumps({"setup_done": False}), "utf-8")
        self.assertTrue(config.load_config(folder / "config.json")["itch"]["enabled"], "setting up, it's offered like the rest")
        self.assertTrue(config.load_config(folder / "missing.json")["itch"]["enabled"])

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


class EmptyLibrary(unittest.TestCase):
    """B-01 (2.3.1 review): once nothing is downloaded any more, catalog.json and tags.json say so, instead of going
    on listing what's gone (the Unity window shows what catalog.json lists)."""

    def test_the_catalog_empties_with_the_downloads(self):
        from hoard import safety
        root = Path(tempfile.mkdtemp())
        folder = root / "Booth" / "Kitsu Studio" / "Rusk"
        folder.mkdir(parents=True)
        (folder / "rusk.zip").write_bytes(b"zip")
        man = downloader.Manifest(root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Rusk")
        rec.update(name="Rusk", creator="Kitsu Studio", url="https://booth.pm/ja/items/111")
        rec["files"]["f1"] = {"path": "rusk.zip", "size": 3}
        man.save()
        cfg = config.load_config()
        downloader.build_catalog(cfg, root)
        self.assertEqual(len(json.loads((root / "catalog.json").read_text("utf-8"))["assets"]), 1)
        shutil.rmtree(root / "Booth")   # every download deleted by hand
        downloader.build_catalog(cfg, root)
        catalog = json.loads((root / "catalog.json").read_text("utf-8"))
        tag_index = json.loads((root / "tags.json").read_text("utf-8"))
        self.assertEqual((catalog["assets"], tag_index["total_assets"], tag_index["tags"]), ([], 0, {}))
        self.assertEqual(safety.check_seal(catalog, root / "catalog.json"), "sealed")

    def test_a_new_folder_is_left_as_it_is(self):
        root = Path(tempfile.mkdtemp())
        downloader.build_catalog(config.load_config(), root)
        self.assertEqual(list(root.iterdir()), [])


class ManifestSaves(unittest.TestCase):
    """P-08 (2.3.1 review): while downloading, a store's manifest is written at most every SAVE_EVERY seconds, not
    after every file and every product; each sync still ends by saving everything, however it ends."""

    def test_checkpoints_are_spaced_out(self):
        man = downloader.Manifest(Path(tempfile.mkdtemp()) / "Booth")
        on_disk = lambda: set(json.loads(man.path.read_text("utf-8"))["assets"])  # noqa: E731
        man.record("1", "Kitsu", "One")
        man.checkpoint()
        self.assertEqual(on_disk(), {"1"}, "the first change is saved straight away")
        man.record("2", "Kitsu", "Two")
        man.checkpoint()
        self.assertEqual(on_disk(), {"1"}, "not again within SAVE_EVERY seconds")
        man._saved_at -= downloader.SAVE_EVERY   # as if that long had passed
        man.checkpoint()
        self.assertEqual(on_disk(), {"1", "2"})

    def test_an_unused_store_gets_no_manifest(self):
        """A manifest is how a sync tells a store you use from one you don't (see cmd_sync)."""
        man = downloader.Manifest(Path(tempfile.mkdtemp()) / "Jinxxy")
        man.checkpoint()
        man.save_changes()
        self.assertFalse(man.path.exists())


class LibraryLookups(unittest.TestCase):
    """P-05/P-06 (2.3.1 review): a picture is found without going through the whole library, and a page's copy of
    the library is a snapshot, not a JSON round trip of all of it."""

    def test_pictures_are_found_and_follow_changes(self):
        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        with lib.lock:
            lib.data["items"] = [library.item("booth", str(n), name=f"Item {n}", thumbnail=f"https://img.example/{n}.png")
                                 for n in range(3)] + [library.item("booth", "plain", name="No Picture")]
        self.assertEqual(lib.thumbnail_for("booth:2"), ("https://img.example/2.png", library.STORES["booth"]["referer"]))
        self.assertIsNone(lib.thumbnail_for("booth:plain"))
        self.assertIsNone(lib.thumbnail_for("booth:nothing"))
        lib.merge_store("booth", [library.item("booth", "2", name="Item 2", thumbnail="https://img.example/new.png")])
        self.assertEqual(lib.thumbnail_for("booth:2")[0], "https://img.example/new.png", "a change is seen straight away")
        lib.forget_products({library.tag_key("booth", "Item 2")})
        self.assertIsNone(lib.thumbnail_for("booth:2"))

    def test_a_snapshot_stays_as_it_was(self):
        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        lib.replace_store("booth", [library.item("booth", "1", name="One")])
        items, stores = lib.snapshot()
        lib.replace_store("booth", [])
        lib.set_error("booth", "changed since")
        self.assertEqual([i["key"] for i in items], ["booth:1"])
        self.assertIsNone(stores["booth"]["error"])


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
                headers = {**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: srv.key}
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
        text = (REPO / "hoard" / "recovery_words.txt").read_bytes().replace(b"\r\n", b"\n")   # as on any checkout
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
                headers = {"Content-Type": "application/json", ACCESS_HEADER: srv.key, **({"Cookie": cookie} if cookie else {})}
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

    def test_a_chosen_browser_thats_missing(self):
        """Settings named Edge or Chrome, which isn't installed: setup offers Hoard's own browser, and once it's
        installed that's the one used and shown as ready (it kept saying the chosen one "isn't installed")."""
        from unittest import mock
        from hoard import browser, setup
        cfg = {**config.load_config(), "browser_channel": "chrome"}
        with mock.patch.object(browser, "channel_installed", lambda channel: False), \
                mock.patch.object(setup, "channel_installed", lambda channel: False):
            self.assertEqual(browser.use_channel(cfg), "chromium")
            with mock.patch.object(setup, "own_browser_installed", lambda: False):
                st = setup.browser_status(cfg)
                self.assertEqual((st["ready"], st["can_install"]), (False, True))
                self.assertIn("Google Chrome isn't installed", st["note"])
            with mock.patch.object(setup, "own_browser_installed", lambda: True):
                st = setup.browser_status(cfg)
                self.assertEqual((st["ready"], st["name"]), (True, "Hoard's own browser"))
        with mock.patch.object(browser, "channel_installed", lambda channel: True), \
                mock.patch.object(setup, "channel_installed", lambda channel: True):
            self.assertEqual(browser.use_channel(cfg), "chrome", "installed: the one you chose")
            self.assertEqual(setup.browser_status(cfg)["name"], "Google Chrome")

    def test_one_browser_folder(self):
        """Installing and launching use the same folder, one outside Hoard's program folder: packaged as an app,
        Playwright looked in the program folder when launching, so an installed browser was never found."""
        from unittest import mock
        from hoard import browser
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
            browser.use_browsers_folder()
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(browser.browsers_folder()))
            self.assertEqual(browser.browsers_folder().name, "ms-playwright")
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/somewhere/you/chose"
            browser.use_browsers_folder()
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], "/somewhere/you/chose", "yours is kept")

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
                          headers={**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: srv.key})
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


class _ItchStandIn:
    """A stand-in api.itch.io and file host, on this computer. It records the Authorization header of every request."""

    KEY = "GoodKey1234567890abcdef"
    DATA = {5550001: b"PAW" * 1000}
    seen: list = []
    uploads: list = []

    @classmethod
    def start(cls):
        import hashlib
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import parse_qs, urlparse
        stand_in = cls

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, status, body=b"", ctype="application/json", headers=None):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                u = urlparse(self.path)
                stand_in.seen.append((self.server.server_port, u.path, self.headers.get("Authorization")))
                if self.server is stand_in.files:
                    data = stand_in.DATA.get(int(u.path.rsplit("/", 1)[-1]), b"")
                    return self.send(200, data, "application/octet-stream")
                if self.headers.get("Authorization") != f"Bearer {stand_in.KEY}":
                    return self.send(403, json.dumps({"errors": ["invalid key"]}).encode())
                q = parse_qs(u.query)
                if u.path == "/profile":
                    body = {"user": {"username": "buyer", "display_name": "Buyer"}}
                elif u.path == "/profile/owned-keys":
                    body = {"page": 1, "per_page": 50, "owned_keys": [] if q.get("page") != ["1"] else [
                        {"id": 77, "game_id": 1001, "game": {"id": 1001, "title": "Paw Suit", "url": "https://kitsu.itch.io/paw-suit",
                                                            "cover_url": "https://img.itch.zone/paw.png",
                                                            "user": {"display_name": "Kitsu Studio", "url": "https://kitsu.itch.io"}}}]}
                elif u.path == "/games/1001/uploads" and q.get("download_key_id") == ["77"]:
                    body = {"uploads": [dict(x, md5_hash=hashlib.md5(stand_in.DATA.get(x["id"], b"")).hexdigest()
                                             if x["id"] in stand_in.DATA else None) for x in stand_in.uploads]}
                elif u.path.startswith("/uploads/") and u.path.endswith("/download") and q.get("uuid"):
                    upload = u.path.split("/")[2]
                    return self.send(302, headers={"Location": f"http://localhost:{stand_in.files.server_port}/f/{upload}"})
                else:
                    return self.send(404, b"{}")
                self.send(200, json.dumps(body).encode())

        cls.api, cls.files = ThreadingHTTPServer(("127.0.0.1", 0), Handler), ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        for srv in (cls.api, cls.files):
            threading.Thread(target=srv.serve_forever, daemon=True).start()

    @classmethod
    def stop(cls):
        for srv in (cls.api, cls.files):
            srv.shutdown()
            srv.server_close()

    @classmethod
    def use(cls, test):
        """Point Hoard's itch.io code at the stand-ins for one test, with the key kept."""
        from unittest import mock
        from hoard import egress, itch, vault
        cls.seen.clear()
        cls.uploads = [{"id": 5550001, "filename": "PawSuit_v1.2.unitypackage", "size": 3000, "storage": "hosted", "traits": []},
                       {"id": 5550002, "filename": "PawSuit-Demo-Windows.zip", "size": 9, "storage": "hosted", "traits": ["p_windows"]},
                       {"id": 5550003, "filename": "Textures", "storage": "external"}]
        api = f"http://127.0.0.1:{cls.api.server_port}"
        egress._TEST_ORIGINS.update({api, f"http://localhost:{cls.files.server_port}"})
        test.addCleanup(egress._TEST_ORIGINS.clear)
        patcher = mock.patch.object(itch, "API", api)
        patcher.start()
        test.addCleanup(patcher.stop)
        cfg = {**config.load_config(), "request_delay": 0, "allow_unprotected_signins": True}
        vault.save_key(cfg, "itch", cls.KEY)
        test.addCleanup(lambda: vault.forget_key(cfg, "itch"))
        return cfg


class ItchKeys(unittest.TestCase):
    """The itch.io API key: kept with the operating system's protection, never in config.json, and deleted on sign-out."""

    def test_kept_and_forgotten(self):
        from hoard import vault
        cfg = {**config.load_config(), "allow_unprotected_signins": True}
        self.assertIsNone(vault.clean_key("not a key!"))
        self.assertEqual(vault.clean_key('  "GoodKey1234567890abcdef"\n'), "GoodKey1234567890abcdef")
        vault.save_key(cfg, "itch", "GoodKey1234567890abcdef")
        self.assertEqual(vault.load_key(cfg, "itch"), "GoodKey1234567890abcdef")
        self.assertNotIn("GoodKey", json.dumps(cfg))
        if os.name == "posix":
            self.assertEqual(os.stat(paths.data_dir() / "keys" / "itch.key").st_mode & 0o777, 0o600)
        else:   # encrypted by the Windows account: the file isn't the key
            self.assertNotIn(b"GoodKey", (paths.data_dir() / "keys" / "itch.dpapi").read_bytes())
        self.assertTrue(vault.forget_key(cfg, "itch"))
        self.assertIsNone(vault.load_key(cfg, "itch"))
        self.assertFalse(vault.forget_key(cfg, "itch"))

    @unittest.skipUnless(sys.platform.startswith("linux"), "the Linux keyring rule")
    def test_no_keyring_no_key(self):
        from unittest import mock
        from hoard import browser, vault
        with mock.patch.object(vault, "linux_keyring", lambda: None):
            with self.assertRaises(browser.SigninsUnprotected):
                vault.save_key(config.load_config(), "itch", "GoodKey1234567890abcdef")
            self.assertIsNone(vault.load_key(config.load_config(), "itch"))

    @unittest.skipUnless(sys.platform.startswith("linux"), "the Linux keyring")
    def test_the_keyring_gets_it_on_stdin(self):
        """Through secret-tool, with the key on stdin: never on a command line, which other accounts can read."""
        from unittest import mock
        from hoard import vault
        calls = []

        def run(cmd, stdin=""):
            calls.append((cmd, stdin))
            return types.SimpleNamespace(returncode=0, stdout="GoodKey1234567890abcdef\n", stderr="")
        import types
        with mock.patch.object(vault, "linux_keyring", lambda: "gnome-libsecret"), \
                mock.patch.object(vault.shutil, "which", lambda name: "/usr/bin/" + name), mock.patch.object(vault, "_run", run):
            vault.save_key(config.load_config(), "itch", "GoodKey1234567890abcdef")
            self.assertEqual(vault.load_key(config.load_config(), "itch"), "GoodKey1234567890abcdef")
        self.assertEqual(calls[0][0][:2], ["secret-tool", "store"])
        self.assertEqual(calls[0][1], "GoodKey1234567890abcdef")
        self.assertFalse(any("GoodKey" in " ".join(cmd) for cmd, _stdin in calls))


class ItchAPI(unittest.TestCase):
    """itch.io through its API, against a stand-in: the library, the files, and where the key goes."""

    @classmethod
    def setUpClass(cls):
        _ItchStandIn.start()

    @classmethod
    def tearDownClass(cls):
        _ItchStandIn.stop()

    def sync(self, cfg, root):
        import types
        report = downloader.Report()
        downloader.sync_itch(cfg, root, types.SimpleNamespace(headed=False, only=None, dry_run=False), report)
        return report

    def test_the_library(self):
        cfg = _ItchStandIn.use(self)
        (i,) = library.fetch_itch(None, cfg, lambda m: None)
        self.assertEqual((i["key"], i["name"], i["creator"], i["url"], i["download_url"]),
                         ("itch:1001", "Paw Suit", "Kitsu Studio", "https://kitsu.itch.io/paw-suit", None))

    def test_downloads_and_where_the_key_goes(self):
        from unittest import mock
        cfg = _ItchStandIn.use(self)
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(downloader, "save_thumbnail", lambda *a, **k: None):
            report = self.sync(cfg, root)
            self.assertEqual(report.failed, [])
            folder = root / "Itch" / "Kitsu Studio" / "Paw Suit"
            self.assertEqual((folder / "PawSuit_v1.2.unitypackage").read_bytes(), b"PAW" * 1000)
            self.assertFalse((folder / "PawSuit-Demo-Windows.zip").exists(), "a game build, skipped")
            skipped = " ".join(report.skipped)
            self.assertIn("a game build for Windows", skipped)
            self.assertIn("kept on another website", skipped)
            api, files = _ItchStandIn.api.server_port, _ItchStandIn.files.server_port
            self.assertTrue(all(auth == f"Bearer {_ItchStandIn.KEY}" for port, _p, auth in _ItchStandIn.seen if port == api))
            self.assertEqual([auth for port, _p, auth in _ItchStandIn.seen if port == files], [None], "the file host never gets the key")
            _ItchStandIn.seen.clear()
            self.assertEqual(self.sync(cfg, root).new_files, [], "nothing again while itch.io shows the same file")
            _ItchStandIn.DATA[5550001] = b"PAW2" * 1000   # the creator updates it
            _ItchStandIn.uploads[0]["filename"] = "PawSuit_v1.3.unitypackage"
            try:
                report = self.sync(cfg, root)
            finally:
                _ItchStandIn.DATA[5550001] = b"PAW" * 1000
            self.assertEqual(len(report.updated), 1)
            self.assertEqual((folder / "PawSuit_v1.3.unitypackage").read_bytes(), b"PAW2" * 1000)
            cfg["itch"] = {**cfg["itch"], "skip_game_builds": False}
            _ItchStandIn.DATA[5550002] = b"DEMO"
            try:
                self.sync(cfg, root)
            finally:
                del _ItchStandIn.DATA[5550002]
            self.assertTrue((folder / "PawSuit-Demo-Windows.zip").is_file(), "game builds when you want them")
        manifest = (root / "Itch" / "_manifest.json").read_text("utf-8")
        self.assertNotIn(_ItchStandIn.KEY, manifest)
        catalog, _tags = downloader.collect_catalog(config.load_config(), root)
        self.assertEqual(downloader.validate_catalog_entry(catalog[0]), [])

    def test_a_file_that_doesnt_match_its_checksum(self):
        from unittest import mock
        cfg = _ItchStandIn.use(self)
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(downloader, "save_thumbnail", lambda *a, **k: None), \
                mock.patch.object(downloader, "md5_of", lambda path: "0" * 32):
            report = self.sync(cfg, root)
        self.assertIn("didn't match itch.io's checksum", report.failed[0])
        self.assertFalse((root / "Itch" / "Kitsu Studio" / "Paw Suit" / "PawSuit_v1.2.unitypackage").exists())

    def test_a_refused_key(self):
        from hoard import itch, vault
        cfg = _ItchStandIn.use(self)
        vault.save_key(cfg, "itch", "WrongKey1234567890abcdef")
        with self.assertRaises(itch.KeyRefused):
            library.fetch_itch(None, cfg, lambda m: None)
        vault.forget_key(cfg, "itch")
        with self.assertRaises(common.NotLoggedIn):
            self.sync(cfg, Path(tempfile.mkdtemp()))

    def test_signing_in_and_out(self):
        """The page's key goes to POST /api/itch-key: checked with itch.io, kept, and the library read, no browser."""
        from unittest import mock
        from hoard import vault
        cfg = _ItchStandIn.use(self)
        vault.forget_key(cfg, "itch")
        srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        srv.lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        srv.jobs.lib = srv.lib
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def post(path, body):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
            c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key})
            r = c.getresponse()
            data = json.loads(r.read() or b"{}")
            c.close()
            return r.status, data
        self.assertEqual(post("/api/itch-key", {"key": "short"})[0], 400)
        self.assertEqual(post("/api/itch-key", {"key": "WrongKey1234567890abcdef"})[0], 400)
        self.assertIsNone(vault.load_key(cfg, "itch"), "a refused key isn't kept")
        self.assertEqual(post("/api/login", {"stores": ["itch"]})[0], 400, "no browser sign-in for itch.io")
        with mock.patch.object(jobs, "reachable", lambda store, timeout=5.0: True), \
                mock.patch.object(jobs, "launch", lambda *a, **k: self.fail("a browser was opened")):
            status, said = post("/api/itch-key", {"key": _ItchStandIn.KEY})
            self.assertEqual((status, said["user"]), (200, "Buyer"))
            for _ in range(200):
                if not srv.jobs.state["running"] and srv.lib.data["items"]:
                    break
                time.sleep(0.05)
        self.assertEqual(vault.load_key(cfg, "itch"), _ItchStandIn.KEY)
        self.assertEqual([i["key"] for i in srv.lib.data["items"]], ["itch:1001"])
        from hoard import browser
        said = browser.sign_out(None, cfg, "itch")
        self.assertIn("deleted the saved API key", said)
        self.assertIsNone(vault.load_key(cfg, "itch"))


class PayhipIsListedOnly(unittest.TestCase):
    """Hoard reads Payhip and never downloads from it: a sync leaves it out, however it's asked."""

    def test_syncing_leaves_payhip_out(self):
        import types
        from unittest import mock
        synced = []
        pretend = {f"sync_{s}": (lambda s: lambda cfg, root, args, report: synced.append(s))(s) for s in library.DOWNLOADABLE}
        cfg = {**config.load_config(), "root": tempfile.mkdtemp()}
        with mock.patch.multiple(downloader, reachable=lambda store, timeout=5.0: True, build_catalog=lambda cfg, root: None,
                                 **pretend):
            for asked in ("all", ["payhip", "booth"], ["payhip"]):
                downloader.cmd_sync(cfg, types.SimpleNamespace(store=asked, dry_run=False, only=None, headed=False))
        self.assertEqual(synced, ["booth", "gumroad", "jinxxy", "itch", "booth"])
        self.assertFalse(hasattr(downloader, "sync_payhip"))

    def test_refreshing_without_shops_opens_no_window(self):
        """With no shop listed there's nothing to read, so no window opens just to say so; importing is suggested."""
        from unittest import mock
        cfg = config.load_config()
        cfg["payhip"] = {**cfg["payhip"], "shops": []}
        job = jobs.Jobs(cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))

        class NoBrowser:
            def __enter__(self):
                return None

            def __exit__(self, *a):
                return False

        def launch(*a, **k):
            raise AssertionError("a browser window was opened")
        with mock.patch.multiple(jobs, reachable=lambda store, timeout=5.0: True, _playwright=lambda: NoBrowser, launch=launch):
            job._refresh(["payhip"])
        self.assertIn("Import each shop's saved library pages", job.lib.data["stores"]["payhip"]["error"])

    def test_nothing_that_downloads_takes_payhip(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["sync", "--store", "payhip"])
        job = jobs.Jobs(config.load_config(), library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        done = []
        job.on_download_done = lambda: done.append(True)
        job._download(["payhip"], None)
        self.assertIn("download it from Payhip yourself", job.state["message"])
        self.assertEqual(done, [True], "the downloads view is still told the job ended")
        srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            c.request("POST", "/api/download", body=json.dumps({"stores": ["payhip"]}),
                      headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key})
            r = c.getresponse()
            said = json.loads(r.read())
            c.close()
            self.assertEqual(r.status, 400)
            self.assertIn("doesn't download from it", said["error"])
            self.assertFalse(srv.jobs.state["running"])
        finally:
            srv.shutdown()
            srv.server_close()


class ImportingPages(unittest.TestCase):
    """The import endpoint: saved pages a batch at a time, each with its own result. A Payhip shop a page names is
    only added once you've confirmed it; test_readers reads real pages, and test_pages goes through the Library."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        cfg = {**config.load_config(), "offline_images": False}
        cfg["payhip"] = {**cfg["payhip"], "shops": []}
        self.srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False, config_path=self.tmp / "config.json")
        self.srv.lib = library.Library(self.tmp / "library.json")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        config.apply_store_sites(config.load_config())

    def post(self, body):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=20)
        c.request("POST", "/api/import", body=json.dumps(body),
                  headers={"Content-Type": "application/json", ACCESS_HEADER: self.srv.key})
        r = c.getresponse()
        data = json.loads(r.read() or b"{}")
        c.close()
        return r.status, data

    @staticmethod
    def pretend(cfg, pages, store, trust):
        """import_saved_pages without a browser: shop pages need their shop trusted, itch pages are read, the rest fail."""
        results = []
        for name, text in pages:
            if name.startswith("shop"):
                if "https://testshop.store" not in trust:
                    results.append({"filename": name, "confirm_shop": "https://testshop.store"})
                    continue
                cfg["payhip"]["shops"] = ["https://testshop.store"]
                results.append({"filename": name, "store": "payhip", "items": [library.item("payhip", "testshop.store-" + text, name=text)]})
            elif name.startswith("itch"):
                results.append({"filename": name, "store": "itch", "items": [library.item("itch", "kitsu/" + text, name=text)]})
            else:
                results.append({"filename": name, "error": "couldn't tell which store this page is from"})
        return results

    def test_each_page_gets_its_own_result(self):
        from unittest import mock
        with mock.patch.object(server, "import_saved_pages", self.pretend):
            status, got = self.post({"files": [{"filename": "shop 1.mhtml", "content": "One"},
                                               {"filename": "itch library.html", "content": "paw-suit"},
                                               {"filename": "notes.html", "content": "hello"}]})
            self.assertEqual(status, 200)
            self.assertEqual([r.get("count", r.get("confirm_shop", r.get("error"))) for r in got["results"]],
                             ["https://testshop.store", 1, "couldn't tell which store this page is from"])
            self.assertEqual(got["totals"], {"itch": {"label": "itch.io", "total": 1}})
            self.assertEqual(got["added_shops"], [])
            self.assertFalse((self.tmp / "config.json").exists(), "nothing confirmed, so no shop added")
            status, got = self.post({"files": [{"filename": "shop 1.mhtml", "content": "One"}],
                                     "trust_shops": ["https://testshop.store"]})
        self.assertEqual((got["results"][0]["count"], got["added_shops"]), (1, ["https://testshop.store"]))
        self.assertEqual(json.loads((self.tmp / "config.json").read_text("utf-8"))["payhip"]["shops"], ["https://testshop.store"])
        self.assertEqual(sorted(i["key"] for i in self.srv.lib.data["items"]), ["itch:kitsu/paw-suit", "payhip:testshop.store-One"])
        self.assertEqual(self.srv.lib.data["stores"]["itch"]["source"], "import")

    def test_what_isnt_a_batch_of_pages(self):
        for body in ({}, {"files": []}, {"files": "page"}, {"files": [{"filename": "a.mhtml"}]}, {"files": [{"content": 5}]},
                     {"files": [{"filename": "p.mhtml", "content": ""}] * (server.MAX_IMPORT_FILES + 1)}):
            self.assertEqual(self.post(body)[0], 400, body)


class ImportCommand(unittest.TestCase):
    """hoard-cli import: files and folders of saved pages, a batch at a time, with a line for each page that wasn't
    imported."""

    def test_files_and_folders(self):
        import contextlib
        import io
        import types
        from unittest import mock
        tmp = Path(tempfile.mkdtemp())
        (tmp / "pages" / "more").mkdir(parents=True)
        for rel in ("pages/a.mhtml", "pages/more/b.html", "pages/notes.txt", "c.mht"):
            (tmp / rel).write_text("page " + rel, "utf-8")
        batches = []

        def pretend(cfg, pages, store, trust, progress):
            batches.append([name for name, _text in pages])
            for n, (name, _text) in enumerate(pages, 1):
                progress(n, len(pages), name)
            return [{"filename": name, "confirm_shop": "https://testshop.store"} if name == "c.mht"
                    else {"filename": name, "store": "booth", "items": [library.item("booth", name, name=name)]}
                    for name, _text in pages]
        out = io.StringIO()
        with mock.patch.object(cli, "import_saved_pages", pretend), mock.patch.object(cli, "LIBRARY_FILE", tmp / "library.json"), \
                contextlib.redirect_stdout(out):
            code = cli.cmd_import(config.load_config(), types.SimpleNamespace(
                paths=[tmp / "pages", tmp / "c.mht"], store=None, trust_shop=None, config=tmp / "config.json"), batch=2)
        self.assertEqual(batches, [["a.mhtml", "b.html"], ["c.mht"]], "folders searched, other files left alone")
        said = out.getvalue()
        self.assertIn("Reading b.html (2 of 3)", said)
        self.assertIn("Imported 2 Booth items", said)
        self.assertIn("--trust-shop testshop.store", said)
        self.assertEqual(code, 1, "a page wasn't imported, and a script can tell")
        self.assertEqual(len(library.Library(tmp / "library.json").data["items"]), 2)

    def test_a_shop_must_be_a_shop(self):
        import types
        with self.assertRaises(SystemExit) as stopped:
            cli.cmd_import(config.load_config(), types.SimpleNamespace(paths=[], store=None, trust_shop=["http://192.168.1.5"],
                                                                        config=None))
        self.assertIn("isn't a Payhip shop", str(stopped.exception))


class StoreTables(unittest.TestCase):
    """Every list of stores, in the app, its pages and Hoard for Unity, names the same stores, so a store can't be
    half added, or half taken away."""

    def test_the_same_stores_everywhere(self):
        import re
        from hoard import browser, downloads, net, safety, tags
        stores = set(library.STORES)
        for name, table in (("browser.STORE_SITES", browser.STORE_SITES), ("browser.STORE_ORIGINS", browser.STORE_ORIGINS),
                            ("browser.STORE_ACCOUNT_PAGES", browser.STORE_ACCOUNT_PAGES), ("net.STORE_HOSTS", net.STORE_HOSTS),
                            ("safety.STORE_LINK_SITES", safety.STORE_LINK_SITES), ("library.FETCHERS", library.FETCHERS),
                            ("downloader.STORE_DIRS", downloader.STORE_DIRS)):
            self.assertEqual(set(table), stores, name)
        for s in stores:
            self.assertIn(s, config.DEFAULT_CONFIG)
            self.assertTrue(tags.TAG_KEY_RX.match(f"{s}:thing"), s)
            self.assertEqual(downloader.STORE_DIRS[s].lower(), s, "a store's folder is its name: records find their store by it")
        self.assertEqual(set(downloads.STORES), set(downloader.STORE_DIRS.values()))
        self.assertTrue(set(library.DOWNLOADABLE) <= stores and set(library.IMPORTABLE) <= stores)
        self.assertNotIn("payhip", library.DOWNLOADABLE)
        web = REPO / "hoard" / "web"
        for page in ("library.html", "downloads.html"):
            html = (web / page).read_text("utf-8")
            for const in ("STORE_SITES", "STORE_NAMES"):
                keys = set(re.findall(r"(\w+):", re.search(rf"const {const} = \{{(.*?)\}};", html).group(1)))
                self.assertEqual(keys, stores, f"{page}: {const}")
            for s in stores:
                self.assertEqual(len(re.findall(rf"--{s}: #[0-9A-Fa-f]{{6}};", html)), 2, f"{page}: {s}'s colour, in both themes")
                self.assertIn(f".{s} {{ --c: var(--{s}); }}", html, page)
        order = re.search(r"const STORE_ORDER = \[(.*?)\];", (web / "library.html").read_text("utf-8")).group(1)
        self.assertEqual(re.findall(r'"(\w+)"', order), list(library.STORES))
        self.assertEqual(set(re.findall(r'data-store="(\w+)"', (web / "downloads.html").read_text("utf-8"))),
                         set(downloader.STORE_DIRS.values()))
        unity = REPO / "Packages" / "soloflighter.hoard" / "Editor"
        catalog = (unity / "Core" / "Catalog.cs").read_text("utf-8")
        self.assertEqual(set(re.findall(r'"(\w+)"', re.search(r"Stores = \{(.*?)\};", catalog).group(1))),
                         set(downloader.STORE_DIRS.values()))
        self.assertEqual(dict(re.findall(r'\{ "(\w+)", "([\w.]+)" \}', catalog)),
                         {downloader.STORE_DIRS[s]: safety.STORE_LINK_SITES[s][0] for s in stores})
        window = (unity / "HoardWindow.cs").read_text("utf-8")
        self.assertEqual(re.findall(r'"(\w+)"', re.search(r"StoreNames = \{(.*?)\};", window).group(1)),
                         [downloader.STORE_DIRS[s] for s in library.STORES])


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


class CatalogSeal(unittest.TestCase):
    """The Unity window reads catalog.json: when it isn't sealed with this install's key, Hoard seals it again."""

    def setUp(self):
        from hoard import safety
        self.safety = safety
        self.root = Path(tempfile.mkdtemp())
        self.cfg = {**config.load_config(), "root": str(self.root)}

    def catalog(self, key: bytes | None = None, text: str | None = None) -> Path:
        path = self.root / "catalog.json"
        if text is not None:
            path.write_text(text, "utf-8")
            return path
        saved = self.safety._integrity_key
        if key is not None:
            self.safety._integrity_key = key
        try:
            path.write_text(json.dumps(self.safety.seal({"format": "hoard-catalog", "version": 3, "assets": []})), "utf-8")
        finally:
            self.safety._integrity_key = saved
        return path

    def status(self) -> str:
        return self.safety.check_seal(json.loads((self.root / "catalog.json").read_text("utf-8")))

    def test_sealed_elsewhere_is_sealed_again(self):
        self.catalog(bytes(range(32)))   # another key: another computer, or Hoard on Store Python
        self.assertEqual(self.status(), "foreign")
        self.assertEqual(downloader.reseal_catalog(self.cfg, self.root), "foreign")
        self.assertEqual(self.status(), "sealed")

    def test_already_sealed_is_left_alone(self):
        path = self.catalog()
        before = path.stat().st_mtime_ns
        self.assertIsNone(downloader.reseal_catalog(self.cfg, self.root))
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_unreadable_or_missing(self):
        self.catalog(text="{not json")
        self.assertEqual(downloader.reseal_catalog(self.cfg, self.root), "unreadable")
        self.assertEqual(self.status(), "sealed")
        (self.root / "catalog.json").unlink()
        self.assertIsNone(downloader.reseal_catalog(self.cfg, self.root))

    def test_at_startup(self):
        self.catalog(bytes(range(32)))
        ready = threading.Event()
        state = {}
        threading.Thread(target=server.serve, daemon=True, kwargs=dict(
            cfg=self.cfg, port=0, open_browser=False,
            on_ready=lambda url, srv: (state.update(srv=srv), ready.set()))).start()
        self.assertTrue(ready.wait(20))
        try:
            for _ in range(100):
                if self.status() == "sealed":
                    break
                time.sleep(0.1)
            self.assertEqual(self.status(), "sealed", "opening Hoard seals the catalog again")
        finally:
            state["srv"].shutdown()
            state["srv"].server_close()

    def test_not_while_a_job_runs(self):
        self.catalog(bytes(range(32)))
        srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)
        try:
            srv.jobs.busy.acquire()
            server.reseal_in_background(srv, self.cfg)
            self.assertEqual(self.status(), "foreign", "a running job rebuilds the catalog itself")
            srv.jobs.busy.release()
            server.reseal_in_background(srv, self.cfg)
            self.assertEqual(self.status(), "sealed")
        finally:
            srv.server_close()

    def test_store_python_is_recognised(self):
        from unittest import mock
        store = r"C:\Users\sam\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe"
        org = r"C:\Users\sam\AppData\Local\Programs\Python\Python312\python.exe"
        with mock.patch.object(paths.sys, "platform", "win32"):
            with mock.patch.object(paths.sys, "executable", store):
                self.assertTrue(paths.store_python())
            with mock.patch.object(paths.sys, "executable", org), mock.patch.object(paths.sys, "prefix", org), \
                 mock.patch.object(paths.sys, "base_prefix", org):
                self.assertFalse(paths.store_python())
        with mock.patch.object(paths.sys, "platform", "linux"), mock.patch.object(paths.sys, "executable", store):
            self.assertFalse(paths.store_python())


class TagMatching(unittest.TestCase):
    """Matching tags go through a word index (review finding P-04), with exactly name_has_word's answers."""

    def test_same_answers(self):
        import random
        from hoard.tags import TagMatcher, name_has_word
        rng = random.Random(7)
        parts = ["fox", "foxes", "foxs", "foxess", "box", "boxes", "Fox", "FoxEars", "fox-ears", "fox ears", "ear",
                 "v-roid", "3d", "3D", "model", "models", "ラスク", "ﾗｽｸ", "Kemonomimi", "cat's", "v2", "_", "-", "【", "】",
                 "x", "xs", "xes", "es", "s"]
        words = ["fox", "box", "ear", "fox ears", "v-roid", "3d model", "3d", "model", "ラスク", "kemono", "fox-", "-x",
                 "Fox", "x", "es", "s", "cat's", "ﾗｽｸ", "fox ear"]
        tags = {f"t{n}": {"match": w} for n, w in enumerate(words)} | {"plain": {"match": None}}
        matcher = TagMatcher(tags)
        names = [" ".join(rng.choice(parts) for _ in range(rng.randint(1, 6))) for _ in range(2000)]
        names += ["".join(rng.choice(parts) for _ in range(rng.randint(1, 4))) for _ in range(1000)]
        for name in names:
            want = {t for t, i in tags.items() if i["match"] and name_has_word(name, i["match"])}
            self.assertEqual(matcher.tags(name), want, name)

    def test_big_library(self):
        import random
        from hoard.tags import TagMatcher, TagStore
        rng = random.Random(3)
        vocab = [f"word{n}" for n in range(3000)]
        data = {"items": {}, "excluded": {}, "hidden": [],
                "tags": {f"tag{n}": {"match": vocab[n * 7 % 3000]} for n in range(300)}}
        names = [" ".join(rng.choice(vocab) for _ in range(5)) for _ in range(20000)]
        start = time.time()
        matcher = TagMatcher(data["tags"])
        for n, name in enumerate(names):
            TagStore.tags_for(data, f"Booth/{n}", name, matcher)
        self.assertLess(time.time() - start, 5, "20,000 names with 300 matching tags (every tag on every name: ~30 s)")


class DownloadsIndex(unittest.TestCase):
    """The downloads index is rebuilt outside its lock (review finding P-07): downloads never wait for it."""

    def setUp(self):
        from unittest import mock
        self.builds, self.started, self.release = 0, threading.Event(), threading.Event()
        self.release.set()

        def slow_build(root, catalog):
            self.builds += 1
            self.started.set()
            self.release.wait(10)
            return {"root": str(root), "assets": [{"id": self.builds, "tag_key": f"k{self.builds}"}], "status": {}}
        self.patches = [mock.patch.object(server, "build_index", slow_build),
                        mock.patch.object(server, "collect_catalog", lambda cfg, root: ([], None))]
        for p in self.patches:
            p.start()
        self.cfg = {**config.load_config(), "root": tempfile.mkdtemp()}
        self.srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)

    def tearDown(self):
        self.release.set()
        self.srv.server_close()
        for p in self.patches:
            p.stop()

    def rebuild_in_background(self):
        self.started.clear()
        self.release.clear()
        t = threading.Thread(target=self.srv.index, daemon=True)
        t.start()
        self.assertTrue(self.started.wait(5))
        return t

    def test_a_download_never_waits_for_a_rebuild(self):
        t = self.rebuild_in_background()
        start = time.time()
        self.srv.forget_index()
        self.assertLess(time.time() - start, 0.2)
        self.release.set()
        t.join(5)

    def test_the_library_page_gets_the_index_as_it_was(self):
        self.srv.index()
        self.srv.forget_index()
        t = self.rebuild_in_background()
        start = time.time()
        self.assertEqual(self.srv.index(stale_ok=True)["assets"][0]["id"], 1)
        self.assertLess(time.time() - start, 0.2)
        self.release.set()
        t.join(5)

    def test_one_rebuild_for_everyone_waiting(self):
        t = self.rebuild_in_background()
        results = []
        others = [threading.Thread(target=lambda: results.append(self.srv.index()["assets"][0]["id"])) for _ in range(5)]
        for o in others:
            o.start()
        time.sleep(0.2)
        self.release.set()
        for o in [t, *others]:
            o.join(5)
        self.assertEqual(self.builds, 1)
        self.assertEqual(results, [1] * 5)

    def test_a_change_during_a_rebuild_is_not_missed(self):
        t = self.rebuild_in_background()
        self.srv.forget_index()   # a download finishes while the index is being rebuilt
        self.release.set()
        t.join(5)
        self.assertEqual(self.srv.index()["assets"][0]["id"], 2, "rebuilt again for the new download")
        self.assertEqual(self.srv.index()["assets"][0]["id"], 2, "and then kept")
        self.assertEqual(self.srv.index(rescan=True)["assets"][0]["id"], 3, "a rescan always rebuilds")

    def test_a_failed_rebuild_never_leaves_anyone_waiting(self):
        from unittest import mock
        with mock.patch.object(server, "build_index", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.srv.index()
        self.assertEqual(self.srv.index()["assets"][0]["id"], 1)


class CompressedLists(unittest.TestCase):
    """The library and downloads lists are gzipped for a browser that accepts it, when they're large."""

    def setUp(self):
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": tempfile.mkdtemp(),
                                                       "setup_done": True}, lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, path, gzip_ok=True):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=30)
        headers = {"X-Hoard-Key": self.srv.key, "Cookie": f"hoard_key={self.srv.key}"}
        if gzip_ok:
            headers["Accept-Encoding"] = "gzip, deflate, br"
        c.request("GET", path, headers=headers)
        r = c.getresponse()
        return r, r.read()

    def test_large_lists(self):
        import gzip
        with self.srv.lib.lock:
            self.srv.lib.data["items"] = [library.item("booth", str(n), name=f"Item {n}", creator="Kitsu")
                                          for n in range(2000)]
        r, body = self.get("/api/library")
        self.assertEqual(r.getheader("Content-Encoding"), "gzip")
        self.assertEqual(len(json.loads(gzip.decompress(body))["items"]), 2000)
        r, body = self.get("/api/library", gzip_ok=False)
        self.assertIsNone(r.getheader("Content-Encoding"), "only when the browser accepts it")
        self.assertEqual(len(json.loads(body)["items"]), 2000)

    def test_small_replies_are_sent_as_they_are(self):
        r, body = self.get("/api/library")
        self.assertIsNone(r.getheader("Content-Encoding"))
        r, body = self.get("/api/status")
        self.assertIsNone(r.getheader("Content-Encoding"))


class DownloadEstimate(unittest.TestCase):
    """While downloading: the file's size, the speed, the time it has left, and this sync's totals."""

    def test_speed_and_time_left(self):
        from hoard.transfers import Transfers
        now = [0.0]
        t = Transfers(clock=lambda: now[0])
        mb = 1024 * 1024
        first = t.update("Rusk.unitypackage", 0, 100 * mb)
        self.assertEqual((first["files"], first["speed"], first["left"]), (1, None, None), "no speed from one sample")
        now[0] = 1
        view = t.update("Rusk.unitypackage", 10 * mb, 100 * mb)
        self.assertEqual((view["speed"], view["left"]), (10 * mb, 9))
        now[0] = 2
        self.assertEqual(t.update("Rusk.unitypackage", 20 * mb, 100 * mb)["left"], 8)
        now[0] = 3   # a resumed file: its first 50 MB were already there, and aren't speed
        view = t.update("Mochi.zip", 50 * mb, 60 * mb)
        self.assertEqual((view["files"], view["bytes"], view["left"]), (2, 20 * mb, 1))
        now[0] = 4
        self.assertIsNone(t.update("Mochi.zip", 51 * mb, None)["left"], "no size, no time left")

    def test_the_speed_is_smoothed(self):
        from hoard.transfers import Transfers
        now = [0.0]
        t = Transfers(clock=lambda: now[0])
        t.update("a", 0, None)
        done = 0
        for _ in range(10):   # 10 MB/s for 5 s
            now[0] += 0.5
            done += 5 * 1024 * 1024
            t.update("a", done, None)
        now[0] += 0.5   # then a half-second stall
        speed = t.update("a", done, None)["speed"]
        self.assertGreater(speed, 8 * 1024 * 1024, "one slow moment doesn't halve the speed")

    def test_the_job_shows_it(self):
        from types import SimpleNamespace
        from unittest import mock
        from hoard import common
        seen = []
        j = jobs.Jobs({**config.load_config(), "root": tempfile.mkdtemp()}, library.Library(Path(tempfile.mkdtemp()) / "l.json"))

        def fake_sync(cfg, args):
            for n in range(4):
                common.report_transfer("Rusk.unitypackage", n * 1000, 4000)
                time.sleep(0.05)
                seen.append(dict(j.state.get("transfer") or {}))
            return SimpleNamespace(new_assets=[], new_files=[], updated=[], skipped=[], failed=[])
        with mock.patch.object(downloader, "cmd_sync", fake_sync):
            j._download(["booth"], None)
        self.assertEqual(seen[-1]["file"], "Rusk.unitypackage")
        self.assertEqual(seen[-1]["done"], 3000)
        self.assertIsNotNone(seen[-1]["speed"])
        self.assertIsNone(j.state.get("transfer"), "cleared when the download ends")


if __name__ == "__main__":
    unittest.main()


class AutomaticSync(unittest.TestCase):
    """Settings, Sync automatically: when a sync starts by itself, and what it leaves alone."""

    def setUp(self):
        from unittest import mock
        self.cfg = {**config.load_config(), "setup_done": True, "auto_sync_hours": 24}
        self.started = []
        self.fake = mock.Mock(state={"running": False})
        self.fake.start = lambda task, stores, **kw: self.started.append((task, stores, kw)) or True
        self.schedule = jobs.Schedule(self.cfg, self.fake)
        self.schedule.not_before = 0
        jobs._sync_file().unlink(missing_ok=True)
        patch = mock.patch.object(jobs, "reachable", lambda store: True)
        patch.start()
        self.addCleanup(patch.stop)

    def test_due_after_the_interval_from_the_last_sync(self):
        now = time.time()
        self.assertTrue(self.schedule.tick(now))
        (task, stores, kw), = self.started
        self.assertEqual((task, kw), ("sync", {"skip_imported": False, "scheduled": True}))
        self.assertNotIn("payhip", stores, "Payhip needs you there for its bot check")
        self.assertIn("booth", stores)
        jobs._record_sync()   # what the sync itself does as it starts
        self.assertFalse(self.schedule.due(now + 23 * 3600))
        self.assertTrue(self.schedule.due(time.time() + 24 * 3600 + 1))

    def test_when_it_waits(self):
        now = time.time()
        for change, why in (({"auto_sync_hours": 0}, "off"), ({"auto_sync_hours": 5}, "not a choice"),
                            ({"setup_done": False}, "before setup is done")):
            with self.subTest(why):
                cfg = {**self.cfg, **change}
                self.assertFalse(jobs.Schedule(cfg, self.fake).due(now + 3600), why)
        self.fake.state["running"] = True
        self.assertFalse(self.schedule.due(now), "another job is running")
        self.fake.state["running"] = False
        self.assertFalse(jobs.Schedule(self.cfg, self.fake).due(now), "not straight after Hoard starts")
        only_payhip = {**self.cfg, **{s: {**self.cfg[s], "enabled": s == "payhip"} for s in library.STORES}}
        self.assertFalse(jobs.Schedule(only_payhip, self.fake).due(now), "nothing it can sync unattended")

    def test_offline_it_tries_again_later(self):
        from unittest import mock
        now = time.time()
        with mock.patch.object(jobs, "reachable", lambda store: False):
            self.assertFalse(self.schedule.tick(now))
        self.assertEqual(self.started, [])
        self.assertEqual(self.schedule.not_before, now + jobs.OFFLINE_RETRY)
        self.assertEqual(jobs.last_sync(), 0, "a sync that never started isn't counted")

    def test_any_sync_counts(self):
        """A sync you start resets the clock too, and the job says whether it started by itself."""
        from unittest import mock
        runner = jobs.Jobs(self.cfg, library.Library(Path(tempfile.mkdtemp()) / "library.json"))
        checked = threading.Event()   # the job waits here, so it can be looked at while it runs
        with mock.patch.object(runner, "_refresh", lambda *a, **k: checked.wait(10)), \
                mock.patch.object(runner, "_download"):
            self.assertTrue(runner.start("sync", ["booth"], scheduled=True))
            self.assertTrue(runner.state["scheduled"])
            checked.set()
            for _ in range(100):
                if not runner.state["running"] and runner.busy.acquire(blocking=False):
                    runner.busy.release()
                    break
                time.sleep(0.02)
        self.assertAlmostEqual(jobs.last_sync(), time.time(), delta=5)
        self.assertFalse(runner.state["scheduled"])

    def test_settings(self):
        cfg = config.load_config()
        self.assertEqual(config.DEFAULT_CONFIG["auto_sync_hours"], 0, "off unless you turn it on")
        self.assertEqual(server.apply_settings(cfg, {"auto_sync_hours": 12}), {"auto_sync_hours": 12})
        for bad in (5, "24", True, None):
            with self.assertRaises(ValueError):
                server.apply_settings(cfg, {"auto_sync_hours": bad})
        change = server.apply_settings(cfg, {"display": {"text_size": 130, "pause_animations": 1, "reduce_motion": 0}})
        self.assertEqual(change, {"display": {"text_size": 130, "pause_animations": True, "reduce_motion": False}})
        for bad in (99, "130", True):
            with self.assertRaises(ValueError):
                server.apply_settings(cfg, {"display": {"text_size": bad}})
        shown = server.public_settings({**cfg, "display": {"text_size": 7}, "auto_sync_hours": 3})
        self.assertEqual((shown["display"]["text_size"], shown["auto_sync_hours"]), (100, 0), "damaged values read as defaults")
