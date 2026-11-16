"""Per-project opt-in update policy and coordination through the existing task lanes."""
from __future__ import annotations
import time
from pathlib import Path
from . import listing
from .project import ProjectError, UnityProject

MODES = ("off", "packages", "assets", "both")
INTERVAL = 3600


def preference(path):
    entry = listing.load_state()["projects"].get(listing._key(str(path)), {})
    mode = entry.get("auto_update", "off") if isinstance(entry, dict) else "off"
    return mode if mode in MODES else "off"


def configure(path, mode):
    if mode not in MODES:
        raise ValueError("Choose off, packages, assets or both.")
    listing.note(str(path), auto_update=mode, auto_pending=None, auto_checked=None)
    return mode


def tick(server, now=None):
    """Coordinate check -> download -> apply, processing one project at a time."""
    if not server.cfg.get("setup_done") or server._background_stop.is_set():
        return False
    if any(j.state.get("running") or j.state.get("queue") for j in (server.jobs, server.project_jobs)):
        return False
    now = time.time() if now is None else now
    from ..asset_updates import AssetUpdates
    from ..library import DOWNLOADABLE
    from .api import ProjectsError
    for entry in list(listing.load_state()["projects"].values()):
        if not isinstance(entry, dict):
            continue
        mode, path = entry.get("auto_update"), entry.get("path")
        if mode not in MODES or mode == "off" or not isinstance(path, str):
            continue
        pending = entry.get("auto_pending")
        checked = entry.get("auto_checked")
        if not pending and isinstance(checked, (int, float)) and now - checked < INTERVAL:
            continue
        try:
            path = server.vpm.listed(path)
            if UnityProject.load(path).unity_running():
                continue
        except (ProjectsError, ProjectError, OSError, ValueError):
            continue
        error = None
        phase = pending.get("phase") if isinstance(pending, dict) else None
        if phase:
            report = next((h for h in server.jobs.tasks()["history"] if h["id"] == pending.get("job")), None)
            if report is None or report.get("outcome") != "done":
                error = "Automatic project update stopped: its download/check did not finish successfully."
        imported = entry.get("preloaded") if isinstance(entry.get("preloaded"), list) else []
        keys = list(dict.fromkeys(i.get("tag_key") for i in imported
                                 if isinstance(i, dict) and isinstance(i.get("tag_key"), str)))
        stores = list(dict.fromkeys(k.split(":", 1)[0].lower() for k in keys))
        stores = [s for s in stores if s in DOWNLOADABLE and server.cfg.get(s, {}).get("enabled", True)]
        if not error and mode in ("assets", "both") and stores and phase != "download":
            task = "check-updates" if not phase else "download"
            available = AssetUpdates().load()["items"] if phase else {}
            selected = keys if not phase else [k for k in keys if k in available]
            if selected:
                started = server.jobs.start(task, stores, keys=selected, scheduled=True, queue=False)
                if started == "started":
                    job = server.jobs.state.get("job_id")
                    if not job and server.jobs.history:
                        job = server.jobs.history[-1]["id"]
                    listing.note(path, auto_pending={"phase": "check" if not phase else "download", "job": job}, auto_checked=now)
                    return True
                return False
        listing.note(path, auto_pending=None, auto_checked=now)
        started = server.project_jobs.start("project", [], queue=False, scheduled=True,
                                           project={"op": "auto-update", "path": path, "name": Path(path).name, "download_error": error})
        if started == "started":
            return True
        listing.note(path, auto_pending=pending, auto_checked=checked)
    return False


def run(service, path, assets_by_key):
    """Re-read opt-in immediately before changes, so disabling also cancels queued work."""
    from . import managed
    from ..common import log
    from ..safety import safe_join
    from .api import ProjectsError
    from .preload import contents
    mode = preference(path)
    if mode == "off":
        return "Automatic updates are off for this project."
    project = UnityProject.load(path)
    if project.unity_running():
        listing.note(path, auto_checked=0)
        raise ProjectsError("Close Unity before updating this project. The next automatic check will try again.")
    managed.recover(Path(path))
    packages, updated, skipped = 0, 0, 0
    if mode in ("packages", "both"):
        failed = service.collection().refresh()
        service.forget()
        if failed:
            raise ProjectsError("Automatic package updates stopped: a repository could not be refreshed.")
        service._fetch_missing()
        project = UnityProject.load(path)
        changes = service.changes(project, {"upgrade_all": True})
        if any(c.packages or c.unity or c.unlocked for c in changes.conflicts.values()):
            raise ProjectsError("Automatic package updates need review: package conflicts were found.")
        if not changes.empty() and preference(path) in ("packages", "both"):
            if project.unity_running():
                listing.note(path, auto_checked=0)
                raise ProjectsError("Close Unity before updating this project.")
            packages = len(service._apply(project, changes))
    if mode in ("assets", "both"):
        entry = listing.load_state()["projects"].get(listing._key(path), {})
        imported_items = entry.get("preloaded") if isinstance(entry.get("preloaded"), list) else []
        for imported in imported_items:
            if preference(path) not in ("assets", "both"):
                break
            if not isinstance(imported, dict):
                continue
            asset = assets_by_key(imported.get("tag_key"))
            if not asset or imported.get("kind") != "unitypackage":
                skipped += 1
                continue
            matches = [c for c in contents(asset) if c["kind"] == "unitypackage" and c["file"] == imported.get("file") and c.get("member") == imported.get("member")]
            if len(matches) != 1:
                raise ProjectsError("An imported package file changed its name or is unavailable; choose its replacement manually.")
            content = matches[0]
            file = safe_join(Path(asset["abs_folder"]), content["file"])
            if file is None:
                raise ProjectsError("An imported package is outside its download folder.")
            log("Updating managed assets in " + Path(path).name)
            try:
                result = managed.update_file(Path(path), file, asset["tag_key"], content.get("member"))
            except ValueError:
                if UnityProject.load(path).unity_running():
                    listing.note(path, auto_checked=0)
                raise
            log(f"Managed asset update: {result['updated']} updated, {result['skipped']} left unchanged.")
            updated += result["updated"]
            skipped += result["skipped"]
    return f"Automatic update: {packages} package changes, {updated} managed assets updated; {skipped} untracked, modified or unsupported entries left unchanged."
