"""Library endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

from .. import server as app
from .routing import Route


def _library_folders(self, path: str, body: dict):
    """Add a library folder (one that's there, checked by libraries.check_new_folder), or forget one: its files
    stay where they are, and leave Hoard's library until it's added again. Not while a job runs, which may be
    using it."""
    srv = self.server
    if srv.jobs.state.get("running") or srv.jobs.state.get("queue"):
        return self._json({"error": "Wait for Hoard to finish what it's doing, then try again."}, 409)
    folders = [str(f) for f in app.libraries.other_folders(srv.cfg)]
    try:
        if path == "/api/libraries/add":
            folders.append(str(app.libraries.check_new_folder(srv.cfg, str(body.get("path") or "")[:1000])))
        else:
            n = body.get("n")
            if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(folders):
                raise ValueError("That isn't one of your library folders.")
            folders.pop(n - 1)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    srv.cfg["library_folders"] = folders
    srv.save_settings()
    try:
        app.build_catalog(srv.cfg, app.root_dir(srv.cfg))   # catalog.json (and Hoard for Unity) follow straight away
    except OSError as e:
        print(f"Couldn't rebuild the catalog: {e}", flush=True)
    srv.forget_index()
    return self._json({"ok": True, "libraries": srv.library_view()})


def _privacy_action(self, path: str, body: dict):
    """Archive, hide, remove and the hidden library's PIN."""
    srv, store = self.server, app.MarkStore()
    keys = {k for k in (body.get("keys") or [])[:5000] if isinstance(k, str)} if isinstance(body.get("keys"), list) else set()
    try:
        if path == "/api/marks":
            kind, on = str(body.get("kind") or ""), bool(body.get("on", True))
            marks = store.load()
            if (keys & marks["hidden"]) and not self._unlocked() and not (kind == "hidden" and on):
                return self._json({"error": "Unlock your hidden library first."}, 403)
            # each product's own key on its store, so the choice stays with it if the store renames it
            ids = {i["key"]: k for i in srv.lib.snapshot()[0] if (k := app.tag_key(i["store"], i["name"])) in keys} if on else {}
            store.change(kind, keys, on, ids)
        elif path == "/api/purge":   # removed products, deleted from Hoard's list for good
            keys &= store.load()["removed"]
            gone = srv.lib.forget_products(keys)
            return self._json({"ok": True, "deleted": gone})
        elif path == "/api/pin":   # the first PIN comes with its recovery phrase, shown this once
            phrase = store.set_pin(str(body.get("pin") or ""), body.get("current"))
            return self._json({"ok": True, **({"recovery": phrase} if phrase else {})})
        elif path == "/api/pin/recover":   # forgotten PIN: the recovery words set a new one, nothing is lost
            store.recover(str(body.get("phrase") or "")[:400], str(body.get("pin") or ""))
            with srv.unlocks_lock:
                srv.unlocks.clear()
            return self._json({"ok": True})
        elif path == "/api/pin/phrase":   # a new recovery phrase, replacing the old: only while unlocked
            if not self._unlocked():
                return self._json({"error": "Unlock your hidden library first."}, 403)
            return self._json({"ok": True, "recovery": store.new_phrase()})
        elif path == "/api/unlock":
            store.check_pin(str(body.get("pin") or ""))
            token = app.secrets.token_urlsafe(32)
            with srv.unlocks_lock:
                srv.unlocks[token] = app.time.time() + app.UNLOCK_MINUTES * 60
            secure = "; Secure" if getattr(srv, "tls", False) else ""
            data = app.json.dumps({"ok": True}).encode()
            return self._send(200, data, "application/json; charset=utf-8",
                              {"Set-Cookie": f"hoard_unlock={token}; HttpOnly; SameSite=Strict; Path=/{secure}",
                               "Cache-Control": "no-store"})
        elif path == "/api/lock":
            with srv.unlocks_lock:
                srv.unlocks.clear()
        elif path == "/api/hidden/forget":   # forgotten PIN: the hidden products are deleted, never shown
            if body.get("confirm") is not True:
                return self._json({"error": "Confirm first."}, 400)
            gone = store.forget_hidden()
            srv.lib.forget_products(gone)
            with srv.unlocks_lock:
                srv.unlocks.clear()
            return self._json({"ok": True, "deleted": len(gone)})
    except app.PinError as e:
        return self._json({"error": str(e)}, 403)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    srv.forget_index()
    return self._json({"ok": True})


def _product_details(self):
    """details(key): what Hoard knows of a product, for a set to remember (hoard/sets.py): from the library
    list (its store page and picture), else from your downloads (a product of your own in Local, say)."""
    srv = self.server
    lib, dl = {}, {}
    for i in srv.lib.snapshot()[0]:
        lib.setdefault(app.tag_key(i["store"], i["name"]), i)
    for a in srv.index(stale_ok=True)["assets"]:
        dl.setdefault(a["tag_key"], a)

    public = app.sets.public_page   # its own public page, else its creator's: never one of yours

    from .. import adult
    marks, mine = app.MarkStore().view(), app.TagStore().load()["items"]

    def for_adults(key: str, name: str, i: dict | None) -> bool:
        """Whether a product is for adults (hoard/adult.py): a set shared with it in says so (issue #337)."""
        return bool(adult.why(key, name=name, tags=[*((i or {}).get("store_tags") or []), *mine.get(key, [])],
                              flagged=(i or {}).get("adult") is True, marks=marks))

    def known(key: str) -> dict | None:
        """A product's details for the page, from the library or the downloads, with only its public link."""
        i = lib.get(key)
        if i:
            return {"store": i["store"], "id": i.get("id"), "name": i["name"], "creator": i.get("creator"),
                    "url": public(i["store"], i.get("page"), i.get("url"), i.get("creator_url")),
                    "thumbnail": i.get("thumbnail"), "adult": for_adults(key, i["name"], i)}
        a = dl.get(key)
        if a:
            store = str(a["store"]).lower()
            return {"store": store, "name": a["name"], "creator": a.get("creator"), "url": public(store, a.get("url")),
                    "adult": for_adults(key, a["name"], None)}
        return None

    def details(key: str) -> dict | None:
        """known(key), and whether you said It isn't for adults (it wins over what a set remembers: issue #337)."""
        got = known(key)
        if key in marks.get("not_adult", ()):
            return {**(got or {}), "not_adult": True}
        return got
    return details


def _hidden_key(self, key) -> bool:
    """Whether a product is hidden and Hoard is locked, so the request is answered as if it weren't there."""
    return isinstance(key, str) and key in app.MarkStore().keys("hidden") and not self._unlocked()


def _hidden_file(self, target: app.Path) -> bool:
    """Whether a file is in a hidden product's folder while the hidden library is locked (issue #171): Look inside
    and Extract refuse it, as Make an editable copy does. Folders are compared as they resolve, so another
    spelling of the same path is the same file."""
    hidden = app.MarkStore().keys("hidden")
    if not hidden or self._unlocked():
        return False
    try:
        real = target.resolve()
    except OSError:
        return True
    for a in self.server.index(stale_ok=True)["assets"]:
        if a.get("tag_key") not in hidden:
            continue
        folder = app.open_target(self.server.cfg, a.get("folder") or "")
        try:
            if folder and (real == folder.resolve() or folder.resolve() in real.parents):
                return True
        except OSError:
            return True
    return False


def get_api_library(self, path, body, query):
    """GET /api/library. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    from .. import adult
    items, stores = srv.lib.snapshot()   # enrich() makes new items, so the library's own are never changed
    tagdata = app.TagStore().load()
    items = app.enrich(items, srv.cfg["tags"], tagdata, apart=app.MarkStore().keys("apart"),
                   progress=app.loading.counter("library", "products", len(items)))   # (counted on the splash: #200)
    downloaded = srv.index(stale_ok=True)["assets"]   # never waits for a rebuild; read once, for both below
    on_disk = {a["tag_key"]: a["id"] for a in downloaded}
    app.loading.finished("library")
    app.MarkStore().follow(items)   # a product renamed since it was removed (or hidden...) stays so (issue #224)
    marks, unlocked = app.MarkStore().view(), self._unlocked()
    checked = app.AssetUpdates().load()
    updates = checked["items"]
    from ..downloads import problems
    wrong = problems(downloaded, app.last_integrity(), checked["failed"])   # (issue #334)
    cutoff = app.new_cutoff(srv.cfg)
    first_read = {s: (info.get("first_read") or "") for s, info in stores.items()}
    shown = []
    for i in items:
        added = i.get("added") or ""
        i["new"] = bool(cutoff and added and added >= cutoff and added > first_read.get(i["store"], ""))
        i["on_disk"] = on_disk.get(i["tag_key"])
        i["update"] = i["on_disk"] is not None and i["tag_key"] in updates   # its store has newer files
        i["problems"] = wrong.get(i["tag_key"], [])   # what's wrong with it, for its tile's error mark (issue #334)
        # what Copy store link copies: its public page, never a page of the buyer's own ("url" is a Gumroad
        # purchase's download page, which opens its files for whoever has it)
        i["public"] = app.sets.public_page(i["store"], i.get("page"), i.get("url"))
        i["mark"] = ("removed" if i["tag_key"] in marks["removed"] else "hidden" if i["tag_key"] in marks["hidden"]
                     else "archived" if app.is_archived(i, marks) else None)
        i["apart"] = i["tag_key"] in marks["apart"]   # "Not a copy": never stacked (issue #217)
        # for adults (issues #311, #338): by your word, its store's, or its tags and name; and which of them said so
        i["adult_from"] = adult.why(i["tag_key"], name=i["name"], tags=[*(i.get("store_tags") or []), *i["tags"]],
                                    flagged=i.get("adult") is True, marks=marks)
        i["adult"] = bool(i["adult_from"])
        i["not_adult"] = i["tag_key"] in marks["not_adult"]
        # hidden items never leave the server while it's locked: hidden by the mark itself, whatever else
        # it's marked (a hidden product also removed is labelled removed, and was let out)
        if i["tag_key"] not in marks["hidden"] or unlocked:
            shown.append(i)
    counted = [i for i in shown if i["mark"] not in ("removed", "hidden")]
    privacy = {"pin_set": bool(marks["pin"]), "unlocked": unlocked, "lock_in": self._lock_in() if unlocked else 0,
               "recovery_set": bool(marks["recovery"]),
               "hidden": len({i["tag_key"] for i in shown if i["mark"] == "hidden"}) if unlocked else None}
    keys = {i["tag_key"] for i in shown}
    hidden_now = set() if unlocked else set(marks["hidden"])
    mine = [{"id": x["id"], "name": x["name"], "kind": x.get("kind"), "items": [k for k in x["items"] if k not in hidden_now],
             "owned": len([k for k in x["items"] if k in keys])} for x in app.sets.SetStore().load()["sets"]]
    from ..stores import health
    return self._json({"items": shown, "tagset": app.tag_overview(tagdata, counted), "stores": stores, "store_health": health.snapshot(),
                       "privacy": privacy, "sets": mine,
                       "labels": {k: v["label"] for k, v in app.STORES.items()}, "job": app.public_job(srv.jobs.state, self._hidden_names()),
                       "downloadable": list(app.DOWNLOADABLE), "importable": list(app.IMPORTABLE),
                       "itch_key": app.vault.has_key(srv.cfg, "itch"),
                       # which stores Hoard holds a sign-in for, so Stores offers Sign in or Sign out, not both
                       "signed_in": {s: app.signed_in(srv.cfg, s) for s in app.STORES if srv.cfg[s].get("enabled", True)},
                       "signins": str(app.signins_root(srv.cfg)), "signins_note": app.signin_protection(srv.cfg),
                       "store_sites": app.store_sites(), "version": app.__version__,
                       "enabled": {s: bool(srv.cfg[s].get("enabled", True)) for s in app.STORES},
                       "setup_done": bool(srv.cfg.get("setup_done")), "can_quit": srv.quit_app is not None, "can_background": srv.hide_window is not None, "can_notify": srv.can_notify, "can_pick": srv.pick_path is not None,
                       "display": app.display_settings(srv.cfg), "ui": app.ui_settings(srv.cfg),
                       "ask_files": bool(srv.cfg.get("ask_files", True)),   # (issue #225)
                       "routine": app.routine_record()["found"]}, compress=True)


def get_thumb(self, path, body, query):
    """GET /thumb/*. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    got = app.fetch_thumbnail(app.unquote(path[len("/thumb/"):]), srv.lib)
    if not got:
        return self._send(404, b"Not found", "text/plain")
    return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})


def post_api_tags(self, path, body, query):
    """POST /api/tags. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    try:
        app.TagStore().change(body)
    except (ValueError, TimeoutError) as e:
        return self._json({"error": str(e)}, 400)
    srv.forget_index()
    return self._json({"ok": True})


def post_api_libraries_add(self, path, body, query):
    """POST /api/libraries/add, /api/libraries/remove. the other library folders, from Settings"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._library_folders(path, body)


def post_api_picture_looks(self, path, body, query):
    """POST /api/picture-looks. how pictures look, worked out by a page, for stacking copies (hoard/library.py)"""
    srv = self.server
    u = app.urlparse(self.path)
    looks = body.get("looks") if isinstance(body.get("looks"), dict) else {}
    if not looks or len(looks) > 500:
        return self._json({"error": "Send between 1 and 500 at a time."}, 400)
    try:
        return self._json({"ok": True, "kept": app.save_picture_looks(looks)})
    except OSError as e:
        return self._json({"error": f"Couldn't keep them: {e}"}, 500)


def post_api_unlock_touch(self, path, body, query):
    """POST /api/unlock/touch. someone's using the page (used): Hidden stays unlocked a while longer"""
    srv = self.server
    u = app.urlparse(self.path)
    lock_in = self._lock_in(touch=body.get("used") is True)
    return self._json({"ok": True, "unlocked": lock_in > 0, "lock_in": lock_in})


def post_api_marks(self, path, body, query):
    """POST /api/marks, /api/pin, /api/unlock, /api/lock, /api/purge, /api/hidden/forget, /api/pin/recover, /api/pin/phrase. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    return self._privacy_action(path, body)



METHODS = {'_library_folders': _library_folders, '_privacy_action': _privacy_action, '_product_details': _product_details, '_hidden_key': _hidden_key, '_hidden_file': _hidden_file}

ROUTES = [
    Route('GET', '/api/library', get_api_library, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/thumb/*', get_thumb, changes=False, auth='key', image_key=True, max_body=1048576, request=(), response='application/octet-stream'),
    Route('POST', '/api/tags', post_api_tags, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/libraries/add', post_api_libraries_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('n', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/libraries/remove', post_api_libraries_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('n', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/picture-looks', post_api_picture_looks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('looks', 'object'),), response='object'),
    Route('POST', '/api/unlock/touch', post_api_unlock_touch, changes=True, auth='key', image_key=False, max_body=1048576, request=(('used', 'boolean'),), response='object'),
    Route('POST', '/api/marks', post_api_marks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('current', 'any'), ('keys', 'array'), ('kind', 'any'), ('on', 'any'), ('phrase', 'string'), ('pin', 'string')), response='object'),
    Route('POST', '/api/pin', post_api_marks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('current', 'any'), ('keys', 'array'), ('kind', 'any'), ('on', 'any'), ('phrase', 'string'), ('pin', 'string')), response='object'),
    Route('POST', '/api/unlock', post_api_marks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('current', 'any'), ('keys', 'array'), ('kind', 'any'), ('on', 'any'), ('phrase', 'string'), ('pin', 'string')), response='object'),
    Route('POST', '/api/lock', post_api_marks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('current', 'any'), ('keys', 'array'), ('kind', 'any'), ('on', 'any'), ('phrase', 'string'), ('pin', 'string')), response='object'),
    Route('POST', '/api/purge', post_api_marks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('current', 'any'), ('keys', 'array'), ('kind', 'any'), ('on', 'any'), ('phrase', 'string'), ('pin', 'string')), response='object'),
    Route('POST', '/api/hidden/forget', post_api_marks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('current', 'any'), ('keys', 'array'), ('kind', 'any'), ('on', 'any'), ('phrase', 'string'), ('pin', 'string')), response='object'),
    Route('POST', '/api/pin/recover', post_api_marks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('current', 'any'), ('keys', 'array'), ('kind', 'any'), ('on', 'any'), ('phrase', 'string'), ('pin', 'string')), response='object'),
    Route('POST', '/api/pin/phrase', post_api_marks, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('current', 'any'), ('keys', 'array'), ('kind', 'any'), ('on', 'any'), ('phrase', 'string'), ('pin', 'string')), response='object'),
]
