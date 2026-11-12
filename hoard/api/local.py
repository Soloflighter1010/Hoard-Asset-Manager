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
        if srv.jobs.state["running"] and srv.jobs.state.get("task") in ("add-local", "rescan-local", "remove-local",
                                                                        "move"):
            return self._json({"error": "Wait for Hoard to finish with Local, then try again."}, 409)
        try:
            local.choose_picture(srv.cfg, app.root_dir(srv.cfg), found[0], body.get("image"))
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


def post_api_local_add(self, path, body, query):
    """POST /api/local/add, /api/local/rescan, /api/local/remove, /api/local/preview, /api/local/picture. your own packages (issue #80)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._local(path, body)


def post_api_konoasset_preview(self, path, body, query):
    """POST /api/konoasset/preview, /api/konoasset/bring-in. a KonoAsset library, brought in (issue #305)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._konoasset(path, body)



METHODS = {'_konoasset': _konoasset, '_local': _local}

ROUTES = [
    Route('POST', '/api/local/add', post_api_local_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/local/rescan', post_api_local_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/local/remove', post_api_local_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/local/preview', post_api_local_add, changes=False, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/local/picture', post_api_local_add, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('copy', 'any'), ('creator', 'any'), ('depth', 'any'), ('folder', 'string'), ('image', 'any'), ('name', 'string'), ('note', 'any'), ('path', 'string')), response='object'),
    Route('POST', '/api/konoasset/preview', post_api_konoasset_preview, changes=False, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('path', 'string')), response='object'),
    Route('POST', '/api/konoasset/bring-in', post_api_konoasset_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('path', 'string')), response='object'),
]
