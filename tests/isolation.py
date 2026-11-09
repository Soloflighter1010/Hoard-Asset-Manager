"""Class-scoped homes for every test, including tests run by ordinary unittest discovery.

The application still has a few paths captured at import time. Rebind all their
aliases together, restore them afterwards, and reject writes through stale paths.
This is test infrastructure: no production process installs the audit hook.
"""
from __future__ import annotations

import atexit
import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_bootstrap = tempfile.TemporaryDirectory(prefix="hoard-test-imports-")
atexit.register(_bootstrap.cleanup)
os.environ["HOARD_DATA_DIR"] = str(Path(_bootstrap.name) / "data")
_protected = {Path(_bootstrap.name).resolve()}
_active: Path | None = None
_violations: list[str] = []


def _inside(path: Path, root: Path) -> bool:
    """Compare normalized paths without opening files (safe inside an audit hook)."""
    return path == root or root in path.parents


def _audit(event, args) -> None:
    """Fail a write into another class's home, even when it comes from a worker thread."""
    if _active is None:
        return
    targets = ()
    if event == "open":
        name, mode, flags = args
        if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            targets = (name,)
    elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.truncate"}:
        targets = args[:1]
    elif event in {"os.rename", "os.link", "os.symlink"}:
        targets = args[:2]
    elif event == "sqlite3.connect":
        targets = args[:1]
    for name in targets:
        if not isinstance(name, (str, bytes, os.PathLike)):
            continue
        path = Path(os.path.abspath(os.fsdecode(name)))
        if any(_inside(path, root) for root in _protected) and not _inside(path, _active):
            message = f"Test wrote outside its own app-data folder: {path} (active: {_active})"
            _violations.append(message)
            raise AssertionError(message)


sys.addaudithook(_audit)


class TestHome(contextlib.ExitStack):
    """Own a class's data, downloads and VCC folders, and restore imported path aliases."""

    def __enter__(self):
        global _active
        super().__enter__()
        from hoard import paths, safety
        old = paths.DATA
        original_default = paths.default_downloads
        self.root = Path(self.enter_context(tempfile.TemporaryDirectory(prefix="hoard-test-class-")))
        data, downloads = self.root / "data", self.root / "downloads" / "Hoard"
        data.mkdir()
        downloads.mkdir(parents=True)
        self.enter_context(mock.patch.dict(os.environ, {
            "HOARD_DATA_DIR": str(data), "HOARD_VCC_DIR": str(self.root / "vcc"),
        }))
        # from-import aliases must move too: changing paths.THUMB_DIR alone would
        # leave library.THUMB_DIR pointing into a previous test's directory.
        for name, module in list(sys.modules.items()):
            if name.startswith("hoard.") and module is not None:
                for attr, value in list(vars(module).items()):
                    if isinstance(value, Path) and _inside(value, old):
                        self.enter_context(mock.patch.object(module, attr, data / value.relative_to(old)))
                    elif value is paths.default_downloads and module is not paths:
                        self.enter_context(mock.patch.object(module, attr, lambda: downloads))
        current_default = lambda: downloads
        self.enter_context(mock.patch.object(paths, "default_downloads", current_default))
        self.enter_context(mock.patch.object(safety, "_integrity_key", None))
        self.enter_context(mock.patch.object(safety, "_sealed_ids", None))
        self.enter_context(mock.patch.dict(safety._EXTRA_SITES, {}, clear=True))
        _protected.add(self.root.resolve())
        self._previous, _active = _active, self.root.resolve()
        start = len(_violations)
        self.callback(self._check_guard, start)
        self.callback(self._restore_new_aliases, old, data, original_default, current_default)
        self.callback(self._close_metadata)
        return self

    @staticmethod
    def _restore_new_aliases(old, data, original_default, current_default):
        """A module first imported inside this fixture must not retain its deleted home."""
        for name, module in list(sys.modules.items()):
            if name.startswith("hoard.") and module is not None:
                for attr, value in list(vars(module).items()):
                    if isinstance(value, Path) and _inside(value, data):
                        setattr(module, attr, old / value.relative_to(data))
                    elif value is current_default:
                        setattr(module, attr, original_default)

    @staticmethod
    def _close_metadata():
        """Close database connections before their home or sealing key is restored."""
        scheduler = sys.modules.get("hoard.scheduler")
        if scheduler is not None:
            scheduler.close_all()
        module = sys.modules.get("hoard.storage")
        if module is not None:
            module.close_all()

    def __exit__(self, *exc):
        """Allow our own temporary-folder cleanup, then restore an enclosing fixture."""
        global _active
        _active = None
        try:
            return super().__exit__(*exc)
        finally:
            _active = self._previous

    @staticmethod
    def _check_guard(start):
        """Report worker-thread violations as class cleanup failures too."""
        if len(_violations) > start:
            raise AssertionError("\n".join(_violations[start:]))


class IsolatedTestCase(unittest.TestCase):
    """Give subclasses a fresh home before their existing setUpClass, without requiring super()."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        original = getattr(cls, "setUpClass").__func__
        # Inherited fixtures still belong to the concrete subclass. Unwrap our
        # parent's wrapper so it does not create a second home around that fixture.
        original = getattr(original, "_hoard_original", original)

        @classmethod
        def isolated_setup(current):
            """Enter before class fixtures; unittest runs cleanups even if setup fails."""
            home = TestHome().__enter__()
            current.addClassCleanup(home.close)
            current.test_home = home.root
            original(current)
        isolated_setup.__func__._hoard_original = original
        cls.setUpClass = isolated_setup
