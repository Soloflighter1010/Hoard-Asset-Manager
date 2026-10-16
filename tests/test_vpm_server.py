"""Projects through Hoard's server (hoard/vpm/api.py, server.py's /api/vpm): a project made from a template, its
VRChat SDK installed from a repository (a stand-in on this computer), products from the library put in, its
packages changed, all as Tasks jobs; and only projects on the list are ever touched."""
import gzip
import hashlib
import http.client
import http.server
import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from urllib.parse import quote
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))   # (the unitypackage maker in test_vpm_projects.py)

from hoard import config, egress, server  # noqa: E402
from hoard.safety import ACCESS_HEADER  # noqa: E402
from test_vpm_projects import SAMPLE, make_unitypackage  # noqa: E402


class _Repo(http.server.BaseHTTPRequestHandler):
    files: dict = {}

    def do_GET(self):
        body = _Repo.files.get(self.path)
        self.send_response(200 if body is not None else 404)
        self.send_header("Content-Length", str(len(body or b"")))
        self.end_headers()
        self.wfile.write(body or b"")

    def log_message(self, *a):
        pass


def _zip(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for k, v in members.items():
            zf.writestr(k, v)
    return buf.getvalue()


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Repo)
        threading.Thread(target=cls.repo.serve_forever, daemon=True).start()
        cls.origin = f"http://127.0.0.1:{cls.repo.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.repo.shutdown()
        cls.repo.server_close()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.vcc = self.tmp / "VRChatCreatorCompanion"
        env = mock.patch.dict(os.environ, {"HOARD_VCC_DIR": str(self.vcc), "HOARD_DATA_DIR": str(self.tmp / "Hoard")})
        env.start()
        self.addCleanup(env.stop)
        egress._TEST_ORIGINS.add(self.origin)
        self.addCleanup(egress._TEST_ORIGINS.clear)
        # VRChat's official repository, as a cache file whose packages download from the stand-in
        packages = {}
        for name, deps in (("com.vrchat.base", {}), ("com.vrchat.avatars", {"com.vrchat.base": "3.10.5"})):
            data = _zip({"package.json": json.dumps({"name": name, "version": "3.10.5"}), "Runtime/x.cs": "//"})
            _Repo.files[f"/{name}.zip"] = data
            packages[name] = {"versions": {"3.10.5": {"name": name, "version": "3.10.5", "unity": "2022.3",
                                                      "url": f"{self.origin}/{name}.zip", "vpmDependencies": deps,
                                                      "zipSHA256": hashlib.sha256(data).hexdigest()}}}
        (self.vcc / "Repos").mkdir(parents=True)
        (self.vcc / "Repos" / "vrc-official.json").write_text(json.dumps(
            {"repo": {"name": "Official", "id": "com.vrchat.repos.official", "url": "https://packages.vrchat.com/official?download",
                      "packages": packages}}))
        (self.vcc / "settings.json").write_text(json.dumps({"userProjects": [], "keepMe": 1}))
        downloads = self.tmp / "downloads" / "Booth" / "Hoodie"
        downloads.mkdir(parents=True)
        (downloads / "Hoodie.unitypackage").write_bytes(make_unitypackage(SAMPLE))
        self.asset = {"abs_folder": str(downloads), "name": "Hoodie", "store": "Booth", "tag_key": "booth/hoodie", "id": 0,
                      "files": [{"path": "Hoodie.unitypackage", "size": 1}]}
        self.srv = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        self.srv.asset_by_key = lambda key: self.asset if key == "booth/hoodie" else None
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=30)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={**({"Content-Type": "application/json"} if body is not None else {}), ACCESS_HEADER: self.srv.key})
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw or b"{}")
        except ValueError:
            return r.status, {"raw": raw[:200]}

    def wait(self):
        for _ in range(300):
            if not self.srv.jobs.state["running"] and not self.srv.jobs.state["queue"]:
                return self.srv.jobs.history[0] if self.srv.jobs.history else None
            time.sleep(0.05)
        self.fail("the job didn't finish")

    def test_make_a_project_with_its_sdk_and_a_product(self):
        status, overview = self.call("GET", "/api/vpm")
        self.assertEqual(status, 200)
        self.assertEqual({t["name"] for t in overview["templates"]} >= {"VRChat Avatars", "VRChat Worlds", "Blank"}, True)
        self.assertEqual(overview["repos"][0]["packages"], 2)
        status, made = self.call("POST", "/api/vpm/create", {
            "name": "My Avatar", "location": str(self.tmp / "Projects"), "template": "com.anatawa12.vrc-get.vrchat.avatars",
            "unity": "2022.3.22f1", "picks": [{"key": "booth/hoodie", "kind": "unitypackage", "file": "Hoodie.unitypackage"}]})
        self.assertEqual(status, 200, made)
        job = self.wait()
        project = self.tmp / "Projects" / "My Avatar"
        self.assertEqual(job["outcome"], "done", job)
        self.assertTrue((project / "Packages" / "com.vrchat.avatars" / "Runtime" / "x.cs").is_file())
        self.assertTrue((project / "Packages" / "com.vrchat.base" / "package.json").is_file())
        self.assertEqual((project / "Assets" / "Creator" / "Hoodie.prefab").read_bytes(), b"%YAML 1.1\nprefab")
        saved = json.loads((self.vcc / "settings.json").read_text())
        self.assertEqual((saved["userProjects"], saved["keepMe"]), ([str(project)], 1))
        status, detail = self.call("GET", f"/api/vpm/project?path={quote(str(project))}")
        self.assertEqual(status, 200, detail)
        self.assertEqual({p["name"] for p in detail["packages"]}, {"com.vrchat.avatars", "com.vrchat.base"})
        self.assertFalse(detail["needs_repair"])
        self.assertEqual(detail["preloaded"][0]["tag_key"], "booth/hoodie")
        # removing the SDK: previewed first, then done as a job
        status, preview = self.call("POST", "/api/vpm/preview", {"path": str(project), "remove": ["com.vrchat.avatars"]})
        self.assertEqual({r["name"] for r in preview["remove"]}, {"com.vrchat.avatars", "com.vrchat.base"})
        self.assertEqual(self.call("POST", "/api/vpm/apply", {"path": str(project), "remove": ["com.vrchat.avatars"]})[0], 200)
        self.assertEqual(self.wait()["outcome"], "done")
        self.assertFalse((project / "Packages" / "com.vrchat.avatars").exists())

    def test_only_listed_projects_are_touched(self):
        elsewhere = self.tmp / "NotListed"
        for sub in ("Assets", "Packages", "ProjectSettings"):
            (elsewhere / sub).mkdir(parents=True)
        for path, body in (("/api/vpm/apply", {"repair": True}), ("/api/vpm/backup", {}), ("/api/vpm/preload", {"picks": []}),
                           ("/api/vpm/open", {}), ("/api/vpm/preview", {"repair": True}), ("/api/vpm/remove-project", {})):
            status, answer = self.call("POST", path, {"path": str(elsewhere), **body})
            self.assertEqual(status, 400, (path, answer))
        self.assertEqual(self.call("GET", f"/api/vpm/project?path={quote(str(elsewhere))}")[0], 400)
        self.assertEqual(self.call("POST", "/api/vpm/add-project", {"path": str(self.tmp)})[0], 400, "not a project")
        self.assertEqual(self.call("POST", "/api/vpm/add-project", {"path": "relative"})[0], 400)
        self.assertEqual(self.call("POST", "/api/vpm/add-project", {"path": str(elsewhere)})[0], 200)
        self.assertEqual(self.call("GET", f"/api/vpm/project?path={quote(str(elsewhere))}")[0], 200)

    def test_names_and_settings(self):
        status, check = self.call("POST", "/api/vpm/check-name", {"location": str(self.tmp), "name": "CON"})
        self.assertIsNotNone(check["problem"])
        self.assertEqual(self.call("POST", "/api/vpm/create", {"name": "a/b", "location": str(self.tmp)})[0], 400)
        self.assertEqual(self.call("POST", "/api/vpm/settings", {"projects_folder": "relative"})[0], 400)
        self.assertEqual(self.call("POST", "/api/vpm/settings", {"projects_folder": str(self.tmp / "P"), "prerelease": True})[0], 200)
        saved = json.loads((self.vcc / "settings.json").read_text())
        self.assertEqual((saved["defaultProjectPath"], saved["showPrereleasePackages"]), (str(self.tmp / "P"), True))

    def test_presets(self):
        preset = {"name": "Avatar base", "template": "com.anatawa12.vrc-get.vrchat.avatars", "unity": "2022.3.22f1",
                  "packages": {"nadena.dev.modular-avatar": "^1.10.0"},
                  "products": [{"key": "booth/hoodie", "kind": "unitypackage", "file": "Hoodie.unitypackage", "label": "Hoodie"}]}
        status, saved = self.call("POST", "/api/vpm/presets", {"action": "save", "preset": preset})
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.call("GET", "/api/vpm")[1]["presets"][0]["name"], "Avatar base")
        status, out = self.call("POST", "/api/vpm/presets", {"action": "export", "id": saved["preset"]["id"]})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["left_out"], [], "a plain .unitypackage goes into the ALCOM template")
        template = json.loads(Path(out["path"]).read_text())
        self.assertEqual(template["unityPackages"], [str(Path(self.asset["abs_folder"]) / "Hoodie.unitypackage")])
        self.assertEqual(template["vpmDependencies"], {"nadena.dev.modular-avatar": "^1.10.0"})
        listed = {t["name"]: t for t in self.call("GET", "/api/vpm")[1]["templates"]}
        self.assertTrue(listed["Avatar base"]["available"], "ALCOM's template, made from it, is listed as one")
        self.assertEqual(self.call("POST", "/api/vpm/presets", {"action": "save", "preset": {"name": ""}})[0], 400)


if __name__ == "__main__":
    unittest.main()
