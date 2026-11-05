"""Hoard's window from its Tauri shell (shell/, the experimental Tauri and Nuitka build): the shell starts this Hoard
(hoard-server, compiled by Nuitka) with --shell, and the two talk over its standard input and output, one JSON
message to a line. Hoard is the same as in its own pywebview window; only the window is the shell's.

From Hoard to the shell, each line starting with MARK (anything else the shell only logs):
    {"do": "open", "url": ...}            show the window, on Hoard's page (a one-time link)
    {"do": "show"}                        bring it back, in front (a second start of Hoard asks for this)
    {"do": "minimize"}                    to the taskbar (the Dock): Hoard carries on
    {"do": "hide"}                        Hoard is quitting: the window goes now, the shell ends when Hoard has
    {"do": "js", "code": ...}             run a page script (the page asks what to do about a running task)
    {"do": "pick", "id": n, "kind": "folder" or "file", "start": ...}   the system's picker, over the window

From the shell to Hoard:
    {"event": "closing", "quitting": bool}   the window's close button (quitting: Command-Q on a Mac)
    {"event": "picked", "id": n, "path": ... or null}
and the end of its input: the shell has gone, so Hoard quits.

Standard input and output are kept for this alone: claim_pipes() takes them before anything prints, and gives
what Hoard and the programs it starts would print or read the null device instead (what Hoard prints goes to its
log, as in the installed app)."""
from __future__ import annotations

import json
import os
import sys
import threading

MARK = "\x1ehoard:"   # (a record separator first: no line Hoard or another program prints starts with it)
BUILD = False         # set by packaging/hoard_shell.py: this copy of Hoard is the shell build (no pywebview)


class Shell:
    """The line to the Tauri shell: messages out (send), its events in (listen, on its own thread)."""

    def __init__(self, out_fd: int, inp):
        self._out, self._inp = out_fd, inp
        self._lock = threading.Lock()
        self._picks: dict[int, list] = {}   # id -> [Event, path]
        self._n = 0
        self.on_closing = lambda quitting: None
        self.on_gone = lambda: None
        self.gone = threading.Event()

    def send(self, **message) -> None:
        """One message to the shell (dropped once it's gone)."""
        if self.gone.is_set():
            return
        line = (MARK + json.dumps(message, ensure_ascii=True) + "\n").encode("ascii")
        try:
            with self._lock:
                os.write(self._out, line)
        except OSError:   # (the shell has gone)
            self._ended()

    def listen(self) -> None:
        """Read the shell's events until its input ends, on a thread of its own."""
        threading.Thread(target=self._read, daemon=True, name="shell").start()

    def _read(self) -> None:
        """Each line from the shell, as an event, until it ends."""
        try:
            for line in self._inp:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    self._event(event)
        except (OSError, ValueError):
            pass
        self._ended()

    def _event(self, event: dict) -> None:
        """One event from the shell: the close button, or a picker's answer."""
        kind = event.get("event")
        if kind == "closing":
            self.on_closing(bool(event.get("quitting")))
        elif kind == "picked":
            waiting = self._picks.get(event.get("id"))
            if waiting:
                path = event.get("path")
                waiting[1] = path if isinstance(path, str) and path else None
                waiting[0].set()

    def _ended(self) -> None:
        """The shell has gone: any picker waiting gets nothing, and Hoard is told (once)."""
        if self.gone.is_set():
            return
        self.gone.set()
        for waiting in list(self._picks.values()):   # (a picker that was open: nothing was chosen)
            waiting[0].set()
        self.on_gone()

    def pick(self, kind: str, start: str = "") -> str | None:
        """The system's own folder (or file) picker, over the window: the chosen path, or None if cancelled."""
        with self._lock:
            self._n += 1
            n = self._n
        waiting = self._picks[n] = [threading.Event(), None]
        self.send(do="pick", id=n, kind="file" if kind == "file" else "folder", start=str(start or ""))
        waiting[0].wait()
        self._picks.pop(n, None)
        return waiting[1]


SHELL: Shell | None = None


def claim_pipes() -> Shell:
    """Keep standard input and output for the shell alone, before anything prints: Hoard's own (and those of the
    programs it starts, which would otherwise share them) become the null device."""
    global SHELL
    out_fd, in_fd = os.dup(1), os.dup(0)   # (new descriptors aren't passed on to other programs: PEP 446)
    null_out, null_in = os.open(os.devnull, os.O_WRONLY), os.open(os.devnull, os.O_RDONLY)
    os.dup2(null_out, 1)
    os.dup2(null_in, 0)
    os.close(null_out)
    os.close(null_in)
    if sys.platform == "win32":   # (Windows hands a program's own standard handles to what it starts, not its fds)
        try:
            import ctypes
            import msvcrt
            k32 = ctypes.windll.kernel32
            k32.SetStdHandle(-11, msvcrt.get_osfhandle(1))   # STD_OUTPUT_HANDLE
            k32.SetStdHandle(-12, msvcrt.get_osfhandle(1))   # STD_ERROR_HANDLE
            k32.SetStdHandle(-10, msvcrt.get_osfhandle(0))   # STD_INPUT_HANDLE
        except Exception:
            pass
    SHELL = Shell(out_fd, os.fdopen(in_fd, "r", encoding="utf-8", errors="replace"))
    return SHELL


def open_in_shell(srv, shell: Shell) -> None:
    """Hoard in the shell's window, as open_window does it in pywebview's: the one-time link to its page, the close
    button's choice, the picker, and Quit Hoard. Blocks until Hoard is quitting, or the shell has gone."""
    from .app import close_decision
    leaving = threading.Event()

    def quit_app():
        """Quit Hoard from its page: the window goes at once, and Hoard stops (then the shell ends)."""
        leaving.set()
        shell.send(do="hide")

    def closing(quitting: bool):
        """The window's close button (or Command-Q), decided as in pywebview's window."""
        if leaving.is_set():
            return
        decision = close_decision(srv, quitting=quitting)
        if decision == "quit":
            quit_app()
        elif decision == "background":
            shell.send(do="minimize")
        else:   # something's running: the page asks what to do (stop it first, the background, or now)
            shell.send(do="js", code="window.dispatchEvent(new Event('hoard-close'))")

    srv.show_window = lambda: shell.send(do="show")
    srv.hide_window = lambda: shell.send(do="minimize")
    srv.quit_app = quit_app
    srv.pick_path = shell.pick
    shell.on_closing = closing
    shell.on_gone = leaving.set
    shell.listen()
    shell.send(do="open", url=srv.entry_url())
    leaving.wait()
