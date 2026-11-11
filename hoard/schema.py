"""Validate exports with Hoard's bundled, versioned JSON Schemas.

Only the JSON Schema vocabulary used by the bundled schemas is implemented; a
check rejects unknown keywords so a schema edit can never silently weaken it.
This does not replace store-link, text normalization or filesystem checks.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .schema_data import SCHEMAS

KEYWORDS = {"$schema", "$id", "$ref", "title", "description", "type", "properties", "required",
            "additionalProperties", "items", "minItems", "maxItems", "minLength", "maxLength",
            "minimum", "maximum", "pattern", "enum", "const", "anyOf"}


def check_vocabulary(node: dict) -> None:
    """Reject unsupported validation keywords and remote references in our own schema source."""
    unknown = set(node) - KEYWORDS
    if unknown:
        raise ValueError(f"Unsupported schema keywords: {sorted(unknown)}")
    if "$ref" in node and node["$ref"] not in SCHEMAS:
        raise ValueError(f"Unknown schema: {node['$ref']}")
    for value in node.get("properties", {}).values():
        check_vocabulary(value)
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            check_vocabulary(node[key])
    for value in node.get("anyOf", []):
        check_vocabulary(value)


def _type(value, kind: str) -> bool:
    """JSON types, keeping Python's bool distinct from its int superclass."""
    return {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
            "integer": type(value) is int, "number": type(value) in (int, float),
            "boolean": type(value) is bool, "null": value is None}.get(kind, False)


@lru_cache(maxsize=64)
def _pattern(pattern: str):
    """Compile only patterns from the trusted schema bundle, once."""
    return re.compile(pattern)


def _errors(value, rule: dict, path: str):
    """Yield structural violations with JSON-style paths for diagnostics."""
    if "$ref" in rule:
        yield from _errors(value, SCHEMAS[rule["$ref"]], path)
    kinds = rule.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    if kinds and not any(_type(value, kind) for kind in kinds):
        yield f"{path}: expected {' or '.join(kinds)}"
        return
    if "const" in rule and (type(value) is not type(rule["const"]) or value != rule["const"]):
        yield f"{path}: expected {rule['const']!r}"
    if "enum" in rule and value not in rule["enum"]:
        yield f"{path}: value is not one of the allowed choices"
    if "anyOf" in rule and not any(not list(_errors(value, choice, path)) for choice in rule["anyOf"]):
        yield f"{path}: no allowed shape matches"
    if isinstance(value, dict):
        for name in rule.get("required", []):
            if name not in value:
                yield f"{path}.{name}: required"
        props, extra = rule.get("properties", {}), rule.get("additionalProperties", True)
        for name, child in value.items():
            if name in props:
                yield from _errors(child, props[name], f"{path}.{name}")
            elif extra is False:
                yield f"{path}.{name}: not in the schema"
            elif isinstance(extra, dict):
                yield from _errors(child, extra, f"{path}.{name}")
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0) or len(value) > rule.get("maxItems", float("inf")):
            yield f"{path}: array length is outside its bounds"
        if "items" in rule:
            for i, child in enumerate(value):
                yield from _errors(child, rule["items"], f"{path}[{i}]")
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0) or len(value) > rule.get("maxLength", float("inf")):
            yield f"{path}: text length is outside its bounds"
        if "pattern" in rule and not _pattern(rule["pattern"]).search(value):
            yield f"{path}: text does not match its pattern"
    if type(value) in (int, float):
        if value < rule.get("minimum", float("-inf")) or value > rule.get("maximum", float("inf")):
            yield f"{path}: number is outside its bounds"


def errors(value, name: str = "entry-v4.schema.json") -> list[str]:
    """Return a bounded list of violations against a bundled schema, without network access."""
    import itertools
    return list(itertools.islice(_errors(value, SCHEMAS[name], "$"), 20))


def require(value, name: str) -> dict:
    """Refuse to publish an export that differs from its documented contract."""
    problems = errors(value, name)
    if problems:
        raise ValueError("Invalid Hoard export: " + "; ".join(problems))
    return value
