"""Tests for Hoard updating itself: finding the newest release, checking the installer before it's run, and when
Hoard asks GitHub at all.

Run from the repository root:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import __version__, config, egress, server, updater  # noqa: E402
from hoard.safety import ACCESS_HEADER  # noqa: E402

NEXT = "99.0.0"   # always newer than this copy
SETUP = f"Hoard-Setup-{NEXT}.exe"


def release(tag, **extra):
    return {"tag_name": tag, "draft": False, "prerelease": False, "html_url": f"https://github.com/{updater.REPO}/releases/tag/{tag}",
            "body": "What's new", "published_at": "2026-09-01T00:00:00Z", "assets": [], **extra}


def complete_release(tag, **extra):
    """A release as the release workflow makes it: its installer and checksums attached."""
    version = tag.lstrip("v")
    files = [{"name": updater.SETUP_NAME.format(version)}, {"name": updater.SUMS_NAME}]
    return release(tag, assets=files, **extra)


class _GitHub:
    """A stand-in api.github.com and file host on this computer. Asset links point at the API server, which
    redirects to the file host, as GitHub's do."""

    setup = b"MZ" + b"new Hoard" * 5000
    sums_hash = None      # what SHA256SUMS-windows.txt says; None: the right hash
    digest = None         # what GitHub lists for the installer; None: the right one
    seen: list = []

    @classmethod
    def start(cls):
        gh = cls

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, status, body=b"", ctype="application/json", headers=None):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path
                gh.seen.append((self.server.server_port, path, self.headers.get("User-Agent")))
                if self.server is gh.files:
                    return self.send(200, gh.setup if path.endswith(".exe") else gh.sums(), "application/octet-stream")
                if path == f"/repos/{updater.REPO}/releases":
                    return self.send(200, json.dumps(gh.releases()).encode())
                if path.startswith("/dl/"):
                    return self.send(302, headers={"Location": f"http://localhost:{gh.files.server_port}/f/{path[4:]}"})
                self.send(404, b"{}")

        cls.api, cls.files = ThreadingHTTPServer(("127.0.0.1", 0), Handler), ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        for srv in (cls.api, cls.files):
            threading.Thread(target=srv.serve_forever, daemon=True).start()

    @classmethod
    def stop(cls):
        for srv in (cls.api, cls.files):
            srv.shutdown()
            srv.server_close()

    @classmethod
    def right_hash(cls):
        return hashlib.sha256(cls.setup).hexdigest()

    @classmethod
    def sums(cls):
        return (f"{cls.sums_hash or cls.right_hash()}  {SETUP}\n"
                f"{'0' * 64}  Hoard-{NEXT}-windows.zip\n").encode()

    @classmethod
    def releases(cls):
        base = f"http://127.0.0.1:{cls.api.server_port}/dl/"
        return [release("unity-v100.0.0"), release("v100.0.0", draft=True), release("v101.0.0", prerelease=True),
                release("v2.0.0"),
                release(f"v{NEXT}", assets=[
                    {"name": SETUP, "size": len(cls.setup), "browser_download_url": base + SETUP,
                     "digest": f"sha256:{cls.digest or cls.right_hash()}"},
                    {"name": "SHA256SUMS-windows.txt", "size": 200, "browser_download_url": base + "SHA256SUMS-windows.txt"}])]

    @classmethod
    def use(cls, test):
        api = f"http://127.0.0.1:{cls.api.server_port}"
        egress._TEST_ORIGINS.update({api, f"http://localhost:{cls.files.server_port}"})
        test.addCleanup(egress._TEST_ORIGINS.clear)
        patch = mock.patch.object(updater, "API", api)
        patch.start()
        test.addCleanup(patch.stop)
        cls.sums_hash = cls.digest = None
        cls.seen.clear()


class Versions(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(updater.newer("2.10.0", "2.9.9"))
        self.assertTrue(updater.newer("v3.0.0", "2.99.99"))
        self.assertFalse(updater.newer("2.6.0", "2.6.0"))
        self.assertFalse(updater.newer("2.5.9", "2.6.0"))
        for bad in ("", "latest", "2.6", "2.6.0-beta", "unity-v9.0.0", "v2.6.0.1", None):
            self.assertFalse(updater.newer(bad, "0.0.1"), bad)
        self.assertTrue(updater.newer(NEXT))

    def test_only_hoards_own_published_releases(self):
        """Not the Unity package's releases, drafts, pre-releases or anything not tagged vX.Y.Z; the highest wins,
        whatever order GitHub lists them in."""
        picked = updater.pick_latest([complete_release("v2.5.0"), complete_release("unity-v9.9.9"),
                                      complete_release("v9.0.0", draft=True), complete_release("v8.0.0", prerelease=True),
                                      complete_release("v7.0.0-rc1"), complete_release("v2.10.0"),
                                      complete_release("v2.9.0"), "junk", None])
        self.assertEqual(picked["tag_name"], "v2.10.0")
        self.assertIsNone(updater.pick_latest([release("unity-v3.0.0")]))
        self.assertIsNone(updater.pick_latest({"message": "Not Found"}))

    def test_a_release_without_its_files_is_never_offered(self):
        """2.8.2 was published by hand without its files: the updater offered it, and it couldn't be installed."""
        empty = release("v2.8.2")
        only_installer = release("v2.8.4", assets=[{"name": updater.SETUP_NAME.format("2.8.4")}])
        picked = updater.pick_latest([complete_release("v2.8.1"), empty, only_installer])
        self.assertEqual(picked["tag_name"], "v2.8.1")
        self.assertIsNone(updater.pick_latest([empty]))
        self.assertEqual(updater.pick_latest([empty, complete_release("v2.8.3")])["tag_name"], "v2.8.3")

    def test_what_the_page_is_shown(self):
        r = release("v3.1.0", html_url="https://evil.example/", body="x" * 10000)
        shown = updater.describe(r)
        self.assertEqual(shown["version"], "3.1.0")
        self.assertEqual(shown["url"], updater.RELEASES_PAGE, "only links to Hoard's own releases")
        self.assertEqual(len(shown["notes"]), 4000)
        self.assertFalse(shown["has_installer"])


class Checksums(unittest.TestCase):
    def test_sums_file(self):
        h = "ab" * 32
        text = f"\ufeff{h.upper()}  Hoard-Setup-3.0.0.exe\r\n{'cd' * 32} *Hoard-3.0.0-windows.zip\nnot a line\n"
        self.assertEqual(updater.parse_sums(text), {"Hoard-Setup-3.0.0.exe": h, "Hoard-3.0.0-windows.zip": "cd" * 32})

    def test_both_hashes_must_agree(self):
        h = "ab" * 32
        r = release("v3.0.0", assets=[{"name": "Hoard-Setup-3.0.0.exe", "digest": f"sha256:{h}"}])
        self.assertEqual(updater.expected_hash(r, "Hoard-Setup-3.0.0.exe", f"{h}  Hoard-Setup-3.0.0.exe"), h)
        with self.assertRaises(updater.UpdateRefused):
            updater.expected_hash(r, "Hoard-Setup-3.0.0.exe", f"{'cd' * 32}  Hoard-Setup-3.0.0.exe")
        with self.assertRaises(updater.UpdateRefused):
            updater.expected_hash(r, "Hoard-Setup-3.0.0.exe", f"{h}  Hoard-3.0.0-windows.zip")
        no_digest = release("v3.0.0", assets=[{"name": "Hoard-Setup-3.0.0.exe"}])
        self.assertEqual(updater.expected_hash(no_digest, "Hoard-Setup-3.0.0.exe", f"{h}  Hoard-Setup-3.0.0.exe"), h)


class Downloading(unittest.TestCase):
    """Against the stand-in GitHub."""

    @classmethod
    def setUpClass(cls):
        _GitHub.start()

    @classmethod
    def tearDownClass(cls):
        _GitHub.stop()

    def setUp(self):
        _GitHub.use(self)
        for f in updater.updates_dir().glob("*") if updater.updates_dir().is_dir() else []:
            f.unlink()

    def test_the_newest_release(self):
        latest = updater.fetch_latest()
        self.assertEqual(latest["tag_name"], f"v{NEXT}")
        self.assertTrue(updater.describe(latest)["has_installer"])
        self.assertEqual({ua for _port, _path, ua in _GitHub.seen}, {f"Hoard/{__version__}"}, "only Hoard's name and version")

    def test_a_checked_installer(self):
        path = updater.download_installer(updater.fetch_latest())
        self.assertEqual(path, updater.updates_dir() / SETUP)
        self.assertEqual(path.read_bytes(), _GitHub.setup)
        self.assertTrue(updater.ready_installer(path))
        self.assertIn((_GitHub.files.server_port, f"/f/{SETUP}"), [(p, x) for p, x, _ua in _GitHub.seen], "followed the redirect")
        path.write_bytes(b"MZ changed afterwards")
        self.assertFalse(updater.ready_installer(path), "changed after it was checked: never run")

    def test_a_wrong_installer_is_deleted(self):
        for attr in ("sums_hash", "digest"):
            with self.subTest(wrong=attr):
                _GitHub.sums_hash = _GitHub.digest = None
                setattr(_GitHub, attr, "ee" * 32)
                with self.assertRaises(updater.UpdateRefused):
                    updater.download_installer(updater.fetch_latest())
                self.assertEqual(list(updater.updates_dir().glob("*")), [], "nothing left to run")

    def test_the_file_must_be_the_size_github_says(self):
        latest = updater.fetch_latest()
        latest["assets"][0]["size"] += 1
        with self.assertRaises(updater.UpdateRefused):
            updater.download_installer(latest)
        self.assertEqual(list(updater.updates_dir().glob("*.exe")), [])

    def test_no_installer(self):
        with self.assertRaises(updater.UpdateRefused):
            updater.download_installer(release(f"v{NEXT}"))

    def test_only_https_to_public_addresses(self):
        egress._TEST_ORIGINS.clear()   # the stand-in is plain http on this computer: refused like anything else
        with self.assertRaises(egress.UnsafeRequest):
            updater.fetch_latest()

    def test_the_whole_update(self):
        """Check, download, quit, and only then run the installer, with the arguments that reopen Hoard."""
        cfg = config.load_config()
        srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        quit_called = threading.Event()
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def call(method, path, body=None):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
                c.request(method, path, body=json.dumps(body) if body is not None else None,
                          headers={**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: srv.key})
                r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
                return r.status, data

            status, view = call("GET", "/api/update")
            self.assertEqual((status, view["current"]), (200, __version__))
            status, view = call("POST", "/api/update/check", {})
            self.assertEqual(status, 200)
            self.assertTrue(view["available"])
            self.assertEqual(view["latest"]["version"], NEXT)
            self.assertFalse(view["can_install"], "not the installed app")
            self.assertEqual(call("POST", "/api/update/install", {})[0], 409)

            srv.quit_app = quit_called.set
            with mock.patch.object(updater, "installed_copy", lambda: True):
                self.assertTrue(call("GET", "/api/update")[1]["can_install"])
                srv.jobs.state["running"] = True
                self.assertEqual(call("POST", "/api/update/install", {})[0], 409, "not in the middle of a job")
                srv.jobs.state["running"] = False
                self.assertEqual(call("POST", "/api/update/install", {})[0], 202)
                self.assertTrue(quit_called.wait(20), call("GET", "/api/update")[1])
            self.assertEqual(srv.updates.pending, updater.updates_dir() / SETUP)
        finally:
            srv.shutdown()
            srv.server_close()
        with mock.patch.object(updater.subprocess, "Popen") as popen:
            self.assertTrue(updater.finish(srv.updates))
        args = popen.call_args[0][0]
        self.assertEqual(args[0], str(updater.updates_dir() / SETUP))
        self.assertIn("/SILENT", args)
        self.assertIn("/RELAUNCH=1", args)
        self.assertFalse(updater.finish(None))

    def test_a_failed_download_is_shown(self):
        _GitHub.sums_hash = "ee" * 32
        updates = updater.Updates(config.load_config())
        called = threading.Event()
        self.assertIsNone(updates.start_install(called.set))
        for _ in range(100):
            if not updates.state["busy"]:
                break
            time.sleep(0.1)
        self.assertFalse(called.is_set(), "Hoard doesn't quit for an update it can't run")
        self.assertIn("disagree", updates.state["error"])
        self.assertIsNone(updates.pending)


class WhenHoardAsks(unittest.TestCase):
    def test_off_unless_turned_on(self):
        cfg = config.load_config()
        self.assertFalse(config.DEFAULT_CONFIG["check_for_updates"])
        updates = updater.Updates(cfg)
        updates.state["checked"] = 0
        self.assertFalse(updates.due())
        with mock.patch.object(updater, "fetch_latest") as fetch:
            updates.check_in_background()
            time.sleep(0.2)
            fetch.assert_not_called()
        cfg["check_for_updates"] = True
        self.assertTrue(updates.due())
        updates.state["checked"] = time.time() - 3600
        self.assertFalse(updates.due(), "at most once a day")

    def test_the_setting(self):
        cfg = config.load_config()
        self.assertEqual(server.apply_settings(cfg, {"check_for_updates": 1}), {"check_for_updates": True})
        self.assertFalse(server.public_settings(cfg)["check_for_updates"])

    def test_the_last_check_is_remembered(self):
        with mock.patch.object(updater, "fetch_latest", lambda: release(f"v{NEXT}")):
            updater.Updates(config.load_config()).check()
        again = updater.Updates(config.load_config())
        self.assertEqual(again.state["latest"]["version"], NEXT)
        self.assertTrue(again.view(False)["available"])
        (updater.data_dir() / "update.json").write_text("{damaged", "utf-8")
        self.assertIsNone(updater.Updates(config.load_config()).state["latest"])

    def test_old_installers_are_tidied(self):
        folder = updater.updates_dir()
        folder.mkdir(parents=True, exist_ok=True)
        for f in folder.iterdir():
            f.unlink()
        old, current, new, other = (folder / "Hoard-Setup-1.0.0.exe", folder / f"Hoard-Setup-{__version__}.exe.sha256",
                                    folder / SETUP, folder / "notes.txt")
        for f in (old, current, new, other):
            f.write_text("x")
        updater.tidy()
        self.assertEqual(sorted(f.name for f in folder.iterdir()), sorted([new.name, other.name]))
        new.unlink()
        other.unlink()

    def test_only_the_installed_app_installs(self):
        self.assertFalse(updater.installed_copy(), "running from source")

    def test_the_installer_reopens_hoard(self):
        iss = (REPO / "packaging" / "hoard.iss").read_text("utf-8")
        self.assertIn("Check: RelaunchAfterUpdate", iss)
        self.assertIn("{param:RELAUNCH|0}", iss)
        self.assertIn("/RELAUNCH=1", updater.INSTALLER_ARGS)
        self.assertIn("/SILENT", updater.INSTALLER_ARGS)


if __name__ == "__main__":
    unittest.main()
