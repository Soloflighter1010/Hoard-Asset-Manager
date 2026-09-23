#!/usr/bin/env python3
"""
Hoard Downloader - download everything you own on Booth, Gumroad, Jinxxy and Payhip.

Layout under the configured root:
    Booth/<Creator>/<Product>/...files        + Booth/_manifest.json
    Gumroad/<Creator>/<Product>/...files      + Gumroad/_manifest.json
    Jinxxy/<Creator>/<Product>/...files       + Jinxxy/_manifest.json
    Payhip/<Creator>/<Product>/...files       + Payhip/_manifest.json
    catalog.json   every asset from every store, with suggested tags
    tags.json      tag -> assets, built from words that recur across asset names

Each store keeps its own manifest, so re-running only fetches files that are new
or changed, and a product that's renamed on the store keeps its existing folder.

    python asset_dl.py login booth        one-time per store: sign in inside the browser window
    python asset_dl.py sync               every store you're signed in to (--store, --dry-run, --only TEXT)
    python asset_dl.py sync --store payhip --payhip-page "Payhip library.mhtml"
    python asset_dl.py tags               rebuild catalog.json / tags.json without downloading
    python asset_dl.py browse             search and browse everything in your web browser
    python asset_dl.py probe jinxxy       dump what the Jinxxy site loads, for tuning its adapter
"""
from __future__ import annotations

import argparse
import email
import html
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests

try:
    from tqdm import tqdm
except ImportError:  # progress bars are optional
    tqdm = None

__version__ = "1.6.2"

HERE = Path(__file__).resolve().parent
PROBE_DIR = HERE / "probe-output"

GR_BASE = "https://app.gumroad.com"
GR_LIBRARY = GR_BASE + "/library"
GR_LOGIN = GR_BASE + "/login"
JX_BASE = "https://jinxxy.com"
JX_INVENTORY = JX_BASE + "/my/inventory"

DEFAULT_CONFIG = {
    "root": "downloads",
    "request_delay": 1.0,
    "browser_channel": "",  # "" = Playwright's Chromium; "chrome" / "msedge" = your installed browser
    "profile_dir": "",      # "" = Hoard's private sign-in folder (one profile per store), shared by both tools
    "allow_unprotected_signins": False,  # Linux without a keyring only: save sign-ins protected by folder permissions
    "gumroad": {
        "enabled": True,
        "include_archived": True,
        "save_thumbnails": True,
    },
    "jinxxy": {
        "enabled": True,
        "item_link_pattern": r"^/my/(inventory|purchases|library)/[^/]+/?$",
        "save_thumbnails": True,
        "download_start_timeout": 90,
    },
    "booth": {
        "enabled": True,
        "include_gifts": True,
        "save_thumbnails": True,
    },
    "payhip": {
        "enabled": True,
        "library_url": "",      # leave empty to find it automatically
        "headed": True,         # a visible window, so you can complete Payhip's bot check
        "bot_check_wait": 180,  # seconds to wait for you to complete it
        "download_start_timeout": 90,
        "save_thumbnails": True,
    },
    "tags": {
        "min_count": 3,        # a word must appear in at least this many asset names
        "max_share": 0.4,      # ...and in no more than this fraction of them (drops filler)
        "min_length": 2,
        "extra_stopwords": [],
        "blocklist": [],
    },
}

STOPWORDS = set("""
a an and are as at be by for from in into is it its of on or the to with without your you my our
this that these those v ver version update updated new free paid full set pack bundle edition
package unitypackage zip file files ft feat x vs vrchat vrc
""".split())

WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class NotLoggedIn(Exception):
    """The store sent its sign-in page instead of your purchases."""
    pass


# ----------------------------------------------------------------------------- helpers

def log(msg: str) -> None:
    """Print a progress line straight away, so it shows up while long downloads run."""
    print(msg, flush=True)


def now_iso() -> str:
    """The current time in UTC, as an ISO 8601 string with seconds."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_name(value, maxlen: int = 80) -> str:
    """Make a string safe as a single Windows/Linux path component."""
    s = unicodedata.normalize("NFC", str(value or ""))
    # Invisible formatting characters go entirely: a right-to-left override could make "photo\u202egpj.exe"
    # show as "photoexe.jpg". Control characters and characters Windows forbids become "_".
    s = "".join(c for c in s if unicodedata.category(c) == "Cc" or unicodedata.category(c)[0] != "C")
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', "_", s)
    s = re.sub(r"\s+", " ", s).strip().strip(".").strip()
    if not s:
        s = "_"
    if s.split(".")[0].upper() in WIN_RESERVED:
        s = "_" + s
    if len(s) > maxlen:
        stem, dot, ext = s.rpartition(".")
        if dot and stem and 0 < len(ext) <= 16:
            s = stem[: maxlen - len(ext) - 1].rstrip(" .") + "." + ext
        else:
            s = s[:maxlen].rstrip(" .")
    return s


# ----------------------------------------------------------------------------- data files
#
# Everything these tools write (manifests, catalog.json, tags.json, asset.json, the library list, your
# tags, images) may be read back later, by these tools or by other programs such as a Unity plugin, and
# may sit somewhere others can reach, like a shared drive. So text from stores is cleaned before it's
# stored, data files are read defensively, and files are written in a way that can't be redirected.

MAX_DATA_FILE = 64 * 1024 * 1024  # no data file these tools write is anywhere near this


class DataFileError(ValueError):
    """A data file that's too large, isn't valid JSON, or is nested absurdly deep."""


def clean_text(value, limit: int = 300) -> str:
    """Text from a store or a data file, made safe to show and to store.

    Control characters and invisible formatting characters (such as right-to-left overrides and
    zero-width spaces, which can make a name look like something else) are removed, runs of
    whitespace become single spaces, and the result is at most `limit` characters.
    """
    s = unicodedata.normalize("NFC", value if isinstance(value, str) else "" if value is None else str(value))
    s = "".join(" " if unicodedata.category(c) == "Cc" else "" if unicodedata.category(c)[0] == "C" else c for c in s)
    return re.sub(r"\s+", " ", s).strip()[:limit].strip()


def read_json_file(path: Path, max_bytes: int = MAX_DATA_FILE):
    """Read a JSON data file defensively, raising DataFileError when it's too big or damaged."""
    size = path.stat().st_size
    if size > max_bytes:
        raise DataFileError(f"{path.name} is unexpectedly large ({size // 1048576} MB)")
    try:
        return json.loads(path.read_text("utf-8"))
    except (ValueError, RecursionError, UnicodeDecodeError) as e:
        raise DataFileError(f"{path.name} is damaged ({e.__class__.__name__})") from None


def set_aside(path: Path) -> Path:
    """Rename a damaged data file out of the way (keeping it, in case it matters) and return its new path."""
    aside = path.with_name(f"{path.stem}.damaged-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}")
    os.replace(path, aside)
    return aside


def write_file_safely(path: Path, data, root: Path | None = None) -> None:
    """Write a file through a new temporary file in the same folder, then swap it into place.

    A reader never sees half a file, and a symlink planted where the file goes is replaced rather than
    followed. With root, the file's folder must also really be inside root (checked after resolving links).
    """
    if root is not None:
        base, folder = root.resolve(), path.parent.resolve()
        if folder != base and base not in folder.parents:
            raise PermissionError(f"refused to write {path}: its folder leads outside {root}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)  # created new, so never a planted link
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode("utf-8") if isinstance(data, str) else data)
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Windows: another program is reading the old file this instant
                if attempt == 9:
                    raise
                time.sleep(0.2)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# Every link to a store must lead to that store's own website (or a subdomain of it, such as a Booth
# shop's <shop>.booth.pm), over HTTPS. Hoard never downloads from a stored link; they're only for you to
# open, so this is what stops an edited record turning "Open on Booth" into a lookalike sign-in page.
STORE_LINK_SITES = {"booth": ("booth.pm",), "gumroad": ("gumroad.com",), "jinxxy": ("jinxxy.com",), "payhip": ("payhip.com",)}


def store_link(store, url) -> str | None:
    """url if it's an https address on the given store's own website, otherwise None."""
    if not isinstance(url, str) or not isinstance(store, str):
        return None
    url = url.strip()
    try:
        u = urlparse(url)
        port = u.port
    except ValueError:
        return None
    host = (u.hostname or "").rstrip(".")
    if u.scheme != "https" or u.username or u.password or port not in (None, 443) or not host.isascii():
        return None
    return url if any(host == s or host.endswith("." + s) for s in STORE_LINK_SITES.get(store.lower(), ())) else None


# Seals. The tools seal each data file they write (manifests, the catalog files, Hoard's library list)
# with an HMAC-SHA256 keyed by a random key kept private to your user account. Reading a file back, a
# broken or missing seal means something else edited it, so its links aren't trusted until they're
# fetched from the store again. docs/DATA-FORMATS.md describes the seal for other programs.
_integrity_key: bytes | None = None
_sealed_ids: set | None = None


def _hoard_folder() -> Path:
    """Hoard's private folder in this user account's app data."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Hoard"


def integrity_key() -> bytes:
    """This install's sealing key: 32 random bytes, made on first use, readable only by your account."""
    global _integrity_key
    if _integrity_key:
        return _integrity_key
    path = _hoard_folder() / "integrity.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    for _attempt in range(3):
        try:
            key = bytes.fromhex(path.read_text("ascii").strip())
            if len(key) == 32:
                _integrity_key = key
                return key
            set_aside(path)  # not a key these tools made: keep it, and make a new one
        except FileNotFoundError:
            pass
        except (ValueError, UnicodeDecodeError):
            set_aside(path)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(secrets.token_hex(32))
        except FileExistsError:
            pass  # the other tool made one a moment ago: use theirs
    raise OSError(f"Couldn't read or create {path}")


def _canonical(obj) -> bytes:
    """The exact bytes a seal covers: JSON with sorted keys, no spaces, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:16]


def seal(obj: dict) -> dict:
    """obj plus an "integrity" field sealing everything else in it."""
    body = {k: v for k, v in obj.items() if k != "integrity"}
    key = integrity_key()
    return {**body, "integrity": {"alg": "HMAC-SHA256", "key_id": _key_id(key),
                                  "mac": hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()}}


def _path_id(path: Path) -> str:
    return hashlib.sha256(os.path.normcase(os.path.realpath(path)).encode("utf-8", "surrogatepass")).hexdigest()[:32]


def _sealed_file_ids() -> set:
    """Which files this install has sealed (by a hash of their location), so a removed seal is noticed."""
    global _sealed_ids
    if _sealed_ids is None:
        try:
            data = read_json_file(_hoard_folder() / "sealed-files.json", 4 * 1024 * 1024)
            _sealed_ids = {x for x in data.get("files", []) if isinstance(x, str)} if isinstance(data, dict) else set()
        except (OSError, DataFileError):
            _sealed_ids = set()
    return _sealed_ids


def remember_sealed(path: Path) -> None:
    """Note that this install has sealed the file at path."""
    ids = _sealed_file_ids()
    pid = _path_id(path)
    if pid not in ids:
        ids.add(pid)
        write_file_safely(_hoard_folder() / "sealed-files.json", json.dumps({"files": sorted(ids)[-20000:]}))


def check_seal(obj, path: Path | None = None) -> str:
    """How far to trust a data file just read.

    "sealed": this install wrote it and nothing has changed it. "unsealed": it has no seal and this install
    never sealed it (written by an older version). "foreign": another install sealed it (say, Hoard on a
    second computer sharing the folder). "changed": edited after this install sealed it, or its seal removed.
    """
    if not isinstance(obj, dict) or not isinstance(obj.get("integrity"), dict):
        return "changed" if path is not None and _path_id(path) in _sealed_file_ids() else "unsealed"
    info, key = obj["integrity"], integrity_key()
    if info.get("key_id") != _key_id(key):
        return "foreign"
    body = {k: v for k, v in obj.items() if k != "integrity"}
    expected = hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()
    return "sealed" if hmac.compare_digest(expected, str(info.get("mac"))) else "changed"


class UnsafePath(ValueError):
    """A path from a data file that isn't a plain relative path inside its folder."""


def valid_rel(rel) -> bool:
    """True for a relative path written with /, made only of plain names: no "..", drives, streams or hidden characters."""
    if not isinstance(rel, str) or not rel or len(rel) > 1000 or rel.startswith("/"):
        return False
    for part in rel.split("/"):
        if (part in ("", ".", "..") or part != part.strip() or re.search(r'[<>:"\\|?*\x00-\x1f\x7f-\x9f]', part)
                or any(unicodedata.category(c)[0] == "C" for c in part)):
            return False
    return True


def rel_to_path(base: Path, rel: str) -> Path:
    """Turn a path from a data file (always written with /) into a real path inside base.

    Raises UnsafePath when the path isn't plain, or leads outside base, including through a symlink.
    """
    if not valid_rel(rel):
        raise UnsafePath(f"refused the path {rel!r}")
    path = base.joinpath(*rel.split("/"))
    inside, target = base.resolve(), path.resolve()
    if target != inside and inside not in target.parents:
        raise UnsafePath(f"refused {rel!r}: it leads outside {base}")
    return path


def no_link(path: Path) -> Path:
    """Remove a symlink planted where a file is about to be written, so writing can't follow it."""
    if path.is_symlink():
        path.unlink()
    return path


def clean_manifest(data, store_dir: Path, trust_links: bool = True) -> tuple[dict, int]:
    """Keep only well-formed manifest records whose folder and files stay inside the store's folder.

    Text is cleaned, and a record's link is kept only when it leads to that store's own website and the
    manifest is trusted (see check_seal); otherwise it's dropped until the next sync fetches it again.
    Returns the cleaned data and how many entries were dropped.
    """
    store = store_dir.name.lower()
    assets = data.get("assets") if isinstance(data, dict) and isinstance(data.get("assets"), dict) else {}
    kept, dropped = {}, 0
    for key, rec in assets.items():
        try:
            if not isinstance(key, str) or len(key) > 500 or not isinstance(rec, dict):
                raise UnsafePath("malformed record")
            folder_path = rel_to_path(store_dir, rec.get("folder"))
        except UnsafePath:
            dropped += 1
            continue
        files = {}
        for fk, f in (rec.get("files") if isinstance(rec.get("files"), dict) else {}).items():
            if isinstance(fk, str) and len(fk) <= 500 and isinstance(f, dict):
                try:
                    rel_to_path(folder_path, f.get("path"))
                    files[fk] = f
                except UnsafePath:
                    dropped += 1
        rec = {**rec, "files": files, "name": clean_text(rec.get("name"), 300) or "Untitled",
               "creator": clean_text(rec.get("creator"), 200) or "Unknown creator",
               "url": store_link(store, rec.get("url")) if trust_links else None}
        if rec.get("variants") is not None:
            rec["variants"] = clean_text(rec["variants"], 300) or None
        kept[key] = rec
    rest = {k: v for k, v in (data.items() if isinstance(data, dict) else []) if k not in ("assets", "integrity")}
    return {**rest, "assets": kept}, dropped


def deep_merge(dst: dict, src: dict) -> dict:
    """Copy src into dst, merging nested dicts instead of replacing them. Returns dst."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_config(path: Path) -> dict:
    """The built-in defaults, overlaid with config.json when it exists."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.exists():
        deep_merge(cfg, json.loads(path.read_text("utf-8")))
    else:
        log(f"(no config found at {path} - using defaults; copy config.example.json to config.json to change them)")
    return cfg


def root_dir(cfg: dict) -> Path:
    """The download folder from config.json. A relative path is taken from this program's folder."""
    root = Path(os.path.expandvars(cfg["root"])).expanduser()
    return root if root.is_absolute() else HERE / root


@dataclass
class Report:
    """Tally of one sync: new, updated, skipped and failed items, printed as a summary at the end."""
    new_assets: list = field(default_factory=list)
    new_files: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    failed: list = field(default_factory=list)

    def print(self) -> None:
        """Print the summary, then the updated, skipped and failed items one per line."""
        log("\n=== Summary ===")
        log(f"New assets: {len(self.new_assets)}   New files: {len(self.new_files)}   "
            f"Updated files: {len(self.updated)}   Skipped: {len(self.skipped)}   Failed: {len(self.failed)}")
        for title, items in (("Updated on the store since last sync", self.updated),
                             ("Skipped", self.skipped), ("Failed", self.failed)):
            if items:
                log(f"\n{title}:")
                for line in items:
                    log(f"  - {line}")


class Manifest:
    """Per-store record of what's been downloaded and where."""

    def __init__(self, store_dir: Path):
        """Load a store's manifest, or start an empty one."""
        self.store_dir = store_dir
        self.path = store_dir / "_manifest.json"
        raw, trusted = {}, True
        if self.path.exists():
            try:
                raw = read_json_file(self.path)
                trusted = self._check(raw)
            except DataFileError as e:
                aside = set_aside(self.path)
                log(f"{store_dir.name}: {e}, so it was kept as {aside.name} and a new record started. "
                    "Files already on disk are kept.")
        self.data, dropped = clean_manifest(raw, store_dir, trust_links=trusted)
        if dropped:
            log(f"{store_dir.name}: ignored {dropped} entries in _manifest.json that pointed outside {store_dir} "
                "or weren't valid. Check who else can change that folder.")
        self.assets: dict = self.data.setdefault("assets", {})

    def _check(self, raw) -> bool:
        """Check the manifest's seal, say what it means, and return whether its links can be trusted."""
        status = check_seal(raw, self.path)
        name = self.store_dir.name
        if status == "changed":
            copy = self.path.with_name(f"_manifest.changed-{time.strftime('%Y%m%d-%H%M%S')}.json")
            shutil.copy2(self.path, copy)
            log(f"{name}: _manifest.json was changed by something other than Hoard Downloader since it last saved it. "
                f"Its store links won't be used until this sync fetches them from {name} again. A copy is kept as "
                f"{copy.name}. Check what else can change {self.store_dir}.")
        elif status == "foreign":
            log(f"{name}: _manifest.json was last saved by Hoard Downloader on another computer, so its store links will "
                f"be fetched from {name} again. To share this folder between computers, copy integrity.key from Hoard's "
                "app-data folder on one to the other.")
        return status in ("sealed", "unsealed")

    def save(self) -> None:
        """Seal the manifest and write it through a temporary file, so a crash can't leave it half-written."""
        write_file_safely(self.path, json.dumps(seal(self.data), indent=2, ensure_ascii=False))
        remember_sealed(self.path)

    def record(self, key: str, creator: str, name: str) -> dict:
        """Existing record for a product, or a new one with a folder no other product uses."""
        if key in self.assets:
            return self.assets[key]
        used = {a.get("folder") for a in self.assets.values()}
        base = f"{safe_name(creator)}/{safe_name(name)}"
        folder, n = base, 2
        while folder in used:
            folder, n = f"{base} ({n})", n + 1
        rec = {"key": key, "name": name, "creator": creator, "folder": folder,
               "files": {}, "first_seen": now_iso()}
        self.assets[key] = rec
        return rec


def http_download(sess: requests.Session, url: str, dest: Path, desc: str = "") -> int:
    """Stream url to dest via a .part file, resuming a previous partial download if possible."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = no_link(dest.with_name(dest.name + ".part"))
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with sess.get(url, stream=True, headers=headers, timeout=(20, 300)) as r:
        if have and r.status_code == 416:  # .part was already complete
            os.replace(part, dest)
            return dest.stat().st_size
        if have and r.status_code == 206:
            mode = "ab"
        else:
            r.raise_for_status()
            mode, have = "wb", 0
        ctype = r.headers.get("Content-Type", "")
        if ctype.startswith("text/html") and not dest.suffix.lower().startswith(".htm"):
            raise RuntimeError("store returned a web page instead of the file (file may be unavailable)")
        total = int(r.headers.get("Content-Length", 0) or 0) + have
        bar = tqdm(total=total or None, initial=have, unit="B", unit_scale=True, unit_divisor=1024,
                   desc=desc[:40], leave=False) if tqdm else None
        with open(part, mode) as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                if bar:
                    bar.update(len(chunk))
        if bar:
            bar.close()
    os.replace(part, dest)
    return dest.stat().st_size


# ----------------------------------------------------------------------------- browser

def _playwright():
    """Import Playwright's sync API, or exit with a clear message when setup hasn't been run."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright isn't installed. Run Setup.bat (Windows) or ./setup.sh first.")
    return sync_playwright


# ----------------------------------------------------------------------------- sign-ins
#
# Each store's sign-in lives in its own browser profile, used by Hoard alone (never your everyday
# browser), in your user account's private app-data folder: Hoard/sign-ins/<store>. Keeping stores
# apart means one store's pages never share a browser with another store's sign-in, signing out of a
# store deletes that store's folder outright, and the two tools can work with different stores at once.
#
# The browser encrypts saved cookies with the operating system's protection: your Windows account
# (DPAPI), the macOS Keychain, or a Linux keyring (the Secret Service or KWallet). On a Linux computer
# without a keyring the browser would fall back to a publicly known key, so Hoard refuses to save
# sign-ins there unless you allow it in config.json ("allow_unprotected_signins").

LEGACY_PROFILE = HERE / ".browser-profile"   # before 1.2: one profile next to the program
STORE_SITES = {
    "booth": ["booth.pm", "pixiv.net"],        # Booth signs in through pixiv
    "gumroad": ["gumroad.com"],
    "jinxxy": ["jinxxy.com"],
    "payhip": ["payhip.com"],
}
STORE_ORIGINS = {
    "booth": ["https://booth.pm", "https://accounts.booth.pm", "https://www.pixiv.net", "https://accounts.pixiv.net"],
    "gumroad": ["https://gumroad.com", "https://app.gumroad.com"],
    "jinxxy": ["https://jinxxy.com", "https://www.jinxxy.com"],
    "payhip": ["https://payhip.com"],
}
# Pages that show whether you're signed in (a sign-in form means you're not), and where to sign out.
STORE_ACCOUNT_PAGES = {
    "booth": "https://accounts.booth.pm/library",
    "gumroad": "https://app.gumroad.com/library",
    "jinxxy": "https://jinxxy.com/my/inventory",
    "payhip": "https://payhip.com/account",
}
GUMROAD_SIGN_OUT = "https://app.gumroad.com/logout"   # Gumroad's own sign-out address
SIGN_OUT_JS = r"""
() => {
  const label = /^(log ?out|sign ?out|ログアウト)$/i;
  const items = [...document.querySelectorAll('a, button, [role="menuitem"], input[type="submit"]')];
  const el = items.find(e => label.test((e.innerText || e.value || e.getAttribute('aria-label') || '').trim()))
    || items.find(e => /log_?out|sign_?out/i.test(e.getAttribute('href') || ''));
  if (!el) return false;
  setTimeout(() => el.click(), 0);
  return true;
}
"""
# Playwright normally starts Chromium with a fixed, publicly known cookie key on Linux and macOS.
# Dropping these two switches lets Chromium use the real keyring or Keychain instead.
WEAK_KEY_SWITCHES = ["--password-store=basic", "--use-mock-keychain"]


class ProfileBusy(Exception):
    """The other Hoard tool is using this store's sign-in right now."""


class SigninsUnprotected(Exception):
    """This computer has no keyring to protect sign-ins, and unprotected ones aren't allowed."""


def app_data_dir() -> Path:
    """Hoard's folder in this user account's private app-data location, per operating system."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Hoard"


def signins_root(cfg: dict) -> Path:
    """The folder holding one profile per store. config.json's profile_dir can move it."""
    value = (cfg.get("profile_dir") or "").strip()
    if value and Path(value).name != ".browser-profile":  # that name was the pre-1.2 default: ignore it
        p = Path(os.path.expandvars(value)).expanduser()
        return p if p.is_absolute() else HERE / p
    return app_data_dir() / "sign-ins"


def profile_dir(cfg: dict, store: str) -> Path:
    """Where one store's sign-in is kept."""
    return signins_root(cfg) / store


def _lock_down(path: Path) -> None:
    """Create a folder and, on Linux and macOS, make it and Hoard's folder readable only by you."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":  # Windows keeps app data private to your account already
        for p in (path, path.parent, path.parent.parent):
            if p.name in ("Hoard", "sign-ins") or p == path:
                os.chmod(p, 0o700)


class ProfileLock:
    """Keeps two Hoard programs from using one store's sign-in at once. The OS drops it if a program crashes."""

    def __init__(self, profile: Path):
        """Prepare a lock file next to the profile; nothing is locked until acquire()."""
        self.path = profile.parent / (profile.name + ".lock")
        self.fh = None

    def acquire(self) -> None:
        """Lock the sign-in for this program, or raise ProfileBusy if another program has it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            self.fh = None
            raise ProfileBusy(f"The other Hoard tool is using your {self.path.stem.title()} sign-in right now. "
                              "Try again when it has finished.")

    def release(self) -> None:
        """Unlock the sign-in. Safe to call more than once."""
        if self.fh:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.fh.seek(0)
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
                self.fh.close()
            except OSError:
                pass
            self.fh = None


def _remove_tree(path: Path) -> None:
    """Delete a folder tree, clearing read-only flags that would otherwise stop Windows deleting it."""
    def retry(func, p, _exc):
        os.chmod(p, 0o700)
        func(p)
    shutil.rmtree(path, onerror=retry)


def _dbus_names() -> set[str]:
    """Names on the desktop's D-Bus session bus, running or startable on demand. Empty without one."""
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return set()
    names: set[str] = set()
    for method in ("ListNames", "ListActivatableNames"):
        for cmd in (["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
                     "/org/freedesktop/DBus", "--method", f"org.freedesktop.DBus.{method}"],
                    ["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.DBus",
                     "/org/freedesktop/DBus", f"org.freedesktop.DBus.{method}"]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            names |= {a or b for a, b in re.findall(r"'([\w.]+)'|\"([\w.]+)\"", out)}
            break
    return names


def linux_keyring() -> str | None:
    """The keyring Chromium can use on this Linux desktop ("gnome-libsecret" or "kwallet5/6"), or None."""
    if not sys.platform.startswith("linux"):
        return None
    names = _dbus_names()
    if "org.freedesktop.secrets" in names:        # GNOME Keyring, KeePassXC and other Secret Service keyrings
        return "gnome-libsecret"
    if "org.kde.kwalletd6" in names:
        return "kwallet6"
    if "org.kde.kwalletd5" in names:
        return "kwallet5"
    return None


def signin_protection(cfg: dict) -> str:
    """How saved sign-ins are protected on this computer, in words."""
    if sys.platform == "win32":
        return "encrypted by your Windows account"
    if sys.platform == "darwin":
        return "encrypted with your macOS Keychain"
    keyring = linux_keyring()
    if keyring:
        return "encrypted with your " + ("KWallet" if keyring.startswith("kwallet") else "Secret Service keyring")
    if cfg.get("allow_unprotected_signins"):
        return "protected only by folder permissions, because this computer has no keyring"
    return "not saved, because this computer has no keyring to protect them"


def _cookie_rows(profile: Path, query: str) -> list:
    """Run a read-only query on a profile's cookie database (a copy, so a running browser isn't disturbed)."""
    import sqlite3
    import tempfile
    for rel in ("Default/Network/Cookies", "Default/Cookies"):
        db = profile / rel
        if db.is_file():
            with tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp) / "Cookies"
                shutil.copyfile(db, copy)
                con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
                try:
                    return con.execute(query).fetchall()
                except sqlite3.Error:
                    return []
                finally:
                    con.close()
    return []


def unprotected_cookie_count(profile: Path) -> int:
    """On Linux, how many saved cookies use the browser's fixed fallback key ("v10") instead of a keyring ("v11")."""
    if not sys.platform.startswith("linux"):
        return 0
    rows = _cookie_rows(profile, "SELECT encrypted_value, value FROM cookies")
    return sum(1 for enc, plain in rows if (bytes(enc or b"")[:3] == b"v10") or (plain or ""))


def _cookie_hosts(profile: Path) -> set[str]:
    """The sites a profile holds cookies for."""
    return {h.lstrip(".") for (h,) in _cookie_rows(profile, "SELECT DISTINCT host_key FROM cookies")}


def _on_sites(host: str, sites: list[str]) -> bool:
    """True when host is one of the sites, or a subdomain of one."""
    host = host.lstrip(".")
    return any(host == s or host.endswith("." + s) for s in sites)


def _launch(p, cfg: dict, profile: Path, headless: bool):
    """Start Chromium on a profile with the strongest cookie protection this computer offers."""
    kwargs = dict(user_data_dir=str(profile), headless=headless, accept_downloads=True,
                  viewport={"width": 1400, "height": 950}, ignore_default_args=WEAK_KEY_SWITCHES)
    if sys.platform.startswith("linux"):
        keyring = linux_keyring()
        if keyring:
            kwargs["args"] = [f"--password-store={keyring}"]
        elif cfg.get("allow_unprotected_signins"):
            kwargs["args"] = ["--password-store=basic"]   # the user chose this in config.json
        else:
            raise SigninsUnprotected(
                "This computer has no keyring to protect store sign-ins, so Hoard won't save them. Install and "
                "unlock one (GNOME Keyring, KeePassXC with Secret Service turned on, or KWallet), then try again. "
                "On a computer without a desktop you can instead set \"allow_unprotected_signins\": true in "
                "config.json; sign-ins are then protected only by your user account's folder permissions.")
    if cfg.get("browser_channel"):
        kwargs["channel"] = cfg["browser_channel"]
    return p.chromium.launch_persistent_context(**kwargs)


_migrated = False


def _migrate_old_signins(p, cfg: dict) -> None:
    """Split sign-ins saved by older versions (one profile for every store) into a profile per store."""
    global _migrated
    if _migrated:
        return
    root = signins_root(cfg)
    old_places = []   # (folder, how it was started)
    if (root / "Local State").exists() or (root / "Default").exists():   # 1.2 to 1.5: one shared profile
        shared = root.parent / (root.name + ".old")
        guard = ProfileLock(root)                     # the lock those versions used
        guard.acquire()
        try:
            if shared.exists():
                _remove_tree(shared)
            staging = root.parent / (root.name + ".moving")
            os.replace(root, staging)
            root.mkdir(parents=True, exist_ok=True)
            os.replace(staging, shared)
        finally:
            guard.release()
        old_places.append((shared, "1.2"))
    elif (root.parent / (root.name + ".old")).exists():  # an earlier move that stopped part-way
        old_places.append((root.parent / (root.name + ".old"), "1.2"))
    value = (cfg.get("profile_dir") or "").strip()
    legacy = [LEGACY_PROFILE]
    if value and Path(value).name == ".browser-profile":
        v = Path(os.path.expandvars(value)).expanduser()
        legacy.append(v if v.is_absolute() else HERE / v)
    old_places += [(o, "1.0") for o in dict.fromkeys(x.resolve() for x in legacy) if o.is_dir()]

    for old, era in old_places:
        start = {} if era == "1.0" else {"ignore_default_args": WEAK_KEY_SWITCHES}  # read with the key it was saved under
        src = p.chromium.launch_persistent_context(str(old), headless=True, **start)
        try:
            cookies = src.cookies()
        finally:
            src.close()
        for store, sites in STORE_SITES.items():
            mine = [c for c in cookies if _on_sites(c["domain"], sites)]
            if not mine:
                continue
            target = profile_dir(cfg, store)
            lock = ProfileLock(target)
            lock.acquire()
            try:
                _lock_down(target)
                dst = _launch(p, cfg, target, headless=True)
                try:
                    dst.add_cookies(mine)
                finally:
                    dst.close()
            finally:
                lock.release()
        _remove_tree(old)
        print(f"Moved your sign-ins from {old} into a separate folder for each store under {root}", flush=True)
    _migrated = True


def launch_context(p, cfg: dict, headless: bool, store: str):
    """Open Hoard's browser with one store's saved sign-in. Close it with ctx.close()."""
    _migrate_old_signins(p, cfg)
    target = profile_dir(cfg, store)
    lock = ProfileLock(target)
    lock.acquire()
    try:
        _lock_down(target)
        ctx = _launch(p, cfg, target, headless)
    except BaseException:
        lock.release()
        raise
    ctx.on("close", lambda _ctx: lock.release())
    return ctx


def check_saved_signin(cfg: dict, store: str) -> None:
    """After signing in: make sure the saved sign-in really is encrypted, or delete it and say why."""
    target = profile_dir(cfg, store)
    if cfg.get("allow_unprotected_signins") or not unprotected_cookie_count(target):
        return
    _remove_tree(target)
    raise SigninsUnprotected(
        f"Your {store.title()} sign-in was saved without your keyring's protection (the keyring may be locked), so "
        "Hoard deleted it. Unlock your keyring and sign in again.")


def _signed_out_page(page) -> bool:
    """True when the open page is a sign-in page."""
    url = page.url.lower()
    return any(w in url for w in ("login", "sign_in", "signin")) or page.locator("input[type=password]").count() > 0


def _end_store_session(p, cfg: dict, profile: Path, store: str) -> bool:
    """Ask the store to end the session (best effort). True when the store then shows this browser as signed out."""
    try:
        ctx = _launch(p, cfg, profile, headless=True)
    except Exception:
        return False
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if store == "gumroad":
            page.goto(GUMROAD_SIGN_OUT, wait_until="domcontentloaded", timeout=20000)
        else:
            page.goto(STORE_ACCOUNT_PAGES[store], wait_until="domcontentloaded", timeout=20000)
            settle(page)
            if _signed_out_page(page):
                return True  # the store already treats this browser as signed out
            if not page.evaluate(SIGN_OUT_JS):
                return False
        settle(page, 1500)
        page.goto(STORE_ACCOUNT_PAGES[store], wait_until="domcontentloaded", timeout=20000)
        settle(page)
        return _signed_out_page(page)
    except Exception:
        return False
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def sign_out(p, cfg: dict, store: str, online: bool | None = None) -> str:
    """Sign out of a store (or "all"): end the session on the store's side when possible, delete the saved
    sign-in, check nothing is left behind, and say what was done."""
    if store == "all":
        done = [sign_out(p, cfg, s, online) for s in STORE_SITES]
        root = signins_root(cfg)
        for extra in (root.parent / (root.name + ".old"), LEGACY_PROFILE):
            if extra.exists():
                _remove_tree(extra)
        return "\n".join(done)
    label = store.title()
    target = profile_dir(cfg, store)
    if not target.exists():
        return f"{label}: no saved sign-in."
    if online is None:
        online = reachable(store)
    lock = ProfileLock(target)
    lock.acquire()
    try:
        count = (_cookie_rows(target, "SELECT COUNT(*) FROM cookies") or [(0,)])[0][0]
        remote = _end_store_session(p, cfg, target, store) if online else None
        _remove_tree(target)
    finally:
        lock.release()
    if target.exists():
        raise RuntimeError(f"Couldn't delete {target}. Close any Hoard window using it and try again.")
    # no other store's folder should hold this store's cookies; if one somehow does, clear them there too
    for other in STORE_SITES:
        other_dir = profile_dir(cfg, other)
        if other != store and other_dir.exists() and any(_on_sites(h, STORE_SITES[store]) for h in _cookie_hosts(other_dir)):
            ctx = launch_context(p, cfg, True, other)
            try:
                for site in STORE_SITES[store]:
                    ctx.clear_cookies(domain=re.compile(rf"(^|\.){re.escape(site)}$"))
            finally:
                ctx.close()
    said = f"{label}: deleted the saved sign-in ({count} {'cookie' if count == 1 else 'cookies'}, plus the store's site data)."
    if remote:
        return said + f" {label} also confirmed you're signed out."
    if remote is None:
        return said + f" You're offline, so {label} wasn't told; sign out on its website to end that session."
    return said + f" Couldn't sign out on {label}'s side; sign out on its website to end that session there too."


def browser_cookies(cfg: dict, store: str) -> tuple[list, str]:
    """A store's cookies (only that store's) and a matching User-Agent, from its saved sign-in.

    They stay in memory for this run and are only ever sent to that store's own sites.
    """
    with _playwright()() as p:
        ctx = launch_context(p, cfg, True, store)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            ua = page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
            cookies = [c for c in ctx.cookies() if _on_sites(c["domain"], STORE_SITES[store])]
        finally:
            ctx.close()
    return cookies, ua


def cmd_login(cfg: dict, args) -> None:
    """Open Hoard's browser at a store's sign-in page and wait while you sign in."""
    url = {"booth": BOOTH_LIBRARY, "gumroad": GR_LOGIN, "jinxxy": JX_INVENTORY, "payhip": PAYHIP_LOGIN}[args.store]
    with _playwright()() as p:
        ctx = launch_context(p, cfg, False, args.store)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url)
        input(f"\nSign in to {args.store.title()} in the browser window, then press Enter here... ")
        ctx.close()
    check_saved_signin(cfg, args.store)
    log(f"Saved in {profile_dir(cfg, args.store)}, {signin_protection(cfg)}.")
    log("Only Hoard uses it. Never share that folder.")


def cmd_logout(cfg: dict, args) -> None:
    """Sign out of one store, or of every store, in Hoard."""
    with _playwright()() as p:
        log(sign_out(p, cfg, args.store))
    log("Hoard doesn't keep store passwords, so there's nothing else to remove.")


# ----------------------------------------------------------------------------- Gumroad

def extract_page_json(text: str):
    """Pull the Inertia page object (component + props) out of a Gumroad HTML page."""
    m = re.search(r'<script[^>]*\bdata-page="app"[^>]*>(.*?)</script>', text, re.S)
    if m:
        return json.loads(m.group(1))
    m = re.search(r'\bdata-page="(\{[^"]*)"', text)
    if m:
        return json.loads(html.unescape(m.group(1)))
    # Older react-on-rails markup, kept as a fallback
    best = None
    for m in re.finditer(r'<script[^>]*js-react-on-rails-component[^>]*data-component-name="([^"]+)"[^>]*>(.*?)</script>',
                         text, re.S):
        if best is None or len(m.group(2)) > len(best[1]):
            best = (m.group(1), m.group(2))
    if best:
        return {"component": best[0], "props": json.loads(best[1])}
    return None


def gumroad_session(cfg: dict) -> requests.Session:
    """An HTTP session signed in to Gumroad, using your Gumroad sign-in in Hoard's browser.

    Earlier versions also accepted a copied session cookie from config.json or an environment variable.
    That's a password-equivalent in plain text, so it's no longer read; sign in with `login gumroad` instead.
    """
    if cfg["gumroad"].get("session_cookie") or os.environ.get("HOARD_GUMROAD_SESSION"):
        log("Note: a Gumroad session cookie in config.json or HOARD_GUMROAD_SESSION is no longer used, because "
            "anyone who sees it can use your account. Delete it (and sign out of Gumroad on its website to end that "
            "session), then sign in with: login gumroad")
    s = requests.Session()
    cookies, ua = browser_cookies(cfg, "gumroad")
    if not any(c["name"].startswith("_gumroad_app_session") for c in cookies):
        raise NotLoggedIn("Not signed in to Gumroad")
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    s.headers["User-Agent"] = ua
    return s


class Gumroad:
    """Reads Gumroad pages. Gumroad embeds each page's data as JSON, so no scraping is needed."""
    def __init__(self, cfg: dict, sess: requests.Session):
        """Wrap a signed-in session; request_delay from the config spaces out page loads."""
        self.cfg, self.sess = cfg, sess
        self.delay = float(cfg.get("request_delay", 1.0))

    def page(self, url: str, params: dict | None = None) -> dict:
        """Load a Gumroad page and return its embedded page data (component and props)."""
        time.sleep(self.delay)
        r = self.sess.get(url, params=params, timeout=60)
        if "/login" in urlparse(r.url).path:
            raise NotLoggedIn("Gumroad session expired")
        r.raise_for_status()
        data = extract_page_json(r.text)
        if not data:
            raise RuntimeError(f"no page data found at {r.url} (Gumroad's markup may have changed)")
        return data

    def library(self):
        """Every purchase card in the library, archived ones included if configured."""
        modes = [False, True] if self.cfg["gumroad"].get("include_archived", True) else [False]
        for archived in modes:
            page_no = 1
            while True:
                params = {"page": page_no, "sort": "purchase_date"}
                if archived:
                    params["show_archived_only"] = "true"
                props = self.page(GR_LIBRARY, params).get("props", {})
                yield from props.get("results") or []
                pages = (props.get("pagination") or {}).get("pages") or 1
                if page_no >= pages:
                    break
                page_no += 1

    def file_url(self, page_url: str, token: str, file_id: str, fallback: str | None) -> str | None:
        """Ask for a signed download URL; fall back to the redirecting link on the download page."""
        try:
            r = self.sess.get(urljoin(page_url, f"/r/{token}/product_files.json"),
                              params={"product_file_ids[]": file_id},
                              headers={"Accept": "application/json"}, timeout=60)
            if r.ok:
                files = r.json().get("files") or []
                if files and files[0].get("url"):
                    return files[0]["url"]
        except (requests.RequestException, ValueError):
            pass
        return urljoin(page_url, fallback) if fallback else None


def gumroad_files(items, prefix: str = ""):
    """Yield (sub-folder, file) for every file on a download page, following Gumroad's folders."""
    for it in items or []:
        if it.get("type") == "folder":
            yield from gumroad_files(it.get("children"), prefix + safe_name(it.get("name") or "Folder") + "/")
        elif it.get("type") == "file":
            yield prefix, it


def gumroad_filename(f: dict) -> str:
    """A safe local name for a Gumroad file: its name plus its extension, in lower case."""
    name = (f.get("file_name") or f.get("id") or "file").strip()
    ext = (f.get("extension") or "").strip().lower().lstrip(".")
    if ext and not name.lower().endswith("." + ext):
        name = f"{name}.{ext}"
    return safe_name(name, 150)


def save_thumbnail(url: str | None, folder: Path, referer: str | None = None) -> None:
    """Save a product's store image as _thumbnail.<ext> in its folder, once. Failures are only logged.

    Image addresses come from store pages (and from Payhip pages you save yourself), so they're fetched
    through a connection that only reaches public internet addresses, and only raster images are kept.
    """
    if not url or any(folder.glob("_thumbnail.*")):
        return
    from asset_browser import fetch_public
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/140.0 Safari/537.36"}
    if referer:
        headers["Referer"] = referer
    got = fetch_public(url, headers, 15 * 1024 * 1024)
    exts = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/avif": "avif"}
    if not got or got[1] not in exts:
        log("    (thumbnail skipped)")
        return
    write_file_safely(folder / f"_thumbnail.{exts[got[1]]}", got[0])


def store_url(url: str, sites: list[str]) -> bool:
    """True when url is an https (or http) address on one of the store's own sites."""
    u = urlparse(url or "")
    return u.scheme in ("https", "http") and bool(u.hostname) and _on_sites(u.hostname, sites)


def sync_gumroad(cfg: dict, root: Path, args, report: Report) -> None:
    """Download everything new or changed in your Gumroad library."""
    store_dir = root / "Gumroad"
    man = Manifest(store_dir)
    gr = Gumroad(cfg, gumroad_session(cfg))

    try:
        _sync_gumroad_purchases(cfg, gr, store_dir, man, args, report)
    finally:
        gr.sess.cookies.clear()  # the copied sign-in only lives for this sync
        gr.sess.close()


def _sync_gumroad_purchases(cfg: dict, gr: "Gumroad", store_dir: Path, man: "Manifest", args, report: Report) -> None:
    """Download everything new or changed, one purchase at a time (see sync_gumroad)."""
    cards = list(gr.library())
    log(f"Gumroad: {len(cards)} purchases in your library")
    seen: set[str] = set()

    for card in cards:
        prod, pur = card.get("product") or {}, card.get("purchase") or {}
        name = (prod.get("name") or "Untitled").strip()
        creator = ((prod.get("creator") or {}).get("name") or "Unknown Creator").strip()
        if args.only and args.only.lower() not in f"{name} {creator}".lower():
            continue
        page_url = pur.get("download_url")
        if not page_url:
            report.skipped.append(f"Gumroad: {name} - no download page (refunded or membership inactive)")
            continue
        try:
            page = gr.page(page_url)
        except NotLoggedIn:
            raise
        except Exception as e:
            report.failed.append(f"Gumroad: {name} - couldn't open download page: {e}")
            continue

        props = page.get("props") or {}
        content = props.get("content")
        if not content:
            report.skipped.append(f"Gumroad: {name} - page type {page.get('component')!r} has no files "
                                  "(may need email confirmation - open it once in the browser)")
            continue

        p = props.get("purchase") or {}
        key = f"{p.get('product_id') or pur.get('id')}:{p.get('variant_id') or ''}"
        if key in seen:  # bought the same product/variant twice
            continue
        seen.add(key)

        variants = (pur.get("variants") or "").strip()
        rec = man.record(key, creator, f"{name} - {variants}" if variants else name)
        is_new_asset = not rec["files"]
        rec.update(name=name, creator=creator, variants=variants or None, url=p.get("product_long_url"),
                   last_synced=now_iso())
        folder = rel_to_path(store_dir, rec["folder"])
        token = props.get("token")
        log(f"\n[Gumroad] {creator} / {name}{f' ({variants})' if variants else ''}")

        got_any = False
        for sub, f in gumroad_files(content.get("content_items")):
            fid, size = f.get("id"), f.get("file_size")
            relpath = sub + gumroad_filename(f)
            target = rel_to_path(folder, relpath)
            old = rec["files"].get(fid)
            if target.exists() and (not size or target.stat().st_size == size):
                rec["files"][fid] = {**(old or {}), "path": relpath, "size": target.stat().st_size}
                continue
            if not f.get("download_url"):
                report.skipped.append(f"Gumroad: {name} / {relpath} - streaming only, no download")
                continue
            is_update = target.exists() or (old is not None and (old.get("size") != size or old.get("path") != relpath))
            label = f"{creator} / {name} / {relpath}"
            if args.dry_run:
                log(f"    would {'update' if is_update else 'download'}: {relpath}")
                continue
            try:
                url = gr.file_url(page_url, token, fid, f.get("download_url"))
                got = http_download(gr.sess, url, target, desc=relpath)
            except Exception as e:
                report.failed.append(f"Gumroad: {label} - {e}")
                continue
            log(f"    {'updated' if is_update else 'saved'}: {relpath}")
            (report.updated if is_update else report.new_files).append(f"Gumroad: {label}")
            rec["files"][fid] = {"path": relpath, "size": got, "downloaded_at": now_iso()}
            got_any = True
            man.save()

        if got_any and is_new_asset:
            report.new_assets.append(f"Gumroad: {creator} / {name}")
        if cfg["gumroad"].get("save_thumbnails", True) and not args.dry_run:
            save_thumbnail(prod.get("thumbnail_url"), folder)
        man.save()


# ----------------------------------------------------------------------------- Jinxxy
#
# Jinxxy has no public API for buyers, so this drives the website with your saved
# login: list the inventory, open each item, click each file's download button.
# If Jinxxy changes its layout, run `probe jinxxy` and adjust item_link_pattern
# in config.json (or share the probe output to rework this into direct API calls).

DOWNLOAD_BUTTONS_JS = r"""
({ allowAll, hosts }) => {
  const dl = /download|ダウンロード/i, all = /download\s*all|all\s*files|まとめて/i;
  const hostOk = new RegExp('(^|\\.)(' + hosts.join('|') + ')$', 'i');
  const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const text = e => [e.innerText, e.getAttribute('aria-label'), e.getAttribute('title')].filter(Boolean).join(' ');
  // links in product descriptions ("Download Poiyomi here") lead off-site; only follow the store's own
  const onSite = e => {
    if (e.tagName !== 'A' || e.hasAttribute('download')) return true;
    const h = e.getAttribute('href') || '';
    if (!h || h.startsWith('#') || h.startsWith('javascript:') || h.startsWith('blob:')) return true;
    try { return hostOk.test(new URL(h, location.href).hostname); } catch (x) { return false; }
  };
  document.querySelectorAll('[data-adl-idx]').forEach(e => e.removeAttribute('data-adl-idx'));
  const cands = [...document.querySelectorAll('button, a, [role="button"]')]
    .filter(e => visible(e) && onSite(e) && dl.test(text(e)) && (allowAll || !all.test(text(e))));
  const leaf = cands.filter(e => !cands.some(o => o !== e && e.contains(o)));
  const set = new Set(leaf);
  return leaf.map((e, i) => {
    e.setAttribute('data-adl-idx', String(i));
    let row = e;
    while (row.parentElement && row.parentElement !== document.body) {
      const p = row.parentElement;
      const n = [...p.querySelectorAll('button, a, [role="button"]')].filter(x => set.has(x)).length;
      if (n > 1 || (p.innerText || '').length > 500) break;
      row = p;
    }
    return { idx: i, label: (row.innerText || text(e)).replace(/\s+/g, ' ').trim().slice(0, 300) };
  });
}
"""
JX_HOSTS = ["jinxxy\\.com"]

JX_INFO_JS = r"""
() => {
  const meta = p => (document.querySelector(`meta[property="${p}"]`) || {}).content || '';
  const h1 = document.querySelector('main h1') || document.querySelector('h1');
  const name = ((h1 && h1.innerText) || meta('og:title') || document.title || '').trim();
  const reserved = new Set(['my','login','signin','signup','register','market','marketplace','search','help',
    'about','terms','privacy','discover','cart','checkout','settings','creators','categories','tags','blog',
    'api','dashboard','products','inventory','support','faq','legal']);
  const links = [];
  for (const a of document.querySelectorAll('a[href]')) {
    let u; try { u = new URL(a.href); } catch (e) { continue; }
    if (!/(^|\.)jinxxy\.com$/.test(u.hostname)) continue;
    const segs = u.pathname.split('/').filter(Boolean);
    if (!(segs.length === 1 || (segs.length === 2 && segs[1] === 'products'))) continue;
    if (reserved.has(segs[0].toLowerCase())) continue;
    const after = h1 ? !!(h1.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING) : true;
    links.push({ after, creator: (a.innerText || '').trim() || segs[0] });
  }
  const pick = links.find(l => l.after) || links[0];
  return { name, creator: pick ? pick.creator : '', thumbnail: meta('og:image') };
}
"""


def settle(page, ms: int = 800) -> None:
    """Give a page time to finish loading: wait for the network to go quiet (at most 15 s), then ms more."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def jinxxy_require_login(page) -> None:
    """Raise NotLoggedIn when Jinxxy is showing its sign-in form."""
    path = urlparse(page.url).path.lower()
    if "login" in path or "signin" in path or page.locator("input[type=password]").count():
        raise NotLoggedIn("Not signed in to Jinxxy")


def _scan_inventory(page, rx, inv_path: str, found: dict) -> list[str]:
    """Scroll / click 'load more' until this page stops growing. Returns numbered-page links seen."""
    page_links: list[str] = []
    quiet = 0
    for _ in range(300):
        before = len(found)
        for href in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
            u = urlparse(href)
            if not u.netloc.endswith("jinxxy.com"):
                continue
            path = u.path.rstrip("/")
            if path == inv_path and re.search(r"(^|&)page=\d+", u.query):
                page_links.append(href)
            elif path != inv_path and rx.search(u.path):
                found.setdefault(f"{u.scheme}://{u.netloc}{path}", None)
        more = page.get_by_role("button", name=re.compile(r"load more|show more", re.I))
        if more.count() and more.first.is_visible() and more.first.is_enabled():
            more.first.click()
            settle(page, 600)
            quiet = 0
            continue
        page.mouse.wheel(0, 20000)
        page.wait_for_timeout(1200)
        quiet = quiet + 1 if len(found) == before else 0
        if quiet >= 3:
            break
    return page_links


def jinxxy_item_links(page, pattern: str) -> list[str]:
    """Every item URL in the inventory, whether it scrolls, has 'load more', or has numbered pages."""
    rx = re.compile(pattern)
    inv_path = urlparse(JX_INVENTORY).path.rstrip("/")
    found: dict[str, None] = {}
    visited, pending = {page.url}, []
    for _ in range(100):
        for href in _scan_inventory(page, rx, inv_path, found):
            if href not in visited and href not in pending:
                pending.append(href)
        if not pending:
            break
        nxt = pending.pop(0)
        visited.add(nxt)
        page.goto(nxt, wait_until="domcontentloaded")
        settle(page)
    return list(found)


def jinxxy_click_download(ctx, page, idx: int, timeout_s: int):
    """Click a tagged button and return the Download it triggers (in this tab or a popup)."""
    captured = []
    hooked = list(ctx.pages)
    popups = []

    def on_download(d):
        captured.append(d)

    def on_page(pg):
        pg.on("download", on_download)
        hooked.append(pg)
        popups.append(pg)

    for pg in hooked:
        pg.on("download", on_download)
    ctx.on("page", on_page)
    try:
        page.locator(f'[data-adl-idx="{idx}"]').first.click()
        deadline = time.time() + timeout_s
        while not captured and time.time() < deadline:
            page.wait_for_timeout(250)
    finally:
        ctx.remove_listener("page", on_page)
        for pg in hooked:
            try:
                pg.remove_listener("download", on_download)
            except Exception:
                pass
    for pg in popups:
        try:
            if not captured or pg is not captured[0].page:
                pg.close()
        except Exception:
            pass
    return captured[0] if captured else None


def close_if_popup(page, main_page) -> None:
    """Close a tab a download opened, leaving the main tab alone."""
    try:
        if page is not main_page:
            page.close()
    except Exception:
        pass


def label_key(label: str) -> str:
    """The part of a download button's row that identifies the file, without the word "download"."""
    return re.sub(r"\s+", " ", re.sub(r"\bdownload\b|ダウンロード", "", label, flags=re.I)).strip()


def download_by_clicking(ctx, page, url: str, rec: dict, folder: Path, store: str, hosts: list[str], timeout_s: int,
                         name: str, creator: str, man: "Manifest", args, report: "Report") -> bool:
    """Click every file's download button on the open page and save what each one downloads."""
    find = lambda allow_all: page.evaluate(DOWNLOAD_BUTTONS_JS, {"allowAll": allow_all, "hosts": hosts})  # noqa: E731
    buttons = find(False)
    allow_all = not buttons
    if allow_all:  # the product only offers a "download all" zip
        buttons = find(True)
    if not buttons:
        report.skipped.append(f"{store}: {name} - no download buttons found on {url}")
        return False

    wanted, used = [], set()
    for b in buttons:
        k = label_key(b["label"]) or f"file #{b['idx'] + 1}"
        if k in used:
            k = f"{k} #{b['idx'] + 1}"
        used.add(k)
        wanted.append((b["label"], k))

    got_any = False
    for pos, (label, k) in enumerate(wanted):
        old = rec["files"].get(k)
        if old and rel_to_path(folder, old["path"]).exists():
            continue
        if args.dry_run:
            log(f"    would download: {k}")
            continue
        current = find(allow_all)  # re-tag; the page may have re-rendered
        match = next((b for b in current if b["label"] == label), current[pos] if pos < len(current) else None)
        if not match:
            report.failed.append(f"{store}: {name} / {k} - button disappeared")
            continue
        dl = jinxxy_click_download(ctx, page, match["idx"], timeout_s)
        if page.url.split("#")[0].rstrip("/") != url.split("#")[0].rstrip("/"):  # the click navigated away
            page.goto(url, wait_until="domcontentloaded")
            settle(page)
        if not dl:
            report.failed.append(f"{store}: {name} / {k} - clicking download didn't start a download")
            continue
        fname = safe_name(dl.suggested_filename or k, 150)
        target = folder / fname
        # the same filename under a different label means the creator updated that file
        prev = next((fk for fk, fv in rec["files"].items() if fv.get("path") == fname and fk != k), None)
        is_update = prev is not None or target.exists()
        part = no_link(target.with_name(target.name + ".part"))
        try:
            folder.mkdir(parents=True, exist_ok=True)
            dl.save_as(str(part))
            os.replace(part, target)
        except Exception as e:
            report.failed.append(f"{store}: {name} / {fname} - {e}")
            continue
        finally:
            close_if_popup(dl.page, page)
        if prev:
            rec["files"].pop(prev, None)
        rec["files"][k] = {"path": fname, "size": target.stat().st_size, "label": label, "downloaded_at": now_iso()}
        log(f"    {'updated' if is_update else 'saved'}: {fname}")
        (report.updated if is_update else report.new_files).append(f"{store}: {creator} / {name} / {fname}")
        got_any = True
        man.save()
    return got_any


def sync_jinxxy(cfg: dict, root: Path, args, report: Report) -> None:
    """Download everything new or changed in your Jinxxy inventory."""
    jcfg = cfg["jinxxy"]
    store_dir = root / "Jinxxy"
    man = Manifest(store_dir)
    delay = float(cfg.get("request_delay", 1.0))

    with _playwright()() as p:
        ctx = launch_context(p, cfg, not args.headed, "jinxxy")
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(JX_INVENTORY, wait_until="domcontentloaded")
            settle(page, 1500)
            jinxxy_require_login(page)
            links = jinxxy_item_links(page, jcfg["item_link_pattern"])
            if not links:
                raise RuntimeError("found no items on the inventory page - run the command: probe jinxxy")
            log(f"Jinxxy: {len(links)} items in your inventory")

            for url in links:
                time.sleep(delay)
                try:
                    _jinxxy_item(ctx, page, url, man, store_dir, jcfg, args, report)
                except NotLoggedIn:
                    raise
                except Exception as e:
                    report.failed.append(f"Jinxxy: {url} - {e}")
        finally:
            ctx.close()


def _jinxxy_item(ctx, page, url, man, store_dir, jcfg, args, report) -> None:
    """Open one Jinxxy item and download the files its page offers."""
    page.goto(url, wait_until="domcontentloaded")
    settle(page)
    jinxxy_require_login(page)
    info = page.evaluate(JX_INFO_JS)
    key = urlparse(url).path.rstrip("/").split("/")[-1]
    name = (info.get("name") or key).strip()
    creator = (info.get("creator") or "Unknown Creator").strip()
    if args.only and args.only.lower() not in f"{name} {creator}".lower():
        return

    rec = man.record(key, creator, name)
    is_new_asset = not rec["files"]
    rec.update(name=name, creator=creator, url=url, last_synced=now_iso())
    folder = rel_to_path(store_dir, rec["folder"])
    log(f"\n[Jinxxy] {creator} / {name}")

    got_any = download_by_clicking(ctx, page, url, rec, folder, "Jinxxy", JX_HOSTS,
                                   int(jcfg.get("download_start_timeout", 90)), name, creator, man, args, report)

    if got_any and is_new_asset:
        report.new_assets.append(f"Jinxxy: {creator} / {name}")
    if jcfg.get("save_thumbnails", True) and not args.dry_run:
        save_thumbnail(info.get("thumbnail"), folder, "https://jinxxy.com/")
    man.save()


# ----------------------------------------------------------------------------- Booth
#
# Booth lists every purchase and gift at accounts.booth.pm/library, with a link for each file.
# The list is read in the browser with your saved login; the files then come straight from
# Booth over HTTP, so big downloads resume if they're interrupted.

BOOTH_LIBRARY = "https://accounts.booth.pm/library"

BOOTH_JS = r"""
() => {
  const idOf = h => { const m = (h || '').match(/\/items\/(\d+)/); return m ? m[1] : null; };
  const text = e => ((e && e.innerText) || '').replace(/\s+/g, ' ').trim();
  const out = new Map();
  for (const a of document.querySelectorAll('a[href*="/items/"]')) {
    const id = idOf(a.href);
    if (!id || out.has(id)) continue;
    let c = a;
    while (c.parentElement && c.parentElement !== document.body) {
      const ids = new Set([...c.parentElement.querySelectorAll('a[href*="/items/"]')].map(x => idOf(x.href)).filter(Boolean));
      if (ids.size > 1) break;
      c = c.parentElement;
    }
    const name = [...c.querySelectorAll('a[href*="/items/"]')].map(text).sort((x, y) => y.length - x.length)[0]
      || text(c.querySelector('.font-bold'));
    let creator = '', creatorUrl = '';
    for (const s of c.querySelectorAll('a[href]')) {
      let u; try { u = new URL(s.href); } catch (e) { continue; }
      if (/\.booth\.pm$/.test(u.hostname) && !['accounts.booth.pm', 'www.booth.pm'].includes(u.hostname)
          && !/\/items\//.test(u.pathname) && text(s)) { creator = text(s); creatorUrl = u.origin + '/'; break; }
    }
    if (!creator) creator = text(c.querySelector('.text-text-gray600'));
    const img = c.querySelector('a[href*="/items/"] img') || c.querySelector('img');
    const thumb = img ? (img.getAttribute('data-original') || img.getAttribute('data-src') || img.currentSrc || img.src || '') : '';
    const files = [...c.querySelectorAll('a[href*="/downloadables/"]')].map(d => {
      let r = d;
      while (r.parentElement && r.parentElement !== c
             && r.parentElement.querySelectorAll('a[href*="/downloadables/"]').length === 1
             && !r.parentElement.querySelector('a[href*="/items/"], img')) r = r.parentElement;
      return { name: text(r).replace(/ダウンロード|Download/gi, '').trim() || 'File', url: d.href };
    });
    const order = c.querySelector('a[href*="/orders/"]');
    out.set(id, { id, name, creator, creator_url: creatorUrl, thumbnail: thumb, url: a.href,
                  order_url: order ? order.href : '', files });
  }
  return [...out.values()];
}
"""


def booth_require_login(page) -> None:
    """Raise NotLoggedIn when Booth has sent the browser to its sign-in page."""
    u = urlparse(page.url)
    if u.hostname != "accounts.booth.pm" or "sign_in" in u.path or page.locator("input[type=password]").count():
        raise NotLoggedIn("Not signed in to Booth")


def booth_library(page, cfg: dict) -> list[dict]:
    """Every purchase (and, if enabled, gift) in your Booth library, one dict per item."""
    items: dict[str, dict] = {}
    delay = float(cfg.get("request_delay", 1.0))
    sources = [("", False)] + ([("/gifts", True)] if cfg["booth"].get("include_gifts", True) else [])
    for path, gift in sources:
        for page_no in range(1, 500):
            resp = page.goto(f"{BOOTH_LIBRARY}{path}?page={page_no}", wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            booth_require_login(page)  # a sign-in page means the session ended, whatever its status code
            if resp is not None and resp.status >= 400:
                raise RuntimeError(f"accounts.booth.pm answered HTTP {resp.status}")
            if not urlparse(page.url).path.startswith("/library"):
                break
            new = 0
            for b in page.evaluate(BOOTH_JS):
                if b["id"] not in items:
                    items[b["id"]] = {**b, "gift": gift}
                    new += 1
            if not new:  # past the last page
                break
            time.sleep(delay)
    return list(items.values())


def session_from_context(ctx, domain: str) -> requests.Session:
    """A requests session carrying the browser's cookies for one site, and the same User-Agent."""
    s = requests.Session()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    s.headers["User-Agent"] = page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
    for c in ctx.cookies():
        if c["domain"].lstrip(".").endswith(domain):
            s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    return s


def booth_file_location(sess: requests.Session, url: str) -> str:
    """Booth answers a file link with a redirect to a short-lived download address."""
    r = sess.get(url, allow_redirects=False, timeout=60, headers={"Referer": BOOTH_LIBRARY})
    if r.status_code in (301, 302, 303, 307, 308):
        loc = urljoin(url, r.headers.get("Location", ""))
        if "sign_in" in loc or urlparse(loc).path.startswith("/users"):
            raise NotLoggedIn("Booth session expired")
        return loc
    if r.ok and not r.headers.get("Content-Type", "").startswith("text/html"):
        return url
    if r.ok:
        raise NotLoggedIn("Booth sent a web page instead of the file; the session may have expired")
    raise RuntimeError(f"booth.pm answered HTTP {r.status_code} instead of sending the file")


def booth_filename(label: str, location: str, fallback: str) -> str:
    """A safe local name for a Booth file: the name Booth shows, or the one in its download address."""
    name = (label or "").strip()
    if not re.search(r"\.[A-Za-z0-9]{1,12}$", name):  # Booth shows the file name; if not, use the download address
        name = unquote(Path(urlparse(location).path).name) or name or fallback
    return safe_name(name, 150)


def sync_booth(cfg: dict, root: Path, args, report: Report) -> None:
    """Download everything new or changed in your Booth library and gifts."""
    bcfg = cfg["booth"]
    store_dir = root / "Booth"
    man = Manifest(store_dir)
    delay = float(cfg.get("request_delay", 1.0))
    with _playwright()() as p:
        ctx = launch_context(p, cfg, not args.headed, "booth")
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            items = booth_library(page, cfg)
            sess = session_from_context(ctx, "booth.pm")
        finally:
            ctx.close()
    log(f"Booth: {len(items)} items in your library")

    for b in items:
        name = (b["name"] or f"Booth item {b['id']}").strip()
        creator = (b["creator"] or "Unknown Creator").strip()
        if args.only and args.only.lower() not in f"{name} {creator}".lower():
            continue
        rec = man.record(b["id"], creator, name)
        is_new_asset, had_files = not rec["files"], bool(rec["files"])
        rec.update(name=name, creator=creator, url=b["url"], gift=b["gift"] or None, last_synced=now_iso())
        folder = rel_to_path(store_dir, rec["folder"])
        log(f"\n[Booth] {creator} / {name}")
        if not b["files"]:
            report.skipped.append(f"Booth: {name} - no files listed in your library")
            continue

        got_any = False
        for f in b["files"]:
            if not store_url(f["url"], ["booth.pm"]):
                report.skipped.append(f"Booth: {name} - a file link that isn't on booth.pm was ignored")
                continue
            m = re.search(r"/downloadables/(\d+)", f["url"])
            fid = m.group(1) if m else f["url"]
            old = rec["files"].get(fid)
            if old and rel_to_path(folder, old["path"]).exists():
                continue
            guess = booth_filename(f["name"], "", f"file-{fid}")
            replaces = next((k for k, v in rec["files"].items() if v.get("path") == guess), None)
            if not old and not replaces and (folder / guess).exists():  # already on disk, e.g. downloaded by hand
                rec["files"][fid] = {"path": guess, "size": (folder / guess).stat().st_size, "label": f["name"]}
                continue
            if args.dry_run:
                log(f"    would download: {guess}")
                continue
            try:
                loc = booth_file_location(sess, f["url"])
                fname = booth_filename(f["name"], loc, f"file-{fid}")
                target = folder / fname
                prev = next((k for k, v in rec["files"].items() if v.get("path") == fname and k != fid), None)
                is_update = had_files or prev is not None or target.exists()
                got = http_download(sess, loc, target, desc=fname)
            except NotLoggedIn:
                raise
            except Exception as e:
                report.failed.append(f"Booth: {creator} / {name} / {f['name']} - {e}")
                continue
            if prev:
                rec["files"].pop(prev, None)
            rec["files"][fid] = {"path": fname, "size": got, "label": f["name"], "downloaded_at": now_iso()}
            log(f"    {'updated' if is_update else 'saved'}: {fname}")
            (report.updated if is_update else report.new_files).append(f"Booth: {creator} / {name} / {fname}")
            got_any = True
            man.save()
            time.sleep(delay)

        if got_any and is_new_asset:
            report.new_assets.append(f"Booth: {creator} / {name}")
        if bcfg.get("save_thumbnails", True) and not args.dry_run:
            save_thumbnail(b["thumbnail"], folder, "https://booth.pm/")
        man.save()
    sess.cookies.clear()  # the copied sign-in only lives for this sync
    sess.close()


# ----------------------------------------------------------------------------- Payhip
#
# Payhip keeps a buyer library while your account is in Customer mode, and puts a bot check in
# front of automated browsers. So Payhip runs in a visible browser window: if a check appears,
# complete it there and the downloads carry on. If Payhip still won't let the tool in, it
# writes Payhip/_download-yourself.html with each product's download page and the folder its
# files belong in; files you save into those folders are picked up by the next sync.

PAYHIP_LOGIN = "https://payhip.com/auth/login"
PAYHIP_HOSTS = ["payhip\\.com", "amazonaws\\.com", "cloudfront\\.net"]
BOT_CHECK_TITLES = ("just a moment", "attention required", "access denied", "verify you are human", "are you a robot")

PAYHIP_FIND_LIBRARY_JS = r"""
() => {
  const a = [...document.querySelectorAll('a[href]')].find(x => {
    let u; try { u = new URL(x.href); } catch (e) { return false; }
    return /(^|\.)payhip\.com$/.test(u.hostname) && /\b(library|my purchases|purchases)\b/i.test(x.innerText || '');
  });
  return a ? a.href : null;
}
"""

PAYHIP_CARDS_JS = r"""
() => {
  const reserved = /^\/(auth|account|settings|marketplace|help|blog|pricing|features|login|signup|register|cart|checkout|search|explore|dashboard|users)(\/|$)/i;
  const text = e => ((e && e.innerText) || '').replace(/\s+/g, ' ').trim();
  const isItemLink = a => {
    let u; try { u = new URL(a.href); } catch (e) { return false; }
    if (!/(^|\.)payhip\.com$/.test(u.hostname) || u.pathname === '/' || reserved.test(u.pathname)) return false;
    return /^\/(b|d|download|downloads|order|orders|purchase|purchases|library|p)\//i.test(u.pathname)
      || /download|access|view content/i.test(a.innerText || '');
  };
  const cards = new Map();
  for (const img of document.querySelectorAll('img')) {
    const w = img.naturalWidth || parseInt(img.getAttribute('width') || '0', 10) || img.width;
    if (w && w < 40) continue;
    let c = img;
    while (c.parentElement && c.parentElement !== document.body && c.parentElement.querySelectorAll('img').length === 1) c = c.parentElement;
    const links = [...c.querySelectorAll('a[href]')].filter(isItemLink);
    if (!links.length) continue;
    const product = links.find(a => /^\/b\//i.test(new URL(a.href).pathname));
    const dl = links.find(a => /download|access/i.test(a.innerText || ''))
      || links.find(a => a !== product && !/^\/b\//i.test(new URL(a.href).pathname)) || links[0];
    const id = (product ? new URL(product.href).pathname : new URL(dl.href).pathname).replace(/\/$/, '');
    if (cards.has(id)) continue;
    const heading = c.querySelector('h1,h2,h3,h4,h5,strong');
    const name = text(heading) || links.map(text).sort((x, y) => y.length - x.length)[0] || img.alt || '';
    const by = (c.innerText || '').match(/\bby\s+([^\n]+)/i);
    let creator = by ? by[1].trim() : '';
    let creatorUrl = '';
    if (!creator) {
      for (const s of c.querySelectorAll('a[href]')) {
        let u; try { u = new URL(s.href); } catch (e) { continue; }
        const segs = u.pathname.split('/').filter(Boolean);
        if (/(^|\.)payhip\.com$/.test(u.hostname) && segs.length === 1 && !reserved.test(u.pathname) && text(s) && text(s) !== name) {
          creator = text(s); creatorUrl = u.href; break;
        }
      }
    }
    cards.set(id, { id, name, creator, creator_url: creatorUrl, thumbnail: img.currentSrc || img.src || '',
                    url: product ? product.href : dl.href, download_url: dl.href });
  }
  const next = document.querySelector('a[rel="next"]')
    || [...document.querySelectorAll('a[href]')].find(a => /^(next|›|»)$/i.test(text(a)));
  return { cards: [...cards.values()], next: next ? next.href : null };
}
"""


class Blocked(Exception):
    """The store showed a bot check that didn't clear."""


def is_bot_check(page) -> bool:
    """True when the page is a bot check (Cloudflare's "Just a moment" and similar)."""
    try:
        title = page.title().lower()
        return any(t in title for t in BOT_CHECK_TITLES) or page.locator(
            "iframe[src*='challenges.cloudflare.com'], #challenge-form, #cf-wrapper, #cf-challenge-running").count() > 0
    except Exception:
        return False


def open_past_bot_check(page, url: str, wait_s: int, headed: bool) -> None:
    """Open a page; if a bot check shows up, wait for you to complete it in the window."""
    page.goto(url, wait_until="domcontentloaded")
    settle(page)
    if not is_bot_check(page):
        return
    if not headed:
        raise Blocked("Payhip showed a bot check")
    log(f"    Payhip is showing a check in the browser window. Complete it there; waiting up to {wait_s} seconds...")
    deadline = time.time() + wait_s
    while time.time() < deadline:
        page.wait_for_timeout(2000)
        if not is_bot_check(page):
            settle(page)
            return
    raise Blocked(f"the bot check didn't clear within {wait_s} seconds")


def payhip_require_login(page) -> None:
    """Raise NotLoggedIn when Payhip is showing its sign-in form."""
    if "/auth/login" in urlparse(page.url).path or page.locator("input[type=password]").count():
        raise NotLoggedIn("Not signed in to Payhip")


def payhip_library_url(page, cfg: dict, wait_s: int, headed: bool) -> str:
    """The address of your Payhip library: from config.json, a link on your account page, or a known path."""
    if cfg["payhip"].get("library_url"):
        return cfg["payhip"]["library_url"]
    open_past_bot_check(page, PAYHIP_LOGIN, wait_s, headed)
    payhip_require_login(page)
    found = page.evaluate(PAYHIP_FIND_LIBRARY_JS)
    if found:
        return found
    for guess in ("https://payhip.com/library", "https://payhip.com/account/library",
                  "https://payhip.com/customer/library", "https://payhip.com/purchases"):
        resp = page.goto(guess, wait_until="domcontentloaded")
        if resp and resp.ok and "/auth/login" not in urlparse(page.url).path and not is_bot_check(page):
            return page.url
    raise RuntimeError("couldn't find your Payhip library. If your account is in Creator mode, switch it to Customer "
                       "(Account menu, Use Payhip as), or put your library's address in payhip.library_url in config.json.")


def payhip_products(page, cfg: dict, wait_s: int, headed: bool) -> list[dict]:
    """Every product in your Payhip library, following its pages."""
    url = payhip_library_url(page, cfg, wait_s, headed)
    cards: dict[str, dict] = {}
    for _ in range(100):
        open_past_bot_check(page, url, wait_s, headed)
        payhip_require_login(page)
        result = page.evaluate(PAYHIP_CARDS_JS)
        for c in result["cards"]:
            cards.setdefault(c["id"], c)
        if not result["next"] or result["next"] == url:
            break
        url = result["next"]
        time.sleep(float(cfg.get("request_delay", 1.0)))
    return list(cards.values())


def read_saved_page(filename: str, text: str) -> tuple[str, str | None, dict]:
    """HTML, the page's original address, and any images saved with it (single-file .mhtml keeps them)."""
    images: dict[str, tuple[bytes, str]] = {}
    if filename.lower().endswith((".mhtml", ".mht")) or re.search(r"^Content-Type:\s*multipart/related", text[:4000], re.I | re.M):
        msg = email.message_from_string(text)
        page_html, location = None, msg.get("Snapshot-Content-Location")
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html" and page_html is None:
                raw = part.get_payload(decode=True) or b""
                page_html = raw.decode(part.get_content_charset() or "utf-8", "replace")
                location = location or part.get("Content-Location")
            elif ctype.startswith("image/") and part.get("Content-Location"):
                images[part.get("Content-Location")] = (part.get_payload(decode=True) or b"", ctype)
        if page_html is None:
            raise ValueError("there's no web page inside that file")
        return page_html, location, images
    m = re.search(r"saved from url=\(\d+\)(\S+?)\s*-->", text[:4000])
    return text, (m.group(1) if m else None), images


def payhip_products_from_file(p, path: Path) -> list[dict]:
    """Read the product list from a Payhip library page you saved from your own browser."""
    page_html, source, _ = read_saved_page(path.name, path.read_text("utf-8", errors="replace"))
    host = urlparse(source or "").hostname or ""
    if source and not (host == "payhip.com" or host.endswith(".payhip.com")):
        raise RuntimeError(f"{path.name} is a page from {host}, not Payhip")
    page_html = re.sub(r"<script\b[^>]*>.*?</script>", "", page_html, flags=re.S | re.I)
    head = re.search(r"<head[^>]*>", page_html, re.I)
    base_tag = f'<base href="{html.escape(source or "https://payhip.com/", quote=True)}">'
    page_html = page_html[:head.end()] + base_tag + page_html[head.end():] if head else base_tag + page_html
    browser = p.chromium.launch()
    try:
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())  # read the file only
        page.set_content(page_html, wait_until="domcontentloaded")
        cards = page.evaluate(PAYHIP_CARDS_JS)["cards"]
    finally:
        browser.close()
    if not cards:
        raise RuntimeError(f"no Payhip products found in {path.name}. Save the library page itself, after it has loaded.")
    return cards


def adopt_files_on_disk(rec: dict, folder: Path) -> int:
    """Record files you put in a product's folder yourself, so they count as downloaded."""
    if not folder.is_dir():
        return 0
    known = {v["path"] for v in rec["files"].values()}
    added = 0
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.name.startswith("_thumbnail") or f.name == "asset.json" or f.suffix == ".part":
            continue
        rel = f.relative_to(folder).as_posix()
        if rel not in known:
            rec["files"][f"by-hand:{rel}"] = {"path": rel, "size": f.stat().st_size, "added_by_hand": True}
            added += 1
    return added


def write_payhip_todo(store_dir: Path, pending: list) -> Path:
    """Write Payhip/_download-yourself.html, listing products Payhip wouldn't let the tool open."""
    esc = lambda v: html.escape(str(v or ""))  # noqa: E731
    rows = "".join(
        f"<li><b>{esc(c['name'])}</b> <span>by {esc(c['creator'] or 'Unknown creator')}</span>"
        f"<a href=\"{esc(c['download_url'])}\">Open download page</a>"
        f"<label>Save its files into<input readonly value=\"{esc(folder)}\" onclick=\"this.select()\"></label></li>"
        for c, folder in pending)
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Payhip downloads for you to grab</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;background:#211C18;color:#F4EDE3;max-width:760px;margin:40px auto;padding:0 20px}}
h1{{font-size:26px}}p{{color:#B3A695}}li{{margin:0 0 18px;padding:14px 16px;background:#2B2520;border-radius:12px}}
span{{color:#B3A695}}a{{display:block;color:#F0B429;margin:6px 0}}label{{display:block;font-size:13px;color:#B3A695}}
input{{display:block;width:100%;margin-top:4px;padding:6px 8px;border:0;border-radius:6px;background:#372F28;color:#F4EDE3}}</style>
<h1>Payhip downloads for you to grab</h1>
<p>Payhip didn't let Hoard Downloader in, so these are yours to download. Open each download page, save its files
into the folder shown, then run a sync again. It records whatever you saved.</p>
<ol>{rows}</ol></html>"""
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / "_download-yourself.html"
    path.write_text(page, "utf-8")
    return path


def sync_payhip(cfg: dict, root: Path, args, report: Report) -> None:
    """Download everything new in your Payhip library, in a visible window so you can pass Payhip's bot check."""
    pcfg = cfg["payhip"]
    store_dir = root / "Payhip"
    man = Manifest(store_dir)
    headed = bool(pcfg.get("headed", True) or args.headed)
    wait_s = int(pcfg.get("bot_check_wait", 180))
    saved_page = getattr(args, "payhip_page", None)
    with _playwright()() as p:
        products = payhip_products_from_file(p, Path(saved_page)) if saved_page else None
        ctx = launch_context(p, cfg, not headed, "payhip")
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            if headed:
                log("Payhip: working in a visible browser window, because Payhip checks for automated browsers.")
            if products is None:
                try:
                    products = payhip_products(page, cfg, wait_s, headed)
                except Blocked as e:
                    raise Blocked(f"{e}. Save your Payhip library page from your own browser (Ctrl+S, "
                                  f"\"Webpage, Single File\") and run: sync --store payhip --payhip-page \"<saved file>\"")
            log(f"Payhip: {len(products)} products in your library")

            pending, blocked = [], None
            for c in products:
                name = (c["name"] or c["id"]).strip()
                creator = (c["creator"] or "Unknown Creator").strip()
                if args.only and args.only.lower() not in f"{name} {creator}".lower():
                    continue
                key = c["id"].strip("/").replace("/", "-")
                rec = man.record(key, creator, name)
                is_new_asset = not rec["files"]
                rec.update(name=name, creator=creator, url=c["url"], last_synced=now_iso())
                folder = rel_to_path(store_dir, rec["folder"])
                if adopt_files_on_disk(rec, folder):
                    man.save()
                log(f"\n[Payhip] {creator} / {name}")
                if blocked:
                    pending.append((c, folder))
                    continue
                if not store_url(c["download_url"], ["payhip.com"]):
                    report.skipped.append(f"Payhip: {name} - its download link isn't on payhip.com, so it wasn't opened")
                    continue
                try:
                    open_past_bot_check(page, c["download_url"], wait_s, headed)
                    payhip_require_login(page)
                    got_any = download_by_clicking(ctx, page, page.url, rec, folder, "Payhip", PAYHIP_HOSTS,
                                                   int(pcfg.get("download_start_timeout", 90)), name, creator,
                                                   man, args, report)
                except Blocked as e:
                    blocked = str(e)
                    pending.append((c, folder))
                    continue
                except NotLoggedIn:
                    raise
                except Exception as e:
                    report.failed.append(f"Payhip: {creator} / {name} - {e}")
                    continue
                if got_any and is_new_asset:
                    report.new_assets.append(f"Payhip: {creator} / {name}")
                if pcfg.get("save_thumbnails", True) and not args.dry_run:
                    save_thumbnail(c.get("thumbnail"), folder, "https://payhip.com/")
                man.save()
            man.save()
            if pending and not args.dry_run:
                todo = write_payhip_todo(store_dir, pending)
                what = "1 product is" if len(pending) == 1 else f"{len(pending)} products are"
                report.failed.append(f"Payhip: {blocked}. {what} listed in {todo} for you to "
                                     "download yourself; the next sync records files you save there.")
        finally:
            ctx.close()


REDACT_KEYS = re.compile(r'("[^"]*(?:email|token|password|secret|session|cookie|authorization|jwt|license)[^"]*"\s*:\s*)"[^"]*"', re.I)
REDACT_QS = re.compile(r'((?:X-Amz-[A-Za-z-]+|Signature|Key-Pair-Id|Policy|token|sig)=)[^&"\s]+', re.I)


def redact(s: str) -> str:
    """Mask emails, tokens, passwords and signed-URL parts in text saved for troubleshooting."""
    return REDACT_QS.sub(r"\1***", REDACT_KEYS.sub(r'\1"***"', s or ""))


def cmd_probe(cfg: dict, args) -> None:
    """Record what Jinxxy's inventory and first item page load, for tuning the adapter."""
    PROBE_DIR.mkdir(exist_ok=True)
    out = open(PROBE_DIR / "jinxxy_network.jsonl", "w", encoding="utf-8")
    with _playwright()() as p:
        ctx = launch_context(p, cfg, False, "jinxxy")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        responses = []
        page.on("response", responses.append)

        def dump(stage):
            for r in responses:
                try:
                    if "json" not in r.headers.get("content-type", "") and "graphql" not in r.url:
                        continue
                    body = r.text()
                except Exception:
                    continue
                out.write(json.dumps({"stage": stage, "method": r.request.method, "status": r.status,
                                      "url": redact(r.url), "request": redact((r.request.post_data or "")[:4000]),
                                      "response": redact(body[:30000])}, ensure_ascii=False) + "\n")
            responses.clear()

        page.goto(JX_INVENTORY, wait_until="domcontentloaded")
        settle(page, 2000)
        jinxxy_require_login(page)
        links = jinxxy_item_links(page, cfg["jinxxy"]["item_link_pattern"])
        dump("inventory")
        (PROBE_DIR / "inventory.html").write_text(page.content(), "utf-8")
        page.screenshot(path=str(PROBE_DIR / "inventory.png"), full_page=True)
        hrefs = sorted({urlparse(h).path for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")})
        (PROBE_DIR / "inventory_links.txt").write_text("\n".join(hrefs), "utf-8")
        log(f"Item links matching item_link_pattern: {len(links)}")

        if links:
            page.goto(links[0], wait_until="domcontentloaded")
            settle(page, 2000)
            dump("item")
            (PROBE_DIR / "item.html").write_text(page.content(), "utf-8")
            page.screenshot(path=str(PROBE_DIR / "item.png"), full_page=True)
            log(f"First item: {page.evaluate(JX_INFO_JS)}")
            for b in page.evaluate(DOWNLOAD_BUTTONS_JS, {"allowAll": True, "hosts": JX_HOSTS}):
                log(f"  download button: {b['label'][:120]}")
        ctx.close()
    out.close()
    log(f"\nWrote {PROBE_DIR}. Skim it for personal info before sharing it with anyone.")


# ----------------------------------------------------------------------------- tags & catalog

def name_tokens(name: str, min_len: int, stop: set) -> set[str]:
    """The words in an asset name that could become tags, lower-cased and without filler or version numbers."""
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)  # FoxyHoodie -> Foxy Hoodie
    out = set()
    for t in re.findall(r"[^\W_]+", name.lower()):
        if t.isdigit() or re.fullmatch(r"v\d+[a-z]?|\d+(st|nd|rd|th)", t):
            continue
        if len(t) >= min_len and t not in stop:
            out.add(t)
    return out


_warned_changed: set = set()


def read_manifests(root: Path) -> list[dict]:
    """Every downloaded asset from every store's manifest, each tagged with its store."""
    assets = []
    for store in STORE_DIRS.values():
        mpath = root / store / "_manifest.json"
        if not mpath.exists():
            continue
        try:
            raw = read_json_file(mpath)
        except (DataFileError, PermissionError) as e:
            log(f"{store}: skipped its _manifest.json ({e})")
            continue
        status = check_seal(raw, mpath)
        if status == "changed" and mpath not in _warned_changed:
            _warned_changed.add(mpath)
            log(f"{store}: _manifest.json was changed by something other than Hoard Downloader, so its store links "
                "aren't shown. The next sync fetches them again.")
        data, dropped = clean_manifest(raw, root / store, trust_links=status in ("sealed", "unsealed"))
        for rec in data["assets"].values():
            if rec.get("files"):
                assets.append({"store": store, **rec})
    return assets


def collect_catalog(cfg: dict, root: Path) -> tuple[list, dict]:
    """Catalog entries + tag index, computed from the manifests on disk. Writes nothing."""
    from asset_browser import TagStore, clean_tag, tag_key  # your tags, shared with Hoard
    tcfg = cfg["tags"]
    stop = STOPWORDS | {w.lower() for w in tcfg.get("extra_stopwords", [])}
    tagdata = TagStore().load()
    block = {w.lower() for w in tcfg.get("blocklist", [])} | set(tagdata["hidden"]) | set(tagdata["tags"])
    assets = read_manifests(root)
    if not assets:
        return [], {}

    toks = [name_tokens(a["name"], int(tcfg.get("min_length", 2)), stop) for a in assets]
    df = Counter(t for ts in toks for t in ts)
    plural = {w: w[:-1] for w in df if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and w[:-1] in df}
    toks = [{plural.get(t, t) for t in ts} for ts in toks]
    df = Counter(t for ts in toks for t in ts)

    n = len(assets)
    min_count, max_share = int(tcfg.get("min_count", 3)), float(tcfg.get("max_share", 0.4))
    tags = {w for w, c in df.items()
            if c >= min_count and w not in block and (n < 10 or c / n <= max_share) and clean_tag(w) == w}

    index: dict[str, list] = {}
    catalog = []
    for a, ts in zip(assets, toks):
        folder = f"{a['store']}/{a['folder']}"
        mine = TagStore.tags_for(tagdata, tag_key(a["store"], a["name"]), a["name"])
        a_tags = sorted((ts & tags) - set(mine))
        added = a.get("first_seen") if isinstance(a.get("first_seen"), str) and len(a["first_seen"]) <= 40 else None
        catalog.append({"store": a["store"], "name": a["name"], "creator": a["creator"], "folder": folder,
                        "url": store_link(a["store"], a.get("url")), "variants": a.get("variants"), "added": added,
                        "files": sorted(f["path"] for f in a["files"].values()),
                        "tags": mine, "suggested_tags": a_tags})
        for t in a_tags:
            index.setdefault(t, []).append(folder)
    catalog.sort(key=lambda e: (e["store"], e["creator"].lower(), e["name"].lower()))
    return catalog, dict(sorted(index.items(), key=lambda kv: (-len(kv[1]), kv[0])))


# What catalog.json, tags.json and asset.json promise (docs/DATA-FORMATS.md describes them in full).
CATALOG_FORMAT = {"catalog": {"format": "hoard-catalog", "version": 3},
                  "asset": {"format": "hoard-asset", "version": 3},
                  "tags": {"format": "hoard-tags", "version": 3}}


def validate_catalog_entry(entry: dict) -> list[str]:
    """Problems with one catalog entry, measured against the promises in docs/DATA-FORMATS.md (empty when fine)."""
    from asset_browser import clean_tag
    problems = []
    label = str(entry.get("folder"))[:80]
    if entry.get("store") not in STORE_DIRS.values():
        problems.append(f"{label}: unknown store")
    for field, limit in (("name", 300), ("creator", 200)):
        v = entry.get(field)
        if not isinstance(v, str) or not v or v != clean_text(v, limit):
            problems.append(f"{label}: {field} isn't clean text")
    if entry.get("variants") is not None and entry["variants"] != clean_text(entry["variants"], 300):
        problems.append(f"{label}: variants isn't clean text")
    if not valid_rel(entry.get("folder")):
        problems.append(f"{label}: folder isn't a plain relative path")
    if not isinstance(entry.get("files"), list) or not all(valid_rel(f) for f in entry["files"]):
        problems.append(f"{label}: a file path isn't a plain relative path")
    if entry.get("url") is not None and store_link(str(entry.get("store")), entry["url"]) != entry["url"]:
        problems.append(f"{label}: url isn't an https address on the store's own website")
    for field in ("tags", "suggested_tags"):
        if not isinstance(entry.get(field), list) or any(not isinstance(t, str) or clean_tag(t) != t or not t for t in entry[field]):
            problems.append(f"{label}: {field} has a tag that isn't clean")
    return problems


def build_catalog(cfg: dict, root: Path) -> None:
    """Write catalog.json, tags.json and each product's asset.json."""
    catalog, ordered = collect_catalog(cfg, root)
    if not catalog:
        log(f"No downloaded assets found under {root} - nothing to tag.")
        return
    # clean_manifest should make every entry pass; any that doesn't is left out rather than written
    checked = [(entry, validate_catalog_entry(entry)) for entry in catalog]
    left_out = [problems[0] for _entry, problems in checked if problems]
    if left_out:
        log(f"Left {len(left_out)} assets out of the catalog because their records failed the check, "
            f"for example: {left_out[0]}")
    catalog = [entry for entry, problems in checked if not problems]
    for entry in catalog:
        try:
            adir = rel_to_path(root, entry["folder"])
        except UnsafePath:
            continue
        if adir.is_dir():
            write_file_safely(adir / "asset.json", json.dumps(seal({**CATALOG_FORMAT["asset"], **entry}), indent=2,
                                                              ensure_ascii=False), root)
    write_file_safely(root / "catalog.json", json.dumps(seal({**CATALOG_FORMAT["catalog"], "generated_at": now_iso(),
                                                              "assets": catalog}), indent=2, ensure_ascii=False), root)
    yours: dict[str, list] = {}
    for entry in catalog:
        for t in entry["tags"]:
            yours.setdefault(t, []).append(entry["folder"])
    write_file_safely(root / "tags.json", json.dumps(seal({
        **CATALOG_FORMAT["tags"], "generated_at": now_iso(), "total_assets": len(catalog),
        "tags": {t: {"count": len(v), "assets": v} for t, v in sorted(yours.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "suggested": {t: {"count": len(v), "assets": v} for t, v in ordered.items()},
    }), indent=2, ensure_ascii=False), root)
    top = ", ".join(f"{t} ({len(v)})" for t, v in list(ordered.items())[:25])
    log(f"\nTagged {len(catalog)} assets with {len(ordered)} suggested tags. Top: {top or '-'}")
    log("Prune noisy ones via tags.blocklist in config.json, then run `tags` again.")


def cmd_verify(cfg: dict, root: Path) -> int:
    """Check the seal on every data file in the download folder, then rebuild the catalog files. 1 if any were changed."""
    labels = {"sealed": "fine", "unsealed": "not sealed yet (saved by an older version; sealed on the next sync)",
              "foreign": "sealed by Hoard Downloader on another computer",
              "changed": "CHANGED by something other than Hoard Downloader"}
    changed = 0
    files = [root / d / "_manifest.json" for d in STORE_DIRS.values()] + [root / "catalog.json", root / "tags.json"]
    files += sorted(root.glob("*/*/*/asset.json"))
    counts: Counter = Counter()
    for path in files:
        if not path.is_file():
            continue
        try:
            status = check_seal(read_json_file(path), path if path.name == "_manifest.json" else None)
        except DataFileError as e:
            status = "changed"
            log(f"  {path.relative_to(root)}: {e}")
        counts[status] += 1
        if status != "sealed":
            log(f"  {path.relative_to(root)}: {labels[status]}")
        changed += status == "changed"
    log(f"Checked {sum(counts.values())} files: " + ", ".join(f"{n} {labels[k].split(' (')[0]}" for k, n in counts.items()))
    for store in STORE_DIRS.values():  # keep changed manifests' records, without their links, and seal them again
        mpath = root / store / "_manifest.json"
        if mpath.is_file():
            try:
                changed_here = check_seal(read_json_file(mpath), mpath) == "changed"
            except DataFileError:
                changed_here = True
            if changed_here:
                Manifest(root / store).save()
                log(f"  {store}/_manifest.json: kept its records without their links and sealed it again. "
                    f"The next {store} sync fetches the links from the store.")
    log("Rebuilding catalog.json, tags.json and every asset.json from the records...")
    build_catalog(cfg, root)
    return 1 if changed else 0


# ----------------------------------------------------------------------------- CLI

STORE_DIRS = {"booth": "Booth", "gumroad": "Gumroad", "jinxxy": "Jinxxy", "payhip": "Payhip"}
STORE_HOSTS = {"booth": "accounts.booth.pm", "gumroad": "app.gumroad.com", "jinxxy": "jinxxy.com", "payhip": "payhip.com"}
NETWORK_ERRORS = ("ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED", "ERR_NAME_RESOLUTION_FAILED",
                  "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET", "ERR_CONNECTION_TIMED_OUT", "ERR_TIMED_OUT",
                  "ERR_NETWORK_CHANGED", "ERR_ADDRESS_UNREACHABLE", "ERR_PROXY_CONNECTION_FAILED",
                  "getaddrinfo", "Name or service not known", "Temporary failure in name resolution",
                  "Failed to establish a new connection", "Max retries exceeded")


def reachable(store: str, timeout: float = 5.0) -> bool:
    """True when a connection to the store's website can be opened right now."""
    import socket
    try:
        with socket.create_connection((STORE_HOSTS[store], 443), timeout=timeout):
            return True
    except OSError:
        return False


def unreachable_message(store: str) -> str:
    """What to tell you when a store's website can't be reached."""
    host = STORE_HOSTS[store].replace("accounts.", "").replace("app.", "")
    return (f"{STORE_DIRS[store]}: couldn't reach {host}, so nothing was synced from it. You may be offline, or the "
            "store may be down. Your downloads are unchanged; try again when you're connected.")


def cmd_sync(cfg: dict, args) -> None:
    """Sync the chosen stores, then rebuild the catalog and print a summary, even after Ctrl+C."""
    root = root_dir(cfg)
    root.mkdir(parents=True, exist_ok=True)
    log(f"Downloading into {root}")
    report = Report()
    stores = list(STORE_DIRS) if args.store == "all" else [args.store]
    syncers = {"booth": sync_booth, "gumroad": sync_gumroad, "jinxxy": sync_jinxxy, "payhip": sync_payhip}
    try:
        for store in stores:
            label = STORE_DIRS[store]
            if not cfg[store].get("enabled", True):
                continue
            if not reachable(store):
                report.failed.append(unreachable_message(store))
                continue
            try:
                syncers[store](cfg, root, args, report)
            except SigninsUnprotected as e:
                report.failed.append(str(e))
                break
            except ProfileBusy as e:
                report.failed.append(str(e))
            except NotLoggedIn as e:
                if (root / label / "_manifest.json").exists():
                    report.failed.append(f"{label}: {e} - sign in to {label} again from the menu (or the command: login {store})")
                else:
                    report.skipped.append(f"{label}: not signed in, so skipped. Sign in from the menu to include it.")
            except Exception as e:
                if any(code in str(e) for code in NETWORK_ERRORS):
                    report.failed.append(unreachable_message(store))
                else:
                    report.failed.append(f"{label}: sync stopped - {e}")
    finally:  # also runs after Ctrl+C, so what did download is catalogued
        if not args.dry_run:
            build_catalog(cfg, root)
        report.print()


def main() -> None:
    """Read the command line and run the chosen command."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="hoard-downloader", description=f"Hoard Downloader {__version__}: download what you own on Booth, Gumroad, Jinxxy and Payhip.")
    ap.add_argument("--version", action="version", version=f"Hoard Downloader {__version__}")
    ap.add_argument("--config", type=Path, default=HERE / "config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("login", help="sign in to a store in a browser window (one-time)")
    s.add_argument("store", choices=list(STORE_DIRS))
    s = sub.add_parser("logout", help="remove Hoard's saved sign-in for a store, or for every store")
    s.add_argument("store", choices=[*STORE_DIRS, "all"])

    s = sub.add_parser("sync", help="download new/changed files and rebuild tags")
    s.add_argument("--store", choices=[*STORE_DIRS, "all"], default="all")
    s.add_argument("--dry-run", action="store_true", help="list what would download, download nothing")
    s.add_argument("--only", help="only products whose name or creator contains this text")
    s.add_argument("--headed", action="store_true", help="show the browser while syncing Booth or Jinxxy")
    s.add_argument("--payhip-page", metavar="FILE",
                   help="read your Payhip products from a library page saved in your own browser (.mhtml or .html)")

    sub.add_parser("tags", help="rebuild catalog.json and tags.json from what's downloaded")
    sub.add_parser("verify", help="check whether any data file was changed outside Hoard Downloader, and rebuild the catalog")

    s = sub.add_parser("browse", help="open a searchable asset browser in your web browser")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to also reach it from other devices on your network")
    s.add_argument("--tls-cert", help="with --host: your HTTPS certificate file (PEM)")
    s.add_argument("--tls-key", help="with --host: the certificate's private key file (PEM)")
    s.add_argument("--plain-http", action="store_true",
                   help="with --host: serve plain HTTP, only when the network is already encrypted (a VPN such as Tailscale)")
    s.add_argument("--no-open", action="store_true", help="don't open a browser tab automatically")

    s = sub.add_parser("probe", help="record what the Jinxxy site loads, for debugging")
    s.add_argument("store", choices=["jinxxy"])

    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.cmd == "login":
        cmd_login(cfg, args)
    elif args.cmd == "logout":
        cmd_logout(cfg, args)
    elif args.cmd == "sync":
        cmd_sync(cfg, args)
    elif args.cmd == "verify":
        sys.exit(cmd_verify(cfg, root_dir(cfg)))
    elif args.cmd == "tags":
        build_catalog(cfg, root_dir(cfg))
    elif args.cmd == "browse":
        from asset_browser import serve
        root = root_dir(cfg)
        serve(root, lambda: collect_catalog(cfg, root)[0], args.host, args.port,
              open_browser=not args.no_open, config_path=args.config, version=__version__,
              tls_cert=args.tls_cert, tls_key=args.tls_key, plain_http=args.plain_http)
    elif args.cmd == "probe":
        cmd_probe(cfg, args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\nStopped. Partial downloads resume (Booth, Gumroad) or restart (Jinxxy, Payhip) next run.")
    except (ProfileBusy, SigninsUnprotected) as e:
        log(f"\n{e}")
