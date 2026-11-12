"""Everything you own on every store: the store readers, saved-page imports and your library list."""
from __future__ import annotations

from . import storage

import email
import contextlib
import copy
import hashlib
import html
import json
import os
import re
import threading
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from .config import NewShop, apply_store_sites, clean_payhip_shop, payhip_shops
from . import itch, vault
from .browser import Blocked, PageLoadError, _playwright, goto, goto_past_check, has_password_field, hops_text, settle
from .common import QUICK_ITEMS, NotLoggedIn, log, now_iso, pause, quick_done
from .net import STORE_HOSTS, blocked_here, blocked_message, plain_error
from .paths import THUMB_DIR
from .safety import DataFileError, STORE_LINK_SITES, clean_text, fetch_public, inert_html, is_video_address, offline_page, remember_sealed, safe_url, seal, store_link
from .storage import seal_status as check_seal, read_document as read_json_file, archive_document as set_aside, write_document as write_file_safely
from .tags import TagMatcher, TagStore, clean_tag, product_type, tag_key


from .stores import adapters

STORES = {key: {"label": a.label, "login": a.login, "referer": a.referer} for key, a in adapters().items()}
DOWNLOADABLE = tuple(key for key, a in adapters().items() if a.downloads)


ADDED_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")


def item(store: str, id_, **fields) -> dict:
    """One library item in the shape every store reader produces. Links that aren't http(s) are dropped."""
    d = {"key": f"{store}:{id_}", "store": store, "id": str(id_), "name": "", "creator": "",
         "creator_url": None, "thumbnail": None, "url": None, "download_url": None, "files": [],
         "variants": None, "archived": False, "gift": False, "page": None}
    d.update({k: v for k, v in fields.items() if v not in (None, "")})
    # page: the product's public page on its store, where a store's "url" is a page of yours (a Gumroad
    # purchase's download page): what a set you share links to (hoard/sets.py), never your own
    for k in ("creator_url", "url", "download_url", "page"):  # links you can open: only to this store's own website
        d[k] = store_link(store, d[k])
    d["thumbnail"] = safe_url(d["thumbnail"])       # images come from the stores' image hosts
    if is_video_address(d["thumbnail"]):            # (a video's address isn't a picture: issue #212)
        d["thumbnail"] = None
    d["files"] = [{"name": clean_text(f.get("name"), 200) or "File", "url": store_link(store, f.get("url"))}
                  for f in d["files"][:500] if store_link(store, f.get("url"))]
    d["name"] = clean_text(d["name"], 300) or "Untitled"
    d["creator"] = clean_text(d["creator"], 200) or "Unknown creator"
    d["variants"] = clean_text(d["variants"], 300) or None
    d["archived"], d["gift"] = d["archived"] is True, d["gift"] is True
    if "gift_from" in d:   # who gave it you (issue #276: Jinxxy says), on a gift only
        d["gift_from"] = clean_text(d["gift_from"], 120) if d["gift"] and isinstance(d["gift_from"], str) else ""
        if not d["gift_from"]:
            del d["gift_from"]
    added = d.get("added")
    d["added"] = added if isinstance(added, str) and ADDED_TIME.fullmatch(added) else None
    if "adult" in d:   # what its store says, once read (hoard/adult.py): for adults, or not
        d["adult"] = d["adult"] is True
    if "store_tags" in d:   # the tags its creator gave it on its store's page (issue #206): read, even if none
        tags = d["store_tags"] if isinstance(d["store_tags"], list) else []
        d["store_tags"] = list(dict.fromkeys(c for c in (clean_tag(x) for x in tags[:60] if isinstance(x, str)) if c))[:30]
    return d


# Store code lives in hoard/stores; these aliases preserve the public Python API.
from .stores import install as _install_stores
_install_stores('library', globals())


def script_tags(text: str):
    """Each <script ...>...</script> in a page, in order: (its opening tag's attributes, what's inside it). Found by
    looking for each one's ends, reading the page once: a regular expression for them (<script[^>]*...>(.*?)</script>)
    took time growing with the square of a page's length when it had many <script tags left open, as a saved page
    you import might (45 seconds for 70 KB)."""
    start = text.find("<script")
    while start != -1:
        tag_end = text.find(">", start)
        close = text.find("</script>", tag_end) if tag_end != -1 else -1
        if close == -1:
            return
        yield text[start + len("<script"):tag_end], text[tag_end + 1:close]
        start = text.find("<script", close + len("</script>"))


# An inventory item's video still, when its first picture is a video (issue #212): a still the page gives the video


def sign_in_urls(cfg: dict, store: str) -> list[str]:
    """The page(s) where you sign in to a store. For Payhip, its own sign-in page first, then one page per shop in
    your settings: a shop keeps its own buyer account, and a shop on its own address also asks payhip.com whether
    you're signed in to Payhip itself (its sign-in check, payhip.com/global-identity), which goes round in a loop
    when you aren't."""
    shops = [s + "/b-account" for s in payhip_shops(cfg)] if store == "payhip" else []
    return [STORES[store]["login"], *shops]


def open_sign_in_pages(ctx, cfg: dict, store: str):
    """Open the page(s) where you sign in to a store (sign_in_urls), one tab each, in Hoard's own window."""
    first = ctx.pages[0] if ctx.pages else ctx.new_page()
    urls = sign_in_urls(cfg, store)
    first.goto(urls[0])
    for url in urls[1:]:
        ctx.new_page().goto(url)
    return first


FETCHERS = {key: a.read_library for key, a in adapters().items()}


# ----------------------------------------------------------------------------- saved pages
#
# When a store won't let Hoard's browser read your library (or, for Payhip, when you'd rather not sign in), you can
# save the library pages from your own browser and import them. A library often spans several pages (Payhip keeps
# one per shop), so any number are imported at once, read together in one browser with scripts off and no network.

IMPORTABLE = tuple(key for key, a in adapters().items() if a.saved_pages)


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
    # inert_html removes every script (and every <base>) from the saved page. The readers get the page's address
    # as prep["base"]; a <base> tag here would be removed by inert_html along with any the page brought, so none
    # is added (earlier versions added one that was then always removed).
    # (Jinxxy's page came with its items' data in its scripts, read as data before they're taken out: issue #276)
    data = jinxxy_data(jinxxy_ssr([t for _, t in script_tags(page_html) if "ApolloSSRDataTransport" in t])) if store == "jinxxy" else {}
    return {"store": store, "html": inert_html(page_html), "base": base, "shop_page": shop_page, "images": images,
            "jinxxy_data": data}


def _read_import(browser, cfg: dict, prep: dict) -> list[dict]:
    """The items on one prepared page (see _prepare_import), read offline, with the images saved inside it kept."""
    store = prep["store"]
    page = offline_page(browser)   # scripts off, no network: read the file, run nothing, contact nobody
    try:
        # at its own address, so that links the page left relative (/my/inventory/...) are its store's: the page is
        # handed over from here, never fetched (offline_page refuses everything else)
        at = (store_link(store, prep["base"]) or "").split("#")[0]
        if at:
            page.route(lambda u: u == at, lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=prep["html"]))
            page.goto(at, wait_until="domcontentloaded")
        else:
            page.set_content(prep["html"], wait_until="domcontentloaded")
        from .stores import adapters
        items = adapters()[store].read_saved(page, cfg, prep)
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
            write_file_safely(THUMB_DIR / f"{hashlib.sha1(i['thumbnail'].encode(), usedforsecurity=False).hexdigest()}.{IMAGE_TYPES[ctype]}", data)
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

def _forget_pictures(gone: list[dict], kept: set) -> None:
    """Delete the cached pictures of products taken off the list, but not one a product still listed uses too (the
    same picture, as two copies of a product share)."""
    for url in {i.get("thumbnail") for i in gone} - kept:
        if url:
            for cached in THUMB_DIR.glob(hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest() + ".*"):
                cached.unlink(missing_ok=True)


class Library:
    """Your combined library, kept in library.json. Safe to use from several threads."""
    def __init__(self, path: Path):
        """Load library.json, or start empty."""
        self.path = path
        self.lock = storage.metadata_lock
        self.data = {"items": [], "stores": {}}
        self._pictured, self._pictured_from = {}, None   # key -> item with a picture, for data["items"] (see _with_picture)
        if storage.exists(path):
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
                    i.update(creator_url=None, thumbnail=None, url=None, download_url=None, files=[], page=None)
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
                                             "variants", "archived", "gift", "gift_from", "added", "page", "store_tags", "adult")}
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
                    **{k: clean_text(info[k], 40) for k in ("refreshed", "updated", "first_read") if isinstance(info.get(k), str)},
                    **({"source": info["source"]} if info.get("source") in ("import", "refresh") else {}),
                    **({"found_shops": [f for f in info["found_shops"][:200] if isinstance(f, str) and clean_payhip_shop(f) == f]}
                       if store == "payhip" and isinstance(info.get("found_shops"), list) else {}),
                }
        return out

    def save(self) -> None:
        """Seal library.json and write it safely (see write_file_safely)."""
        write_file_safely(self.path, json.dumps(seal(self.data), indent=1, ensure_ascii=False))
        remember_sealed(self.path)

    @contextlib.contextmanager
    def changing(self):
        """Publish a refresh and its identities together; restore memory if persistence fails."""
        with self.lock:
            before = copy.deepcopy(self.data)
            try:
                with storage.transaction() if storage.managed(self.path) else contextlib.nullcontext():
                    yield
            except BaseException:
                self.data = before
                raise

    def _stamp(self, store: str, items: list[dict]) -> str:
        """Note when each item first appeared in the library (issue #18: Recently added, and the New badge), and
        return when this store was first read. An item seen before keeps its time (an item listed before Hoard
        kept times has none). The first read of a store brings everything at once, so its items are dated then but
        aren't new: an item is new when it appeared after the store's first read."""
        now = now_iso()
        before = {i["key"]: i for i in self.data["items"] if i["store"] == store}
        info = self.data["stores"].get(store) or {}
        # a store read before Hoard kept these times: anything appearing from now on is new ("" is before any time)
        first = info.get("first_read") if isinstance(info.get("first_read"), str) else ("" if before else now)
        for i in items:
            i["added"] = before[i["key"]].get("added") if i["key"] in before else now
            if not i.get("page") and i["key"] in before:   # (its public page, found by an earlier refresh)
                i["page"] = before[i["key"]].get("page")
            if "store_tags" not in i and "store_tags" in before.get(i["key"], {}):   # (its store's tags, read before)
                i["store_tags"] = before[i["key"]]["store_tags"]
            if "adult" not in i and "adult" in before.get(i["key"], {}):   # (and whether it's for adults)
                i["adult"] = before[i["key"]]["adult"]
        return first

    def replace_store(self, store: str, items: list[dict], keep_others: bool = False) -> None:
        """Swap in a store's freshly read items and record the refresh. keep_others: the refresh couldn't read
        everything (a Payhip shop), so items it didn't find are kept rather than dropped."""
        with self.changing():
            if keep_others:
                found = {i["key"] for i in items}
                items = items + [i for i in self.data["items"] if i["store"] == store and i["key"] not in found]
            first = self._stamp(store, items)
            self.data["items"] = [i for i in self.data["items"] if i["store"] != store] + items
            self.data["stores"][store] = {"updated": now_iso(), "count": len(items), "error": None, "source": "refresh",
                                          "first_read": first}
            self.save()

    def merge_store(self, store: str, items: list[dict]) -> int:
        """Add or update imported items without dropping ones from other imported pages."""
        with self.changing():
            first = self._stamp(store, items)
            merged = {i["key"]: i for i in self.data["items"] if i["store"] == store}
            merged.update({i["key"]: i for i in items})
            self.data["items"] = [i for i in self.data["items"] if i["store"] != store] + list(merged.values())
            self.data["stores"][store] = {"updated": now_iso(), "count": len(merged), "error": None, "source": "import",
                                          "first_read": first}
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
            kept = {i.get("thumbnail") for i in self.data["items"]}
        _forget_pictures(gone, kept)
        return len(gone)

    def clear_store(self, store: str, note: str) -> int:
        """Forget a store's items and their cached pictures (after signing out, so the next account on this
        computer never sees them). Downloaded files aren't touched. Returns how many items were removed."""
        with self.lock:
            gone = [i for i in self.data["items"] if i["store"] == store]
            self.data["items"] = [i for i in self.data["items"] if i["store"] != store]
            self.data["stores"][store] = {"updated": None, "count": 0, "error": note}
            self.save()
            kept = {i.get("thumbnail") for i in self.data["items"]}
        _forget_pictures(gone, kept)
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


def name_tokens(name: str) -> set[str]:
    """The words of a product's name that could be a tag: not too short, not a number, a version or a stopword."""
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name or "")
    return {t for t in re.findall(r"[^\W_]+", name.lower())
            if len(t) >= 2 and t not in STOPWORDS and not t.isdigit() and not re.fullmatch(r"v\d+[a-z]?", t)}


def common_words(names: list[str], min_count: int, max_share: float, block=frozenset()) -> list[set[str]]:
    """Suggested tags: for each name, its words that min_count or more of the names share (a plural counting as its
    singular), leaving out those most of them share (over max_share of ten or more) and those in block."""
    toks = [name_tokens(n) for n in names]
    df = Counter(t for ts in toks for t in ts)
    plural = {w: w[:-1] for w in df if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and w[:-1] in df}
    toks = [{plural.get(t, t) for t in ts} for ts in toks]
    df = Counter(t for ts in toks for t in ts)
    n = len(names)
    keep = {w for w, c in df.items() if c >= min_count and w not in block and (n < 10 or c / n <= max_share)}
    return [ts & keep for ts in toks]


def enrich(items: list[dict], tcfg: dict, tagdata: dict | None = None, apart=frozenset(), progress=None) -> list[dict]:
    """Add your tags, suggested tags (words shared by several names) and cross-store matches (apart: products you
    said aren't copies of anything, stack_by_picture). progress: called with how many are done (issue #200)."""
    tagdata = tagdata or TagStore.empty()
    block = {w.lower() for w in tcfg.get("blocklist", [])} | set(tagdata["hidden"]) | set(tagdata["tags"])
    suggestions = common_words([i["name"] for i in items], int(tcfg.get("min_count", 3)),
                               float(tcfg.get("max_share", 0.4)), block)

    groups: dict[str, list] = {}
    out = []
    matcher = TagMatcher(tagdata["tags"])
    for n, (i, ts) in enumerate(zip(items, suggestions), 1):
        if progress:
            progress(n)
        key = tag_key(i["store"], i["name"])
        mine = TagStore.tags_for(tagdata, key, i["name"], matcher)
        kind, known = product_type(tagdata, key, i["name"], mine, i.get("store_tags"))   # what it is (issue #223)
        e = {**i, "tag_key": key, "tags": mine, "suggested": sorted(ts - set(mine)),
             "also_in": [], "copy_keys": [], "match_key": _norm(i["name"]), "stack_key": "", "type": kind, "type_from": known,
             "your_note": tagdata.get("notes", {}).get(key, "")}   # (issue #304; "note" is a Local item's own)
        for k in ("creator_url", "url", "download_url", "page"):  # also covers lists saved by older versions
            e[k] = store_link(e["store"], e.get(k))
        e["thumbnail"] = safe_url(e.get("thumbnail"))
        e["files"] = [f for f in e.get("files", []) if store_link(e["store"], f.get("url"))]
        shop = payhip_shop_of(e) if e["store"] == "payhip" and not e["download_url"] else None
        if shop:   # why there's no Open on Payhip, and the shop to add for it
            e["payhip_shop"], e["payhip_shop_added"] = shop, bool(store_link("payhip", shop + "/"))
        out.append(e)
        groups.setdefault(e["match_key"], []).append(e)
    stack_by_picture(out, apart=apart)
    for g in groups.values():
        by_store: dict[str, set] = {}
        for e in g:
            by_store.setdefault(e["store"], set()).add(e["tag_key"])
        if len(by_store) > 1:   # (worked out once per store, not once per item: a common name can be on hundreds)
            others = {s: (sorted(o for o in by_store if o != s), sorted(k for o, ks in by_store.items() if o != s for k in ks))
                      for s in by_store}
            for e in g:
                e["also_in"], e["copy_keys"] = (list(v) for v in others[e["store"]])
    return out


# Only plain raster images are kept. SVG can carry script, so it's never fetched, cached or served.
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/avif": "avif"}


def fetch_thumbnail(key: str, lib: Library) -> tuple[bytes, str] | None:
    """Store images, fetched once with the right referrer and cached on disk."""
    found = lib.thumbnail_for(key)
    return fetch_picture(*found) if found else None


def fetch_picture(url: str, referer: str, hosts: tuple[str, ...] | None = None) -> tuple[bytes, str] | None:
    """A picture from a store's image host (an item's, or one a set remembers), fetched once with the store's
    referrer and cached on disk: (its bytes, its type), or None. Given hosts, only from those, redirects included."""
    h = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()
    for p in THUMB_DIR.glob(h + ".*"):
        ctype = next((t for t, e in IMAGE_TYPES.items() if e == p.suffix.lstrip(".")), None)
        if ctype:
            return p.read_bytes(), ctype
        p.unlink(missing_ok=True)  # e.g. an SVG saved by an older version
    got = fetch_public(url, {"Referer": referer, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"}, 15 * 1024 * 1024, hosts=hosts)
    if not got:
        return None
    data, ctype = got
    if ctype not in IMAGE_TYPES:
        return None
    ext = IMAGE_TYPES[ctype]
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    write_file_safely(THUMB_DIR / f"{h}.{ext}", data)
    return data, ctype


_PICTURE_HASHES: dict[str, tuple[int, int, str]] = {}   # saved picture's file name -> (size, modified, SHA-256)
_PICTURE_LOCK = storage.metadata_lock


def picture_hashes(urls) -> dict[str, str]:
    """The SHA-256 of each saved picture's bytes, by its address, for the pictures Hoard has saved (issue #111). Each
    file is read once, and again only if its size or modified time changes."""
    try:
        saved = {e.name.split(".", 1)[0]: e for e in os.scandir(THUMB_DIR) if e.is_file(follow_symlinks=False)}
    except OSError:
        return {}
    out = {}
    for url in set(urls):
        e = saved.get(hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest())
        if not e or e.name.rsplit(".", 1)[-1] not in IMAGE_TYPES.values():
            continue
        try:
            st = e.stat(follow_symlinks=False)
            with _PICTURE_LOCK:
                known = _PICTURE_HASHES.get(e.name)
            if known and known[:2] == (st.st_size, st.st_mtime_ns):
                out[url] = known[2]
                continue
            if st.st_size > 15 * 1024 * 1024:   # larger than Hoard saves
                continue
            digest = hashlib.sha256(Path(e.path).read_bytes()).hexdigest()
        except OSError:
            continue
        with _PICTURE_LOCK:
            _PICTURE_HASHES[e.name] = (st.st_size, st.st_mtime_ns, digest)
        out[url] = digest
    return out


PICTURE_LOOKS_FILE = "picture-looks.json"
MAX_LOOKS = 50_000
LOOK_DISTANCE = 10      # of 64 bits: two pictures closer than this look the same (a store re-saved it, say)
_LOOKS_CACHE: dict = {"at": None, "looks": {}}


def _looks_file() -> Path:
    """Where what Hoard worked out about each product picture (how it looks, to stack copies by) is kept."""
    from .paths import data_dir
    return data_dir() / PICTURE_LOOKS_FILE


def picture_looks() -> dict[str, str]:
    """How each saved picture looks, by its SHA-256: a 64-bit difference hash (16 hex digits) the pages work out
    from the picture as they show it, kept in picture-looks.json so it's worked out once. Read again only when
    the file changes."""
    path = _looks_file()
    try:
        st = storage.stat(path)
    except OSError:
        return {}
    stamp = (str(path), st.st_size, st.st_mtime_ns)
    if _LOOKS_CACHE["at"] == stamp:
        return _LOOKS_CACHE["looks"]
    try:
        raw = read_json_file(path, 8 * 1024 * 1024)
    except (DataFileError, OSError):
        raw = {}
    looks = {k: v for k, v in (raw.get("looks") if isinstance(raw, dict) and isinstance(raw.get("looks"), dict) else {}).items()
             if _is_hex(k, 64) and _is_hex(v, 16)}
    _LOOKS_CACHE.update(at=stamp, looks=looks)
    return looks


def save_picture_looks(new: dict) -> int:
    """Keep how these pictures look (from a page: SHA-256 -> difference hash). Returns how many are kept now."""
    with _PICTURE_LOCK:
        looks = dict(picture_looks())
        looks.update({k: v for k, v in new.items() if _is_hex(k, 64) and _is_hex(v, 16)})
        if len(looks) > MAX_LOOKS:   # the oldest go first (dicts keep their order)
            looks = dict(list(looks.items())[-MAX_LOOKS:])
        write_file_safely(_looks_file(), json.dumps({"looks": looks}))
        return len(looks)


def _is_hex(value, n: int) -> bool:
    """Is value n hexadecimal digits?"""
    return isinstance(value, str) and len(value) == n and all(c in "0123456789abcdef" for c in value)


def stack_name(name: str) -> str:
    """A product's name for stacking: without case, spacing, punctuation and 【store】 [labels], but with its
    numbers and (variants), so "Hair Pack 1" isn't "Hair Pack 2" and "Hoodie (Pink)" isn't "Hoodie (Blue)"."""
    s = unicodedata.normalize("NFKC", name or "").casefold()
    key = re.sub(r"[\W_]+", "", re.sub(r"【[^】]*】|\[[^\]]*\]", " ", s))
    return key if len(key) >= 4 else re.sub(r"[\W_]+", "", s)


def _maker(creator: str) -> str:
    """A creator's name as copies are matched by (letters and digits only, any case); blank for an unknown creator."""
    key = re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", creator or "").casefold())
    return "" if key in ("", "unknowncreator") else key


def _names_alike(a: str, b: str, enough: float = 0.8) -> bool:
    """Two stack names that are probably one product's: the same, or nearly (a word more or less), with the same
    numbers in them."""
    if a == b:
        return True
    if not a or not b or re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return False
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() >= enough


# words a store's listing adds around a product's name, not part of it (issue #217)
_FILLER = re.compile(r"\b(?:for vrchat|vrchat|vrc|assets?|unitypackage|unity package|free|ver|version|edition|new|updated?)\b")
_VERSION = re.compile(r"\bv\d+(?:\.\d+)*[a-z]?\b|\b\d+(?:\.\d+)+\b")   # v2, 1.0.3 (a plain number is the name's: Pack 2)


# what a [label] says that isn't the product (besides _FILLER and versions): what it runs on, and where it's sold
_LABEL_WORDS = re.compile(r"\b(?:pc|quest|android|ios|mobile|sale|3d|model|booth|gumroad|jinxxy|payhip|itch(?:\.io)?|unity)\b")
_LABEL_JA = re.compile(r"無料|想定|向け|対応|モデル|オリジナル|新作|セール")   # (free, made for, works with, model...)


def _label(m: re.Match) -> str:
    """A 【label】 or [label] in a name: gone when it only says what listings say ([Asset], 【VRChat】, [PC/Quest]),
    kept when it names anything else (the avatar it's for: 【Rusk】)."""
    inside = m.group(0)[1:-1]
    rest = _LABEL_WORDS.sub(" ", _FILLER.sub(" ", _VERSION.sub(" ", _LABEL_JA.sub(" ", inside))))
    return f" {inside} " if re.sub(r"[\W_]+", "", rest) else " "


def fuzzy_name(name: str) -> str:
    """A product's name with what listings add around it left out, to tell two stores' listings of it apart from
    other products (issue #217): no case, punctuation, emoji, labels that only say what listings say ([Asset],
    【VRChat】), versions (v2, 1.0.3), or words like VRChat, Asset or Free. Its other numbers stay, so "Hair Pack 1"
    isn't "Hair Pack 2"; and the avatar it's for stays ("for <base>", or 【Rusk】), as a hoodie for one avatar isn't
    the hoodie for another."""
    s = re.sub(r"【[^】]*】|\[[^\]]*\]", _label, unicodedata.normalize("NFKC", name or "").casefold())
    s = _FILLER.sub(" ", _VERSION.sub(" ", s))
    return re.sub(r"[\W_]+", "", s)


STACK_WHY = ("picture", "name", "look", "alike")   # why copies stack: the same picture, name, a look-alike picture, names alike


def stack_by_picture(items: list[dict], looks: dict | None = None, apart=frozenset()) -> None:
    """Give each item a stack_key: copies of one product show as one tile (issue #111), from any store. Copies are:

    - items with the same picture, byte for byte, when no other creator uses it (bought twice, or in versions);
    - items whose picture other creators use too (a store's stand-in, say, or a creator who renamed their shop)
      when their names are alike as well;
    - items with the same name by the same creator, on any store (bought on both);
    - items with the same name by creators named differently (one shop under two names) whose pictures look the
      same (picture_looks): the same picture saved again by another store isn't the same bytes.

    - items by the same creator on two stores whose names are alike once what listings add around a name is left
      out (fuzzy_name: "[Asset] Fox Tail v2" and "Fox Tail"), with the same numbers in them (issue #217).

    "Hair Pack 1" and "Hair Pack 2" stay apart unless they have the same picture. An item that might stack, once
    it's known how its picture looks, gets look_for: its picture's SHA-256, for the page to work out (save_picture_looks).
    An item with nothing to stack with gets "", as does one whose picture isn't saved yet unless its name and
    creator say it's a copy. Each item in a stack gets stack_why: why its stack's copies were put together (STACK_WHY).
    apart: product keys you said aren't copies of anything ("Not a copy"): they never stack."""
    looks = picture_looks() if looks is None else looks
    hashes = picture_hashes(i["thumbnail"] for i in items if i.get("thumbnail"))
    pic = [hashes.get(i.get("thumbnail") or "", "") for i in items]
    names = [stack_name(i.get("name") or "") for i in items]
    makers = [_maker(i.get("creator") or "") for i in items]
    kept_apart = [bool(apart) and (i.get("tag_key") or tag_key(str(i.get("store") or ""), i.get("name") or "")) in apart
                  for i in items]
    parent = list(range(len(items)))
    why: dict[int, set] = {}   # a stack's root -> why its copies were put together

    def find(x: int) -> int:
        """The group a product is in (the first product of it)."""
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int, reason: str = "picture") -> None:
        """Put two products in one group of copies, for this reason (unless you said either isn't a copy)."""
        if kept_apart[a] or kept_apart[b]:
            return
        ra, rb = find(a), find(b)
        if ra != rb:
            root, other = min(ra, rb), max(ra, rb)
            parent[other] = root
            why[root] = why.get(root, set()) | why.pop(other, set()) | {reason}

    by_pic: dict[str, list[int]] = {}
    for n, h in enumerate(pic):
        if h:
            by_pic.setdefault(h, []).append(n)
    for group in by_pic.values():
        if len({makers[n] for n in group}) == 1:
            for n in group[1:]:
                union(group[0], n)
        elif len(group) <= 200:   # (a stand-in on hundreds of items: those aren't copies of each other)
            for x, a in enumerate(group):
                for b in group[x + 1:]:
                    if _names_alike(names[a], names[b]):
                        union(a, b)
    by_name: dict[str, list[int]] = {}
    for n, k in enumerate(names):
        by_name.setdefault(k, []).append(n)
    look_for: set[int] = set()
    for k, group in by_name.items():
        if not k or len(group) < 2 or len(group) > 200:   # (no name: nothing says two are one product)
            continue
        first_by_maker: dict[str, int] = {}
        for n in group:
            if makers[n]:
                if makers[n] in first_by_maker:
                    union(first_by_maker[makers[n]], n, "name")
                else:
                    first_by_maker[makers[n]] = n
        for x, a in enumerate(group):
            for b in group[x + 1:]:
                if find(a) == find(b) or not (pic[a] and pic[b]) or makers[a] == makers[b]:
                    continue
                la, lb = looks.get(pic[a]), looks.get(pic[b])
                if la and lb:
                    if bin(int(la, 16) ^ int(lb, 16)).count("1") <= LOOK_DISTANCE:
                        union(a, b, "look")
                else:
                    look_for.update(n for n, known in ((a, la), (b, lb)) if not known)
    # issue #217: one creator's listings on two stores whose names are alike once what listings add is left out. Only
    # names starting alike are compared, a creator's few at a time, so a big library stays quick to read
    loose = [fuzzy_name(i.get("name") or "") for i in items]
    by_start: dict[tuple, list[int]] = {}
    for n, f in enumerate(loose):
        if makers[n] and len(f) >= 4:
            by_start.setdefault((makers[n], f[:4]), []).append(n)
    for group in by_start.values():
        if not 2 <= len(group) <= 60:
            continue
        for x, a in enumerate(group):
            for b in group[x + 1:]:
                if items[a].get("store") != items[b].get("store") and find(a) != find(b) \
                        and _names_alike(loose[a], loose[b], 0.86):
                    union(a, b, "alike")
    members: dict[int, list[int]] = {}
    for n in range(len(items)):
        members.setdefault(find(n), []).append(n)
    for root, group in members.items():
        key = ""
        if len(group) > 1:   # named by its copies, so it's the same from one read to the next
            key = hashlib.sha256("\n".join(sorted(items[n].get("key") or f"{items[n].get('store')}:{items[n].get('name')}"
                                                   for n in group)).encode()).hexdigest()[:24]
        for n in group:
            items[n]["stack_key"] = key
            items[n]["stack_why"] = [w for w in STACK_WHY if w in why.get(root, ())] if key else []
    for n in look_for:
        items[n]["look_for"] = pic[n]


STORE_TAG_PAGES = 40   # products' public pages read for their store's tags, at most, each time a store is read


_TAG_PAGE_FAILS: dict[str, int] = {}   # products whose page couldn't be read, and how often, this run: tried after the rest


def _pages_waiting(lib: "Library", store: str) -> list[tuple[str, str, bool]]:
    """The store's products whose own page is still to be read (key, its page, whether it was read before Hoard asked
    whether it's for adults): never read, or read before that, where the store says it there (Booth, Jinxxy)."""
    from .sets import product_link
    from .wishlists import ADULT_SAID_BY
    with lib.lock:
        return [(i["key"], link, "store_tags" in i) for i in lib.data["items"] if i["store"] == store
                and ("store_tags" not in i or (store in ADULT_SAID_BY and "adult" not in i))
                and (link := next((u for u in (i.get("page"), i.get("url")) if product_link(store, u)), None))]


def store_pages_waiting(lib: "Library", store: str) -> int:
    """How many of the store's products' pages are still to be read, not counting those that couldn't be read this
    run (they're tried again with the store's next refresh)."""
    from .wishlists import TAGGED_STORES
    if store not in TAGGED_STORES:
        return 0
    return sum(1 for key, _, _ in _pages_waiting(lib, store) if not _TAG_PAGE_FAILS.get(key))


def store_tags_from_pages(lib: "Library", store: str, fetch, progress=lambda m: None, delay: float = 0.0,
                          limit: int = STORE_TAG_PAGES) -> int:
    """Issue #206: the tags creators gave their products on Booth, Jinxxy and itch.io (wishlists.store_tags_in), read
    from each product's public page as anyone sees it, a few each time the store is read, until every product has
    been read once (each keeps "store_tags", empty when its page has none; and "adult", where its store says whether
    it's for adults: one read before Hoard kept that is read once more, after the rest). Only a product with a public page is read
    (one without, a Jinxxy item Hoard knows only by your inventory, waits until it has one). A page that couldn't be
    read is tried again next time, after those not tried yet, so a few gone for good never hold up the rest. Returns
    how many products' pages were read."""
    from .wishlists import ADULT_SAID_BY, TAGGED_STORES, LinkError, from_product_page
    if store not in TAGGED_STORES:
        return 0
    waiting = _pages_waiting(lib, store)
    # (those never read first, then those read before Hoard asked whether they're for adults; otherwise in the library's order)
    todo = [(k, link) for k, link, _ in sorted(waiting, key=lambda w: (w[2], _TAG_PAGE_FAILS.get(w[0], 0)))[:limit]]
    read: dict[str, list] = {}
    adult: dict[str, bool] = {}
    for n, (key, page) in enumerate(todo, 1):
        progress(f"The tags creators gave their products, {n} of {len(todo)}")
        try:
            got = from_product_page(page, fetch)
            read[key] = got.get("store_tags") or []
            adult[key] = got.get("adult") is True
        except LinkError as e:
            if "couldn't be read" not in str(e):   # (its page is there, and isn't a product's: nothing to read later)
                read[key] = []
            else:
                _TAG_PAGE_FAILS[key] = _TAG_PAGE_FAILS.get(key, 0) + 1
        except Exception as e:   # (anything else leaves it to try again next time)
            _TAG_PAGE_FAILS[key] = _TAG_PAGE_FAILS.get(key, 0) + 1
            print(f"Couldn't read the store's tags for {key!r}: {str(e)[:200]}", flush=True)
        if n < len(todo):
            pause(delay)
    if read:
        with lib.lock:
            for i in lib.data["items"]:
                if i["key"] in read:
                    i["store_tags"] = item(i["store"], i["id"], store_tags=read[i["key"]])["store_tags"]
                    if store in ADULT_SAID_BY:   # (read: not asked again, whatever the answer)
                        i["adult"] = adult.get(i["key"], False)
            lib.save()
    return len(read)


def unreachable_message(store: str, what: str = "refreshed", error: BaseException | None = None) -> str:
    """What to tell you when a store's website can't be reached (error: why, when it's known: something on this
    computer refusing the connection is said as that, net.blocked_message)."""
    host = STORE_HOSTS[store].replace("accounts.", "").replace("app.", "")
    if error is not None and blocked_here(error):
        return blocked_message(host.replace("api.", ""))
    return (f"Couldn't reach {host}, so {STORES[store]['label']} wasn't {what}. You may be offline, or the store may "
            "be down. Your saved list is unchanged; try again when you're connected.")


def cache_images(lib: "Library", keys: list[str], progress, stop=lambda: False) -> int:
    """Fetch and keep the images for these items, so they show without a connection. Returns how many are saved.
    stop: when it says so, the rest are left (Force stop)."""
    keys = [k for k in keys if lib.thumbnail_for(k)]
    done = saved = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for got in pool.map(lambda k: None if stop() else fetch_thumbnail(k, lib), keys):
            done += 1
            saved += bool(got)
            if done % 10 == 0 or done == len(keys):
                progress(f"Saving images for offline use: {done} of {len(keys)}")
    return saved


def public_pages(path: Path | None = None) -> dict[str, str]:
    """Each product in library.json that has a public page (its own, else its link when that's public, else its
    creator's, as a set links it: hoard/sets.py), by its link and by its tag key: for the catalog's downloads
    (hoard/downloader.py), whose own link is often the buyer's (Jinxxy's inventory, a Gumroad download page). A
    list Hoard didn't write here (edited, or another computer's) gives none, as Library hides its links; so does one
    that can't be read, which is left as it is for Library to deal with."""
    from .paths import LIBRARY_FILE
    from .sets import product_link
    path = path or LIBRARY_FILE
    try:
        raw = read_json_file(path, 256 * 1024 * 1024)
    except (DataFileError, OSError, ValueError):
        return {}
    if check_seal(raw, path) in ("changed", "foreign"):
        return {}
    found: dict[str, str] = {}
    for i in Library.sanitize(raw)["items"]:
        page = next((u for u in (product_link(i["store"], i.get(k)) for k in ("page", "url", "creator_url")) if u), None)
        if page:
            if i.get("url"):
                found.setdefault(i["url"], page)
            found.setdefault(tag_key(i["store"], i["name"]), page)
    return found
