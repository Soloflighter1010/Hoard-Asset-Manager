"""Small things every part of Hoard uses: times, progress messages, and the errors stores raise."""
from __future__ import annotations

import contextlib
import threading
import time
from datetime import datetime, timezone

_sinks: list = []   # (lane, sink): each job's, while it runs
_sink_lock = threading.Lock()
_lane = threading.local()
_stops: dict = {}   # lane -> (the running job's Stop, the job's thread), while one runs (stoppable)


def set_lane(name: str) -> None:
    """This thread's work is that lane's (hoard/jobs.py: Projects' tasks run in a lane of their own, beside the main
    one's). Its progress messages go to that lane's job only, never to a download running at the same time."""
    _lane.name = name


def _this_lane() -> str:
    return getattr(_lane, "name", "main")   # (any thread not set: the main lane's, as all were before)


def _sinks_here() -> list:
    lane = _this_lane()
    with _sink_lock:
        return [sink for on, sink in _sinks if on == lane]


class NotLoggedIn(Exception):
    """The store sent its sign-in page instead of your purchases."""


class Cancelled(BaseException):
    """You stopped a download. A BaseException, so it passes through the per-file error handling."""


@contextlib.contextmanager
def stoppable(stop: threading.Event):
    """While inside: this thread runs its lane's job, which stop ends (Stop and Force stop set it), so pause() in
    this thread ends the job at once rather than after the wait."""
    lane = _this_lane()
    _stops[lane] = (stop, threading.get_ident())
    try:
        yield
    finally:
        if _stops.get(lane, (None, None))[1] == threading.get_ident():
            del _stops[lane]


def pause(seconds: float) -> None:
    """Wait seconds, as time.sleep does: between a store's pages, before trying a download again. In a running job's
    own thread, Stop or Force stop chosen meanwhile ends the job straight away (raising Cancelled, as a progress
    message would; the Stop is used up), instead of only after the wait (issue #201)."""
    got = _stops.get(_this_lane())
    if got is None or got[1] != threading.get_ident():
        time.sleep(seconds)
        return
    if got[0].wait(max(0.0, seconds)):
        got[0].clear()
        raise Cancelled()


def now_iso() -> str:
    """The current time in UTC, as an ISO 8601 string with seconds."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    """Report progress: printed when there's a console, and passed to the app while it runs a job."""
    try:
        print(msg, flush=True)
    except (AttributeError, OSError, ValueError):  # a windowed app has no console
        pass
    for sink in _sinks_here():
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
    for sink in _sinks_here():
        sink(note)


@contextlib.contextmanager
def capture_log(sink):
    """Send every progress message to sink while inside this block (sink may raise Cancelled to stop): those said in
    this thread's lane (set_lane), so two lanes' jobs never hear each other's."""
    entry = (_this_lane(), sink)
    with _sink_lock:
        _sinks.append(entry)
    try:
        yield
    finally:
        with _sink_lock:
            _sinks.remove(entry)
