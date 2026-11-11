"""Projects for the pages: what the server answers about projects, packages and repositories, and the work it hands
to a job (making a project, changing its packages, putting your products in it, backing it up, refreshing the
repositories), so it shows in Tasks and can be stopped.

Only projects on the list are ever changed: a path the page sends is checked against it first.
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import threading
import time
from pathlib import Path

from .. import loading
from ..common import log
from ..safety import DataFileError
from . import backup, environment, git, imports, listing, logbook, presets, repos, resolve, templates, unity
from .logbook import Warn
from .manifest import valid_name
from .preload import apply as put_in
from .preload import contents, suggested_packages
from .project import TYPE_NAMES, ProjectError, UnityProject, disk_use, is_project
from .repos import Selector
from .version import UnityVersion, Version, VersionError, VersionRange

MAX_PACKAGES_LISTED = 5000
# Hoard for Unity: in every new project unless you leave it out, from its own repository (added when it isn't yet)
HOARD_PACKAGE = "soloflighter.hoard"
HOARD_REPO = "https://hoard.furryup.link/index.json"
MAX_VERSIONS_LISTED = 2000   # (VRCFury alone has well over a thousand)
SIZE_KEPT = 300   # seconds a project's size on disk is shown before it's counted again


class ProjectsError(Exception):
    """Something asked of Projects that can't be done, in words to show."""


class Service:
    """The repositories, loaded once and kept until they change."""

    def __init__(self):
        self._lock = threading.RLock()
        self._collection: repos.Collection | None = None
        self._sizes: dict[str, tuple[float, dict]] = {}   # each project's size on disk, by path, as last counted

    def settings(self) -> environment.Settings:
        """The Creator Companion's settings; raises ProjectsError when they can't be read."""
        try:
            return environment.Settings.load()
        except DataFileError as e:
            raise ProjectsError(f"The Creator Companion's settings can't be read ({e}).") from None

    def collection(self, reload: bool = False) -> repos.Collection:
        """Every repository and package folder, read once and kept until forgotten (reload reads them again)."""
        with self._lock:
            if self._collection is None or reload:
                self._collection = repos.Collection.load(self.settings())
                for r in self._collection.repos:   # (in Projects' log: a repository that couldn't be read)
                    if r.error:
                        logbook.warning(f"The repository {r.label()} couldn't be read: {r.error}")
            return self._collection

    def forget(self) -> None:
        """Forget the repositories read, to read them again next time (they changed)."""
        with self._lock:
            self._collection = None

    # ---- reading

    def overview(self) -> dict:
        """Everything Projects shows first: the projects, the Unity editors, the templates, the settings, the
        repositories, presets and backups."""
        settings = self.settings()
        db = environment.database(settings.folder)
        editors = unity.find_editors(db["unityVersions"])
        coll = self.collection()
        return {
            "projects": listing.projects(progress=lambda total: loading.counter("projects", "projects", total, every=1)),
            "editors": editors,
            "templates": templates.templates(settings.folder, sorted({e["version"] for e in editors}, reverse=True)),
            "settings": {"projects_folder": settings.default_project_path() or str(Path.home() / "ALCOM" / "Projects"),
                         "backups_folder": settings.project_backup_path() or str(backup.default_folder()),
                         "prerelease": settings.show_prerelease(), "vcc_folder": str(settings.folder)},
            "repos": [{"label": r.label(), "url": r.url, "path": str(r.path), "id": r.id, "builtin": r.builtin,
                       "packages": len(r.packages), "loaded": r.loaded, "error": r.error} for r in coll.repos],
            "presets": presets.load(),
            "backups": self.backups(summary=True),
            "hoard_for_unity": {"package": HOARD_PACKAGE, "repo": HOARD_REPO, "repo_added": self._has_hoard(coll)},
        }

    def updates(self) -> dict:
        """For Projects' list (issue #253): each project's packages with a newer version (as its own page lists them:
        stable ones only, unless it has a prerelease already or you asked for them), by its path. A project that
        can't be read just now isn't there."""
        settings = self.settings()
        coll = self.collection()
        out = {}
        for listed in listing.projects():
            if not listed.get("exists"):
                continue
            try:
                p = UnityProject.load(listed["path"])
            except (ProjectError, OSError, ValueError):
                continue
            newer = []
            for name, (version, _deps) in sorted(p.locked.items()):
                found = coll.find(name, Selector.latest(p.unity, settings.show_prerelease() or version.is_pre))
                if found and found.version > version:
                    newer.append(name)
            out[listed["path"]] = {"packages": len(newer), "names": newer[:20]}
        return out

    def about(self, path: str) -> dict:
        """A project's details beside Projects' list: its size on disk (counted again after a few minutes), its
        packages, each with any newer version, the products Hoard put in it, and its backups."""
        path = self.listed(path)
        counted = self._sizes.get(path)
        if counted is None or time.time() - counted[0] > SIZE_KEPT:
            counted = (time.time(), disk_use(path))
            self._sizes[path] = counted
        out = {"path": path, "size": counted[1], "packages": [], "own_packages": 0}
        try:
            p = UnityProject.load(path)
            coll, show_pre = self.collection(), self.settings().show_prerelease()
            out["packages"] = [self._package_row(coll, p, name, version, p.installed.get(name), own=False, show_pre=show_pre)
                               for name, (version, _deps) in sorted(p.locked.items())]
            out["own_packages"] = sum(1 for _name, pkg in p.unlocked if pkg is not None)
        except (ProjectError, ProjectsError, OSError, ValueError):
            pass   # (a project that can't be read just now: its size still shows)
        state = listing.load_state()["projects"].get(listing._key(path), {})
        out["preloaded"] = [{"tag_key": i.get("tag_key"), "name": i.get("name"), "when": i.get("when")}
                            for i in state.get("preloaded") or [] if isinstance(i, dict)]
        out["backed_up"] = state.get("backed_up")
        prefs, name = listing.backup_prefs(), Path(path).name.lower()
        moved = Path(prefs["moved_to"]) if prefs["moved_to"] and Path(prefs["moved_to"]).is_dir() else None
        mine = [b for b in backup.found(self.backups_folder()) if b["project"].lower() == name]
        away = [b for b in backup.found(moved) if b["project"].lower() == name] if moved else []
        out["backups"] = {"count": len(mine), "size": sum(b["size"] for b in mine), "newest": mine[0]["when"] if mine else None,
                          "moved": len(away)}
        out["git"] = git.summary(path)   # (its source control, in a few words: issue #296)
        return out

    @staticmethod
    def _has_hoard(coll) -> bool:
        """Is Hoard for Unity's repository added (by its address, or a repository that has the package)?"""
        return any((r.url or "").rstrip("/") == HOARD_REPO or HOARD_PACKAGE in r.packages for r in coll.repos)

    def backups_folder(self) -> Path:
        """Where project backups go."""
        return Path(self.settings().project_backup_path() or backup.default_folder())

    def backups(self, summary: bool = False) -> dict:
        """The backups panel: every backup, which are old, and the room left on their drive. In the overview, just
        enough to say when the drive is low on room and old backups could go."""
        prefs = listing.backup_prefs()
        view = backup.overview(self.backups_folder(), Path(prefs["moved_to"]) if prefs["moved_to"] else None,
                               prefs["keep"], prefs["days"])
        if summary:
            return {k: view[k] for k in ("room", "old_count", "old_size")}
        return view

    def backups_chosen(self, paths) -> list[Path]:
        """The backups chosen to delete or move, each checked to be in a backups folder; raises ProjectsError
        otherwise."""
        prefs = listing.backup_prefs()
        try:
            return backup.chosen(paths, [self.backups_folder(), Path(prefs["moved_to"]) if prefs["moved_to"] else None])
        except ValueError as e:
            raise ProjectsError(str(e)) from None

    def listed(self, path) -> str:
        """The project's path as the list has it: what's worked on is always the list's own, never what was sent."""
        if not isinstance(path, str) or not path or len(path) > 2000:
            raise ProjectsError("Choose a project.")
        found = listing.find(path)
        if found is None:
            raise ProjectsError("That project isn't on the list any more.")
        return found

    def project(self, path: str) -> dict:
        """One project, for its page: its packages (each with any newer version), its Unity, and what's installed of
        your library."""
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
        """A package as the project's page lists it: its version, a newer one if there is, where it comes from."""
        newest = None if own else coll.find(name, Selector.latest(p.unity, show_pre or version.is_pre))
        return {"name": name, "label": have.label() if have else name, "version": str(version),
                "description": have.description if have else "", "own": own, "folder": folder,
                "missing": not own and have is None,
                "latest": str(newest.version) if newest and newest.version > version else None,
                "repo": newest.repo.label() if newest and newest.repo else None,
                "changelog": have.changelog_url if have else None}

    def packages(self, unity_text, pre: bool) -> list[dict]:
        """The newest version of every package there is for this Unity, for Add packages."""
        u = UnityVersion.parse(unity_text) if unity_text else None
        coll = self.collection()
        out = []
        for info in coll.newest(u, pre)[:MAX_PACKAGES_LISTED]:
            pk = info.package
            out.append({"name": pk.name, "label": pk.label(), "version": str(pk.version), "description": pk.description[:300],
                        "author": pk.author, "repo": info.repo.label() if info.repo else "your package folders",
                        "source": ("vrchat" if info.repo.builtin else "repo") if info.repo else "folder",   # (to group them by)
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

    def product(self, asset: dict, needs: dict | None, project: str | None = None) -> dict:
        """What in a downloaded product can go into a project, and the VPM packages for what it needs: each with
        whether a repository you have already gives it (in_repo: which; then its own isn't added again), and, for a
        project on the list, the version the project already has of it (in_project)."""
        tools = [t["key"] for t in (needs or {}).get("tools", [])]
        coll = self.collection()
        has = {}
        if project:
            try:
                p = UnityProject.load(self.listed(project))
                has = {**{n: "" for n in p.dependencies}, **{n: str(v) for n, (v, _) in p.locked.items()}}
            except (ProjectsError, ProjectError):
                pass   # (not one on the list: what it has isn't known)
        suggested = []
        for s in suggested_packages(tools):
            source = coll.provides(s["package"]) or (coll.has_repo(s["repo"]) if s["repo"] else None)
            suggested.append({**s, "repo_added": s["repo"] is None or source is not None,
                              "in_repo": source.label() if source else None,
                              "in_project": has.get(s["package"]) if s["package"] in has else None})
        return {"name": asset["name"], "key": asset["tag_key"], "contents": contents(asset), "suggested": suggested}

    # ---- changes, worked out (for the page to show before they're made) and made (in a job)

    def changes(self, project: UnityProject, request: dict) -> resolve.Changes:
        """What a request (add, upgrade, downgrade, remove, repair) would do to the project, worked out by the
        resolver."""
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
        """What a request would do, for the page to show before it's done."""
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
            for why in failed:   # (each a warning in Projects' log)
                log(Warn(f"Couldn't refresh {why}"))
            return "Repositories refreshed." if not failed else "Refreshed, except: " + "; ".join(failed)
        if op == "move-backups":
            paths, to = self.backups_chosen(what.get("paths")), Path(str(what.get("to") or ""))
            if not to.is_absolute():
                raise ProjectsError("Choose a folder to move them to, by its full path.")
            count, freed, problems = backup.move(paths, to)
            if count:
                listing.set_backup_prefs(moved_to=str(to))
            for why in problems[:10]:
                log(Warn(f"Not moved: {why}"))
            done = f"Moved {count} {'backup' if count == 1 else 'backups'} to {to}, {freed / (1 << 30):.1f} GB freed."
            return done + (" Not moved: " + "; ".join(problems[:10]) if problems else "")
        if op in ("git-fetch", "git-pull", "git-push", "git-clone"):
            return self._git_task(op, what)
        path = self.listed(what.get("path"))
        if op in ("change", "preload"):
            self._fetch_missing()
        if op == "change":
            project = UnityProject.load(path)
            changes = self.changes(project, what)
            if changes.empty():
                return "Nothing needed changing."
            lines = self._apply(project, changes)
            view = changes.view()
            return (f"{Path(path).name}: {len(view['install'])} installed, {len(view['remove'])} removed"
                    + (f" ({', '.join(lines[:8])}{', ...' if len(lines) > 8 else ''})." if lines else "."))
        if op == "preload":
            return self._preload(path, what.get("picks") or [], assets_by_key, new=False)
        if op == "backup":
            project = UnityProject.load(path)
            leave_out = set(project.locked) if what.get("leave_out_packages") else set()
            history = None
            if what.get("git_bundle"):   # (issue #299: its Git history, as a bundle in the zip)
                self.backups_folder().mkdir(parents=True, exist_ok=True)
                history = self.backups_folder() / f".{Path(path).name}-{os.getpid()}.bundle.part"
                log(f"Putting {Path(path).name}'s Git history in a bundle")
                try:
                    if not git.bundle(path, history):
                        history = None
                except git.GitError as e:   # (Git missing, say: backed up all the same, without its history)
                    log(Warn(f"Its Git history couldn't be put in: {e}"))
                    history = None
            try:
                out = backup.back_up(Path(path), self.backups_folder(), leave_out, history=history)
            finally:
                if history is not None and history.exists():
                    history.unlink()
            listing.note(path, backed_up=time.strftime("%Y-%m-%dT%H:%M:%S"))
            return f"Backed up {Path(path).name} to {out}." + (" Its Git history is in it, as a bundle." if history else "")
        if op == "delete":
            return self._delete(path, backup_first=what.get("backup") is not False)
        raise ProjectsError("Hoard doesn't know that project task.")

    # ---- source control (hoard/vpm/git.py, issues #296 to #299): only for a project on the list

    def git(self, path: str, action: str, args: dict | None = None):
        """One named source control action on a listed project (never a command of the page's own): what it says.
        A GitError is a ProjectsError with Git's code (git_code) for the page."""
        folder = self.listed(path)
        if not Path(folder).is_dir():
            raise ProjectsError("Its folder isn't there any more.")
        a = args or {}
        actions = {
            "state": lambda: {**git.state(folder, again=a.get("again") is True), "app": listing.git_app()},
            "plan": lambda: {"plan": git.ignore_plan(folder), "examples": git.examples(folder), "where": git.where(folder)},
            "init": lambda: git.set_up(folder, nested=a.get("nested") is True),
            "ignore": lambda: {"written": git.update_ignore(folder)},
            "stage": lambda: {"staged": git.stage(folder, a.get("files"))},
            "unstage": lambda: {"unstaged": git.unstage(folder, a.get("files"))},
            "commit": lambda: {"commit": self._git_commit(folder, a.get("message"))},
            "identity": lambda: git.set_identity(folder, a.get("name"), a.get("email")),
            "diff": lambda: git.diff(folder, str(a.get("file") or ""), staged=a.get("staged") is True, ref=a.get("ref") or None),
            "history": lambda: {"commits": git.history(folder, skip=int(a.get("skip") or 0))},
            "files": lambda: {"files": git.commit_files(folder, a.get("ref"))},
            "remote": lambda: {"remotes": git.set_remote(folder, str(a.get("action") or ""), a.get("name"), a.get("url"))},
            "branch": lambda: {"branches": git.set_branch(folder, str(a.get("action") or ""), a.get("name"))},
            "abort": lambda: git.abort_merge(folder) or {"ok": True},
            "open-app": lambda: git.open_app(folder, listing.git_app()) or {"ok": True},
            "trust": lambda: git.trust(folder) or {"ok": True},   # (its settings that run programs, as shown)
        }
        if action not in actions:
            raise ProjectsError("Hoard doesn't know that.")
        try:
            return actions[action]()
        except git.GitError as e:
            err = ProjectsError(str(e))
            err.git_code = e.code
            raise err from None

    @staticmethod
    def _git_commit(folder: str, message) -> dict:
        """Commit what's staged, saying so in Projects' log."""
        done = git.commit(folder, message)
        log(f"Committed {Path(folder).name}: {done['short']} {done['subject']}")
        return done

    def _git_task(self, op: str, what: dict) -> str:
        """A source control task that talks to a remote, as Projects' tasks run (Stop ends Git): fetch, pull, push, or
        getting a project from a Git address (clone), which then goes on the list."""
        from ..common import tick
        try:
            if op == "git-clone":
                url, name = str(what.get("url") or ""), str(what.get("name") or "").strip()
                location = Path(str(what.get("location") or ""))
                why, _ = templates.check_name(location, name)
                if why or not location.is_absolute() or not location.is_dir():
                    raise ProjectsError(why or "Choose the folder it goes in, by its full path.")
                dest = location / name
                log(f"Getting {name} from {git.redact(url)}")
                git.clone(url, dest, progress=tick)
                if not is_project(dest):
                    return f"Copied it to {dest}, but it isn't a Unity project, so it isn't on the list."
                listing.add(str(dest))
                return f"Got {name}: it's on the list. Open it in Unity and its VPM packages are restored."
            path = self.listed(what.get("path"))
            if op == "git-fetch":
                return git.fetch(path, what.get("remote") or None, progress=tick)
            if op == "git-pull":
                return git.pull(path, merge=what.get("merge") is True, progress=tick)
            return git.push(path, what.get("remote") or None, progress=tick)
        except git.GitError as e:
            raise ProjectsError(str(e)) from None

    def deletable(self, path: str, doing: str = "delete") -> Path:
        """The project's folder, when it's safe to delete (or, doing "rename", to rename): on the list, a Unity project,
        closed in Unity, and holding none of Hoard's own folders (its data, the downloads, the project backups), nor
        being a drive's top or your home folder. Raises ProjectsError saying why not."""
        from ..config import load_config, root_dir   # (here: the config isn't Projects' own)
        from ..paths import data_dir
        keep = [data_dir(), root_dir(load_config()), self.backups_folder()]
        folder = Path(self.listed(path))
        try:
            real = folder.resolve(strict=True)
        except OSError:
            raise ProjectsError("Its folder isn't there any more: take it off the list instead.") from None
        if not real.is_dir() or not is_project(real):
            raise ProjectsError(f"That folder isn't a Unity project, so Hoard won't {doing} it.")
        if real.parent == real or real == Path.home().resolve() or len(real.parts) < 3:
            raise ProjectsError(f"Hoard won't {doing} a folder that high up.")
        for other in keep:
            try:
                inside = Path(other).resolve()
            except OSError:
                continue
            if inside == real or real in inside.parents:
                went = "go" if doing == "delete" else "move"
                raise ProjectsError(f"{inside} is inside this project, so it would {went} too. Move it somewhere else first.")
        try:
            if UnityProject.load(str(real)).unity_running():
                raise ProjectsError("Unity has this project open. Close it first.")
        except ProjectError:
            pass   # (a project whose files can't be read is still deleted when you ask)
        return real

    def rename(self, path: str, name) -> str:
        """Rename a project's folder (issue #290), where it is: as a delete is, only on the list and closed in Unity,
        and only to a name a folder can have that isn't taken beside it. The list and Hoard's notes follow it (and
        what Hoard for Unity reported about it); returns its new path."""
        folder = self.deletable(path, "rename")
        name = str(name or "").strip()
        if name == folder.name:
            raise ProjectsError("That's its name already.")
        case_only = name.lower() == folder.name.lower()
        why, _warning = templates.check_name(folder.parent, name)
        if why and not (case_only and _same_folder(folder, folder.parent / name)):   # (a case-insensitive drive: itself)
            raise ProjectsError(why)
        listed = self.listed(path)
        to = Path(listed).parent / name
        try:
            if case_only:   # (Windows and macOS don't see a change of case alone: by way of another name)
                step = folder.with_name(f"{folder.name}.renaming-{os.getpid()}")
                folder.rename(step)
                try:
                    step.rename(folder.parent / name)
                except OSError:
                    step.rename(folder)   # (back as it was: never left under the step's name)
                    raise
            else:
                folder.rename(folder.parent / name)
        except OSError as e:
            raise ProjectsError(f"Couldn't rename it: {e.strerror or e}") from None
        listing.rename(listed, str(to))
        from .. import projects as reports   # (what Hoard for Unity reported, by its folder)
        reports.moved(listed, str(to))
        return str(to)

    def _delete(self, path: str, backup_first: bool) -> str:
        """Delete a project from this computer: backed up first (unless you said not to), taken off the list, then its
        folder deleted. Stop works until the deleting starts; after that it carries on, so no half-deleted project is
        left behind."""
        name = Path(path).name
        folder = self.deletable(path)
        if backup_first:
            log(f"Backing up {name} first")
            out = backup.back_up(folder, self.backups_folder(), set(), keep_git=True)   # (its Git history too: never lost)
            log(f"Backed up to {out}")
        log(f"Deleting {name}")   # (the last word Stop can come at)
        listed = self.listed(path)   # (as the list has it: on Windows, a short name like RUNNER~1 resolves to another)
        listing.remove(listed)
        listing.forget(listed)
        shutil.rmtree(folder, **({"onexc": _writable_then_again} if sys.version_info >= (3, 12) else {"onerror": _writable_then_again}))
        return f"Deleted {name} from this computer." + (" Its backup is in your backups folder." if backup_first else "")

    def _fetch_missing(self) -> None:
        """Before packages are chosen: the repositories never fetched here yet, fetched (a first project, say)."""
        coll = self.collection()
        if any(r.url and not r.loaded for r in coll.repos):
            log("Fetching the repositories")
            for failed in coll.fetch_missing():
                log(Warn(f"Couldn't fetch {failed}"))

    def _create(self, what: dict, assets_by_key) -> str:
        """Make a new project from a template, with its packages, then put in your products; returns what was done."""
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
        if HOARD_PACKAGE in extra and not self._has_hoard(self.collection()):   # its repository, added first
            log("Adding Hoard for Unity's repository")
            try:
                repos.add_repo(settings, HOARD_REPO, "Hoard for Unity")
                self.forget()
            except repos.RepoError as e:
                log(Warn(f"Hoard for Unity's repository couldn't be added ({e}), so the project is made without it"))
                del extra[HOARD_PACKAGE]
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
        self._apply(project, resolve.repair(project, self.collection()))
        done = f"Made the project {name}."
        if what.get("picks"):
            done += " " + self._preload(path, what["picks"], assets_by_key, new=True)
        return done

    def _apply(self, project: UnityProject, changes: resolve.Changes) -> list[str]:
        """Make a project's package changes, saying first what each is (a package's version now and the one it gets),
        then reading the project back to see they were made: one that wasn't (Unity putting a package back while it
        had the project open, say) fails the task, naming it, rather than ending as done (issue #335). Returns the
        lines said."""
        lines = resolve.planned(project, changes)
        log(f"Changing {project.folder.name}'s packages: " + ("; ".join(lines) if lines else "nothing to change"))
        resolve.apply(project, changes, self.settings().folder)
        left = resolve.not_applied(project.folder, changes)
        if left:
            raise ProjectsError(f"{project.folder.name}'s packages weren't all changed: " + "; ".join(left[:8]) +
                                (". Close Unity if it has the project open, then try again." if project.unity_running()
                                 else ". Try again; if it happens again, create a support report."))
        return lines

    def _preload(self, path: str, picks: list, assets_by_key, new: bool) -> str:
        """Put products from your library (their Unity packages and VPM packages) into a project, with what they need;
        returns what was done."""
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
                self._apply(project, resolve.repair(project, self.collection()))
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


def _same_folder(a, b) -> bool:
    """Whether two paths are the very same folder (as a name differing only in case is, on Windows and macOS)."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _writable_then_again(func, path, _exc):
    """Deleting a project: a file Unity or git left read-only (as on Windows) is made writable, then deleted."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise
