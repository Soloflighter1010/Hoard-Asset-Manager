"""Download speed and time left, for the progress shown while Hoard downloads.

A sync finds its files as it goes, product by product, so it can't know in advance how much there is: what's
shown is the file being downloaded (its size, the speed, and the time it has left), and how many files and bytes
this sync has downloaded so far.
"""
from __future__ import annotations

import math
import time


class Transfers:
    SMOOTHING = 5.0   # seconds: the speed follows the last few seconds, so it doesn't jump about

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.name: str | None = None
        self.done, self.at, self.speed = 0, None, None
        self.files, self.bytes = 0, 0

    def update(self, name: str, done: int, total: int | None) -> dict:
        """Take a download's progress (bytes done of total) and return what the page shows."""
        now = self.clock()
        if name != self.name:
            # a new file: a resumed one starts where its .part file ended, which isn't counted as speed
            self.name, self.files = name, self.files + 1
        elif self.at is not None and now > self.at and done >= self.done:
            got, took = done - self.done, now - self.at
            rate = got / took
            weight = 1 - math.exp(-took / self.SMOOTHING)
            self.speed = rate if self.speed is None else self.speed + weight * (rate - self.speed)
            self.bytes += got
        self.done, self.at = done, now
        left = None
        if total and self.speed and self.speed >= 1 and total >= done:
            left = round((total - done) / self.speed)
        return {"file": self.name, "done": done, "total": total, "speed": round(self.speed) if self.speed else None,
                "left": left, "files": self.files, "bytes": self.bytes}
