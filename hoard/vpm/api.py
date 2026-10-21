"""Projects for the pages: what the server answers about projects, packages and repositories, and the work it hands
to a job (making a project, changing its packages, putting your products in it, backing it up, refreshing the
repositories), so it shows in Tasks and can be stopped.

Only projects on the list are ever changed: a path the page sends is checked against it first.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from ..common import log
from ..safety import DataFileError
from . import backup, environment, imports, listing, presets, repos, resolve, templates, unity
from .manifest import valid_name
from .preload import apply as put_in
from .preload import contents, suggested_packages
from .project import TYPE_NAMES, ProjectError, UnityProject
from .repos import Selector
from .version import UnityVersion, Version, VersionError, VersionRange

MAX_PACKAGES_LISTED = 5000
MAX_VERSIONS_LISTED = 2000   # (VRCFury alone has well over a thousand)


class ProjectsError(Exception):
    """Something asked of Projects that can't be done, in words to show."""


class Service:
    """The repositories, loaded once and kept until they change."""

    def __init__(self):
        self._lock = threading.RLock()
        self._collection: repos.Collection | None = None

    def settings(self) -> environment.Settings:
        try:
            return environment.Settings.load()
        except DataFileError as e:
            raise ProjectsError(f"The Creator Companion's settings can't be read ({e}).") from None

    def collection(self, reload: bool = False) -> repos.Collection:
        with self._lock:
            if self._collection is None or reload:
                self._collection = repos.Collection.load(self.settings())
            return self._collection

    def forget(self) -> None:
        with self._lock:
            self._collection = None

    # ---- reading

    def overview(self) -> dict:
        settings = self.settings()
        db = environment.database(settings.folder)
        editors = unity.find_editors(db["unityVersions"])
        coll = self.collection()
        return {
            "projects": listing.projects(),
            "editors": editors,
            "templates": templates.templates(settings.folder, sorted({e["version"] for e in editors}, reverse=True)),
            "settings": {"projects_folder": settings.default_project_path() or str(Path.home() / "ALCOM" / "Projects"),
                         "backups_folder": settings.project_backup_path() or str(backup.default_folder()),
                         "prerelease": settings.show_prerelease(), "vcc_folder": str(settings.folder)},
            "repos": [{"label": r.label(), "url": r.url, "path": str(r.path), "id": r.id, "builtin": r.builtin,
                       "packages": len(r.packages), "loaded": r.loaded, "error": r.error} for r in coll.repos],
            "presets": presets.load(),
        }

    def listed(self, path) -> str:
        """The project's path as the list has it: what's worked on is always the list's own, never what was sent."""
        if not isinstance(path, str) or not path or len(path) > 2000:
            raise ProjectsError("Choose a project.")
        found = listing.find(path)
        if found is None:
            raise ProjectsError("That project isn't on the list any more.")
        return found

    def project(self, path: str) -> dict:
        path = self.listed(path)
        try:
            p = UnityProject.load(path)
        except ProjectError as e:
            raise ProjectsError(str(e)) from None
        settings = self.settings()
        coll = self.collection()
        editors = unity.find_editors(environment.database(settings.folder)["unityVersions"])
        packages = []
        for name, (version, _deps) in sorted(p.locked.items()):
            have = p.installed.get(name)
            packages.append(self._package_row(coll, p, name, version, have, own=False, show_pre=settings.show_prerelease()))
        for folder_name, pkg in p.unlocked:
            if pkg is not None:
                packages.append(self._package_row(coll, p, pkg.name, pkg.version, pkg, own=True, show_pre=False,
                                                  folder=folder_name))
        state = listing.load_state()["projects"].get(listing._key(path), {})
        return {"path": path, "name": Path(path).name, "unity": str(p.unity) if p.unity else None, "type": p.project_type(),
                "type_name": TYPE_NAMES.get(p.project_type(), "Unknown"), "editor": unity.editor_for(p.unity, editors),
                "editors": editors, "open_in_unity": p.unity_running(), "packages": packages,
                "needs_repair": resolve.needs_repair(p), "preloaded": state.get("preloaded") or [],
                "favorite": bool(state.get("favorite"))}

    def _package_row(self, coll, p, name, version, have, own, show_pre, folder=None) -> dict:
        newest = None if own else coll.find(name, Selector.latest(p.unity, show_pre or version.is_pre))
        return {"name": name, "label": have.label() if have else name, "version": str(version),
                "description": have.description if have else "", "own": own, "folder": folder,
                "missing": not own and have is None,
                "latest": str(newest.version) if newest and newest.version > version else None,
                "repo": newest.repo.label() if newest and newest.repo else None,
                "changelog": have.changelog_url if have else None}

    def packages(self, unity_text, pre: bool) -> list[dict]:
        u = UnityVersion.parse(unity_text) if unity_text else None
        coll = self.collection()
        out = []
        for info in coll.newest(u, pre)[:MAX_PACKAGES_LISTED]:
            pk = info.package
            out.append({"name": pk.name, "label": pk.label(), "version": str(pk.version), "description": pk.description[:300],
                        "author": pk.author, "repo": info.repo.label() if info.repo else "your package folders",
                        "keywords": pk.keywords[:10], "changelog": pk.changelog_url})
        return out

    def versions(self, name: str, unity_text, pre: bool = False, keep: str | None = None) -> list[dict]:
        """Every version of a package there is to choose from (Manage project, Add packages), newest first: those that
        work in this Unity, not yanked, and prereleases only when they're offered (or it's the one installed, keep)."""
        u = UnityVersion.parse(unity_text) if unity_text else None
        fits = Selector.latest(u, True)
        found = sorted({i.version for i in self.collection().versions(name) if fits.satisfies(i.package)
                        and (pre or not i.version.is_pre or str(i.version) == keep)}, reverse=True)
        return [{"version": str(v), "pre": v.is_pre} for v in found[:MAX_VERSIONS_LISTED]]

    def product(self, asset: dict, needs: dict | None) -> dict:
        """What in a downloaded product can go into a project, and the VPM packages for what it needs."""
        tools = [t["key"] for t in (needs or {}).get("tools", [])]
        coll = self.collection()
        have_repo = {r.url for r in coll.repos if r.url}
        suggested = [{**s, "repo_added": s["repo"] is None or s["repo"] in have_repo} for s in suggested_packages(tools)]
        return {"name": asset["name"], "key": asset["tag_key"], "contents": contents(asset), "suggested": suggested}

    # ---- changes, worked out (for the page to show before they're made) and made (in a job)

    def changes(self, project: UnityProject, request: dict) -> resolve.Changes:
        coll = self.collection()
        prerelease = request.get("prerelease") is True
        if request.get("repair"):
            return resolve.repair(project, coll)
        if request.get("remove"):
            names = [n for n in request["remove"] if isinstance(n, str) and valid_name(n)][:200]
            return resolve.remove(project, names)
        wanted = []
        if request.get("upgrade_all"):
            for name, (version, _deps) in project.locked.items():
                newest = coll.find(name, Selector.latest(project.unity, prerelease or version.is_pre))
                if newest and newest.version > version:
                    wanted.append(newest)
            return resolve.add(project, coll, wanted, resolve.UPGRADE, prerelease) if wanted else resolve.Changes()
        for item in (request.get("add") or [])[:200]:
            name = item.get("name") if isinstance(item, dict) else None
            if not valid_name(name):
                continue
            version = Version.maybe(item.get("version")) if item.get("version") else None
            found = coll.find(name, Selector.specific(version) if version else Selector.latest(project.unity, prerelease))
            if found is None:
                found = coll.find(name, Selector.latest(None, prerelease)) if not version else None
            if found is None:
                raise ProjectsError(f"No repository has {name}{f' {version}' if version else ''}.")
            wanted.append(found)
        if not wanted:
            raise ProjectsError("Choose what to change.")
        return resolve.add(project, coll, wanted, resolve.AUTO, prerelease)

    def preview(self, request: dict) -> dict:
        path = self.listed(request.get("path"))
        try:
            project = UnityProject.load(path)
            changes = self.changes(project, request)
        except (ProjectError, resolve.ResolveError) as e:
            raise ProjectsError(str(e)) from None
        return {**changes.view(), "open_in_unity": project.unity_running()}

    # ---- the job's work (jobs.Jobs._project)

    def run(self, what: dict, assets_by_key) -> str:
        """Do one piece of project work: the sentence to show when it's done. log() says how it's going."""
        op = what.get("op")
        if op == "create":
            return self._create(what, assets_by_key)
        if op == "refresh":
            failed = self.collection().refresh()
            self.forget()
            return "Repositories refreshed." if not failed else "Refreshed, except: " + "; ".join(failed)
        path = self.listed(what.get("path"))
        if op in ("change", "preload"):
            self._fetch_missing()
        if op == "change":
            project = UnityProject.load(path)
            changes = self.changes(project, what)
            if changes.empty():
                return "Nothing needed changing."
            resolve.apply(project, changes, self.settings().folder)
            view = changes.view()
            return f"{Path(path).name}: {len(view['install'])} installed, {len(view['remove'])} removed."
        if op == "preload":
            return self._preload(path, what.get("picks") or [], assets_by_key, new=False)
        if op == "backup":
            project = UnityProject.load(path)
            leave_out = set(project.locked) if what.get("leave_out_packages") else set()
            out = backup.back_up(Path(path), Path(self.overview()["settings"]["backups_folder"]), leave_out)
            listing.note(path, backed_up=time.strftime("%Y-%m-%dT%H:%M:%S"))
            return f"Backed up {Path(path).name} to {out}."
        raise ProjectsError("Hoard doesn't know that project task.")

    def _fetch_missing(self) -> None:
        """Before packages are chosen: the repositories never fetched here yet, fetched (a first project, say)."""
        coll = self.collection()
        if any(r.url and not r.loaded for r in coll.repos):
            log("Fetching the repositories")
            for failed in coll.fetch_missing():
                log(f"Couldn't fetch {failed}")

    def _create(self, what: dict, assets_by_key) -> str:
        settings = self.settings()
        u = UnityVersion.parse(what.get("unity"))
        if u is None:
            raise ProjectsError("Choose a Unity version.")
        location = Path(str(what.get("location") or "")) if what.get("location") else None
        if location is None or not location.is_absolute():
            raise ProjectsError("Choose where the project goes.")
        extra = {}
        for name, text in (what.get("packages") or {}).items() if isinstance(what.get("packages"), dict) else ():
            if valid_name(name):
                try:
                    extra[name] = VersionRange.parse(text or "*")
                except VersionError:
                    raise ProjectsError(f"The version asked for {name} can't be read.") from None
        editors = unity.find_editors(environment.database(settings.folder)["unityVersions"])
        name = str(what.get("name") or "").strip()
        self._fetch_missing()
        log(f"Making the project {name}")
        try:
            project = templates.create(settings.folder, sorted({e["version"] for e in editors}), str(what.get("template")),
                                       location, name, u, extra)
        except templates.TemplateError as e:
            raise ProjectsError(str(e)) from None
        path = str(project.folder)
        listing.add(path)
        listing.note(path, created=time.strftime("%Y-%m-%dT%H:%M:%S"), template=what.get("template"))
        log("Installing its packages")
        changes = resolve.repair(project, self.collection())
        resolve.apply(project, changes, settings.folder)
        done = f"Made the project {name}."
        if what.get("picks"):
            done += " " + self._preload(path, what["picks"], assets_by_key, new=True)
        return done

    def _preload(self, path: str, picks: list, assets_by_key, new: bool) -> str:
        chosen = []
        for pick in picks[:500]:
            if not isinstance(pick, dict):
                continue
            asset = assets_by_key(pick.get("key"))
            if asset is None:
                continue
            entry = next((c for c in contents(asset) if c["kind"] == pick.get("kind") and c["file"] == pick.get("file")
                          and c.get("member") == pick.get("member")), None)
            if entry is not None:
                chosen.append((asset, entry))
        if not chosen:
            return "Nothing from your library was there to put in."
        project = UnityProject.load(path)
        done = put_in(Path(path), chosen, new_project=new, locked=set(project.locked), log=log)
        project = UnityProject.load(path)
        if resolve.needs_repair(project):
            log("Installing what the added packages need")
            try:
                resolve.apply(project, resolve.repair(project, self.collection()), self.settings().folder)
            except resolve.ResolveError as e:
                done["failed"].append({"what": "the packages they need", "why": str(e)})
        listing.add_preloaded(path, [{"tag_key": a["tag_key"], "name": a["name"], "file": e["file"],
                                      "member": e.get("member"), "label": e.get("label"), "kind": e["kind"],
                                      "added": one.get("added", [])[:20]}
                                     for (a, e), one in zip(chosen, done["each"])])
        imports.note(path, done["each"], log=log)   # and in the project itself, for you and Hoard for Unity (#155)
        parts = [f"{done['placed']:,} assets placed"]
        if done["already_there"] or done["in_the_way"]:
            parts.append(f"{done['already_there'] + done['in_the_way']:,} already there, left as they were")
        if done["packages"]:
            parts.append(f"{len(done['packages'])} packages added")
        message = "From your library: " + ", ".join(parts) + "."
        if done["failed"]:
            message += " Not put in: " + "; ".join(f"{f['what']} ({f['why']})" for f in done["failed"][:5]) + "."
        return message

