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
Each runs Hoard (the Tauri shell) with --hoard-add <path>, --hoard-sync-now or --hoard-open-local, which a second start
hands to the Hoard that's running over its signed /api/show (as a hoard:// link is): never as a hoard:// link, which
any web page can send. Windows 11 shows them under "Show more options" (its short menu is only for packaged apps).
Settings turns the menu off; turning the sync folder off takes the menu and the icon away, and so does uninstalling.

Everything here does nothing off Windows; macOS and Linux are issue #411."""
from __future__ import annotations

import os
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
KEYS = {   # (key under ROOT, its menu words, the argument it runs Hoard with, whether it's only the sync folder's)
    "add_file": (r"*\shell\Hoard.Add", "Add to Hoard", "--hoard-add \"%1\"", False),
    "add_folder": (r"Directory\shell\Hoard.Add", "Add to Hoard", "--hoard-add \"%1\"", False),
    "sync": (r"Directory\shell\Hoard.SyncNow", "Sync with Hoard now", "--hoard-sync-now", True),
    "sync_inside": (r"Directory\Background\shell\Hoard.SyncNow", "Sync with Hoard now", "--hoard-sync-now", True),
    "open": (r"Directory\shell\Hoard.OpenLocal", "Open in Hoard", "--hoard-open-local", True),
    "open_inside": (r"Directory\Background\shell\Hoard.OpenLocal", "Open in Hoard", "--hoard-open-local", True),
}
FILE_ATTRIBUTE_READONLY, FILE_ATTRIBUTE_HIDDEN, FILE_ATTRIBUTE_SYSTEM = 0x1, 0x2, 0x4
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
        got = ctypes.windll.kernel32.GetFileAttributesW(str(path))
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
    if ini.exists() and mine is None:
        return False   # (someone else's: left as it is)
    try:
        attrs = win.attributes(folder)
        if attrs is None:
            return False
        before = (READONLY_WAS + "1") in mine if mine else bool(attrs & FILE_ATTRIBUTE_READONLY)
        for f in (ini, icon):   # (a hidden, system file can't be written over until it's plain again)
            if f.exists() and not f.is_symlink():
                win.set_attributes(f, 0x80)   # FILE_ATTRIBUTE_NORMAL
        if icon.is_symlink():
            icon.unlink()
        shutil.copyfile(ICON_SOURCE, icon)
        if ini.is_symlink():
            ini.unlink()
        ini.write_text(_ini(before), encoding="utf-8", newline="")
        for f in (ini, icon):
            win.set_attributes(f, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
        win.set_attributes(folder, attrs | FILE_ATTRIBUTE_READONLY)
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
                win.set_attributes(f, 0x80)
                f.unlink()
        attrs = win.attributes(folder)
        if attrs is not None and (READONLY_WAS + "0") in mine:
            win.set_attributes(folder, attrs & ~FILE_ATTRIBUTE_READONLY)
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


def register(exe, sync_folder, win: Windows | None = None) -> bool:
    """Put Hoard's options in Explorer's right-click menu for this account: Add to Hoard everywhere, and Sync with Hoard
    now and Open in Hoard on the sync folder (Explorer's AppliesTo, by its full path). False when it can't be."""
    win = win or Windows()
    exe, sync = str(exe), str(sync_folder)
    if not exe or not sync or '"' in exe or '"' in sync:
        return False
    reg = win.registry()
    only_sync = f'System.ItemPathDisplay:="{sync}"'
    try:
        for path, words, arg, sync_only in KEYS.values():
            _set_key(reg, path, words, f'"{exe}" {arg}', f'"{exe}",0', only_sync if sync_only else None)
        return True
    except OSError:
        return False


def unregister(win: Windows | None = None) -> None:
    """Take Hoard's options out of Explorer's right-click menu (they're gone with no error when they aren't there)."""
    reg = (win or Windows()).registry()
    for path, _words, _arg, _sync in KEYS.values():
        _delete_tree(reg, f"{ROOT}\\{path}")


def apply(cfg: dict, exe: str | None, was: str | None = None, win: Windows | None = None) -> dict:
    """Make Explorer show what Hoard's settings say: the icon on the sync folder (and off the one it was, was), and the
    right-click options while there's a sync folder, the menu isn't turned off (explorer_menu) and Hoard knows the
    program to run (the Tauri shell's, from its hello). {"icon": bool, "menu": bool}: what's in place now."""
    if not here() and win is None:
        return {"icon": False, "menu": False}
    win = win or Windows()
    sync = str(cfg.get("local_sync") or "").strip()
    if was and os.path.normcase(str(was)) != os.path.normcase(sync):
        unmark(was, win)
    icon = mark(sync, win) if sync else False
    if sync and exe and cfg.get("explorer_menu", True) is not False:
        menu = register(exe, sync, win)
    else:
        unregister(win)
        menu = False
    return {"icon": icon, "menu": menu}


# ---- what the menu asks of the Hoard that's running (from a second start, over /api/show)

ACTIONS = ("add", "sync", "local")
MAX_ACTIONS = 20


def actions(given) -> list[dict]:
    """The menu's requests, checked: [{"do": "add", "path": a full path}, {"do": "sync"}, {"do": "local"}], at most
    MAX_ACTIONS (Explorer starts Hoard once for each file chosen)."""
    out = []
    for a in given if isinstance(given, list) else []:
        if not isinstance(a, dict) or a.get("do") not in ACTIONS:
            continue
        if a["do"] == "add":
            p = a.get("path")
            if not isinstance(p, str) or not 0 < len(p) <= 1000 or "\x00" in p or not os.path.isabs(p):
                continue
            out.append({"do": "add", "path": p})
        else:
            out.append({"do": a["do"]})
    return out[:MAX_ACTIONS]


def add(srv, path: str) -> str:
    """Add to Hoard (the menu's): a file copied into the sync folder (never over one there: "name (2)"), which Hoard
    then looks at; a folder (or a file, with no sync folder) added to Local as Add to Local does, a folder listed where
    it is. What's said in Hoard, in words."""
    from . import local, localsync
    from .config import root_dir
    p = Path(path)
    if not p.exists():
        return f"{p.name} isn't there any more."
    sync = str(srv.cfg.get("local_sync") or "").strip()
    if sync and p.is_file() and not p.is_symlink():
        folder = Path(sync)
        if p.resolve().parent == folder.resolve():
            return f"{p.name} is in the sync folder already."
        if p.stat().st_size > localsync.MAX_FILE:
            return f"{p.name} is over {localsync.MAX_FILE // (1024 * 1024)} MB, so the sync folder doesn't take it."
        out, n = folder / p.name, 2
        while out.exists():
            out, n = folder / f"{p.stem} ({n}){p.suffix}", n + 1
        shutil.copy2(p, out)
        srv.start_worker("Look at the Local sync folder", localsync.tick, srv)
        return f"{p.name} is in the sync folder: Hoard adds it to Local."
    copy = not p.is_dir()
    local.check_source(root_dir(srv.cfg), str(p), copy)   # (ValueError: said in Hoard)
    started = srv.jobs.start("add-local", [], local={"path": str(p), "name": "", "creator": "", "note": "",
                                                      "copy": copy, "depth": 0})
    return f"Adding {p.name} to Local." if started else f"{p.name} is waiting its turn already."
