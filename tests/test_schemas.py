"""Export schemas stay in step with the Python writer and C# reader, using shared examples."""
from __future__ import annotations

import json
import re
from pathlib import Path

from tests.isolation import IsolatedTestCase
from hoard import downloader, schema
from scripts.build_schemas import generated

ROOT = Path(__file__).resolve().parent.parent


class Contracts(IsolatedTestCase):
    def test_bundled_schemas_match_the_public_source(self):
        self.assertEqual((ROOT / "hoard/schema_data.py").read_text("utf-8"), generated())
        for rule in schema.SCHEMAS.values():
            schema.check_vocabulary(rule)

    def test_the_writer_obeys_every_shared_example(self):
        examples = json.loads((ROOT / "docs/schemas/examples.json").read_text("utf-8"))
        for case in examples:
            with self.subTest(case=case["name"]):
                problems = downloader.validate_catalog_entry(case["entry"])
                self.assertEqual(not problems, case["valid"], problems)

    def test_a_new_field_needs_a_schema_and_a_reader(self):
        entry = json.loads((ROOT / "docs/schemas/examples.json").read_text("utf-8"))[0]["entry"]
        self.assertIn("not in the schema", " ".join(schema.errors({**entry, "unwritten_field": "value"})))
        reader = (ROOT / "Packages/soloflighter.hoard/Editor/Core/Catalog.cs").read_text("utf-8")
        read = reader.split("static HoardAsset Read(", 1)[1].split("return a;", 1)[0]
        fields = set(re.findall(r'e\.(?:Str|Get|Strings)\("(\w+)"\)', read))
        self.assertEqual(fields, set(schema.SCHEMAS["entry-v4.schema.json"]["properties"]))

    def test_unknown_schema_rules_are_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            schema.check_vocabulary({"type": "object", "madeUpRule": 1})
        with self.assertRaises(ValueError):
            schema.check_vocabulary({"$ref": "https://example.com/schema.json"})

    def test_wrong_shapes_and_bool_counts_are_refused(self):
        entry = json.loads((ROOT / "docs/schemas/examples.json").read_text("utf-8"))[0]["entry"]
        self.assertTrue(schema.errors({**entry, "files": "one.zip"}))
        self.assertTrue(schema.errors({**entry, "code": {"scripts": True, "plugins": 0, "editor": 0,
                                                        "tools": [], "folders": []}}))
