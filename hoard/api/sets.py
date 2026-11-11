"""Sets endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

from .. import server as app
from .routing import Route


def _sets_view(self) -> dict:
    """Every set, for the Sets tab: each product with what it is here: in your library (owned), downloaded (its
    download's id), or neither (where to buy it), with a picture to show for it. Hidden products are left out
    while the hidden library is locked."""
    srv = self.server
    marks, unlocked = app.MarkStore().view(), self._unlocked()
    hidden = set() if unlocked else set(marks["hidden"])
    lib = {}
    for i in srv.lib.snapshot()[0]:
        lib.setdefault(app.tag_key(i["store"], i["name"]), i)
    dl = {}
    for a in srv.index(stale_ok=True)["assets"]:
        dl.setdefault(a["tag_key"], a)
    from .. import adult
    mine = app.TagStore().load()["items"]
    out, left_out = [], False
    for s in app.sets.SetStore().load()["sets"]:
        known, rows = s.get("products") or {}, []
        for n, key in enumerate(s["items"]):
            if key in hidden:
                left_out = True
                continue
            i, a, p = lib.get(key), dl.get(key), known.get(key) or {}
            store = (i or {}).get("store") or p.get("store") or (str(a["store"]).lower() if a else "")
            if i and i.get("thumbnail"):
                pic = "/thumb/" + app.quote(i["key"], safe=":")
            elif a and a.get("thumb"):
                pic = "/files/" + app.quote(a["thumb"]) + (f"?v={a['thumb_v']}" if a.get("thumb_v") else "")
            elif p.get("thumbnail"):   # (with the product it's for: a place in the list is another's once one goes)
                pic = f"/setpic/{s['id']}/{n}?p={app.pic_for(key)}"
            else:
                pic = None
            mark = ("removed" if key in marks["removed"] else "hidden" if key in marks["hidden"]
                    else "archived" if key in marks["archived"] else None)
            rows.append({"key": key, "store": store,
                         "name": (i or a or p).get("name") or key.split(":", 1)[-1],
                         "creator": (i or a or p).get("creator") or "",
                         "url": (i or {}).get("url") or p.get("url") or (a or {}).get("url"),
                         "pic": pic, "owned": bool(i), "lib": (i or {}).get("key"), "download": a["id"] if a else None,
                         "local": store == "local", "mark": mark,
                         # for adults (hoard/adult.py): as its store, tags or you say, or whoever shared the set
                         "adult": bool(adult.why(key, name=(i or a or p).get("name") or "", marks=marks,
                                                 tags=[*((i or {}).get("store_tags") or []), *mine.get(key, [])],
                                                 flagged=(i or {}).get("adult") is True or p.get("adult") is True)),
                         **{k: p[k] for k in ("price", "was", "elsewhere") if p.get(k)}})   # on a wishlist: what it
                                                                                            # costs, and its page elsewhere
        if s.get("kind") == "wishlist":   # suggested tags, from words its products' names share, to narrow it down
            block = {str(w).lower() for w in (srv.cfg.get("tags") or {}).get("blocklist", [])}
            for row, words in zip(rows, app.common_words([r["name"] for r in rows], 2, 0.5, block)):
                row["words"] = sorted(words)
        out.append({"id": s["id"], "name": s["name"], "note": s.get("note", ""), "photos": s.get("photos", []),
                    # where its products are on its photos (issue #346), only those shown
                    "marks": {u: [m for m in ms if m[0] not in hidden] for u, ms in (s.get("marks") or {}).items()},
                    "photo_p": [app.pic_for(u) for u in s.get("photos", [])],   # (each photo's address mark: /setphoto)
                    "cover": f"/setcover/{s['id']}/{s['picture']}" if app.sets.picture_file(s) else None,
                    "short": (s.get("short") or {}).get("expires"), "short_ended": s.get("short_ended"),
                    "items": rows, "from_link": s.get("from_link") is True,
                    "adult": any(r["adult"] for r in rows),   # an Adult set, while any product in it is (issue #337)
                    **({"kind": "wishlist", "source": s.get("source"), "read": s.get("read")} if s.get("kind") == "wishlist" else {})})
    return {"sets": out, "hidden_left_out": left_out, "viewer": app.sets.VIEWER, "photo_hosts": list(app.sets.PHOTO_HOSTS)}


def _add_links(self, sid: str, links):
    """Products added to a wishlist by their store links (at most 30): each one's public page read
    (wishlists.from_product_page), what was added and what wasn't, and why. A set is made from what's in your
    library, so it isn't added to by link (issue #208)."""
    from .. import wishlists
    if not isinstance(links, list) or not links:
        return self._json({"error": "Paste a product's link."}, 400)
    found = next((x for x in app.sets.SetStore().load()["sets"] if x["id"] == sid), None)
    if not found:
        return self._json({"error": "That set isn't there anymore."}, 404)
    if found.get("kind") != "wishlist":
        return self._json({"error": "Products are added by link to wishlists. A set is made from what's in your library."}, 400)
    got, said = [], []
    for link in [str(x)[:2000] for x in links[:30]]:
        try:
            p = wishlists.from_product_page(link, app.read_store_page)
        except wishlists.LinkError as e:
            said.append({"link": link[:200], "error": str(e)})
            continue
        got.append(p)
        said.append({"link": link[:200], "added": p["name"]})
    try:
        if got:
            app.sets.SetStore().add_products(sid, got)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    self.server.start_worker("Updating Unity catalog", app.rebuild_catalog_quietly, self.server)
    return self._json({"ok": True, "links": said})


def _set_code(self, sid: str):
    """A set and its share code: (set, code, how many products are in it), or a Response saying why not. Hidden
    products and your own (Local) are never in one."""
    s = next((x for x in app.sets.SetStore().load()["sets"] if x["id"] == sid), None)
    if s is None:
        return self._json({"error": "That set isn't there anymore."}, 400)
    hidden = app.MarkStore().keys("hidden")
    code, count = app.sets.share_code({**s, "items": [k for k in s["items"] if k not in hidden]}, self._product_details())
    if not count:
        return self._json({"error": "There's nothing in this set to share: products of your own (Local) and "
                                    "hidden ones stay on this computer."}, 400)
    return s, code, count


@staticmethod
def _short_view(rec: dict | None, code: str) -> dict | None:
    """What the share dialog shows of a set's short link: its link and code, when it runs out, and whether the set
    has changed since."""
    if not rec:
        return None
    short = app.shortlinks.code(rec["id"], rec["key"])
    return {"link": app.sets.share_link(short), "code": short, "expires": rec["expires"],
            "changed": rec["made"] != app.sets.code_mark(code), "days": app.shortlinks.LIFETIME_DAYS}


def _share_set(self, sid: str):
    """A set's share code (hoard/sets.py), for the page to lock for its short link, and that link, if it has one.
    The code's own long link isn't offered: a set is shared only by a short link (issue #162)."""
    got = self._set_code(sid)
    if not isinstance(got, tuple):
        return got
    s, code, count = got
    fits, more = app.shortlinks.fits(code), {}
    if not fits:
        try:
            more = {"parts": len(self._share_parts(s))}
        except ValueError as e:   # a product too big on its own: no split makes it fit, so say so (issue #178)
            more = {"parts": 0, "why": str(e)}
    return self._json({"ok": True, "code": code, "count": count,
                       "left_out": len(s["items"]) - count, "short": self._short_view(s.get("short"), code),
                       "short_days": app.shortlinks.LIFETIME_DAYS, "fits": fits, **more})


def _share_parts(self, s: dict) -> list[list[str]]:
    """A set's products in parts that each fit a short link (sets.share_parts), hidden ones left out of the
    sizes, as they're left out of what's shared."""
    return app.sets.share_parts(s, self._product_details(), leave_out=app.MarkStore().keys("hidden"))


def _split_set(self, sid: str):
    """Split into...: a set too big for one short link, as new sets that each fit (sets.SetStore.split). The set
    stays as it is."""
    try:   # (its parts worked out under the sets' lock, from what it holds then: issue #179)
        data = app.sets.SetStore().split(sid, self._share_parts)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    self.server.start_worker("Updating Unity catalog", app.rebuild_catalog_quietly, self.server)   # (Unity's Import set)
    names = {x["id"]: x["name"] for x in data["sets"]}
    return self._json({"ok": True, "made": data["made"], "names": [names[i] for i in data["made"]]})


def _shorten_set(self, body: dict):
    """Make a set's short link, or update the set behind the one it has (hoard/shortlinks.py): {"id", "code" (the
    code the page locked: it has to be the set's code now), "key" (what it locked it with), "data" (the locked
    set)}. A set with a short link keeps it, with its key: the page locks the set with that key again."""
    sid = str(body.get("id", ""))
    got = self._set_code(sid)
    if not isinstance(got, tuple):
        return got
    s, code, _ = got
    if body.get("code") != code:
        return self._json({"error": "The set changed while it was being shared. Try again."}, 409)
    key, data, old = body.get("key"), body.get("data"), s.get("short")
    if not isinstance(key, str) or not app.shortlinks.KEY.fullmatch(key):
        return self._json({"error": "That short link can't be kept."}, 400)
    rec = None
    try:
        if old and old["key"] == key:
            try:
                rec = {**old, "expires": app.shortlinks.replace(old["id"], old["token"], data)}
            except app.shortlinks.Gone:
                pass   # (it ran out on the server first: a new one, with the same key)
        if rec is None:
            made = app.shortlinks.make(data)
            rec = {"id": made["id"], "key": key, "token": made["token"], "expires": made["expires"]}
    except app.shortlinks.ShortLinkError as e:
        return self._json({"error": str(e)}, 502)
    rec["made"] = app.sets.code_mark(code)
    try:
        app.sets.SetStore().set_short(sid, rec)
    except ValueError as e:   # (the set was deleted meanwhile: its new link goes too)
        try:
            app.shortlinks.delete(rec["id"], rec["token"])
        except app.shortlinks.ShortLinkError:
            pass
        return self._json({"error": str(e)}, 400)
    if old and old["id"] != rec["id"]:   # (a key that wasn't its link's: the old link goes)
        try:
            app.shortlinks.delete(old["id"], old["token"])
        except app.shortlinks.ShortLinkError:
            pass
    return self._json({"ok": True, "short": self._short_view(rec, code)})


def _unshorten_set(self, sid: str):
    """Delete a set's short link now: from the server, then from the set."""
    s = next((x for x in app.sets.SetStore().load()["sets"] if x["id"] == sid), None)
    if s is None:
        return self._json({"error": "That set isn't there anymore."}, 400)
    if s.get("short"):
        try:
            app.shortlinks.delete(s["short"]["id"], s["short"]["token"])
        except app.shortlinks.ShortLinkError as e:
            return self._json({"error": str(e)}, 502)
        try:
            app.sets.SetStore().set_short(sid, None)
        except ValueError:   # (the set was deleted meanwhile: its link is gone either way)
            pass
    return self._json({"ok": True})


def get_api_sets(self, path, body, query):
    """GET /api/sets. the Sets tab: every set, each product as it is here (hoard/sets.py)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json(self._sets_view(), compress=True)


def get_setpic(self, path, body, query):
    """GET /setpic/*. a set's product's picture, from its store, when it isn't in your library"""
    srv = self.server
    u = app.urlparse(self.path)
    sid, _, n = path[len("/setpic/"):].partition("/")
    s = next((x for x in app.sets.SetStore().load()["sets"] if x["id"] == sid), None)
    key = s["items"][int(n)] if s and n.isdigit() and int(n) < len(s["items"]) else None
    if key and app.parse_qs(u.query).get("p", [""])[0] != app.pic_for(key):
        key = None   # an address from before a product was taken out: that place is another product's now
    p = (s.get("products") or {}).get(key) if key else None
    hidden = key in app.MarkStore().keys("hidden") and not self._unlocked()
    url = app.sets.product_picture(p["store"], p.get("thumbnail")) if p and not hidden else None
    got = app.fetch_picture(url, app.STORES[p["store"]]["referer"]) if url and p["store"] in app.STORES else None
    if not got:
        return self._send(404, b"Not found", "text/plain")
    return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})


def get_setphoto(self, path, body, query):
    """GET /setphoto/*. one of a set's photos (/setphoto/<set id>/<n>?p=<its address' mark>), fetched from its photo
    site once and kept, for its page to show it with what's marked on it (issue #346): Hoard's pages load pictures only
    from Hoard. Only a set's own photos, on the photo sites a set allows (sets.photo_url), are fetched."""
    srv = self.server
    u = app.urlparse(self.path)
    sid, _, n = path[len("/setphoto/"):].partition("/")
    s = next((x for x in app.sets.SetStore().load()["sets"] if x["id"] == sid), None)
    photos = (s or {}).get("photos") or []
    url = app.sets.photo_url(photos[int(n)]) if n.isdigit() and int(n) < len(photos) else None
    if url and app.parse_qs(u.query).get("p", [""])[0] != app.pic_for(url):
        url = None   # an address from before the photos changed: that place is another photo's now
    got = app.fetch_picture(url, f"https://{app.urlparse(url).hostname}/") if url else None
    if not got:
        return self._send(404, b"Not found", "text/plain")
    return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})


def get_setcover(self, path, body, query):
    """GET /setcover/*. the picture you chose for a set's tile"""
    srv = self.server
    u = app.urlparse(self.path)
    sid, _, name = path[len("/setcover/"):].partition("/")
    s = next((x for x in app.sets.SetStore().load()["sets"] if x["id"] == sid), None)
    f = app.sets.picture_file(s) if s and s.get("picture") == name else None
    try:
        data = f.read_bytes() if f else None
    except OSError:
        data = None
    if not data:
        return self._send(404, b"Not found", "text/plain")
    return self._send(200, data, app.SERVED_IMAGE_TYPES["." + name.rsplit(".", 1)[1]],
                      {"Cache-Control": "max-age=86400"})


def post_api_sets(self, path, body, query):
    """POST /api/sets. the Sets tab, Library and Downloads: your sets (hoard/sets.py)"""
    srv = self.server
    u = app.urlparse(self.path)
    if body.get("action") in ("add", "remove", "create") and not self._unlocked():
        hidden = app.MarkStore().keys("hidden")   # a hidden product isn't added or taken out while it's locked
        body = {**body, "items": [k for k in body.get("items") or [] if k not in hidden]}
    if body.get("action") == "photos" and isinstance(body.get("photos"), list):   # a photo site's page: its picture
        try:
            body = {**body, "photos": [app.sets.photo_from_page(u, app.read_photo_page) if app.sets.photo_page(u) else u
                                       for u in body["photos"][:app.sets.MAX_PHOTOS + 1]]}
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
    if body.get("action") == "add-links":   # Add products by link: each product's public page, read
        return self._add_links(str(body.get("id", "")), body.get("links"))
    if body.get("action") == "share":
        return self._share_set(str(body.get("id", "")))
    if body.get("action") == "split":   # too big for one short link: sets of it that each fit
        return self._split_set(str(body.get("id", "")))
    if body.get("action") == "short":   # Make a short link, or update the one it has
        return self._shorten_set(body)
    if body.get("action") == "unshort":
        return self._unshorten_set(str(body.get("id", "")))
    if body.get("action") == "open-short":   # Add a shared set, from a short link: the page unlocks it
        try:
            return self._json({"ok": True, **app.shortlinks.fetch(body.get("short"))})
        except app.shortlinks.ShortLinkError as e:
            return self._json({"error": str(e)}, 404 if isinstance(e, app.shortlinks.Gone) else 502)
    gone = None
    if body.get("action") == "delete":   # its short link goes with it, once the set has
        gone = next((x for x in app.sets.SetStore().load()["sets"] if x["id"] == body.get("id")), None)
    try:
        data = app.sets.SetStore().change(body, self._product_details())
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    except OSError as e:   # (a set's picture that couldn't be saved)
        return self._json({"error": f"Couldn't save that: {e.strerror or e}."}, 500)
    kept_short = None
    if gone and gone.get("short"):   # (if the share server can be reached)
        try:
            app.shortlinks.delete(gone["short"]["id"], gone["short"]["token"])
        except app.shortlinks.ShortLinkError:
            kept_short = gone["short"]["expires"]   # (it runs out by itself)
    srv.start_worker("Updating Unity catalog", app.rebuild_catalog_quietly, srv)   # (Unity's Import set)
    return self._json({"ok": True, "made": data.get("made"), **({"kept_short": kept_short} if kept_short else {})})


def post_api_wishlists_read(self, path, body, query):
    """POST /api/wishlists/read. Read wishlists: each chosen store's, in its signed-in window (wishlists.py)"""
    srv = self.server
    u = app.urlparse(self.path)
    stores = [x for x in body.get("stores") or [] if x in app.wishlists.READERS] if isinstance(body.get("stores"), list) else []
    if not stores:
        return self._json({"error": "Choose the stores to read your wishlists from."}, 400)
    one = body.get("list")   # a quick refresh of one wishlist (issue #331): its store and its list's name on it
    if one is not None:
        if not isinstance(one, str) or not one.strip() or len(one) > 60 or len(stores) != 1:
            return self._json({"error": "Choose one wishlist to refresh."}, 400)
        started = srv.jobs.start("quick-wishlist", stores, only=app.wishlists.clean_text(one, 60))
        return self._json({"ok": bool(started), "started": started}, 202 if started else 409)
    started = srv.jobs.start("wishlists", stores)
    return self._json({"ok": bool(started), "started": started}, 202 if started else 409)


def post_api_wishlists_import(self, path, body, query):
    """POST /api/wishlists/import. wishlist pages saved from your own browser, read offline"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._import_wishlists(body)



METHODS = {'_sets_view': _sets_view, '_add_links': _add_links, '_set_code': _set_code, '_short_view': _short_view, '_share_set': _share_set, '_share_parts': _share_parts, '_split_set': _split_set, '_shorten_set': _shorten_set, '_unshorten_set': _unshorten_set}

ROUTES = [
    Route('GET', '/api/sets', get_api_sets, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/setpic/*', get_setpic, changes=False, auth='key', image_key=True, max_body=1048576, request=(), response='application/octet-stream'),
    Route('GET', '/setphoto/*', get_setphoto, changes=False, auth='key', image_key=True, max_body=1048576, request=(), response='application/octet-stream'),
    Route('GET', '/setcover/*', get_setcover, changes=False, auth='key', image_key=True, max_body=1048576, request=(), response='application/octet-stream'),
    Route('POST', '/api/sets', post_api_sets, changes=True, auth='key', image_key=False, max_body=1048576, request=(('action', 'string'), ('code', 'string'), ('data', 'string'), ('id', 'string'), ('items', 'array'), ('key', 'string'), ('links', 'array'), ('marks', 'array'), ('photo', 'string'), ('photos', 'array'), ('short', 'string')), response='object'),
    Route('POST', '/api/wishlists/read', post_api_wishlists_read, changes=True, auth='key', image_key=False, max_body=1048576, request=(('stores', 'array'), ('list', 'string')), response='object'),
    Route('POST', '/api/wishlists/import', post_api_wishlists_import, changes=True, auth='key', image_key=False, max_body=83886080, request=(('files', 'array'),), response='object'),
]
