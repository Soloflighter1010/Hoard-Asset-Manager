"""Bundle the versioned JSON Schemas into the Python package; --check detects drift.

The files in docs/schemas are the editable source. The bundle is shipped with
source, PyInstaller and Flatpak builds without needing a schema package at runtime.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def generated() -> str:
    """Generate a deterministic Python literal from the public schema files."""
    schemas = {p.name: json.loads(p.read_text("utf-8")) for p in sorted((ROOT / "docs/schemas").glob("*.schema.json"))}
    return ('"""Generated catalog schemas; edit docs/schemas, then run scripts/build_schemas.py."""\n'
            'SCHEMAS = ' + repr(schemas) + '\n')


def main() -> int:
    """Write the bundle, or fail if committed schemas and the runtime bundle disagree."""
    target = ROOT / "hoard/schema_data.py"
    text = generated()
    if "--check" in sys.argv:
        if not target.exists() or target.read_text("utf-8") != text:
            print("Schemas changed: run python scripts/build_schemas.py", file=sys.stderr)
            return 1
    else:
        target.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
