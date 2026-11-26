"""Local endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

from .. import server as app
from .routing import Route


def _konoasset(self, path: str, body: dict):
    """A KonoAsset library: what bringing it in would do (changing nothing), then bringing it in, as a task."""
    from .. import konoasset
    srv = self.server
    try:
        folder = konoasset.check_folder(str(body.get("path") or "")[:1000])
        if path == "/api/konoasset/preview":
            return self._json(konoasset.summary(konoasset.plan(folder, srv.lib.snapshot()[0])))
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    if path != "/api/konoasset/bring-in" or body.get("confirm") is not True:
        return self._json({"error": "Unknown request."}, 404)
    started = srv.jobs.start("konoasset", [], local={"path": str(folder)})
    if not started:
        return self._json({"error": "That's already waiting its turn."}, 409)
    return self._json({"ok": True, "queued": started == "queued"})


def _bblm(self, path: str, body: dict):
    """A BB's Library Manager library (issue #416): what bringing it in would do (changing nothing), then bringing it
    in, as a task."""
    from .. import bblm
    srv = self.server
    try:
        folder = bblm.check_folder(str(body.get("path") or "")[:1000])
        if path == "/api/bblm/preview":
            return self._json(bblm.summary(bblm.plan(folder, srv.lib.snapshot()[0], app.root_dir(srv.cfg))))
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    if path != "/api/bblm/bring-in" or body.get("confirm") is not True:
        return self._json({"error": "Unknown request."}, 404)
    started = srv.jobs.start("bblm", [], local={"path": str(folder)})
    if not started:
        return self._json({"error": "That's already waiting its turn."}, 409)
    return self._json({"ok": True, "queued": started == "queued"})


# Local's tasks that change its records: Edit... and Fill in wait for them (and for its records, local.WRITING).
LOCAL_TASKS = ("add-local", "rescan-local", "remove-local", "move", "konoasset", "bblm", "verify", "delete-files")


def _local_busy(srv) -> bool:
    """Whether one of Local's tasks is running, in either lane (Local's tasks can run in the side lane: issue #403)."""
    return any(j.state["running"] and j.state.get("task") in LOCAL_TASKS for j in (srv.jobs, srv.side_jobs))


def _edit(srv, path: str, found: tuple, body: dict) -> tuple[dict, int]:
    """Edit... (its name, creator, note and page on a store) and Fill in from its page, for a Local product (issue
    #416): each changes its record only while nothing else is changing Local's (local.WRITING), and says so when
    something is. Fill in reads its page first, as anyone sees it (nothing of yours is sent)."""
    from .. import local
    wait = ({"error": "Wait for Hoard to finish with Local, then try again."}, 409)
    if _local_busy(srv):
        return wait
    got = None
    if path == "/api/local/from-page":
        if not found[1].get("page"):
            return {"error": "Give it its page on a store first, with Edit..."}, 400
        try:
            got = app.wishlists.from_product_page(found[1]["page"], app.read_store_page)
        except app.wishlists.PageRefused:   # (Payhip's, behind Cloudflare: read in Hoard's browser, as a task, #387)
            job = srv.jobs.start("links", list(app.wishlists.BROWSER_READ[:1]),
                                 local={"fill": str(body.get("folder") or "")[:1000], "links": [found[1]["page"]]})
            if not job:
                return {"error": "Hoard has too much waiting to read it in its browser now: try again later."}, 409
            return {"ok": True, "browser": True, "queued": job == "queued"}, 200
        except app.wishlists.LinkError as e:   # (its reason, as a sentence the translations have)
            return {"error": f"{str(e)[:1].upper()}{str(e)[1:]}."}, 400
        if not got:
            return {"error": "Its page doesn't say what it is."}, 400
    if _local_busy(srv) or not local.WRITING.acquire(timeout=2):   # (read again after the page: a task may have begun)
        return wait
    try:
        if got is not None:
            done = local.fill_from_page(srv.cfg, app.root_dir(srv.cfg), found[0], got)
        else:
            given = {k: str(body[k])[:2000] for k in ("name", "creator", "note", "link") if isinstance(body.get(k), str)}
            rec = local.edit(srv.cfg, app.root_dir(srv.cfg), found[0], **given)
            done = {"name": rec["name"], "creator": rec["creator"], "note": rec.get("note"), "link": rec.get("page")}
    except ValueError as e:
        return {"error": str(e)}, 400
    finally:
        local.WRITING.release()
    srv.forget_index()
    return {"ok": True, **done}, 200


def _local(self, path: str, body: dict):
    """Local: add a folder or file of your own (a task, since copying can take a while), rescan one listed where
    it is, or take one out."""
    from .. import local
    srv = self.server
    if path == "/api/local/preview":   # issue #109: the packages a folder of folders would add
        try:
            plan = local.split(app.root_dir(srv.cfg), str(body.get("path") or "")[:1000], body.get("depth"),
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
                local.split(app.root_dir(srv.cfg), what["path"], depth, copy)
            else:
                local.check_source(app.root_dir(srv.cfg), what["path"], copy)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        if srv.cfg.get("local_copy", True) != copy:   # the choice you made last time is offered next time
            srv.cfg["local_copy"] = copy
            srv.save_settings()
        started = srv.jobs.start("add-local", [], local=what)
        if not started:
            return self._json({"error": "That's already waiting its turn."}, 409)
        return self._json({"ok": True, "queued": started == "queued"})
    found = local.by_folder(app.root_dir(srv.cfg), str(body.get("folder") or "")[:1000])
    if not found:
        return self._json({"error": "That isn't in Local any more."}, 404)
    if path == "/api/local/picture":   # a picture of your choosing for its tile, or back to one of its own
        if any(j.state["running"] and j.state.get("task") in ("add-local", "rescan-local", "remove-local", "move")
               for j in (srv.jobs, srv.side_jobs)):   # (Local's tasks can run in the side lane: issue #403)
            return self._json({"error": "Wait for Hoard to finish with Local, then try again."}, 409)
        try:
            local.choose_picture(srv.cfg, app.root_dir(srv.cfg), found[0], body.get("image"))
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except OSError as e:
            return self._json({"error": f"Couldn't save the picture: {e.strerror or e}."}, 500)
        srv.forget_index()
        return self._json({"ok": True})
    if path in ("/api/local/edit", "/api/local/from-page"):   # its name, creator, note and store page (issue #416)
        return self._json(*_edit(srv, path, found, body))
    if path == "/api/local/unitypackage":   # a Unity package of it, made without Unity (issue #382)
        return self._json(*_unitypackage(srv, found[1]))
    if path == "/api/local/remove" and body.get("confirm") is not True:
        return self._json({"error": "Confirm first."}, 400)
    if not srv.jobs.busy.acquire(blocking=False):   # a job is running: this waits its turn after it
        task = "rescan-local" if path == "/api/local/rescan" else "remove-local"
        return self._queued(srv.jobs.start(task, [], files={"folder": str(body.get("folder"))[:1000],
                                                            "name": found[1].get("name")}))
    try:
        if path == "/api/local/rescan":
            rec = local.rescan(srv.cfg, app.root_dir(srv.cfg), found[0])
            done = {"files": len(rec["files"])}
        else:
            done = local.remove(srv.cfg, app.root_dir(srv.cfg), found[0])
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    finally:
        srv.jobs.busy.release()
        srv.jobs.kick()
    srv.forget_index()
    return self._json({"ok": True, **done})


def post_api_local_sync(self, path, body, query):
    """POST /api/local/sync {folder ("" turns it off), look, explorer}. Issue #388: the Local sync folder, checked (on
    this computer, answering, not inside a library folder); look: look at it now; explorer: show it in File Explorer
    (issue #410: its icon, and Hoard in the right-click menu). What it holds and skipped, as view(), and explorer:
    whether that's on, can be here (Windows), and what's in place."""
    from .. import explorer, localsync
    srv = self.server
    was = str(srv.cfg.get("local_sync") or "")
    if "folder" in body:
        value = str(body.get("folder") or "").strip()[:1000]
        try:
            srv.cfg["local_sync"] = str(localsync.check_folder(srv.cfg, value)) if value else ""
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        srv.save_settings()
    if isinstance(body.get("explorer"), bool):
        srv.cfg["explorer"] = body["explorer"]
        srv.save_settings()
    if "folder" in body or "explorer" in body:
        srv.apply_explorer(was)
    shown = {"explorer": {"here": explorer.here(), "on": explorer.on(srv.cfg), **srv.explorer_state}}
    if body.get("look") is True and not app.feature_on(srv.cfg, "local"):   # (turned off in Settings, Features: #422)
        return self._json({"error": "Local is turned off in Settings, Features."}, 409)
    if srv.cfg.get("local_sync") and (body.get("look") is True or "folder" in body):
        if localsync.tick(srv) is None:
            return self._json({"ok": True, "busy": True, **localsync.view(srv.cfg), **shown})
    return self._json({"ok": True, **localsync.view(srv.cfg), **shown})


MAX_PACKAGE_BYTES = 2 << 30   # a Local item bigger than this isn't packed by Hoard: export it from Unity (issue #382)


def _unitypackage(srv, rec: dict) -> tuple[dict, int]:
    """Issue #382: a .unitypackage of a Local item, made without Unity, in "Unity packages" in the folder for editable
    copies (named after it, "Name (2)" beside one already there), then shown in its folder. (answer, status)."""
    from .. import local, makepackage, reach
    from ..downloader import edits_root, record_folder
    from ..safety import UnsafePath
    root = app.root_dir(srv.cfg)
    if rec.get("location") and reach.is_away(rec["location"]):
        return {"error": f"Its folder is on a drive that isn't connected now: {rec['location']}"}, 409
    try:
        folder = record_folder(local.local_dir(root), rec)
    except UnsafePath:
        return {"error": "Its folder can't be used any more."}, 400
    files = [f["path"] for f in (rec.get("files") or {}).values() if isinstance(f, dict) and isinstance(f.get("path"), str)]
    if sum(int(f.get("size") or 0) for f in (rec.get("files") or {}).values() if isinstance(f, dict)) > MAX_PACKAGE_BYTES:
        return {"error": "It's over 2 GB, too big for a package Hoard makes: export it from Unity instead."}, 400
    if not folder.is_dir() or not files:
        return {"error": "There's nothing in it to put in a package."}, 400
    try:
        out_dir = edits_root(srv.cfg, root) / "Unity packages"
    except ValueError as e:   # (the folder for editable copies is inside a library: Settings says so)
        return {"error": str(e)}, 400
    base = makepackage.folder_name(rec.get("name") or folder.name)
    out = out_dir / f"{base}.unitypackage"
    for n in range(2, 1000):
        if not out.exists():
            break
        out = out_dir / f"{base} ({n}).unitypackage"
    try:
        done = makepackage.make(folder, files, rec.get("name") or folder.name, out)
    except ValueError as e:
        return {"error": str(e)}, 400
    except OSError as e:
        return {"error": f"The package couldn't be written: {e.strerror or e}."}, 500
    try:
        app.reveal(out)
    except OSError:
        pass   # (it's made: the answer says where)
    return {"ok": True, **done, "new_ids": len(done["new_ids"]),
            "left_out": [{"path": p, "why": why} for p, why in done["left_out"][:50]]}, 200


def post_api_local_add(self, path, body, query):
    """POST /api/local/add, /api/local/rescan, /api/local/remove, /api/local/preview, /api/local/unitypackage, /api/local/picture. your own packages (issue #80)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._local(path, body)


def post_api_bblm_preview(self, path, body, query):
    """POST /api/bblm/preview, /api/bblm/bring-in. a BB's Library Manager library, brought in (issue #416)"""
    return self._bblm(path, body)


def post_api_konoasset_preview(self, path, body, query):
    """POST /api/konoasset/preview, /api/konoasset/bring-in. a KonoAsset library, brought in (issue #305)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._konoasset(path, body)



METHODS = {'_bblm': _bblm, '_konoasset': _konoasset, '_local': _local}

ROUTES = [
    Route('POST', '/api/local/add', post_api_local_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/local/rescan', post_api_local_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/local/remove', post_api_local_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/local/preview', post_api_local_add, changes=False, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/local/sync', post_api_local_sync, changes=True, auth='key', image_key=False, max_body=1048576, request=(('explorer', 'boolean'), ('folder', 'string'), ('look', 'boolean')), response='object'),
    Route('POST', '/api/local/unitypackage', post_api_local_add, changes=False, auth='key', image_key=False, max_body=1048576, request=(('folder', 'string'),), response='object'),
    Route('POST', '/api/local/edit', post_api_local_add, changes=True, auth='key', image_key=False, max_body=65536, request=(('creator', 'any'), ('folder', 'string'), ('link', 'any'), ('name', 'any'), ('note', 'any')), response='object'),
    Route('POST', '/api/local/from-page', post_api_local_add, changes=True, auth='key', image_key=False, max_body=65536, request=(('folder', 'string'),), response='object'),
    Route('POST', '/api/local/picture', post_api_local_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/bblm/preview', post_api_bblm_preview, changes=False, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('path', 'string')), response='object'),
    Route('POST', '/api/bblm/bring-in', post_api_bblm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('path', 'string')), response='object'),
    Route('POST', '/api/konoasset/preview', post_api_konoasset_preview, changes=False, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('path', 'string')), response='object'),
    Route('POST', '/api/konoasset/bring-in', post_api_konoasset_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('path', 'string')), response='object'),
]
