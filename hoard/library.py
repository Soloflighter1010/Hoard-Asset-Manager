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

from .config import NewShop, apply_store_sites, clean_payhip_shop, payhip_shops
from . import itch, vault
from .browser import _playwright, goto, goto_past_check, has_password_field, settle
from .common import NotLoggedIn, now_iso
from .net import STORE_HOSTS
from .paths import THUMB_DIR
from .safety import DataFileError, STORE_LINK_SITES, check_seal, clean_text, fetch_public, inert_html, offline_page, read_json_file, remember_sealed, safe_url, seal, set_aside, store_link, write_file_safely
from .tags import TagMatcher, TagStore, tag_key


STORES = {
    "booth": {"label": "Booth", "login": "https://accounts.booth.pm/library", "referer": "https://booth.pm/"},
    "gumroad": {"label": "Gumroad", "login": "https://app.gumroad.com/login", "referer": "https://gumroad.com/"},
    "jinxxy": {"label": "Jinxxy", "login": "https://jinxxy.com/my/inventory", "referer": "https://jinxxy.com/"},
    "payhip": {"label": "Payhip", "login": "https://payhip.com/auth/login", "referer": "https://payhip.com/"},
    "itch": {"label": "itch.io", "login": "https://itch.io/user/settings/api-keys", "referer": "https://itch.io/"},
}


# The stores Hoard downloads from. Payhip is only read: its bot check made downloading unreliable, so Hoard lists
# what you own there, with each product's download page, and you download from Payhip yourself.
DOWNLOADABLE = ("booth", "gumroad", "jinxxy", "itch")


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
    // Files. Booth now draws each file's buttons from placeholders that carry the address in data-href
    // (2026); older pages used plain links. "Download" is the file itself; "Open in Browser" (?browse=1) and the
    // Booth Library Manager links (/deeplink) are other ways to the same file, so they're skipped.
    const FILE_SEL = '[data-href*="/downloadables/"], a[href*="/downloadables/"]';
    const addr = el => el.getAttribute('data-href') || el.getAttribute('href') || '';
    const fileId = el => {
      const h = addr(el), m = h.match(/\/downloadables\/(\d+)(?:[?#]|$)/);
      return m && !/[?&]browse=/.test(h) && (el.getAttribute('data-test') || 'downloadable') === 'downloadable' ? m[1] : null;
    };
    const seen = new Set(), files = [];
    for (const d of c.querySelectorAll(FILE_SEL)) {
      const fid = fileId(d);
      if (!fid || seen.has(fid)) continue;
      seen.add(fid);
      let r = d;   // the file's row: widen from its button while the row is still about this one file
      while (r.parentElement && r.parentElement !== c) {
        const p = r.parentElement;
        const ids = new Set([...p.querySelectorAll(FILE_SEL)].map(x => (addr(x).match(/\/downloadables\/(\d+)/) || [])[1]).filter(Boolean));
        if (ids.size > 1 || p.querySelector('a[href*="/items/"], img')) break;
        r = p;
      }
      const row = r.cloneNode(true);
      row.querySelectorAll('.js-download-button, button, [data-href], a[href*="/downloadables/"]').forEach(x => x.remove());
      const name = (row.textContent || '').replace(/\s+/g, ' ').replace(/ダウンロード|Download|Open in Browser|Other Downloads/gi, '').trim();
      files.push({ name: name || 'File', url: new URL(addr(d), location.href).href });
    }
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
    sources = [("", False)] + ([("/gifts", True)] if cfg["booth"].get("include_gifts", True) else []) \
        + ([("/free_downloads", False)] if cfg["booth"].get("include_free", True) else [])
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
  // Page furniture, never an item's name
  const GENERIC = /^(navigation|menu|profile|likes|lists|wishlist|inventory|marketplace|popular|leaderboard|product details|details|support info|my review)$/i;
  // The site's menus, header, footer and sidebars: an item's card never reaches into them
  const LANDMARKS = 'nav, aside, header, footer, [role="navigation"], [role="banner"], [role="contentinfo"], [role="complementary"]';
  // You, the signed-in user: the profile your "Profile" link points to is never an item's creator
  const own = new Set();
  for (const l of document.querySelectorAll('a[href]')) {
    const t = (l.innerText || l.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    if (!/^(profile|my profile|view profile|account|my account)$/i.test(t)) continue;
    try { const segs = new URL(l.href).pathname.split('/').filter(Boolean); if (segs.length === 1) own.add(segs[0].toLowerCase()); } catch (e) {}
  }
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
      const p = c.parentElement;
      if (p.matches('main, [role="main"]')) break;               // never past the page's content
      if ([...p.querySelectorAll(LANDMARKS)].some(l => !c.contains(l))) break;  // never into menus or sidebars
      const keys = new Set([...p.querySelectorAll('a[href]')].filter(x => set.has(x)).map(keyOf));
      if (keys.size > 1) break;                                    // never into a second item
      c = p;
    }
    // Creator: a link to their store page (jinxxy.com/<name>), else a "by ..." line
    let creator = '', creatorUrl = '';
    for (const s of c.querySelectorAll('a[href]')) {
      if (set.has(s)) continue;
      let u; try { u = new URL(s.href); } catch (e) { continue; }
      const segs = u.pathname.split('/').filter(Boolean);
      if (onJinxxy(u) && (segs.length === 1 || (segs.length === 2 && segs[1] === 'products'))
          && !RESERVED.has(segs[0].toLowerCase()) && !own.has(segs[0].toLowerCase()) && !s.closest(LANDMARKS)) {
        creator = linesOf(s)[0] || segs[0]; creatorUrl = u.origin + '/' + segs[0]; break;
      }
    }
    const lines = linesOf(c).filter(s => !GENERIC.test(s));
    const byLine = lines.find(s => /^by\s+/i.test(s));
    if (!creator && byLine) creator = byLine.replace(/^by\s+/i, '');
    const heading = [...c.querySelectorAll('h1, h2, h3, h4, h5, h6, [class*="title" i]')]
      .map(h => linesOf(h)[0]).find(t => t && !GENERIC.test(t));
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
# Payhip keeps your purchases in each shop you bought from, on that shop's own library page (<shop>/b-account),
# not in one library. Hoard reads Payhip and never downloads from it. PAYHIP_SHOP_JS reads a shop's library page,
# PAYHIP_CARDS_JS a page saved from Payhip's own site. If either gets things wrong, run: debug payhip

PAYHIP_NO_SHOPS = ("Payhip keeps your purchases in each shop you bought from, not in one library. Import each "
                   "shop's saved library pages (Import pages, in Stores), or add your shops in Settings to refresh "
                   "them (a shop's address is in your purchase email).")


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


PAYHIP_SHOP_JS = r"""
() => {
  // A Payhip shop's own library page (https://<shop>/b-account): one card per product you bought there,
  // each linking to its download page at /b-account/digital/<code>.
  const LANDMARKS = 'nav, header, footer, aside, [role="navigation"], [role="banner"], [role="contentinfo"]';
  const pathOf = a => { try { return new URL(a.href).pathname.replace(/\/$/, ''); } catch (e) { return ''; } };
  const isProduct = a => /\/b-account\/(digital|products?|downloads?)\/[^/]+$/i.test(pathOf(a));
  const text = e => ((e && e.innerText) || '').replace(/\s+/g, ' ').trim();
  const shopName = text(document.querySelector('a.logo-link, .logo-link'))
    || (document.title.includes(' - ') ? document.title.split(' - ').slice(1).join(' - ').trim() : '');
  const cards = new Map();
  for (const a of document.querySelectorAll('a[href]')) {
    if (!isProduct(a) || a.closest(LANDMARKS)) continue;
    const key = pathOf(a);
    if (cards.has(key)) continue;
    let c = a;   // the product's card: widen from its link while it's still about this one product
    while (c.parentElement && c.parentElement !== document.body) {
      const p = c.parentElement;
      if (p.matches('main, [role="main"]')) break;
      if (new Set([...p.querySelectorAll('a[href]')].filter(isProduct).map(pathOf)).size > 1) break;
      c = p;
    }
    const heading = c.querySelector('.product-name, h1, h2, h3, h4, h5');
    const img = c.querySelector('img');
    const url = a.href.split(/[?#]/)[0], host = new URL(url).hostname;
    cards.set(key, { id: host + ':' + key.split('/').pop(), name: text(heading) || text(a) || (img && img.alt) || '',
                     creator: shopName || host, creator_url: url.split('/b-account')[0],
                     thumbnail: img ? (img.currentSrc || img.src || '') : '',
                     url, download_url: url, bought: text(c.querySelector('.card-meta')) });
  }
  const next = [...document.querySelectorAll('a[rel="next"], .pagination a, a.next')]
    .find(x => /next|›|»/i.test(text(x) + ' ' + (x.getAttribute('rel') || '')));
  return { cards: [...cards.values()], next: next ? next.href : null, shop: shopName };
}
"""


def read_payhip_shop(page, shop: str, cfg: dict, progress) -> list[dict]:
    """Every product you bought from one Payhip shop, from its library page (<shop>/b-account), all its pages."""
    url, cards = shop + "/b-account", {}
    wait = float(cfg["payhip"].get("bot_check_wait", 180)) if cfg["payhip"].get("headed", True) else 0
    for page_no in range(1, 200):   # 15 products a page: 3,000 products
        goto_past_check(page, url, wait, progress)
        settle(page)
        if "/b-account" not in urlparse(page.url).path or has_password_field(page):
            raise NotLoggedIn(f"not signed in to {urlparse(shop).hostname}{urlparse(shop).path}")
        result = page.evaluate(PAYHIP_SHOP_JS)
        for c in result["cards"]:
            cards.setdefault(c["id"], c)
        progress(f"{result['shop']}: {len(cards)} products")
        if not result["next"] or result["next"] == url:
            break
        url = result["next"]
        time.sleep(float(cfg.get("request_delay", 0.8)))
    return list(cards.values())


def open_sign_in_pages(ctx, cfg: dict, store: str):
    """Open the page(s) where you sign in to a store. For Payhip, one tab per shop in your settings (each shop keeps
    its own buyer account); with no shops listed yet, Payhip's own sign-in page."""
    first = ctx.pages[0] if ctx.pages else ctx.new_page()
    urls = [s + "/b-account" for s in payhip_shops(cfg)] if store == "payhip" else []
    urls = urls or [STORES[store]["login"]]
    first.goto(urls[0])
    for url in urls[1:]:
        ctx.new_page().goto(url)
    return first


def fetch_payhip(ctx, cfg, progress) -> list[dict]:
    """Every product you bought on Payhip. Payhip keeps purchases in each shop, so this reads every shop in
    your settings; a shop you aren't signed in to is noted and the others still count."""
    shops = payhip_shops(cfg)
    if not shops:
        raise RuntimeError(PAYHIP_NO_SHOPS)
    page = ctx.new_page()
    cards: dict[str, dict] = {}
    signed_out = []
    try:
        for shop in shops:
            try:
                for c in read_payhip_shop(page, shop, cfg, progress):
                    cards.setdefault(c["id"], c)
            except NotLoggedIn:
                signed_out.append(shop.split("://", 1)[1])
    finally:
        page.close()
    if signed_out and not cards:
        raise NotLoggedIn("not signed in to " + ", ".join(signed_out))
    if signed_out:
        progress(f"Not signed in to {', '.join(signed_out)}; sign in to Payhip again to include them")
    # Payhip's library lists purchases from every shop, including shops on their own domains. Those aren't trusted
    # until you add them (their links are left out till then), so they're offered for you to review.
    known = set(payhip_shops(cfg)) | {"https://payhip.com"}
    found = {s for s in (clean_payhip_shop(c.get("creator_url")) for c in cards.values()) if s and s not in known
             and not s.startswith("https://payhip.com/")}
    cfg["_found_payhip_shops"] = sorted(found)
    return [payhip_item(c) for c in cards.values()]


def payhip_item(c: dict) -> dict:
    """Turn a card read from Payhip's library page into a library item."""
    return item("payhip", c["id"].strip("/").replace("/", "-"), name=c["name"], creator=c["creator"],
                creator_url=c["creator_url"], thumbnail=c["thumbnail"], url=c["url"], download_url=c["download_url"])


# ----------------------------------------------------------------------------- itch.io
#
# itch.io is read through its API (itch.py), with an API key you create on itch.io: its website shows automated
# browsers a Cloudflare check they never get past. ITCH_JS reads a library page you saved yourself (itch.io/
# my-purchases), for importing: a card per project, each with a Download button leading to the project's download
# page (<creator>.itch.io/<project>/download/<key>). Items are known by itch.io's own project number either way.

ITCH_LIBRARY = "https://itch.io/my-purchases"


ITCH_JS = r"""
() => {
  const text = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim();
  const LANDMARKS = 'nav, header, footer, aside, [role="navigation"], [role="banner"], [role="contentinfo"]';
  const NOT_CREATORS = new Set(['www', 'static', 'img', 'api', 'itch', 'assets', 'cdn']);
  // A creator's site (<creator>.itch.io), one of their projects (<creator>.itch.io/<project>), or a project's
  // download page (<creator>.itch.io/<project>/download/<key>)
  const parse = href => {
    let u; try { u = new URL(href, location.href); } catch (e) { return null; }
    const m = u.hostname.toLowerCase().replace(/\.$/, '').match(/^([a-z0-9][a-z0-9-]*)\.itch\.io$/);
    if (u.protocol !== 'https:' || !m || NOT_CREATORS.has(m[1])) return null;
    const segs = u.pathname.split('/').filter(Boolean);
    if (!segs.length) return { kind: 'creator', creator: m[1], url: u.origin };
    const id = m[1] + '/' + segs[0].toLowerCase(), url = u.origin + '/' + segs[0];
    if (segs.length === 1) return { kind: 'project', id, url };
    if (segs.length === 3 && segs[1] === 'download' && /^[A-Za-z0-9_-]{6,}$/.test(segs[2]))
      return { kind: 'download', id, url: url + '/download/' + segs[2] };
    return null;
  };
  const links = [];
  for (const a of document.querySelectorAll('a[href]')) {
    if (a.closest(LANDMARKS)) continue;
    const p = parse(a.getAttribute('href'));
    if (p && p.kind !== 'creator') { a.setAttribute('data-hoard-project', p.id); links.push({ a, ...p }); }
  }
  // Yours: every project with a download page here. On a page with no download pages at all (a layout Hoard
  // doesn't know), the project cards itch.io marks with an id, so the library still lists them.
  const withDownload = new Set(links.filter(l => l.kind === 'download').map(l => l.id));
  const owned = withDownload.size ? withDownload
    : new Set(links.filter(l => l.a.closest('[data-game_id]')).map(l => l.id));
  const cardOf = (a, id) => {   // the project's card: widen from its link while it's still about this one project
    let c = a;
    while (c.parentElement && c.parentElement !== document.body) {
      const p = c.parentElement;
      if (p.matches('main, [role="main"]')) break;
      if ([...p.querySelectorAll('[data-hoard-project]')].some(x => x.getAttribute('data-hoard-project') !== id)) break;
      c = p;
    }
    return c;
  };
  const picture = c => {   // itch.io loads pictures as you scroll: the address waits in data-lazy_src until then
    const img = c.querySelector('a[data-hoard-project] img') || c.querySelector('img');
    const src = img ? (img.getAttribute('data-lazy_src') || img.getAttribute('data-src') || img.currentSrc || img.getAttribute('src') || '') : '';
    if (src && !src.startsWith('data:')) return src;
    const bg = c.querySelector('[data-background_image]');
    if (bg) return bg.getAttribute('data-background_image');
    const styled = [c, ...c.querySelectorAll('[style*="background-image"]')]
      .map(e => (e.getAttribute('style') || '').match(/url\(["']?([^"')]+)/)).find(Boolean);
    return styled ? styled[1] : '';
  };
  const cards = new Map();
  for (const l of links) {
    if (!owned.has(l.id)) continue;
    const old = cards.get(l.id);
    if (old) { if (l.kind === 'download' && !old.download_url) old.download_url = l.url; continue; }
    const c = cardOf(l.a, l.id);
    const mine = links.filter(x => x.id === l.id && c.contains(x.a));
    const img = c.querySelector('img');
    const name = mine.filter(x => x.kind === 'project').map(x => text(x.a)).find(Boolean)
      || text(c.querySelector('.game_title, .title')) || (img && img.alt) || l.id.split('/')[1];
    const who = l.id.split('/')[0];
    let creator = '', creatorUrl = 'https://' + who + '.itch.io';
    for (const a of c.querySelectorAll('a[href]')) {
      const p = parse(a.getAttribute('href'));
      if (p && p.kind === 'creator' && p.creator === who && text(a)) { creator = text(a); creatorUrl = p.url; break; }
    }
    creator = creator || text(c.querySelector('.game_author')).replace(/^by\s+/i, '') || who;
    const page = mine.find(x => x.kind === 'project'), dl = mine.find(x => x.kind === 'download');
    const cell = l.a.closest('[data-game_id]'), number = cell && cell.getAttribute('data-game_id');
    cards.set(l.id, { id: /^\d{1,20}$/.test(number || '') ? number : l.id, name, creator, creator_url: creatorUrl, thumbnail: picture(c),
                      url: page ? page.url : l.url.split('/download/')[0], download_url: dl ? dl.url : '' });
  }
  const next = [...document.querySelectorAll('a[rel="next"], a.next_page, .pager a, .pagination a')]
    .find(a => /next|›|»/i.test(text(a) + ' ' + (a.getAttribute('rel') || '') + ' ' + (a.className || '')));
  let nextUrl = null;
  if (next) {
    try { const u = new URL(next.getAttribute('href'), location.href); if (u.protocol === 'https:' && u.hostname === 'itch.io') nextUrl = u.href; } catch (e) {}
  }
  return { cards: [...cards.values()], next: nextUrl };
}
"""


def fetch_itch(ctx, cfg, progress) -> list[dict]:
    """Everything you own on itch.io, through its API (no browser: ctx is unused)."""
    key = vault.load_key(cfg, "itch")
    if not key:
        raise NotLoggedIn("No itch.io API key yet")
    sess = itch.session(key)
    try:
        keys = itch.owned_keys(sess, float(cfg.get("request_delay", 1.0)), progress)
    finally:
        sess.close()
    items = []
    for k in keys:
        g = itch.game_of(k)
        if g["id"]:
            items.append(item("itch", g["id"], name=g["title"], creator=g["creator"], creator_url=g["creator_url"],
                              thumbnail=g["cover"], url=g["url"]))
    return items


def itch_item(c: dict) -> dict:
    """Turn a card read from your itch.io library into a library item."""
    return item("itch", c["id"], name=c["name"], creator=c["creator"], creator_url=c.get("creator_url"),
                thumbnail=c.get("thumbnail"), url=c.get("url"), download_url=c.get("download_url"))


FETCHERS = {"booth": fetch_booth, "gumroad": fetch_gumroad, "jinxxy": fetch_jinxxy, "payhip": fetch_payhip,
            "itch": fetch_itch}


# ----------------------------------------------------------------------------- saved pages
#
# When a store won't let Hoard's browser read your library (or, for Payhip, when you'd rather not sign in), you can
# save the library pages from your own browser and import them. A library often spans several pages (Payhip keeps
# one per shop), so any number are imported at once, read together in one browser with scripts off and no network.

IMPORTABLE = ("booth", "jinxxy", "payhip", "itch")


IMPORT_BASES = {"booth": "https://accounts.booth.pm/library", "jinxxy": JX_INVENTORY, "payhip": "https://payhip.com/",
                "itch": ITCH_LIBRARY}


SAVED_PAGE_TYPES = (".mhtml", ".mht", ".html", ".htm")


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
                try:
                    page_html = raw.decode(part.get_content_charset() or "utf-8", "replace")
                except LookupError:   # a character set Python doesn't know
                    page_html = raw.decode("utf-8", "replace")
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


def _prepare_import(cfg: dict, store: str | None, filename: str, text: str, trust_shops: set) -> dict:
    """Which store a saved page is from, and the page ready to read: scripts stripped, anything that could run
    removed, and its own address as the base for its links. Raises NewShop for a page from a Payhip shop that isn't
    in your list (unless trust_shops names it), and ValueError for a page that can't be imported."""
    if store not in (None, "", "auto") and store not in STORES:
        raise ValueError("unknown store")
    page_html, source_url, images = read_saved_page(filename, text)
    detected = store_for_url(source_url)
    shop_page = "/b-account" in urlparse(source_url or "").path
    if shop_page and not detected and store in (None, "", "auto", "payhip"):
        # A Payhip shop's own library page, on the shop's own domain. A shop Hoard doesn't know yet is only added
        # when you confirm its exact address (trust_shops): an address inside a file isn't enough on its own.
        shop = clean_payhip_shop(source_url)
        if not shop:
            raise ValueError("that page's address isn't one Hoard can use as a Payhip shop")
        if shop not in payhip_shops(cfg):
            if shop not in trust_shops:
                raise NewShop(shop)
            cfg["payhip"]["shops"] = list(dict.fromkeys((cfg["payhip"].get("shops") or []) + [shop]))
            apply_store_sites(cfg)
        detected = "payhip"
    if not store or store == "auto":
        store = detected
        if not store:
            raise ValueError("couldn't tell which store this page is from. Use Import pages on that store's row in "
                             "Stores.")
    elif detected and detected != store:
        raise ValueError(f"that page is from {STORES[detected]['label']}, not {STORES[store]['label']}")
    if store not in IMPORTABLE:
        raise ValueError(f"{STORES[store]['label']} doesn't need importing; its refresh reads everything")
    base = source_url or IMPORT_BASES[store]
    page_html = re.sub(r"<script\b[^>]*>.*?</script>", "", page_html, flags=re.S | re.I)  # don't run the saved page
    head = re.search(r"<head[^>]*>", page_html, re.I)
    base_tag = f'<base href="{html.escape(base, quote=True)}">'
    page_html = page_html[:head.end()] + base_tag + page_html[head.end():] if head else base_tag + page_html
    return {"store": store, "html": inert_html(page_html), "base": base, "shop_page": shop_page, "images": images}


def _read_import(browser, cfg: dict, prep: dict) -> list[dict]:
    """The items on one prepared page (see _prepare_import), read offline, with the images saved inside it kept."""
    store = prep["store"]
    page = offline_page(browser)   # scripts off, no network: read the file, run nothing, contact nobody
    try:
        page.set_content(prep["html"], wait_until="domcontentloaded")
        if store == "booth":
            gift = "/gifts" in urlparse(prep["base"]).path
            items = [booth_item(b, gift, prep["base"].split("?")[0]) for b in page.evaluate(BOOTH_JS)]
        elif store == "jinxxy":
            seen = {}
            for c in page.evaluate(JX_CARDS_JS, cfg["jinxxy"]["item_link_pattern"]):
                seen.setdefault(c["key"], c)
            items = [jinxxy_item(c) for c in seen.values()]
        elif store == "itch":
            items = [itch_item(c) for c in page.evaluate(ITCH_JS)["cards"]]
        else:
            items = [payhip_item(c) for c in page.evaluate(PAYHIP_SHOP_JS if prep["shop_page"] else PAYHIP_CARDS_JS)["cards"]]
    finally:
        page.context.close()
    if not items:
        raise ValueError(f"no {STORES[store]['label']} items in that page. Save your library page itself, after "
                         "everything on it has loaded (scroll to the bottom first).")
    for i in items:  # keep the images that came inside the file (plain raster images only)
        if i.get("thumbnail") in prep["images"]:
            data, ctype = prep["images"][i["thumbnail"]]
            if ctype not in IMAGE_TYPES:
                continue
            THUMB_DIR.mkdir(parents=True, exist_ok=True)
            write_file_safely(THUMB_DIR / f"{hashlib.sha1(i['thumbnail'].encode()).hexdigest()}.{IMAGE_TYPES[ctype]}", data)
    return items


def import_saved_pages(cfg: dict, pages, store: str | None = None, trust_shops=(), progress=lambda done, total, name: None) -> list[dict]:
    """Read store pages saved from your own browser, (filename, text) each, and return one result per page, in order:

    - {"filename", "store", "items"} for a page that was read,
    - {"filename", "confirm_shop"} for a page from a Payhip shop that isn't in your list, unless trust_shops names
      it: an address inside a file isn't trusted on its own, so the caller asks you first,
    - {"filename", "error"} for a page that couldn't be imported. One bad page never stops the others.

    Shops in trust_shops that a page comes from are added to cfg["payhip"]["shops"]; the caller saves the settings.
    Every page is read in one browser, with scripts off and every network request blocked (see offline_page).
    """
    trusted = {s for s in (clean_payhip_shop(x) for x in trust_shops or ()) if s}
    results: list[dict] = []
    ready: list[tuple[dict, dict]] = []
    for filename, text in pages:
        result = {"filename": filename}
        results.append(result)
        try:
            ready.append((result, _prepare_import(cfg, store, filename, text, trusted)))
        except NewShop as e:
            result["confirm_shop"] = e.shop
        except Exception as e:   # a damaged or unexpected file: say so, and carry on with the rest
            result["error"] = str(e) or type(e).__name__
    if ready:
        with _playwright()() as p:
            browser = p.chromium.launch()
            try:
                for n, (result, prep) in enumerate(ready, 1):
                    progress(n, len(ready), result["filename"])
                    try:
                        result.update(store=prep["store"], items=_read_import(browser, cfg, prep))
                    except Exception as e:
                        result.pop("store", None)
                        result["error"] = str(e).splitlines()[0] if str(e) else type(e).__name__
            finally:
                browser.close()
    return results


def import_saved_page(cfg: dict, store: str | None, filename: str, text: str, trust_shop: str | None = None) -> tuple[str, list[dict]]:
    """Read one store page saved from your own browser and return (store, items). Raises NewShop when the page is
    from a Payhip shop you haven't added (and trust_shop isn't its exact address), and ValueError when it can't be
    imported. See import_saved_pages."""
    (result,) = import_saved_pages(cfg, [(filename, text)], store, [trust_shop] if trust_shop else [])
    if "confirm_shop" in result:
        raise NewShop(result["confirm_shop"])
    if "error" in result:
        raise ValueError(result["error"])
    return result["store"], result["items"]


def saved_pages_in(paths, limit: int = 2000) -> list[Path]:
    """The saved pages among these files and folders (folders are searched, with everything in them), in order and
    without repeats; at most limit."""
    found: dict[Path, None] = {}
    for path in paths:
        path = Path(path)
        if path.is_dir():
            inside = []
            for f in path.rglob("*"):
                if f.suffix.lower() in SAVED_PAGE_TYPES and f.is_file():
                    inside.append(f)
                    if len(found) + len(inside) >= limit:
                        break
            for f in sorted(inside):
                found.setdefault(f, None)
        else:
            found.setdefault(path, None)
        if len(found) >= limit:
            break
    return list(found)[:limit]


# ----------------------------------------------------------------------------- library data

class Library:
    """Your combined library, kept in library.json. Safe to use from several threads."""
    def __init__(self, path: Path):
        """Load library.json, or start empty."""
        self.path = path
        self.lock = threading.Lock()
        self.data = {"items": [], "stores": {}}
        self._pictured, self._pictured_from = {}, None   # key -> item with a picture, for data["items"] (see _with_picture)
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
                    **({"found_shops": [f for f in info["found_shops"][:200] if isinstance(f, str) and clean_payhip_shop(f) == f]}
                       if store == "payhip" and isinstance(info.get("found_shops"), list) else {}),
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

    def forget_products(self, keys: set) -> int:
        """Delete these products (by product key) from the list, with their cached pictures. Returns how many."""
        with self.lock:
            gone = [i for i in self.data["items"] if tag_key(i["store"], i["name"]) in keys]
            self.data["items"] = [i for i in self.data["items"] if tag_key(i["store"], i["name"]) not in keys]
            for store in {i["store"] for i in gone}:
                info = self.data["stores"].get(store)
                if isinstance(info, dict):
                    info["count"] = sum(1 for i in self.data["items"] if i["store"] == store)
            self.save()
        for i in gone:
            if i.get("thumbnail"):
                for cached in THUMB_DIR.glob(hashlib.sha1(i["thumbnail"].encode()).hexdigest() + ".*"):
                    cached.unlink(missing_ok=True)
        return len(gone)

    def clear_store(self, store: str, note: str) -> int:
        """Forget a store's items and their cached pictures (after signing out, so the next account on this
        computer never sees them). Downloaded files aren't touched. Returns how many items were removed."""
        with self.lock:
            gone = [i for i in self.data["items"] if i["store"] == store]
            self.data["items"] = [i for i in self.data["items"] if i["store"] != store]
            self.data["stores"][store] = {"updated": None, "count": 0, "error": note}
            self.save()
        for i in gone:
            if i.get("thumbnail"):
                for cached in THUMB_DIR.glob(hashlib.sha1(i["thumbnail"].encode()).hexdigest() + ".*"):
                    cached.unlink(missing_ok=True)
        return len(gone)

    def set_error(self, store: str, message: str) -> None:
        """Note a problem with a store without touching its items."""
        with self.lock:
            s = self.data["stores"].setdefault(store, {"updated": None, "count": 0})
            s["error"] = message
            self.save()

    def snapshot(self) -> tuple[list[dict], dict]:
        """The items and each store's notes as they are now, to read without holding the lock. Every change replaces
        the list of items rather than editing the items in it, so a copy of the list is a consistent picture; the
        store notes are edited in place, so each is copied."""
        with self.lock:
            return list(self.data["items"]), {s: dict(info) for s, info in self.data["stores"].items()}

    def thumbnail_for(self, key: str) -> tuple[str, str] | None:
        """(image address, referrer) for an item's thumbnail, or None."""
        with self.lock:
            i = self._with_picture(key)
            return (i["thumbnail"], STORES[i["store"]]["referer"]) if i else None

    def _with_picture(self, key: str) -> dict | None:
        """The item with this key, if it has a picture, found in a lookup table instead of by going through the whole
        list for every picture shown. Every change replaces data["items"], so the table is made again when that list
        isn't the one it was made from. Call with the lock held."""
        items = self.data["items"]
        if self._pictured_from is not items:
            self._pictured = {}
            for i in items:
                if i.get("thumbnail"):
                    self._pictured.setdefault(i["key"], i)   # the first, as a walk through the list would find
            self._pictured_from = items
        return self._pictured.get(key)


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
    matcher = TagMatcher(tagdata["tags"])
    for i, ts in zip(items, toks):
        key = tag_key(i["store"], i["name"])
        mine = TagStore.tags_for(tagdata, key, i["name"], matcher)
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
