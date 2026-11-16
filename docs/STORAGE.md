# Private metadata

> **Held back.** Hoard keeps its private metadata in the JSON files it always has. The database described here is
> used only when Hoard is started with `HOARD_METADATA=sqlite` (`storage.enabled()`), for development and testing.
> It stays off until these are solved:
>
> - **No way back.** After migrating, an older Hoard (and the Tauri build, which shares the folder) finds no
>   settings or library and runs setup again; what it then saves is ignored by the newer one.
> - **No recovery.** A home whose `integrity.key` is lost, or that was copied to another computer, raises
>   `DatabaseIntegrityError` before any window opens. JSON files with a foreign seal are still read.
> - **Write cost addressed in schema v2.** Changed documents get individual seals and the root covers their
>   authenticated directory. Identity rows are re-sealed when identities change. Small writes no longer re-hash
>   the library. Recovery, rollback compatibility and ambiguous identity projection still hold back the rollout.
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

These names previously ended in `.json`. They remain document identifiers; current SQLite writes still do not maintain
legacy JSON mirrors. Explicit custom paths outside app-data
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
| 1,000 | 5 | 0.60 ms | 2.52 ms | 0.013 s | 0.014 s |
| 20,000 | 3 | 0.64 ms | 2.46 ms | 0.292 s | 0.291 s |
| 50,000 | 5 | 0.59 ms | 2.34 ms | 0.742 s | 0.820 s |

Small SQLite writes retain a roughly 2 ms durability overhead over JSON here,
but do not grow with library size. The documented earlier whole-database seal
cost was about 80 ms at 20,000 products; that historical figure was not rerun on
this machine. The 50,000-product migration took 1.86 s and the database occupied
26.0 MB, compared with 16.6 MB for JSON.

Reproduce with `python scripts/benchmark_storage.py --products 50000 --repeats 5`.
Storage tests additionally assert that a small write hashes only its changed
document, while externally changed document bodies, missing seals, product rows
and aliases still fail verification. SQLite remains opt-in.
