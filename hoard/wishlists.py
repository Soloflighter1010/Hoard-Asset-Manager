"""Your wishlists from the stores (issue #158): Booth's loved items, Gumroad's wishlists, Jinxxy's wishlist, likes and
lists, and each Payhip shop's wishlists. Each list the store has becomes a wishlist in Hoard (a set of the kind
"wishlist", hoard/sets.py), with what each product cost when it was read, so a price that changes shows.

They're read as a refresh reads your library: in each store's own signed-in browser window (read_lists), or from
pages you saved from your own browser (from_saved_pages), read offline with scripts off. Every reader returns the
same shape: [{"store", "list", "url", "products": [{"store", "id"?, "name", "creator", "url", "thumbnail", "price"}]}].
"""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .browser import goto, goto_past_check, has_password_field, settle
from .common import NotLoggedIn
from .config import payhip_shops
from .safety import clean_text, inert_html, offline_page, safe_url

MAX_PAGES = 200            # pages of one list (Booth shows 20 on each: 4,000 products)
MAX_LISTS = 50             # lists from one store
BOOTH_WISHES = "https://accounts.booth.pm/wish_lists"
GUMROAD_WISHLISTS = "https://gumroad.com/wishlists"
JX_WISHLIST, JX_LIKES, JX_LISTS = "https://jinxxy.com/my/wishlist", "https://jinxxy.com/my/likes", "https://jinxxy.com/my/lists"
LIST_NAMES = {"booth": "Loved items", "jinxxy-wishlist": "Wishlist", "jinxxy-likes": "Likes"}


# ----------------------------------------------------------------------------- prices

_AMOUNT = r"\d[\d,]*(?:\.\d+)?"
_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "￥": "JPY", "₩": "KRW"}


def parse_price(text) -> dict | None:
    """A price as a store shows it ("1,000 JPY", "15.00 - 50.00 USD", "$22.46+", "¥1,000", "Free"), as
    {"text", "amount", "currency"}: amount is the lowest it's sold for. None when there's no price in it."""
    if not isinstance(text, str):
        return None
    t = re.sub(r"\s+", " ", text).strip()[:60]
    if not t:
        return None
    if re.fullmatch(r"(?i)free|無料|0", t):
        return {"text": t, "amount": 0.0, "currency": ""}
    m = re.search(rf"({_AMOUNT})\s*(?:-\s*{_AMOUNT}\s*)?([A-Z]{{3}})\b", t) or re.search(rf"({_AMOUNT})\s*(円)", t)
    if m:
        currency = "JPY" if m.group(2) == "円" else m.group(2)
    else:
        m = re.search(rf"([$€£¥￥₩])\s*({_AMOUNT})", t)
        if not m:
            return None
        currency, m = _SYMBOLS[m.group(1)], re.match(r"(.*)", m.group(2))
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return {"text": t, "amount": amount, "currency": currency}


def cents_price(cents, currency, more: bool = False) -> dict | None:
    """A price Gumroad gives in cents and a currency code (its page data)."""
    if not isinstance(cents, (int, float)) or isinstance(cents, bool) or not isinstance(currency, str):
        return None
    cur = currency.upper()[:3]
    zero = cur in ("JPY", "KRW")   # currencies with no cents: Gumroad counts them in whole units
    amount = float(cents) if zero else cents / 100
    text = (f"{amount:,.0f}" if zero else f"{amount:,.2f}") + f" {cur}" + ("+" if more else "")
    return {"text": text, "amount": amount, "currency": cur}


def product(store: str, name, *, id_=None, creator=None, url=None, thumbnail=None, price=None,
            elsewhere=None) -> dict | None:
    """One product on a wishlist, cleaned: None without a name. elsewhere: its page on a site that isn't one of the
    stores (one a Jinxxy list sends you to), kept as it is but for anything after #."""
    name = clean_text(name if isinstance(name, str) else "", 300)
    if not name:
        return None
    out = {"store": store, "name": name, "creator": clean_text(creator if isinstance(creator, str) else "", 200)}
    if isinstance(id_, (str, int)) and re.fullmatch(r"[\w.-]{1,80}", str(id_)):
        out["id"] = str(id_)
    if isinstance(url, str) and url:
        u = urlparse(url)
        out["url"] = urlunparse((u.scheme, u.netloc, u.path, "", "", ""))   # without a store's tracking (?ref=...)
    if isinstance(elsewhere, str) and elsewhere:
        u = urlparse(elsewhere)
        out["elsewhere"] = urlunparse((u.scheme, u.netloc, u.path, "", u.query, ""))   # (another site may need its query)
    if safe_url(thumbnail):
        out["thumbnail"] = safe_url(thumbnail)
    if isinstance(price, dict) or isinstance(price, str):
        p = price if isinstance(price, dict) else parse_price(price)
        if p:
            out["price"] = p
    return out


def _store_of(url: str) -> str | None:
    host = (urlparse(url or "").hostname or "").lower()
    if host == "booth.pm" or host.endswith(".booth.pm"):
        return "booth"
    if host == "gumroad.com" or host.endswith(".gumroad.com"):
        return "gumroad"
    if host in ("jinxxy.com", "www.jinxxy.com"):
        return "jinxxy"
    if host in ("payhip.com", "www.payhip.com"):
        return "payhip"
    if host.endswith(".itch.io"):
        return "itch"
    return None


# ----------------------------------------------------------------------------- a product by its link

# each store's own site, which a product's page may send you on to (besides the page's own host, a creator's)
LINK_HOSTS = {"booth": ("booth.pm",), "gumroad": ("gumroad.com",), "jinxxy": ("jinxxy.com", "www.jinxxy.com"),
              "payhip": ("payhip.com", "www.payhip.com"), "itch": ()}
MAX_PRODUCT_PAGE = 3 * 1024 * 1024


class LinkError(ValueError):
    """A link that isn't a product's page on a store, or whose page couldn't be read: why, in words to show."""


def from_product_page(link: str, fetch) -> dict:
    """A product added to a set or wishlist by its link (Add products by link): read from its public page, as anyone
    can see it (no sign-in is sent). fetch(url, hosts) gives (text, content type) or None, from those hosts only.
    Booth's item has its JSON beside its page; the other stores' pages say what they sell in their JSON-LD or Open
    Graph tags. Returns product()'s shape; raises LinkError saying why not."""
    import json
    from .sets import product_link   # (here: sets uses this module's shapes)
    store = _store_of(link if isinstance(link, str) else "")
    url = product_link(store, (link or "").strip()) if store else None
    path = urlparse(url or "").path
    is_product = url and (store == "booth" and "/items/" in path or store == "gumroad" and "/l/" in path
                          or store == "jinxxy" and path.count("/") == 2 or store == "payhip" and "/b/" in path
                          or store == "itch" and len(path) > 1)
    if not is_product:
        raise LinkError("not a product's page on Booth, Gumroad, Jinxxy, Payhip or itch.io")
    host = urlparse(url).hostname
    if store == "booth":   # https://booth.pm/en/items/<id>.json: its name, price, shop and pictures
        item = re.search(r"/items/(\d+)", path).group(1)
        got = fetch(f"https://booth.pm/en/items/{item}.json", ("booth.pm",))
        try:
            data = json.loads(got[0]) if got else None
        except ValueError:
            data = None
        if not isinstance(data, dict) or not data.get("name"):
            raise LinkError("Booth didn't show that item (it may be gone, or for adults only)")
        pics = [x.get("original") or x.get("resized") for x in data.get("images") or [] if isinstance(x, dict)]
        return product("booth", data.get("name"), id_=item, creator=(data.get("shop") or {}).get("name"),
                       url=url, thumbnail=next((x for x in pics if x), None), price=data.get("price"))
    got = fetch(url, tuple(dict.fromkeys((host,) + LINK_HOSTS[store])))
    if not got or "html" not in got[1]:
        raise LinkError("its page couldn't be read")
    page = got[0]
    found = _ld_product(page) or {}
    meta = lambda prop: _meta(page, prop)  # noqa: E731
    name = found.get("name") or meta("og:title")
    if not name:
        raise LinkError("its page doesn't say what it is")
    creator = found.get("creator") or (host.split(".")[0] if store in ("gumroad", "itch") and host.count(".") == 2 else "") \
        or (path.split("/")[1] if store == "jinxxy" else "") or meta("og:site_name")
    amount, currency = found.get("price"), found.get("currency")
    if amount is None:
        amount, currency = meta("product:price:amount"), meta("product:price:currency")
    price = parse_price(f"{amount} {currency}") if amount not in (None, "") and currency else None
    if price is None and amount not in (None, "") and str(amount).strip() in ("0", "0.0", "0.00"):
        price = {"text": "Free", "amount": 0.0, "currency": ""}
    return product(store, name, creator=creator, url=url, thumbnail=found.get("image") or meta("og:image"), price=price)


def _meta(page: str, prop: str) -> str:
    """A <meta property|name="prop" content="..."> tag's content (either order), unescaped, or ""."""
    import html as html_text
    for pat in (rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]*\bcontent=["\']([^"\']*)',
                rf'<meta[^>]+\bcontent=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']{re.escape(prop)}["\']'):
        m = re.search(pat, page, re.I)
        if m:
            return clean_text(html_text.unescape(m.group(1)), 300)
    return ""


def _ld_product(page: str) -> dict | None:
    """The Product a page describes in its JSON-LD: name, image, creator, price and currency (its lowest offer)."""
    import json
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I)[:10]:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []):
            if not isinstance(item, dict) or "Product" not in str(item.get("@type")):
                continue
            offers = item.get("offers")
            offers = [offers] if isinstance(offers, dict) else offers if isinstance(offers, list) else []
            priced = [o for o in offers if isinstance(o, dict) and o.get("price") not in (None, "")]
            image = item.get("image")
            image = image[0] if isinstance(image, list) and image else image
            who = item.get("brand") or item.get("author") or item.get("seller") or {}
            return {"name": item.get("name") if isinstance(item.get("name"), str) else "",
                    "image": image.get("url") if isinstance(image, dict) else image if isinstance(image, str) else None,
                    "creator": who.get("name", "") if isinstance(who, dict) else who if isinstance(who, str) else "",
                    "price": priced[0].get("price") if priced else None,
                    "currency": priced[0].get("priceCurrency") if priced else None}
    return None


# ----------------------------------------------------------------------------- what's on a page

# Booth's loved items (accounts.booth.pm/wish_lists): a card for each item, 20 to a page; above them, a button for
# each of your lists ("all", "uncategorized" and any you made), the shown one data-state="default".
BOOTH_JS = r"""() => {
  const cards = [];
  for (const w of document.querySelectorAll('.item-card-wrapper')) {
    const links = [...w.querySelectorAll('a[href*="/items/"]')];
    const m = links.length ? links[0].href.match(/\/items\/(\d+)/) : null;
    if (!m) continue;
    const title = w.querySelector('a[href*="/items/"] .break-all') || links.reverse().find(a => a.textContent.trim() && !/^Loading/.test(a.textContent.trim()));
    const shop = [...w.querySelectorAll('a[href]')].find(a => /^https:\/\/[a-z0-9-]+\.booth\.pm\/?$/i.test(a.href));
    const img = [...w.querySelectorAll('img')].find(i => !i.classList.contains('hidden') && /\/i\/\d+\//.test(i.src));
    const leaves = [...w.querySelectorAll('div, span')].filter(e => !e.children.length).map(e => e.textContent.trim());
    cards.push({id: m[1], url: 'https://booth.pm/en/items/' + m[1], name: title ? title.textContent.trim() : '',
                creator: shop ? shop.textContent.trim() : '', creator_url: shop ? shop.href : '', thumbnail: img ? img.src : '',
                price: leaves.find(t => /^[~〜]?\s*(¥\s*\d|\d[\d,]*\s*(JPY|円))/.test(t)) || ''});
  }
  const lists = [...document.querySelectorAll('button.charcoal-tag-item')].map(b => ({name: b.textContent.trim(),
    shown: b.getAttribute('data-state') === 'default'})).filter(l => l.name);
  return {cards, lists};
}"""

# Booth's next page of loved items: its page numbers, under the cards, are drawn by its script, not links (an address
# with ?page=2 shows the first page again), so its arrow to the next page is chosen. False on the last page.
BOOTH_NEXT_JS = r"""() => {
  const arrow = [...document.querySelectorAll('pixiv-icon[name="24/ArrowOpenRight"]')].map(i => i.closest('.cursor-pointer'))
    .find(el => el && el.offsetParent !== null);
  if (!arrow) return false;
  arrow.click();
  return true;
}"""
# ...and the first card shown, to know when the next page has taken its place
BOOTH_FIRST_JS = r"""() => { const a = document.querySelector('.item-card-wrapper a[href*="/items/"]');
  const m = a && a.href.match(/\/items\/(\d+)/); return m ? m[1] : ''; }"""

# Gumroad's wishlists (gumroad.com/wishlists): a row for each, its name and its own address.
GUMROAD_INDEX_JS = r"""() => [...document.querySelectorAll('a[href*="/wishlists/"]')]
  .filter(a => a.querySelector('h4, h3, h2')).map(a => ({name: a.textContent.trim(), url: a.href}))"""

# A Gumroad wishlist's own page, when its page data can't be read: a card (<article>) for each product.
GUMROAD_CARDS_JS = r"""() => [...document.querySelectorAll('article')].map(a => {
  const link = a.querySelector('a[href*="/l/"]'), seller = a.querySelector('header a[href]:not([href*="/l/"])');
  const price = a.querySelector('[itemprop="price"]'), cur = a.querySelector('[itemprop="priceCurrency"]');
  return {url: link ? link.href : '', name: (a.querySelector('h4, h3') || {}).textContent || '',
          creator: seller ? seller.textContent.trim() : '', thumbnail: (a.querySelector('figure img') || {}).src || '',
          amount: price ? price.getAttribute('content') : '', currency: cur ? cur.textContent.trim() : '',
          shown: price ? price.textContent.trim() : ''};
}).filter(c => c.url && c.name.trim())"""

# Jinxxy's wishlist, likes and lists all show a product the same way: its picture and name, each a link to its page
# (jinxxy.com/<creator>/<product>, or a store elsewhere), its creator's link, and its price. And the lists page: a
# link to each list, with its name.
JINXXY_JS = r"""(base) => {
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
    // its picture is the one in the other link to the same product (beside the name, not in the box around it)
    const img = [...document.querySelectorAll('a[href] img')].find(i => abs(i.closest('a')) === url && !/profile picture/i.test(i.alt || ''));
    const price = [...card.querySelectorAll('span')].map(s => s.textContent.trim())
      .find(t => /^(\d[\d.,]*(\s*-\s*\d[\d.,]*)?\s*[A-Z]{3}|Free)$/.test(t));
    cards.push({url, name, creator: creator ? creator.textContent.trim() : '', thumbnail: img ? img.src : '', price: price || ''});
  }
  const lists = [...document.querySelectorAll('a[href*="/my/lists/"]')].map(a => ({url: abs(a),
    name: (a.querySelector('h3') || {}).textContent || ''})).filter(l => l.name.trim());
  const next = document.querySelector('nav[aria-label="pagination"] a[aria-label="Go to next page"]:not([aria-disabled="true"])');
  return {cards, lists, next: next ? abs(next) : ''};
}"""

# A Payhip shop's wishlists (<shop>/b-account/wishlists): its products, each a link to its page (/b/<code>).
PAYHIP_JS = r"""() => {
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


def booth_products(cards) -> list[dict]:
    return [p for p in (product("booth", c.get("name"), id_=c.get("id"), creator=c.get("creator"), url=c.get("url"),
                                thumbnail=c.get("thumbnail"), price=c.get("price")) for c in cards) if p]


def jinxxy_products(cards) -> list[dict]:
    out = []
    for c in cards:
        store = _store_of(c.get("url"))   # a product Jinxxy lists from another store is that store's; one on a site
        away = store is None              # that isn't a store keeps that page as its link, elsewhere
        p = product(store or "jinxxy", c.get("name"), creator=c.get("creator"), url=None if away else c.get("url"),
                    thumbnail=c.get("thumbnail"), price=c.get("price"), elsewhere=c.get("url") if away else None)
        if p:
            out.append(p)
    return out


def gumroad_products(items) -> list[dict]:
    """A Gumroad wishlist's products, from its page data (props.items)."""
    out = []
    for it in items or []:
        prod = (it or {}).get("product") or {}
        seller = prod.get("seller") or {}
        permalink = prod.get("permalink") if isinstance(prod.get("permalink"), str) else None
        profile = (seller.get("profile_url") or "").split("?", 1)[0].rstrip("/")
        url = f"{profile}/l/{permalink}" if profile and permalink else prod.get("url")
        p = product("gumroad", prod.get("name"), id_=permalink, creator=seller.get("name"), url=url,
                    thumbnail=prod.get("thumbnail_url"),
                    price=cents_price(prod.get("price_cents"), prod.get("currency_code"), prod.get("is_pay_what_you_want") is True))
        if p:
            out.append(p)
    return out


def gumroad_card_products(cards) -> list[dict]:
    """A Gumroad wishlist's products, from its cards (when its page data can't be read)."""
    out = []
    for c in cards:
        price = None
        try:
            price = {"text": c["shown"] or f"{float(c['amount']):.2f} {c['currency']}", "amount": float(c["amount"]),
                     "currency": (c.get("currency") or "").upper()[:3]}
        except (KeyError, TypeError, ValueError):
            price = parse_price(c.get("shown"))
        m = re.search(r"/l/([A-Za-z0-9_-]{1,80})", c.get("url") or "")
        p = product("gumroad", c.get("name"), id_=m.group(1) if m else None, creator=c.get("creator"), url=c.get("url"),
                    thumbnail=c.get("thumbnail"), price=price)
        if p:
            out.append(p)
    return out


def payhip_products(cards) -> list[dict]:
    return [p for p in (product("payhip", c.get("name"), url=c.get("url"), thumbnail=c.get("thumbnail"),
                                price=c.get("price")) for c in cards) if p]


# ----------------------------------------------------------------------------- reading them, signed in

def _with_page(url: str, n: int) -> str:
    u = urlparse(url)
    q = {k: v for k, v in parse_qs(u.query).items() if k != "page"}
    return urlunparse(u._replace(query=urlencode({**q, **({"page": n} if n > 1 else {})}, doseq=True)))


def _signed_in(page, host: str) -> None:
    u = urlparse(page.url)
    if u.hostname != host or re.search(r"sign_in|login|/auth/", u.path) or has_password_field(page):
        raise NotLoggedIn()


def read_booth(ctx, cfg, progress) -> list[dict]:
    """Your loved items on Booth, all of them as one list, and each list of them you made as one more."""
    page = ctx.new_page()
    delay = float(cfg.get("request_delay", 0.8))
    try:
        def read_all(url: str, label: str) -> list[dict]:
            found: dict[str, dict] = {}
            goto(page, url)
            settle(page, 900)
            _signed_in(page, "accounts.booth.pm")
            for n in range(1, MAX_PAGES + 1):
                new = 0
                for c in page.evaluate(BOOTH_JS)["cards"]:
                    if c["id"] not in found:
                        found[c["id"]] = c
                        new += 1
                progress(f"{label}, page {n}: {len(found)} items")
                first = page.evaluate(BOOTH_FIRST_JS)
                if not new or not page.evaluate(BOOTH_NEXT_JS):   # the last page
                    break
                try:   # the next page's cards in place of these (Booth reads them as you turn the page)
                    page.wait_for_function(f"() => ({BOOTH_FIRST_JS})() !== {first!r}", timeout=20000)
                except Exception:
                    break
                settle(page, 600)
                time.sleep(delay)
            return booth_products(found.values())
        everything = read_all(BOOTH_WISHES, LIST_NAMES["booth"])
        out = [{"store": "booth", "list": LIST_NAMES["booth"], "url": BOOTH_WISHES, "products": everything}]
        goto(page, BOOTH_WISHES)
        settle(page, 900)
        names = [x["name"] for x in page.evaluate(BOOTH_JS)["lists"]][2:MAX_LISTS + 2]   # after "all" and "uncategorized"
        for name in names:   # a list you made: its button shows it, and the address it goes to is the list's
            try:
                page.locator("button.charcoal-tag-item", has_text=name).first.click(timeout=10000)
                page.wait_for_url(lambda u: u != BOOTH_WISHES, timeout=10000)
            except Exception:
                continue
            url = page.url
            out.append({"store": "booth", "list": clean_text(name, 60), "url": url, "products": read_all(url, name)})
            goto(page, BOOTH_WISHES)
            settle(page, 600)
        return out
    finally:
        page.close()


def read_gumroad(ctx, cfg, progress) -> list[dict]:
    """Each of your Gumroad wishlists."""
    from .library import extract_page_json
    page = ctx.new_page()
    delay = float(cfg.get("request_delay", 0.8))
    try:
        goto(page, GUMROAD_WISHLISTS)
        settle(page, 1200)
        _signed_in(page, "gumroad.com")
        found = {w["url"]: w for w in page.evaluate(GUMROAD_INDEX_JS)}
        out = []
        for w in list(found.values())[:MAX_LISTS]:
            products: dict[str, dict] = {}
            for n in range(1, MAX_PAGES + 1):
                r = ctx.request.get(_with_page(w["url"], n), timeout=60000)
                data = extract_page_json(r.text()) if r.ok else None
                props = (data or {}).get("props") or {}
                if not data or not isinstance(props.get("items"), list):   # no page data: its cards, as shown
                    goto(page, w["url"])
                    settle(page, 1500)
                    page.mouse.wheel(0, 100000)
                    settle(page, 1200)
                    for p in gumroad_card_products(page.evaluate(GUMROAD_CARDS_JS)):
                        products.setdefault(p["url"], p)
                    break
                for p in gumroad_products(props["items"]):
                    products.setdefault(p.get("url") or p["name"], p)
                progress(f"{w['name']}, page {n}: {len(products)} products")
                pages = (props.get("pagination") or {}).get("pages") or 1
                if n >= pages:
                    break
                time.sleep(delay)
            out.append({"store": "gumroad", "list": clean_text(w["name"], 60), "url": w["url"], "products": list(products.values())})
        return out
    finally:
        page.close()


def read_jinxxy(ctx, cfg, progress) -> list[dict]:
    """Your Jinxxy wishlist, your likes, and each of your lists."""
    page = ctx.new_page()
    delay = float(cfg.get("request_delay", 0.8))
    try:
        def read_all(url: str, label: str) -> tuple[list[dict], list[dict]]:
            cards: dict[str, dict] = {}
            lists: dict[str, dict] = {}
            visited = set()
            for n in range(1, MAX_PAGES + 1):
                goto(page, url)
                settle(page, 1500)
                _signed_in(page, "jinxxy.com")
                visited.add(url)
                got = page.evaluate(JINXXY_JS, page.url)
                for c in got["cards"]:
                    cards.setdefault(c["url"], c)
                for x in got["lists"]:
                    lists.setdefault(x["url"], x)
                progress(f"{label}, page {n}: {len(cards) or len(lists)}")
                if not got["next"] or got["next"] in visited:
                    break
                url = got["next"]
                time.sleep(delay)
            return jinxxy_products(cards.values()), list(lists.values())
        out = []
        for url, name in ((JX_WISHLIST, LIST_NAMES["jinxxy-wishlist"]), (JX_LIKES, LIST_NAMES["jinxxy-likes"])):
            products, _ = read_all(url, name)
            out.append({"store": "jinxxy", "list": name, "url": url, "products": products})
        _, lists = read_all(JX_LISTS, "Lists")
        for x in lists[:MAX_LISTS]:
            products, _ = read_all(x["url"], x["name"])
            out.append({"store": "jinxxy", "list": clean_text(x["name"], 60), "url": x["url"], "products": products})
        return out
    finally:
        page.close()


def read_payhip(ctx, cfg, progress) -> list[dict]:
    """The wishlists in each Payhip shop you've added."""
    page = ctx.new_page()
    try:
        out = []
        for shop in payhip_shops(cfg):
            url = shop.rstrip("/") + "/b-account/wishlists"
            goto_past_check(page, url, float(cfg.get("payhip", {}).get("check_wait", 60)), progress)
            settle(page, 1000)
            cards = page.evaluate(PAYHIP_JS)["cards"]
            out.extend(_payhip_lists(cards, shop, url))
            progress(f"{urlparse(shop).hostname}: {len(cards)} products")
        return out
    finally:
        page.close()


def _payhip_lists(cards, shop: str, url: str) -> list[dict]:
    by: dict[str, list] = {}
    for c in cards:
        by.setdefault(c.get("list") or "Wishlist", []).append(c)
    host = urlparse(shop).hostname or shop
    return [{"store": "payhip", "list": clean_text(f"{host}: {name}", 60), "url": url, "products": payhip_products(cs)}
            for name, cs in (by.items() or [("Wishlist", [])])]


READERS = {"booth": read_booth, "gumroad": read_gumroad, "jinxxy": read_jinxxy, "payhip": read_payhip}


# ----------------------------------------------------------------------------- from pages you saved

def page_kind(url: str | None) -> str | None:
    """Which wishlist page a saved page is, from its own address: booth, gumroad-index, gumroad, jinxxy, payhip."""
    u = urlparse(url or "")
    host, path = (u.hostname or "").lower(), u.path.rstrip("/")
    if host == "accounts.booth.pm" and path == "/wish_lists":
        return "booth"
    if host == "gumroad.com" and path == "/wishlists":
        return "gumroad-index"
    if (host == "gumroad.com" or host.endswith(".gumroad.com")) and re.fullmatch(r"/wishlists/[\w-]+", path):
        return "gumroad"
    if host in ("jinxxy.com", "www.jinxxy.com") and re.fullmatch(r"/my/(wishlist|likes|lists(/\d+)?)", path):
        return "jinxxy"
    if path == "/b-account/wishlists":
        return "payhip"
    return None


def _list_name(kind: str, url: str, page) -> str:
    path = urlparse(url).path.rstrip("/")
    if kind == "booth":
        q = parse_qs(urlparse(url).query)
        shown = next((x["name"] for x in page.evaluate(BOOTH_JS)["lists"] if x["shown"]), "")
        return LIST_NAMES["booth"] if not q or shown.lower() in ("all", "すべて") else clean_text(shown, 60)
    if kind == "jinxxy":
        if path.endswith("/wishlist"):
            return LIST_NAMES["jinxxy-wishlist"]
        if path.endswith("/likes"):
            return LIST_NAMES["jinxxy-likes"]
    title = page.evaluate("() => (document.querySelector('h1') || {}).textContent || ''").strip()
    return clean_text(title, 60) or "Wishlist"


def _canonical(html: str) -> str:
    """A page's <link rel="canonical" href="https://..."> address, or "". Each tag is found first, then read on its
    own, so a page full of half-made <link tags can't make the search slow."""
    start = html.find("<link")
    while start != -1:
        end = html.find(">", start)
        if end == -1:
            break
        tag = html[start:end]
        if 'rel="canonical"' in tag:
            m = re.search(r'\bhref="(https://[^"]+)"', tag)
            if m:
                return m.group(1)
        start = html.find("<link", end)
    return ""


def from_saved_pages(pages) -> list[dict]:
    """Read wishlist pages saved from your own browser, (filename, text) each: one result per page, in order, as
    {"filename", "lists"} or {"filename", "error"}. Read offline, with scripts off and every request blocked. The
    lists of a wishlist saved over several pages (Booth's, Jinxxy's likes) come back once, with every page's
    products together."""
    from .library import _playwright, extract_page_json, read_saved_page
    results, ready = [], []
    for filename, text in pages:
        result = {"filename": filename}
        results.append(result)
        try:
            html, url, _images = read_saved_page(filename, text)
            if not page_kind(url):   # saved as HTML only: the page names its own address
                url = _canonical(html[:200000]) or url
            kind = page_kind(url)
            if not kind:
                raise ValueError("that isn't a wishlist page Hoard can read (Booth's loved items, a Gumroad wishlist, "
                                 "Jinxxy's wishlist, likes or a list, or a Payhip shop's wishlists)")
            ready.append((result, kind, url, html))
        except Exception as e:
            result["error"] = str(e) or type(e).__name__
    if not ready:
        return results
    with _playwright()() as p:
        browser = p.chromium.launch()
        try:
            for result, kind, url, html in ready:
                page = offline_page(browser)
                try:
                    page.set_content(inert_html(html), wait_until="domcontentloaded")
                    name = _list_name(kind, url, page)
                    if kind == "booth":
                        lists = [{"store": "booth", "list": name, "url": url, "products": booth_products(page.evaluate(BOOTH_JS)["cards"])}]
                    elif kind == "gumroad":
                        data = extract_page_json(html)
                        props = (data or {}).get("props") or {}
                        products = gumroad_products(props["items"]) if isinstance(props.get("items"), list) \
                            else gumroad_card_products(page.evaluate(GUMROAD_CARDS_JS))
                        lists = [{"store": "gumroad", "list": clean_text(props.get("name") or name, 60), "url": url.split("?")[0],
                                  "products": products}]
                    elif kind == "gumroad-index":
                        raise ValueError("that's the list of your Gumroad wishlists: save each wishlist's own page instead")
                    elif kind == "jinxxy":
                        got = page.evaluate(JINXXY_JS, url)
                        if urlparse(url).path.rstrip("/").endswith("/my/lists"):
                            raise ValueError("that's the list of your Jinxxy lists: save each list's own page instead")
                        lists = [{"store": "jinxxy", "list": name, "url": url.split("?")[0], "products": jinxxy_products(got["cards"])}]
                    else:
                        u = urlparse(url)
                        lists = _payhip_lists(page.evaluate(PAYHIP_JS)["cards"], f"{u.scheme}://{u.netloc}", url)
                    result["lists"] = lists
                except Exception as e:
                    result["error"] = str(e).splitlines()[0] if str(e) else type(e).__name__
                finally:
                    page.context.close()
        finally:
            browser.close()
    return results


def merge_lists(lists: list[dict]) -> list[dict]:
    """Lists of the same store and name (one saved page each of a long wishlist) as one, products in order."""
    out: dict[tuple, dict] = {}
    for x in lists:
        k = (x["store"], x["list"])
        have = out.setdefault(k, {**x, "products": []})
        seen = {p.get("url") or p["name"] for p in have["products"]}
        have["products"] += [p for p in x["products"] if (p.get("url") or p["name"]) not in seen]
    return list(out.values())
