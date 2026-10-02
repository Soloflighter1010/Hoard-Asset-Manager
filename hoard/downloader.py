"""Keeping local copies: downloading from each store, the records of what's on disk, and the catalog files."""
from __future__ import annotations

import hashlib
import html
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

from .browser import ProfileBusy, STORE_SITES, SigninsUnprotected, _on_sites, _playwright, launch_context
from .common import NotLoggedIn, log, now_iso, tick
from .library import DOWNLOADABLE, STORES
from .config import root_dir
from .net import NETWORK_ERRORS, STORE_HOSTS, reachable
from .paths import PROBE_DIR, STORE_PYTHON_NOTE, store_python
from . import egress, itch, vault
from .safety import DataFileError, UnsafePath, check_seal, clean_text, fetch_public, open_under, read_json_file, rel_to_path, remember_sealed, safe_name, save_browser_download, scrub, seal, set_aside, store_link, valid_rel, write_file_safely
from .tags import TagMatcher, TagStore, clean_tag, tag_key

try:
    from tqdm import tqdm
except ImportError:  # progress bars are optional
    tqdm = None


GR_BASE = "https://app.gumroad.com"


GR_LIBRARY = GR_BASE + "/library"


GR_LOGIN = GR_BASE + "/login"


JX_BASE = "https://jinxxy.com"


JX_INVENTORY = JX_BASE + "/my/inventory"


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
    Downloads page, by tag_key)?"""
    if args.only and args.only.lower() not in f"{name} {creator}".lower():
        return True
    keys = getattr(args, "keys", None)
    return bool(keys) and tag_key(store, name) not in keys


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
              deleted_here: bool = False) -> None:
    """A dry run: note a file the store has that isn't on disk. For a product already downloaded, a file the store
    changed or added goes on the list of updates the Downloads page shows (issue #26); one downloaded before and
    since deleted from disk, unchanged, isn't an update (it's downloaded again all the same)."""
    log(f"    would {'update' if changed else 'download again' if deleted_here else 'download'}: {file}")
    if rec.get("files") and not deleted_here:
        report.available.append({"store": store, "key": tag_key(store, name), "name": name, "creator": creator,
                                 "file": file, "kind": "changed" if changed else "new"})


RETRY_WAITS = (5.0, 15.0, 30.0)   # seconds before each try again (issue #19)
NO_RETRY_STATUS = {400, 401, 403, 404, 410, 451}   # a store's answer that won't change by asking again


def download_retries(cfg: dict) -> int:
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


def with_retries(report: "Report", what: str, attempt, sleep=time.sleep):
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
            sleep(wait)


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
        time.sleep(seconds)


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
        self._saved, self._saved_at = self._contents(), 0.0   # what's on disk, and when this last wrote it

    def _check(self, raw) -> bool:
        """Check the manifest's seal, say what it means, and return whether its links can be trusted."""
        status = check_seal(raw, self.path)
        name = self.store_dir.name
        if status == "changed":
            copy = self.path.with_name(f"_manifest.changed-{time.strftime('%Y%m%d-%H%M%S')}.json")
            shutil.copy2(self.path, copy)
            log(f"{name}: _manifest.json was changed by something other than Hoard since it last saved it. "
                f"Its store links won't be used until this sync fetches them from {name} again. A copy is kept as "
                f"{copy.name}. Check what else can change {self.store_dir}.")
        elif status == "foreign":
            log(f"{name}: _manifest.json was last saved by Hoard on another computer, so its store links will "
                f"be fetched from {name} again. To share this folder between computers, copy integrity.key from Hoard's "
                "app-data folder on one to the other.")
        return status in ("sealed", "unsealed")

    def save(self) -> None:
        """Seal the manifest and write it through a temporary file, so a crash can't leave it half-written."""
        write_file_safely(self.path, json.dumps(seal(self.data), indent=2, ensure_ascii=False))
        remember_sealed(self.path)
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
        for m in (self.main, *self.others):
            m.checkpoint()

    def save_changes(self) -> None:
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
    from .marks import MarkStore   # read fresh: removing something takes effect on the next product
    return MarkStore().load()["removed"]


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


# ----------------------------------------------------------------------------- Gumroad

def extract_page_json(text: str):
    """Pull the Inertia page object (component + props) out of a Gumroad HTML page."""
    m = re.search(r'<script[^>]*\bdata-page="app"[^>]*>(.*?)</script>', text, re.S)
    if m:
        return json.loads(m.group(1))
    m = re.search(r'\bdata-page="(\{[^"]*)"', text)
    if m:
        return json.loads(html.unescape(m.group(1)))
    # Older react-on-rails markup, kept as a fallback
    best = None
    for m in re.finditer(r'<script[^>]*js-react-on-rails-component[^>]*data-component-name="([^"]+)"[^>]*>(.*?)</script>',
                         text, re.S):
        if best is None or len(m.group(2)) > len(best[1]):
            best = (m.group(1), m.group(2))
    if best:
        return {"component": best[0], "props": json.loads(best[1])}
    return None


def gumroad_session(cfg: dict) -> requests.Session:
    """An HTTP session signed in to Gumroad, using your Gumroad sign-in in Hoard's browser.

    Earlier versions also accepted a copied session cookie from config.json or an environment variable.
    That's a password-equivalent in plain text, so it's no longer read; sign in with `login gumroad` instead.
    """
    if cfg["gumroad"].get("session_cookie") or os.environ.get("HOARD_GUMROAD_SESSION"):
        log("Note: a Gumroad session cookie in config.json or HOARD_GUMROAD_SESSION is no longer used, because "
            "anyone who sees it can use your account. Delete it (and sign out of Gumroad on its website to end that "
            "session), then sign in with: login gumroad")
    s = egress.session()
    cookies, ua = browser_cookies(cfg, "gumroad")
    if not any(c["name"].startswith("_gumroad_app_session") for c in cookies):
        raise NotLoggedIn("Not signed in to Gumroad")
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    s.headers["User-Agent"] = ua
    return s


class Gumroad:
    """Reads Gumroad pages. Gumroad embeds each page's data as JSON, so no scraping is needed."""
    def __init__(self, cfg: dict, sess: requests.Session):
        """Wrap a signed-in session; request_delay from the config spaces out page loads."""
        self.cfg, self.sess = cfg, sess
        self.delay = float(cfg.get("request_delay", 1.0))

    def page(self, url: str, params: dict | None = None) -> dict:
        """Load a Gumroad page and return its embedded page data (component and props)."""
        time.sleep(self.delay)
        r = egress.get(self.sess, url, STORE_SITES["gumroad"], params=params, timeout=60)
        if "/login" in urlparse(r.url).path:
            raise NotLoggedIn("Gumroad session expired")
        r.raise_for_status()
        data = extract_page_json(r.text)
        if not data:
            raise RuntimeError(f"no page data found at {r.url} (Gumroad's markup may have changed)")
        return data

    def library(self):
        """Every purchase card in the library, archived ones included if configured."""
        modes = [False, True] if self.cfg["gumroad"].get("include_archived", True) else [False]
        for archived in modes:
            page_no = 1
            while True:
                params = {"page": page_no, "sort": "purchase_date"}
                if archived:
                    params["show_archived_only"] = "true"
                props = self.page(GR_LIBRARY, params).get("props", {})
                yield from props.get("results") or []
                pages = (props.get("pagination") or {}).get("pages") or 1
                if page_no >= pages:
                    break
                page_no += 1

    def file_url(self, page_url: str, token: str, file_id: str, fallback: str | None) -> str | None:
        """Ask for a signed download URL; fall back to the redirecting link on the download page."""
        try:
            r = egress.get(self.sess, urljoin(page_url, f"/r/{token}/product_files.json"), STORE_SITES["gumroad"],
                           params={"product_file_ids[]": file_id}, headers={"Accept": "application/json"}, timeout=60)
            if r.ok:
                files = r.json().get("files") or []
                if files and files[0].get("url"):
                    return files[0]["url"]
        except (requests.RequestException, ValueError):
            pass
        return urljoin(page_url, fallback) if fallback else None


def gumroad_files(items, prefix: str = ""):
    """Yield (sub-folder, file) for every file on a download page, following Gumroad's folders."""
    for it in items or []:
        if it.get("type") == "folder":
            yield from gumroad_files(it.get("children"), prefix + safe_name(it.get("name") or "Folder") + "/")
        elif it.get("type") == "file":
            yield prefix, it


def gumroad_page_images(content: dict) -> list[str]:
    """The pictures a creator put in a download page itself (Gumroad's rich content), in page order. Some products
    are only that: a set of PNG textures shown on the page, with no files listed."""
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "image":
                src = (node.get("attrs") or {}).get("src")
                if isinstance(src, str) and urlparse(src).scheme == "https" and urlparse(src).hostname == "public-files.gumroad.com":
                    found.append(src)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    for page in (content or {}).get("rich_content_pages") or []:
        if isinstance(page, dict):
            walk(page.get("description"))
    return list(dict.fromkeys(found))


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


def gumroad_filename(f: dict) -> str:
    """A safe local name for a Gumroad file: its name plus its extension, in lower case."""
    name = (f.get("file_name") or f.get("id") or "file").strip()
    ext = (f.get("extension") or "").strip().lower().lstrip(".")
    if ext and not name.lower().endswith("." + ext):
        name = f"{name}.{ext}"
    return safe_name(name, 150)


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


def _gumroad_page_images(gr, content: dict, rec: dict, folder: Path, name: str, creator: str, man, args,
                         report: Report) -> bool:
    """Save the pictures in a download page that lists no files, into "Page images", each named by its place on the
    page and typed by what it is. True when one was downloaded."""
    got_any = False
    public = egress.session()   # public pictures: fetched without your Gumroad sign-in
    for n, src in enumerate(gumroad_page_images(content), 1):
        token = urlparse(src).path.rstrip("/").rsplit("/", 1)[-1]
        fid = "page-image:" + token
        old = rec["files"].get(fid)
        if old and rel_to_path(folder, old["path"]).exists():
            continue
        stem = f"Page images/{n:02d} {safe_name(token, 40)}"
        if args.dry_run:
            would_get(args, report, "gumroad", rec, name, creator, stem, False, old is not None)
            continue
        staged = rel_to_path(folder, stem + ".download")
        try:
            with_retries(report, stem, lambda src=src, staged=staged: egress.download(
                public, src, staged, ["public-files.gumroad.com"], desc=stem, progress=downloading(stem)))
        except Exception as e:
            report.failed.append(f"Gumroad: {creator} / {name} / {stem} - {e}")
            continue
        ext = picture_extension(staged)
        if not ext:   # not a picture after all: not kept
            staged.unlink(missing_ok=True)
            report.skipped.append(f"Gumroad: {name} / {stem} - not a picture")
            continue
        relpath = f"{stem}.{ext}"
        os.replace(staged, rel_to_path(folder, relpath))
        rec["files"][fid] = {"path": relpath, "size": rel_to_path(folder, relpath).stat().st_size, "downloaded_at": now_iso()}
        log(f"    saved: {relpath}")
        report.new_files.append(f"Gumroad: {creator} / {name} / {relpath}")
        report.got.add(tag_key("gumroad", name))
        got_any = True
        man.checkpoint()
    return got_any


def sync_gumroad(cfg: dict, root: Path, args, report: Report) -> None:
    """Download everything new or changed in your Gumroad library."""
    store_dir = root / "Gumroad"
    man = StoreRecords(cfg, root, "Gumroad")
    gr = Gumroad(cfg, gumroad_session(cfg))

    try:
        _sync_gumroad_purchases(cfg, gr, store_dir, man, args, report)
    finally:
        gr.sess.cookies.clear()  # the copied sign-in only lives for this sync
        gr.sess.close()
        man.save_changes()   # every finished file recorded, however the sync ended


def _sync_gumroad_purchases(cfg: dict, gr: "Gumroad", store_dir: Path, man: StoreRecords, args, report: Report) -> None:
    """Download everything new or changed, one purchase at a time (see sync_gumroad)."""
    chosen = (getattr(args, "targets", None) or {}).get("gumroad")
    if chosen:   # straight to the chosen purchases' download pages
        cards = [{"product": {"name": i.get("name"), "creator": {"name": i.get("creator")}},
                  "purchase": {"id": i.get("id"), "download_url": i.get("download_url"), "variants": i.get("variants") or ""}}
                 for i in chosen]
        log(f"Gumroad: {len(cards)} chosen {'purchase' if len(cards) == 1 else 'purchases'}")
    else:
        cards = list(gr.library())
        log(f"Gumroad: {len(cards)} purchases in your library")
    seen: set[str] = set()

    for n, card in enumerate(cards, 1):
        tick(f"Gumroad: purchase {n} of {len(cards)}")   # Stop is noticed here too
        prod, pur = card.get("product") or {}, card.get("purchase") or {}
        name = (prod.get("name") or "Untitled").strip()
        creator = ((prod.get("creator") or {}).get("name") or "Unknown Creator").strip()
        if not chosen and skip_product(args, "gumroad", name, creator):
            continue
        page_url = pur.get("download_url")
        if not page_url:
            report.skipped.append(f"Gumroad: {name} - no download page (refunded or membership inactive)")
            continue
        try:
            page = gr.page(page_url)
        except NotLoggedIn:
            raise
        except Exception as e:
            report.failed.append(f"Gumroad: {name} - couldn't open download page: {e}")
            continue

        props = page.get("props") or {}
        content = props.get("content")
        if not content:
            report.skipped.append(f"Gumroad: {name} - page type {page.get('component')!r} has no files "
                                  "(may need email confirmation - open it once in the browser)")
            continue

        p = props.get("purchase") or {}
        key = f"{p.get('product_id') or pur.get('id')}:{p.get('variant_id') or ''}"
        if key in seen:  # bought the same product/variant twice
            continue
        seen.add(key)

        variants = (pur.get("variants") or "").strip()
        if removed_product("gumroad", name, report) or man.away(key, f"Gumroad: {name}", report):
            continue
        rec = man.record(key, creator, f"{name} - {variants}" if variants else name)
        is_new_asset = not rec["files"]
        rec.update(name=name, creator=creator, variants=variants or None, url=p.get("product_long_url"),
                   last_synced=now_iso())
        folder = man.folder_of(rec)
        token = props.get("token")
        log(f"\n[Gumroad] {creator} / {name}{f' ({variants})' if variants else ''}")

        got_any = False
        offered = {f.get("id") for _sub, f in gumroad_files(content.get("content_items"))}
        for sub, f in gumroad_files(content.get("content_items")):
            fid, size = f.get("id"), f.get("file_size")
            relpath = distinct_name(sub + gumroad_filename(f), fid, rec, offered)
            target = rel_to_path(folder, relpath)
            old = rec["files"].get(fid)
            if target.exists() and (not size or target.stat().st_size == size):
                rec["files"][fid] = {**(old or {}), "path": relpath, "size": target.stat().st_size}
                continue
            if not f.get("download_url"):
                report.skipped.append(f"Gumroad: {name} / {relpath} - streaming only, no download")
                continue
            is_update = target.exists() or (old is not None and (old.get("size") != size or old.get("path") != relpath))
            label = f"{creator} / {name} / {relpath}"
            if args.dry_run:
                would_get(args, report, "gumroad", rec, name, creator, relpath, is_update, old is not None and not is_update)
                continue
            try:
                got = with_retries(report, relpath, lambda fid=fid, f=f, target=target, relpath=relpath: egress.download(
                    gr.sess, gr.file_url(page_url, token, fid, f.get("download_url")), target, STORE_SITES["gumroad"],
                    desc=relpath, progress=downloading(relpath)))
            except Exception as e:
                report.failed.append(f"Gumroad: {label} - {e}")
                continue
            log(f"    {'updated' if is_update else 'saved'}: {relpath}")
            (report.updated if is_update else report.new_files).append(f"Gumroad: {label}")
            report.got.add(tag_key("gumroad", name))
            rec["files"][fid] = {"path": relpath, "size": got, "downloaded_at": now_iso()}
            got_any = True
            man.checkpoint()

        if not offered:   # no files: what the creator put in the page itself, such as a set of textures
            got_any = _gumroad_page_images(gr, content, rec, folder, name, creator, man, args, report) or got_any

        if got_any and is_new_asset:
            report.new_assets.append(f"Gumroad: {creator} / {name}")
        if cfg["gumroad"].get("save_thumbnails", True) and not args.dry_run:
            save_thumbnail(prod.get("thumbnail_url"), folder)
        man.checkpoint()


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
    return { idx: i, label: label.replace(/\s+/g, ' ').trim().slice(0, 300) };
  });
}
"""


JX_HOSTS = ["jinxxy\\.com"]


JX_INFO_JS = r"""
() => {
  const meta = p => (document.querySelector(`meta[property="${p}"]`) || {}).content || '';
  const LANDMARKS = 'nav, aside, header, footer, [role="navigation"], [role="banner"], [role="contentinfo"], [role="complementary"]';
  const GENERIC = /^(navigation|menu|profile|likes|lists|wishlist|inventory|marketplace|popular|leaderboard|product details|details|support info|my review|instructions from the creator.*)$/i;
  // A heading's own words, without its buttons and icons (a back arrow, a menu)
  const words = h => { const c = h.cloneNode(true); c.querySelectorAll('button, svg, [aria-hidden="true"]').forEach(x => x.remove());
    return c.textContent.replace(/\s+/g, ' ').trim(); };
  const bare = t => t.replace(/^[^\p{L}\p{N}]+/u, '').trim();
  // The product's title: the first heading in the page's content that isn't page furniture
  const h1 = [...document.querySelectorAll('main h1, main h2, h1, h2, h3')]
    .find(h => !h.closest(LANDMARKS) && bare(words(h)) && !GENERIC.test(bare(words(h))));
  const ogTitle = meta('og:title');
  const name = ((h1 && words(h1)) || (ogTitle && !/^jinxxy$/i.test(ogTitle.trim()) ? ogTitle : '')
    || (document.title || '').replace(/\s*[|\-\u2013]\s*jinxxy\s*$/i, '') || '').trim();
  // You, the signed-in user: your "Profile" link is never the creator
  const own = new Set();
  for (const l of document.querySelectorAll('a[href]')) {
    const t = (l.innerText || l.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    if (!/^(profile|my profile|view profile|account|my account)$/i.test(t)) continue;
    try { const segs = new URL(l.href).pathname.split('/').filter(Boolean); if (segs.length === 1) own.add(segs[0].toLowerCase()); } catch (e) {}
  }
  const reserved = new Set(['my','login','signin','signup','register','market','marketplace','search','help',
    'about','terms','privacy','discover','cart','checkout','settings','creators','categories','tags','blog',
    'api','dashboard','products','inventory','support','faq','legal']);
  const links = [];
  for (const a of document.querySelectorAll('a[href]')) {
    let u; try { u = new URL(a.href); } catch (e) { continue; }
    if (!/(^|\.)jinxxy\.com$/.test(u.hostname)) continue;
    const segs = u.pathname.split('/').filter(Boolean);
    if (!(segs.length === 1 || (segs.length === 2 && segs[1] === 'products'))) continue;
    if (reserved.has(segs[0].toLowerCase()) || own.has(segs[0].toLowerCase()) || a.closest(LANDMARKS)) continue;
    const after = h1 ? !!(h1.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING) : true;
    links.push({ after, creator: (a.innerText || '').trim() || segs[0] });
  }
  const pick = links.find(l => l.after) || links[0];
  const big = img => { const r = img.getBoundingClientRect(); return r.width >= 100 && r.height >= 100; };
  const usable = img => !img.closest(LANDMARKS) && big(img) && (img.currentSrc || img.src || '').startsWith('http');
  let thumbnail = '';
  for (let box = h1; box && box !== document.body && !thumbnail; box = box.parentElement) {
    const imgs = [...box.querySelectorAll('img')].filter(usable);
    if (imgs.length) thumbnail = imgs[0].currentSrc || imgs[0].src;   // the nearest picture to the title
  }
  return { name, creator: pick ? pick.creator : '', thumbnail };
}
"""


def settle(page, ms: int = 800) -> None:
    """Give a page time to finish loading: wait for the network to go quiet (at most 15 s), then ms more."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def jinxxy_require_login(page) -> None:
    """Raise NotLoggedIn when Jinxxy is showing its sign-in form."""
    path = urlparse(page.url).path.lower()
    if "login" in path or "signin" in path or page.locator("input[type=password]").count():
        raise NotLoggedIn("Not signed in to Jinxxy")


def jinxxy_link(u) -> bool:
    """Is this parsed link on Jinxxy itself: https, on jinxxy.com or one of its subdomains, with no user name,
    password or unusual port? (Not "jinxxy.com" anywhere in the address: notjinxxy.com, jinxxy.com.example.net and
    example.net/?jinxxy.com aren't Jinxxy.)"""
    try:
        port = u.port
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return (u.scheme == "https" and port in (None, 443) and u.username is None and u.password is None
            and (host == "jinxxy.com" or host.endswith(".jinxxy.com")))


def _scan_inventory(page, rx, inv_path: str, found: dict) -> list[str]:
    """Scroll / click 'load more' until this page stops growing. Returns numbered-page links seen."""
    page_links: list[str] = []
    quiet = 0
    for _ in range(300):
        before = len(found)
        for href in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
            u = urlparse(href)
            if not jinxxy_link(u):
                continue
            path = u.path.rstrip("/")
            if path == inv_path and re.search(r"(^|&)page=\d+", u.query):
                page_links.append(href)
            elif path != inv_path and rx.search(u.path):
                found.setdefault(f"{u.scheme}://{u.netloc}{path}", None)
        more = page.get_by_role("button", name=re.compile(r"load more|show more", re.I))
        if more.count() and more.first.is_visible() and more.first.is_enabled():
            more.first.click()
            settle(page, 600)
            quiet = 0
            continue
        page.mouse.wheel(0, 20000)
        page.wait_for_timeout(1200)
        quiet = quiet + 1 if len(found) == before else 0
        if quiet >= 3:
            break
    return page_links


def jinxxy_item_links(page, pattern: str) -> list[str]:
    """Every item URL in the inventory, whether it scrolls, has 'load more', or has numbered pages."""
    rx = re.compile(pattern)
    inv_path = urlparse(JX_INVENTORY).path.rstrip("/")
    found: dict[str, None] = {}
    visited, pending = {page.url}, []
    for _ in range(100):
        for href in _scan_inventory(page, rx, inv_path, found):
            if href not in visited and href not in pending:
                pending.append(href)
        if not pending:
            break
        nxt = pending.pop(0)
        visited.add(nxt)
        page.goto(nxt, wait_until="domcontentloaded")
        settle(page)
    return list(found)


def click_download(ctx, page, idx: int, timeout_s: int):
    """Click a tagged button and return the Download it triggers (in this tab or a popup)."""
    captured = []
    hooked = list(ctx.pages)
    popups = []

    def on_download(d):
        captured.append(d)

    def on_page(pg):
        pg.on("download", on_download)
        hooked.append(pg)
        popups.append(pg)

    for pg in hooked:
        pg.on("download", on_download)
    ctx.on("page", on_page)
    try:
        button = page.locator(f'[data-adl-idx="{idx}"]').first
        if button.is_visible():
            button.click(timeout=30000)   # a real click, waiting for overlays and animations to clear
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


def download_by_clicking(ctx, page, url: str, rec: dict, folder: Path, store: str, hosts: list[str], timeout_s: int,
                         name: str, creator: str, man: StoreRecords, args, report: "Report") -> bool:
    """Click every file's download button on the open page and save what each one downloads."""
    find = lambda allow_all: page.evaluate(DOWNLOAD_BUTTONS_JS, {"allowAll": allow_all, "hosts": hosts})  # noqa: E731
    buttons = find(False)
    allow_all = not buttons
    if allow_all:  # the product only offers a "download all" zip
        buttons = find(True)
    if not buttons:
        report.skipped.append(f"{store}: {name} - no download buttons found on {url}")
        return False

    wanted, used = [], set()
    for b in buttons:
        k = label_key(b["label"]) or f"file #{b['idx'] + 1}"
        if k in used:
            k = f"{k} #{b['idx'] + 1}"
        used.add(k)
        wanted.append((b["label"], k))

    got_any = False
    for pos, (label, k) in enumerate(wanted):
        old = rec["files"].get(k)
        if old and rel_to_path(folder, old["path"]).exists():
            continue
        if args.dry_run:
            would_get(args, report, store.lower(), rec, name, creator, label or k, False, old is not None)
            continue
        def attempt(label=label, k=k, pos=pos):
            """Click the file's button and save what it downloads (tried again by with_retries)."""
            current = find(allow_all)  # re-tag; the page may have re-rendered
            match = next((b for b in current if b["label"] == label), current[pos] if pos < len(current) else None)
            if not match:
                raise RuntimeError("button disappeared")
            dl = click_download(ctx, page, match["idx"], timeout_s)
            if page.url.split("#")[0].rstrip("/") != url.split("#")[0].rstrip("/"):  # the click navigated away
                page.goto(url, wait_until="domcontentloaded")
                settle(page)
            if not dl:
                raise RuntimeError("clicking download didn't start a download")
            fname = distinct_name(safe_name(dl.suggested_filename or k, 150), k, rec, {key for _label, key in wanted})
            # the same filename under a different label means the creator updated that file
            prev = next((fk for fk, fv in rec["files"].items() if fv.get("path") == fname and fk != k), None)
            is_update = prev is not None or (folder / fname).exists()
            log(f"    downloading: {fname}")
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
        report.got.add(tag_key(store, name))
        got_any = True
        man.checkpoint()
    return got_any


def forget_repeated_thumbnails(store_dir: Path) -> int:
    """Delete product pictures that are byte-for-byte identical across different products: that's a site's
    default banner, not a product. (Versions before 2.0.1 saved Jinxxy's.) Returns how many were removed."""
    by_hash: dict = {}
    for p in store_dir.glob("*/*/_thumbnail.*"):
        if p.is_file() and not p.is_symlink():
            by_hash.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), []).append(p)
    removed = 0
    for same in by_hash.values():
        if len(same) > 1:
            for p in same:
                p.unlink()
                removed += 1
    return removed


def sync_jinxxy(cfg: dict, root: Path, args, report: Report) -> None:
    """Download everything new or changed in your Jinxxy inventory."""
    jcfg = cfg["jinxxy"]
    store_dir = root / "Jinxxy"
    man = StoreRecords(cfg, root, "Jinxxy")
    if store_dir.is_dir() and not args.dry_run:
        banners = forget_repeated_thumbnails(store_dir)
        if banners:
            log(f"Jinxxy: removed {banners} copies of Jinxxy's default banner saved as product pictures; "
                "the real pictures are saved this time.")
    delay = float(cfg.get("request_delay", 1.0))

    with _playwright()() as p:
        browser = {"ctx": launch_context(p, cfg, not args.headed, "jinxxy")}
        try:
            ctx = browser["ctx"]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            chosen = (getattr(args, "targets", None) or {}).get("jinxxy")
            if chosen:   # straight to the chosen items' pages (each checks the sign-in as it opens)
                links = [i["url"] for i in chosen if jinxxy_link(urlparse(i["url"]))]
                log(f"Jinxxy: {len(links)} chosen {'item' if len(links) == 1 else 'items'}")
            else:
                page.goto(JX_INVENTORY, wait_until="domcontentloaded")
                settle(page, 1500)
                jinxxy_require_login(page)
                links = jinxxy_item_links(page, jcfg["item_link_pattern"])
                if not links:
                    raise RuntimeError("found no items on the inventory page - run the command: probe jinxxy")
                log(f"Jinxxy: {len(links)} items in your inventory")

            reopened = 0
            for n, url in enumerate(links, 1):
                tick(f"Jinxxy: item {n} of {len(links)}")   # Stop is noticed here, even when items fail fast
                time.sleep(delay)
                for again in (False, True):
                    if page.is_closed():
                        if reopened >= REOPENS:
                            raise RuntimeError(f"Jinxxy's browser closed by itself {reopened} times, so the rest of "
                                               "Jinxxy was left for next time. Hoard's log has what happened before each (Settings, "
                                               "Open logs folder).")
                        reopened += 1
                        page = reopen_tab(p, cfg, args, "jinxxy", browser)
                    try:
                        _jinxxy_item(browser["ctx"], page, url, man, store_dir, jcfg, args, report, chosen=bool(chosen))
                    except NotLoggedIn:
                        raise
                    except Exception as e:
                        if not again and (tab_closed(e) or page.is_closed()):
                            log(f"    Jinxxy's browser closed while on {url} ({e}); trying it again")
                            if not page.is_closed():
                                try:
                                    page.close()
                                except Exception:
                                    pass
                            continue
                        report.failed.append(f"Jinxxy: {url} - {e}")
                    break
        finally:
            man.save_changes()   # every finished file recorded, however the sync ended
            try:
                browser["ctx"].close()
            except Exception:
                pass   # a browser that already closed by itself


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


def _jinxxy_item(ctx, page, url, man, store_dir, jcfg, args, report, chosen: bool = False) -> None:
    """Open one Jinxxy item and download the files its page offers."""
    page.goto(url, wait_until="domcontentloaded")
    settle(page)
    jinxxy_require_login(page)
    info = page.evaluate(JX_INFO_JS)
    key = urlparse(url).path.rstrip("/").split("/")[-1]
    name = (info.get("name") or key).strip()
    creator = (info.get("creator") or "Unknown Creator").strip()
    if not chosen and skip_product(args, "jinxxy", name, creator):   # (a chosen item was picked by its page, not its name)
        return
    if removed_product("jinxxy", name, report) or man.away(key, f"Jinxxy: {name}", report):
        return
    rec = man.record(key, creator, name)
    is_new_asset = not rec["files"]
    rec.update(name=name, creator=creator, url=url, last_synced=now_iso())
    folder = man.folder_of(rec)
    log(f"\n[Jinxxy] {creator} / {name}")

    got_any = download_by_clicking(ctx, page, url, rec, folder, "Jinxxy", JX_HOSTS,
                                   int(jcfg.get("download_start_timeout", 90)), name, creator, man, args, report)

    if got_any and is_new_asset:
        report.new_assets.append(f"Jinxxy: {creator} / {name}")
    if jcfg.get("save_thumbnails", True) and not args.dry_run:
        save_thumbnail(info.get("thumbnail"), folder, "https://jinxxy.com/")
    man.checkpoint()


# ----------------------------------------------------------------------------- Booth
#
# Booth lists every purchase and gift at accounts.booth.pm/library, with a link for each file.
# The list is read in the browser with your saved login; the files then come straight from
# Booth over HTTP, so big downloads resume if they're interrupted.

BOOTH_LIBRARY = "https://accounts.booth.pm/library"


BOOTH_JS = r"""
() => {
  const idOf = h => { const m = (h || '').match(/\/items\/(\d+)/); return m ? m[1] : null; };
  const text = e => ((e && e.innerText) || '').replace(/\s+/g, ' ').trim();
  const out = new Map();
  for (const a of document.querySelectorAll('a[href*="/items/"]')) {
    const id = idOf(a.href);
    if (!id || out.has(id)) continue;
    let c = a;
    while (c.parentElement && c.parentElement !== document.body) {
      const ids = new Set([...c.parentElement.querySelectorAll('a[href*="/items/"]')].map(x => idOf(x.href)).filter(Boolean));
      if (ids.size > 1) break;
      c = c.parentElement;
    }
    const name = [...c.querySelectorAll('a[href*="/items/"]')].map(text).sort((x, y) => y.length - x.length)[0]
      || text(c.querySelector('.font-bold'));
    let creator = '', creatorUrl = '';
    for (const s of c.querySelectorAll('a[href]')) {
      let u; try { u = new URL(s.href); } catch (e) { continue; }
      if (/\.booth\.pm$/.test(u.hostname) && !['accounts.booth.pm', 'www.booth.pm'].includes(u.hostname)
          && !/\/items\//.test(u.pathname) && text(s)) { creator = text(s); creatorUrl = u.origin + '/'; break; }
    }
    if (!creator) creator = text(c.querySelector('.text-text-gray600'));
    const img = c.querySelector('a[href*="/items/"] img') || c.querySelector('img');
    const thumb = img ? (img.getAttribute('data-original') || img.getAttribute('data-src') || img.currentSrc || img.src || '') : '';
    // Files. Booth now draws each file's buttons from placeholders that carry the address in data-href
    // (2026); older pages used plain links. "Download" is the file itself; "Open in Browser" (?browse=1) and the
    // Booth Library Manager links (/deeplink) are other ways to the same file, so they're skipped.
    const FILE_SEL = '[data-href*="/downloadables/"], a[href*="/downloadables/"]';
    const addr = el => el.getAttribute('data-href') || el.getAttribute('href') || '';
    const fileId = el => {
      const h = addr(el), m = h.match(/\/downloadables\/(\d+)(?:[?#]|$)/);
      return m && !/[?&]browse=/.test(h) && (el.getAttribute('data-test') || 'downloadable') === 'downloadable' ? m[1] : null;
    };
    const seen = new Set(), files = [];
    for (const d of c.querySelectorAll(FILE_SEL)) {
      const fid = fileId(d);
      if (!fid || seen.has(fid)) continue;
      seen.add(fid);
      let r = d;   // the file's row: widen from its button while the row is still about this one file
      while (r.parentElement && r.parentElement !== c) {
        const p = r.parentElement;
        const ids = new Set([...p.querySelectorAll(FILE_SEL)].map(x => (addr(x).match(/\/downloadables\/(\d+)/) || [])[1]).filter(Boolean));
        if (ids.size > 1 || p.querySelector('a[href*="/items/"], img')) break;
        r = p;
      }
      const row = r.cloneNode(true);
      row.querySelectorAll('.js-download-button, button, [data-href], a[href*="/downloadables/"]').forEach(x => x.remove());
      const name = (row.textContent || '').replace(/\s+/g, ' ').replace(/ダウンロード|Download|Open in Browser|Other Downloads/gi, '').trim();
      files.push({ name: name || 'File', url: new URL(addr(d), location.href).href });
    }
    const order = c.querySelector('a[href*="/orders/"]');
    out.set(id, { id, name, creator, creator_url: creatorUrl, thumbnail: thumb, url: a.href,
                  order_url: order ? order.href : '', files });
  }
  return [...out.values()];
}
"""


def booth_require_login(page) -> None:
    """Raise NotLoggedIn when Booth has sent the browser to its sign-in page."""
    u = urlparse(page.url)
    if u.hostname != "accounts.booth.pm" or "sign_in" in u.path or page.locator("input[type=password]").count():
        raise NotLoggedIn("Not signed in to Booth")


def booth_library(page, cfg: dict) -> list[dict]:
    """Every purchase (and, if enabled, gift) in your Booth library, one dict per item."""
    items: dict[str, dict] = {}
    delay = float(cfg.get("request_delay", 1.0))
    sources = [("", False)] + ([("/gifts", True)] if cfg["booth"].get("include_gifts", True) else []) \
        + ([("/free_downloads", False)] if cfg["booth"].get("include_free", True) else [])
    for path, gift in sources:
        for page_no in range(1, 500):
            resp = page.goto(f"{BOOTH_LIBRARY}{path}?page={page_no}", wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            booth_require_login(page)  # a sign-in page means the session ended, whatever its status code
            if resp is not None and resp.status >= 400:
                raise RuntimeError(f"accounts.booth.pm answered HTTP {resp.status}")
            if not urlparse(page.url).path.startswith("/library"):
                break
            new = 0
            for b in page.evaluate(BOOTH_JS):
                if b["id"] not in items:
                    items[b["id"]] = {**b, "gift": gift}
                    new += 1
            if not new:  # past the last page
                break
            time.sleep(delay)
    return list(items.values())


def session_from_context(ctx, domain: str) -> requests.Session:
    """A requests session carrying the browser's cookies for one site, and the same User-Agent."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    s = egress.session(page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome"))
    for c in ctx.cookies():
        if c["domain"].lstrip(".").endswith(domain):
            s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    return s


def booth_file_location(sess: requests.Session, url: str) -> str:
    """Booth answers a file link with a redirect to a short-lived download address."""
    r = egress.get(sess, url, STORE_SITES["booth"], follow=False, timeout=60, headers={"Referer": BOOTH_LIBRARY})
    if r.status_code in (301, 302, 303, 307, 308):
        loc = urljoin(url, r.headers.get("Location", ""))
        if "sign_in" in loc or urlparse(loc).path.startswith("/users"):
            raise NotLoggedIn("Booth session expired")
        return loc
    if r.ok and not r.headers.get("Content-Type", "").startswith("text/html"):
        return url
    if r.ok:
        raise NotLoggedIn("Booth sent a web page instead of the file; the session may have expired")
    raise RuntimeError(f"booth.pm answered HTTP {r.status_code} instead of sending the file")


def booth_filename(label: str, location: str, fallback: str) -> str:
    """A safe local name for a Booth file: the name Booth shows, or the one in its download address."""
    name = (label or "").strip()
    if not re.search(r"\.[A-Za-z0-9]{1,12}$", name):  # Booth shows the file name; if not, use the download address
        name = unquote(Path(urlparse(location).path).name) or name or fallback
    return safe_name(name, 150)


BOOTH_ITEM_FILES_JS = r"""
() => {
  // A Booth item's own page (booth.pm/.../items/<id>): each file's download link, booth.pm/downloadables/<id>.
  // Items in the library's "free downloads" list only have their files here.
  const text = e => ((e && e.innerText) || '').replace(/\s+/g, ' ').trim();
  const fileName = /[^\s\/\\]+\.[A-Za-z][A-Za-z0-9]{0,11}(?=\s|$)/;   // (an extension starts with a letter: not "Ver1.2")
  const LINKS = 'a[href*="/downloadables/"], [data-href*="/downloadables/"]';
  const idOf = e => { const m = (e.getAttribute('href') || e.getAttribute('data-href') || '').match(/\/downloadables\/(\d+)/); return m && m[1]; };
  const out = new Map();
  for (const e of document.querySelectorAll(LINKS)) {
    let u; try { u = new URL(e.getAttribute('href') || e.getAttribute('data-href') || '', location.href); } catch (x) { continue; }
    const m = u.pathname.match(/^\/downloadables\/(\d+)\/?$/);   // not a deeplink for Booth's app, not "open in browser"
    if (!m || u.searchParams.has('browse') || !/(^|\.)booth\.pm$/.test(u.hostname) || out.has(m[1])) continue;
    // the file's name: in its own row (widened from the link while the row is about this file only)
    let row = e;
    while (row.parentElement && row.parentElement !== document.body
           && [...row.parentElement.querySelectorAll(LINKS)].every(x => idOf(x) === m[1])) row = row.parentElement;
    const f = text(row).match(fileName);
    const name = f ? f[0] : '';
    out.set(m[1], { name, url: 'https://booth.pm/downloadables/' + m[1] });
  }
  return [...out.values()];
}
"""


def booth_item_files(page, url: str) -> list[dict]:
    """The files on a Booth item's own page, for an item the library lists without them (free downloads)."""
    page.goto(url, wait_until="domcontentloaded")
    settle(page)
    u = urlparse(page.url)   # (an item page is public: only a move to the sign-in page means the session ended)
    if "sign_in" in u.path or (u.hostname == "accounts.booth.pm" and page.locator("input[type=password]").count()):
        raise NotLoggedIn("Not signed in to Booth")
    return [f for f in page.evaluate(BOOTH_ITEM_FILES_JS) if store_url(f.get("url"), ["booth.pm"])]


BOOTH_CLICK_JS = """url => { const a = document.createElement('a'); a.href = url; a.rel = 'noreferrer';
  document.body.appendChild(a); a.click(); a.remove(); }"""


def booth_browser_download(page, url: str, folder: Path, label: str, fid: str, timeout_s: float,
                           name_for=lambda n: n) -> tuple[str, int]:
    """Download one Booth file through the signed-in browser, just as clicking its download button would.

    Returns (file name, size). Raises NotLoggedIn when Booth answers with its sign-in page instead.
    """
    started: list = []

    def on_download(download):
        started.append(download)

    page.on("download", on_download)
    try:
        page.evaluate(BOOTH_CLICK_JS, url)
        deadline = time.time() + timeout_s
        while not started and time.time() < deadline:
            page.wait_for_timeout(250)
            if "sign_in" in page.url or urlparse(page.url).path.startswith("/users"):
                raise NotLoggedIn("Booth session expired")
    finally:
        page.remove_listener("download", on_download)
    if not started:
        raise RuntimeError("Booth didn't start the download")
    dl = started[0]
    fname = name_for(booth_filename(label, dl.suggested_filename or dl.url, f"file-{fid}"))
    wait_for_browser_download(dl, fname)
    target = save_browser_download(dl, folder, fname)
    return fname, target.stat().st_size


def booth_fetch(page, sess, f: dict, folder: Path, fid: str, route: dict, timeout_s: float,
                name_for=lambda n: n) -> tuple[str, int]:
    """Download one Booth file. The direct route is fastest and resumes where it stopped; if Booth turns it away
    (sites often screen out anything that isn't a real browser), the rest of the run goes through the browser."""
    if route["direct"]:
        try:
            loc = booth_file_location(sess, f["url"])
            fname = name_for(booth_filename(f["name"], loc, f"file-{fid}"))
            return fname, egress.download(sess, loc, folder / fname, STORE_SITES["booth"], desc=fname,
                                          progress=downloading(fname))
        except (NotLoggedIn, RuntimeError, requests.RequestException, egress.UnsafeRequest) as e:
            route["direct"] = False
            log(f"    Booth turned the direct download away ({e}), so Hoard downloads through the browser instead.")
    return booth_browser_download(page, f["url"], folder, f["name"], fid, timeout_s, name_for)


def sync_booth(cfg: dict, root: Path, args, report: Report) -> None:
    """Download everything new or changed in your Booth library and gifts."""
    bcfg = cfg["booth"]
    man = StoreRecords(cfg, root, "Booth")
    delay = float(cfg.get("request_delay", 1.0))
    timeout_s = float(bcfg.get("download_start_timeout", 90))
    route = {"direct": True}
    with _playwright()() as p:
        ctx = launch_context(p, cfg, not args.headed, "booth")
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            items = booth_library(page, cfg)
            sess = session_from_context(ctx, "booth.pm")
            log(f"Booth: {len(items)} items in your library")
            try:
                for n, b in enumerate(items, 1):
                    tick(f"Booth: item {n} of {len(items)}")   # Stop is noticed here, even when items fail fast
                    name = (b["name"] or f"Booth item {b['id']}").strip()
                    creator = (b["creator"] or "Unknown Creator").strip()
                    if skip_product(args, "booth", name, creator):
                        continue
                    if removed_product("booth", name, report) or man.away(b["id"], f"Booth: {name}", report):
                        continue
                    rec = man.record(b["id"], creator, name)
                    is_new_asset, had_files = not rec["files"], bool(rec["files"])
                    rec.update(name=name, creator=creator, url=b["url"], gift=b["gift"] or None, last_synced=now_iso())
                    folder = man.folder_of(rec)
                    log(f"\n[Booth] {creator} / {name}")
                    if not b["files"] and store_url(b.get("url"), ["booth.pm"]):   # free items: on the item's page
                        try:
                            b["files"] = booth_item_files(page, b["url"])
                        except NotLoggedIn:
                            raise
                        except Exception as e:
                            log(f"    couldn't read the item's page for its files: {e}")
                    if not b["files"]:
                        report.skipped.append(f"Booth: {name} - no files listed in your library or on its page")
                        continue

                    got_any = False
                    for f in b["files"]:
                        if not store_url(f["url"], ["booth.pm"]):
                            report.skipped.append(f"Booth: {name} - a file link that isn't on booth.pm was ignored")
                            continue
                        m = re.search(r"/downloadables/(\d+)", f["url"])
                        fid = m.group(1) if m else f["url"]
                        old = rec["files"].get(fid)
                        if old and rel_to_path(folder, old["path"]).exists():
                            continue
                        guess = booth_filename(f["name"], "", f"file-{fid}")
                        replaces = next((k for k, v in rec["files"].items() if v.get("path") == guess), None)
                        if not old and not replaces and (folder / guess).exists():  # already on disk, e.g. downloaded by hand
                            rec["files"][fid] = {"path": guess, "size": (folder / guess).stat().st_size, "label": f["name"]}
                            continue
                        if args.dry_run:
                            would_get(args, report, "booth", rec, name, creator, f["name"] or guess, bool(replaces), old is not None)
                            continue
                        on_disk = {x.name for x in folder.iterdir()} if folder.is_dir() else set()
                        try:
                            offered = {(re.search(r"/downloadables/(\d+)", x["url"]) or [None, x["url"]])[1] for x in b["files"]}
                            fname, got = with_retries(report, f["name"] or guess, lambda f=f, fid=fid, offered=offered: booth_fetch(
                                page, sess, f, folder, fid, route, timeout_s,
                                name_for=lambda n, fid=fid, offered=offered: distinct_name(n, fid, rec, offered)))
                            prev = next((k for k, v in rec["files"].items() if v.get("path") == fname and k != fid), None)
                            is_update = had_files or prev is not None or fname in on_disk
                        except NotLoggedIn:
                            raise
                        except Exception as e:
                            report.failed.append(f"Booth: {creator} / {name} / {f['name']} - {e}")
                            continue
                        if prev:
                            rec["files"].pop(prev, None)
                        rec["files"][fid] = {"path": fname, "size": got, "label": f["name"], "downloaded_at": now_iso()}
                        log(f"    {'updated' if is_update else 'saved'}: {fname}")
                        (report.updated if is_update else report.new_files).append(f"Booth: {creator} / {name} / {fname}")
                        report.got.add(tag_key("booth", name))
                        got_any = True
                        man.checkpoint()
                        time.sleep(delay)

                    if got_any and is_new_asset:
                        report.new_assets.append(f"Booth: {creator} / {name}")
                    if bcfg.get("save_thumbnails", True) and not args.dry_run:
                        save_thumbnail(b["thumbnail"], folder, "https://booth.pm/")
                    man.checkpoint()
            finally:
                sess.cookies.clear()  # the copied sign-in only lives for this sync
                sess.close()
        finally:
            man.save_changes()   # every finished file recorded, however the sync ended
            ctx.close()


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


def sync_itch(cfg: dict, root: Path, args, report: Report) -> None:
    """Download everything new or changed in your itch.io library."""
    key = vault.load_key(cfg, "itch")
    if not key:
        raise NotLoggedIn("no itch.io API key yet")
    store_dir = root / STORE_DIRS["itch"]
    man = StoreRecords(cfg, root, STORE_DIRS["itch"])
    delay = float(cfg.get("request_delay", 1.0))
    sess = itch.session(key)
    try:
        keys = itch.owned_keys(sess, delay)
        log(f"itch.io: {len(keys)} {'item' if len(keys) == 1 else 'items'} in your library")
        for k in keys:
            g = itch.game_of(k)
            name = clean_text(g["title"], 300) or f"itch.io project {g['id']}"
            creator = clean_text(g["creator"], 200) or "Unknown Creator"
            if not g["id"] or skip_product(args, "itch", name, creator):
                continue
            if removed_product("itch", name, report) or man.away(str(g["id"]), f"itch.io: {name}", report):
                continue
            time.sleep(delay)
            try:
                _itch_project(sess, k, g, name, creator, man, store_dir, cfg["itch"], args, report)
            except NotLoggedIn:
                raise
            except Exception as e:
                report.failed.append(f"itch.io: {creator} / {name} - {e}")
    finally:
        sess.headers.pop("Authorization", None)   # the key only lives for this sync
        sess.close()
        man.save_changes()   # every finished file recorded, however the sync ended


def _itch_project(sess, k: dict, g: dict, name: str, creator: str, man: StoreRecords, store_dir: Path, icfg: dict, args,
                  report: Report) -> None:
    """Download each of one project's files that isn't here yet, or has changed."""
    files = itch.uploads(sess, g["id"], k["id"])
    if not files:
        report.skipped.append(f"itch.io: {name} - no files to download")
        return
    rec = man.record(str(g["id"]), creator, name)
    is_new_asset = not rec["files"]
    rec.update(name=name, creator=creator, url=store_link("itch", g["url"]), last_synced=now_iso())
    folder = man.folder_of(rec)
    log(f"\n[itch.io] {creator} / {name}")
    offered = {str(u["id"]) for u in files}
    got_any = False
    for u in files:
        fid = str(u["id"])
        label = clean_text(u.get("display_name") or u.get("filename"), 200) or f"file {fid}"
        # what itch.io says about the file: when it changes, the creator updated it
        shown = str(u.get("md5_hash") or f"{u.get('filename')}|{u.get('size')}|{u.get('updated_at')}")
        old = rec["files"].get(fid)
        if old and old.get("shown", shown) == shown and rel_to_path(folder, old["path"]).exists():
            continue
        if u.get("storage") == "external":
            report.skipped.append(f"itch.io: {name} / {label} - kept on another website, so not downloaded")
            continue
        if itch.systems(u) and icfg.get("skip_game_builds", True):
            report.skipped.append(f"itch.io: {name} / {label} - a game build for {' and '.join(itch.systems(u))}, so not "
                                  "downloaded (Settings, itch.io: Skip game builds)")
            continue
        if args.dry_run:
            would_get(args, report, "itch", rec, name, creator, label, old is not None and old.get("shown", shown) != shown,
                      old is not None and old.get("shown", shown) == shown)
            continue
        fname = distinct_name(safe_name(u.get("filename") or label, 150), fid, rec, offered)
        target = folder / fname
        prev = next((f for f, v in rec["files"].items() if v.get("path") == fname and f != fid), None)
        is_update = old is not None or prev is not None or target.exists()
        def fetch(fid=fid, target=target, fname=fname, u=u):
            got = egress.download(sess, itch.download_address(fid, k["id"]), target, itch.sites(), desc=fname,
                                 progress=downloading(fname))
            expected = str(u.get("md5_hash") or "").lower()
            if expected and md5_of(target) != expected:
                target.unlink(missing_ok=True)
                raise RuntimeError("the file didn't match itch.io's checksum, so it was deleted")
            return got
        try:
            size = with_retries(report, fname, fetch)
        except NotLoggedIn:
            raise
        except Exception as e:
            report.failed.append(f"itch.io: {creator} / {name} / {fname} - {e}")
            continue
        if prev:
            rec["files"].pop(prev, None)
        rec["files"][fid] = {"path": fname, "size": size, "label": label, "shown": shown, "downloaded_at": now_iso()}
        log(f"    {'updated' if is_update else 'saved'}: {fname}")
        (report.updated if is_update else report.new_files).append(f"itch.io: {creator} / {name} / {fname}")
        report.got.add(tag_key("itch", name))
        got_any = True
        man.checkpoint()
    if got_any and is_new_asset:
        report.new_assets.append(f"itch.io: {creator} / {name}")
    if rec["files"] and icfg.get("save_thumbnails", True) and not args.dry_run:
        save_thumbnail(g["cover"], folder, "https://itch.io/")
    man.checkpoint()


REDACT_KEYS = re.compile(r'("[^"]*(?:email|token|password|secret|session|cookie|authorization|jwt|license)[^"]*"\s*:\s*)"[^"]*"', re.I)


REDACT_QS = re.compile(r'((?:X-Amz-[A-Za-z-]+|Signature|Key-Pair-Id|Policy|token|sig)=)[^&"\s]+', re.I)


def redact(s: str) -> str:
    """Mask emails, tokens, passwords and signed-URL parts in text saved for troubleshooting."""
    return REDACT_QS.sub(r"\1***", REDACT_KEYS.sub(r'\1"***"', s or ""))


def cmd_probe(cfg: dict, args) -> None:
    """Record what Jinxxy's inventory and first item page load, for tuning the adapter."""
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    out = open(PROBE_DIR / "jinxxy_network.jsonl", "w", encoding="utf-8")
    with _playwright()() as p:
        ctx = launch_context(p, cfg, False, "jinxxy")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        responses = []
        page.on("response", responses.append)

        def dump(stage):
            for r in responses:
                try:
                    if "json" not in r.headers.get("content-type", "") and "graphql" not in r.url:
                        continue
                    body = r.text()
                except Exception:
                    continue
                out.write(json.dumps({"stage": stage, "method": r.request.method, "status": r.status,
                                      "url": redact(r.url), "request": redact((r.request.post_data or "")[:4000]),
                                      "response": redact(body[:30000])}, ensure_ascii=False) + "\n")
            responses.clear()

        page.goto(JX_INVENTORY, wait_until="domcontentloaded")
        settle(page, 2000)
        jinxxy_require_login(page)
        links = jinxxy_item_links(page, cfg["jinxxy"]["item_link_pattern"])
        dump("inventory")
        raw = bool(getattr(args, "raw", False))
        (PROBE_DIR / "inventory.html").write_text(page.content() if raw else scrub(page.content()), "utf-8")
        if raw:
            page.screenshot(path=str(PROBE_DIR / "inventory.png"), full_page=True)
        hrefs = sorted({urlparse(h).path for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")})
        (PROBE_DIR / "inventory_links.txt").write_text("\n".join(hrefs), "utf-8")
        log(f"Item links matching item_link_pattern: {len(links)}")

        if links:
            page.goto(links[0], wait_until="domcontentloaded")
            settle(page, 2000)
            dump("item")
            (PROBE_DIR / "item.html").write_text(page.content() if raw else scrub(page.content()), "utf-8")
            if raw:
                page.screenshot(path=str(PROBE_DIR / "item.png"), full_page=True)
            log(f"First item: {page.evaluate(JX_INFO_JS)}")
            for b in page.evaluate(DOWNLOAD_BUTTONS_JS, {"allowAll": True, "hosts": JX_HOSTS}):
                log(f"  download button: {b['label'][:120]}")
        ctx.close()
    out.close()
    log(f"\nWrote {PROBE_DIR}. " + ("These files are exactly what Jinxxy showed you, including your purchases and "
                                     "account details: only share them with someone you trust." if getattr(args, "raw", False)
                                     else "Email addresses, form values, tokens and signed links were removed, and there are "
                                          "no screenshots. If someone helping you needs more, run again with --raw."))


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
        mine = TagStore.tags_for(tagdata, tag_key(a["store"], a["name"]), a["name"], matcher)
        a_tags = sorted((ts & tags) - set(mine))
        added = a.get("first_seen") if isinstance(a.get("first_seen"), str) and len(a["first_seen"]) <= 40 else None
        catalog.append({"store": a["store"], "name": a["name"], "creator": a["creator"], "folder": folder,
                        "url": store_link(a["store"], a.get("url")), "variants": a.get("variants"), "added": added,
                        "files": sorted(f["path"] for f in a["files"].values()),
                        "tags": mine, "suggested_tags": a_tags,
                        **({"location": a["location"]} if a.get("location") else {}),
                        **({"library": a["library"]} if a.get("library") else {}),
                        **({"note": a["note"]} if a.get("note") else {})})
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


def move_product(cfg: dict, root: Path, key: str, to: int, progress=None) -> dict:
    """Move a downloaded product's files to another library folder (to: its number, 0 for the downloads folder; see
    hoard/libraries.py), and its record with them, so it's kept up to date there.

    Every file Hoard recorded is copied, and checked against its fingerprint (or its size, before the first check)
    as it arrives; only when all have arrived is the record moved and the originals deleted (Hoard's picture and
    asset.json with them, and the folder when that leaves it empty; anything else of yours in it stays). If anything
    goes wrong part way, what was copied is deleted and the original is left as it was. Nothing is read or written
    through a link. A Local item stays in the downloads folder. Returns {"name", "files", "bytes", "to"}; raises
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


EDIT_NOTE = """This is an editable copy of a download, made by Hoard on {when}.

    {name} by {creator} ({store})
    The original: {original}

Change anything here. Hoard never checks, updates or replaces this folder, and doesn't import from it: it's yours.

The original stays as the store sent it. Hoard checks that one, and replaces a file there that was changed, so
edit here instead. Only files that still matched what Hoard downloaded were copied. Anything you add to this
folder (a texture from a website, a tool someone sent you) hasn't been checked by Hoard, so be as careful with it
as with any download.
"""


def make_editable_copy(cfg: dict, root: Path, key: str) -> dict:
    """Copy a product's downloaded files into a folder of their own under edits_dir (issue #82), for you to change.

    Hoard checks and re-downloads files in the downloads folder, so edits there are lost, and an edited file can't
    be told from one that something else changed. The copy is outside Hoard's care altogether. Only the files Hoard
    recorded are copied, and only while they're still the size they were downloaded at; one that isn't is left out
    and named, so a file changed behind Hoard's back isn't passed on as the store's. Nothing is read through a
    link. The copy goes in a new folder each time ("Name (2)" beside an earlier copy), and a note in it says what
    it is. Returns {"folder", "files", "bytes", "skipped": [(path, why)]}. Raises ValueError when there's nothing to copy."""
    from .config import edits_dir
    dest_root = edits_dir(cfg)
    from . import libraries
    rdest = dest_root.resolve()
    for lib in libraries.roots(cfg, root):
        rroot = lib.resolve()
        if rdest == rroot or rroot in rdest.parents:
            raise ValueError("The folder for editable copies can't be inside a library folder. Choose another in "
                             "config.json (edits_root).")
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
    from .paths import data_dir
    return data_dir() / "integrity.json"


def last_integrity() -> dict | None:
    """What the last check of the downloads found (issue #83), or None if there hasn't been one."""
    try:
        raw = read_json_file(integrity_file()) if integrity_file().is_file() else None
    except (DataFileError, OSError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("checked"), str):
        return None
    num = lambda k: raw[k] if isinstance(raw.get(k), int) and not isinstance(raw.get(k), bool) else 0  # noqa: E731
    texts = lambda k: [str(x)[:500] for x in raw[k][:200]] if isinstance(raw.get(k), list) else []  # noqa: E731
    return {"checked": raw["checked"][:40], "products": num("products"), "files": num("files"), "fine": num("fine"),
            "changed": texts("changed"), "missing": texts("missing"), "data_changed": texts("data_changed"),
            "complete": raw.get("complete") is not False}


def check_integrity(root: Path, stop=None, progress=None, others=()) -> dict:
    """Check the downloads are as Hoard downloaded them (issue #83): every data file's seal, and every recorded file's
    size and SHA-256. A file's fingerprint is taken the first time it's checked and kept in its record; after that it's
    read again only when its size or modified time changed, so a routine check is quick. Nothing is changed but the
    records' fingerprints, and nothing is followed through a link. The result is kept in integrity.json (the
    Downloads page shows it) and returned: products and files checked, which files changed or are missing, and which
    data files were changed outside Hoard. stop: a threading.Event that ends the check early (it says so). others: the
    other library folders (hoard/libraries.py), checked the same way when their drive is connected, and named in
    "away" when it isn't."""
    import stat as _stat
    from .safety import _is_link
    say = progress or (lambda line: None)
    result = {"checked": now_iso(), "products": 0, "files": 0, "fine": 0, "changed": [], "missing": [],
              "data_changed": [], "complete": True, "away": []}
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
                    result["missing"].append(shown)
                    continue
                if _is_link(st) or not _stat.S_ISREG(st.st_mode) or (f.get("size") is not None and st.st_size != f["size"]):
                    result["changed"].append(shown)
                    continue
                if f.get("sha256") and f.get("mtime_ns") == st.st_mtime_ns:
                    result["fine"] += 1
                    continue
                try:
                    with open_under(base, where) as fh:
                        digest = hashlib.sha256()
                        for block in iter(lambda: fh.read(1024 * 1024), b""):
                            digest.update(block)
                except (UnsafePath, OSError):
                    result["missing"].append(shown)
                    continue
                if f.get("sha256") and f["sha256"] != digest.hexdigest():
                    result["changed"].append(shown)
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
    problems = []
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
    if entry.get("url") is not None and store_link(str(entry.get("store")), entry["url"]) != entry["url"]:
        problems.append(f"{label}: url isn't an https address on the store's own website")
    for key in ("tags", "suggested_tags"):
        if not isinstance(entry.get(key), list) or any(not isinstance(t, str) or clean_tag(t) != t or not t for t in entry[key]):
            problems.append(f"{label}: {key} has a tag that isn't clean")
    return problems


def build_catalog(cfg: dict, root: Path) -> None:
    """Write catalog.json, tags.json and each product's asset.json."""
    catalog, ordered = collect_catalog(cfg, root)
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
            write_file_safely(adir / "asset.json", json.dumps(seal({**CATALOG_FORMAT["asset"], **entry}), indent=2,
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
    write_file_safely(root / "catalog.json", json.dumps(seal({**form, "generated_at": now_iso(),
                                                              "assets": catalog}), indent=2, ensure_ascii=False), root)
    yours: dict[str, list] = {}
    for entry in catalog:
        for t in entry["tags"]:
            yours.setdefault(t, []).append(entry["folder"])
    write_file_safely(root / "tags.json", json.dumps(seal({
        **CATALOG_FORMAT["tags"], "generated_at": now_iso(), "total_assets": len(catalog),
        "tags": {t: {"count": len(v), "assets": v} for t, v in sorted(yours.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "suggested": {t: {"count": len(v), "assets": v} for t, v in ordered.items()},
    }), indent=2, ensure_ascii=False), root)


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
    report = Report(retries=download_retries(cfg))
    asked = list(DOWNLOADABLE) if args.store == "all" else ([args.store] if isinstance(args.store, str) else list(args.store))
    stores = [s for s in asked if s in DOWNLOADABLE]   # Payhip is read, never downloaded from
    syncers = {"booth": sync_booth, "gumroad": sync_gumroad, "jinxxy": sync_jinxxy, "itch": sync_itch}
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
