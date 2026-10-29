"""Every folder Hoard uses, for Settings' Hoard's folders: each by a name of its own (its id), with where it is and
whether it's there, to open. Only these are ever opened (/api/folders/open names one by its id), never a path the
page sends; Hoard's own folders are made when you open one that isn't there yet, the others only opened when they
are."""
from __future__ import annotations

from pathlib import Path

# Hoard's own: made when they're opened before Hoard has put anything in them
OWN = {"data", "logs", "backups", "reports"}


def places(cfg: dict, vpm_settings=None) -> list[dict]:
    """[{"id", "path", "exists", "label" (a library folder's own name, else None)}], in the order Settings shows them:
    your files first (downloads, library folders, editable copies), then Hoard's own, then Projects' (the Creator
    Companion's folder, new projects, project backups) when its settings can be read."""
    from . import libraries
    from .backup import backups_dir
    from .browser import signins_root
    from .config import edits_dir
    from .diagnostics import support_report_dir
    from .paths import data_dir, logs_dir
    out = []
    for lib in libraries.view(cfg):
        out.append(_place("downloads" if lib["main"] else f"library-{lib['n']}", Path(lib["path"]),
                          None if lib["main"] else lib["label"]))
    out.append(_place("edits", edits_dir(cfg)))
    out += [_place("data", data_dir()), _place("logs", logs_dir()), _place("backups", backups_dir()),
            _place("reports", support_report_dir()), _place("signins", signins_root(cfg))]
    if vpm_settings is not None:
        from .vpm.backup import default_folder
        out.append(_place("vcc", Path(vpm_settings.folder)))
        if vpm_settings.default_project_path():
            out.append(_place("projects", Path(vpm_settings.default_project_path())))
        out.append(_place("project-backups", Path(vpm_settings.project_backup_path() or default_folder())))
    return out


def _place(pid: str, path: Path, label: str | None = None) -> dict:
    """A place a library folder can be, for the page: its id, path, a label, and whether it's there."""
    try:
        there = path.is_dir()
    except OSError:
        there = False
    return {"id": pid, "path": str(path), "exists": there, "label": label}


def find(found: list[dict], pid) -> dict | None:
    """The place with that id, or None."""
    return next((p for p in found if p["id"] == pid), None) if isinstance(pid, str) else None
