"""Private metadata migration, stable product references, transactions and tamper detection."""
from __future__ import annotations

import json
from contextlib import closing
import os
import sqlite3
import tempfile
from unittest import mock
from pathlib import Path

from tests.isolation import IsolatedTestCase
from hoard.storage import Database, DatabaseIntegrityError, FILES
# Raw name fixtures must not consult another test's live default database.
from hoard.tags import legacy_tag_key as tag_key

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
            self.assertEqual(json.loads((self.home / name).read_text("utf-8")), value)
            self.assertEqual(json.loads((self.home / (name + ".pre-sqlite-v1")).read_text("utf-8")), value)
        self.assertEqual(db.connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_mirrors_publish_only_committed_state_and_deletes_keep_migration_backups(self):
        path = self.home / "config.json"
        path.write_text('{"before": true}', encoding="utf-8")
        db = self.open()
        before = path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with db.transaction():
                db.write("config.json", {"after": True})
                self.assertEqual(path.read_bytes(), before)
                raise RuntimeError("rollback")
        self.assertEqual(path.read_bytes(), before)
        with db.transaction():
            db.write("config.json", {"committed": "日本語"})
            with self.assertRaises(ValueError):
                with db.transaction():
                    db.write("routine.json", {"not_committed": True})
                    raise ValueError()
        self.assertEqual(json.loads(path.read_text("utf-8")), {"committed": "日本語"})
        self.assertFalse((self.home / "routine.json").exists())
        db.delete("config.json")
        self.assertFalse(path.exists())
        self.assertEqual(json.loads((self.home / "config.json.pre-sqlite-v1").read_text("utf-8")), {"before": True})

    def test_old_release_edits_and_new_documents_are_imported_on_reopen(self):
        db = self.open()
        db.write("config.json", {"before": True})
        db.write("tags.json", {"notes": {"booth:hoodie": "keep"}})
        db.close()
        (self.home / "config.json").write_text('{"legacy_edit": true}', encoding="utf-8")
        (self.home / "routine.json").write_text('{"legacy_new": true}', encoding="utf-8")
        reopened = self.open()
        self.assertEqual(reopened.read("config.json"), {"legacy_edit": True})
        self.assertEqual(reopened.read("routine.json"), {"legacy_new": True})
        self.assertEqual(reopened.read("tags.json"), {"notes": {"booth:hoodie": "keep"}})

    def test_empty_database_imports_first_document_from_old_release(self):
        self.open().close()
        (self.home / "config.json").write_text('{"legacy_new": true}', encoding="utf-8")
        self.assertEqual(self.open().read("config.json"), {"legacy_new": True})

    def test_missing_mirror_is_restored_but_malformed_edit_is_preserved(self):
        db = self.open()
        db.write("config.json", {"good": True})
        db.write("routine.json", {"good": "also"})
        db.close()
        (self.home / "routine.json").unlink()
        (self.home / "config.json").write_bytes(b"not valid JSON")
        with self.assertLogs("hoard.storage", level="WARNING"):
            reopened = self.open()
        self.assertEqual(reopened.read("config.json"), {"good": True})
        self.assertEqual(json.loads((self.home / "routine.json").read_text("utf-8")), {"good": "also"})
        conflicts = list(self.home.glob("config.json.legacy-conflict-*"))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].read_bytes(), b"not valid JSON")

    def test_failed_mirror_write_keeps_committed_database_and_retries_on_open(self):
        db = self.open()
        db.write("routine.json", {"before": True})
        with mock.patch("hoard.safety.write_file_safely", side_effect=OSError("disk unavailable")):
            with self.assertLogs("hoard.storage", level="ERROR"):
                db.write("routine.json", {"after": True})
        self.assertEqual(db.read("routine.json"), {"after": True})
        self.assertEqual(json.loads((self.home / "routine.json").read_text("utf-8")), {"before": True})
        self.assertIn("routine.json", db._metadata_json("mirror_pending", []))
        db.close()
        reopened = self.open()
        self.assertEqual(json.loads((self.home / "routine.json").read_text("utf-8")), {"after": True})
        self.assertEqual(reopened._metadata_json("mirror_pending", []), [])

    def test_old_release_edit_during_pending_mirror_is_retained_as_conflict(self):
        db = self.open()
        db.write("routine.json", {"before": True})
        with mock.patch("hoard.safety.write_file_safely", side_effect=OSError("disk unavailable")):
            with self.assertLogs("hoard.storage", level="ERROR"):
                db.write("routine.json", {"committed": True})
        db.close()
        (self.home / "routine.json").write_text('{"legacy_edit": true}', encoding="utf-8")
        with self.assertLogs("hoard.storage", level="WARNING"):
            reopened = self.open()
        self.assertEqual(reopened.read("routine.json"), {"committed": True})
        conflicts = list(self.home.glob("routine.json.legacy-conflict-*"))
        self.assertEqual(json.loads(conflicts[0].read_text("utf-8")), {"legacy_edit": True})

    def test_mirrors_keep_untrusted_library_quarantined_for_old_readers(self):
        from hoard import safety
        db = self.open()
        db.close()
        foreign = {"items": [{"store": "booth", "id": "1", "name": "Hoodie", "url": "https://example.com"}],
                   "integrity": {"key_id": "another-install", "mac": "bad"}}
        path = self.home / "library.json"
        path.write_text(json.dumps(foreign), encoding="utf-8")
        reopened = self.open()
        self.assertEqual(reopened.trust("library.json"), "foreign")
        mirror = json.loads(path.read_text("utf-8"))
        with mock.patch.object(safety, "integrity_key", return_value=KEY):
            self.assertEqual(safety.check_seal(mirror, path), "foreign")
            from hoard.library import Library
            self.assertIsNone(Library(path).data["items"][0]["url"])
        self.assertEqual(reopened.connection.execute("SELECT count(*) FROM products").fetchone()[0], 0)

    def test_settings_and_library_round_trip_through_json_mode(self):
        from hoard import config, library, paths, storage
        path = paths.data_dir() / "library.json"
        cfg = config.load_config()
        config.save_config({**cfg, "setup_done": True, "new_days": 11})
        current = library.Library(path)
        current.data = {"items": [library.item("booth", "1", name="Hoodie", url="https://booth.pm/en/items/1")],
                        "stores": {"booth": {"count": 1}}}
        current.save()
        storage.close_all()
        with mock.patch.dict(os.environ, {"HOARD_METADATA": ""}):
            old_cfg = config.load_config()
            self.assertTrue(old_cfg["setup_done"])
            self.assertEqual(old_cfg["new_days"], 11)
            old_library = library.Library(path)
            self.assertEqual(old_library.data["items"][0]["url"], "https://booth.pm/en/items/1")
            config.save_config({**old_cfg, "new_days": 23})
            old_library.data["items"][0]["name"] = "Renamed Hoodie"
            old_library.save()
        self.assertEqual(config.load_config()["new_days"], 23)
        updated = library.Library(path)
        self.assertEqual(updated.data["items"][0]["name"], "Renamed Hoodie")
        self.assertEqual(updated.data["items"][0]["url"], "https://booth.pm/en/items/1")

    def test_directory_in_place_of_mirror_is_preserved_without_losing_database(self):
        db = self.open()
        db.write("routine.json", {"good": True})
        db.close()
        path = self.home / "routine.json"
        path.unlink()
        path.mkdir()
        (path / "keep.txt").write_text("keep", encoding="utf-8")
        with self.assertLogs("hoard.storage", level="WARNING"):
            reopened = self.open()
        self.assertEqual(reopened.read("routine.json"), {"good": True})
        aside = next(self.home.glob("routine.json.legacy-conflict-*"))
        self.assertEqual((aside / "keep.txt").read_text("utf-8"), "keep")
        self.assertEqual(json.loads(path.read_text("utf-8")), {"good": True})

    def test_partial_mirror_batch_retries_without_importing_partial_snapshots(self):
        from hoard import safety
        db = self.open()
        db.write("config.json", {"before": True})
        db.write("routine.json", {"before": True})
        original = safety.write_file_safely
        def fail_second(path, *args, **kwargs):
            if path.name == "routine.json":
                raise OSError("second mirror unavailable")
            return original(path, *args, **kwargs)
        with mock.patch.object(safety, "write_file_safely", side_effect=fail_second):
            with self.assertLogs("hoard.storage", level="ERROR"):
                with db.transaction():
                    db.write("config.json", {"after": True})
                    db.write("routine.json", {"after": True})
        self.assertEqual(json.loads((self.home / "config.json").read_text("utf-8")), {"after": True})
        self.assertEqual(json.loads((self.home / "routine.json").read_text("utf-8")), {"before": True})
        db.close()
        reopened = self.open()
        for name in ("config.json", "routine.json"):
            self.assertEqual(reopened.read(name), {"after": True})
            self.assertEqual(json.loads((self.home / name).read_text("utf-8")), {"after": True})
        self.assertEqual(list(self.home.glob("*.legacy-conflict-*")), [])

    def test_sealed_mirror_is_valid_after_name_projection(self):
        from hoard import safety
        db = self.open()
        product = {"store": "booth", "id": "1", "name": "Old Hoodie"}
        db.write("library.json", {"items": [product]})
        with mock.patch.object(safety, "integrity_key", return_value=KEY):
            db.write("tags.json", safety.seal({"notes": {"booth:oldhoodie": "keep"}}))
            db.write("library.json", {"items": [{**product, "name": "New Hoodie"}]})
            mirror = json.loads((self.home / "tags.json").read_text("utf-8"))
            self.assertEqual(safety.check_seal(mirror), "sealed")
        self.assertEqual(mirror["notes"], {"booth:newhoodie": "keep"})

    def test_numbered_products_keep_distinct_annotations_through_migration_and_renames(self):
        from hoard.tags import legacy_tag_key, TAG_KEY_RX
        products = [{"store": "booth", "id": str(n), "name": f"Hair Pack {n}", "creator": "Kitsu"} for n in (1, 2)]
        (self.home / "library.json").write_text(json.dumps({"items": products}), encoding="utf-8")
        (self.home / "tags.json").write_text(json.dumps({"notes": {"booth:hairpack": "ambiguous legacy note"}}), encoding="utf-8")
        db = self.open()
        keys = [db.product_reference("booth", p["name"], p["id"], legacy_tag_key("booth", p["name"])) for p in products]
        self.assertNotEqual(*keys)
        self.assertTrue(all(TAG_KEY_RX.fullmatch(k) for k in keys))
        self.assertEqual(db.read("tags.json")["notes"], {"booth:hairpack": "ambiguous legacy note"})
        notes = dict(zip(keys, ("first", "second")))
        db.write("tags.json", {"notes": notes, "items": dict(zip(keys, (["one"], ["two"])))})
        db.write("marks.json", {"hidden": [keys[0]]})
        db.write("sets.json", {"sets": [{"id": "a", "items": keys}]})
        db.write("config.json", {"file_skip": dict(zip(keys, (["a.zip"], ["b.zip"])))})
        db.write("library.json", {"items": [{**p, "name": f"Renamed Hair {p['id']}"} for p in products]})
        self.assertEqual(db.read("tags.json")["notes"], notes)
        self.assertEqual(db.read("marks.json")["hidden"], [keys[0]])
        self.assertEqual(db.read("sets.json")["sets"][0]["items"], keys)
        self.assertEqual(set(db.read("config.json")["file_skip"]), set(keys))
        self.assertEqual(json.loads((self.home / "tags.json").read_text("utf-8"))["notes"], notes)
        db.close()
        reopened = self.open()
        self.assertEqual(reopened.read("tags.json")["notes"], notes)
        self.assertEqual(reopened.connection.execute("SELECT count(*) FROM products").fetchone()[0], 2)

    def test_live_download_preferences_follow_product_when_a_collision_appears(self):
        db = self.open()
        product = {"store": "booth", "id": "1", "name": "Hair Pack 1"}
        db.write("library.json", {"items": [product]})
        db.write("config.json", {"download_skip": ["booth:hairpack"], "file_skip": {"booth:hairpack": ["mobile.zip"]}})
        live = db.read("config.json")
        db.write("library.json", {"items": [product, {**product, "id": "2", "name": "Hair Pack 2"}]})
        current = db.current_references("config.json", live)
        self.assertEqual(current, db.read("config.json"))
        self.assertNotEqual(current["download_skip"], ["booth:hairpack"])
        self.assertEqual(live["download_skip"], ["booth:hairpack"], "don't mutate the caller")

    def test_rolled_back_identity_does_not_bind_live_preferences(self):
        db = self.open()
        with self.assertRaises(RuntimeError):
            with db.transaction():
                db.write("library.json", {"items": [{"store": "booth", "id": "1", "name": "Hair Pack 1"}]})
                db.write("config.json", {"download_skip": ["booth:hairpack"]})
                raise RuntimeError()
        self.assertEqual(db.current_references("config.json", {"download_skip": ["booth:hairpack"]}),
                         {"download_skip": ["booth:hairpack"]})

    def test_product_name_cannot_steal_an_existing_public_identity_key(self):
        from hoard.tags import legacy_tag_key
        db = self.open()
        products = [{"store": "booth", "id": str(n), "name": f"Hair Pack {n}"} for n in (1, 2)]
        db.write("library.json", {"items": products})
        first = db.product_reference("booth", "Hair Pack 1", "1", "booth:hairpack")
        product = {"store": "booth", "id": "3", "name": first.split(":", 1)[1]}
        db.write("library.json", {"items": [*products, product]})
        third = db.product_reference("booth", product["name"], "3", legacy_tag_key("booth", product["name"]))
        self.assertNotEqual(first, third)
        db.write("tags.json", {"notes": {first: "first", third: "third"}})
        self.assertEqual(db.read("tags.json")["notes"], {first: "first", third: "third"})

    def test_public_keys_do_not_steal_a_previous_name_alias(self):
        import hashlib
        db = self.open()
        reserved = "booth:x" + hashlib.sha256(b"booth:1").hexdigest()
        predecessor = {"store": "booth", "id": "3", "name": reserved.split(":", 1)[1]}
        db.write("library.json", {"items": [predecessor]})
        db.write("tags.json", {"notes": {reserved: "third product"}})
        products = [{"store": "booth", "id": str(n), "name": f"Hair Pack {n}"} for n in (1, 2)]
        db.write("library.json", {"items": [{**predecessor, "name": "Other Name"}, *products]})
        first = db.product_reference("booth", "Hair Pack 1", "1", "booth:hairpack")
        self.assertNotEqual(first, reserved)
        db.write("tags.json", {"notes": {reserved: "still the third product"}})
        self.assertEqual(db.read("tags.json")["notes"], {"booth:othername": "still the third product"})

    def test_identically_named_products_render_distinct_keys_by_store_id(self):
        from hoard import library, storage
        from hoard.tags import TagStore, tag_key
        db = self.open()
        products = [library.item("booth", str(n), name="Same Hoodie", creator="Kitsu") for n in range(20)]
        db.write("library.json", {"items": products})
        with mock.patch.object(storage, "database", return_value=db):
            keys = [tag_key("booth", "Same Hoodie", p["id"]) for p in products]
            self.assertEqual(len(set(keys)), 20)
            notes = [f"note {n}" for n in range(20)]
            tagdata = {**TagStore.empty(), "notes": dict(zip(keys, notes))}
            with mock.patch.object(db, "_reading", wraps=db._reading) as reads:
                rendered = library.enrich(products, {}, tagdata)
                self.assertLessEqual(reads.call_count, 3, "identity/picture snapshots, no per-item SQL")
        self.assertEqual([p["tag_key"] for p in rendered], keys)
        self.assertEqual([p["your_note"] for p in rendered], notes)

    def test_identical_downloads_keep_notes_and_delete_only_the_selected_store_id(self):
        from hoard import config, downloader, downloads, library, storage
        from hoard.tags import TagStore, tag_key
        from types import SimpleNamespace
        db = self.open()
        products = [library.item("booth", str(n), name="Same Hoodie", creator="Kitsu") for n in (1, 2)]
        db.write("library.json", {"items": products})
        root = self.home / "downloads"
        manifest = downloader.Manifest(root / "Booth")
        paths = []
        for product in products:
            rec = manifest.record(product["id"], "Kitsu", "Same Hoodie")
            target = root / "Booth" / rec["folder"] / "asset.zip"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"asset")
            paths.append(target)
            rec["files"] = {"asset": {"path": "asset.zip"}}
        with mock.patch.object(storage, "database", return_value=db):
            manifest.save()
            keys = [tag_key("booth", p["name"], p["id"]) for p in products]
            db.write("tags.json", {**TagStore.empty(), "notes": dict(zip(keys, ("first", "second")))})
            cfg = {**config.load_config(), "root": str(root)}
            catalog = downloader.collect_catalog(cfg, root)[0]
            self.assertEqual({p["your_note"] for p in catalog}, {"first", "second"})
            index = downloads.build_index(root, catalog)
            self.assertEqual({a["tag_key"] for a in index["assets"]}, set(keys))
            args = SimpleNamespace(only=None, keys={keys[0]})
            self.assertFalse(downloader.skip_product(args, "booth", "Same Hoodie", "Kitsu", "1"))
            self.assertTrue(downloader.skip_product(args, "booth", "Same Hoodie", "Kitsu", "2"))
            downloader.delete_downloaded_files(cfg, root, {keys[0]})
        self.assertFalse(paths[0].exists())
        self.assertTrue(paths[1].exists())

    def test_existing_stable_references_are_not_collapsed_on_projection_upgrade(self):
        from hoard.tags import legacy_tag_key
        db = self.open()
        products = [{"store": "booth", "id": str(n), "name": f"Hair Pack {n}"} for n in (1, 2)]
        db.write("library.json", {"items": products})
        db.write("tags.json", {"notes": {"product:booth:1": "first", "product:booth:2": "second"}})
        with db.transaction():
            db.connection.execute("DELETE FROM aliases WHERE alias LIKE 'public:%' OR alias LIKE 'name:booth:x%'")
            db.connection.execute("DELETE FROM metadata WHERE key='identity_projection'")
            db._identity_dirty = True
        db.close()
        reopened = self.open()
        notes = reopened.read("tags.json")["notes"]
        self.assertEqual(len(notes), 2)
        self.assertEqual(set(notes.values()), {"first", "second"})
        keys = [reopened.product_reference("booth", p["name"], p["id"], legacy_tag_key("booth", p["name"])) for p in products]
        self.assertEqual(set(notes), set(keys))

    def test_recovery_preserves_original_and_disables_automatic_work(self):
        import io
        from contextlib import redirect_stdout
        db = self.open()
        db.write("library.json", {"items": [{"store": "booth", "id": "1", "name": "Hoodie", "url": "https://booth.pm/en/items/1"}]})
        db.write("config.json", {"setup_done": True, "auto_sync_hours": 1, "routine_hours": 1})
        db.write("job-queue.json", {"main": [{"task": "download", "stores": ["booth"]}]})
        db.write("vpm-projects.json", {"git_trusted": {"project": "fingerprint"}, "projects": {"project": {"auto_update": "both", "auto_pending": {"phase": "apply"}}}})
        db.close()
        new_key = b"new install key, entirely different"
        with redirect_stdout(io.StringIO()) as notice:
            recovered = Database(self.home, new_key, recover=True)
        self.addCleanup(recovered.close)
        self.assertIn("refresh", notice.getvalue())
        self.assertEqual(recovered.trust("library.json"), "changed")
        self.assertTrue(recovered.read("config.json")["setup_done"])
        self.assertEqual(recovered.read("config.json")["auto_sync_hours"], 0)
        self.assertEqual(recovered.read("job-queue.json"), {})
        state = recovered.read("vpm-projects.json")
        self.assertEqual(state["git_trusted"], {})
        self.assertEqual(state["projects"]["project"]["auto_update"], "off")
        self.assertIsNone(state["projects"]["project"]["auto_pending"])
        backup = next(self.home.glob("metadata.before-recovery-*.sqlite3"))
        with closing(sqlite3.connect(backup)) as original:
            body = original.execute("SELECT body FROM documents WHERE name='config.json'").fetchone()[0]
            self.assertEqual(json.loads(body)["auto_sync_hours"], 1)
            self.assertEqual(original.execute("SELECT count(*) FROM products").fetchone()[0], 1)
        recovered.close()
        again = Database(self.home, new_key)
        self.addCleanup(again.close)
        self.assertEqual(again.trust("library.json"), "changed")
        self.assertEqual(len(list(self.home.glob("metadata.before-recovery-*.sqlite3"))), 1)

    def test_missing_seal_can_recover_but_unexpected_schema_cannot(self):
        db = self.open()
        db.write("tags.json", {"kept": True})
        db.close()
        with closing(sqlite3.connect(self.home / "metadata.sqlite3")) as other, other:
            other.execute("DELETE FROM metadata WHERE key='seal'")
        recovered = Database(self.home, KEY, recover=True)
        self.addCleanup(recovered.close)
        self.assertEqual(recovered.read("tags.json"), {"kept": True})
        recovered.close()
        with closing(sqlite3.connect(self.home / "metadata.sqlite3")) as other, other:
            other.execute("CREATE TRIGGER unexpected AFTER UPDATE ON documents BEGIN DELETE FROM aliases; END")
        with self.assertRaisesRegex(DatabaseIntegrityError, "unexpected metadata schema"):
            Database(self.home, b"foreign", recover=True)
        self.assertEqual(len(list(self.home.glob("metadata.before-recovery-*.sqlite3"))), 1)

    def test_foreign_v1_can_recover_before_upgrading_seals(self):
        class Legacy(Database):
            def _migrate_v2(self):
                pass
        db = Legacy(self.home, KEY)
        db.write("tags.json", {"kept": True})
        db.close()
        recovered = Database(self.home, b"foreign", recover=True)
        self.addCleanup(recovered.close)
        self.assertEqual(recovered.connection.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(recovered.read("tags.json"), {"kept": True})
        self.assertEqual(recovered.trust("tags.json"), "changed")

    def test_injected_trigger_is_rejected_even_when_logical_seals_still_match(self):
        db = self.open()
        db.write("tags.json", {"kept": True})
        db.close()
        with closing(sqlite3.connect(self.home / "metadata.sqlite3")) as other, other:
            other.execute("CREATE TRIGGER unexpected AFTER UPDATE ON documents BEGIN DELETE FROM aliases; END")
        with self.assertRaisesRegex(DatabaseIntegrityError, "unexpected metadata schema"):
            Database(self.home, KEY, recover=True)
        self.assertEqual(list(self.home.glob("metadata.before-recovery-*.sqlite3")), [])

    def test_failed_recovery_backup_leaves_original_data_unchanged(self):
        db = self.open()
        db.write("tags.json", {"kept": True})
        db.close()
        before = (self.home / "metadata.sqlite3").read_bytes()
        with mock.patch("hoard.storage_recovery.tempfile.mkstemp", side_effect=OSError("backup unavailable")):
            with self.assertRaises(OSError):
                Database(self.home, b"foreign", recover=True)
        self.assertEqual((self.home / "metadata.sqlite3").read_bytes(), before)
        self.assertEqual(self.open().read("tags.json"), {"kept": True})

    def test_a_rename_keeps_tags_notes_marks_and_set_membership(self):
        db = self.open()
        old, new = tag_key("booth", "Old Hoodie"), tag_key("booth", "New Hoodie")
        product = {"store": "booth", "id": "1", "name": "Old Hoodie", "creator": "Kitsu"}
        db.write("library.json", {"items": [product]})
        db.write("tags.json", {"items": {old: ["winter"]}, "notes": {old: "My note"}})
        db.write("marks.json", {"hidden": [old]})
        db.write("sets.json", {"sets": [{"id": "a", "items": [old], "marks": {"photo.png": [[old, 0.25, 0.5]]}}]})
        db.write("library.json", {"items": [{**product, "name": "New Hoodie"}]})
        self.assertEqual(db.read("tags.json"), {"items": {new: ["winter"]}, "notes": {new: "My note"}})
        self.assertEqual(db.read("marks.json")["hidden"], [new])
        self.assertEqual(db.read("sets.json")["sets"][0]["items"], [new])
        self.assertEqual(db.read("sets.json")["sets"][0]["marks"], {"photo.png": [[new, 0.25, 0.5]]},
                         "its place on the set's photo too (issue #416)")
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
        with closing(sqlite3.connect(db.path)) as other, other:
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
        with closing(sqlite3.connect(db.path)) as other, other:
            other.execute("DELETE FROM metadata WHERE key='seal'")
        with self.assertRaises(DatabaseIntegrityError):
            Database(self.home, KEY)

    def test_small_write_reseals_only_its_document_not_library_or_identities(self):
        db = self.open()
        db.write("library.json", {"items": [{"store": "booth", "id": str(n), "name": f"Product {n}"} for n in range(100)]})
        fingerprint = db._document_fingerprint
        with mock.patch.object(db, "_document_fingerprint", wraps=fingerprint) as document, mock.patch.object(db, "_identity_fingerprint", wraps=db._identity_fingerprint) as identities:
            db.write("routine.json", {"last": 123})
            self.assertEqual([c.args[0][0] for c in document.call_args_list], ["routine.json"])
            identities.assert_not_called()
        self.assertEqual(db.read("routine.json"), {"last": 123})

    def test_authenticated_v1_upgrades_atomically_and_keeps_documents(self):
        class Legacy(Database):
            def _migrate_v2(self):
                pass
        legacy = Legacy(self.home, KEY)
        legacy.write("tags.json", {"notes": {"booth:hoodie": "original"}})
        self.assertEqual(legacy.connection.execute("PRAGMA user_version").fetchone()[0], 1)
        legacy.close()
        db = self.open()
        self.assertEqual(db.connection.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(db.read("tags.json"), {"notes": {"booth:hoodie": "original"}})
        self.assertEqual(db.connection.execute("SELECT count(*) FROM document_seals").fetchone()[0], 1)

    def test_tampered_v1_is_not_upgraded_or_resealed(self):
        class Legacy(Database):
            def _migrate_v2(self):
                pass
        legacy = Legacy(self.home, KEY)
        legacy.write("tags.json", {"original": True})
        legacy.close()
        with closing(sqlite3.connect(self.home / "metadata.sqlite3")) as other, other:
            other.execute("UPDATE documents SET body='{}'")
        with self.assertRaises(DatabaseIntegrityError):
            Database(self.home, KEY)
        with closing(sqlite3.connect(self.home / "metadata.sqlite3")) as other:
            self.assertEqual(other.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertIsNone(other.execute("SELECT name FROM sqlite_master WHERE name='document_seals'").fetchone())

    def test_v2_verifies_document_bodies_and_identity_rows_even_when_root_is_unchanged(self):
        for index, statement in enumerate(("UPDATE documents SET body='{}' WHERE name='library.json'",
                                            "DELETE FROM document_seals WHERE name='library.json'",
                                            "UPDATE products SET creator='tampered'",
                                            "DELETE FROM aliases")):
            with self.subTest(statement=statement):
                db = Database(self.home / str(index), KEY)
                self.addCleanup(db.close)
                db.write("library.json", {"items": [{"store": "booth", "id": "1", "name": "Hoodie"}]})
                with closing(sqlite3.connect(db.path)) as other, other:
                    other.execute(statement)
                with self.assertRaises(DatabaseIntegrityError):
                    db.read("library.json")

    def test_failed_migration_leaves_every_original_in_place(self):
        (self.home / "tags.json").write_text('{"tags":{}}')
        (self.home / "sets.json").write_text("not JSON")
        with self.assertRaises(ValueError):
            Database(self.home, KEY)
        self.assertTrue((self.home / "tags.json").is_file())
        self.assertFalse(list(self.home.glob("*.pre-sqlite-v1")))


class OffByDefault(IsolatedTestCase):
    """Until the database can recover a lost sealing key and project ambiguous product identities safely,
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

