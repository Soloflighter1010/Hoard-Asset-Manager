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

from . import __version__, alerts, backup, credits, diagnostics, i18n, itch, libraries, loading, needs, packages, places, previous, projects, sets, shortlinks, space, themes, updater, vault, wishlists
from .changelog import whats_new
from .asset_updates import AssetUpdates
from .browser import SigninsUnprotected, signin_protection, signins_root, use_channel
from .config import DEFAULT_CONFIG, apply_store_sites, clean_payhip_shop, deep_merge, payhip_shops, root_dir, save_config
from .downloader import (build_catalog, catalog_seal, collect_catalog, delete_downloaded_files, download_retries, integrity_summary,
                         restore_previous, file_rules, remembered_files, ruled_out, MAX_REMEMBERED, MAX_PROBLEMS, STORE_DIRS,
                         edits_root, last_integrity, make_editable_copy, reseal_catalog, resolve_problem)
from .downloads import build_index, library_status, reveal, with_tags
from .jobs import MAX_SKIP, PROJECTS, ROUTINE_CHOICES, Jobs, Schedule, download_skip, forget_deleted_signins, routine_hours, routine_record, save_routine
from .net import blocked_here, blocked_message, is_network_error
from .wishlists import read_store_page   # (Add products by link: tests stand in for it here)
from .library import (DOWNLOADABLE, IMPORTABLE, STORES, Library, cache_images, common_words, enrich, fetch_picture, fetch_thumbnail, import_saved_pages,
                      save_picture_looks, stack_by_picture)
from .paths import LIBRARY_FILE, STORE_PYTHON_NOTE, WEB, default_downloads, store_python
from .safety import (LOOPBACK, SECURITY_HEADERS, TLSServerMixin, check_access, contained_rel, content_security_policy,
                     fetch_public, header_safe, network_tls, open_under, rel_to_path, safe_join, safe_name, store_sites, UnsafePath)
from .app import token_matches
from .marks import MarkStore, PinError, is_archived
from .setup import browser_problem, migrate_from, setup_status, signed_in
from .tags import TagStore, product_type, tag_key, tag_overview
from .vpm import api as vpm_api, logbook as vpm_log

PAGES = {"/": "library.html", "/index.html": "library.html", "/downloads": "downloads.html"}
FONT_FILES = ("DelaGothicOne-Regular.woff2", "ZenMaruGothic-Medium.woff2", "ZenMaruGothic-Bold.woff2",
              "OpenDyslexic-Regular.woff2", "OpenDyslexic-Bold.woff2")
# Actions that prove themselves another way than the access key: the one-time link a page is opened with,
# and a second copy of Hoard with the token in the running copy's private file.
MAX_UNWRAPPED = 5000   # gifts remembered as opened (issue #263): the last ones opened, past that
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
            "seasonal": d.get("seasonal") is not False,   # Seasonal Secrets (issue #260): on unless you turn it off
            # easier reading: OpenDyslexic for Latin letters, and more space between letters, words and lines
            "font": d.get("font") if d.get("font") in FONTS else "standard", "spacing": bool(d.get("spacing")),
            "card_outlines": bool(d.get("card_outlines")),   # each card outlined, on a background of its own (#222)
            "blur_adult": d.get("blur_adult") is not False,   # adult products' pictures blurred, unless you turn it off (#311)
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
UI_SORTS = ("name", "creator", "store", "added", "season", "size")   # the Library's and Downloads' Sort (size: Downloads only)


def ui_settings(cfg: dict) -> dict:
    """How you left the pages (kept in config.json, since the pages' own storage goes with the server's address, which
    is new each time Hoard starts): each window's place and size, the sidebar and its sections folded, the tile size,
    the sort, one for both pages, the sets you added to last, the gifts you've opened, and the notes on what's new
    you've seen."""
    ui = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
    out: dict = {"windows": {}, "sections": {}}
    for wid, place in (ui.get("windows") or {}).items() if isinstance(ui.get("windows"), dict) else ():
        if wid in UI_WINDOWS and isinstance(place, dict):
            out["windows"][wid] = {k: v for k, v in place.items() if k in ("x", "y", "w", "h")
                                   and isinstance(v, (int, float)) and not isinstance(v, bool) and -20000 <= v <= 20000}
    for name, open_ in list((ui.get("sections") or {}).items())[:30] if isinstance(ui.get("sections"), dict) else ():
        if isinstance(name, str) and len(name) <= 40 and isinstance(open_, bool):
            out["sections"][name] = open_
    # the sidebar folded; copies stacked (issue #111); the tour offered; the last PyInstaller build's note read (5.2.0b5)
    for k in ("side_folded", "stack", "toured", "moving_seen"):
        if isinstance(ui.get(k), bool):
            out[k] = ui[k]
    for k in ("tile_size", "dl_tile_size"):   # the Library's and the Downloads page's
        if isinstance(ui.get(k), int) and not isinstance(ui.get(k), bool) and 100 <= ui[k] <= 400:
            out[k] = ui[k]
    if ui.get("sort") in UI_SORTS:
        out["sort"] = ui["sort"]
    if ui.get("pj_layout") in ("list", "tiles"):   # Projects as a list or as tiles (issue #250)
        out["pj_layout"] = ui["pj_layout"]
    if isinstance(ui.get("recent_sets"), list):   # the sets you added to last, first in the right-click menu (issue #228)
        out["recent_sets"] = [s for s in ui["recent_sets"] if isinstance(s, str) and re.fullmatch(r"[0-9A-Za-z]{1,16}", s)][:10]
    if isinstance(ui.get("spots_seen"), list):   # the "new here" notes you've seen (issue #244), by their names
        out["spots_seen"] = [k for k in ui["spots_seen"] if isinstance(k, str) and re.fullmatch(r"[a-z0-9-]{1,40}", k)][:100]
    if isinstance(ui.get("unwrapped"), list):   # the gifts you've opened (issue #263): their keys, never their names
        out["unwrapped"] = [k for k in ui["unwrapped"] if isinstance(k, str) and re.fullmatch(r"[a-z]{2,12}:[\w.:-]{1,120}", k)][-MAX_UNWRAPPED:]
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
                    summary=integrity_summary(last), listed=len(last["problems"]))   # (to deal with: issue #231)
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
        # notifications through Apprise (issue #230): how many addresses are kept (never the addresses), and what's sent
        "apprise": {"available": alerts.available(), "kept": alerts.kept(cfg), "addresses": alerts.described(cfg),
                    "events": sorted(alerts.chosen(cfg))},
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
    if "apprise_events" in body:   # issue #230: what's sent through Apprise (the addresses go to /api/apprise)
        events = body["apprise_events"] if isinstance(body["apprise_events"], list) else []
        change["apprise_events"] = [e for e in alerts.EVENTS if e in events]
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
        display.update({k: bool(given[k]) for k in ("pause_animations", "reduce_motion", "glow", "spacing", "card_outlines",
                                                    "seasonal", "blur_adult") if k in given})
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
VPM_ACTIONS = {"/api/vpm": "Reading your projects", "/api/vpm/project": "Reading a project", "/api/vpm/about": "Reading a project",
               "/api/vpm/packages": "Reading the packages", "/api/vpm/versions": "Reading a package's versions",
               "/api/vpm/preview": "Working out the changes", "/api/vpm/apply": "Changing packages",
               "/api/vpm/create": "New project", "/api/vpm/preload": "Putting products in", "/api/vpm/backup": "Back up",
               "/api/vpm/refresh": "Refreshing the repositories", "/api/vpm/open": "Open in Unity",
               "/api/vpm/open-folder": "Open folder", "/api/vpm/add-project": "Add a project",
               "/api/vpm/remove-project": "Take off the list", "/api/vpm/delete-project": "Delete from this computer",
               "/api/vpm/favorite": "Favourite", "/api/vpm/organize": "Folders and tags", "/api/vpm/rename": "Rename a project",
               "/api/vpm/git": "Source control", "/api/vpm/git/plan": "Set up Git", "/api/vpm/git/init": "Set up Git",
               "/api/vpm/git/ignore": "Git's ignore rules", "/api/vpm/git/stage": "Stage", "/api/vpm/git/unstage": "Unstage",
               "/api/vpm/git/commit": "Commit", "/api/vpm/git/identity": "Who commits", "/api/vpm/git/diff": "A file's changes",
               "/api/vpm/git/history": "History", "/api/vpm/git/files": "A commit's files", "/api/vpm/git/remote": "Remotes",
               "/api/vpm/git/branch": "Branches", "/api/vpm/git/abort": "Abort the merge", "/api/vpm/git/open-app": "Open in your Git app",
               "/api/vpm/git/app": "Your Git app", "/api/vpm/git/trust": "Trust its Git settings", "/api/vpm/git/sync": "Fetch, pull or push", "/api/vpm/git/clone": "A project from a Git address", "/api/vpm/repos/add": "Add a repository",
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
        """Serve the connection, then give its slot back."""
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def __init__(self, addr, cfg: dict, lan: bool, config_path: Path | None = None):
        """Start listening, with a new access key: every request for data, images or an action needs it."""
        super().__init__(addr, Handler)
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._background_stop = threading.Event()
        from .scheduler import Scheduler
        self.scheduler = Scheduler()
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
        self.jobs = Jobs(cfg, self.lib, on_download_done=self.forget_index, scheduler=self.scheduler)
        self.project_jobs = Jobs(cfg, self.lib, lane=PROJECTS, scheduler=self.scheduler)
        # The downloads index: rebuilt outside the lock, one rebuild at a time (review finding P-07). _wanted counts
        # "the downloads changed"; _built_for is the count the current index was built for.
        self._index, self._index_lock = None, threading.Lock()
        self._wanted, self._built_for, self._rebuild = 0, -1, None
        self.updates = updater.Updates(cfg)
        self.updates.scheduler = self.scheduler
        # news, sent through Apprise as you chose (issue #230): counts, never a product's name
        self.jobs.on_news = self.project_jobs.on_news = self._news
        self.updates.on_available = lambda version: alerts.send(
            self.cfg, "other", f"**Hoard {version}** is available. Open Hoard to update.", title="A new version of Hoard",
            link=f"{alerts.HOARD_URL}/releases")
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
        """Both lanes' jobs: the main one's and Projects'."""
        return self.jobs, self.project_jobs

    def working(self) -> bool:
        """Is a task running, or waiting its turn, in either lane? (Closing Hoard asks first.)"""
        return any(jobs.state.get("running") or jobs.state.get("queue") for jobs in self.lanes())

    def tasks(self) -> dict:
        """The Tasks tab, both lanes: what's running in each, what's waiting, and what finished, newest first."""
        main, pj = self.jobs.tasks(), self.project_jobs.tasks()
        history = sorted(main["history"] + pj["history"], key=lambda h: h.get("ended") or "", reverse=True)
        return {"current": main["current"], "project": pj["current"], "queue": main["queue"] + pj["queue"],
                "history": history, "background": self.scheduler.snapshot()}

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
        self.schedule.register(self.scheduler, self._background_stop)
        return self._background_stop

    def start_worker(self, name: str, target, *args) -> None:
        """Submit maintenance through the server's single worker owner."""
        self.scheduler.call(name, lambda: target(*args), priority=20, foreground=False, visible=True)

    def server_close(self) -> None:
        """Wake and join readers before releasing this server's data and listening socket."""
        self._background_stop.set()
        self.needs_reader.wake.set()
        self.scheduler.close()
        super().server_close()

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

    def files_with_code(self, a: dict) -> list[dict]:
        """A download's files, each package (.unitypackage or .zip) that holds scripts or plugins with what they are
        ("code": needs.file_code), as far as the background reader has got."""
        out = []
        for f in a.get("files") or []:
            code = None
            if not f.get("missing") and packages.can_look_inside(f.get("path") or ""):
                code = needs.file_code(self.needs_index.get(os.path.join(a["abs_folder"], *f["path"].split("/"))))
            out.append({**f, "code": code} if code else f)
        return out

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

    def _news(self, kind: str, what) -> None:
        """Issue #230: news from the tasks, sent through Apprise as you chose (hoard/alerts.py): how many, never names."""
        if kind == "found":
            for event, title in (("new", "New products to download"), ("updates", "Updates to download")):
                text = alerts.found_text(what, event)
                if text:
                    alerts.send(self.cfg, event, text, title=title)
        elif kind == "cheaper":   # (issue #285: a wishlist's products, which are a store's, with their picture and link)
            count, items = (what.get("count", 0), what.get("items") or []) if isinstance(what, dict) else (what, [])
            hidden = MarkStore().keys("hidden")
            items = [i for i in items if isinstance(i, dict) and i.get("key") not in hidden]
            text, link = alerts.cheaper_text(count, items)
            first = next((i for i in items if i.get("thumbnail") and i.get("store") in STORES), None)
            pic_url = sets.product_picture(first["store"], first["thumbnail"]) if first else None
            picture = (lambda: fetch_picture(pic_url, STORES[first["store"]]["referer"])) if pic_url else None   # (fetched as it's sent)
            alerts.send(self.cfg, "prices", text, title="Cheaper on your wishlists", link=link, picture=picture,
                        picture_url=pic_url)   # (a Discord embed shows it from the store itself: issue #330)
        elif kind == "checked":
            parts = [alerts.plural(what[k], f"file {k}", f"files {k}") for k in ("changed", "missing") if what.get(k)]
            alerts.send(self.cfg, "other", f"The check of your downloads found **{' and '.join(parts)}**. "
                                           "Open Hoard to see what it found.", title="The check of your downloads")
        elif kind == "finished" and what.get("task") == "routine":
            counts = (what.get("report") or {}).get("routine") or {}
            found = [alerts.plural(counts[k], one) for k, one in (("new", "new product"), ("updates", "update")) if counts.get(k)]
            alerts.send(self.cfg, "routine", "The routine check **failed**." if what.get("outcome") == "failed" else
                        f"The routine check found **{' and '.join(found)}**." if found else "The routine check found nothing new.",
                        title="The routine check")
        elif kind == "finished" and what.get("task") not in ("list-files",):
            alerts.send(self.cfg, "tasks", alerts.task_text(what), title="A task finished")

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
    """Answers the pages' requests."""
    timeout = 30   # seconds a connection may sit idle or trickle a request before it's closed
    # HTTP/1.1, so a page's requests share their connections (keep-alive) instead of opening one each. On Windows each
    # closed connection holds on to its port for minutes, and a page that asks often (Projects' news every second and
    # a half, a large library's pictures) ran out of them: its next request failed (ERR_NO_BUFFER_SPACE), a change
    # it saved with it lost. Every reply says its length (_send), and one sent before its request's body was read
    # closes the connection (_send: the body would be read as the next request).
    protocol_version = "HTTP/1.1"
    # A reply's headers and body go out as two writes; on a connection kept open, Nagle's algorithm held the second
    # until the first was acknowledged, which the browser delays (about 40 ms a reply on Linux, 200 on Windows).
    disable_nagle_algorithm = True
    server: AppServer

    def log_message(self, *args):
        """Keep the console quiet: individual requests aren't logged."""

    def _send(self, status, body: bytes, ctype: str, headers: dict | None = None):
        """Send a reply with the security headers; pages get their own policy, everything else is sandboxed."""
        ctype = header_safe(ctype)   # every header is checked for line breaks before anything is sent
        extra = [(header_safe(k), header_safe(v)) for k, v in (headers or {}).items()]
        try:
            unread = int(self.headers.get("Content-Length") or 0) != 0 and not getattr(self, "_body_read", False)
        except ValueError:
            unread = True
        if unread or self.headers.get("Transfer-Encoding"):   # (left on the connection: never read as a request)
            self.close_connection = True
            extra.append(("Connection", "close"))
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
        return self._lock_in() > 0

    def _lock_in(self, touch: bool = False) -> int:
        """Seconds until this browser's hidden library locks itself again (0: it's locked). Only touching it starts
        the time again, as someone uses the page (issue #248): the page asking for news every few seconds would
        otherwise keep it unlocked for as long as it's open."""
        srv = self.server
        cookie = self.headers.get("Cookie") or ""
        token = next((c.split("=", 1)[1] for c in (x.strip() for x in cookie.split(";")) if c.startswith("hoard_unlock=")), "")
        now = time.time()
        with srv.unlocks_lock:
            for t in [t for t, until in srv.unlocks.items() if until < now]:
                srv.unlocks.pop(t, None)
            if not token or token not in srv.unlocks:
                return 0
            if touch:
                srv.unlocks[token] = now + UNLOCK_MINUTES * 60
            return max(1, int(srv.unlocks[token] - now))


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
                self._body_read = len(self.rfile.read(length)) == length
            except OSError:
                pass

    def _refused(self):
        """The request didn't carry this run's access key (see check_access)."""
        return self._json({"error": "Hoard didn't recognise this page. Open Hoard again, or the address it printed."}, 401)

    # ---- reading
    def do_GET(self):
        """Authenticate and dispatch a registered read endpoint, including static pages."""
        self._body_read = False   # (each request on a kept-alive connection starts afresh)
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        u = urlparse(self.path)
        route = api_routes.find("GET", u.path)
        if route is None:
            return self._send(404, b"Not found", "text/plain")
        if route.auth != "public" and not check_access(self, self.server.key, in_address=route.image_key):
            return self._refused()
        self.server.last_seen = time.time()
        return route.handler(self, u.path, None, parse_qs(u.query))


    # ---- Projects (hoard/vpm): the Creator Companion's and ALCOM's projects, with your library in them


    # ---- acting
    def do_POST(self):
        """Check method, origin, key and body size from the route before calling its handler."""
        path, srv = urlparse(self.path).path, self.server
        self._body_read = False   # (each request on a kept-alive connection starts afresh)
        route = api_routes.find("POST", path)
        if route is None:
            self._drop_body()
            return self._send(404, b"Not found", "text/plain")
        if (not self._host_ok() or self.client_address[0] not in LOOPBACK
                or not (self.headers.get("Content-Type") or "").startswith("application/json")):
            self._drop_body()
            return self._json({"error": "That only works on the computer running Hoard."}, 403)
        if route.auth == "key" and not check_access(self, srv.key):
            self._drop_body()
            return self._refused()
        srv.last_seen = time.time()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "Bad request."}, 400)
        if length < 0:
            return self._json({"error": "Bad request."}, 400)
        if length > route.max_body:
            message = ("That's too large to be saved pages. Import fewer at a time."
                       if route.path in ("/api/import", "/api/wishlists/import") else "That's too large.")
            return self._json({"error": message}, 413)
        raw = self.rfile.read(length)
        self._body_read = len(raw) == length
        try:
            body = json.loads(raw or b"{}")
        except (ValueError, RecursionError):
            return self._json({"error": "Bad request."}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "Bad request."}, 400)
        return route.handler(self, path, body, {})


SHARED_MARK = b"//@include shared.js\n"


def page_source(name: str, cfg: dict | None = None, accept_language: str | None = None) -> bytes:
    """Serve one app shell at both public addresses, with its view modules and compiled Look inside trial.

    All code remains in one inline script allowed by the Content-Security-Policy's hash. Shared styles and the
    chosen theme follow the view styles, and the translation catalog precedes the script. Translated pages stay
    hidden until their first translation, avoiding an English flash during startup.
    """
    # Both public addresses share the same shell and load their view code once.
    page = (WEB / ("library.html" if name == "downloads.html" else name)).read_bytes()
    page = page.replace(b"<!-- @include downloads.html -->", (WEB / "downloads.html").read_bytes())
    if SHARED_MARK in page:
        page = page.replace(SHARED_MARK, b"\n".join((WEB / part).read_bytes().replace(b"\r\n", b"\n") for part in ("shared.js", "products.js", "inside.generated.js", "view-common.js", "library.js", "downloads.js", "app.js")) + b"\n", 1)
    d = (cfg or {}).get("display") if isinstance((cfg or {}).get("display"), dict) else {}
    # the styles' layouts (web/looks.css, both pages alike), then the theme's colours
    looks = '<style id="looks">\n' + (WEB / "looks.css").read_text("utf-8").replace("\r\n", "\n") + "</style>\n"
    style = '<style id="theme">\n' + themes.css(d.get("theme"), d.get("mode")) + "\n</style>\n"
    page = page.replace(b"</head>", looks.encode() + style.encode() + b"</head>", 1)
    # the font, spacing, card outlines (Settings, Accessibility) and style (Appearance) you chose, on the page from its
    # first moment
    marks = (' data-font="dyslexic"' if d.get("font") == "dyslexic" else "") + (' data-spacing="wide"' if d.get("spacing") is True else "")
    marks += ' data-cards="outlined"' if d.get("card_outlines") is True else ""
    marks += ' data-adult="show"' if d.get("blur_adult") is False else ""   # (adult pictures blurred unless you say: #311)
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
        """One value from the address (at most 40 characters)."""
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
        """One of the guide bar's dropdowns."""
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
    showed, "chosen": the ones left ticked}}. Only a file that was shown and unticked is left out, and one shown and
    ticked is downloaded whatever an earlier choice or a rule says (downloader.left_out); a file that wasn't shown is
    left to them. Anything else is ignored."""
    if not isinstance(raw, dict):
        return None
    names = lambda v: [n for n in v[:500] if isinstance(n, str) and 0 < len(n) <= 500] if isinstance(v, list) else []  # noqa: E731
    out = {}
    for key, pick in list(raw.items())[:5000]:
        if not (isinstance(key, str) and 0 < len(key) <= 400 and isinstance(pick, dict)):
            continue
        if names(pick.get("shown")):
            out[key] = {"shown": names(pick.get("shown")), "chosen": names(pick.get("chosen"))}
    return out or None


def remember_choice(kept: dict[str, set], chosen: dict, rules=()) -> dict[str, list]:
    """The files left out of each product from now on (config.json's "file_skip", issue #225), after choosing what
    to download: those of the files shown that weren't ticked, and any left out before that weren't shown. One that
    one of your rules leaves out isn't remembered: the rule keeps it out (and it comes back if you take the rule away)."""
    kept = dict(kept)
    for key, pick in chosen.items():
        shown, store = set(pick["shown"]), key.split(":", 1)[0]
        left = (kept.get(key, set()) - shown) | {n for n in shown - set(pick["chosen"]) if not ruled_out(rules, store, n)}
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
    srv.start_worker("Checking Unity catalog", reseal_in_background, srv, cfg)
    srv.needs_reader.register(srv.scheduler)
    srv.jobs.kick()
    srv.project_jobs.kick()
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


# Import only after the HTTP facade is complete; handlers refer to its shared services.
from . import api as api_routes
api_routes.install(Handler)
ACTIONS = tuple(route.path for route in api_routes.ROUTES if route.method == "POST")
KEYLESS_ACTIONS = tuple(route.path for route in api_routes.ROUTES if route.auth in ("entry", "instance"))
