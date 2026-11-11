"""Private metadata migration, stable product references, transactions and tamper detection."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from unittest import mock
from pathlib import Path

from tests.isolation import IsolatedTestCase
from hoard.storage import Database, DatabaseIntegrityError, FILES
from hoard.tags import tag_key

KEY = b"test metadata key, never a secret"


class Metadata(IsolatedTestCase):
    def setUp(self):
        on = mock.patch.dict(os.environ, {"HOARD_METADATA": "sqlite"})   # (off unless asked for: OffByDefault)
        on.start()
        self.addCleanup(on.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def open(self):
        db = Database(self.home, KEY)
        self.addCleanup(db.close)
        return db

    def test_every_legacy_shape_is_preserved_and_originals_are_kept(self):
        values = {}
        for name in FILES:
            value = {"unknown_future_field": [name, None, {"text": "日本語"}]}
            values[name] = value
            (self.home / name).write_text(json.dumps(value), "utf-8")
        db = self.open()
        for name, value in values.items():
            self.assertEqual(db.read(name), value)
            self.assertFalse((self.home / name).exists())
            self.assertEqual(json.loads((self.home / (name + ".pre-sqlite-v1")).read_text()), value)
        self.assertEqual(db.connection.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_a_rename_keeps_tags_notes_marks_and_set_membership(self):
        db = self.open()
        old, new = tag_key("booth", "Old Hoodie"), tag_key("booth", "New Hoodie")
        product = {"store": "booth", "id": "1", "name": "Old Hoodie", "creator": "Kitsu"}
        db.write("library.json", {"items": [product]})
        db.write("tags.json", {"items": {old: ["winter"]}, "notes": {old: "My note"}})
        db.write("marks.json", {"hidden": [old]})
        db.write("sets.json", {"sets": [{"id": "a", "items": [old]}]})
        db.write("library.json", {"items": [{**product, "name": "New Hoodie"}]})
        self.assertEqual(db.read("tags.json"), {"items": {new: ["winter"]}, "notes": {new: "My note"}})
        self.assertEqual(db.read("marks.json")["hidden"], [new])
        self.assertEqual(db.read("sets.json")["sets"][0]["items"], [new])
        raw = db.connection.execute("SELECT body FROM documents WHERE name='tags.json'").fetchone()[0]
        self.assertIn("product:booth:1", raw)

    def test_a_changed_store_id_follows_a_unique_name_but_ambiguous_names_do_not(self):
        db = self.open()
        product = {"store": "booth", "id": "1", "name": "Hoodie", "creator": "Kitsu"}
        db.write("library.json", {"items": [product]})
        db.write("library.json", {"items": [{**product, "id": "2"}]})
        self.assertEqual(db.connection.execute("SELECT uid,store_id FROM products").fetchall(), [("booth:1", "2")])
        db.write("library.json", {"items": [{**product, "id": "3"}, {**product, "id": "4"}]})
        self.assertEqual(db.connection.execute("SELECT count(*) FROM products").fetchone()[0], 3)

    def test_live_download_preferences_follow_a_renamed_product(self):
        from hoard import downloader, jobs, storage
        db = storage.database()
        old, new = tag_key("booth", "Old Hoodie"), tag_key("booth", "New Hoodie")
        product = {"store": "booth", "id": "1", "name": "Old Hoodie", "creator": "Kitsu"}
        db.write("library.json", {"items": [product]})
        cfg = {"download_skip": [old], "file_skip": {old: ["mobile.zip"]}}
        db.write("config.json", cfg)
        db.write("library.json", {"items": [{**product, "name": "New Hoodie"}]})
        # The server retains its config object across a refresh; resolving references must not need a restart.
        self.assertEqual(jobs.download_skip(cfg), {new})
        self.assertEqual(downloader.remembered_files(cfg), {new: {"mobile.zip"}})
        self.assertEqual(cfg["download_skip"], [old], "reading must not mutate the caller's preferences")

    def test_failed_import_rolls_back_all_documents_and_identity_changes(self):
        db = self.open()
        db.write("tags.json", {"notes": {"booth:hoodie": "before"}})
        with self.assertRaisesRegex(RuntimeError, "failed halfway"):
            with db.transaction():
                db.write("tags.json", {"notes": {"booth:hoodie": "after"}})
                db.write("konoasset.json", {"brought_in": {"id": "booth:hoodie"}})
                db.write("library.json", {"items": [{"store": "booth", "id": "1", "name": "Hoodie"}]})
                raise RuntimeError("failed halfway")
        self.assertEqual(db.read("tags.json"), {"notes": {"booth:hoodie": "before"}})
        self.assertFalse(db.exists("konoasset.json"))
        self.assertEqual(db.connection.execute("SELECT count(*) FROM products").fetchone()[0], 0)

    def test_a_failed_refresh_restores_the_live_library_and_saved_identity(self):
        from hoard import library, paths, storage
        lib = library.Library(paths.LIBRARY_FILE)
        product = library.item("booth", "1", name="Old Hoodie", creator="Kitsu")
        lib.replace_store("booth", [product])
        db = storage.database()
        save = db.write

        def fail_after_write(name, value):
            save(name, value)
            raise RuntimeError("disk failed")

        with mock.patch.object(db, "write", fail_after_write):
            with self.assertRaisesRegex(RuntimeError, "disk failed"):
                lib.replace_store("booth", [{**product, "name": "New Hoodie"}])
        self.assertEqual(lib.snapshot()[0][0]["name"], "Old Hoodie")
        self.assertEqual(library.Library(paths.LIBRARY_FILE).snapshot()[0][0]["name"], "Old Hoodie")
        self.assertEqual(db.connection.execute("SELECT name_key FROM products").fetchone()[0], "booth:oldhoodie")

    def test_a_caught_inner_failure_rolls_back_only_its_savepoint(self):
        db = self.open()
        with db.transaction():
            db.write("tags.json", {"kept": True})
            try:
                with db.transaction():
                    db.write("tags.json", {"kept": False})
                    raise ValueError("inner failure")
            except ValueError:
                pass
            db.write("routine.json", {"done": True})
        self.assertEqual(db.read("tags.json"), {"kept": True})

    def test_external_changes_are_detected_without_restarting(self):
        db = self.open()
        db.write("tags.json", {"kept": True})
        with sqlite3.connect(db.path) as other:
            other.execute("DELETE FROM documents WHERE name='tags.json'")
        with self.assertRaises(DatabaseIntegrityError):
            db.read("tags.json")
        with self.assertRaises(DatabaseIntegrityError):
            db.write("routine.json", {})

    def test_wrong_key_or_removed_seal_cannot_open_the_database(self):
        db = self.open()
        db.write("tags.json", {})
        with self.assertRaises(DatabaseIntegrityError):
            Database(self.home, b"a different key")
        with sqlite3.connect(db.path) as other:
            other.execute("DELETE FROM metadata WHERE key='seal'")
        with self.assertRaises(DatabaseIntegrityError):
            Database(self.home, KEY)

    def test_failed_migration_leaves_every_original_in_place(self):
        (self.home / "tags.json").write_text('{"tags":{}}')
        (self.home / "sets.json").write_text("not JSON")
        with self.assertRaises(ValueError):
            Database(self.home, KEY)
        self.assertTrue((self.home / "tags.json").is_file())
        self.assertFalse(list(self.home.glob("*.pre-sqlite-v1")))


class OffByDefault(IsolatedTestCase):
    """Until the database has a way back to an older Hoard, and a way to recover a home whose sealing key is lost,
    private metadata stays the JSON files it was: nothing is moved, and no database is made."""

    def test_documents_stay_json_files(self):
        from hoard import config, paths, storage
        from hoard.tags import TagStore
        self.assertNotIn("HOARD_METADATA", os.environ)
        home = paths.data_dir()
        cfg = config.load_config()
        config.save_config({**cfg, "setup_done": True})
        TagStore().change({"action": "create", "name": "avatars"})
        storage.identify_local({"a": {"name": "Rusk", "creator": "Kitsu"}})
        with storage.transaction():
            self.assertEqual(storage.current_references("config.json", {"download_skip": ["booth:rusk"]}),
                             {"download_skip": ["booth:rusk"]})
        self.assertTrue(json.loads((home / "config.json").read_text("utf-8"))["setup_done"])
        self.assertTrue((home / "tags.json").is_file())
        self.assertFalse((home / "metadata.sqlite3").exists(), "no database")
        self.assertEqual(list(home.glob("*.pre-sqlite-v1")), [], "nothing set aside")
        self.assertFalse(storage.managed(home / "config.json"))
        with mock.patch.dict(os.environ, {"HOARD_METADATA": "sqlite"}):
            self.assertTrue(storage.managed(home / "config.json"))

