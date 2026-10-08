"""A notification from the system (Windows, macOS, Linux) when the routine check finds something to download while
Hoard runs in the background: a count only, never a product's name (a hidden one stays hidden on screen too).

Each system's own way, without anything to install: on Windows a notification from Hoard's icon in the notification
area (Windows shows it as a toast, and keeps quiet hours), on macOS osascript, on Linux notify-send or, without it,
gdbus. The text goes as arguments, never as part of a script or a command line a shell reads. A system without any
of these just doesn't show one: the pages still say what was found.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading

TITLE = "Hoard"
SHOWN_S = 20   # Windows: how long Hoard's icon stays in the notification area for it


def found_text(counts: dict) -> str:
    """What the routine check found, as a notification says it."""
    def plural(n: int, word: str) -> str:
        return f"{n:,} {word}{'' if n == 1 else 's'}"
    parts = [plural(counts["new"], "new product")] if counts.get("new") else []
    parts += [plural(counts["updates"], "update")] if counts.get("updates") else []
    return f"Found {' and '.join(parts)}. Open Hoard to choose what to download."


def show(text: str, title: str = TITLE) -> bool:
    """Show a notification, in the background (it never holds up the job that asked). True when one was sent."""
    text, title = str(text)[:250], str(title)[:60]
    if sys.platform == "win32":
        target = _windows
    elif sys.platform == "darwin":
        target = _mac
    elif shutil.which("notify-send") or shutil.which("gdbus"):
        target = _linux
    else:
        return False
    threading.Thread(target=_quietly, args=(target, title, text), daemon=True, name="notify").start()
    return True


def _quietly(target, title: str, text: str) -> None:
    try:
        target(title, text)
    except Exception as e:   # only ever a courtesy: the pages say the same
        print(f"Couldn't show a notification: {e}", flush=True)


def _run(args: list[str]) -> None:
    subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=15, check=False)


def _mac(title: str, text: str) -> None:
    _run(["osascript", "-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
          "-e", "end run", title, text])


def _gvariant(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _linux(title: str, text: str) -> None:
    if shutil.which("notify-send"):
        _run(["notify-send", "--app-name=Hoard", "--icon=io.github.soloflighter1010.Hoard", "--", title, text])
    else:   # (the Flatpak, and desktops without libnotify's tools): the same, straight to the notification service
        _run(["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
              "--object-path", "/org/freedesktop/Notifications", "--method", "org.freedesktop.Notifications.Notify",
              _gvariant("Hoard"), "0", _gvariant("io.github.soloflighter1010.Hoard"), _gvariant(title), _gvariant(text), "[]", "{}", "-1"])


def _windows(title: str, text: str) -> None:
    """A balloon from an icon of Hoard's own in the notification area, there just long enough to show it."""
    import ctypes
    import time
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                    ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                    ("szInfo", wintypes.WCHAR * 256), ("uTimeoutOrVersion", wintypes.UINT),
                    ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
                    ("hBalloonIcon", wintypes.HICON)]

    NIM_ADD, NIM_DELETE = 0, 2
    NIF_ICON, NIF_TIP, NIF_INFO = 0x2, 0x4, 0x10
    NIIF_INFO, NIIF_RESPECT_QUIET_TIME = 0x1, 0x80
    HWND_MESSAGE = wintypes.HWND(-3)

    user32, shell32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("shell32", use_last_error=True)
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.LoadIconW.restype = wintypes.HICON
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
    shell32.ExtractIconW.restype = wintypes.HICON
    shell32.ExtractIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    user32.DestroyIcon.argtypes = [wintypes.HICON]

    # a message-only window (nothing on screen) for the icon to belong to, in this thread
    hwnd = user32.CreateWindowExW(0, "STATIC", "Hoard", 0, 0, 0, 0, 0, HWND_MESSAGE, None, None, None)
    if not hwnd:
        raise OSError(ctypes.get_last_error(), "no window for the notification")
    icon = shell32.ExtractIconW(None, sys.executable, 0) if getattr(sys, "frozen", False) else None
    own = bool(icon) and icon > 1   # (1: not an icon file)
    try:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd, nid.uID = hwnd, 1
        nid.uFlags = NIF_ICON | NIF_TIP | NIF_INFO
        nid.hIcon = icon if own else user32.LoadIconW(None, ctypes.c_void_p(32512))   # IDI_APPLICATION
        nid.szTip, nid.szInfoTitle, nid.szInfo = TITLE, title[:63], text[:255]
        nid.dwInfoFlags = NIIF_INFO | NIIF_RESPECT_QUIET_TIME
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            raise OSError(ctypes.get_last_error(), "the notification area refused it")
        time.sleep(SHOWN_S)
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
    finally:
        if own:
            user32.DestroyIcon(icon)
        user32.DestroyWindow(hwnd)
