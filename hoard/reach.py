"""Is a folder somewhere Hoard can reach now? A Local item listed where it is (issue #80) can be on a drive that's
unplugged, or on a network share (a NAS) that's switched off, asleep or out of reach. On Windows each look at a file on a
share that doesn't answer can wait half a minute or more before it fails, so with dozens of such items every list of
the library (the downloads, the catalog, what each product needs) stopped for hours (issue #368).

So each folder is looked at first, on threads of their own (MOST at once), with a short wait for them all; what it
said is kept for a minute. A folder is away when it doesn't answer in time, when it took longer than that to say it
isn't there, or when the drive or share it's on isn't there (an unplugged drive, on Windows): nothing reads from it
until it answers again, and it's shown as not connected, never as gone (its record, its tags and its place in sets
are kept). A folder that's waiting to be looked at, or whose look hasn't answered yet, isn't looked at again."""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from pathlib import Path

WAIT = 3.0    # seconds to wait for the folders to answer, all of them together
KEEP = 60.0   # seconds an answer is kept
MOST = 16     # looks at once: one that doesn't answer holds its thread until the drive gives up

_lock = threading.Lock()
_said: dict[str, tuple[float, str]] = {}               # folder -> (when it answered, "there", "gone" or "away")
_asking: dict[str, tuple[float, threading.Event]] = {}  # folder -> (when it was asked about, set once it answers)
_queue: deque[str] = deque()                            # folders waiting for a thread to look at them
_overdue: set[str] = set()                              # folders someone has already waited out, with no answer yet
_looking = 0                                            # threads looking
_now = time.monotonic                                   # (the clock: Windows' moves in steps of about 16 ms)


def _there(folder: str) -> str:
    """The look itself, which can wait as long as the drive does: "there", "gone" (not there, on a drive that is) or
    "away" (its drive or share isn't there)."""
    if os.path.isdir(folder):
        return "there"
    anchor = Path(folder).anchor   # (Windows: "E:\\" or "\\\\nas\\share\\"; elsewhere "/", which is always there)
    return "gone" if anchor and os.path.isdir(anchor) else "away"


def _look() -> None:
    """One of the threads that look: it takes the folders waiting in turn, notes what each said (and when), and wakes
    whoever is waiting for it; it ends when none are left waiting."""
    global _looking
    while True:
        with _lock:
            if not _queue:
                _looking -= 1
                return
            folder = _queue.popleft()
        started = _now()
        try:
            said = _there(folder)
        except Exception:   # (whatever it was, the thread goes on to the next, and this one is looked at again later)
            said = "gone"
        if said == "gone" and _now() - started >= WAIT:
            said = "away"   # that long to say it isn't there: its drive doesn't answer, and each file would wait as long
        with _lock:
            _said[folder] = (_now(), said)
            _overdue.discard(folder)
            done = _asking.pop(folder, (0.0, None))[1]
        if done is not None:
            done.set()


def away(folders, wait: float | None = None) -> set[str]:
    """Which of these folders (absolute paths) are away now (see above), waiting at most wait seconds (WAIT unless
    said; 0 doesn't wait: what isn't known yet is away, and known the next time). A folder that answered, there or
    not, on a drive that answers, isn't."""
    global _looking
    wait = WAIT if wait is None else wait
    now = _now()
    out: set[str] = set()
    waiting: dict[str, threading.Event] = {}
    with _lock:
        for f in {str(f) for f in folders if f}:
            said = _said.get(f)
            if said and now - said[0] < KEEP:
                if said[1] == "away":
                    out.add(f)
                continue
            asking = _asking.get(f)
            if asking is None:
                done = threading.Event()
                _asking[f] = (now, done)
                _queue.append(f)
                waiting[f] = done
            elif f in _overdue or now - asking[0] >= wait:   # waited out before, and still no answer: away, without
                out.add(f)                                     # waiting again
            else:
                waiting[f] = asking[1]
        while _looking < min(MOST, len(_queue)):
            try:
                threading.Thread(target=_look, daemon=True, name="hoard-reach").start()
            except RuntimeError:   # (no more threads to be had: the ones looking take the rest)
                break
            _looking += 1
    deadline = now + wait
    for f, done in waiting.items():
        if not done.wait(max(0.0, deadline - _now())):
            out.add(f)
            with _lock:
                if f in _asking:   # (no answer yet: the next to ask doesn't wait for it again)
                    _overdue.add(f)
            continue
        with _lock:
            said = _said.get(f)
        if said and said[1] == "away":
            out.add(f)
    return out


def is_away(folder, wait: float | None = None) -> bool:
    """away() for one folder."""
    return bool(folder) and str(folder) in away([folder], wait)


def forget() -> None:
    """Forget every answer (for tests)."""
    with _lock:
        _said.clear()
