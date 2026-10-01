"""Local support-report tests: diagnostics stay private until the sanitized ZIP is created."""
from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
_TEST_HOME = Path(tempfile.mkdtemp(prefix="hoard-diagnostic-tests-"))
os.environ["HOARD_DATA_DIR"] = str(_TEST_HOME / "Hoard")
import sys
sys.path.insert(0, str(REPO))

from hoard import config, diagnostics, library, safety, server  # noqa: E402


class Sanitizing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "downloads"
        self.root.mkdir()
        self.cfg = {**config.load_config(), "root": str(self.root), "setup_done": True}
        self.patcher = mock.patch.object(diagnostics, "support_report_dir", return_value=Path(self.tmp.name) / "reports")
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        log_dir = diagnostics.data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "hoard.log").write_text(
            "[Booth] Secret Creator / My Private Asset\n"
            f"    saved: {self.root}\\Booth\\Secret Creator\\My Private Asset.zip\n"
            "Authorization: Bearer super-secret-token\n"
            "Cookie: session=super-secret-cookie\n"
            "URL: https://private.example.com/my-purchase?download=signed-value\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_sensitive_values_are_not_exported(self):
        raw = (diagnostics.data_dir() / "logs" / "hoard.log").read_text("utf-8")
        clean = diagnostics.sanitize_text(raw, self.cfg, asset_names=True)
        for secret in ("super-secret-token", "super-secret-cookie", "Secret Creator", "My Private Asset", str(self.root)):
            self.assertNotIn(secret, clean)
        self.assertIn("<CREATOR_001>", clean)
        self.assertIn("<ASSET_001>", clean)
        self.assertIn("https://<URL_HOST_001>/<path>", clean)

    def test_incident_traceback_is_local_and_sanitized_in_export(self):
        lib = library.Library(Path(self.tmp.name) / "library.json")
        with lib.lock:
            lib.data["items"] = [library.item("booth", "111", name="My Private Asset", creator="Secret Creator", thumbnail=None)]
            lib.save()
        try:
            raise RuntimeError(f"failed for My Private Asset at {self.root} with token super-secret-token")
        except RuntimeError as exc:
            incident = diagnostics.record_exception(exc, area="job", task="sync", store="booth")
        self.assertIn("super-secret-token", json.dumps(diagnostics._recent_incidents()))
        result = diagnostics.create_support_report(self.cfg, lib, {"diagnostic": incident}, notes="I saw My Private Asset from Secret Creator")
        with zipfile.ZipFile(result["path"]) as archive:
            files = {name: archive.read(name).decode("utf-8") for name in archive.namelist()}
        joined = "\n".join(files.values())
        self.assertNotIn("super-secret-token", joined)
        self.assertNotIn("Secret Creator", joined)
        self.assertNotIn(str(self.root), joined)
        self.assertIn("traceback.txt", files)
        recent = json.loads(files["report.json"])["recent_incidents"]
        self.assertTrue(recent[-1]["has_traceback"])
        self.assertNotIn("traceback", recent[-1])

    def test_report_contains_only_safe_files(self):
        lib = library.Library(Path(self.tmp.name) / "library.json")
        result = diagnostics.create_support_report(self.cfg, lib)
        with zipfile.ZipFile(result["path"]) as archive:
            names = set(archive.namelist())
        self.assertIn("README.txt", names)
        self.assertIn("report.json", names)
        self.assertIn("report.txt", names)
        self.assertIn("application-log.txt", names)
        forbidden = {"config.json", "library.json", "integrity.key", "running.json", "cookies.sqlite"}
        self.assertTrue(names.isdisjoint(forbidden))

    def test_what_the_first_real_reports_let_through(self):
        """Found in support reports from 2.8.4 (the names here are made up): a Windows user name inside a path
        written with doubled backslashes, as Python writes one in an error message, and downloaded file names at
        the start of progress bars. Both are now hidden, and the log uses the same placeholders as the report."""
        log = (diagnostics.data_dir() / "logs" / "hoard.log")
        log.write_text(
            "PermissionError: [Errno 13] Permission denied: "
            "'C:\\\\Users\\\\kitsune\\\\AppData\\\\Local\\\\Hoard\\\\sign-ins\\\\gumroad\\\\Default\\\\Network\\\\Cookies'\n"
            "FileNotFoundError: 'C:\\\\\\\\Users\\\\\\\\kitsune\\\\\\\\Downloads'\n"
            "Mochi Deluxe Hair.unitypackage:  82%|########2 | 1.00M/1.22M [00:00<00:00, 3.45MB/s]\n"
            "Rusk_Licenses.pdf: 100%|##########| 198k/198k [00:00<00:00, 1.01MB/s]\n"
            "[Jinxxy] Secret Creator / My Private Asset\n"
            "    downloading: Rusk_Licenses.pdf\n"
            "    saved: Mochi Deluxe Hair.unitypackage\n"
            "Tagged 4 assets with 0 suggested tags. Top: -\n", encoding="utf-8")
        lib = library.Library(Path(self.tmp.name) / "library.json")
        with lib.lock:
            lib.data["items"] = [library.item("jinxxy", "111", name="My Private Asset", creator="Secret Creator", thumbnail=None)]
        result = diagnostics.create_support_report(self.cfg, lib, job={"store": "jinxxy", "running": True,
                                                                       "message": "[Jinxxy] Secret Creator / My Private Asset"})
        with zipfile.ZipFile(result["path"]) as archive:
            files = {n: archive.read(n).decode("utf-8") for n in archive.namelist()}
        everything = "\n".join(files.values())
        for private in ("kitsune", "Mochi Deluxe Hair", "Rusk_Licenses", "Secret Creator", "My Private Asset"):
            self.assertNotIn(private, everything)
        app_log = files["application-log.txt"]
        self.assertIn("<WINDOWS_USER>", app_log)
        self.assertIn("82%|", app_log, "the progress itself is kept")
        self.assertIn("Tagged 4 assets", app_log, "and ordinary lines are left alone")
        bar_name = app_log.splitlines()[2].split(":")[0]
        self.assertIn(f"saved: {bar_name}", app_log, "a file's progress bar and its saved: line share a placeholder")
        store_line = next(line for line in app_log.splitlines() if line.startswith("[Jinxxy]"))
        self.assertIn(store_line, files["report.txt"], "the log names the item as the report does")

    def test_the_summary_a_sync_ends_with(self):
        """The Updated, Skipped and Failed lines at the end of a sync name products and creators in their own format
        ("Booth: creator / product / file - why"), and in 2.8.4 went into reports as they were."""
        lib = library.Library(Path(self.tmp.name) / "library.json")
        with lib.lock:
            lib.data["items"] = [library.item("booth", "111", name="Secret Fox Avatar", creator="Kitsu Studio"),
                                 library.item("gumroad", "abc", name="Hidden Hoodie", creator="Mochi Works")]
        (diagnostics.data_dir() / "logs" / "hoard.log").write_text(
            "\n=== Summary ===\n"
            "Updated on the store since last sync:\n"
            "  - Booth: Kitsu Studio / Secret Fox Avatar / SecretFox_v2.unitypackage\n"
            "Skipped:\n"
            "  - Gumroad: Hidden Hoodie - no download page (refunded or membership inactive)\n"
            "  - Booth: Unlisted Thing / extra.zip - streaming only, no download\n"
            "  - Booth: not signed in, so skipped. Sign in from Stores to include it.\n"
            "Failed:\n"
            "  - Gumroad: Mochi Works / Hidden Hoodie / hoodie.zip - HTTP 500\n"
            "  - itch.io: Mochi Works / Hidden Hoodie - timed out\n", encoding="utf-8")
        result = diagnostics.create_support_report(self.cfg, lib)
        with zipfile.ZipFile(result["path"]) as archive:
            log = archive.read("application-log.txt").decode("utf-8")
        for name in ("Kitsu Studio", "Secret", "Fox", "Hidden Hoodie", "Mochi Works", "SecretFox_v2", "Unlisted Thing",
                     "extra.zip", "hoodie.zip"):
            self.assertNotIn(name, log)
        self.assertIn("  - Gumroad: <CREATOR_002> / <ASSET_002> / <ASSET_", log, "the same name, the same placeholder")
        self.assertIn(" - HTTP 500", log, "what went wrong stays")
        self.assertIn("  - Booth: not signed in, so skipped. Sign in from Stores to include it.", log, "not a name")

    def test_this_launch_and_the_one_before(self):
        """2.9.2: a log for each launch. The report takes this launch's (the one Hoard is writing), and the one
        before it, not whichever log happens to be the newest file."""
        import os
        import time
        from hoard import paths
        folder = paths.logs_dir()
        for other in folder.glob("hoard*.log"):   # only these two (other tests leave logs here too)
            other.unlink()
        before = folder / "hoard-2026-09-29_10-00-00.log"
        before.write_text("[Jinxxy] earlier launch line\n", encoding="utf-8")
        now = folder / "hoard-2026-09-30_10-00-00.log"
        now.write_text("[Jinxxy] this launch line\n", encoding="utf-8")
        stamp = time.time()
        os.utime(before, (stamp - 7200, stamp - 7200))
        os.utime(now, (stamp - 3600, stamp - 3600))
        (folder / "hoard.log").unlink(missing_ok=True)   # (setUp's, as a pre-2.9.2 log)
        paths.current_log = now
        self.addCleanup(setattr, paths, "current_log", None)
        result = diagnostics.create_support_report(self.cfg, library.Library(Path(self.tmp.name) / "library.json"))
        with zipfile.ZipFile(result["path"]) as archive:
            this, earlier = archive.read("application-log.txt").decode(), archive.read("application-old-log.txt").decode()
        self.assertIn("this launch line", this)
        self.assertIn("earlier launch line", earlier)

    def test_a_name_with_secret_in_it(self):
        """"secret" or "token" followed by a word isn't a credential unless the word looks like one."""
        self.assertEqual(diagnostics._redact_credentials("Secret Fox Avatar and token soup"), "Secret Fox Avatar and token soup")
        self.assertEqual(diagnostics._redact_credentials("token abcdefghijklmnop1234"), "token [credential]")

    def test_the_webview_is_reported_when_its_there(self):
        """pywebview has no __version__, so every 2.8.4 report said "WebView: not installed" beside a check that
        found it."""
        fake = type(sys)("webview")
        with mock.patch.dict(sys.modules, {"webview": fake}):
            env = diagnostics._environment(self.cfg, diagnostics._ReportSanitizer(self.cfg))
        self.assertTrue(env["webview"])
        with mock.patch.dict(sys.modules, {"webview": None}):
            env = diagnostics._environment(self.cfg, diagnostics._ReportSanitizer(self.cfg))
        self.assertIsNone(env["webview"])


class ServerExposure(unittest.TestCase):
    def test_default_export_folder_is_user_visible(self):
        expected = diagnostics.documents_dir() / "Hoard" / "Support Reports"
        self.assertEqual(diagnostics.support_report_dir(), expected)

    def test_report_endpoint_creates_local_sanitized_zip(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "downloads"
        root.mkdir()
        report_dir = Path(tmp.name) / "Support Reports"
        cfg = {**config.load_config(), "root": str(root), "setup_done": True}
        srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False, config_path=Path(tmp.name) / "config.json")
        with srv.lib.lock:
            srv.lib.data["items"] = [
                library.item("booth", "111", name="Private Asset", creator="Secret Creator", thumbnail=None)
            ]
            srv.lib.save()
        srv.jobs.state["task"] = None
        srv.jobs.state["store"] = None
        try:
            raise RuntimeError("problem for Private Asset")
        except RuntimeError as exc:
            srv.jobs.state["diagnostic"] = diagnostics.record_exception(exc, area="job", task="sync", store="booth")
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        with mock.patch.object(diagnostics, "support_report_dir", return_value=report_dir):
            body = json.dumps({"notes": "Private Asset", "context": {"source": "job", "store": "booth"}})
            # Making a report gathers the environment first (Python's platform lookups, which on Windows ask WMI,
            # and pywebview's first import): on a cold Windows runner that alone has taken over 5 seconds. This
            # checks what the report holds, not how fast it's made.
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=60)
            conn.request("POST", "/api/diagnostics/report", body=body,
                         headers={safety.ACCESS_HEADER: srv.key, "Content-Type": "application/json"})
            response = conn.getresponse()
            data = json.loads(response.read().decode("utf-8"))
            conn.close()
        self.assertEqual(response.status, 200)
        self.assertTrue(data.get("ok"))
        report_path = Path(data["path"])
        self.assertTrue(report_path.is_file())
        self.assertEqual(report_path.parent, report_dir)
        with zipfile.ZipFile(report_path) as archive:
            joined = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist())
        self.assertNotIn("Private Asset", joined)


    def test_raw_diagnostic_never_reaches_status(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "downloads"
        root.mkdir()
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True},
                               lan=False, config_path=Path(tmp.name) / "config.json")
        srv.jobs.state["diagnostic"] = {"id": "H-TEST", "traceback": "very-private-traceback", "message": "secret"}
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
        conn.request("GET", "/api/status", headers={safety.ACCESS_HEADER: srv.key})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()
        self.assertEqual(response.status, 200)
        self.assertNotIn("diagnostic", body["job"])
        self.assertNotIn("very-private-traceback", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
