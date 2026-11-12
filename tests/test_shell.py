"""Hoard in its Tauri shell's window (hoard/shell.py, for the experimental Tauri and Nuitka build): the messages to
the shell, its events back, the picker, the close button's choice, and quitting when the shell has gone."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hoard import shell  # noqa: E402
from tests.isolation import IsolatedTestCase  # noqa: E402


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


class Protocol(IsolatedTestCase):
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

    def test_the_shell_says_whether_it_updates_this_copy(self):
        self.shell.listen()
        self.assertFalse(self.shell.can_update, "not until it says so")
        self.event(event="hello", updates=True)
        for _ in range(50):
            if self.shell.can_update:
                break
            threading.Event().wait(0.05)
        self.assertTrue(self.shell.can_update)
        self.event(event="hello", updates="yes")   # (only true itself)
        threading.Event().wait(0.2)
        self.assertFalse(self.shell.can_update)

    def test_an_update_through_the_shell(self):
        """Hoard asks for the update it chose; the shell says how far it's got, then that it's here (checked against
        its signature), or why not; a shell that's gone ends the wait."""
        self.shell.listen()
        url = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/download/v5.2.0-beta.6/Hoard-update.json"
        seen, outcome = [], []

        def get():
            try:
                self.shell.get_update(url, "5.2.0-beta.6", lambda got, total: seen.append((got, total)))
                outcome.append("ready")
            except RuntimeError as e:
                outcome.append(str(e))
        t = threading.Thread(target=get)
        t.start()
        self.assertEqual(self.message(), {"do": "update", "url": url, "version": "5.2.0-beta.6"})
        self.event(event="update", state="downloading", got=1048576, total=52428800)
        self.event(event="update", state="downloading", got=52428800, total=None)
        self.event(event="update", state="ready")
        t.join(5)
        self.assertEqual((seen, outcome), ([(1048576, 52428800), (52428800, None)], ["ready"]))
        t = threading.Thread(target=get)
        t.start()
        self.message()
        self.event(event="update", state="failed", why="signature mismatch")
        t.join(5)
        self.assertEqual(outcome[-1], "signature mismatch")
        t = threading.Thread(target=get)
        t.start()
        self.message()
        os.close(self.to_hoard_w)   # (the shell ended)
        t.join(5)
        self.assertEqual(outcome[-1], "Hoard's window has closed")


class _Window:
    """The shell, as hoard/updater.py sees it."""
    def __init__(self, can_update=True, fails=""):
        self.can_update, self.fails, self.asked, self.sent = can_update, fails, [], []

    def get_update(self, url, version, progress):
        self.asked.append((url, version))
        progress(10 * 1024 * 1024, 50 * 1024 * 1024)
        if self.fails:
            raise RuntimeError(self.fails)

    def send(self, **message):
        self.sent.append(message)


def _release(version, assets):
    base = f"https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/download/v{version}/"
    return {"tag_name": f"v{version}", "prerelease": "beta" in version, "draft": False,
            "html_url": f"https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/tag/v{version}",
            "assets": [{"name": a, "browser_download_url": a if a.startswith("https://") else base + a} for a in assets]}


class Updates(IsolatedTestCase):
    def setUp(self):
        from unittest import mock
        self.addCleanup(setattr, shell, "BUILD", shell.BUILD)
        self.addCleanup(setattr, shell, "SHELL", shell.SHELL)
        shell.BUILD = True
        self.mock = mock

    def test_the_shell_build_says_where_its_updates_are(self):
        """When it can't update itself: what to get instead, never the old installer or the portable zip, and no
        version in it, so the page can translate it."""
        from hoard import updater
        with self.mock.patch("hoard.paths.in_flatpak", lambda: False):
            said = updater.how_to_update("5.2.0")
        self.assertIn("AppImage", said)
        self.assertNotIn("portable zip", said)
        self.assertNotIn("Hoard-Setup", said)
        with self.mock.patch("hoard.paths.in_flatpak", lambda: True):
            said = updater.how_to_update("5.2.0")
        self.assertIn(".flatpak", said)
        self.assertNotIn("5.2.0", said)

    def test_only_hoards_own_manifest(self):
        from hoard import updater
        r = _release("5.2.0-beta.6", ["Hoard-update.json"])
        self.assertEqual(updater.describe(r)["update_url"], r["assets"][0]["browser_download_url"])
        self.assertEqual(updater.describe(_release("5.2.0-beta.6", ["https://example.com/Hoard-update.json"]))["update_url"], "")
        self.assertEqual(updater.describe(_release("5.2.0-beta.6", ["Hoard-5.2.0-beta.6-windows-setup.exe"]))["update_url"], "")

    def test_the_window_installs_it(self):
        """Hoard picks the release; its window downloads it, checks its signature and installs it once Hoard has
        quit: only where the window says it can (not the Flatpak, nor without the updates' key)."""
        from hoard import updater
        shell.SHELL = None
        self.assertFalse(updater.can_update_itself(), "no window")
        shell.SHELL = _Window(can_update=False)
        self.assertFalse(updater.can_update_itself(), "the window can't")
        window = shell.SHELL = _Window()
        self.assertTrue(updater.can_update_itself())
        r = _release("5.2.0-beta.6", ["Hoard-update.json"])
        u = updater.Updates({"beta_updates": True})
        u.state["latest"] = updater.describe(r)
        with self.mock.patch.object(updater, "__version__", "5.2.0-beta.5"):
            self.assertTrue(u.view(True)["can_install"])
            u.state["latest"] = updater.describe(_release("5.2.0-beta.6", ["Hoard-Setup-5.2.0-beta.6.exe", updater.SUMS_NAME]))
            self.assertFalse(u.view(True)["can_install"], "the old installer is never this build's")
        quit_ = threading.Event()
        with self.mock.patch.object(updater, "__version__", "5.2.0-beta.5"), \
                self.mock.patch.object(updater, "fetch_latest", lambda betas: r):
            self.assertIsNone(u.start_install(quit_.set))
            self.assertTrue(quit_.wait(5))
        self.assertEqual(window.asked, [(r["assets"][0]["browser_download_url"], "5.2.0-beta.6")])
        self.assertEqual(window.sent, [{"do": "install"}], "told to install it once Hoard has quit")
        self.assertIsNone(u.pending, "nothing for Hoard itself to run")
        # a download that fails: said, and Hoard doesn't quit
        window = shell.SHELL = _Window(fails="the signature doesn't match")
        u = updater.Updates({"beta_updates": True})
        quit_.clear()
        with self.mock.patch.object(updater, "__version__", "5.2.0-beta.5"), \
                self.mock.patch.object(updater, "fetch_latest", lambda betas: r):
            u.start_install(quit_.set)
            for _ in range(100):
                if u.state["error"]:
                    break
                threading.Event().wait(0.05)
        self.assertIn("the signature doesn't match", u.state["error"])
        self.assertFalse(quit_.is_set())
        self.assertEqual(window.sent, [])

    def test_the_window_installs_only_what_hoard_chose(self):
        """The shell's side (shell/src/main.rs): the updater only with the updates' key and never in the Flatpak; the
        version Hoard chose (its numbers can't tell betas apart), from Hoard's own releases; installed only once
        Hoard has quit for it."""
        root = Path(__file__).resolve().parent.parent / "shell"
        rust = (root / "src" / "main.rs").read_text("utf-8")
        for needed in ('include_str!("../updater.pub")', 'var_os("FLATPAK_ID")', '"/.flatpak-info"',
                       "remote.version.to_string() == wanted", "manifest.starts_with(RELEASES)",
                       "update.download_url.as_str().starts_with(RELEASES)", 'Some("install")',
                       "if !server.install.load(Ordering::SeqCst)", "if updates_here() {"):
            self.assertIn(needed, rust)
        conf = json.loads((root / "tauri.conf.json").read_text("utf-8"))
        self.assertEqual(conf["plugins"]["updater"]["pubkey"], "", "the key is the shell's own, from updater.pub")
        self.assertIn('tauri-plugin-updater = "=', (root / "Cargo.toml").read_text("utf-8"))
        key = (root / "updater.pub").read_text("utf-8").strip()
        self.assertNotIn("PRIVATE", key.upper(), "only ever the public half")
        if key:   # (the public half, as tauri signer generate writes it: a minisign public key, base64)
            import base64
            comment, line = base64.b64decode(key).decode("utf-8").splitlines()[:2]
            self.assertTrue(comment.startswith("untrusted comment: minisign public key: "), comment)
            raw = base64.b64decode(line)
            self.assertEqual((raw[:2], len(raw)), (b"Ed", 42), "an Ed25519 key: its id and 32 bytes")
            self.assertEqual(raw[2:10][::-1].hex().upper(), comment.rsplit(" ", 1)[1], "its id is the one it says")


class Packaging(IsolatedTestCase):
    """How Hoard is made into releases (.github/workflows/release.yml), built with Tauri and Nuitka."""
    ROOT = Path(__file__).resolve().parent.parent

    def test_hoard_update_json(self):
        """Each system's part becomes Tauri's manifest, with each file's address on the release; anything else is
        refused."""
        import tempfile
        from datetime import datetime, timezone
        sys.path.insert(0, str(self.ROOT / "scripts"))
        import update_manifest
        sig = "dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZSBmcm9tIHRhdXJpIHNlY3JldCBrZXk="
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "update-windows.tsv").write_text(
                f"windows-x86_64\tHoard-5.2.0-beta.6-windows-setup.exe\t{sig}\n"
                f"windows-x86_64-nsis\tHoard-5.2.0-beta.6-windows-setup.exe\t{sig}\n")
            # (each system's files as the workflow's "Name the files" names them: the AppImage's has x86_64 in it)
            (Path(d) / "update-linux.tsv").write_text(
                f"linux-x86_64\tHoard-5.2.0-beta.6-linux-x86_64.AppImage\t{sig}\n"
                f"linux-x86_64-appimage\tHoard-5.2.0-beta.6-linux-x86_64.AppImage\t{sig}\n"
                f"linux-x86_64-deb\tHoard-5.2.0-beta.6-linux-amd64.deb\t{sig}\n")
            for name, keys in (("macos-apple-silicon", ("darwin-aarch64", "darwin-aarch64-app")),
                               ("macos-intel", ("darwin-x86_64", "darwin-x86_64-app"))):
                (Path(d) / f"update-{name}.tsv").write_text(
                    "".join(f"{k}\tHoard-5.2.0-beta.6-{name}.app.tar.gz\t{sig}\n" for k in keys))
            m = update_manifest.manifest(Path(d), "v5.2.0-beta.6", datetime(2026, 11, 20, tzinfo=timezone.utc))
            self.assertEqual(m["pub_date"], "2026-11-20T00:00:00Z")
            self.assertEqual(sorted(m["platforms"]), ["darwin-aarch64", "darwin-aarch64-app", "darwin-x86_64", "darwin-x86_64-app",
                                                      "linux-x86_64", "linux-x86_64-appimage", "linux-x86_64-deb",
                                                      "windows-x86_64", "windows-x86_64-nsis"])
            # the names the workflow gives the files are the names the manifest takes
            flow = (self.ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
            names = re.findall(r'"dist/(Hoard-[^"]+)"', flow)
            self.assertEqual(len(names), 5, "the setup, a Mac's .dmg and .app.tar.gz, the AppImage and the .deb")
            for made in names:
                example = made.replace("$version", "5.2.0-beta.6").replace("${{ matrix.name }}", "macos-apple-silicon")
                if example.endswith((".exe", ".app.tar.gz", ".AppImage", ".deb")):
                    self.assertTrue(update_manifest.FILE.fullmatch(example), example)
            self.assertEqual(m["platforms"]["linux-x86_64-deb"], {"signature": sig, "url":
                "https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/download/v5.2.0-beta.6/Hoard-5.2.0-beta.6-linux-amd64.deb"})
            for bad in (f"macos-x86_64\tHoard-a.dmg\t{sig}", f"linux-x86_64\t../evil.AppImage\t{sig}",
                        "linux-x86_64\tHoard-a.AppImage\tnot a signature"):
                (Path(d) / "update-zz.tsv").write_text(bad + "\n")
                with self.assertRaises(ValueError, msg=bad):
                    update_manifest.manifest(Path(d), "v5.2.0-beta.6")
            with self.assertRaises(ValueError):
                update_manifest.manifest(Path(d), "../v5")

    def test_never_the_names_older_hoards_install(self):
        """Hoard 5.1.3 and earlier install a release's Hoard-Setup-<version>.exe by itself when SHA256SUMS-windows.txt
        is beside it: the Tauri and Nuitka build's files are named otherwise, so none of them ever runs its setup."""
        flow = "".join((self.ROOT / ".github" / "workflows" / f).read_text("utf-8") for f in ("release.yml", "check.yml"))
        self.assertNotIn("Hoard-Setup-", flow)
        self.assertNotIn("SHA256SUMS-windows.txt", flow)

    def test_the_flatpak_replaces_the_old_one(self):
        """The same app ID as the earlier Flatpak, so it installs over it (its data where it was), with the same
        permissions; its window from the .deb, where the window looks for its server; hoard opens the window, and
        hoard <command> runs one."""
        import re

        def read(path):   # (the manifest's top-level values and its finish-args, without a YAML library)
            text = (self.ROOT / path).read_text("utf-8")
            top = dict(re.findall(r"^([a-z-]+): '?([^'\n]+?)'?$", text, re.M))
            args = re.findall(r"^  - (--\S+)", text.split("finish-args:", 1)[1].split("modules:", 1)[0], re.M)
            return top, args, text
        old, old_args, _ = read("packaging/flatpak/io.github.soloflighter1010.Hoard.yml")
        new, new_args, text = read("shell/flatpak/io.github.soloflighter1010.Hoard.yml")
        self.assertEqual((new["app-id"], new["runtime"], new["runtime-version"], new["command"]),
                         (old["app-id"], old["runtime"], old["runtime-version"], "hoard"))
        self.assertEqual(new_args, [a for a in old_args if not a.startswith("--env=PYWEBVIEW")])
        commands = text.split("build-commands:", 1)[1]
        self.assertIn("${FLATPAK_DEST}/bin/Hoard", commands)
        self.assertIn("${FLATPAK_DEST}/lib/Hoard", commands, "bin/../lib/Hoard: where the window finds its server")
        self.assertIn("self-test", commands)
        launcher = (self.ROOT / "shell" / "flatpak" / "hoard.sh").read_text("utf-8")
        self.assertIn("exec /app/bin/Hoard", launcher)
        self.assertIn('exec /app/lib/Hoard/server/hoard-server "$@"', launcher)


if __name__ == "__main__":
    unittest.main()
