"""Offline Hoard linked-Local rescue. Python 3.10+, standard library only."""
from __future__ import annotations
import argparse
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import uuid

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def sealed(value, key):
    body = {k: v for k, v in value.items() if k != 'integrity'}
    return {**body, 'integrity': {'alg': 'HMAC-SHA256',
            'key_id': hashlib.sha256(key).hexdigest()[:16],
            'mac': hmac.new(key, canonical(body), hashlib.sha256).hexdigest()}}

def plain(path):
    # Reject symlinks and Windows junctions before reading or replacing metadata.
    for part in [path, *path.parents]:
        s = part.lstat()
        if stat.S_ISLNK(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'Link/junction in metadata path: {part}')

def read(path, key=None):
    plain(path)
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f'Expected a JSON object: {path}')
    if key is not None and 'integrity' in value:
        if value['integrity'] != sealed(value, key)['integrity']:
            raise ValueError(f'Integrity seal does not match this install: {path}. No files changed.')
    return raw, value

def replace(path, data):
    plain(path)
    fd, draft = tempfile.mkstemp(prefix='.hoard-rescue-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(draft, path)
    finally:
        if os.path.exists(draft):
            os.unlink(draft)

def settings(home):
    db = home / 'metadata.sqlite3'
    if db.exists():
        plain(db)
        with sqlite3.connect(db.absolute().as_uri() + '?mode=ro', uri=True) as conn:
            conn.execute('PRAGMA trusted_schema=OFF')
            row = conn.execute("SELECT body FROM documents WHERE name='config.json'").fetchone()
        if not row:
            raise ValueError('No saved config in metadata.sqlite3; pass --root explicitly.')
        return json.loads(row[0])
    return read(home / 'config.json')[1]

def default_root():
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) != 0:
            raise ValueError('Could not find Documents; pass --root explicitly.')
        return Path(buffer.value) / 'Hoard'
    return Path.home() / 'Documents' / 'Hoard'

def plan(roots, key):
    changes, removed = {}, []
    folders = set()
    for root in roots:
        manifest = root / 'Local' / '_manifest.json'
        if not manifest.exists():
            print(f'No Local manifest: {root}')
            continue
        raw, value = read(manifest, key)
        assets = value.get('assets')
        if not isinstance(assets, dict) or any(not isinstance(v, dict) for v in assets.values()):
            raise ValueError(f'Unexpected Local manifest: {manifest}')
        gone = {k: v for k, v in assets.items() if v.get('location')}
        if not gone:
            continue
        for ident, record in gone.items():
            folder = record.get('folder')
            if not isinstance(folder, str) or not folder.startswith('_linked/'):
                raise ValueError(f'Unexpected linked folder for {ident}; no files changed.')
            folders.add('Local/' + folder)
            removed.append({'manifest': str(manifest), 'id': ident, 'name': record.get('name'),
                            'location': record.get('location')})
            print(f"Linked: {record.get('name', ident)}")
        updated = copy.deepcopy(value)
        updated['assets'] = {k: v for k, v in assets.items() if k not in gone}
        changes[manifest] = (raw, updated)
    # Filter existing exports without rebuilding: rebuild would probe offline NAS paths.
    for root in roots:
        for name in ('catalog.json', 'tags.json'):
            path = root / name
            if not path.exists():
                continue
            raw, value = read(path, key)
            updated = copy.deepcopy(value)
            if name == 'catalog.json':
                if not isinstance(updated.get('assets'), list):
                    raise ValueError(f'Unexpected catalog: {path}')
                updated['assets'] = [e for e in updated['assets'] if e.get('folder') not in folders]
                for group in updated.get('sets', []):
                    if isinstance(group.get('items'), list):
                        group['items'] = [f for f in group['items'] if f not in folders]
                if 'sets' in updated:
                    updated['sets'] = [g for g in updated['sets'] if g.get('items')]
            else:
                for section in ('tags', 'suggested'):
                    for tag, entry in list(updated.get(section, {}).items()):
                        entry['assets'] = [f for f in entry['assets'] if f not in folders]
                        entry['count'] = len(entry['assets'])
                        if not entry['assets']:
                            del updated[section][tag]
                catalog_path = root / 'catalog.json'
                if catalog_path in changes:
                    updated['total_assets'] = len(changes[catalog_path][1]['assets'])
            if updated != value:
                changes[path] = (raw, updated)
    return changes, removed

def apply(changes, removed, key, backup_parent):
    backup = backup_parent / ('hoard-rescue-' + uuid.uuid4().hex)
    backup.mkdir(parents=True, exist_ok=False)
    journal = []
    # Finish every backup before replacing any live file.
    for i, (path, (original, updated)) in enumerate(changes.items()):
        if path.read_bytes() != original:
            raise ValueError(f'File changed since preview: {path}. Close Hoard and retry.')
        saved = backup / f'{i:03}.original'
        with saved.open('xb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        journal.append({'path': str(path.absolute()), 'backup': saved.name,
                        'sha256': hashlib.sha256(original).hexdigest()})
    (backup / 'restore.json').write_text(json.dumps(journal, indent=2), encoding='utf-8')
    (backup / 'removed.json').write_text(json.dumps(removed, indent=2, ensure_ascii=False), encoding='utf-8')
    written = []
    try:
        for path, (original, updated) in changes.items():
            if path.read_bytes() != original:
                raise ValueError(f'File changed during rescue: {path}')
            replace(path, json.dumps(sealed(updated, key), indent=2, ensure_ascii=False).encode('utf-8'))
            written.append(path)
    except BaseException:
        for path in reversed(written):
            replace(path, changes[path][0])
        raise
    print(f'Backup: {backup}')
    print('Rescue complete. Start Hoard again. NAS files and copied assets were untouched.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('HOARD_DATA_DIR') or
                        str(Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Hoard')))
    parser.add_argument('--root', type=Path, action='append', help='Downloads/library root; repeat for every library')
    parser.add_argument('--apply', action='store_true', help='Back up and remove links; otherwise preview only')
    parser.add_argument('--backup-dir', type=Path, default=Path.cwd())
    args = parser.parse_args()
    print('Close Hoard completely, including its system-tray process, before applying.')
    home = args.data_dir.expanduser().absolute()
    plain(home / 'integrity.key')
    key = bytes.fromhex((home / 'integrity.key').read_text('ascii').strip())
    if len(key) != 32:
        raise ValueError('Invalid integrity.key; original files unchanged.')
    if args.root:
        roots = args.root
    else:
        cfg = settings(home)
        value = str(cfg.get('root') or '').strip()
        root = Path(os.path.expandvars(value)).expanduser() if value else default_root()
        if not root.is_absolute():
            root = Path.home() / root
        roots = [root] + [Path(os.path.expandvars(p)).expanduser() for p in cfg.get('library_folders', [])]
    roots = list(dict.fromkeys(p.absolute() for p in roots))
    for root in roots:
        plain(root)  # disconnected configured libraries must not be silently skipped
        print(f'Library: {root}')
    changes, removed = plan(roots, key)
    print(f'{len(removed)} linked local assets; {len(changes)} metadata files to update.')
    if not changes:
        return
    if args.apply:
        if input('Type REMOVE LINKS after fully exiting Hoard: ').strip() != 'REMOVE LINKS':
            print('Cancelled. No changes.')
            return
        apply(changes, removed, key, args.backup_dir)
    else:
        print('Preview only. Run again with --apply to back up and remove these links.')

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError) as error:
        print(f'Rescue stopped: {error}')
        raise SystemExit(1)
