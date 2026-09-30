"""Work Hoard does in the background, one job at a time: refreshing, signing in and out, and downloading."""
from __future__ import annotations

import json
import threading
import time

from .browser import (Blocked, LEGACY_PROFILE, ProfileBusy, SigninsUnprotected, _playwright, _remove_tree, check_saved_signin,
                      chosen_channel, launch, sign_out, signins_root, use_channel)
from .safety import store_link
from .setup import BROWSER_NAMES, browser_problem, install_browser
from .common import Cancelled, NotLoggedIn, Progress, capture_log
from . import diagnostics
from .config import payhip_shops
from .library import DOWNLOADABLE, FETCHERS, IMPORTABLE, PAYHIP_NO_SHOPS, Library, STORES, cache_images, open_sign_in_pages, unreachable_message
from .net import is_network_error, reachable
from .paths import data_dir
from .browser import old_signins_waiting, profile_dir   # (issue #31)
from .safety import DataFileError, read_json_file, write_file_safely
from .common import now_iso


NO_BROWSER = ("itch",)   # read through an API with a key, rather than with a sign-in in a browser


def forget_deleted_signins(cfg: dict, lib: Library) -> list[str]:
    """A store whose sign-in folder was deleted (by hand, from Hoard's app data) is signed out, so its list goes
    too, as when you choose Sign out: whoever signs in next never sees what that account owned (issue #31).
    Downloaded files stay. Only lists read from a signed-in store count: imported pages don't need a sign-in, and
    neither does itch.io (an API key). Returns the stores whose lists were removed."""
    try:
        if old_signins_waiting(cfg):   # an older version's shared sign-in, not split up yet: they may be in there
            return []
        # Sign-ins kept somewhere of your choosing (advanced_signin_location) may be on a drive that isn't plugged
        # in: with no sign-ins folder there at all, nothing is known about them, so no list is removed.
        if cfg.get("advanced_signin_location") and (cfg.get("profile_dir") or "").strip() \
                and not signins_root(cfg).is_dir():
            print(f"The sign-ins folder ({signins_root(cfg)}) isn't there (a drive not plugged in?), so Hoard left "
                  "your stores' lists as they are.", flush=True)
            return []
        folders = {store: profile_dir(cfg, store) for store in STORES if store not in NO_BROWSER}
    except (SigninsUnprotected, OSError):
        return []
    forgot = []
    with lib.lock:
        listed = {i["store"] for i in lib.data["items"]}
        read = {s for s, info in lib.data["stores"].items() if isinstance(info, dict) and info.get("source") == "refresh"}
    for store, folder in folders.items():
        if store in listed and store in read and not folder.exists():
            label = STORES[store]["label"]
            with lib.lock:
                n = sum(1 for i in lib.data["items"] if i["store"] == store)
            lib.clear_store(store, f"Signed out: Hoard's sign-in for {label} was deleted, so its list of {n} items was "
                                   "removed too. Your downloaded files are still on disk. Sign in to see them again.")
            print(f"{label}: its sign-in folder is gone, so its list of {n} items was removed", flush=True)
            forgot.append(store)
    return forgot
SYNC_CHOICES = (0, 6, 12, 24, 168)   # hours between automatic syncs; 0 = off
UNATTENDED = ("payhip",)   # never synced automatically: Payhip needs a visible window, for its bot check
OFFLINE_RETRY = 15 * 60    # an automatic sync that found no connection tries again this much later
FIRST_WAIT = 2 * 60        # after Hoard starts, before an automatic sync that's due


def _sync_file():
    return data_dir() / "sync.json"


def last_sync() -> float:
    """When the last sync started (yours or an automatic one), or 0."""
    try:
        data = read_json_file(_sync_file()) if _sync_file().is_file() else {}
    except (DataFileError, OSError):
        return 0.0
    last = data.get("last") if isinstance(data, dict) else None
    return float(last) if isinstance(last, (int, float)) and last > 0 else 0.0


def _record_sync() -> None:
    try:
        write_file_safely(_sync_file(), json.dumps({"last": time.time()}))
    except OSError:
        pass


class Schedule:
    """Automatic syncs, while Hoard is open: every auto_sync_hours after the last sync, whoever started it. Only
    stores that can be read without you (Payhip is left out), only once setup is done, never while another job
    runs, and not while offline (it tries again later, without marking your stores as unreachable)."""

    def __init__(self, cfg: dict, jobs: "Jobs"):
        self.cfg, self.jobs = cfg, jobs
        self.not_before = time.time() + FIRST_WAIT

    def stores(self) -> list[str]:
        return [s for s in STORES if self.cfg[s].get("enabled", True) and s not in UNATTENDED]

    def due(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        hours = self.cfg.get("auto_sync_hours") or 0
        return bool(hours in SYNC_CHOICES and hours and self.cfg.get("setup_done") and now >= self.not_before
                    and not self.jobs.state["running"] and now - last_sync() >= hours * 3600 and self.stores())

    def tick(self, now: float | None = None) -> bool:
        """Start a sync if one is due. True when it started."""
        now = time.time() if now is None else now
        if not self.due(now):
            return False
        stores = self.stores()
        if not any(reachable(s) for s in stores):
            self.not_before = now + OFFLINE_RETRY
            return False
        started = self.jobs.start("sync", stores, skip_imported=False, scheduled=True, queue=False) == "started"
        if started:
            print(f"Syncing by itself ({', '.join(STORES[s]['label'] for s in stores)})", flush=True)
        return started

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.wait(60):
            try:
                self.tick()
            except Exception as e:   # never let the schedule die: say so, and try again next minute
                diagnostics.record_exception(e, area="scheduler", task="sync", include_traceback=True)
                print(f"Automatic sync: {type(e).__name__}: {e}", flush=True)


# ----------------------------------------------------------------------------- background jobs

TASK_NAMES = {"refresh": "Refresh", "sync": "Sync", "download": "Download", "check-updates": "Check for updates",
              "login": "Sign in", "logout": "Sign out", "install-browser": "Install Hoard's browser"}
MAX_QUEUE = 50       # jobs waiting at once
MAX_HISTORY = 60     # finished jobs kept in the Tasks tab (tasks.json)
MAX_TRAIL = 400      # lines kept of each job's progress


def tasks_file():
    return data_dir() / "tasks.json"


def describe_job(task: str, stores: list[str], only: str | None = None, keys: list | None = None,
                 scheduled: bool = False) -> str:
    """What a job does, in a few words: "Download: Booth, Gumroad (3 items)"."""
    names = ("every store" if stores == ["all"] else
             ", ".join(STORES[s]["label"] for s in stores if s in STORES)) if stores else ""
    extra = [f"{len(keys)} {'item' if len(keys) == 1 else 'items'}"] if keys else []
    extra += [f'"{only}"'] if only else []
    extra += ["automatic"] if scheduled else []
    return (TASK_NAMES.get(task, task) + (f": {names}" if names else "")
            + (f" ({', '.join(extra)})" if extra else ""))


class Jobs:
    """Background work, one job at a time: refreshing stores, signing in and out, downloading. A job started while
    another runs waits in a queue and starts when its turn comes (issue #49); finished jobs are kept, with their
    progress, for the Tasks tab."""

    def __init__(self, cfg: dict, lib: Library, on_download_done=None):
        """No job is running at first. on_download_done is called after every download job."""
        self.cfg, self.lib = cfg, lib
        self.on_download_done = on_download_done or (lambda: None)
        self.busy = threading.Lock()
        self.stop = threading.Event()
        self.pending_link: str | None = None   # a sign-in link from an email, for the open sign-in window
        self.state = {"running": False, "task": None, "store": None, "message": "", "error": None,
                      "log": [], "report": None, "sync": False, "scheduled": False, "diagnostic": None,
                      "queue": [], "job_id": None, "transfer": None}
        self._queue: list[dict] = []        # jobs waiting their turn, oldest first
        self._qlock = threading.Lock()      # the queue, and taking the runner from it
        self._current: dict | None = None
        self._trail: list[str] = []         # the running job's progress, line by line
        self._ids = 0
        self.history: list[dict] = self._load_history()

    def _set(self, **kw):
        """Update the job state the page polls (and note each new message in the running job's progress)."""
        message = kw.get("message")
        if message and message != self.state.get("message") and self._current is not None:
            self._trail.append(str(message)[:500])
            del self._trail[:-MAX_TRAIL]
        self.state.update(kw)

    # ---- the queue (issue #49)

    def start(self, task: str, stores: list[str], skip_imported: bool = False, only: str | None = None,
              scheduled: bool = False, keys: list[str] | None = None, queue: bool = True) -> str | None:
        """Start a job in the background, or when one is running, queue it to start after (and after anything
        already waiting). Returns "started", "queued", or None: not started, because something is running and
        queue is False, the same job is already waiting, or the queue is full."""
        spec = {"task": task, "stores": list(stores), "skip_imported": skip_imported, "only": only,
                "scheduled": scheduled, "keys": list(keys) if keys else None}
        with self._qlock:
            if not self._queue and self.busy.acquire(blocking=False):
                self._launch(spec)
                return "started"
            same = [q for q in self._queue if all(q[k] == spec[k] for k in spec)]
            if not queue or same or len(self._queue) >= MAX_QUEUE:
                return None
            self._ids += 1
            self._queue.append({**spec, "id": f"q{self._ids}", "label": describe_job(task, stores, only, keys, scheduled),
                                "queued": now_iso()})
            self._publish_queue()
        self.kick()   # the running job may have finished meanwhile
        return "queued"

    def kick(self) -> None:
        """Start the next waiting job, if nothing is running. (Called whenever the runner is let go.)"""
        with self._qlock:
            if self._queue and self.busy.acquire(blocking=False):
                spec = self._queue.pop(0)
                self._publish_queue()
                self._launch(spec)

    def remove(self, job_id: str) -> bool:
        """Take a waiting job off the queue. False when it isn't waiting (it may have started)."""
        with self._qlock:
            before = len(self._queue)
            self._queue = [q for q in self._queue if q["id"] != job_id]
            self._publish_queue()
            return len(self._queue) != before

    def clear_queue(self) -> int:
        with self._qlock:
            n, self._queue = len(self._queue), []
            self._publish_queue()
            return n

    def _publish_queue(self) -> None:
        self.state["queue"] = [{"id": q["id"], "task": q["task"], "label": q["label"], "queued": q["queued"]}
                               for q in self._queue]

    def _launch(self, spec: dict) -> None:
        """Run spec now (the runner is already taken)."""
        task, stores, only, keys = spec["task"], spec["stores"], spec.get("only"), spec.get("keys")
        skip_imported, scheduled = spec.get("skip_imported", False), spec.get("scheduled", False)
        self._ids += 1
        self._current = {"id": f"j{self._ids}", "task": task, "stores": stores,
                         "label": describe_job(task, stores, only, keys, scheduled), "started": now_iso()}
        self._trail = []
        self.stop.clear()
        self.state.update(error=None, log=[], report=None, diagnostic=None, scheduled=scheduled, message="", transfer=None,
                          job_id=self._current["id"], job_label=self._current["label"])
        if task == "download":
            target = lambda s: self._download(s, only, keys)  # noqa: E731
        elif task == "check-updates":
            target = lambda s: self._download(s, only, keys, check=True)  # noqa: E731
        elif task == "sync":
            target = self._sync
        elif task == "install-browser":
            target = self._install_browser
        elif task == "login":
            target = self._login_then_refresh
        elif task == "logout":
            target = self._logout
        else:
            target = lambda s: self._refresh(s, skip_imported)  # noqa: E731
        self.state["running"] = True   # before the thread starts, so a page asking straight away sees it
        threading.Thread(target=self._wrap, args=(target, stores), daemon=True).start()

    def _wrap(self, fn, stores):
        """Run a job, recording any error for the page, and always free the runner afterwards (then start the next
        waiting job)."""
        try:
            self._set(running=True)
            fn(stores)
        except (ProfileBusy, SigninsUnprotected) as e:
            diagnostic = diagnostics.record_exception(e, area="job", task=self.state.get("task"),
                                                       store=self.state.get("store"), include_traceback=False)
            self._set(message=str(e), error=str(e), diagnostic=diagnostic)
        except Exception as e:
            why = browser_problem(e) or f"Stopped: {e}"
            diagnostic = diagnostics.record_exception(e, area="job", task=self.state.get("task"),
                                                       store=self.state.get("store"), include_traceback=True)
            self._set(message=why, error=why, diagnostic=diagnostic)
        finally:
            self._finish()
            self._set(running=False, task=None, store=None, scheduled=False, job_id=None, transfer=None)
            self.busy.release()
            self.kick()

    # ---- the Tasks tab: finished jobs

    def _finish(self) -> None:
        """Keep the job that just ended, with how it went and its progress, for the Tasks tab."""
        job = self._current
        if job is None:
            return
        self._current = None
        st = self.state
        message = str(st.get("message") or "")
        outcome = "failed" if st.get("error") else "stopped" if message.startswith("Stopped") else "done"
        trail = self._trail + [line for line in (st.get("log") or []) if line not in self._trail]
        report = st.get("report") if isinstance(st.get("report"), dict) else None
        self.history.append({**job, "ended": now_iso(), "outcome": outcome, "message": message[:600],
                             "report": report, "log": [str(x)[:500] for x in trail][-MAX_TRAIL:]})
        del self.history[:-MAX_HISTORY]
        try:
            write_file_safely(tasks_file(), json.dumps({"history": self.history}, ensure_ascii=False))
        except OSError as e:
            print(f"Couldn't save the task log: {e}", flush=True)

    def _load_history(self) -> list[dict]:
        try:
            raw = read_json_file(tasks_file()) if tasks_file().is_file() else {}
        except (DataFileError, OSError):
            return []
        out = []
        for h in (raw.get("history") if isinstance(raw, dict) and isinstance(raw.get("history"), list) else [])[-MAX_HISTORY:]:
            if not isinstance(h, dict) or h.get("task") not in TASK_NAMES:
                continue
            out.append({"id": str(h.get("id") or "")[:20], "task": h["task"], "label": str(h.get("label") or "")[:300],
                        "stores": [s for s in (h.get("stores") or []) if s in STORES or s == "all"] if isinstance(h.get("stores"), list) else [],
                        "started": str(h.get("started") or "")[:40], "ended": str(h.get("ended") or "")[:40],
                        "outcome": h.get("outcome") if h.get("outcome") in ("done", "failed", "stopped") else "done",
                        "message": str(h.get("message") or "")[:600],
                        "report": h.get("report") if isinstance(h.get("report"), dict) else None,
                        "log": [str(x)[:500] for x in h.get("log") or [] if isinstance(x, str)][-MAX_TRAIL:]
                        if isinstance(h.get("log"), list) else []})
        return out

    def tasks(self) -> dict:
        """The Tasks tab: what's running (with its progress so far), what's waiting, and what finished, newest
        first."""
        current = None
        if self.state.get("running") and self._current:
            current = {**self._current, "message": self.state.get("message") or "", "transfer": self.state.get("transfer"),
                       "log": (self._trail + [x for x in (self.state.get("log") or []) if x not in self._trail])[-MAX_TRAIL:]}
        return {"current": current, "queue": list(self.state["queue"]), "history": list(reversed(self.history))}

    def clear_history(self) -> None:
        self.history = []
        try:
            tasks_file().unlink(missing_ok=True)
        except OSError:
            pass

    def open_link(self, url: str) -> str | None:
        """Open a link from an email (a sign-in or "is this you?" link) in the sign-in window that's open now.
        Returns None when it will open, or why it won't. Only links on that store's own site are accepted."""
        store = self.state.get("store")
        if not (self.state["running"] and self.state["task"] == "login" and store):
            return "Start signing in to the store first, then paste the link while its window is open."
        if not store_link(store, url):
            return f"That link isn't on {STORES[store]['label']}'s own site, so Hoard won't open it."
        self.pending_link = url
        return None

    def _install_browser(self, stores: list[str]) -> None:
        """Download Hoard's own browser, passing progress to the page."""
        self._set(task="install-browser", message="Downloading Hoard's browser")
        lines: list[str] = []

        def progress(line: str) -> None:
            lines.append(line)
            del lines[:-40]
            self._set(message=line, log=lines[-20:])
            print(f"Installing the browser: {line}", flush=True)   # in hoard.log too, for when it goes wrong
        try:
            install_browser(progress)
        except RuntimeError as e:   # already a plain explanation
            why = str(e)[:1].upper() + str(e)[1:]
            print(why, flush=True)
            self._set(message=why, error=why, diagnostic=diagnostics.record_note(
                area="browser-install", task="install-browser", message=why))
            return
        self._set(message="Hoard's browser is installed.")

    def _sync(self, stores: list[str]) -> None:
        """Sync: read what you own from each store, then download anything new, as one job."""
        self.state["sync"] = True
        _record_sync()
        try:
            self._refresh(stores, skip_imported=True)
            if self.stop.is_set():
                self._set(message="Stopped. Anything half-downloaded resumes next time.")
                return
            self._download(stores, None)
        finally:
            self.state["sync"] = False

    def cancel(self) -> bool:
        """Stop the running download (or sync) within a few seconds; a file it was part way through resumes next time
        where it can. False when neither is running."""
        if self.state["running"] and (self.state["task"] in ("download", "check-updates") or self.state.get("sync")):
            self._set(message="Stopping")   # before the job can see Stop, so its "Stopped" is never overwritten
            self.stop.set()
            return True
        return False

    def _download(self, stores: list[str], only: str | None, keys: list[str] | None = None, check: bool = False) -> None:
        """Download everything new or changed from these stores (or only the products keys names), passing progress
        to the page as it goes. (Payhip is only read, so it's left out.) With check, download nothing: note what
        each product already downloaded has on its store that isn't on disk, for the Downloads page (issue #26)."""
        from types import SimpleNamespace
        from .downloader import cmd_sync
        from .asset_updates import AssetUpdates
        task = "check-updates" if check else "download"
        stores = [s for s in stores if s in DOWNLOADABLE]
        if not stores:
            self._set(task=task, message="Nothing to download: Hoard lists what you own on Payhip, and you "
                                         "download it from Payhip yourself.")
            self.on_download_done()
            return
        self._set(task=task, store=stores[0] if len(stores) == 1 else None, message="Starting")
        lines: list[str] = []

        def progress(msg):
            if isinstance(msg, Progress):   # how far a download has got: shown, not kept in the log or Tasks
                self.state.update(message=str(msg), transfer=msg.transfer)
            else:
                lines.extend(line.rstrip() for line in str(msg).splitlines() if line.strip())
                del lines[:-300]
                self._set(message=lines[-1] if lines else "", log=lines[-80:], transfer=None)
            if self.stop.is_set():
                self.stop.clear()   # the catalog is still rebuilt on the way out
                raise Cancelled()

        args = SimpleNamespace(store="all" if set(stores) >= set(DOWNLOADABLE) else stores, dry_run=check, only=only,
                               headed=False, keys=set(keys) if keys else None)
        try:
            with capture_log(progress):
                report = cmd_sync(self.cfg, args)
            if check:
                total = AssetUpdates().record_check(report.stores_done, args.keys, report.available)
                found = len({a["key"] for a in report.available})
                missed = [STORES[s]["label"] for s in stores if s not in report.stores_done and self.cfg[s].get("enabled", True)]
                self._set(report={"updates": found, "problems": report.failed[:20], "skipped_list": report.skipped[:20]},
                          message=(f"Checked: {found} {'item has' if found == 1 else 'items have'} updates" if found
                                   else "Checked: no updates") + (f" ({total} in all)" if total != found and not keys else "")
                                  + (f". Couldn't check {', '.join(missed)}." if missed else "."))
                return
            AssetUpdates().after_download(report.got, report.failed)
            summary = {k: len(getattr(report, k)) for k in ("new_assets", "new_files", "updated", "skipped", "failed")}
            self._set(report={**summary, "problems": report.failed[:20], "skipped_list": report.skipped[:20]},
                      message=(f"Done: {summary['new_assets']} new, {summary['updated']} updated"
                               + (f", {summary['failed']} couldn't be downloaded" if summary["failed"] else "") + "."))
        except Cancelled:
            self._set(message="Stopped checking for updates." if check else "Stopped. Anything half-downloaded resumes next time.")
        finally:
            self.on_download_done()   # a check can record files it finds already on disk, too

    def _logout(self, stores: list[str]) -> None:
        """Sign out of one store, or of every store, and mark the affected stores as signed out."""
        chosen = list(STORES) if stores[0] == "all" else [stores[0]]
        with _playwright()() as p:
            for store in chosen:
                label = STORES[store]["label"]
                self._set(task="logout", store=store, message=f"Signing out of {label}")
                done = sign_out(p, self.cfg, store)
                # The list of what that account owns goes too, so whoever signs in next never sees it.
                # Downloaded files stay where they are.
                forgot = self.lib.clear_store(store, "Signed out. " + done.split(": ", 1)[-1])
                if forgot:
                    self.lib.set_error(store, f"Signed out. {done.split(': ', 1)[-1]} Removed {forgot} items from the "
                                              "library; your downloaded files are still on disk.")
        if stores[0] == "all":
            root = signins_root(self.cfg)
            for extra in (root.parent / (root.name + ".old"), LEGACY_PROFILE):
                if extra.exists():
                    _remove_tree(extra)
            self._set(message="Signed out of every store. Each store's row in Stores says what was done.")
        else:
            self._set(message="Signed out. " + done.split(": ", 1)[-1])

    def _refresh(self, stores: list[str], skip_imported: bool = False) -> None:
        """Read each store's purchases and save them, keeping the old list when a read fails or comes back empty."""
        if skip_imported:
            stores = [s for s in stores if self.lib.data["stores"].get(s, {}).get("source") != "import"]
        self._set(task="refresh", message="Checking your connection")
        online = [s for s in stores if reachable(s)]
        for store in stores:
            if store not in online:
                self.lib.set_error(store, unreachable_message(store))
        if not online:
            self._set(message="You're offline. Your saved library still works.")
            return
        refreshed = []
        with _playwright()() as p:
            for store in online:
                label = STORES[store]["label"]
                if store == "payhip" and not payhip_shops(self.cfg):   # no shop to read: no window opened for nothing
                    self.lib.set_error(store, PAYHIP_NO_SHOPS)
                    continue
                self._set(task="refresh", store=store, message=f"Reading {label}")
                try:
                    # each store has its own sign-in; Payhip checks for automated browsers, so it gets a visible
                    # window you can complete its check in. itch.io is read through its API: no browser at all.
                    ctx = None if store in NO_BROWSER else \
                        launch(p, self.cfg, not (store == "payhip" and self.cfg["payhip"].get("headed", True)), store)
                except (ProfileBusy, SigninsUnprotected) as e:
                    self.lib.set_error(store, str(e))
                    continue
                try:
                    try:
                        items = FETCHERS[store](ctx, self.cfg, lambda m, l=label: self._set(message=f"{l}: {m}"))
                        before = self.lib.data["stores"].get(store, {}).get("count", 0)
                        if not items and before:
                            self.lib.set_error(store, f"Found no items this time (last time: {before}), so the old list was kept. "
                                                      f"Try again, or run the command: debug {store}")
                        else:
                            self.lib.replace_store(store, items)
                            if store == "payhip":   # shops on their own domains, found in your library, to review
                                with self.lib.lock:
                                    self.lib.data["stores"]["payhip"]["found_shops"] = self.cfg.pop("_found_payhip_shops", [])[:200]
                                    self.lib.save()
                            refreshed.append(store)
                    except NotLoggedIn as e:
                        self.lib.set_error(store, (
                            f"{str(e).rstrip('.')}. Choose Sign in to add an API key from itch.io." if store == "itch"
                            else "Not signed in. Choose Sign in, then close the browser window when you're done."))
                    except Blocked as e:
                        self.lib.set_error(store, (
                            f"{label} blocked the automated browser ({e}). Import your library instead: open it in "
                            f"your usual browser, scroll to the bottom, press Ctrl+S and save it as \"Webpage, Single "
                            f"File\" (each page of it, and for Payhip each shop's), then choose Import pages here.")
                            if store in IMPORTABLE
                            else f"{label} blocked the automated browser ({e}). Try again later.")
                    except Exception as e:
                        self.lib.set_error(store, unreachable_message(store) if is_network_error(e)
                                           else f"Couldn't read the library: {e}")
                finally:
                    if ctx:
                        ctx.close()
        if refreshed and self.cfg.get("offline_images", True):
            with self.lib.lock:
                keys = [i["key"] for i in self.lib.data["items"] if i["store"] in refreshed]
            cache_images(self.lib, keys, lambda m: self._set(message=m))
        self._set(message="Library updated")

    def _login_then_refresh(self, stores: list[str]) -> None:
        """Open a visible browser at a store's sign-in page, wait for the window to close, then refresh that store."""
        store = stores[0]
        label = STORES[store]["label"]
        if store in NO_BROWSER:   # signs in with an API key, from the page (POST /api/itch-key), not a window
            raise RuntimeError("itch.io signs in with an API key: choose Sign in on its row in Stores")
        if not reachable(store):
            self.lib.set_error(store, unreachable_message(store, "opened for signing in"))
            self._set(message=f"Couldn't reach {label}.", error=unreachable_message(store, "opened for signing in"))
            return
        channel, chosen = use_channel(self.cfg), chosen_channel(self.cfg)
        name = BROWSER_NAMES[channel]
        # which browser, in the log and on screen: a chosen browser that isn't installed is stood in for by Hoard's
        # own, and that used to happen without a word (issue #20)
        print(f"Signing in to {label} with {name}" + (f" ({BROWSER_NAMES[chosen]} was chosen, and isn't installed)"
                                                     if chosen != channel else ""), flush=True)
        with _playwright()() as p:
            ctx = launch(p, self.cfg, False, store)
            open_sign_in_pages(ctx, self.cfg, store)
            tabs = " (one tab per shop; sign in on each)" if store == "payhip" and len(ctx.pages) > 1 else ""
            self._set(task="login", store=store,
                      message=f"Sign in to {label} in the {name} window that opened{tabs}, then close that window.")
            while True:  # wait for the window to be closed
                try:
                    if not ctx.pages:
                        break
                    if self.pending_link:   # a link you pasted from an email: open it in this window
                        link, self.pending_link = self.pending_link, None
                        ctx.pages[0].goto(link)
                        self._set(message=f"Opened the link from your email in the {label} window. Finish there, "
                                          "then close the window.")
                    ctx.pages[0].wait_for_timeout(500)
                except Exception:
                    break
            try:
                ctx.close()
            except Exception:
                pass
        try:
            check_saved_signin(self.cfg, store)
        except SigninsUnprotected as e:
            self.lib.set_error(store, str(e))
            raise
        self._refresh([store])
