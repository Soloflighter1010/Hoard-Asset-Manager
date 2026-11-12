"""Compare cold metadata opens against the legacy sealed-JSON reader on a synthetic library.

Uses temporary homes only, writes no user data, and reports medians rather than
enforcing a timing threshold on shared CI machines. Include its JSON output when
reviewing persistence changes; the one-time migration is measured separately.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def benchmark(count: int, repeats: int) -> dict:
    """Read equivalent data through the previous file path and the new database path."""
    with tempfile.TemporaryDirectory(prefix="hoard-storage-benchmark-") as tmp:
        home = Path(tmp)
        os.environ["HOARD_DATA_DIR"] = str(home)
        from hoard import library, safety, storage
        values = {"items": [library.item("booth", str(n), name=f"Benchmark asset {n}", creator="Example")
                           for n in range(count)], "stores": {"booth": {"count": count}}}
        sealed = safety.seal(values)
        path = home / "library.json"
        text = json.dumps(sealed, ensure_ascii=False, indent=1)
        path.write_text(text, "utf-8")
        file_times, db_times = [], []
        for _ in range(repeats):
            started = time.perf_counter()
            raw = safety.read_json_file(path, 256 * 1024 * 1024)
            assert safety.check_seal(raw) == "sealed"
            assert len(library.Library.sanitize(raw)["items"]) == count
            file_times.append(time.perf_counter() - started)
        started = time.perf_counter()
        db = storage.Database(home, safety.integrity_key())
        migration = time.perf_counter() - started
        db.close()
        for _ in range(repeats):
            started = time.perf_counter()
            db = storage.Database(home, safety.integrity_key())
            raw = db.read("library.json")
            assert len(library.Library.sanitize(raw)["items"]) == count
            db.close()
            db_times.append(time.perf_counter() - started)
        return {"products": count, "repeats": repeats, "legacy_open_seconds": statistics.median(file_times),
                "sqlite_open_seconds": statistics.median(db_times), "migration_seconds": migration,
                "legacy_bytes": len(text.encode("utf-8")), "sqlite_bytes": (home / "metadata.sqlite3").stat().st_size}


def main():
    """Print machine-readable measurements for a chosen synthetic library size."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--products", type=int, default=50000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.products <= 200000 or args.repeats < 1:
        parser.error("products must be 1..200000 and repeats must be positive")
    print(json.dumps(benchmark(args.products, args.repeats), indent=2))


if __name__ == "__main__":
    main()
