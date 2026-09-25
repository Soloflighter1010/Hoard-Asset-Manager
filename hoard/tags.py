"""Your tags, shared by the library and the downloads."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

from .paths import data_dir
from .safety import DataFileError, read_json_file, set_aside, write_file_safely


# ----------------------------------------------------------------------------- tags
#
# Your own tags are shared by Hoard and Hoard, in tags.json in Hoard's app-data folder, so a
# product you tag in one shows the same tags in the other. Both tools know a product by its store and
# its name (tag_key), even though they number products differently.
#
# A tag can carry a word to match: every item whose name contains that word gets the tag, including
# items you buy later, unless you've removed it from that item. Keeping a suggested tag creates one.
# Suggested tags (words that turn up in several item names) are worked out fresh each time; hiding one
# stops it being suggested.

TAG_MAX_LENGTH = 40


TAG_LIMITS = {"tags": 1000, "matching": 200, "per_item": 100, "tagged_items": 50000, "keys_per_change": 5000}


# Characters a tag may contain besides letters, marks and digits (in any script, so Japanese works).
TAG_PUNCTUATION = " -_.+&'"


# Names that can confuse JavaScript programs reading tags.json into plain objects.
TAG_RESERVED = {"__proto__", "constructor", "prototype", "__defineGetter__", "__defineSetter__", "__lookupGetter__"}


TAG_KEY_RX = re.compile(r"^(booth|gumroad|jinxxy|payhip):[^\W_]{1,300}$")


_tag_lock = threading.Lock()


def tags_file() -> Path:
    """Where your tags are saved: tags.json in Hoard's folder in this user account's app data."""
    return data_dir() / "tags.json"


def tag_key(store: str, name: str) -> str:
    """How both tools identify a product for tagging: its store and its name, without versions or [labels]."""
    s = unicodedata.normalize("NFKC", name or "").lower()
    core = re.sub(r"【[^】]*】|\[[^\]]*\]|\([^)]*\)", " ", s)
    key = re.sub(r"[\W_]+", "", re.sub(r"\bv?\d+(?:\.\d+)*\b", " ", core))
    if len(key) < 4:
        key = re.sub(r"[\W_]+", "", s)
    if not key:  # a name made only of symbols
        key = "x" + hashlib.sha1(s.encode()).hexdigest()[:16]
    return f"{store.lower()}:{key[:300]}"


def clean_tag(value) -> str:
    """A tag as it's stored: lower case, letters, digits, spaces and - _ . + & ' only, at most 40 characters.

    Everything else, including invisible characters, commas, # and angle brackets, becomes a space, so
    tags are safe wherever they end up (the pages, the address bar, asset.json and other programs).
    """
    t = unicodedata.normalize("NFKC", value if isinstance(value, str) else "").lower()
    t = "".join(c if unicodedata.category(c)[0] in "LMN" or c in TAG_PUNCTUATION else " " for c in t)
    t = re.sub(r"\s+", " ", t).strip(TAG_PUNCTUATION)[:TAG_MAX_LENGTH].strip(TAG_PUNCTUATION)
    return "" if t in TAG_RESERVED else t


def name_has_word(name: str, word: str) -> bool:
    """True when an item's name contains word on its own (plurals and joined-up CamelCase count)."""
    text = unicodedata.normalize("NFKC", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name or "")).lower()
    if word.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?:s|es)?(?![a-z0-9])", text) is not None
    return word in text  # Japanese and other scripts don't separate words with spaces


@contextlib.contextmanager
def _file_lock(path: Path, timeout: float = 10.0):
    """Hold an OS lock on path for the duration, so the two tools never save tags at the same moment."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    deadline = time.time() + timeout
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() > deadline:
                    raise TimeoutError("The other Hoard tool is saving tags right now. Try again in a moment.")
                time.sleep(0.05)
        yield
    finally:
        if os.name == "nt":
            try:
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        fh.close()


class TagStore:
    """Your tags. Every change re-reads tags.json under a lock, so both tools can edit them safely.

    tags.json holds:
      tags      {name: {"match": word or null}}   every tag you have, even ones on no items yet
      items     {tag_key: [tag, ...]}              tags you put on items
      excluded  {tag_key: [tag, ...]}              matched tags you took off an item
      hidden    [word, ...]                        suggestions you hid
    """

    def __init__(self, path: Path | None = None):
        """Use tags.json in Hoard's app-data folder, or another file (for tests)."""
        self.path = path or tags_file()

    @staticmethod
    def empty() -> dict:
        """A tag file with nothing in it."""
        return {"version": 1, "tags": {}, "items": {}, "excluded": {}, "hidden": []}

    @staticmethod
    def sanitize(raw) -> dict:
        """Keep only well-formed content from a tags file: clean names, valid product keys, within the limits."""
        data = TagStore.empty()
        if not isinstance(raw, dict):
            return data
        tags = raw.get("tags") if isinstance(raw.get("tags"), dict) else {}
        matching, renamed = 0, {}
        for name, info in list(tags.items())[:TAG_LIMITS["tags"]]:
            # a name older versions allowed but the rules no longer do is converted, not lost ("fox/dog" -> "fox dog")
            new = clean_tag(name) if isinstance(name, str) else ""
            if not new:
                continue
            renamed[name] = new
            match = info.get("match") if isinstance(info, dict) else None
            match = clean_tag(match) if isinstance(match, str) else ""
            if match and matching >= TAG_LIMITS["matching"]:
                match = ""
            if new in data["tags"]:  # two old names became one: keep the first's match unless it had none
                match = data["tags"][new]["match"] or match
                matching -= bool(data["tags"][new]["match"])
            matching += bool(match)
            data["tags"][new] = {"match": match or None}
        for field in ("items", "excluded"):
            mapping = raw.get(field) if isinstance(raw.get(field), dict) else {}
            for key, names in list(mapping.items())[:TAG_LIMITS["tagged_items"]]:
                if isinstance(key, str) and TAG_KEY_RX.match(key) and isinstance(names, list):
                    keep = sorted({renamed[t] for t in names[:TAG_LIMITS["per_item"]] if isinstance(t, str) and t in renamed})
                    if keep:
                        data[field][key] = keep
        hidden = raw.get("hidden") if isinstance(raw.get("hidden"), list) else []
        data["hidden"] = sorted({w for w in hidden[:TAG_LIMITS["tags"]] if isinstance(w, str) and w and clean_tag(w) == w})
        return data

    def load(self) -> dict:
        """The saved tags, checked, or an empty set when there's no file yet or it can't be read."""
        try:
            return self.sanitize(read_json_file(self.path, 16 * 1024 * 1024))
        except (OSError, DataFileError):
            return self.empty()

    def _save(self, data: dict) -> None:
        """Write tags.json safely; on Linux and macOS only you can read it."""
        write_file_safely(self.path, json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True))
        if os.name == "posix":
            os.chmod(self.path, 0o600)
            os.chmod(self.path.parent, 0o700)

    @staticmethod
    def tags_for(data: dict, key: str, name: str) -> list[str]:
        """The tags an item has: the ones you gave it, plus matching ones, minus any you took off it."""
        mine = {t for t in data["items"].get(key, []) if t in data["tags"]}
        auto = {t for t, info in data["tags"].items() if (info or {}).get("match") and name_has_word(name, info["match"])}
        return sorted((mine | auto) - set(data["excluded"].get(key, [])))

    def change(self, body: dict) -> None:
        """Apply one change from the page. Raises ValueError with a readable message when it doesn't make sense."""
        if not isinstance(body, dict):
            raise ValueError("Unknown tag change.")
        action = body.get("action")
        with _tag_lock, _file_lock(self.path.with_suffix(".lock")):
            data = self.empty()
            if self.path.exists():
                try:
                    data = self.sanitize(read_json_file(self.path, 16 * 1024 * 1024))
                except DataFileError:
                    set_aside(self.path)  # keep the damaged file rather than overwrite it
            self._apply(data, action, body)
            self._save(data)

    @staticmethod
    def _apply(data: dict, action, body: dict) -> None:
        """Make one change to the loaded tags. See change() for the actions."""
        tags, items, excluded = data["tags"], data["items"], data["excluded"]
        name = clean_tag(body.get("name"))

        def need(value, what="a tag name"):
            if not value:
                raise ValueError(f"Give {what}.")
            return value

        def drop(mapping, key, tag):
            left = [t for t in mapping.get(key, []) if t != tag]
            if left:
                mapping[key] = left
            else:
                mapping.pop(key, None)

        if action == "assign":
            given = body.get("keys") if isinstance(body.get("keys"), list) else []
            if len(given) > TAG_LIMITS["keys_per_change"]:
                raise ValueError(f"Tag at most {TAG_LIMITS['keys_per_change']} items at a time.")
            keys = [k for k in given if isinstance(k, str) and TAG_KEY_RX.match(k)]
            add = [t for t in (clean_tag(v) for v in (body.get("add") or [])[:20]) if t]
            remove = [t for t in (clean_tag(v) for v in (body.get("remove") or [])[:20]) if t]
            if not keys or not (add or remove):
                raise ValueError("Choose items and a tag.")
            if len(set(tags) | set(add)) > TAG_LIMITS["tags"]:
                raise ValueError(f"That's more than {TAG_LIMITS['tags']} tags. Delete some first.")
            if len(set(items) | set(keys)) > TAG_LIMITS["tagged_items"] and add:
                raise ValueError("That's more tagged items than Hoard can keep.")
            for t in add:
                tags.setdefault(t, {"match": None})
            for key in keys:
                for t in add:
                    items[key] = sorted(set(items.get(key, [])) | {t})
                    drop(excluded, key, t)
                if len(items.get(key, [])) > TAG_LIMITS["per_item"]:
                    raise ValueError(f"An item can have at most {TAG_LIMITS['per_item']} tags.")
                for t in remove:
                    drop(items, key, t)
                    if (tags.get(t) or {}).get("match"):  # keep a matching tag off this item from now on
                        excluded[key] = sorted(set(excluded.get(key, [])) | {t})
        elif action == "create":
            tags.setdefault(need(name), {"match": None})
            if len(tags) > TAG_LIMITS["tags"]:
                raise ValueError(f"That's more than {TAG_LIMITS['tags']} tags. Delete some first.")
        elif action == "keep":  # a suggestion becomes your tag, matched by its word
            need(name)
            if len(set(tags) | {name}) > TAG_LIMITS["tags"]:
                raise ValueError(f"That's more than {TAG_LIMITS['tags']} tags. Delete some first.")
            tags[name] = {"match": name}
            data["hidden"] = [w for w in data["hidden"] if w != name]
        elif action == "match":
            if need(name) not in tags:
                raise ValueError(f"There's no tag called {name}.")
            tags[name] = {"match": clean_tag(body.get("match")) or None}
        elif action == "rename":
            new = need(clean_tag(body.get("to")), "a new name")
            if need(name) not in tags:
                raise ValueError(f"There's no tag called {name}.")
            if new != name:
                old_info = tags.pop(name)
                tags.setdefault(new, old_info)  # renaming onto an existing tag merges the two
                if not (tags[new] or {}).get("match") and (old_info or {}).get("match"):
                    tags[new] = old_info
                for mapping in (items, excluded):
                    for key in list(mapping):
                        if name in mapping[key]:
                            mapping[key] = sorted((set(mapping[key]) - {name}) | {new})
        elif action == "delete":
            tags.pop(need(name), None)
            for mapping in (items, excluded):
                for key in list(mapping):
                    drop(mapping, key, name)
        elif action == "hide":
            if need(name) not in data["hidden"]:
                data["hidden"] = sorted(data["hidden"] + [name])
        elif action == "unhide":
            data["hidden"] = [w for w in data["hidden"] if w != need(name)]
        else:
            raise ValueError("Unknown tag change.")
        if sum(1 for info in tags.values() if (info or {}).get("match")) > TAG_LIMITS["matching"]:
            raise ValueError(f"At most {TAG_LIMITS['matching']} tags can match names. Turn matching off on some first.")
        if len(data["hidden"]) > TAG_LIMITS["tags"]:
            raise ValueError("That's too many hidden suggestions.")


def tag_overview(data: dict, entries: list[dict]) -> dict:
    """What the page's tag manager shows: every tag with its item count and match word, suggestions, hidden words."""
    counts: dict[str, int] = {}
    sugg: dict[str, int] = {}
    for e in entries:
        for t in e["tags"]:
            counts[t] = counts.get(t, 0) + 1
        for t in e["suggested"]:
            sugg[t] = sugg.get(t, 0) + 1
    return {
        "file": str(tags_file()),
        "tags": sorted(({"name": t, "match": (info or {}).get("match"), "count": counts.get(t, 0)}
                        for t, info in data["tags"].items()), key=lambda x: (-x["count"], x["name"])),
        "suggestions": sorted(({"name": t, "count": n} for t, n in sugg.items()), key=lambda x: (-x["count"], x["name"])),
        "hidden": sorted(data["hidden"]),
    }
