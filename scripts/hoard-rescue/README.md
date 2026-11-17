# Hoard linked asset rescue for Windows 11

For branch `fix/335-project-package-updates`, inspected at commit
`8fb004f154acf8492baa8dfb33adc8aaee03c336`.

Requires Python 3.10 or newer (no third-party packages). Uses your existing
Hoard integrity key. Does not launch or import Hoard, scan NAS source folders,
delete source files, delete copied Local assets, or modify the private database.

1. Exit Hoard from its system tray menu. Check Task Manager for a leftover Hoard
   process or the Python process running your source build and close it.
2. Extract all rescue files together. You can put them in your Hoard checkout
   to use its `.venv\Scripts\python.exe` automatically.
3. Double-click `Preview-Hoard-Rescue.bat`. Check the library path and linked
   asset count. The count might differ from 64: this removes ALL linked Local
   entries, including earlier ones. Preview changes nothing.
4. Double-click `Run-Hoard-Rescue.bat`. Type `REMOVE LINKS` when prompted.
5. Keep the printed `hoard-rescue-...` backup folder. Start Hoard again.

The default private data location is `%LOCALAPPDATA%\Hoard`, or
`HOARD_DATA_DIR` when set. Saved downloads and additional library roots are read
from the private database in read-only mode, falling back to legacy config.json
only if no database exists. A disconnected configured library stops the tool;
use explicit roots to rescue only connected libraries.

For a custom build/data folder, run in Command Prompt:

```
py -3 hoard_rescue.py --data-dir "D:\HoardData" --root "D:\My Assets"
py -3 hoard_rescue.py --data-dir "D:\HoardData" --root "D:\My Assets" --apply
```

Repeat `--root` for additional library folders. Choose the folder containing
`Local`, not a NAS source asset folder. Microsoft Store Python can use separate
AppData storage; pass that build's actual `--data-dir`, or use the same Python
environment that you used to run Hoard. The tool refuses mismatched seals
instead of generating a replacement key.

## What gets updated

Linked records (a truthy `location` field) are removed from each selected
`Local/_manifest.json`. Matching folders are filtered from existing catalog.json,
catalog set items, and tags.json exports. Changes are sealed with your existing
key. Cached pictures, `_linked` metadata folders, personal tags/sets, and stable
product identities are retained; they are harmless without the manifest records.
No catalog rebuild is performed, since rebuilding can access NAS locations.

Each changed file is backed up byte-for-byte before the first replacement.
`restore.json` maps backup filenames to their original paths and includes hashes;
`removed.json` lists removed records. Backups contain private paths; keep them
private. On a normal write error, previously replaced files are rolled back.
If power is lost partway through, close Hoard and restore every original file
listed in restore.json by copying the corresponding `.original` backup to its
original path. Restore the entire set before restarting Hoard.

## Validation and limits

Tested with 64 unreachable linked entries plus a copied asset: preview is read
only, linked entries disappear, the copied record survives, exports and seals
remain valid, repeated runs do nothing, mismatched seals and symlinks are refused,
changed files abort, and a simulated partial write failure rolls back.

Tests ran on Linux; the Windows launcher, junction check, and Documents lookup
have not been exercised on Windows here. This addresses linked records as the
suspected cause; recovery on your actual library still needs to be confirmed.
It does not repair corrupt databases or force-stop running Hoard processes.
