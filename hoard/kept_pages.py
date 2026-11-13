"""The page a store read couldn't use, kept for a support report: its shape, never its words.

When a store's library can't be read (its page isn't what the reader knows) or comes back empty, Hoard opens the
library page again straight away, in the same browser, and keeps its shape: every tag, class and id as the store wrote
them, and every word, number, address and value replaced, so nothing in it says what you bought or who you are. What
the reader found there is kept beside it as counts. It's kept in Hoard's own folder, one page per store, until that
store reads fine again or you sign out of it, and Create report puts it in the report, its start shown in the
report's preview. Nothing is sent anywhere: the report is a file you choose to share.
"""
from __future__ import annotations

import json
import os
import re
import time
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from . import __version__
from .paths import data_dir
from .safety import write_file_safely

MAX_PAGE = 3_000_000    # characters of a page's shape kept; the rest is cut (a store's library page is far less)
CAPTURE_SECONDS = 30    # the most a capture waits for the page to load
PROBLEMS = ("layout", "empty")   # a read that failed on the page itself: not signing in, a block, or the network

# Attributes whose values are the store's own structure, kept (digits aside) while they're plain names: what a reader
# looks for. One holding anything else (JSON, an address, words of yours) is blanked like any other.
STRUCTURE = {"class", "id", "role", "type", "rel", "name", "lang", "dir", "for", "method", "target", "hidden",
             "disabled", "checked", "selected", "colspan", "rowspan", "tabindex", "loading", "decoding", "charset",
             "http-equiv", "aria-hidden", "aria-expanded", "aria-selected", "aria-current", "aria-haspopup",
             "data-page", "data-testid", "data-test", "data-test-id", "data-component-name", "data-controller",
             "data-action", "data-target", "data-state", "data-orientation", "data-side"}
_PLAIN = re.compile(r"[A-Za-z0-9_ :./#-]{0,200}", re.A)   # a structural value: names, never words of yours
# Attributes holding an address: its site is kept when it's a store's, and its path where it's the store's words.
ADDRESSES = {"href", "src", "action", "formaction", "poster", "cite", "background", "data-src", "data-href", "data-url"}
# The words of a store's addresses that say what a page is (never what you bought): kept in an address's path.
PATH_WORDS = {"library", "items", "item", "l", "d", "s", "r", "gifts", "gift", "b-account", "account", "accounts",
              "orders", "order", "purchases", "purchase", "products", "product", "inventory", "downloads", "download",
              "wishlists", "wishlist", "collections", "collection", "settings", "login", "logout", "sign_in", "signin",
              "users", "user", "u", "api", "assets", "asset", "files", "file", "shop", "shops", "creator", "creators",
              "en", "ja", "ko", "zh-cn", "zh-tw", "library.json", "product_files.json", "images", "img", "static",
              "cdn", "public", "uploads", "thumbnails", "c", "p", "b", "a"}
JSON_TYPES = {"application/json", "application/ld+json"}
_TAKEN = (".html", ".json")


def blank(text: str) -> str:
    """Text with every letter (in any script) made x and every digit 0; spaces and punctuation as they were."""
    return "".join("0" if c.isdigit() else "x" if c.isalpha() or (ord(c) > 127 and not c.isspace()) else c
                   for c in text)


IMAGE_SITES = ("pximg.net",)   # where a store's pictures come from (Booth's), named in its pages' addresses too
# The stores' own services, kept by name. A creator's shop is a site of its own on some stores (<shop>.booth.pm,
# <creator>.gumroad.com, <creator>.itch.io, <shop>.payhip.com), which says whose shop it is: that part is blanked.
STORE_HOSTS = {"booth.pm", "www.booth.pm", "accounts.booth.pm", "manage.booth.pm", "checkout.booth.pm",
               "booth.pximg.net", "s.pximg.net", "i.pximg.net", "pixiv.net", "www.pixiv.net", "accounts.pixiv.net",
               "gumroad.com", "www.gumroad.com", "app.gumroad.com", "api.gumroad.com", "assets.gumroad.com",
               "public-files.gumroad.com", "files.gumroad.com", "jinxxy.com", "www.jinxxy.com", "api.jinxxy.com",
               "cdn.jinxxy.com", "payhip.com", "www.payhip.com", "itch.io", "www.itch.io", "api.itch.io"}


def _store_sites() -> list[str]:
    """The stores' own sites (and their sign-in and picture sites)."""
    from .browser import STORE_SITES
    return [site for sites in STORE_SITES.values() for site in sites] + list(IMAGE_SITES)


def _host(host: str) -> str:
    """An address's site: a store's own service kept (it says which store the page is from); a creator's shop on a
    store kept to the store's part (xxxxx.booth.pm: whose shop it is would say what you bought); any other blanked."""
    host = host.lower()
    if host in STORE_HOSTS:
        return host
    site = next((s for s in _store_sites() if host.endswith("." + s)), None)
    return blank(host[:-len(site) - 1]) + "." + site if site else blank(host)


def _name(key: str) -> str:
    """A key of the store's (a JSON key, a query's name): kept while it's a plain name (snake_case, kebab-case or
    camelCase), digits made 0; anything else (an address, an email, a token) blanked."""
    if len(key) <= 30 and re.fullmatch(r"[a-z][a-z0-9_]*(?:[-.][a-z0-9_]+)*|[a-z]+(?:[A-Z][a-z]+)*[0-9]*", key):
        return blank_digits(key)
    return blank(key)


def address(value: str) -> str:
    """An address with only the store's structure left: its scheme, a store's site, the path's words that say what
    the page is, and its query's names; every other part (ids, names, values) blanked, and no fragment."""
    value = value.strip()
    if not value:
        return value
    if re.match(r"^(javascript|data|blob|mailto|tel):", value, re.I):
        return value.split(":", 1)[0].lower() + ":x"
    try:
        parts = urlsplit(value)
    except ValueError:
        return blank(value)
    out = f"{parts.scheme}://{_host(parts.hostname or '')}" if parts.netloc else ""
    path = "/".join(seg if seg.lower() in PATH_WORDS or not seg else blank(seg) for seg in parts.path.split("/"))
    out += path
    if parts.query:
        out += "?" + "&".join(f"{_name(k)}={blank(v)}" if v else _name(k)
                              for k, v in parse_qsl(parts.query, keep_blank_values=True))
    return out


def blank_digits(text: str) -> str:
    """Text with its digits made 0 (an id or class can carry a number that's yours: an account's, an order's)."""
    return re.sub(r"\d", "0", text)


def _blank_json(value):
    """JSON with every string blanked and every number 0; its keys kept while they're plain names (the store's
    names for things: see _name)."""
    if isinstance(value, dict):
        out = {}
        for key, inner in value.items():
            name = _name(str(key))
            while name in out:   # (keys that differed only in their digits)
                name += "#"
            out[name] = _blank_json(inner)
        return out
    if isinstance(value, list):
        return [_blank_json(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return 0
    return blank(str(value))


def _json_or_none(text: str):
    """The JSON in text, or None when it isn't JSON."""
    text = text.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


class _Shaper(HTMLParser):
    """Writes a page again with its structure and none of its words (see shape)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.inside: list[tuple[str, str]] = []   # the script or style being read: (its tag, its type)
        self.size = 0

    def _put(self, text: str) -> None:
        """Add to the page being written."""
        self.out.append(text)
        self.size += len(text)

    def _attrs(self, attrs) -> str:
        """A tag's attributes as the shape has them: the store's own values kept, addresses kept to their structure,
        every other value blanked."""
        said = []
        for name, value in attrs:
            name = name.lower()
            if value is None:
                said.append(f" {name}")
                continue
            found = _json_or_none(value) if name not in ADDRESSES else None
            if found is not None:   # (JSON in any attribute: Inertia's data-page holds the whole page's data)
                kept = json.dumps(_blank_json(found), ensure_ascii=False)
            elif name in STRUCTURE:
                kept = blank_digits(value) if _PLAIN.fullmatch(value) and "@" not in value else blank(value)
            elif name in ADDRESSES:
                kept = address(value)
            elif name == "srcset":
                kept = ", ".join(address(part.strip().split(" ", 1)[0]) for part in value.split(",") if part.strip())
            elif name == "style":
                kept = "x"
            else:
                kept = blank(value)
            said.append(f' {name}="{escape(kept, quote=True)}"')
        return "".join(said)

    def handle_starttag(self, tag, attrs):
        """A tag opening (a script or style is noted, so what's inside it is left out)."""
        if tag in ("script", "style"):
            kind = next((v or "" for n, v in attrs if n.lower() == "type"), "").lower()
            self.inside.append((tag, kind))
        self._put(f"<{tag}{self._attrs(attrs)}>")

    def handle_startendtag(self, tag, attrs):
        """A tag that closes itself."""
        self._put(f"<{tag}{self._attrs(attrs)}/>")

    def handle_endtag(self, tag):
        """A tag closing."""
        if self.inside and self.inside[-1][0] == tag:
            self.inside.pop()
        self._put(f"</{tag}>")

    def handle_data(self, data):
        """Text: blanked; a script's JSON kept to its keys, any other script or style left out."""
        if self.inside:
            tag, kind = self.inside[-1]
            if tag == "style":
                self._put("/* its style */")
                return
            found = _json_or_none(data)
            if found is not None and (kind in JSON_TYPES or not kind or kind == "text/javascript"):
                self._put(json.dumps(_blank_json(found), ensure_ascii=False))
            elif data.strip():
                self._put("/* its script */")
            return
        self._put(escape(blank(data), quote=False))

    def handle_decl(self, decl):
        """The page's doctype, kept."""
        if decl.lower().startswith("doctype"):
            self._put(f"<!{decl}>")

    def handle_comment(self, data):
        """A comment: left out (a page's comments can name you)."""
        return

    def unknown_decl(self, data):
        """Anything else declared (CDATA and the like): left out."""
        return


def shape(html: str) -> str:
    """The page with its structure and none of its words: tags, classes, ids and the store's own attribute values
    kept (digits made 0); every text, value and data attribute blanked (letters x, digits 0); addresses kept to the
    store's site and the words of its paths; JSON kept to its keys; scripts and styles left out; at most MAX_PAGE
    characters."""
    shaper = _Shaper()
    shaper.feed(html)
    shaper.close()
    text = "".join(shaper.out)
    return text if len(text) <= MAX_PAGE else text[:MAX_PAGE] + "\n<!-- cut here: the rest of the page was longer -->"


# ----------------------------------------------------------------------------- kept pages

def folder() -> Path:
    """Where the pages are kept: one store's page and what was found on it, in Hoard's own folder."""
    return data_dir() / "store-pages"


def _path(store: str, ext: str) -> Path:
    """A store's kept file; only a store's name (letters) is one, so it's never a file outside the folder."""
    if not re.fullmatch(r"[a-z]{2,20}", store or ""):
        raise ValueError("not a store")
    return folder() / f"{store}{ext}"


def keep(store: str, html: str, problem: str, page_address: str = "", found: dict | None = None) -> None:
    """Keep a store's page (its shape: shape) and what the reader found there, for a report."""
    folder().mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(folder(), 0o700)
    info = {"store": store, "problem": problem if problem in PROBLEMS else "layout",
            "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hoard": __version__,
            "address": address(page_address), "page_characters": len(html), "found": found or {}}
    write_file_safely(_path(store, ".html"), shape(html))
    write_file_safely(_path(store, ".json"), json.dumps(info, ensure_ascii=False, indent=2))


def forget(store: str) -> None:
    """Delete a store's kept page (it read fine, or you signed out of it)."""
    for ext in _TAKEN:
        try:
            _path(store, ext).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


def kept(store: str | None = None) -> list[tuple[dict, str]]:
    """The pages kept, as (what was found, the page's shape): one store's, or every store's."""
    out = []
    names = [store] if store else sorted({p.stem for p in folder().glob("*.json")}) if folder().is_dir() else []
    for name in names:
        try:
            info = json.loads(_path(name, ".json").read_text("utf-8"))
            page = _path(name, ".html").read_text("utf-8")
        except (OSError, ValueError):
            continue
        if isinstance(info, dict):
            out.append((info, page))
    return out


# ----------------------------------------------------------------------------- reading the page again

def library_address(cfg: dict, store: str) -> str | None:
    """The page a store's library is read from (Payhip's: the first shop's), or None for one read another way."""
    from .config import payhip_shops
    from .library import GR_LIBRARY, JX_INVENTORY
    if store == "payhip":
        shops = payhip_shops(cfg)
        return shops[0] + "/b-account" if shops else None
    return {"booth": "https://accounts.booth.pm/library", "gumroad": GR_LIBRARY, "jinxxy": JX_INVENTORY}.get(store)


def reader_summary(parsed) -> dict:
    """What the reader found, without the purchases themselves: how many items, and how often each field was filled."""
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        items = parsed.get("cards") or parsed.get("items") or []
    else:
        items = []
    fields: dict = {}
    for item in items:
        for k, v in (item.items() if isinstance(item, dict) else ()):
            fields[k] = fields.get(k, 0) + (1 if v not in (None, "", [], {}) else 0)
    files = sum(len(i.get("files") or []) for i in items if isinstance(i, dict))
    return {"items": len(items), "fields_filled": fields, **({"files": files} if files else {})}


def open_library(page, cfg: dict, store: str, patient: bool = True, timeout: float | None = None) -> None:
    """Open a store's library page in a tab and let it finish, scrolled once for what loads as it's scrolled to.
    patient: wait for the network to go quiet (the debug command); otherwise for the page's load, at most 10 s."""
    from .browser import settle
    page.goto(library_address(cfg, store) or "https://payhip.com/", wait_until="domcontentloaded",
              **({"timeout": timeout * 1000} if timeout else {}))
    if patient:
        settle(page, 2000)
    else:
        try:
            page.wait_for_load_state("load", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
    page.mouse.wheel(0, 4000)
    page.wait_for_timeout(1500 if patient else 1000)


def read_found(page, cfg: dict, store: str):
    """What the store's reader finds on the page open now, as it finds it (its purchases: never kept or shared as
    they are), or None for Gumroad, whose library is read from the page's data rather than its layout."""
    from .library import BOOTH_JS, JX_CARDS_JS, PAYHIP_SHOP_JS
    js = {"booth": BOOTH_JS, "payhip": PAYHIP_SHOP_JS}.get(store)
    if js:
        return page.evaluate(js)
    if store == "jinxxy":
        return page.evaluate(JX_CARDS_JS, cfg["jinxxy"]["item_link_pattern"])
    return None


def read_page(page, cfg: dict, store: str) -> dict:
    """What the reader finds on the store's page open now: a summary (reader_summary), never the purchases."""
    from .library import extract_page_json
    if store != "gumroad":
        return reader_summary(read_found(page, cfg, store))
    data = extract_page_json(page.content())
    return {"page_data": data is not None,
            "page_data_keys": sorted(_name(str(k)) for k in data)[:40] if isinstance(data, dict) else []}


def browser_trouble(error: BaseException | None) -> bool:
    """Did a read fail because the browser stopped answering or closed (not because of the page)? Then reading the
    page again would only wait on it too."""
    if error is None:
        return False
    said = f"{type(error).__name__} {error}".lower()
    return any(w in said for w in ("timeout", "has been closed", "target closed", "connection closed",
                                   "browser closed", "crashed"))


def capture(ctx, cfg: dict, store: str, problem: str, error: BaseException | None = None) -> bool:
    """After a read failed on the page itself: open the store's library page again in its browser and keep its shape,
    and, for a read that came back empty, what the reader finds on it (one that failed on the page isn't run again).
    Not after the browser stopped answering. Best effort, within CAPTURE_SECONDS or so: True when it was kept."""
    if ctx is None or not library_address(cfg, store) or problem not in PROBLEMS or browser_trouble(error):
        return False
    page = None
    try:
        page = ctx.new_page()
        page.set_default_timeout(CAPTURE_SECONDS * 1000)   # (each wait on the page: its load, its content)
        open_library(page, cfg, store, patient=False, timeout=CAPTURE_SECONDS)
        if problem == "empty":
            try:
                found = read_page(page, cfg, store)
            except Exception as e:   # (the reader's own script failing on it is worth knowing too)
                found = {"reader_failed": type(e).__name__}
        else:
            found = {"reader": "failed on this page"}
        keep(store, page.content(), problem, page.url, found)
        return True
    except Exception as e:
        print(f"Couldn't keep {store}'s page for a report ({type(e).__name__}).", flush=True)
        return False
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
