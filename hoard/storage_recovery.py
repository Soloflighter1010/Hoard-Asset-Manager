"""Quarantine an unauthenticated, recognized metadata database without losing its original."""
from __future__ import annotations

from contextlib import closing
import json
import os
import sqlite3
import tempfile
from pathlib import Path

# Recovery may only write a schema made by our migrations, with no triggers,
# views, virtual tables or additional executable SQL. Do not trust its seal first.
_SCHEMA = {
    "metadata": "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "documents": "CREATE TABLE documents (name TEXT PRIMARY KEY, body TEXT NOT NULL, revision INTEGER NOT NULL, trust TEXT NOT NULL)",
    "products": "CREATE TABLE products (uid TEXT PRIMARY KEY, store TEXT NOT NULL, store_id TEXT NOT NULL, name_key TEXT NOT NULL, creator TEXT NOT NULL, UNIQUE(store,store_id))",
    "aliases": "CREATE TABLE aliases (alias TEXT NOT NULL, uid TEXT NOT NULL REFERENCES products(uid), PRIMARY KEY(alias,uid))",
    "document_seals": "CREATE TABLE document_seals (name TEXT PRIMARY KEY, mac TEXT NOT NULL)",
}


def validate_schema(conn):
    """Logical seals do not authorize injected triggers or altered table definitions."""
    from .storage import DatabaseIntegrityError
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    expected = dict(_SCHEMA)
    if version == 1:
        expected.pop("document_seals")
    elif version != 2:
        raise DatabaseIntegrityError("Cannot open an unknown metadata schema; original data is unchanged.")
    actual = {}
    for kind, name, sql in conn.execute("SELECT type,name,sql FROM sqlite_master"):
        if kind == "index" and sql is None and name.startswith("sqlite_autoindex_"):
            continue
        if kind != "table":
            raise DatabaseIntegrityError("Cannot open an unexpected metadata schema; original data is unchanged.")
        actual[name] = sql
    if actual != expected:
        raise DatabaseIntegrityError("Cannot open an unexpected metadata schema; original data is unchanged.")


def recover(db):
    from .storage import DatabaseIntegrityError, DatabaseSealError, FILES, _json
    conn = db.connection
    conn.execute("BEGIN IMMEDIATE")
    try:
        # A different connection might have repaired it while we waited.
        try:
            db._verify()
        except DatabaseSealError:
            pass
        else:
            conn.execute("COMMIT")
            return
        validate_schema(conn)
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise DatabaseIntegrityError("Cannot recover invalid metadata references; original data is unchanged.")
        # A separate reader can snapshot while this connection reserves the write
        # lock. Calling backup on the writer itself would wait for its transaction.
        fd, name = tempfile.mkstemp(prefix="metadata.before-recovery-", suffix=".sqlite3", dir=db.home)
        os.close(fd)
        backup = Path(name)
        with closing(sqlite3.connect(db.path.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(backup)) as destination:
                source.backup(destination)
        with backup.open("rb+") as saved:
            os.fsync(saved.fileno())
        if os.name == "posix":
            backup.chmod(0o600)
            directory = os.open(db.home, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        # Keep every document and stable identity as data, but never bless links,
        # repository execution approvals, waiting jobs or unattended updates.
        for name, body in conn.execute("SELECT name,body FROM documents").fetchall():
            if name not in FILES or len(body.encode("utf-8")) > 256 * 1024 * 1024:
                raise DatabaseIntegrityError("Cannot recover unexpected metadata documents; the original snapshot is preserved.")
            value = json.loads(body)
            if name == "config.json" and isinstance(value, dict):
                value.update(auto_sync_hours=0, routine_hours=0, automated_sign_in=False,
                             allow_unprotected_signins=False, apprise_events=[])
            elif name in {"job-queue.json", "scheduler.json"}:
                value = {}
            elif name == "vpm-projects.json" and isinstance(value, dict):
                value["git_trusted"] = {}
                projects = value.get("projects")
                for entry in projects.values() if isinstance(projects, dict) else ():
                    if isinstance(entry, dict):
                        entry.update(auto_update="off", auto_pending=None, auto_checked=None)
            conn.execute("UPDATE documents SET body=?,trust='changed',revision=revision+1 WHERE name=?", (_json(value), name))
        conn.execute("DELETE FROM metadata")
        conn.execute("INSERT INTO metadata VALUES ('legacy_pending', '{}')")
        conn.execute("INSERT INTO metadata VALUES ('recovery', ?)", (_json({"backup": backup.name, "refresh_required": True}),))
        db._dirty_documents = {r[0] for r in conn.execute("SELECT name FROM documents")}
        db._identity_dirty = True
        db._identity_maps = None
        db._seal()
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    print(f"Hoard could not authenticate its saved metadata. The original is preserved as {backup.name}. "
          "Library links and pictures are hidden until you refresh your stores. Automatic work is off; "
          "review your settings before enabling it again.", flush=True)
