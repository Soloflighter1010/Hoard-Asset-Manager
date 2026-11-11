"""Payhip store adapter: library pages, downloads and recorded wishlist readers.

Shared browser, transport, limits and persistence remain in their common modules.
Compatibility service references preserve dependency overrides during extraction.
"""
from __future__ import annotations

import re
from .services import lib, dl, wish


# ----------------------------------------------------------------------------- Payhip
#
# Payhip keeps your purchases in each shop you bought from, on that shop's own library page (<shop>/b-account),
# not in one library. Hoard reads Payhip and never downloads from it. PAYHIP_SHOP_JS reads a shop's library page,
# PAYHIP_CARDS_JS a page saved from Payhip's own site. If either gets things wrong, run: debug payhip

lib_PAYHIP_NO_SHOPS = ("Payhip keeps your purchases in each shop you bought from, not in one library. Import each "
                   "shop's saved library pages (Import pages, in Stores), or add your shops in Settings to refresh "
                   "them (a shop's address is in your purchase email).")


lib_PAYHIP_SIGNED_IN_NO_SHOPS = ("Signed in to Payhip. Payhip keeps your purchases in each shop you bought from, so add "
                             "those shops in Settings (a shop's address is in your purchase email), then choose Refresh "
                             "on Payhip's row. Or import each shop's saved library pages (Import pages, in Stores).")


lib_PAYHIP_CARDS_JS = r"""
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


lib_PAYHIP_SHOP_JS = r"""
() => {
  // A Payhip shop's own library page (https://<shop>/b-account): one card per product you bought there,
  // each linking to its download page at /b-account/digital/<code>.
  const LANDMARKS = 'nav, header, footer, aside, [role="navigation"], [role="banner"], [role="contentinfo"]';
  const pathOf = a => { try { return new URL(a.href).pathname.replace(/\/$/, ''); } catch (e) { return ''; } };
  const isProduct = a => /\/b-account\/(digital|products?|downloads?)\/[^/]+$/i.test(pathOf(a));
  const text = e => ((e && e.innerText) || '').replace(/\s+/g, ' ').trim();
  const shopName = text(document.querySelector('a.logo-link, .logo-link'))
    || (document.title.includes(' - ') ? document.title.split(' - ').slice(1).join(' - ').trim() : '');
  // A Payhip creator's own purchases, from every shop, are listed on their own shop's library page (its menu's
  // Creator/Customer switch leads there), with nothing on the cards saying who made each one. Those aren't this
  // shop's products, so they're left without a creator rather than credited to you (issue #25). Shops are compared
  // by their whole address: every shop at payhip.com/<name> shares payhip.com, so its hostname says nothing.
  const baseOf = href => href.split(/[?#]/)[0].split('/b-account')[0].replace(/\/$/, '');
  const ownShops = new Set([...document.querySelectorAll('.account-type-switcher-wrapper a[href], a.account-type-switcher-link')]
    .filter(a => /\/b-account$/.test(pathOf(a))).map(a => baseOf(a.href)));
  // A card from another shop (its link is in that shop) is credited to that shop, not to the one whose page it is.
  const logo = document.querySelector('a.logo-link[href]');
  const pageShop = logo ? baseOf(logo.href) : '';
  const shopLabel = base => { const u = new URL(base); return u.hostname.replace(/^www\./, '') === 'payhip.com'
    ? decodeURIComponent(u.pathname.split('/').filter(Boolean)[0] || u.hostname) : u.hostname; };
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
    const url = a.href.split(/[?#]/)[0], host = new URL(url).hostname, base = baseOf(url), mine = ownShops.has(base);
    const elsewhere = pageShop && base !== pageShop;
    cards.set(key, { id: host + ':' + key.split('/').pop(), name: text(heading) || text(a) || (img && img.alt) || '',
                     creator: mine ? '' : elsewhere ? shopLabel(base) : shopName || host, creator_url: mine ? '' : base,
                     thumbnail: img ? (img.currentSrc || img.src || '') : '',
                     url, download_url: url, bought: text(c.querySelector('.card-meta')) });
  }
  const next = [...document.querySelectorAll('a[rel="next"], .pagination a, a.next')]
    .find(x => /next|›|»/i.test(text(x) + ' ' + (x.getAttribute('rel') || '')));
  return { cards: [...cards.values()], next: next ? next.href : null, shop: shopName, own: ownShops.size > 0 };
}
"""


lib_PAYHIP_SIGN_IN_LOOP = ("Payhip kept sending the page back and forth between the shop and its sign-in check on "
                       "payhip.com. Sign in to Payhip itself (Payhip's Sign in, in Stores, opens payhip.com's own "
                       "sign-in page first), then refresh again")


def lib_read_payhip_shop(page, shop: str, cfg: dict, progress) -> list[dict]:
    """Every product you bought from one Payhip shop, from its library page (<shop>/b-account), all its pages."""
    url, cards = shop + "/b-account", {}
    wait = float(cfg["payhip"].get("bot_check_wait", 180)) if cfg["payhip"].get("headed", True) else 0
    for page_no in range(1, 200):   # 15 products a page: 3,000 products
        try:
            lib.goto_past_check(page, url, wait, progress)
        except lib.PageLoadError as e:
            if e.hops:   # where it went, for a support report (addresses only: no query strings)
                lib.log(f"{shop.split('://', 1)[1]}: {e.code or 'the page'} after {lib.hops_text(e.hops)}")
            if any(lib.urlparse(u).path.rstrip("/").endswith("/global-identity") for _status, u in e.hops):
                raise lib.PayhipSignInLoop(lib.PAYHIP_SIGN_IN_LOOP, e.code, e.hops) from None
            raise
        lib.settle(page)
        if "/b-account" not in lib.urlparse(page.url).path or lib.has_password_field(page):
            raise lib.NotLoggedIn(f"not signed in to {lib.urlparse(shop).hostname}{lib.urlparse(shop).path}")
        result = page.evaluate(lib.PAYHIP_SHOP_JS)
        for c in result["cards"]:
            if cfg.get("_quick") and len(cards) >= lib.QUICK_ITEMS:   # (a quick refresh, issue #300: the start of it)
                break
            cards.setdefault(c["id"], c)
        progress(f"{result['shop']}: {len(cards)} products" + (" (your own shop: it lists what you bought everywhere "
                 "on Payhip without saying who made it, so those show as Unknown creator)" if result.get("own") else ""))
        if not result["next"] or result["next"] == url or lib.quick_done(cfg, page_no, len(cards)):
            break
        url = result["next"]
        lib.pause(float(cfg.get("request_delay", 0.8)))
    return list(cards.values())


def lib_fetch_payhip(ctx, cfg, progress) -> list[dict]:
    """Every product you bought on Payhip. Payhip keeps purchases in each shop, so this reads every shop in your
    settings. A shop that can't be read (you aren't signed in there, or its website fails: a shop on its own address
    redirected in a loop during an outage at Payhip) is left out, with why, in cfg["_unread_payhip_shops"], and the
    others still count. Only when nothing could be read does the refresh fail."""
    shops = lib.payhip_shops(cfg)
    if not shops:
        raise RuntimeError(lib.PAYHIP_NO_SHOPS)
    page = ctx.new_page()
    cards: dict[str, dict] = {}
    unread: list[tuple[str, str]] = []   # (shop, why)
    failed: Exception | None = None
    try:
        for shop in shops:
            name = shop.split("://", 1)[1]
            try:
                for c in lib.read_payhip_shop(page, shop, cfg, progress):
                    cards.setdefault(c["id"], c)
            except lib.NotLoggedIn:
                unread.append((name, "you aren't signed in there"))
            except lib.PayhipSignInLoop as e:
                failed = failed or e
                unread.append((name, str(e)))
                progress(f"Couldn't read {name}: Payhip's sign-in check went round in a loop; reading your other shops")
            except lib.Blocked:
                raise   # Payhip's bot check: every shop would wait for it in turn
            except Exception as e:
                if page.is_closed():   # Force stop closed the browser: nothing more can be read
                    raise
                failed = failed or e
                unread.append((name, lib.plain_error(e)))
                progress(f"Couldn't read {name} ({lib.plain_error(e)}); reading your other shops")
    finally:
        page.close()
    if unread and not cards:
        if failed:
            raise failed
        raise lib.NotLoggedIn("not signed in to " + ", ".join(n for n, _why in unread))
    cfg["_unread_payhip_shops"] = unread
    # Payhip's library lists purchases from every shop, including shops on their own domains. Those aren't trusted
    # until you add them (their links are left out till then), so they're offered for you to review.
    known = set(lib.payhip_shops(cfg)) | {"https://payhip.com"}
    found = {s for s in (lib.clean_payhip_shop(c.get("creator_url")) for c in cards.values()) if s and s not in known
             and not s.startswith("https://payhip.com/")}
    cfg["_found_payhip_shops"] = sorted(found)
    return [lib.payhip_item(c) for c in cards.values()]


def lib_payhip_shop_of(i: dict) -> str | None:
    """The Payhip shop on its own address that a purchase is from (a shop's library page names its products by the
    shop's host and a code), or None. Its links count only once the shop is in your settings (store_link), so until
    then its purchase has no Open on Payhip: the library says so, and offers to add the shop."""
    host, sep, _code = str(i.get("id", "")).partition(":")
    shop = lib.clean_payhip_shop(host) if sep and host else None
    return shop if shop and lib.urlparse(shop).hostname not in ("payhip.com", "www.payhip.com") else None


def lib_payhip_unread_note(unread: list[tuple[str, str]]) -> str:
    """What Payhip's row in Stores says after a refresh that couldn't read every shop."""
    if len(unread) == 1:
        name, why = unread[0]
        return (f"Couldn't read the Payhip shop {name}: {why}. Your other shops were read, and what Hoard had from "
                f"{name} is kept. Refresh again later.")
    said = "; ".join(f"{name}: {why}" for name, why in unread[:5]) + ("; and others" if len(unread) > 5 else "")
    return (f"Couldn't read {len(unread)} of your Payhip shops ({said}). Your other shops were read, and what Hoard "
            "had from these is kept. Refresh again later.")


def lib_payhip_item(c: dict) -> dict:
    """Turn a card read from Payhip's library page into a library item."""
    return lib.item("payhip", c["id"].strip("/").replace("/", "-"), name=c["name"], creator=c["creator"],
                creator_url=c["creator_url"], thumbnail=c["thumbnail"], url=c["url"], download_url=c["download_url"])


# A Payhip shop's wishlists (<shop>/b-account/wishlists): its products, each a link to its page (/b/<code>).
wish_PAYHIP_JS = r"""() => {
  const box = document.querySelector('.wishlist-rows-wrapper-outer') || document.body, cards = [], seen = new Set();
  for (const a of box.querySelectorAll('a[href*="/b/"]')) {
    if (seen.has(a.href)) continue;
    let card = a;
    while (card.parentElement && card.parentElement !== box && !card.querySelector('img')) card = card.parentElement;
    const name = (a.textContent.trim() || (card.querySelector('h1,h2,h3,h4,h5,.title,[class*="title"]') || {}).textContent || '').trim();
    if (!name) continue;
    seen.add(a.href);
    const price = [...card.querySelectorAll('*')].filter(e => !e.children.length).map(e => e.textContent.trim())
      .find(t => /^(Free|[$€£¥]\s*\d|\d[\d.,]*\s*[A-Z]{3})/.test(t));
    const list = card.closest('[class*="wishlist-row"]');
    cards.push({url: a.href, name, thumbnail: (card.querySelector('img') || {}).src || '', price: price || '',
                list: list ? ((list.querySelector('h2,h3,h4,.wishlist-name,[class*="name"]') || {}).textContent || '').trim() : ''});
  }
  return {cards};
}"""


def wish_payhip_products(cards) -> list[dict]:
    """A Payhip shop's wishlist cards, as products."""
    return [p for p in (wish.product("payhip", c.get("name"), url=c.get("url"), thumbnail=c.get("thumbnail"),
                                price=c.get("price")) for c in cards) if p]


def wish_read_payhip(ctx, cfg, progress) -> list[dict]:
    """The wishlists in each Payhip shop you've added."""
    page = ctx.new_page()
    try:
        out = []
        for shop in wish.payhip_shops(cfg):
            only, host = cfg.get("_only_list"), wish.urlparse(shop).hostname or shop
            if only and not only.startswith(f"{host}:"):   # (a quick refresh of another shop's list: issue #331)
                continue
            url = shop.rstrip("/") + "/b-account/wishlists"
            wish.goto_past_check(page, url, float(cfg.get("payhip", {}).get("check_wait", 60)), progress)
            wish.settle(page, 1000)
            cards = page.evaluate(wish.PAYHIP_JS)["cards"]
            out.extend(x for x in wish._payhip_lists(cards, shop, url, bool(cfg.get("_quick"))) if wish.wanted(cfg, x["list"]))
            progress(f"{wish.urlparse(shop).hostname}: {len(cards)} products")
        return out
    finally:
        page.close()


def wish__payhip_lists(cards, shop: str, url: str, quick: bool = False) -> list[dict]:
    """A Payhip shop's wishlists, one list for each name the shop gives them, named with the shop (in a quick refresh,
    each list's first QUICK_ITEMS products: issue #300)."""
    by: dict[str, list] = {}
    for c in cards:
        by.setdefault(c.get("list") or "Wishlist", []).append(c)
    host = wish.urlparse(shop).hostname or shop
    return [{"store": "payhip", "list": wish.clean_text(f"{host}: {name}", 60), "url": url,
             "products": wish.payhip_products(cs[:wish.QUICK_ITEMS] if quick else cs),
             **({"partial": True} if quick and len(cs) > wish.QUICK_ITEMS else {})}
            for name, cs in (by.items() or [("Wishlist", [])])]

LIBRARY_EXPORTS = {
    'PAYHIP_NO_SHOPS': lib_PAYHIP_NO_SHOPS,
    'PAYHIP_SIGNED_IN_NO_SHOPS': lib_PAYHIP_SIGNED_IN_NO_SHOPS,
    'PAYHIP_CARDS_JS': lib_PAYHIP_CARDS_JS,
    'PAYHIP_SHOP_JS': lib_PAYHIP_SHOP_JS,
    'PAYHIP_SIGN_IN_LOOP': lib_PAYHIP_SIGN_IN_LOOP,
    'read_payhip_shop': lib_read_payhip_shop,
    'fetch_payhip': lib_fetch_payhip,
    'payhip_shop_of': lib_payhip_shop_of,
    'payhip_unread_note': lib_payhip_unread_note,
    'payhip_item': lib_payhip_item,
}

DOWNLOADER_EXPORTS = {
}

WISHLISTS_EXPORTS = {
    'PAYHIP_JS': wish_PAYHIP_JS,
    'payhip_products': wish_payhip_products,
    'read_payhip': wish_read_payhip,
    '_payhip_lists': wish__payhip_lists,
}


from .base import Adapter

STORE = Adapter('payhip', 'Payhip', 'https://payhip.com/auth/login', 'https://payhip.com/', 4, downloads=False)


def read_saved(page, cfg: dict, prep: dict) -> list[dict]:
    """Parse this store's saved library page in the caller's isolated browser."""
    items = [lib.payhip_item(c) for c in page.evaluate(lib.PAYHIP_SHOP_JS if prep["shop_page"] else lib.PAYHIP_CARDS_JS)["cards"]]
    return items


def saved_wishlist(page, kind: str, url: str, html: str, name: str) -> list[dict]:
    """Parse this store's saved wishlist with scripts and network already disabled."""
    u = wish.urlparse(url)
    lists = wish._payhip_lists(page.evaluate(wish.PAYHIP_JS)["cards"], f"{u.scheme}://{u.netloc}", url)
    return lists


from ..browser import PageLoadError

class PayhipSignInLoop(PageLoadError):
    """A shop's page went back and forth with Payhip's sign-in check (payhip.com/global-identity) until the browser
    gave up. A shop on its own address, and one on payhip.com that has moved to its own address, asks payhip.com
    whether you're signed in to Payhip itself on every visit: when that never comes back as yes, the two send the
    page to each other in a loop."""

LIBRARY_EXPORTS['PayhipSignInLoop'] = PayhipSignInLoop
