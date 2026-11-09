"""Transactional private metadata, with legacy JSON imports and unchanged public exports.

Only the explicitly listed files directly inside Hoard's app-data home belong to
this database. Downloaded files, public catalogs, project files, credentials and
the running-instance handshake remain ordinary files. Callers keep their domain
validation; this module owns persistence, migrations, identity and integrity.
"""
from __future__ import annotations

import contextlib
import collections
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import threading
from types import SimpleNamespace
from pathlib import Path

from .paths import data_dir

VERSION = 1
FILES = frozenset({
    "config.json", "library.json", "tags.json", "marks.json", "sets.json",
    "package-needs.json", "konoasset.json", "asset-updates.json", "routine.json",
    "sync.json", "tasks.json", "project-tasks.json", "library_folders.json",
    "integrity.json", "picture-looks.json", "update.json", "window-place.json",
    "vpm-projects.json", "vpm-presets.json", "sealed-files.json", "store-health.json", "scheduler.json", "job-queue.json",
})
_instances: dict[Path, "Database"] = {}
# Domain read/modify/write sections share the same lock as transactions. This
# fixed ordering prevents an import holding the DB from waiting on a tag lock
# held by another thread that is itself waiting for the DB.
metadata_lock = threading.RLock()
_instances_lock = metadata_lock
_log = logging.getLogger(__name__)
_file_batches = threading.local()


class DatabaseIntegrityError(RuntimeError):
    """Metadata changed outside Hoard; never replace it with empty defaults."""


def _json(value) -> str:
    """Canonical JSON makes seals independent of indentation and dictionary order."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Database:
    """One serialized SQLite connection; nested operations use rollback savepoints."""

    def __init__(self, home: Path, key: bytes):
        self.home, self.path, self.key = home, home / "metadata.sqlite3", key
        self.lock, self.depth = metadata_lock, 0
        home.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise DatabaseIntegrityError("Hoard's metadata database must not be a symbolic link.")
        if os.name == "posix":
            os.chmod(home, 0o700)
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA trusted_schema=OFF")
        # A rollback journal is deliberately used: the database and its committed
        # seal are one file, so copying it while Hoard is closed needs no WAL files.
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute("PRAGMA synchronous=FULL")
        try:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version > VERSION:
                raise DatabaseIntegrityError("This metadata database needs a newer Hoard.")
            if version == 0:
                self._migrate_v1()
            self.connection.execute("BEGIN")
            self._verify()
            self._external_version = self.connection.execute("PRAGMA data_version").fetchone()[0]
            self.connection.execute("COMMIT")
            self._finish_legacy_files()
        except BaseException:
            self.connection.close()
            raise
        if os.name == "posix":
            os.chmod(self.path, 0o600)

    def _migrate_v1(self):
        """Import every known document before committing version 1; rename only after commit."""
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.connection.execute("CREATE TABLE documents (name TEXT PRIMARY KEY, body TEXT NOT NULL, revision INTEGER NOT NULL, trust TEXT NOT NULL)")
            self.connection.execute("CREATE TABLE products (uid TEXT PRIMARY KEY, store TEXT NOT NULL, store_id TEXT NOT NULL, name_key TEXT NOT NULL, creator TEXT NOT NULL, UNIQUE(store,store_id))")
            self.connection.execute("CREATE TABLE aliases (alias TEXT NOT NULL, uid TEXT NOT NULL REFERENCES products(uid), PRIMARY KEY(alias,uid))")
            pending = {}
            for name in sorted(FILES):
                path = self.home / name
                if not path.exists():
                    continue
                if path.is_symlink() or path.stat().st_size > 256 * 1024 * 1024:
                    raise DatabaseIntegrityError(f"Cannot migrate {name}: not a regular bounded metadata file.")
                data = path.read_bytes()
                # Preserve the current document shape, including unknown fields
                # and its old seal. Domain sanitizers still decide what to use.
                value = json.loads(data)
                trust = self._legacy_trust(value, path)
                self.connection.execute("INSERT INTO documents VALUES (?, ?, 1, ?)", (name, _json(value), trust))
                pending[name] = hashlib.sha256(data).hexdigest()
            library = self.connection.execute("SELECT body,trust FROM documents WHERE name='library.json'").fetchone()
            if library and library[1] not in {"changed", "foreign"}:
                self._identify(json.loads(library[0]))
                for name, body in list(self.connection.execute("SELECT name,body FROM documents")):
                    self.connection.execute("UPDATE documents SET body=? WHERE name=?", (_json(self._references(name, json.loads(body), encode=True)), name))
            self.connection.execute("INSERT INTO metadata VALUES ('legacy_pending', ?)", (_json(pending),))
            self.connection.execute(f"PRAGMA user_version={VERSION}")
            self._seal()
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        if pending:
            _log.info("Imported %d private JSON documents into metadata.sqlite3; keeping originals for one release.", len(pending))

    def _legacy_trust(self, value, path: Path) -> str:
        """Check old seals without recursing through the database being constructed."""
        info = value.get("integrity") if isinstance(value, dict) else None
        if isinstance(info, dict):
            if info.get("key_id") != hashlib.sha256(self.key).hexdigest()[:16]:
                return "foreign"
            body = {k: v for k, v in value.items() if k != "integrity"}
            expected = hmac.new(self.key, _json(body).encode("utf-8"), hashlib.sha256).hexdigest()
            return "sealed" if hmac.compare_digest(expected, str(info.get("mac"))) else "changed"
        from .safety import _path_id
        try:
            remembered = json.loads((self.home / "sealed-files.json").read_text("utf-8")).get("files", [])
        except (OSError, ValueError, AttributeError):
            remembered = []
        return "changed" if _path_id(path) in remembered else "unsealed"

    def _finish_legacy_files(self):
        """Finish an interrupted post-commit rename without overwriting any recovery copy."""
        row = self.connection.execute("SELECT value FROM metadata WHERE key='legacy_pending'").fetchone()
        pending = json.loads(row[0]) if row else {}
        for name, digest in pending.items():
            path, aside = self.home / name, self.home / (name + ".pre-sqlite-v1")
            if path.exists() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                if aside.exists():
                    if hashlib.sha256(aside.read_bytes()).hexdigest() != digest:
                        raise DatabaseIntegrityError(f"A different migration backup already exists: {aside.name}")
                    path.unlink()
                else:
                    path.rename(aside)
        # Keep the manifest itself: it documents exactly which originals were
        # imported and lets a restart safely finish the same idempotent operation.

    def _fingerprint(self) -> bytes:
        """Seal all logical tables, including names, deletions, aliases and schema version."""
        digest = hmac.new(self.key, b"hoard-metadata-v1\0", hashlib.sha256)
        digest.update(str(self.connection.execute("PRAGMA user_version").fetchone()[0]).encode("ascii"))
        for sql in (
            "SELECT key,value FROM metadata WHERE key != 'seal' ORDER BY key",
            "SELECT name,body,revision,trust FROM documents ORDER BY name",
            "SELECT uid,store,store_id,name_key,creator FROM products ORDER BY uid",
            "SELECT alias,uid FROM aliases ORDER BY alias,uid",
        ):
            digest.update(sql.encode("ascii"))
            cursor = self.connection.execute(sql)
            if sql.startswith("SELECT name,body"):
                # Documents can be tens of MB. Feed their already canonical
                # JSON directly, avoiding an extra escaped copy of the string.
                for row in cursor:
                    for value in row:
                        data = str(value).encode("utf-8")
                        digest.update(len(data).to_bytes(8, "big"))
                        digest.update(data)
                continue
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break
                # JSON's C encoder hashes identity rows in bounded chunks rather
                # than making millions of Python/HMAC calls for large libraries.
                # The row order and chunk size are part of version 1's format.
                data = _json(rows).encode("utf-8")
                digest.update(len(data).to_bytes(8, "big"))
                digest.update(data)
        return digest.digest()

    def _seal(self):
        """Write the logical-content seal inside the same transaction as the change."""
        self.connection.execute("INSERT OR REPLACE INTO metadata VALUES ('seal', ?)", (self._fingerprint().hex(),))

    def _verify(self):
        """Fail closed on external changes, including a removed row or removed seal."""
        row = self.connection.execute("SELECT value FROM metadata WHERE key='seal'").fetchone()
        if not row or not hmac.compare_digest(str(row[0]), self._fingerprint().hex()):
            raise DatabaseIntegrityError("Hoard's metadata changed outside Hoard. Keep metadata.sqlite3 and restore a known backup; the legacy .pre-sqlite-v1 files have not been overwritten.")

    def _check_external(self):
        """Another connection's commit invalidates trust even while this Hoard stays open."""
        version = self.connection.execute("PRAGMA data_version").fetchone()[0]
        if version != self._external_version:
            self._verify()
            self._identity_maps = None
            self._external_version = version

    @contextlib.contextmanager
    def transaction(self):
        """Commit all participating documents together; an inner failure rolls back its savepoint."""
        with self.lock:
            depth = self.depth
            self.connection.execute("BEGIN IMMEDIATE" if depth == 0 else f"SAVEPOINT hoard_{depth}")
            self.depth += 1
            try:
                self._check_external()
                yield self
                if depth == 0:
                    self._seal()
                    self.connection.execute("COMMIT")
                else:
                    self.connection.execute(f"RELEASE hoard_{depth}")
            except BaseException:
                self._identity_maps = None
                if depth == 0:
                    self.connection.execute("ROLLBACK")
                else:
                    self.connection.execute(f"ROLLBACK TO hoard_{depth}")
                    self.connection.execute(f"RELEASE hoard_{depth}")
                raise
            finally:
                self.depth -= 1

    @contextlib.contextmanager
    def _reading(self):
        """Verify and read one consistent snapshot, including across another process's commits."""
        with self.lock:
            own = self.depth == 0
            if own:
                self.connection.execute("BEGIN")
            try:
                self._check_external()
                yield
            finally:
                if own:
                    self.connection.execute("ROLLBACK")

    def read(self, name: str, max_bytes: int = 256 * 1024 * 1024):
        """Read a detached document, with the same bounded JSON boundary as legacy files."""
        from .safety import DataFileError
        with self._reading():
            row = self.connection.execute("SELECT body FROM documents WHERE name=?", (name,)).fetchone()
            if row is None:
                raise FileNotFoundError(name)
            if len(row[0].encode("utf-8")) > max_bytes:
                raise DataFileError(f"{name} is unexpectedly large")
            return self._references(name, json.loads(row[0]), encode=False)

    def write(self, name: str, value):
        """Replace one complete document; callers may surround several writes in a transaction."""
        with self.transaction():
            if name == "library.json":
                self._identify(value)
                # Documents written before the first library refresh may still
                # have name references. Bind them once an unambiguous id exists.
                for other, body in list(self.connection.execute("SELECT name,body FROM documents WHERE name IN ('tags.json','marks.json','sets.json','asset-updates.json','config.json')")):
                    self.connection.execute("UPDATE documents SET body=?, revision=revision+1 WHERE name=?", (_json(self._references(other, json.loads(body), encode=True)), other))
            body = _json(self._references(name, value, encode=True))
            trust = "sealed" if isinstance(value, dict) and "integrity" in value else "unsealed"
            self.connection.execute("INSERT INTO documents VALUES (?, ?, 1, ?) ON CONFLICT(name) DO UPDATE SET body=excluded.body, revision=documents.revision+1, trust=excluded.trust", (name, body, trust))

    def _identify(self, library, *, follow_names: bool = True):
        """Follow store ids first, then unique old names when a store changes an id.

        A name is never enough to merge two products present in the same refresh.
        Creator names must also agree. Ambiguous legacy names remain unresolved,
        preserving the previous metadata instead of attaching it to a wrong item.
        """
        from .tags import tag_key
        items = library.get("items", []) if isinstance(library, dict) else []
        items = [i for i in items if isinstance(i, dict) and isinstance(i.get("store"), str)
                 and isinstance(i.get("id"), (str, int)) and isinstance(i.get("name"), str)]
        incoming = {(i["store"].lower(), str(i["id"])) for i in items}
        name_counts = collections.Counter((i["store"].lower(), tag_key(i["store"], i["name"]),
                                           str(i.get("creator") or "").casefold()) for i in items)
        known = { (store, sid): (uid, name, creator) for uid, store, sid, name, creator in
                 self.connection.execute("SELECT uid,store,store_id,name_key,creator FROM products") }
        by_name = {}
        for (store, sid), (uid, name, creator) in known.items():
            if (store, sid) not in incoming:
                by_name.setdefault((store, name, creator), []).append(uid)
        for item in items:
            store, sid = item["store"].lower(), str(item["id"])
            name, creator = tag_key(store, item["name"]), str(item.get("creator") or "").casefold()
            previous = known.get((store, sid))
            alias = self.connection.execute("SELECT uid FROM aliases WHERE alias=?", ("id:" + store + ":" + sid,)).fetchall()
            candidates = by_name.get((store, name, creator), []) if follow_names and name_counts[(store, name, creator)] == 1 else []
            uid = previous[0] if previous else alias[0][0] if len(alias) == 1 else candidates.pop() if len(candidates) == 1 else store + ":" + sid
            self.connection.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?) ON CONFLICT(uid) DO UPDATE SET store_id=excluded.store_id, name_key=excluded.name_key, creator=excluded.creator", (uid, store, sid, name, creator))
            for reference in ("id:" + store + ":" + sid, "name:" + name):
                self.connection.execute("INSERT OR IGNORE INTO aliases VALUES (?, ?)", (reference, uid))
        self._identity_maps = None

    def _maps(self):
        """Cache identity lookups for repeated tag/mark reads in the same database generation."""
        if getattr(self, "_identity_maps", None) is None:
            names = dict(self.connection.execute("SELECT uid,name_key FROM products"))
            aliases = dict(self.connection.execute("SELECT substr(alias,6),min(uid) FROM aliases WHERE alias LIKE 'name:%' GROUP BY alias HAVING count(*)=1"))
            self._identity_maps = aliases, names
        return self._identity_maps

    def _references(self, name: str, value, *, encode: bool):
        """Keep product references as ids internally, projecting names for existing APIs/exports."""
        if name not in {"tags.json", "marks.json", "sets.json", "asset-updates.json", "config.json"} or not isinstance(value, dict):
            return value
        aliases, names = self._maps()

        def ref(key):
            """Leave unknown or ambiguous legacy names untouched until a reliable id is known."""
            if not isinstance(key, str):
                return key
            if encode:
                return "product:" + aliases[key] if key in aliases else key
            return names.get(key[8:], key) if key.startswith("product:") else key

        def mapping(values):
            """Translate dictionary keys without dropping unrelated fields."""
            return {ref(k): v for k, v in values.items()} if isinstance(values, dict) else values

        out = dict(value)
        if name == "config.json":
            if isinstance(out.get("download_skip"), list):
                out["download_skip"] = [ref(k) for k in out["download_skip"]]
            if "file_skip" in out:
                out["file_skip"] = mapping(out["file_skip"])
        elif name in {"tags.json", "asset-updates.json"}:
            for field in ("items", "excluded", "notes", "types"):
                if field in out:
                    out[field] = mapping(out[field])
        elif name == "marks.json":
            for field in ("archived", "unarchived", "removed", "hidden", "apart"):
                if isinstance(out.get(field), list):
                    out[field] = [ref(k) for k in out[field]]
            if isinstance(out.get("ids"), dict):
                out["ids"] = {kind: {i: ref(k) for i, k in entries.items()} if isinstance(entries, dict) else entries
                              for kind, entries in out["ids"].items()}
        elif isinstance(out.get("sets"), list):
            out["sets"] = [{**s, "items": [ref(k) for k in s.get("items", [])],
                            **({"products": mapping(s["products"])} if "products" in s else {})}
                           if isinstance(s, dict) and isinstance(s.get("items", []), list) else s for s in out["sets"]]
        return out

    def trust(self, name: str) -> str:
        """Preserve a migrated file's trust status; a valid DB seal does not bless old unsafe links."""
        with self._reading():
            row = self.connection.execute("SELECT trust FROM documents WHERE name=?", (name,)).fetchone()
            return row[0] if row else "unsealed"

    def current_references(self, name: str, value):
        """Resolve a live document's old names through stable ids after a refresh renamed a product."""
        with self._reading():
            return self._references(name, self._references(name, value, encode=True), encode=False)

    def stamp(self, name: str):
        """A logical revision for existing read caches, independent of SQLite file timestamps."""
        with self._reading():
            row = self.connection.execute("SELECT length(body),revision FROM documents WHERE name=?", (name,)).fetchone()
            if row is None:
                raise FileNotFoundError(name)
            return SimpleNamespace(st_size=row[0], st_mtime_ns=row[1], st_mtime=row[1], st_ino=hash(str(self.path)))

    def exists(self, name: str) -> bool:
        """Check for a logical document without decoding its contents."""
        with self._reading():
            return self.connection.execute("SELECT 1 FROM documents WHERE name=?", (name,)).fetchone() is not None

    def delete(self, name: str):
        """Remove a logical document transactionally; legacy recovery copies stay untouched."""
        with self.transaction():
            self.connection.execute("DELETE FROM documents WHERE name=?", (name,))

    def close(self):
        """Release the connection when a server or test home finishes using it."""
        with self.lock:
            self.connection.close()


def managed(path: Path) -> bool:
    """Only known private metadata paths use SQLite; exports and custom paths remain files."""
    return path.name in FILES and path.absolute().parent == data_dir().absolute()


def database() -> Database:
    """Get the database for the current home; never cache it across a moved data directory."""
    from .safety import integrity_key
    home = data_dir().absolute()
    with _instances_lock:
        if home not in _instances:
            _instances[home] = Database(home, integrity_key())
        return _instances[home]


def close_all():
    """Release cached homes, used by test fixture cleanup and application shutdown."""
    with _instances_lock:
        for db in _instances.values():
            db.close()
        _instances.clear()


@contextlib.contextmanager
def transaction():
    """Group domain writes without exposing SQL or connection ownership to callers."""
    with database().transaction() as db:
        yield db


def read_document(path: Path, max_bytes: int = 64 * 1024 * 1024):
    """Read private metadata from SQLite, or an external JSON file through its existing checks."""
    if managed(path):
        return database().read(path.name, max_bytes)
    from .safety import read_json_file as read_file
    with metadata_lock:
        return read_file(path, max_bytes)


def write_document(path: Path, data, root: Path | None = None):
    """Persist a private JSON document; preserve ordinary atomic writes for public/external files."""
    if managed(path):
        return database().write(path.name, json.loads(data))
    from .safety import write_file_safely as write_file
    with metadata_lock:
        for batch in getattr(_file_batches, "active", []):
            if path not in batch:
                batch[path] = (("link", os.readlink(path)) if path.is_symlink() else
                               ("bytes", path.read_bytes()) if path.exists() else ("missing", None))
        return write_file(path, data, root)


@contextlib.contextmanager
def import_transaction():
    """Roll back metadata and companion export writes when an import raises.

    SQLite provides crash atomicity for private metadata. Companion files use
    their usual atomic replacements; this undo log additionally restores them
    on a caught import failure. Exports remain rebuildable after process death.
    The shared lock keeps this process's readers from seeing intermediate files.
    """
    from .safety import write_file_safely as write_file
    with metadata_lock:
        active = getattr(_file_batches, "active", [])
        batch = {}
        _file_batches.active = active + [batch]
        try:
            with transaction():
                yield
        except BaseException:
            _file_batches.active = active
            for path, (kind, previous) in reversed(list(batch.items())):
                if kind == "bytes":
                    write_file(path, previous)
                else:
                    path.unlink(missing_ok=True)
                    if kind == "link":
                        path.symlink_to(previous)
            raise
        finally:
            _file_batches.active = active


def exists(path: Path) -> bool:
    """Logical existence for metadata, filesystem existence for everything else."""
    return database().exists(path.name) if managed(path) else path.exists()


def is_file(path: Path) -> bool:
    """Metadata documents are logical files; ordinary directories do not count as files."""
    return exists(path) if managed(path) else path.is_file()


def stat(path: Path):
    """Supply a logical cache stamp for metadata, the real stat result for other files."""
    return database().stamp(path.name) if managed(path) else path.stat()


def seal_status(value, path: Path | None = None) -> str:
    """Use verified database trust for metadata and the existing seal checks for exports."""
    if path is not None and managed(path):
        return database().trust(path.name)
    from .safety import check_seal as check_file
    return check_file(value, path)


def archive_document(path: Path) -> Path:
    """Keep a damaged logical document as a diagnostic file before removing it from the database."""
    if not managed(path):
        from .safety import set_aside as aside_file
        return aside_file(path)
    import time
    from .safety import write_file_safely as write_file
    aside = path.with_name(f"{path.stem}.damaged-{time.time_ns()}{path.suffix}")
    with transaction() as db:
        write_file(aside, _json(db.read(path.name)))
        db.delete(path.name)
    return aside


def private(path: Path):
    """Apply owner-only permissions to a legacy file or the database that now holds it."""
    if os.name == "posix":
        os.chmod(database().path if managed(path) else path, 0o600)


def remove(path: Path, *, missing_ok: bool = False):
    """Delete current metadata or an ordinary file, preserving migration recovery copies."""
    if not managed(path):
        return path.unlink(missing_ok=missing_ok)
    with transaction() as db:
        if not missing_ok and not db.exists(path.name):
            raise FileNotFoundError(path)
        db.delete(path.name)


def identify_local(records: dict):
    """Bind Local metadata to its manifest id; identical names never merge separate Local items."""
    from .tags import tag_key
    db = database()
    items = [{"store": "local", "id": key, "name": rec.get("name") or "", "creator": rec.get("creator") or ""}
             for key, rec in records.items() if isinstance(rec, dict)]
    with metadata_lock:
        changed = []
        for item in items:
            old = db.connection.execute("SELECT name_key,creator FROM products WHERE store='local' AND store_id=?", (item["id"],)).fetchone()
            if old != (tag_key("local", item["name"]), item["creator"].casefold()):
                changed.append(item)
        if changed:
            with db.transaction():
                db._identify({"items": changed}, follow_names=False)
                for name, body in list(db.connection.execute("SELECT name,body FROM documents WHERE name IN ('tags.json','marks.json','sets.json','asset-updates.json','config.json')")):
                    db.connection.execute("UPDATE documents SET body=?,revision=revision+1 WHERE name=?", (_json(db._references(name, json.loads(body), encode=True)), name))
