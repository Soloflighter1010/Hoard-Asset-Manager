"""Keeping to a store's rate limit (issue #262).

Jinxxy allows 120 requests a minute (the limit its API sets for creators), so Hoard never sends it more. Every request
to Jinxxy's own sites is counted as it goes: those its pages make themselves, through Hoard's browser
(count_requests), and Hoard's own downloads and reads (egress.py). Before Hoard asks for a page or a file there
(before), it waits until the last minute's count leaves room for it, and for what that page will ask for in turn.
Pictures from Jinxxy's image servers (jinxxy-cdn.com) aren't its API, and aren't counted.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from urllib.parse import urlparse

from .common import tick

JINXXY_PER_MINUTE = 120
PAGE_ROOM = 24   # what a page of Jinxxy's asks for itself, at most, as it loads (its data, its scripts)


class Window:
    """At most `limit` requests in any `per` seconds: each one noted as it's sent, and wait() before sending more."""

    def __init__(self, limit: int, per: float = 60.0, clock=time.monotonic, sleep=time.sleep):
        self.limit, self.per, self.clock, self.sleep = limit, per, clock, sleep
        self.sent: deque[float] = deque()
        self.lock = threading.Lock()

    def _recent(self, now: float) -> int:
        """How many were sent in the last `per` seconds (the older ones forgotten)."""
        while self.sent and self.sent[0] <= now - self.per:
            self.sent.popleft()
        return len(self.sent)

    def note(self, n: int = 1) -> None:
        """Requests sent just now."""
        with self.lock:
            now = self.clock()
            self._recent(now)
            self.sent.extend([now] * n)

    def room(self) -> int:
        """How many more can be sent now."""
        with self.lock:
            return self.limit - self._recent(self.clock())

    def wait(self, need: int = 1, say=None) -> float:
        """Wait until `need` more can be sent (saying so, now and then, which also lets Stop stop it). Returns how long
        it waited."""
        need = min(need, self.limit)
        waited = 0.0
        while True:
            with self.lock:
                now = self.clock()
                if self._recent(now) + need <= self.limit:
                    return waited
                # until enough of the oldest are a minute old
                until = self.sent[self._recent(now) + need - self.limit - 1] + self.per - now
            if say:
                say()
            step = max(0.05, min(until, 1.0))
            self.sleep(step)
            waited += step


JINXXY = Window(JINXXY_PER_MINUTE)


def jinxxy_host(url: str) -> bool:
    """Is this one of Jinxxy's own sites (jinxxy.com, api.jinxxy.com...), whose requests count?"""
    host = (urlparse(url).hostname or "").lower()
    return host == "jinxxy.com" or host.endswith(".jinxxy.com")


def _say() -> None:
    """While waiting: say why (and let Stop stop it)."""
    tick(f"Keeping to Jinxxy's limit of {JINXXY_PER_MINUTE} requests a minute...")


def before(url: str, room: int = PAGE_ROOM) -> None:
    """Before Hoard loads a page (or a file) of Jinxxy's: wait until there's room for it and what it asks for."""
    if jinxxy_host(url):
        JINXXY.wait(room, _say)


def sending(url: str) -> None:
    """One request Hoard itself sends (a download, a read): waited for, and counted."""
    if jinxxy_host(url):
        JINXXY.wait(1, _say)
        JINXXY.note()


def count_requests(ctx) -> None:
    """Count every request a browser's pages send to Jinxxy's own sites, as they're sent."""
    try:
        ctx.on("request", lambda r: JINXXY.note() if jinxxy_host(r.url) else None)
    except Exception:   # (a browser that can't report its requests: Hoard's own are still paced)
        pass
