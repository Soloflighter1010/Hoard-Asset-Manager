"""Changing where Hoard's folders are (issue #385): Settings' Hoard's folders, Change... beside each.

What each does, said before anything changes (plan), then done (change):

- Downloads folder: the new folder is the main one, where downloads go from now on; the old one stays as a library
  folder, so everything in it is still found and nothing large is copied.
- Editable copies, Backups, Support reports: Hoard uses the new folder from now on; what's in the old one is moved
  there too when you tick that (as a task), else left where it is.
- Hoard's own folder, Logs, Store sign-ins: Hoard's own data is in use while Hoard runs, so they're moved as Hoard
  next starts, before anything opens them (finish_pending): copied, checked, then the old copy deleted. Never onto a
  network drive; Store sign-ins only within your own user folder, as their protection depends on where they are.
- The Creator Companion's folder: never moved (it's the Creator Companion's and ALCOM's), only pointed at another
  one that is a Creator Companion folder.
- New projects, Project backups: Projects' own settings (the Creator Companion's settings.json), as Unity and
  folders sets them.

Default puts one back where it started. Where they are is in paths.py's location.json (and config.json for the
downloads folder, editable copies and sign-ins).
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from .paths import PENDING, base_dir, data_dir, logs_dir, on_network, placed, set_moved

MOVE_LATER = {"data", "logs", "signins"}     # moved as Hoard next starts
MOVE_NOW = {"edits", "backups", "reports"}   # what's there moved now (a task), if you say so
MAX_COUNTED = 200_000                          # files counted for "how much", at most


def current(srv, pid: str) -> Path:
    """Where a folder is now."""
    from . import places
    found = places.find(places.places(srv.cfg, _vpm_settings(srv)), pid)
    if found is None:
        raise ValueError("That isn't one of Hoard's folders.")
    return Path(found["path"])


def _vpm_settings(srv):
    """Projects' settings, when they can be read (else its folders aren't offered)."""
    try:
        return srv.vpm.settings()
    except Exception:
        return None


def default(srv, pid: str) -> Path:
    """Where a folder starts out."""
    from .backup import documents_dir
    from .config import root_dir
    if pid == "data":
        return base_dir()
    if pid == "logs":
        return data_dir() / "logs"
    if pid == "backups":
        return documents_dir() / "Hoard backups"
    if pid == "reports":
        return documents_dir() / "Hoard" / "Support Reports"
    if pid == "signins":
        return data_dir() / "sign-ins"
    if pid == "edits":
        return root_dir(srv.cfg).parent / "Hoard Edits"
    if pid == "vcc":   # (where the Creator Companion keeps it, as if you hadn't pointed at another)
        from .vpm import environment
        return environment.usual_vcc_dir()
    raise ValueError("That one has no usual place to go back to.")


def size(folder: Path, cap: int | None = MAX_COUNTED) -> tuple[int, int]:
    """(files, bytes) in a folder, without following links; counted up to cap files (None: all of them)."""
    files = total = 0
    for top, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(top, d))]
        for n in names:
            try:
                st = os.stat(os.path.join(top, n), follow_symlinks=False)
            except OSError:
                continue
            files += 1
            total += st.st_size
            if cap is not None and files >= cap:
                return files, total
    return files, total


def _inside(a: Path, b: Path) -> bool:
    """Is a the same folder as b, or inside it?"""
    try:
        a, b = a.resolve(), b.resolve()
    except OSError:
        return False
    return a == b or b in a.parents


def plan(srv, pid: str, value: str | None) -> dict:
    """What changing a folder to value (None: back to where it started) would do, without doing it: {"id", "from",
    "to", "how" ("library", "move-now", "move-later", "point", "projects"), "files", "bytes", "warning"}. Raises
    ValueError for a folder it can't be."""
    from . import reach
    now = current(srv, pid)
    to = default(srv, pid) if value is None else Path(os.path.expandvars(str(value).strip())).expanduser()
    if not to.is_absolute():
        raise ValueError("Choose the folder by its full path.")
    if _inside(to, now) and _inside(now, to):
        raise ValueError("That's where it is already.")
    how = ("library" if pid == "downloads" else "move-later" if pid in MOVE_LATER else "move-now" if pid in MOVE_NOW
           else "point" if pid == "vcc" else "projects" if pid in ("projects", "project-backups") else None)
    if how is None:
        raise ValueError("That folder can't be changed here.")
    if how in ("move-later", "move-now") and (_inside(to, now) or _inside(now, to)):
        raise ValueError("A folder can't be moved into itself, or into a folder inside it.")
    there = next((p for p in [to, *to.parents] if p.exists()), None)
    if there is None or reach.away([str(there)], 3):
        raise ValueError(f"That drive doesn't answer just now: {to.anchor or to}")
    network = on_network(there)
    if network and pid in MOVE_LATER:
        raise ValueError("Hoard's own folder, its logs and its sign-ins can't go on a network drive: choose a folder "
                         "on this computer.")
    if pid == "signins" and not _inside(to, Path.home()):
        raise ValueError("Store sign-ins can only go in a folder in your own user folder, where only you can read "
                         "them.")
    if how == "move-later" and to.exists() and any(p.name not in KEEP for p in to.iterdir()) and value is not None:
        raise ValueError("Choose a new folder, or an empty one: that one has things in it.")
    if how == "point" and not ((to / "settings.json").is_file() or (to / "vcc.liteDb").is_file()):
        raise ValueError("That isn't a Creator Companion folder (it has no settings.json).")
    files, total = size(now) if how in ("move-later", "move-now") and now.is_dir() else (0, 0)
    return {"id": pid, "from": str(now), "to": str(to), "how": how, "files": files, "bytes": total,
            "warning": "It's on a network drive: it's only there while that drive is." if network else None}


def change(srv, pid: str, value: str | None, move: bool = False) -> dict:
    """Make the change plan() described. {"how", "to", "restart": whether Hoard has to be opened again for it}."""
    p = plan(srv, pid, value)
    to = Path(p["to"])
    if p["how"] == "library":
        return _downloads(srv, Path(p["from"]), to)
    if p["how"] == "projects":
        settings = srv.vpm.settings()
        settings.set("defaultProjectPath" if pid == "projects" else "projectBackupPath", str(to) if value is not None else "")
        settings.save()
        return {"how": p["how"], "to": str(to), "restart": False}
    if p["how"] == "point":
        set_moved("vcc", str(to) if value is not None else None)
        srv.vpm.forget()
        return {"how": "point", "to": str(to), "restart": False}
    if p["how"] == "move-later":
        base_dir().mkdir(parents=True, exist_ok=True)
        from .safety import write_file_safely
        write_file_safely(base_dir() / PENDING, json.dumps({"what": pid, "to": str(to), "asked": time.strftime("%Y-%m-%dT%H:%M:%S")}))
        return {"how": "move-later", "to": str(to), "restart": True}
    # move-now: Hoard uses the new folder from now on; what's there goes too when asked (a task)
    old = Path(p["from"])
    to.mkdir(parents=True, exist_ok=True)
    if pid == "edits":
        srv.cfg["edits_root"] = "" if value is None else str(to)
        srv.save_settings()
    else:
        set_moved(pid, None if value is None else str(to))
    if move and old.is_dir():
        srv.start_worker(f"Moving {old.name}", move_contents, old, to)
    return {"how": "move-now", "to": str(to), "restart": False, "moving": bool(move and old.is_dir())}


def _downloads(srv, old: Path, to: Path) -> dict:
    """The main downloads folder changed: the new one is where downloads go; the old one stays a library folder."""
    from . import libraries
    if any(j.state.get("running") or j.state.get("queue") for j in (srv.jobs, getattr(srv, "side_jobs", None)) if j):
        raise ValueError("Wait for Hoard to finish what it's doing, then try again.")
    to.mkdir(parents=True, exist_ok=True)
    folders = [str(f) for f in libraries.other_folders(srv.cfg) if not _inside(f, to)]
    srv.cfg["root"] = str(to)
    if old.is_dir() and any(old.iterdir()) and str(old) not in folders:
        folders.append(str(old))
    srv.cfg["library_folders"] = folders
    srv.save_settings()
    srv.forget_index()
    return {"how": "library", "to": str(to), "restart": False, "kept": str(old)}


def move_contents(old: Path, to: Path) -> None:
    """Move what's in one folder into another (as a task: Stop leaves what's moved where it is): each thing in it,
    unless the new folder has one of that name already."""
    from .common import log, tick
    moved = left = 0
    for entry in sorted(old.iterdir()):
        tick(f"Moving {entry.name}")
        target = to / entry.name
        if target.exists() or entry.is_symlink():
            left += 1
            continue
        shutil.move(str(entry), str(target))
        moved += 1
    log(f"Moved {moved} {'thing' if moved == 1 else 'things'} from {old} to {to}" +
        (f"; {left} left where {'it was' if left == 1 else 'they were'} (already in the new folder, or a link)" if left else ""))


# ---- as Hoard starts: Hoard's own folder, its logs or its sign-ins, moved before anything opens them

def finish_pending(say=print) -> str | None:
    """Make the move asked for last time (move-pending.json), if there is one: copy, check every file arrived, switch
    to the new place, then delete the old copy. A move that can't be made is left undone (the old place stays in use)
    and said, in move-failed.json too, for Settings to show. Returns what happened, or None."""
    pending = base_dir() / PENDING
    if not pending.is_file():
        return None
    from .app import InstanceLock
    lock = InstanceLock(data_dir() / LOCK)
    if not lock.acquire():   # (another Hoard is running and using it: the move waits until Hoard starts on its own)
        return None
    ask = stale = None
    try:
        ask = json.loads(pending.read_text("utf-8"))
        what, to = ask.get("what"), Path(str(ask.get("to") or ""))
        if what not in MOVE_LATER or not to.is_absolute():
            raise ValueError("that move isn't one Hoard makes")
        if what == "signins":
            from .browser import signins_root
            from .config import CONFIG_FILE, load_config, save_config
            cfg = load_config()
            old = signins_root(cfg)
            back = to == data_dir() / "sign-ins"

            def switch():
                """Sign in from the new place from now on."""
                cfg["profile_dir"] = "" if back else str(to)
                cfg["advanced_signin_location"] = not back
                save_config(cfg, CONFIG_FILE)
            left = _copy_then_delete(old, to, switch)
        else:
            old = data_dir() if what == "data" else logs_dir()
            back = to == (base_dir() if what == "data" else data_dir() / "logs")
            keep = KEEP if old == base_dir() or to == base_dir() else frozenset({LOCK})   # (the lock stays, held)
            left = _copy_then_delete(old, to, lambda: set_moved(what, None if back else str(to)), keep=keep)
            if what == "data":
                stale = old / LOCK   # (let go of below: the next start locks it in the new place)
        said = f"Moved {old} to {to}." + (f" {left} old {'file' if left == 1 else 'files'} couldn't be deleted: they're "
                                          f"left in {old}." if left else "")
    except Exception as e:   # (anything at all: Hoard still starts, where it was)
        said = f"Couldn't move it ({e}); it's still where it was."
        try:
            (base_dir() / "move-failed.json").write_text(json.dumps({"said": said, "asked": ask}))
        except OSError:
            pass
    finally:
        lock.release()
    if stale is not None:
        try:
            stale.unlink()
        except OSError:
            pass
    try:
        pending.unlink()
    except OSError:
        pass
    say(said)
    return said


LOCK = "running.lock"   # (app.py's: held while Hoard runs, never copied)
KEEP = frozenset({PENDING, "location.json", "move-failed.json", LOCK})   # what stays in base_dir() whatever moves


def _copy_then_delete(old: Path, to: Path, switch, keep: frozenset = frozenset()) -> int:
    """Copy a folder's contents (but keep's names) to a new or empty folder through a .part folder beside it, check
    every file arrived the size it was, put them in place, switch() to using them, then delete the old copies. A copy
    that doesn't match raises before anything switches; an old copy that can't be deleted after is left, and counted
    (the new place is in use by then). Returns how many were left."""
    if to.exists() and any(p.name not in keep for p in to.iterdir()):
        raise ValueError(f"{to} has things in it already")
    names = [p for p in old.iterdir() if p.name not in keep and not p.is_symlink()] if old.is_dir() else []
    part = to.with_name(to.name + ".part")
    if part.exists():
        shutil.rmtree(part)
    part.mkdir(parents=True)
    try:
        for p in names:
            if p.is_dir():
                shutil.copytree(p, part / p.name, symlinks=True)
            else:
                shutil.copy2(p, part / p.name)
        if size(part, cap=None) != _size_of(names):
            raise ValueError("the copy didn't match, so nothing was moved")
        to.mkdir(parents=True, exist_ok=True)
        for p in part.iterdir():
            os.replace(p, to / p.name)
    finally:
        shutil.rmtree(part, ignore_errors=True)
    switch()
    left = 0
    for p in names:
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        except OSError:
            left += 1
    return left


def _size_of(names: list[Path]) -> tuple[int, int]:
    """(files, bytes) of these things, as size() counts them."""
    files = total = 0
    for p in names:
        if p.is_dir():
            f, b = size(p, cap=None)
            files, total = files + f, total + b
        else:
            files, total = files + 1, total + p.stat().st_size
    return files, total
