"""hoard:// links (issue #396): a web page, a chat or another program asks Hoard to open something in it.

    hoard://                               bring Hoard to the front (hoard://open too)
    hoard://set/<code>                     Add a shared set..., with that set: a short link's S1.<id>.<key>, or a long
                                           H1.... code (as the website's set viewer and set maker show them)
    hoard://add?link=<a product's page>    Add products by link..., with that link, for a wishlist you choose
    hoard://product/<store>/<id>           that product's details in your library (or that it isn't in it)

Any web page can fire one (browsers ask you first), so a link is only ever untrusted words: each part is checked
here as Hoard checks a set code or a store link that's pasted, and nothing else is done with it. There are no file
paths, downloads or settings in a link, and Hoard's page adds or changes nothing until you confirm there. Hoard
never writes a link down, in its log or anywhere else: a short link's key is in it."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote

SCHEME = "hoard"
MAX_LINK = 300 * 1024   # a long set code (sets.MAX_CODE) and the words around it
_ID = re.compile(r"[A-Za-z0-9_.~=+-]{1,200}")   # a product's id in its store, as Hoard keys it (library.item)
ABOUT = ("Hoard links open a shared set, a product to add to a wishlist, or a product in your library.")


class Refused(ValueError):
    """A link Hoard won't open: why, in words for the page."""


def is_link(text) -> bool:
    """Whether a program's argument is a hoard:// link (its scheme, in any case), to be handed to Hoard."""
    return isinstance(text, str) and text[:len(SCHEME) + 1].lower() == SCHEME + ":"


def parse(url) -> dict:
    """What a hoard:// link asks for, checked: {"do": "show"}, {"do": "set", "code"}, {"do": "add", "link"} or
    {"do": "product", "key"}. Raises Refused for anything else, saying why."""
    if not is_link(url):
        raise Refused("That isn't a Hoard link.")
    if len(url) > MAX_LINK:
        raise Refused("That Hoard link is too long to be one.")
    rest = re.sub(r"\s+", "", url)[len(SCHEME) + 1:]
    rest = rest[2:] if rest.startswith("//") else rest
    rest = rest.split("#", 1)[0]   # (no part of a link has a #: a browser keeps what follows one to itself)
    path, _, query = rest.partition("?")
    parts = [unquote(p) for p in path.split("/") if p]
    what = parts[0].lower() if parts else ""
    if what in ("", "open") and len(parts) <= 1:
        return {"do": "show"}
    if what == "set" and len(parts) == 2:
        return {"do": "set", "code": _set_code(parts[1])}
    if what == "add" and len(parts) == 1:
        return {"do": "add", "link": _product_link(query)}
    if what == "product" and len(parts) == 3:
        return {"do": "product", "key": _product_key(parts[1], parts[2])}
    raise Refused("Hoard doesn't know what that link asks for. " + ABOUT)


def _set_code(code: str) -> str:
    """A shared set's code from a link: a short link's (S1.<id>.<key>, opened by the page with its key), or a long
    one, unpacked here as Add a shared set would (so a damaged one is said at once)."""
    from . import sets, shortlinks
    if shortlinks.CODE.fullmatch(code):
        return code
    if code.startswith(shortlinks.PREFIX):
        raise Refused("That link's short link is cut short, or has been changed: copy all of it, and try again.")
    if not code.startswith(sets.CODE_PREFIX):
        raise Refused("That link has no set in it. A set's code starts with H1. or S1.")
    try:
        sets.from_code(code)
    except ValueError as e:
        raise Refused(str(e)) from None
    return code


def _product_link(query: str) -> str:
    """The product's page an add link names (link=..., once), checked as Add products by link checks a pasted one."""
    from .wishlists import LinkError, product_page_link
    pairs = parse_qsl(query, keep_blank_values=True)
    links = [v for k, v in pairs if k == "link"]
    if len(links) != 1 or len(pairs) != 1:
        raise Refused("That link doesn't name one product to add. It needs ?link= and a product's page on a store.")
    try:
        return product_page_link(links[0])[1]
    except LinkError:
        raise Refused("That link's product isn't a product's page on Booth, Gumroad, Jinxxy, Payhip or itch.io.") from None


def _product_key(store: str, id_: str) -> str:
    """A product's key in the library ("<store>:<id>"), from a link's store and id."""
    from .library import STORES
    store = store.lower()
    if store not in STORES or not _ID.fullmatch(id_):
        raise Refused("That link doesn't name a product on Booth, Gumroad, Jinxxy, Payhip or itch.io.")
    return f"{store}:{id_}"
