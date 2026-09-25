"""The local server behind Hoard's window: the Library and Downloads pages and everything they ask for.

It only answers this computer unless started with --host (then other devices need HTTPS), refuses requests
that name another host, and takes actions only from this computer, sent as JSON. Every request for data,
images or an action needs this run's access key, from this computer too (check_access): Hoard opens its
page with a one-time link that the page trades for the key. Every page is sent with a strict
Content-Security-Policy; everything else is sandboxed.
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .browser import signin_protection, signins_root
from .config import DEFAULT_CONFIG, apply_store_sites, clean_payhip_shop, deep_merge, payhip_shops, root_dir, save_config
from .downloader import collect_catalog
from .downloads import IMAGE_EXT, build_index, library_status, reveal, with_tags
from .jobs import Jobs
from .library import DOWNLOADABLE, IMPORTABLE, STORES, Library, cache_images, enrich, fetch_thumbnail, import_saved_pages
from .paths import LIBRARY_FILE, WEB, default_downloads
from .safety import (LOOPBACK, SECURITY_HEADERS, TLSServerMixin, check_access, content_security_policy, network_tls,
                     open_under, safe_join, store_sites, UnsafePath)
from .app import token_matches
from .marks import MarkStore, PinError, is_archived
from .setup import browser_problem, migrate_from, setup_status
from .tags import TagStore, tag_overview

PAGES = {"/": "library.html", "/index.html": "library.html", "/downloads": "downloads.html"}
FONT_FILES = ("DelaGothicOne-Regular.woff2", "ZenMaruGothic-Medium.woff2", "ZenMaruGothic-Bold.woff2")
ACTIONS = ("/api/refresh", "/api/login", "/api/logout", "/api/import", "/api/tags", "/api/open",
           "/api/download", "/api/sync", "/api/cancel", "/api/settings", "/api/setup/browser", "/api/setup/done",
           "/api/setup/migrate", "/api/signin-link", "/api/marks", "/api/pin", "/api/unlock", "/api/lock",
           "/api/purge", "/api/hidden/forget", "/api/pin/recover", "/api/pin/phrase", "/api/show", "/api/quit",
           "/api/enter")
# Actions that prove themselves another way than the access key: the one-time link a page is opened with,
# and a second copy of Hoard with the token in the running copy's private file.
KEYLESS_ACTIONS = ("/api/enter", "/api/show")
UNLOCK_MINUTES = 15   # how long unlocking the hidden library lasts in one browser, extended while it's in use
ENTRY_SECONDS = 300   # how long a one-time link to open Hoard's page stays usable, if it's never used
BROWSER_CHOICES = ("", "msedge", "chrome", "chromium")
MAX_IMPORT_FILES = 50   # saved pages in one request; the page sends more as several requests


def font_path(name: str) -> Path | None:
    """One of the bundled font files, or None."""
    return WEB / "fonts" / name if name in FONT_FILES and (WEB / "fonts" / name).is_file() else None


def public_settings(cfg: dict) -> dict:
    """The settings the page can show and change, with the downloads folder spelled out."""
    return {
        "root": str(root_dir(cfg)), "default_root": str(default_downloads()),
        "browser_channel": cfg.get("browser_channel", ""), "offline_images": bool(cfg.get("offline_images", True)),
        "request_delay": cfg.get("request_delay", 1.0), "payhip_shops": payhip_shops(cfg),
        "stores": {s: {"enabled": bool(cfg[s].get("enabled", True)),
                       **({"include_gifts": bool(cfg[s].get("include_gifts", True)),
                           "include_free": bool(cfg[s].get("include_free", True))} if s == "booth" else {}),
                       **({"include_archived": bool(cfg[s].get("include_archived", True))} if s == "gumroad" else {}),
                       **({"skip_game_builds": bool(cfg[s].get("skip_game_builds", True))} if s == "itch" else {})}
                   for s in STORES},
    }


def apply_settings(cfg: dict, body: dict) -> dict:
    """Check changed settings from the page and return them as a config change. Raises ValueError when invalid."""
    change: dict = {}
    if "root" in body:
        value = str(body["root"] or "").strip()
        if value:
            folder = Path(value).expanduser()
            if not folder.is_absolute():
                raise ValueError("Choose the downloads folder as a full path, such as D:\\VRChat\\Hoard.")
            if folder.exists() and not folder.is_dir():
                raise ValueError("That's a file, not a folder.")
        change["root"] = value
    if "browser_channel" in body:
        if body["browser_channel"] not in BROWSER_CHOICES:
            raise ValueError("Unknown browser.")
        change["browser_channel"] = body["browser_channel"]
    if "offline_images" in body:
        change["offline_images"] = bool(body["offline_images"])
    if "request_delay" in body:
        try:
            delay = float(body["request_delay"])
        except (TypeError, ValueError):
            raise ValueError("The delay between page loads must be a number of seconds.") from None
        if not 0.3 <= delay <= 10:
            raise ValueError("Keep the delay between page loads between 0.3 and 10 seconds.")
        change["request_delay"] = delay
    if "payhip_shops" in body:
        given = body["payhip_shops"] if isinstance(body["payhip_shops"], list) else []
        shops, bad = [], []
        for value in given[:200]:
            if str(value or "").strip():
                shop = clean_payhip_shop(value)
                (shops.append(shop) if shop else bad.append(str(value)[:80]))
        if bad:
            raise ValueError("These aren't Payhip shop addresses: " + ", ".join(bad) +
                             ". Use the shop's own address, such as myshop.store or payhip.com/MyShop.")
        change.setdefault("payhip", {})["shops"] = list(dict.fromkeys(shops))
    for store, opts in (body.get("stores") or {}).items():
        if store not in STORES or not isinstance(opts, dict):
            raise ValueError("Unknown store.")
        allowed = {"enabled"} | ({"include_gifts", "include_free"} if store == "booth" else set()) | \
                  ({"include_archived"} if store == "gumroad" else set()) | ({"skip_game_builds"} if store == "itch" else set())
        change.setdefault(store, {}).update({k: bool(v) for k, v in opts.items() if k in allowed})
    return change


MAX_SERVED_IMAGE = 30 * 1024 * 1024
MAX_CONNECTIONS = 64      # at once; more are closed straight away, so held-open connections can't pile up


class AppServer(TLSServerMixin, ThreadingHTTPServer):
    """Holds everything the pages work with: settings, your library, the downloads index and the job runner."""
    daemon_threads = True
    request_queue_size = 32

    def process_request(self, request, client_address):
        """Serve each connection on its own thread, but never more than MAX_CONNECTIONS at once."""
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def __init__(self, addr, cfg: dict, lan: bool, config_path: Path | None = None):
        """Start listening, with a new access key: every request for data, images or an action needs it."""
        super().__init__(addr, Handler)
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.unlocks: dict[str, float] = {}   # hidden-library unlock tokens, in memory only: a restart locks it
        # The desktop app (app.py) fills these in: bring its window to the front, quit, and the token a second
        # copy of Hoard proves itself with. last_seen: when a page last asked for anything.
        self.show_window = None
        self.quit_app = None
        self.show_token = None
        self.last_seen = time.time()
        self.cfg, self.lan, self.config_path = cfg, lan, config_path
        self.key = secrets.token_urlsafe(32)   # new on every start, in memory only
        self.url = f"http://127.0.0.1:{self.server_port}/"   # serve() makes it https when there's a certificate
        self._entries: dict[str, float] = {}   # one-time links: token -> until when it can be used
        self._entries_lock = threading.Lock()
        self.lib = Library(LIBRARY_FILE)
        self.jobs = Jobs(cfg, self.lib, on_download_done=self.forget_index)
        self._index, self._index_lock = None, threading.Lock()

    def handle_error(self, request, client_address):
        """A page that closes mid-reply (a closed window, a cancelled image) isn't a problem; anything else is shown."""
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)

    def entry_url(self) -> str:
        """A one-time link to Hoard's page, for opening its window or a browser. The page trades the token in it for
        the access key, so the key itself never appears where other programs can see it (a browser's command
        line, which other accounts can read on some systems). Usable once, within ENTRY_SECONDS."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._entries_lock:
            self._entries = {t: until for t, until in self._entries.items() if until > now}
            self._entries[token] = now + ENTRY_SECONDS
        return f"{self.url}#enter={token}"

    def use_entry(self, token) -> bool:
        """Is token a one-time link that hasn't been used or run out? Using it ends it."""
        if not isinstance(token, str) or not token:
            return False
        with self._entries_lock:
            until = self._entries.pop(token, None)
        return until is not None and until > time.time()

    def forget_index(self) -> None:
        """The downloads changed: rebuild the index next time it's asked for."""
        with self._index_lock:
            self._index = None

    def index(self, rescan: bool = False) -> dict:
        """What's on disk, rebuilt from the records on the first call, after a download, and on every rescan."""
        root = root_dir(self.cfg)
        with self._index_lock:
            if rescan or self._index is None or self._index.get("root") != str(root):
                try:
                    self._index = build_index(root, collect_catalog(self.cfg, root)[0])
                except Exception as e:  # show the problem in the page instead of a blank grid
                    self._index = {"root": str(root), "assets": [], "status": library_status(root),
                                   "error": f"Couldn't read the downloads: {e}"}
            return self._index


class Handler(BaseHTTPRequestHandler):
    timeout = 30   # seconds a connection may sit idle or trickle a request before it's closed
    """Answers the pages' requests."""
    server: AppServer

    def log_message(self, *args):
        """Keep the console quiet: individual requests aren't logged."""

    def _send(self, status, body: bytes, ctype: str, headers: dict | None = None):
        """Send a reply with the security headers; pages get their own policy, everything else is sandboxed."""
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", content_security_policy(body))
        else:
            self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _unlocked(self) -> bool:
        """Has this browser unlocked the hidden library (and used it within the last UNLOCK_MINUTES)?"""
        srv = self.server
        cookie = self.headers.get("Cookie") or ""
        token = next((c.split("=", 1)[1] for c in (x.strip() for x in cookie.split(";")) if c.startswith("hoard_unlock=")), "")
        now = time.time()
        for t in [t for t, until in srv.unlocks.items() if until < now]:
            del srv.unlocks[t]
        if token and token in srv.unlocks:
            srv.unlocks[token] = now + UNLOCK_MINUTES * 60
            return True
        return False

    def _json(self, obj, status=200):
        """Send obj as JSON that the browser won't cache."""
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        """False when a request names a host other than this computer (a DNS-rebinding attempt)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return self.server.lan or host in LOOPBACK

    def _refused(self):
        """The request didn't carry this run's access key (see check_access)."""
        return self._json({"error": "Hoard didn't recognise this page. Open Hoard again, or the address it printed."}, 401)

    # ---- reading
    def do_GET(self):
        """Serve the pages, their data and images."""
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        u = urlparse(self.path)
        path, srv = u.path, self.server
        if path in PAGES:   # the pages hold nothing private: everything they show is fetched with the access key
            srv.last_seen = time.time()
            return self._send(200, (WEB / PAGES[path]).read_bytes(), "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        if path.startswith("/fonts/"):
            font = font_path(unquote(path[len("/fonts/"):]))
            if not font:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, font.read_bytes(), "font/woff2", {"Cache-Control": "max-age=31536000, immutable"})
        if not check_access(self, srv.key, in_address=path.startswith(("/thumb/", "/files/"))):
            return self._refused()
        srv.last_seen = time.time()
        if path == "/api/library":
            items, stores = srv.lib.snapshot()   # enrich() makes new items, so the library's own are never changed
            tagdata = TagStore().load()
            items = enrich(items, srv.cfg["tags"], tagdata)
            on_disk = {a["tag_key"]: a["id"] for a in srv.index()["assets"]}
            marks, unlocked = MarkStore().load(), self._unlocked()
            shown = []
            for i in items:
                i["on_disk"] = on_disk.get(i["tag_key"])
                i["mark"] = ("removed" if i["tag_key"] in marks["removed"] else "hidden" if i["tag_key"] in marks["hidden"]
                             else "archived" if is_archived(i, marks) else None)
                if i["mark"] != "hidden" or unlocked:   # hidden items never leave the server while it's locked
                    shown.append(i)
            counted = [i for i in shown if i["mark"] not in ("removed", "hidden")]
            privacy = {"pin_set": bool(marks["pin"]), "unlocked": unlocked, "recovery_set": bool(marks["recovery"]),
                       "hidden": len({i["tag_key"] for i in shown if i["mark"] == "hidden"}) if unlocked else None}
            return self._json({"items": shown, "tagset": tag_overview(tagdata, counted), "stores": stores,
                               "privacy": privacy,
                               "labels": {k: v["label"] for k, v in STORES.items()}, "job": srv.jobs.state,
                               "downloadable": list(DOWNLOADABLE), "importable": list(IMPORTABLE),
                               "signins": str(signins_root(srv.cfg)), "signins_note": signin_protection(srv.cfg),
                               "store_sites": store_sites(), "version": __version__,
                               "enabled": {s: bool(srv.cfg[s].get("enabled", True)) for s in STORES},
                               "setup_done": bool(srv.cfg.get("setup_done")), "can_quit": srv.quit_app is not None})
        if path == "/api/status":
            return self._json({"job": srv.jobs.state, "stores": srv.lib.snapshot()[1]})
        if path == "/api/assets":
            index = with_tags(srv.index(rescan="rescan" in parse_qs(u.query)))
            if not self._unlocked():   # hidden products' downloads stay out of view too
                hidden = MarkStore().load()["hidden"]
                index = {**index, "assets": [a for a in index["assets"] if a.get("tag_key") not in hidden]}
            return self._json({**index, "version": __version__, "job": srv.jobs.state, "store_sites": store_sites(),
                               "can_quit": srv.quit_app is not None})
        if path == "/api/settings":
            return self._json(public_settings(srv.cfg))
        if path == "/api/setup":
            return self._json({**setup_status(srv.cfg), "job": srv.jobs.state})
        if path.startswith("/thumb/"):
            got = fetch_thumbnail(unquote(path[len("/thumb/"):]), srv.lib)
            if not got:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})
        if path.startswith("/files/"):
            rel = unquote(path[len("/files/"):])
            if Path(rel).suffix.lower() not in IMAGE_EXT or not safe_join(root_dir(srv.cfg), rel):
                return self._send(404, b"Not found", "text/plain")
            try:   # opened without following any link below the downloads folder; what's served is what was opened
                with open_under(root_dir(srv.cfg), rel) as fh:
                    data = fh.read(MAX_SERVED_IMAGE + 1)
            except (UnsafePath, OSError):
                return self._send(404, b"Not found", "text/plain")
            if len(data) > MAX_SERVED_IMAGE:
                return self._send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(rel)[0] or "application/octet-stream"
            return self._send(200, data, ctype, {"Cache-Control": "max-age=3600"})
        self._send(404, b"Not found", "text/plain")

    def _privacy_action(self, path: str, body: dict):
        """Archive, hide, remove and the hidden library's PIN."""
        srv, store = self.server, MarkStore()
        keys = {k for k in (body.get("keys") or [])[:5000] if isinstance(k, str)} if isinstance(body.get("keys"), list) else set()
        try:
            if path == "/api/marks":
                kind, on = str(body.get("kind") or ""), bool(body.get("on", True))
                marks = store.load()
                if (keys & marks["hidden"]) and not self._unlocked() and not (kind == "hidden" and on):
                    return self._json({"error": "Unlock your hidden library first."}, 403)
                store.change(kind, keys, on)
            elif path == "/api/purge":   # removed products, deleted from Hoard's list for good
                keys &= store.load()["removed"]
                gone = srv.lib.forget_products(keys)
                return self._json({"ok": True, "deleted": gone})
            elif path == "/api/pin":   # the first PIN comes with its recovery phrase, shown this once
                phrase = store.set_pin(str(body.get("pin") or ""), body.get("current"))
                return self._json({"ok": True, **({"recovery": phrase} if phrase else {})})
            elif path == "/api/pin/recover":   # forgotten PIN: the recovery words set a new one, nothing is lost
                store.recover(str(body.get("phrase") or "")[:400], str(body.get("pin") or ""))
                srv.unlocks.clear()
                return self._json({"ok": True})
            elif path == "/api/pin/phrase":   # a new recovery phrase, replacing the old: only while unlocked
                if not self._unlocked():
                    return self._json({"error": "Unlock your hidden library first."}, 403)
                return self._json({"ok": True, "recovery": store.new_phrase()})
            elif path == "/api/unlock":
                store.check_pin(str(body.get("pin") or ""))
                token = secrets.token_urlsafe(32)
                srv.unlocks[token] = time.time() + UNLOCK_MINUTES * 60
                secure = "; Secure" if getattr(srv, "tls", False) else ""
                data = json.dumps({"ok": True}).encode()
                return self._send(200, data, "application/json; charset=utf-8",
                                  {"Set-Cookie": f"hoard_unlock={token}; HttpOnly; SameSite=Strict; Path=/{secure}",
                                   "Cache-Control": "no-store"})
            elif path == "/api/lock":
                srv.unlocks.clear()
            elif path == "/api/hidden/forget":   # forgotten PIN: the hidden products are deleted, never shown
                if body.get("confirm") is not True:
                    return self._json({"error": "Confirm first."}, 400)
                gone = store.forget_hidden()
                srv.lib.forget_products(gone)
                srv.unlocks.clear()
                return self._json({"ok": True, "deleted": len(gone)})
        except PinError as e:
            return self._json({"error": str(e)}, 403)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        srv.forget_index()
        return self._json({"ok": True})

    def _import(self, body: dict):
        """Import library pages saved from your own browser: any number, sent a batch at a time. Each page gets its
        own result, so one bad page doesn't stop the rest. A page from a Payhip shop you haven't added comes back
        asking you to confirm that shop; sent again with the shop in trust_shops, it's added."""
        srv = self.server
        files = body.get("files")
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_IMPORT_FILES or \
                not all(isinstance(f, dict) and isinstance(f.get("content"), str) for f in files):
            return self._json({"error": f"Send between 1 and {MAX_IMPORT_FILES} saved pages at a time."}, 400)
        store = body.get("store") if isinstance(body.get("store"), str) else None
        trust = [s for s in body.get("trust_shops") or [] if isinstance(s, str)][:200] \
            if isinstance(body.get("trust_shops"), list) else []
        shops_before = payhip_shops(srv.cfg)
        try:
            results = import_saved_pages(srv.cfg, [(str(f.get("filename") or "page")[:300], f["content"]) for f in files],
                                         store, trust)
        except Exception as e:   # the reading browser itself didn't start: no page could be read
            return self._json({"error": browser_problem(e) or f"Couldn't read the pages: {e}"}, 500)
        found: dict[str, list] = {}
        for r in results:
            if r.get("items"):
                found.setdefault(r["store"], []).extend(r["items"])
        totals = {s: srv.lib.merge_store(s, items) for s, items in found.items()}
        added = [s for s in payhip_shops(srv.cfg) if s not in shops_before]
        if added:   # importing a shop's page, once you've confirmed the shop, adds it to your list
            save_config({k: srv.cfg[k] for k in DEFAULT_CONFIG if k in srv.cfg}, srv.config_path)
        if found and srv.cfg.get("offline_images", True):
            keys = [i["key"] for items in found.values() for i in items]
            threading.Thread(target=cache_images, args=(srv.lib, keys, lambda m: None), daemon=True).start()
        said = []
        for r in results:
            if "items" in r:
                said.append({"filename": r["filename"], "store": r["store"], "label": STORES[r["store"]]["label"],
                             "count": len(r["items"])})
            else:
                said.append({"filename": r["filename"], **{k: r[k] for k in ("confirm_shop", "error") if k in r}})
        return self._json({"ok": True, "results": said, "added_shops": added,
                           "totals": {s: {"label": STORES[s]["label"], "total": n} for s, n in totals.items()}})

    # ---- acting
    def do_POST(self):
        """Run an action. Only requests from this computer, sent as JSON with the access key, are accepted."""
        path, srv = urlparse(self.path).path, self.server
        if path not in ACTIONS:
            return self._send(404, b"Not found", "text/plain")
        if (not self._host_ok() or self.client_address[0] not in LOOPBACK
                or not (self.headers.get("Content-Type") or "").startswith("application/json")):
            return self._json({"error": "That only works on the computer running Hoard."}, 403)
        if path not in KEYLESS_ACTIONS and not check_access(self, srv.key):
            return self._refused()
        srv.last_seen = time.time()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "Bad request."}, 400)
        if length > (80 * 1024 * 1024 if path == "/api/import" else 1024 * 1024):  # only imports are large
            return self._json({"error": "That's too large." if path != "/api/import"
                               else "That's too large to be library pages. Import fewer at a time."}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, RecursionError):
            return self._json({"error": "Bad request."}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "Bad request."}, 400)

        if path == "/api/enter":   # a page Hoard opened with a one-time link, trading it for the access key
            if not srv.use_entry(body.get("token")):
                return self._json({"error": "That link to Hoard was already used or is too old. Open Hoard again."}, 403)
            return self._json({"ok": True, "key": srv.key})
        if path == "/api/tags":
            try:
                TagStore().change(body)
            except (ValueError, TimeoutError) as e:
                return self._json({"error": str(e)}, 400)
            srv.forget_index()
            return self._json({"ok": True})
        if path == "/api/settings":
            if srv.jobs.state["running"]:
                return self._json({"error": "Wait for the current job to finish before changing settings."}, 409)
            try:
                change = apply_settings(srv.cfg, body)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            deep_merge(srv.cfg, change)
            apply_store_sites(srv.cfg)   # added or removed Payhip shops count (or stop counting) straight away
            save_config({k: srv.cfg[k] for k in DEFAULT_CONFIG if k in srv.cfg}, srv.config_path)
            srv.forget_index()
            return self._json({"ok": True, "settings": public_settings(srv.cfg)})
        if path == "/api/open":
            target = safe_join(root_dir(srv.cfg), str(body.get("path", "")))
            if not target or not target.exists():
                return self._json({"error": "That file or folder isn't on disk anymore."}, 404)
            try:
                return self._json({"ok": True, "opened_in": reveal(target)})
            except OSError as e:
                return self._json({"error": str(e)}, 500)
        if path == "/api/import":
            return self._import(body)
        if path == "/api/cancel":
            return self._json({"ok": srv.jobs.cancel()})
        if path in ("/api/marks", "/api/pin", "/api/unlock", "/api/lock", "/api/purge", "/api/hidden/forget",
                    "/api/pin/recover", "/api/pin/phrase"):
            return self._privacy_action(path, body)
        if path == "/api/show":   # a second copy of Hoard, asking this one to come to the front
            if not token_matches(body.get("token"), srv.show_token) or not srv.show_window:
                return self._json({"error": "No."}, 403)
            srv.show_window()
            return self._json({"ok": True})
        if path == "/api/quit":
            if not srv.quit_app:
                return self._json({"error": "Hoard is running as a server; stop it where it was started."}, 409)
            threading.Timer(0.3, srv.quit_app).start()   # after this answer is on its way
            return self._json({"ok": True})
        if path == "/api/signin-link":
            why = srv.jobs.open_link(str(body.get("url") or "").strip()[:2000])
            return self._json({"error": why}, 400) if why else self._json({"ok": True})
        if path == "/api/setup/browser":
            if not srv.jobs.start("install-browser", []):
                return self._json({"error": "Hoard is busy. Wait for the current job to finish."}, 409)
            return self._json({"ok": True}, 202)
        if path == "/api/setup/done":
            srv.cfg["setup_done"] = bool(body.get("done", True))
            save_config({k: srv.cfg[k] for k in DEFAULT_CONFIG if k in srv.cfg}, srv.config_path)
            return self._json({"ok": True})
        if path == "/api/setup/migrate":
            folder = str(body.get("folder") or "").strip().strip('"')[:1000]
            if not folder or not Path(folder).expanduser().is_absolute():
                return self._json({"error": "Enter the full path of the folder you ran Hoard 1.x from."}, 400)
            said = migrate_from(srv.cfg, Path(folder), srv.config_path, srv.lib)
            srv.forget_index()
            return self._json({"ok": True, "message": said})

        stores = [s for s in (body.get("stores") or list(STORES)) if s in STORES or (path == "/api/logout" and s == "all")]
        if path == "/api/sync":   # only the stores you use
            stores = [s for s in stores if srv.cfg[s].get("enabled", True)]
        if path == "/api/download" and stores and not any(s in DOWNLOADABLE for s in stores):
            return self._json({"error": "Hoard lists what you own on Payhip, and doesn't download from it. Open the "
                                        "product's download page from its details, and download it there."}, 400)
        if not stores:
            return self._json({"error": "Unknown store." if path != "/api/sync" else "No stores are switched on in Settings."}, 400)
        task = {"/api/login": "login", "/api/logout": "logout", "/api/download": "download",
                "/api/sync": "sync"}.get(path, "refresh")
        only = str(body.get("only") or "").strip()[:200] or None
        if not srv.jobs.start(task, stores[:1] if task in ("login", "logout") else stores,
                              skip_imported=bool(body.get("all")), only=only):
            return self._json({"error": "Hoard is busy. Wait for the current job to finish."}, 409)
        self._json({"ok": True}, 202)


def serve(cfg: dict, host: str = "127.0.0.1", port: int = 0, open_browser: bool = True, tls_cert: str | None = None,
          tls_key: str | None = None, plain_http: bool = False, config_path: Path | None = None,
          on_ready=None) -> None:
    """Start Hoard's server. With port 0 the system picks a free port. Blocks until stopped."""
    tls = network_tls(host, tls_cert, tls_key, plain_http)
    try:
        srv = AppServer((host, port), cfg, lan=host not in LOOPBACK, config_path=config_path)
    except OSError as e:
        sys.exit(f"Couldn't start on port {port} ({e}). Try another one with --port.")
    srv.tls_context, srv.tls = tls, bool(tls)
    scheme = "https" if tls else "http"
    srv.url = url = f"{scheme}://127.0.0.1:{srv.server_port}/"
    if srv.lan:
        print(f"Other devices on your network: {scheme}://<this computer's address>:{srv.server_port}/#key={srv.key}")
        print("That address includes the access key, new each time Hoard starts. Share it only with devices you trust.")
        if not tls:
            print("This is plain HTTP: only use it where the connection is already encrypted, such as over Tailscale.")
    print(f"Hoard {__version__}: {url}   (library: {len(srv.lib.data['items'])} items; downloads: {root_dir(cfg)})")
    if on_ready:   # the desktop app: it opens its window with a one-time link, and never logs the key
        on_ready(url, srv)
    else:
        print(f"Open Hoard at {url}#key={srv.key}   (this address includes the access key: keep it to yourself)")
        if open_browser:
            threading.Timer(0.6, webbrowser.open, (srv.entry_url(),)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        srv.server_close()


__all__ = ["serve", "AppServer", "Handler", "public_settings", "apply_settings", "IMPORTABLE"]
