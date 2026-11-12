"""Lazy references to shared services during the store-adapter extraction.

Adapters import no browser/server at module load. Existing facade attributes
remain the injection boundary for recorded-page tests and third-party scripts;
their implementations live only in the owning store module.
"""
from __future__ import annotations

import importlib


class Services:
    """Resolve a shared module only when an adapter operation actually needs it."""

    def __init__(self, name: str):
        self.name = name

    def __getattr__(self, name: str):
        """Preserve current dependency overrides instead of capturing stale from-import aliases."""
        return getattr(importlib.import_module("hoard." + self.name), name)


lib = Services("library")
dl = Services("downloader")
wish = Services("wishlists")
