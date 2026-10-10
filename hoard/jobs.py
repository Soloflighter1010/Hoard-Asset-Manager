"""Work Hoard does in the background, one job at a time: refreshing, signing in and out, and downloading."""
from __future__ import annotations

import contextlib
import json
import sys
import threading
import time
import traceback
from pathlib import Path

from .browser import (Blocked, LEGACY_PROFILE, ProfileBusy, SigninsUnprotected, SignInWindow, _playwright, _remove_tree,
                      check_saved_signin, chosen_channel, launch, sign_out, signins_root, use_channel)
from .safety import store_link
from .tags import tag_key
from .setup import BROWSER_NAMES, browser_problem, install_browser, own_browser_installed, stop_install
from .common import Cancelled, NotLoggedIn, Progress, capture_log
from . import diagnostics
from .config import payhip_shops
from .library import DOWNLOADABLE, FETCHERS, IMPORTABLE, PAYHIP_NO_SHOPS, PAYHIP_SIGNED_IN_NO_SHOPS, Library, STORES, cache_images, open_sign_in_pages, sign_in_urls, unreachable_message
from .net import is_network_error, reachable
from .paths import data_dir
from .browser import end_browsers, old_signins_waiting, profile_dir   # (issue #31)
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
# issue #113: one routine check instead of both: hours between them (0 = off). It reads your stores, checks your
# downloads and checks for updates, then asks you which of what it found to download.
ROUTINE_CHOICES = (0, 6, 12, 24, 168, 720)


def routine_hours(cfg: dict) -> int:
    """How often the routine check runs: off until you choose, since it reads your stores. Before beta 4 there was
    Sync automatically: if you'd turned that on, the routine check keeps its hours."""
    hours = cfg.get("routine_hours")
    if hours in ROUTINE_CHOICES and not isinstance(hours, bool):
        return hours
    sync = cfg.get("auto_sync_hours")
    return sync if sync in SYNC_CHOICES and not isinstance(sync, bool) else 0


def _routine_file():
    return data_dir() / "routine.json"


def routine_record() -> dict:
    """When the routine check last ran ("last", seconds), and what it found that you haven't looked at yet ("found":
    when, and how many new products and updates), or None."""
    try:
        raw = read_json_file(_routine_file()) if _routine_file().is_file() else {}
    except (DataFileError, OSError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    last = raw.get("last") if isinstance(raw.get("last"), (int, float)) and not isinstance(raw.get("last"), bool) else 0.0
    found = raw.get("found") if isinstance(raw.get("found"), dict) else None
    if found:
        count = lambda k: found[k] if isinstance(found.get(k), int) and not isinstance(found.get(k), bool) and found[k] >= 0 else 0  # noqa: E731
        found = {"at": str(found.get("at") or "")[:40], "new": count("new"), "updates": count("updates")}
        found = found if found["new"] or found["updates"] else None
    return {"last": float(last), "found": found}


def save_routine(**change) -> None:
    """Change the routine check's record: last (when it ran) or found (None once you've looked)."""
    rec = routine_record()
    rec.update(change)
    try:
        write_file_safely(_routine_file(), json.dumps(rec))
    except OSError as e:
        print(f"Couldn't save the routine check's record: {e}", flush=True)


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


def _when(stamp: str) -> float:
    """An ISO time (as now_iso writes it) as seconds, or 0."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _record_sync() -> None:
    try:
        write_file_safely(_sync_file(), json.dumps({"last": time.time()}))
    except OSError:
        pass


class Schedule:
    """The routine check (issue #113), while Hoard is open: every routine_hours after the last one. It reads the
    stores that can be read without you (Payhip is left out), checks your downloads and checks for updates, then
    asks you which of what it found to download. Only once setup is done, never while another job runs, and not
    while offline (it tries again later, without marking your stores as unreachable)."""

    def __init__(self, cfg: dict, jobs: "Jobs"):
        self.cfg, self.jobs = cfg, jobs
        self.not_before = time.time() + FIRST_WAIT

    def stores(self) -> list[str]:
        return [s for s in STORES if self.cfg[s].get("enabled", True) and s not in UNATTENDED]

    def _downloaded(self) -> bool:
        from .config import root_dir
        from .downloader import STORE_DIRS
        root = root_dir(self.cfg)
        return any((root / d / "_manifest.json").is_file() for d in STORE_DIRS.values())

    def due(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        hours = routine_hours(self.cfg)
        return bool(hours and self.cfg.get("setup_done") and now >= self.not_before and not self.jobs.state["running"]
                    and now - routine_record()["last"] >= hours * 3600 and (self.stores() or self._downloaded()))

    def tick(self, now: float | None = None) -> bool:
        """Start the routine check if it's due. True when it started."""
        now = time.time() if now is None else now
        if not self.due(now):
            return False
        stores = self.stores()
        if stores and not any(reachable(s) for s in stores):
            self.not_before = now + OFFLINE_RETRY
            return False
        started = self.jobs.start("routine", stores, scheduled=True, queue=False) == "started"
        if started:
            print(f"Routine check ({', '.join(STORES[s]['label'] for s in stores) or 'your downloads'})", flush=True)
        return started

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.wait(60):
            try:
                self.tick()
            except Exception as e:   # never let the schedule die: say so, and try again next minute
                diagnostics.record_exception(e, area="scheduler", task="sync", include_traceback=True)
                print(f"Automatic sync: {type(e).__name__}: {e}", flush=True)


MAX_SKIP = 5000   # products you chose to always skip


def download_skip(cfg: dict) -> set[str]:
    """The products you chose to always skip when downloading (issue #107), by tag key. A download of products you
    choose by name still gets them."""
    keys = cfg.get("download_skip")
    return {k for k in keys[:MAX_SKIP] if isinstance(k, str) and 0 < len(k) <= 400} if isinstance(keys, list) else set()


# ----------------------------------------------------------------------------- background jobs

TASK_NAMES = {"refresh": "Refresh", "sync": "Sync", "download": "Download", "check-updates": "Check for updates",
              "login": "Sign in", "logout": "Sign out", "install-browser": "Install Hoard's browser",
              "verify": "Check downloads", "add-local": "Add to Local", "move": "Move to another library folder",
              "rescan-local": "Rescan in Local", "remove-local": "Take out of Local",
              "delete-files": "Delete downloaded files", "routine": "Routine check"}
MAX_QUEUE = 50       # jobs waiting at once
MAX_HISTORY = 60     # finished jobs kept in the Tasks tab (tasks.json)
MAX_TRAIL = 400      # lines kept of each job's progress
FORCE_AFTER = 20.0   # seconds after Stop before a store browser that stopped answering is ended
STUCK_AFTER = 300.0  # seconds without any progress before a job's whereabouts are written to Hoard's log
WATCHED = ("download", "check-updates", "sync", "refresh", "verify", "routine")   # jobs that never wait on you (sign-ins do)


# How a finished job went, in the Tasks tab. Partly done: it finished, but a store couldn't be read or a file
# couldn't be downloaded.
OUTCOMES = ("done", "partial", "failed", "stopped")


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _names(stores: list[str]) -> str:
    """Store names for a message: "Booth", "Booth and Gumroad", "Booth, Gumroad and Payhip"."""
    labels = [STORES[s]["label"] for s in stores if s in STORES]
    return " and ".join(labels) if len(labels) < 3 else ", ".join(labels[:-1]) + " and " + labels[-1]


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


def _paused_in_hoard() -> str:
    """Where Hoard's own code is paused, waiting on a store's browser. Playwright runs its side in a greenlet, so a job
    waiting on the browser shows only Playwright's event loop as the thread's stack; the call that's waiting is in
    the greenlet the job's code is paused in. Empty when there's none."""
    try:
        import gc
        import greenlet
    except ImportError:
        return ""
    here = str(Path(__file__).resolve().parent)
    out = []
    for g in gc.get_objects():
        try:
            frame = g.gr_frame if isinstance(g, greenlet.greenlet) else None
        except Exception:
            continue
        if frame is None:
            continue
        stack = traceback.extract_stack(frame)
        if any(str(Path(f.filename).resolve().parent) == here for f in stack):
            out.append("".join(traceback.format_list(stack)))
    return "".join(f"Waiting in:\n{s}" for s in out)


class Jobs:
    """Background work, one job at a time: refreshing stores, signing in and out, downloading. A job started while
    another runs waits in a queue and starts when its turn comes (issue #49); finished jobs are kept, with their
    progress, for the Tasks tab."""

    def __init__(self, cfg: dict, lib: Library, on_download_done=None):
        """No job is running at first. on_download_done is called after every download job."""
        self.cfg, self.lib = cfg, lib
        self.on_download_done = on_download_done or (lambda: None)
        self.find_choices = None   # how many new products and updates there are to download (the server sets it)
        self.on_found = None   # the routine check found more to download than before: Hoard's app tells you (hoard/notify.py)
        self._spec: dict | None = None   # what the running job was started with, to start an automatic one again
        self._made_way = False   # the running automatic job was stopped for one of yours (issue #110)
        self._forced = False     # Force stop was chosen for the running job
        self._sign_in = None     # the sign-in window open now, for Force stop to close
        self.busy = threading.Lock()
        self.stop = threading.Event()
        self.pending_link: str | None = None   # a sign-in link from an email, for the open sign-in window
        self.state = {"running": False, "task": None, "store": None, "message": "", "error": None,
                      "log": [], "report": None, "sync": False, "scheduled": False, "diagnostic": None,
                      "queue": [], "job_id": None, "transfer": None, "partial": None}
        self._queue: list[dict] = []        # jobs waiting their turn, oldest first
        self._qlock = threading.Lock()      # the queue, and taking the runner from it
        self._current: dict | None = None
        self._trail: list[str] = []         # the running job's progress, line by line
        self._job_thread: int | None = None   # the running job's thread, to say where it is when it's stuck
        self._moved = time.monotonic()      # when the running job last said anything
        self._ids = 0
        self.history: list[dict] = self._load_history()

    def _set(self, **kw):
        """Update the job state the page polls (and note each new message in the running job's progress)."""
        message = kw.get("message")
        if message:
            self._moved = time.monotonic()
        if message and message != self.state.get("message") and self._current is not None:
            self._trail.append(str(message)[:500])
            del self._trail[:-MAX_TRAIL]
        self.state.update(kw)

    # ---- the queue (issue #49)

    def start(self, task: str, stores: list[str], skip_imported: bool = False, only: str | None = None,
              scheduled: bool = False, keys: list[str] | None = None, queue: bool = True,
              items: list[str] | None = None, local: dict | None = None, move: dict | None = None,
              files: dict | None = None, chosen: dict | None = None) -> str | None:
        """Start a job in the background, or when one is running, queue it to start after (and after anything
        already waiting). Returns "started", "queued", or None: not started, because something is running and
        queue is False, the same job is already waiting, or the queue is full. items: the library items (by key) a
        download is for, when it's for chosen ones, so it can go straight to them. files: what a rescan, a take-out
        of Local or a deletion of downloaded files is for, when it waits its turn. chosen: of a download, the files
        chosen of each product ({tag_key: [file names]}) when you left some out."""
        spec = {"task": task, "stores": list(stores), "skip_imported": skip_imported, "only": only,
                "scheduled": scheduled, "keys": list(keys) if keys else None, "items": list(items) if items else None,
                "local": dict(local) if local else None, "move": dict(move) if move else None,
                "files": dict(files) if files else None, "chosen": dict(chosen) if chosen else None}
        with self._qlock:
            if not self._queue and self.busy.acquire(blocking=False):
                self._launch(spec)
                return "started"
            same = [q for q in self._queue if all(q[k] == spec[k] for k in spec)]
            if not queue or same or len(self._queue) >= MAX_QUEUE:
                return None
            self._ids += 1
            entry = {**spec, "id": f"q{self._ids}", "label": describe_job(task, stores, only, keys, scheduled),
                     "queued": now_iso()}
            # issue #110: yours go ahead of automatic ones waiting, and an automatic one running makes way for it
            ahead = next((n for n, q in enumerate(self._queue) if q.get("scheduled")), len(self._queue))
            self._queue.insert(len(self._queue) if scheduled else ahead, entry)
            make_way = not scheduled and self.state.get("scheduled") and self.state.get("running")
            if make_way and self._spec and not any(q.get("scheduled") and q["task"] == self._spec["task"] for q in self._queue):
                self._ids += 1   # it starts again after yours (what it had done is kept; a file part way resumes)
                self._queue.append({**self._spec, "id": f"q{self._ids}", "queued": now_iso(),
                                    "label": describe_job(self._spec["task"], self._spec["stores"], scheduled=True)})
            self._publish_queue()
        if make_way:
            self.make_way()
        self.kick()   # the running job may have finished meanwhile
        return "queued"

    def make_way(self) -> None:
        """Stop the automatic job that's running, safely, so the job you started goes first (issue #110). It says
        so in Tasks, and waits its turn after yours."""
        if not self.state.get("scheduled"):
            return
        self._made_way = True   # first: a quick job can be over as soon as it's stopped
        if self.cancel():
            self._set(message="Making way for your task: this carries on after it")
        else:
            self._made_way = False

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
        """Run spec now (the runner is already taken). If it can't even start, the runner is let go again, so one job
        that fails to start never leaves every later one waiting behind it."""
        try:
            self._start(spec)
        except BaseException:
            self._current = None
            self.state.update(running=False, task=None, job_id=None)
            self.busy.release()
            raise

    def _start(self, spec: dict) -> None:
        """Start spec's job on a thread of its own (see _launch)."""
        task, stores, only, keys = spec["task"], spec["stores"], spec.get("only"), spec.get("keys")
        items = spec.get("items")
        self._spec = dict(spec)
        skip_imported, scheduled = spec.get("skip_imported", False), spec.get("scheduled", False)
        self._ids += 1
        self._current = {"id": f"j{self._ids}", "task": task, "stores": stores,
                         "label": describe_job(task, stores, only, keys, scheduled), "started": now_iso()}
        self._trail = []
        self.stop.clear()
        self._forced = False   # (a Force stop that came as the last job ended isn't this one's)
        self.state.update(error=None, partial=None, log=[], report=None, diagnostic=None, scheduled=scheduled, message="",
                          transfer=None,
                          job_id=self._current["id"], job_label=self._current["label"])
        if task == "download":
            target = lambda s: self._download(s, only, keys, items=items, chosen=spec.get("chosen"))  # noqa: E731
        elif task == "check-updates":
            target = lambda s: self._download(s, only, keys, check=True, items=items)  # noqa: E731
        elif task == "sync":
            target = self._sync
        elif task == "install-browser":
            target = self._install_browser
        elif task == "verify":
            target = self._verify
        elif task == "routine":
            target = self._routine
        elif task == "add-local":
            target = lambda s: self._add_local(spec.get("local") or {})  # noqa: E731
        elif task == "move":
            target = lambda s: self._move(spec.get("move") or {})  # noqa: E731
        elif task in ("rescan-local", "remove-local", "delete-files"):
            target = lambda s: self._files(task, spec.get("files") or {})  # noqa: E731
        elif task == "login":
            target = self._login_then_refresh
        elif task == "logout":
            target = self._logout
        else:
            target = lambda s: self._refresh(s, skip_imported)  # noqa: E731
        self.state["running"] = True   # before the thread starts, so a page asking straight away sees it
        self._moved = time.monotonic()
        job_id = self._current["id"]   # (taken now: a quick job can be over before the next line runs)
        threading.Thread(target=self._wrap, args=(target, stores), daemon=True).start()
        if task in WATCHED:
            threading.Thread(target=self._watch, args=(job_id,), daemon=True).start()

    def _wrap(self, fn, stores):
        """Run a job, recording any error for the page, and always free the runner afterwards (then start the next
        waiting job)."""
        self._job_thread = threading.get_ident()
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
        if self._forced:   # Force stop: whatever it was doing when it ended (a closed browser, say) isn't a failure
            self._forced = self._made_way = False
            message = "Force stopped. " + message.removeprefix("Stopped.").removeprefix("Force stopping").strip()
            st["error"] = None
        if self._made_way:   # not stopped by you: it made way for your task, and carries on after it
            self._made_way = False
            message = "Made way for your task: it carries on after it. " + message.removeprefix("Stopped.").strip()
            st["error"] = None
        outcome = ("failed" if st.get("error") else "stopped" if message.startswith(("Stopped", "Made way", "Force stopped"))
                   else "partial" if st.get("partial") else "done")
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
                        "outcome": h.get("outcome") if h.get("outcome") in OUTCOMES else "done",
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
        if self._forced:
            return
        self._set(task="install-browser", message="Downloading Hoard's browser")
        lines: list[str] = []

        def progress(line: str) -> None:
            lines.append(line)
            del lines[:-40]
            self._set(message=line, log=lines[-20:])
            print(f"Installing the browser: {line}", flush=True)   # in Hoard's log too, for when it goes wrong
        try:
            install_browser(progress, stop=self.stop)
        except RuntimeError as e:   # already a plain explanation
            if self._forced:   # ended by Force stop, not by a failed download
                self._set(message="Stopped. Hoard's browser wasn't installed; installing it starts again next time.")
                return
            why = str(e)[:1].upper() + str(e)[1:]
            print(why, flush=True)
            self._set(message=why, error=why, diagnostic=diagnostics.record_note(
                area="browser-install", task="install-browser", message=why))
            return
        self._set(message="Hoard's browser is installed.")

    def _quietly(self, line: str) -> None:
        """Progress shown on the page (and counted as moving), but not kept in the job's log."""
        self._moved = time.monotonic()
        self.state["message"] = line

    def _move(self, what: dict) -> None:
        """Move a downloaded product to another library folder (hoard/libraries.py). Stop stops it part way, leaving
        it where it was."""
        from .config import root_dir
        from .downloader import move_product

        moved = []   # set once the move has gone through: a Stop after that can't undo it, so it lets it finish

        def sink(msg):
            self._moved = time.monotonic()
            self.state["message"] = str(msg)
            if self.stop.is_set() and not moved and threading.get_ident() == self._job_thread:
                self.stop.clear()
                raise Cancelled()
        self._set(task="move", message=f"Moving {what.get('name') or 'it'}")
        try:
            with capture_log(sink):
                done = move_product(self.cfg, root_dir(self.cfg), str(what.get("key") or ""), what.get("to"),
                                    committed=lambda: moved.append(True))
        except Cancelled:
            self._set(message="Stopped. Nothing was moved: it's where it was.")
            return
        except (ValueError, OSError) as e:
            why = str(e) if isinstance(e, ValueError) else f"Couldn't move it ({e}). Nothing was moved: it's where it was."
            self._set(message=why, error=why)
            return
        finally:
            self.on_download_done()
        self._set(message=f"Moved {done['name']}: {plural(done['files'], 'file')} to {done['to']}.")

    def _files(self, task: str, what: dict) -> None:
        """A rescan or take-out of something in Local, or deleting a removed product's downloaded files, that was
        asked for while another job ran, so it waited its turn (the server does them at once when nothing runs)."""
        from .config import root_dir
        from . import local
        from .downloader import delete_downloaded_files
        root, name = root_dir(self.cfg), what.get("name") or "it"
        self._set(task=task, message=f"{TASK_NAMES[task]}: {name}")
        try:
            if task == "delete-files":
                done = delete_downloaded_files(self.cfg, root, set(what.get("keys") or []))
                message = (f"Deleted {done['files']:,} {'file' if done['files'] == 1 else 'files'} of {name}."
                           + (" Its folder still has other files, so it was kept." if done["kept"] else ""))
            else:
                found = local.by_folder(root, str(what.get("folder") or ""))
                if not found:
                    raise ValueError(f"{name} isn't in Local any more.")
                if task == "rescan-local":
                    rec = local.rescan(self.cfg, root, found[0])
                    message = f"Rescanned {name}: {plural(len(rec['files']), 'file')}."
                else:
                    local.remove(self.cfg, root, found[0])
                    message = f"Took {name} out of Local."
        except (ValueError, OSError) as e:
            self._set(message=str(e), error=str(e))
            return
        finally:
            self.on_download_done()
        self._set(message=message)

    def _add_local(self, what: dict) -> None:
        """Add a folder or file of your own to Local (issue #80): copied in, or listed where it is."""
        from .config import root_dir
        from . import local
        self._set(task="add-local", message="Adding to Local")
        if what.get("depth"):
            return self._add_local_folders(what)
        try:
            rec = local.add(self.cfg, root_dir(self.cfg), what.get("path", ""), what.get("name", ""), what.get("creator", ""),
                            what.get("note", ""), bool(what.get("copy", True)), progress=self._quietly)
        except ValueError as e:
            self._set(message=str(e), error=str(e))
            return
        self._set(message=f"Added {rec['name']} to Local: {plural(len(rec['files']), 'file')}"
                          + (", copied into Hoard." if not rec.get("location") else ", listed where they are."))
        self.on_download_done()

    def _add_local_folders(self, what: dict) -> None:
        """Issue #109: each folder some levels down in a folder of folders, added to Local as a package of its own."""
        from .config import root_dir
        from .downloader import build_catalog
        from . import local
        root = root_dir(self.cfg)
        try:
            plan = local.split(root, what.get("path", ""), what.get("depth"), bool(what.get("copy", True)))
        except ValueError as e:
            self._set(message=str(e), error=str(e))
            return
        added, left = 0, []
        already = [pkg for pkg in plan["packages"] if pkg.get("added")]
        plan["packages"] = [pkg for pkg in plan["packages"] if not pkg.get("added")]   # added before: not twice
        try:
            for n, pkg in enumerate(plan["packages"], 1):
                if self.stop.is_set():
                    break
                self._set(message=f"Adding {n} of {len(plan['packages'])} to Local: {pkg['name']}")
                try:
                    local.add(self.cfg, root, pkg["path"], pkg["name"], what.get("creator") or pkg["creator"],
                              what.get("note", ""), bool(what.get("copy", True)), progress=self._quietly, catalog=False)
                    added += 1
                except ValueError as e:
                    left.append(f"{pkg['rel']}: {e}")
        finally:
            if added:
                build_catalog(self.cfg, root)
        said = f"Added {plural(added, 'package')} to Local" + (" (stopped part way)" if self.stop.is_set() else "") + "."
        if already:
            one = len(already) == 1
            said += (f" {len(already)} {'was' if one else 'were'} already in Local, and "
                     f"{'was left as it was' if one else 'were left as they were'}.")
        if left:
            said += f" Left out {len(left)}: " + "; ".join(left[:5]) + ("…" if len(left) > 5 else "")
        self._set(message=said, log=[f"Left out {x}" for x in left][-200:], partial=bool(left))
        self.on_download_done()

    def _verify(self, stores: list[str], fresh: bool = False) -> str:
        """Check the downloads are as Hoard downloaded them (issue #83), naming any file that isn't. fresh: files
        downloaded since the last check aren't read yet (issue #113): they were checked as they came in."""
        from .config import root_dir
        from .downloader import check_integrity, integrity_summary, last_integrity
        self._set(task="verify" if not self.state.get("routine") else "routine", message="Checking your downloads")
        from .libraries import other_folders
        since = (last_integrity() or {}).get("checked") if fresh else None
        result = check_integrity(root_dir(self.cfg), stop=self.stop, progress=self._quietly,
                                 others=other_folders(self.cfg), fresh_since=since)
        lines = ([f"Changed: {p}" for p in result["changed"][:100]] + [f"Missing: {p}" for p in result["missing"][:100]]
                 + [f"Changed outside Hoard: {p}" for p in result["data_changed"]]
                 + [f"Not checked, as its drive isn't connected: {p}" for p in result.get("away", [])])
        summary = integrity_summary(result)
        if not result["complete"]:
            summary = "Stopped. " + summary
        self._set(message=summary, log=lines[-200:])
        for line in [summary] + lines:
            print(f"Check downloads: {line}", flush=True)
        return summary

    def _routine(self, stores: list[str]) -> None:
        """The routine check (issue #113), as one job: read your stores, check your downloads, check for updates,
        and then, if anything's new or updated, keep how much for the pages, which ask which of it to download.
        Nothing is downloaded here."""
        save_routine(last=time.time())
        self.state["routine"] = True
        try:
            unread = self._refresh(stores, skip_imported=True) if stores else []
            self.state["error"] = None   # a store that couldn't be read doesn't stop the rest
            if self.stop.is_set():
                self._set(message="Stopped.")
                return
            checked = self._verify(stores, fresh=True)
            if self.stop.is_set():
                return
            downloadable = [s for s in stores if s in DOWNLOADABLE and s not in unread]
            if downloadable:
                if self._download(downloadable, None, check=True) is False or self.stop.is_set():
                    return   # stopped while checking for updates: its "Stopped" stands, and nothing found is kept
            counts = self.find_choices() if self.find_choices else {"new": 0, "updates": 0}
            found = {"at": now_iso(), **counts} if counts["new"] or counts["updates"] else None
            before = routine_record()["found"] or {"new": 0, "updates": 0}
            save_routine(found=found)
            if found and self.on_found and (counts["new"] > before["new"] or counts["updates"] > before["updates"]):
                self.on_found(counts)   # (what you were told already and haven't looked at, only once)
            said = (f"Found {plural(counts['new'], 'new product')} and {plural(counts['updates'], 'update')}: "
                    "choose what to download." if found else "Nothing new to download.")
            self._set(message=f"{checked} {said}" + (f" Couldn't read {_names(unread)}: see Stores." if unread else ""),
                      partial=bool(unread), report={"routine": counts})
        finally:
            self.state["routine"] = False

    def _sync(self, stores: list[str]) -> None:
        """Sync: read what you own from each store, then download anything new, as one job."""
        self.state["sync"] = True
        _record_sync()
        try:
            unread = self._refresh(stores, skip_imported=True)
            if self.stop.is_set():
                self._set(message="Stopped. Anything half-downloaded resumes next time.")
                return
            if self.state.get("error"):   # no store could be read: downloading would only fail the same way
                return
            self._download(stores, None)
            if unread and not self.state.get("error"):
                self._set(message=f"{self.state.get('message') or ''} Couldn't read {_names(unread)}: see Stores.".strip(),
                          partial=True)
        finally:
            self.state["sync"] = False

    def cancel(self) -> bool:
        """Stop the running download (or sync) within a few seconds; a file it was part way through resumes next time
        where it can. False when neither is running."""
        if self.state["running"] and (self.state["task"] in ("download", "check-updates", "verify", "move", "routine")
                                      or self.state.get("sync") or self.state.get("routine")):
            self._set(message="Stopping")   # before the job can see Stop, so its "Stopped" is never overwritten
            self.stop.set()
            threading.Thread(target=self._force_stop, args=(self.state.get("job_id"),), daemon=True).start()
            return True
        return False

    def force_stop(self) -> bool:
        """Force stop: end the running task now, whatever it is, rather than at its next safe point. Hoard's store
        browsers, a sign-in window and a browser download are ended at once, so a task waiting on one ends straight
        away; anything else ends at its next step (a thread can't be ended from outside). What finished is kept, and
        a file part way through resumes next time where it can. False when nothing is running."""
        if not self.state["running"]:
            return False
        self._forced = True
        self._set(message="Force stopping")
        self.stop.set()
        window = self._sign_in
        if window is not None:
            window.end()
        stop_install()
        end_browsers()
        return True

    # ---- a job that doesn't stop, or doesn't move

    def _still(self, job_id) -> bool:
        return bool(self.state.get("running")) and self.state.get("job_id") == job_id

    def where(self) -> str:
        """Where the running job is, as a Python stack (Hoard's own code only: no names or addresses)."""
        frame = sys._current_frames().get(self._job_thread or -1)
        return "".join(traceback.format_stack(frame)) + _paused_in_hoard() if frame else "(not running)"

    def _force_stop(self, job_id, wait: float | None = None) -> None:
        """After Stop: a job still running FORCE_AFTER seconds later is waiting on a store browser that stopped
        answering (every other wait Hoard makes has a time limit). End that browser, so the job can finish, and say
        in Hoard's log where it was waiting."""
        deadline = time.monotonic() + (FORCE_AFTER if wait is None else wait)
        while time.monotonic() < deadline:
            if not self._still(job_id):
                return
            time.sleep(0.25)
        print(f"Stop hadn't taken effect after {FORCE_AFTER:.0f} s, so Hoard ended the store's browser. The job was "
              f"at:\n{self.where()}", flush=True)
        if end_browsers():
            self._set(message="Stopping: the store's browser had stopped answering, so Hoard closed it")

    def _watch(self, job_id, every: float = 15.0) -> None:
        """While a job runs: if it goes STUCK_AFTER seconds without a word, write where it is to Hoard's log (once),
        and say so, so a stuck job can be told apart from a slow one, and the log shows why."""
        told = False
        while self._still(job_id):
            time.sleep(every)
            quiet = time.monotonic() - self._moved
            if not told and quiet >= STUCK_AFTER and self._still(job_id):
                told = True
                last = self.state.get("message") or ""
                print(f"No progress for {quiet / 60:.0f} minutes (last: {last!r}). The job is at:\n{self.where()}", flush=True)
                self.state["message"] = (f"No progress for {quiet / 60:.0f} minutes. Stop ends it (closing the store's "
                                         f"browser if it has stopped answering). Last: {last}")[:500]

    def _download(self, stores: list[str], only: str | None, keys: list[str] | None = None, check: bool = False,
                  items: list[str] | None = None, chosen: dict | None = None) -> None:
        """Download everything new or changed from these stores (or only the products keys names), passing progress
        to the page as it goes. (Payhip is only read, so it's left out.) With check, download nothing: note what
        each product already downloaded has on its store that isn't on disk, for the Downloads page (issue #26)."""
        from types import SimpleNamespace
        from .downloader import cmd_sync, direct_targets
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
                self._moved = time.monotonic()
                self.state.update(message=str(msg), transfer=msg.transfer)
            else:
                lines.extend(line.rstrip() for line in str(msg).splitlines() if line.strip())
                del lines[:-300]
                self._set(message=lines[-1] if lines else "", log=lines[-80:], transfer=None)
            # Stop ends this job, in its own thread: a message can come from any thread that logs (anything else
            # running), and raising there would end that thread instead, and use up the Stop.
            if self.stop.is_set() and threading.get_ident() == self._job_thread:
                self.stop.clear()   # the catalog is still rebuilt on the way out
                raise Cancelled()

        args = SimpleNamespace(store="all" if set(stores) >= set(DOWNLOADABLE) else stores, dry_run=check, only=only,
                               headed=False, keys=set(keys) if keys else None,
                               skip=None if keys or items else download_skip(self.cfg),   # issue #107: chosen wins
                               targets=direct_targets(self.lib.snapshot()[0], stores, only, keys, items),
                               files={k: {"shown": set(v["shown"]), "chosen": set(v["chosen"])}
                                      for k, v in (chosen or {}).items()} or None)   # the files you chose
        try:
            with capture_log(progress):
                report = cmd_sync(self.cfg, args)
            if check:
                # a check of chosen products (by key, by library item, or by name) replaces only what an earlier
                # check found for those, and doesn't count as a check of the whole store
                narrowed = args.keys
                if not narrowed and (items or only):
                    snap = self.lib.snapshot()[0]
                    picked = [i for i in snap if (items and i.get("key") in items) or
                              (only and only.lower() in f"{i.get('name', '')} {i.get('creator', '')}".lower())]
                    narrowed = {tag_key(i["store"], i["name"]) for i in picked} or {"(none)"}
                total = AssetUpdates().record_check(report.stores_done, narrowed, report.available)
                found = len({a["key"] for a in report.available})
                missed = [STORES[s]["label"] for s in stores if s not in report.stores_done and self.cfg[s].get("enabled", True)]
                self._set(report={"updates": found, "problems": report.failed[:20], "skipped_list": report.skipped[:20]},
                          message=(f"Checked: {found} {'item has' if found == 1 else 'items have'} updates" if found
                                   else "Checked: no updates") + (f" ({total} in all)" if total != found and not keys else "")
                                  + (f". Couldn't check {', '.join(missed)}." if missed else "."))
                return
            AssetUpdates().after_download(report.got, report.failed, report.got_files)
            summary = {k: len(getattr(report, k)) for k in ("new_assets", "new_files", "updated", "skipped", "failed")}
            self._set(report={**summary, "problems": report.failed[:20], "skipped_list": report.skipped[:20]},
                      partial=bool(summary["failed"]) or None,
                      message=(f"Done: {summary['new_assets']} new, {summary['updated']} updated"
                               + (f", {summary['failed']} couldn't be downloaded" if summary["failed"] else "") + "."))
        except Cancelled:
            self._set(message="Stopped checking for updates." if check else "Stopped. Anything half-downloaded resumes next time.")
            return False   # (Stop was used up raising Cancelled: a caller carrying on after this checks for False)
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

    def _refresh(self, stores: list[str], skip_imported: bool = False) -> list[str]:
        """Read each store's purchases and save them, keeping the old list when a read fails or comes back empty.
        Returns the stores that couldn't be read. When none could, the job has failed: it says which, and why is on
        each store's row in Stores (a Sync used to say Done here)."""
        if skip_imported:
            stores = [s for s in stores if self.lib.data["stores"].get(s, {}).get("source") != "import"]
        self._set(task="refresh", message="Checking your connection")
        online = [s for s in stores if reachable(s)]
        for store in stores:
            if store not in online:
                self.lib.set_error(store, unreachable_message(store))
        if stores and not online:
            self._set(message="You're offline. Your saved library still works.",
                      error="You're offline. Your saved library still works.")
            return list(stores)
        refreshed, unread = [], [s for s in stores if s not in online]
        # itch.io is read through its API: Playwright isn't started (nor needed) when it's the only store read
        with (_playwright()() if any(s not in NO_BROWSER for s in online) else contextlib.nullcontext()) as p:
            for store in online:
                if self._forced:   # Force stop: the rest are left as they were
                    break
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
                        if not self._forced:   # (its browser was closed by Force stop: not the store's fault)
                            self.lib.set_error(store, unreachable_message(store) if is_network_error(e)
                                               else f"Couldn't read the library: {e}")
                finally:
                    if ctx:
                        ctx.close()
        unread += [s for s in online if s not in refreshed and not (s == "payhip" and not payhip_shops(self.cfg))]
        if refreshed and self.cfg.get("offline_images", True) and not self._forced:
            with self.lib.lock:
                keys = [i["key"] for i in self.lib.data["items"] if i["store"] in refreshed]
            cache_images(self.lib, keys, lambda m: self._set(message=m), stop=lambda: self._forced)
        if unread and not refreshed:
            why = f"Couldn't read {_names(unread)}. Each store's row in Stores says why."
            self._set(message=why, error=why)
        elif unread:
            self._set(message=f"Library updated, except {_names(unread)}: see Stores.", partial=True)
        else:
            self._set(message="Library updated")
        return unread

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
        if channel == "chromium" and not own_browser_installed():
            # Hoard's own browser isn't downloaded yet: download it here, as part of signing in, rather than failing
            # and sending you to Set up Hoard (a tester tried twice before finding it)
            self._install_browser(stores)
            if self.state.get("error") or self._forced:
                return
        # which browser, in the log and on screen: a chosen browser that isn't installed is stood in for by Hoard's
        # own, and that used to happen without a word (issue #20)
        print(f"Signing in to {label} with {name}" + (f" ({BROWSER_NAMES[chosen]} was chosen, and isn't installed)"
                                                     if chosen != channel else ""), flush=True)
        if not self.cfg.get("automated_sign_in"):
            self._sign_in_plainly(store, label, name)
        else:
            self._sign_in_in_hoards_window(store, label, name)
        if self._forced:   # Force stop while signing in: nothing to read
            return
        try:
            check_saved_signin(self.cfg, store)
        except SigninsUnprotected as e:
            self.lib.set_error(store, str(e))
            raise
        if store == "payhip" and not payhip_shops(self.cfg):
            # nothing to read until you've added the shops you bought from: reading Payhip straight after would only
            # fail with "add your shops", which read as the sign-in failing (a tester's report)
            self._set(task="login", store=store, message=PAYHIP_SIGNED_IN_NO_SHOPS)
            return
        self._refresh([store])

    def _sign_in_plainly(self, store: str, label: str, name: str) -> None:
        """Sign in in the browser's own window, which nothing drives, so Google (and "Sign in with Google" on a
        store), Discord and the like accept it (issue #21). Wait until it's closed."""
        with _playwright()() as p:
            window = SignInWindow(p, self.cfg, store, sign_in_urls(self.cfg, store))
        self._sign_in = window
        if self._forced:   # Force stop came while the window was opening: it closes now
            window.end()
        try:
            tabs = " (one tab per shop; sign in on each)" if store == "payhip" and len(sign_in_urls(self.cfg, store)) > 1 else ""
            close = "quit it (Command-Q)" if sys.platform == "darwin" else "close that window"
            self._set(task="login", store=store,
                      message=f"Sign in to {label} in the {name} window that opened{tabs}, then {close}.")
            while window.is_open() and not self._forced:
                if self.pending_link:   # a link you pasted from an email: open it in that window
                    link, self.pending_link = self.pending_link, None
                    window.open(link)
                    self._set(message=f"Opened the link from your email in the {label} window. Finish there, "
                                      f"then {close}.")
                time.sleep(0.5)
            if not self._forced:
                window.wait_released()
            else:   # the profile is let go only once its browser has ended, so nothing else opens it meanwhile
                for _ in range(40):
                    if not window.is_open():
                        break
                    time.sleep(0.25)
        finally:
            self._sign_in = None
            window.close()

    def _sign_in_in_hoards_window(self, store: str, label: str, name: str) -> None:
        """Sign in in a window Hoard drives (before 2.11, and with "automated_sign_in": true in config.json). Wait
        until it's closed."""
        with _playwright()() as p:
            ctx = launch(p, self.cfg, False, store)
            open_sign_in_pages(ctx, self.cfg, store)
            tabs = " (one tab per shop; sign in on each)" if store == "payhip" and len(ctx.pages) > 1 else ""
            self._set(task="login", store=store,
                      message=f"Sign in to {label} in the {name} window that opened{tabs}, then close that window.")
            while not self._forced:  # wait for the window to be closed
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
