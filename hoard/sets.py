"""Sets (the Sets tab, Downloads, and Hoard for Unity's Import set): products you group to use together, such as an
avatar, its outfits and hair, and the shaders they need: downloaded or not, and yours or not yet (a set someone
shared with you lists what to buy, and where).

Kept in sets.json in Hoard's app-data folder: {"sets": [{"id", "name", "items": [product key, ...], "note"?,
"photos"?: [address, ...], "picture"?: "<version>.<png|jpg|webp>", "products"?: {product key: {"store", "id", "name",
"creator", "url", "thumbnail"}}, "short"?: {"id", "key", "token", "expires", "made"}}]}. A set's picture, if you chose one for its tile, is beside it in set-pictures/, as
"<set id>-<picture>" (a new name each time, so a page never shows the one it replaced). A
product is known by the same key your tags use (tags.tag_key), so a set keeps its products whichever store or library
folder they're in; "products" remembers what each was when it was added (its store page and picture), so a set can be
shown and shared whether or not it's in your library. catalog.json lists each set by its downloaded products' folders,
for Hoard for Unity. Every change re-reads the file under a lock.

A set is shared as a code (share_code): the set itself, packed into a link to the set viewer on Hoard's website
(VIEWER), after its "#", which a browser never sends anywhere. Nothing is uploaded: the viewer reads the code in the
page, and shows each product's picture from its store's own image host, and the sharer's photos from the photo sites
in PHOTO_HOSTS (links they made there). The same code, pasted into Hoard, adds the set (from_code).

A set can also have a short link (shortlinks.py): its code kept on Hoard's share server for 14 days, locked with a
key that's only in the link. "short" is that link's id and key, the token that lets this Hoard update or delete it,
when it runs out, and "made", which code it holds (code_mark), so the page can say when the set has changed since.
A short link that has run out is dropped when the file is read.
"""
from __future__ import annotations

import base64
import json
import re
import secrets
import hashlib
import threading
import time
import zlib
from pathlib import Path
from urllib.parse import urlparse

from .paths import data_dir
from .safety import STORE_LINK_SITES, DataFileError, chosen_picture, clean_text, read_json_file, write_file_safely
from .shortlinks import CODE as SHORT_CODE, ID as SHORT_ID, KEY as SHORT_KEY, PREFIX as SHORT_PREFIX, TOKEN as SHORT_TOKEN
from .tags import TAG_KEY_RX

MAX_SETS = 200
MAX_ITEMS = 500
NAME_LENGTH = 60
NOTE_LENGTH = 1000
MAX_PHOTOS = 8
MAX_URL = 600
VIEWER = "https://hoard.furryup.link/set.html"
CODE_PREFIX = "H1."
MAX_CODE = 256 * 1024             # characters of a code (a set of 500 products is well under it)
MAX_CODE_JSON = 1024 * 1024       # what a code may unpack to: a bomb stops here
STORES = tuple(STORE_LINK_SITES)  # the stores a shared product can be from (not Local: your own files stay yours)
# where store pictures come from: a shared product's picture is shown only from its store's own image host
STORE_IMAGE_HOSTS = {"booth": ("booth.pximg.net",), "gumroad": ("public-files.gumroad.com",),
                     "jinxxy": ("jinxxy-c.jinxxy-cdn.com",), "payhip": ("images.payhip.com",), "itch": ("img.itch.zone",)}
# the photo sites a sharer's own photos can be on (Hoard hosts nothing): links to pictures, https only
PHOTO_HOSTS = ("i.imgur.com", "i.gyazo.com", "pbs.twimg.com", "cdn.bsky.app", "i.redd.it", "i.postimg.cc", "i.ibb.co",
               "cdn.discordapp.com", "media.discordapp.net", "booth.pximg.net", "img.itch.zone",
               "public-files.gumroad.com")

PICTURE_NAME = re.compile(r"[0-9a-f]{8}\.(?:png|jpg|webp)")   # a set's "picture"
CODE_MARK = re.compile(r"[0-9a-f]{16}")                        # a short link's "made"
_lock = threading.Lock()


def sets_file() -> Path:
    return data_dir() / "sets.json"


def pictures_dir() -> Path:
    return data_dir() / "set-pictures"


def picture_file(s: dict) -> Path | None:
    """Where a set's own picture is, if it has one and it's there (a backup brings the set, not its picture)."""
    name = s.get("picture")
    if not (isinstance(name, str) and PICTURE_NAME.fullmatch(name)):
        return None
    f = pictures_dir() / f"{s['id']}-{name}"
    return f if f.is_file() and not f.is_symlink() else None


def _tidy_pictures(sets: list[dict]) -> None:
    """Delete the pictures no set has any more (replaced, taken off, or their set deleted)."""
    keep = {f"{s['id']}-{s['picture']}" for s in sets if s.get("picture")}
    try:
        found = list(pictures_dir().iterdir()) if pictures_dir().is_dir() else []
    except OSError:
        return
    for f in found:
        if f.name not in keep and re.fullmatch(r"[0-9A-Za-z]{1,16}-" + PICTURE_NAME.pattern, f.name) and f.is_file():
            f.unlink(missing_ok=True)


def clean_name(value) -> str:
    return clean_text(value, NAME_LENGTH) if isinstance(value, str) else ""


def _https_on(value, hosts) -> str | None:
    """value if it's a plain https address (no user name, no other port) on one of these hosts, else None."""
    if not isinstance(value, str) or len(value) > MAX_URL:
        return None
    try:
        u = urlparse(value.strip())
        port = u.port
    except ValueError:
        return None
    host = (u.hostname or "").rstrip(".").lower()
    if u.scheme != "https" or u.username or u.password or port not in (None, 443) or not host.isascii():
        return None
    return value.strip() if host in hosts else None


def photo_url(value) -> str | None:
    """A sharer's photo: an https link on one of the photo sites (PHOTO_HOSTS), or None."""
    return _https_on(value, PHOTO_HOSTS)


def product_picture(store, value) -> str | None:
    """A product's picture: an https address on its store's own image host, or None."""
    return _https_on(value, STORE_IMAGE_HOSTS.get(store, ())) if isinstance(store, str) else None


def clean_note(value) -> str:
    """A set's note: its lines, each made safe as a name is, at most 20 of them and NOTE_LENGTH characters."""
    if not isinstance(value, str):
        return ""
    lines = [clean_text(line, NOTE_LENGTH) for line in value.replace("\r\n", "\n").split("\n")[:20]]
    return "\n".join(lines).strip()[:NOTE_LENGTH].strip()


# Store sites' own parts, never a creator's: a library, an account, a checkout (Booth's accounts.booth.pm, Gumroad's
# app.gumroad.com, where your purchases are) and the like
_NOT_A_SHOP = {"www", "app", "accounts", "manage", "api", "assets", "help", "support", "checkout", "auth", "login"}
_JINXXY_NOT_A_CREATOR = {"my", "market", "api", "auth", "cart", "checkout", "about", "login", "signup", "settings",
                         "search", "help", "support", "feedback", "terms-of-service", "privacy-policy", "refund-policy",
                         "_next", "static", "admin"}
_SEGMENT = re.compile(r"[A-Za-z0-9_.~-]{1,120}")
_BOOTH_ITEM = re.compile(r"/(?:[a-z]{2}(?:-[a-z]+)?/)?items/\d{1,12}")


def product_link(store, value) -> str | None:
    """A product's public page on its store, or its creator's (https, without its query or anything after #), or
    None. Never a page of the buyer's own: a Gumroad purchase's link is its download page (gumroad.com/d/...),
    which opens its files for whoever has it; Jinxxy's is the buyer's inventory; an itch.io download page carries
    its key. Only the stores' own websites (not a site added on one computer), so a shared link is the same
    everywhere. site/set.js checks the same way."""
    if not isinstance(store, str) or store not in STORE_LINK_SITES or not isinstance(value, str) or len(value) > MAX_URL:
        return None
    try:
        u = urlparse(value.strip())
        port = u.port
    except ValueError:
        return None
    host = (u.hostname or "").rstrip(".").lower()
    if u.scheme != "https" or u.username or u.password or port not in (None, 443) or not host.isascii():
        return None
    path = u.path.rstrip("/")

    def shop(site: str) -> bool:   # <creator>.site, one level down, not one of the site's own
        name, _, rest = host.partition(".")
        return rest == site and re.fullmatch(r"[a-z0-9-]{1,63}", name) is not None and name not in _NOT_A_SHOP
    on = lambda site: host in (site, "www." + site)   # noqa: E731
    segs = path.split("/")[1:] if path else []
    if store == "booth":
        ok = (on("booth.pm") and _BOOTH_ITEM.fullmatch(path)) or (shop("booth.pm") and (not path or _BOOTH_ITEM.fullmatch(path)))
    elif store == "gumroad":
        ok = (on("gumroad.com") or shop("gumroad.com")) and re.fullmatch(r"/l/[A-Za-z0-9_-]{1,80}", path) or (shop("gumroad.com") and not path)
    elif store == "jinxxy":
        ok = (on("jinxxy.com") and 1 <= len(segs) <= 2 and all(_SEGMENT.fullmatch(x) for x in segs)
              and segs[0].lower() not in _JINXXY_NOT_A_CREATOR and (len(segs) == 1 or segs[1].lower() not in ("products", "lists", "posts")))
    elif store == "payhip":
        ok = on("payhip.com") and re.fullmatch(r"/b/[A-Za-z0-9]{1,20}", path)
    else:   # itch.io: a project's page, or its creator's
        ok = shop("itch.io") and (not path or re.fullmatch(r"/[A-Za-z0-9_-]{1,120}", path))
    return f"https://{host}{path}" if ok else None


def clean_product(p) -> dict | None:
    """What a set remembers of one product, checked: its store, id, name, creator, store page and picture."""
    if not isinstance(p, dict) or not isinstance(p.get("store"), str):
        return None
    store = p["store"].lower()
    if store not in STORES and store != "local":
        return None
    name = clean_text(p.get("name"), 300) if isinstance(p.get("name"), str) else ""
    if not name:
        return None
    out = {"store": store, "name": name}
    creator = clean_text(p.get("creator"), 200) if isinstance(p.get("creator"), str) else ""
    if creator:
        out["creator"] = creator
    if isinstance(p.get("id"), (str, int)) and re.fullmatch(r"[\w.-]{1,80}", str(p["id"])):
        out["id"] = str(p["id"])
    url, picture = product_link(store, p.get("url")), product_picture(store, p.get("thumbnail"))
    if url:
        out["url"] = url
    if picture:
        out["thumbnail"] = picture
    return out


def clean_short(rec) -> dict | None:
    """A set's short link as sets.json keeps it, every part checked; None for one that's damaged or has run out."""
    if not isinstance(rec, dict):
        return None
    sid, key, token, made, expires = (rec.get(k) for k in ("id", "key", "token", "made", "expires"))
    if not (isinstance(sid, str) and SHORT_ID.fullmatch(sid) and isinstance(key, str) and SHORT_KEY.fullmatch(key)
            and isinstance(token, str) and SHORT_TOKEN.fullmatch(token) and isinstance(made, str)
            and CODE_MARK.fullmatch(made) and isinstance(expires, int) and not isinstance(expires, bool)):
        return None
    return {"id": sid, "key": key, "token": token, "expires": expires, "made": made} if expires > time.time() else None


def code_mark(code: str) -> str:
    """Which code a short link holds, to tell whether the set has changed since (not the code itself)."""
    return hashlib.sha256(code.encode()).hexdigest()[:16]


class SetStore:
    def __init__(self, path: Path | None = None):
        self.path = path or sets_file()

    @staticmethod
    def sanitize(raw) -> dict:
        out = {"sets": []}
        seen = set()
        for s in (raw.get("sets") if isinstance(raw, dict) and isinstance(raw.get("sets"), list) else [])[:MAX_SETS]:
            if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not s["id"].isalnum() or len(s["id"]) > 16:
                continue
            name = clean_name(s.get("name"))
            if not name or s["id"] in seen:
                continue
            seen.add(s["id"])
            items = []
            for k in s.get("items") if isinstance(s.get("items"), list) else []:
                if isinstance(k, str) and TAG_KEY_RX.match(k) and k not in items:
                    items.append(k)
            one = {"id": s["id"], "name": name, "items": items[:MAX_ITEMS]}
            note = clean_note(s.get("note"))
            if note:
                one["note"] = note
            photos = list(dict.fromkeys(u for u in (photo_url(x) for x in (s.get("photos") or [])[:MAX_PHOTOS]
                                                    if isinstance(s.get("photos"), list)) if u))
            if photos:
                one["photos"] = photos
            if isinstance(s.get("picture"), str) and PICTURE_NAME.fullmatch(s["picture"]):
                one["picture"] = s["picture"]
            given = s.get("products") if isinstance(s.get("products"), dict) else {}
            products = {k: p for k, p in ((k, clean_product(given.get(k))) for k in one["items"]) if p}
            if products:
                one["products"] = products
            short = clean_short(s.get("short"))
            if short:
                one["short"] = short
            out["sets"].append(one)
        return out

    def load(self) -> dict:
        try:
            raw = read_json_file(self.path) if self.path.is_file() else {}
        except (DataFileError, OSError):
            raw = {}
        return self.sanitize(raw)

    def _save(self, data: dict) -> None:
        write_file_safely(self.path, json.dumps({"version": 1, **data}, ensure_ascii=False, indent=1))

    def change(self, body: dict, details=None) -> dict:
        """One change, from the page: {"action": "create", "name", "items"?, "note"?, "photos"?},
        {"action": "rename", "id", "name"}, {"action": "delete", "id"}, {"action": "add" or "remove", "id", "items"},
        {"action": "note", "id", "note"}, {"action": "photos", "id", "photos"}, {"action": "picture", "id", "image"}
        (a picture for its tile, as safety.chosen_picture takes it, or null to go back to its products' pictures),
        {"action": "import", "code"} (a set someone shared). details(key) gives what Hoard knows of a product added (clean_product's shape, or None), to
        keep with it. Returns the sets after it, and the new set's id for "create" and "import". Raises ValueError
        for one that can't be made."""
        action = body.get("action")
        details = details or (lambda key: None)
        with _lock:
            data = self.load()
            sets = data["sets"]
            items = [k for k in body.get("items", []) if isinstance(k, str) and TAG_KEY_RX.match(k)] \
                if isinstance(body.get("items"), list) else []
            made = None

            def remember(s: dict, keys) -> None:   # what each product added is, for showing and sharing the set
                known = s.setdefault("products", {})
                for k in keys:
                    p = clean_product(details(k))
                    if p:
                        known[k] = p
            if action in ("create", "import"):
                given = from_code(body.get("code")) if action == "import" else None
                name = clean_name(given["name"] if given else body.get("name"))
                if not name:
                    raise ValueError("Give the set a name.")
                if len(sets) >= MAX_SETS:
                    raise ValueError(f"Hoard keeps up to {MAX_SETS} sets.")
                if given:   # a name of yours stays yours: "Rusk, winter (2)"
                    taken, base, n = {x["name"] for x in sets}, name, 2
                    while name in taken:
                        name, n = clean_name(f"{base} ({n})"), n + 1
                made = secrets.token_hex(4)
                one = {"id": made, "name": name,
                       "items": list(dict.fromkeys(given["items"] if given else items))[:MAX_ITEMS]}
                if given:
                    one.update({k: given[k] for k in ("note", "photos", "products") if given.get(k)})
                else:
                    one.update(note=clean_note(body.get("note")), photos=body.get("photos") or [])
                    remember(one, one["items"])
                sets.append(one)
            else:
                s = next((s for s in sets if s["id"] == body.get("id")), None)
                if s is None:
                    raise ValueError("That set isn't there anymore.")
                if action == "rename":
                    name = clean_name(body.get("name"))
                    if not name:
                        raise ValueError("Give the set a name.")
                    s["name"] = name
                elif action == "delete":
                    sets.remove(s)
                elif action == "add":
                    s["items"] = list(dict.fromkeys(s["items"] + items))
                    if len(s["items"]) > MAX_ITEMS:
                        raise ValueError(f"A set holds up to {MAX_ITEMS} products.")
                    remember(s, items)
                elif action == "remove":
                    s["items"] = [k for k in s["items"] if k not in items]
                elif action == "note":
                    s["note"] = clean_note(body.get("note"))
                elif action == "photos":
                    given = body.get("photos") if isinstance(body.get("photos"), list) else []
                    if len(given) > MAX_PHOTOS:
                        raise ValueError(f"A set has up to {MAX_PHOTOS} photos.")
                    bad = [str(u)[:80] for u in given if not photo_url(u)]
                    if bad:
                        raise ValueError(f"{bad[0]} isn't a link to a picture on a photo site Hoard knows "
                                         f"({', '.join(PHOTO_HOSTS[:6])} and others).")
                    s["photos"] = given
                elif action == "picture":
                    s.pop("picture", None)
                    if body.get("image") is not None:
                        picture, kind = chosen_picture(body.get("image"))
                        s["picture"] = f"{secrets.token_hex(4)}.{kind}"
                        pictures_dir().mkdir(parents=True, exist_ok=True)
                        write_file_safely(pictures_dir() / f"{s['id']}-{s['picture']}", picture)
                else:
                    raise ValueError("Unknown change.")
            data = self.sanitize(data)   # (what was added, checked as a file read is: products of other keys go)
            self._save(data)
            if action in ("picture", "delete"):
                _tidy_pictures(data["sets"])
        return {**data, **({"made": made} if made else {})}

    def set_short(self, sid: str, rec: dict | None) -> None:
        """Keep a set's short link (clean_short's shape), or forget it (None). Not one of change()'s: only Hoard's
        server, which made the link, sets it."""
        with _lock:
            data = self.load()
            s = next((x for x in data["sets"] if x["id"] == sid), None)
            if s is None:
                raise ValueError("That set isn't there anymore.")
            s.pop("short", None)
            if rec is not None:
                s["short"] = clean_short(rec)
                if not s["short"]:
                    raise ValueError("That short link can't be kept.")
            self._save(data)


# ----------------------------------------------------------------------------- sharing a set

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def share_code(s: dict, details=None) -> tuple[str, int]:
    """A set as a code to share: CODE_PREFIX and its contents (name, note, photos, and each product's store, id,
    name, creator, store page and picture), packed. details(key) fills in what the set doesn't remember of a
    product. Products of your own (Local) aren't shared, and neither is one Hoard knows nothing about. Returns the
    code and how many products are in it."""
    details = details or (lambda key: None)
    known = s.get("products") or {}
    rows = []
    for k in s.get("items", []):
        remembered, now = clean_product(known.get(k)), clean_product(details(k))
        p = {**(now or {}), **(remembered or {})} if remembered or now else None   # (a link remembered from 4.2.0
        if not p or p["store"] not in STORES:                                        # was dropped: Hoard's, now)
            continue
        if now and now.get("url"):   # its page as Hoard knows it now: its own, once a refresh has found it, not
            p["url"] = now["url"]    # the creator's page remembered before then
        row = [p["store"], p.get("id", ""), p["name"], p.get("creator", ""), p.get("url", ""), p.get("thumbnail", "")]
        while row and row[-1] == "":   # (what's left out at the end costs nothing)
            row.pop()
        rows.append(row)
    doc = {"v": 1, "n": s.get("name", ""), "i": rows}
    if s.get("note"):
        doc["d"] = s["note"]
    if s.get("photos"):
        doc["p"] = s["photos"]
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)   # raw deflate: what a browser's DecompressionStream reads
    return CODE_PREFIX + _b64(packer.compress(raw) + packer.flush()), len(rows)


def share_link(code: str) -> str:
    return f"{VIEWER}#{code}"


def from_code(text) -> dict:
    """A shared set, from its code or a link with it: {"name", "note", "photos", "items": [product key, ...],
    "products": {key: product}}, every part checked as Hoard checks a set it reads from its own file. Raises
    ValueError for anything that isn't one."""
    from .tags import tag_key
    if not isinstance(text, str):
        raise ValueError("Paste a set's code, or its link.")
    text = text.strip()
    if "#" in text:
        text = text.split("#", 1)[1]
    text = re.sub(r"\s+", "", text)
    if text.startswith(SHORT_PREFIX):   # (Hoard's page opens a whole one itself, before it gets here)
        raise ValueError("That's a short link: open it with Add a shared set, in Hoard 4.3 or later."
                         if SHORT_CODE.fullmatch(text) else
                         "That short link is cut short, or has been changed: copy all of it, and try again.")
    if not text.startswith(CODE_PREFIX) or len(text) > MAX_CODE:
        raise ValueError("That isn't a Hoard set code. A set's code starts with H1.")
    body = text[len(CODE_PREFIX):]
    try:
        packed = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        unpacker = zlib.decompressobj(-15)
        raw = unpacker.decompress(packed, MAX_CODE_JSON + 1)
        if len(raw) > MAX_CODE_JSON or unpacker.unconsumed_tail:
            raise ValueError("too large")
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, zlib.error, UnicodeDecodeError, RecursionError):
        raise ValueError("That set code is damaged, or cut short: copy all of it, and try again.") from None
    if not isinstance(doc, dict) or doc.get("v") != 1 or not isinstance(doc.get("i"), list):
        raise ValueError("That set code was made by a newer Hoard, or isn't one. Update Hoard, then try again.")
    items, products = [], {}
    for row in doc["i"][:MAX_ITEMS]:
        if not isinstance(row, list):
            continue
        row = (row + ["", "", "", "", "", ""])[:6]
        p = clean_product({"store": row[0], "id": row[1] or None, "name": row[2], "creator": row[3], "url": row[4],
                           "thumbnail": row[5]})
        if not p or p["store"] not in STORES:
            continue
        key = tag_key(p["store"], p["name"])
        if key not in products:
            items.append(key)
            products[key] = p
    name = clean_name(doc.get("n")) or "A shared set"
    if not items:
        raise ValueError("That set code has no products in it.")
    photos = [u for u in (photo_url(x) for x in (doc.get("p") or [])[:MAX_PHOTOS]) if u] \
        if isinstance(doc.get("p"), list) else []
    return {"name": name, "note": clean_note(doc.get("d")), "photos": list(dict.fromkeys(photos)), "items": items,
            "products": products}


def for_catalog(catalog: list[dict], data: dict | None = None) -> list[dict]:
    """The sets as catalog.json lists them: [{"name", "items": [folder, ...]}], each product by its catalog folder
    (every copy of it, on every store), only products the catalog has, and only sets with any."""
    from .tags import tag_key
    data = data if data is not None else SetStore().load()
    folders: dict[str, list[str]] = {}
    for e in catalog:
        folders.setdefault(tag_key(e["store"], e["name"]), []).append(e["folder"])
    out = []
    for s in data["sets"]:
        items = [f for k in s["items"] for f in folders.get(k, [])]
        if items:
            out.append({"name": s["name"], "items": items})
    return out
