"""Small things every part of Hoard uses: times, progress messages, and the errors stores raise."""
from __future__ import annotations

import contextlib
import threading
from datetime import datetime, timezone

_sinks: list = []
_sink_lock = threading.Lock()


class NotLoggedIn(Exception):
    """The store sent its sign-in page instead of your purchases."""


class Cancelled(BaseException):
    """You stopped a download. A BaseException, so it passes through the per-file error handling."""


def now_iso() -> str:
    """The current time in UTC, as an ISO 8601 string with seconds."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    """Report progress: printed when there's a console, and passed to the app while it runs a job."""
    try:
        print(msg, flush=True)
    except (AttributeError, OSError, ValueError):  # a windowed app has no console
        pass
    with _sink_lock:
        sinks = list(_sinks)
    for sink in sinks:
        sink(msg)


class Progress(str):
    """A passing note of how far something has got (a download's size so far): shown while it's current, not kept.
    transfer, when it's a file download, is its numbers for the app: file, got, total, speed (bytes a second), eta
    (seconds left)."""
    transfer: dict | None = None


def tick(msg: str, transfer: dict | None = None) -> None:
    """Say how far something has got, for the app to show while it's current. Unlike log, it isn't printed or kept,
    so it can be said every second; and a job's sink checks for Stop on every tick, as it does on every log."""
    note = Progress(msg)
    note.transfer = transfer
    with _sink_lock:
        sinks = list(_sinks)
    for sink in sinks:
        sink(note)


@contextlib.contextmanager
def capture_log(sink):
    """Send every progress message to sink while inside this block (sink may raise Cancelled to stop)."""
    with _sink_lock:
        _sinks.append(sink)
    try:
        yield
    finally:
        with _sink_lock:
            _sinks.remove(sink)
