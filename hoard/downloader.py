"""Keeping local copies: downloading from each store, the records of what's on disk, and the catalog files."""
from __future__ import annotations

from . import storage

import hashlib
import json
import os
import re
import shutil
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests

from .browser import ProfileBusy, STORE_SITES, SigninsUnprotected, _on_sites, _playwright, launch_context, settle
from .common import NotLoggedIn, log, now_iso, pause, tick
from .library import DOWNLOADABLE, STORES, booth_cards, extract_page_json, gumroad_cards, scroll_inventory
from .config import root_dir
from .net import NETWORK_ERRORS, STORE_HOSTS, reachable
from .paths import PROBE_DIR, STORE_PYTHON_NOTE, store_python
from . import egress, itch, pace, vault
from .safety import DataFileError, UnsafePath, clean_text, fetch_public, open_under, rel_to_path, remember_sealed, safe_name, save_browser_download, scrub, seal, store_link, valid_rel
from .storage import seal_status as check_seal, read_document as read_json_file, archive_document as set_aside, write_document as write_file_safely
from .tags import TagMatcher, TagStore, clean_note, clean_tag, tag_key

try:
    from tqdm import tqdm
except ImportError:  # progress bars are optional
    tqdm = None


# Store code lives in hoard/stores; these aliases preserve the public Python API.
from .stores import install as _install_stores
_install_stores('downloader', globals())


STOPWORDS = set("""
a an and are as at be by for from in into is it its of on or the to with without your you my our
this that these those v ver version update updated new free paid full set pack bundle edition
package unitypackage zip file files ft feat x vs vrchat vrc
""".split())


def clean_manifest(data, store_dir: Path, trust_links: bool = True) -> tuple[dict, int]:
    """Keep only well-formed manifest records whose folder and files stay inside the store's folder.

    Text is cleaned, and a record's link is kept only when it leads to that store's own website and the
    manifest is trusted (see check_seal); otherwise it's dropped until the next sync fetches it again.
    Returns the cleaned data and how many entries were dropped.
    """
    store = store_dir.name.lower()
    assets = data.get("assets") if isinstance(data, dict) and isinstance(data.get("assets"), dict) else {}
    kept, dropped = {}, 0
    for key, rec in assets.items():
        try:
            if not isinstance(key, str) or len(key) > 500 or not isinstance(rec, dict):
                raise UnsafePath("malformed record")
            folder_path = rel_to_path(store_dir, rec.get("folder"))
        except UnsafePath:
            dropped += 1
            continue
        files = {}
        for fk, f in (rec.get("files") if isinstance(rec.get("files"), dict) else {}).items():
            if isinstance(fk, str) and len(fk) <= 500 and isinstance(f, dict):
                try:
                    rel_to_path(folder_path, f.get("path"))
                    files[fk] = f
                except UnsafePath:
                    dropped += 1
        rec = {**rec, "files": files, "name": clean_text(rec.get("name"), 300) or "Untitled",
               "creator": clean_text(rec.get("creator"), 200) or "Unknown creator",
               "url": store_link(store, rec.get("url")) if trust_links else None}
        if "location" in rec:   # a Local item listed where it is (issue #80): only from a manifest Hoard sealed here
            if store != "local" or not trust_links or not valid_location(rec["location"]):
                rec.pop("location")
        if rec.get("note") is not None:
            rec["note"] = clean_text(rec["note"], 300) or None
        if rec.get("variants") is not None:
            rec["variants"] = clean_text(rec["variants"], 300) or None
        kept[key] = rec
    rest = {k: v for k, v in (data.items() if isinstance(data, dict) else []) if k not in ("assets", "integrity")}
    return {**rest, "assets": kept}, dropped


@dataclass
class Report:
    """Tally of one sync: new, updated, skipped and failed items, printed as a summary at the end."""
    new_assets: list = field(default_factory=list)
    new_files: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    # a check for updates (a dry run): per product already downloaded, what the store has that isn't on disk
    available: list = field(default_factory=list)
    got: set = field(default_factory=set)             # products (tag_key) that had a file saved in this run
    got_files: set = field(default_factory=set)       # (tag_key, file) saved in this run, named as a check names it
    # what each product has on its store, read without downloading it (issue #225: to choose from): {tag_key: {...}}
    listed: dict = field(default_factory=dict)

    def saved(self, store: str, name: str, file: str, *also: str | None) -> None:
        """A file saved: its product, and the file as Check for updates names it, so only what came is taken off
        the list of updates (asset_updates.after_download). also: other names the product goes by."""
        for n in (name, *also):
            if n:
                self.got.add(tag_key(store, n))
                self.got_files.add((tag_key(store, n), file))
    stores_done: list = field(default_factory=list)   # stores read to the end, without an error
    retries: int = 2   # how many more times a failed file download is tried (Settings; see with_retries)

    def print(self) -> None:
        """Print the summary, then the updated, skipped and failed items one per line."""
        log("\n=== Summary ===")
        log(f"New assets: {len(self.new_assets)}   New files: {len(self.new_files)}   "
            f"Updated files: {len(self.updated)}   Skipped: {len(self.skipped)}   Failed: {len(self.failed)}")
        for title, items in (("Updated on the store since last sync", self.updated),
                             ("Skipped", self.skipped), ("Failed", self.failed)):
            if items:
                log(f"\n{title}:")
                for line in items:
                    log(f"  - {line}")


def skip_product(args, store: str, name: str, creator: str) -> bool:
    """Is this product outside what was asked for: --only (a name or creator), or keys (products chosen on the
    Downloads page, by tag_key)? Or one you chose to always skip (issue #107), unless it's chosen by name now?"""
    if args.only and args.only.lower() not in f"{name} {creator}".lower():
        return True
    keys = getattr(args, "keys", None)
    if keys:
        return tag_key(store, name) not in keys
    return tag_key(store, name) in (getattr(args, "skip", None) or ())


DIRECT_STORES = ("jinxxy", "gumroad")   # stores whose products can be opened one by one, from the library


def direct_targets(library_items: list[dict], stores: list[str], only: str | None, keys, items) -> dict:
    """For a download of chosen products (items: library keys, from the Library; keys: tag keys, from Downloads;
    only: a name or creator): each store's chosen products, from the library, where the store's reader can go
    straight to them (a Jinxxy item's page, a Gumroad purchase's download page) instead of reading through the whole
    store to find them. A store that isn't in the result is read in full, as before: it can't be opened product by
    product, or a chosen product isn't in the library, or has no link to open."""
    if not (only or keys or items):
        return {}
    keys, items = set(keys or ()), set(items or ())
    out = {}
    for store in stores:
        if store not in DIRECT_STORES:
            continue
        mine = [i for i in library_items if i.get("store") == store]
        if items:
            chosen = [i for i in mine if i.get("key") in items]
        elif keys:
            wanted = {k for k in keys if k.startswith(store + ":")}
            chosen = [i for i in mine if tag_key(store, i.get("name") or "") in wanted]
            if {tag_key(store, i.get("name") or "") for i in chosen} != wanted:
                continue   # a chosen product the library doesn't have (by that name): read the store in full
        else:
            chosen = [i for i in mine if only.lower() in f"{i.get('name', '')} {i.get('creator', '')}".lower()]
        link = "url" if store == "jinxxy" else "download_url"
        if chosen and all(store_link(store, i.get(link)) for i in chosen):
            out[store] = [dict(i) for i in chosen]
    return out


def would_get(args, report: Report, store: str, rec: dict, name: str, creator: str, file: str, changed: bool,
              deleted_here: bool = False, also: str | None = None) -> None:
    """A dry run: note a file the store has that isn't on disk. For a product already downloaded, a file the store
    changed or added goes on the list of updates the Downloads page shows (issue #26); one downloaded before and
    since deleted from disk, unchanged, isn't an update (it's downloaded again all the same). also: the product's name
    in your library, when its page names it differently (a chosen Jinxxy item's)."""
    log(f"    would {'update' if changed else 'download again' if deleted_here else 'download'}: {file}")
    if getattr(args, "listing", False):   # what's there to choose from (issue #225), and not an update either way
        entry = report.listed.setdefault(tag_key(store, name), {"store": store, "name": name, "creator": creator, "files": []})
        if also:   # (the same list, under the name it was asked for by)
            report.listed.setdefault(tag_key(store, also), entry)
        if file not in entry["files"] and len(entry["files"]) < 500:
            entry["files"].append(file)
        return
    if rec.get("files") and not deleted_here:
        report.available.append({"store": store, "key": tag_key(store, name), "name": name, "creator": creator,
                                 "file": file, "kind": "changed" if changed else "new"})


# Files to leave out of every download (issue #225): a rule names a kind of file (by the end of its name) or words in
# its name, for every store or one. config.json's "file_rules": [{"store": "all" or a store, "kind": ...} or
# {"store": ..., "words": "quest android"}]. A product's own files you left out are remembered too ("file_skip").
FILE_KINDS = {
    "unitypackage": ("Unity packages", (".unitypackage",)),
    "archive": ("Archives", (".zip", ".7z", ".rar", ".tar", ".gz")),
    "layered": ("Layered images", (".psd", ".psb", ".clip", ".kra", ".sai", ".sai2", ".xcf")),
    "picture": ("Pictures and textures", (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr", ".webp", ".dds", ".bmp")),
    "blender": ("Blender files", (".blend", ".blend1")),
    "substance": ("Substance Painter projects", (".spp", ".sbsar", ".sbs")),
    "model": ("3D models", (".fbx", ".obj", ".vrm", ".glb", ".gltf", ".dae", ".3ds", ".max", ".ma", ".mb")),
    "audio": ("Sound", (".wav", ".mp3", ".ogg", ".flac", ".m4a")),
    "video": ("Video", (".mp4", ".mov", ".webm", ".mkv", ".avi")),
    "document": ("Documents", (".pdf", ".txt", ".md", ".rtf", ".docx")),
}
MAX_RULES = 50
MAX_REMEMBERED = 5000   # products whose files you left out, remembered


def file_rules(cfg: dict) -> list[dict]:
    """Your rules for files to leave out, checked: each {"store": "all" or a store, "kind" or "words"}."""
    out: list[dict] = []
    raw = cfg.get("file_rules") if isinstance(cfg.get("file_rules"), list) else []
    for r in raw[:MAX_RULES]:
        if not isinstance(r, dict) or r.get("store") not in ("all", *DOWNLOADABLE):
            continue
        if r.get("kind") in FILE_KINDS:
            out.append({"store": r["store"], "kind": r["kind"]})
        elif isinstance(r.get("words"), str):
            words = [w for w in re.split(r"[\s,]+", unicodedata.normalize("NFKC", r["words"]).lower()) if 0 < len(w) <= 40][:20]
            if words:
                out.append({"store": r["store"], "words": " ".join(dict.fromkeys(words))})
    return out


def ruled_out(rules: list[dict], store: str, file: str) -> str | None:
    """Why one of your rules leaves this file out ("Layered images", or the word its name has), or None."""
    name = unicodedata.normalize("NFKC", file or "").lower()
    for r in rules:
        if r["store"] not in ("all", store):
            continue
        if "kind" in r and name.endswith(FILE_KINDS[r["kind"]][1]):
            return FILE_KINDS[r["kind"]][0]
        for w in r.get("words", "").split():
            if (re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", name) if w.isascii() else w in name):
                return f"named with {w}"
    return None


def remembered_files(cfg: dict) -> dict[str, set]:
    """The files you left out of each product (Download new's Choose files), by its tag key: left out from then on."""
    raw = storage.current_references("config.json", cfg).get("file_skip") if isinstance(cfg.get("file_skip"), dict) else {}
    return {k: {n for n in v[:500] if isinstance(n, str) and n} for k, v in list(raw.items())[:MAX_REMEMBERED]
            if isinstance(k, str) and 0 < len(k) <= 400 and isinstance(v, list)}


def left_out(args, report: Report, store: str, name: str, file: str, *also: str) -> bool:
    """A file left out of this download. First what you chose for it now (args.files: {tag_key: {"shown": the files
    listed, "chosen": the ones ticked}}): only a file that was listed and unticked is left out, and one you ticked is
    downloaded whatever a rule says. Then a file you left out of the product before (args.remembered), and then one
    your rules name (args.rules: issue #225). A file that wasn't listed (a product whose name makes the same key, a
    file the creator added or relabelled since) is only left out by a rule. also: other names the product goes by (a
    chosen Jinxxy item's name in your library, besides its page's). It's named in the summary as skipped. Checks for
    updates see every file."""
    if getattr(args, "dry_run", False):
        return False
    keys = [tag_key(store, n) for n in (name, *also) if n]
    chosen = getattr(args, "files", None)
    pick = next((chosen[k] for k in keys if k in chosen), None) if isinstance(chosen, dict) else None
    label = STORES[store]["label"] if store in STORES else store
    if isinstance(pick, dict) and file in pick.get("shown", ()):
        if file in pick.get("chosen", ()):
            return False
        why = "left out, as you chose"
    elif isinstance(remembered := getattr(args, "remembered", None), dict) and any(file in remembered.get(k, ()) for k in keys):
        why = "left out, as you chose before"
    else:
        rules = getattr(args, "rules", None)   # (only what a sync gave it: a stand-in's arguments may have anything)
        rule = ruled_out(rules if isinstance(rules, list) else [], store, file)
        if not rule:
            return False
        why = f"left out by your rule ({rule})"
    log(f"    {why}: {file}")
    report.skipped.append(f"{label}: {name} / {file} - {why}")
    return True


_SAID_CHANGED: set = set()   # (manifest, its contents' hash) already reported as changed outside Hoard, this run

RETRY_WAITS = (5.0, 15.0, 30.0)   # seconds before each try again (issue #19)
NO_RETRY_STATUS = {400, 401, 403, 404, 410, 451}   # a store's answer that won't change by asking again


def download_retries(cfg: dict) -> int:
    """How many times a failed file download is tried again (Settings, Failed downloads): 0 to 5, 2 unless you chose
    otherwise."""
    n = cfg.get("download_retries", 2)
    return n if isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 5 else 2


class BrowserClosed(RuntimeError):
    """The browser tab a store was being read in closed (or the whole browser did) part way through a product."""


def tab_closed(e: BaseException) -> bool:
    """Does this error mean the browser tab it happened in (or the whole browser) has gone?"""
    text = str(e)
    return isinstance(e, BrowserClosed) or any(w in text for w in ("has been closed", "Target closed", "Connection closed"))


def worth_retrying(e: BaseException) -> bool:
    """Could trying the same file again go differently? Not after a refusal Hoard made itself (an unsafe address or
    path), a sign-in that's gone, or a store saying the file isn't there or isn't yours; nor in a tab that has gone
    (the store's loop opens a new one and tries the whole product again)."""
    if isinstance(e, (NotLoggedIn, egress.UnsafeRequest, UnsafePath, SigninsUnprotected)) or tab_closed(e):
        return False
    status = getattr(getattr(e, "response", None), "status_code", None)
    return status not in NO_RETRY_STATUS


def with_retries(report: "Report", what: str, attempt, sleep=None):
    """attempt(), tried again (up to download_retries more times, waiting a little longer each time) when it fails
    in a way that might go differently next time: a dropped connection, a timeout, a busy server, a checksum that
    didn't match. The last failure is raised as it was. A download stopped with Stop still stops at once."""
    tries = report.retries
    for n in range(tries + 1):
        try:
            return attempt()
        except Exception as e:
            if n >= tries or not worth_retrying(e):
                raise
            wait = RETRY_WAITS[min(n, len(RETRY_WAITS) - 1)]
            log(f"    {what}: {e} - trying again in {wait:.0f} s ({n + 1} of {tries})")   # Stop is noticed here
            (sleep or pause)(wait)   # (and during the wait)


def amount(n: int) -> str:
    """A size in bytes, as people read it."""
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


def duration(s: float) -> str:
    """Seconds, as people read a time left."""
    s = max(0, round(s))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{round(s / 60)} min"
    return f"{s // 3600} h {round(s % 3600 / 60)} min"


class Transfer:
    """How a file download is going, told to the app each time it's called with (bytes so far, whole size or None):
    how much has come in, how fast (smoothed over the last few seconds, so it doesn't jump about) and how long is
    left."""

    def __init__(self, fname: str, clock=time.monotonic):
        self.fname, self.clock = fname, clock
        self.last: tuple[float, int] | None = None   # when it was last told, and how much had come in then
        self.speed: float | None = None

    def __call__(self, got: int, whole: int | None = None) -> None:
        now = self.clock()
        if self.last is not None and now > self.last[0]:
            rate = max(0, got - self.last[1]) / (now - self.last[0])
            self.speed = rate if self.speed is None else 0.3 * rate + 0.7 * self.speed
        self.last = (now, got)
        eta = (whole - got) / self.speed if whole and self.speed and whole > got else None
        text = f"    downloading {self.fname}: {amount(got)}"
        text += f" of {amount(whole)} ({min(100, got * 100 // whole)}%)" if whole else " so far"
        if self.speed is not None:
            text += f", {amount(int(self.speed))}/s"
        if eta is not None:
            text += f", {duration(eta)} left"
        tick(text, {"file": self.fname, "got": got, "total": whole or None,
                    "speed": None if self.speed is None else round(self.speed),
                    "eta": None if eta is None else round(eta)})


def downloading(fname: str) -> Transfer:
    """A progress callback for egress.download: how fname's download is going, shown while it downloads."""
    return Transfer(fname)


def browser_download_file(dl) -> Path | None:
    """Where the browser is writing a download, from Playwright's own record of it (Chromium writes to that name
    plus .crdownload until it's complete, then renames it). None when Playwright doesn't say."""
    try:
        where = dl._impl_obj._artifact._initializer.get("absolutePath")
    except Exception:
        return None
    return Path(where) if isinstance(where, str) and where else None


def _file_size(path: Path) -> int | None:
    """A file's size, or None when it isn't there."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def wait_for_browser_download(dl, fname: str, stall_s: float | None = None) -> None:
    """Wait for a download the browser is making to end, saying how far it's got.

    Saving a browser download waits for it to finish, with no time limit and no way for Stop to reach it. So a
    download the store stopped sending without hanging up would hold up the whole job (and every job after it)
    for ever. Here, a download that gets no bigger for stall_s seconds is cancelled and raised as a failure, which
    is tried again like any other; and Stop cancels it at once. Returns when the file is complete or the browser
    has given up on it (saving it then says which)."""
    where = browser_download_file(dl)
    if where is None:
        return
    stall_s = egress.STALL_SECONDS if stall_s is None else stall_s
    part = where.with_name(where.name + ".crdownload")
    size, seen, ended = -1, False, False
    began = moved = said = time.monotonic()
    report = Transfer(fname)
    try:
        while True:
            done, growing = _file_size(where), _file_size(part)
            if done is not None and growing is None:
                ended = True   # complete
                return
            now = time.monotonic()
            if growing is None and (seen or now - began >= 5):   # (or it was over before its file appeared)
                ended = True   # the browser gave up on it (and deleted what it had): saving it says why
                return
            if growing is not None:
                seen = True
                if growing != size:
                    size, moved = growing, now
            if now - moved >= stall_s:
                raise RuntimeError(f"the download stalled: nothing more came in for {stall_s:.0f} s")
            if now - said >= egress.PROGRESS_EVERY:
                said = now
                report(max(size, 0))   # Stop is noticed here
            _pause(dl, 0.5)
    finally:
        if not ended:   # stalled, or stopped
            try:
                dl.cancel()
            except Exception:
                pass


def _pause(dl, seconds: float) -> None:
    """Wait a moment, letting Playwright handle what the browser says meanwhile (unless the tab has closed)."""
    try:
        dl.page.wait_for_timeout(seconds * 1000)
    except Exception:
        pause(seconds)


SAVE_EVERY = 10.0   # seconds: while downloading, a store's manifest is saved at most this often (Manifest.checkpoint)


class Manifest:
    """Per-store record of what's been downloaded and where."""

    def __init__(self, store_dir: Path):
        """Load a store's manifest, or start an empty one."""
        self.store_dir = store_dir
        self.path = store_dir / "_manifest.json"
        raw, trusted = {}, True
        if self.path.exists():
            try:
                raw = read_json_file(self.path)
                trusted = self._check(raw)
            except DataFileError as e:
                aside = set_aside(self.path)
                log(f"{store_dir.name}: {e}, so it was kept as {aside.name} and a new record started. "
                    "Files already on disk are kept.")
        self.data, dropped = clean_manifest(raw, store_dir, trust_links=trusted)
        if dropped:
            log(f"{store_dir.name}: ignored {dropped} entries in _manifest.json that pointed outside {store_dir} "
                "or weren't valid. Check who else can change that folder.")
        self.assets: dict = self.data.setdefault("assets", {})
        if store_dir.name == "Local" and trusted:
            storage.identify_local(self.assets)
        self._saved, self._saved_at = self._contents(), 0.0   # what's on disk, and when this last wrote it

    def _check(self, raw) -> bool:
        """Check the manifest's seal, say what it means, and return whether its links can be trusted."""
        status = check_seal(raw, self.path)
        name = self.store_dir.name
        if status == "changed":
            # one copy of each changed version, said once: a manifest is opened by checks, moves and the Downloads
            # page too, which don't save it, so it stays "changed" until a sync does, and a copy each time piled up
            data = self.path.read_bytes()
            kept = next((c for c in self.store_dir.glob("_manifest.changed-*.json")
                         if c.is_file() and not c.is_symlink() and c.stat().st_size == len(data) and c.read_bytes() == data),
                        None)
            if kept is None:
                kept = self.path.with_name(f"_manifest.changed-{time.strftime('%Y%m%d-%H%M%S')}.json")
                shutil.copy2(self.path, kept)
            if (str(self.path), hashlib.sha256(data).hexdigest()) not in _SAID_CHANGED:
                _SAID_CHANGED.add((str(self.path), hashlib.sha256(data).hexdigest()))
                log(f"{name}: _manifest.json was changed by something other than Hoard since it last saved it. "
                    f"Its store links won't be used until this sync fetches them from {name} again. A copy is kept as "
                    f"{kept.name}. Check what else can change {self.store_dir}.")
        elif status == "foreign":
            log(f"{name}: _manifest.json was last saved by Hoard on another computer, so its store links will "
                f"be fetched from {name} again. To share this folder between computers, copy integrity.key from Hoard's "
                "app-data folder on one to the other.")
        return status in ("sealed", "unsealed")

    def save(self) -> None:
        """Seal the manifest and write it through a temporary file, so a crash can't leave it half-written."""
        write_file_safely(self.path, json.dumps(seal(self.data), indent=2, ensure_ascii=False))
        remember_sealed(self.path)
        if self.store_dir.name == "Local":
            storage.identify_local(self.assets)
        self._saved, self._saved_at = self._contents(), time.monotonic()

    def save_changes(self) -> None:
        """Save, if anything changed since the manifest was read or last saved. Every sync ends with this, however it
        ends (a stop, an error), so every file that finished downloading is recorded; and a store that was never
        used isn't given a manifest it never had."""
        if self._contents() != self._saved:
            self.save()

    def checkpoint(self) -> None:
        """While downloading: save changes, at most once every SAVE_EVERY seconds. A whole manifest rewritten after every
        file and every product adds up in a large library; the sync's closing save_changes() writes whatever's newer."""
        if time.monotonic() - self._saved_at >= SAVE_EVERY:
            self.save_changes()

    def _contents(self) -> str:
        """The manifest as text, to tell whether it changed since it was read or saved."""
        return json.dumps(self.data, sort_keys=True, ensure_ascii=False)

    def record(self, key: str, creator: str, name: str) -> dict:
        """Existing record for a product, or a new one with a folder no other product uses."""
        if key in self.assets:
            return self.assets[key]
        used = {same_name_key(a.get("folder") or "") for a in self.assets.values()}
        base = f"{safe_name(creator)}/{safe_name(name)}"
        folder = base
        if same_name_key(folder) in used:   # another product's name cleans up to the same folder name
            folder = f"{base} [{short_id(key)}]"
            n = 2
            while same_name_key(folder) in used:
                folder, n = f"{base} [{short_id(key)}-{n}]", n + 1
        rec = {"key": key, "name": name, "creator": creator, "folder": folder,
               "files": {}, "first_seen": now_iso()}
        self.assets[key] = rec
        return rec


class StoreRecords:
    """One store's records in every library folder (hoard/libraries.py), for a sync. A product already in one of
    them is kept up to date where it is; a new one goes to the downloads folder. A product last seen in a library
    folder whose drive isn't connected is left alone (away), never downloaded again into the downloads folder.
    Used like a Manifest: record(), checkpoint(), save_changes(); and folder_of(rec) says where a record's files go."""

    def __init__(self, cfg: dict, root: Path, store_name: str):
        from . import libraries
        self.main = Manifest(root / store_name)
        self.store_dir = self.main.store_dir
        self.others = [Manifest(lib / store_name) for lib in libraries.other_folders(cfg)
                       if libraries.available(lib) and (lib / store_name / "_manifest.json").is_file()]
        self._away = libraries.away(cfg, store_name)
        self._owner: dict[int, Manifest] = {}

    def away(self, key, what: str, report: "Report") -> bool:
        """Is this product in a library folder whose drive isn't connected? Then it's noted as skipped."""
        folder = self._away.get(str(key))
        if folder is None or (key in self.main.assets and self.main.assets[key].get("files")):
            return False
        report.skipped.append(f"{what} - it's in {folder}, whose drive isn't connected")
        return True

    def record(self, key: str, creator: str, name: str) -> dict:
        """The product's record where it is (the downloads folder first), or a new one in the downloads folder."""
        if not (key in self.main.assets and self.main.assets[key].get("files")):
            for m in self.others:
                rec = m.assets.get(key)
                if rec and rec.get("files"):
                    self._owner[id(rec)] = m
                    return rec
        rec = self.main.record(key, creator, name)
        self._owner[id(rec)] = self.main
        return rec

    def folder_of(self, rec: dict) -> Path:
        """Where a record's files are, in the library folder it's in."""
        return rel_to_path(self._owner.get(id(rec), self.main).store_dir, rec["folder"])

    def checkpoint(self) -> None:
        """Save each library folder's records, at most once every SAVE_EVERY seconds."""
        for m in (self.main, *self.others):
            m.checkpoint()

    def save_changes(self) -> None:
        """Save whatever changed in each library folder's records."""
        for m in (self.main, *self.others):
            m.save_changes()


def valid_location(value) -> bool:
    """A Local item's own folder, as it's kept: a plain absolute path, written as the system writes it."""
    return (isinstance(value, str) and 0 < len(value) <= 1000 and "\x00" not in value and os.path.isabs(value)
            and os.path.normpath(value) == value)


def record_folder(sdir: Path, rec: dict) -> Path:
    """Where a record's files are: inside its store's folder, or for a Local item listed where it is (issue #80),
    the folder you chose. Raises UnsafePath for a folder that isn't plain, or is a link."""
    loc = rec.get("location")
    if loc is None:
        return rel_to_path(sdir, rec["folder"])
    if sdir.name != "Local" or not valid_location(loc) or os.path.islink(loc):
        raise UnsafePath("not a folder Hoard can list")
    return Path(loc)


def same_name_key(name: str) -> str:
    """How a file system that ignores case and Unicode form (Windows, macOS) sees a name."""
    return unicodedata.normalize("NFC", name).casefold()


def short_id(key: str) -> str:
    """A short, stable tag for a store id, used to tell apart names that would otherwise collide."""
    return hashlib.sha256(str(key).encode()).hexdigest()[:8]


def distinct_name(name: str, fid: str, rec: dict, offered: set) -> str:
    """name, unless a different file that's still offered (its id in offered) already has that name in this
    product's folder. Then the two are different files whose names clean up alike, so this one gets a stable tag
    instead of overwriting the other. (A name held by a file that's no longer offered is the creator's update
    of it, and is replaced as before.)"""
    holder = next((k for k, v in rec["files"].items() if same_name_key(v.get("path") or "") == same_name_key(name)), None)
    if holder is None or holder == fid or holder not in offered:
        return name
    folder, slash, last = name.rpartition("/")
    stem, dot, ext = last.rpartition(".")
    tagged = f"{stem} [{short_id(fid)}].{ext}" if dot and stem else f"{last} [{short_id(fid)}]"
    return folder + slash + tagged


def removed_product(store: str, name: str, report: "Report") -> bool:
    """True (and noted in the report) for a product you removed from your library: it isn't downloaded."""
    if tag_key(store, name) in _removed_keys():
        report.skipped.append(f"{STORES[store]['label']}: {name} - removed from your library, so not downloaded")
        return True
    return False


def _removed_keys() -> set:
    """The products you removed from your library, which no download or sync gets."""
    from .marks import MarkStore   # read again once it changes: removing something takes effect on the next product
    return MarkStore().keys("removed")


def browser_cookies(cfg: dict, store: str) -> tuple[list, str]:
    """A store's cookies (only that store's) and a matching User-Agent, from its saved sign-in.

    They stay in memory for this run and are only ever sent to that store's own sites.
    """
    with _playwright()() as p:
        ctx = launch_context(p, cfg, True, store)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            ua = page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
            cookies = [c for c in ctx.cookies() if _on_sites(c["domain"], STORE_SITES[store])]
        finally:
            ctx.close()
    return cookies, ua


PICTURE_TYPES = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF87a", "gif"), (b"GIF89a", "gif"))


def picture_extension(path: Path) -> str | None:
    """What kind of picture a file is, from its first bytes (Gumroad's picture addresses don't say)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return next((ext for magic, ext in PICTURE_TYPES if head.startswith(magic)), None)


def save_thumbnail(url: str | None, folder: Path, referer: str | None = None) -> None:
    """Save a product's store image as _thumbnail.<ext> in its folder, once. Failures are only logged.

    Image addresses come from store pages, so they're fetched through a connection that only reaches public
    internet addresses, and only raster images are kept.
    """
    if not url or any(folder.glob("_thumbnail.*")):
        return
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/140.0 Safari/537.36"}
    if referer:
        headers["Referer"] = referer
    got = fetch_public(url, headers, 15 * 1024 * 1024)
    exts = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/avif": "avif"}
    if not got or got[1] not in exts:
        log("    (thumbnail skipped)")
        return
    write_file_safely(folder / f"_thumbnail.{exts[got[1]]}", got[0])


def store_url(url: str, sites: list[str]) -> bool:
    """True when url is an https (or http) address on one of the store's own sites."""
    u = urlparse(url or "")
    return u.scheme == "https" and bool(u.hostname) and not u.username and _on_sites(u.hostname, sites)


# ----------------------------------------------------------------------------- Jinxxy
#
# Jinxxy has no public API for buyers, so this drives the website with your saved
# login: list the inventory, open each item, click each file's download button.
# If Jinxxy changes its layout, run `probe jinxxy` and adjust item_link_pattern
# in config.json (or share the probe output to rework this into direct API calls).

DOWNLOAD_BUTTONS_JS = r"""
({ allowAll, hosts }) => {
  const dl = /download|ダウンロード/i, all = /download\s*all|all\s*files|まとめて/i;
  const hostOk = new RegExp('(^|\\.)(' + hosts.join('|') + ')$', 'i');
  const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const text = e => [e.innerText, e.getAttribute('aria-label'), e.getAttribute('title')].filter(Boolean).join(' ');
  // links in product descriptions ("Download Poiyomi here") lead off-site; only follow the store's own
  const onSite = e => {
    if (e.tagName !== 'A' || e.hasAttribute('download')) return true;
    const h = e.getAttribute('href') || '';
    if (!h || h.startsWith('#') || h.startsWith('javascript:') || h.startsWith('blob:')) return true;
    try { return hostOk.test(new URL(h, location.href).hostname); } catch (x) { return false; }
  };
  // Never these, whatever they say about downloading: resetting download credits or limits, and the like
  const never = /reset|credit|limit|remove|delete|archive|report|refund|review|how to|instruction/i;
  document.querySelectorAll('[data-adl-idx]').forEach(e => e.removeAttribute('data-adl-idx'));
  const cands = [...document.querySelectorAll('button, a, [role="button"]')]
    .filter(e => visible(e) && onSite(e) && dl.test(text(e)) && !never.test(text(e)) && (allowAll || !all.test(text(e))));
  const leaf = cands.filter(e => !cands.some(o => o !== e && e.contains(o)));
  const set = new Set(leaf);
  return leaf.map((e, i) => {
    e.setAttribute('data-adl-idx', String(i));
    let row = e;
    while (row.parentElement && row.parentElement !== document.body) {
      const p = row.parentElement;
      const n = [...p.querySelectorAll('button, a, [role="button"]')].filter(x => set.has(x)).length;
      if (n > 1 || (p.innerText || '').length > 500) break;
      row = p;
    }
    const label = row.innerText || text(e);
    // a plain link to the file (Jinxxy's are), which can be downloaded without the browser
    const href = e.tagName === 'A' && !e.hasAttribute('download') && /^https?:/i.test(e.href) ? e.href : '';
    return { idx: i, label: label.replace(/\s+/g, ' ').trim().slice(0, 300), href };
  });
}
"""


def click_download(ctx, page, idx: int, timeout_s: int):
    """Click a tagged button and return the Download it triggers (in this tab or a popup)."""
    captured = []
    hooked = list(ctx.pages)
    popups = []

    def on_download(d):
        """Note a download the click started."""
        captured.append(d)

    def on_page(pg):
        """Watch a tab the click opened for its download too."""
        pg.on("download", on_download)
        hooked.append(pg)
        popups.append(pg)

    for pg in hooked:
        pg.on("download", on_download)
    ctx.on("page", on_page)
    try:
        button = page.locator(f'[data-adl-idx="{idx}"]').first
        if button.is_visible():
            # a real click, waiting for overlays and animations to clear; but not for a navigation it starts: a link
            # that turns into a download (Jinxxy's) can leave that navigation unfinished, and the job waiting on it
            button.click(timeout=30000, no_wait_after=True)
        else:   # a button that isn't showing: click it through the page's own code
            button.evaluate("e => e.click()")
        started = time.time()
        deadline, said = started + timeout_s, started
        while not captured and time.time() < deadline:
            page.wait_for_timeout(250)
            if time.time() - said >= 5:   # keeps the progress panel moving, and lets Stop work while waiting
                said = time.time()
                log(f"    waiting for the download to start ({int(said - started)} s)")
    finally:
        ctx.remove_listener("page", on_page)
        for pg in hooked:
            try:
                pg.remove_listener("download", on_download)
            except Exception:
                pass
        for extra in captured[1:]:   # a second download from the same click isn't one Hoard asked for
            try:
                extra.cancel()
            except Exception:
                pass
    for pg in popups:
        try:
            if not captured or pg is not captured[0].page:
                pg.close()
        except Exception:
            pass
    return captured[0] if captured else None


def close_if_popup(page, main_page) -> None:
    """Close a tab a download opened, leaving the main tab alone."""
    try:
        if page is not main_page:
            page.close()
    except Exception:
        pass


def label_key(label: str) -> str:
    """The part of a download button's row that identifies the file, without the word "download"."""
    return re.sub(r"\s+", " ", re.sub(r"\bdownload\b|ダウンロード", "", label, flags=re.I)).strip()


def disposition_name(header: str) -> str:
    """The file name a Content-Disposition header gives (filename*= preferred), or ""."""
    m = re.search(r"filename\*\s*=\s*([\w-]+)'[^']*'([^;]+)", header or "", re.I)
    if m:
        try:
            return unquote(m[2].strip().strip('"'), encoding=m[1], errors="replace")
        except LookupError:
            return unquote(m[2].strip().strip('"'))
    m = re.search(r'filename\s*=\s*("([^"]*)"|[^;]+)', header or "", re.I)
    return (m[2] if m and m[2] is not None else (m[1] if m else "")).strip()


def file_link_name(sess: requests.Session, href: str, sites: list[str]) -> str:
    """What a store's file link downloads as, asked of the store with your sign-in, without downloading it.
    Raises when the store turns the request away (a web page, or an error), or the link isn't the store's."""
    u = urlparse(href)
    if not egress._test_origin(href) and not (u.scheme == "https" and _on_sites(u.hostname or "", sites)):
        raise egress.UnsafeRequest(f"{u.hostname} isn't one of the store's sites")
    r = egress.get(sess, href, sites, stay_on_sites=False, stream=True, timeout=60,
                   headers={"Accept-Encoding": "identity"})
    with r:
        if not r.ok:
            raise RuntimeError(f"it answered HTTP {r.status_code}")
        if r.headers.get("Content-Type", "").startswith("text/html"):
            raise RuntimeError("it sent a web page instead of the file")
        return disposition_name(r.headers.get("Content-Disposition", "")) or unquote(Path(urlparse(r.url).path).name)


def download_by_clicking(ctx, page, url: str, rec: dict, folder: Path, store: str, hosts: list[str], timeout_s: int,
                         name: str, creator: str, man: StoreRecords, args, report: "Report", direct=None,
                         listed_name: str | None = None) -> bool:
    """Click every file's download button on the open page and save what each one downloads.

    direct, when given, is {"sess": a session with the store's cookies, "sites": its sites, "on": True}: a button
    that's a plain link to the file is then downloaded straight from the store (resuming where it stopped), without
    the browser. If the store turns that away, direct["on"] goes False and the rest go through the browser."""
    find = lambda allow_all: page.evaluate(DOWNLOAD_BUTTONS_JS, {"allowAll": allow_all, "hosts": hosts})  # noqa: E731
    buttons = find(False)
    allow_all = not buttons
    if allow_all:  # the product only offers a "download all" zip
        buttons = find(True)
    if not buttons:
        report.skipped.append(f"{store}: {name} - no download buttons found on {url}")
        return False

    wanted, used, seen = [], set(), {}
    for b in buttons:
        k = label_key(b["label"]) or f"file #{b['idx'] + 1}"
        if k in used:
            k = f"{k} #{b['idx'] + 1}"
        used.add(k)
        nth = seen[b["label"]] = seen.get(b["label"], -1) + 1   # which of the buttons with this label it is
        wanted.append((b["label"], k, nth))

    got_any = False
    for label, k, nth in wanted:
        old = rec["files"].get(k)
        if old and rel_to_path(folder, old["path"]).exists():
            continue
        if left_out(args, report, store.lower(), name, label or k, listed_name or ""):
            continue
        if args.dry_run:
            would_get(args, report, store.lower(), rec, name, creator, label or k, False, old is not None, listed_name)
            continue
        def named(raw: str, k=k):
            """The file's name in the product's folder, the file it replaces (if any), and whether it's an update."""
            fname = distinct_name(safe_name(raw or k, 150), k, rec, {key for _label, key, _nth in wanted})
            # the same filename under a different label means the creator updated that file
            prev = next((fk for fk, fv in rec["files"].items() if fv.get("path") == fname and fk != k), None)
            is_update = prev is not None or (folder / fname).exists()
            log(f"    downloading: {fname}")
            return fname, prev, is_update

        def attempt(label=label, k=k, nth=nth):
            """Click the file's button and save what it downloads (tried again by with_retries)."""
            current = find(allow_all)  # re-tag; the page may have re-rendered
            # the same button again: the nth with its label. Never whatever is now where it was: after a re-render
            # that may be another file, which would then be saved as this one, and this one never downloaded
            alike = [b for b in current if b["label"] == label]
            match = alike[nth] if nth < len(alike) else None
            if not match:
                raise RuntimeError("its download button is no longer on the page")
            if direct and direct["on"] and match.get("href"):
                try:
                    raw = file_link_name(direct["sess"], match["href"], direct["sites"])
                except (RuntimeError, requests.RequestException, egress.UnsafeRequest) as e:
                    direct["on"] = False
                    log(f"    {store} turned the direct download away ({e}), so Hoard downloads through the browser instead.")
                else:
                    fname, prev, is_update = named(raw)
                    egress.download(direct["sess"], match["href"], folder / fname, direct["sites"], desc=fname,
                                    progress=downloading(fname))
                    return fname, prev, is_update
            dl = click_download(ctx, page, match["idx"], timeout_s)
            if page.url.split("#")[0].rstrip("/") != url.split("#")[0].rstrip("/"):  # the click navigated away
                pace.before(url)
                page.goto(url, wait_until="domcontentloaded")
                settle(page)
            if not dl:
                raise RuntimeError("clicking download didn't start a download")
            fname, prev, is_update = named(dl.suggested_filename)
            try:
                wait_for_browser_download(dl, fname)
                save_browser_download(dl, folder, fname)
            except Exception as e:
                raise RuntimeError(f"{fname} - {e}") from e
            finally:
                close_if_popup(dl.page, page)
            return fname, prev, is_update

        try:
            fname, prev, is_update = with_retries(report, label or k, attempt)
        except Exception as e:
            if tab_closed(e) or page.is_closed():   # not this file's doing: every file after it would fail too
                raise BrowserClosed(str(e)) from e
            report.failed.append(f"{store}: {name} / {k} - {e}")
            continue
        target = folder / fname
        if prev:
            rec["files"].pop(prev, None)
        rec["files"][k] = {"path": fname, "size": target.stat().st_size, "label": label, "downloaded_at": now_iso()}
        log(f"    {'updated' if is_update else 'saved'}: {fname}")
        (report.updated if is_update else report.new_files).append(f"{store}: {creator} / {name} / {fname}")
        report.saved(store.lower(), name, label or k, listed_name)   # (its update may be under its library name)
        got_any = True
        man.checkpoint()
    return got_any


REOPENS = 3   # how often a store's browser that closed by itself is opened again in one sync


def reopen_tab(p, cfg: dict, args, store: str, browser: dict):
    """A new tab for a store whose tab closed by itself: in the same browser while it still answers, otherwise in
    the browser started again with the store's sign-in (browser["ctx"] is then the new one)."""
    label = STORES[store]["label"]
    try:
        page = browser["ctx"].new_page()
        page.evaluate("1")   # answers?
        log(f"    {label}'s browser tab closed by itself, so Hoard opened a new one")
        return page
    except Exception:
        pass
    try:
        browser["ctx"].close()   # lets go of its sign-in
    except Exception:
        pass
    browser["ctx"] = launch_context(p, cfg, not args.headed, store)
    log(f"    {label}'s browser closed by itself, so Hoard started it again")
    return browser["ctx"].pages[0] if browser["ctx"].pages else browser["ctx"].new_page()


def session_from_context(ctx, domain: str) -> requests.Session:
    """A requests session carrying the browser's cookies for one site, and the same User-Agent."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    s = egress.session(page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome"))
    for c in ctx.cookies():
        if _on_sites(c["domain"], [domain]):
            s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    return s


def chosen_here(args) -> bool:
    """Was this download (or look at what's there to choose from) of products chosen, not a whole store's?"""
    return bool(getattr(args, "keys", None) or getattr(args, "only", None) or getattr(args, "listing", False))


# ----------------------------------------------------------------------------- itch.io
#
# Through itch.io's API (itch.py), with your API key: what you own, each project's files, and each file from its
# download address, which redirects to the file host. Downloads resume, and a file whose checksum itch.io gives is
# checked against it. Game builds (files the creator marked for Windows, macOS, Linux or Android) are skipped while
# itch.skip_game_builds is on: creators mark their games' builds, and hardly ever asset files, so a library with
# games in it doesn't fill your drive with them.

def md5_of(path: Path) -> str:
    """A file's MD5, read a piece at a time (files can be many gigabytes). itch.io gives it to check downloads by."""
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


REDACT_KEYS = re.compile(r'("[^"]*(?:email|token|password|secret|session|cookie|authorization|jwt|license)[^"]*"\s*:\s*)"[^"]*"', re.I)


REDACT_QS = re.compile(r'((?:X-Amz-[A-Za-z-]+|Signature|Key-Pair-Id|Policy|token|sig)=)[^&"\s]+', re.I)


def redact(s: str) -> str:
    """Mask emails, tokens, passwords and signed-URL parts in text saved for troubleshooting."""
    return REDACT_QS.sub(r"\1***", REDACT_KEYS.sub(r'\1"***"', s or ""))


# ----------------------------------------------------------------------------- tags & catalog

def name_tokens(name: str, min_len: int, stop: set) -> set[str]:
    """The words in an asset name that could become tags, lower-cased and without filler or version numbers."""
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)  # FoxyHoodie -> Foxy Hoodie
    out = set()
    for t in re.findall(r"[^\W_]+", name.lower()):
        if t.isdigit() or re.fullmatch(r"v\d+[a-z]?|\d+(st|nd|rd|th)", t):
            continue
        if len(t) >= min_len and t not in stop:
            out.add(t)
    return out


_warned_changed: set = set()


def read_manifests(root: Path) -> list[dict]:
    """Every downloaded asset from every store's manifest, each tagged with its store."""
    assets = []
    for store in STORE_DIRS.values():
        mpath = root / store / "_manifest.json"
        if not mpath.exists():
            continue
        try:
            raw = read_json_file(mpath)
        except (DataFileError, PermissionError) as e:
            log(f"{store}: skipped its _manifest.json ({e})")
            continue
        status = check_seal(raw, mpath)
        if status == "changed" and mpath not in _warned_changed:
            _warned_changed.add(mpath)
            log(f"{store}: _manifest.json was changed by something other than Hoard, so its store links "
                "aren't shown. The next sync fetches them again.")
        data, dropped = clean_manifest(raw, root / store, trust_links=status in ("sealed", "unsealed"))
        for rec in data["assets"].values():
            if rec.get("files"):
                assets.append({"store": store, **rec})
    return assets


def library_store_dirs(cfg: dict, root: Path):
    """(library folder, store, its folder) for each store folder with records, in every connected library folder:
    the downloads folder (root) first (hoard/libraries.py)."""
    from . import libraries
    for base in [root, *(lib for lib in libraries.other_folders(cfg) if libraries.available(lib))]:
        for store in STORE_DIRS.values():
            if (base / store / "_manifest.json").is_file():
                yield base, store, base / store


def read_library(cfg: dict, root: Path) -> list[dict]:
    """Every downloaded asset in every library folder (hoard/libraries.py): the downloads folder (root) first, then
    the others that are connected, each asset from another folder tagged with it ("library", its full path). A
    product in two of them counts once, where it's found first. What each other folder holds is noted, so a sync
    leaves its products alone while its drive is away."""
    from . import libraries
    assets = read_manifests(root)
    seen = {(a["store"], a.get("key") or a.get("folder")) for a in assets}
    for lib in libraries.other_folders(cfg):
        if not libraries.available(lib):
            continue
        found = read_manifests(lib)
        for store in STORE_DIRS.values():
            if (lib / store / "_manifest.json").is_file():
                libraries.remember(lib, store, [a.get("key") for a in found if a["store"] == store])
        for a in found:
            if (a["store"], a.get("key") or a.get("folder")) not in seen and not a.get("location"):   # (Local items listed where they
                seen.add((a["store"], a.get("key") or a.get("folder")))            # are belong to the downloads folder)
                assets.append({**a, "library": str(lib)})
    return assets


def collect_catalog(cfg: dict, root: Path) -> tuple[list, dict]:
    """Catalog entries + tag index, computed from the manifests on disk, in every library folder. Writes nothing."""
    tcfg = cfg["tags"]
    stop = STOPWORDS | {w.lower() for w in tcfg.get("extra_stopwords", [])}
    tagdata = TagStore().load()
    block = {w.lower() for w in tcfg.get("blocklist", [])} | set(tagdata["hidden"]) | set(tagdata["tags"])
    assets = read_library(cfg, root)
    if not assets:
        return [], {}
    from .library import public_pages
    from .sets import product_link
    pages = public_pages()

    toks = [name_tokens(a["name"], int(tcfg.get("min_length", 2)), stop) for a in assets]
    df = Counter(t for ts in toks for t in ts)
    plural = {w: w[:-1] for w in df if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and w[:-1] in df}
    toks = [{plural.get(t, t) for t in ts} for ts in toks]
    df = Counter(t for ts in toks for t in ts)

    n = len(assets)
    min_count, max_share = int(tcfg.get("min_count", 3)), float(tcfg.get("max_share", 0.4))
    tags = {w for w, c in df.items()
            if c >= min_count and w not in block and (n < 10 or c / n <= max_share) and clean_tag(w) == w}

    index: dict[str, list] = {}
    catalog = []
    matcher = TagMatcher(tagdata["tags"])
    for a, ts in zip(assets, toks):
        folder = f"{a['store']}/{a['folder']}"
        key = tag_key(a["store"], a["name"])
        mine = TagStore.tags_for(tagdata, key, a["name"], matcher)
        a_tags = sorted((ts & tags) - set(mine))
        added = a.get("first_seen") if isinstance(a.get("first_seen"), str) and len(a["first_seen"]) <= 40 else None
        url = store_link(a["store"], a.get("url"))
        # its public page, for a credits list: the download's own link is often the buyer's (Jinxxy's inventory, a
        # Gumroad download page), so the library's page for it, else that link when it's public
        page = None if a["store"] == "Local" else (pages.get(url or "") or pages.get(tag_key(a["store"], a["name"]))
                                                   or product_link(a["store"].lower(), url))
        catalog.append({"store": a["store"], "name": a["name"], "creator": a["creator"], "folder": folder,
                        "url": url, **({"page": page} if page else {}), "variants": a.get("variants"), "added": added,
                        "files": sorted(f["path"] for f in a["files"].values()),
                        "tags": mine, "suggested_tags": a_tags,
                        **({"location": a["location"]} if a.get("location") else {}),
                        **({"library": a["library"]} if a.get("library") else {}),
                        **({"note": a["note"]} if a.get("note") else {}),
                        **({"your_note": tagdata["notes"][key]} if tagdata.get("notes", {}).get(key) else {})})
        for t in a_tags:
            index.setdefault(t, []).append(folder)
    catalog.sort(key=lambda e: (e["store"], e["creator"].lower(), e["name"].lower()))
    return catalog, dict(sorted(index.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def delete_downloaded_files(cfg: dict, root: Path, keys: set) -> dict:
    """Delete the files Hoard downloaded for these products (tag keys) (issue #81). The caller makes sure they're
    products you removed from your library, and that nothing is downloading.

    Only the files Hoard's records list are deleted, with the picture and asset.json Hoard saved beside them; anything
    else in the folder (files of your own) stays, and a folder is removed only when that leaves it empty. Nothing is
    followed through a link: a path that leads outside the store's folder, or is a link, is left alone. The deleted
    files leave the product's record (so the catalog, Downloads and Hoard for Unity stop listing them, and a product
    you restore is downloaded again); the record itself keeps its folder name. Returns what was deleted and kept."""
    import stat as _stat
    from .safety import _is_link
    done = {"products": 0, "files": 0, "bytes": 0, "kept": []}
    for _base, store, sdir in library_store_dirs(cfg, root):
        manifest = Manifest(sdir)
        for rec in manifest.assets.values():
            if tag_key(store, rec.get("name") or "") not in keys or rec.get("location"):
                continue   # (a Local item listed where it is: its files are yours, never deleted here)
            try:
                folder = rel_to_path(sdir, rec["folder"])
            except UnsafePath:
                continue
            paths = [f.get("path") for f in rec.get("files", {}).values()]
            gone = set()
            try:
                paths += [p.name for p in folder.glob("_thumbnail.*")] + ["asset.json"]
            except OSError:
                pass
            dirs, count = set(), 0
            for rel in paths:
                try:
                    target = rel_to_path(folder, rel)
                    st = os.stat(target, follow_symlinks=False)
                except (UnsafePath, OSError):
                    continue
                if _is_link(st) or not _stat.S_ISREG(st.st_mode):
                    continue
                try:
                    os.unlink(target)
                except OSError as e:
                    log(f"Couldn't delete {store}/{rec['folder']}/{rel}: {e.strerror or e}")
                    continue
                gone.add(rel)
                count, done["files"], done["bytes"] = count + 1, done["files"] + 1, done["bytes"] + st.st_size
                for parent in Path(rel).parents:
                    if str(parent) != ".":
                        dirs.add(folder / parent)
            if not rec.get("location"):   # its previous versions (hoard/previous.py) were Hoard's too
                from . import previous
                done["files"] += previous.delete_all(folder, [f.get("path") for f in rec["files"].values()])
            for d in sorted(dirs, key=lambda d: len(d.parts), reverse=True) + [folder, folder.parent]:
                if d != sdir and sdir in d.parents:
                    try:
                        d.rmdir()   # only when empty
                    except OSError:
                        pass
            # a recorded file that's gone now (deleted here, or before) leaves the record
            rec["files"] = {k: f for k, f in rec.get("files", {}).items()
                            if f.get("path") not in gone and _still_there(folder, f.get("path"))}
            if count:
                done["products"] += 1
            if folder.is_dir():
                done["kept"].append(f"{store}/{rec['folder']}")
        manifest.save_changes()
    if done["files"] or done["products"]:
        log(f"Deleted {done['files']} downloaded files of {done['products']} removed products.")
        build_catalog(cfg, root)
    return done


def move_product(cfg: dict, root: Path, key: str, to: int, progress=None, committed=None) -> dict:
    """Move a downloaded product's files to another library folder (to: its number, 0 for the downloads folder; see
    hoard/libraries.py), and its record with them, so it's kept up to date there.

    Every file Hoard recorded is copied, and checked against its fingerprint (or its size, before the first check)
    as it arrives; only when all have arrived is the record moved and the originals deleted (Hoard's picture and
    asset.json with them, and the folder when that leaves it empty; anything else of yours in it stays). If anything
    goes wrong part way, what was copied is deleted and the original is left as it was. Nothing is read or written
    through a link. A Local item stays in the downloads folder. committed() is called once the move can't be undone
    (the record has moved), so a Stop after it lets the rest finish. Returns {"name", "files", "bytes", "to"}; raises
    ValueError saying what's wrong."""
    import stat as _stat
    from . import libraries
    from .safety import _is_link
    say = progress or (lambda line: None)
    folders = libraries.roots(cfg, root)
    if not isinstance(to, int) or isinstance(to, bool) or not 0 <= to < len(folders):
        raise ValueError("Choose one of your library folders.")
    dest_base = folders[to]
    if not libraries.available(dest_base):
        raise ValueError(f"{dest_base} isn't there: connect its drive, then try again.")
    found = None
    for base, store, sdir in library_store_dirs(cfg, root):
        manifest = Manifest(sdir)
        for k, rec in manifest.assets.items():
            if tag_key(store, rec.get("name") or "") == key and rec.get("files"):
                found = (base, store, sdir, manifest, k, rec)
                break
        if found:
            break
    if not found:
        raise ValueError("That isn't downloaded any more.")
    base, store, sdir, manifest, k, rec = found
    if store == STORE_DIRS["local"]:
        raise ValueError("Your own packages stay in the downloads folder's Local.")
    if base == dest_base:
        raise ValueError("It's already there.")
    src = rel_to_path(sdir, rec["folder"])
    total = sum(int(f.get("size") or 0) for f in rec["files"].values())
    free = libraries.free_space(dest_base)
    if free is not None and free < total + 64 * 1024 * 1024:
        raise ValueError(f"There isn't room on that drive: it needs {amount(total)}, and has {amount(free)} free.")
    dest_dir = dest_base / store
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_man = Manifest(dest_dir)
    if k in dest_man.assets and dest_man.assets[k].get("files"):
        raise ValueError("That folder already has its own copy of it.")
    dest_man.assets.pop(k, None)
    folder_name = dest_man.record(k, rec.get("creator") or "", rec.get("name") or "")["folder"]
    dest_man.assets.pop(k)
    dest = rel_to_path(dest_dir, folder_name)
    if dest.is_symlink() or (os.path.lexists(dest) and not dest.is_dir()):
        raise ValueError(f"{dest} is already there and isn't a folder. Move or rename it first.")
    extras = [p.name for p in src.glob("_thumbnail.*") if p.is_file() and not p.is_symlink()] if src.is_dir() else []
    from . import previous   # its previous versions go with it
    extras += [v["path"] for v in previous.listed(src, [f.get("path") for f in rec["files"].values()])] if src.is_dir() else []
    made: list[Path] = []
    try:
        entries = [(f.get("path"), f) for f in rec["files"].values()] + [(name, None) for name in extras]
        for n, (rel, f) in enumerate(entries, 1):
            line = f"Moving {rec.get('name')}: {n:,} of {len(entries):,}: {rel}"
            say(line)
            target = rel_to_path(dest, rel)
            if f is None and os.path.lexists(target):
                continue   # a picture already there is kept
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with open_under(src, rel) as fh, open(target, "xb") as out:
                made.append(target)
                for block in iter(lambda: fh.read(1024 * 1024), b""):
                    tick(line)   # (Stop is noticed between blocks)
                    digest.update(block)
                    out.write(block)
            if f is None:
                continue
            got = os.stat(target, follow_symlinks=False)
            if (f.get("size") is not None and got.st_size != f["size"]) or (f.get("sha256") and f["sha256"] != digest.hexdigest()):
                raise ValueError(f"{rel} didn't arrive as it was: it may have been changed. Check your downloads first.")
            f.update(sha256=digest.hexdigest(), mtime_ns=got.st_mtime_ns)
    except BaseException:
        for t in reversed(made):
            t.unlink(missing_ok=True)
        for d in sorted({p for t in made for p in t.parents if dest in (p, *p.parents) and p != dest_dir},
                        key=lambda d: len(d.parts), reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass
        raise
    dest_man.assets[k] = {**rec, "folder": folder_name}
    dest_man.save()
    manifest.assets.pop(k)
    manifest.save()
    if committed:
        committed()
    dirs = set()
    for rel in [f.get("path") for f in rec["files"].values()] + extras + ["asset.json"]:
        try:
            target = rel_to_path(src, rel)
            st = os.stat(target, follow_symlinks=False)
        except (UnsafePath, OSError):
            continue
        if _is_link(st) or not _stat.S_ISREG(st.st_mode):
            continue
        try:
            os.unlink(target)
        except OSError:
            continue
        dirs.update(p for p in target.parents if p != sdir and sdir in p.parents)
    for d in sorted(dirs, key=lambda d: len(d.parts), reverse=True):
        try:
            d.rmdir()   # only when empty
        except OSError:
            pass
    build_catalog(cfg, root)
    log(f"Moved {rec.get('name')} ({store}) to {dest}: {len(rec['files']):,} files, {amount(total)}")
    return {"name": rec.get("name"), "files": len(rec["files"]), "bytes": total, "to": str(dest)}


def restore_previous(cfg: dict, root: Path, folder: Path, stamp: str, name: str) -> dict:
    """Put a previous version of one of a product's files back (hoard/previous.py), keeping the current one as a
    previous version. Its record then has the restored file's size and no fingerprint, so the next check of the
    downloads takes the restored file's, rather than calling it changed. Raises ValueError when there's no such
    version, or no product of Hoard's in that folder."""
    from . import previous

    def same(a: Path, b: Path) -> bool:   # as resolved: one may be written with Windows' short names (RUNNER~1)
        try:
            return a == b or a.resolve() == b.resolve()
        except OSError:
            return False
    found = None
    for _base, _store, sdir in library_store_dirs(cfg, root):
        if not (sdir / "_manifest.json").is_file():
            continue
        man = Manifest(sdir)
        for rec in man.assets.values():
            try:
                if not rec.get("location") and same(rel_to_path(sdir, rec["folder"]), folder):
                    found = (man, rec)
                    break
            except (UnsafePath, KeyError, TypeError):
                continue
        if found:
            break
    if not found:
        raise ValueError("That isn't a download of Hoard's.")
    man, rec = found
    done = previous.restore(folder, stamp, name, [f.get("path") for f in rec.get("files", {}).values()])
    for f in rec.get("files", {}).values():
        if f.get("path") == name:
            f["size"] = done["size"]
            f.pop("sha256", None)
            f.pop("mtime_ns", None)
            f["restored_at"] = now_iso()
    man.save()
    log(f"Restored the previous version of {rec.get('name')}: {name} ({stamp})")
    return done


EDIT_NOTE = """This is an editable copy of a download, made by Hoard on {when}.

    {name} by {creator} ({store})
    The original: {original}

Change anything here. Hoard never checks, updates or replaces this folder, and doesn't import from it: it's yours.

The original stays as the store sent it. Hoard checks that one, and replaces a file there that was changed, so
edit here instead. Only files that still matched what Hoard downloaded were copied. Anything you add to this
folder (a texture from a website, a tool someone sent you) hasn't been checked by Hoard, so be as careful with it
as with any download.
"""


def edits_root(cfg: dict, root: Path) -> Path:
    """The folder for editable copies (config.edits_dir), and for what Look inside takes out of a package: outside
    Hoard's care, so never inside a library folder. Raises ValueError for one that is."""
    from .config import edits_dir
    from . import libraries
    dest_root = edits_dir(cfg)
    rdest = dest_root.resolve()
    for lib in libraries.roots(cfg, root):
        rroot = lib.resolve()
        if rdest == rroot or rroot in rdest.parents:
            raise ValueError("The folder for editable copies can't be inside a library folder. Choose another in "
                             "config.json (edits_root).")
    return dest_root


def make_editable_copy(cfg: dict, root: Path, key: str) -> dict:
    """Copy a product's downloaded files into a folder of their own under edits_dir (issue #82), for you to change.

    Hoard checks and re-downloads files in the downloads folder, so edits there are lost, and an edited file can't
    be told from one that something else changed. The copy is outside Hoard's care altogether. Only the files Hoard
    recorded are copied, and only while they're still the size they were downloaded at; one that isn't is left out
    and named, so a file changed behind Hoard's back isn't passed on as the store's. Nothing is read through a
    link. The copy goes in a new folder each time ("Name (2)" beside an earlier copy), and a note in it says what
    it is. Returns {"folder", "files", "bytes", "skipped": [(path, why)]}. Raises ValueError when there's nothing to copy."""
    dest_root = edits_root(cfg, root)
    for _base, store, sdir in library_store_dirs(cfg, root):
        for rec in Manifest(sdir).assets.values():
            if tag_key(store, rec.get("name") or "") != key or not rec.get("files"):
                continue
            try:
                folder = record_folder(sdir, rec)
            except UnsafePath:
                continue
            base = dest_root / store / (rec["folder"] if not rec.get("location") else safe_name(rec.get("name") or "Copy"))
            dest, n = base, 2
            while os.path.lexists(dest):
                dest, n = base.with_name(f"{base.name} ({n})"), n + 1
            dest.mkdir(parents=True)
            copied, size, skipped = 0, 0, []
            for f in sorted(rec["files"].values(), key=lambda f: f.get("path") or ""):
                rel = f.get("path")
                try:
                    src = open_under(folder, rel)
                except UnsafePath:
                    skipped.append((rel, "missing, or not a plain file"))
                    continue
                with src:
                    got = os.fstat(src.fileno()).st_size
                    if f.get("size") is not None and got != f["size"]:
                        skipped.append((rel, "changed since Hoard downloaded it"))
                        continue
                    target = rel_to_path(dest, rel)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open(target, "xb") as out:
                        shutil.copyfileobj(src, out, 1024 * 1024)
                copied, size = copied + 1, size + got
            note = EDIT_NOTE.format(when=now_iso()[:10], name=rec.get("name"), creator=rec.get("creator"), store=store,
                                    original=folder)
            if skipped:
                note += "\nLeft out:\n" + "".join(f"    {rel}: {why}\n" for rel, why in skipped)
            (dest / "_EDITABLE COPY - read me.txt").write_text(note, "utf-8")
            log(f"Made an editable copy of {store}/{rec['folder']} in {dest}: {copied} files"
                + (f", {len(skipped)} left out" if skipped else ""))
            return {"folder": str(dest), "files": copied, "bytes": size, "skipped": skipped}
    raise ValueError("That download isn't on disk any more.")


def integrity_file() -> Path:
    """Where the last check of your downloads keeps what it found."""
    from .paths import data_dir
    return data_dir() / "integrity.json"


def last_integrity() -> dict | None:
    """What the last check of the downloads found (issue #83), or None if there hasn't been one."""
    try:
        raw = read_json_file(integrity_file()) if storage.is_file(integrity_file()) else None
    except (DataFileError, OSError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("checked"), str):
        return None
    num = lambda k: raw[k] if isinstance(raw.get(k), int) and not isinstance(raw.get(k), bool) else 0  # noqa: E731
    texts = lambda k: [str(x)[:500] for x in raw[k][:200]] if isinstance(raw.get(k), list) else []  # noqa: E731
    return {"checked": raw["checked"][:40], "products": num("products"), "files": num("files"), "fine": num("fine"),
            "changed": texts("changed"), "missing": texts("missing"), "data_changed": texts("data_changed"),
            "complete": raw.get("complete") is not False,
            "problems": [p for p in (_problem(x) for x in (raw.get("problems") or [])[:MAX_PROBLEMS]
                                     if isinstance(raw.get("problems"), list)) if p]}


MAX_PROBLEMS = 1000   # the files a check lists to deal with (issue #231): the counts go on past it


def _problem(x) -> dict | None:
    """One file a check found changed or missing, as integrity.json keeps it (each field checked: it's a file on disk)."""
    if not isinstance(x, dict) or x.get("kind") not in ("changed", "missing") or x.get("store") not in STORE_DIRS:
        return None
    text = lambda k, n: x[k][:n] if isinstance(x.get(k), str) else ""  # noqa: E731
    out = {"kind": x["kind"], "store": x["store"], "base": text("base", 1000), "folder": text("folder", 1000),
           "path": text("path", 1000), "name": text("name", 300)}
    return out if out["base"] and out["folder"] and out["path"] else None


def check_integrity(root: Path, stop=None, progress=None, others=(), fresh_since: str | None = None,
                    leave_out=frozenset()) -> dict:
    """Check the downloads are as Hoard downloaded them (issue #83): every data file's seal, and every recorded file's
    size and SHA-256. A file's fingerprint is taken the first time it's checked and kept in its record; after that it's
    read again only when its size or modified time changed, so a routine check is quick. Nothing is changed but the
    records' fingerprints, and nothing is followed through a link. The result is kept in integrity.json (the
    Downloads page shows it) and returned: products and files checked, which files changed or are missing, and which
    data files were changed outside Hoard. stop: a threading.Event that ends the check early (it says so). others: the
    other library folders (hoard/libraries.py), checked the same way when their drive is connected, and named in
    "away" when it isn't. fresh_since: a file downloaded after this time and not fingerprinted yet counts as fine
    without being read (issue #113: it was checked as it came in); the next check takes its fingerprint. leave_out:
    the product keys not to check (the products you removed: issue #259)."""
    import stat as _stat
    from .safety import _is_link
    say = progress or (lambda line: None)
    result = {"checked": now_iso(), "products": 0, "files": 0, "fine": 0, "changed": [], "missing": [],
              "data_changed": [], "complete": True, "away": [], "problems": []}
    store_ids = {d: s for s, d in STORE_DIRS.items()}

    def found(kind: str, shown: str, base: Path, store: str, rec: dict, rel: str) -> None:
        """A file that isn't as Hoard downloaded it: named in the summary's list, and kept with what it takes to
        deal with it from the check's results (issue #231)."""
        result[kind].append(shown)
        if len(result["problems"]) < MAX_PROBLEMS:
            result["problems"].append({"kind": kind, "base": str(base), "store": store_ids.get(store, store.lower()),
                                       "folder": rec["folder"], "path": rel, "name": str(rec.get("name") or "")[:300]})
    bases = [root]
    for lib in others:
        (bases.append(lib) if lib.is_dir() and not lib.is_symlink() else result["away"].append(str(lib)))
    for base in bases:
        data_files = [base / d / "_manifest.json" for d in STORE_DIRS.values()]
        data_files += [root / "catalog.json", root / "tags.json"] if base == root else []
        for path in data_files:
            if path.is_file():
                try:
                    status = check_seal(read_json_file(path), path if path.name == "_manifest.json" else None)
                except DataFileError:
                    status = "changed"
                if status == "changed":
                    name = str(path.relative_to(root)).replace(os.sep, "/") if base == root else str(path)
                    result["data_changed"].append(name)
    for base, store, sdir in ((b, st, b / st) for b in bases for st in STORE_DIRS.values()):
        if not (sdir / "_manifest.json").is_file():
            continue
        manifest = Manifest(sdir)
        for rec in manifest.assets.values():
            if stop is not None and stop.is_set():
                result["complete"] = False
                break
            if not rec.get("files") or rec.get("location"):
                continue   # (a Local item listed where it is: your own working folder, yours to change)
            if tag_key(store_ids.get(store, store.lower()), rec.get("name") or "") in leave_out:
                continue   # (one you removed: not yours to keep track of now)
            result["products"] += 1
            say(f"Checking {store}: {rec.get('name')}")
            try:
                folder = rel_to_path(sdir, rec["folder"])
            except UnsafePath:
                continue
            for f in rec["files"].values():
                rel = f.get("path")
                where = f"{store}/{rec['folder']}/{rel}"
                shown = f"{rec.get('name')} ({store}): {rel}"   # by the product's name, so a hidden one can be masked
                result["files"] += 1
                try:
                    target = rel_to_path(folder, rel)
                    st = os.stat(target, follow_symlinks=False)
                except (UnsafePath, OSError):
                    found("missing", shown, base, store, rec, rel)
                    continue
                if _is_link(st) or not _stat.S_ISREG(st.st_mode) or (f.get("size") is not None and st.st_size != f["size"]):
                    found("changed", shown, base, store, rec, rel)
                    continue
                if f.get("sha256") and f.get("mtime_ns") == st.st_mtime_ns:
                    result["fine"] += 1
                    continue
                if fresh_since and not f.get("sha256") and str(f.get("downloaded_at") or "") > fresh_since:
                    result["fine"] += 1   # new since the last check: read next time, not now
                    continue
                try:
                    with open_under(base, where) as fh:
                        digest = hashlib.sha256()
                        for block in iter(lambda: fh.read(1024 * 1024), b""):
                            digest.update(block)
                except (UnsafePath, OSError):
                    found("missing", shown, base, store, rec, rel)
                    continue
                if f.get("sha256") and f["sha256"] != digest.hexdigest():
                    found("changed", shown, base, store, rec, rel)
                    continue
                f.update(sha256=digest.hexdigest(), mtime_ns=st.st_mtime_ns)   # the fingerprint, taken once
                result["fine"] += 1
            manifest.checkpoint()
        manifest.save_changes()
        if not result["complete"]:
            break
    try:
        write_file_safely(integrity_file(), json.dumps(result, ensure_ascii=False))
    except OSError as e:
        log(f"Couldn't save what the check found: {e}")
    return result


def resolve_problem(root: Path, others, problem: dict, action: str) -> dict:
    """Issue #231: deal with a file the last check found changed or missing (problem: as last_integrity lists it).
    action: "keep" (a changed file as it is now: its fingerprint is taken again, so it's fine from now on), "forget"
    (a missing file: taken off its product's record), or "again" (to be downloaded again: a changed file is moved to
    _Previous versions first, so nothing of yours is lost). It's taken off the check's results. Returns the product
    ({"key", "store", "name", "file"}) for what the caller does next (a download, a file to leave out); raises
    ValueError when it can't be done (the file's record has gone, or it's back as it was)."""
    import stat as _stat
    from . import previous
    from .safety import _is_link
    bases = {str(b): b for b in (root, *others)}
    base, store = bases.get(problem.get("base")), problem.get("store")
    if base is None or store not in STORE_DIRS or action not in ("keep", "forget", "again"):
        raise ValueError("That isn't something Hoard can do.")
    sdir = base / STORE_DIRS[store]
    manifest = Manifest(sdir)
    rec = next((r for r in manifest.assets.values() if r.get("folder") == problem.get("folder") and not r.get("location")), None)
    fkey = next((k for k, f in (rec or {}).get("files", {}).items() if f.get("path") == problem.get("path")), None)
    if fkey is None:
        _drop_problem(problem)
        raise ValueError("Hoard has no record of that file now: check your downloads again.")
    f, rel = rec["files"][fkey], rec["files"][fkey]["path"]
    try:
        target = rel_to_path(rel_to_path(sdir, rec["folder"]), rel)
        st = os.stat(target, follow_symlinks=False)
    except UnsafePath:
        raise ValueError("That file's folder isn't one Hoard can use.") from None
    except OSError:
        st = None
    plain = st is not None and not _is_link(st) and _stat.S_ISREG(st.st_mode)
    if action == "keep":
        if not plain:
            raise ValueError("That file isn't there now: check your downloads again.")
        digest = hashlib.sha256()
        with open_under(base, f"{STORE_DIRS[store]}/{rec['folder']}/{rel}") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
        f.update(size=st.st_size, sha256=digest.hexdigest(), mtime_ns=st.st_mtime_ns)
    elif action == "forget":
        if st is not None:
            raise ValueError("That file is there now: check your downloads again.")
        del rec["files"][fkey]
    elif st is not None:   # again: what's there now is kept aside, so the download is a whole new copy
        if not plain or (previous.keep(target, max(1, previous.keeping())) is None and st.st_size):
            raise ValueError("That file couldn't be moved aside, so it wasn't downloaded again.")
        target.unlink(missing_ok=True)   # (an empty file: nothing to keep)
    manifest.save()
    _drop_problem(problem)
    return {"key": tag_key(store, rec.get("name") or ""), "store": store, "name": rec.get("name") or "",
            "file": chosen_name(store, fkey, f)}


def chosen_name(store: str, fkey: str, f: dict) -> str:
    """The name a downloaded file is left out by (left_out's file), from its record: what its store called it when it
    was downloaded (a Jinxxy button's label, itch.io's name for it, Booth's), else its path."""
    if f.get("label"):
        return f["label"]
    if store == "gumroad" and fkey.startswith("page-image:"):
        return f["path"].rsplit(".", 1)[0]   # (a page's pictures are left out by their name before their type is known)
    if "label" in f and store in ("jinxxy", "payhip"):
        return fkey   # (a button with no words is left out by its key)
    return f["path"]


def _drop_problem(problem: dict) -> None:
    """Take a file dealt with off the last check's results (and its count)."""
    try:
        raw = read_json_file(integrity_file())
    except (DataFileError, OSError):
        return
    same = lambda x: isinstance(x, dict) and all(x.get(k) == problem.get(k) for k in ("base", "store", "folder", "path"))  # noqa: E731
    gone = [x for x in raw.get("problems") or [] if same(x)]
    if not gone:
        return
    raw["problems"] = [x for x in raw["problems"] if not same(x)]
    for x in gone:
        shown = f"{x.get('name')} ({STORE_DIRS.get(x.get('store'), '')}): {x.get('path')}"
        if shown in (raw.get(x["kind"]) or []):
            raw[x["kind"]].remove(shown)
    try:
        write_file_safely(integrity_file(), json.dumps(raw, ensure_ascii=False))
    except OSError as e:
        log(f"Couldn't save what the check found: {e}")


def integrity_summary(r: dict) -> str:
    """One line about a check, for the Tasks list and the page."""
    if not r["complete"]:
        return f"Stopped after checking {r['files']:,} files."
    problems = []
    if r["changed"]:
        problems.append(f"{len(r['changed'])} changed since Hoard downloaded {'it' if len(r['changed']) == 1 else 'them'}")
    if r["missing"]:
        problems.append(f"{len(r['missing'])} missing")
    if r["data_changed"]:
        problems.append(f"{len(r['data_changed'])} of Hoard's own records changed outside Hoard")
    away = r.get("away") or []
    later = (f" {len(away)} library {'folder wasn' if len(away) == 1 else 'folders weren'}'t checked, as "
             f"{'its drive isn' if len(away) == 1 else 'their drives aren'}'t connected." if away else "")
    if not problems:
        return f"All {r['files']:,} files of {r['products']:,} downloads are as Hoard downloaded them." + later
    return f"Checked {r['files']:,} files: " + ", ".join(problems) + "." + later


def _still_there(folder: Path, rel) -> bool:
    """Is the file (or a link of that name) still in the product's folder?"""
    try:
        return os.path.lexists(rel_to_path(folder, rel))
    except UnsafePath:
        return False


# What catalog.json, tags.json and asset.json promise (docs/DATA-FORMATS.md describes them in full).
CATALOG_FORMAT = {"catalog": {"format": "hoard-catalog", "version": 3},
                  "asset": {"format": "hoard-asset", "version": 3},
                  "tags": {"format": "hoard-tags", "version": 3}}


def validate_catalog_entry(entry: dict) -> list[str]:
    """Problems with one catalog entry, measured against the promises in docs/DATA-FORMATS.md (empty when fine)."""
    from .schema import errors
    problems = errors(entry)
    if not isinstance(entry, dict):
        return problems
    label = str(entry.get("folder"))[:80]
    if entry.get("store") not in STORE_DIRS.values():
        problems.append(f"{label}: unknown store")
    for key, limit in (("name", 300), ("creator", 200)):
        v = entry.get(key)
        if not isinstance(v, str) or not v or v != clean_text(v, limit):
            problems.append(f"{label}: {key} isn't clean text")
    if entry.get("variants") is not None and entry["variants"] != clean_text(entry["variants"], 300):
        problems.append(f"{label}: variants isn't clean text")
    if not valid_rel(entry.get("folder")):
        problems.append(f"{label}: folder isn't a plain relative path")
    if not isinstance(entry.get("files"), list) or not all(valid_rel(f) for f in entry["files"]):
        problems.append(f"{label}: a file path isn't a plain relative path")
    if "location" in entry and (entry.get("store") != "Local" or not valid_location(entry["location"])):
        problems.append(f"{label}: location is only for Local items, as a plain absolute path")
    if "library" in entry and (not valid_location(entry["library"]) or "location" in entry):
        problems.append(f"{label}: library is another library folder, as a plain absolute path")
    if entry.get("note") is not None and entry["note"] != clean_text(entry["note"], 300):
        problems.append(f"{label}: note isn't clean text")
    if "your_note" in entry and (not entry["your_note"] or entry["your_note"] != clean_note(entry["your_note"])):
        problems.append(f"{label}: your_note isn't clean text")
    if entry.get("url") is not None and store_link(str(entry.get("store")), entry["url"]) != entry["url"]:
        problems.append(f"{label}: url isn't an https address on the store's own website")
    if "page" in entry:
        from .sets import product_link
        if product_link(str(entry.get("store")).lower(), entry["page"]) != entry["page"]:
            problems.append(f"{label}: page isn't a public page on the store's own website")
    if "needs" in entry:
        from .needs import valid_needs
        if not valid_needs(entry["needs"], set(STORE_DIRS.values())):
            problems.append(f"{label}: needs isn't as Hoard writes it")
    if "code" in entry:
        from .needs import valid_code
        if not valid_code(entry["code"]):
            problems.append(f"{label}: code isn't as Hoard writes it")
    for key in ("tags", "suggested_tags"):
        if not isinstance(entry.get(key), list) or any(not isinstance(t, str) or clean_tag(t) != t or not t for t in entry[key]):
            problems.append(f"{label}: {key} has a tag that isn't clean")
    return problems


def build_catalog(cfg: dict, root: Path) -> None:
    """Write catalog.json, tags.json and each product's asset.json."""
    catalog, ordered = collect_catalog(cfg, root)
    if catalog:   # what each product needs, as far as its packages have been read (hoard/needs.py)
        from .needs import add_to_catalog
        try:
            add_to_catalog(root, catalog)
        except Exception as e:   # the catalog is written without it rather than not at all
            log(f"What the downloads need couldn't be added to catalog.json: {e}")
    if not catalog:
        stale = [name for name in ("catalog.json", "tags.json") if os.path.lexists(root / name)]
        if stale:   # an earlier catalog mustn't go on listing products that are no longer here
            write_catalog_files(root, [], {})
            log(f"No downloaded assets found under {root}, so {' and '.join(stale)} now list none.")
        else:       # an empty or new folder isn't given files it never had
            log(f"No downloaded assets found under {root} - nothing to tag.")
        return
    # clean_manifest should make every entry pass; any that doesn't is left out rather than written
    checked = [(entry, validate_catalog_entry(entry)) for entry in catalog]
    left_out = [problems[0] for _entry, problems in checked if problems]
    if left_out:
        log(f"Left {len(left_out)} assets out of the catalog because their records failed the check, "
            f"for example: {left_out[0]}")
    catalog = [entry for entry, problems in checked if not problems]
    for entry in catalog:
        base = Path(entry["library"]) if entry.get("library") else root
        try:
            adir = rel_to_path(base, entry["folder"])
        except UnsafePath:
            continue
        if adir.is_dir():
            from .schema import require
            write_file_safely(adir / "asset.json", json.dumps(require(seal({**CATALOG_FORMAT["asset"], **entry}),
                                                                    "asset-v3.schema.json"), indent=2,
                                                              ensure_ascii=False), base)
    write_catalog_files(root, catalog, ordered)
    top = ", ".join(f"{t} ({len(v)})" for t, v in list(ordered.items())[:25])
    log(f"\nTagged {len(catalog)} assets with {len(ordered)} suggested tags. Top: {top or '-'}")
    log("Hide suggestions you don't want in the Tags panel.")


def write_catalog_files(root: Path, catalog: list, ordered: dict) -> None:
    """catalog.json (every product) and tags.json (every tag, and the suggested ones, with their products)."""
    # Version 4 says some products are in other library folders ("library"): older Hoard for Unity, which would look
    # for them in the downloads folder, asks to be updated instead (docs/DATA-FORMATS.md)
    form = {**CATALOG_FORMAT["catalog"], **({"version": 4} if any(e.get("library") for e in catalog) else {})}
    from .sets import for_catalog   # your sets (hoard/sets.py), by their products' folders: Import set in Unity
    grouped = for_catalog(catalog) if catalog else []
    from .schema import require
    write_file_safely(root / "catalog.json", json.dumps(require(seal({**form, "generated_at": now_iso(), "assets": catalog,
                                                              **({"sets": grouped} if grouped else {})}),
                                                              f"catalog-v{form['version']}.schema.json"),
                                                        indent=2, ensure_ascii=False), root)
    yours: dict[str, list] = {}
    for entry in catalog:
        for t in entry["tags"]:
            yours.setdefault(t, []).append(entry["folder"])
    from .tags import TagStore
    kinds = {t: info["type"] for t, info in TagStore().load()["tags"].items() if info.get("type")}   # (issue #157)
    write_file_safely(root / "tags.json", json.dumps(require(seal({
        **CATALOG_FORMAT["tags"], "generated_at": now_iso(), "total_assets": len(catalog),
        "tags": {t: {"count": len(v), "assets": v, **({"type": kinds[t]} if t in kinds else {})}
                 for t, v in sorted(yours.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "suggested": {t: {"count": len(v), "assets": v} for t, v in ordered.items()},
    }), "tags-v3.schema.json"), indent=2, ensure_ascii=False), root)


def catalog_seal(root: Path) -> str | None:
    """How catalog.json is sealed (see check_seal), "unreadable", or None when there isn't one."""
    path = root / "catalog.json"
    if not path.is_file():
        return None
    try:
        return check_seal(read_json_file(path))
    except (DataFileError, OSError, ValueError):
        return "unreadable"


def reseal_catalog(cfg: dict, root: Path) -> str | None:
    """If catalog.json isn't sealed with this install's key (Hoard on another computer, an earlier install, a Hoard
    whose files Windows keeps separately, or an edit), rebuild it from the store records, which seals it again.
    Returns what its seal was, if it was rebuilt; None if it was already fine or there's no catalog."""
    status = catalog_seal(root)
    if status in (None, "sealed"):
        return None
    build_catalog(cfg, root)
    log(f"catalog.json was {status}: rebuilt from the store records and sealed with this computer's key.")
    return status


def cmd_verify(cfg: dict, root: Path) -> int:
    """Check the seal on every data file in the download folder, then rebuild the catalog files. 1 if any were changed."""
    labels = {"sealed": "fine", "unsealed": "not sealed yet (saved by an older version; sealed on the next sync)",
              "foreign": "sealed by Hoard on another computer",
              "changed": "CHANGED by something other than Hoard"}
    changed = 0
    if store_python():
        log(STORE_PYTHON_NOTE)
    files = [root / d / "_manifest.json" for d in STORE_DIRS.values()] + [root / "catalog.json", root / "tags.json"]
    files += sorted(root.glob("*/*/*/asset.json"))
    counts: Counter = Counter()
    for path in files:
        if not path.is_file():
            continue
        try:
            status = check_seal(read_json_file(path), path if path.name == "_manifest.json" else None)
        except DataFileError as e:
            status = "changed"
            log(f"  {path.relative_to(root)}: {e}")
        counts[status] += 1
        if status != "sealed":
            log(f"  {path.relative_to(root)}: {labels[status]}")
        changed += status == "changed"
    log(f"Checked {sum(counts.values())} files: " + ", ".join(f"{n} {labels[k].split(' (')[0]}" for k, n in counts.items()))
    for store in STORE_DIRS.values():  # keep changed manifests' records, without their links, and seal them again
        mpath = root / store / "_manifest.json"
        if mpath.is_file():
            try:
                changed_here = check_seal(read_json_file(mpath), mpath) == "changed"
            except DataFileError:
                changed_here = True
            if changed_here:
                Manifest(root / store).save()
                log(f"  {store}/_manifest.json: kept its records without their links and sealed it again. "
                    f"The next {store} sync fetches the links from the store.")
    log("Rebuilding catalog.json, tags.json and every asset.json from the records...")
    build_catalog(cfg, root)
    return 1 if changed else 0


# ----------------------------------------------------------------------------- CLI

STORE_DIRS = {"booth": "Booth", "gumroad": "Gumroad", "jinxxy": "Jinxxy", "payhip": "Payhip", "itch": "Itch",
              "local": "Local"}   # Local: your own packages (issue #80), not a store; see hoard/local.py


def unreachable_message(store: str) -> str:
    """What to tell you when a store's website can't be reached."""
    host = STORE_HOSTS[store].replace("accounts.", "").replace("app.", "")
    return (f"{STORES[store]['label']}: couldn't reach {host}, so nothing was synced from it. You may be offline, or the "
            "store may be down. Your downloads are unchanged; try again when you're connected.")


def cmd_sync(cfg: dict, args) -> None:
    """Sync the chosen stores, then rebuild the catalog and print a summary, even after Ctrl+C."""
    root = root_dir(cfg)
    root.mkdir(parents=True, exist_ok=True)
    log(f"Downloading into {root}")
    from . import previous
    previous.set_keep(cfg.get("keep_previous", 1))   # what an update replaces is kept (hoard/previous.py)
    report = Report(retries=download_retries(cfg))
    asked = list(DOWNLOADABLE) if args.store == "all" else ([args.store] if isinstance(args.store, str) else list(args.store))
    stores = [s for s in asked if s in DOWNLOADABLE]   # Payhip is read, never downloaded from
    from .stores import adapters
    syncers = {key: a.transfer for key, a in adapters().items() if a.downloads}
    try:
        for store in stores:
            label, folder = STORES[store]["label"], STORE_DIRS[store]
            if not cfg[store].get("enabled", True):
                continue
            if not reachable(store):
                report.failed.append(unreachable_message(store))
                continue
            try:
                syncers[store](cfg, root, args, report)
                report.stores_done.append(store)
            except SigninsUnprotected as e:
                report.failed.append(str(e))
                break
            except ProfileBusy as e:
                report.failed.append(str(e))
            except NotLoggedIn as e:
                if (root / folder / "_manifest.json").exists():
                    report.failed.append(f"{label}: {e} - sign in to {label} again (Stores, then Sign in)")
                else:
                    report.skipped.append(f"{label}: not signed in, so skipped. Sign in from Stores to include it.")
            except Exception as e:
                from .setup import browser_problem   # (setup imports this module's neighbours; imported here to keep it light)
                if any(code in str(e) for code in NETWORK_ERRORS):
                    report.failed.append(unreachable_message(store))
                elif browser_problem(e):
                    report.failed.append(f"{label}: {browser_problem(e)}")
                    break
                else:
                    report.failed.append(f"{label}: sync stopped - {e}")
    finally:  # also runs after Ctrl+C, so what did download is catalogued
        if not args.dry_run:
            build_catalog(cfg, root)
        report.print()
    return report
