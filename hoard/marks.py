"""Your choices about what to show: archived, hidden and removed products, and the PIN for hidden ones.

Kept in marks.json in Hoard's app-data folder, sealed like every other data file. Choices are keyed by product (the
same keys tags use), so they apply in the Library and in Downloads, and no refresh or import ever undoes them.

- archived: out of the main library, in the Archive. Gumroad's own archived purchases start there too, unless
  you've moved one back ("unarchived").
- removed: out of everything but the Removed view. Kept out after refreshes, so a store can't bring it back.
- hidden: out of view everywhere (library, Downloads, counts, tags) until unlocked with your PIN.

The PIN is stored only as a slow, salted hash (scrypt). Wrong guesses lock the hidden library for longer each
time, and that survives restarts. It's a privacy screen for the app, not encryption: anyone who can open your
files can still see them.

A forgotten PIN is reset with a recovery phrase: 6 words from the BIP-39 list (2,048 words, so about 66 bits),
made when the PIN is first set and shown once. Like the PIN, it's kept only as a salted scrypt hash, and wrong
phrases count toward the same lockout. It only unlocks Hoard's hidden library; it isn't a crypto wallet phrase.
"""
from __future__ import annotations

import hashlib
import json
import hmac
import os
import secrets
import threading
import time
from pathlib import Path

from .paths import data_dir
from .safety import DataFileError, check_seal, read_json_file, seal, write_file_safely
from .tags import TAG_KEY_RX

KINDS = ("archived", "unarchived", "removed", "hidden")
PHRASE_WORDS = 6
WORDS = (Path(__file__).with_name("recovery_words.txt")).read_text("utf-8").split()   # the BIP-39 English list
_BY_PREFIX = {w[:4]: w for w in WORDS}   # every word is unique in its first four letters, as wallets rely on
MAX_KEYS = 50000
PIN_MIN, PIN_MAX = 4, 64
FREE_TRIES = 5            # wrong PINs before the waits start
MAX_WAIT = 3600           # the longest wait between tries, in seconds
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


class PinError(Exception):
    """A PIN that's wrong, missing, badly formed, or can't be tried yet."""


def read_phrase(text: str) -> list[str]:
    """The recovery words someone typed, as the list's words. Case, commas, numbering ("1. apple") and extra spaces
    don't matter, and the first four letters of a word are enough. Raises PinError saying which word isn't right."""
    import re
    raw = [w for w in re.split(r"[^a-zA-Z]+", str(text or "").lower()) if w]
    if len(raw) != PHRASE_WORDS:
        raise PinError(f"Enter all {PHRASE_WORDS} recovery words (that was {len(raw)}).")
    words = []
    for n, w in enumerate(raw, 1):
        word = w if w in _BY_PREFIX.values() else _BY_PREFIX.get(w[:4]) if len(w) >= 4 else None
        if not word or not word.startswith(w[:4]):
            raise PinError(f"Word {n} ({w}) isn't one of the recovery words. Check its spelling.")
        words.append(word)
    return words


def _hash(pin: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=64 * 1024 * 1024)


class MarkStore:
    """marks.json: one lock for every change, read fresh each time."""
    _lock = threading.Lock()

    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "marks.json"

    def load(self) -> dict:
        """Your choices, as sets of product keys, plus the PIN's hash and lockout state (if any)."""
        empty = {k: set() for k in KINDS} | {"pin": None, "recovery": None, "failures": 0, "wait_until": 0.0}
        try:
            raw = read_json_file(self.path, 16 * 1024 * 1024) if self.path.exists() else None
        except (DataFileError, OSError, ValueError):
            return empty
        if not isinstance(raw, dict):
            return empty
        if check_seal(raw, self.path) == "changed":   # edited outside Hoard: keep the choices, drop PIN and phrase
            raw["pin"] = raw["recovery"] = None
        out = dict(empty)
        for k in KINDS:
            values = raw.get(k) if isinstance(raw.get(k), list) else []
            out[k] = {v for v in values[:MAX_KEYS] if isinstance(v, str) and TAG_KEY_RX.match(v)}
        for field in ("pin", "recovery"):
            h = raw.get(field)
            if (isinstance(h, dict) and isinstance(h.get("salt"), str) and isinstance(h.get("hash"), str)
                    and all(isinstance(h.get(k), int) for k in _SCRYPT)):
                out[field] = h
        out["failures"] = raw.get("failures") if isinstance(raw.get("failures"), int) else 0
        out["wait_until"] = float(raw.get("wait_until")) if isinstance(raw.get("wait_until"), (int, float)) else 0.0
        return out

    def _save(self, data: dict) -> None:
        body = {k: sorted(data[k]) for k in KINDS} | {
            "format": "hoard-marks", "version": 1, "pin": data["pin"], "recovery": data["recovery"],
            "failures": data["failures"], "wait_until": data["wait_until"]}
        write_file_safely(self.path, json.dumps(seal(body), indent=1, sort_keys=True))
        if os.name == "posix":
            os.chmod(self.path, 0o600)

    def change(self, kind: str, keys, on: bool) -> dict:
        """Mark (on) or unmark products. Returns the new choices."""
        if kind not in KINDS:
            raise ValueError("unknown choice")
        keys = {k for k in keys if isinstance(k, str) and TAG_KEY_RX.match(k)}
        with self._lock:
            data = self.load()
            if on:
                if kind == "hidden" and not data["pin"]:
                    raise PinError("Set a PIN for your hidden library first.")
                data[kind] |= keys
                if kind == "archived":
                    data["unarchived"] -= keys
                if kind == "unarchived":
                    data["archived"] -= keys
            else:
                data[kind] -= keys
            if len(data[kind]) > MAX_KEYS:
                raise ValueError("That's more than Hoard can keep track of.")
            self._save(data)
            return data

    # ---- the PIN
    def set_pin(self, pin: str, current: str | None = None) -> str | None:
        """Set the PIN, or change it (which needs the current one). Setting the first PIN also makes a recovery
        phrase, returned here once and never again; changing the PIN keeps the phrase."""
        pin = str(pin or "")
        if not PIN_MIN <= len(pin) <= PIN_MAX:
            raise PinError(f"Use {PIN_MIN} to {PIN_MAX} characters.")
        with self._lock:
            data = self.load()
            if data["pin"]:
                self._check(data, current or "")
            data["pin"] = _hashed(pin)
            data["failures"], data["wait_until"] = 0, 0.0
            phrase = None
            if not data["recovery"]:
                phrase = self._new_phrase(data)
            self._save(data)
            return phrase

    def new_phrase(self) -> str:
        """A new recovery phrase, replacing the old one (the caller checks the hidden library is unlocked)."""
        with self._lock:
            data = self.load()
            if not data["pin"]:
                raise PinError("Set a PIN first.")
            phrase = self._new_phrase(data)
            self._save(data)
            return phrase

    @staticmethod
    def _new_phrase(data: dict) -> str:
        words = [secrets.choice(WORDS) for _ in range(PHRASE_WORDS)]
        phrase = " ".join(words)
        data["recovery"] = _hashed(phrase)
        return phrase

    def recover(self, phrase: str, new_pin: str) -> None:
        """Set a new PIN with the recovery phrase. Hidden items stay hidden. Wrong phrases count toward the lockout."""
        new_pin = str(new_pin or "")
        if not PIN_MIN <= len(new_pin) <= PIN_MAX:
            raise PinError(f"Use {PIN_MIN} to {PIN_MAX} characters for the new PIN.")
        words = read_phrase(phrase)   # a typo is pointed out without counting as a wrong try
        with self._lock:
            data = self.load()
            if not data["recovery"]:
                raise PinError("There's no recovery phrase for this hidden library.")
            self._check(data, " ".join(words), field="recovery")
            data["pin"] = _hashed(new_pin)
            data["failures"], data["wait_until"] = 0, 0.0
            self._save(data)

    def check_pin(self, pin: str) -> None:
        """Raise PinError unless pin is right (and it isn't too soon to try again)."""
        with self._lock:
            data = self.load()
            self._check(data, str(pin or ""))
            if data["failures"]:
                data["failures"], data["wait_until"] = 0, 0.0
                self._save(data)

    def _check(self, data: dict, pin: str, field: str = "pin") -> None:
        if not data[field]:
            raise PinError("There's no PIN yet.")
        wait = data["wait_until"] - time.time()
        if wait > 0:
            raise PinError(f"Too many wrong tries. Try again in {int(wait) + 1} seconds.")
        p = data[field]
        try:
            good = hmac.compare_digest(_hash(pin, bytes.fromhex(p["salt"]), p["n"], p["r"], p["p"]), bytes.fromhex(p["hash"]))
        except (ValueError, TypeError):
            good = False
        if not good:
            data["failures"] += 1
            over = data["failures"] - FREE_TRIES
            if over >= 0:
                data["wait_until"] = time.time() + min(MAX_WAIT, 30 * 2 ** over)
            self._save(data)
            raise PinError("That PIN isn't right." if field == "pin" else "Those aren't your recovery words.")

    def forget_hidden(self) -> set:
        """For a forgotten PIN: returns the hidden products (for the caller to delete from the library), and clears
        them and the PIN. Nothing hidden is ever revealed this way."""
        with self._lock:
            data = self.load()
            gone = set(data["hidden"])
            data["hidden"], data["pin"], data["recovery"], data["failures"], data["wait_until"] = set(), None, None, 0, 0.0
            data["removed"] -= gone
            self._save(data)
            return gone


def _hashed(secret: str) -> dict:
    salt = secrets.token_bytes(16)
    return {"salt": salt.hex(), "hash": _hash(secret, salt, **_SCRYPT).hex(), **_SCRYPT}


def is_archived(item: dict, marks: dict) -> bool:
    """Archived by you, or by the store (Gumroad), unless you've moved it back."""
    key = item["tag_key"]
    return key in marks["archived"] or (bool(item.get("archived")) and key not in marks["unarchived"])
