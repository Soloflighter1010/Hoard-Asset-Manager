"""Compatibility import for itch.io's API, now owned by its store adapter.

Aliasing the module preserves the established patchable API constant and session
helpers for command-line clients and recorded API tests.
"""
import sys
from .stores import itch as _implementation

sys.modules[__name__] = _implementation
