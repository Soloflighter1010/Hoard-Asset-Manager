"""The local server behind Hoard's window: the Library and Downloads pages and everything they ask for.

It only answers this computer unless started with --host (then other devices need HTTPS), refuses requests
that name another host, and takes actions only from this computer, sent as JSON. Every request for data,
images or an action needs this run's access key, from this computer too (check_access): Hoard opens its
page with a one-time link that the page trades for the key. Every page is sent with a strict
Content-Security-Policy; everything else is sandboxed.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import secrets
import sys
import threading
import time
import webbrowser
from shutil import rmtree
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import __version__, backup, diagnostics, i18n, itch, libraries, loading, needs, packages, places, previous, projects, sets, shortlinks, space, themes, updater, vault, wishlists
from .changelog import whats_new
from .asset_updates import AssetUpdates
from .browser import SigninsUnprotected, signin_protection, signins_root, use_channel
from .config import DEFAULT_CONFIG, apply_store_sites, clean_payhip_shop, deep_merge, payhip_shops, root_dir, save_config
from .downloader import (build_catalog, catalog_seal, collect_catalog, delete_downloaded_files, download_retries, integrity_summary,
                         restore_previous, file_rules, remembered_files, ruled_out, MAX_REMEMBERED,
                         edits_root, last_integrity, make_editable_copy, reseal_catalog)
from .downloads import build_index, library_status, reveal, with_tags
from .jobs import MAX_SKIP, PROJECTS, ROUTINE_CHOICES, Jobs, Schedule, download_skip, forget_deleted_signins, routine_hours, routine_record, save_routine
from .net import blocked_here, blocked_message, is_network_error
from .wishlists import read_store_page   # (Add products by link: tests stand in for it here)
from .library import (DOWNLOADABLE, IMPORTABLE, STORES, Library, cache_images, common_words, enrich, fetch_picture, fetch_thumbnail, import_saved_pages,
                      save_picture_looks, stack_by_picture)
from .paths import LIBRARY_FILE, STORE_PYTHON_NOTE, WEB, default_downloads, store_python
from .safety import (LOOPBACK, SECURITY_HEADERS, TLSServerMixin, check_access, contained_rel, content_security_policy,
                     fetch_public, header_safe, network_tls, open_under, safe_join, safe_name, store_sites, UnsafePath)
from .app import token_matches
from .marks import MarkStore, PinError, is_archived
from .setup import browser_problem, migrate_from, setup_status, signed_in
from .tags import TagStore, product_type, tag_key, tag_overview
from .vpm import api as vpm_api, logbook as vpm_log

PAGES = {"/": "library.html", "/index.html": "library.html", "/downloads": "downloads.html"}
FONT_FILES = ("DelaGothicOne-Regular.woff2", "ZenMaruGothic-Medium.woff2", "ZenMaruGothic-Bold.woff2",
              "OpenDyslexic-Regular.woff2", "OpenDyslexic-Bold.woff2")
ACTIONS = ("/api/refresh", "/api/login", "/api/logout", "/api/import", "/api/tags", "/api/open",
           "/api/download", "/api/sync", "/api/cancel", "/api/force-stop", "/api/settings", "/api/setup/browser", "/api/setup/done",
           "/api/setup/migrate", "/api/signin-link", "/api/marks", "/api/pin", "/api/unlock", "/api/lock",
           "/api/purge", "/api/hidden/forget", "/api/pin/recover", "/api/pin/phrase", "/api/show", "/api/quit",
           "/api/app/close", "/api/open-logs", "/api/folders/open",
           "/api/enter", "/api/itch-key", "/api/update/check", "/api/update/install",
           "/api/diagnostics/report", "/api/diagnostics/open-folder", "/api/check-updates",
           "/api/queue/remove", "/api/queue/clear", "/api/tasks/clear", "/api/delete-files", "/api/edit-copy", "/api/verify",
           "/api/local/add", "/api/local/rescan", "/api/local/remove", "/api/projects/forget",
           "/api/pick", "/api/move", "/api/libraries/add", "/api/libraries/remove", "/api/download-skip", "/api/product-files",
           "/api/routine/seen", "/api/local/preview", "/api/picture-looks", "/api/look-inside", "/api/look-inside/extract",
           "/api/previous/restore", "/api/sets", "/api/backup/make", "/api/backup/check", "/api/backup/restore",
           "/api/backup/show", "/api/local/picture", "/api/wishlists/read", "/api/wishlists/import",
           # Projects (hoard/vpm): the Creator Companion's and ALCOM's projects, their packages, and your library in them
           "/api/vpm/preview", "/api/vpm/apply", "/api/vpm/create", "/api/vpm/preload", "/api/vpm/backup",
           "/api/vpm/refresh", "/api/vpm/open", "/api/vpm/add-project", "/api/vpm/remove-project", "/api/vpm/favorite", "/api/vpm/organize",
           "/api/vpm/repos/add", "/api/vpm/repos/remove", "/api/vpm/settings", "/api/vpm/check-name",
           "/api/vpm/presets", "/api/vpm/open-folder", "/api/vpm/backups", "/api/vpm/backups/settings",
           "/api/vpm/backups/delete", "/api/vpm/backups/move", "/api/vpm/backups/show", "/api/vpm/delete-project")
# Actions that prove themselves another way than the access key: the one-time link a page is opened with,
# and a second copy of Hoard with the token in the running copy's private file.
KEYLESS_ACTIONS = ("/api/enter", "/api/show")
UNLOCK_MINUTES = 15   # how long unlocking the hidden library lasts in one browser, extended while it's in use
ENTRY_SECONDS = 300   # how long a one-time link to open Hoard's page stays usable, if it's never used
BROWSER_CHOICES = ("", "msedge", "chrome", "chromium")
TEXT_SIZES = (100, 115, 130, 150)   # percent
FONTS = ("standard", "dyslexic")    # Settings, Accessibility: the pages' own, or OpenDyslexic
JOB_SETTINGS = ("root", "browser_channel", "stores", "payhip_shops", "library_folders")   # read by a running job: not changed during one
NEW_DAYS = (0, 1, 3, 7, 14, 30)     # how long something new in the library is marked New (0: never)


def new_cutoff(cfg: dict) -> str | None:
    """Items added since this time are New (issue #18); None when New is switched off."""
    days = cfg.get("new_days", 7)
    if days not in NEW_DAYS or not days or isinstance(days, bool):
        return None
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
MAX_IMPORT_FILES = 50   # saved pages in one request; the page sends more as several requests


def font_path(name: str) -> Path | None:
    """One of the bundled font files, or None. The path is built from Hoard's own list of names, never from the
    name asked for, so no request can name any other file."""
    for known in FONT_FILES:
        if known == name:
            path = WEB / "fonts" / known
            return path if path.is_file() else None
    return None


COLOUR_SCHEMES = ("standard", "colourblind", "custom")   # store colours (issue #112)
COLOURED = ("booth", "gumroad", "jinxxy", "payhip", "itch", "local")   # what has a colour of its own
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")


def custom_colours(given) -> dict:
    """Your own store colours, as #rrggbb, for the stores that have one; anything else is left out."""
    given = given if isinstance(given, dict) else {}
    return {k: given[k].lower() for k in COLOURED if isinstance(given.get(k), str) and HEX_COLOUR.fullmatch(given[k])}


def display_settings(cfg: dict) -> dict:
    """Text size, motion, the glow, the store colours and the theme, as the pages apply them."""
    d = cfg.get("display") if isinstance(cfg.get("display"), dict) else {}
    return {"text_size": d.get("text_size") if d.get("text_size") in TEXT_SIZES else 100,
            "pause_animations": bool(d.get("pause_animations")), "reduce_motion": bool(d.get("reduce_motion")),
            "glow": d.get("glow") is not False,
            # easier reading: OpenDyslexic for Latin letters, and more space between letters, words and lines
            "font": d.get("font") if d.get("font") in FONTS else "standard", "spacing": bool(d.get("spacing")),
            "card_outlines": bool(d.get("card_outlines")),   # each card outlined, on a background of its own (#222)
            "colours": d.get("colours") if d.get("colours") in COLOUR_SCHEMES else "standard",
            "custom_colours": custom_colours(d.get("custom_colours")),
            # the theme and Light or Dark (Settings, Appearance), with its colours for the page to put in place
            "theme": themes.theme_id(d.get("theme")), "mode": themes.mode_id(d.get("mode")),
            "theme_css": themes.css(d.get("theme"), d.get("mode")), "themes": themes.choices(),
            "style": themes.style_id(d.get("style")),
            "language": i18n.setting(d.get("language"))}


def public_job(job: dict, hidden_names: list[str] | None = None) -> dict:
    """Job state safe for the browser: raw exception diagnostics stay inside the Hoard process, and while the hidden
    library is locked, hidden products' names are taken out of its messages and log."""
    out = {k: v for k, v in (job or {}).items() if k != "diagnostic"}
    if hidden_names:
        for k in ("message", "error", "job_label", "label"):
            if isinstance(out.get(k), str):
                out[k] = mask_names(out[k], hidden_names)
        if isinstance(out.get("log"), list):
            out["log"] = [mask_names(str(x), hidden_names) for x in out["log"]]
        if isinstance(out.get("transfer"), dict):
            out["transfer"] = {**out["transfer"], "file": mask_names(str(out["transfer"].get("file") or ""), hidden_names)}
        if isinstance(out.get("report"), dict):
            out["report"] = {k: [mask_names(str(x), hidden_names) for x in v] if isinstance(v, list) else v
                             for k, v in out["report"].items()}
    return out


def pic_for(key: str) -> str:
    """Which product a set's picture address is for (/setpic/<set>/<place>?p=...): a place in a list is another
    product's once one before it is taken out, so the address names the product too, and a picture kept by the
    browser for that place is never shown for the next one."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def mask_names(text: str, names: list[str]) -> str:
    """text with each of these names (hidden products) replaced by "a hidden item"."""
    for name in names:
        if name and name in text:
            text = text.replace(name, "a hidden item")
    return text


UI_WINDOWS = ("tagPanel", "stores", "settingsPanel", "tasksWin")
UI_SORTS = ("name", "creator", "store", "added", "size")   # the Library's and Downloads' Sort (size: Downloads only)


def ui_settings(cfg: dict) -> dict:
    """How you left the pages (kept in config.json, since the pages' own storage goes with the server's address, which
    is new each time Hoard starts): each window's place and size, the sidebar and its sections folded, the tile size,
    the sort, one for both pages, and the sets you added to last."""
    ui = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
    out: dict = {"windows": {}, "sections": {}}
    for wid, place in (ui.get("windows") or {}).items() if isinstance(ui.get("windows"), dict) else ():
        if wid in UI_WINDOWS and isinstance(place, dict):
            out["windows"][wid] = {k: v for k, v in place.items() if k in ("x", "y", "w", "h")
                                   and isinstance(v, (int, float)) and not isinstance(v, bool) and -20000 <= v <= 20000}
    for name, open_ in list((ui.get("sections") or {}).items())[:30] if isinstance(ui.get("sections"), dict) else ():
        if isinstance(name, str) and len(name) <= 40 and isinstance(open_, bool):
            out["sections"][name] = open_
    for k in ("side_folded", "stack", "toured"):   # the sidebar folded; copies stacked (issue #111); the tour offered
        if isinstance(ui.get(k), bool):
            out[k] = ui[k]
    for k in ("tile_size", "dl_tile_size"):   # the Library's and the Downloads page's
        if isinstance(ui.get(k), int) and not isinstance(ui.get(k), bool) and 100 <= ui[k] <= 400:
            out[k] = ui[k]
    if ui.get("sort") in UI_SORTS:
        out["sort"] = ui["sort"]
    if isinstance(ui.get("recent_sets"), list):   # the sets you added to last, first in the right-click menu (issue #228)
        out["recent_sets"] = [s for s in ui["recent_sets"] if isinstance(s, str) and re.fullmatch(r"[0-9A-Za-z]{1,16}", s)][:10]
    return out


def open_target(cfg: dict, rel: str) -> Path | None:
    """What Open folder or Show in folder means: a path inside the downloads folder, inside another library folder
    ("@1/Booth/...", hoard/libraries.py), or inside a Local item listed where it is (issue #80), named by its place in
    the catalog ("Local/_linked/<key>/...")."""
    rel = rel.replace("\\", "/")
    if rel.startswith("@"):
        found = libraries.resolve(cfg, rel)
        if found and not found[1].strip("/"):   # "@1/": the library folder itself
            return found[0] if libraries.available(found[0]) else None
        rest = contained_rel(found[0], found[1]) if found else None   # plain, and inside that library folder
        return safe_join(found[0], rest) if rest else None
    root = root_dir(cfg)
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "Local" and parts[1] == "_linked":
        from . import local
        found = local.by_folder(root, "/".join(parts[:3]))
        if not found or not found[1].get("location"):
            return None
        from .downloader import record_folder
        try:
            folder = record_folder(local.local_dir(root), found[1])
        except UnsafePath:
            return None
        return safe_join(folder, "/".join(parts[3:])) if len(parts) > 3 else folder
    return safe_join(root, rel)


def integrity_view(cfg: dict) -> dict:
    """The last check of the downloads (issue #83), for the Downloads page: when, and how many files were fine,
    changed or missing. Counts only: which files is in the check's log in Tasks, where hidden names are masked."""
    last = last_integrity()
    view = {"every_hours": routine_hours(cfg), "checked": None}   # (checked by the routine check: issue #113)
    if last:
        view.update(checked=last["checked"], files=last["files"], fine=last["fine"], changed=len(last["changed"]),
                    missing=len(last["missing"]), data_changed=len(last["data_changed"]), complete=last["complete"],
                    summary=integrity_summary(last))
    return view


def public_settings(cfg: dict) -> dict:
    """The settings the page can show and change, with the downloads folder spelled out."""
    return {
        "root": str(root_dir(cfg)), "default_root": str(default_downloads()), "libraries": libraries.view(cfg),
        "browser_channel": cfg.get("browser_channel", ""), "offline_images": bool(cfg.get("offline_images", True)),
        "store_tags": bool(cfg.get("store_tags", True)), "file_rules": file_rules(cfg), "ask_files": bool(cfg.get("ask_files", True)),
        "request_delay": cfg.get("request_delay", 1.0), "payhip_shops": payhip_shops(cfg),
        "check_for_updates": bool(cfg.get("check_for_updates")),
        "beta_updates": bool(cfg.get("beta_updates")),
        "close_to_taskbar": bool(cfg.get("close_to_taskbar", True)),
        "notify_found": cfg.get("notify_found", True) is not False,
        "routine_hours": routine_hours(cfg),
        "new_days": cfg.get("new_days") if cfg.get("new_days") in NEW_DAYS and not isinstance(cfg.get("new_days"), bool) else 7,
        "download_retries": download_retries(cfg),
        "keep_previous": keep_previous(cfg),
        "local_copy": cfg.get("local_copy", True) is not False,
        "display": display_settings(cfg),
        # the browser each choice would really start on this computer (a chosen one that isn't installed is stood in
        # for by Hoard's own), so Settings can say so rather than leave it to a surprise at sign-in (issue #20)
        "browsers": {choice: use_channel({**cfg, "browser_channel": choice}) for choice in BROWSER_CHOICES},
        "stores": {s: {"enabled": bool(cfg[s].get("enabled", True)),
                       **({"include_gifts": bool(cfg[s].get("include_gifts", True)),
                           "include_free": bool(cfg[s].get("include_free", True))} if s == "booth" else {}),
                       **({"include_archived": bool(cfg[s].get("include_archived", True))} if s == "gumroad" else {}),
                       **({"skip_game_builds": bool(cfg[s].get("skip_game_builds", True))} if s == "itch" else {})}
                   for s in STORES},
    }


KEEP_PREVIOUS = (0, 1, 2, 3, 5)


def keep_previous(cfg: dict) -> int:
    """How many previous versions of a replaced file to keep (Settings, Previous versions)."""
    n = cfg.get("keep_previous", 1)
    return n if n in KEEP_PREVIOUS and not isinstance(n, bool) else 1


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
    if "store_tags" in body:
        change["store_tags"] = bool(body["store_tags"])
    if "ask_files" in body:   # ask which of a product's files to download, before downloading it (issue #225)
        change["ask_files"] = bool(body["ask_files"])
    if "file_rules" in body:   # files to leave out of every download (issue #225), checked as downloads read them
        change["file_rules"] = file_rules({"file_rules": body["file_rules"]})
    if "check_for_updates" in body:
        change["check_for_updates"] = bool(body["check_for_updates"])
    if "beta_updates" in body:
        change["beta_updates"] = bool(body["beta_updates"])
    if "close_to_taskbar" in body:
        change["close_to_taskbar"] = bool(body["close_to_taskbar"])
    if "notify_found" in body:
        change["notify_found"] = bool(body["notify_found"])
    if "routine_hours" in body:   # issue #113
        if body["routine_hours"] not in ROUTINE_CHOICES or isinstance(body["routine_hours"], bool):
            raise ValueError("Choose how often to run the routine check from the list.")
        change["routine_hours"] = body["routine_hours"]
    if "download_retries" in body:
        if body["download_retries"] not in (0, 1, 2, 3) or isinstance(body["download_retries"], bool):
            raise ValueError("Choose how many times to try a failed download again from the list.")
        change["download_retries"] = body["download_retries"]
    if "keep_previous" in body:   # previous versions (hoard/previous.py)
        if body["keep_previous"] not in KEEP_PREVIOUS or isinstance(body["keep_previous"], bool):
            raise ValueError("Choose how many previous versions to keep from the list.")
        change["keep_previous"] = body["keep_previous"]
    if "new_days" in body:
        if body["new_days"] not in NEW_DAYS or isinstance(body["new_days"], bool):
            raise ValueError("Choose how long things are marked New from the list.")
        change["new_days"] = body["new_days"]
    if "ui" in body:   # checked the same way as it's read back (ui_settings), and only what's valid is kept
        change["ui"] = ui_settings({"ui": body["ui"]})
        change["ui"] = {k: v for k, v in change["ui"].items() if v != {}}
    if "display" in body:
        given = body["display"] if isinstance(body["display"], dict) else {}
        display = {}
        if "text_size" in given:
            if given["text_size"] not in TEXT_SIZES or isinstance(given["text_size"], bool):
                raise ValueError("Choose a text size from the list.")
            display["text_size"] = given["text_size"]
        display.update({k: bool(given[k]) for k in ("pause_animations", "reduce_motion", "glow", "spacing", "card_outlines")
                        if k in given})
        if "font" in given:
            if given["font"] not in FONTS:
                raise ValueError("Choose a font from the list.")
            display["font"] = given["font"]
        if "colours" in given:
            if given["colours"] not in COLOUR_SCHEMES:
                raise ValueError("Choose store colours from the list.")
            display["colours"] = given["colours"]
        if "theme" in given:
            if given["theme"] not in themes.THEMES:
                raise ValueError("Choose a theme from the list.")
            display["theme"] = given["theme"]
        if "language" in given:
            if given["language"] not in i18n.SETTINGS:
                raise ValueError("Choose a language from the list.")
            display["language"] = given["language"]
        if "mode" in given:
            if given["mode"] not in themes.MODES:
                raise ValueError("Choose Match my computer, Light or Dark.")
            display["mode"] = given["mode"]
        if "style" in given:
            if given["style"] not in themes.STYLES:
                raise ValueError("Choose Standard, Treasure or Workbench.")
            display["style"] = given["style"]
        if "custom_colours" in given:
            colours = custom_colours(given["custom_colours"])
            if not isinstance(given["custom_colours"], dict) or len(colours) != len(given["custom_colours"]):
                raise ValueError("Each store's colour needs to be a colour such as #FF6259.")
            display["custom_colours"] = colours
        change["display"] = display
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
    given_stores = body.get("stores") or {}
    if not isinstance(given_stores, dict):
        raise ValueError("Unknown store.")
    for store, opts in given_stores.items():
        if store not in STORES or not isinstance(opts, dict):
            raise ValueError("Unknown store.")
        allowed = {"enabled"} | ({"include_gifts", "include_free"} if store == "booth" else set()) | \
                  ({"include_archived"} if store == "gumroad" else set()) | ({"skip_game_builds"} if store == "itch" else set())
        change.setdefault(store, {}).update({k: bool(v) for k, v in opts.items() if k in allowed})
    return change


MAX_SERVED_IMAGE = 30 * 1024 * 1024
# The type each image in the downloads folder is served as: from this fixed list, never worked out from the request
SERVED_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
                      ".gif": "image/gif"}
MAX_CONNECTIONS = 64      # at once; more are closed straight away, so held-open connections can't pile up


# Projects' requests, as Projects' log names one it couldn't do (hoard/vpm/logbook.py); those not here (a name checked
# as it's typed, a product's contents, the log itself) aren't logged
VPM_ACTIONS = {"/api/vpm": "Reading your projects", "/api/vpm/project": "Reading a project",
               "/api/vpm/packages": "Reading the packages", "/api/vpm/versions": "Reading a package's versions",
               "/api/vpm/preview": "Working out the changes", "/api/vpm/apply": "Changing packages",
               "/api/vpm/create": "New project", "/api/vpm/preload": "Putting products in", "/api/vpm/backup": "Back up",
               "/api/vpm/refresh": "Refreshing the repositories", "/api/vpm/open": "Open in Unity",
               "/api/vpm/open-folder": "Open folder", "/api/vpm/add-project": "Add a project",
               "/api/vpm/remove-project": "Take off the list", "/api/vpm/delete-project": "Delete from this computer",
               "/api/vpm/favorite": "Favourite", "/api/vpm/organize": "Folders and tags", "/api/vpm/repos/add": "Add a repository",
               "/api/vpm/repos/remove": "Remove a repository", "/api/vpm/settings": "Unity and folders",
               "/api/vpm/presets": "Presets", "/api/vpm/backups": "Backups", "/api/vpm/backups/settings": "Backups",
               "/api/vpm/backups/show": "Backups", "/api/vpm/backups/delete": "Delete backups",
               "/api/vpm/backups/move": "Move backups"}


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
        self.unlocks_lock = threading.Lock()   # (requests are answered on threads of their own)
        # The desktop app (app.py) fills these in: bring its window to the front, quit, and the token a second
        # copy of Hoard proves itself with. last_seen: when a page last asked for anything.
        self.show_window = None
        self.can_notify = False   # Hoard's app (window or browser) tells you what the routine check found (hoard/notify.py)
        self.accept_language = None   # the language the window last asked a page in: Match my computer's, for a notification
        self.hide_window = None   # the window only: minimized to the taskbar, and Hoard carries on
        self.pick_path = None     # Hoard's own window: the system's folder or file picker (kind, start) -> path or None
        self.picking = threading.Lock()   # a system picker is open (see /api/pick)
        # one change to the settings file at a time (the always-skip list's read and change too, issue #107);
        # re-entrant, as that change saves the settings while holding it
        self.cfg_lock = threading.RLock()
        self.quit_app = None
        self.show_token = None
        self.last_seen = time.time()
        self.cfg, self.lan, self.config_path = cfg, lan, config_path
        self.key = secrets.token_urlsafe(32)   # new on every start, in memory only
        self.url = f"http://127.0.0.1:{self.server_port}/"   # serve() makes it https when there's a certificate
        self._entries: dict[str, float] = {}   # one-time links: token -> until when it can be used
        self._entries_lock = threading.Lock()
        self.lib = Library(LIBRARY_FILE)
        forget_deleted_signins(cfg, self.lib)   # a sign-in folder deleted while Hoard was closed (issue #31)
        self.jobs = Jobs(cfg, self.lib, on_download_done=self.forget_index)
        self.project_jobs = Jobs(cfg, self.lib, lane=PROJECTS)   # Projects' tasks: a lane of their own (see Jobs)
        # The downloads index: rebuilt outside the lock, one rebuild at a time (review finding P-07). _wanted counts
        # "the downloads changed"; _built_for is the count the current index was built for.
        self._index, self._index_lock = None, threading.Lock()
        self._wanted, self._built_for, self._rebuild = 0, -1, None
        self.updates = updater.Updates(cfg)
        self.schedule = Schedule(cfg, self.jobs)
        previous.set_keep(keep_previous(cfg))
        # What it needs (hoard/needs.py): every downloaded package read once, in the background (started by serve())
        self.needs_index = needs.NeedsIndex()
        self.needs_reader = needs.NeedsReader(self.needs_index, lambda: self.index(stale_ok=True).get("assets", []),
                                              lambda: bool(self.jobs.state.get("running")))
        self.needs_reader.on_read = lambda: rebuild_catalog_quietly(self)
        self._needs = (None, None, None)   # (the index and the read packages' time it was worked out from, {product id: ...})
        self.jobs.find_choices = lambda: {k: len(v) for k, v in self.download_choices(False).items() if k in ("new", "updates")}
        self._by_key = (None, {})       # (asset_by_key's map, and the index it was made from)
        self.vpm = vpm_api.Service()   # Projects (hoard/vpm): the repositories, loaded once
        self.project_jobs.project_runner = lambda what: self.vpm.run(what, self.asset_by_key)

    def lane(self, name) -> Jobs:
        """The jobs of a lane: Projects' (PROJECTS), else the main one."""
        return self.project_jobs if name == PROJECTS else self.jobs

    def lanes(self) -> tuple[Jobs, Jobs]:
        return self.jobs, self.project_jobs

    def working(self) -> bool:
        """Is a task running, or waiting its turn, in either lane? (Closing Hoard asks first.)"""
        return any(jobs.state.get("running") or jobs.state.get("queue") for jobs in self.lanes())

    def tasks(self) -> dict:
        """The Tasks tab, both lanes: what's running in each, what's waiting, and what finished, newest first."""
        main, pj = self.jobs.tasks(), self.project_jobs.tasks()
        history = sorted(main["history"] + pj["history"], key=lambda h: h.get("ended") or "", reverse=True)
        return {"current": main["current"], "project": pj["current"], "queue": main["queue"] + pj["queue"],
                "history": history}

    def asset_by_key(self, key) -> dict | None:
        """A downloaded product, by its tag key (Projects: your library in a project). The keys are looked up in a
        map made once for each index, not by going through every download for each product."""
        if not isinstance(key, str):
            return None
        index = self.index(stale_ok=True)
        made_for, by_key = self._by_key
        if made_for is not index:
            by_key = {}
            for a in index.get("assets", []):
                by_key.setdefault(a.get("tag_key"), a)   # (the first, as before)
            self._by_key = (index, by_key)
        return by_key.get(key)

    def start_schedule(self) -> threading.Event:
        """Automatic syncs, while this server runs (the desktop app starts it). Set the returned event to stop."""
        stop = threading.Event()
        threading.Thread(target=self.schedule.run_forever, args=(stop,), daemon=True, name="schedule").start()
        return stop

    def can_update(self) -> bool:
        """Can Hoard install an update itself? Only the installed Windows app, which can quit to let it run."""
        return self.quit_app is not None and updater.installed_copy()

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
        """The downloads changed: rebuild the index next time it's asked for. Never waits for a rebuild in progress
        (downloads call this after every file)."""
        with self._index_lock:
            self._wanted += 1
        self.needs_reader.poke()   # (it waits for the job to finish before reading anything new)

    def needs_view(self, index: dict) -> dict:
        """What each product in the downloads index needs (hoard/needs.py), worked out again only when the index or
        what's been read changes."""
        # the index itself is kept (not its id): a rebuilt index can be given a freed one's id, and take its answer
        known, at, found = self._needs
        if known is not index or at != self.needs_index.changed_at:
            found = needs.work_out(index.get("assets", []), self.needs_index)
            self._needs = (index, self.needs_index.changed_at, found)
        return found

    def save_settings(self) -> None:
        """Write the settings to config.json (the ones it keeps), one writer at a time."""
        with self.cfg_lock:
            save_config({k: self.cfg[k] for k in DEFAULT_CONFIG if k in self.cfg}, self.config_path)

    def download_choices(self, unlocked: bool) -> dict:
        """What Download new and Update all would get, for you to choose from (issue #107), each product once by its
        tag key: new, things in your library on a store Hoard downloads from with nothing on disk yet; updates, what
        the last check for updates found; and skipped, what you chose to always skip. Removed products are left
        out, as downloading leaves them out, and hidden ones too while the hidden library is locked."""
        srv = self
        on_disk = {a["tag_key"] for a in srv.index(stale_ok=True)["assets"]}
        marks = MarkStore().view()
        updates, skip = AssetUpdates().load()["items"], download_skip(srv.cfg)
        enabled = {s for s in DOWNLOADABLE if srv.cfg[s].get("enabled", True)}
        out_of_view = lambda k: k in marks["removed"] or (k in marks["hidden"] and not unlocked)  # noqa: E731
        known, new = {}, {}
        rules, kept = file_rules(srv.cfg), remembered_files(srv.cfg)   # what's left out, unticked to begin with (#225)
        out = lambda store, key, names: sorted({n for n in names if n in kept.get(key, ()) or ruled_out(rules, store, n)})  # noqa: E731
        for i in srv.lib.snapshot()[0]:
            key = tag_key(i["store"], i["name"])
            if i["store"] not in DOWNLOADABLE or out_of_view(key):
                continue
            known.setdefault(key, {"key": key, "store": i["store"], "name": i["name"], "creator": i.get("creator") or "",
                                   "names": [f["name"] for f in i.get("files") or [] if isinstance(f, dict) and f.get("name")][:500]})
            if i["store"] in enabled and key not in on_disk and key not in skip:
                new.setdefault(key, {**known[key], "out": out(i["store"], key, known[key]["names"])})
        ups = [{"key": k, "store": e["store"], "name": e["name"], "creator": e["creator"], "files": len(e["files"]),
                "names": [f["file"] for f in e["files"]][:500], "out": out(e["store"], k, [f["file"] for f in e["files"]][:500])}
               for k, e in updates.items() if k in on_disk and k not in skip and e["store"] in enabled and not out_of_view(k)]
        skipped = [known.get(k) or {"key": k, "store": k.split(":", 1)[0], "name": k.split(":", 1)[-1], "creator": ""}
                   for k in sorted(skip) if not out_of_view(k)]
        order = lambda e: (e["store"], e["name"].lower())  # noqa: E731
        return {"new": sorted(new.values(), key=order), "updates": sorted(ups, key=order),
                "skipped": sorted(skipped, key=order)}

    def library_view(self) -> list[dict]:
        """The library folders (libraries.view), each with how many downloads it holds, for Settings and the tabs.
        Hidden products aren't counted, so a count never gives them away while the hidden library is locked."""
        counts: dict[int, int] = {}
        try:
            hidden = MarkStore().keys("hidden")
            for a in self.index(stale_ok=True)["assets"]:
                if a.get("tag_key") in hidden:
                    continue
                counts[a.get("library") or 0] = counts.get(a.get("library") or 0, 0) + 1
        except Exception:  # noqa: BLE001 - counts are a nicety; the folders still show
            pass
        return [{**f, "products": counts.get(f["n"], 0)} for f in libraries.view(self.cfg)]

    def index(self, rescan: bool = False, stale_ok: bool = False) -> dict:
        """What's on disk, rebuilt from the records on the first call, after a download, and on every rescan.

        The rebuild runs without holding the lock, one at a time: others who need it fresh wait for that rebuild,
        and with stale_ok a caller gets the index as it was straight away (the library page only needs to know
        what's downloaded). If the downloads change during a rebuild, the next request rebuilds again."""
        root = str(root_dir(self.cfg))
        with self._index_lock:
            if rescan:
                self._wanted += 1
            target = self._wanted
        while True:
            with self._index_lock:
                current = self._index if self._index is not None and self._index.get("root") == root else None
                if current is not None and (self._built_for >= target or stale_ok):
                    return current
                if self._rebuild is None:
                    self._rebuild, building, goal = threading.Event(), True, self._wanted
                else:
                    building, waiting = False, self._rebuild
            if not building:
                waiting.wait(300)
                continue
            fresh = None
            try:
                try:
                    catalog = collect_catalog(self.cfg, Path(root))[0]   # (how far it's got, for the splash: #200)
                    fresh = build_index(Path(root), catalog, libraries.roots(self.cfg, Path(root)),
                                        progress=loading.counter("library", "downloads", len(catalog)))
                except Exception as e:  # show the problem in the page instead of a blank grid
                    fresh = {"root": root, "assets": [], "status": library_status(Path(root)),
                             "error": f"Couldn't read the downloads: {e}"}
            finally:   # whatever happened, the next caller isn't left waiting for this rebuild
                with self._index_lock:
                    if fresh is not None:
                        self._index, self._built_for = fresh, goal
                    done, self._rebuild = self._rebuild, None
                done.set()


class Handler(BaseHTTPRequestHandler):
    timeout = 30   # seconds a connection may sit idle or trickle a request before it's closed
    """Answers the pages' requests."""
    server: AppServer

    def log_message(self, *args):
        """Keep the console quiet: individual requests aren't logged."""

    def _send(self, status, body: bytes, ctype: str, headers: dict | None = None):
        """Send a reply with the security headers; pages get their own policy, everything else is sandboxed."""
        ctype = header_safe(ctype)   # every header is checked for line breaks before anything is sent
        extra = [(header_safe(k), header_safe(v)) for k, v in (headers or {}).items()]
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", content_security_policy(body))
        else:
            self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _unlocked(self) -> bool:
        """Has this browser unlocked the hidden library (and used it within the last UNLOCK_MINUTES)?"""
        srv = self.server
        cookie = self.headers.get("Cookie") or ""
        token = next((c.split("=", 1)[1] for c in (x.strip() for x in cookie.split(";")) if c.startswith("hoard_unlock=")), "")
        now = time.time()
        with srv.unlocks_lock:
            for t in [t for t, until in srv.unlocks.items() if until < now]:
                srv.unlocks.pop(t, None)
            if token and token in srv.unlocks:
                srv.unlocks[token] = now + UNLOCK_MINUTES * 60
                return True
        return False

    def _product_files(self, body: dict) -> dict:
        """Issue #225: what each of these products has on its store, as a quick look at it read it (no file is
        downloaded), each with the files your rules or an earlier choice leave out ("out"), for Hoard to ask which to
        download. A product not read in the last ten minutes is read, with read: true, as a task of its own;
        "reading" says one is under way. names: the files the page knows a product has already ({key: [names]}: an
        update's, or Booth's from your library), answered with what's left out of them, without reading anything."""
        srv = self.server
        keys = [k for k in (body.get("keys") if isinstance(body.get("keys"), list) else [])[:20]
                if isinstance(k, str) and 0 < len(k) <= 400 and ":" in k]
        rules, kept = file_rules(srv.cfg), remembered_files(srv.cfg)
        out = lambda k, names: sorted(n for n in names if n in kept.get(k, ()) or ruled_out(rules, k.split(":", 1)[0], n))  # noqa: E731
        given = body.get("names") if isinstance(body.get("names"), dict) else {}
        now, files = time.monotonic(), {}
        for k in keys:
            got, known = srv.jobs.listed.get(k), given.get(k)
            if got and now - got["at"] < 600:
                files[k] = {"files": got["files"], "read": got["read"], "out": out(k, got["files"])}
            elif isinstance(known, list) and known:
                names = [n for n in known[:500] if isinstance(n, str) and 0 < len(n) <= 500]
                files[k] = {"files": names, "read": False, "out": out(k, names)}
        missing = [k for k in keys if k not in files]
        busy = any(q.get("task") == "list-files" for q in srv.jobs.state["queue"]) or \
            bool(srv.jobs.state.get("running") and srv.jobs.state.get("task") == "list-files")
        if missing and body.get("read") is True and not busy:
            stores = sorted({k.split(":", 1)[0] for k in missing} & set(DOWNLOADABLE))
            busy = bool(stores) and bool(srv.jobs.start("list-files", stores, keys=missing))
        return {"files": files, "reading": bool(missing and busy)}

    def _remember_files(self, chosen: dict | None) -> dict | None:
        """The files you left out of a product, as you chose them to download, kept for its downloads from now on
        (issue #225: Sync, Download new and the routine check leave them out too); one you ticked again is
        forgotten. Returns chosen as it was."""
        if chosen:
            srv = self.server
            with srv.cfg_lock:
                srv.cfg["file_skip"] = remember_choice(remembered_files(srv.cfg), chosen)
                srv.save_settings()
        return chosen

    def _download_choices(self) -> dict:
        return self.server.download_choices(self._unlocked())

    def _hidden_names(self) -> list[str]:
        """The names of hidden products, longest first, while this browser hasn't unlocked the hidden library (so
        they can be taken out of job logs); [] when it has, or nothing is hidden."""
        hidden = MarkStore().keys("hidden")
        if not hidden or self._unlocked():
            return []
        names = {i["name"] for i in self.server.lib.snapshot()[0] if tag_key(i["store"], i["name"]) in hidden}
        return sorted((n for n in names if len(n) >= 3), key=len, reverse=True)

    def _json(self, obj, status=200, compress: bool = False):
        """Send obj as JSON that the browser won't cache. With compress, a large reply is gzipped for a browser that
        accepts it (the library and downloads lists: 5 MB for 10,000 items becomes about 0.2 MB, which matters when
        Hoard is opened from another device). Only for replies that carry no secrets."""
        doing = getattr(self, "_vpm_doing", None)   # (a Projects request: what it couldn't do goes in its log too)
        if doing and status >= 400 and isinstance(obj, dict) and obj.get("error"):
            (vpm_log.warning if status == 409 else vpm_log.error)(f"{doing}: {obj['error']}")
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        headers = {"Cache-Control": "no-store"}
        if compress and len(body) > 64 * 1024 and "gzip" in (self.headers.get("Accept-Encoding") or "").lower():
            body = gzip.compress(body, compresslevel=5)
            headers.update({"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
        self._send(status, body, "application/json; charset=utf-8", headers)

    def _host_ok(self) -> bool:
        """False when a request names a host other than this computer (a DNS-rebinding attempt)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return self.server.lan or host in LOOPBACK

    def _drop_body(self) -> None:
        """Read a small request body that won't be used, before answering without it: Windows resets a connection
        closed with bytes it hasn't read, and the answer can be lost on the way (WinError 10053 for the page)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if 0 < length <= 64 * 1024:   # (a larger one is closed on: not worth reading for a refusal)
            try:
                self.rfile.read(length)
            except OSError:
                pass

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
            srv.accept_language = self.headers.get("Accept-Language")
            return self._send(200, page_source(PAGES[path], srv.cfg, srv.accept_language), "text/html; charset=utf-8",
                              {"Cache-Control": "no-store"})
        if path == "/styleguide":   # every part of the pages, for making and checking them (nothing of yours in it)
            return self._send(200, guide_source(parse_qs(u.query)), "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        if path.startswith("/fonts/"):
            font = font_path(unquote(path[len("/fonts/"):]))
            if not font:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, font.read_bytes(), "font/woff2", {"Cache-Control": "max-age=31536000, immutable"})
        if not check_access(self, srv.key, in_address=path.startswith(("/thumb/", "/files/", "/inside/", "/setpic/", "/setcover/"))):
            return self._refused()
        srv.last_seen = time.time()
        if path == "/api/library":
            items, stores = srv.lib.snapshot()   # enrich() makes new items, so the library's own are never changed
            tagdata = TagStore().load()
            items = enrich(items, srv.cfg["tags"], tagdata, apart=MarkStore().keys("apart"),
                           progress=loading.counter("library", "products", len(items)))   # (counted on the splash: #200)
            on_disk = {a["tag_key"]: a["id"] for a in srv.index(stale_ok=True)["assets"]}   # never waits for a rebuild
            loading.finished("library")
            MarkStore().follow(items)   # a product renamed since it was removed (or hidden...) stays so (issue #224)
            marks, unlocked = MarkStore().view(), self._unlocked()
            updates = AssetUpdates().load()["items"]
            cutoff = new_cutoff(srv.cfg)
            first_read = {s: (info.get("first_read") or "") for s, info in stores.items()}
            shown = []
            for i in items:
                added = i.get("added") or ""
                i["new"] = bool(cutoff and added and added >= cutoff and added > first_read.get(i["store"], ""))
                i["on_disk"] = on_disk.get(i["tag_key"])
                i["update"] = i["on_disk"] is not None and i["tag_key"] in updates   # its store has newer files
                i["mark"] = ("removed" if i["tag_key"] in marks["removed"] else "hidden" if i["tag_key"] in marks["hidden"]
                             else "archived" if is_archived(i, marks) else None)
                i["apart"] = i["tag_key"] in marks["apart"]   # "Not a copy": never stacked (issue #217)
                # hidden items never leave the server while it's locked: hidden by the mark itself, whatever else
                # it's marked (a hidden product also removed is labelled removed, and was let out)
                if i["tag_key"] not in marks["hidden"] or unlocked:
                    shown.append(i)
            counted = [i for i in shown if i["mark"] not in ("removed", "hidden")]
            privacy = {"pin_set": bool(marks["pin"]), "unlocked": unlocked, "recovery_set": bool(marks["recovery"]),
                       "hidden": len({i["tag_key"] for i in shown if i["mark"] == "hidden"}) if unlocked else None}
            keys = {i["tag_key"] for i in shown}
            hidden_now = set() if unlocked else set(marks["hidden"])
            mine = [{"id": x["id"], "name": x["name"], "kind": x.get("kind"), "items": [k for k in x["items"] if k not in hidden_now],
                     "owned": len([k for k in x["items"] if k in keys])} for x in sets.SetStore().load()["sets"]]
            return self._json({"items": shown, "tagset": tag_overview(tagdata, counted), "stores": stores,
                               "privacy": privacy, "sets": mine,
                               "labels": {k: v["label"] for k, v in STORES.items()}, "job": public_job(srv.jobs.state, self._hidden_names()),
                               "downloadable": list(DOWNLOADABLE), "importable": list(IMPORTABLE),
                               "itch_key": vault.has_key(srv.cfg, "itch"),
                               # which stores Hoard holds a sign-in for, so Stores offers Sign in or Sign out, not both
                               "signed_in": {s: signed_in(srv.cfg, s) for s in STORES if srv.cfg[s].get("enabled", True)},
                               "signins": str(signins_root(srv.cfg)), "signins_note": signin_protection(srv.cfg),
                               "store_sites": store_sites(), "version": __version__,
                               "enabled": {s: bool(srv.cfg[s].get("enabled", True)) for s in STORES},
                               "setup_done": bool(srv.cfg.get("setup_done")), "can_quit": srv.quit_app is not None, "can_background": srv.hide_window is not None, "can_notify": srv.can_notify, "can_pick": srv.pick_path is not None,
                               "display": display_settings(srv.cfg), "ui": ui_settings(srv.cfg),
                               "ask_files": bool(srv.cfg.get("ask_files", True)),   # (issue #225)
                               "routine": routine_record()["found"]}, compress=True)
        if path == "/api/download-choices":   # issue #107: what downloading new things, or updating, would get
            return self._json(self._download_choices(), compress=True)
        if path == "/api/tasks":   # the Tasks tab: running, waiting and finished jobs
            tasks, hidden = srv.tasks(), self._hidden_names()
            if hidden:
                def mask(job):
                    return {**job, **public_job({k: job.get(k) for k in ("message", "log", "report", "label", "transfer") if k in job}, hidden)}
                tasks = {"current": mask(tasks["current"]) if tasks["current"] else None,
                         "project": mask(tasks["project"]) if tasks["project"] else None,
                         "queue": [mask(q) for q in tasks["queue"]], "history": [mask(h) for h in tasks["history"]]}
            return self._json(tasks, compress=True)
        if path == "/api/loading":   # issue #200: how far reading what a page shows first has got, for its splash
            return self._json(loading.view((parse_qs(u.query).get("part") or [""])[0]))
        if path == "/api/status":
            return self._json({"job": public_job(srv.jobs.state, self._hidden_names()), "stores": srv.lib.snapshot()[1],
                               "project_job": public_job(srv.project_jobs.state, self._hidden_names()),
                               "routine": routine_record()["found"]})
        if path == "/api/assets":
            index = with_tags(srv.index(rescan="rescan" in parse_qs(u.query)))
            loading.finished("library")   # (the splash's count: issue #200)
            # each download carries its product's mark from the Library (archived, removed, hidden), so the Downloads
            # page has the same views (issue #29); hidden products' downloads stay out of view while it's locked
            marks, unlocked = MarkStore().view(), self._unlocked()
            by_store = {tag_key(i["store"], i["name"]) for i in srv.lib.snapshot()[0] if i.get("archived")}
            updates = AssetUpdates().load()   # what the last check for updates found (issue #26)
            used = projects.used_in(self._visible_projects())   # the Unity projects using each (issue #86)
            stacks, looks = {}, []   # copies of one product stack here as in the Library: by its products (hoard/library.py)
            listed = [dict(i) for i in srv.lib.snapshot()[0]]
            store_tags = {tag_key(i["store"], i["name"]): i["store_tags"] for i in listed if i.get("store_tags")}   # (#206)
            tagdata = TagStore().load()   # (for each product's type, as the Library has it: issue #223)
            stack_by_picture(listed, apart=marks["apart"])
            for i in listed:
                # a download's stack is its own product's (by store and name), even one that stacks with nothing:
                # "Hair Pack 1" and "Hair Pack 2" share a product key (tag_key leaves numbers out), but the Library
                # keeps them apart, and so must Disk space's copies. The key is for downloads the library doesn't list
                stacks.setdefault((str(i["store"]).lower(), i["name"]), i["stack_key"])
                if i["stack_key"]:
                    stacks.setdefault(tag_key(i["store"], i["name"]), i["stack_key"])
                if i.get("look_for") and (unlocked or tag_key(i["store"], i["name"]) not in marks["hidden"]):
                    looks.append({"look_for": i["look_for"], "key": i["key"]})   # (its picture: /thumb/<key>)
            assets = []
            needed = srv.needs_view(index)
            from . import local
            chosen = local.chosen_folders(root_dir(srv.cfg))   # Local items with a picture you chose
            for a in index["assets"]:
                key = a.get("tag_key")
                mark = ("removed" if key in marks["removed"] else "hidden" if key in marks["hidden"]
                        else "archived" if is_archived({"tag_key": key, "archived": key in by_store}, marks) else None)
                if key not in marks["hidden"] or unlocked:   # (hidden, whatever else it's marked)
                    kind, known = product_type(tagdata, key, a["name"], a.get("tags") or [], store_tags.get(key, []))
                    assets.append({**a, "mark": mark, "update": (updates["items"].get(key) or {}).get("files", []),
                                   "store_tags": store_tags.get(key, []), "type": kind, "type_from": known,
                                   "stack_key": stacks.get((str(a["store"]).lower(), a["name"]), stacks.get(key, "")),
                                   "needs": needed.get(a["id"]),
                                   "own_picture": a.get("catalog_folder") in chosen,
                                   "used_in": used.get(a.get("catalog_folder") or a.get("folder"), [])})
            shown = {a["id"] for a in assets}   # a hidden product isn't named as one another needs while it's locked
            keys = {a["tag_key"] for a in assets}   # nor kept in a set while it's locked
            grouped = [{**s, "items": [k for k in s["items"] if k in keys]} for s in sets.SetStore().load()["sets"]]
            for a in assets:
                if a["needs"]:
                    a["needs"] = {**a["needs"], "products": [o for o in a["needs"]["products"] if o["id"] in shown]}
            index = {**index, "assets": assets, "privacy": {"pin_set": bool(marks["pin"]), "unlocked": unlocked}, "looks_wanted": looks[:500],
                     "libraries": srv.library_view(),
                     "updates_checked": updates["checked"], "integrity": integrity_view(srv.cfg),
                     "needs_reading": dict(srv.needs_reader.state), "sets": grouped}
            return self._json({**index, "version": __version__, "job": public_job(srv.jobs.state, self._hidden_names()), "store_sites": store_sites(),
                               "can_quit": srv.quit_app is not None, "can_background": srv.hide_window is not None, "can_notify": srv.can_notify, "can_pick": srv.pick_path is not None, "display": display_settings(srv.cfg), "ask_files": bool(srv.cfg.get("ask_files", True)),
                               "ui": ui_settings(srv.cfg), "routine": routine_record()["found"]}, compress=True)
        if path == "/api/projects":   # the Unity projects that use your assets (issue #86)
            found = self._visible_projects()
            updates = AssetUpdates().load()["items"]
            return self._json({"projects": projects.view(found, srv.index(stale_ok=True), updates),
                               "hidden_left_out": not self._unlocked() and bool(MarkStore().keys("hidden"))}, compress=True)
        if path.startswith("/api/vpm"):   # Projects (hoard/vpm)
            return self._vpm_logged(path, self._vpm_get, parse_qs(u.query))
        if path == "/api/space":   # Downloads, Disk space: the same file kept more than once (hoard/space.py)
            hidden = frozenset() if self._unlocked() else frozenset(MarkStore().keys("hidden"))
            with srv.cfg_lock:
                roots = libraries.roots(srv.cfg, root_dir(srv.cfg))
            return self._json({**space.copies(roots, hidden), "projects": len(self._visible_projects())}, compress=True)
        if path == "/api/settings":
            return self._json({**public_settings(srv.cfg), "libraries": srv.library_view()})
        if path == "/api/folders":   # Settings' Hoard's folders: every one it uses, where it is, and whether it's there
            return self._json({"folders": self._places()})
        if path == "/api/update":
            return self._json(srv.updates.view(srv.can_update()))
        if path == "/api/changelog":   # What's new, in the app: betas too when asked for (?betas=1)
            betas = parse_qs(u.query).get("betas", [""])[0] == "1"
            return self._json({"version": __version__, "releases": whats_new(betas)}, compress=True)
        if path == "/api/setup":
            return self._json({**setup_status(srv.cfg), "job": public_job(srv.jobs.state, self._hidden_names()),
                               "close_to_taskbar": bool(srv.cfg.get("close_to_taskbar", True))})
        if path == "/api/sets":   # the Sets tab: every set, each product as it is here (hoard/sets.py)
            return self._json(self._sets_view(), compress=True)
        if path.startswith("/setpic/"):   # a set's product's picture, from its store, when it isn't in your library
            sid, _, n = path[len("/setpic/"):].partition("/")
            s = next((x for x in sets.SetStore().load()["sets"] if x["id"] == sid), None)
            key = s["items"][int(n)] if s and n.isdigit() and int(n) < len(s["items"]) else None
            if key and parse_qs(u.query).get("p", [""])[0] != pic_for(key):
                key = None   # an address from before a product was taken out: that place is another product's now
            p = (s.get("products") or {}).get(key) if key else None
            hidden = key in MarkStore().keys("hidden") and not self._unlocked()
            url = sets.product_picture(p["store"], p.get("thumbnail")) if p and not hidden else None
            got = fetch_picture(url, STORES[p["store"]]["referer"]) if url and p["store"] in STORES else None
            if not got:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})
        if path.startswith("/setcover/"):   # the picture you chose for a set's tile
            sid, _, name = path[len("/setcover/"):].partition("/")
            s = next((x for x in sets.SetStore().load()["sets"] if x["id"] == sid), None)
            f = sets.picture_file(s) if s and s.get("picture") == name else None
            try:
                data = f.read_bytes() if f else None
            except OSError:
                data = None
            if not data:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, data, SERVED_IMAGE_TYPES["." + name.rsplit(".", 1)[1]],
                              {"Cache-Control": "max-age=86400"})
        if path.startswith("/inside/"):   # a preview from inside a package (Look inside: hoard/packages.py)
            cid, _, name = path[len("/inside/"):].partition("/")
            data = packages.preview(cid, name)
            if data is None:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, data, "image/png", {"Cache-Control": "max-age=86400"})
        if path.startswith("/thumb/"):
            got = fetch_thumbnail(unquote(path[len("/thumb/"):]), srv.lib)
            if not got:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, got[0], got[1], {"Cache-Control": "max-age=86400"})
        if path.startswith("/files/"):
            # a picture in the downloads folder, or in another library folder ("@1/Booth/...": hoard/libraries.py),
            # whose number names one of Hoard's own folders, never a path from the request
            found = libraries.resolve(srv.cfg, unquote(path[len("/files/"):]))
            if not found:
                return self._send(404, b"Not found", "text/plain")
            root = found[0]
            rel = contained_rel(root, found[1])   # plain, and inside that library folder
            ctype = SERVED_IMAGE_TYPES.get(Path(rel).suffix.lower()) if rel else None
            if not rel or not ctype or not safe_join(root, rel):   # safe_join: no link out of the folder either
                return self._send(404, b"Not found", "text/plain")
            try:   # opened without following any link below the downloads folder; what's served is what was opened
                with open_under(root, rel) as fh:
                    data = fh.read(MAX_SERVED_IMAGE + 1)
            except (UnsafePath, OSError):
                return self._send(404, b"Not found", "text/plain")
            if len(data) > MAX_SERVED_IMAGE:
                return self._send(404, b"Not found", "text/plain")
            return self._send(200, data, ctype, {"Cache-Control": "max-age=3600"})
        self._send(404, b"Not found", "text/plain")

    def _library_folders(self, path: str, body: dict):
        """Add a library folder (one that's there, checked by libraries.check_new_folder), or forget one: its files
        stay where they are, and leave Hoard's library until it's added again. Not while a job runs, which may be
        using it."""
        srv = self.server
        if srv.jobs.state.get("running") or srv.jobs.state.get("queue"):
            return self._json({"error": "Wait for Hoard to finish what it's doing, then try again."}, 409)
        folders = [str(f) for f in libraries.other_folders(srv.cfg)]
        try:
            if path == "/api/libraries/add":
                folders.append(str(libraries.check_new_folder(srv.cfg, str(body.get("path") or "")[:1000])))
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
            build_catalog(srv.cfg, root_dir(srv.cfg))   # catalog.json (and Hoard for Unity) follow straight away
        except OSError as e:
            print(f"Couldn't rebuild the catalog: {e}", flush=True)
        srv.forget_index()
        return self._json({"ok": True, "libraries": srv.library_view()})

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
                # each product's own key on its store, so the choice stays with it if the store renames it
                ids = {i["key"]: k for i in srv.lib.snapshot()[0] if (k := tag_key(i["store"], i["name"])) in keys} if on else {}
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
                token = secrets.token_urlsafe(32)
                with srv.unlocks_lock:
                    srv.unlocks[token] = time.time() + UNLOCK_MINUTES * 60
                secure = "; Secure" if getattr(srv, "tls", False) else ""
                data = json.dumps({"ok": True}).encode()
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
        except PinError as e:
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
            lib.setdefault(tag_key(i["store"], i["name"]), i)
        for a in srv.index(stale_ok=True)["assets"]:
            dl.setdefault(a["tag_key"], a)

        def public(store: str, *links) -> str | None:   # its own public page, else its creator's: never one of yours
            return next((u for u in (sets.product_link(store, x) for x in links) if u), None)

        def details(key: str) -> dict | None:
            i = lib.get(key)
            if i:
                return {"store": i["store"], "id": i.get("id"), "name": i["name"], "creator": i.get("creator"),
                        "url": public(i["store"], i.get("page"), i.get("url"), i.get("creator_url")),
                        "thumbnail": i.get("thumbnail")}
            a = dl.get(key)
            if a:
                store = str(a["store"]).lower()
                return {"store": store, "name": a["name"], "creator": a.get("creator"), "url": public(store, a.get("url"))}
            return None
        return details

    def _sets_view(self) -> dict:
        """Every set, for the Sets tab: each product with what it is here: in your library (owned), downloaded (its
        download's id), or neither (where to buy it), with a picture to show for it. Hidden products are left out
        while the hidden library is locked."""
        srv = self.server
        marks, unlocked = MarkStore().view(), self._unlocked()
        hidden = set() if unlocked else set(marks["hidden"])
        lib = {}
        for i in srv.lib.snapshot()[0]:
            lib.setdefault(tag_key(i["store"], i["name"]), i)
        dl = {}
        for a in srv.index(stale_ok=True)["assets"]:
            dl.setdefault(a["tag_key"], a)
        out, left_out = [], False
        for s in sets.SetStore().load()["sets"]:
            known, rows = s.get("products") or {}, []
            for n, key in enumerate(s["items"]):
                if key in hidden:
                    left_out = True
                    continue
                i, a, p = lib.get(key), dl.get(key), known.get(key) or {}
                store = (i or {}).get("store") or p.get("store") or (str(a["store"]).lower() if a else "")
                if i and i.get("thumbnail"):
                    pic = "/thumb/" + quote(i["key"], safe=":")
                elif a and a.get("thumb"):
                    pic = "/files/" + quote(a["thumb"]) + (f"?v={a['thumb_v']}" if a.get("thumb_v") else "")
                elif p.get("thumbnail"):   # (with the product it's for: a place in the list is another's once one goes)
                    pic = f"/setpic/{s['id']}/{n}?p={pic_for(key)}"
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
                             **{k: p[k] for k in ("price", "was", "elsewhere") if p.get(k)}})   # on a wishlist: what it
                                                                                                # costs, and its page elsewhere
            if s.get("kind") == "wishlist":   # suggested tags, from words its products' names share, to narrow it down
                block = {str(w).lower() for w in (srv.cfg.get("tags") or {}).get("blocklist", [])}
                for row, words in zip(rows, common_words([r["name"] for r in rows], 2, 0.5, block)):
                    row["words"] = sorted(words)
            out.append({"id": s["id"], "name": s["name"], "note": s.get("note", ""), "photos": s.get("photos", []),
                        "cover": f"/setcover/{s['id']}/{s['picture']}" if sets.picture_file(s) else None,
                        "short": (s.get("short") or {}).get("expires"), "items": rows,
                        **({"kind": "wishlist", "source": s.get("source"), "read": s.get("read")} if s.get("kind") == "wishlist" else {})})
        return {"sets": out, "hidden_left_out": left_out, "viewer": sets.VIEWER, "photo_hosts": list(sets.PHOTO_HOSTS)}

    def _add_links(self, sid: str, links):
        """Products added to a wishlist by their store links (at most 30): each one's public page read
        (wishlists.from_product_page), what was added and what wasn't, and why. A set is made from what's in your
        library, so it isn't added to by link (issue #208)."""
        from . import wishlists
        if not isinstance(links, list) or not links:
            return self._json({"error": "Paste a product's link."}, 400)
        found = next((x for x in sets.SetStore().load()["sets"] if x["id"] == sid), None)
        if not found:
            return self._json({"error": "That set isn't there anymore."}, 404)
        if found.get("kind") != "wishlist":
            return self._json({"error": "Products are added by link to wishlists. A set is made from what's in your library."}, 400)
        got, said = [], []
        for link in [str(x)[:2000] for x in links[:30]]:
            try:
                p = wishlists.from_product_page(link, read_store_page)
            except wishlists.LinkError as e:
                said.append({"link": link[:200], "error": str(e)})
                continue
            got.append(p)
            said.append({"link": link[:200], "added": p["name"]})
        try:
            if got:
                sets.SetStore().add_products(sid, got)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        threading.Thread(target=rebuild_catalog_quietly, args=(self.server,), daemon=True).start()
        return self._json({"ok": True, "links": said})

    def _set_code(self, sid: str):
        """A set and its share code: (set, code, how many products are in it), or a Response saying why not. Hidden
        products and your own (Local) are never in one."""
        s = next((x for x in sets.SetStore().load()["sets"] if x["id"] == sid), None)
        if s is None:
            return self._json({"error": "That set isn't there anymore."}, 400)
        hidden = MarkStore().keys("hidden")
        code, count = sets.share_code({**s, "items": [k for k in s["items"] if k not in hidden]}, self._product_details())
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
        short = shortlinks.code(rec["id"], rec["key"])
        return {"link": sets.share_link(short), "code": short, "expires": rec["expires"],
                "changed": rec["made"] != sets.code_mark(code), "days": shortlinks.LIFETIME_DAYS}

    def _share_set(self, sid: str):
        """A set's share code (hoard/sets.py), for the page to lock for its short link, and that link, if it has one.
        The code's own long link isn't offered: a set is shared only by a short link (issue #162)."""
        got = self._set_code(sid)
        if not isinstance(got, tuple):
            return got
        s, code, count = got
        fits, more = shortlinks.fits(code), {}
        if not fits:
            try:
                more = {"parts": len(self._share_parts(s))}
            except ValueError as e:   # a product too big on its own: no split makes it fit, so say so (issue #178)
                more = {"parts": 0, "why": str(e)}
        return self._json({"ok": True, "code": code, "count": count,
                           "left_out": len(s["items"]) - count, "short": self._short_view(s.get("short"), code),
                           "short_days": shortlinks.LIFETIME_DAYS, "fits": fits, **more})

    def _share_parts(self, s: dict) -> list[list[str]]:
        """A set's products in parts that each fit a short link (sets.share_parts), hidden ones left out of the
        sizes, as they're left out of what's shared."""
        return sets.share_parts(s, self._product_details(), leave_out=MarkStore().keys("hidden"))

    def _extract(self, body: dict):
        """Look inside's Extract (packages.extract): the chosen files of a downloaded .unitypackage or .zip, or all of
        them, into a new folder named after it in Extracted, in the folder for editable copies (never in a library
        folder, so Hoard's checks leave them alone); then that folder opened, when asked."""
        srv = self.server
        target = open_target(srv.cfg, str(body.get("path", "")))
        if not target or not packages.can_look_inside(target.name) or not target.is_file():
            return self._json({"error": "That file isn't on disk anymore."}, 404)
        if self._hidden_file(target):
            return self._json({"error": "Unlock your hidden library first."}, 403)
        picks = body.get("picks")
        if not isinstance(picks, list) or not picks or len(picks) > 100_000 or \
                not all(isinstance(p, str) and len(p) <= 2100 for p in picks):
            return self._json({"error": "Choose what to take out first."}, 400)
        try:
            base = edits_root(srv.cfg, root_dir(srv.cfg)) / "Extracted"
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        name, n = safe_name(target.name.rsplit(".", 1)[0], 80), 1
        try:
            base.mkdir(parents=True, exist_ok=True)
            while True:   # (made here, not just looked for: two at once never share one, nor delete the other's)
                dest = base / (name if n == 1 else f"{name} ({n})")
                try:
                    dest.mkdir()
                    break
                except FileExistsError:
                    n += 1
        except OSError as e:
            return self._json({"error": f"Couldn't make a folder in {base}: {e.strerror or e}."}, 500)
        try:
            done = packages.extract(target, dest, picks, metas=body.get("metas") is True)
        except (packages.CantExtract, packages.NotAPackage, OSError) as e:
            rmtree(dest, ignore_errors=True)   # (what was taken out before it stopped goes with it)
            said = str(e) if isinstance(e, packages.CantExtract) else (f"Couldn't take them out: {e.strerror or e}."
                                                                       if isinstance(e, OSError) else "That file couldn't be read.")
            return self._json({"error": said}, 400 if isinstance(e, packages.CantExtract) else 500)
        if not done["files"] and done["skipped"]:   # nothing at all came out: say why, not an empty folder (#174)
            rmtree(dest, ignore_errors=True)
            return self._json({"error": "Nothing could be taken out.",
                               "skipped": [{"name": n, "why": w} for n, w in done["skipped"]]}, 400)
        print(f"Took {done['files']} files out of {target.name} into {dest}"
              + (f" ({len(done['skipped'])} left out)" if done["skipped"] else ""), flush=True)
        opened = None
        if body.get("open"):
            try:
                opened = reveal(dest)
            except OSError:
                pass
        return self._json({"ok": True, "folder": str(dest), "files": done["files"], "bytes": done["bytes"],
                           "skipped": [{"name": n, "why": w} for n, w in done["skipped"]], "opened_in": opened})

    def _split_set(self, sid: str):
        """Split into...: a set too big for one short link, as new sets that each fit (sets.SetStore.split). The set
        stays as it is."""
        try:   # (its parts worked out under the sets' lock, from what it holds then: issue #179)
            data = sets.SetStore().split(sid, self._share_parts)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        threading.Thread(target=rebuild_catalog_quietly, args=(self.server,), daemon=True).start()   # (Unity's Import set)
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
        if not isinstance(key, str) or not shortlinks.KEY.fullmatch(key):
            return self._json({"error": "That short link can't be kept."}, 400)
        rec = None
        try:
            if old and old["key"] == key:
                try:
                    rec = {**old, "expires": shortlinks.replace(old["id"], old["token"], data)}
                except shortlinks.Gone:
                    pass   # (it ran out on the server first: a new one, with the same key)
            if rec is None:
                made = shortlinks.make(data)
                rec = {"id": made["id"], "key": key, "token": made["token"], "expires": made["expires"]}
        except shortlinks.ShortLinkError as e:
            return self._json({"error": str(e)}, 502)
        rec["made"] = sets.code_mark(code)
        try:
            sets.SetStore().set_short(sid, rec)
        except ValueError as e:   # (the set was deleted meanwhile: its new link goes too)
            try:
                shortlinks.delete(rec["id"], rec["token"])
            except shortlinks.ShortLinkError:
                pass
            return self._json({"error": str(e)}, 400)
        if old and old["id"] != rec["id"]:   # (a key that wasn't its link's: the old link goes)
            try:
                shortlinks.delete(old["id"], old["token"])
            except shortlinks.ShortLinkError:
                pass
        return self._json({"ok": True, "short": self._short_view(rec, code)})

    def _unshorten_set(self, sid: str):
        """Delete a set's short link now: from the server, then from the set."""
        s = next((x for x in sets.SetStore().load()["sets"] if x["id"] == sid), None)
        if s is None:
            return self._json({"error": "That set isn't there anymore."}, 400)
        if s.get("short"):
            try:
                shortlinks.delete(s["short"]["id"], s["short"]["token"])
            except shortlinks.ShortLinkError as e:
                return self._json({"error": str(e)}, 502)
            try:
                sets.SetStore().set_short(sid, None)
            except ValueError:   # (the set was deleted meanwhile: its link is gone either way)
                pass
        return self._json({"ok": True})

    def _visible_projects(self) -> list[dict]:
        """Projects' reports, without hidden products while the hidden library is locked (their names never leave
        the server then, here as everywhere)."""
        found = projects.read_all()
        if self._unlocked():
            return found
        hidden = MarkStore().keys("hidden")
        if not hidden:
            return found
        return [{**p, "assets": [a for a in p["assets"] if tag_key(a["store"], a["name"]) not in hidden]} for p in found]

    def _local(self, path: str, body: dict):
        """Local: add a folder or file of your own (a task, since copying can take a while), rescan one listed where
        it is, or take one out."""
        from . import local
        srv = self.server
        if path == "/api/local/preview":   # issue #109: the packages a folder of folders would add
            try:
                plan = local.split(root_dir(srv.cfg), str(body.get("path") or "")[:1000], body.get("depth"),
                                   body.get("copy") is not False)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"packages": [{k: p[k] for k in ("rel", "name", "creator", "added")} for p in plan["packages"]],
                               "loose": plan["loose"]})
        if path == "/api/local/add":
            copy = body.get("copy") is not False
            depth = body.get("depth") if body.get("depth") in local.DEPTHS and not isinstance(body.get("depth"), bool) else 0
            what = {"path": str(body.get("path") or "")[:1000], "name": str(body.get("name") or "")[:300],
                    "creator": str(body.get("creator") or "")[:200], "note": str(body.get("note") or "")[:300], "copy": copy,
                    "depth": depth}
            try:   # said straight away, not in Tasks
                if depth:
                    local.split(root_dir(srv.cfg), what["path"], depth, copy)
                else:
                    local.check_source(root_dir(srv.cfg), what["path"], copy)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            if srv.cfg.get("local_copy", True) != copy:   # the choice you made last time is offered next time
                srv.cfg["local_copy"] = copy
                srv.save_settings()
            started = srv.jobs.start("add-local", [], local=what)
            if not started:
                return self._json({"error": "That's already waiting its turn."}, 409)
            return self._json({"ok": True, "queued": started == "queued"})
        found = local.by_folder(root_dir(srv.cfg), str(body.get("folder") or "")[:1000])
        if not found:
            return self._json({"error": "That isn't in Local any more."}, 404)
        if path == "/api/local/picture":   # a picture of your choosing for its tile, or back to one of its own
            if srv.jobs.state["running"] and srv.jobs.state.get("task") in ("add-local", "rescan-local", "remove-local",
                                                                            "move"):
                return self._json({"error": "Wait for Hoard to finish with Local, then try again."}, 409)
            try:
                local.choose_picture(srv.cfg, root_dir(srv.cfg), found[0], body.get("image"))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except OSError as e:
                return self._json({"error": f"Couldn't save the picture: {e.strerror or e}."}, 500)
            srv.forget_index()
            return self._json({"ok": True})
        if path == "/api/local/remove" and body.get("confirm") is not True:
            return self._json({"error": "Confirm first."}, 400)
        if not srv.jobs.busy.acquire(blocking=False):   # a job is running: this waits its turn after it
            task = "rescan-local" if path == "/api/local/rescan" else "remove-local"
            return self._queued(srv.jobs.start(task, [], files={"folder": str(body.get("folder"))[:1000],
                                                                "name": found[1].get("name")}))
        try:
            if path == "/api/local/rescan":
                rec = local.rescan(srv.cfg, root_dir(srv.cfg), found[0])
                done = {"files": len(rec["files"])}
            else:
                done = local.remove(srv.cfg, root_dir(srv.cfg), found[0])
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        finally:
            srv.jobs.busy.release()
            srv.jobs.kick()
        srv.forget_index()
        return self._json({"ok": True, **done})

    # ---- Projects (hoard/vpm): the Creator Companion's and ALCOM's projects, with your library in them

    def _hidden_key(self, key) -> bool:
        return isinstance(key, str) and key in MarkStore().keys("hidden") and not self._unlocked()

    def _hidden_file(self, target: Path) -> bool:
        """Whether a file is in a hidden product's folder while the hidden library is locked (issue #171): Look inside
        and Extract refuse it, as Make an editable copy does. Folders are compared as they resolve, so another
        spelling of the same path is the same file."""
        hidden = MarkStore().keys("hidden")
        if not hidden or self._unlocked():
            return False
        try:
            real = target.resolve()
        except OSError:
            return True
        for a in self.server.index(stale_ok=True)["assets"]:
            if a.get("tag_key") not in hidden:
                continue
            folder = open_target(self.server.cfg, a.get("folder") or "")
            try:
                if folder and (real == folder.resolve() or folder.resolve() in real.parents):
                    return True
            except OSError:
                return True
        return False

    def _places(self) -> list[dict]:
        """Every folder Hoard uses (places.py), Projects' too when the Creator Companion's settings can be read."""
        try:
            vpm_settings = self.server.vpm.settings()
        except vpm_api.ProjectsError:
            vpm_settings = None
        return places.places(self.server.cfg, vpm_settings)

    def _vpm_logged(self, path: str, handle, arg):
        """A Projects request: what it couldn't do is said in Projects' log too (by _json), as ALCOM's log says it."""
        self._vpm_doing = VPM_ACTIONS.get(path)
        try:
            return handle(path, arg)
        except Exception as e:
            if self._vpm_doing:
                vpm_log.error(f"{self._vpm_doing}: {type(e).__name__}: {e}")
            raise
        finally:
            self._vpm_doing = None

    def _vpm_get(self, path: str, query: dict):
        srv = self.server
        one = lambda k: (query.get(k) or [""])[0][:2000]  # noqa: E731
        try:
            if path == "/api/vpm":
                try:
                    return self._json({**srv.vpm.overview(), "job": public_job(srv.project_jobs.state, self._hidden_names())},
                                      compress=True)
                finally:
                    loading.finished("projects")
            if path == "/api/vpm/logs":   # Projects' log: this run's entries after the one numbered after
                after = one("after")
                return self._json({"run": vpm_log.book.run, "entries": vpm_log.book.entries(int(after) if after.isdigit() else 0),
                                   "file": vpm_log.book.file.name if vpm_log.book.file else None})
            if path == "/api/vpm/project":
                found = srv.vpm.project(one("path"))
                report = next((r for r in projects.read_all() if r.get("path") and os.path.normcase(os.path.normpath(r["path"]))
                               == os.path.normcase(os.path.normpath(found["path"]))), None)
                if report is not None:   # what Hoard for Unity reported: the products it uses, and its credits
                    updates = AssetUpdates().load()["items"]
                    report = projects.view([r for r in self._visible_projects() if r["id"] == report["id"]],
                                           srv.index(stale_ok=True), updates)
                    report = report[0] if report else None
                hidden = set() if self._unlocked() else set(MarkStore().keys("hidden"))
                found["preloaded"] = [x for x in found["preloaded"] if x.get("tag_key") not in hidden]
                return self._json({**found, "report": report}, compress=True)
            if path == "/api/vpm/packages":
                return self._json({"packages": srv.vpm.packages(one("unity"), one("pre") == "1")}, compress=True)
            if path == "/api/vpm/versions":
                return self._json({"versions": srv.vpm.versions(one("name"), one("unity"), one("pre") == "1", one("keep"))},
                                  compress=True)
            if path == "/api/vpm/product":
                key = one("key")
                asset = srv.asset_by_key(key)
                if asset is None:
                    return self._json({"error": "That isn't downloaded."}, 404)
                if self._hidden_key(key):
                    return self._json({"error": "Unlock your hidden library first."}, 403)
                index = srv.index(stale_ok=True)
                return self._json(srv.vpm.product(asset, srv.needs_view(index).get(asset["id"]), one("path") or None))
        except vpm_api.ProjectsError as e:
            return self._json({"error": str(e)}, 400)
        return self._send(404, b"Not found", "text/plain")

    def _vpm_job(self, what: dict):
        started = self.server.project_jobs.start("project", [], project=what)
        if not started:
            return self._json({"error": "That's already waiting its turn."}, 409)
        return self._json({"ok": True, "queued": started == "queued"})

    def _vpm_post(self, path: str, body: dict):
        from .vpm import imports as vpm_imports, listing, presets as vpm_presets, templates as vpm_templates, unity as vpm_unity
        from .vpm.project import is_project
        srv = self.server
        try:
            if path == "/api/vpm/preview":
                return self._json(srv.vpm.preview(body))
            if path in ("/api/vpm/apply", "/api/vpm/backup", "/api/vpm/preload"):
                srv.vpm.listed(body.get("path"))
                what = {"op": {"/api/vpm/apply": "change", "/api/vpm/backup": "backup", "/api/vpm/preload": "preload"}[path],
                        "path": body["path"], "name": Path(body["path"]).name}
                if path == "/api/vpm/apply":
                    what.update({k: body.get(k) for k in ("add", "remove", "repair", "upgrade_all", "prerelease")})
                elif path == "/api/vpm/backup":
                    what["leave_out_packages"] = body.get("leave_out_packages") is True
                else:
                    what["picks"] = self._picks(body.get("picks"))
                return self._vpm_job(what)
            if path == "/api/vpm/create":
                location, name = str(body.get("location") or "")[:1000], str(body.get("name") or "")[:255]
                problem, _ = vpm_templates.check_name(Path(location), name) if location else ("Choose where it goes.", None)
                if problem:
                    return self._json({"error": problem}, 400)
                return self._vpm_job({"op": "create", "name": name, "location": location,
                                      "template": str(body.get("template") or "")[:200],
                                      "unity": str(body.get("unity") or "")[:40],
                                      "packages": body.get("packages") if isinstance(body.get("packages"), dict) else {},
                                      "picks": self._picks(body.get("picks"))})
            if path == "/api/vpm/refresh":
                return self._vpm_job({"op": "refresh", "name": "repositories"})
            # the backups panel (vpm/backup.py): old ones deleted, or moved to a drive with more room
            if path == "/api/vpm/backups":
                return self._json({"ok": True, **srv.vpm.backups()})
            if path == "/api/vpm/backups/settings":
                from .vpm import backup as vpm_backup
                changes = {}
                if body.get("keep") in vpm_backup.KEEP_CHOICES:
                    changes["keep"] = body["keep"]
                if body.get("days") in vpm_backup.DAYS_CHOICES:
                    changes["days"] = body["days"]
                listing.set_backup_prefs(**changes)
                return self._json({"ok": True, **srv.vpm.backups()})
            if path == "/api/vpm/backups/show":
                folder = srv.vpm.backups_folder()
                folder.mkdir(parents=True, exist_ok=True)
                return self._json({"ok": True, "in": reveal(folder)})
            if path == "/api/vpm/backups/delete":
                from .vpm import backup as vpm_backup
                count, freed = vpm_backup.delete(srv.vpm.backups_chosen(body.get("paths")))
                if count:
                    vpm_log.info(f"Deleted {vpm_log.count(count, 'backup')}, freeing {vpm_log.size_text(freed)}")
                return self._json({"ok": True, "deleted": count, "freed": freed})
            if path == "/api/vpm/backups/move":
                paths = srv.vpm.backups_chosen(body.get("paths"))
                to = str(body.get("to") or "").strip()[:1000]
                if not paths:
                    return self._json({"error": "Choose the backups to move."}, 400)
                if not to or not Path(to).is_absolute():
                    return self._json({"error": "Choose a folder to move them to, by its full path."}, 400)
                return self._vpm_job({"op": "move-backups", "paths": [str(p) for p in paths], "to": to,
                                      "name": f"{len(paths)} {'backup' if len(paths) == 1 else 'backups'}"})
            if path == "/api/vpm/check-name":
                problem, warning = vpm_templates.check_name(Path(str(body.get("location") or "")[:1000]), str(body.get("name") or "")[:300])
                return self._json({"problem": problem, "warning": warning})
            if path == "/api/vpm/open":
                found = srv.vpm.project(str(body.get("path") or ""))
                if found["open_in_unity"]:
                    return self._json({"error": "Unity already has this project open."}, 409)
                wanted = body.get("editor") if isinstance(body.get("editor"), str) else (found["editor"] or {}).get("path")
                editor = next((e["path"] for e in found["editors"] if e["path"] == wanted), None)   # (Hoard's own copy)
                if not editor:
                    return self._json({"error": f"Unity {found['unity']} isn't installed. Install it with Unity Hub, or "
                                                "choose another version to open it in."}, 400)
                vpm_unity.open_project(Path(editor), Path(found["path"]))
                listing.note(found["path"], opened=time.strftime("%Y-%m-%dT%H:%M:%S"))
                version = next((e["version"] for e in found["editors"] if e["path"] == editor), found["unity"])
                vpm_log.info(f"Opened {found['name']} in Unity {version}")
                return self._json({"ok": True})
            if path == "/api/vpm/open-folder":
                where = Path(srv.vpm.listed(body.get("path")))
                if body.get("show") == "imports":   # what Hoard put in it (vpm/imports.py), shown in its folder
                    where = where / vpm_imports.NOTE_NAME
                    if not where.is_file():
                        return self._json({"error": "There's no list of what Hoard put in this project yet."}, 404)
                return self._json({"ok": True, "in": reveal(where)})
            if path == "/api/vpm/add-project":
                where = str(body.get("path") or "")[:2000]
                if not where or not Path(where).is_absolute() or not Path(where).is_dir() or not is_project(Path(where)):
                    return self._json({"error": "That folder isn't a Unity project."}, 400)
                listing.add(str(Path(where)))
                vpm_log.info(f"Added {Path(where).name} to the list ({Path(where)})")
                return self._json({"ok": True})
            if path == "/api/vpm/remove-project":
                where = srv.vpm.listed(body.get("path"))
                ok = listing.remove(where)
                if ok:
                    vpm_log.info(f"Took {Path(where).name} off the list ({where})")
                return self._json({"ok": ok})
            if path == "/api/vpm/delete-project":   # from this computer: only with its name typed, as a task
                where = srv.vpm.listed(body.get("path"))
                if str(body.get("confirm") or "") != Path(where).name:
                    return self._json({"error": "Type the project's name to delete it."}, 400)
                srv.vpm.deletable(where)   # (said now when it can't be: Unity has it open, say)
                return self._vpm_job({"op": "delete", "path": where, "name": Path(where).name, "backup": body.get("backup") is not False})
            if path == "/api/vpm/favorite":
                listing.note(srv.vpm.listed(body.get("path")), favorite=body.get("on") is True)
                return self._json({"ok": True})
            if path == "/api/vpm/organize":   # a project's folder and tags on Hoard's list (issue #190)
                kept = listing.organize(srv.vpm.listed(body.get("path")), folder=body.get("folder"), tags=body.get("tags"))
                return self._json({"ok": True, "folder": kept.get("folder"), "tags": kept.get("tags") or []})
            if path == "/api/vpm/repos/add":
                from .vpm import repos as vpm_repos
                try:
                    repo = vpm_repos.add_repo(srv.vpm.settings(), str(body.get("url") or "")[:2000],
                                              str(body.get("name") or "")[:200] or None, body.get("headers") or None)
                except vpm_repos.RepoError as e:
                    return self._json({"error": str(e)}, 400)
                srv.vpm.forget()
                vpm_log.info(f"Added the repository {repo.label()} ({vpm_log.count(len(repo.packages), 'package')})")
                return self._json({"ok": True, "label": repo.label(), "packages": len(repo.packages)})
            if path == "/api/vpm/repos/remove":
                from .vpm import repos as vpm_repos
                local = str(body.get("path") or "")[:2000]
                label = next((r.label() for r in srv.vpm.collection().repos if str(r.path) == local), local)
                ok = vpm_repos.remove_repo(srv.vpm.settings(), local)
                srv.vpm.forget()
                if ok:
                    vpm_log.info(f"Removed the repository {label}")
                return self._json({"ok": ok})
            if path == "/api/vpm/settings":
                settings = srv.vpm.settings()
                for key, field in (("projects_folder", "defaultProjectPath"), ("backups_folder", "projectBackupPath")):
                    if isinstance(body.get(key), str) and body[key].strip():
                        if not Path(body[key].strip()).is_absolute():
                            return self._json({"error": "Use a folder's full path."}, 400)
                        settings.set(field, body[key].strip()[:1000])
                if isinstance(body.get("prerelease"), bool):
                    settings.set("showPrereleasePackages", body["prerelease"])
                settings.save()
                vpm_log.info("Saved Unity and folders: projects in " + str(settings.default_project_path() or "the usual folder") +
                             ", backups in " + str(settings.project_backup_path() or "the usual folder") +
                             (", prerelease packages shown" if settings.show_prerelease() else ""))
                return self._json({"ok": True})
            if path == "/api/vpm/presets":
                action = body.get("action")
                if action == "save":
                    saved = vpm_presets.save(body.get("preset") or {})
                    vpm_log.info(f"Saved the preset {saved['name']}")
                    return self._json({"ok": True, "preset": saved})
                if action == "delete":
                    gone = next((x["name"] for x in vpm_presets.load() if x["id"] == body.get("id")), None)
                    ok = vpm_presets.delete(str(body.get("id") or "")[:40])
                    if ok and gone:
                        vpm_log.info(f"Deleted the preset {gone}")
                    return self._json({"ok": ok})
                if action == "export":
                    preset = next((x for x in vpm_presets.load() if x["id"] == body.get("id")), None)
                    if preset is None:
                        return self._json({"error": "That preset isn't there any more."}, 404)
                    assets = {x["key"]: srv.asset_by_key(x["key"]) for x in preset["products"]}
                    out = vpm_presets.export_alcom(preset, assets, srv.vpm.settings().folder)
                    vpm_log.info(f"Saved the preset {preset['name']} for ALCOM too ({out['path']})")
                    return self._json({"ok": True, **out})
                return self._json({"error": "Bad request."}, 400)
        except vpm_presets.PresetError as e:
            return self._json({"error": str(e)}, 400)
        except vpm_api.ProjectsError as e:
            return self._json({"error": str(e)}, 400)
        except OSError as e:
            return self._json({"error": f"That couldn't be done ({e.strerror or e})."}, 500)
        return self._send(404, b"Not found", "text/plain")

    def _picks(self, raw) -> list[dict]:
        """Products from your library to put in a project, as the page chose them; hidden ones only when unlocked."""
        out, hidden = [], set() if self._unlocked() else set(MarkStore().keys("hidden"))   # (read once, not for each)
        for p in (raw if isinstance(raw, list) else [])[:500]:
            if not isinstance(p, dict) or not isinstance(p.get("key"), str) or p["key"] in hidden:
                continue
            out.append({"key": p["key"][:400], "kind": str(p.get("kind") or "")[:20], "file": str(p.get("file") or "")[:1000],
                        "member": p["member"][:1000] if isinstance(p.get("member"), str) else None})
        return out

    def _queued(self, started: str | None):
        """The answer for something asked while a job ran: it waits its turn (or started, if that job just ended)."""
        if not started:
            return self._json({"error": "That's already waiting its turn."}, 409)
        return self._json({"ok": True, "queued": started == "queued", "job": True})

    def _delete_files(self, body: dict):
        """Delete the downloaded files of these products, only when confirmed (the pages ask first), and not while a
        job could be writing them (it waits its turn). A product still in your library stays there, as not downloaded,
        to download again whenever you like; a removed one leaves Downloads."""
        srv = self.server
        if body.get("confirm") is not True:
            return self._json({"error": "Confirm first."}, 400)
        raw = body.get("keys")
        keys = {k for k in raw[:5000] if isinstance(k, str)} if isinstance(raw, list) else set()
        marks = MarkStore().view()
        if keys & marks["hidden"] and not self._unlocked():
            return self._json({"error": "Unlock your hidden library first."}, 403)
        if not keys:
            return self._json({"error": "Choose the downloads to delete."}, 400)
        if not srv.jobs.busy.acquire(blocking=False):   # a job is running: this waits its turn after it
            names = sorted({a["name"] for a in srv.index(stale_ok=True)["assets"] if a.get("tag_key") in keys})
            name = names[0] if len(names) == 1 and len(keys) == 1 else f"{len(keys):,} {'product' if len(keys) == 1 else 'products'}"
            return self._queued(srv.jobs.start("delete-files", [], files={"keys": sorted(keys), "name": name}))
        try:
            done = delete_downloaded_files(srv.cfg, root_dir(srv.cfg), keys)
        finally:
            srv.jobs.busy.release()
            srv.jobs.kick()
        srv.forget_index()
        return self._json({"ok": True, **done})

    def _import_wishlists(self, body: dict):
        """Wishlist pages saved from your own browser: each read offline (wishlists.from_saved_pages), and each list
        in them kept as a wishlist. A long wishlist saved a page at a time comes together as one."""
        files = body.get("files")
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_IMPORT_FILES or \
                not all(isinstance(f, dict) and isinstance(f.get("content"), str) for f in files):
            return self._json({"error": f"Send between 1 and {MAX_IMPORT_FILES} saved pages at a time."}, 400)
        try:
            results = wishlists.from_saved_pages([(str(f.get("filename") or "page")[:300], f["content"]) for f in files])
        except Exception as e:   # the reading browser itself didn't start
            return self._json({"error": browser_problem(e) or f"Couldn't read the pages: {e}"}, 500)
        lists = wishlists.merge_lists([x for r in results for x in r.get("lists", [])])
        try:
            done = sets.SetStore().put_wishlists(lists) if lists else {"lists": 0, "cheaper": []}
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
            srv.save_settings()
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

    def _itch_key(self, body: dict):
        """Check an itch.io API key with itch.io, keep it (vault), and read your itch.io library with it."""
        srv = self.server
        key = vault.clean_key(body.get("key"))
        if not key:
            return self._json({"error": "That doesn't look like an itch.io API key. Copy the whole key from itch.io "
                                        "(Settings, API keys)."}, 400)
        sess = itch.session(key)
        try:
            who = itch.profile(sess)
        except itch.KeyRefused:
            return self._json({"error": "itch.io didn't accept that key. Check you copied all of it, and that it hasn't "
                                        "been deleted on itch.io."}, 400)
        except Exception as e:
            return self._json({"error": blocked_message("itch.io") if blocked_here(e)
                               else "Couldn't reach itch.io. Check your connection and try again." if is_network_error(e)
                               else f"itch.io didn't answer as expected: {e}"}, 502)
        finally:
            sess.close()
        try:
            vault.save_key(srv.cfg, "itch", key)
        except (SigninsUnprotected, OSError) as e:
            return self._json({"error": str(e)}, 500)
        started = srv.jobs.start("refresh", ["itch"])   # queued after anything running
        name = str(who.get("display_name") or who.get("username") or "")[:100]
        return self._json({"ok": True, "user": name, "kept": vault.key_protection(srv.cfg), "queued": started == "queued"})

    # ---- acting
    def do_POST(self):
        """Run an action. Only requests from this computer, sent as JSON with the access key, are accepted."""
        path, srv = urlparse(self.path).path, self.server
        if path not in ACTIONS:
            self._drop_body()
            return self._send(404, b"Not found", "text/plain")
        if (not self._host_ok() or self.client_address[0] not in LOOPBACK
                or not (self.headers.get("Content-Type") or "").startswith("application/json")):
            self._drop_body()
            return self._json({"error": "That only works on the computer running Hoard."}, 403)
        if path not in KEYLESS_ACTIONS and not check_access(self, srv.key):
            self._drop_body()
            return self._refused()
        srv.last_seen = time.time()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "Bad request."}, 400)
        if length < 0:   # (read(-1) would wait for the connection to close)
            return self._json({"error": "Bad request."}, 400)
        if length > (80 * 1024 * 1024 if path in ("/api/import", "/api/wishlists/import", "/api/backup/check",
                                                    "/api/backup/restore")
                     else 1024 * 1024):  # only imports and backups are large
            return self._json({"error": "That's too large to be saved pages. Import fewer at a time."
                               if path in ("/api/import", "/api/wishlists/import") else "That's too large."}, 413)
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
            # Settings save as they're changed. Only the ones a running job reads as it goes wait for it to finish:
            # where files go, which browser, which stores, and Payhip's shops.
            busy = [k for k in JOB_SETTINGS if k in body]
            if srv.jobs.state["running"] and busy:
                return self._json({"error": "That setting can't change while Hoard is refreshing or downloading. It's "
                                            "put back: change it again once the current job has finished.",
                                   "settings": public_settings(srv.cfg)}, 409)
            try:
                change = apply_settings(srv.cfg, body)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            deep_merge(srv.cfg, change)
            apply_store_sites(srv.cfg)   # added or removed Payhip shops count (or stop counting) straight away
            previous.set_keep(keep_previous(srv.cfg))
            srv.save_settings()
            srv.forget_index()
            return self._json({"ok": True, "settings": {**public_settings(srv.cfg), "libraries": srv.library_view()}})
        if path == "/api/diagnostics/open-folder":
            try:
                folder = diagnostics.support_report_dir()
                folder.mkdir(parents=True, exist_ok=True)
                return self._json({"ok": True, "opened_in": reveal(folder), "folder": str(folder)})
            except OSError as e:
                return self._json({"error": str(e)}, 500)
        if path == "/api/diagnostics/report":
            try:
                result = diagnostics.create_support_report(srv.cfg, srv.lib, srv.jobs.state, str(body.get("notes") or "")[:6000], body.get("context"))
            except Exception as e:
                diagnostics.record_exception(e, area="support-report", task="create-report")
                return self._json({"error": "Hoard couldn't save the support report. Make sure your Documents folder is writable, then try again."}, 500)
            try:
                result["opened_in"] = reveal(Path(result["path"]))
            except OSError:
                # The ZIP is already safely written; failure to open Explorer must not make the report look failed.
                result["opened_in"] = None
            return self._json(result)
        if path == "/api/open":
            target = open_target(srv.cfg, str(body.get("path", "")))
            if not target or not target.exists():
                return self._json({"error": "That file or folder isn't on disk anymore."}, 404)
            try:
                return self._json({"ok": True, "opened_in": reveal(target)})
            except OSError as e:
                return self._json({"error": str(e)}, 500)
        if path == "/api/look-inside":   # Downloads: what a .unitypackage or .zip holds, without extracting it
            target = open_target(srv.cfg, str(body.get("path", "")))
            if not target or not packages.can_look_inside(target.name) or not target.is_file():
                return self._json({"error": "That file isn't on disk anymore."}, 404)
            if self._hidden_file(target):   # (what's in a hidden product, as its name, stays hidden: #171)
                return self._json({"error": "Unlock your hidden library first."}, 403)
            try:
                return self._json(packages.look_inside(target), compress=True)
            except (packages.NotAPackage, OSError):
                return self._json({"error": "That file couldn't be read."}, 500)
        if path == "/api/look-inside/extract":   # Look inside: the chosen files taken out, into a folder of their own
            return self._extract(body)
        if path == "/api/previous/restore":   # Downloads: put a previous version of a file back (hoard/previous.py)
            if srv.jobs.state.get("running"):
                return self._json({"error": "Wait for Hoard to finish what it's doing, then try again."}, 409)
            folder = open_target(srv.cfg, str(body.get("folder", "")))
            if not folder or not folder.is_dir():
                return self._json({"error": "That product's folder isn't on disk anymore."}, 404)
            try:
                restore_previous(srv.cfg, root_dir(srv.cfg), folder, str(body.get("stamp", "")), str(body.get("file", "")))
            except (ValueError, OSError) as e:
                return self._json({"error": str(e) if isinstance(e, ValueError) else "That version couldn't be put back."}, 400)
            srv.forget_index()
            return self._json({"ok": True})
        if path == "/api/backup/make":   # Settings, Backup (hoard/backup.py)
            with srv.cfg_lock:
                doc = backup.make(srv.cfg, public_settings(srv.cfg), srv.lib, self._unlocked())
            try:
                where = backup.save(doc)
            except OSError as e:
                return self._json({"error": f"The backup couldn't be saved ({e.strerror or e})."}, 500)
            return self._json({"ok": True, "path": str(where), "hidden": "hidden" in doc["marks"],
                               "pin_set": bool(MarkStore().view()["pin"])})
        if path == "/api/backup/show":
            backup.backups_dir().mkdir(parents=True, exist_ok=True)
            try:
                return self._json({"ok": True, "opened_in": reveal(backup.backups_dir())})
            except OSError as e:
                return self._json({"error": str(e)}, 500)
        if path in ("/api/backup/check", "/api/backup/restore"):
            try:
                doc = backup.read(str(body.get("content") or ""))
            except backup.BackupError as e:
                return self._json({"error": str(e)}, 400)
            if path == "/api/backup/check":
                return self._json({"ok": True, **backup.summary(doc)})
            if srv.jobs.state.get("running") or srv.jobs.state.get("queue"):
                return self._json({"error": "Wait for Hoard to finish what it's doing, then try again."}, 409)
            replaces_hidden = isinstance((doc.get("marks") or {}).get("pin"), dict) if isinstance(doc.get("marks"), dict) else False
            if replaces_hidden and MarkStore().view()["pin"] and not self._unlocked():
                return self._json({"error": "This backup has hidden items, which take the place of yours: unlock your "
                                            "hidden library first, then restore it."}, 409)
            try:   # how things are now, kept first, so a restore can be undone
                with srv.cfg_lock:
                    before = backup.save(backup.make(srv.cfg, public_settings(srv.cfg), srv.lib, self._unlocked()),
                                         label=" (before restoring)")
            except OSError as e:
                return self._json({"error": f"A backup of how things are now couldn't be saved first ({e.strerror or e}), "
                                            "so nothing was restored."}, 500)

            def add_folder(value: str) -> None:
                folder = str(libraries.check_new_folder(srv.cfg, value))
                srv.cfg["library_folders"] = [str(f) for f in libraries.other_folders(srv.cfg)] + [folder]
            dropped = []
            with srv.cfg_lock:
                done = backup.restore(doc, srv.cfg, srv.lib, apply_settings, add_folder, dropped.append)
                apply_store_sites(srv.cfg)
                previous.set_keep(keep_previous(srv.cfg))
            if dropped:   # sets the backup doesn't have: their short links go too (else they'd run out by themselves)
                threading.Thread(target=forget_short_links, args=(dropped,), daemon=True).start()
            srv.save_settings()
            srv.forget_index()
            threading.Thread(target=rebuild_catalog_quietly, args=(srv,), daemon=True).start()
            return self._json({"ok": True, **done, "before": str(before)})
        if path == "/api/sets":   # the Sets tab, Library and Downloads: your sets (hoard/sets.py)
            if body.get("action") in ("add", "remove", "create") and not self._unlocked():
                hidden = MarkStore().keys("hidden")   # a hidden product isn't added or taken out while it's locked
                body = {**body, "items": [k for k in body.get("items") or [] if k not in hidden]}
            if body.get("action") == "photos" and isinstance(body.get("photos"), list):   # a photo site's page: its picture
                try:
                    body = {**body, "photos": [sets.photo_from_page(u, read_photo_page) if sets.photo_page(u) else u
                                               for u in body["photos"][:sets.MAX_PHOTOS + 1]]}
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
                    return self._json({"ok": True, **shortlinks.fetch(body.get("short"))})
                except shortlinks.ShortLinkError as e:
                    return self._json({"error": str(e)}, 404 if isinstance(e, shortlinks.Gone) else 502)
            gone = None
            if body.get("action") == "delete":   # its short link goes with it, once the set has
                gone = next((x for x in sets.SetStore().load()["sets"] if x["id"] == body.get("id")), None)
            try:
                data = sets.SetStore().change(body, self._product_details())
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except OSError as e:   # (a set's picture that couldn't be saved)
                return self._json({"error": f"Couldn't save that: {e.strerror or e}."}, 500)
            kept_short = None
            if gone and gone.get("short"):   # (if the share server can be reached)
                try:
                    shortlinks.delete(gone["short"]["id"], gone["short"]["token"])
                except shortlinks.ShortLinkError:
                    kept_short = gone["short"]["expires"]   # (it runs out by itself)
            threading.Thread(target=rebuild_catalog_quietly, args=(srv,), daemon=True).start()   # (Unity's Import set)
            return self._json({"ok": True, "made": data.get("made"), **({"kept_short": kept_short} if kept_short else {})})
        if path == "/api/folders/open":   # one of Settings' Hoard's folders, by its name: never a path the page sends
            found = places.find(self._places(), body.get("id"))
            if found is None:
                return self._json({"error": "That isn't one of Hoard's folders."}, 400)
            folder = Path(found["path"])
            try:
                if found["id"] in places.OWN:
                    folder.mkdir(parents=True, exist_ok=True)
                elif not folder.is_dir():
                    return self._json({"error": "That folder isn't there yet."}, 404)
                return self._json({"ok": True, "opened_in": reveal(folder)})
            except OSError as e:
                return self._json({"error": f"It didn't open ({e.strerror or e})."}, 500)
        if path == "/api/open-logs":   # Settings, Troubleshooting: a log for each time Hoard started, 30 days' worth
            from .paths import logs_dir
            logs_dir().mkdir(parents=True, exist_ok=True)
            try:
                return self._json({"ok": True, "opened_in": reveal(logs_dir())})
            except OSError as e:
                return self._json({"error": str(e)}, 500)
        if path == "/api/import":
            return self._import(body)
        if path == "/api/wishlists/read":   # Read wishlists: each chosen store's, in its signed-in window (wishlists.py)
            stores = [x for x in body.get("stores") or [] if x in wishlists.READERS] if isinstance(body.get("stores"), list) else []
            if not stores:
                return self._json({"error": "Choose the stores to read your wishlists from."}, 400)
            started = srv.jobs.start("wishlists", stores)
            return self._json({"ok": bool(started), "started": started}, 202 if started else 409)
        if path == "/api/wishlists/import":   # wishlist pages saved from your own browser, read offline
            return self._import_wishlists(body)
        if path == "/api/itch-key":
            return self._itch_key(body)
        if path == "/api/cancel":   # lane: "projects" for Projects' task
            return self._json({"ok": srv.lane(body.get("lane")).cancel()})
        if path == "/api/force-stop":   # any task, now (Tasks: Force stop)
            return self._json({"ok": srv.lane(body.get("lane")).force_stop()})
        if path == "/api/queue/remove":   # a job waiting its turn (issue #49); Projects' ids start with "p"
            job_id = str(body.get("id") or "")[:20]
            return self._json({"ok": srv.lane(PROJECTS if job_id.startswith("p") else None).remove(job_id)})
        if path == "/api/queue/clear":
            return self._json({"ok": True, "removed": sum(jobs.clear_queue() for jobs in srv.lanes())})
        if path == "/api/tasks/clear":
            for jobs in srv.lanes():
                jobs.clear_history()
            return self._json({"ok": True})
        if path == "/api/update/check":
            try:
                srv.updates.check()
            except Exception as e:
                if blocked_here(e):
                    return self._json({"error": "Couldn't check for updates. " + blocked_message("GitHub")}, 502)
                why = "you're offline, or GitHub can't be reached" if is_network_error(e) else str(e)[:200]
                return self._json({"error": f"Couldn't check for updates: {why}."}, 502)
            return self._json({"ok": True, **srv.updates.view(srv.can_update())})
        if path == "/api/update/install":
            if not srv.can_update():
                return self._json({"error": "This copy of Hoard can't update itself. Download the new version from "
                                            "the releases page."}, 409)
            if srv.jobs.state["running"]:
                return self._json({"error": "Wait for the current job to finish (or stop it), then update."}, 409)
            why = srv.updates.start_install(srv.quit_app)
            return self._json({"error": why}, 409) if why else self._json({"ok": True}, 202)
        if path == "/api/pick":   # Browse: the system's own picker, in Hoard's window (never in a web browser)
            if not srv.pick_path:
                return self._json({"error": "Choosing a folder needs Hoard's own window. Type the path instead."}, 409)
            kind = "file" if body.get("kind") == "file" else "folder"
            if not srv.picking.acquire(blocking=False):   # one picker at a time, over the window
                return self._json({"error": "A picker is already open."}, 409)
            # It opens in the downloads folder, or Projects' projects or backups folder: Hoard's own settings, never a
            # path the request names
            start = root_dir(srv.cfg)
            try:
                if body.get("start") == "projects":
                    start = Path(srv.vpm.settings().default_project_path() or start)
                elif body.get("start") == "backups":
                    start = srv.vpm.backups_folder()
            except vpm_api.ProjectsError:
                pass
            try:
                chosen = srv.pick_path(kind, str(start) if start.is_dir() else str(Path.home()))
            except Exception as e:   # the window went away, or the system has no picker
                return self._json({"error": f"The picker couldn't open ({type(e).__name__}). Type the path instead."}, 500)
            finally:
                srv.picking.release()
            return self._json({"ok": True, "path": chosen})
        if path == "/api/move":   # a download to another library folder (hoard/libraries.py), as a job
            key, to = str(body.get("key") or "")[:400], body.get("to")
            if not isinstance(to, int) or isinstance(to, bool):
                return self._json({"error": "Choose one of your library folders."}, 400)
            asset = next((a for a in srv.index(stale_ok=True)["assets"] if a.get("tag_key") == key), None)
            if asset is None:
                return self._json({"error": "That isn't downloaded any more."}, 404)
            if key in MarkStore().keys("hidden") and not self._unlocked():
                return self._json({"error": "Unlock your hidden library first."}, 403)
            started = srv.jobs.start("move", [], move={"key": key, "to": to, "name": asset.get("name")})
            if not started:
                return self._json({"error": "That's already waiting its turn."}, 409)
            return self._json({"ok": True, "queued": started == "queued"})
        if path in ("/api/libraries/add", "/api/libraries/remove"):   # the other library folders, from Settings
            return self._library_folders(path, body)
        if path.startswith("/api/vpm/"):   # Projects (hoard/vpm)
            return self._vpm_logged(path, self._vpm_post, body)
        if path == "/api/projects/forget":   # a Unity project out of Projects (issue #86); opening it again brings it back
            return self._json({"ok": projects.forget(str(body.get("id") or "")[:40])})
        if path.startswith("/api/local/"):   # your own packages (issue #80)
            return self._local(path, body)
        if path == "/api/verify":   # check the downloads now (issue #83), after anything already running
            started = srv.jobs.start("verify", [])
            if not started:
                return self._json({"error": "A check is already waiting its turn."}, 409)
            return self._json({"ok": True, "queued": started == "queued"})
        if path == "/api/edit-copy":   # a copy of a download to change, outside Hoard's care (issue #82)
            key = str(body.get("key") or "")[:400]
            if key in MarkStore().keys("hidden") and not self._unlocked():
                return self._json({"error": "Unlock your hidden library first."}, 403)
            try:
                done = make_editable_copy(srv.cfg, root_dir(srv.cfg), key)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except OSError as e:
                return self._json({"error": f"Couldn't make the copy: {e.strerror or e}."}, 500)
            opened = None
            if body.get("open"):
                try:
                    opened = reveal(Path(done["folder"]))
                except OSError:
                    pass
            return self._json({"ok": True, **done, "skipped": [{"path": p, "why": w} for p, w in done["skipped"]],
                               "opened_in": opened})
        if path == "/api/picture-looks":   # how pictures look, worked out by a page, for stacking copies (hoard/library.py)
            looks = body.get("looks") if isinstance(body.get("looks"), dict) else {}
            if not looks or len(looks) > 500:
                return self._json({"error": "Send between 1 and 500 at a time."}, 400)
            try:
                return self._json({"ok": True, "kept": save_picture_looks(looks)})
            except OSError as e:
                return self._json({"error": f"Couldn't keep them: {e}"}, 500)
        if path == "/api/routine/seen":   # issue #113: you've looked at what the routine check found
            save_routine(found=None)
            return self._json({"ok": True})
        if path == "/api/product-files":   # issue #225: what products have, to choose their files from before downloading
            return self._json(self._product_files(body))
        if path == "/api/download-skip":   # issue #107: always skip these products when downloading, or stop
            keys = body.get("keys") if isinstance(body.get("keys"), list) else []
            keys = {k for k in keys[:MAX_SKIP] if isinstance(k, str) and 0 < len(k) <= 400 and ":" in k}
            if not keys:
                return self._json({"error": "Choose the products to skip."}, 400)
            with srv.cfg_lock:
                now = download_skip(srv.cfg)
                now = (now | keys) if body.get("skip") is not False else (now - keys)
                if len(now) > MAX_SKIP:
                    return self._json({"error": f"Hoard can skip up to {MAX_SKIP:,} products."}, 400)
                srv.cfg["download_skip"] = sorted(now)
                srv.save_settings()
            return self._json({"ok": True, "skipped": len(now)})
        if path == "/api/delete-files":   # a removed product's downloaded files, after you've confirmed (issue #81)
            return self._delete_files(body)
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
            if srv.working() and not body.get("anyway"):
                return self._json({"busy": True, "error": "Hoard is still working."}, 409)   # the page asks what to do
            threading.Timer(0.3, srv.quit_app).start()   # after this answer is on its way
            return self._json({"ok": True})
        if path == "/api/app/close":   # what to do about closing while something runs (the page asked you)
            from .app import quit_now, quit_when_done
            how = body.get("how")
            if not srv.quit_app:
                return self._json({"error": "Hoard is running as a server; stop it where it was started."}, 409)
            if how == "background":
                if not srv.hide_window:
                    return self._json({"error": "Hoard carries on in the background only in its own window."}, 409)
                threading.Timer(0.3, srv.hide_window).start()
            elif how == "wait":
                threading.Thread(target=quit_when_done, args=(srv,), daemon=True).start()
            elif how == "now":
                threading.Timer(0.3, quit_now, args=(srv,)).start()
            else:
                return self._json({"error": "Unknown choice."}, 400)
            return self._json({"ok": True})
        if path == "/api/signin-link":
            why = srv.jobs.open_link(str(body.get("url") or "").strip()[:2000])
            return self._json({"error": why}, 400) if why else self._json({"ok": True})
        if path == "/api/setup/browser":
            started = srv.jobs.start("install-browser", [])
            if not started:
                return self._json({"error": "Installing Hoard's browser is already waiting its turn."}, 409)
            return self._json({"ok": True, "queued": started == "queued"}, 202)
        if path == "/api/setup/done":
            srv.cfg["setup_done"] = bool(body.get("done", True))
            srv.save_settings()
            return self._json({"ok": True})
        if path == "/api/setup/migrate":
            if srv.jobs.state["running"]:   # it can change the downloads folder, which a running job is writing to
                return self._json({"error": "Wait for Hoard to finish what it's doing (or stop it), then bring your "
                                            "library over."}, 409)
            folder = str(body.get("folder") or "").strip().strip('"')[:1000]
            if not folder or not Path(folder).expanduser().is_absolute():
                return self._json({"error": "Enter the full path of the folder you ran Hoard 1.x from."}, 400)
            said = migrate_from(srv.cfg, Path(folder), srv.config_path, srv.lib)
            srv.forget_index()
            return self._json({"ok": True, "message": said})

        named = body.get("stores")
        if named is not None and not isinstance(named, list):
            return self._json({"error": "Unknown store."}, 400)
        stores = list(dict.fromkeys(s for s in (named or list(STORES))[:20]
                                    if isinstance(s, str) and (s in STORES or (path == "/api/logout" and s == "all"))))
        bulk = path in ("/api/download", "/api/check-updates") and not (body.get("keys") or body.get("item") or body.get("only"))
        if path == "/api/sync" or bulk:   # only the stores you use (a chosen product is fetched wherever it is)
            stores = [s for s in stores if srv.cfg[s].get("enabled", True)]
        if path == "/api/login" and stores[:1] == ["itch"]:   # (a sign-in is one store's: the first named)
            return self._json({"error": "itch.io signs in with an API key: choose Sign in on its row in Stores."}, 400)
        if path in ("/api/download", "/api/check-updates") and stores and not any(s in DOWNLOADABLE for s in stores):
            return self._json({"error": "Hoard lists what you own on Payhip, and doesn't download from it. Open the "
                                        "product's download page from its details, and download it there."}, 400)
        if not stores:
            return self._json({"error": "No stores are switched on in Settings." if path == "/api/sync" or bulk else "Unknown store."}, 400)
        task = {"/api/login": "login", "/api/logout": "logout", "/api/download": "download",
                "/api/sync": "sync", "/api/check-updates": "check-updates"}.get(path, "refresh")
        only = str(body.get("only") or "").strip()[:200] or None
        # products chosen on the Downloads page (to update, or to check), by their tag_key
        keys = [k for k in (body.get("keys") if isinstance(body.get("keys"), list) else [])[:5000]
                if isinstance(k, str) and 0 < len(k) <= 400] or None
        # the library item chosen in the Library, so the download can go straight to it
        item = body.get("item") if isinstance(body.get("item"), str) and 0 < len(body.get("item")) <= 400 else None
        started = srv.jobs.start(task, stores[:1] if task in ("login", "logout") else stores,
                                 skip_imported=bool(body.get("all")), only=only, keys=keys,
                                 items=[item] if item and task in ("download", "check-updates") else None,
                                 chosen=self._remember_files(chosen_files(body.get("files"))) if task == "download" else None)
        if not started:
            return self._json({"error": "That's already waiting its turn in Tasks (or the queue is full)."}, 409)
        self._json({"ok": True, "queued": started == "queued"}, 202)


SHARED_MARK = b"//@include shared.js\n"


def page_source(name: str, cfg: dict | None = None, accept_language: str | None = None) -> bytes:
    """A page as it's served: its file, with what both pages share (web/shared.js) put in its script where it says
    so, so each page is still one script the Content-Security-Policy allows by its hash; the styles (web/looks.css),
    and the theme you chose (Settings, Appearance) after the page's own colours, so it shows from the first moment;
    and your language: the page's lang, and the catalog it translates itself from (hoard/i18n.py), before its
    script. The page stays hidden until it has (data-i18n), so it never shows in English first."""
    page = (WEB / name).read_bytes()
    if SHARED_MARK in page:
        page = page.replace(SHARED_MARK, (WEB / "shared.js").read_bytes().replace(b"\r\n", b"\n") + b"\n", 1)
    d = (cfg or {}).get("display") if isinstance((cfg or {}).get("display"), dict) else {}
    # the styles' layouts (web/looks.css, both pages alike), then the theme's colours
    looks = '<style id="looks">\n' + (WEB / "looks.css").read_text("utf-8").replace("\r\n", "\n") + "</style>\n"
    style = '<style id="theme">\n' + themes.css(d.get("theme"), d.get("mode")) + "\n</style>\n"
    page = page.replace(b"</head>", looks.encode() + style.encode() + b"</head>", 1)
    # the font, spacing, card outlines (Settings, Accessibility) and style (Appearance) you chose, on the page from its
    # first moment
    marks = (' data-font="dyslexic"' if d.get("font") == "dyslexic" else "") + (' data-spacing="wide"' if d.get("spacing") is True else "")
    marks += ' data-cards="outlined"' if d.get("card_outlines") is True else ""
    if themes.style_id(d.get("style")) != "standard":
        marks += f' data-style="{themes.style_id(d.get("style"))}"'
    if marks:
        page = page.replace(b'<html lang="en">', f'<html lang="en"{marks}>'.encode(), 1)
    lang = i18n.language(cfg, accept_language)
    if lang != "en":
        page = page.replace(f'<html lang="en"{marks}>'.encode(), f'<html lang="{lang}"{marks} data-i18n>'.encode(), 1)
        page = page.replace(b"\n<script>\n", b"\n" + i18n.page_script(lang).encode() + b"<script>\n", 1)
    return page


GUIDE = "styleguide.html"
GUIDE_PAGES = {"library": "library.html", "downloads": "downloads.html"}
GUIDE_SIZES = (100, 115, 130, 150)
_OWN_STYLE = re.compile(rb"<style[^>]*>(.*?)</style>", re.S)
# what each of a theme's colours is for (hoard/themes.py), for the guide's swatches
TOKEN_USES = {"cave": "the page", "ledge": "panels, and the ground under tiles", "stone": "hover, and boxes in panels",
              "seam": "lines and edges", "bone": "text", "dust": "quieter text", "gold": "the accent: yours, or do this",
              "gold-ink": "text on the accent", "gold-text": "the accent as text", "warn": "problems",
              "booth": "Booth", "gumroad": "Gumroad", "jinxxy": "Jinxxy", "payhip": "Payhip", "itch": "itch.io",
              "local": "Local (your own packages)"}


def guide_source(query: dict) -> bytes:
    """The style guide (/styleguide, web/styleguide.html): every part of the pages, drawn with one page's own
    stylesheet (the Library's or Downloads'), web/looks.css and a theme, as the pages are served, so it never drifts
    from them. What it's shown in (page, style, theme, Light or Dark, font, spacing, colours, text size) is in its
    address, chosen in its own bar (and card outlines). Nothing of yours is in it: every product, project and file in it
    is made up."""
    def one(k):
        return (query.get(k) or [""])[0][:40]
    page = one("page") if one("page") in GUIDE_PAGES else "library"
    style, theme, mode = themes.style_id(one("style")), themes.theme_id(one("theme")), themes.mode_id(one("mode"))
    size = int(one("size")) if one("size") in {str(s) for s in GUIDE_SIZES} else 100
    font, spacing, colours = one("font") == "dyslexic", one("spacing") == "wide", one("colours") == "colourblind"
    outlined = one("cards") == "outlined"
    own = _OWN_STYLE.search((WEB / GUIDE_PAGES[page]).read_bytes())
    styles = (b'<style id="page">' + (own.group(1) if own else b"") + b"</style>\n" +
              b'<style id="looks">\n' + (WEB / "looks.css").read_bytes() + b"</style>\n" +
              b'<style id="theme">\n' + themes.css(theme, mode).encode() + b"\n</style>\n")
    marks = (f' data-page="{page}"' + (f' data-style="{style}"' if style != "standard" else "") +
             (' data-font="dyslexic"' if font else "") + (' data-spacing="wide"' if spacing else "") +
             (' data-cards="outlined"' if outlined else "") + (' data-colours="colourblind"' if colours else "") +
             (f' style="zoom: {size / 100}; --zoom: {size / 100}"' if size != 100 else ""))

    def choice(name, label, options, chosen):
        opts = "".join(f'<option value="{v}"{" selected" if v == chosen else ""}>{text}</option>' for v, text in options)
        return f'<label>{label} <select name="{name}">{opts}</select></label>'
    bar = (choice("page", "Page", [("library", "Library"), ("downloads", "Downloads")], page) +
           choice("style", "Style", [(s, s.title()) for s in themes.STYLES], style) +
           choice("theme", "Theme", [(t["id"], t["name"]) for t in themes.choices()], theme) +
           choice("mode", "Light or Dark", [("system", "Match my computer"), ("light", "Light"), ("dark", "Dark")], mode) +
           choice("font", "Font", [("standard", "Standard"), ("dyslexic", "OpenDyslexic")], "dyslexic" if font else "standard") +
           choice("size", "Text size", [(str(s), f"{s}%") for s in GUIDE_SIZES], str(size)) +
           choice("colours", "Store colours", [("standard", "Standard"), ("colourblind", "Easier to tell apart")],
                  "colourblind" if colours else "standard") +
           f'<label class="check"><input type="checkbox" name="spacing" value="wide"{" checked" if spacing else ""}> Wider spacing</label>'
           f'<label class="check"><input type="checkbox" name="cards" value="outlined"{" checked" if outlined else ""}> Card outlines</label>')
    tokens = "".join(f'<li class="sg-tok"><i style="background: var(--{k})"></i><code>--{k}</code><small>{use}</small>'
                     f'<span class="sg-val" data-token="{k}"></span></li>' for k, use in TOKEN_USES.items())
    out = (WEB / GUIDE).read_bytes()
    out = out.replace(b"<!--@styles-->", styles, 1).replace(b"<!--@bar-->", bar.encode(), 1)
    out = out.replace(b"<!--@tokens-->", tokens.encode(), 1)
    return out.replace(b'<html lang="en">', f'<html lang="en"{marks}>'.encode(), 1)


def chosen_files(raw) -> dict[str, dict] | None:
    """The files you chose of each product, when choosing what to download: {tag_key: {"shown": the files the list
    showed, "chosen": the ones left ticked}}, for the products you left some files out of. Only a file that was
    shown and unticked is left out (downloader.left_out). {"all": true}: everything of that product, this time,
    whatever an earlier choice or a rule leaves out (issue #225: Download everything). Anything else is ignored."""
    if not isinstance(raw, dict):
        return None
    names = lambda v: [n for n in v[:500] if isinstance(n, str) and 0 < len(n) <= 500] if isinstance(v, list) else []  # noqa: E731
    out = {}
    for key, pick in list(raw.items())[:5000]:
        if not (isinstance(key, str) and 0 < len(key) <= 400 and isinstance(pick, dict)):
            continue
        if pick.get("all") is True:
            out[key] = {"shown": [], "chosen": [], "all": True}
        elif names(pick.get("shown")):
            out[key] = {"shown": names(pick.get("shown")), "chosen": names(pick.get("chosen"))}
    return out or None


def remember_choice(kept: dict[str, set], chosen: dict) -> dict[str, list]:
    """The files left out of each product from now on (config.json's "file_skip", issue #225), after choosing what
    to download: those of the files shown that weren't ticked, and any left out before that weren't shown."""
    kept = dict(kept)
    for key, pick in chosen.items():
        if pick.get("all"):   # everything this time: nothing of it left out from now on
            kept.pop(key, None)
            continue
        shown = set(pick["shown"])
        left = (kept.get(key, set()) - shown) | (shown - set(pick["chosen"]))
        if left:
            kept[key] = left
        else:
            kept.pop(key, None)
    return {k: sorted(v) for k, v in list(kept.items())[-MAX_REMEMBERED:]}


def read_photo_page(url: str) -> str | None:
    """A photo site's page, read once for the picture it shows (sets.photo_from_page), as a browser would ask for
    it: from the photo sites only (sets.PAGE_HOSTS, redirects included), at public addresses, 2 MB at most. Its text,
    or None."""
    got = fetch_public(url, {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
                                           "like Gecko) Chrome/140.0 Safari/537.36", "Accept": "text/html"},
                       sets.MAX_PHOTO_PAGE, hosts=sets.PAGE_HOSTS)
    return got[0].decode("utf-8", "replace") if got and got[1] in ("text/html", "application/xhtml+xml") else None


def forget_short_links(records: list[dict]) -> None:
    """Delete short links whose sets are gone (a restore of a backup without them), as well as the share server can
    be reached: one it can't delete runs out by itself."""
    for rec in records:
        try:
            shortlinks.delete(rec["id"], rec["token"])
        except shortlinks.ShortLinkError:
            pass


def rebuild_catalog_quietly(srv) -> None:
    """After packages were read for What it needs: write catalog.json again, so Hoard for Unity knows what each
    product needs. Skipped while a job runs: that job writes the catalog itself when it ends."""
    if not srv.jobs.busy.acquire(blocking=False):
        return
    try:
        build_catalog(srv.cfg, root_dir(srv.cfg))
    except Exception as e:   # never stops Hoard
        print(f"Couldn't write catalog.json: {e}")
    finally:
        srv.jobs.busy.release()
        srv.jobs.kick()


def reseal_in_background(srv, cfg: dict) -> None:
    """At startup: if the downloads folder's catalog.json isn't sealed with this install's key, rebuild and seal it
    (the Unity window reads it). Skipped when a job is already running: that job rebuilds the catalog anyway. The
    seal is looked at first, without holding the job lock: only a rebuild takes it, so a catalog that's fine never
    makes the first thing you choose after starting Hoard say it's busy."""
    try:
        if catalog_seal(root_dir(cfg)) in (None, "sealed"):
            return
    except Exception as e:
        print(f"Couldn't check catalog.json's seal: {e}")
        return
    if not srv.jobs.busy.acquire(blocking=False):
        return
    try:
        reseal_catalog(cfg, root_dir(cfg))
    except Exception as e:   # never stops Hoard from starting
        print(f"Couldn't check catalog.json's seal: {e}")
    finally:
        srv.jobs.busy.release()
        srv.jobs.kick()   # anything queued meanwhile


def _reach(host: str) -> str:
    """Where this computer reaches a server listening on host: 127.0.0.1 when it listens there (or everywhere), else
    the address it listens on (--host with one network address, where nothing listens on 127.0.0.1)."""
    host = (host or "").strip("[]")
    if host in ("", "0.0.0.0", "::", "localhost", "127.0.0.1"):
        return "127.0.0.1"
    return f"[{host}]" if ":" in host else host


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
    srv.url = url = f"{scheme}://{_reach(host)}:{srv.server_port}/"
    if srv.lan:
        print(f"Other devices on your network: {scheme}://<this computer's address>:{srv.server_port}/#key={srv.key}")
        print("That address includes the access key, new each time Hoard starts. Share it only with devices you trust.")
        if not tls:
            print("This is plain HTTP: only use it where the connection is already encrypted, such as over Tailscale.")
    print(f"Hoard {__version__}: {url}   (library: {len(srv.lib.data['items'])} items; downloads: {root_dir(cfg)})")
    if store_python():
        print(STORE_PYTHON_NOTE)
    threading.Thread(target=reseal_in_background, args=(srv, cfg), name="hoard-reseal", daemon=True).start()
    threading.Thread(target=srv.needs_reader.run_forever, args=(threading.Event(),), name="hoard-needs", daemon=True).start()
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


__all__ = ["serve", "AppServer", "Handler", "public_settings", "apply_settings", "page_source", "IMPORTABLE"]
