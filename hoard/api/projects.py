"""Projects endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

from .. import server as app
from .routing import Route


def _visible_projects(self) -> list[dict]:
    """Projects' reports, without hidden products while the hidden library is locked (their names never leave
    the server then, here as everywhere)."""
    found = app.projects.read_all()
    if self._unlocked():
        return found
    hidden = app.MarkStore().keys("hidden")
    if not hidden:
        return found
    return [{**p, "assets": [a for a in p["assets"] if app.tag_key(a["store"], a["name"]) not in hidden]} for p in found]


def _vpm_logged(self, path: str, handle, arg):
    """A Projects request: what it couldn't do is said in Projects' log too (by _json), as ALCOM's log says it."""
    self._vpm_doing = app.VPM_ACTIONS.get(path)
    try:
        return handle(path, arg)
    except Exception as e:
        if self._vpm_doing:
            app.vpm_log.error(f"{self._vpm_doing}: {type(e).__name__}: {e}")
        raise
    finally:
        self._vpm_doing = None


def _vpm_get(self, path: str, query: dict):
    """Answer a Projects (VPM) GET request."""
    srv = self.server
    one = lambda k: (query.get(k) or [""])[0][:2000]  # noqa: E731
    try:
        if path == "/api/vpm":
            try:
                return self._json({**srv.vpm.overview(), "job": app.public_job(srv.project_jobs.state, self._hidden_names())},
                                  compress=True)
            finally:
                app.loading.finished("projects")
        if path == "/api/vpm/logs":   # Projects' log: this run's entries after the one numbered after
            after = one("after")
            return self._json({"run": app.vpm_log.book.run, "entries": app.vpm_log.book.entries(int(after) if after.isdigit() else 0),
                               "file": app.vpm_log.book.file.name if app.vpm_log.book.file else None})
        if path == "/api/vpm/project":
            found = srv.vpm.project(one("path"))
            report = next((r for r in app.projects.read_all() if r.get("path") and app.os.path.normcase(app.os.path.normpath(r["path"]))
                           == app.os.path.normcase(app.os.path.normpath(found["path"]))), None)
            if report is not None:   # what Hoard for Unity reported: the products it uses, and its credits
                updates = app.AssetUpdates().load()["items"]
                report = app.projects.view([r for r in self._visible_projects() if r["id"] == report["id"]],
                                       srv.index(stale_ok=True), updates)
                report = report[0] if report else None
            hidden = set() if self._unlocked() else set(app.MarkStore().keys("hidden"))
            found["preloaded"] = [x for x in found["preloaded"] if x.get("tag_key") not in hidden]
            return self._json({**found, "report": report}, compress=True)
        if path == "/api/vpm/updates":   # issue #253: each project's packages with newer versions, for the list
            return self._json({"projects": srv.vpm.updates()}, compress=True)
        if path in ("/api/vpm/git", "/api/vpm/git/plan", "/api/vpm/git/diff", "/api/vpm/git/history", "/api/vpm/git/files"):
            action = {"/api/vpm/git": "state"}.get(path, path.rsplit("/", 1)[-1])   # source control (issues #296 to #299)
            return self._vpm_git(one("path"), action, {"again": one("again") == "1", "file": one("file"), "staged": one("staged") == "1",
                                                     "ref": one("ref") or None, "skip": one("skip") if one("skip").isdigit() else 0})
        if path == "/api/vpm/about":   # a project's details beside the list: its size on disk, packages, backups
            found = srv.vpm.about(one("path"))
            hidden = set() if self._unlocked() else set(app.MarkStore().keys("hidden"))
            found["preloaded"] = [x for x in found["preloaded"] if x.get("tag_key") not in hidden]
            return self._json(found, compress=True)
        if path == "/api/vpm/packages":
            return self._json({"packages": srv.vpm.packages(one("unity"), one("pre") == "1")}, compress=True)
        if path == "/api/vpm/versions":
            return self._json({"versions": srv.vpm.versions(one("name"), one("unity"), one("pre") == "1", one("keep"))},
                              compress=True)
        if path == "/api/vpm/product":
            key = one("key")
            asset = srv.asset_by_key(key)
            if asset is None:
                return self._json({"error": "That isn't downloaded."}, 404)
            if self._hidden_key(key):
                return self._json({"error": "Unlock your hidden library first."}, 403)
            index = srv.index(stale_ok=True)
            return self._json(srv.vpm.product(asset, srv.needs_view(index).get(asset["id"]), one("path") or None))
    except app.vpm_api.ProjectsError as e:
        return self._json({"error": str(e)}, 400)
    return self._send(404, b"Not found", "text/plain")


def _vpm_git(self, path, action: str, args: dict):
    """A source control action on a listed project, answered with what it says, or its error and Git's code."""
    try:
        return self._json(self.server.vpm.git(path, action, args), compress=True)
    except app.vpm_api.ProjectsError as e:
        return self._json({"error": str(e), "code": getattr(e, "git_code", "")}, 400)


def _vpm_job(self, what: dict):
    """Queue a Projects task, saying whether it waits its turn."""
    started = self.server.project_jobs.start("project", [], project=what)
    if not started:
        return self._json({"error": "That's already waiting its turn."}, 409)
    return self._json({"ok": True, "queued": started == "queued"})


def _vpm_post(self, path: str, body: dict):
    """Answer a Projects (VPM) POST request."""
    from ..vpm import imports as vpm_imports, listing, presets as vpm_presets, templates as vpm_templates, unity as vpm_unity
    from ..vpm.project import is_project
    srv = self.server
    try:
        if path == "/api/vpm/preview":
            return self._json(srv.vpm.preview(body))
        if path in ("/api/vpm/apply", "/api/vpm/backup", "/api/vpm/preload"):
            srv.vpm.listed(body.get("path"))
            what = {"op": {"/api/vpm/apply": "change", "/api/vpm/backup": "backup", "/api/vpm/preload": "preload"}[path],
                    "path": body["path"], "name": app.Path(body["path"]).name}
            if path == "/api/vpm/apply":
                what.update({k: body.get(k) for k in ("add", "remove", "repair", "upgrade_all", "prerelease")})
            elif path == "/api/vpm/backup":
                what["leave_out_packages"] = body.get("leave_out_packages") is True
                what["git_bundle"] = body.get("git_bundle") is True   # (its Git history in it: issue #299)
            else:
                what["picks"] = self._picks(body.get("picks"))
            return self._vpm_job(what)
        if path == "/api/vpm/create":
            location, name = str(body.get("location") or "")[:1000], str(body.get("name") or "")[:255]
            problem, _ = vpm_templates.check_name(app.Path(location), name) if location else ("Choose where it goes.", None)
            if problem:
                return self._json({"error": problem}, 400)
            return self._vpm_job({"op": "create", "name": name, "location": location,
                                  "template": str(body.get("template") or "")[:200],
                                  "unity": str(body.get("unity") or "")[:40],
                                  "packages": body.get("packages") if isinstance(body.get("packages"), dict) else {},
                                  "picks": self._picks(body.get("picks"))})
        if path == "/api/vpm/refresh":
            return self._vpm_job({"op": "refresh", "name": "repositories"})
        # the backups panel (vpm/backup.py): old ones deleted, or moved to a drive with more room
        if path == "/api/vpm/backups":
            return self._json({"ok": True, **srv.vpm.backups()})
        if path == "/api/vpm/backups/settings":
            from ..vpm import backup as vpm_backup
            changes = {}
            if body.get("keep") in vpm_backup.KEEP_CHOICES:
                changes["keep"] = body["keep"]
            if body.get("days") in vpm_backup.DAYS_CHOICES:
                changes["days"] = body["days"]
            listing.set_backup_prefs(**changes)
            return self._json({"ok": True, **srv.vpm.backups()})
        if path == "/api/vpm/backups/show":
            folder = srv.vpm.backups_folder()
            folder.mkdir(parents=True, exist_ok=True)
            return self._json({"ok": True, "in": app.reveal(folder)})
        if path == "/api/vpm/backups/delete":
            from ..vpm import backup as vpm_backup
            count, freed = vpm_backup.delete(srv.vpm.backups_chosen(body.get("paths")))
            if count:
                app.vpm_log.info(f"Deleted {app.vpm_log.count(count, 'backup')}, freeing {app.vpm_log.size_text(freed)}")
            return self._json({"ok": True, "deleted": count, "freed": freed})
        if path == "/api/vpm/backups/move":
            paths = srv.vpm.backups_chosen(body.get("paths"))
            to = str(body.get("to") or "").strip()[:1000]
            if not paths:
                return self._json({"error": "Choose the backups to move."}, 400)
            if not to or not app.Path(to).is_absolute():
                return self._json({"error": "Choose a folder to move them to, by its full path."}, 400)
            return self._vpm_job({"op": "move-backups", "paths": [str(p) for p in paths], "to": to,
                                  "name": f"{len(paths)} {'backup' if len(paths) == 1 else 'backups'}"})
        if path == "/api/vpm/check-name":
            problem, warning = vpm_templates.check_name(app.Path(str(body.get("location") or "")[:1000]), str(body.get("name") or "")[:300])
            return self._json({"problem": problem, "warning": warning})
        if path == "/api/vpm/open":
            found = srv.vpm.project(str(body.get("path") or ""))
            if found["open_in_unity"]:
                return self._json({"error": "Unity already has this project open."}, 409)
            wanted = body.get("editor") if isinstance(body.get("editor"), str) else (found["editor"] or {}).get("path")
            editor = next((e["path"] for e in found["editors"] if e["path"] == wanted), None)   # (Hoard's own copy)
            if not editor:
                return self._json({"error": f"Unity {found['unity']} isn't installed. Install it with Unity Hub, or "
                                            "choose another version to open it in."}, 400)
            vpm_unity.open_project(app.Path(editor), app.Path(found["path"]))
            listing.note(found["path"], opened=app.time.strftime("%Y-%m-%dT%H:%M:%S"))
            version = next((e["version"] for e in found["editors"] if e["path"] == editor), found["unity"])
            app.vpm_log.info(f"Opened {found['name']} in Unity {version}")
            return self._json({"ok": True})
        if path == "/api/vpm/open-folder":
            where = app.Path(srv.vpm.listed(body.get("path")))
            if body.get("show") == "imports":   # what Hoard put in it (vpm/imports.py), shown in its folder
                where = where / vpm_imports.NOTE_NAME
                if not where.is_file():
                    return self._json({"error": "There's no list of what Hoard put in this project yet."}, 404)
            return self._json({"ok": True, "in": app.reveal(where)})
        if path == "/api/vpm/add-project":
            where = str(body.get("path") or "")[:2000]
            if not where or not app.Path(where).is_absolute() or not app.Path(where).is_dir() or not is_project(app.Path(where)):
                return self._json({"error": "That folder isn't a Unity project."}, 400)
            listing.add(str(app.Path(where)))
            app.vpm_log.info(f"Added {app.Path(where).name} to the list ({app.Path(where)})")
            return self._json({"ok": True})
        if path == "/api/vpm/remove-project":
            where = srv.vpm.listed(body.get("path"))
            ok = listing.remove(where)
            if ok:
                app.vpm_log.info(f"Took {app.Path(where).name} off the list ({where})")
            return self._json({"ok": ok})
        if path == "/api/vpm/delete-project":   # from this computer: only with its name typed, as a task
            where = srv.vpm.listed(body.get("path"))
            if str(body.get("confirm") or "") != app.Path(where).name:
                return self._json({"error": "Type the project's name to delete it."}, 400)
            srv.vpm.deletable(where)   # (said now when it can't be: Unity has it open, say)
            return self._vpm_job({"op": "delete", "path": where, "name": app.Path(where).name, "backup": body.get("backup") is not False})
        if path == "/api/vpm/git/sync":   # fetch, pull or push: a task, as it talks to a remote (issue #298)
            where = srv.vpm.listed(body.get("path"))
            op = {"fetch": "git-fetch", "pull": "git-pull", "push": "git-push"}.get(str(body.get("op") or ""))
            if not op:
                return self._json({"error": "Hoard doesn't know that."}, 400)
            return self._vpm_job({"op": op, "path": where, "name": app.Path(where).name, "merge": body.get("merge") is True,
                                  "remote": str(body.get("remote") or "")[:40] or None})
        if path == "/api/vpm/git/clone":   # a project from a Git address (issue #299): a task, then it's on the list
            from ..vpm import git as vpm_git
            try:
                url = vpm_git.check_url(body.get("url"))
            except vpm_git.GitError as e:
                return self._json({"error": str(e)}, 400)
            name = str(body.get("name") or "").strip()[:255] or vpm_git.clone_name(url)
            location = str(body.get("location") or "")[:1000]
            problem, _ = vpm_templates.check_name(app.Path(location), name) if location else ("Choose where it goes.", None)
            if problem:
                return self._json({"error": problem}, 400)
            return self._vpm_job({"op": "git-clone", "url": url, "name": name, "location": location})
        if path == "/api/vpm/git/app":   # the Git app to open repositories in (issue #299)
            try:
                return self._json({"ok": True, "app": listing.set_git_app(body.get("app"))})
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if path.startswith("/api/vpm/git/"):   # each one a named action (hoard/vpm/api.py Service.git)
            return self._vpm_git(body.get("path"), path.rsplit("/", 1)[-1], body)
        if path == "/api/vpm/rename":   # its folder, where it is (issue #290): the list and Hoard's notes follow it
            where = srv.vpm.listed(body.get("path"))
            renamed = srv.vpm.rename(where, str(body.get("name") or "")[:300])
            app.vpm_log.info(f"Renamed {app.Path(where).name} to {app.Path(renamed).name} ({renamed})")
            return self._json({"ok": True, "path": renamed, "name": app.Path(renamed).name})
        if path == "/api/vpm/favorite":
            listing.note(srv.vpm.listed(body.get("path")), favorite=body.get("on") is True)
            return self._json({"ok": True})
        if path == "/api/vpm/organize":   # a project's folder and tags on Hoard's list (issue #190)
            kept = listing.organize(srv.vpm.listed(body.get("path")), folder=body.get("folder"), tags=body.get("tags"))
            return self._json({"ok": True, "folder": kept.get("folder"), "tags": kept.get("tags") or []})
        if path == "/api/vpm/repos/add":
            from ..vpm import repos as vpm_repos
            try:
                repo = vpm_repos.add_repo(srv.vpm.settings(), str(body.get("url") or "")[:2000],
                                          str(body.get("name") or "")[:200] or None, body.get("headers") or None)
            except vpm_repos.RepoError as e:
                return self._json({"error": str(e)}, 400)
            srv.vpm.forget()
            app.vpm_log.info(f"Added the repository {repo.label()} ({app.vpm_log.count(len(repo.packages), 'package')})")
            return self._json({"ok": True, "label": repo.label(), "packages": len(repo.packages)})
        if path == "/api/vpm/repos/remove":
            from ..vpm import repos as vpm_repos
            local = str(body.get("path") or "")[:2000]
            label = next((r.label() for r in srv.vpm.collection().repos if str(r.path) == local), local)
            ok = vpm_repos.remove_repo(srv.vpm.settings(), local)
            srv.vpm.forget()
            if ok:
                app.vpm_log.info(f"Removed the repository {label}")
            return self._json({"ok": ok})
        if path == "/api/vpm/settings":
            settings = srv.vpm.settings()
            for key, field in (("projects_folder", "defaultProjectPath"), ("backups_folder", "projectBackupPath")):
                if isinstance(body.get(key), str) and body[key].strip():
                    if not app.Path(body[key].strip()).is_absolute():
                        return self._json({"error": "Use a folder's full path."}, 400)
                    settings.set(field, body[key].strip()[:1000])
            if isinstance(body.get("prerelease"), bool):
                settings.set("showPrereleasePackages", body["prerelease"])
            settings.save()
            app.vpm_log.info("Saved Unity and folders: projects in " + str(settings.default_project_path() or "the usual folder") +
                         ", backups in " + str(settings.project_backup_path() or "the usual folder") +
                         (", prerelease packages shown" if settings.show_prerelease() else ""))
            return self._json({"ok": True})
        if path == "/api/vpm/presets":
            action = body.get("action")
            if action == "save":
                saved = vpm_presets.save(body.get("preset") or {})
                app.vpm_log.info(f"Saved the preset {saved['name']}")
                return self._json({"ok": True, "preset": saved})
            if action == "delete":
                gone = next((x["name"] for x in vpm_presets.load() if x["id"] == body.get("id")), None)
                ok = vpm_presets.delete(str(body.get("id") or "")[:40])
                if ok and gone:
                    app.vpm_log.info(f"Deleted the preset {gone}")
                return self._json({"ok": ok})
            if action == "export":
                preset = next((x for x in vpm_presets.load() if x["id"] == body.get("id")), None)
                if preset is None:
                    return self._json({"error": "That preset isn't there any more."}, 404)
                assets = {x["key"]: srv.asset_by_key(x["key"]) for x in preset["products"]}
                out = vpm_presets.export_alcom(preset, assets, srv.vpm.settings().folder)
                app.vpm_log.info(f"Saved the preset {preset['name']} for ALCOM too ({out['path']})")
                return self._json({"ok": True, **out})
            return self._json({"error": "Bad request."}, 400)
    except vpm_presets.PresetError as e:
        return self._json({"error": str(e)}, 400)
    except app.vpm_api.ProjectsError as e:
        return self._json({"error": str(e)}, 400)
    except OSError as e:
        return self._json({"error": f"That couldn't be done ({e.strerror or e})."}, 500)
    return self._send(404, b"Not found", "text/plain")


def get_api_projects(self, path, body, query):
    """GET /api/projects. the Unity projects that use your assets (issue #86)"""
    srv = self.server
    u = app.urlparse(self.path)
    found = self._visible_projects()
    updates = app.AssetUpdates().load()["items"]
    return self._json({"projects": app.projects.view(found, srv.index(stale_ok=True), updates),
                       "hidden_left_out": not self._unlocked() and bool(app.MarkStore().keys("hidden"))}, compress=True)


def get_api_vpm(self, path, body, query):
    """GET /api/vpm, /api/vpm/about, /api/vpm/git, /api/vpm/git/diff, /api/vpm/git/files, /api/vpm/git/history, /api/vpm/git/plan, /api/vpm/logs, /api/vpm/packages, /api/vpm/product, /api/vpm/project, /api/vpm/updates, /api/vpm/versions. Projects (hoard/vpm)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._vpm_logged(path, self._vpm_get, app.parse_qs(u.query))


def post_api_vpm_preview(self, path, body, query):
    """POST /api/vpm/preview, /api/vpm/apply, /api/vpm/create, /api/vpm/preload, /api/vpm/backup, /api/vpm/refresh, /api/vpm/open, /api/vpm/add-project, /api/vpm/remove-project, /api/vpm/favorite, /api/vpm/organize, /api/vpm/rename, /api/vpm/git/init, /api/vpm/git/ignore, /api/vpm/git/stage, /api/vpm/git/unstage, /api/vpm/git/commit, /api/vpm/git/identity, /api/vpm/git/remote, /api/vpm/git/branch, /api/vpm/git/abort, /api/vpm/git/open-app, /api/vpm/git/app, /api/vpm/git/sync, /api/vpm/git/clone, /api/vpm/git/trust, /api/vpm/repos/add, /api/vpm/repos/remove, /api/vpm/settings, /api/vpm/check-name, /api/vpm/presets, /api/vpm/open-folder, /api/vpm/backups, /api/vpm/backups/settings, /api/vpm/backups/delete, /api/vpm/backups/move, /api/vpm/backups/show, /api/vpm/delete-project. Projects (hoard/vpm)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._vpm_logged(path, self._vpm_post, body)


def post_api_projects_forget(self, path, body, query):
    """POST /api/projects/forget. a Unity project out of Projects (issue #86); opening it again brings it back"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json({"ok": app.projects.forget(str(body.get("id") or "")[:40])})



METHODS = {'_visible_projects': _visible_projects, '_vpm_logged': _vpm_logged, '_vpm_get': _vpm_get, '_vpm_git': _vpm_git, '_vpm_job': _vpm_job, '_vpm_post': _vpm_post}

ROUTES = [
    Route('GET', '/api/projects', get_api_projects, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/about', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/git', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/git/diff', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/git/files', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/git/history', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/git/plan', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/logs', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/packages', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/product', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/project', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/updates', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/vpm/versions', get_api_vpm, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/preview', post_api_vpm_preview, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/apply', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/create', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/preload', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/backup', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/refresh', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/open', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/add-project', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/remove-project', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/favorite', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/organize', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/rename', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/init', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/ignore', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/stage', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/unstage', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/commit', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/identity', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/remote', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/branch', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/abort', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/open-app', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/app', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/sync', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/clone', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/git/trust', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/repos/add', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/repos/remove', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/settings', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/check-name', post_api_vpm_preview, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/presets', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/open-folder', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/backups', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/backups/settings', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/backups/delete', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/backups/move', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/backups/show', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/vpm/delete-project', post_api_vpm_preview, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/projects/forget', post_api_projects_forget, changes=True, auth='key', image_key=False, max_body=1048576, request=(('id', 'string'),), response='object'),
]
