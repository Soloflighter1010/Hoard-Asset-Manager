# Private metadata

`hoard/storage.py` owns `metadata.sqlite3` in Hoard's app-data folder. Python's
standard SQLite module is the only database dependency. Domain modules retain
their validation and public data shapes; their persistence calls go through
`read_document`, `write_document`, `exists`, `stat` and `remove`.

The version 1 migration imports these logical documents:

| Area | Documents |
| --- | --- |
| Settings and library | config, library, library_folders |
| Organization | tags, marks, sets |
| Readers and imports | package-needs, konoasset, picture-looks |
| Work and checks | asset-updates, routine, sync, tasks, project-tasks, integrity, update, scheduler, job-queue, store-health |
| Desktop and projects | window-place, vpm-projects, vpm-presets |
| Integrity bookkeeping | sealed-files |

These names previously ended in `.json`. They remain document identifiers, not
files written alongside the database. Explicit custom paths outside app-data
continue to use the legacy file reader/writer. Credentials, images, logs and the
running-instance handshake are not database documents. Unity's project reports,
download manifests and the exported `catalog.json`, `tags.json` and `asset.json`
remain interoperable files.

## Migration and recovery

`PRAGMA user_version` records the migration version. On the first open, every
existing known document is read into a single transaction, preserving its shape
and unknown fields. A malformed or oversized source aborts migration without
moving any original. Only after commit are originals renamed to
`<name>.json.pre-sqlite-v1`. A sealed import manifest makes those renames
restartable without overwriting a different backup. Keep these files for the
first release using SQLite; Hoard does not automatically delete them.

To restore the pre-migration state, close Hoard, preserve the current database
and its `integrity.key` together, move the database aside, and copy the recovery
files back to their original names. The recovery files are the state at migration,
not backups of later edits. Use Settings' Backup for current, portable backups.

The database and its journal are private to the account. A logical HMAC-SHA256
seal covers all documents, identity records, aliases, revisions, trust flags and
the schema version. It is checked when opened, and again if another connection
commits. Missing/changed rows or a removed seal stop access rather than becoming
empty defaults. A migrated document retains its original trust status: moving a
foreign or altered library into SQLite does not authorize its links.

## Product identity

Products have a persistent `store:id` identity and aliases for previous store ids
and normalized names. A refresh follows the store id first. If the id changes,
only a unique absent predecessor with the same normalized name and creator is
matched. Two simultaneously listed products are never merged just because their
names agree. Local manifests use their existing random Local ids.

Tags, notes, types, marks, set membership, download/file skip preferences and update records use these ids inside
the database. The storage boundary projects the current name keys for existing
API clients and exported files. Unresolved or ambiguous legacy names remain
unchanged until a reliable identity is available. Old name aliases keep a request
from a page opened before a rename attached to the same product.

## Transactions and exports

Nested transactions use savepoints. A shared reentrant lock orders domain changes
and database access, avoiding lock inversions during imports. Library refreshes
restore the live in-memory snapshot if saving fails; a saved-page import commits
all parsed stores and their confirmed shop settings together. KonoAsset commits
its remembered ids, tags, notes and types together and restores companion files
if an import raises or is stopped.

SQLite guarantees crash atomicity for private metadata. Public files still use
atomic file replacement, and are regenerated from the current metadata. The
import's companion-file undo log handles raised failures; it is not a filesystem
transaction across process death. Do not infer a committed database transaction
from the presence of a newly written export after a crash.

## Measuring changes

Run `python scripts/benchmark_storage.py --products 50000 --repeats 5`. It uses a
temporary home, compares the previous sealed-JSON read plus sanitization with a
cold database open plus sanitization, and reports migration time separately.
The initial Linux measurement was approximately 0.95 seconds for either reader,
2.01 seconds for the one-time migration, 16.6 MB for JSON and 26.0 MB for SQLite.
These are local measurements, not a timing assertion for shared CI machines.
