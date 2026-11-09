"""Settings endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

from .. import server as app
from .routing import Route


def _places(self) -> list[dict]:
    """Every folder Hoard uses (places.py), Projects' too when the Creator Companion's settings can be read."""
    try:
        vpm_settings = self.server.vpm.settings()
    except app.vpm_api.ProjectsError:
        vpm_settings = None
    return app.places.places(self.server.cfg, vpm_settings)


def get_page(self, path, body, query):
    """GET /, /index.html, /downloads. the pages hold nothing private: everything they show is fetched with the access key"""
    srv = self.server
    u = app.urlparse(self.path)
    srv.last_seen = app.time.time()
    srv.accept_language = self.headers.get("Accept-Language")
    return self._send(200, app.page_source(app.PAGES[path], srv.cfg, srv.accept_language), "text/html; charset=utf-8",
                      {"Cache-Control": "no-store"})


def get_styleguide(self, path, body, query):
    """GET /styleguide. every part of the pages, for making and checking them (nothing of yours in it)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._send(200, app.guide_source(app.parse_qs(u.query)), "text/html; charset=utf-8", {"Cache-Control": "no-store"})


def get_fonts(self, path, body, query):
    """GET /fonts/*. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    font = app.font_path(app.unquote(path[len("/fonts/"):]))
    if not font:
        return self._send(404, b"Not found", "text/plain")
    return self._send(200, font.read_bytes(), "font/woff2", {"Cache-Control": "max-age=31536000, immutable"})


def get_api_credits(self, path, body, query):
    """GET /api/credits. issue #227: Acknowledgements (Settings): everything Hoard uses, with its license"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json(app.credits.view())


def get_api_credits_license(self, path, body, query):
    """GET /api/credits/license. one of them's license text, where Hoard has it"""
    srv = self.server
    u = app.urlparse(self.path)
    text = app.credits.license_text((app.parse_qs(u.query).get("name") or [""])[0][:300])
    return self._json({"text": text}) if text else self._json({"error": "Hoard has no copy of that license here: its link has it."}, 404)


def get_api_settings(self, path, body, query):
    """GET /api/settings. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json({**app.public_settings(srv.cfg), "libraries": srv.library_view()})


def get_api_folders(self, path, body, query):
    """GET /api/folders. Settings' Hoard's folders: every one it uses, where it is, and whether it's there"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json({"folders": self._places()})


def get_api_update(self, path, body, query):
    """GET /api/update. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json(srv.updates.view(srv.can_update()))


def get_api_changelog(self, path, body, query):
    """GET /api/changelog. What's new, in the app: betas too when asked for (?betas=1)"""
    srv = self.server
    u = app.urlparse(self.path)
    betas = app.parse_qs(u.query).get("betas", [""])[0] == "1"
    return self._json({"version": app.__version__, "releases": app.whats_new(betas)}, compress=True)


def get_api_setup(self, path, body, query):
    """GET /api/setup. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json({**app.setup_status(srv.cfg), "job": app.public_job(srv.jobs.state, self._hidden_names()),
                       "close_to_taskbar": bool(srv.cfg.get("close_to_taskbar", True)),
                       # issue #288: its notifications step (the addresses described, as Settings has them)
                       "apprise": {"available": app.alerts.available(), "addresses": app.alerts.described(srv.cfg),
                                   "events": sorted(app.alerts.chosen(srv.cfg))}})


def post_api_enter(self, path, body, query):
    """POST /api/enter. a page Hoard opened with a one-time link, trading it for the access key"""
    srv = self.server
    u = app.urlparse(self.path)
    if not srv.use_entry(body.get("token")):
        return self._json({"error": "That link to Hoard was already used or is too old. Open Hoard again."}, 403)
    return self._json({"ok": True, "key": srv.key})


def post_api_settings(self, path, body, query):
    """POST /api/settings. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    busy = [k for k in app.JOB_SETTINGS if k in body]
    if srv.jobs.state["running"] and busy:
        return self._json({"error": "That setting can't change while Hoard is refreshing or downloading. It's "
                                    "put back: change it again once the current job has finished.",
                           "settings": app.public_settings(srv.cfg)}, 409)
    try:
        change = app.apply_settings(srv.cfg, body)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    app.deep_merge(srv.cfg, change)
    app.apply_store_sites(srv.cfg)   # added or removed Payhip shops count (or stop counting) straight away
    app.previous.set_keep(app.keep_previous(srv.cfg))
    srv.save_settings()
    srv.forget_index()
    return self._json({"ok": True, "settings": {**app.public_settings(srv.cfg), "libraries": srv.library_view()}})


def post_api_diagnostics_open_folder(self, path, body, query):
    """POST /api/diagnostics/open-folder. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    try:
        folder = app.diagnostics.support_report_dir()
        folder.mkdir(parents=True, exist_ok=True)
        return self._json({"ok": True, "opened_in": app.reveal(folder), "folder": str(folder)})
    except OSError as e:
        return self._json({"error": str(e)}, 500)


def post_api_diagnostics_report(self, path, body, query):
    """POST /api/diagnostics/report. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    try:
        result = app.diagnostics.create_support_report(srv.cfg, srv.lib, srv.jobs.state, str(body.get("notes") or "")[:6000], body.get("context"))
    except Exception as e:
        app.diagnostics.record_exception(e, area="support-report", task="create-report")
        return self._json({"error": "Hoard couldn't save the support report. Make sure your Documents folder is writable, then try again."}, 500)
    try:
        result["opened_in"] = app.reveal(app.Path(result["path"]))
    except OSError:
        # The ZIP is already safely written; failure to open Explorer must not make the report look failed.
        result["opened_in"] = None
    return self._json(result)


def post_api_backup_make(self, path, body, query):
    """POST /api/backup/make. Settings, Backup (hoard/backup.py)"""
    srv = self.server
    u = app.urlparse(self.path)
    with srv.cfg_lock:
        doc = app.backup.make(srv.cfg, app.public_settings(srv.cfg), srv.lib, self._unlocked())
    try:
        where = app.backup.save(doc)
    except OSError as e:
        return self._json({"error": f"The backup couldn't be saved ({e.strerror or e})."}, 500)
    return self._json({"ok": True, "path": str(where), "hidden": "hidden" in doc["marks"],
                       "pin_set": bool(app.MarkStore().view()["pin"])})


def post_api_backup_show(self, path, body, query):
    """POST /api/backup/show. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    app.backup.backups_dir().mkdir(parents=True, exist_ok=True)
    try:
        return self._json({"ok": True, "opened_in": app.reveal(app.backup.backups_dir())})
    except OSError as e:
        return self._json({"error": str(e)}, 500)


def post_api_backup_check(self, path, body, query):
    """POST /api/backup/check, /api/backup/restore. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    try:
        doc = app.backup.read(str(body.get("content") or ""))
    except app.backup.BackupError as e:
        return self._json({"error": str(e)}, 400)
    if path == "/api/backup/check":
        return self._json({"ok": True, **app.backup.summary(doc)})
    if srv.jobs.state.get("running") or srv.jobs.state.get("queue"):
        return self._json({"error": "Wait for Hoard to finish what it's doing, then try again."}, 409)
    replaces_hidden = isinstance((doc.get("marks") or {}).get("pin"), dict) if isinstance(doc.get("marks"), dict) else False
    if replaces_hidden and app.MarkStore().view()["pin"] and not self._unlocked():
        return self._json({"error": "This backup has hidden items, which take the place of yours: unlock your "
                                    "hidden library first, then restore it."}, 409)
    try:   # how things are now, kept first, so a restore can be undone
        with srv.cfg_lock:
            before = app.backup.save(app.backup.make(srv.cfg, app.public_settings(srv.cfg), srv.lib, self._unlocked()),
                                 label=" (before restoring)")
    except OSError as e:
        return self._json({"error": f"A backup of how things are now couldn't be saved first ({e.strerror or e}), "
                                    "so nothing was restored."}, 500)

    def add_folder(value: str) -> None:
        """Add a library folder from the backup, checked as one added in Settings is."""
        folder = str(app.libraries.check_new_folder(srv.cfg, value))
        srv.cfg["library_folders"] = [str(f) for f in app.libraries.other_folders(srv.cfg)] + [folder]
    dropped = []
    with srv.cfg_lock:
        done = app.backup.restore(doc, srv.cfg, srv.lib, app.apply_settings, add_folder, dropped.append)
        app.apply_store_sites(srv.cfg)
        app.previous.set_keep(app.keep_previous(srv.cfg))
    if dropped:   # sets the backup doesn't have: their short links go too (else they'd run out by themselves)
        srv.start_worker("Forgetting old share links", app.forget_short_links, dropped)
    srv.save_settings()
    srv.forget_index()
    srv.start_worker("Updating Unity catalog", app.rebuild_catalog_quietly, srv)
    return self._json({"ok": True, **done, "before": str(before)})


def post_api_folders_open(self, path, body, query):
    """POST /api/folders/open. one of Settings' Hoard's folders, by its name: never a path the page sends"""
    srv = self.server
    u = app.urlparse(self.path)
    found = app.places.find(self._places(), body.get("id"))
    if found is None:
        return self._json({"error": "That isn't one of Hoard's folders."}, 400)
    folder = app.Path(found["path"])
    try:
        if found["id"] in app.places.OWN:
            folder.mkdir(parents=True, exist_ok=True)
        elif not folder.is_dir():
            return self._json({"error": "That folder isn't there yet."}, 404)
        return self._json({"ok": True, "opened_in": app.reveal(folder)})
    except OSError as e:
        return self._json({"error": f"It didn't open ({e.strerror or e})."}, 500)


def post_api_update_check(self, path, body, query):
    """POST /api/update/check. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    try:
        srv.updates.check()
    except Exception as e:
        if app.blocked_here(e):
            return self._json({"error": "Couldn't check for updates. " + app.blocked_message("GitHub")}, 502)
        why = "you're offline, or GitHub can't be reached" if app.is_network_error(e) else str(e)[:200]
        return self._json({"error": f"Couldn't check for updates: {why}."}, 502)
    return self._json({"ok": True, **srv.updates.view(srv.can_update())})


def post_api_update_install(self, path, body, query):
    """POST /api/update/install. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    if not srv.can_update():
        return self._json({"error": "This copy of Hoard can't update itself. Download the new version from "
                                    "the releases page."}, 409)
    if srv.jobs.state["running"]:
        return self._json({"error": "Wait for the current job to finish (or stop it), then update."}, 409)
    why = srv.updates.start_install(srv.quit_app)
    return self._json({"error": why}, 409) if why else self._json({"ok": True}, 202)


def post_api_pick(self, path, body, query):
    """POST /api/pick. Browse: the system's own picker, in Hoard's window (never in a web browser)"""
    srv = self.server
    u = app.urlparse(self.path)
    if not srv.pick_path:
        return self._json({"error": "Choosing a folder needs Hoard's own window. Type the path instead."}, 409)
    kind = "file" if body.get("kind") == "file" else "folder"
    if not srv.picking.acquire(blocking=False):   # one picker at a time, over the window
        return self._json({"error": "A picker is already open."}, 409)
    # It opens in the downloads folder, or Projects' projects or backups folder: Hoard's own settings, never a
    # path the request names
    start = app.root_dir(srv.cfg)
    try:
        if body.get("start") == "projects":
            start = app.Path(srv.vpm.settings().default_project_path() or start)
        elif body.get("start") == "backups":
            start = srv.vpm.backups_folder()
    except app.vpm_api.ProjectsError:
        pass
    try:
        chosen = srv.pick_path(kind, str(start) if start.is_dir() else str(app.Path.home()))
    except Exception as e:   # the window went away, or the system has no picker
        return self._json({"error": f"The picker couldn't open ({type(e).__name__}). Type the path instead."}, 500)
    finally:
        srv.picking.release()
    return self._json({"ok": True, "path": chosen})


def post_api_apprise(self, path, body, query):
    """POST /api/apprise. issues #230, #287: Apprise's addresses, kept as API keys are, one at a time"""
    srv = self.server
    u = app.urlparse(self.path)
    try:   # (add, replace or remove one; forget forgets them all; the page only ever sees them described)
        if body.get("forget") is True:
            app.alerts.save_urls(srv.cfg, [])
        elif body.get("action") in ("add", "replace", "remove"):
            app.alerts.change(srv.cfg, body["action"], str(body.get("id") or ""), body.get("urls"))
        else:
            addresses = app.alerts.clean_urls(body.get("urls"))
            if not addresses:
                raise ValueError("Type an address first, one a line.")
            app.alerts.save_urls(srv.cfg, addresses)
    except (ValueError, app.SigninsUnprotected) as e:
        return self._json({"error": str(e)}, 400)
    except OSError as e:
        return self._json({"error": f"They couldn't be kept: {e}"}, 500)
    shown = app.alerts.described(srv.cfg)
    return self._json({"ok": True, "kept": len(shown), "addresses": shown})


def post_api_apprise_test(self, path, body, query):
    """POST /api/apprise/test. a test notification, now: to one address (its id), or to every one kept"""
    srv = self.server
    u = app.urlparse(self.path)
    if not app.alerts.available():
        return self._json({"error": "Apprise isn't installed. Run Setup again to install it."}, 400)
    addresses = app.alerts.by_id(srv.cfg, str(body.get("id"))) if body.get("id") else app.alerts.urls(srv.cfg)
    if not addresses:
        return self._json({"error": "Add an Apprise address first." if not body.get("id") else "That address isn't kept any more."}, 400)
    problem = app.alerts.deliver(addresses, "This is a test from **Hoard**: notifications through Apprise work.",
                             title="A test from Hoard", link=app.alerts.HOARD_URL)
    return self._json({"ok": problem is None, "error": problem})


def post_api_show(self, path, body, query):
    """POST /api/show. a second copy of Hoard, asking this one to come to the front"""
    srv = self.server
    u = app.urlparse(self.path)
    if not app.token_matches(body.get("token"), srv.show_token) or not srv.show_window:
        return self._json({"error": "No."}, 403)
    srv.show_window()
    return self._json({"ok": True})


def post_api_quit(self, path, body, query):
    """POST /api/quit. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    if not srv.quit_app:
        return self._json({"error": "Hoard is running as a server; stop it where it was started."}, 409)
    if srv.working() and not body.get("anyway"):
        return self._json({"busy": True, "error": "Hoard is still working."}, 409)   # the page asks what to do
    app.threading.Timer(0.3, srv.quit_app).start()   # after this answer is on its way
    return self._json({"ok": True})


def post_api_app_close(self, path, body, query):
    """POST /api/app/close. what to do about closing while something runs (the page asked you)"""
    srv = self.server
    u = app.urlparse(self.path)
    from ..app import quit_now, quit_when_done
    how = body.get("how")
    if not srv.quit_app:
        return self._json({"error": "Hoard is running as a server; stop it where it was started."}, 409)
    if how == "background":
        if not srv.hide_window:
            return self._json({"error": "Hoard carries on in the background only in its own window."}, 409)
        app.threading.Timer(0.3, srv.hide_window).start()
    elif how == "wait":
        app.threading.Thread(target=quit_when_done, args=(srv,), daemon=True).start()
    elif how == "now":
        app.threading.Timer(0.3, quit_now, args=(srv,)).start()
    else:
        return self._json({"error": "Unknown choice."}, 400)
    return self._json({"ok": True})


def post_api_setup_done(self, path, body, query):
    """POST /api/setup/done. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    srv.cfg["setup_done"] = bool(body.get("done", True))
    srv.save_settings()
    return self._json({"ok": True})


def post_api_setup_migrate(self, path, body, query):
    """POST /api/setup/migrate. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    if srv.jobs.state["running"]:   # it can change the downloads folder, which a running job is writing to
        return self._json({"error": "Wait for Hoard to finish what it's doing (or stop it), then bring your "
                                    "library over."}, 409)
    folder = str(body.get("folder") or "").strip().strip('"')[:1000]
    if not folder or not app.Path(folder).expanduser().is_absolute():
        return self._json({"error": "Enter the full path of the folder you ran Hoard 1.x from."}, 400)
    said = app.migrate_from(srv.cfg, app.Path(folder), srv.config_path, srv.lib)
    srv.forget_index()
    return self._json({"ok": True, "message": said})



METHODS = {'_places': _places}

ROUTES = [
    Route('GET', '/', get_page, changes=False, auth='public', image_key=False, max_body=1048576, request=(), response='text/html'),
    Route('GET', '/index.html', get_page, changes=False, auth='public', image_key=False, max_body=1048576, request=(), response='text/html'),
    Route('GET', '/downloads', get_page, changes=False, auth='public', image_key=False, max_body=1048576, request=(), response='text/html'),
    Route('GET', '/styleguide', get_styleguide, changes=False, auth='public', image_key=False, max_body=1048576, request=(), response='text/html'),
    Route('GET', '/fonts/*', get_fonts, changes=False, auth='public', image_key=False, max_body=1048576, request=(), response='font/woff2'),
    Route('GET', '/api/credits', get_api_credits, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/credits/license', get_api_credits_license, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/settings', get_api_settings, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/folders', get_api_folders, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/update', get_api_update, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/changelog', get_api_changelog, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/setup', get_api_setup, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/enter', post_api_enter, changes=False, auth='entry', image_key=False, max_body=1048576, request=(('token', 'string'),), response='object'),
    Route('POST', '/api/settings', post_api_settings, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/diagnostics/open-folder', post_api_diagnostics_open_folder, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/diagnostics/report', post_api_diagnostics_report, changes=True, auth='key', image_key=False, max_body=1048576, request=(('context', 'string'), ('notes', 'string')), response='object'),
    Route('POST', '/api/backup/make', post_api_backup_make, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/backup/show', post_api_backup_show, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/backup/check', post_api_backup_check, changes=False, auth='key', image_key=False, max_body=83886080, request=(('content', 'string'),), response='object'),
    Route('POST', '/api/backup/restore', post_api_backup_check, changes=True, auth='key', image_key=False, max_body=83886080, request=(('content', 'string'),), response='object'),
    Route('POST', '/api/folders/open', post_api_folders_open, changes=True, auth='key', image_key=False, max_body=1048576, request=(('id', 'string'),), response='object'),
    Route('POST', '/api/update/check', post_api_update_check, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/update/install', post_api_update_install, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/pick', post_api_pick, changes=True, auth='key', image_key=False, max_body=1048576, request=(('kind', 'any'), ('start', 'any')), response='object'),
    Route('POST', '/api/apprise', post_api_apprise, changes=True, auth='key', image_key=False, max_body=1048576, request=(('action', 'string'), ('forget', 'boolean'), ('id', 'string'), ('urls', 'any')), response='object'),
    Route('POST', '/api/apprise/test', post_api_apprise_test, changes=True, auth='key', image_key=False, max_body=1048576, request=(('id', 'string'),), response='object'),
    Route('POST', '/api/show', post_api_show, changes=False, auth='instance', image_key=False, max_body=1048576, request=(('token', 'string'),), response='object'),
    Route('POST', '/api/quit', post_api_quit, changes=True, auth='key', image_key=False, max_body=1048576, request=(('anyway', 'boolean'),), response='object'),
    Route('POST', '/api/app/close', post_api_app_close, changes=True, auth='key', image_key=False, max_body=1048576, request=(('how', 'string'),), response='object'),
    Route('POST', '/api/setup/done', post_api_setup_done, changes=True, auth='key', image_key=False, max_body=1048576, request=(('done', 'boolean'),), response='object'),
    Route('POST', '/api/setup/migrate', post_api_setup_migrate, changes=True, auth='key', image_key=False, max_body=1048576, request=(('folder', 'string'),), response='object'),
]
