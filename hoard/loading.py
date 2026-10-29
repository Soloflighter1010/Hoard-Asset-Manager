"""How far Hoard has got reading what a page shows first (issue #200): the Library's products, what's on disk, and
Projects' list, for the page's splash to count while it waits.

Each part ("library", "projects") is a step at a time ({"step": what it's reading, "done", "total"}), set by the code
doing the reading as it goes and read by GET /api/loading. Nothing here is kept: it's how far this run has got.
"""
from __future__ import annotations

import threading
import time

PARTS = ("library", "projects")
_lock = threading.Lock()
_now: dict[str, dict] = {}


def step(part: str, what: str, done: int, total: int) -> None:
    """part has read done of total of what ("products", "downloads", ...)."""
    with _lock:
        _now[part] = {"step": what, "done": max(0, int(done)), "total": max(0, int(total)), "at": time.monotonic()}


def counter(part: str, what: str, total: int, every: int = 25):
    """A function to call with how many are done so far: it notes it every so many (and the last), so a long loop
    costs next to nothing."""
    step(part, what, 0, total)

    def tick(done: int) -> None:
        """Note done of total, every so many and the last."""
        if done == total or done % every == 0:
            step(part, what, done, total)
    return tick


def finished(part: str) -> None:
    """That part has finished loading: the splash stops showing it."""
    with _lock:
        _now.pop(part, None)


def view(part: str) -> dict:
    """How far part has got: {"step", "done", "total"}, or {} when it isn't reading anything (or stopped saying so a
    minute ago)."""
    with _lock:
        now = _now.get(part)
        if not now or time.monotonic() - now["at"] > 60:
            return {}
        return {k: now[k] for k in ("step", "done", "total")}
