"""Offline rescue preserves copied assets and never opens linked source paths."""
from pathlib import Path
import json
from unittest.mock import patch

from tests.isolation import IsolatedTestCase
from hoard.paths import data_dir
from hoard.safety import check_seal, seal
from scripts.rescue_linked_local import rescue


class LinkedLocal(IsolatedTestCase):
    def test_sixty_four_links_are_removed_from_signed_records(self):
        root = data_dir() / "downloads"
        manifest = root / "Local" / "_manifest.json"
        manifest.parent.mkdir(parents=True)
        catalog = root / "catalog.json"
        copied_file = manifest.parent / "keep.zip"
        copied_file.write_bytes(b"keep")
        copied = {"store": "Local", "folder": "Local/keep", "source": "original-path"}
        linked = [{"store": "Local", "folder": f"Local/_linked/{n}", "location": fr"\\offline-nas\assets\{n}"}
                  for n in range(64)]
        records = {
            manifest: {"assets": {"copy": copied, **{str(n): item for n, item in enumerate(linked)}}},
            catalog: {"assets": [copied, *linked], "sets": [{"name": "Mixed", "items": [copied["folder"], linked[0]["folder"]]}]},
        }
        originals = {}
        for path, value in records.items():
            originals[path] = json.dumps(seal(value)).encode()
            path.write_bytes(originals[path])
        original_lstat = Path.lstat

        def refuse_nas(path):
            if "offline-nas" in str(path):
                self.fail("Rescue tried to access a linked source")
            return original_lstat(path)

        with patch.object(Path, "lstat", refuse_nas):
            rescue([root])
            self.assertEqual(manifest.read_bytes(), originals[manifest])
            rescue([root], apply=True)
            rescue([root], apply=True)
        for path in records:
            value = json.loads(path.read_bytes())
            self.assertEqual(check_seal(value), "sealed")
            backups = list(path.parent.glob(path.name + ".before-rescue-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), originals[path])
        self.assertEqual(json.loads(manifest.read_bytes())["assets"], {"copy": copied})
        self.assertEqual(json.loads(catalog.read_bytes())["sets"], [{"name": "Mixed", "items": ["Local/keep"]}])
        self.assertEqual(copied_file.read_bytes(), b"keep")
