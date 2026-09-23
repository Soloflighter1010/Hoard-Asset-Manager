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
import json
import os
import re
import secrets
import shutil
import socket
import sys
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

__version__ = "1.5.0"

HERE = Path(__file__).resolve().parent
LIBRARY_FILE = HERE / "library.json"
THUMB_DIR = HERE / ".cache" / "thumbs"
DEBUG_DIR = HERE / "debug"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}

DEFAULT_CONFIG = {
    "port": 8766,
    "profile_dir": "",                   # "" = Hoard's private sign-in folder, shared with Hoard Downloader
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
    for k in ("creator_url", "thumbnail", "url", "download_url"):
        d[k] = safe_url(d[k])
    d["files"] = [{"name": str(f.get("name") or "File"), "url": safe_url(f.get("url"))}
                  for f in d["files"] if safe_url(f.get("url"))]
    d["name"] = re.sub(r"\s+", " ", d["name"] or "").strip() or "Untitled"
    d["creator"] = re.sub(r"\s+", " ", d["creator"] or "").strip() or "Unknown creator"
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
# Store sign-ins live in a browser profile that belongs to Hoard alone, never your everyday browser.
# It sits in your user account's private app-data folder instead of next to the program, so zipping,
# sharing, syncing or committing the program folder never carries your sign-ins, and both Hoard tools
# share one set. The browser encrypts the saved cookies with the operating system's own protection:
# your Windows account (DPAPI), the macOS Keychain, or the Linux keyring when one is available.

LEGACY_PROFILE = HERE / ".browser-profile"   # where versions before 1.2 kept sign-ins
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
# Playwright normally starts Chromium with a fixed, publicly known cookie key on Linux and macOS.
# Dropping these two switches lets Chromium use the real keyring / Keychain instead.
WEAK_KEY_SWITCHES = ["--password-store=basic", "--use-mock-keychain"]


class ProfileBusy(Exception):
    """The other Hoard tool is using the sign-ins right now."""


def app_data_dir() -> Path:
    """Hoard's folder in this user account's private app-data location, per operating system."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Hoard"


def _custom_profile(cfg: dict):
    """The sign-in folder named in config.json, or None to use the private default.

    An empty value, or one ending in the pre-1.2 name .browser-profile, means the default.
    """
    value = (cfg.get("profile_dir") or "").strip()
    if not value or Path(value).name == ".browser-profile":  # empty, or an old default: use the private folder
        return None
    p = Path(os.path.expandvars(value)).expanduser()
    return p if p.is_absolute() else HERE / p


def profile_dir(cfg: dict) -> Path:
    """Where Hoard keeps its browser profile, which holds your store sign-ins."""
    return _custom_profile(cfg) or app_data_dir() / "sign-ins"


def _lock_down(path: Path) -> None:
    """Create a folder and, on Linux and macOS, make it readable only by you."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":  # only you can open it; Windows keeps app-data private to your account already
        os.chmod(path, 0o700)
        if path.parent.name == "Hoard":
            os.chmod(path.parent, 0o700)


class ProfileLock:
    """Keeps two Hoard programs from using the sign-ins at once. The OS drops it if a program crashes."""

    def __init__(self, profile: Path):
        """Prepare a lock file next to the sign-in folder; nothing is locked until acquire()."""
        self.path = profile.parent / (profile.name + ".lock")
        self.fh = None

    def acquire(self) -> None:
        """Lock the sign-ins for this program, or raise ProfileBusy if another program has them."""
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
            raise ProfileBusy("Your store sign-ins are in use by the other Hoard tool right now. "
                              "Try again when it has finished.")

    def release(self) -> None:
        """Unlock the sign-ins. Safe to call more than once."""
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


_migrated = False


def _migrate_legacy_profiles(p, cfg: dict, target: Path) -> None:
    """Move sign-ins that older versions kept next to the program into the private folder."""
    global _migrated
    if _migrated or _custom_profile(cfg):
        return
    _migrated = True
    old_places = [LEGACY_PROFILE]
    value = (cfg.get("profile_dir") or "").strip()
    if value and Path(value).name == ".browser-profile":
        old = Path(os.path.expandvars(value)).expanduser()
        old_places.append(old if old.is_absolute() else HERE / old)
    for old in dict.fromkeys(o.resolve() for o in old_places):
        if not old.is_dir() or old == target.resolve():
            continue
        if not (target / "Default").exists():  # nothing saved in the private folder yet: move it all
            if target.exists():
                _remove_tree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(target))
            print(f"Moved your store sign-ins out of the program folder, to {target}", flush=True)
            continue
        # Both places have sign-ins (each tool had its own): copy the store cookies across, then remove the old one.
        src = p.chromium.launch_persistent_context(str(old), headless=True)  # old profiles used the old cookie key
        try:
            cookies = [c for c in src.cookies() if any(c["domain"].lstrip(".").endswith(d)
                                                       for sites in STORE_SITES.values() for d in sites)]
        finally:
            src.close()
        if cookies:
            dst = p.chromium.launch_persistent_context(str(target), headless=True, ignore_default_args=WEAK_KEY_SWITCHES)
            try:
                dst.add_cookies(cookies)
            finally:
                dst.close()
        _remove_tree(old)
        print(f"Merged the store sign-ins from {old} into {target} and removed the old copy.", flush=True)


def launch_context(p, cfg: dict, headless: bool):
    """Open Hoard's own browser with your saved sign-ins. Close it with ctx.close()."""
    target = profile_dir(cfg)
    lock = ProfileLock(target)
    lock.acquire()
    try:
        _migrate_legacy_profiles(p, cfg, target)
        _lock_down(target)
        kwargs = dict(user_data_dir=str(target), headless=headless, accept_downloads=True,
                      viewport={"width": 1400, "height": 950}, ignore_default_args=WEAK_KEY_SWITCHES)
        if cfg.get("browser_channel"):
            kwargs["channel"] = cfg["browser_channel"]
        ctx = p.chromium.launch_persistent_context(**kwargs)
    except BaseException:
        lock.release()
        raise
    ctx.on("close", lambda _ctx: lock.release())
    return ctx


def sign_out(p, cfg: dict, store: str) -> str:
    """Remove Hoard's saved sign-in for one store, or delete every saved sign-in ("all")."""
    target = profile_dir(cfg)
    if store == "all":
        lock = ProfileLock(target)
        lock.acquire()
        try:
            if target.exists():
                _remove_tree(target)
        finally:
            lock.release()
        return "Signed out of every store. Hoard's saved sign-ins are deleted."
    ctx = launch_context(p, cfg, headless=True)
    try:
        for site in STORE_SITES[store]:
            ctx.clear_cookies(domain=re.compile(rf"(^|\.){re.escape(site)}$"))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        for origin in STORE_ORIGINS[store]:  # sites can also keep sign-in tokens in their own storage
            cdp.send("Storage.clearDataForOrigin", {"origin": origin, "storageTypes": "all"})
    finally:
        ctx.close()
    return f"Signed out of {store.title()} in Hoard. Your account itself isn't affected."


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
    for i in items:  # keep the images that came inside the file
        if i.get("thumbnail") in images:
            data, ctype = images[i["thumbnail"]]
            THUMB_DIR.mkdir(parents=True, exist_ok=True)
            ext = {"image/jpeg": "jpg", "image/svg+xml": "svg"}.get(ctype, ctype.split("/")[1])
            (THUMB_DIR / f"{hashlib.sha1(i['thumbnail'].encode()).hexdigest()}.{ext}").write_bytes(data)
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
            self.data = json.loads(path.read_text("utf-8"))

    def save(self) -> None:
        """Write library.json through a temporary file, retrying if Windows has it open elsewhere."""
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), "utf-8")
        for attempt in range(10):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:  # Windows: something is reading the file right now
                if attempt == 9:
                    raise
                time.sleep(0.2)

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
        for k in ("creator_url", "thumbnail", "url", "download_url"):  # also covers lists saved by older versions
            e[k] = safe_url(e.get(k))
        e["files"] = [f for f in e.get("files", []) if safe_url(f.get("url"))]
        out.append(e)
        groups.setdefault(e["match_key"], []).append(e)
    for g in groups.values():
        if len({e["store"] for e in g}) > 1:
            for e in g:
                e["also_in"] = sorted({o["store"] for o in g if o["store"] != e["store"]})
                e["copy_keys"] = sorted({o["tag_key"] for o in g if o["store"] != e["store"]})
    return out


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
    return f"{store.lower()}:{key}"


def clean_tag(value) -> str:
    """A tag as it's stored: lower case, single spaces, no commas or #, at most 40 characters."""
    t = unicodedata.normalize("NFKC", str(value or "")).lower().replace(",", " ").replace("#", " ")
    return re.sub(r"\s+", " ", t).strip()[:TAG_MAX_LENGTH].strip()


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

    def load(self) -> dict:
        """The saved tags, or an empty set when there's no file yet (or it can't be read)."""
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return self.empty()
        base = self.empty()
        for k in base:
            if isinstance(data.get(k), type(base[k])):
                base[k] = data[k]
        return base

    def _save(self, data: dict) -> None:
        """Write tags.json through a temporary file, so a crash can't leave it half-written."""
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True), "utf-8")
        for attempt in range(10):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:  # Windows: the other tool is reading it this instant
                if attempt == 9:
                    raise
                time.sleep(0.1)

    @staticmethod
    def tags_for(data: dict, key: str, name: str) -> list[str]:
        """The tags an item has: the ones you gave it, plus matching ones, minus any you took off it."""
        mine = {t for t in data["items"].get(key, []) if t in data["tags"]}
        auto = {t for t, info in data["tags"].items() if (info or {}).get("match") and name_has_word(name, info["match"])}
        return sorted((mine | auto) - set(data["excluded"].get(key, [])))

    def change(self, body: dict) -> None:
        """Apply one change from the page. Raises ValueError with a readable message when it doesn't make sense."""
        action = body.get("action")
        with _tag_lock, _file_lock(self.path.with_suffix(".lock")):
            data = self.load()
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
            keys = [str(k) for k in (body.get("keys") or []) if isinstance(k, str) and ":" in k][:5000]
            add = [t for t in (clean_tag(v) for v in body.get("add") or []) if t]
            remove = [t for t in (clean_tag(v) for v in body.get("remove") or []) if t]
            if not keys or not (add or remove):
                raise ValueError("Choose items and a tag.")
            for t in add:
                tags.setdefault(t, {"match": None})
            for key in keys:
                for t in add:
                    items[key] = sorted(set(items.get(key, [])) | {t})
                    drop(excluded, key, t)
                for t in remove:
                    drop(items, key, t)
                    if (tags.get(t) or {}).get("match"):  # keep a matching tag off this item from now on
                        excluded[key] = sorted(set(excluded.get(key, [])) | {t})
        elif action == "create":
            tags.setdefault(need(name), {"match": None})
            if len(tags) > 1000:
                raise ValueError("That's more tags than Hoard can keep. Delete some first.")
        elif action == "keep":  # a suggestion becomes your tag, matched by its word
            tags[need(name)] = {"match": name}
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
        except ProfileBusy as e:
            self._set(message=str(e), error=str(e))
        except Exception as e:
            self._set(message=f"Stopped: {e}", error=f"Stopped: {e}")
        finally:
            self._set(running=False, task=None, store=None)
            self.busy.release()

    def _logout(self, stores: list[str]) -> None:
        """Sign out of one store, or of every store, and mark the affected stores as signed out."""
        store = stores[0]
        self._set(task="logout", store=store, message="Signing out")
        with _playwright()() as p:
            done = sign_out(p, self.cfg, store)
        for s in (list(STORES) if store == "all" else [store]):
            if s in self.lib.data["stores"]:
                self.lib.set_error(s, "Signed out. Choose Sign in to refresh this store again.")
        self._set(message=done)

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
            ctx = launch(p, self.cfg, headless=True)
            try:
                for store in online:
                    label = STORES[store]["label"]
                    self._set(task="refresh", store=store, message=f"Reading {label}")
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
            ctx = launch(p, self.cfg, headless=False)
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


def public_http_url(url: str) -> bool:
    """True when url is http(s) and every address its host resolves to is on the public internet."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            return False
    return True


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only if it leads to another public http(s) address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Refuse the redirect unless it leads to a public http(s) address."""
        if not public_http_url(newurl):
            raise urllib.error.URLError(f"refused a redirect to {urlparse(newurl).hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url: str, headers: dict, max_bytes: int, timeout: int = 20) -> tuple[bytes, str] | None:
    """Download a small file from a public http(s) address. Returns (data, content type) or None."""
    if not public_http_url(url):
        return None
    opener = urllib.request.OpenerDirector()  # http(s) only: no file://, ftp:// or data: handlers
    for handler in (urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), _PublicRedirects(),
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
        handler.send_header("Set-Cookie", f"hoard_key={key}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000")
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


def fetch_thumbnail(key: str, lib: Library) -> tuple[bytes, str] | None:
    """Store images, fetched once with the right referrer and cached on disk."""
    found = lib.thumbnail_for(key)
    if not found:
        return None
    url, referer = found
    h = hashlib.sha1(url.encode()).hexdigest()
    for p in THUMB_DIR.glob(h + ".*"):
        ext = p.suffix.lstrip(".")
        return p.read_bytes(), {"jpg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, f"image/{ext}")
    got = fetch_public(url, {"Referer": referer, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"}, 15 * 1024 * 1024)
    if not got:
        return None
    data, ctype = got
    if not ctype.startswith("image/"):
        return None
    ext = {"image/jpeg": "jpg", "image/svg+xml": "svg"}.get(ctype, ctype.split("/")[1])
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    (THUMB_DIR / f"{h}.{ext}").write_bytes(data)
    return data, ctype


class Server(ThreadingHTTPServer):
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
                               "signins": str(profile_dir(self.server.cfg)), "version": __version__})
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
        length = int(self.headers.get("Content-Length") or 0)
        if length > 80 * 1024 * 1024:
            return self._json({"error": "That file is too large to be a library page."}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
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


def serve(cfg: dict, host: str, port: int, open_browser: bool) -> None:
    """Start the library page and open it in the default web browser."""
    lib = Library(LIBRARY_FILE)
    jobs = Jobs(cfg, lib)
    try:
        srv = Server((host, port), cfg, lib, jobs, lan=host not in LOOPBACK)
    except OSError as e:
        sys.exit(f"Couldn't start on port {port} ({e}). Try the command: --port {port + 1}")
    url = f"http://127.0.0.1:{port}/"
    if srv.key:
        print(f"Other devices on your network: http://<this computer's address>:{port}/?key={srv.key}")
        print("That key is needed to see your library from another device. Share it only with devices you trust.")
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
        ctx = launch(p, cfg, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(STORES[store]["login"])
        input(f"Sign in to {STORES[store]['label']} in the browser window, then press Enter here... ")
        ctx.close()
    print(f"Saved. Your sign-ins are kept in {profile_dir(cfg)}, encrypted by your operating system.")


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
        ctx = launch(p, cfg, headless=False)
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
        serve(cfg, args.host, args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()
