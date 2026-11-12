"""Jinxxy store adapter: library pages, downloads and recorded wishlist readers.

Shared browser, transport, limits and persistence remain in their common modules.
Compatibility service references preserve dependency overrides during extraction.
"""
from __future__ import annotations

import re
from .services import lib, dl, wish


# ----------------------------------------------------------------------------- Jinxxy
#
# Jinxxy has no buyer API; this reads the inventory page like you would. If it misses
# things, run `python library.py debug jinxxy` and adjust jinxxy.item_link_pattern.

lib_JX_INVENTORY = "https://jinxxy.com/my/inventory"


lib_JX_CARDS_JS = r"""
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
    // The product's own page (jinxxy.com/<creator>/<product>), where the card links it
    let productUrl = '';
    for (const s of c.querySelectorAll('a[href]')) {
      if (set.has(s) || s.closest(LANDMARKS)) continue;
      let u; try { u = new URL(s.href); } catch (e) { continue; }
      const segs = u.pathname.split('/').filter(Boolean);
      if (onJinxxy(u) && segs.length === 2 && !RESERVED.has(segs[0].toLowerCase()) && !own.has(segs[0].toLowerCase())
          && !['products', 'lists', 'posts'].includes(segs[1].toLowerCase())) { productUrl = u.origin + u.pathname.replace(/\/$/, ''); break; }
    }
    const lines = linesOf(c).filter(s => !GENERIC.test(s));
    const byLine = lines.find(s => /^by\s+/i.test(s));
    if (!creator && byLine) creator = byLine.replace(/^by\s+/i, '');
    const heading = [...c.querySelectorAll('h1, h2, h3, h4, h5, h6, [class*="title" i]')]
      .map(h => linesOf(h)[0]).find(t => t && !GENERIC.test(t));
    const img = c.querySelector('img'), vid = c.querySelector('video');   // (a product shown by its video: its still)
    const name = heading || lines.find(s => s !== byLine && s !== creator) || (img && img.alt) || '';
    if (!creator) creator = lines.find(s => s !== name && s !== byLine) || '';
    out.push({ key: keyOf(a), url: a.href.split(/[?#]/)[0], name, creator, creator_url: creatorUrl, page: productUrl,
               thumbnail: img ? (img.currentSrc || img.src || '') : vid ? vid.poster : '', video: !img && !!vid, lines });
  }
  return out;
}
"""


# An inventory item's own page (/my/inventory/<id>): the links on it to a product's page on Jinxxy
# (jinxxy.com/<creator>/<product>), the one around its title first
lib_JX_PRODUCT_JS = r"""
() => {
  const two = a => { try { const u = new URL(a.href); return /(^|\.)jinxxy\.com$/.test(u.hostname)
    && u.pathname.split('/').filter(Boolean).length === 2 ? u.origin + u.pathname.replace(/\/$/, '') : ''; } catch (e) { return ''; } };
  const titled = [...document.querySelectorAll('h1, h2, h3')].map(h => h.closest('a[href]') || h.querySelector('a[href]'));
  const out = [...titled, ...document.querySelectorAll('main a[href]')].filter(Boolean).map(two).filter(Boolean);
  return [...new Set(out)];
}
"""


lib_JX_PAGE_VISITS = 150   # items whose own page is read for their product's page, at most, in one refresh


def lib_jinxxy_product_page(hrefs, creator_url=None) -> str | None:
    """The product's public page among an inventory item page's links (JX_PRODUCT_JS): on its creator's shop when
    Hoard knows the creator, never one of yours."""
    from ..sets import product_link
    shop = (creator_url or "").rstrip("/").lower()
    for h in hrefs if isinstance(hrefs, list) else []:
        u = product_link("jinxxy", h) if isinstance(h, str) else None
        if u and u.count("/") == 4 and (not shop or u.lower().startswith(shop + "/")):
            return u
    return None


def lib_fetch_jinxxy(ctx, cfg, progress) -> list[dict]:
    """Every item in your Jinxxy inventory, scrolling and following pages until nothing new appears; then its Gifts
    tab. What the pages loaded about each item as they did (jinxxy_data) says which are gifts, who from, and each
    product's public page, so few items' own pages need opening (issues #275, #276)."""
    page = ctx.new_page()
    pattern = cfg["jinxxy"]["item_link_pattern"]
    found: dict[str, dict] = {}
    loaded: list = []   # (what the pages loaded from Jinxxy's API, and the data each page came with)
    heard = lib.jinxxy_listener(loaded)
    page.on("response", heard)
    try:
        lib.goto(page, lib.JX_INVENTORY)
        lib.settle(page, 1500)
        if "login" in lib.urlparse(page.url).path.lower() or lib.has_password_field(page):
            raise lib.NotLoggedIn()
        visited, pending = {page.url}, []
        most = lib.QUICK_ITEMS if cfg.get("_quick") else 0   # (a quick refresh, issue #300: the start of it)
        for page_no in range(1, 101):  # numbered pages
            def read() -> int:
                """Note the products now on the inventory page, and its other pages to visit; returns how many are
                known."""
                for c in page.evaluate(lib.JX_CARDS_JS, pattern):
                    old = found.get(c["key"], {})
                    found[c["key"]] = {k: old.get(k) or c.get(k)
                                       for k in ("key", "url", "name", "creator", "creator_url", "thumbnail", "page", "video")}
                for href in lib.jinxxy_inventory_pages(page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")):
                    if href not in visited and href not in pending:
                        pending.append(href)
                progress(f"Inventory, {len(found)} items")
                return len(found)
            lib.scroll_inventory(page, read, most=most)
            loaded.append(lib.jinxxy_page_data(page))
            if not pending or lib.quick_done(cfg, page_no, len(found)):
                break
            nxt = pending.pop(0)
            visited.add(nxt)
            lib.goto(page, nxt)
            lib.settle(page)
        if most:
            found = dict(list(found.items())[:most])
        gifts = lib.jinxxy_gifts(page, pattern, progress, most)
        loaded.append(lib.jinxxy_page_data(page))
        page.remove_listener("response", heard)
        lib.jinxxy_merge(found, gifts, lib.jinxxy_data(loaded))
        loaded.clear()
        if found:
            lib.jinxxy_product_pages(page, found, cfg, progress)
    finally:
        page.close()
    if not found:
        raise RuntimeError("found no items on the inventory page. Run the command: debug jinxxy")
    return [lib.jinxxy_item(c) for c in found.values()]


def lib_jinxxy_product_pages(page, found: dict, cfg: dict, progress) -> None:
    """Each item's public product page (what a set you share links to), where the inventory didn't show it: one a
    refresh found before (cfg["_known_pages"], from the library), else read from the item's own page, at most
    JX_PAGE_VISITS in one refresh, with the usual pause between pages. An item whose page can't be read keeps its
    creator's page."""
    known = cfg.pop("_known_pages", None) or {}
    pictures = cfg.pop("_known_pictures", None) or {}   # (each product's picture a refresh found before)
    stillless = lambda c: c.get("video") and (not c.get("thumbnail") or lib.is_video_address(c["thumbnail"]))  # noqa: E731
    for c in found.values():
        c["page"] = c.get("page") or known.get(lib.jinxxy_key(c))
        if stillless(c) and pictures.get(lib.jinxxy_key(c)):
            c["thumbnail"] = pictures[lib.jinxxy_key(c)]
    todo = [c for c in found.values() if not c.get("page") and lib.store_link("jinxxy", c.get("url"))][:lib.JX_PAGE_VISITS]
    delay = float(cfg.get("request_delay", 0.8))
    for n, c in enumerate(todo, 1):
        progress(f"Product pages, {n} of {len(todo)}")
        try:
            lib.goto(page, c["url"])
            lib.settle(page)
            c["page"] = lib.jinxxy_product_page(page.evaluate(lib.JX_PRODUCT_JS), c.get("creator_url"))
            if stillless(c):   # (shown by its video: the video's still, while here)
                c["thumbnail"] = page.evaluate(lib.STILL_JS) or c.get("thumbnail")
        except Exception as e:   # (one page that won't open never stops the refresh)
            print(f"Jinxxy: couldn't read the product page of {c.get('name')!r}: {str(e)[:200]}", flush=True)
        lib.pause(delay)
    # a product its card showed by a video, with no still: the picture its public page gives (issue #212)
    from ..wishlists import pictures_from_pages, read_store_page
    pictures_from_pages([c for c in found.values() if stillless(c) and c.get("page")], read_store_page, progress, delay,
                        page_of=lambda c: c["page"])


# ---- What Jinxxy's pages load about your inventory (issues #275, #276)
#
# Jinxxy's inventory page comes with its first items' data in its scripts (Apollo's "SSR data transport"), and asks
# Jinxxy's API for more as you scroll. Each item there has its product's listing (its creator, and its public page,
# jinxxy.com/<creator>/<product>) and, for a gift, who sent it. Hoard reads what the page loaded, and asks Jinxxy
# for nothing more: the data is read as JSON, never run, and only what's checked below is kept.

lib_JX_API_HOST = "api.jinxxy.com"


lib_JX_DATA_MAX = 16 << 20   # characters of data read from one response, or from one page's scripts, at most


lib_JX_DATA_JS = r"""() => {
  let room = 16 << 20;
  const out = [];
  for (const s of document.scripts) {
    const t = s.textContent || '';
    if (!t.includes('ApolloSSRDataTransport') || t.length > room) continue;
    out.push(t); room -= t.length;
  }
  return out;
}"""


lib_JX_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")    # a Jinxxy username, as its addresses use it


lib_JX_SLUG = re.compile(r"[A-Za-z0-9_.~-]{1,200}")  # a product's own part of its address


lib_JX_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")       # an inventory item's id (/my/inventory/<id>)


lib__JS_TOKEN = re.compile(r'[{}\[\]]|undefined\b|[^"{}\[\]u]+|u')   # (and strings: json's own scanner reads them)


def lib_js_data(text: str, start: int) -> tuple[object, int]:
    """The object or array written at text[start:] as a page writes its data for itself (JSON, but for JavaScript's
    undefined), and where it ends. Read as JSON: nothing in it is run. ValueError when it isn't one."""
    i = start
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    if i >= len(text) or text[i] not in "{[":
        raise ValueError("not an object")
    parts, depth = [], 0
    while i < len(text):
        if text[i] == '"':   # a string, to its closing quote (JSON's escapes: anything else isn't JSON anyway)
            end = lib.json.decoder.scanstring(text, i + 1, True)[1]   # (ValueError when it doesn't end, or isn't JSON)
            tok, i = text[i:end], end
            parts.append(tok)
            continue
        m = lib._JS_TOKEN.match(text, i)
        if not m:
            raise ValueError("unreadable")
        tok, i = m.group(), m.end()
        if tok in ("{", "["):
            depth += 1
        elif tok in ("}", "]"):
            depth -= 1
        parts.append("null" if tok == "undefined" else tok)
        if depth == 0:
            return lib.json.loads("".join(parts)), i
    raise ValueError("unfinished")


def lib_jinxxy_ssr(texts) -> list:
    """The data Jinxxy's pages came with: each value its scripts hand to Apollo's SSR data transport (the
    `...ApolloSSRDataTransport")] ??= []).push({...})` it writes), from a page's scripts or a page saved whole."""
    out, room = [], lib.JX_DATA_MAX
    for text in texts if isinstance(texts, list) else []:
        if not isinstance(text, str) or len(text) > room:
            continue
        room -= len(text)
        at = 0
        while (at := text.find("ApolloSSRDataTransport", at)) >= 0:
            push = text.find(".push(", at)
            at += 22
            if push < 0 or push - at > 40:
                continue
            try:
                value, end = lib.js_data(text, push + 6)
            except ValueError:
                continue
            out.append(value)
            at = max(at, end)
    return out


def lib_jinxxy_listener(into: list):
    """A page's response listener that keeps what Jinxxy's API sent the page (JSON only, JX_DATA_MAX at most each,
    and eight times that in all) in into, for jinxxy_data. A response it can't read is passed by."""
    room = [8 * lib.JX_DATA_MAX]

    def heard(r):
        """Keep one response from Jinxxy's API."""
        try:
            if lib.urlparse(r.url).hostname != lib.JX_API_HOST or r.status != 200 or room[0] <= 0:
                return
            if "json" not in (r.headers.get("content-type") or "").lower():
                return
            body = r.body()
            if len(body) <= min(lib.JX_DATA_MAX, room[0]):
                room[0] -= len(body)
                into.append(lib.json.loads(body))
        except Exception:   # (a response gone, or not JSON: nothing to keep)
            pass
    return heard


def lib_jinxxy_page_data(page) -> list:
    """The data the page now shown came with (jinxxy_ssr), or none."""
    try:
        return lib.jinxxy_ssr(page.evaluate(lib.JX_DATA_JS))
    except Exception:
        return []


def lib__jx_image(files) -> str | None:
    """The first picture (not a video) among a listing's thumbnails, or its cover's."""
    for f in (files if isinstance(files, list) else [files])[:20]:
        if isinstance(f, dict) and isinstance(f.get("url"), str) and str(f.get("content_type") or "image/").startswith("image/"):
            u = lib.safe_url(f["url"])
            if u and not lib.is_video_address(u):
                return u
    return None


def lib__jx_note(out: dict, id_, listing, product, gift) -> None:
    """Note what one inventory item's data says (jinxxy_data)."""
    if not isinstance(id_, str) or not lib.JX_ID.fullmatch(id_):
        return
    listing = listing if isinstance(listing, dict) else {}
    product = product if isinstance(product, dict) else {}
    seller = listing.get("user") if isinstance(listing.get("user"), dict) else {}
    maker = product.get("user") if isinstance(product.get("user"), dict) else {}
    user = next((u for u in (listing.get("user_username"), seller.get("username"), maker.get("username"))
                 if isinstance(u, str) and lib.JX_NAME.fullmatch(u)), None)
    slug = next((u for u in (listing.get("url"), product.get("url")) if isinstance(u, str) and lib.JX_SLUG.fullmatch(u)), None)
    note = {"name": next((n for n in (listing.get("name"), product.get("name")) if isinstance(n, str) and n.strip()), None),
            "creator": next((n for n in (seller.get("name"), listing.get("seller_name"), user)
                             if isinstance(n, str) and n.strip()), None),
            "creator_url": f"https://jinxxy.com/{user}" if user else None,
            "page": f"https://jinxxy.com/{user}/{slug}" if user and slug and listing.get("has_public_page") is True else None,
            "thumbnail": lib._jx_image(listing.get("thumbnails")) or lib._jx_image(product.get("cover"))}
    if isinstance(gift, dict) and gift.get("is_revoked") is not True:
        sender = gift.get("sender") if isinstance(gift.get("sender"), dict) else {}
        note["gift"] = True
        note["gift_from"] = next((n for n in (sender.get("name"), sender.get("username")) if isinstance(n, str) and n.strip()), None)
    old = out.setdefault(id_, {})
    for k, v in note.items():
        if v and not old.get(k):
            old[k] = v
    # whether it's for adults, where the data has its content warnings (hoard/adult.py): known without its page
    from ..adult import jinxxy_rated
    rated = [r for r in (jinxxy_rated(listing.get("restrictions")), jinxxy_rated(product.get("restrictions"))) if r is not None]
    if rated:
        old["adult"] = old.get("adult") is True or any(rated)


def lib_jinxxy_data(values) -> dict:
    """What Jinxxy's own data (jinxxy_ssr, jinxxy_listener) says about inventory items, by item id: "name",
    "creator", "creator_url", "page" (its product's public page, when it has one), "thumbnail", "gift" with
    "gift_from" (who sent it), and "adult" where it has the product's content warnings. Inventory items
    (getInventoryItems: an item's listing, and its gift) and received gifts (getGiftsReceived: the gift's product,
    sender and inventory item) are read; anything else is passed by."""
    out: dict[str, dict] = {}
    stack, looked = [values], 0
    while stack and looked < 2_000_000:
        o = stack.pop()
        looked += 1
        if isinstance(o, list):
            stack.extend(o[:20000])
            continue
        if not isinstance(o, dict):
            continue
        kind = o.get("__typename")
        if kind == "InventoryItem" or (kind is None and "listing" in o and "item" in o):
            lib._jx_note(out, o.get("id"), o.get("listing"), o.get("item"), o.get("gift"))
        elif (kind == "Gift" or (kind is None and "inventory_item" in o and "sender" in o)) \
                and isinstance(o.get("inventory_item"), dict) and o.get("status") in (None, "ACCEPTED"):
            lib._jx_note(out, o["inventory_item"].get("id"), o.get("product"), None, {"sender": o.get("sender")})
        stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
    return out


def lib_jinxxy_gift_sender(c: dict) -> str | None:
    """Who a card on the inventory's Gifts tab says sent it ("A gift from <name>"), or None for any other card."""
    lines = c.get("lines") if isinstance(c.get("lines"), list) else []
    for n, line in enumerate(lines[:40]):
        m = lib.re.match(r"(?i)a gift from\b:?\s*(.*)$", line) if isinstance(line, str) else None
        if m:
            name = m.group(1).strip() or (lines[n + 1] if n + 1 < len(lines) and isinstance(lines[n + 1], str) else "")
            return lib.clean_text(name, 120) or ""
    return None


def lib_jinxxy_gifts(page, pattern: str, progress, most: int = 0) -> dict:
    """The cards on your inventory's Gifts tab (Jinxxy keeps gifts you've accepted there as well as with your
    products), by their key, each with "gift_from"; none when there's no Gifts tab. most: only the first that many
    (a quick refresh)."""
    tab = page.locator('[role="tab"][id$="-trigger-gifts"]')
    if not tab.count():
        tab = page.get_by_role("tab", name=lib.re.compile(r"^\s*gifts?\b", lib.re.I))
    if not tab.count():
        return {}
    from .. import pace
    pace.before(lib.JX_INVENTORY, 6)   # (the tab asks Jinxxy's API for its gifts: a few requests)
    try:
        tab.first.click()
        lib.settle(page, 1500)
    except Exception as e:   # (no Gifts tab to show: the products are read all the same)
        print(f"Jinxxy: couldn't open the Gifts tab: {str(e)[:200]}", flush=True)
        return {}
    gifts: dict[str, dict] = {}

    def read() -> int:
        """Note the gifts now shown; returns how many are known."""
        for c in page.evaluate(lib.JX_CARDS_JS, pattern):
            sender = lib.jinxxy_gift_sender(c)
            if sender is not None:
                gifts.setdefault(c["key"], {**c, "gift_from": sender})
        progress(f"Gifts, {len(gifts)}")
        return len(gifts)
    lib.scroll_inventory(page, read, most=most)
    return dict(list(gifts.items())[:most]) if most else gifts


def lib_jinxxy_merge(found: dict, gifts: dict, known: dict) -> None:
    """Put what Jinxxy's data says (jinxxy_data) into the items read from the inventory's cards: each product's
    public page, a creator or picture a card didn't show, and which are gifts and who from. A gift found only on the
    Gifts tab is added. A gift card's profile link is who sent it, never taken for its creator."""
    for key, c in gifts.items():
        mine = found.get(key)
        if mine is None:
            mine = found[key] = {k: c.get(k) for k in ("key", "url", "name", "thumbnail", "page", "video")}
            mine["creator"], mine["creator_url"] = "", None
        mine["gift"], mine["gift_from"] = True, mine.get("gift_from") or c.get("gift_from") or None
    for key, c in found.items():
        k = known.get(key.rsplit("/", 1)[-1]) or {}
        if k.get("gift"):
            c["gift"], c["gift_from"] = True, c.get("gift_from") or k.get("gift_from")
        if c.get("gift") and (k.get("creator") or (c.get("gift_from") and c.get("creator") == c["gift_from"])):
            c["creator"], c["creator_url"] = k.get("creator") or "", k.get("creator_url")
        for f in ("page", "creator", "creator_url", "name"):
            c[f] = c.get(f) or k.get(f)
        if isinstance(k.get("adult"), bool) and not isinstance(c.get("adult"), bool):
            c["adult"] = k["adult"]
        if not c.get("thumbnail") or (c.get("video") and lib.is_video_address(c["thumbnail"])):
            c["thumbnail"] = k.get("thumbnail") or c.get("thumbnail")
        c["creator"] = c.get("creator") or ""


def lib_jinxxy_key(c: dict) -> str:
    """A Jinxxy product's key in your library (jinxxy:<its id>)."""
    return "jinxxy:" + c["key"].rsplit("/", 1)[-1]


def lib_jinxxy_item(c: dict) -> dict:
    """Turn a card read from Jinxxy's inventory page into a library item."""
    page = c.get("page")
    return lib.item("jinxxy", c["key"].rsplit("/", 1)[-1], name=c["name"], creator=c["creator"],
                creator_url=c.get("creator_url"), thumbnail=c["thumbnail"], url=c["url"], download_url=c["url"],
                page=page if isinstance(page, str) and lib.jinxxy_product_page([page], c.get("creator_url")) else None,
                gift=c.get("gift") is True, gift_from=c.get("gift_from"),
                **({"adult": c["adult"]} if isinstance(c.get("adult"), bool) else {}))   # (its content warnings: #311)


def lib_jinxxy_inventory_pages(hrefs) -> list[str]:
    """The links among these that are more pages of your Jinxxy inventory (/my/inventory?page=N), on Jinxxy itself
    only: its browser is signed in to Jinxxy, so a page of the same path on another site (a link in someone's
    product text, say) is never opened in it."""
    out = []
    for href in hrefs:
        u = lib.urlparse(str(href))
        if u.path.rstrip("/") == "/my/inventory" and lib.re.search(r"(^|&)page=\d+", u.query) and lib.store_link("jinxxy", str(href)):
            out.append(str(href))
    return out


dl_JX_BASE = "https://jinxxy.com"


dl_JX_INVENTORY = dl_JX_BASE + "/my/inventory"


dl_JX_HOSTS = ["jinxxy\\.com"]


dl_JX_INFO_JS = r"""
() => {
  const meta = p => (document.querySelector(`meta[property="${p}"]`) || {}).content || '';
  const LANDMARKS = 'nav, aside, header, footer, [role="navigation"], [role="banner"], [role="contentinfo"], [role="complementary"]';
  const GENERIC = /^(navigation|menu|profile|likes|lists|wishlist|inventory|marketplace|popular|leaderboard|product details|details|support info|my review|instructions from the creator.*)$/i;
  // A heading's own words, without its buttons and icons (a back arrow, a menu)
  const words = h => { const c = h.cloneNode(true); c.querySelectorAll('button, svg, [aria-hidden="true"]').forEach(x => x.remove());
    return c.textContent.replace(/\s+/g, ' ').trim(); };
  const bare = t => t.replace(/^[^\p{L}\p{N}]+/u, '').trim();
  // The product's title: the first heading in the page's content that isn't page furniture
  const h1 = [...document.querySelectorAll('main h1, main h2, h1, h2, h3')]
    .find(h => !h.closest(LANDMARKS) && bare(words(h)) && !GENERIC.test(bare(words(h))));
  const ogTitle = meta('og:title');
  const name = ((h1 && words(h1)) || (ogTitle && !/^jinxxy$/i.test(ogTitle.trim()) ? ogTitle : '')
    || (document.title || '').replace(/\s*[|\-\u2013]\s*jinxxy\s*$/i, '') || '').trim();
  // You, the signed-in user: your "Profile" link is never the creator
  const own = new Set();
  for (const l of document.querySelectorAll('a[href]')) {
    const t = (l.innerText || l.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    if (!/^(profile|my profile|view profile|account|my account)$/i.test(t)) continue;
    try { const segs = new URL(l.href).pathname.split('/').filter(Boolean); if (segs.length === 1) own.add(segs[0].toLowerCase()); } catch (e) {}
  }
  const reserved = new Set(['my','login','signin','signup','register','market','marketplace','search','help',
    'about','terms','privacy','discover','cart','checkout','settings','creators','categories','tags','blog',
    'api','dashboard','products','inventory','support','faq','legal']);
  const links = [];
  for (const a of document.querySelectorAll('a[href]')) {
    let u; try { u = new URL(a.href); } catch (e) { continue; }
    if (!/(^|\.)jinxxy\.com$/.test(u.hostname)) continue;
    const segs = u.pathname.split('/').filter(Boolean);
    if (!(segs.length === 1 || (segs.length === 2 && segs[1] === 'products'))) continue;
    if (reserved.has(segs[0].toLowerCase()) || own.has(segs[0].toLowerCase()) || a.closest(LANDMARKS)) continue;
    const after = h1 ? !!(h1.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING) : true;
    links.push({ after, creator: (a.innerText || '').trim() || segs[0] });
  }
  const pick = links.find(l => l.after) || links[0];
  const big = img => { const r = img.getBoundingClientRect(); return r.width >= 100 && r.height >= 100; };
  const usable = img => !img.closest(LANDMARKS) && big(img) && (img.currentSrc || img.src || '').startsWith('http');
  let thumbnail = '';
  for (let box = h1; box && box !== document.body && !thumbnail; box = box.parentElement) {
    const imgs = [...box.querySelectorAll('img')].filter(usable);
    if (imgs.length) thumbnail = imgs[0].currentSrc || imgs[0].src;   // the nearest picture to the title
  }
  return { name, creator: pick ? pick.creator : '', thumbnail };
}
"""


def dl_jinxxy_require_login(page) -> None:
    """Raise NotLoggedIn when Jinxxy is showing its sign-in form."""
    path = dl.urlparse(page.url).path.lower()
    if "login" in path or "signin" in path or page.locator("input[type=password]").count():
        raise dl.NotLoggedIn("Not signed in to Jinxxy")


def dl_jinxxy_link(u) -> bool:
    """Is this parsed link on Jinxxy itself: https, on jinxxy.com or one of its subdomains, with no user name,
    password or unusual port? (Not "jinxxy.com" anywhere in the address: notjinxxy.com, jinxxy.com.example.net and
    example.net/?jinxxy.com aren't Jinxxy.)"""
    try:
        port = u.port
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return (u.scheme == "https" and port in (None, 443) and u.username is None and u.password is None
            and (host == "jinxxy.com" or host.endswith(".jinxxy.com")))


def dl__scan_inventory(page, rx, inv_path: str, found: dict) -> list[str]:
    """Scroll / click 'load more' until this page stops growing. Returns numbered-page links seen."""
    page_links: list[str] = []

    def read() -> int:
        """Read the links now on the page: products noted, and numbered pages of the inventory kept for later; returns
        how many products are known."""
        for href in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
            u = dl.urlparse(href)
            if not dl.jinxxy_link(u):
                continue
            path = u.path.rstrip("/")
            if path == inv_path and dl.re.search(r"(^|&)page=\d+", u.query):
                page_links.append(href)
            elif path != inv_path and rx.search(u.path):
                found.setdefault(f"{u.scheme}://{u.netloc}{path}", None)
        return len(found)
    dl.scroll_inventory(page, read, settle_ms=600, wait_ms=1200)
    return page_links


def dl_jinxxy_item_links(page, pattern: str) -> list[str]:
    """Every item URL in the inventory, whether it scrolls, has 'load more', or has numbered pages."""
    rx = dl.re.compile(pattern)
    inv_path = dl.urlparse(dl.JX_INVENTORY).path.rstrip("/")
    found: dict[str, None] = {}
    visited, pending = {page.url}, []
    for _ in range(100):
        for href in dl._scan_inventory(page, rx, inv_path, found):
            if href not in visited and href not in pending:
                pending.append(href)
        if not pending:
            break
        nxt = pending.pop(0)
        visited.add(nxt)
        dl.pace.before(nxt)
        page.goto(nxt, wait_until="domcontentloaded")
        dl.settle(page)
    return list(found)


def dl_forget_repeated_thumbnails(store_dir: dl.Path) -> int:
    """Delete Jinxxy's default banner where versions before 2.0.1 saved it as product pictures: a picture
    byte-for-byte identical across different creators' products (Creator/Product/_thumbnail.*). One creator's
    products sharing a picture (copies of one product, issue #111) are real pictures, and kept. Done once: a
    marker in Hoard's own folder says so, so pictures aren't read again on every sync. Returns how many were
    removed."""
    from ..paths import data_dir
    done = data_dir() / "jinxxy-banners-checked"
    if done.exists():
        return 0
    by_hash: dict = {}
    for p in store_dir.glob("*/*/_thumbnail.*"):
        if p.is_file() and not p.is_symlink():
            by_hash.setdefault(dl.hashlib.sha256(p.read_bytes()).hexdigest(), []).append(p)
    removed = 0
    for same in by_hash.values():
        if len({p.parent.parent.name for p in same}) > 1:   # more than one creator: the site's banner
            for p in same:
                p.unlink()
                removed += 1
    try:
        done.parent.mkdir(parents=True, exist_ok=True)
        done.write_text("Jinxxy's default banner, saved as product pictures before 2.0.1, was cleared.\n", "utf-8")
    except OSError:
        pass
    return removed


def dl_sync_jinxxy(cfg: dict, root: dl.Path, args, report: dl.Report) -> None:
    """Download everything new or changed in your Jinxxy inventory."""
    jcfg = cfg["jinxxy"]
    store_dir = root / "Jinxxy"
    man = dl.StoreRecords(cfg, root, "Jinxxy")
    if store_dir.is_dir() and not args.dry_run:
        banners = dl.forget_repeated_thumbnails(store_dir)
        if banners:
            dl.log(f"Jinxxy: removed {banners} copies of Jinxxy's default banner saved as product pictures; "
                "the real pictures are saved this time.")
    delay = float(cfg.get("request_delay", 1.0))

    with dl._playwright()() as p:
        browser = {"ctx": dl.launch_context(p, cfg, not args.headed, "jinxxy")}
        direct = None
        try:
            ctx = browser["ctx"]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            # files come straight from Jinxxy with your sign-in, not through the browser (unless Jinxxy turns that away)
            direct = {"sess": dl.session_from_context(ctx, "jinxxy.com"), "sites": dl.STORE_SITES["jinxxy"],
                      "on": bool(jcfg.get("direct_downloads", True))}
            chosen = (getattr(args, "targets", None) or {}).get("jinxxy")
            listed = {}   # a chosen item's name in your library, which may not be its page's
            if chosen:   # straight to the chosen items' pages (each checks the sign-in as it opens)
                links = [i["url"] for i in chosen if dl.jinxxy_link(dl.urlparse(i["url"]))]
                listed = {i["url"]: i.get("name") for i in chosen}
                dl.log(f"Jinxxy: {len(links)} chosen {'item' if len(links) == 1 else 'items'}")
            else:
                dl.pace.before(dl.JX_INVENTORY)
                page.goto(dl.JX_INVENTORY, wait_until="domcontentloaded")
                dl.settle(page, 1500)
                dl.jinxxy_require_login(page)
                links = dl.jinxxy_item_links(page, jcfg["item_link_pattern"])
                if not links:
                    raise RuntimeError("found no items on the inventory page - run the command: probe jinxxy")
                dl.log(f"Jinxxy: {len(links)} items in your inventory")

            reopened = 0
            for n, url in enumerate(links, 1):
                dl.tick(f"Jinxxy: item {n} of {len(links)}")   # Stop is noticed here, even when items fail fast
                dl.pause(delay)
                for again in (False, True):
                    if page.is_closed():
                        if reopened >= dl.REOPENS:
                            raise RuntimeError(f"Jinxxy's browser closed by itself {reopened} times, so the rest of "
                                               "Jinxxy was left for next time. Hoard's log has what happened before each (Settings, "
                                               "Open logs folder).")
                        reopened += 1
                        page = dl.reopen_tab(p, cfg, args, "jinxxy", browser)
                    try:
                        dl._jinxxy_item(browser["ctx"], page, url, man, store_dir, jcfg, args, report, chosen=bool(chosen),
                                     direct=direct, listed_name=listed.get(url))
                    except dl.NotLoggedIn:
                        raise
                    except Exception as e:
                        if not again and (dl.tab_closed(e) or page.is_closed()):
                            dl.log(f"    Jinxxy's browser closed while on {url} ({e}); trying it again")
                            if not page.is_closed():
                                try:
                                    page.close()
                                except Exception:
                                    pass
                            continue
                        report.failed.append(f"Jinxxy: {url} - {e}")
                    break
        finally:
            man.save_changes()   # every finished file recorded, however the sync ended
            if direct:
                direct["sess"].cookies.clear()   # the copied sign-in only lives for this sync
            try:
                browser["ctx"].close()
            except Exception:
                pass   # a browser that already closed by itself


def dl__jinxxy_item(ctx, page, url, man, store_dir, jcfg, args, report, chosen: bool = False, direct=None,
                 listed_name: str | None = None) -> None:
    """Open one Jinxxy item and download the files its page offers."""
    dl.pace.before(url)
    page.goto(url, wait_until="domcontentloaded")
    dl.settle(page)
    dl.jinxxy_require_login(page)
    info = page.evaluate(dl.JX_INFO_JS)
    key = dl.urlparse(url).path.rstrip("/").split("/")[-1]
    name = (info.get("name") or key).strip()
    creator = (info.get("creator") or "Unknown Creator").strip()
    if not chosen and dl.skip_product(args, "jinxxy", name, creator):   # (a chosen item was picked by its page, not its name)
        return
    if dl.removed_product("jinxxy", name, report) or man.away(key, f"Jinxxy: {name}", report):
        return
    rec = man.record(key, creator, name)
    is_new_asset = not rec["files"]
    rec.update(name=name, creator=creator, url=url, last_synced=dl.now_iso())
    folder = man.folder_of(rec)
    dl.log(f"\n[Jinxxy] {creator} / {name}")

    got_any = dl.download_by_clicking(ctx, page, url, rec, folder, "Jinxxy", dl.JX_HOSTS,
                                   int(jcfg.get("download_start_timeout", 90)), name, creator, man, args, report,
                                   direct=direct, listed_name=listed_name)

    if got_any and is_new_asset:
        report.new_assets.append(f"Jinxxy: {creator} / {name}")
    if jcfg.get("save_thumbnails", True) and not args.dry_run:
        dl.save_thumbnail(info.get("thumbnail"), folder, "https://jinxxy.com/")
    man.checkpoint()


def dl_cmd_probe(cfg: dict, args) -> None:
    """Record what Jinxxy's inventory and first item page load, for tuning the adapter."""
    dl.PROBE_DIR.mkdir(parents=True, exist_ok=True)
    out = open(dl.PROBE_DIR / "jinxxy_network.jsonl", "w", encoding="utf-8")
    with dl._playwright()() as p:
        ctx = dl.launch_context(p, cfg, False, "jinxxy")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        responses = []
        page.on("response", responses.append)

        def dump(stage):
            """Record the JSON responses seen so far, for this stage of the probe, with any key or pass taken out."""
            for r in responses:
                try:
                    if "json" not in r.headers.get("content-type", "") and "graphql" not in r.url:
                        continue
                    body = r.text()
                except Exception:
                    continue
                out.write(dl.json.dumps({"stage": stage, "method": r.request.method, "status": r.status,
                                      "url": dl.redact(r.url), "request": dl.redact((r.request.post_data or "")[:4000]),
                                      "response": dl.redact(body[:30000])}, ensure_ascii=False) + "\n")
            responses.clear()

        dl.pace.before(dl.JX_INVENTORY)
        page.goto(dl.JX_INVENTORY, wait_until="domcontentloaded")
        dl.settle(page, 2000)
        dl.jinxxy_require_login(page)
        links = dl.jinxxy_item_links(page, cfg["jinxxy"]["item_link_pattern"])
        dump("inventory")
        raw = bool(getattr(args, "raw", False))
        (dl.PROBE_DIR / "inventory.html").write_text(page.content() if raw else dl.scrub(page.content()), "utf-8")
        if raw:
            page.screenshot(path=str(dl.PROBE_DIR / "inventory.png"), full_page=True)
        hrefs = sorted({dl.urlparse(h).path for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")})
        (dl.PROBE_DIR / "inventory_links.txt").write_text("\n".join(hrefs), "utf-8")
        dl.log(f"Item links matching item_link_pattern: {len(links)}")

        if links:
            dl.pace.before(links[0])
            page.goto(links[0], wait_until="domcontentloaded")
            dl.settle(page, 2000)
            dump("item")
            (dl.PROBE_DIR / "item.html").write_text(page.content() if raw else dl.scrub(page.content()), "utf-8")
            if raw:
                page.screenshot(path=str(dl.PROBE_DIR / "item.png"), full_page=True)
            dl.log(f"First item: {page.evaluate(dl.JX_INFO_JS)}")
            for b in page.evaluate(dl.DOWNLOAD_BUTTONS_JS, {"allowAll": True, "hosts": dl.JX_HOSTS}):
                dl.log(f"  download button: {b['label'][:120]}")
        ctx.close()
    out.close()
    dl.log(f"\nWrote {dl.PROBE_DIR}. " + ("These files are exactly what Jinxxy showed you, including your purchases and "
                                     "account details: only share them with someone you trust." if getattr(args, "raw", False)
                                     else "Email addresses, form values, tokens and signed links were removed, and there are "
                                          "no screenshots. If someone helping you needs more, run again with --raw."))


# Jinxxy's wishlist, likes and lists all show a product the same way: its picture and name, each a link to its page
# (jinxxy.com/<creator>/<product>, or a store elsewhere), its creator's link, and its price. And the lists page: a
# link to each list, with its name.
wish_JINXXY_JS = r"""(base) => {
  const abs = a => { try { return new URL(a.getAttribute('href'), base || location.href).href; } catch (e) { return ''; } };
  const cards = [], seen = new Set();
  for (const h of document.querySelectorAll('a[href] h3')) {
    const a = h.closest('a'), url = abs(a);
    if (!url || seen.has(url) || /\/my\//.test(new URL(url).pathname)) continue;
    let card = a;   // the smallest box around it that has its price
    while (card.parentElement && !/\d\s*[A-Z]{3}\s*$|^Free$/m.test(card.innerText || card.textContent)) card = card.parentElement;
    if (!card.parentElement) continue;
    seen.add(url);
    const path = new URL(url).pathname.split('/').filter(Boolean);
    const creator = [...card.querySelectorAll('a[href]')].find(x => x !== a && abs(x) !== url && path.length > 1
      && abs(x) && new URL(abs(x)).pathname.replace(/\/$/, '') === '/' + path[0]);
    const name = h.textContent.trim();
    // its picture is the one in the other link to the same product (beside the name, not in the box around it), or the
    // still of the video it shows first (issue #212)
    const img = [...document.querySelectorAll('a[href] img')].find(i => abs(i.closest('a')) === url && !/profile picture/i.test(i.alt || ''));
    const vid = [...document.querySelectorAll('a[href] video[poster]')].find(v => abs(v.closest('a')) === url);
    const price = [...card.querySelectorAll('span')].map(s => s.textContent.trim())
      .find(t => /^(\d[\d.,]*(\s*-\s*\d[\d.,]*)?\s*[A-Z]{3}|Free)$/.test(t));
    const adult = [...card.querySelectorAll('span, div')].some(e => !e.children.length && /^(NSFW|18\+)$/i.test(e.textContent.trim()));
    cards.push({url, name, creator: creator ? creator.textContent.trim() : '', thumbnail: img ? img.src : vid ? vid.poster : '',
                price: price || '', adult});   // (adult: its NSFW badge, hoard/adult.py)
  }
  const lists = [...document.querySelectorAll('a[href*="/my/lists/"]')].map(a => ({url: abs(a),
    name: (a.querySelector('h3') || {}).textContent || ''})).filter(l => l.name.trim());
  const next = document.querySelector('nav[aria-label="pagination"] a[aria-label="Go to next page"]:not([aria-disabled="true"])');
  return {cards, lists, next: next ? abs(next) : ''};
}"""


def wish_jinxxy_products(cards) -> list[dict]:
    """Jinxxy's wishlist and likes cards, as products: one Jinxxy lists from another store is that store's, and one from
    a site that isn't a store keeps that page as its link."""
    out = []
    for c in cards:
        store = wish._store_of(c.get("url"))   # a product Jinxxy lists from another store is that store's; one on a site
        away = store is None              # that isn't a store keeps that page as its link, elsewhere
        p = wish.product(store or "jinxxy", c.get("name"), creator=c.get("creator"), url=None if away else c.get("url"),
                    thumbnail=c.get("thumbnail"), price=c.get("price"), elsewhere=c.get("url") if away else None,
                    adult=c.get("adult") is True)
        if p:
            out.append(p)
    return out


def wish_read_jinxxy(ctx, cfg, progress) -> list[dict]:
    """Your Jinxxy wishlist, your likes, and each of your lists."""
    page = ctx.new_page()
    delay = float(cfg.get("request_delay", 0.8))
    try:
        def read_all(url: str, label: str, whole: bool = False) -> tuple[list[dict], list[dict], bool]:
            """Every product on one of your Jinxxy lists, page by page, the other lists it links to, and whether a
            quick refresh stopped short of its end (issue #300). whole: to its end even in a quick refresh (the
            index of your lists, where the one asked for may be on any page)."""
            quick = {**cfg, "_quick": False} if whole else cfg
            cards: dict[str, dict] = {}
            lists: dict[str, dict] = {}
            visited, short = set(), False
            for n in range(1, wish.MAX_PAGES + 1):
                wish.goto(page, url)
                wish.settle(page, 1500)
                wish._signed_in(page, "jinxxy.com")
                visited.add(url)
                got = page.evaluate(wish.JINXXY_JS, page.url)
                for c in got["cards"]:
                    if quick.get("_quick") and len(cards) >= wish.QUICK_ITEMS:
                        short = True
                        break
                    cards.setdefault(c["url"], c)
                for x in got["lists"]:
                    lists.setdefault(x["url"], x)
                progress(f"{label}, page {n}: {len(cards) or len(lists)}")
                if not got["next"] or got["next"] in visited:
                    break
                if wish.quick_done(quick, n, len(cards)):
                    short = True
                    break
                url = got["next"]
                wish.time.sleep(delay)
            return wish.jinxxy_products(cards.values()), list(lists.values()), short
        out = []
        built_in = ((wish.JX_WISHLIST, wish.LIST_NAMES["jinxxy-wishlist"]), (wish.JX_LIKES, wish.LIST_NAMES["jinxxy-likes"]))
        for url, name in built_in:
            if wish.wanted(cfg, name):
                products, _, short = read_all(url, name)
                out.append({"store": "jinxxy", "list": name, "url": url, "products": products, **({"partial": True} if short else {})})
        if cfg.get("_only_list") in {name for _, name in built_in}:   # (the one list asked for: issue #331)
            return out
        # the index of your lists: read whole when one list is asked for (it may be past a quick refresh's pages)
        _, lists, _ = read_all(wish.JX_LISTS, "Lists", whole=bool(cfg.get("_only_list")))
        for x in lists[:wish.MAX_LISTS]:
            if not wish.wanted(cfg, x["name"]):
                continue
            products, _, short = read_all(x["url"], x["name"])
            out.append({"store": "jinxxy", "list": wish.clean_text(x["name"], 60), "url": x["url"], "products": products,
                        **({"partial": True} if short else {})})
        return out
    finally:
        page.close()

LIBRARY_EXPORTS = {
    'JX_INVENTORY': lib_JX_INVENTORY,
    'JX_CARDS_JS': lib_JX_CARDS_JS,
    'JX_PRODUCT_JS': lib_JX_PRODUCT_JS,
    'JX_PAGE_VISITS': lib_JX_PAGE_VISITS,
    'jinxxy_product_page': lib_jinxxy_product_page,
    'fetch_jinxxy': lib_fetch_jinxxy,
    'jinxxy_product_pages': lib_jinxxy_product_pages,
    'JX_API_HOST': lib_JX_API_HOST,
    'JX_DATA_MAX': lib_JX_DATA_MAX,
    'JX_DATA_JS': lib_JX_DATA_JS,
    'JX_NAME': lib_JX_NAME,
    'JX_SLUG': lib_JX_SLUG,
    'JX_ID': lib_JX_ID,
    '_JS_TOKEN': lib__JS_TOKEN,
    'js_data': lib_js_data,
    'jinxxy_ssr': lib_jinxxy_ssr,
    'jinxxy_listener': lib_jinxxy_listener,
    'jinxxy_page_data': lib_jinxxy_page_data,
    '_jx_image': lib__jx_image,
    '_jx_note': lib__jx_note,
    'jinxxy_data': lib_jinxxy_data,
    'jinxxy_gift_sender': lib_jinxxy_gift_sender,
    'jinxxy_gifts': lib_jinxxy_gifts,
    'jinxxy_merge': lib_jinxxy_merge,
    'jinxxy_key': lib_jinxxy_key,
    'jinxxy_item': lib_jinxxy_item,
    'jinxxy_inventory_pages': lib_jinxxy_inventory_pages,
}

DOWNLOADER_EXPORTS = {
    'JX_BASE': dl_JX_BASE,
    'JX_INVENTORY': dl_JX_INVENTORY,
    'JX_HOSTS': dl_JX_HOSTS,
    'JX_INFO_JS': dl_JX_INFO_JS,
    'jinxxy_require_login': dl_jinxxy_require_login,
    'jinxxy_link': dl_jinxxy_link,
    '_scan_inventory': dl__scan_inventory,
    'jinxxy_item_links': dl_jinxxy_item_links,
    'forget_repeated_thumbnails': dl_forget_repeated_thumbnails,
    'sync_jinxxy': dl_sync_jinxxy,
    '_jinxxy_item': dl__jinxxy_item,
    'cmd_probe': dl_cmd_probe,
}

WISHLISTS_EXPORTS = {
    'JINXXY_JS': wish_JINXXY_JS,
    'jinxxy_products': wish_jinxxy_products,
    'read_jinxxy': wish_read_jinxxy,
}


from .base import Adapter

STORE = Adapter('jinxxy', 'Jinxxy', 'https://jinxxy.com/my/inventory', 'https://jinxxy.com/', 3, requests_per_minute=120)


def read_saved(page, cfg: dict, prep: dict) -> list[dict]:
    """Parse this store's saved library page in the caller's isolated browser."""
    seen, gifts = {}, {}
    for c in page.evaluate(lib.JX_CARDS_JS, cfg["jinxxy"]["item_link_pattern"]):
        sender = lib.jinxxy_gift_sender(c)   # (a page saved from the Gifts tab: its cards are gifts)
        if sender is not None:
            gifts.setdefault(c["key"], {**c, "gift_from": sender})
        else:
            seen.setdefault(c["key"], c)
    lib.jinxxy_merge(seen, gifts, prep.get("jinxxy_data") or {})
    items = [lib.jinxxy_item(c) for c in seen.values()]
    return items


def saved_wishlist(page, kind: str, url: str, html: str, name: str) -> list[dict]:
    """Parse this store's saved wishlist with scripts and network already disabled."""
    got = page.evaluate(wish.JINXXY_JS, url)
    if wish.urlparse(url).path.rstrip("/").endswith("/my/lists"):
        raise ValueError("that's the list of your Jinxxy lists: save each list's own page instead")
    lists = [{"store": "jinxxy", "list": name, "url": url.split("?")[0], "products": wish.jinxxy_products(got["cards"])}]
    return lists


def read_tags(got) -> list:
    """Read the raw creator tags; the shared normalizer bounds and cleans them."""
    import json
    import html as html_text
    if not isinstance(got, str):
        return []
    m = re.search(r'\\"tags\\":(\[[^\]]{0,4000}\])', got) or re.search(r'"tags":(\[[^\]]{0,4000}\])', got)
    try:
        raw = json.loads(m.group(1).replace('\\"', '"')) if m else []
    except ValueError:
        raw = []
    return raw


def scroll_inventory(page, read, settle_ms: int = 500, wait_ms: int = 1100, rounds: int = 300, most: int = 0) -> None:
    """Show all of a Jinxxy inventory page: read() what's shown (it returns how many it has found in all), then
    choose "Load more" or scroll down, until three rounds in a row find nothing new (or, given most, once that many
    are found). Reading the library and downloading both go through an inventory this way."""
    count, quiet = -1, 0
    for _ in range(rounds):
        now = read()
        if most and now >= most:
            break
        more = page.get_by_role("button", name=lib.re.compile(r"load more|show more", lib.re.I))
        if more.count() and more.first.is_visible() and more.first.is_enabled():
            more.first.click()
            lib.settle(page, settle_ms)
            count, quiet = now, 0
            continue
        page.mouse.wheel(0, 20000)
        page.wait_for_timeout(wait_ms)
        quiet = quiet + 1 if now == count else 0
        count = now
        if quiet >= 3:
            break

LIBRARY_EXPORTS['scroll_inventory'] = scroll_inventory


STILL_JS = r"""() => {
  const vid = document.querySelector('video[poster]');
  return vid ? vid.poster : '';
}"""

LIBRARY_EXPORTS['STILL_JS'] = STILL_JS
