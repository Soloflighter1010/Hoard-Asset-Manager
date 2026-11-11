"""Downloads endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

from .. import server as app
from .routing import Route


def _product_files(self, body: dict) -> dict:
    """Issue #225: what each of these products has on its store, as a quick look at it read it (no file is
    downloaded), each with the files your rules or an earlier choice leave out ("out"), for Hoard to ask which to
    download. A product not read in the last ten minutes is read, with read: true, as a task of its own;
    "reading" says one is under way. names: the files the page knows a product has already ({key: [names]}: an
    update's, or Booth's from your library), answered with what's left out of them, without reading anything."""
    srv = self.server
    keys = [k for k in (body.get("keys") if isinstance(body.get("keys"), list) else [])[:20]
            if isinstance(k, str) and 0 < len(k) <= 400 and ":" in k]
    rules, kept = app.file_rules(srv.cfg), app.remembered_files(srv.cfg)
    out = lambda k, names: sorted(n for n in names if n in kept.get(k, ()) or app.ruled_out(rules, k.split(":", 1)[0], n))  # noqa: E731
    given = body.get("names") if isinstance(body.get("names"), dict) else {}
    now, files = app.time.monotonic(), {}
    for k in keys:
        got, known = srv.jobs.listed.get(k), given.get(k)
        if got and now - got["at"] < 600:
            files[k] = {"files": got["files"], "read": got["read"], "out": out(k, got["files"])}
        elif isinstance(known, list) and known:
            names = [n for n in known[:500] if isinstance(n, str) and 0 < len(n) <= 500]
            files[k] = {"files": names, "read": False, "out": out(k, names)}
    missing = [k for k in keys if k not in files]
    reading = srv.jobs.keys_of("list-files")   # (being read, or waiting its turn: asked for once, not again)
    unread = [k for k in missing if k not in reading]
    if unread and body.get("read") is True:   # a read of its own, waiting its turn behind another's if need be
        stores = sorted({k.split(":", 1)[0] for k in unread} & set(app.DOWNLOADABLE))
        if stores and srv.jobs.start("list-files", stores, keys=unread):
            reading = reading | set(unread)
    return {"files": files, "reading": any(k in reading for k in missing)}


def _resolve_integrity(self, body: dict):
    """Issue #231: files the last check found changed or missing, dealt with: "keep" (a change, as it is now),
    "forget" (a missing file, which is left out of its product's downloads from now on, so a sync doesn't bring it
    back), "again" (downloaded again, all of them as one task), or "show" (one file, in its folder)."""
    srv = self.server
    action = body.get("action")
    problems = [x for x in (body.get("problems") if isinstance(body.get("problems"), list) else [])[:app.MAX_PROBLEMS]
                if isinstance(x, dict)]
    if action not in ("keep", "forget", "again", "show") or not problems:
        return self._json({"error": "Nothing to do."}, 400)
    root = app.root_dir(srv.cfg)
    others = app.libraries.other_folders(srv.cfg)
    if any(self._hidden_key(app.tag_key(str(x.get("store")), str(x.get("name")))) for x in problems):
        return self._json({"error": "Unlock your hidden library first."}, 403)
    if action == "show":
        x = problems[0]
        bases = {str(b): b for b in (root, *others)}
        try:
            if bases.get(x.get("base")) is None or x.get("store") not in app.STORE_DIRS:
                raise app.UnsafePath("not a library folder")
            folder = app.rel_to_path(bases[x["base"]] / app.STORE_DIRS[x["store"]], str(x.get("folder")))
            target = app.rel_to_path(folder, str(x.get("path")))
            return self._json({"ok": True, "in": app.reveal(target if target.is_file() else folder if folder.is_dir() else folder.parent)})
        except (app.UnsafePath, OSError):
            return self._json({"error": "That folder couldn't be opened."}, 400)
    if srv.jobs.state.get("running"):   # (a sync or check holds its own copy of a store's records, and saves it)
        return self._json({"error": "Wait for Hoard to finish what it's doing, then try again."}, 409)
    done, failed, again = 0, [], {}
    for x in problems:
        try:
            got = app.resolve_problem(root, others, x, action)
        except (ValueError, OSError) as e:
            failed.append({"path": str(x.get("path"))[:300], "error": str(e)[:300]})
            continue
        done += 1
        if action == "forget":
            with srv.cfg_lock:
                kept = app.remembered_files(srv.cfg)
                kept.setdefault(got["key"], set()).add(got["file"])
                srv.cfg["file_skip"] = {k: sorted(v) for k, v in kept.items()}
                srv.save_settings()
        elif action == "again":
            pick = again.setdefault(got["key"], {"store": got["store"], "shown": [], "chosen": []})
            pick["shown"].append(got["file"]); pick["chosen"].append(got["file"])
    started = None
    if again:   # one download for all of them: those files, whatever was left out of them before
        started = srv.jobs.start("download", sorted({v["store"] for v in again.values()}), keys=sorted(again),
                                 chosen={k: {"shown": v["shown"], "chosen": v["chosen"]} for k, v in again.items()})
    return self._json({"ok": not failed, "done": done, "failed": failed[:50], "started": started})


def _extract(self, body: dict):
    """Look inside's Extract (packages.extract): the chosen files of a downloaded .unitypackage or .zip, or all of
    them, into a new folder named after it in Extracted, in the folder for editable copies (never in a library
    folder, so Hoard's checks leave them alone); then that folder opened, when asked."""
    srv = self.server
    target = app.open_target(srv.cfg, str(body.get("path", "")))
    if not target or not app.packages.can_look_inside(target.name) or not target.is_file():
        return self._json({"error": "That file isn't on disk anymore."}, 404)
    if self._hidden_file(target):
        return self._json({"error": "Unlock your hidden library first."}, 403)
    picks = body.get("picks")
    if not isinstance(picks, list) or not picks or len(picks) > 100_000 or \
            not all(isinstance(p, str) and len(p) <= 2100 for p in picks):
        return self._json({"error": "Choose what to take out first."}, 400)
    try:
        base = app.edits_root(srv.cfg, app.root_dir(srv.cfg)) / "Extracted"
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    name, n = app.safe_name(target.name.rsplit(".", 1)[0], 80), 1
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
        done = app.packages.extract(target, dest, picks, metas=body.get("metas") is True)
    except (app.packages.CantExtract, app.packages.NotAPackage, OSError) as e:
        app.rmtree(dest, ignore_errors=True)   # (what was taken out before it stopped goes with it)
        said = str(e) if isinstance(e, app.packages.CantExtract) else (f"Couldn't take them out: {e.strerror or e}."
                                                                   if isinstance(e, OSError) else "That file couldn't be read.")
        return self._json({"error": said}, 400 if isinstance(e, app.packages.CantExtract) else 500)
    if not done["files"] and done["skipped"]:   # nothing at all came out: say why, not an empty folder (#174)
        app.rmtree(dest, ignore_errors=True)
        return self._json({"error": "Nothing could be taken out.",
                           "skipped": [{"name": n, "why": w} for n, w in done["skipped"]]}, 400)
    print(f"Took {done['files']} files out of {target.name} into {dest}"
          + (f" ({len(done['skipped'])} left out)" if done["skipped"] else ""), flush=True)
    opened = None
    if body.get("open"):
        try:
            opened = app.reveal(dest)
        except OSError:
            pass
    return self._json({"ok": True, "folder": str(dest), "files": done["files"], "bytes": done["bytes"],
                       "skipped": [{"name": n, "why": w} for n, w in done["skipped"]], "opened_in": opened})


def _picks(self, raw) -> list[dict]:
    """Products from your library to put in a project, as the page chose them; hidden ones only when unlocked."""
    out, hidden = [], set() if self._unlocked() else set(app.MarkStore().keys("hidden"))   # (read once, not for each)
    for p in (raw if isinstance(raw, list) else [])[:500]:
        if not isinstance(p, dict) or not isinstance(p.get("key"), str) or p["key"] in hidden:
            continue
        out.append({"key": p["key"][:400], "kind": str(p.get("kind") or "")[:20], "file": str(p.get("file") or "")[:1000],
                    "member": p["member"][:1000] if isinstance(p.get("member"), str) else None})
    return out


def _delete_files(self, body: dict):
    """Delete the downloaded files of these products, only when confirmed (the pages ask first), and not while a
    job could be writing them (it waits its turn). A product still in your library stays there, as not downloaded,
    to download again whenever you like; a removed one leaves Downloads."""
    srv = self.server
    if body.get("confirm") is not True:
        return self._json({"error": "Confirm first."}, 400)
    raw = body.get("keys")
    keys = {k for k in raw[:5000] if isinstance(k, str)} if isinstance(raw, list) else set()
    marks = app.MarkStore().view()
    if keys & marks["hidden"] and not self._unlocked():
        return self._json({"error": "Unlock your hidden library first."}, 403)
    if not keys:
        return self._json({"error": "Choose the downloads to delete."}, 400)
    if not srv.jobs.busy.acquire(blocking=False):   # a job is running: this waits its turn after it
        names = sorted({a["name"] for a in srv.index(stale_ok=True)["assets"] if a.get("tag_key") in keys})
        name = names[0] if len(names) == 1 and len(keys) == 1 else f"{len(keys):,} {'product' if len(keys) == 1 else 'products'}"
        return self._queued(srv.jobs.start("delete-files", [], files={"keys": sorted(keys), "name": name}))
    try:
        done = app.delete_downloaded_files(srv.cfg, app.root_dir(srv.cfg), keys)
    finally:
        srv.jobs.busy.release()
        srv.jobs.kick()
    srv.forget_index()
    return self._json({"ok": True, **done})


def get_api_integrity(self, path, body, query):
    """GET /api/integrity. issue #231: the files the last check found, each to deal with"""
    srv = self.server
    u = app.urlparse(self.path)
    last = app.last_integrity() or {"problems": [], "changed": [], "missing": [], "data_changed": [], "checked": None}
    hidden = set() if self._unlocked() else set(app.MarkStore().keys("hidden"))
    removed = app.MarkStore().keys("removed")   # (removed since the check: not listed, issue #259)
    listed = [x for x in ({**x, "key": app.tag_key(x["store"], x["name"])} for x in last["problems"]) if x["key"] not in removed]
    shown = [x for x in listed if x["key"] not in hidden]
    return self._json({"checked": last["checked"], "problems": shown, "hidden_left_out": len(listed) - len(shown),
                       "more": max(0, len(last["changed"]) + len(last["missing"]) - len(last["problems"])),
                       "data_changed": last["data_changed"]})


def get_api_assets(self, path, body, query):
    """GET /api/assets. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    index = app.with_tags(srv.index(rescan="rescan" in app.parse_qs(u.query)))
    app.loading.finished("library")   # (the splash's count: issue #200)
    # each download carries its product's mark from the Library (archived, removed, hidden), so the Downloads
    # page has the same views (issue #29); hidden products' downloads stay out of view while it's locked
    marks, unlocked = app.MarkStore().view(), self._unlocked()
    by_store = {app.tag_key(i["store"], i["name"]) for i in srv.lib.snapshot()[0] if i.get("archived")}
    updates = app.AssetUpdates().load()   # what the last check for updates found (issue #26)
    used = app.projects.used_in(self._visible_projects())   # the Unity projects using each (issue #86)
    stacks, looks = {}, []   # copies of one product stack here as in the Library: by its products (hoard/library.py)
    listed = [dict(i) for i in srv.lib.snapshot()[0]]
    store_tags = {app.tag_key(i["store"], i["name"]): i["store_tags"] for i in listed if i.get("store_tags")}   # (#206)
    from .. import adult
    flagged = {app.tag_key(i["store"], i["name"]) for i in listed if i.get("adult") is True}   # (its store says: #311)
    tagdata = app.TagStore().load()   # (for each product's type, as the Library has it: issue #223)
    app.stack_by_picture(listed, apart=marks["apart"])
    for i in listed:
        # a download's stack is its own product's (by store and name), even one that stacks with nothing:
        # "Hair Pack 1" and "Hair Pack 2" share a product key (tag_key leaves numbers out), but the Library
        # keeps them apart, and so must Disk space's copies. The key is for downloads the library doesn't list
        stacks.setdefault((str(i["store"]).lower(), i["name"]), i["stack_key"])
        if i["stack_key"]:
            stacks.setdefault(app.tag_key(i["store"], i["name"]), i["stack_key"])
        if i.get("look_for") and (unlocked or app.tag_key(i["store"], i["name"]) not in marks["hidden"]):
            looks.append({"look_for": i["look_for"], "key": i["key"]})   # (its picture: /thumb/<key>)
    assets = []
    needed = srv.needs_view(index)
    from .. import local
    chosen = local.chosen_folders(app.root_dir(srv.cfg))   # Local items with a picture you chose
    from ..downloads import problems
    wrong = problems(index["assets"], app.last_integrity(), updates.get("failed"))   # (its error mark: issue #334)
    for a in index["assets"]:
        key = a.get("tag_key")
        mark = ("removed" if key in marks["removed"] else "hidden" if key in marks["hidden"]
                else "archived" if app.is_archived({"tag_key": key, "archived": key in by_store}, marks) else None)
        if key not in marks["hidden"] or unlocked:   # (hidden, whatever else it's marked)
            kind, known = app.product_type(tagdata, key, a["name"], a.get("tags") or [], store_tags.get(key, []))
            grown = adult.why(key, name=a["name"], tags=[*store_tags.get(key, []), *(a.get("tags") or [])],
                              flagged=key in flagged, marks=marks)   # for adults, and who says so (issues #311, #338)
            assets.append({**a, "mark": mark, "update": (updates["items"].get(key) or {}).get("files", []),
                           "adult": bool(grown), "adult_from": grown, "not_adult": key in marks["not_adult"],
                           "files": srv.files_with_code(a),   # (what code each holds: issue #303)
                           "store_tags": store_tags.get(key, []), "type": kind, "type_from": known,
                           "your_note": tagdata["notes"].get(key, ""),   # (issue #304; "note" is a Local item's own)
                           "stack_key": stacks.get((str(a["store"]).lower(), a["name"]), stacks.get(key, "")),
                           "needs": needed.get(a["id"]), "problems": wrong.get(key, []),
                           "own_picture": a.get("catalog_folder") in chosen,
                           "used_in": used.get(a.get("catalog_folder") or a.get("folder"), [])})
    shown = {a["id"] for a in assets}   # a hidden product isn't named as one another needs while it's locked
    keys = {a["tag_key"] for a in assets}   # nor kept in a set while it's locked
    grouped = [{**s, "items": [k for k in s["items"] if k in keys]} for s in app.sets.SetStore().load()["sets"]]
    for a in assets:
        if a["needs"]:
            a["needs"] = {**a["needs"], "products": [o for o in a["needs"]["products"] if o["id"] in shown]}
    index = {**index, "assets": assets, "privacy": {"pin_set": bool(marks["pin"]), "unlocked": unlocked,
                                                        "lock_in": self._lock_in() if unlocked else 0}, "looks_wanted": looks[:500],
             "libraries": srv.library_view(),
             "updates_checked": updates["checked"], "integrity": app.integrity_view(srv.cfg),
             "needs_reading": dict(srv.needs_reader.state), "sets": grouped}
    return self._json({**index, "version": app.__version__, "job": app.public_job(srv.jobs.state, self._hidden_names()), "store_sites": app.store_sites(),
                       # the logo's boxes: the stores you use (issue #278)
                       "enabled": {s: bool(srv.cfg[s].get("enabled", True)) for s in app.STORES},
                       "can_quit": srv.quit_app is not None, "can_background": srv.hide_window is not None, "can_notify": srv.can_notify, "can_pick": srv.pick_path is not None, "display": app.display_settings(srv.cfg), "ask_files": bool(srv.cfg.get("ask_files", True)),
                       "ui": app.ui_settings(srv.cfg), "routine": app.routine_record()["found"]}, compress=True)


def get_api_space(self, path, body, query):
    """GET /api/space. Downloads, Disk space: the same file kept more than once (hoard/space.py)"""
    srv = self.server
    u = app.urlparse(self.path)
    hidden = frozenset() if self._unlocked() else frozenset(app.MarkStore().keys("hidden"))
    with srv.cfg_lock:
        roots = app.libraries.roots(srv.cfg, app.root_dir(srv.cfg))
    return self._json({**app.space.copies(roots, hidden), "projects": len(self._visible_projects())}, compress=True)


def get_inside(self, path, body, query):
    """GET /inside/*. a preview from inside a package (Look inside: hoard/packages.py)"""
    srv = self.server
    u = app.urlparse(self.path)
    cid, _, name = path[len("/inside/"):].partition("/")
    data = app.packages.preview(cid, name)
    if data is None:
        return self._send(404, b"Not found", "text/plain")
    return self._send(200, data, "image/png", {"Cache-Control": "max-age=86400"})


def get_files(self, path, body, query):
    """GET /files/*. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    found = app.libraries.resolve(srv.cfg, app.unquote(path[len("/files/"):]))
    if not found:
        return self._send(404, b"Not found", "text/plain")
    root = found[0]
    rel = app.contained_rel(root, found[1])   # plain, and inside that library folder
    ctype = app.SERVED_IMAGE_TYPES.get(app.Path(rel).suffix.lower()) if rel else None
    if not rel or not ctype or not app.safe_join(root, rel):   # safe_join: no link out of the folder either
        return self._send(404, b"Not found", "text/plain")
    try:   # opened without following any link below the downloads folder; what's served is what was opened
        with app.open_under(root, rel) as fh:
            data = fh.read(app.MAX_SERVED_IMAGE + 1)
    except (app.UnsafePath, OSError):
        return self._send(404, b"Not found", "text/plain")
    if len(data) > app.MAX_SERVED_IMAGE:
        return self._send(404, b"Not found", "text/plain")
    return self._send(200, data, ctype, {"Cache-Control": "max-age=3600"})


def post_api_open(self, path, body, query):
    """POST /api/open. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    target = app.open_target(srv.cfg, str(body.get("path", "")))
    if not target or not target.exists():
        return self._json({"error": "That file or folder isn't on disk anymore."}, 404)
    try:
        return self._json({"ok": True, "opened_in": app.reveal(target)})
    except OSError as e:
        return self._json({"error": str(e)}, 500)


def post_api_look_inside(self, path, body, query):
    """POST /api/look-inside. Downloads: what a .unitypackage or .zip holds, without extracting it"""
    srv = self.server
    u = app.urlparse(self.path)
    target = app.open_target(srv.cfg, str(body.get("path", "")))
    if not target or not app.packages.can_look_inside(target.name) or not target.is_file():
        return self._json({"error": "That file isn't on disk anymore."}, 404)
    if self._hidden_file(target):   # (what's in a hidden product, as its name, stays hidden: #171)
        return self._json({"error": "Unlock your hidden library first."}, 403)
    try:
        return self._json(app.packages.look_inside(target), compress=True)
    except (app.packages.NotAPackage, OSError):
        return self._json({"error": "That file couldn't be read."}, 500)


def post_api_look_inside_extract(self, path, body, query):
    """POST /api/look-inside/extract. Look inside: the chosen files taken out, into a folder of their own"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._extract(body)


def post_api_previous_restore(self, path, body, query):
    """POST /api/previous/restore. Downloads: put a previous version of a file back (hoard/previous.py)"""
    srv = self.server
    u = app.urlparse(self.path)
    if srv.jobs.state.get("running"):
        return self._json({"error": "Wait for Hoard to finish what it's doing, then try again."}, 409)
    folder = app.open_target(srv.cfg, str(body.get("folder", "")))
    if not folder or not folder.is_dir():
        return self._json({"error": "That product's folder isn't on disk anymore."}, 404)
    try:
        app.restore_previous(srv.cfg, app.root_dir(srv.cfg), folder, str(body.get("stamp", "")), str(body.get("file", "")))
    except (ValueError, OSError) as e:
        return self._json({"error": str(e) if isinstance(e, ValueError) else "That version couldn't be put back."}, 400)
    srv.forget_index()
    return self._json({"ok": True})


def post_api_open_logs(self, path, body, query):
    """POST /api/open-logs. Settings, Troubleshooting: a log for each time Hoard started, 30 days' worth"""
    srv = self.server
    u = app.urlparse(self.path)
    from ..paths import logs_dir
    logs_dir().mkdir(parents=True, exist_ok=True)
    try:
        return self._json({"ok": True, "opened_in": app.reveal(logs_dir())})
    except OSError as e:
        return self._json({"error": str(e)}, 500)


def post_api_move(self, path, body, query):
    """POST /api/move. a download to another library folder (hoard/libraries.py), as a job"""
    srv = self.server
    u = app.urlparse(self.path)
    key, to = str(body.get("key") or "")[:400], body.get("to")
    if not isinstance(to, int) or isinstance(to, bool):
        return self._json({"error": "Choose one of your library folders."}, 400)
    asset = next((a for a in srv.index(stale_ok=True)["assets"] if a.get("tag_key") == key), None)
    if asset is None:
        return self._json({"error": "That isn't downloaded any more."}, 404)
    if key in app.MarkStore().keys("hidden") and not self._unlocked():
        return self._json({"error": "Unlock your hidden library first."}, 403)
    started = srv.jobs.start("move", [], move={"key": key, "to": to, "name": asset.get("name")})
    if not started:
        return self._json({"error": "That's already waiting its turn."}, 409)
    return self._json({"ok": True, "queued": started == "queued"})


def post_api_verify(self, path, body, query):
    """POST /api/verify. check the downloads now (issue #83), after anything already running"""
    srv = self.server
    u = app.urlparse(self.path)
    started = srv.jobs.start("verify", [])
    if not started:
        return self._json({"error": "A check is already waiting its turn."}, 409)
    return self._json({"ok": True, "queued": started == "queued"})


def post_api_edit_copy(self, path, body, query):
    """POST /api/edit-copy. a copy of a download to change, outside Hoard's care (issue #82)"""
    srv = self.server
    u = app.urlparse(self.path)
    key = str(body.get("key") or "")[:400]
    if key in app.MarkStore().keys("hidden") and not self._unlocked():
        return self._json({"error": "Unlock your hidden library first."}, 403)
    try:
        done = app.make_editable_copy(srv.cfg, app.root_dir(srv.cfg), key)
    except ValueError as e:
        return self._json({"error": str(e)}, 400)
    except OSError as e:
        return self._json({"error": f"Couldn't make the copy: {e.strerror or e}."}, 500)
    opened = None
    if body.get("open"):
        try:
            opened = app.reveal(app.Path(done["folder"]))
        except OSError:
            pass
    # Issue #328: the copy is listed in Local, where it is (never copied again), so it's found in Hoard afterwards,
    # with its own tile, tags and note. It's a task, as adding to Local is: the page opens its tile once it's there.
    listed = queued = False
    if body.get("local") is not False and done["files"]:
        from .. import local
        label = app.STORES.get(str(done["store"]).lower(), {}).get("label") or done["store"]
        what = {"path": done["folder"], "name": f"{done['name']} (editable copy)"[:300], "creator": done["creator"][:200],
                "note": f"An editable copy of your download from {label}. Hoard never checks or replaces it."[:300],
                "copy": False, "depth": 0}
        try:
            local.check_source(app.root_dir(srv.cfg), what["path"], False)
            started = srv.jobs.start("add-local", [], local=what)
            listed, queued = bool(started), started == "queued"
        except ValueError as e:   # (a copy all the same: it's in its folder, and can be added to Local by hand)
            print(f"Couldn't list the editable copy in Local: {e}", flush=True)
    return self._json({"ok": True, **done, "skipped": [{"path": p, "why": w} for p, w in done["skipped"]],
                       "opened_in": opened, "local": listed, "queued": queued})


def post_api_integrity_resolve(self, path, body, query):
    """POST /api/integrity/resolve. issue #231: deal with what the last check found"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._resolve_integrity(body)


def post_api_product_files(self, path, body, query):
    """POST /api/product-files. issue #225: what products have, to choose their files from before downloading"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json(self._product_files(body))


def post_api_delete_files(self, path, body, query):
    """POST /api/delete-files. a removed product's downloaded files, after you've confirmed (issue #81)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._delete_files(body)



METHODS = {'_product_files': _product_files, '_resolve_integrity': _resolve_integrity, '_extract': _extract, '_picks': _picks, '_delete_files': _delete_files}

ROUTES = [
    Route('GET', '/api/integrity', get_api_integrity, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/assets', get_api_assets, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/space', get_api_space, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/inside/*', get_inside, changes=False, auth='key', image_key=True, max_body=1048576, request=(), response='application/octet-stream'),
    Route('GET', '/files/*', get_files, changes=False, auth='key', image_key=True, max_body=1048576, request=(), response='application/octet-stream'),
    Route('POST', '/api/open', post_api_open, changes=True, auth='key', image_key=False, max_body=1048576, request=(('path', 'string'),), response='object'),
    Route('POST', '/api/look-inside', post_api_look_inside, changes=False, auth='key', image_key=False, max_body=1048576, request=(('path', 'string'),), response='object'),
    Route('POST', '/api/look-inside/extract', post_api_look_inside_extract, changes=True, auth='key', image_key=False, max_body=1048576, request=(('metas', 'any'), ('open', 'boolean'), ('path', 'string'), ('picks', 'any')), response='object'),
    Route('POST', '/api/previous/restore', post_api_previous_restore, changes=True, auth='key', image_key=False, max_body=1048576, request=(('file', 'string'), ('folder', 'string'), ('stamp', 'string')), response='object'),
    Route('POST', '/api/open-logs', post_api_open_logs, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/move', post_api_move, changes=True, auth='key', image_key=False, max_body=1048576, request=(('key', 'string'), ('to', 'string')), response='object'),
    Route('POST', '/api/verify', post_api_verify, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/edit-copy', post_api_edit_copy, changes=True, auth='key', image_key=False, max_body=1048576, request=(('key', 'string'), ('local', 'boolean'), ('open', 'boolean')), response='object'),
    Route('POST', '/api/integrity/resolve', post_api_integrity_resolve, changes=True, auth='key', image_key=False, max_body=1048576, request=(('action', 'string'), ('problems', 'any')), response='object'),
    Route('POST', '/api/product-files', post_api_product_files, changes=False, auth='key', image_key=False, max_body=1048576, request=(('keys', 'array'), ('names', 'any'), ('read', 'any')), response='object'),
    Route('POST', '/api/delete-files', post_api_delete_files, changes=True, auth='key', image_key=False, max_body=1048576, request=(('confirm', 'boolean'), ('keys', 'array')), response='object'),
]
