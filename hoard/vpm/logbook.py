"""Projects' log: what Hoard did to your projects, packages and repositories, and what went wrong, as ALCOM keeps one
(its Logs page) and the Creator Companion keeps one (its Logs tab). Each entry has its time, its level (info, warning
or error) and what happened.

This run's entries are kept to show in Projects' Logs tab, and each is written to a log of its own for each time
Hoard starts, in Hoard's logs folder beside Hoard's own logs (logs/projects-<date>_<time>.log, made when there's
first something to write; the newest 30 are kept, as ALCOM keeps its own), a line an entry:

    2026-10-22T22:10:00.123456+09:00 [ INFO] Projects: Making Rusk Avatar
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from pathlib import Path

LEVELS = ("info", "warning", "error")
SHOWN = 2000      # this run's entries kept to show (the file has them all)
KEEP_FILES = 30   # Projects' logs kept, the newest first
MAX_MESSAGE = 4000
_NAMES = {"info": " INFO", "warning": " WARN", "error": "ERROR"}


class Warn(str):
    """A progress message that's a warning: log(Warn("Couldn't fetch ...")) shows in Tasks as any message does, and
    in Projects' log as a warning."""
    level = "warning"


class Logbook:
    def __init__(self, folder: Path | None = None):
        self._folder = folder   # (None: Hoard's logs folder, found when there's first something to write)
        self._lock = threading.Lock()
        self._entries: deque[dict] = deque(maxlen=SHOWN)
        self._n = 0
        self._file: Path | None = None
        self._failed = False   # the file couldn't be written: the entries are still shown
        self.run = datetime.now().astimezone().isoformat(timespec="microseconds")   # (a page sees Hoard started again)

    def add(self, level: str, message: str) -> dict:
        level = level if level in LEVELS else "info"
        message = str(message).strip()[:MAX_MESSAGE] or "(nothing said)"
        with self._lock:
            self._n += 1
            entry = {"n": self._n, "time": datetime.now().astimezone().isoformat(timespec="microseconds"),
                     "level": level, "message": message}
            self._entries.append(entry)
            self._write(entry)
        return entry

    def entries(self, after: int = 0) -> list[dict]:
        """This run's entries after the one numbered after (0: all that are kept), oldest first."""
        with self._lock:
            return [dict(e) for e in self._entries if e["n"] > after]

    @property
    def file(self) -> Path | None:
        return self._file

    def _write(self, entry: dict) -> None:
        if self._failed:
            return
        try:
            if self._file is None:
                self._file = self._new_file()
            with open(self._file, "a", encoding="utf-8", errors="replace") as fh:
                fh.write(f"{entry['time']} [{_NAMES[entry['level']]}] {entry['message']}\n")
        except OSError as e:
            self._failed = True
            print(f"Couldn't write Projects' log: {e}", flush=True)

    def _new_file(self) -> Path:
        folder = self._folder
        if folder is None:
            from ..paths import logs_dir
            folder = logs_dir()
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path, n = folder / f"projects-{stamp}.log", 1
        while path.exists():   # (started more than once within a second)
            n += 1
            path = folder / f"projects-{stamp}-{n}.log"
        path.touch()
        tidy(folder)
        return path


def tidy(folder: Path) -> int:
    """Delete Projects' logs past the newest KEEP_FILES. Returns how many went."""
    try:
        found = sorted((p for p in folder.iterdir() if p.name.startswith("projects-") and p.suffix == ".log"),
                       key=lambda p: p.name, reverse=True)
    except OSError:
        return 0
    gone = 0
    for p in found[KEEP_FILES:]:
        try:
            p.unlink()
            gone += 1
        except OSError:
            pass
    return gone


book = Logbook()


def info(message: str) -> dict:
    return book.add("info", message)


def warning(message: str) -> dict:
    return book.add("warning", message)


def error(message: str) -> dict:
    return book.add("error", message)


def count(n: int, word: str) -> str:
    return f"{n:,} {word if n == 1 else word + 's'}"


def size_text(n: float) -> str:
    if n < 1024:
        return f"{int(n):,} bytes"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unit == "GB":
            break
    return f"{n:.1f} {unit}"


def level_of(message) -> str:
    """A progress message's level: a warning when it's said as one (Warn), otherwise info."""
    return getattr(message, "level", "info")
