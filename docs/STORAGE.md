# Private metadata

> **Held back.** Hoard keeps its private metadata in the JSON files it always has. The database described here is
> used only when Hoard is started with `HOARD_METADATA=sqlite` (`storage.enabled()`), for development and testing.
> Implementation now covers:
>
> - **Older-release compatibility.** Committed documents have current JSON mirrors; older JSON edits are imported
>   on reopening. Run releases separately, with the SQLite flag off in older experimental builds.
> - **Recovery.** Recognized databases with missing/foreign seals are preserved, then opened with untrusted
>   library links hidden and automatic work disabled. The library shows a refresh notice.
> - **Write cost.** Per-document seals keep small writes independent of library size.
> - **Distinct identities.** Products sharing a normalized name receive separate, permanent API keys tied to
>   their store identities. Ambiguous legacy annotations remain preserved without guessing an owner.
>
> Default activation still waits for native packaged Windows/macOS/Linux validation and the desktop transition
> to settle (#324). Source-package and sidecar checks below do not certify native installers or windows.
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
| Readers and imports | package-needs, konoasset, bblm, picture-looks |
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
inside one transaction. Low-level `Database` opens remain strict; failed authentication does not upgrade or
bless data. The application's database factory enables quarantine recovery for recognized schema v1/v2
seal failures. It reserves the writer lock, validates the exact known schema (rejecting triggers, views,
virtual tables and additional executable schema), and makes a consistent, flushed snapshot named
`metadata.before-recovery-<unique>.sqlite3` before changing anything. A backup failure leaves the original
unchanged. Unknown versions/schemas and structurally invalid data are not silently replaced with defaults.
Schema validation also rejects injected triggers even when logical data seals still match.

Recovery retains settings, library, annotations and stable identities, marks every recovered document
untrusted, and signs that quarantine state with the current key. It disables scheduled sync/checks and
project auto-updates, clears pending jobs/scheduler state and repository execution approvals, and keeps
original JSON conflicts and migration backups. The library's visible notice explains that links/images
are hidden until a store refresh, automatic work is off, and the original database was preserved.
A trusted refresh restores store links; it does not silently re-enable automatic work.

Live external tampering still stops the current connection; recovery is an explicit startup policy,
not a way for a running process to bless external edits. A migrated document retains its original
trust status: moving a foreign or altered library into SQLite does not authorize its links.

## Product identity

Products have a persistent `store:id` identity and aliases for previous store ids
and normalized names. A refresh follows the store id first. If the id changes,
only a unique absent predecessor with the same normalized name and creator is
matched. Two simultaneously listed products are never merged just because their
names agree. Local manifests use their existing random Local ids.

Tags, notes, types, marks, set membership, download/file skip preferences and update records use these ids inside
the database. The storage boundary projects the current name keys for existing
API clients and exported files. Unambiguous products keep their existing name keys. Colliding products
get permanent `store:x<digest>` keys derived from stable identities, valid in existing tag/mark/set formats.
Reserved keys cannot be stolen by a later product with the same literal name. Exact full-title aliases
resolve numbered names; callers with a store id also distinguish identical titles. Library rendering uses
one verified identity snapshot, not a query per product. Download selection, file preferences, catalog
annotations and deletion use available store/manifest identities; catalog indexes are never treated as store ids.
Gumroad retains its purchase id in new manifest records and deduplicates by product id rather than title.
Old name-only records whose owner is ambiguous stay unresolved until a reliable store identity is available.

Existing stable references are projected distinctly on upgrade, without collapsing dictionary entries.
Ambiguous shared legacy annotations remain preserved under the old key; Hoard cannot infer which numbered
product an old shared note belonged to. Old aliases preserve unambiguous rename requests, and live download
preferences retain their original binding when a new collision appears. Historical experimental SQLite
prototypes do not understand this projection; use their JSON mode when testing a rollback.

## Transactions and exports

Nested transactions use savepoints. A shared reentrant lock orders domain changes
and database access, avoiding lock inversions during imports. Library refreshes
restore the live in-memory snapshot if saving fails; a saved-page import commits
all parsed stores and their confirmed shop settings together. KonoAsset commits
its remembered ids, tags, notes and types together and restores companion files
if an import raises or is stopped; BB's Library Manager's import does the same with
its remembered ids, tags and 18+ marks.

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

A local Windows synthetic run (16 November 2026) produced these medians. The
comparison uses a small sealed JSON write and a small SQLite document transaction;
it does not weaken SQLite's `synchronous=FULL` durability. These are observations,
not cross-machine timing assertions.

| Library products | Repetitions | Small JSON write | Small SQLite write | Cold JSON open | Cold SQLite open |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 5 | 0.64 ms | 6.67 ms | 0.014 s | 0.023 s |
| 20,000 | 5 | 0.68 ms | 6.44 ms | 0.308 s | 0.373 s |
| 50,000 | 5 | 0.65 ms | 6.54 ms | 0.789 s | 0.949 s |

These measurements include current JSON mirrors and their durable retry bookkeeping.
Small SQLite writes retain roughly 6 ms of overhead over JSON here, but do not
grow with library size. Before mirrors, schema v2 measured 2.3–2.5 ms for these
small writes; compatibility currently adds a second durable database transaction. The documented earlier whole-database seal
cost was about 80 ms at 20,000 products; that historical figure was not rerun on
this machine. The 50,000-product migration took 4.87 s and the database occupied
53.0 MB, compared with 16.6 MB for JSON. The synthetic numbered names all collide under the legacy
normalizer, so this also stresses the additional title/public-key aliases and their storage cost.

Reproduce with `python scripts/benchmark_storage.py --products 50000 --repeats 5`.
Storage tests additionally assert that a small write hashes only its changed
document, while externally changed document bodies, missing seals, product rows
and aliases still fail verification. SQLite remains opt-in.

Compatibility tests exercise settings/library round trips through JSON mode, old-release edits and new documents,
rollback isolation, failed and partially completed mirror batches, missing files, malformed conflicts and
directories, and retaining the old readers' trust restrictions.


## Compatibility evidence and rollout gate

Published source ZIPs 5.1.4 and 5.2.0-beta.4 were downloaded and checked against their published SHA256SUMS.
Both read a migrated fixture without repeating setup, retained two library entries, saved settings/library
edits, and round-tripped those edits and distinct annotations back into current SQLite. The published beta 9
source sidecar and the compiled Windows sidecar extracted from its checksum-verified installer also passed its real `--shell` open/authentication/settings/setup/library/close protocol using
JSON mirrors. The installer was extracted with portable tools from [the official 7-Zip downloads](https://www.7-zip.org/download.html); no archive tool was installed. The current SQLite sidecar passed the same protocol before and after losing `integrity.key`.
Desktop tests additionally open a stand-in window after both key loss and a foreign key.
The existing Check build matrix now runs `--current-sidecar` against its newly compiled Windows/macOS/Linux
servers, checking JSON/SQLite round trips and both lost/foreign keys. These checks, compiled self-tests and
app packaging passed on all four targets in [Check run 531](https://github.com/Soloflighter1010/Hoard-Asset-Manager/actions/runs/43816987488).
That workflow failed in separate documentation/wiki/isolation tests; native window interaction remains untested.

Reproduce after extracting those source ZIPs into the following directories:

```powershell
python scripts/check_storage_compat.py --legacy-root .atlas/compat/5.1.4/source/Hoard --legacy-root .atlas/compat/beta.4/source/Hoard --shell-root .atlas/compat/beta.9/source/Hoard --sidecar .atlas/compat/beta.9/native/server/hoard-server.exe --check-current-shell
```

Archive identities and explicit test limits are recorded in
[the compatibility evidence](measurements/sqlite-compat-2026-11-16.json).
This tests released source packages and source/compiled sidecars, not the native Tauri window or
installer execution. No installer was run and no installed app or real user data was changed.

Before activating SQLite by default in a beta:

- [x] Per-document sealing, current JSON mirrors, quarantine recovery and distinct identity projection.
- [x] Published older source-package round trips, source/compiled Windows sidecar protocols and lost-key startup checks.
- [ ] Native packaged Windows/macOS/Linux app checks on disposable migrated homes, including lost/foreign keys,
  interruption/restart, returning to an older JSON release, and returning to SQLite.
- [ ] Confirm the desktop transition is settled (#324), then activate SQLite in a beta while retaining
  current JSON mirrors and `.pre-sqlite-v1` recovery files.
- [ ] Review beta migration/recovery reports before removing the opt-in gate or compatibility window.
