"""The local server behind Hoard's window: the Library and Downloads pages and everything they ask for.

It only answers this computer unless started with --host (then other devices need HTTPS and the access
key), refuses requests that name another host, and takes actions only from this computer, sent as JSON.
Every page is sent with a strict Content-Security-Policy; everything else is sandboxed.
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .browser import signin_protection, signins_root
from .config import DEFAULT_CONFIG, deep_merge, root_dir, save_config
from .downloader import collect_catalog
from .downloads import IMAGE_EXT, build_index, library_status, reveal, with_tags
from .jobs import Jobs
from .library import IMPORTABLE, STORES, Library, cache_images, enrich, fetch_thumbnail, import_saved_page
from .paths import LIBRARY_FILE, WEB, default_downloads
from .safety import (LOOPBACK, SECURITY_HEADERS, TLSServerMixin, check_access, content_security_policy, network_tls,
                     safe_join)
from .tags import TagStore, tag_overview

PAGES = {"/": "library.html", "/index.html": "library.html", "/downloads": "downloads.html"}
FONT_FILES = ("DelaGothicOne-Regular.woff2", "ZenMaruGothic-Medium.woff2", "ZenMaruGothic-Bold.woff2")
ACTIONS = ("/api/refresh", "/api/login", "/api/logout", "/api/import", "/api/tags", "/api/open",
           "/api/download", "/api/cancel", "/api/settings")
BROWSER_CHOICES = ("", "msedge", "chrome", "chromium")


def font_path(name: str) -> Path | None:
    """One of the bundled font files, or None."""
    return WEB / "fonts" / name if name in FONT_FILES and (WEB / "fonts" / name).is_file() else None


def public_settings(cfg: dict) -> dict:
    """The settings the page can show and change, with the downloads folder spelled out."""
    return {
        "root": str(root_dir(cfg)), "default_root": str(default_downloads()),
        "browser_channel": cfg.get("browser_channel", ""), "offline_images": bool(cfg.get("offline_images", True)),
        "request_delay": cfg.get("request_delay", 1.0),
        "stores": {s: {"enabled": bool(cfg[s].get("enabled", True)),
                       **({"include_gifts": bool(cfg[s].get("include_gifts", True))} if s == "booth" else {}),
                       **({"include_archived": bool(cfg[s].get("include_archived", True))} if s == "gumroad" else {})}
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
    for store, opts in (body.get("stores") or {}).items():
        if store not in STORES or not isinstance(opts, dict):
            raise ValueError("Unknown store.")
        allowed = {"enabled"} | ({"include_gifts"} if store == "booth" else set()) | \
                  ({"include_archived"} if store == "gumroad" else set())
        change[store] = {k: bool(v) for k, v in opts.items() if k in allowed}
    return change


class AppServer(TLSServerMixin, ThreadingHTTPServer):
    """Holds everything the pages work with: settings, your library, the downloads index and the job runner."""
    daemon_threads = True

    def __init__(self, addr, cfg: dict, lan: bool, config_path: Path | None = None):
        """Start listening; with lan=True, also create the access key other devices need."""
        super().__init__(addr, Handler)
        self.cfg, self.lan, self.config_path = cfg, lan, config_path
        self.key = secrets.token_urlsafe(18) if lan else None
        self.lib = Library(LIBRARY_FILE)
        self.jobs = Jobs(cfg, self.lib, on_download_done=self.forget_index)
        self._index, self._index_lock = None, threading.Lock()

    def handle_error(self, request, client_address):
        """A page that closes mid-reply (a closed window, a cancelled image) isn't a problem; anything else is shown."""
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)

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

    def _json(self, obj, status=200):
        """Send obj as JSON that the browser won't cache."""
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        """False when a request names a host other than this computer (a DNS-rebinding attempt)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return self.server.lan or host in LOOPBACK

    # ---- reading
    def do_GET(self):
        """Serve the pages, their data and images."""
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        if not check_access(self, self.server.lan, self.server.key):
            return
        u = urlparse(self.path)
        path, srv = u.path, self.server
        if path in PAGES:
            return self._send(200, (WEB / PAGES[path]).read_bytes(), "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        if path == "/api/library":
            with srv.lib.lock:
                data = json.loads(json.dumps(srv.lib.data))
            tagdata = TagStore().load()
            items = enrich(data["items"], srv.cfg["tags"], tagdata)
            on_disk = {a["tag_key"]: a["id"] for a in srv.index()["assets"]}
            for i in items:
                i["on_disk"] = on_disk.get(i["tag_key"])
            return self._json({"items": items, "tagset": tag_overview(tagdata, items), "stores": data["stores"],
                               "labels": {k: v["label"] for k, v in STORES.items()}, "job": srv.jobs.state,
                               "signins": str(signins_root(srv.cfg)), "signins_note": signin_protection(srv.cfg),
                               "version": __version__})
        if path == "/api/status":
            with srv.lib.lock:
                stores = json.loads(json.dumps(srv.lib.data["stores"]))
            return self._json({"job": srv.jobs.state, "stores": stores})
        if path == "/api/assets":
            return self._json({**with_tags(srv.index(rescan="rescan" in parse_qs(u.query))), "version": __version__,
                               "job": srv.jobs.state})
        if path == "/api/settings":
            return self._json(public_settings(srv.cfg))
        if path.startswith("/fonts/"):
            font = font_path(unquote(path[len("/fonts/"):]))
            if not font:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, font.read_bytes(), "font/woff2", {"Cache-Control": "max-age=31536000, immutable"})
        if path.startswith("/thumb/"):
            got = fetch_thumbnail(unquote(path[len("/thumb/"):]), srv.lib)
            if not got:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})
        if path.startswith("/files/"):
            p = safe_join(root_dir(srv.cfg), unquote(path[len("/files/"):]))
            if not p or p.suffix.lower() not in IMAGE_EXT or not p.is_file():
                return self._send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            return self._send(200, p.read_bytes(), ctype, {"Cache-Control": "max-age=3600"})
        self._send(404, b"Not found", "text/plain")

    # ---- acting
    def do_POST(self):
        """Run an action. Only requests from this computer, sent as JSON, are accepted."""
        path, srv = urlparse(self.path).path, self.server
        if path not in ACTIONS:
            return self._send(404, b"Not found", "text/plain")
        if (not self._host_ok() or self.client_address[0] not in LOOPBACK
                or not (self.headers.get("Content-Type") or "").startswith("application/json")):
            return self._json({"error": "That only works on the computer running Hoard."}, 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "Bad request."}, 400)
        if length > (80 * 1024 * 1024 if path == "/api/import" else 1024 * 1024):  # only imports are large
            return self._json({"error": "That's too large." if path != "/api/import"
                               else "That file is too large to be a library page."}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, RecursionError):
            return self._json({"error": "Bad request."}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "Bad request."}, 400)

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
            try:
                store, items = import_saved_page(srv.cfg, body.get("store"), str(body.get("filename") or ""),
                                                 str(body.get("content") or ""))
            except (ValueError, RuntimeError) as e:
                return self._json({"error": f"Couldn't import: {e}"}, 422)
            total = srv.lib.merge_store(store, items)
            if srv.cfg.get("offline_images", True):
                threading.Thread(target=cache_images, args=(srv.lib, [i["key"] for i in items], lambda m: None),
                                 daemon=True).start()
            return self._json({"ok": True, "store": store, "label": STORES[store]["label"], "count": len(items), "total": total})
        if path == "/api/cancel":
            return self._json({"ok": srv.jobs.cancel()})

        stores = [s for s in (body.get("stores") or list(STORES)) if s in STORES or (path == "/api/logout" and s == "all")]
        if not stores:
            return self._json({"error": "Unknown store."}, 400)
        task = {"/api/login": "login", "/api/logout": "logout", "/api/download": "download"}.get(path, "refresh")
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
    url = f"{scheme}://127.0.0.1:{srv.server_port}/"
    if srv.key:
        print(f"Other devices on your network: {scheme}://<this computer's address>:{srv.server_port}/?key={srv.key}")
        print("That key is needed to use Hoard from another device. Share it only with devices you trust.")
        if not tls:
            print("This is plain HTTP: only use it where the connection is already encrypted, such as over Tailscale.")
    print(f"Hoard {__version__}: {url}   (library: {len(srv.lib.data['items'])} items; downloads: {root_dir(cfg)})")
    if on_ready:
        on_ready(url, srv)
    elif open_browser:
        threading.Timer(0.6, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        srv.server_close()


__all__ = ["serve", "AppServer", "Handler", "public_settings", "apply_settings", "IMPORTABLE"]
