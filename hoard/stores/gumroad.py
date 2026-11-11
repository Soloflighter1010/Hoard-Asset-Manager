"""Gumroad store adapter: library pages, downloads and recorded wishlist readers.

Shared browser, transport, limits and persistence remain in their common modules.
Compatibility service references preserve dependency overrides during extraction.
"""
from __future__ import annotations

import re
from .services import lib, dl, wish


# ----------------------------------------------------------------------------- Gumroad

lib_GR_LIBRARY = "https://app.gumroad.com/library"


def lib_gumroad_cards(read_props, include_archived: bool, delay: float = 0.0, on_page=None, cfg: dict | None = None):
    """Every purchase card in your Gumroad library, page by page (and the archived ones, when wanted). read_props
    gets a page's query (page, sort, archived) and returns that page's props; on_page(archived, page, pages) is
    told as each is read. Listing the library and downloading both read it this way. A quick refresh's cfg (issue
    #300): only the start of each, the newest purchases."""
    quick = bool((cfg or {}).get("_quick"))
    for archived in ([False, True] if include_archived else [False]):
        page_no, given = 1, 0
        while True:
            params = {"page": page_no, "sort": "purchase_date"} | ({"show_archived_only": "true"} if archived else {})
            props = read_props(params) or {}
            cards = props.get("results") or []
            cards = cards[:max(0, lib.QUICK_ITEMS - given)] if quick else cards
            given += len(cards)
            yield from cards
            pages = (props.get("pagination") or {}).get("pages") or 1
            if on_page:
                on_page(archived, page_no, pages)
            if page_no >= pages or lib.quick_done(cfg or {}, page_no, given):
                break
            page_no += 1
            lib.pause(delay)


def lib_gumroad_page(profile_url, permalink) -> str | None:
    """A Gumroad product's public page (<creator>.gumroad.com/l/<permalink>, or gumroad.com/l/<permalink> for a
    creator on a domain of their own): the purchase's own link is your download page, which is never shared."""
    if not (isinstance(permalink, str) and lib.re.fullmatch(r"[A-Za-z0-9_-]{1,80}", permalink)):
        return None
    own = lib.store_link("gumroad", profile_url.split("?", 1)[0].rstrip("/") + "/l/" + permalink) \
        if isinstance(profile_url, str) else None
    return own or lib.store_link("gumroad", "https://gumroad.com/l/" + permalink)


def lib_gumroad_permalink(prod: dict):
    """A Gumroad library card's product permalink, under whichever name the card has it, or from its own page."""
    for k in ("permalink", "custom_permalink", "unique_permalink"):
        if isinstance(prod.get(k), str) and prod[k]:
            return prod[k]
    for k in ("url", "long_url", "short_url"):
        m = lib.re.search(r"/l/([A-Za-z0-9_-]{1,80})/?$", prod.get(k) or "") if isinstance(prod.get(k), str) else None
        if m:
            return m.group(1)
    return None


def lib_fetch_gumroad(ctx, cfg, progress) -> list[dict]:
    """Every purchase in your Gumroad library, archived ones included when configured."""
    items, seen = [], set()

    def read_props(params: dict) -> dict:
        """One page of Gumroad's library, as the page's own data; raises NotLoggedIn when Gumroad asks you to sign
        in."""
        r = ctx.request.get(lib.GR_LIBRARY, params=params, timeout=60000)
        if "/login" in lib.urlparse(r.url).path:
            raise lib.NotLoggedIn()
        if not r.ok:
            raise RuntimeError(f"the library page answered HTTP {r.status}")
        data = lib.extract_page_json(r.text())
        if not data:
            raise RuntimeError("couldn't find the library data on the page (Gumroad may have changed its site)")
        return data.get("props") or {}

    def on_page(archived, page_no, pages):
        """Say which page of the library is being read."""
        progress(f"{'Archived purchases, page' if archived else 'Page'} {page_no} of {pages}, {len(items)} items")
    for card in lib.gumroad_cards(read_props, cfg["gumroad"].get("include_archived", True),
                              float(cfg.get("request_delay", 0.8)), on_page, cfg):
        prod, pur = card.get("product") or {}, card.get("purchase") or {}
        creator = prod.get("creator") or {}
        variants = (pur.get("variants") or "").strip() or None
        dedupe = ((prod.get("name") or "").lower(), (creator.get("name") or "").lower(), variants)
        if dedupe in seen:  # bought twice
            continue
        seen.add(dedupe)
        items.append(lib.item("gumroad", pur.get("id") or len(items), name=prod.get("name"),
                          creator=creator.get("name"), creator_url=creator.get("profile_url"),
                          thumbnail=prod.get("thumbnail_url"), url=pur.get("download_url"),
                          page=lib.gumroad_page(creator.get("profile_url"), lib.gumroad_permalink(prod)),
                          download_url=pur.get("download_url"), variants=variants,
                          archived=bool(pur.get("is_archived"))))
    return items


dl_GR_BASE = "https://app.gumroad.com"


dl_GR_LIBRARY = dl_GR_BASE + "/library"


dl_GR_LOGIN = dl_GR_BASE + "/login"


# ----------------------------------------------------------------------------- Gumroad

def dl_gumroad_session(cfg: dict) -> dl.requests.Session:
    """An HTTP session signed in to Gumroad, using your Gumroad sign-in in Hoard's browser.

    Earlier versions also accepted a copied session cookie from config.json or an environment variable.
    That's a password-equivalent in plain text, so it's no longer read; sign in with `login gumroad` instead.
    """
    if cfg["gumroad"].get("session_cookie") or dl.os.environ.get("HOARD_GUMROAD_SESSION"):
        dl.log("Note: a Gumroad session cookie in config.json or HOARD_GUMROAD_SESSION is no longer used, because "
            "anyone who sees it can use your account. Delete it (and sign out of Gumroad on its website to end that "
            "session), then sign in with: login gumroad")
    s = dl.egress.session()
    cookies, ua = dl.browser_cookies(cfg, "gumroad")
    if not any(c["name"].startswith("_gumroad_app_session") for c in cookies):
        raise dl.NotLoggedIn("Not signed in to Gumroad")
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    s.headers["User-Agent"] = ua
    return s


class dl_Gumroad:
    """Reads Gumroad pages. Gumroad embeds each page's data as JSON, so no scraping is needed."""
    def __init__(self, cfg: dict, sess: dl.requests.Session):
        """Wrap a signed-in session; request_delay from the config spaces out page loads."""
        self.cfg, self.sess = cfg, sess
        self.delay = float(cfg.get("request_delay", 1.0))

    def page(self, url: str, params: dict | None = None) -> dict:
        """Load a Gumroad page and return its embedded page data (component and props)."""
        dl.pause(self.delay)
        r = dl.egress.get(self.sess, url, dl.STORE_SITES["gumroad"], params=params, timeout=60)
        if "/login" in dl.urlparse(r.url).path:
            raise dl.NotLoggedIn("Gumroad session expired")
        r.raise_for_status()
        data = dl.extract_page_json(r.text)
        if not data:
            raise RuntimeError(f"no page data found at {r.url} (Gumroad's markup may have changed)")
        return data

    def library(self):
        """Every purchase card in the library, archived ones included if configured."""
        yield from dl.gumroad_cards(lambda params: self.page(dl.GR_LIBRARY, params).get("props", {}),
                                 self.cfg["gumroad"].get("include_archived", True))   # (page() waits between pages)

    def file_url(self, page_url: str, token: str, file_id: str, fallback: str | None) -> str | None:
        """Ask for a signed download URL; fall back to the redirecting link on the download page."""
        try:
            r = dl.egress.get(self.sess, dl.urljoin(page_url, f"/r/{token}/product_files.json"), dl.STORE_SITES["gumroad"],
                           params={"product_file_ids[]": file_id}, headers={"Accept": "application/json"}, timeout=60)
            if r.ok:
                files = r.json().get("files") or []
                if files and files[0].get("url"):
                    return files[0]["url"]
        except (dl.requests.RequestException, ValueError):
            pass
        return dl.urljoin(page_url, fallback) if fallback else None


def dl_gumroad_files(items, prefix: str = ""):
    """Yield (sub-folder, file) for every file on a download page, following Gumroad's folders."""
    for it in items or []:
        if it.get("type") == "folder":
            yield from dl.gumroad_files(it.get("children"), prefix + dl.safe_name(it.get("name") or "Folder") + "/")
        elif it.get("type") == "file":
            yield prefix, it


def dl_gumroad_page_images(content: dict) -> list[str]:
    """The pictures a creator put in a download page itself (Gumroad's rich content), in page order. Some products
    are only that: a set of PNG textures shown on the page, with no files listed."""
    found: list[str] = []

    def walk(node):
        """Note each picture from Gumroad's own file host in this part of the page, and in what's under it."""
        if isinstance(node, dict):
            if node.get("type") == "image":
                src = (node.get("attrs") or {}).get("src")
                if isinstance(src, str) and dl.urlparse(src).scheme == "https" and dl.urlparse(src).hostname == "public-files.gumroad.com":
                    found.append(src)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    for page in (content or {}).get("rich_content_pages") or []:
        if isinstance(page, dict):
            walk(page.get("description"))
    return list(dict.fromkeys(found))


def dl_gumroad_filename(f: dict) -> str:
    """A safe local name for a Gumroad file: its name plus its extension, in lower case."""
    name = (f.get("file_name") or f.get("id") or "file").strip()
    ext = (f.get("extension") or "").strip().lower().lstrip(".")
    if ext and not name.lower().endswith("." + ext):
        name = f"{name}.{ext}"
    return dl.safe_name(name, 150)


def dl__gumroad_page_images(gr, content: dict, rec: dict, folder: dl.Path, name: str, creator: str, man, args,
                         report: dl.Report) -> bool:
    """Save the pictures in a download page that lists no files, into "Page images", each named by its place on the
    page and typed by what it is. True when one was downloaded."""
    got_any = False
    public = dl.egress.session()   # public pictures: fetched without your Gumroad sign-in
    for n, src in enumerate(dl.gumroad_page_images(content), 1):
        token = dl.urlparse(src).path.rstrip("/").rsplit("/", 1)[-1]
        fid = "page-image:" + token
        old = rec["files"].get(fid)
        if old and dl.rel_to_path(folder, old["path"]).exists():
            continue
        stem = f"Page images/{n:02d} {dl.safe_name(token, 40)}"
        if dl.left_out(args, report, "gumroad", name, stem):
            continue
        if args.dry_run:
            dl.would_get(args, report, "gumroad", rec, name, creator, stem, False, old is not None)
            continue
        staged = dl.rel_to_path(folder, stem + ".download")
        try:
            dl.with_retries(report, stem, lambda src=src, staged=staged: dl.egress.download(
                public, src, staged, ["public-files.gumroad.com"], desc=stem, progress=dl.downloading(stem)))
        except Exception as e:
            report.failed.append(f"Gumroad: {creator} / {name} / {stem} - {e}")
            continue
        ext = dl.picture_extension(staged)
        if not ext:   # not a picture after all: not kept
            staged.unlink(missing_ok=True)
            report.skipped.append(f"Gumroad: {name} / {stem} - not a picture")
            continue
        relpath = f"{stem}.{ext}"
        dl.os.replace(staged, dl.rel_to_path(folder, relpath))
        rec["files"][fid] = {"path": relpath, "size": dl.rel_to_path(folder, relpath).stat().st_size, "downloaded_at": dl.now_iso()}
        dl.log(f"    saved: {relpath}")
        report.new_files.append(f"Gumroad: {creator} / {name} / {relpath}")
        report.saved("gumroad", name, stem)
        got_any = True
        man.checkpoint()
    return got_any


def dl_sync_gumroad(cfg: dict, root: dl.Path, args, report: dl.Report) -> None:
    """Download everything new or changed in your Gumroad library."""
    store_dir = root / "Gumroad"
    man = dl.StoreRecords(cfg, root, "Gumroad")
    gr = dl.Gumroad(cfg, dl.gumroad_session(cfg))

    try:
        dl._sync_gumroad_purchases(cfg, gr, store_dir, man, args, report)
    finally:
        gr.sess.cookies.clear()  # the copied sign-in only lives for this sync
        gr.sess.close()
        man.save_changes()   # every finished file recorded, however the sync ended


def dl__sync_gumroad_purchases(cfg: dict, gr: "Gumroad", store_dir: dl.Path, man: dl.StoreRecords, args, report: dl.Report) -> None:
    """Download everything new or changed, one purchase at a time (see sync_gumroad)."""
    chosen = (getattr(args, "targets", None) or {}).get("gumroad")
    if chosen:   # straight to the chosen purchases' download pages
        cards = [{"product": {"name": i.get("name"), "creator": {"name": i.get("creator")},
                              "thumbnail_url": i.get("thumbnail")},   # its picture, as the library has it
                  "purchase": {"id": i.get("id"), "download_url": i.get("download_url"), "variants": i.get("variants") or ""}}
                 for i in chosen]
        dl.log(f"Gumroad: {len(cards)} chosen {'purchase' if len(cards) == 1 else 'purchases'}")
    else:
        cards = list(gr.library())
        dl.log(f"Gumroad: {len(cards)} purchases in your library")
    seen: set[str] = set()

    for n, card in enumerate(cards, 1):
        dl.tick(f"Gumroad: purchase {n} of {len(cards)}")   # Stop is noticed here too
        prod, pur = card.get("product") or {}, card.get("purchase") or {}
        name = (prod.get("name") or "Untitled").strip()
        creator = ((prod.get("creator") or {}).get("name") or "Unknown Creator").strip()
        if not chosen and dl.skip_product(args, "gumroad", name, creator):
            continue
        page_url = pur.get("download_url")
        if not page_url:
            report.skipped.append(f"Gumroad: {name} - no download page (refunded or membership inactive)")
            continue
        try:
            page = gr.page(page_url)
        except dl.NotLoggedIn:
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
        if dl.removed_product("gumroad", name, report) or man.away(key, f"Gumroad: {name}", report):
            continue
        rec = man.record(key, creator, f"{name} - {variants}" if variants else name)
        is_new_asset = not rec["files"]
        rec.update(name=name, creator=creator, variants=variants or None, url=p.get("product_long_url"),
                   last_synced=dl.now_iso())
        folder = man.folder_of(rec)
        token = props.get("token")
        dl.log(f"\n[Gumroad] {creator} / {name}{f' ({variants})' if variants else ''}")

        got_any = False
        offered = {f.get("id") for _sub, f in dl.gumroad_files(content.get("content_items"))}
        for sub, f in dl.gumroad_files(content.get("content_items")):
            fid, size = f.get("id"), f.get("file_size")
            relpath = dl.distinct_name(sub + dl.gumroad_filename(f), fid, rec, offered)
            target = dl.rel_to_path(folder, relpath)
            old = rec["files"].get(fid)
            if target.exists() and (not size or target.stat().st_size == size):
                rec["files"][fid] = {**(old or {}), "path": relpath, "size": target.stat().st_size}
                continue
            if not f.get("download_url"):
                report.skipped.append(f"Gumroad: {name} / {relpath} - streaming only, no download")
                continue
            is_update = target.exists() or (old is not None and (old.get("size") != size or old.get("path") != relpath))
            label = f"{creator} / {name} / {relpath}"
            if dl.left_out(args, report, "gumroad", name, relpath):
                continue
            if args.dry_run:
                dl.would_get(args, report, "gumroad", rec, name, creator, relpath, is_update, old is not None and not is_update)
                continue
            try:
                got = dl.with_retries(report, relpath, lambda fid=fid, f=f, target=target, relpath=relpath: dl.egress.download(
                    gr.sess, gr.file_url(page_url, token, fid, f.get("download_url")), target, dl.STORE_SITES["gumroad"],
                    desc=relpath, progress=dl.downloading(relpath)))
            except Exception as e:
                report.failed.append(f"Gumroad: {label} - {e}")
                continue
            dl.log(f"    {'updated' if is_update else 'saved'}: {relpath}")
            (report.updated if is_update else report.new_files).append(f"Gumroad: {label}")
            report.saved("gumroad", name, relpath)
            rec["files"][fid] = {"path": relpath, "size": got, "downloaded_at": dl.now_iso()}
            got_any = True
            man.checkpoint()

        if not offered:   # no files: what the creator put in the page itself, such as a set of textures
            got_any = dl._gumroad_page_images(gr, content, rec, folder, name, creator, man, args, report) or got_any

        if got_any and is_new_asset:
            report.new_assets.append(f"Gumroad: {creator} / {name}")
        if cfg["gumroad"].get("save_thumbnails", True) and not args.dry_run:
            dl.save_thumbnail(prod.get("thumbnail_url"), folder)
        man.checkpoint()


wish_GUMROAD_WISHLISTS = "https://gumroad.com/wishlists"


# Gumroad's wishlists (gumroad.com/wishlists): a row for each, its name and its own address.
wish_GUMROAD_INDEX_JS = r"""() => [...document.querySelectorAll('a[href*="/wishlists/"]')]
  .filter(a => a.querySelector('h4, h3, h2')).map(a => ({name: a.textContent.trim(), url: a.href}))"""


# A Gumroad wishlist's own page, when its page data can't be read: a card (<article>) for each product.
wish_GUMROAD_CARDS_JS = r"""() => [...document.querySelectorAll('article')].map(a => {
  const link = a.querySelector('a[href*="/l/"]'), seller = a.querySelector('header a[href]:not([href*="/l/"])');
  const price = a.querySelector('[itemprop="price"]'), cur = a.querySelector('[itemprop="priceCurrency"]');
  return {url: link ? link.href : '', name: (a.querySelector('h4, h3') || {}).textContent || '',
          creator: seller ? seller.textContent.trim() : '', thumbnail: (a.querySelector('figure img') || {}).src || '',
          amount: price ? price.getAttribute('content') : '', currency: cur ? cur.textContent.trim() : '',
          shown: price ? price.textContent.trim() : ''};
}).filter(c => c.url && c.name.trim())"""


def wish_gumroad_products(items) -> list[dict]:
    """A Gumroad wishlist's products, from its page data (props.items)."""
    out = []
    for it in items or []:
        prod = (it or {}).get("product") or {}
        seller = prod.get("seller") or {}
        permalink = prod.get("permalink") if isinstance(prod.get("permalink"), str) else None
        profile = (seller.get("profile_url") or "").split("?", 1)[0].rstrip("/")
        url = f"{profile}/l/{permalink}" if profile and permalink else prod.get("url")
        p = wish.product("gumroad", prod.get("name"), id_=permalink, creator=seller.get("name"), url=url,
                    thumbnail=prod.get("thumbnail_url"),
                    price=wish.cents_price(prod.get("price_cents"), prod.get("currency_code"), prod.get("is_pay_what_you_want") is True))
        if p:
            out.append(p)
    return out


def wish_gumroad_card_products(cards) -> list[dict]:
    """A Gumroad wishlist's products, from its cards (when its page data can't be read)."""
    out = []
    for c in cards:
        price = None
        try:
            price = {"text": c["shown"] or f"{float(c['amount']):.2f} {c['currency']}", "amount": float(c["amount"]),
                     "currency": (c.get("currency") or "").upper()[:3]}
        except (KeyError, TypeError, ValueError):
            price = wish.parse_price(c.get("shown"))
        m = wish.re.search(r"/l/([A-Za-z0-9_-]{1,80})", c.get("url") or "")
        p = wish.product("gumroad", c.get("name"), id_=m.group(1) if m else None, creator=c.get("creator"), url=c.get("url"),
                    thumbnail=c.get("thumbnail"), price=price)
        if p:
            out.append(p)
    return out


def wish_read_gumroad(ctx, cfg, progress) -> list[dict]:
    """Each of your Gumroad wishlists."""
    from ..library import extract_page_json
    page = ctx.new_page()
    delay = float(cfg.get("request_delay", 0.8))
    try:
        wish.goto(page, wish.GUMROAD_WISHLISTS)
        wish.settle(page, 1200)
        wish._signed_in(page, "gumroad.com")
        found = {w["url"]: w for w in page.evaluate(wish.GUMROAD_INDEX_JS)}
        out = []
        for w in list(found.values())[:wish.MAX_LISTS]:
            if not wish.wanted(cfg, w["name"]):   # (a quick refresh of another list: issue #331)
                continue
            products: dict[str, dict] = {}
            short = False   # (a quick refresh stopped before its end: issue #300)
            for n in range(1, wish.MAX_PAGES + 1):
                r = ctx.request.get(wish._with_page(w["url"], n), timeout=60000)
                data = extract_page_json(r.text()) if r.ok else None
                props = (data or {}).get("props") or {}
                if not data or not isinstance(props.get("items"), list):   # no page data: its cards, as shown
                    wish.goto(page, w["url"])
                    wish.settle(page, 1500)
                    page.mouse.wheel(0, 100000)
                    wish.settle(page, 1200)
                    for p in wish.gumroad_card_products(page.evaluate(wish.GUMROAD_CARDS_JS)):
                        products.setdefault(p["url"], p)
                    break
                for p in wish.gumroad_products(props["items"]):
                    if cfg.get("_quick") and len(products) >= wish.QUICK_ITEMS:
                        short = True
                        break
                    products.setdefault(p.get("url") or p["name"], p)
                progress(f"{w['name']}, page {n}: {len(products)} products")
                pages = (props.get("pagination") or {}).get("pages") or 1
                if n >= pages:
                    break
                if wish.quick_done(cfg, n, len(products)):
                    short = True
                    break
                wish.time.sleep(delay)
            out.append({"store": "gumroad", "list": wish.clean_text(w["name"], 60), "url": w["url"], "products": list(products.values()),
                        **({"partial": True} if short else {})})
        return out
    finally:
        page.close()

LIBRARY_EXPORTS = {
    'GR_LIBRARY': lib_GR_LIBRARY,
    'gumroad_cards': lib_gumroad_cards,
    'gumroad_page': lib_gumroad_page,
    'gumroad_permalink': lib_gumroad_permalink,
    'fetch_gumroad': lib_fetch_gumroad,
}

DOWNLOADER_EXPORTS = {
    'GR_BASE': dl_GR_BASE,
    'GR_LIBRARY': dl_GR_LIBRARY,
    'GR_LOGIN': dl_GR_LOGIN,
    'gumroad_session': dl_gumroad_session,
    'Gumroad': dl_Gumroad,
    'gumroad_files': dl_gumroad_files,
    'gumroad_page_images': dl_gumroad_page_images,
    'gumroad_filename': dl_gumroad_filename,
    '_gumroad_page_images': dl__gumroad_page_images,
    'sync_gumroad': dl_sync_gumroad,
    '_sync_gumroad_purchases': dl__sync_gumroad_purchases,
}

WISHLISTS_EXPORTS = {
    'GUMROAD_WISHLISTS': wish_GUMROAD_WISHLISTS,
    'GUMROAD_INDEX_JS': wish_GUMROAD_INDEX_JS,
    'GUMROAD_CARDS_JS': wish_GUMROAD_CARDS_JS,
    'gumroad_products': wish_gumroad_products,
    'gumroad_card_products': wish_gumroad_card_products,
    'read_gumroad': wish_read_gumroad,
}


from .base import Adapter

STORE = Adapter('gumroad', 'Gumroad', 'https://app.gumroad.com/login', 'https://gumroad.com/', 2, saved_pages=False)


def saved_wishlist(page, kind: str, url: str, html: str, name: str) -> list[dict]:
    """Parse this store's saved wishlist with scripts and network already disabled."""
    if kind == "gumroad-index":
        raise ValueError("that's the list of your Gumroad wishlists: save each wishlist's own page instead")
    data = lib.extract_page_json(html)
    props = (data or {}).get("props") or {}
    products = wish.gumroad_products(props["items"]) if isinstance(props.get("items"), list) \
        else wish.gumroad_card_products(page.evaluate(wish.GUMROAD_CARDS_JS))
    lists = [{"store": "gumroad", "list": wish.clean_text(props.get("name") or name, 60), "url": url.split("?")[0],
              "products": products}]
    return lists


def extract_page_json(text: str):
    """The page data Gumroad embeds in its HTML (component and props), or None. (Reading the library and
    downloading both use this.)"""
    found = next((inside for attrs, inside in lib.script_tags(text) if lib.re.search(r'\bdata-page="app"', attrs)), None)
    if found is not None:
        return lib.json.loads(found)
    m = lib.re.search(r'\bdata-page="(\{[^"]*)"', text)
    if m:
        return lib.json.loads(lib.html.unescape(m.group(1)))
    # Older react-on-rails markup, kept as a fallback
    best = None
    for attrs, inside in lib.script_tags(text):
        m = lib.re.search(r'data-component-name="([^"]+)"', attrs) if "js-react-on-rails-component" in attrs else None
        if m and (best is None or len(inside) > len(best[1])):
            best = (m.group(1), inside)
    if best:
        return {"component": best[0], "props": lib.json.loads(best[1])}
    return None

LIBRARY_EXPORTS['extract_page_json'] = extract_page_json
