# Private metadata

> **Held back.** Hoard keeps its private metadata in the JSON files it always has. The database described here is
> used only when Hoard is started with `HOARD_METADATA=sqlite` (`storage.enabled()`), for development and testing.
> It stays off until these are solved:
>
> - **Older-release compatibility addressed.** Committed documents have current JSON mirrors; edits saved
>   by a JSON-only release are imported at the next SQLite open. Run releases separately. See below.
> - **No recovery.** A home whose `integrity.key` is lost, or that was copied to another computer, raises
>   `DatabaseIntegrityError` before any window opens. JSON files with a foreign seal are still read.
> - **Write cost addressed in schema v2.** Changed documents get individual seals and the root covers their
>   authenticated directory. Identity rows are re-sealed when identities change. Small writes no longer re-hash
>   the library. Recovery and ambiguous identity projection still hold back the rollout.
> - **One key, two products.** Products whose names make the same key ("Hair Pack 1", "Hair Pack 2") can come to
>   share one entry when read back.
>
> With the switch off, `managed()` is false for every path, so `read_document`, `write_document`, `exists`,
> `stat` and `remove` are the file calls they replaced; `transaction()` only takes the shared lock.

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

These names end in `.json`. They remain document identifiers and current JSON mirrors are maintained for
older releases during the compatibility window. Explicit custom paths outside app-data
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

After each outer transaction commits, Hoard writes current JSON copies of changed
known documents using atomic file replacement. Nested or failed transactions never
publish uncommitted state. A pending list is authenticated in the database commit;
a second transaction records completed mirror hashes. If a mirror write fails,
the database remains committed and usable, with the pending work retried on the
next write or open. Mirrors are individually atomic, not one atomic snapshot across
all files; after a crash, reopen SQLite once to finish pending mirrors before using
an older release.

An older JSON-only release can read these current files without finding an empty
library or repeating setup. Close one release before starting the other. On the
next SQLite open, edits and newly created known JSON documents are imported in one
transaction, with the library processed first and original trust restrictions
retained. Missing files are regenerated rather than treated as metadata deletions.
Malformed files and conflicting edits during pending mirror work are kept as
`<name>.json.legacy-conflict-<timestamp>` before current mirrors are restored.
Symlinks and directories in place of mirrors are also preserved, not followed.
A foreign/changed library mirror carries a foreign integrity marker so older
readers continue hiding its links and pictures. Trusted mirrors are sealed again
after product references are projected back to names.

These copies support returning to a JSON-only release while keeping current
settings and library. They are not a concurrent synchronization protocol between
a running old release and a running SQLite release. Migration recovery copies
remain unchanged; current mirrors and those original copies serve different purposes.

To restore the pre-migration state, close Hoard, preserve the current database
and its `integrity.key` together, move the database aside, and copy the recovery
files back to their original names. The recovery files are the state at migration,
not backups of later edits. Use Settings' Backup for current, portable backups.

The database and its journal are private to the account. Schema v2 gives each
document an HMAC-SHA256 seal over its name, body, revision and trust flag. A root
seal authenticates the document-seal directory, metadata, schema version and an
identity-table seal. Identity rows and aliases are re-sealed only when they
change. Opening the database or observing another connection's commit verifies
all document contents and identity rows against these seals; small writes only
re-seal changed documents and the small root directory.

An existing v1 database is fully authenticated before its seal format upgrades
inside one transaction. Failed authentication does not upgrade or bless it. Missing/changed rows or a removed seal stop access rather than becoming
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

## Schema v2 write measurements

A local Windows synthetic run (15 November 2026) produced these medians. The
comparison uses a small sealed JSON write and a small SQLite document transaction;
it does not weaken SQLite's `synchronous=FULL` durability. These are observations,
not cross-machine timing assertions.

| Library products | Repetitions | Small JSON write | Small SQLite write | Cold JSON open | Cold SQLite open |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 5 | 0.64 ms | 6.12 ms | 0.013 s | 0.019 s |
| 20,000 | 5 | 0.62 ms | 6.53 ms | 0.317 s | 0.321 s |
| 50,000 | 5 | 0.65 ms | 6.41 ms | 0.811 s | 0.932 s |

These measurements include current JSON mirrors and their durable retry bookkeeping.
Small SQLite writes retain roughly 6 ms of overhead over JSON here, but do not
grow with library size. Before mirrors, schema v2 measured 2.3–2.5 ms for these
small writes; compatibility currently adds a second durable database transaction. The documented earlier whole-database seal
cost was about 80 ms at 20,000 products; that historical figure was not rerun on
this machine. The 50,000-product migration took 2.36 s and the database occupied
26.0 MB, compared with 16.6 MB for JSON.

Reproduce with `python scripts/benchmark_storage.py --products 50000 --repeats 5`.
Storage tests additionally assert that a small write hashes only its changed
document, while externally changed document bodies, missing seals, product rows
and aliases still fail verification. SQLite remains opt-in.

Compatibility tests exercise settings/library round trips through JSON mode, old-release edits and new documents,
rollback isolation, failed and partially completed mirror batches, missing files, malformed conflicts and
directories, and retaining the old readers' trust restrictions. They do not replace testing packaged historical
releases or the Tauri build against a migrated fixture before beta rollout.
