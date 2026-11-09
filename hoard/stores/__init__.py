"""Discover one adapter per store and retain the established Python import names."""
from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache


@lru_cache(maxsize=1)
def modules() -> dict:
    """A new store needs one module exposing STORE, plus its recorded-page fixtures."""
    found = [importlib.import_module(__name__ + "." + entry.name)
             for entry in pkgutil.iter_modules(__path__) if entry.name not in {"base", "health", "services"}]
    return {module.STORE.key: module for module in sorted(found, key=lambda module: module.STORE.order)}


def adapters() -> dict:
    """The registered store contracts in the application's presentation order."""
    return {key: module.STORE for key, module in modules().items()}


def install(area: str, namespace: dict):
    """Keep existing import names available while their code belongs to one store adapter."""
    for module in modules().values():
        namespace.update(getattr(module, area.upper() + "_EXPORTS"))
