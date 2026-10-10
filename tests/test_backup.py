"""Backup and restore (hoard/backup.py): what you've set up, in one file, and put back."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertNotIn("2468", text)
        for word in self.phrase.split():
            self.assertNotIn(f'"{word}"', text, "never the recovery words")

    def test_locked_leaves_hidden_out(self):
        doc = self.make(unlocked=False)
        self.assertNotIn("secretthing", json.dumps(doc))
        self.assertEqual(set(doc["marks"]), {"archived", "unarchived", "removed"})

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
            page.get_by_text("Hoard backups").first.wait_for()
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
