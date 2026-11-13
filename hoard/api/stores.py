"""Stores endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

from .. import server as app
from .routing import Route


def _remember_files(self, chosen: dict | None) -> dict | None:
    """The files you left out of a product, as you chose them to download, kept for its downloads from now on
    (issue #225: Sync, Download new and the routine check leave them out too); one you ticked again is
    forgotten. Returns chosen as it was."""
    if chosen:
        srv = self.server
        with srv.cfg_lock:
            srv.cfg["file_skip"] = app.remember_choice(app.remembered_files(srv.cfg), chosen, app.file_rules(srv.cfg))
            srv.save_settings()
    return chosen


def _download_choices(self) -> dict:
    """The download choices the page may see (hidden products only once unlocked)."""
    return self.server.download_choices(self._unlocked())


def _itch_key(self, body: dict):
    """Check an itch.io API key with itch.io, keep it (vault), and read your itch.io library with it."""
    srv = self.server
    key = app.vault.clean_key(body.get("key"))
    if not key:
        return self._json({"error": "That doesn't look like an itch.io API key. Copy the whole key from itch.io "
                                    "(Settings, API keys)."}, 400)
    sess = app.itch.session(key)
    try:
        who = app.itch.profile(sess)
    except app.itch.KeyRefused:
        return self._json({"error": "itch.io didn't accept that key. Check you copied all of it, and that it hasn't "
                                    "been deleted on itch.io."}, 400)
    except Exception as e:
        return self._json({"error": app.blocked_message("itch.io") if app.blocked_here(e)
                           else "Couldn't reach itch.io. Check your connection and try again." if app.is_network_error(e)
                           else f"itch.io didn't answer as expected: {e}"}, 502)
    finally:
        sess.close()
    try:
        app.vault.save_key(srv.cfg, "itch", key)
    except (app.SigninsUnprotected, OSError) as e:
        return self._json({"error": str(e)}, 500)
    started = srv.jobs.start("refresh", ["itch"])   # queued after anything running
    name = str(who.get("display_name") or who.get("username") or "")[:100]
    return self._json({"ok": True, "user": name, "kept": app.vault.key_protection(srv.cfg), "queued": started == "queued"})


def get_api_gumroad_receipts(self, path, body, query):
    """GET /api/gumroad-receipts. The purchases you added by their Gumroad receipts (receipts.py): never their links
    or emails, which stay on the server."""
    return self._json({"receipts": app.receipts.listing(), "kept": app.vault.key_protection(self.server.cfg)})


def post_api_gumroad_receipts(self, path, body, query):
    """POST /api/gumroad-receipts. Keep the Gumroad receipts in what you add (receipts.find): View content links
    pasted as text, and receipt emails (.eml), receipt pages and purchases' saved pages, as files. Gumroad's refresh
    reads them; the page starts one."""
    srv = self.server
    text = body.get("text") if isinstance(body.get("text"), str) else ""
    files = body.get("files") if isinstance(body.get("files"), list) else []
    if len(text) > 200000 or len(files) > app.MAX_IMPORT_FILES or \
            not all(isinstance(f, dict) and isinstance(f.get("content"), str) for f in files):
        return self._json({"error": f"Add at most {app.MAX_IMPORT_FILES} receipts at a time."}, 400)
    found, problems = app.receipts.find("", text) if text.strip() else [], []
    if text.strip() and not found:
        problems.append({"error": "There's no Gumroad View content link in what you pasted (it starts gumroad.com/d/)."})
    for f in files:
        name = str(f.get("filename") or "receipt")[:300]
        try:
            got = app.receipts.find(name, f["content"])
        except Exception:   # (a damaged file: said, and the rest carry on)
            problems.append({"filename": name, "error": "It couldn't be read."})
            continue
        if not got:
            problems.append({"filename": name, "error": "There's no Gumroad receipt in it. Save the email with its View "
                                                        "content button, or the purchase's page from your browser."})
        found += got
    if not found:
        return self._json({"error": "Nothing was added.", "problems": problems}, 400)
    with srv.cfg_lock:
        done = app.receipts.add(srv.cfg, found)
    if not done["emails_kept"]:
        problems.append({"error": "This computer has no keyring to protect the receipts' emails, so Hoard didn't keep "
                                  "them: a purchase Gumroad asks to confirm can't be read."})
    return self._json({"ok": True, "found": len({f["token"] for f in found}), "added": done["added"],
                       "already": done["already"], "problems": problems, "receipts": app.receipts.listing()})


def post_api_gumroad_receipts_remove(self, path, body, query):
    """POST /api/gumroad-receipts/remove. Forget a receipt (by the ref the list gives it, or "all"), and take its
    purchase off your library list. One also in your Gumroad library comes back with the next refresh."""
    srv = self.server
    which = body.get("ref")
    if not isinstance(which, str) or not app.re.fullmatch(r"[0-9a-f]{12}|all", which):
        return self._json({"error": "That receipt isn't one Hoard keeps."}, 400)
    gone = app.receipts.remove(srv.cfg, which)
    if gone is None:
        return self._json({"error": "That receipt isn't one Hoard keeps."}, 404)
    removed = srv.lib.forget_downloads("gumroad", set(gone["tokens"]), app.receipts.token_of)
    return self._json({"ok": True, "removed": removed, "receipts": app.receipts.listing()})


def get_api_download_choices(self, path, body, query):
    """GET /api/download-choices. issue #107: what downloading new things, or updating, would get"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json(self._download_choices(), compress=True)


def post_api_itch_key(self, path, body, query):
    """POST /api/itch-key. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    return self._itch_key(body)


def post_api_download_skip(self, path, body, query):
    """POST /api/download-skip. issue #107: always skip these products when downloading, or stop"""
    srv = self.server
    u = app.urlparse(self.path)
    keys = body.get("keys") if isinstance(body.get("keys"), list) else []
    keys = {k for k in keys[:app.MAX_SKIP] if isinstance(k, str) and 0 < len(k) <= 400 and ":" in k}
    if not keys:
        return self._json({"error": "Choose the products to skip."}, 400)
    with srv.cfg_lock:
        now = app.download_skip(srv.cfg)
        now = (now | keys) if body.get("skip") is not False else (now - keys)
        if len(now) > app.MAX_SKIP:
            return self._json({"error": f"Hoard can skip up to {app.MAX_SKIP:,} products."}, 400)
        srv.cfg["download_skip"] = sorted(now)
        srv.save_settings()
    return self._json({"ok": True, "skipped": len(now)})


def post_api_signin_link(self, path, body, query):
    """POST /api/signin-link. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    why = srv.jobs.open_link(str(body.get("url") or "").strip()[:2000])
    return self._json({"error": why}, 400) if why else self._json({"ok": True})


def post_api_setup_browser(self, path, body, query):
    """POST /api/setup/browser. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    started = srv.jobs.start("install-browser", [])
    if not started:
        return self._json({"error": "Installing Hoard's browser is already waiting its turn."}, 409)
    return self._json({"ok": True, "queued": started == "queued"}, 202)


def post_api_refresh(self, path, body, query):
    """POST /api/refresh, /api/login, /api/logout, /api/download, /api/sync, /api/check-updates. Queue a store job, after validating the selection."""
    srv = self.server
    u = app.urlparse(self.path)
    named = body.get("stores")
    if named is not None and not isinstance(named, list):
        return self._json({"error": "Unknown store."}, 400)
    stores = list(dict.fromkeys(s for s in (named or list(app.STORES))[:20]
                                if isinstance(s, str) and (s in app.STORES or (path == "/api/logout" and s == "all"))))
    bulk = path in ("/api/download", "/api/check-updates") and not (body.get("keys") or body.get("item") or body.get("only"))
    if path == "/api/sync" or bulk:   # only the stores you use (a chosen product is fetched wherever it is)
        stores = [s for s in stores if srv.cfg[s].get("enabled", True)]
    if path == "/api/login" and stores[:1] == ["itch"]:   # (a sign-in is one store's: the first named)
        return self._json({"error": "itch.io signs in with an API key: choose Sign in on its row in Stores."}, 400)
    if path in ("/api/download", "/api/check-updates") and stores and not any(s in app.DOWNLOADABLE for s in stores):
        return self._json({"error": "Hoard lists what you own on Payhip, and doesn't download from it. Open the "
                                    "product's download page from its details, and download it there."}, 400)
    if not stores:
        return self._json({"error": "No stores are switched on in Settings." if path == "/api/sync" or bulk else "Unknown store."}, 400)
    task = {"/api/login": "login", "/api/logout": "logout", "/api/download": "download",
            "/api/sync": "sync", "/api/check-updates": "check-updates"}.get(path, "refresh")
    if task == "refresh" and body.get("quick") is True:   # issue #300: only the start of each library and list
        task = "quick-refresh"
    only = str(body.get("only") or "").strip()[:200] or None
    # products chosen on the Downloads page (to update, or to check), by their tag_key
    keys = [k for k in (body.get("keys") if isinstance(body.get("keys"), list) else [])[:5000]
            if isinstance(k, str) and 0 < len(k) <= 400] or None
    # the library item chosen in the Library, so the download can go straight to it
    item = body.get("item") if isinstance(body.get("item"), str) and 0 < len(body.get("item")) <= 400 else None
    started = srv.jobs.start(task, stores[:1] if task in ("login", "logout") else stores,
                             skip_imported=bool(body.get("all")), only=only, keys=keys,
                             items=[item] if item and task in ("download", "check-updates") else None,
                             chosen=self._remember_files(app.chosen_files(body.get("files"))) if task == "download" else None)
    if not started:
        return self._json({"error": "That's already waiting its turn in Tasks (or the queue is full)."}, 409)
    self._json({"ok": True, "queued": started == "queued"}, 202)



METHODS = {'_remember_files': _remember_files, '_download_choices': _download_choices, '_itch_key': _itch_key}

ROUTES = [
    Route('GET', '/api/gumroad-receipts', get_api_gumroad_receipts, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/gumroad-receipts', post_api_gumroad_receipts, changes=True, auth='key', image_key=False, max_body=83886080, request=(('files', 'array'), ('text', 'string')), response='object'),
    Route('POST', '/api/gumroad-receipts/remove', post_api_gumroad_receipts_remove, changes=True, auth='key', image_key=False, max_body=1048576, request=(('ref', 'string'),), response='object'),
    Route('GET', '/api/download-choices', get_api_download_choices, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/itch-key', post_api_itch_key, changes=True, auth='key', image_key=False, max_body=1048576, request=(('key', 'string'),), response='object'),
    Route('POST', '/api/download-skip', post_api_download_skip, changes=True, auth='key', image_key=False, max_body=1048576, request=(('keys', 'array'), ('skip', 'boolean')), response='object'),
    Route('POST', '/api/signin-link', post_api_signin_link, changes=True, auth='key', image_key=False, max_body=1048576, request=(('url', 'string'),), response='object'),
    Route('POST', '/api/setup/browser', post_api_setup_browser, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/refresh', post_api_refresh, changes=True, auth='key', image_key=False, max_body=1048576, request=(('all', 'boolean'), ('files', 'object'), ('item', 'object'), ('keys', 'array'), ('only', 'string'), ('quick', 'boolean'), ('stores', 'array')), response='object'),
    Route('POST', '/api/login', post_api_refresh, changes=True, auth='key', image_key=False, max_body=1048576, request=(('all', 'boolean'), ('files', 'object'), ('item', 'object'), ('keys', 'array'), ('only', 'string'), ('quick', 'boolean'), ('stores', 'array')), response='object'),
    Route('POST', '/api/logout', post_api_refresh, changes=True, auth='key', image_key=False, max_body=1048576, request=(('all', 'boolean'), ('files', 'object'), ('item', 'object'), ('keys', 'array'), ('only', 'string'), ('quick', 'boolean'), ('stores', 'array')), response='object'),
    Route('POST', '/api/download', post_api_refresh, changes=True, auth='key', image_key=False, max_body=1048576, request=(('all', 'boolean'), ('files', 'object'), ('item', 'object'), ('keys', 'array'), ('only', 'string'), ('quick', 'boolean'), ('stores', 'array')), response='object'),
    Route('POST', '/api/sync', post_api_refresh, changes=True, auth='key', image_key=False, max_body=1048576, request=(('all', 'boolean'), ('files', 'object'), ('item', 'object'), ('keys', 'array'), ('only', 'string'), ('quick', 'boolean'), ('stores', 'array')), response='object'),
    Route('POST', '/api/check-updates', post_api_refresh, changes=True, auth='key', image_key=False, max_body=1048576, request=(('all', 'boolean'), ('files', 'object'), ('item', 'object'), ('keys', 'array'), ('only', 'string'), ('quick', 'boolean'), ('stores', 'array')), response='object'),
]
