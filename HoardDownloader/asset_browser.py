#!/usr/bin/env python3
"""
Local, read-only browser for everything asset_dl.py has downloaded.

    python asset_dl.py browse                 opens http://127.0.0.1:8765
    python asset_dl.py browse --port 9000 --no-open

It reads the store manifests and the files on disk every time you open or rescan it,
so it's current even while a sync is still running. Nothing here moves, renames or deletes
anything; the only action it takes is asking Explorer (or your file manager) to open a
folder or highlight a file inside your download root.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import unicodedata
import urllib.error
import urllib.request
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
UI_FILE = HERE / "browser.html"
FONT_FILES = ("DelaGothicOne-Regular.woff2", "ZenMaruGothic-Medium.woff2", "ZenMaruGothic-Bold.woff2")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
PREVIEW_HINT = re.compile(r"preview|thumb|cover|icon|promo|banner", re.I)
VERSION_RX = re.compile(r"\bv?\d+(?:\.\d+)*\b", re.I)
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


# ----------------------------------------------------------------------------- index

def _norm(s: str) -> str:
    """A name reduced to letters and digits, without version numbers, for matching across stores."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\W_]+", "", VERSION_RX.sub(" ", s))


def _same_creator(a: str, b: str) -> bool:
    """True when two creator names are probably the same creator (or one is unknown)."""
    na, nb = _norm(a), _norm(b)
    if "unknowncreator" in (na, nb):
        return True
    return bool(na and nb and (na == nb or na in nb or nb in na))


def _thumbnail(folder: Path, files: list[str]) -> str | None:
    """_thumbnail.* saved by the downloader, else a preview-looking image, else any image."""
    try:
        for p in sorted(folder.glob("_thumbnail.*")):
            if p.suffix.lower() in IMAGE_EXT:
                return p.name
    except OSError:
        pass
    images = [f for f in files if Path(f).suffix.lower() in IMAGE_EXT]
    for f in images:
        if PREVIEW_HINT.search(Path(f).stem):
            return f
    return images[0] if images else None


STORES = ("Booth", "Gumroad", "Jinxxy", "Payhip")


def library_status(root: Path) -> dict:
    """What's actually under root, plus other places downloads might be, for troubleshooting."""
    stores = {}
    for store in STORES:
        m = root / store / "_manifest.json"
        count = 0
        if m.exists():
            try:
                count = sum(1 for a in json.loads(m.read_text("utf-8")).get("assets", {}).values() if a.get("files"))
            except (ValueError, OSError):
                count = -1
        stores[store] = {"manifest": str(m), "found": m.exists(), "assets": count}
    def subdirs(d: Path) -> list[Path]:
        try:
            return [p for p in d.iterdir() if p.is_dir()][:200]
        except OSError:
            return []

    # the default folder, the parent, siblings, and subfolders of root
    candidates = [HERE / "downloads", root.parent, *subdirs(root.parent), *subdirs(root)]
    elsewhere = []
    for c in candidates:
        try:
            if c.resolve() != root.resolve() and any((c / s / "_manifest.json").exists() for s in STORES):
                elsewhere.append(str(c))
        except OSError:
            pass
    return {"root_exists": root.is_dir(), "stores": stores, "elsewhere": elsewhere}


def build_index(root: Path, catalog: list[dict]) -> dict:

    """The data behind the page: every downloaded asset with its files, sizes, image and matches."""
    assets = []
    for i, e in enumerate(catalog):
        folder = root.joinpath(*e["folder"].split("/"))
        files, total, missing, newest = [], 0, 0, 0.0
        for rel in e.get("files", []):
            try:
                st = folder.joinpath(*rel.split("/")).stat()
                total += st.st_size
                newest = max(newest, st.st_mtime)
                files.append({"path": rel, "size": st.st_size})
            except OSError:
                missing += 1
                files.append({"path": rel, "size": None, "missing": True})
        thumb = _thumbnail(folder, e.get("files", []))
        assets.append({
            "id": i,
            "store": e["store"],
            "name": e["name"],
            "creator": e["creator"],
            "variants": e.get("variants"),
            "url": safe_url(e.get("url")),
            "folder": e["folder"],
            "abs_folder": str(folder),
            "tags": e.get("suggested_tags", []),
            "types": sorted({Path(f).suffix.lower().lstrip(".") for f in e.get("files", []) if Path(f).suffix}),
            "files": files,
            "size": total,
            "missing": missing,
            "added": e.get("added"),
            "modified": newest or None,
            "thumb": f"{e['folder']}/{thumb}" if thumb else None,
            "also_in": [],
        })

    # The same product bought on both stores: flag it, never merge it.
    by_name: dict[str, list] = {}
    for a in assets:
        by_name.setdefault(_norm(a["name"]), []).append(a)
    for group in by_name.values():
        if len({a["store"] for a in group}) < 2:
            continue
        for a in group:
            a["also_in"] = [{"id": b["id"], "store": b["store"]} for b in group
                            if b["store"] != a["store"] and _same_creator(a["creator"], b["creator"])]

    return {"root": str(root), "assets": assets, "status": library_status(root)}


# ----------------------------------------------------------------------------- web safety
#
# The page runs on your own computer, but the text and links it shows come from store pages and
# from saved pages you import, so none of it is trusted:
#   - links are only kept when they are ordinary http(s) addresses (no javascript: or file:),
#   - server-side fetches only go to public internet addresses, never your home network or this PC,
#   - every page is sent with a Content-Security-Policy that only runs the page's own script, and
#     with headers that stop other sites from framing it or reading its responses,
#   - on your network (--host 0.0.0.0) other devices need the access key printed at start-up.

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}
_csp_cache: dict = {}


def safe_url(value) -> str | None:
    """Return value if it's a plain http(s) address, otherwise None."""
    if not isinstance(value, str):
        return None
    u = urlparse(value.strip())
    return value.strip() if u.scheme in ("http", "https") and u.netloc else None


def public_http_url(url: str) -> bool:
    """True when url is http(s) and every address its host resolves to is on the public internet."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            return False
    return True


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only if it leads to another public http(s) address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Refuse the redirect unless it leads to a public http(s) address."""
        if not public_http_url(newurl):
            raise urllib.error.URLError(f"refused a redirect to {urlparse(newurl).hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url: str, headers: dict, max_bytes: int, timeout: int = 20) -> tuple[bytes, str] | None:
    """Download a small file from a public http(s) address. Returns (data, content type) or None."""
    if not public_http_url(url):
        return None
    opener = urllib.request.OpenerDirector()  # http(s) only: no file://, ftp:// or data: handlers
    for handler in (urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), _PublicRedirects(),
                    urllib.request.HTTPErrorProcessor(), urllib.request.HTTPDefaultErrorHandler()):
        opener.add_handler(handler)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None
            return data, r.headers.get_content_type()
    except Exception:
        return None


def content_security_policy(page: bytes) -> str:
    """A policy that runs only the page's own inline script (by its hash) and loads nothing unexpected."""
    key = hashlib.sha256(page).hexdigest()
    if key not in _csp_cache:
        scripts = re.findall(rb"<script>(.*?)</script>", page, re.S)
        hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s).digest()).decode() + "'" for s in scripts)
        script_src = hashes or "'none'"
        _csp_cache[key] = ("default-src 'none'; "
                           f"script-src {script_src}; "
                           "style-src 'self' 'unsafe-inline'; "
                           "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
                           "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return _csp_cache[key]


def check_access(handler, lan: bool, key: str | None) -> bool:
    """On the network (--host 0.0.0.0), let a device in only with the access key. True when allowed.

    The key arrives once in the address (?key=...); after that it's kept in a cookie. Sends the reply
    itself (a redirect that sets the cookie, or a refusal) when it returns False.
    """
    if not lan or not key:
        return True
    host = (handler.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
    if handler.client_address[0] in LOOPBACK and host in LOOPBACK:
        return True  # this computer itself
    cookies = SimpleCookie(handler.headers.get("Cookie") or "")
    if "hoard_key" in cookies and hmac.compare_digest(cookies["hoard_key"].value, key):
        return True
    given = (parse_qs(urlparse(handler.path).query).get("key") or [""])[0]
    if given and hmac.compare_digest(given, key):
        handler.send_response(303)
        handler.send_header("Location", urlparse(handler.path).path or "/")
        handler.send_header("Set-Cookie", f"hoard_key={key}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return False
    body = (b"<!doctype html><meta charset=utf-8><title>Access key needed</title>"
            b"<p style='font:16px system-ui;margin:40px'>Open the address shown in the Hoard window on the computer "
            b"running it. It includes the access key.</p>")
    handler.send_response(401)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    for k, v in SECURITY_HEADERS.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)
    return False


# ----------------------------------------------------------------------------- server

def font_path(name: str) -> Path | None:
    """A bundled font file: next to the program (release zips) or one folder up (the repository and the bundle)."""
    if name not in FONT_FILES:
        return None
    for folder in (HERE / "fonts", HERE.parent / "fonts"):
        if (folder / name).is_file():
            return folder / name
    return None


def safe_join(root: Path, rel: str) -> Path | None:
    """Resolve a /-separated path inside root; None if it would escape root."""
    parts = [s for s in rel.replace("\\", "/").split("/") if s not in ("", ".", "..")]
    try:
        base = root.resolve()
        p = base.joinpath(*parts).resolve()
    except (OSError, ValueError):
        return None
    return p if p == base or base in p.parents else None


def reveal(p: Path) -> str:
    """Show a folder, or a file within its folder, in Explorer, Finder or the file manager."""
    if sys.platform == "win32":
        if p.is_dir():
            os.startfile(str(p))  # noqa: S606 - opens a folder inside the download root
        else:
            subprocess.Popen(f'explorer /select,"{p}"')
        return "Explorer"
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(p)] if p.is_file() else ["open", str(p)])
        return "Finder"
    subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])
    return "your file manager"


class BrowserServer(ThreadingHTTPServer):
    """The local server for "Browse your downloads". Holds the index and rebuilds it on request."""
    daemon_threads = True

    def __init__(self, addr, root: Path, collect, lan: bool, version: str = ""):
        """Start listening; with lan=True, also create the access key other devices need."""
        super().__init__(addr, Handler)
        self.root = root
        self.collect = collect
        self.lan = lan
        self.version = version
        self.key = secrets.token_urlsafe(18) if lan else None
        self._index = None
        self._lock = threading.Lock()

    def index(self, rescan: bool = False) -> dict:
        """The current index, rebuilt from the manifests on the first call and on every rescan."""
        with self._lock:
            if rescan or self._index is None:
                try:
                    self._index = build_index(self.root, self.collect())
                except Exception as e:  # show the problem in the page instead of a blank grid
                    self._index = {"root": str(self.root), "assets": [], "status": library_status(self.root),
                                   "error": f"Couldn't read the library: {e}"}
            return self._index


class Handler(BaseHTTPRequestHandler):
    """Answers the page's requests. Only this computer is served unless the tool was started with --host."""
    server: BrowserServer

    def log_message(self, *args):  # keep the console quiet
        """Keep the console quiet: individual requests aren't logged."""
        pass

    def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        """Send a reply with the security headers, adding the page's Content-Security-Policy to HTML."""
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", content_security_policy(body))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        """Send obj as JSON that the browser won't cache."""
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        """False when a request names a host other than this computer (a DNS-rebinding attempt)."""
        if self.server.lan:
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in LOOPBACK  # blocks DNS-rebinding tricks against the local server

    def do_GET(self):
        """Serve the page, its data and images."""
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        if not check_access(self, self.server.lan, self.server.key):
            return
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, UI_FILE.read_bytes(), "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        if u.path == "/api/assets":
            return self._json({**self.server.index(rescan="rescan" in parse_qs(u.query)), "version": self.server.version})
        if u.path.startswith("/fonts/"):
            font = font_path(unquote(u.path[len("/fonts/"):]))
            if not font:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, font.read_bytes(), "font/woff2", {"Cache-Control": "max-age=31536000, immutable"})
        if u.path.startswith("/files/"):
            p = safe_join(self.server.root, unquote(u.path[len("/files/"):]))
            if not p or p.suffix.lower() not in IMAGE_EXT or not p.is_file():
                return self._send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            return self._send(200, p.read_bytes(), ctype, {"Cache-Control": "max-age=3600"})
        self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        """Run an action. Only requests from this computer, sent as JSON, are accepted."""
        if urlparse(self.path).path != "/api/open":
            return self._send(404, b"Not found", "text/plain")
        # Only this computer may open folders, and only via a JSON request (which other sites can't forge).
        if (not self._host_ok() or self.client_address[0] not in LOOPBACK
                or not (self.headers.get("Content-Type") or "").startswith("application/json")):
            return self._json({"error": "Opening folders only works from this computer."}, 403)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._json({"error": "Bad request."}, 400)
        target = safe_join(self.server.root, str(body.get("path", "")))
        if not target or not target.exists():
            return self._json({"error": "That file or folder isn't on disk anymore."}, 404)
        try:
            opened_in = reveal(target)
        except OSError as e:
            return self._json({"error": str(e)}, 500)
        self._json({"ok": True, "opened_in": opened_in})


def print_status(root: Path, count: int, config_path: Path | None) -> None:
    """Print which folder is being browsed and what's in it, with hints when nothing is found."""
    st = library_status(root)
    print(f"Library folder: {root}" + ("" if st["root_exists"] else "   <- this folder doesn't exist"))
    for store, info in st["stores"].items():
        state = (f"{info['assets']} assets" if info["assets"] >= 0 else "manifest unreadable") if info["found"] \
            else "no downloads here"
        print(f"  {store:<8} {state}")
    if count == 0:
        where = f"`root` in {config_path}" if config_path and Path(config_path).exists() \
            else f"no config.json was found{f' at {config_path}' if config_path else ''}, so the default folder is used"
        print(f"\nNo downloaded assets found. Check the library folder above ({where}).")
        for other in st["elsewhere"]:
            print(f"  Downloads exist in: {other}  - set \"root\" to this folder in config.json")


def serve(root: Path, collect, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True,
          config_path: Path | None = None, version: str = "") -> None:
    """Start the downloads browser and open it in the default web browser."""
    lan = host not in LOOPBACK
    try:
        srv = BrowserServer((host, port), root, collect, lan, version)
    except OSError as e:
        sys.exit(f"Couldn't start on port {port} ({e}). Try the command: browse --port {port + 1}")
    url = f"http://127.0.0.1:{port}/"
    print_status(root, len(srv.index()["assets"]), config_path)
    print(f"\nYour downloads: {url}")
    if lan:
        print(f"Other devices on your network: http://<this computer's address>:{port}/?key={srv.key}")
        print("That key is needed to browse from another device. Opening folders only works on this computer.")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    import asset_dl  # standalone use: python asset_browser.py

    cfg_path = HERE / "config.json"
    cfg = asset_dl.load_config(cfg_path)
    lib_root = asset_dl.root_dir(cfg)
    serve(lib_root, lambda: asset_dl.collect_catalog(cfg, lib_root)[0], config_path=cfg_path)
