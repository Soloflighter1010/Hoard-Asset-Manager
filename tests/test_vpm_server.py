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
        (self.vcc / "Repos" / "vrc-curated.json").write_text(json.dumps(
            {"repo": {"name": "Curated", "url": "https://packages.vrchat.com/curated?download", "packages": {}}}))
        # a repository of yours that hasn't been fetched on this computer yet: fetched when a project needs packages
        extra = _zip({"package.json": json.dumps({"name": "com.example.extra", "version": "1.0.0"})})
        _Repo.files["/extra.zip"] = extra
        _Repo.files["/extra.json"] = json.dumps({"name": "Extra", "id": "com.example.repo", "url": f"{self.origin}/extra.json",
                                                 "packages": {"com.example.extra": {"versions": {"1.0.0": {
                                                     "name": "com.example.extra", "version": "1.0.0",
                                                     "url": f"{self.origin}/extra.zip"}}}}}).encode()
        (self.vcc / "settings.json").write_text(json.dumps({"userProjects": [], "keepMe": 1, "userRepos": [
            {"localPath": str(self.vcc / "Repos" / "extra.json"), "url": f"{self.origin}/extra.json", "name": "Extra"}]}))
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

    def test_the_backups_panel(self):
        """Projects' backups: listed with which are old, the rule changed, old ones moved to another drive as a task,
        one deleted, and a file that isn't one of the backups refused."""
        settings = json.loads((self.vcc / "settings.json").read_text())
        folder = self.tmp / "Backups"
        settings["projectBackupPath"] = str(folder)
        (self.vcc / "settings.json").write_text(json.dumps(settings))
        folder.mkdir()
        for m in range(1, 6):
            (folder / f"Avatar-2024-0{m}-01T10-00-00.zip").write_bytes(b"PK" + bytes(m))
        (folder / "notes.zip").write_bytes(b"mine")
        status, view = self.call("POST", "/api/vpm/backups", {})
        self.assertEqual((status, len(view["backups"]), view["old_count"]), (200, 5, 2))
        status, overview = self.call("GET", "/api/vpm")
        self.assertEqual(overview["backups"]["old_count"], 2, "the list's page says when the drive is low")
        status, view = self.call("POST", "/api/vpm/backups/settings", {"keep": 1, "days": 7})
        self.assertEqual((view["keep"], view["old_count"]), (1, 4))
        status, out = self.call("POST", "/api/vpm/backups/delete", {"paths": [str(folder / "notes.zip")]})
        self.assertEqual(status, 400)
        self.assertTrue((folder / "notes.zip").exists())
        old = [b["path"] for b in view["backups"] if b["old"]]
        away = self.tmp / "E" / "Old backups"
        status, out = self.call("POST", "/api/vpm/backups/move", {"paths": old[:3], "to": str(away)})
        self.assertEqual(status, 200, out)
        done = self.wait()
        self.assertIn("Moved 3 backups", done["message"])
        self.assertEqual(len(list(away.glob("*.zip"))), 3)
        status, view = self.call("POST", "/api/vpm/backups", {})
        self.assertEqual((len(view["backups"]), len(view["moved"]), view["moved_to"]), (2, 3, str(away)))
        status, out = self.call("POST", "/api/vpm/backups/delete", {"paths": [view["moved"][0]["path"]]})
        self.assertEqual((status, out["deleted"]), (200, 1))
        status, out = self.call("POST", "/api/vpm/backups/move", {"paths": [view["backups"][0]["path"]], "to": "relative"})
        self.assertEqual(status, 400)

    def test_make_a_project_with_its_sdk_and_a_product(self):
        status, overview = self.call("GET", "/api/vpm")
        self.assertEqual(status, 200)
        self.assertEqual({t["name"] for t in overview["templates"]} >= {"VRChat Avatars", "VRChat Worlds", "Blank"}, True)
        self.assertEqual(overview["repos"][0]["packages"], 2)
        status, made = self.call("POST", "/api/vpm/create", {
            "name": "My Avatar", "location": str(self.tmp / "Projects"), "template": "com.anatawa12.vrc-get.vrchat.avatars",
            "unity": "2022.3.22f1", "packages": {"com.example.extra": "*"},
            "picks": [{"key": "booth/hoodie", "kind": "unitypackage", "file": "Hoodie.unitypackage"}]})
        self.assertEqual(status, 200, made)
        job = self.wait()
        project = self.tmp / "Projects" / "My Avatar"
        self.assertEqual(job["outcome"], "done", job)
        self.assertTrue((project / "Packages" / "com.vrchat.avatars" / "Runtime" / "x.cs").is_file())
        self.assertTrue((project / "Packages" / "com.vrchat.base" / "package.json").is_file())
        self.assertTrue((project / "Packages" / "com.example.extra" / "package.json").is_file(),
                        "from a repository fetched for the first time, as the project was made")
        self.assertTrue((self.vcc / "Repos" / "extra.json").is_file(), "its listing kept, as ALCOM keeps it")
        self.assertEqual((project / "Assets" / "Creator" / "Hoodie.prefab").read_bytes(), b"%YAML 1.1\nprefab")
        saved = json.loads((self.vcc / "settings.json").read_text())
        self.assertEqual((saved["userProjects"], saved["keepMe"]), ([str(project)], 1))
        status, detail = self.call("GET", f"/api/vpm/project?path={quote(str(project))}")
        self.assertEqual(status, 200, detail)
        self.assertEqual({p["name"] for p in detail["packages"]}, {"com.vrchat.avatars", "com.vrchat.base", "com.example.extra"})
        self.assertFalse(detail["needs_repair"])
        self.assertEqual(detail["preloaded"][0]["tag_key"], "booth/hoodie")
        self.assertEqual(detail["preloaded"][0]["added"], ["Assets/Creator"])
        # what went in is written into the project too (#155): Hoard for Unity's list of imports, and one to read
        log = json.loads((project / "ProjectSettings" / "Hoard" / "imports.json").read_text("utf-8"))
        self.assertEqual(log["format"], "hoard-unity-imports")
        entry = log["imports"][0]
        self.assertEqual((entry["store"], entry["name"], entry["file"], entry["via"], entry["added"]),
                         ("Booth", "Hoodie", "Hoodie.unitypackage", "hoard", ["Assets/Creator"]))
        self.assertRegex(entry["imported_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        note = (project / "Hoard imports.md").read_text("utf-8")
        self.assertIn("**Hoodie** (Booth): `Hoodie.unitypackage`", note)
        self.assertIn("- Added: `Assets/Creator`", note)
        with mock.patch.object(server, "reveal", lambda p: str(p)):   # Manage's Show the list in the project
            status, shown = self.call("POST", "/api/vpm/open-folder", {"path": str(project), "show": "imports"})
        self.assertEqual((status, Path(shown["in"])), (200, project / "Hoard imports.md"))
        (project / "Hoard imports.md").unlink()
        self.assertEqual(self.call("POST", "/api/vpm/open-folder", {"path": str(project), "show": "imports"})[0], 404)
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

    def test_versions_to_choose_from(self):
        """Manage project's and Add packages' version choice (#160): newest first, only those that work in the
        project's Unity, never a yanked one, and prereleases when they're offered or one is installed."""
        cache = self.vcc / "Repos" / "vrc-official.json"
        repo = json.loads(cache.read_text())
        base = repo["repo"]["packages"]["com.vrchat.base"]["versions"]
        for v, more in (("3.9.0", {}), ("3.11.0-beta.1", {}), ("3.8.0", {"vrc-get": {"yanked": "broken"}}),
                        ("3.12.0", {"unity": "2023.1"})):
            base[v] = {**base["3.10.5"], "version": v, **more}
        cache.write_text(json.dumps(repo))
        self.srv.vpm.forget()

        def versions(**query):
            q = "&".join(f"{k}={v}" for k, v in {"name": "com.vrchat.base", "unity": "2022.3.22f1", **query}.items())
            status, body = self.call("GET", f"/api/vpm/versions?{q}")
            self.assertEqual(status, 200)
            return [(x["version"], x["pre"]) for x in body["versions"]]
        self.assertEqual(versions(), [("3.10.5", False), ("3.9.0", False)])
        self.assertEqual(versions(pre=1), [("3.11.0-beta.1", True), ("3.10.5", False), ("3.9.0", False)])
        self.assertEqual(versions(keep="3.11.0-beta.1")[0], ("3.11.0-beta.1", True), "the one installed is always there")
        self.assertEqual(versions(unity="")[0], ("3.12.0", False), "with no Unity to go by, every version")
        self.assertEqual(versions(name="com.example.none"), [])

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
        # (the file's full path, as the library resolves it: on Windows, not a short 8.3 name such as RUNNER~1)
        self.assertEqual(template["unityPackages"], [str((Path(self.asset["abs_folder"]) / "Hoodie.unitypackage").resolve())])
        self.assertEqual(template["vpmDependencies"], {"nadena.dev.modular-avatar": "^1.10.0"})
        listed = {t["name"]: t for t in self.call("GET", "/api/vpm")[1]["templates"]}
        self.assertTrue(listed["Avatar base"]["available"], "ALCOM's template, made from it, is listed as one")
        self.assertEqual(self.call("POST", "/api/vpm/presets", {"action": "save", "preset": {"name": ""}})[0], 400)



class ImportsList(unittest.TestCase):
    """What Hoard put in a project, written into it (#155): added to Hoard for Unity's own list, never written over."""

    def setUp(self):
        from hoard.vpm import imports
        self.imports = imports
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, True)
        self.log = self.project / "ProjectSettings" / "Hoard" / "imports.json"

    def test_added_to_what_hoard_for_unity_noted(self):
        self.log.parent.mkdir(parents=True)
        unity = {"store": "Gumroad", "name": "Hat", "creator": "Mochi", "file": "Hat.unitypackage", "imported_at": "2026-01-01T00:00:00Z"}
        self.log.write_text(json.dumps({"format": "hoard-unity-imports", "version": 1, "imports": [unity]}))
        self.imports.note(self.project, [
            {"store": "Booth", "name": "[Asset] *Hoodie*", "creator": "Kitsu", "file": "Hoodie.unitypackage",
             "added": ["Assets/Kitsu"], "already_there": 2, "in_the_way": 1},
            {"store": "Booth", "name": "Tool", "creator": "Kitsu", "file": "tool.zip", "label": "Tool",
             "package": "com.kitsu.tool", "result": "added", "added": ["Packages/com.kitsu.tool"]},
            {"store": "Jinxxy", "name": "Broken", "creator": "", "file": "x.unitypackage", "why": "not a package"}])
        doc = json.loads(self.log.read_text())
        self.assertEqual(doc["imports"][0], unity, "what Hoard for Unity noted is kept as it was")
        self.assertEqual([e["name"] for e in doc["imports"]], ["Hat", "[Asset] *Hoodie*", "Tool"], "not what failed")
        self.assertEqual((doc["imports"][1]["left"], doc["imports"][2]["package"]), (3, "com.kitsu.tool"))
        note = (self.project / "Hoard imports.md").read_text("utf-8")
        self.assertTrue(note.startswith("# What Hoard put in this project"))
        self.assertIn(r"**\[Asset\] \*Hoodie\***, by Kitsu (Booth)", note, "a name is never read as Markdown")
        self.assertIn("3 of its assets were already in the project", note)
        self.assertIn("- Added: the package `com.kitsu.tool`, in `Packages/com.kitsu.tool`", note)
        self.assertIn("- Not put in: not a package", note)
        self.imports.note(self.project, [{"store": "Booth", "name": "Again", "file": "a.unitypackage", "added": []}])
        note = (self.project / "Hoard imports.md").read_text("utf-8")
        self.assertEqual(note.count("# What Hoard put in this project"), 1, "added to, not written again")
        self.assertIn("**Again** (Booth)", note)

    def test_a_list_that_cant_be_read_is_kept_aside(self):
        self.log.parent.mkdir(parents=True)
        self.log.write_text("{not json")
        self.imports.note(self.project, [{"store": "Booth", "name": "Hoodie", "file": "h.unitypackage", "added": []}])
        self.assertEqual([e["name"] for e in json.loads(self.log.read_text())["imports"]], ["Hoodie"])
        aside = list(self.log.parent.glob("imports.json.unreadable-*"))
        self.assertEqual(len(aside), 1)
        self.assertEqual(aside[0].read_text(), "{not json")


if __name__ == "__main__":
    unittest.main()
