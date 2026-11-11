"""Imports endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

import copy

from .. import server as app
from .routing import Route


def _import_wishlists(self, body: dict):
    """Wishlist pages saved from your own browser: each read offline (wishlists.from_saved_pages), and each list
    in them kept as a wishlist. A long wishlist saved a page at a time comes together as one."""
    files = body.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= app.MAX_IMPORT_FILES or \
            not all(isinstance(f, dict) and isinstance(f.get("content"), str) for f in files):
        return self._json({"error": f"Send between 1 and {app.MAX_IMPORT_FILES} saved pages at a time."}, 400)
    try:
        results = app.wishlists.from_saved_pages([(str(f.get("filename") or "page")[:300], f["content"]) for f in files])
    except Exception as e:   # the reading browser itself didn't start
        return self._json({"error": app.browser_problem(e) or f"Couldn't read the pages: {e}"}, 500)
    lists = app.wishlists.merge_lists([x for r in results for x in r.get("lists", [])])
    try:
        done = app.sets.SetStore().put_wishlists(lists) if lists else {"lists": 0, "cheaper": []}
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    return self._json({"ok": True, "lists": done["lists"],
                       "pages": [{"filename": r["filename"], **({"error": r["error"]} if "error" in r else
                                  {"lists": [{"list": x["list"], "store": x["store"], "products": len(x["products"])}
                                             for x in r["lists"]]})} for r in results],
                       **self._sets_view()})


def _import(self, body: dict):
    """Import library pages saved from your own browser: any number, sent a batch at a time. Each page gets its
    own result, so one bad page doesn't stop the rest. A page from a Payhip shop you haven't added comes back
    asking you to confirm that shop; sent again with the shop in trust_shops, it's added."""
    srv = self.server
    files = body.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= app.MAX_IMPORT_FILES or \
            not all(isinstance(f, dict) and isinstance(f.get("content"), str) for f in files):
        return self._json({"error": f"Send between 1 and {app.MAX_IMPORT_FILES} saved pages at a time."}, 400)
    store = body.get("store") if isinstance(body.get("store"), str) else None
    trust = [s for s in body.get("trust_shops") or [] if isinstance(s, str)][:200] \
        if isinstance(body.get("trust_shops"), list) else []
    shops_before = app.payhip_shops(srv.cfg)
    settings_before = copy.deepcopy(srv.cfg)
    try:
        results = app.import_saved_pages(srv.cfg, [(str(f.get("filename") or "page")[:300], f["content"]) for f in files],
                                     store, trust)
    except Exception as e:   # the reading browser itself didn't start: no page could be read
        srv.cfg.clear()
        srv.cfg.update(settings_before)
        app.apply_store_sites(srv.cfg)
        return self._json({"error": app.browser_problem(e) or f"Couldn't read the pages: {e}"}, 500)
    found: dict[str, list] = {}
    for r in results:
        if r.get("items"):
            found.setdefault(r["store"], []).extend(r["items"])
    added = [s for s in app.payhip_shops(srv.cfg) if s not in shops_before]
    try:
        with srv.lib.changing():
            totals = {s: srv.lib.merge_store(s, items) for s, items in found.items()}
            if added:   # confirmed shop settings commit with the imported products
                srv.save_settings()
    except Exception as e:
        srv.cfg.clear()
        srv.cfg.update(settings_before)
        app.apply_store_sites(srv.cfg)
        return self._json({"error": str(e)}, 500)
    if found and srv.cfg.get("offline_images", True):
        keys = [i["key"] for items in found.values() for i in items]
        srv.start_worker("Caching store pictures", app.cache_images, srv.lib, keys, lambda m: None)
    said = []
    for r in results:
        if "items" in r:
            said.append({"filename": r["filename"], "store": r["store"], "label": app.STORES[r["store"]]["label"],
                         "count": len(r["items"])})
        else:
            said.append({"filename": r["filename"], **{k: r[k] for k in ("confirm_shop", "error") if k in r}})
    return self._json({"ok": True, "results": said, "added_shops": added,
                       "totals": {s: {"label": app.STORES[s]["label"], "total": n} for s, n in totals.items()}})


def post_api_import(self, path, body, query):
    """POST /api/import. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    return self._import(body)



METHODS = {'_import_wishlists': _import_wishlists, '_import': _import}

ROUTES = [
    Route('POST', '/api/import', post_api_import, changes=True, auth='key', image_key=False, max_body=83886080, request=(('files', 'array'), ('store', 'string'), ('trust_shops', 'array')), response='object'),
]
