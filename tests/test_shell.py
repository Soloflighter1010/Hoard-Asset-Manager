"""Hoard in its Tauri shell's window (hoard/shell.py, for the experimental Tauri and Nuitka build): the messages to
the shell, its events back, the picker, the close button's choice, and quitting when the shell has gone."""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hoard import shell  # noqa: E402


class _Jobs:
    def __init__(self, running=False):
        self.state = {"running": running, "queue": []}


class _Server:
    def __init__(self, close_to_taskbar=True, running=False):
        self.cfg = {"close_to_taskbar": close_to_taskbar}
        self.jobs, self.project_jobs = _Jobs(running), _Jobs()
        self.show_window = self.hide_window = self.quit_app = self.pick_path = None

    def entry_url(self):
        return "http://127.0.0.1:8765/?once=abc"


class Protocol(unittest.TestCase):
    def setUp(self):
        self.to_hoard_r, self.to_hoard_w = os.pipe()   # the shell writes events here
        self.from_hoard_r, self.from_hoard_w = os.pipe()   # and reads Hoard's messages here
        self.shell = shell.Shell(self.from_hoard_w, os.fdopen(self.to_hoard_r, "r", encoding="utf-8"))
        self.read = os.fdopen(self.from_hoard_r, "r", encoding="utf-8")
        self.addCleanup(self.read.close)
        self.addCleanup(self.shell._inp.close)

    def tearDown(self):
        for fd in (self.to_hoard_w, self.from_hoard_w):
            try:
                os.close(fd)
            except OSError:
                pass

    def event(self, **e):
        os.write(self.to_hoard_w, (json.dumps(e) + "\n").encode())

    def message(self) -> dict:
        line = self.read.readline()
        self.assertTrue(line.startswith(shell.MARK), repr(line))
        return json.loads(line[len(shell.MARK):])

    def test_a_message_is_one_marked_line(self):
        self.shell.send(do="open", url="http://127.0.0.1:1/")
        self.assertEqual(self.message(), {"do": "open", "url": "http://127.0.0.1:1/"})

    def test_the_picker_waits_for_its_answer(self):
        self.shell.listen()
        got = []
        t = threading.Thread(target=lambda: got.append(self.shell.pick("folder", "/home")))
        t.start()
        asked = self.message()
        self.assertEqual({k: asked[k] for k in ("do", "kind", "start")}, {"do": "pick", "kind": "folder", "start": "/home"})
        self.event(event="picked", id=asked["id"] + 1, path="/not/this/one")   # (another picker's answer)
        self.event(event="picked", id=asked["id"], path="/home/you/Hoard")
        t.join(5)
        self.assertEqual(got, ["/home/you/Hoard"])
        t = threading.Thread(target=lambda: got.append(self.shell.pick("file")))
        t.start()
        asked = self.message()
        self.assertEqual(asked["kind"], "file")
        self.event(event="picked", id=asked["id"], path=None)   # cancelled
        t.join(5)
        self.assertEqual(got[-1], None)

    def test_the_shell_gone_ends_a_picker_and_hoard(self):
        gone = threading.Event()
        self.shell.on_gone = gone.set
        self.shell.listen()
        got = []
        t = threading.Thread(target=lambda: got.append(self.shell.pick("folder")))
        t.start()
        self.message()
        os.close(self.to_hoard_w)   # (the shell ended)
        t.join(5)
        self.assertEqual(got, [None])
        self.assertTrue(gone.wait(5))
        self.shell.send(do="show")   # nothing to send to: no error

    def run_hoard(self, srv):
        """open_in_shell on its own thread, as run_app runs it; returns the thread once the page is opened."""
        t = threading.Thread(target=shell.open_in_shell, args=(srv, self.shell), daemon=True)
        t.start()
        self.assertEqual(self.message(), {"do": "open", "url": srv.entry_url()})
        return t

    def test_the_close_button_as_in_hoards_own_window(self):
        srv = _Server(close_to_taskbar=True)
        t = self.run_hoard(srv)
        self.event(event="closing", quitting=False)
        self.assertEqual(self.message(), {"do": "minimize"}, "to the taskbar, carrying on")
        srv.jobs.state["running"] = True
        srv.cfg["close_to_taskbar"] = False
        self.event(event="closing", quitting=False)
        self.assertEqual(self.message(), {"do": "js", "code": "window.dispatchEvent(new Event('hoard-close'))"},
                         "a task is running: the page asks")
        srv.jobs.state["running"] = False
        self.event(event="closing", quitting=True)
        self.assertEqual(self.message(), {"do": "hide"}, "quit: the window goes at once")
        t.join(5)
        self.assertFalse(t.is_alive(), "then Hoard stops")

    def test_hoards_own_buttons(self):
        srv = _Server()
        t = self.run_hoard(srv)
        srv.show_window()
        self.assertEqual(self.message(), {"do": "show"})
        srv.hide_window()
        self.assertEqual(self.message(), {"do": "minimize"})
        srv.quit_app()   # Quit Hoard
        self.assertEqual(self.message(), {"do": "hide"})
        t.join(5)
        self.assertFalse(t.is_alive())

    def test_the_shell_gone_quits_hoard(self):
        t = self.run_hoard(_Server())
        os.close(self.to_hoard_w)
        t.join(5)
        self.assertFalse(t.is_alive())


class Updates(unittest.TestCase):
    def test_the_shell_build_says_where_its_updates_are(self):
        """It isn't the app Hoard-Setup installed, nor the portable zip: it says what to get instead."""
        from hoard import updater
        self.addCleanup(setattr, shell, "BUILD", shell.BUILD)
        shell.BUILD = True
        said = updater.how_to_update("5.2.0")
        self.assertIn("Tauri and Nuitka build", said)
        self.assertNotIn("portable zip", said)


if __name__ == "__main__":
    unittest.main()
