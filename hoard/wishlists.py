"""Your wishlists from the stores (issue #158): Booth's loved items, Gumroad's wishlists, Jinxxy's wishlist, likes and
lists, and each Payhip shop's wishlists. Each list the store has becomes a wishlist in Hoard (a set of the kind
"wishlist", hoard/sets.py), with what each product cost when it was read, so a price that changes shows.

They're read as a refresh reads your library: in each store's own signed-in browser window (read_lists), or from
pages you saved from your own browser (from_saved_pages), read offline with scripts off. Every reader returns the
same shape: [{"store", "list", "url", "products": [{"store", "id"?, "name", "creator", "url", "thumbnail", "price"}]}].
A quick refresh (issue #300) reads only the start of each list; one it stopped short in says "partial": True, and
keeps the products it didn't reach.
"""
from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunparse

from .adult import on_a_page as adult_on_a_page
from .browser import goto, goto_past_check, has_password_field, settle
from .common import QUICK_ITEMS, NotLoggedIn, pause, quick_done
from .config import payhip_shops
from .safety import clean_text, fetch_public, inert_html, is_video_address, offline_page, safe_url

MAX_PAGES = 200            # pages of one list (Booth shows 20 on each: 4,000 products)
MAX_LISTS = 50             # lists from one store


# Store code lives in hoard/stores; these aliases preserve the public Python API.
from .stores import install as _install_stores
_install_stores('wishlists', globals())

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
            elsewhere=None, adult=False) -> dict | None:
    """One product on a wishlist, cleaned: None without a name. elsewhere: its page on a site that isn't one of the
    stores (one a Jinxxy list sends you to), kept as it is but for anything after #. adult: its store marks it as
    for adults (hoard/adult.py)."""
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
    if safe_url(thumbnail) and not is_video_address(thumbnail):   # (a video isn't a picture: issue #212)
        out["thumbnail"] = safe_url(thumbnail)
    if isinstance(price, dict) or isinstance(price, str):
        p = price if isinstance(price, dict) else parse_price(price)
        if p:
            out["price"] = p
    if adult is True:
        out["adult"] = True
    return out


def _store_of(url: str) -> str | None:
    """Which store a page is on (booth, gumroad, jinxxy, payhip, itch), by its address; None for any other site."""
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
# where a product's page is read from (Booth's item JSON is read from booth.pm itself): the store's own site, or a
# creator's one level under it
PAGE_SITES = {"gumroad": r"(?:[a-z0-9-]{1,63}\.)?gumroad\.com", "jinxxy": r"(?:www\.)?jinxxy\.com",
              "payhip": r"(?:www\.)?payhip\.com", "itch": r"[a-z0-9-]{1,63}\.itch\.io"}
_PAGE_PATH = r"(?:/[A-Za-z0-9_.~-]{1,120}){1,2}"
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
        got = product("booth", data.get("name"), id_=item, creator=(data.get("shop") or {}).get("name"),
                      url=url, thumbnail=next((x for x in pics if x), None), price=data.get("price"))
        return {**got, "store_tags": store_tags_in("booth", data), "adult": adult_on_a_page("booth", data) is True} if got else got
    address = page_address(store, url)
    got = fetch(address, tuple(dict.fromkeys((host,) + LINK_HOSTS[store]))) if address else None
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
    got = product(store, name, creator=creator, url=url, thumbnail=found.get("image") or meta("og:image"), price=price)
    said = adult_on_a_page(store, page)
    return {**got, "store_tags": store_tags_in(store, page), **({"adult": said} if said is not None else {})} if got else got


TAGGED_STORES = ("booth", "jinxxy", "itch")   # where a product's own page shows the tags its creator gave it
ADULT_SAID_BY = ("booth", "jinxxy")           # ...and where it says whether the product is for adults (hoard/adult.py)
MAX_STORE_TAGS = 30


def store_tags_in(store: str, got) -> list[str]:
    """Issue #206: the tags a product's creator gave it on its store, as Hoard keeps tags (clean_tag): Booth's, and its
    category, from its item JSON (got, a dict); Jinxxy's from its page's data and itch.io's from its page's Tags row
    (got, the page). Gumroad's and Payhip's pages don't show any. At most MAX_STORE_TAGS, in the store's order."""
    import json
    import html as html_text
    from .tags import clean_tag
    raw: list = []
    from .stores import adapters
    adapter = adapters().get(store)
    raw = adapter.tags(got) if adapter else []
    out: list[str] = []
    for t in raw if isinstance(raw, list) else []:
        tag = clean_tag(t) if isinstance(t, str) else ""
        if tag and tag not in out:
            out.append(tag)
    return out[:MAX_STORE_TAGS]


def read_store_page(url: str, hosts: tuple) -> tuple[str, str] | None:
    """A store's public page (or Booth's item JSON), as Add products by link reads it: only from those hosts (https,
    redirects included), at public addresses, sending no sign-in. (Its text, its content type), or None."""
    got = fetch_public(url, {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
                                           "like Gecko) Chrome/140.0 Safari/537.36",
                             "Accept": "application/json" if url.endswith(".json") else "text/html"},
                       MAX_PRODUCT_PAGE, hosts=hosts)
    return (got[0].decode("utf-8", "replace"), got[1]) if got else None


PICTURE_PAGES = 60   # products' public pages read for their pictures, at most, each time a store is read


def pictures_from_pages(items: list[dict], fetch, progress=lambda m: None, delay: float = 0.0, page_of=None,
                        limit: int = PICTURE_PAGES) -> int:
    """Issue #212: products that came with no picture (a store showing a video first: the video isn't one), given the
    picture their public page shows (from_product_page: its JSON-LD, Open Graph tag, or Booth's item JSON). Changes
    items' "thumbnail" in place; page_of(item) is its public page (its "url"). At most limit pages, delay apart.
    Returns how many were found."""
    page_of = page_of or (lambda x: x.get("url"))
    todo = [x for x in items if (not x.get("thumbnail") or is_video_address(x.get("thumbnail"))) and page_of(x)][:limit]
    found = 0
    for n, x in enumerate(todo, 1):
        progress(f"Pictures, {n} of {len(todo)}")
        try:
            still = from_product_page(page_of(x), fetch).get("thumbnail")
        except Exception as e:   # (a page that can't be read leaves its product as it was)
            print(f"Couldn't read the picture of {x.get('name')!r}: {str(e)[:200]}", flush=True)
            still = None
        if still:
            x["thumbnail"] = still
            found += 1
        if n < len(todo):
            pause(delay)
    return found


def page_address(store: str, url: str) -> str | None:
    """Where a product's page is read from, or None: put back together from its link's host and path, each checked
    here, where the address is made, to be the store's site or a creator's on it (PAGE_SITES) and a page's path. So
    the request only ever asks the store, whatever was pasted (product_link has checked the link once already)."""
    parts = urlsplit(url)
    host, path = parts.hostname or "", parts.path
    if store in PAGE_SITES and re.fullmatch(PAGE_SITES[store], host) and re.fullmatch(_PAGE_PATH, path):
        return f"https://{host}{path}"
    return None


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


# ----------------------------------------------------------------------------- reading them, signed in

def _with_page(url: str, n: int) -> str:
    """The address with its page number set (none for the first page)."""
    u = urlparse(url)
    q = {k: v for k, v in parse_qs(u.query).items() if k != "page"}
    return urlunparse(u._replace(query=urlencode({**q, **({"page": n} if n > 1 else {})}, doseq=True)))


def _signed_in(page, host: str) -> None:
    """Raise NotLoggedIn when the store showed its sign-in page instead of your list."""
    u = urlparse(page.url)
    if u.hostname != host or re.search(r"sign_in|login|/auth/", u.path) or has_password_field(page):
        raise NotLoggedIn()


from .stores import adapters
READERS = {key: a.read_wishlists for key, a in adapters().items() if a.wishlists}


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
    """The name a saved list page's list goes by: the store's own list name, or the one you gave it."""
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
                    from .stores import adapters
                    lists = adapters()[kind.split("-")[0]].saved_wishlist(page, kind, url, html, name)
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
