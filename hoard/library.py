"""Everything you own on every store: the store readers, saved-page imports and your library list."""
from __future__ import annotations

import email
import hashlib
import html
import json
import re
import threading
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from .browser import _playwright, goto, has_password_field, settle
from .common import NotLoggedIn, now_iso
from .net import STORE_HOSTS
from .paths import THUMB_DIR
from .safety import STORE_LINK_SITES, DataFileError, check_seal, clean_text, fetch_public, read_json_file, remember_sealed, safe_url, seal, set_aside, store_link, write_file_safely
from .tags import TagStore, tag_key


STORES = {
    "booth": {"label": "Booth", "login": "https://accounts.booth.pm/library", "referer": "https://booth.pm/"},
    "gumroad": {"label": "Gumroad", "login": "https://app.gumroad.com/login", "referer": "https://gumroad.com/"},
    "jinxxy": {"label": "Jinxxy", "login": "https://jinxxy.com/my/inventory", "referer": "https://jinxxy.com/"},
    "payhip": {"label": "Payhip", "login": "https://payhip.com/auth/login", "referer": "https://payhip.com/"},
}


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
    host = (urlparse(url or "").hostname or "").rstrip(".")
    return next((s for s, sites in STORE_LINK_SITES.items() if any(host == h or host.endswith("." + h) for h in sites)), None)


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


def unreachable_message(store: str, what: str = "refreshed") -> str:
    """What to tell you when a store's website can't be reached."""
    host = STORE_HOSTS[store].replace("accounts.", "").replace("app.", "")
    return (f"Couldn't reach {host}, so {STORES[store]['label']} wasn't {what}. You may be offline, or the store may "
            "be down. Your saved list is unchanged; try again when you're connected.")


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
