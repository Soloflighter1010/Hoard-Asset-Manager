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
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
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
