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


_transfer_sinks: list = []


def report_transfer(name: str, done: int, total: int | None) -> None:
    """Report a download's progress in bytes (passed to the app while it runs a job, for its speed and time left)."""
    with _sink_lock:
        sinks = list(_transfer_sinks)
    for sink in sinks:
        sink(name, done, total)


@contextlib.contextmanager
def capture_transfers(sink):
    """Send every download's progress, sink(name, done, total), to sink while inside this block."""
    with _sink_lock:
        _transfer_sinks.append(sink)
    try:
        yield
    finally:
        with _sink_lock:
            _transfer_sinks.remove(sink)


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
