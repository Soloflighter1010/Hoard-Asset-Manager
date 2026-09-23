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

import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import unicodedata
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
UI_FILE = HERE / "browser.html"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
PREVIEW_HINT = re.compile(r"preview|thumb|cover|icon|promo|banner", re.I)
VERSION_RX = re.compile(r"\bv?\d+(?:\.\d+)*\b", re.I)
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


# ----------------------------------------------------------------------------- index

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\W_]+", "", VERSION_RX.sub(" ", s))


def _same_creator(a: str, b: str) -> bool:
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


STORES = ("Gumroad", "Jinxxy")


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
            "url": e.get("url"),
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


# ----------------------------------------------------------------------------- server

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
    daemon_threads = True

    def __init__(self, addr, root: Path, collect, lan: bool):
        super().__init__(addr, Handler)
        self.root = root
        self.collect = collect
        self.lan = lan
        self._index = None
        self._lock = threading.Lock()

    def index(self, rescan: bool = False) -> dict:
        with self._lock:
            if rescan or self._index is None:
                try:
                    self._index = build_index(self.root, self.collect())
                except Exception as e:  # show the problem in the page instead of a blank grid
                    self._index = {"root": str(self.root), "assets": [], "status": library_status(self.root),
                                   "error": f"Couldn't read the library: {e}"}
            return self._index


class Handler(BaseHTTPRequestHandler):
    server: BrowserServer

    def log_message(self, *args):  # keep the console quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        if self.server.lan:
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in LOOPBACK  # blocks DNS-rebinding tricks against the local server

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, UI_FILE.read_bytes(), "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        if u.path == "/api/assets":
            return self._json(self.server.index(rescan="rescan" in parse_qs(u.query)))
        if u.path.startswith("/files/"):
            p = safe_join(self.server.root, unquote(u.path[len("/files/"):]))
            if not p or p.suffix.lower() not in IMAGE_EXT or not p.is_file():
                return self._send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            return self._send(200, p.read_bytes(), ctype, {"Cache-Control": "max-age=3600"})
        self._send(404, b"Not found", "text/plain")

    def do_POST(self):
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
          config_path: Path | None = None) -> None:
    lan = host not in LOOPBACK
    try:
        srv = BrowserServer((host, port), root, collect, lan)
    except OSError as e:
        sys.exit(f"Couldn't start on port {port} ({e}). Try the command: browse --port {port + 1}")
    url = f"http://127.0.0.1:{port}/"
    print_status(root, len(srv.index()["assets"]), config_path)
    print(f"\nYour downloads: {url}")
    if lan:
        print("Serving on your network too. Thumbnails and search work from other devices; "
              "opening folders only works on this computer.")
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
