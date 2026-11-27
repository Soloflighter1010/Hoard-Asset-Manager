"""Hoard's Local sync folder in macOS's Finder and in Linux's file managers (issue #411), as hoard/explorer.py has it in
Windows' File Explorer (#410): a folder icon of its own, and Hoard in the right-click menu.

The icon. Hoard puts its folder icon (hoard/web/icons/sync-folder.png, scripts/make_icons.py) in the sync folder as a
hidden .hoard-folder.png, and has the file manager show it:
    Finder        its own custom-icon call (NSWorkspace's setIcon:forFile:options:, through osascript), which keeps the
                  picture in an Icon\\r file in the folder (Finder hides it)
    GNOME, Nemo   the folder's metadata::custom-icon (gio set), which GVfs keeps, not the folder
    Dolphin       the folder's .directory file, whose Icon= is that picture
A folder with a custom icon that isn't Hoard's (Finder's Icon\\r with no .hoard-folder.png beside it, another
metadata::custom-icon, another Icon= in its .directory) keeps it. Each of these files is left out of the sync folder's
look (a name starting with ".", and Icon\\r: local.SKIP), so none is ever added to Local.

The menu, in this account's own folders (no administrator):
    Add to Hoard          on any file or folder
    Sync with Hoard now   on a folder, or inside one (Hoard says so when it isn't the sync folder)
    Open in Hoard         on a folder, or inside one
as
    Finder        Quick Actions (an Automator workflow each, in ~/Library/Services, running a shell script)
    GNOME Files   scripts (its right-click Scripts), in ~/.local/share/nautilus/scripts
    Dolphin       service menus, in ~/.local/share/kio/servicemenus
    Nemo          actions, in ~/.local/share/nemo/actions
for each file manager that's installed. Each runs one small script of Hoard's (hoard-files, in Hoard's app-data
folder), which starts Hoard with --hoard-add <path>, --hoard-sync-now <folder> or --hoard-open-local, as Explorer's
options do (the Tauri shell hands them to the Hoard that's running). What it starts is the window's own program, or
on a Mac its app (open -n, so Finder isn't kept waiting), the AppImage (the window's own program is in a mount that
goes when it ends), or the Flatpak (flatpak run). When that's gone (Hoard uninstalled, or the AppImage moved), the
script takes Hoard's options away instead, so nothing is left offering Hoard after it; Hoard puts them back when it
next starts.

The Flatpak's sandbox keeps it from GVfs's metadata: there GNOME Files and Nemo don't show the icon, and Settings says
so (Dolphin's .directory still shows it). The sandbox doesn't see the computer's programs either, so there a file
manager counts as installed when its own folder is in your home folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ICON_NAME = ".hoard-folder.png"   # in the sync folder (its "." keeps it out of the sync folder's look)
ICON_SOURCE = Path(__file__).resolve().parent / "web" / "icons" / "sync-folder.png"
FINDER_ICON = "Icon\r"   # where Finder keeps a folder's custom icon, in the folder
DIRECTORY = ".directory"   # Dolphin's settings for a folder
MARK = "# Hoard's sync folder (issue #411): Hoard wrote this, and takes it away when this stops being its sync folder."
HELPER = "hoard-files"   # the script every option runs, in Hoard's app-data folder (file-manager/)
FLATPAK_ID = "io.github.soloflighter1010.Hoard"
# (what it asks Hoard for, its words, whether it's only on folders, its Quick Action's file name)
OPTIONS = (("add", "Add to Hoard", False, "Hoard - Add"),
           ("sync", "Sync with Hoard now", True, "Hoard - Sync now"),
           ("local", "Open in Hoard", True, "Hoard - Open"))
DOLPHIN = ("hoard-add.desktop", "hoard-folder.desktop")
NEMO = ("hoard-add", "hoard-sync", "hoard-sync-here", "hoard-open", "hoard-open-here")
PBS = "/System/Library/CoreServices/pbs"   # (tells Finder's menu at once that Quick Actions changed)
FINDER_PRINTS = "finder-icons.json"   # in file-manager/: the icon Hoard put on a folder in Finder, by its fingerprint


def kind() -> str | None:
    """Which file manager this is about: "finder" on a Mac, "files" on Linux (GNOME Files, Dolphin, Nemo), None
    elsewhere (Windows is hoard/explorer.py's)."""
    if sys.platform == "darwin":
        return "finder"
    if sys.platform.startswith("linux"):
        return "files"
    return None


class System:
    """What this module asks of the computer: running a program, where things are, whether it's the Flatpak. Tests give
    a stand-in."""

    def __init__(self, kind_: str | None = None):
        self.kind = kind_ or kind()

    def run(self, args: list[str], timeout: float = 30) -> subprocess.CompletedProcess | None:
        """A program, run with no shell; None when it can't be run, or takes too long."""
        try:
            return subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout,
                                  stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None

    def which(self, name: str) -> str | None:
        """Where a program is, or None when it isn't installed."""
        return shutil.which(name)

    def home(self) -> Path:
        """This account's home folder."""
        return Path.home()

    def _xdg(self, name: str, default: str) -> Path:
        """One of the XDG folders (in the Flatpak, the computer's, not the sandbox's own)."""
        given = os.environ.get(f"HOST_{name}" if self.flatpak() else name)
        return Path(given) if given and os.path.isabs(given) else self.home() / default

    def data_home(self) -> Path:
        """Where this account's programs keep their data (XDG_DATA_HOME)."""
        return self._xdg("XDG_DATA_HOME", ".local/share")

    def config_home(self) -> Path:
        """Where this account's programs keep their settings (XDG_CONFIG_HOME)."""
        return self._xdg("XDG_CONFIG_HOME", ".config")

    def flatpak(self) -> bool:
        """Is this Hoard the Flatpak?"""
        from .paths import in_flatpak
        return in_flatpak()

    def helper_dir(self) -> Path:
        """Where Hoard's script for the options goes: file-manager/ in Hoard's app-data folder."""
        from .paths import data_dir
        return data_dir() / "file-manager"

    def environ(self) -> dict:
        """The environment this Hoard was started with (where an AppImage is, say)."""
        return dict(os.environ)

    def finder_print(self, folder: Path) -> str | None:
        """A fingerprint of the custom icon Finder shows on a folder (its Icon\\r file's resource fork, where Finder
        keeps the picture), or None when it has none."""
        try:
            return hashlib.sha256((folder / FINDER_ICON / "..namedfork" / "rsrc").read_bytes()).hexdigest()
        except OSError:
            return None


# ---- the icon

def _ours(folder: Path) -> bool:
    """Has Hoard put its icon on this folder (its picture is there)?"""
    icon = folder / ICON_NAME
    return icon.is_file() and not icon.is_symlink()


def _put_picture(folder: Path) -> Path:
    """Hoard's folder icon, as a hidden .hoard-folder.png in the folder: made new, never through a link."""
    icon = folder / ICON_NAME
    if icon.is_symlink() or icon.exists():
        icon.unlink()
    with open(icon, "xb") as w, open(ICON_SOURCE, "rb") as r:
        shutil.copyfileobj(r, w)
    return icon


# Finder's own call for a folder's icon (an image's path to set it, none to take it off), in JavaScript for Automation:
# osascript is on every Mac, and Hoard brings no Objective-C bridge of its own. The paths come as arguments, never as
# part of the script.
FINDER_SET_ICON = ('function run(argv) { ObjC.import("AppKit"); var image = null; '
                   'if (argv.length > 1) { image = $.NSImage.alloc.initWithContentsOfFile(argv[1]); '
                   'if (image.isNil()) { return "no"; } } '
                   'return $.NSWorkspace.sharedWorkspace.setIconForFileOptions(image, argv[0], 0) ? "yes" : "no"; }')


def _finder_icon(system: System, folder: Path, image: Path | None) -> bool:
    """Set (image) or take off (None) a folder's custom icon in Finder."""
    done = system.run(["osascript", "-l", "JavaScript", "-e", FINDER_SET_ICON, str(folder),
                       *([str(image)] if image else [])])
    return bool(done) and done.returncode == 0 and done.stdout.strip() == "yes"


def _finder_prints(system: System, changes: dict | None = None) -> dict:
    """The fingerprints of the icons Hoard put on folders in Finder ({folder: fingerprint}), with changes made to them
    (a fingerprint, or None to forget a folder's). Hoard takes an icon off only while it's still the one it put on: one
    you put on the folder since stays."""
    from .safety import write_file_safely
    path = system.helper_dir() / FINDER_PRINTS
    try:
        kept = json.loads(path.read_text("utf-8")) if path.is_file() and not path.is_symlink() else {}
    except (OSError, ValueError):
        kept = {}
    kept = {k: v for k, v in kept.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(kept, dict) else {}
    before = dict(kept)
    for folder, value in (changes or {}).items():
        if value:
            kept[folder] = value
        else:
            kept.pop(folder, None)
    if kept != before:
        try:
            if kept:
                write_file_safely(path, json.dumps(kept, ensure_ascii=False, indent=1))
            else:
                path.unlink(missing_ok=True)
        except OSError:
            pass
    return kept


def _finder_still_ours(system: System, folder: Path) -> bool:
    """Is the icon Finder shows on this folder still the one Hoard put on it (or is there no note of what that was)?"""
    kept = _finder_prints(system).get(str(folder))
    return kept is None or system.finder_print(folder) == kept


def _gvfs_icon(system: System, folder: Path):
    """The folder's metadata::custom-icon (GNOME Files', Nemo's): its value, None when it has none, False when it
    can't be read (no gio, or the Flatpak, whose sandbox keeps it from GVfs)."""
    if system.flatpak() or not system.which("gio"):
        return False
    got = system.run(["gio", "info", "--attributes=metadata::custom-icon", str(folder)])
    if not got or got.returncode:
        return False
    for line in got.stdout.splitlines():
        key, _, value = line.strip().partition(": ")
        if key == "metadata::custom-icon":
            return value.strip() or None
    return None


def _kde_read(folder: Path) -> list[str] | None:
    """The .directory file's lines, [] when there's none, None when it can't be Hoard's to change (a link, or not a
    file)."""
    path = folder / DIRECTORY
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return None
    try:
        return path.read_text("utf-8", errors="replace").splitlines() if path.exists() else []
    except OSError:
        return None


def _kde_hoards(icon: Path) -> set[str]:
    """Hoard's lines in a .directory file: its mark, and its Icon= and Comment= (Dolphin may drop the mark when it
    writes the file itself, so the other two are known by what they say)."""
    from .explorer import TIP
    return {MARK, f"Icon={icon}", f"Comment={TIP}"}


def _kde_section(lines: list[str]) -> tuple[int, int] | None:
    """Where the [Desktop Entry] section is (its heading's line, and the line after its last), or None."""
    heads = [i for i, ln in enumerate(lines) if ln.strip().startswith("[")]
    for i in heads:
        if lines[i].strip() == "[Desktop Entry]":
            return i, next((j for j in heads if j > i), len(lines))
    return None


def _kde_write(folder: Path, lines: list[str]) -> None:
    """Write the .directory file (keeping who may read it, as it was: anyone, when it's new), or take it away when
    nothing but headings is left in it."""
    from .safety import write_file_safely
    path = folder / DIRECTORY
    if not [ln for ln in lines if ln.strip() and not ln.strip().startswith("[")]:
        path.unlink(missing_ok=True)
        return
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        mode = 0o644
    write_file_safely(path, "\n".join(lines) + "\n", root=folder)
    path.chmod(mode)


def _kde_mark(folder: Path, icon: Path) -> bool:
    """Dolphin's icon for the folder: Hoard's Icon= (and its tip) in the folder's .directory, beside what Dolphin keeps
    there itself. A .directory that gives the folder another icon is left as it is."""
    from .explorer import TIP
    lines = _kde_read(folder)
    if lines is None or any(c in str(icon) for c in "\n\r\x00"):   # (a line break would start another line in it)
        return False
    rest = [ln for ln in lines if ln.strip() not in _kde_hoards(icon)]
    at = _kde_section(rest)
    entry = rest[at[0] + 1:at[1]] if at else []
    if any(ln.strip().startswith("Icon=") for ln in entry):
        return False   # (another icon, someone else's)
    ours = [f"Icon={icon}"] + ([] if any(ln.strip().startswith("Comment=") for ln in entry) else [f"Comment={TIP}"])
    if at:
        rest = rest[:at[0] + 1] + ours + rest[at[0] + 1:]
    else:
        rest = ["[Desktop Entry]"] + ours + ([""] if rest else []) + rest
    try:
        _kde_write(folder, [MARK] + rest)
        return True
    except OSError:
        return False


def _kde_unmark(folder: Path, icon: Path) -> bool:
    """Take Hoard's lines out of the folder's .directory (and the file, when that leaves nothing in it). False when
    none were there."""
    lines = _kde_read(folder)
    if not lines or not any(ln.strip() in _kde_hoards(icon) for ln in lines):
        return False
    rest = [ln for ln in lines if ln.strip() not in _kde_hoards(icon)]
    at = _kde_section(rest)
    if at and not [ln for ln in rest[at[0] + 1:at[1]] if ln.strip()]:   # (its section, when only Hoard's was in it)
        rest = rest[:at[0]] + rest[at[1]:]
    try:
        _kde_write(folder, rest)
    except OSError:
        pass
    return True


def mark(folder, system: System) -> tuple[bool, list[str]]:
    """Give the sync folder Hoard's icon (see the module's notes): whether it has it now in one file manager at least,
    and what couldn't show it (["gvfs"]: GNOME Files and Nemo, from the Flatpak)."""
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        return False, []
    mine = _ours(folder)
    if system.kind == "finder" and (folder / FINDER_ICON).exists() and not (mine and _finder_still_ours(system, folder)):
        if mine:   # (you've put an icon of your own on it since: Hoard's picture goes, and yours stays)
            (folder / ICON_NAME).unlink(missing_ok=True)
            _finder_prints(system, {str(folder): None})
        return False, []   # (a custom icon of someone else's: left as it is)
    if system.kind != "finder":
        current = _gvfs_icon(system, folder)
        if current not in (False, None, (folder / ICON_NAME).as_uri()):
            return False, []   # (GNOME Files and Nemo show another icon: Dolphin isn't given Hoard's either)
    try:
        icon = _put_picture(folder)
    except OSError:
        return False, []
    if system.kind == "finder":
        if _finder_icon(system, folder, icon):
            _finder_prints(system, {str(folder): system.finder_print(folder) or ""})
            return True, []
        icon.unlink(missing_ok=True)
        return False, []
    shown, cant = False, []
    if current is False:
        cant = ["gvfs"] if system.flatpak() else []
    else:
        done = system.run(["gio", "set", str(folder), "metadata::custom-icon", icon.as_uri()])
        shown = bool(done) and done.returncode == 0
    if _installed(system, "dolphin"):
        shown = _kde_mark(folder, icon) or shown
    if not shown:
        icon.unlink(missing_ok=True)
    return shown, cant


def unmark(folder, system: System) -> bool:
    """Take Hoard's icon off a folder that's no longer the sync folder (only Hoard's: another's custom icon stays, and
    in Finder one you put on it since). Also when Hoard's picture was deleted from it: GNOME's, Nemo's and Dolphin's
    notes of it go too. False when there was nothing of Hoard's."""
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        return False
    icon = folder / ICON_NAME
    found = _ours(folder)
    if system.kind == "finder":
        if found and (folder / FINDER_ICON).exists() and _finder_still_ours(system, folder):
            _finder_icon(system, folder, None)
        _finder_prints(system, {str(folder): None})
    else:
        if _gvfs_icon(system, folder) == icon.as_uri():
            system.run(["gio", "set", "--type=unset", str(folder), "metadata::custom-icon"])
            found = True
        found = _kde_unmark(folder, icon) or found
    if _ours(folder):
        icon.unlink(missing_ok=True)
    return found


# ---- the menu

def program(exe: str | None, system: System) -> list[str] | None:
    """The command that starts Hoard for the options (see the module's notes), or None when there's none to start: a
    Hoard started without its window, which knows no program of its own."""
    if system.flatpak():
        return ["flatpak", "run", FLATPAK_ID]
    appimage = system.environ().get("APPIMAGE")
    if appimage and os.path.isabs(appimage) and system.kind == "files":
        return [appimage]
    if not exe or not os.path.isabs(exe):
        return None
    if system.kind == "finder":
        app = next((p for p in Path(exe).parents if p.suffix == ".app"), None)
        if app is not None:
            return ["open", "-n", "-a", str(app), "--args"]
    return [exe]


def _check(command: list[str]) -> str:
    """The shell's test for whether Hoard's program is still there."""
    q = shlex.quote
    if command[:2] == ["flatpak", "run"]:
        return f"command -v flatpak >/dev/null 2>&1 && flatpak info {q(command[2])} >/dev/null 2>&1"
    if command[:1] == ["open"]:
        return f"[ -d {q(command[3])} ]"
    return f"[ -x {q(command[0])} ]"


def _nautilus_names(lang: str) -> list[str]:
    """The GNOME Files scripts' file names (their names are what its Scripts menu shows), in lang."""
    from . import i18n
    return [i18n.say(lang, english).replace("/", "∕").strip(". ") or english for _w, english, *_ in OPTIONS]


def _targets(system: System, lang: str) -> list[Path]:
    """Every file and folder of the options register writes, in lang (the script takes them away when Hoard's gone)."""
    data = system.data_home()
    if system.kind == "finder":
        services = system.home() / "Library" / "Services"
        return [system.helper_dir()] + [services / f"{name}.workflow" for *_, name in OPTIONS]
    return ([system.helper_dir()] + [data / "nautilus" / "scripts" / n for n in _nautilus_names(lang)]
            + [data / "kio" / "servicemenus" / n for n in DOLPHIN]
            + [data / "nemo" / "actions" / f"{n}.nemo_action" for n in NEMO])


def _written(system: System) -> list[Path]:
    """Every file and folder of the options Hoard may have written, in any language, to take away."""
    out = _targets(system, "en")
    scripts = system.data_home() / "nautilus" / "scripts"
    if system.kind == "files" and scripts.is_dir():
        out += sorted(p for p in scripts.iterdir() if p not in out)   # (in another language: _hoards tells)
    return out


def helper_script(command: list[str], gone: list[Path], helper_dir: Path) -> str:
    """Hoard's script for the options (see the module's notes): what it asks Hoard for, from what was chosen; or, when
    Hoard's program is gone, Hoard's options taken away (gone: what register wrote, each taken only while it's still
    Hoard's, its mark in it; helper_dir, Hoard's own folder for this script, last)."""
    q = shlex.quote
    return f"""#!/bin/sh
{MARK}
# Hoard's right-click options in your file manager run this. Settings' "Show it in ..." takes them away with it.
if ! {{ {_check(command)}; }}; then   # (Hoard isn't there any more: its options go with it)
  for f in {" ".join(q(str(p)) for p in gone)}; do
    if [ -L "$f" ]; then
      continue
    elif [ -d "$f" ]; then   # (a Quick Action: only one that runs this script)
      grep -qF {q("/" + HELPER)} "$f/Contents/document.wflow" 2>/dev/null && rm -rf -- "$f"
    elif [ -f "$f" ] && grep -qF {q(MARK)} "$f" 2>/dev/null; then
      rm -f -- "$f"
    fi
  done
  [ -L {q(str(helper_dir))} ] || rm -rf -- {q(str(helper_dir))}
  exit 0
fi
what=$1
shift
case $what in
  add)
    [ "$#" -gt 0 ] || exit 0
    n=$#
    for f in "$@"; do
      case $f in /*) ;; *) f=$PWD/$f ;; esac
      set -- "$@" --hoard-add "$f"
    done
    shift "$n" ;;
  sync)
    f=${{1:-$PWD}}
    case $f in /*) ;; *) f=$PWD/$f ;; esac
    set -- --hoard-sync-now "$f" ;;
  local) set -- --hoard-open-local ;;
  *) exit 2 ;;
esac
exec {" ".join(q(c) for c in command)} "$@"
"""


def _menu_safe(path: Path) -> bool:
    """Can this path go in a Dolphin service menu's or a Nemo action's Exec line, in double quotes? (Each reads %,
    quotes and backslashes its own way: a path with one of those, or a line break, isn't written there.)"""
    return not any(c in str(path) for c in "%\"`$\\\n\r\t\x00")


def _exec_line(path: Path, rest: str) -> str:
    """A .desktop or .nemo_action Exec line running path (a _menu_safe one), with rest after it."""
    return f'"{path}" {rest}'.strip()


def _write(path: Path, text, executable: bool = False) -> None:
    """One file of the options, written whole (never through a link), and runnable when it's a script."""
    from .safety import write_file_safely
    write_file_safely(path, text)
    path.chmod(0o755 if executable else 0o644)


def _finder_workflow(folder: Path, words: str, folders_only: bool, command: str) -> None:
    """One Quick Action: an Automator workflow that runs a shell script with what's chosen in Finder, as Automator
    writes one."""
    contents = folder / "Contents"
    info = {"NSServices": [{
        "NSMenuItem": {"default": words}, "NSMessage": "runWorkflowAsService",
        "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
        "NSSendFileTypes": ["public.folder"] if folders_only else ["public.item"]}]}
    action = {
        "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
        "AMActionVersion": "2.0.3", "AMApplication": ["Automator"],
        "AMParameterProperties": {k: {} for k in ("COMMAND_STRING", "CheckedForUserDefaultShell", "inputMethod",
                                                  "shell", "source")},
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action", "ActionName": "Run Shell Script",
        "ActionParameters": {"COMMAND_STRING": command, "CheckedForUserDefaultShell": True, "inputMethod": 1,
                             "shell": "/bin/sh", "source": ""},
        "BundleIdentifier": "com.apple.RunShellScript", "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False, "CanShowWhenRun": True, "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction", "InputUUID": str(uuid.uuid4()).upper(),
        "Keywords": ["Shell", "Script", "Command", "Run", "Unix"], "OutputUUID": str(uuid.uuid4()).upper(),
        "UUID": str(uuid.uuid4()).upper(), "UnlocalizedApplications": ["Automator"], "isViewVisible": 1,
        "location": "309.000000:305.000000",
        "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib"}
    meta = {"applicationBundleIDsByPath": {}, "applicationPaths": [],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing", "presentationMode": 15, "processesInput": 0,
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing", "serviceProcessesInput": 0,
            "systemImageName": "NSActionTemplate", "useAutomaticInputType": 0,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu"}
    document = {"AMApplicationBuild": "523", "AMApplicationVersion": "2.10", "AMDocumentVersion": "2",
                "actions": [{"action": action, "isViewVisible": 1}], "connectors": {}, "workflowMetaData": meta}
    _write(contents / "Info.plist", plistlib.dumps(info))
    _write(contents / "document.wflow", plistlib.dumps(document))


def _dolphin_menu(icon: Path, mime: str, options: list[tuple[str, str, str]]) -> str:
    """A Dolphin service menu (Plasma 5.85 and later read them from kio/servicemenus): its options, each (its name, its
    words, what it runs), on mime."""
    text = (f"{MARK}\n[Desktop Entry]\nType=Service\nX-KDE-ServiceTypes=KonqPopupMenu/Plugin\nMimeType={mime};\n"
            f"Actions={';'.join(n for n, *_ in options)};\nX-KDE-Priority=TopLevel\n")
    for name, words, run in options:
        text += f"\n[Desktop Action {name}]\nName={words}\nIcon={icon}\nExec={run}\n"
    return text


def _nemo_action(words: str, icon: Path, run: str, selection: str, extensions: str) -> str:
    """A Nemo action: its words, what it runs, and when it shows."""
    return (f"{MARK}\n[Nemo Action]\nActive=true\nName={words}\nComment={words}\nIcon-Name={icon}\nExec={run}\n"
            f"Selection={selection}\nExtensions={extensions};\n")


def _installed(system: System, name: str) -> bool:
    """Is this file manager installed? (In the Flatpak, whose sandbox doesn't see the computer's programs: is its own
    folder in your home folder?)"""
    if system.which(name):
        return True
    if not system.flatpak():
        return False
    data, config = system.data_home(), system.config_home()
    return any(p.exists() for p in {"nautilus": (data / "nautilus", config / "nautilus"),
                                    "dolphin": (config / "dolphinrc", data / "dolphin"),
                                    "nemo": (data / "nemo", config / "nemo")}[name])


def register(command: list[str], system: System, lang: str = "en") -> bool:
    """Put Hoard's options in the file managers' right-click menus for this account, in lang: Hoard's script, and each
    installed file manager's way of running it. A file of yours with the same name as one of Hoard's is left as it is,
    and Hoard's option goes without it. False when none could be put in place."""
    from . import i18n
    helper_dir = system.helper_dir()
    helper, icon = helper_dir / HELPER, helper_dir / "hoard-folder.png"
    words = {what: i18n.say(lang, english) for what, english, *_ in OPTIONS}
    unregister(system, keep_helper=True)   # (what an earlier start wrote: in another language, or for a file manager
    #   that's gone since; what's left where Hoard's go is someone else's)
    free = [p for p in _targets(system, lang) if p != helper_dir and not (p.exists() or p.is_symlink())]
    try:
        helper_dir.mkdir(parents=True, exist_ok=True)
        _write(helper, helper_script(command, free, helper_dir), executable=True)
        _write(icon, ICON_SOURCE.read_bytes())
    except OSError:
        return False

    def put(path: Path, text, executable: bool = False) -> bool:
        """One option's file, when its place is free."""
        if path not in free:
            return False
        _write(path, text, executable)
        return True

    done = False
    try:
        if system.kind == "finder":
            services = system.home() / "Library" / "Services"
            for what, _english, folders_only, name in OPTIONS:
                if services / f"{name}.workflow" in free:
                    _finder_workflow(services / f"{name}.workflow", words[what], folders_only,
                                     f'{shlex.quote(str(helper))} {what} "$@"')
                    done = True
            system.run([PBS, "-update"])
            return done
        data = system.data_home()
        if _installed(system, "nautilus"):
            for (what, *_), name in zip(OPTIONS, _nautilus_names(lang)):
                done = put(data / "nautilus" / "scripts" / name,
                           f'#!/bin/sh\n{MARK}\nexec {shlex.quote(str(helper))} {what} "$@"\n', True) or done
        if not _menu_safe(helper) or not _menu_safe(icon):
            return done
        if _installed(system, "dolphin"):
            menus = data / "kio" / "servicemenus"
            done = put(menus / DOLPHIN[0], _dolphin_menu(icon, "all/all", [
                ("hoardAdd", words["add"], _exec_line(helper, "add %F"))]), True) or done
            done = put(menus / DOLPHIN[1], _dolphin_menu(icon, "inode/directory", [
                ("hoardSync", words["sync"], _exec_line(helper, "sync %f")),
                ("hoardOpen", words["local"], _exec_line(helper, "local"))]), True) or done
        if _installed(system, "nemo"):
            actions = data / "nemo" / "actions"
            for name, (what, run, selection, extensions) in zip(NEMO, (
                    ("add", "add %F", "notnone", "any"), ("sync", "sync %F", "s", "dir"),
                    ("sync", "sync %P", "none", "any"), ("local", "local", "s", "dir"),
                    ("local", "local", "none", "any"))):
                done = put(actions / f"{name}.nemo_action",
                           _nemo_action(words[what], icon, _exec_line(helper, run), selection, extensions)) or done
    except OSError:
        return done
    return done


def _hoards(path: Path, system: System) -> bool:
    """Is this one of the options' files this Hoard wrote: its mark in it, running the script in this Hoard's app-data
    folder? (Another Hoard's, with an app-data folder of its own, a test's say, is never taken.) Never through a
    link."""
    helper = system.helper_dir() / HELPER
    names = {str(helper).encode(), shlex.quote(str(helper)).encode()}
    try:
        if path.is_symlink():
            return False
        if path.is_dir():
            if path == system.helper_dir():
                return helper.is_file() and not helper.is_symlink() and MARK.encode() in helper.read_bytes()[:4096]
            document = path / "Contents" / "document.wflow"
            if document.is_symlink() or not document.is_file():
                return False
            plist = plistlib.loads(document.read_bytes()[:1 << 20])
            command = plist["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"]
            return any(n.decode() in command for n in names)
        head = path.read_bytes()[:4096] if path.is_file() else b""
        return MARK.encode() in head and any(n in head for n in names)
    except (OSError, ValueError, LookupError, TypeError, plistlib.InvalidFileException):
        return False


def unregister(system: System, keep_helper: bool = False) -> None:
    """Take this Hoard's options out of the file managers' menus (nothing to do when they aren't there). Only its own
    files are taken (_hoards): one with the same name that isn't stays."""
    finder = False
    for path in _written(system):
        if (keep_helper and path == system.helper_dir()) or not _hoards(path, system):
            continue
        finder = finder or path.suffix == ".workflow"
        try:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        except OSError:
            pass
    if finder and not keep_helper:
        system.run([PBS, "-update"])


def language(cfg: dict, system: System) -> str:
    """The language for the options' words: the one chosen in Settings, or the system's (LANG) when that's the choice."""
    from . import i18n
    d = cfg.get("display") if isinstance(cfg.get("display"), dict) else {}
    chosen = i18n.setting(d.get("language"))
    if chosen != "system":
        return chosen
    env = system.environ()
    given = (env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG") or "").split(".")[0].replace("_", "-")
    return i18n.from_header(given) if given else "en"


def apply(cfg: dict, exe: str | None, was: str | None = None, system: System | None = None) -> dict:
    """Make the file managers show what Hoard's settings say: the icon on the sync folder (and off the one it was,
    was), and the right-click options while there's a sync folder, Settings shows Hoard in the file manager, and there's
    a program to start (program()). {"icon": bool, "menu": bool, "cant": [...]}: what's in place now."""
    from .explorer import on
    system = system or System()
    if system.kind is None:
        return {"icon": False, "menu": False}
    sync = str(cfg.get("local_sync") or "").strip()
    if was and os.path.normcase(str(was)) != os.path.normcase(sync):
        unmark(was, system)
    icon, cant = False, []
    if sync and on(cfg):
        icon, cant = mark(sync, system)
    elif sync:
        unmark(sync, system)
    menu = False
    command = program(exe, system)
    if not (sync and on(cfg)):
        unregister(system)
    elif command:
        menu = register(command, system, language(cfg, system))
    # (else a Hoard started without its window, which knows no program to start: the options are left as they are)
    return {"icon": icon, "menu": menu, **({"cant": cant} if cant else {})}
