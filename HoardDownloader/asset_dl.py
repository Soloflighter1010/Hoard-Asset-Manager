#!/usr/bin/env python3
"""
asset_dl - download everything you own on Gumroad and Jinxxy.

Layout under the configured root:
    Gumroad/<Creator>/<Product>/...files      + Gumroad/_manifest.json
    Jinxxy/<Creator>/<Product>/...files       + Jinxxy/_manifest.json
    catalog.json   every asset from both stores, with suggested tags
    tags.json      tag -> assets, built from words that recur across asset names

Each store keeps its own manifest, so re-running only fetches files that are new
or changed, and a product that's renamed on the store keeps its existing folder.

    python asset_dl.py login gumroad      one-time: sign in inside the browser window
    python asset_dl.py login jinxxy
    python asset_dl.py sync               both stores (add --store gumroad|jinxxy, --dry-run, --only TEXT)
    python asset_dl.py tags               rebuild catalog.json / tags.json without downloading
    python asset_dl.py browse             search and browse everything in your web browser
    python asset_dl.py probe jinxxy       dump what the Jinxxy site loads, for tuning its adapter
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

try:
    from tqdm import tqdm
except ImportError:  # progress bars are optional
    tqdm = None

__version__ = "1.0.0"

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / ".browser-profile"   # holds your store logins; never share this folder
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
    "gumroad": {
        "enabled": True,
        "include_archived": True,
        "save_thumbnails": True,
        "session_cookie": "",  # optional: paste _gumroad_app_session instead of using `login`
    },
    "jinxxy": {
        "enabled": True,
        "item_link_pattern": r"^/my/(inventory|purchases|library)/[^/]+/?$",
        "save_thumbnails": True,
        "download_start_timeout": 90,
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
    pass


# ----------------------------------------------------------------------------- helpers

def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_name(value, maxlen: int = 80) -> str:
    """Make a string safe as a single Windows/Linux path component."""
    s = unicodedata.normalize("NFC", str(value or ""))
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
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


def rel_to_path(base: Path, rel: str) -> Path:
    return base.joinpath(*rel.split("/"))


def deep_merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_config(path: Path) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.exists():
        deep_merge(cfg, json.loads(path.read_text("utf-8")))
    else:
        log(f"(no config found at {path} - using defaults; copy config.example.json to config.json to change them)")
    return cfg


def root_dir(cfg: dict) -> Path:
    root = Path(os.path.expandvars(cfg["root"])).expanduser()
    return root if root.is_absolute() else HERE / root


@dataclass
class Report:
    new_assets: list = field(default_factory=list)
    new_files: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    failed: list = field(default_factory=list)

    def print(self) -> None:
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
        self.store_dir = store_dir
        self.path = store_dir / "_manifest.json"
        self.data = json.loads(self.path.read_text("utf-8")) if self.path.exists() else {}
        self.assets: dict = self.data.setdefault("assets", {})

    def save(self) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), "utf-8")
        for attempt in range(10):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:  # Windows: another program (e.g. the browser) is reading it
                if attempt == 9:
                    raise
                time.sleep(0.2)

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
    part = dest.with_name(dest.name + ".part")
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
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright isn't installed. Run Setup.bat (Windows) or ./setup.sh first.")
    return sync_playwright


def launch_context(p, cfg: dict, headless: bool):
    kwargs = dict(user_data_dir=str(PROFILE_DIR), headless=headless, accept_downloads=True,
                  viewport={"width": 1400, "height": 950})
    channel = cfg.get("browser_channel")
    if channel:
        kwargs["channel"] = channel
    return p.chromium.launch_persistent_context(**kwargs)


def browser_cookies(cfg: dict, domain: str) -> tuple[list, str]:
    """Pull cookies for a domain (and a matching User-Agent) out of the saved browser profile."""
    with _playwright()() as p:
        ctx = launch_context(p, cfg, headless=True)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            ua = page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
            cookies = [c for c in ctx.cookies() if c["domain"].lstrip(".").endswith(domain)]
        finally:
            ctx.close()
    return cookies, ua


def cmd_login(cfg: dict, args) -> None:
    url = GR_LOGIN if args.store == "gumroad" else JX_INVENTORY
    with _playwright()() as p:
        ctx = launch_context(p, cfg, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url)
        input(f"\nSign in to {args.store.title()} in the browser window, then press Enter here... ")
        ctx.close()
    log("Saved. You can run `sync` now.")


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
    s = requests.Session()
    s.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
    manual = cfg["gumroad"].get("session_cookie")
    if manual:
        s.cookies.set("_gumroad_app_session", manual, domain=".gumroad.com", path="/")
        return s
    cookies, ua = browser_cookies(cfg, "gumroad.com")
    if not any(c["name"].startswith("_gumroad_app_session") for c in cookies):
        raise NotLoggedIn("Not signed in to Gumroad")
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    s.headers["User-Agent"] = ua
    return s


class Gumroad:
    def __init__(self, cfg: dict, sess: requests.Session):
        self.cfg, self.sess = cfg, sess
        self.delay = float(cfg.get("request_delay", 1.0))

    def page(self, url: str, params: dict | None = None) -> dict:
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
    for it in items or []:
        if it.get("type") == "folder":
            yield from gumroad_files(it.get("children"), prefix + safe_name(it.get("name") or "Folder") + "/")
        elif it.get("type") == "file":
            yield prefix, it


def gumroad_filename(f: dict) -> str:
    name = (f.get("file_name") or f.get("id") or "file").strip()
    ext = (f.get("extension") or "").strip().lower().lstrip(".")
    if ext and not name.lower().endswith("." + ext):
        name = f"{name}.{ext}"
    return safe_name(name, 150)


def save_thumbnail(get_bytes, url: str | None, folder: Path) -> None:
    if not url or any(folder.glob("_thumbnail.*")):
        return
    try:
        data, ctype = get_bytes(url)
        ext = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(ctype.split(";")[0], "jpg")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"_thumbnail.{ext}").write_bytes(data)
    except Exception as e:  # thumbnails are nice-to-have
        log(f"    (thumbnail skipped: {e})")


def sync_gumroad(cfg: dict, root: Path, args, report: Report) -> None:
    store_dir = root / "Gumroad"
    man = Manifest(store_dir)
    gr = Gumroad(cfg, gumroad_session(cfg))

    def get_bytes(url):
        r = gr.sess.get(url, timeout=60)
        r.raise_for_status()
        return r.content, r.headers.get("Content-Type", "")

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
            save_thumbnail(get_bytes, prod.get("thumbnail_url"), folder)
        man.save()


# ----------------------------------------------------------------------------- Jinxxy
#
# Jinxxy has no public API for buyers, so this drives the website with your saved
# login: list the inventory, open each item, click each file's download button.
# If Jinxxy changes its layout, run `probe jinxxy` and adjust item_link_pattern
# in config.json (or share the probe output to rework this into direct API calls).

JX_BUTTONS_JS = r"""
(allowAll) => {
  const dl = /download/i, all = /download\s*all|all\s*files/i;
  const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const text = e => [e.innerText, e.getAttribute('aria-label'), e.getAttribute('title')].filter(Boolean).join(' ');
  const onSite = e => {
    if (e.tagName !== 'A' || e.hasAttribute('download')) return true;
    const h = e.getAttribute('href') || '';
    if (!h || h.startsWith('#') || h.startsWith('javascript:') || h.startsWith('blob:')) return true;
    try { return /(^|\.)jinxxy\.com$/.test(new URL(h, location.href).hostname); } catch (x) { return false; }
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
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def jinxxy_require_login(page) -> None:
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
    try:
        if page is not main_page:
            page.close()
    except Exception:
        pass


def label_key(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\bdownload\b", "", label, flags=re.I)).strip()


def sync_jinxxy(cfg: dict, root: Path, args, report: Report) -> None:
    jcfg = cfg["jinxxy"]
    store_dir = root / "Jinxxy"
    man = Manifest(store_dir)
    delay = float(cfg.get("request_delay", 1.0))

    with _playwright()() as p:
        ctx = launch_context(p, cfg, headless=not args.headed)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(JX_INVENTORY, wait_until="domcontentloaded")
            settle(page, 1500)
            jinxxy_require_login(page)
            links = jinxxy_item_links(page, jcfg["item_link_pattern"])
            if not links:
                raise RuntimeError("found no items on the inventory page - run the command: probe jinxxy")
            log(f"Jinxxy: {len(links)} items in your inventory")

            def get_bytes(url):
                r = ctx.request.get(url)
                return r.body(), r.headers.get("content-type", "")

            for url in links:
                time.sleep(delay)
                try:
                    _jinxxy_item(ctx, page, url, man, store_dir, jcfg, args, report, get_bytes)
                except NotLoggedIn:
                    raise
                except Exception as e:
                    report.failed.append(f"Jinxxy: {url} - {e}")
        finally:
            ctx.close()


def _jinxxy_item(ctx, page, url, man, store_dir, jcfg, args, report, get_bytes) -> None:
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

    buttons = page.evaluate(JX_BUTTONS_JS, False)
    allow_all = not buttons
    if allow_all:  # product only offers a "download all" zip
        buttons = page.evaluate(JX_BUTTONS_JS, True)
    if not buttons:
        report.skipped.append(f"Jinxxy: {name} - no download buttons found on {url}")
        return

    wanted, used = [], set()
    for b in buttons:
        k = label_key(b["label"]) or f"file #{b['idx'] + 1}"
        if k in used:
            k = f"{k} #{b['idx'] + 1}"
        used.add(k)
        wanted.append((b["idx"], b["label"], k))

    got_any = False
    for pos, (_, label, k) in enumerate(wanted):
        old = rec["files"].get(k)
        if old and rel_to_path(folder, old["path"]).exists():
            continue
        if args.dry_run:
            log(f"    would download: {k}")
            continue
        current = page.evaluate(JX_BUTTONS_JS, allow_all)  # re-tag; React may have re-rendered
        match = next((b for b in current if b["label"] == label), current[pos] if pos < len(current) else None)
        if not match:
            report.failed.append(f"Jinxxy: {name} / {k} - button disappeared")
            continue
        dl = jinxxy_click_download(ctx, page, match["idx"], int(jcfg.get("download_start_timeout", 90)))
        if page.url.split("#")[0].rstrip("/") != url.rstrip("/"):  # the click navigated away
            page.goto(url, wait_until="domcontentloaded")
            settle(page)
        if not dl:
            report.failed.append(f"Jinxxy: {name} / {k} - clicking download didn't start a download")
            continue
        fname = safe_name(dl.suggested_filename or k, 150)
        target = folder / fname
        # Same filename under a different label = the creator updated that file
        prev = next((fk for fk, fv in rec["files"].items() if fv.get("path") == fname and fk != k), None)
        is_update = prev is not None or target.exists()
        part = target.with_name(target.name + ".part")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            dl.save_as(str(part))
            os.replace(part, target)
        except Exception as e:
            report.failed.append(f"Jinxxy: {name} / {fname} - {e}")
            continue
        finally:
            close_if_popup(dl.page, page)
        if prev:
            rec["files"].pop(prev, None)
        rec["files"][k] = {"path": fname, "size": target.stat().st_size, "label": label,
                           "downloaded_at": now_iso()}
        log(f"    {'updated' if is_update else 'saved'}: {fname}")
        (report.updated if is_update else report.new_files).append(f"Jinxxy: {creator} / {name} / {fname}")
        got_any = True
        man.save()

    if got_any and is_new_asset:
        report.new_assets.append(f"Jinxxy: {creator} / {name}")
    if jcfg.get("save_thumbnails", True) and not args.dry_run:
        save_thumbnail(get_bytes, info.get("thumbnail"), folder)
    man.save()


REDACT_KEYS = re.compile(r'("[^"]*(?:email|token|password|secret|session|cookie|authorization|jwt|license)[^"]*"\s*:\s*)"[^"]*"', re.I)
REDACT_QS = re.compile(r'((?:X-Amz-[A-Za-z-]+|Signature|Key-Pair-Id|Policy|token|sig)=)[^&"\s]+', re.I)


def redact(s: str) -> str:
    return REDACT_QS.sub(r"\1***", REDACT_KEYS.sub(r'\1"***"', s or ""))


def cmd_probe(cfg: dict, args) -> None:
    """Record what Jinxxy's inventory and first item page load, for tuning the adapter."""
    PROBE_DIR.mkdir(exist_ok=True)
    out = open(PROBE_DIR / "jinxxy_network.jsonl", "w", encoding="utf-8")
    with _playwright()() as p:
        ctx = launch_context(p, cfg, headless=False)
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
            for b in page.evaluate(JX_BUTTONS_JS, True):
                log(f"  download button: {b['label'][:120]}")
        ctx.close()
    out.close()
    log(f"\nWrote {PROBE_DIR}. Skim it for personal info before sharing it with anyone.")


# ----------------------------------------------------------------------------- tags & catalog

def name_tokens(name: str, min_len: int, stop: set) -> set[str]:
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)  # FoxyHoodie -> Foxy Hoodie
    out = set()
    for t in re.findall(r"[^\W_]+", name.lower()):
        if t.isdigit() or re.fullmatch(r"v\d+[a-z]?|\d+(st|nd|rd|th)", t):
            continue
        if len(t) >= min_len and t not in stop:
            out.add(t)
    return out


def read_manifests(root: Path) -> list[dict]:
    assets = []
    for store in ("Gumroad", "Jinxxy"):
        mpath = root / store / "_manifest.json"
        if not mpath.exists():
            continue
        for attempt in range(5):  # sync may be rewriting it right now
            try:
                data = json.loads(mpath.read_text("utf-8"))
                break
            except (ValueError, PermissionError):
                time.sleep(0.2)
        else:
            continue
        for rec in data.get("assets", {}).values():
            if rec.get("files"):
                assets.append({"store": store, **rec})
    return assets


def collect_catalog(cfg: dict, root: Path) -> tuple[list, dict]:
    """Catalog entries + tag index, computed from the manifests on disk. Writes nothing."""
    tcfg = cfg["tags"]
    stop = STOPWORDS | {w.lower() for w in tcfg.get("extra_stopwords", [])}
    block = {w.lower() for w in tcfg.get("blocklist", [])}
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
            if c >= min_count and w not in block and (n < 10 or c / n <= max_share)}

    index: dict[str, list] = {}
    catalog = []
    for a, ts in zip(assets, toks):
        folder = f"{a['store']}/{a['folder']}"
        a_tags = sorted(ts & tags)
        catalog.append({"store": a["store"], "name": a["name"], "creator": a["creator"], "folder": folder,
                        "url": a.get("url"), "variants": a.get("variants"), "added": a.get("first_seen"),
                        "files": sorted(f["path"] for f in a["files"].values()), "suggested_tags": a_tags})
        for t in a_tags:
            index.setdefault(t, []).append(folder)
    catalog.sort(key=lambda e: (e["store"], e["creator"].lower(), e["name"].lower()))
    return catalog, dict(sorted(index.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def build_catalog(cfg: dict, root: Path) -> None:
    """Write catalog.json, tags.json and each product's asset.json."""
    catalog, ordered = collect_catalog(cfg, root)
    if not catalog:
        log(f"No downloaded assets found under {root} - nothing to tag.")
        return
    for entry in catalog:
        adir = rel_to_path(root, entry["folder"])
        if adir.exists():
            (adir / "asset.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False), "utf-8")
    (root / "catalog.json").write_text(json.dumps({"generated_at": now_iso(), "assets": catalog},
                                                  indent=2, ensure_ascii=False), "utf-8")
    (root / "tags.json").write_text(json.dumps({"generated_at": now_iso(), "total_assets": len(catalog),
                                                "tags": {t: {"count": len(v), "assets": v} for t, v in ordered.items()}},
                                               indent=2, ensure_ascii=False), "utf-8")
    top = ", ".join(f"{t} ({len(v)})" for t, v in list(ordered.items())[:25])
    log(f"\nTagged {len(catalog)} assets with {len(ordered)} suggested tags. Top: {top or '-'}")
    log("Prune noisy ones via tags.blocklist in config.json, then run `tags` again.")


# ----------------------------------------------------------------------------- CLI

def cmd_sync(cfg: dict, args) -> None:
    root = root_dir(cfg)
    root.mkdir(parents=True, exist_ok=True)
    log(f"Downloading into {root}")
    report = Report()
    stores = ["gumroad", "jinxxy"] if args.store == "all" else [args.store]
    try:
        for store in stores:
            if not cfg[store].get("enabled", True):
                continue
            try:
                (sync_gumroad if store == "gumroad" else sync_jinxxy)(cfg, root, args, report)
            except NotLoggedIn as e:
                report.failed.append(f"{store.title()}: {e} - sign in to {store.title()} again from the menu (or the command: login {store})")
            except Exception as e:
                report.failed.append(f"{store.title()}: sync stopped - {e}")
    finally:  # also runs after Ctrl+C, so what did download is catalogued
        if not args.dry_run:
            build_catalog(cfg, root)
        report.print()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="hoard-downloader", description=f"Hoard Downloader {__version__}: download your owned Gumroad and Jinxxy assets.")
    ap.add_argument("--version", action="version", version=f"Hoard Downloader {__version__}")
    ap.add_argument("--config", type=Path, default=HERE / "config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("login", help="sign in to a store in a browser window (one-time)")
    s.add_argument("store", choices=["gumroad", "jinxxy"])

    s = sub.add_parser("sync", help="download new/changed files and rebuild tags")
    s.add_argument("--store", choices=["gumroad", "jinxxy", "all"], default="all")
    s.add_argument("--dry-run", action="store_true", help="list what would download, download nothing")
    s.add_argument("--only", help="only products whose name or creator contains this text")
    s.add_argument("--headed", action="store_true", help="show the browser while syncing Jinxxy")

    sub.add_parser("tags", help="rebuild catalog.json and tags.json from what's downloaded")

    s = sub.add_parser("browse", help="open a searchable asset browser in your web browser")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to also reach it from other devices on your network")
    s.add_argument("--no-open", action="store_true", help="don't open a browser tab automatically")

    s = sub.add_parser("probe", help="record what the Jinxxy site loads, for debugging")
    s.add_argument("store", choices=["jinxxy"])

    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.cmd == "login":
        cmd_login(cfg, args)
    elif args.cmd == "sync":
        cmd_sync(cfg, args)
    elif args.cmd == "tags":
        build_catalog(cfg, root_dir(cfg))
    elif args.cmd == "browse":
        from asset_browser import serve
        root = root_dir(cfg)
        serve(root, lambda: collect_catalog(cfg, root)[0], args.host, args.port,
              open_browser=not args.no_open, config_path=args.config)
    elif args.cmd == "probe":
        cmd_probe(cfg, args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\nStopped. Partial downloads resume (Gumroad) or restart (Jinxxy) next run.")
