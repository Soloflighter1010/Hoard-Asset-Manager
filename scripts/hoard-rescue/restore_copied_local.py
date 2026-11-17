"""Restore only copied Local records from a backup, never linked records. Close Hoard first."""
import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import re
import tempfile

from hoard_rescue import plain, read, sealed

def safe_relative(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Missing relative path')
    path = PureWindowsPath(value)
    if path.drive or path.root or any(p in ('.', '..') or ':' in p for p in path.parts):
        raise ValueError('Unsafe relative path in copied record')
    return value

def copied_records(value):
    result = {}
    for ident, record in value['assets'].items():
        if record.get('location'):
            continue
        if not re.fullmatch(r'local-[0-9a-f]{12}', ident):
            raise ValueError('Unexpected copied Local identity')
        folder = safe_relative(record['folder'])
        if PureWindowsPath(folder).parts[0].lower() == '_linked':
            raise ValueError('A record without a location still names a linked folder')
        files = record['files']
        for file in files.values():
            safe_relative(file['path'])
        # Fresh copied-only records: never bless arbitrary URLs or source locations.
        result[ident] = {k: record[k] for k in ('key', 'name', 'creator', 'folder', 'files', 'first_seen', 'note') if k in record}
        result[ident]['url'] = None
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path, nargs='?')
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('HOARD_DATA_DIR') or
                        str(Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Hoard')))
    args = parser.parse_args()
    backup = (args.backup or Path(input('Paste the full path to _manifest.rescue-backup.json: ').strip().strip('"'))).absolute()
    value = read(backup)[1]
    records = copied_records(value)
    print(f'Restore {len(records)} copied records; omit {len(value["assets"]) - len(records)} linked records.')
    for record in records.values():
        print(record.get('name', record['folder']))
    if not records:
        return
    target = backup.with_name('_manifest.json')
    if target.exists():
        raise ValueError('A live _manifest.json exists. Nothing changed; keep both files and ask for help merging.')
    key_path = args.data_dir.absolute() / 'integrity.key'
    plain(key_path)
    key = bytes.fromhex(key_path.read_text('ascii').strip())
    if len(key) != 32:
        raise ValueError('Invalid existing key')
    if input('With Hoard fully closed, type RESTORE COPIES: ').strip() != 'RESTORE COPIES':
        print('Cancelled.')
        return
    data = json.dumps(sealed({'assets': records}, key), indent=2, ensure_ascii=False).encode('utf-8')
    # Fully stage before publishing. Hard-link publication refuses any existing target.
    fd, draft = tempfile.mkstemp(prefix='.hoard-copies-', dir=backup.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(draft, target)
    finally:
        os.unlink(draft)
    print('Copied records restored. Original backup unchanged. Restart Hoard.')

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Stopped: {error}')
        raise SystemExit(1)
