"""Hoard's Local sync folder in Windows' File Explorer (issue #410): a folder icon of its own, and Hoard in Explorer's
right-click menu.

The icon. When a sync folder is chosen, Hoard puts its icon (hoard/web/icons/sync-folder.ico: the heap in a gold
folder, scripts/make_icons.py) in it as a hidden .hoard-folder.ico, and a desktop.ini that points to it, with a tip
saying what the folder is for. Explorer reads a folder's desktop.ini only when the folder is marked read-only (which
for a folder means only "customised": what's in it can still be changed), so Hoard marks it, and notes in the
desktop.ini whether it was marked before, to put it back as it was. A desktop.ini that isn't Hoard's (another
program's, or yours) is never written over. Both files are left out by the sync folder's look (a name starting with
".", and desktop.ini, as localsync and local.SKIP have them), so neither is ever added to Local.

The menu (in this account's own registry: HKEY_CURRENT_USER\\Software\\Classes, so no administrator is needed):
    Add to Hoard           on any file or folder: a file is copied into the sync folder, a folder listed in Local where
                           it is (as Add to Local's "list it where it is")
    Sync with Hoard now    on the sync folder (and inside it): Hoard looks at it at once
    Open in Hoard          on the sync folder (and inside it): Hoard, at Local
Each runs Hoard (the Tauri shell) with --hoard-add <path>, --hoard-sync-now or --hoard-open-local. The shell tells its
Hoard in its hello; a second start hands them to the Hoard that's running over its signed /api/show (as a hoard://
link is), never as a hoard:// link, which any web page can send. Hoard then comes to the front at Local and says what
it did. Windows 11 shows them under "Show more options" (its short menu is only for packaged apps).

Settings' "Show it in File Explorer" (the explorer setting) turns the icon and the menu off; turning the sync folder
off takes them away too, and so does uninstalling: Hoard notes the folder with its icon in the registry
(NOTE_KEY), for the uninstaller (shell/installer/hooks.nsh), which never runs Hoard.

Everything here does nothing off Windows; macOS and Linux are issue #411."""
from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import sys
from pathlib import Path

ICON_NAME = ".hoard-folder.ico"   # in the sync folder (its "." keeps it out of the sync folder's look)
INI_NAME = "desktop.ini"
MARK = "; Hoard's sync folder (issue #410): Hoard wrote this, and takes it away when this stops being its sync folder."
READONLY_WAS = "; hoard-readonly-before="
TIP = "Hoard's sync folder: what you put here is added to Hoard's Local."
ICON_SOURCE = Path(__file__).resolve().parent / "web" / "icons" / "sync-folder.ico"
ROOT = r"Software\Classes"
NOTE_KEY = r"Software\Hoard\Explorer"   # SyncFolder: the folder with Hoard's icon, for the uninstaller
KEYS = {   # (key under ROOT, its menu words, the argument it runs Hoard with, whether it's only the sync folder's)
    "add_file": (r"*\shell\Hoard.Add", "Add to Hoard", "--hoard-add \"%1\"", False),
    "add_folder": (r"Directory\shell\Hoard.Add", "Add to Hoard", "--hoard-add \"%1\"", False),
    "sync": (r"Directory\shell\Hoard.SyncNow", "Sync with Hoard now", "--hoard-sync-now \"%V\"", True),
    "sync_inside": (r"Directory\Background\shell\Hoard.SyncNow", "Sync with Hoard now", "--hoard-sync-now \"%V\"", True),
    "open": (r"Directory\shell\Hoard.OpenLocal", "Open in Hoard", "--hoard-open-local", True),
    "open_inside": (r"Directory\Background\shell\Hoard.OpenLocal", "Open in Hoard", "--hoard-open-local", True),
}
FILE_ATTRIBUTE_READONLY, FILE_ATTRIBUTE_HIDDEN, FILE_ATTRIBUTE_SYSTEM = 0x1, 0x2, 0x4
FILE_ATTRIBUTE_NORMAL = 0x80   # (only on its own: none of the others)
SETTABLE = 0x3127   # the attributes a program may set: read-only, hidden, system, archive, temporary, offline, not indexed
INVALID = 0xFFFFFFFF


def here() -> bool:
    """Whether this is Windows, where Explorer reads all this."""
    return sys.platform == "win32"


class Windows:
    """What this module asks of Windows: a file's attributes, telling Explorer a folder changed, and the registry.
    Tests give a stand-in."""

    def attributes(self, path: Path) -> int | None:
        """A file's or folder's attributes, or None when it can't be read."""
        import ctypes
        got = ctypes.windll.kernel32.GetFileAttributesW(str(path)) & 0xFFFFFFFF   # (a DWORD, which ctypes reads signed)
        return None if got == INVALID else got

    def set_attributes(self, path: Path, value: int) -> None:
        """Set a file's or folder's attributes."""
        import ctypes
        if not ctypes.windll.kernel32.SetFileAttributesW(str(path), value):
            raise OSError(f"couldn't set the attributes of {path}")

    def changed(self, folder: Path) -> None:
        """Tell Explorer the folder changed, so it shows its icon now, not after the next restart."""
        import ctypes
        SHCNE_UPDATEITEM, SHCNF_PATHW = 0x2000, 0x0005
        ctypes.windll.shell32.SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW, str(folder), None)

    def registry(self):
        """The winreg module."""
        import winreg
        return winreg

    def long_path(self, path: str) -> str:
        """A path with its folders' short (8.3) names, such as RUNNER~1, written out long, as Explorer shows it.
        Links and junctions aren't followed (Explorer shows the path through them)."""
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetLongPathNameW(str(path), buf, len(buf))
        return buf.value if 0 < n < len(buf) else str(path)

    def ui_language(self) -> str | None:
        """Windows' own language, as a locale name ("ja-JP"), or None."""
        import ctypes
        buf = ctypes.create_unicode_buffer(85)
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return buf.value if ctypes.windll.kernel32.LCIDToLocaleName(langid, buf, 85, 0) else None


def _ini(readonly_before: bool) -> str:
    """The sync folder's desktop.ini: its icon and tip, with Hoard's mark."""
    return (f"{MARK}\r\n{READONLY_WAS}{int(readonly_before)}\r\n[.ShellClassInfo]\r\nIconResource={ICON_NAME},0\r\n"
            f"InfoTip={TIP}\r\n")


def _ours(ini: Path) -> str | None:
    """The text of a desktop.ini Hoard wrote, or None (none there, or not Hoard's)."""
    try:
        text = ini.read_text("utf-8", errors="replace") if ini.is_file() and not ini.is_symlink() else None
    except OSError:
        return None
    return text if text is not None and text.startswith(MARK) else None


def mark(folder, win: Windows | None = None) -> bool:
    """Give the sync folder Hoard's icon (see the module's notes). False when it can't be (another desktop.ini there,
    a folder that isn't, or Windows refused); Hoard carries on without it."""
    win = win or Windows()
    folder = Path(folder)
    ini, icon = folder / INI_NAME, folder / ICON_NAME
    if not folder.is_dir() or folder.is_symlink():
        return False
    mine = _ours(ini)
    if (ini.exists() or ini.is_symlink()) and mine is None:
        return False   # (someone else's, or a link: left as it is)
    try:
        attrs = win.attributes(folder)
        if attrs is None:
            return False
        before = (READONLY_WAS + "1") in mine if mine else bool(attrs & FILE_ATTRIBUTE_READONLY)
        for f in (ini, icon):   # (Hoard's own from before, or a link where its icon goes: made again, from nothing)
            if f.is_symlink():
                f.unlink()
            elif f.exists():
                win.set_attributes(f, FILE_ATTRIBUTE_NORMAL)   # (a hidden, system file can't be replaced)
                f.unlink()
        with open(icon, "xb") as w, open(ICON_SOURCE, "rb") as r:   # (each made new: never through a link)
            shutil.copyfileobj(r, w)
        with open(ini, "x", encoding="utf-8", newline="") as w:
            w.write(_ini(before))
        for f in (ini, icon):
            win.set_attributes(f, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
        win.set_attributes(folder, (attrs & SETTABLE) | FILE_ATTRIBUTE_READONLY)
        win.changed(folder)
        return True
    except OSError:
        return False


def unmark(folder, win: Windows | None = None) -> bool:
    """Take Hoard's icon off a folder that's no longer the sync folder: its desktop.ini and icon file, and the
    folder's read-only mark when Hoard put it there. A desktop.ini that isn't Hoard's is left. False when there was
    nothing of Hoard's, or it couldn't be taken off."""
    win = win or Windows()
    folder = Path(folder)
    ini, icon = folder / INI_NAME, folder / ICON_NAME
    mine = _ours(ini)
    if mine is None:
        return False
    try:
        for f in (ini, icon):
            if f.exists() and not f.is_symlink():
                win.set_attributes(f, FILE_ATTRIBUTE_NORMAL)
                f.unlink()
        attrs = win.attributes(folder)
        if attrs is not None and (READONLY_WAS + "0") in mine:
            win.set_attributes(folder, (attrs & SETTABLE & ~FILE_ATTRIBUTE_READONLY) or FILE_ATTRIBUTE_NORMAL)
        win.changed(folder)
        return True
    except OSError:
        return False


def _set_key(reg, path: str, words: str, command: str, icon: str, applies_to: str | None) -> None:
    """One right-click option: its words, Hoard's icon beside them, where it shows, and what it runs."""
    with reg.CreateKey(reg.HKEY_CURRENT_USER, f"{ROOT}\\{path}") as key:
        reg.SetValueEx(key, "MUIVerb", 0, reg.REG_SZ, words)
        reg.SetValueEx(key, "Icon", 0, reg.REG_SZ, icon)
        if applies_to:
            reg.SetValueEx(key, "AppliesTo", 0, reg.REG_SZ, applies_to)
        else:
            try:
                reg.DeleteValue(key, "AppliesTo")
            except OSError:
                pass
    with reg.CreateKey(reg.HKEY_CURRENT_USER, f"{ROOT}\\{path}\\command") as key:
        reg.SetValueEx(key, "", 0, reg.REG_SZ, command)


def _delete_tree(reg, path: str) -> None:
    """A key and what's under it (the registry deletes only empty keys)."""
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, path, 0, reg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = reg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(reg, f"{path}\\{child}")
        reg.DeleteKey(reg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


def language(cfg: dict, win: Windows) -> str:
    """The language for the menu's words: the one chosen in Settings, or Windows' own when that's the system's."""
    from . import i18n
    d = cfg.get("display") if isinstance(cfg.get("display"), dict) else {}
    chosen = i18n.setting(d.get("language"))
    if chosen != "system":
        return chosen
    try:
        return i18n.from_header(win.ui_language())
    except (OSError, AttributeError, ValueError):
        return "en"


def register(exe, sync_folder, win: Windows | None = None, lang: str = "en") -> bool:
    """Put Hoard's options in Explorer's right-click menu for this account: Add to Hoard everywhere, and Sync with Hoard
    now and Open in Hoard on the sync folder (Explorer's AppliesTo, by its full path), in lang. False when it can't
    be."""
    from . import i18n
    win = win or Windows()
    exe, sync = str(exe), str(sync_folder)
    if not exe or not sync or '"' in exe or '"' in sync:
        return False
    reg = win.registry()
    try:
        sync = win.long_path(sync)   # (Explorer matches AppliesTo against the long name it shows)
    except (OSError, AttributeError, ValueError):
        pass
    if '"' in sync:
        return False
    only_sync = f'System.ItemPathDisplay:="{sync}"'
    try:
        for path, words, arg, sync_only in KEYS.values():
            _set_key(reg, path, i18n.say(lang, words), f'"{exe}" {arg}', f'"{exe}",0', only_sync if sync_only else None)
        return True
    except OSError:
        return False


def unregister(win: Windows | None = None) -> None:
    """Take Hoard's options out of Explorer's right-click menu (they're gone with no error when they aren't there)."""
    reg = (win or Windows()).registry()
    for path, _words, _arg, _sync in KEYS.values():
        _delete_tree(reg, f"{ROOT}\\{path}")


def _note(win: Windows, folder: str | None) -> None:
    """Note the folder with Hoard's icon for the uninstaller (NOTE_KEY), or that there's none."""
    try:
        reg = win.registry()
        if folder:
            with reg.CreateKey(reg.HKEY_CURRENT_USER, NOTE_KEY) as key:
                reg.SetValueEx(key, "SyncFolder", 0, reg.REG_SZ, folder)
        else:
            _delete_tree(reg, NOTE_KEY)
            reg.DeleteKey(reg.HKEY_CURRENT_USER, NOTE_KEY.rsplit("\\", 1)[0])   # (Software\Hoard, when that leaves it empty)
    except OSError:
        pass


def on(cfg: dict) -> bool:
    """Whether Settings has Hoard shown in File Explorer (the explorer setting, on until it's turned off)."""
    return cfg.get("explorer", True) is not False


def apply(cfg: dict, exe: str | None, was: str | None = None, win: Windows | None = None) -> dict:
    """Make Explorer show what Hoard's settings say: the icon on the sync folder (and off the one it was, was), and the
    right-click options while there's a sync folder, Settings shows Hoard in Explorer (on), and Hoard knows the program
    to run (the Tauri shell's, from its hello). {"icon": bool, "menu": bool}: what's in place now."""
    if not here() and win is None:
        return {"icon": False, "menu": False}
    win = win or Windows()
    sync = str(cfg.get("local_sync") or "").strip()
    if was and os.path.normcase(str(was)) != os.path.normcase(sync):
        unmark(was, win)
    icon = False
    if sync and on(cfg):
        icon = mark(sync, win)
    elif sync:
        unmark(sync, win)
    _note(win, sync if icon else None)
    menu = False
    if not (sync and on(cfg)):
        unregister(win)
    elif exe:
        menu = register(exe, sync, win, language(cfg, win))
    # (else a Hoard started without its window, which knows no program to run: the menu is left as it is)
    return {"icon": icon, "menu": menu}


# ---- what the menu asks of the Hoard that's running (from a second start, over /api/show)

ACTIONS = ("add", "sync", "local")
MAX_ACTIONS = 20


def _full_path(p) -> bool:
    """Whether p is a full path, as Explorer gives one."""
    return isinstance(p, str) and 0 < len(p) <= 1000 and "\x00" not in p and os.path.isabs(p)


def actions(given) -> list[dict]:
    """The menu's requests, checked: [{"do": "add", "path": a full path}, {"do": "sync", "path": the folder it was
    chosen on, if it says}, {"do": "local"}], at most MAX_ACTIONS (Explorer starts Hoard once for each file chosen)."""
    out = []
    for a in given if isinstance(given, list) else []:
        if not isinstance(a, dict) or a.get("do") not in ACTIONS:
            continue
        if a["do"] == "add":
            if _full_path(a.get("path")):
                out.append({"do": "add", "path": a["path"]})
        elif a["do"] == "sync" and "path" in a:
            if _full_path(a["path"]):
                out.append({"do": "sync", "path": a["path"]})
        else:
            out.append({"do": a["do"]})
    return out[:MAX_ACTIONS]


def do(srv, action: dict) -> dict | None:
    """One of the menu's requests (checked by actions()), done. What Hoard says about it, for its page, as a code with
    what goes in its words ({"said": "copied", "name": ...}: shared.js has the words); None: nothing to say."""
    from .config import feature_on
    if action["do"] in ("add", "sync") and not feature_on(srv.cfg, "local"):
        return {"said": "local-off"}   # (Local turned off in Settings, Features, issue #422: nothing's added)
    if action["do"] == "add":
        return add(srv, action["path"])
    if action["do"] == "sync":
        from . import localsync
        sync = str(srv.cfg.get("local_sync") or "").strip()
        if not sync:
            return {"said": "no-sync"}
        if action.get("path") and not _inside(Path(action["path"]), Path(sync)):
            return {"said": "not-sync"}   # (Explorer showed it on another folder)
        srv.start_worker("Look at the Local sync folder", localsync.tick, srv)
        return {"said": "looking"}
    return None   # ("local": Hoard at Local, where every request ends)


def _inside(path: Path, folder: Path) -> bool:
    """Whether path is the folder or in it."""
    try:
        p, f = path.resolve(), folder.resolve()
    except OSError:
        return False
    return p == f or f in p.parents


def _place(made: Path, out: Path) -> None:
    """A file made in full put at out in one step, never over a file there (FileExistsError)."""
    try:
        os.link(made, out)   # (there whole, or not at all)
    except FileExistsError:
        raise
    except OSError:   # (a drive that can't link, FAT say: a rename, which on Windows never replaces a file)
        if os.name != "nt" and os.path.lexists(out):
            raise FileExistsError(out) from None
        os.rename(made, out)
        return
    os.unlink(made)


def _copy_new(source: Path, folder: Path) -> Path:
    """Copy a file into folder under its own name, or "name (2)" and on when that's taken: never over a file there.
    It's copied under a hidden name first (one starting with ".", which the sync folder's look leaves out), so the
    look never takes in a file half copied, and one that couldn't be copied leaves nothing behind."""
    made = folder / f".hoard-adding-{secrets.token_hex(6)}"
    try:
        with open(made, "xb") as w, open(source, "rb") as r:
            shutil.copyfileobj(r, w, 1 << 20)
        with contextlib.suppress(OSError):
            shutil.copystat(source, made)   # (its dates, as the file's own)
        for n in range(1, 1000):
            out = folder / (source.name if n == 1 else f"{source.stem} ({n}){source.suffix}")
            try:
                _place(made, out)
            except FileExistsError:
                continue
            return out
        raise OSError(f"no free name for {source.name} in the sync folder")
    finally:
        with contextlib.suppress(OSError):
            made.unlink()   # (gone already once it's in place)


def add(srv, path: str) -> dict:
    """Add to Hoard (the menu's): a file is copied into the sync folder (never over one there: "name (2)"), which Hoard
    then looks at; a folder (or a file, when there's no sync folder) is added to Local as Add to Local does, a folder
    listed where it is. Either way only what Add to Local takes (local.check_source: not a link, nothing in Hoard's
    downloads folder). What Hoard says about it (do's codes)."""
    from . import local, localsync
    from .config import root_dir
    p = Path(path)
    name = p.name or str(p)
    if not p.exists():
        return {"said": "gone", "name": name}
    sync = str(srv.cfg.get("local_sync") or "").strip()
    folder = Path(sync) if sync else None
    if folder and _inside(p, folder):
        return {"said": "there", "name": name}
    copy = not p.is_dir()
    try:
        local.check_source(root_dir(srv.cfg), str(p), copy)
    except ValueError as e:
        return {"said": "refused", "name": name, "why": str(e)}
    if folder and folder.is_dir() and p.is_file():
        if p.stat().st_size > localsync.MAX_FILE:
            return {"said": "big", "name": name, "mb": localsync.MAX_FILE // (1024 * 1024)}
        out = _copy_new(p, folder)
        srv.start_worker("Look at the Local sync folder", localsync.tick, srv)
        return {"said": "copied", "name": out.name}
    started = srv.jobs.start("add-local", [], local={"path": str(p), "name": "", "creator": "", "note": "",
                                                      "copy": copy, "depth": 0})
    return {"said": {"started": "adding", "queued": "queued"}.get(started, "waiting"), "name": name}
