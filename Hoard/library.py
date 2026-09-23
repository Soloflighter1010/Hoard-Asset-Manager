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
import email
import hashlib
import html
import json
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
import urllib.request
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

__version__ = "1.2.0"

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
}

STORES = {
    "booth": {"label": "Booth", "login": "https://accounts.booth.pm/library", "referer": "https://booth.pm/"},
    "gumroad": {"label": "Gumroad", "login": "https://app.gumroad.com/login", "referer": "https://gumroad.com/"},
    "jinxxy": {"label": "Jinxxy", "login": "https://jinxxy.com/my/inventory", "referer": "https://jinxxy.com/"},
    "payhip": {"label": "Payhip", "login": "https://payhip.com/auth/login", "referer": "https://payhip.com/"},
}


class NotLoggedIn(Exception):
    pass


class Blocked(Exception):
    """The store showed a bot check or refused the automated browser."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config() -> dict:
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
    d = {"key": f"{store}:{id_}", "store": store, "id": str(id_), "name": "", "creator": "",
         "creator_url": None, "thumbnail": None, "url": None, "download_url": None, "files": [],
         "variants": None, "archived": False, "gift": False}
    d.update({k: v for k, v in fields.items() if v not in (None, "")})
    d["name"] = re.sub(r"\s+", " ", d["name"] or "").strip() or "Untitled"
    d["creator"] = re.sub(r"\s+", " ", d["creator"] or "").strip() or "Unknown creator"
    return d


# ----------------------------------------------------------------------------- browser

def _playwright():
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
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Hoard"


def _custom_profile(cfg: dict):
    value = (cfg.get("profile_dir") or "").strip()
    if not value or Path(value).name == ".browser-profile":  # empty, or an old default: use the private folder
        return None
    p = Path(os.path.expandvars(value)).expanduser()
    return p if p.is_absolute() else HERE / p


def profile_dir(cfg: dict) -> Path:
    return _custom_profile(cfg) or app_data_dir() / "sign-ins"


def _lock_down(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":  # only you can open it; Windows keeps app-data private to your account already
        os.chmod(path, 0o700)
        if path.parent.name == "Hoard":
            os.chmod(path.parent, 0o700)


class ProfileLock:
    """Keeps two Hoard programs from using the sign-ins at once. The OS drops it if a program crashes."""

    def __init__(self, profile: Path):
        self.path = profile.parent / (profile.name + ".lock")
        self.fh = None

    def acquire(self) -> None:
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
    try:
        return page.locator("input[type=password]").count() > 0
    except Exception:
        return False


# ----------------------------------------------------------------------------- Gumroad

GR_LIBRARY = "https://app.gumroad.com/library"


def extract_page_json(text: str):
    m = re.search(r'<script[^>]*\bdata-page="app"[^>]*>(.*?)</script>', text, re.S)
    if m:
        return json.loads(m.group(1))
    m = re.search(r'\bdata-page="(\{[^"]*)"', text)
    if m:
        return json.loads(html.unescape(m.group(1)))
    return None


def fetch_gumroad(ctx, cfg, progress) -> list[dict]:
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
    return item("booth", b["id"], name=b["name"], creator=b["creator"], creator_url=b["creator_url"],
                thumbnail=b["thumbnail"], url=b["url"], download_url=b["order_url"] or library_url,
                files=b["files"], gift=gift)


def fetch_booth(ctx, cfg, progress) -> list[dict]:
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
    host = urlparse(url or "").hostname or ""
    return next((s for s, h in STORE_HOSTS.items() if host == h or host.endswith("." + h)), None)


def import_saved_page(cfg: dict, store: str | None, filename: str, text: str) -> tuple[str, list[dict]]:
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
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.data = {"items": [], "stores": {}}
        if path.exists():
            self.data = json.loads(path.read_text("utf-8"))

    def save(self) -> None:
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
        with self.lock:
            s = self.data["stores"].setdefault(store, {"updated": None, "count": 0})
            s["error"] = message
            self.save()

    def thumbnail_for(self, key: str) -> tuple[str, str] | None:
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


def enrich(items: list[dict], tcfg: dict) -> list[dict]:
    """Add suggested tags (words shared by several names) and cross-store matches."""
    def tokens(name):
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        return {t for t in re.findall(r"[^\W_]+", name.lower())
                if len(t) >= 2 and t not in STOPWORDS and not t.isdigit() and not re.fullmatch(r"v\d+[a-z]?", t)}

    toks = [tokens(i["name"]) for i in items]
    df = Counter(t for ts in toks for t in ts)
    plural = {w: w[:-1] for w in df if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and w[:-1] in df}
    toks = [{plural.get(t, t) for t in ts} for ts in toks]
    df = Counter(t for ts in toks for t in ts)
    n, block = len(items), {w.lower() for w in tcfg.get("blocklist", [])}
    keep = {w for w, c in df.items() if c >= int(tcfg.get("min_count", 3)) and w not in block
            and (n < 10 or c / n <= float(tcfg.get("max_share", 0.4)))}

    groups: dict[str, list] = {}
    out = []
    for i, ts in zip(items, toks):
        e = {**i, "tags": sorted(ts & keep), "also_in": [], "match_key": _norm(i["name"])}
        out.append(e)
        groups.setdefault(e["match_key"], []).append(e)
    for g in groups.values():
        if len({e["store"] for e in g}) > 1:
            for e in g:
                e["also_in"] = sorted({o["store"] for o in g if o["store"] != e["store"]})
    return out


# ----------------------------------------------------------------------------- background jobs

class Jobs:
    """One browser job at a time: refreshing stores, or waiting for you to sign in."""

    def __init__(self, cfg: dict, lib: Library):
        self.cfg, self.lib = cfg, lib
        self.busy = threading.Lock()
        self.state = {"running": False, "task": None, "store": None, "message": "", "error": None}

    def _set(self, **kw):
        self.state.update(kw)

    def start(self, task: str, stores: list[str], skip_imported: bool = False) -> bool:
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
        store = stores[0]
        self._set(task="logout", store=store, message="Signing out")
        with _playwright()() as p:
            done = sign_out(p, self.cfg, store)
        for s in (list(STORES) if store == "all" else [store]):
            if s in self.lib.data["stores"]:
                self.lib.set_error(s, "Signed out. Choose Sign in to refresh this store again.")
        self._set(message=done)

    def _refresh(self, stores: list[str], skip_imported: bool = False) -> None:
        if skip_imported:
            stores = [s for s in stores if self.lib.data["stores"].get(s, {}).get("source") != "import"]
        with _playwright()() as p:
            ctx = launch(p, self.cfg, headless=True)
            try:
                for store in stores:
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
                    except NotLoggedIn:
                        self.lib.set_error(store, "Not signed in. Choose Sign in, then close the browser window when you're done.")
                    except Blocked as e:
                        self.lib.set_error(store, (
                            f"{label} blocked the automated browser ({e}). Import your library instead: open it in "
                            f"your usual browser, scroll to the bottom, press Ctrl+S and save it as \"Webpage, Single "
                            f"File\", then choose Import page here.") if store in IMPORTABLE
                            else f"{label} blocked the automated browser ({e}). Try again later.")
                    except Exception as e:
                        self.lib.set_error(store, f"Couldn't read the library: {e}")
            finally:
                ctx.close()
        self._set(message="Library updated")

    def _login_then_refresh(self, stores: list[str]) -> None:
        store = stores[0]
        label = STORES[store]["label"]
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
    req = urllib.request.Request(url, headers={
        "Referer": referer,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get_content_type()
            data = r.read(15 * 1024 * 1024)
    except Exception:
        return None
    if not ctype.startswith("image/"):
        return None
    ext = {"image/jpeg": "jpg", "image/svg+xml": "svg"}.get(ctype, ctype.split("/")[1])
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    (THUMB_DIR / f"{h}.{ext}").write_bytes(data)
    return data, ctype


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, cfg, lib, jobs, lan):
        super().__init__(addr, Handler)
        self.cfg, self.lib, self.jobs, self.lan = cfg, lib, jobs, lan


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *args):
        pass

    def _send(self, status, body: bytes, ctype: str, headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        if self.server.lan:
            return True
        return (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]") in LOOPBACK

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, (HERE / "library.html").read_bytes(), "text/html; charset=utf-8",
                              {"Cache-Control": "no-store"})
        if path == "/api/library":
            with self.server.lib.lock:
                data = json.loads(json.dumps(self.server.lib.data))
            return self._json({"items": enrich(data["items"], self.server.cfg["tags"]), "stores": data["stores"],
                               "labels": {k: v["label"] for k, v in STORES.items()}, "job": self.server.jobs.state,
                               "signins": str(profile_dir(self.server.cfg))})
        if path == "/api/status":
            with self.server.lib.lock:
                stores = json.loads(json.dumps(self.server.lib.data["stores"]))
            return self._json({"job": self.server.jobs.state, "stores": stores})
        if path.startswith("/thumb/"):
            got = fetch_thumbnail(unquote(path[len("/thumb/"):]), self.server.lib)
            if not got:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})
        self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/refresh", "/api/login", "/api/import", "/api/logout"):
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
        if path == "/api/import":
            try:
                store, items = import_saved_page(self.server.cfg, body.get("store"), str(body.get("filename") or ""),
                                                 str(body.get("content") or ""))
            except (ValueError, RuntimeError) as e:
                return self._json({"error": f"Couldn't import: {e}"}, 422)
            total = self.server.lib.merge_store(store, items)
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
    lib = Library(LIBRARY_FILE)
    jobs = Jobs(cfg, lib)
    try:
        srv = Server((host, port), cfg, lib, jobs, lan=host not in LOOPBACK)
    except OSError as e:
        sys.exit(f"Couldn't start on port {port} ({e}). Try the command: --port {port + 1}")
    url = f"http://127.0.0.1:{port}/"
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
    with _playwright()() as p:
        ctx = launch(p, cfg, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(STORES[store]["login"])
        input(f"Sign in to {STORES[store]['label']} in the browser window, then press Enter here... ")
        ctx.close()
    print(f"Saved. Your sign-ins are kept in {profile_dir(cfg)}, encrypted by your operating system.")


def cmd_refresh(cfg, stores):
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
