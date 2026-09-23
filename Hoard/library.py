#!/usr/bin/env python3
"""
Hoard - everything you own on Booth, Gumroad, Jinxxy and Payhip, in one page.

Nothing is downloaded. It reads each store's purchase list with your saved logins,
keeps the result in library.json, and shows it as a searchable library with links
back to each store's download page.

    python library.py                 open the library (sign in and refresh from the page)
    python library.py login booth     sign in from the terminal instead
    python library.py refresh         refresh every store from the terminal
    python library.py debug payhip    save what a store's library page looks like, for fixing its reader
    python library.py import page.mhtml   add a library page you saved from your own browser
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import email
import hashlib
import hmac
import html
import ipaddress
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import webbrowser
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

__version__ = "1.6.2"

HERE = Path(__file__).resolve().parent
LIBRARY_FILE = HERE / "library.json"
THUMB_DIR = HERE / ".cache" / "thumbs"
DEBUG_DIR = HERE / "debug"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}

DEFAULT_CONFIG = {
    "port": 8766,
    "profile_dir": "",                   # "" = Hoard's private sign-in folder (one profile per store), shared with Hoard Downloader
    "allow_unprotected_signins": False,  # Linux without a keyring only: save sign-ins protected by folder permissions
    "browser_channel": "",               # "chrome" or "msedge" to use an installed browser
    "request_delay": 0.8,
    "gumroad": {"include_archived": True},
    "booth": {"include_gifts": True},
    "jinxxy": {"item_link_pattern": r"^/my/(inventory|purchases|library)/[^/]+/?$"},
    "payhip": {"library_url": ""},       # leave empty to find it automatically
    "tags": {"min_count": 3, "max_share": 0.4, "blocklist": []},
    "offline_images": True,              # save every product image after a refresh, so the library works offline
}

STORES = {
    "booth": {"label": "Booth", "login": "https://accounts.booth.pm/library", "referer": "https://booth.pm/"},
    "gumroad": {"label": "Gumroad", "login": "https://app.gumroad.com/login", "referer": "https://gumroad.com/"},
    "jinxxy": {"label": "Jinxxy", "login": "https://jinxxy.com/my/inventory", "referer": "https://jinxxy.com/"},
    "payhip": {"label": "Payhip", "login": "https://payhip.com/auth/login", "referer": "https://payhip.com/"},
}


class NotLoggedIn(Exception):
    """The store sent its sign-in page instead of your purchases."""
    pass


class Blocked(Exception):
    """The store showed a bot check or refused the automated browser."""


def now_iso() -> str:
    """The current time in UTC, as an ISO 8601 string with seconds."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config() -> dict:
    """The built-in defaults, overlaid with config.json when it exists."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = HERE / "config.json"
    if path.exists():
        def merge(dst, src):
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dst.get(k), dict):
                    merge(dst[k], v)
                else:
                    dst[k] = v
        merge(cfg, json.loads(path.read_text("utf-8")))
    return cfg


def item(store: str, id_, **fields) -> dict:
    """One library item in the shape every store reader produces. Links that aren't http(s) are dropped."""
    d = {"key": f"{store}:{id_}", "store": store, "id": str(id_), "name": "", "creator": "",
         "creator_url": None, "thumbnail": None, "url": None, "download_url": None, "files": [],
         "variants": None, "archived": False, "gift": False}
    d.update({k: v for k, v in fields.items() if v not in (None, "")})
    for k in ("creator_url", "url", "download_url"):  # links you can open: only to this store's own website
        d[k] = store_link(store, d[k])
    d["thumbnail"] = safe_url(d["thumbnail"])       # images come from the stores' image hosts
    d["files"] = [{"name": clean_text(f.get("name"), 200) or "File", "url": store_link(store, f.get("url"))}
                  for f in d["files"][:500] if store_link(store, f.get("url"))]
    d["name"] = clean_text(d["name"], 300) or "Untitled"
    d["creator"] = clean_text(d["creator"], 200) or "Unknown creator"
    d["variants"] = clean_text(d["variants"], 300) or None
    d["archived"], d["gift"] = d["archived"] is True, d["gift"] is True
    return d


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


launch = launch_context


def settle(page, ms: int = 700) -> None:
    """Give a page time to finish loading: wait for the network to go quiet (at most 15 s), then ms more."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


BOT_CHECK_TITLES = ("just a moment", "attention required", "access denied", "verify you are human", "are you a robot")


def goto(page, url: str):
    """Navigate and fail loudly on an error or bot-check page, so it never looks like an empty library."""
    resp = page.goto(url, wait_until="domcontentloaded")
    status = resp.status if resp is not None else 200
    try:
        title = page.title().lower()
        challenge = page.locator("iframe[src*='challenges.cloudflare.com'], #challenge-form, "
                                 "#cf-wrapper, #cf-challenge-running").count() > 0
    except Exception:
        title, challenge = "", False
    if challenge or any(t in title for t in BOT_CHECK_TITLES) or status in (403, 429, 503):
        raise Blocked(f"{urlparse(url).hostname} answered HTTP {status}" if status >= 400 else "bot check")
    if status >= 400:
        raise RuntimeError(f"{urlparse(url).hostname} answered HTTP {status}")
    return resp


def has_password_field(page) -> bool:
    """True when the page shows a password box, which here means a sign-in form."""
    try:
        return page.locator("input[type=password]").count() > 0
    except Exception:
        return False


# ----------------------------------------------------------------------------- Gumroad

GR_LIBRARY = "https://app.gumroad.com/library"


def extract_page_json(text: str):
    """The page data Gumroad embeds in its HTML (component and props), or None."""
    m = re.search(r'<script[^>]*\bdata-page="app"[^>]*>(.*?)</script>', text, re.S)
    if m:
        return json.loads(m.group(1))
    m = re.search(r'\bdata-page="(\{[^"]*)"', text)
    if m:
        return json.loads(html.unescape(m.group(1)))
    return None


def fetch_gumroad(ctx, cfg, progress) -> list[dict]:
    """Every purchase in your Gumroad library, archived ones included when configured."""
    items, seen = [], set()
    delay = float(cfg.get("request_delay", 0.8))
    for archived in ([False, True] if cfg["gumroad"].get("include_archived", True) else [False]):
        page_no = 1
        while True:
            q = f"?page={page_no}&sort=purchase_date" + ("&show_archived_only=true" if archived else "")
            r = ctx.request.get(GR_LIBRARY + q, timeout=60000)
            if "/login" in urlparse(r.url).path:
                raise NotLoggedIn()
            if not r.ok:
                raise RuntimeError(f"the library page answered HTTP {r.status}")
            data = extract_page_json(r.text())
            if not data:
                raise RuntimeError("couldn't find the library data on the page (Gumroad may have changed its site)")
            props = data.get("props") or {}
            for card in props.get("results") or []:
                prod, pur = card.get("product") or {}, card.get("purchase") or {}
                creator = prod.get("creator") or {}
                variants = (pur.get("variants") or "").strip() or None
                dedupe = ((prod.get("name") or "").lower(), (creator.get("name") or "").lower(), variants)
                if dedupe in seen:  # bought twice
                    continue
                seen.add(dedupe)
                items.append(item("gumroad", pur.get("id") or len(items), name=prod.get("name"),
                                  creator=creator.get("name"), creator_url=creator.get("profile_url"),
                                  thumbnail=prod.get("thumbnail_url"), url=pur.get("download_url"),
                                  download_url=pur.get("download_url"), variants=variants,
                                  archived=bool(pur.get("is_archived"))))
            pages = (props.get("pagination") or {}).get("pages") or 1
            progress(f"{'Archived purchases, page' if archived else 'Page'} {page_no} of {pages}, {len(items)} items")
            if page_no >= pages:
                break
            page_no += 1
            time.sleep(delay)
    return items


# ----------------------------------------------------------------------------- Booth

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


def booth_item(b: dict, gift: bool, library_url: str) -> dict:
    """Turn a card read from Booth's library page into a library item."""
    return item("booth", b["id"], name=b["name"], creator=b["creator"], creator_url=b["creator_url"],
                thumbnail=b["thumbnail"], url=b["url"], download_url=b["order_url"] or library_url,
                files=b["files"], gift=gift)


def fetch_booth(ctx, cfg, progress) -> list[dict]:
    """Every item in your Booth library and gifts, page by page."""
    page = ctx.new_page()
    delay = float(cfg.get("request_delay", 0.8))
    items: dict[str, dict] = {}
    sources = [("", False)] + ([("/gifts", True)] if cfg["booth"].get("include_gifts", True) else [])
    try:
        for path, gift in sources:
            base = f"https://accounts.booth.pm/library{path}"
            for page_no in range(1, 500):
                goto(page, f"{base}?page={page_no}")
                page.wait_for_timeout(400)
                u = urlparse(page.url)
                if u.hostname != "accounts.booth.pm" or "sign_in" in u.path or has_password_field(page):
                    raise NotLoggedIn()
                if not u.path.startswith("/library"):
                    break
                new = 0
                for b in page.evaluate(BOOTH_JS):
                    if b["id"] in items:
                        continue
                    new += 1
                    items[b["id"]] = booth_item(b, gift, base)
                progress(f"{'Gifts' if gift else 'Library'} page {page_no}, {len(items)} items")
                if not new:
                    break
                time.sleep(delay)
    finally:
        page.close()
    return list(items.values())


# ----------------------------------------------------------------------------- Jinxxy
#
# Jinxxy has no buyer API; this reads the inventory page like you would. If it misses
# things, run `python library.py debug jinxxy` and adjust jinxxy.item_link_pattern.

JX_INVENTORY = "https://jinxxy.com/my/inventory"

JX_CARDS_JS = r"""
(pattern) => {
  const rx = new RegExp(pattern);
  const RESERVED = new Set(['my', 'login', 'signin', 'signup', 'register', 'market', 'marketplace', 'search', 'help',
    'about', 'terms', 'privacy', 'discover', 'cart', 'checkout', 'settings', 'creators', 'categories', 'tags', 'blog',
    'api', 'dashboard', 'products', 'inventory', 'support', 'faq', 'legal']);
  // Controls and screen-reader-only labels ("More options" on the card menu) aren't part of the name
  const SKIP = 'button, [role="button"], [role="menu"], [role="menuitem"], [aria-haspopup], [aria-hidden="true"], svg, script, style';
  const JUNK = /^(more options|options|menu|download|view|open|details|see more|share|free|new)$/i;
  const keyOf = a => { try { return new URL(a.href).pathname.replace(/\/$/, ''); } catch (e) { return null; } };
  const onJinxxy = u => /(^|\.)jinxxy\.com$/.test(u.hostname);
  const anchors = [...document.querySelectorAll('a[href]')].filter(a => {
    let u; try { u = new URL(a.href); } catch (e) { return false; }
    return onJinxxy(u) && u.pathname.replace(/\/$/, '') !== '/my/inventory' && rx.test(u.pathname);
  });
  const set = new Set(anchors);
  const invisible = el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return true;
    const r = el.getBoundingClientRect();
    return cs.position === 'absolute' && r.width <= 2 && r.height <= 2;  // "sr-only" labels
  };
  const blockOf = (el, root) => {
    while (el !== root && getComputedStyle(el).display.startsWith('inline')) el = el.parentElement;
    return el;
  };
  const linesOf = root => {
    const lines = []; let block = null;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const t = n.textContent.replace(/\s+/g, ' ').trim();
      const el = n.parentElement;
      if (!t || !el) continue;
      const skip = el.closest(SKIP);
      if (skip && root.contains(skip)) continue;
      let hid = false;
      for (let e = el; e && e !== root.parentElement; e = e.parentElement) if (invisible(e)) { hid = true; break; }
      if (hid) continue;
      const b = blockOf(el, root);
      if (b === block && lines.length) lines[lines.length - 1] += ' ' + t; else lines.push(t);
      block = b;
    }
    return lines.map(s => s.trim()).filter(s => s && !JUNK.test(s) && !/^[$€£¥]\s?\d/.test(s));
  };
  const out = [];
  for (const a of anchors) {
    let c = a;
    while (c.parentElement && c.parentElement !== document.body) {
      const keys = new Set([...c.parentElement.querySelectorAll('a[href]')].filter(x => set.has(x)).map(keyOf));
      if (keys.size > 1) break;
      c = c.parentElement;
    }
    // Creator: a link to their store page (jinxxy.com/<name>), else a "by ..." line
    let creator = '', creatorUrl = '';
    for (const s of c.querySelectorAll('a[href]')) {
      if (set.has(s)) continue;
      let u; try { u = new URL(s.href); } catch (e) { continue; }
      const segs = u.pathname.split('/').filter(Boolean);
      if (onJinxxy(u) && (segs.length === 1 || (segs.length === 2 && segs[1] === 'products'))
          && !RESERVED.has(segs[0].toLowerCase())) {
        creator = linesOf(s)[0] || segs[0]; creatorUrl = u.origin + '/' + segs[0]; break;
      }
    }
    const lines = linesOf(c);
    const byLine = lines.find(s => /^by\s+/i.test(s));
    if (!creator && byLine) creator = byLine.replace(/^by\s+/i, '');
    const heading = [...c.querySelectorAll('h1, h2, h3, h4, h5, h6, [class*="title" i]')]
      .map(h => linesOf(h)[0]).find(Boolean);
    const img = c.querySelector('img');
    const name = heading || lines.find(s => s !== byLine && s !== creator) || (img && img.alt) || '';
    if (!creator) creator = lines.find(s => s !== name && s !== byLine) || '';
    out.push({ key: keyOf(a), url: a.href.split(/[?#]/)[0], name, creator, creator_url: creatorUrl,
               thumbnail: img ? (img.currentSrc || img.src || '') : '', lines });
  }
  return out;
}
"""


def fetch_jinxxy(ctx, cfg, progress) -> list[dict]:
    """Every item in your Jinxxy inventory, scrolling and following pages until nothing new appears."""
    page = ctx.new_page()
    pattern = cfg["jinxxy"]["item_link_pattern"]
    found: dict[str, dict] = {}
    try:
        goto(page, JX_INVENTORY)
        settle(page, 1500)
        if "login" in urlparse(page.url).path.lower() or has_password_field(page):
            raise NotLoggedIn()
        visited, pending = {page.url}, []
        for _ in range(100):  # numbered pages
            quiet = 0
            for _ in range(300):  # infinite scroll / load more
                before = len(found)
                for c in page.evaluate(JX_CARDS_JS, pattern):
                    old = found.get(c["key"], {})
                    found[c["key"]] = {k: old.get(k) or c.get(k)
                                       for k in ("key", "url", "name", "creator", "creator_url", "thumbnail")}
                for href in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
                    u = urlparse(href)
                    if u.path.rstrip("/") == "/my/inventory" and re.search(r"(^|&)page=\d+", u.query) \
                            and href not in visited and href not in pending:
                        pending.append(href)
                progress(f"Inventory, {len(found)} items")
                more = page.get_by_role("button", name=re.compile(r"load more|show more", re.I))
                if more.count() and more.first.is_visible() and more.first.is_enabled():
                    more.first.click()
                    settle(page, 500)
                    continue
                page.mouse.wheel(0, 20000)
                page.wait_for_timeout(1100)
                quiet = quiet + 1 if len(found) == before else 0
                if quiet >= 3:
                    break
            if not pending:
                break
            nxt = pending.pop(0)
            visited.add(nxt)
            goto(page, nxt)
            settle(page)
    finally:
        page.close()
    if not found:
        raise RuntimeError("found no items on the inventory page. Run the command: debug jinxxy")
    return [jinxxy_item(c) for c in found.values()]


def jinxxy_item(c: dict) -> dict:
    """Turn a card read from Jinxxy's inventory page into a library item."""
    return item("jinxxy", c["key"].rsplit("/", 1)[-1], name=c["name"], creator=c["creator"],
                creator_url=c.get("creator_url"), thumbnail=c["thumbnail"], url=c["url"], download_url=c["url"])


# ----------------------------------------------------------------------------- Payhip
#
# Payhip keeps a buyer library when your account is in Customer mode. Its layout isn't
# documented, so this finds product cards by their cover images and links. If it gets
# things wrong, set payhip.library_url and run `python library.py debug payhip`.

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


def payhip_library_url(page, cfg) -> str:
    """The address of your Payhip library: from config.json, a link on your account page, or a known path."""
    if cfg["payhip"].get("library_url"):
        return cfg["payhip"]["library_url"]
    goto(page, "https://payhip.com/auth/login")
    settle(page)
    if "/auth/login" in urlparse(page.url).path or has_password_field(page):
        raise NotLoggedIn()
    found = page.evaluate(PAYHIP_FIND_LIBRARY_JS)
    if found:
        return found
    for guess in ("https://payhip.com/library", "https://payhip.com/account/library",
                  "https://payhip.com/customer/library", "https://payhip.com/purchases"):
        resp = page.goto(guess, wait_until="domcontentloaded")
        if resp and resp.ok and "/auth/login" not in urlparse(page.url).path:
            return page.url
    raise RuntimeError("couldn't find your Payhip library. If your account is in Creator mode, switch it to "
                       "Customer (Account menu, Use Payhip as). Or open your library in a browser and put its "
                       "address in payhip.library_url in config.json.")


def fetch_payhip(ctx, cfg, progress) -> list[dict]:
    """Every product in your Payhip library, following its pages."""
    page = ctx.new_page()
    cards: dict[str, dict] = {}
    try:
        url = payhip_library_url(page, cfg)
        for page_no in range(1, 100):
            goto(page, url)
            settle(page)
            if "/auth/login" in urlparse(page.url).path or has_password_field(page):
                raise NotLoggedIn()
            result = page.evaluate(PAYHIP_CARDS_JS)
            for c in result["cards"]:
                cards.setdefault(c["id"], c)
            progress(f"Library page {page_no}, {len(cards)} items")
            if not result["next"] or result["next"] == url:
                break
            url = result["next"]
            time.sleep(float(cfg.get("request_delay", 0.8)))
    finally:
        page.close()
    if not cards:
        raise RuntimeError("the library page had no items this tool recognised. Import the page instead, or run the command: debug payhip")
    return [payhip_item(c) for c in cards.values()]


def payhip_item(c: dict) -> dict:
    """Turn a card read from Payhip's library page into a library item."""
    return item("payhip", c["id"].strip("/").replace("/", "-"), name=c["name"], creator=c["creator"],
                creator_url=c["creator_url"], thumbnail=c["thumbnail"], url=c["url"], download_url=c["download_url"])


FETCHERS = {"booth": fetch_booth, "gumroad": fetch_gumroad, "jinxxy": fetch_jinxxy, "payhip": fetch_payhip}


# ----------------------------------------------------------------------------- import a saved page
#
# When a store blocks the automated browser, save your library page from your own browser
# (Ctrl+S, "Webpage, Single File") and import it. The file is read offline; nothing is fetched.

STORE_HOSTS = {"booth": "booth.pm", "gumroad": "gumroad.com", "jinxxy": "jinxxy.com", "payhip": "payhip.com"}
IMPORTABLE = ("booth", "jinxxy", "payhip")


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


def store_for_url(url: str | None) -> str | None:
    """Which store an address belongs to, or None."""
    host = urlparse(url or "").hostname or ""
    return next((s for s, h in STORE_HOSTS.items() if host == h or host.endswith("." + h)), None)


def import_saved_page(cfg: dict, store: str | None, filename: str, text: str) -> tuple[str, list[dict]]:
    """Read a store page saved from your own browser and return (store, items).

    The file is read offline: scripts are stripped and every network request is blocked. Images saved
    inside a single-file (.mhtml) page are cached so the library can show them.
    """
    page_html, source_url, images = read_saved_page(filename, text)
    detected = store_for_url(source_url)
    if not store or store == "auto":
        store = detected
        if not store:
            raise ValueError("couldn't tell which store this page is from. Use Import page on that store's row in Stores.")
    elif detected and detected != store:
        raise ValueError(f"that page is from {STORES[detected]['label']}, not {STORES[store]['label']}")
    if store not in IMPORTABLE:
        raise ValueError(f"{STORES[store]['label']} doesn't need importing; its refresh reads everything")
    label = STORES[store]["label"]
    base = source_url or {"booth": "https://accounts.booth.pm/library", "jinxxy": JX_INVENTORY,
                          "payhip": "https://payhip.com/"}[store]
    page_html = re.sub(r"<script\b[^>]*>.*?</script>", "", page_html, flags=re.S | re.I)  # don't run the saved page
    head = re.search(r"<head[^>]*>", page_html, re.I)
    base_tag = f'<base href="{html.escape(base, quote=True)}">'
    page_html = page_html[:head.end()] + base_tag + page_html[head.end():] if head else base_tag + page_html

    with _playwright()() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort())  # read the file only; contact nobody
            page.set_content(page_html, wait_until="domcontentloaded")
            if store == "booth":
                gift = "/gifts" in urlparse(base).path
                library_url = base.split("?")[0]
                items = [booth_item(b, gift, library_url) for b in page.evaluate(BOOTH_JS)]
            elif store == "jinxxy":
                seen = {}
                for c in page.evaluate(JX_CARDS_JS, cfg["jinxxy"]["item_link_pattern"]):
                    seen.setdefault(c["key"], c)
                items = [jinxxy_item(c) for c in seen.values()]
            else:
                items = [payhip_item(c) for c in page.evaluate(PAYHIP_CARDS_JS)["cards"]]
        finally:
            browser.close()
    if not items:
        raise ValueError(f"no {label} items in that page. Save your library page itself, after everything "
                         "on it has loaded (scroll to the bottom first).")
    for i in items:  # keep the images that came inside the file (plain raster images only)
        if i.get("thumbnail") in images:
            data, ctype = images[i["thumbnail"]]
            if ctype not in IMAGE_TYPES:
                continue
            THUMB_DIR.mkdir(parents=True, exist_ok=True)
            write_file_safely(THUMB_DIR / f"{hashlib.sha1(i['thumbnail'].encode()).hexdigest()}.{IMAGE_TYPES[ctype]}", data)
    return store, items


# ----------------------------------------------------------------------------- library data

class Library:
    """Your combined library, kept in library.json. Safe to use from several threads."""
    def __init__(self, path: Path):
        """Load library.json, or start empty."""
        self.path = path
        self.lock = threading.Lock()
        self.data = {"items": [], "stores": {}}
        if path.exists():
            try:
                raw = read_json_file(path, 256 * 1024 * 1024)
            except DataFileError as e:
                aside = set_aside(path)
                print(f"{e}, so it was kept as {aside.name}. Refresh your stores to rebuild the list.", flush=True)
                return
            status = check_seal(raw, path)
            self.data = self.sanitize(raw)
            if status in ("changed", "foreign"):
                # something other than this Hoard wrote the list: keep the items, but none of their links or
                # images, until a refresh reads them from the stores again
                for i in self.data["items"]:
                    i.update(creator_url=None, thumbnail=None, url=None, download_url=None, files=[])
                why = ("was changed by something other than Hoard" if status == "changed"
                       else "was saved by Hoard on another computer")
                note = f"Hoard's saved list {why}, so its links and images are hidden until you refresh."
                for info in self.data["stores"].values():
                    info["error"] = note
                print(note, flush=True)

    @staticmethod
    def sanitize(raw) -> dict:
        """Keep only well-formed items and store notes from library.json, rebuilt through item() so they're clean."""
        out = {"items": [], "stores": {}}
        if not isinstance(raw, dict):
            return out
        seen = set()
        for i in (raw.get("items") if isinstance(raw.get("items"), list) else [])[:200000]:
            if not isinstance(i, dict) or i.get("store") not in STORES or not isinstance(i.get("id"), (str, int)):
                continue
            fields = {k: i.get(k) for k in ("name", "creator", "creator_url", "thumbnail", "url", "download_url",
                                             "variants", "archived", "gift")}
            fields["files"] = [f for f in i.get("files", []) if isinstance(f, dict)] if isinstance(i.get("files"), list) else []
            clean = item(i["store"], clean_text(i["id"], 200), **fields)
            if clean["key"] not in seen:
                seen.add(clean["key"])
                out["items"].append(clean)
        for store, info in (raw.get("stores") if isinstance(raw.get("stores"), dict) else {}).items():
            if store in STORES and isinstance(info, dict):
                out["stores"][store] = {
                    "count": info["count"] if isinstance(info.get("count"), int) else 0,
                    "error": clean_text(info.get("error"), 600) or None,
                    **{k: clean_text(info[k], 40) for k in ("refreshed", "updated") if isinstance(info.get(k), str)},
                    **({"source": info["source"]} if info.get("source") in ("import", "refresh") else {}),
                }
        return out

    def save(self) -> None:
        """Seal library.json and write it safely (see write_file_safely)."""
        write_file_safely(self.path, json.dumps(seal(self.data), indent=1, ensure_ascii=False))
        remember_sealed(self.path)

    def replace_store(self, store: str, items: list[dict]) -> None:
        """Swap in a store's freshly read items and record the refresh."""
        with self.lock:
            self.data["items"] = [i for i in self.data["items"] if i["store"] != store] + items
            self.data["stores"][store] = {"updated": now_iso(), "count": len(items), "error": None, "source": "refresh"}
            self.save()

    def merge_store(self, store: str, items: list[dict]) -> int:
        """Add or update imported items without dropping ones from other imported pages."""
        with self.lock:
            merged = {i["key"]: i for i in self.data["items"] if i["store"] == store}
            merged.update({i["key"]: i for i in items})
            self.data["items"] = [i for i in self.data["items"] if i["store"] != store] + list(merged.values())
            self.data["stores"][store] = {"updated": now_iso(), "count": len(merged), "error": None, "source": "import"}
            self.save()
            return len(merged)

    def set_error(self, store: str, message: str) -> None:
        """Note a problem with a store without touching its items."""
        with self.lock:
            s = self.data["stores"].setdefault(store, {"updated": None, "count": 0})
            s["error"] = message
            self.save()

    def thumbnail_for(self, key: str) -> tuple[str, str] | None:
        """(image address, referrer) for an item's thumbnail, or None."""
        with self.lock:
            for i in self.data["items"]:
                if i["key"] == key and i.get("thumbnail"):
                    return i["thumbnail"], STORES[i["store"]]["referer"]
        return None


STOPWORDS = set("""
a an and are as at be by for from in into is it its of on or the to with without your you my our this that these
those v ver version update updated new free paid full set pack bundle edition package unitypackage zip file files
ft feat x vs vrchat vrc
""".split())


def _norm(s: str) -> str:
    """Name key for spotting the same product on two stores: drops 【tags】, (PC/Quest), versions, punctuation."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    core = re.sub(r"【[^】]*】|\[[^\]]*\]|\([^)]*\)", " ", s)
    key = re.sub(r"[\W_]+", "", re.sub(r"\bv?\d+(?:\.\d+)*\b", " ", core))
    return key if len(key) >= 4 else re.sub(r"[\W_]+", "", s)


def enrich(items: list[dict], tcfg: dict, tagdata: dict | None = None) -> list[dict]:
    """Add your tags, suggested tags (words shared by several names) and cross-store matches."""
    tagdata = tagdata or TagStore.empty()
    def tokens(name):
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        return {t for t in re.findall(r"[^\W_]+", name.lower())
                if len(t) >= 2 and t not in STOPWORDS and not t.isdigit() and not re.fullmatch(r"v\d+[a-z]?", t)}

    toks = [tokens(i["name"]) for i in items]
    df = Counter(t for ts in toks for t in ts)
    plural = {w: w[:-1] for w in df if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and w[:-1] in df}
    toks = [{plural.get(t, t) for t in ts} for ts in toks]
    df = Counter(t for ts in toks for t in ts)
    n, block = len(items), {w.lower() for w in tcfg.get("blocklist", [])} | set(tagdata["hidden"]) | set(tagdata["tags"])
    keep = {w for w, c in df.items() if c >= int(tcfg.get("min_count", 3)) and w not in block
            and (n < 10 or c / n <= float(tcfg.get("max_share", 0.4)))}

    groups: dict[str, list] = {}
    out = []
    for i, ts in zip(items, toks):
        key = tag_key(i["store"], i["name"])
        mine = TagStore.tags_for(tagdata, key, i["name"])
        e = {**i, "tag_key": key, "tags": mine, "suggested": sorted((ts & keep) - set(mine)),
             "also_in": [], "copy_keys": [], "match_key": _norm(i["name"])}
        for k in ("creator_url", "url", "download_url"):  # also covers lists saved by older versions
            e[k] = store_link(e["store"], e.get(k))
        e["thumbnail"] = safe_url(e.get("thumbnail"))
        e["files"] = [f for f in e.get("files", []) if store_link(e["store"], f.get("url"))]
        out.append(e)
        groups.setdefault(e["match_key"], []).append(e)
    for g in groups.values():
        if len({e["store"] for e in g}) > 1:
            for e in g:
                e["also_in"] = sorted({o["store"] for o in g if o["store"] != e["store"]})
                e["copy_keys"] = sorted({o["tag_key"] for o in g if o["store"] != e["store"]})
    return out


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


# ----------------------------------------------------------------------------- tags
#
# Your own tags are shared by Hoard and Hoard Downloader, in tags.json in Hoard's app-data folder, so a
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
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Hoard" / "tags.json"


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


# ----------------------------------------------------------------------------- background jobs

class Jobs:
    """One browser job at a time: refreshing stores, or waiting for you to sign in."""

    def __init__(self, cfg: dict, lib: Library):
        """No job is running at first."""
        self.cfg, self.lib = cfg, lib
        self.busy = threading.Lock()
        self.state = {"running": False, "task": None, "store": None, "message": "", "error": None}

    def _set(self, **kw):
        """Update the job state the page polls."""
        self.state.update(kw)

    def start(self, task: str, stores: list[str], skip_imported: bool = False) -> bool:
        """Start a job in the background. False when one is already running."""
        if not self.busy.acquire(blocking=False):
            return False
        self.state["error"] = None
        if task == "login":
            target = self._login_then_refresh
        elif task == "logout":
            target = self._logout
        else:
            target = lambda s: self._refresh(s, skip_imported)  # noqa: E731
        threading.Thread(target=self._wrap, args=(target, stores), daemon=True).start()
        return True

    def _wrap(self, fn, stores):
        """Run a job, recording any error for the page, and always free the runner afterwards."""
        try:
            self._set(running=True)
            fn(stores)
        except (ProfileBusy, SigninsUnprotected) as e:
            self._set(message=str(e), error=str(e))
        except Exception as e:
            self._set(message=f"Stopped: {e}", error=f"Stopped: {e}")
        finally:
            self._set(running=False, task=None, store=None)
            self.busy.release()

    def _logout(self, stores: list[str]) -> None:
        """Sign out of one store, or of every store, and mark the affected stores as signed out."""
        chosen = list(STORES) if stores[0] == "all" else [stores[0]]
        with _playwright()() as p:
            for store in chosen:
                label = STORES[store]["label"]
                self._set(task="logout", store=store, message=f"Signing out of {label}")
                done = sign_out(p, self.cfg, store)
                if store in self.lib.data["stores"]:  # what was done, shown on the store's row in Stores
                    self.lib.set_error(store, "Signed out. " + done.split(": ", 1)[-1])
        if stores[0] == "all":
            root = signins_root(self.cfg)
            for extra in (root.parent / (root.name + ".old"), LEGACY_PROFILE):
                if extra.exists():
                    _remove_tree(extra)
            self._set(message="Signed out of every store. Each store's row in Stores says what was done.")
        else:
            self._set(message="Signed out. " + done.split(": ", 1)[-1])

    def _refresh(self, stores: list[str], skip_imported: bool = False) -> None:
        """Read each store's purchases and save them, keeping the old list when a read fails or comes back empty."""
        if skip_imported:
            stores = [s for s in stores if self.lib.data["stores"].get(s, {}).get("source") != "import"]
        self._set(task="refresh", message="Checking your connection")
        online = [s for s in stores if reachable(s)]
        for store in stores:
            if store not in online:
                self.lib.set_error(store, unreachable_message(store))
        if not online:
            self._set(message="You're offline. Your saved library still works.")
            return
        refreshed = []
        with _playwright()() as p:
            for store in online:
                label = STORES[store]["label"]
                self._set(task="refresh", store=store, message=f"Reading {label}")
                try:
                    ctx = launch(p, self.cfg, True, store)   # each store has its own sign-in
                except (ProfileBusy, SigninsUnprotected) as e:
                    self.lib.set_error(store, str(e))
                    continue
                try:
                    try:
                        items = FETCHERS[store](ctx, self.cfg, lambda m, l=label: self._set(message=f"{l}: {m}"))
                        before = self.lib.data["stores"].get(store, {}).get("count", 0)
                        if not items and before:
                            self.lib.set_error(store, f"Found no items this time (last time: {before}), so the old list was kept. "
                                                      f"Try again, or run the command: debug {store}")
                        else:
                            self.lib.replace_store(store, items)
                            refreshed.append(store)
                    except NotLoggedIn:
                        self.lib.set_error(store, "Not signed in. Choose Sign in, then close the browser window when you're done.")
                    except Blocked as e:
                        self.lib.set_error(store, (
                            f"{label} blocked the automated browser ({e}). Import your library instead: open it in "
                            f"your usual browser, scroll to the bottom, press Ctrl+S and save it as \"Webpage, Single "
                            f"File\", then choose Import page here.") if store in IMPORTABLE
                            else f"{label} blocked the automated browser ({e}). Try again later.")
                    except Exception as e:
                        self.lib.set_error(store, unreachable_message(store) if is_network_error(e)
                                           else f"Couldn't read the library: {e}")
                finally:
                    ctx.close()
        if refreshed and self.cfg.get("offline_images", True):
            with self.lib.lock:
                keys = [i["key"] for i in self.lib.data["items"] if i["store"] in refreshed]
            cache_images(self.lib, keys, lambda m: self._set(message=m))
        self._set(message="Library updated")

    def _login_then_refresh(self, stores: list[str]) -> None:
        """Open a visible browser at a store's sign-in page, wait for the window to close, then refresh that store."""
        store = stores[0]
        label = STORES[store]["label"]
        if not reachable(store):
            self.lib.set_error(store, unreachable_message(store, "opened for signing in"))
            self._set(message=f"Couldn't reach {label}.", error=unreachable_message(store, "opened for signing in"))
            return
        with _playwright()() as p:
            ctx = launch(p, self.cfg, False, store)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(STORES[store]["login"])
            self._set(task="login", store=store,
                      message=f"Sign in to {label} in the browser window that opened, then close that window.")
            while True:  # wait for the window to be closed
                try:
                    if not ctx.pages:
                        break
                    ctx.pages[0].wait_for_timeout(500)
                except Exception:
                    break
            try:
                ctx.close()
            except Exception:
                pass
        try:
            check_saved_signin(self.cfg, store)
        except SigninsUnprotected as e:
            self.lib.set_error(store, str(e))
            raise
        self._refresh([store])


# ----------------------------------------------------------------------------- server

# ----------------------------------------------------------------------------- offline
#
# Everything the page needs is served from this computer: the page, its fonts (bundled in fonts/),
# your library list and saved product images. Only refreshing, signing in and the store links need
# a connection, and those check first and say so plainly when a store can't be reached.

STORE_HOSTS = {"booth": "accounts.booth.pm", "gumroad": "app.gumroad.com", "jinxxy": "jinxxy.com", "payhip": "payhip.com"}
FONT_FILES = ("DelaGothicOne-Regular.woff2", "ZenMaruGothic-Medium.woff2", "ZenMaruGothic-Bold.woff2")
NETWORK_ERRORS = ("ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED", "ERR_NAME_RESOLUTION_FAILED",
                  "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET", "ERR_CONNECTION_TIMED_OUT", "ERR_TIMED_OUT",
                  "ERR_NETWORK_CHANGED", "ERR_ADDRESS_UNREACHABLE", "ERR_PROXY_CONNECTION_FAILED",
                  "getaddrinfo", "Name or service not known", "Temporary failure in name resolution")


def font_path(name: str) -> Path | None:
    """A bundled font file: next to the program (release zips) or one folder up (the repository and the bundle)."""
    if name not in FONT_FILES:
        return None
    for folder in (HERE / "fonts", HERE.parent / "fonts"):
        if (folder / name).is_file():
            return folder / name
    return None


def reachable(store: str, timeout: float = 5.0) -> bool:
    """True when a connection to the store's website can be opened right now."""
    try:
        with socket.create_connection((STORE_HOSTS[store], 443), timeout=timeout):
            return True
    except OSError:
        return False


def unreachable_message(store: str, what: str = "refreshed") -> str:
    """What to tell you when a store's website can't be reached."""
    host = STORE_HOSTS[store].replace("accounts.", "").replace("app.", "")
    return (f"Couldn't reach {host}, so {STORES[store]['label']} wasn't {what}. You may be offline, or the store may "
            "be down. Your saved list is unchanged; try again when you're connected.")


def is_network_error(error: Exception) -> bool:
    """True when an error means the store couldn't be reached, rather than something going wrong on it."""
    return any(code in str(error) for code in NETWORK_ERRORS)


def cache_images(lib: "Library", keys: list[str], progress) -> int:
    """Fetch and keep the images for these items, so they show without a connection. Returns how many are saved."""
    keys = [k for k in keys if lib.thumbnail_for(k)]
    done = saved = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for got in pool.map(lambda k: fetch_thumbnail(k, lib), keys):
            done += 1
            saved += bool(got)
            if done % 10 == 0 or done == len(keys):
                progress(f"Saving images for offline use: {done} of {len(keys)}")
    return saved


# ----------------------------------------------------------------------------- web safety
#
# The page runs on your own computer, but the text and links it shows come from store pages and
# from saved pages you import, so none of it is trusted:
#   - links are only kept when they are ordinary http(s) addresses (no javascript: or file:),
#   - server-side fetches only go to public internet addresses, never your home network or this PC,
#   - every page is sent with a Content-Security-Policy that only runs the page's own script, and
#     with headers that stop other sites from framing it or reading its responses,
#   - on your network (--host 0.0.0.0) other devices need the access key printed at start-up.

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}
_csp_cache: dict = {}


def safe_url(value) -> str | None:
    """Return value if it's a plain http(s) address, otherwise None."""
    if not isinstance(value, str):
        return None
    u = urlparse(value.strip())
    return value.strip() if u.scheme in ("http", "https") and u.netloc else None


def _is_public(ip) -> bool:
    """True for addresses on the public internet (not this computer, your network, or reserved ranges)."""
    return ip.is_global and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                                 or ip.is_reserved or ip.is_unspecified)


def _public_addresses(host: str, port: int) -> list[tuple]:
    """Look host up once and return its addresses, provided every one of them is public."""
    found = []
    for family, _type, _proto, _name, sockaddr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        if not _is_public(ipaddress.ip_address(sockaddr[0].split("%")[0])):
            raise PermissionError(f"{host} points at an address on this computer or your network")
        found.append((family, sockaddr))
    if not found:
        raise OSError(f"{host} has no address")
    return found


def public_http_url(url: str) -> bool:
    """True when url is http(s) and its host currently resolves only to public addresses."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        _public_addresses(u.hostname, u.port or (443 if u.scheme == "https" else 80))
        return True
    except (OSError, UnicodeError, ValueError):
        return False


def _connect_public(host: str, port: int, timeout) -> socket.socket:
    """Connect to one of the public addresses host resolved to, using exactly the address that was checked.

    Checking a name and then letting the connection look it up again would leave a gap that DNS rebinding
    can use (a name that answers with a public address for the check and a private one for the connection).
    """
    last: Exception | None = None
    for family, sockaddr in _public_addresses(host, port):
        sock = socket.socket(family, socket.SOCK_STREAM)
        if timeout is not None and timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
            sock.settimeout(timeout)
        try:
            sock.connect(sockaddr)
            return sock
        except OSError as e:
            last = e
            sock.close()
    raise last or OSError(f"couldn't connect to {host}")


class _PublicHTTPConnection(http.client.HTTPConnection):
    """An HTTP connection that only ever reaches a checked public address."""

    def connect(self):
        """Connect to a checked public address instead of looking the host up again."""
        self.sock = _connect_public(self.host, self.port, self.timeout)


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection that only ever reaches a checked public address, with the certificate checked for the host."""

    def connect(self):
        """Connect to a checked public address, then start TLS for the original host name."""
        sock = _connect_public(self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    """urllib's http:// handler, using the public-only connection."""

    def http_open(self, req):
        """Open http:// addresses through the public-only connection."""
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    """urllib's https:// handler, using the public-only connection."""

    def https_open(self, req):
        """Open https:// addresses through the public-only connection, verifying certificates."""
        return self.do_open(_PublicHTTPSConnection, req, context=ssl.create_default_context())


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to another http(s) address; the connection itself then checks it's public."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Refuse redirects to anything but http(s)."""
        if urlparse(newurl).scheme not in ("http", "https"):
            raise urllib.error.URLError(f"refused a redirect to {urlparse(newurl).scheme}:")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url: str, headers: dict, max_bytes: int, timeout: int = 20) -> tuple[bytes, str] | None:
    """Download a small file from a public http(s) address. Returns (data, content type) or None.

    Every connection, including each redirect, goes only to an address that was checked to be public.
    """
    if urlparse(url).scheme not in ("http", "https"):
        return None
    opener = urllib.request.OpenerDirector()  # http(s) only: no file://, ftp:// or data: handlers, no proxies
    for handler in (_PublicHTTPHandler(), _PublicHTTPSHandler(), _PublicRedirects(),
                    urllib.request.HTTPErrorProcessor(), urllib.request.HTTPDefaultErrorHandler()):
        opener.add_handler(handler)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None
            return data, r.headers.get_content_type()
    except Exception:
        return None


def network_tls(host: str, tls_cert: str | None, tls_key: str | None, plain_http: bool) -> "ssl.SSLContext | None":
    """What to use when serving beyond this computer: an HTTPS context from your certificate, or None for
    plain HTTP when you've said the network is already encrypted. Stops with an explanation otherwise."""
    if host in LOOPBACK:
        return None
    if tls_cert and tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            context.load_cert_chain(tls_cert, tls_key)
        except (OSError, ssl.SSLError) as e:
            sys.exit(f"Couldn't load the certificate or its key: {e}")
        return context
    if plain_http:
        return None
    sys.exit("Showing this to other devices sends your library and its access key across your network, so it needs "
             "HTTPS. Start it with --tls-cert and --tls-key (a certificate for this computer; the free tool mkcert "
             "makes one). If the other devices reach this computer over an encrypted VPN such as Tailscale or "
             "WireGuard, add --plain-http instead.")


class TLSServerMixin:
    """Adds HTTPS to a ThreadingHTTPServer. The TLS handshake happens in each request's own thread."""
    tls_context = None
    tls = False

    def finish_request(self, request, client_address):
        """Wrap the connection in TLS (when enabled) before handling it."""
        if self.tls_context:
            request.settimeout(30)
            try:
                request = self.tls_context.wrap_socket(request, server_side=True)
            except (ssl.SSLError, OSError):
                return
        super().finish_request(request, client_address)


def content_security_policy(page: bytes) -> str:
    """A policy that runs only the page's own inline script (by its hash) and loads nothing unexpected."""
    key = hashlib.sha256(page).hexdigest()
    if key not in _csp_cache:
        scripts = re.findall(rb"<script>(.*?)</script>", page, re.S)
        hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s).digest()).decode() + "'" for s in scripts)
        script_src = hashes or "'none'"
        _csp_cache[key] = ("default-src 'none'; "
                           f"script-src {script_src}; "
                           "style-src 'self' 'unsafe-inline'; "
                           "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
                           "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return _csp_cache[key]


def check_access(handler, lan: bool, key: str | None) -> bool:
    """On the network (--host 0.0.0.0), let a device in only with the access key. True when allowed.

    The key arrives once in the address (?key=...); after that it's kept in a cookie. Sends the reply
    itself (a redirect that sets the cookie, or a refusal) when it returns False.
    """
    if not lan or not key:
        return True
    host = (handler.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
    if handler.client_address[0] in LOOPBACK and host in LOOPBACK:
        return True  # this computer itself
    cookies = SimpleCookie(handler.headers.get("Cookie") or "")
    if "hoard_key" in cookies and hmac.compare_digest(cookies["hoard_key"].value, key):
        return True
    given = (parse_qs(urlparse(handler.path).query).get("key") or [""])[0]
    if given and hmac.compare_digest(given, key):
        handler.send_response(303)
        handler.send_header("Location", urlparse(handler.path).path or "/")
        secure = "; Secure" if getattr(handler.server, "tls", False) else ""
        handler.send_header("Set-Cookie", f"hoard_key={key}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000{secure}")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return False
    body = (b"<!doctype html><meta charset=utf-8><title>Access key needed</title>"
            b"<p style='font:16px system-ui;margin:40px'>Open the address shown in the Hoard window on the computer "
            b"running it. It includes the access key.</p>")
    handler.send_response(401)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    for k, v in SECURITY_HEADERS.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)
    return False


# Only plain raster images are kept. SVG can carry script, so it's never fetched, cached or served.
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/avif": "avif"}


def fetch_thumbnail(key: str, lib: Library) -> tuple[bytes, str] | None:
    """Store images, fetched once with the right referrer and cached on disk."""
    found = lib.thumbnail_for(key)
    if not found:
        return None
    url, referer = found
    h = hashlib.sha1(url.encode()).hexdigest()
    for p in THUMB_DIR.glob(h + ".*"):
        ctype = next((t for t, e in IMAGE_TYPES.items() if e == p.suffix.lstrip(".")), None)
        if ctype:
            return p.read_bytes(), ctype
        p.unlink(missing_ok=True)  # e.g. an SVG saved by an older version
    got = fetch_public(url, {"Referer": referer, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"}, 15 * 1024 * 1024)
    if not got:
        return None
    data, ctype = got
    if ctype not in IMAGE_TYPES:
        return None
    ext = IMAGE_TYPES[ctype]
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    write_file_safely(THUMB_DIR / f"{h}.{ext}", data)
    return data, ctype


class Server(TLSServerMixin, ThreadingHTTPServer):
    """The local server behind the library page."""
    daemon_threads = True

    def __init__(self, addr, cfg, lib, jobs, lan):
        """Start listening; with lan=True, also create the access key other devices need."""
        super().__init__(addr, Handler)
        self.cfg, self.lib, self.jobs, self.lan = cfg, lib, jobs, lan
        self.key = secrets.token_urlsafe(18) if lan else None


class Handler(BaseHTTPRequestHandler):
    """Answers the page's requests. Only this computer is served unless the tool was started with --host."""
    server: Server

    def log_message(self, *args):
        """Keep the console quiet: individual requests aren't logged."""
        pass

    def _send(self, status, body: bytes, ctype: str, headers: dict | None = None):
        """Send a reply with the security headers, adding the page's Content-Security-Policy to HTML."""
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", content_security_policy(body))
        else:
            self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        """Send obj as JSON that the browser won't cache."""
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        """False when a request names a host other than this computer (a DNS-rebinding attempt)."""
        if self.server.lan:
            return True
        return (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]") in LOOPBACK

    def do_GET(self):
        """Serve the page, its data and images."""
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        if not check_access(self, self.server.lan, self.server.key):
            return
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, (HERE / "library.html").read_bytes(), "text/html; charset=utf-8",
                              {"Cache-Control": "no-store"})
        if path == "/api/library":
            with self.server.lib.lock:
                data = json.loads(json.dumps(self.server.lib.data))
            tagdata = TagStore().load()
            items = enrich(data["items"], self.server.cfg["tags"], tagdata)
            return self._json({"items": items, "tagset": tag_overview(tagdata, items), "stores": data["stores"],
                               "labels": {k: v["label"] for k, v in STORES.items()}, "job": self.server.jobs.state,
                               "signins": str(signins_root(self.server.cfg)),
                               "signins_note": signin_protection(self.server.cfg), "version": __version__})
        if path == "/api/status":
            with self.server.lib.lock:
                stores = json.loads(json.dumps(self.server.lib.data["stores"]))
            return self._json({"job": self.server.jobs.state, "stores": stores})
        if path.startswith("/fonts/"):
            font = font_path(unquote(path[len("/fonts/"):]))
            if not font:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, font.read_bytes(), "font/woff2", {"Cache-Control": "max-age=31536000, immutable"})
        if path.startswith("/thumb/"):
            got = fetch_thumbnail(unquote(path[len("/thumb/"):]), self.server.lib)
            if not got:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})
        self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        """Run an action. Only requests from this computer, sent as JSON, are accepted."""
        path = urlparse(self.path).path
        if path not in ("/api/refresh", "/api/login", "/api/import", "/api/logout", "/api/tags"):
            return self._send(404, b"Not found", "text/plain")
        if (not self._host_ok() or self.client_address[0] not in LOOPBACK
                or not (self.headers.get("Content-Type") or "").startswith("application/json")):
            return self._json({"error": "Signing in and refreshing only work on the computer running the library."}, 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "Bad request."}, 400)
        # an imported page can be large; every other action is a few hundred bytes
        if length > (80 * 1024 * 1024 if path == "/api/import" else 1024 * 1024):
            return self._json({"error": "That's too large." if path != "/api/import"
                               else "That file is too large to be a library page."}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, RecursionError):
            return self._json({"error": "Bad request."}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "Bad request."}, 400)
        if path == "/api/tags":
            try:
                TagStore().change(body)
            except (ValueError, TimeoutError) as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"ok": True})
        if path == "/api/import":
            try:
                store, items = import_saved_page(self.server.cfg, body.get("store"), str(body.get("filename") or ""),
                                                 str(body.get("content") or ""))
            except (ValueError, RuntimeError) as e:
                return self._json({"error": f"Couldn't import: {e}"}, 422)
            total = self.server.lib.merge_store(store, items)
            if self.server.cfg.get("offline_images", True):
                threading.Thread(target=cache_images, args=(self.server.lib, [i["key"] for i in items], lambda m: None),
                                 daemon=True).start()
            return self._json({"ok": True, "store": store, "label": STORES[store]["label"],
                               "count": len(items), "total": total})
        stores = [s for s in (body.get("stores") or list(STORES)) if s in STORES or (path == "/api/logout" and s == "all")]
        if not stores:
            return self._json({"error": "Unknown store."}, 400)
        task = {"/api/login": "login", "/api/logout": "logout"}.get(path, "refresh")
        if not self.server.jobs.start(task, stores[:1] if task in ("login", "logout") else stores,
                                      skip_imported=bool(body.get("all"))):
            return self._json({"error": "Already busy. Wait for the current refresh or sign-in to finish."}, 409)
        self._json({"ok": True}, 202)


def serve(cfg: dict, host: str, port: int, open_browser: bool, tls_cert: str | None = None,
          tls_key: str | None = None, plain_http: bool = False) -> None:
    """Start the library page and open it in the default web browser."""
    tls = network_tls(host, tls_cert, tls_key, plain_http)
    lib = Library(LIBRARY_FILE)
    jobs = Jobs(cfg, lib)
    try:
        srv = Server((host, port), cfg, lib, jobs, lan=host not in LOOPBACK)
    except OSError as e:
        sys.exit(f"Couldn't start on port {port} ({e}). Try the command: --port {port + 1}")
    srv.tls_context, srv.tls = tls, bool(tls)
    scheme = "https" if tls else "http"
    url = f"{scheme}://127.0.0.1:{port}/"
    if srv.key:
        print(f"Other devices on your network: {scheme}://<this computer's address>:{port}/?key={srv.key}")
        print("That key is needed to see your library from another device. Share it only with devices you trust.")
        if not tls:
            print("This is plain HTTP: only use it where the connection is already encrypted, such as over Tailscale.")
    counts = ", ".join(f"{STORES[s]['label']} {v.get('count', 0)}" for s, v in lib.data["stores"].items()) or "no stores yet"
    print(f"Hoard {__version__}: {url}   ({len(lib.data['items'])} items: {counts})")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        srv.server_close()


# ----------------------------------------------------------------------------- CLI

def cmd_login(cfg, store):
    """Open Hoard's browser at a store's sign-in page and wait while you sign in."""
    with _playwright()() as p:
        ctx = launch(p, cfg, False, store)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(STORES[store]["login"])
        input(f"Sign in to {STORES[store]['label']} in the browser window, then press Enter here... ")
        ctx.close()
    check_saved_signin(cfg, store)
    print(f"Saved in {profile_dir(cfg, store)}, {signin_protection(cfg)}. Never share that folder.")


def cmd_refresh(cfg, stores):
    """Refresh stores from the command line, printing progress as it goes."""
    lib = Library(LIBRARY_FILE)
    jobs = Jobs(cfg, lib)
    last = [""]

    def show(**kw):
        jobs.state.update(kw)
        if jobs.state["message"] != last[0]:
            last[0] = jobs.state["message"]
            print(" ", last[0])
    jobs._set = show
    jobs._refresh(stores)
    for s in stores:
        info = lib.data["stores"].get(s, {})
        print(f"{STORES[s]['label']:<8} {info.get('error') or str(info.get('count', 0)) + ' items'}")


def cmd_debug(cfg, store):
    """Save what a store's library page looks like and what the reader found, for troubleshooting."""
    DEBUG_DIR.mkdir(exist_ok=True)
    with _playwright()() as p:
        ctx = launch(p, cfg, False, store)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if store == "payhip":
            try:
                url = payhip_library_url(page, cfg)
            except Exception as e:
                print(f"Finding the library failed: {e}")
                url = "https://payhip.com/"
        else:
            url = {"booth": "https://accounts.booth.pm/library", "gumroad": GR_LIBRARY, "jinxxy": JX_INVENTORY}[store]
        page.goto(url, wait_until="domcontentloaded")
        settle(page, 2000)
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)
        (DEBUG_DIR / f"{store}.html").write_text(page.content(), "utf-8")
        page.screenshot(path=str(DEBUG_DIR / f"{store}.png"), full_page=True)
        links = sorted({urlparse(h).path for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")})
        (DEBUG_DIR / f"{store}_links.txt").write_text("\n".join(links), "utf-8")
        js = {"booth": BOOTH_JS, "payhip": PAYHIP_CARDS_JS}.get(store)
        if js:
            parsed = page.evaluate(js)
        elif store == "jinxxy":
            parsed = page.evaluate(JX_CARDS_JS, cfg["jinxxy"]["item_link_pattern"])
        else:
            parsed = "(Gumroad is read from page data, not the layout)"
        (DEBUG_DIR / f"{store}_parsed.json").write_text(json.dumps(parsed, indent=2, ensure_ascii=False), "utf-8")
        print(f"Page: {page.url}")
        ctx.close()
    print(f"Saved {store}.html, {store}.png, {store}_links.txt and {store}_parsed.json in {DEBUG_DIR}.")
    print("They can contain your name and purchases; skim them before sharing.")


def main():
    """Read the command line and run the chosen command, or start the library page."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    cfg = load_config()
    ap = argparse.ArgumentParser(prog="hoard", description=f"Hoard {__version__}: everything you own on Booth, Gumroad, Jinxxy and Payhip in one page.")
    ap.add_argument("--version", action="version", version=f"Hoard {__version__}")
    ap.add_argument("--port", type=int, default=cfg["port"])
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to also browse from other devices on your network")
    ap.add_argument("--tls-cert", help="with --host: your HTTPS certificate file (PEM)")
    ap.add_argument("--tls-key", help="with --host: the certificate's private key file (PEM)")
    ap.add_argument("--plain-http", action="store_true",
                    help="with --host: serve plain HTTP, only when the network is already encrypted (a VPN such as Tailscale)")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("login", help="sign in to a store from the terminal")
    s.add_argument("store", choices=list(STORES))
    s = sub.add_parser("logout", help="remove Hoard's saved sign-in for a store, or for every store")
    s.add_argument("store", choices=[*STORES, "all"])
    s = sub.add_parser("refresh", help="refresh stores from the terminal")
    s.add_argument("--store", choices=list(STORES), action="append", help="repeat for several; default all")
    s = sub.add_parser("import", help="add a library page you saved from your own browser (.mhtml or .html)")
    s.add_argument("file", type=Path)
    s.add_argument("--store", choices=list(IMPORTABLE), help="only needed if it can't be detected")
    s = sub.add_parser("debug", help="save a store's library page for troubleshooting")
    s.add_argument("store", choices=list(STORES))
    args = ap.parse_args()

    if args.cmd == "login":
        cmd_login(cfg, args.store)
    elif args.cmd == "logout":
        with _playwright()() as p:
            print(sign_out(p, cfg, args.store))
    elif args.cmd == "refresh":
        cmd_refresh(cfg, args.store or list(STORES))
    elif args.cmd == "import":
        store, items = import_saved_page(cfg, args.store, args.file.name,
                                         args.file.read_text("utf-8", errors="replace"))
        total = Library(LIBRARY_FILE).merge_store(store, items)
        print(f"Imported {len(items)} {STORES[store]['label']} items ({total} in the library for that store).")
    elif args.cmd == "debug":
        cmd_debug(cfg, args.store)
    else:
        serve(cfg, args.host, args.port, open_browser=not args.no_open, tls_cert=args.tls_cert,
              tls_key=args.tls_key, plain_http=args.plain_http)


if __name__ == "__main__":
    main()
