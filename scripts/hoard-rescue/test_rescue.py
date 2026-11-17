import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('rescue', str(Path(__file__).with_name('hoard_rescue.py')))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class RescueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = b'x' * 32
        (self.root / 'Local').mkdir()
        self.assets = {f'local-{i:012x}': {'name': str(i), 'folder': f'_linked/local-{i:012x}',
                         'location': '//unreachable-nas/assets/' + str(i)} for i in range(64)}
        self.assets['copied'] = {'name': 'Keep', 'folder': 'Keep', 'files': {'a': {'path': 'keep.zip'}}}
        self.manifest = self.root / 'Local' / '_manifest.json'
        self.write(self.manifest, {'assets': self.assets})
        entries = [{'folder': 'Local/' + a['folder'], 'tags': ['test']} for a in self.assets.values()]
        self.write(self.root / 'catalog.json', {'assets': entries,
                   'sets': [{'name': 'set', 'items': [e['folder'] for e in entries]}]})
        self.write(self.root / 'tags.json', {'total_assets': 65, 'tags': {'test': {
            'count': 65, 'assets': [e['folder'] for e in entries]}}, 'suggested': {}})

    def write(self, path, value):
        path.write_text(json.dumps(r.sealed(value, self.key)), encoding='utf-8')

    def test_preview_apply_backup_and_idempotence(self):
        original = self.manifest.read_bytes()
        changes, removed = r.plan([self.root], self.key)
        self.assertEqual(len(removed), 64)
        self.assertEqual(self.manifest.read_bytes(), original)
        r.apply(changes, removed, self.key, self.root)
        value = r.read(self.manifest, self.key)[1]
        self.assertEqual(value['assets'], {'copied': self.assets['copied']})
        catalog = r.read(self.root / 'catalog.json', self.key)[1]
        self.assertEqual(catalog['sets'][0]['items'], ['Local/Keep'])
        self.assertEqual(len(catalog['assets']), 1)
        self.assertEqual(r.read(self.root / 'tags.json', self.key)[1]['total_assets'], 1)
        backup = next(self.root.glob('hoard-rescue-*'))
        self.assertEqual((backup / '000.original').read_bytes(), original)
        self.assertEqual(r.plan([self.root], self.key), ({}, []))

    def test_bad_seal_refused(self):
        self.write(self.manifest, {'assets': self.assets})
        with self.assertRaises(ValueError):
            r.plan([self.root], b'z' * 32)

    def test_changed_file_refused(self):
        changes, removed = r.plan([self.root], self.key)
        self.manifest.write_text('{}')
        with self.assertRaises(ValueError):
            r.apply(changes, removed, self.key, self.root)
        self.assertEqual(self.manifest.read_text(), '{}')

    def test_partial_failure_rolls_back(self):
        changes, removed = r.plan([self.root], self.key)
        originals = {p: p.read_bytes() for p in changes}
        real = r.replace
        calls = 0
        def fail_second(path, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('simulated write failure')
            real(path, data)
        with patch.object(r, 'replace', fail_second):
            with self.assertRaises(OSError):
                r.apply(changes, removed, self.key, self.root)
        self.assertEqual({p: p.read_bytes() for p in changes}, originals)

    def test_symlink_refused(self):
        target = self.root / 'target.json'
        self.manifest.rename(target)
        self.manifest.symlink_to(target)
        with self.assertRaises(ValueError):
            r.plan([self.root], self.key)

if __name__ == '__main__':
    unittest.main()
