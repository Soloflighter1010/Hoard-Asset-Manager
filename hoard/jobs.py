"""Work Hoard does in the background, one job at a time: refreshing, signing in and out, and downloading."""
from __future__ import annotations

import threading

from .browser import Blocked, LEGACY_PROFILE, ProfileBusy, SigninsUnprotected, _playwright, _remove_tree, check_saved_signin, launch, sign_out, signins_root
from .safety import store_link
from .setup import browser_problem, install_browser
from .common import Cancelled, NotLoggedIn, capture_log
from .config import payhip_shops
from .library import DOWNLOADABLE, FETCHERS, IMPORTABLE, PAYHIP_NO_SHOPS, Library, STORES, cache_images, open_sign_in_pages, unreachable_message
from .net import is_network_error, reachable


# ----------------------------------------------------------------------------- background jobs

class Jobs:
    """One browser job at a time: refreshing stores, or waiting for you to sign in."""

    def __init__(self, cfg: dict, lib: Library, on_download_done=None):
        """No job is running at first. on_download_done is called after every download job."""
        self.cfg, self.lib = cfg, lib
        self.on_download_done = on_download_done or (lambda: None)
        self.busy = threading.Lock()
        self.stop = threading.Event()
        self.pending_link: str | None = None   # a sign-in link from an email, for the open sign-in window
        self.state = {"running": False, "task": None, "store": None, "message": "", "error": None,
                      "log": [], "report": None, "sync": False}

    def _set(self, **kw):
        """Update the job state the page polls."""
        self.state.update(kw)

    def start(self, task: str, stores: list[str], skip_imported: bool = False, only: str | None = None) -> bool:
        """Start a job in the background. False when one is already running."""
        if not self.busy.acquire(blocking=False):
            return False
        self.stop.clear()
        self.state.update(error=None, log=[], report=None)
        if task == "download":
            target = lambda s: self._download(s, only)  # noqa: E731
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
        threading.Thread(target=self._wrap, args=(target, stores), daemon=True).start()
        return True

    def _wrap(self, fn, stores):
        """Run a job, recording any error for the page, and always free the runner afterwards."""
        try:
            self._set(running=True)
            fn(stores)
        except (ProfileBusy, SigninsUnprotected) as e:
            self._set(message=str(e), error=str(e))
        except Exception as e:
            why = browser_problem(e) or f"Stopped: {e}"
            self._set(message=why, error=why)
        finally:
            self._set(running=False, task=None, store=None)
            self.busy.release()

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
            self._set(message=why, error=why)
            return
        self._set(message="Hoard's browser is installed.")

    def _sync(self, stores: list[str]) -> None:
        """Sync: read what you own from each store, then download anything new, as one job."""
        self.state["sync"] = True
        try:
            self._refresh(stores, skip_imported=True)
            if self.stop.is_set():
                self._set(message="Stopped. Anything half-downloaded resumes next time.")
                return
            self._download(stores, None)
        finally:
            self.state["sync"] = False

    def cancel(self) -> bool:
        """Stop the running download (or sync) after the file it's on. False when neither is running."""
        if self.state["running"] and (self.state["task"] == "download" or self.state.get("sync")):
            self.stop.set()
            self._set(message="Stopping after the current file")
            return True
        return False

    def _download(self, stores: list[str], only: str | None) -> None:
        """Download everything new or changed from these stores, passing progress to the page as it goes. (Payhip is
        only read, so it's left out.)"""
        from types import SimpleNamespace
        from .downloader import cmd_sync
        stores = [s for s in stores if s in DOWNLOADABLE]
        if not stores:
            self._set(task="download", message="Nothing to download: Hoard lists what you own on Payhip, and you "
                                                "download it from Payhip yourself.")
            self.on_download_done()
            return
        self._set(task="download", store=stores[0] if len(stores) == 1 else None, message="Starting")
        lines: list[str] = []

        def progress(msg):
            lines.extend(line.rstrip() for line in str(msg).splitlines() if line.strip())
            del lines[:-300]
            self._set(message=lines[-1] if lines else "", log=lines[-80:])
            if self.stop.is_set():
                self.stop.clear()   # the catalog is still rebuilt on the way out
                raise Cancelled()

        args = SimpleNamespace(store="all" if set(stores) >= set(DOWNLOADABLE) else stores, dry_run=False, only=only,
                               headed=False)
        try:
            with capture_log(progress):
                report = cmd_sync(self.cfg, args)
            summary = {k: len(getattr(report, k)) for k in ("new_assets", "new_files", "updated", "skipped", "failed")}
            self._set(report={**summary, "problems": report.failed[:20], "skipped_list": report.skipped[:20]},
                      message=(f"Done: {summary['new_assets']} new, {summary['updated']} updated"
                               + (f", {summary['failed']} couldn't be downloaded" if summary["failed"] else "") + "."))
        except Cancelled:
            self._set(message="Stopped. Anything half-downloaded resumes next time.")
        finally:
            self.on_download_done()

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
                    # window you can complete its check in
                    ctx = launch(p, self.cfg, not (store == "payhip" and self.cfg["payhip"].get("headed", True)), store)
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
                    except NotLoggedIn:
                        self.lib.set_error(store, "Not signed in. Choose Sign in, then close the browser window when you're done.")
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
        if not reachable(store):
            self.lib.set_error(store, unreachable_message(store, "opened for signing in"))
            self._set(message=f"Couldn't reach {label}.", error=unreachable_message(store, "opened for signing in"))
            return
        with _playwright()() as p:
            ctx = launch(p, self.cfg, False, store)
            open_sign_in_pages(ctx, self.cfg, store)
            tabs = " (one tab per shop; sign in on each)" if store == "payhip" and len(ctx.pages) > 1 else ""
            self._set(task="login", store=store,
                      message=f"Sign in to {label} in the browser window that opened{tabs}, then close that window.")
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
