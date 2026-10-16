"""Backup and restore (hoard/backup.py): what you've set up, in one file, and put back."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import backup, config, library, server
from hoard.marks import MarkStore
from hoard.sets import SetStore
from hoard.tags import TagStore, tag_key

RUSK = tag_key("Booth", "Rusk")


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        home = str(self.tmp / "home")
        self.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(self.tmp / "data"), "HOME": home, "USERPROFILE": home})
        self.env.start()
        self.addCleanup(self.env.stop)
        (self.tmp / "home" / "Documents").mkdir(parents=True)
        docs = mock.patch.object(backup, "documents_dir", return_value=self.tmp / "home" / "Documents")   # Windows asks the system
        docs.start()
        self.addCleanup(docs.stop)
        self.root = self.tmp / "Hoard downloads"
        self.root.mkdir()
        self.cfg = {**config.load_config(), "root": str(self.root), "download_retries": 3}
        self.lib = library.Library(self.tmp / "data" / "library.json")
        self.lib.replace_store("booth", [library.item("booth", "1", name="Rusk", creator="Kitsu",
                                                     url="https://booth.pm/ja/items/1",
                                                     download_url="https://booth.pm/downloadables/99",
                                                     files=[{"name": "rusk.zip", "url": "https://booth.pm/downloadables/99"}])])
        TagStore().change({"action": "create", "name": "avatars"})
        SetStore().change({"action": "create", "name": "Rusk, winter", "items": [RUSK]})
        MarkStore().change("archived", [RUSK], True)
        self.phrase = MarkStore().set_pin("2468")
        MarkStore().change("hidden", [tag_key("Booth", "Secret Thing")], True)

    def make(self, unlocked: bool) -> dict:
        return backup.make(self.cfg, server.public_settings(self.cfg), self.lib, unlocked)

    def test_what_goes_in(self):
        doc = self.make(unlocked=True)
        text = json.dumps(doc)
        self.assertEqual(doc["settings"]["download_retries"], 3)
        self.assertEqual(doc["settings"]["root"], str(self.root))
        self.assertIn("avatars", doc["tags"]["tags"])
        self.assertEqual(doc["sets"][0]["items"], [RUSK])
        self.assertEqual(doc["marks"]["archived"], [RUSK])
        self.assertIn("secretthing", text, "unlocked: hidden items go in")
        self.assertIn("pin", doc["marks"])
        self.assertNotIn("downloadables", text, "never a link that downloads what you bought")
        # only as their slow hashes, whose random hex held "2468" by chance once: look everywhere else
        outside = text
        for field in ("pin", "recovery"):
            for part in ("salt", "hash"):
                outside = outside.replace(doc["marks"][field][part], "")
        self.assertNotIn("2468", outside)
        self.assertNotIn(self.phrase, text, "never the recovery words")

        def values(v):   # every value the marks hold (a word can be part of anything else too: "midnight" is a theme)
            if isinstance(v, dict):
                return [x for item in v.values() for x in values(item)]
            return [x for item in v for x in values(item)] if isinstance(v, list) else [v]
        for word in self.phrase.split():
            self.assertNotIn(word, values(doc["marks"]), "only their slow hash")

    def test_recovery_words_that_are_other_names_too(self):
        """A recovery word can be a theme's name ("midnight", "frost"): the settings name it, the marks don't."""
        from hoard import marks
        MarkStore().path.unlink()   # as setUp leaves things, with a phrase made of these words
        words = iter(["midnight", "frost", "abandon", "ability", "able", "about"])
        with mock.patch.object(marks.secrets, "choice", lambda seq: next(words)):
            self.phrase = MarkStore().set_pin("2468")
        self.assertEqual(self.phrase, "midnight frost abandon ability able about")
        MarkStore().change("archived", [RUSK], True)
        MarkStore().change("hidden", [tag_key("Booth", "Secret Thing")], True)
        self.assertIn('"midnight"', json.dumps(self.make(unlocked=True)), "a theme's name, in the settings")
        self.test_what_goes_in()

    def test_locked_leaves_hidden_out(self):
        doc = self.make(unlocked=False)
        self.assertNotIn("secretthing", json.dumps(doc))
        self.assertEqual(set(doc["marks"]), {"archived", "unarchived", "removed"})

    def hide_one_in_use(self) -> str:
        """A hidden product as one really is: in the library, archived, tagged and in a set (setUp's isn't any)."""
        secret = tag_key("Booth", "Secret Thing")
        self.lib.replace_store("booth", [*self.lib.snapshot()[0], library.item(
            "booth", "2", name="Secret Thing", creator="Shy Maker", url="https://booth.pm/ja/items/2")])
        MarkStore().change("archived", [secret], True)
        TagStore().change({"action": "assign", "keys": [secret], "add": ["avatars"]})
        set_id = SetStore().load()["sets"][0]["id"]
        SetStore().change({"action": "add", "id": set_id, "items": [secret]},   # (a set remembers what each product is)
                          details=lambda k: {"store": "booth", "name": "Secret Thing", "creator": "Shy Maker",
                                             "url": "https://booth.pm/ja/items/2"})
        return secret

    def test_locked_names_them_nowhere(self):
        """It left them out of the marks, but listed them in the library list (name, creator, link), the archive,
        tags and sets: a backup made while locked named every hidden product."""
        secret = self.hide_one_in_use()
        text = json.dumps(self.make(unlocked=False))
        for said in ("Secret Thing", "Shy Maker", "booth.pm/ja/items/2", secret):
            self.assertNotIn(said, text)
        self.assertEqual(self.make(unlocked=False)["library"]["stores"]["booth"].get("count", 1), 1, "nor counted")
        self.assertIn("Secret Thing", json.dumps(self.make(unlocked=True)), "unlocked: they go in")

    def test_short_links_stay_on_this_computer(self):
        """A set's short link (its key, and the token that deletes it) is never in a backup; a restore keeps this
        computer's."""
        import time
        sid = SetStore().load()["sets"][0]["id"]
        short = {"id": "abcDEF0123", "key": "k" * 22, "token": "t" * 43, "expires": int(time.time()) + 3600,
                 "made": "0123456789abcdef"}
        SetStore().set_short(sid, short)
        doc = json.loads(json.dumps(self.make(unlocked=True)))
        text = json.dumps(doc)
        for part in ("short", short["key"], short["token"], short["id"]):
            self.assertNotIn(part, text)
        doc["sets"][0]["short"] = {**short, "id": "zzzzzzzzzz"}   # (one put in by hand isn't taken either)
        dropped = []
        backup.restore(doc, self.cfg, self.lib, server.apply_settings, lambda p: None, dropped.append)
        self.assertEqual(SetStore().load()["sets"][0]["short"], short)
        self.assertEqual(dropped, [])
        # a set the backup doesn't have goes, and its short link with it: given back, to be deleted
        made = SetStore().change({"action": "create", "name": "Newer"})["made"]
        SetStore().set_short(made, {**short, "id": "newerABCDE"})
        backup.restore(doc, self.cfg, self.lib, server.apply_settings, lambda p: None, dropped.append)
        self.assertEqual([s["name"] for s in SetStore().load()["sets"]], ["Rusk, winter"])
        self.assertEqual(dropped, [{**short, "id": "newerABCDE"}])

    def test_a_locked_backup_restored_keeps_the_hidden_ones_as_they_are(self):
        secret = self.hide_one_in_use()
        doc = json.loads(json.dumps(self.make(unlocked=False)))
        backup.restore(doc, self.cfg, self.lib, server.apply_settings, lambda p: None)
        self.assertEqual(MarkStore().keys("hidden"), {secret})
        self.assertIn(secret, MarkStore().keys("archived"), "still archived")
        self.assertEqual(TagStore().load()["items"][secret], ["avatars"], "still tagged")
        self.assertIn(secret, SetStore().load()["sets"][0]["items"], "still in its set")
        self.assertEqual(SetStore().load()["sets"][0]["products"][secret]["creator"], "Shy Maker", "and what it is")
        self.assertIn(RUSK, SetStore().load()["sets"][0]["items"])

    def test_never_sign_ins_or_keys(self):
        text = json.dumps(self.make(unlocked=True))
        for word in ("sign-ins", "integrity", "api_key", "cookie", "password"):
            self.assertNotIn(word, text.lower(), word)

    def test_saved_without_writing_over_another(self):
        doc = self.make(unlocked=False)
        with mock.patch.object(backup.time, "strftime", return_value="2026-10-10 1200"):
            a, b = backup.save(doc), backup.save(doc)
        self.assertNotEqual(a, b)
        self.assertEqual(a.parent, self.tmp / "home" / "Documents" / "Hoard backups")
        self.assertEqual(backup.read(a.read_bytes())["settings"]["download_retries"], 3)

    def test_restore_on_a_new_computer(self):
        doc = json.loads(json.dumps(self.make(unlocked=True)))
        elsewhere = self.tmp / "new"
        with mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(elsewhere)}):
            cfg = config.load_config()
            lib = library.Library(elsewhere / "library.json")
            added = []
            done = backup.restore(doc, cfg, lib, server.apply_settings, added.append)
            self.assertEqual(cfg["download_retries"], 3)
            self.assertEqual(Path(cfg["root"]), self.root, "the downloads folder is on this computer: taken")
            self.assertIn("avatars", TagStore().load()["tags"])
            self.assertEqual(SetStore().load()["sets"][0]["name"], "Rusk, winter")
            marks = MarkStore().load()
            self.assertEqual(marks["archived"], {RUSK})
            self.assertEqual(marks["hidden"], {tag_key("Booth", "Secret Thing")})
            MarkStore().check_pin("2468")   # the same PIN still unlocks them
            self.assertEqual(done["items"], 1)
            [item] = lib.snapshot()[0]
            self.assertEqual((item["name"], item["download_url"], item["files"]), ("Rusk", None, []),
                             "listed again, its download links read from the store next refresh")

    def test_a_folder_that_isnt_here_is_kept_as_it_is(self):
        doc = self.make(unlocked=False)
        doc["settings"]["root"] = str(self.tmp / "gone" / "Hoard")
        doc["settings"]["download_retries"] = 99
        cfg = config.load_config()
        before = cfg.get("root")
        done = backup.restore(doc, cfg, self.lib, server.apply_settings, lambda p: None)
        self.assertEqual(cfg.get("root"), before)
        self.assertEqual(cfg["download_retries"], 2, "a setting this Hoard can't use isn't taken")
        self.assertEqual(len(done["skipped"]), 2, done["skipped"])

    def test_a_folder_hoard_shouldnt_download_into_isnt_taken(self):
        (self.tmp / "data").mkdir(exist_ok=True)
        for folder in (Path(self.tmp.anchor), self.tmp / "home", self.tmp / "data", Path(__file__).parent, "rel/dir"):
            with self.subTest(folder=folder):
                doc = self.make(unlocked=False)
                doc["settings"]["root"] = str(folder)
                cfg = {**config.load_config(), "root": str(self.root)}
                done = backup.restore(doc, cfg, self.lib, server.apply_settings, lambda p: None)
                if folder == Path(__file__).parent:
                    self.assertEqual(Path(cfg["root"]), folder, "an ordinary folder that's here is taken")
                    continue
                self.assertEqual(cfg["root"], str(self.root))
                self.assertTrue(any("downloads folder" in s for s in done["skipped"]), done["skipped"])

    def test_a_store_already_read_here_keeps_its_list(self):
        doc = self.make(unlocked=False)
        doc["library"]["items"][0]["name"] = "Old name"
        backup.restore(doc, self.cfg, self.lib, server.apply_settings, lambda p: None)
        self.assertEqual(self.lib.snapshot()[0][0]["name"], "Rusk")

    def test_not_a_backup(self):
        for data in (b"", b"{}", b"[1]", b'{"format": "hoard-backup", "version": 99}', b"\xff\xfe", b"{bad"):
            with self.subTest(data=data), self.assertRaises(backup.BackupError):
                backup.read(data)

    def test_an_edited_pin_hash_isnt_taken(self):
        doc = self.make(unlocked=True)
        doc["marks"]["pin"] = {**doc["marks"]["pin"], "n": 2 ** 30}   # costly enough to stall Hoard
        MarkStore().set_pin("1357", "2468")
        backup.restore(doc, self.cfg, self.lib, server.apply_settings, lambda p: None)
        MarkStore().check_pin("1357")   # kept as it was


try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Page(unittest.TestCase):
    def test_make_and_restore_from_settings(self):
        import threading
        from playwright.sync_api import sync_playwright
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(tmp / "data"), "HOME": str(tmp / "home")})
        env.start()
        self.addCleanup(env.stop)
        (tmp / "home" / "Documents").mkdir(parents=True)
        docs = mock.patch.object(backup, "documents_dir", return_value=tmp / "home" / "Documents")
        docs.start()
        self.addCleanup(docs.stop)
        (tmp / "dl").mkdir()
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(tmp / "dl"), "setup_done": True}, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        TagStore().change({"action": "create", "name": "avatars"})
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.click("nav.apptabs a[href='/downloads']")
            page.click("#settingsBtn")
            page.click("#backupMake")
            # "Show in folder" comes once the file is saved: the hint already names Documents › Hoard backups, so
            # waiting for that text went on before the backup was written (seen on Windows)
            page.locator("#backupShow").wait_for()
            [made] = (tmp / "home" / "Documents" / "Hoard backups").glob("*.json")
            TagStore().change({"action": "delete", "name": "avatars"})
            page.set_input_files("#backupFile", str(made))
            page.locator("dialog[open]").get_by_text("It has 1 tag, 0 sets and").wait_for()
            page.locator("dialog[open] button", has_text="Restore").click()
            page.wait_for_function("() => document.readyState === 'complete' && !document.querySelector('dialog[open]')")
            page.wait_for_timeout(2500)
            browser.close()
        self.assertIn("avatars", TagStore().load()["tags"])
        self.assertEqual(len(list((tmp / "home" / "Documents" / "Hoard backups").glob("*before restoring*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
