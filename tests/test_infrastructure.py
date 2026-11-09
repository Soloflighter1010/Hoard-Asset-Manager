"""The shared test home, reproducible sharding, and parser-based translation checks."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.isolation import IsolatedTestCase

ROOT = Path(__file__).resolve().parent.parent


class TranslationParser(IsolatedTestCase):
    def parse(self, source):
        result = subprocess.run(["node", str(ROOT / "scripts/i18n_keys.mjs")],
                                input=json.dumps([{"source": source, "file": "sample.js"}]),
                                capture_output=True, text=True, check=True)
        return {call["key"] for call in json.loads(result.stdout)}

    def test_only_possible_argument_values(self):
        self.assertEqual(self.parse('''
          // tr("Not a call")
          const fake = 'tr("Nor this")';
          tr(kind === "script" ? "A script" : flag ? "A plugin" : "Neither");
          trHTML("One " + (ok ? "file" : "folder"), "Not a key");
          tr(`Back up`); tr(value || "Fallback");
          tr("Escaped \\\"quotes\\\"");
        '''), {"A script", "A plugin", "Neither", "One file", "One folder", "Back up", "Fallback", 'Escaped "quotes"'})

    def test_changed_words_name_the_old_translations(self):
        from scripts.translation_keys import missing_message
        message = missing_message(["Download the chosen files"],
                                  {"Download chosen files": "選択したファイルをダウンロード"},
                                  {"Download the chosen files"})
        self.assertIn("Download chosen files", message)
        self.assertIn("選択したファイルをダウンロード", message)

    def test_html_json_is_not_javascript(self):
        from scripts.translation_keys import Scripts
        parser = Scripts()
        parser.feed('<script type="application/json">{"words":"tr(fake)"}</script>\n'
                    '<script>tr("Real");</script>')
        self.assertEqual(len(parser.scripts), 1)
        self.assertEqual(self.parse(parser.scripts[0]), {"Real"})


class TestHomes(IsolatedTestCase):
    def test_modules_imported_inside_a_home_do_not_keep_it_afterwards(self):
        import types
        from tests.isolation import TestHome
        from hoard import paths
        original = paths.DATA
        name = "hoard._late_test_import"
        try:
            with TestHome():
                late = types.ModuleType(name)
                late.picture_folder = paths.DATA / "pictures"
                late.default_downloads = paths.default_downloads
                sys.modules[name] = late
            self.assertEqual(late.picture_folder, original / "pictures")
            self.assertEqual(late.default_downloads(), paths.default_downloads())
        finally:
            sys.modules.pop(name, None)

    def test_inherited_class_setup_uses_the_subclass_home(self):
        import unittest
        import io

        class Parent(IsolatedTestCase):
            @classmethod
            def setUpClass(cls):
                cls.inherited_home = cls.test_home

        class Child(Parent):
            def test_fixture(self):
                self.assertEqual(self.inherited_home, self.test_home)

        out = io.StringIO()
        result = unittest.TextTestRunner(stream=out).run(unittest.TestSuite([Child("test_fixture")]))
        self.assertTrue(result.wasSuccessful(), out.getvalue())

    def test_imported_paths_and_default_downloads_are_inside_the_home(self):
        from hoard import config, library, paths, server
        for path in (config.CONFIG_FILE, library.THUMB_DIR, server.LIBRARY_FILE, paths.default_downloads()):
            self.assertTrue(path.is_relative_to(self.test_home), str(path))

    def test_stale_paths_are_rejected_and_classes_restore_their_home(self):
        # A separate process exercises a failing fixture without contaminating
        # this runner's own violation history or changing its active class.
        code = '''
import io, unittest
from tests.isolation import IsolatedTestCase
from hoard import paths, library
first = []
class First(IsolatedTestCase):
    def test_first(self):
        first.append(library.THUMB_DIR)
        library.THUMB_DIR.mkdir(parents=True)
class Second(IsolatedTestCase):
    def test_stale(self):
        self.assertNotEqual(paths.DATA, first[0].parent.parent)
        first[0].mkdir(parents=True, exist_ok=True)
out = io.StringIO()
suite = unittest.TestSuite([First('test_first'), Second('test_stale')])
result = unittest.TextTestRunner(stream=out).run(suite)
assert not result.wasSuccessful(), out.getvalue()
assert 'outside its own app-data folder' in out.getvalue(), out.getvalue()
'''
        done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_every_test_class_uses_isolation(self):
        import ast
        for path in (ROOT / "tests").glob("test_*.py"):
            tree = ast.parse(path.read_text("utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.assertFalse(any(isinstance(base, ast.Attribute) and base.attr == "TestCase"
                                         for base in node.bases), f"{path.name}:{node.lineno}")


class Shards(IsolatedTestCase):
    def test_every_module_appears_exactly_once_and_heavy_ones_are_spread(self):
        from scripts.test_suite import partition
        names = ["a", "b", "c", "d"]
        shards = partition(names, 2, {"a": 10, "b": 9, "c": 2, "d": 1})
        self.assertEqual(sorted(name for shard in shards for name in shard), names)
        self.assertEqual(shards, [["a", "d"], ["b", "c"]])
