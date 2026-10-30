"""Projects through Hoard's server (hoard/vpm/api.py, server.py's /api/vpm): a project made from a template, its
VRChat SDK installed from a repository (a stand-in on this computer), products from the library put in, its
packages changed, all as Tasks jobs; and only projects on the list are ever touched."""
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
            jobs = self.srv.project_jobs   # (Projects' tasks: a lane of their own)
            if not jobs.state["running"] and not jobs.state["queue"]:
                return jobs.history[-1] if jobs.history else None   # (the newest)
            time.sleep(0.05)
        self.fail("the job didn't finish")

    def test_projects_tasks_run_in_a_lane_of_their_own(self):
        """A project's task never waits behind a sync or a download (or they behind it): Projects has its own queue
        and thread. Tasks shows both, Stop stops a project's task without touching the store browsers, and a
        project's task waiting its turn is taken off its own queue."""
        from hoard import jobs as jobs_module
        from hoard.common import capture_log, log
        busy, ended, heard = threading.Event(), [], []
        self.addCleanup(busy.set)

        def verify(stores):   # a long job in the main lane, saying how it's going as it goes
            with capture_log(heard.append):
                while not busy.wait(0.02):
                    log("the main lane's own")
        self.srv.jobs._verify = verify
        self.assertEqual(self.srv.jobs.start("verify", []), "started")
        step = threading.Event()

        def project(what):   # Projects' work, step by step, as hoard/vpm reports it
            for n in range(400):
                log(f"step {n}")
                step.set()
                time.sleep(0.02)
            return "Done."
        runs = []
        self.srv.project_jobs.project_runner = lambda what: runs.append(what) or ("Refreshed." if len(runs) == 1 else project(what))
        self.assertEqual(self.call("POST", "/api/vpm/refresh", {})[0], 200)
        done = self.wait()
        self.assertEqual((done["outcome"], done["message"], done["lane"]), ("done", "Refreshed.", "projects"),
                         "done while the main lane's job still runs")
        self.assertTrue(self.srv.jobs.state["running"])
        with mock.patch.object(jobs_module, "end_browsers", lambda: ended.append(1) or True):
            self.assertEqual(self.call("POST", "/api/vpm/refresh", {})[0], 200)   # (this one goes step by step)
            self.assertTrue(step.wait(10))
            self.assertEqual(self.call("POST", "/api/vpm/refresh", {})[1], {"ok": True, "queued": True})
            status = self.call("GET", "/api/status")[1]
            self.assertTrue(status["job"]["running"] and status["project_job"]["running"])
            tasks = self.call("GET", "/api/tasks")[1]
            self.assertEqual((tasks["current"]["task"], tasks["project"]["task"]), ("verify", "project"))
            waiting = [q for q in tasks["queue"] if q["lane"] == "projects"]
            self.assertTrue(waiting and waiting[0]["id"].startswith("p"))
            self.assertEqual(self.call("POST", "/api/queue/remove", {"id": waiting[0]["id"]})[1], {"ok": True})
            self.assertEqual(self.call("POST", "/api/cancel", {"lane": "projects"})[1], {"ok": True})
            stopped = self.wait()
        self.assertEqual(stopped["outcome"], "stopped")
        self.assertIn("step 0", stopped["log"])
        self.assertNotIn("the main lane's own", stopped["log"], "each lane hears its own job only")
        self.assertTrue(heard and not any(str(x).startswith("step") for x in heard))
        self.assertEqual(ended, [], "the store browsers are the main lane's: left alone")
        self.assertTrue(self.srv.jobs.state["running"], "the main lane's job carries on")
        self.assertEqual(len(self.srv.project_jobs.history), 2, "the refresh waiting its turn was taken off")
        busy.set()
        history = self.call("GET", "/api/tasks")[1]["history"]
        self.assertEqual({h["lane"] for h in history}, {"projects", "main"} if any(h["task"] == "verify" for h in history) else {"projects"})

    def test_projects_log(self):
        """Projects' log, as ALCOM and the Creator Companion keep theirs: what was done (a task's steps and how it
        ended, a project put on the list), a warning said as one, and what couldn't be done, each with its time and
        level; this run's for the page, newest last, and each written to this run's own file in the logs folder."""
        from hoard.common import log
        from hoard.vpm import logbook
        from hoard.vpm.api import ProjectsError
        book = logbook.Logbook(self.tmp / "logs")
        patch = mock.patch.object(logbook, "book", book)
        patch.start()
        self.addCleanup(patch.stop)
        got = self.call("GET", "/api/vpm/logs")[1]
        self.assertEqual((got["entries"], got["file"]), ([], None), "nothing yet, and no file until there is")
        project = self.tmp / "Unity" / "Mochi"
        for sub in ("Assets", "Packages", "ProjectSettings"):
            (project / sub).mkdir(parents=True)
        self.assertEqual(self.call("POST", "/api/vpm/add-project", {"path": str(project)})[0], 200)
        self.assertEqual(self.call("POST", "/api/vpm/open", {"path": str(self.tmp / "Elsewhere")})[0], 400)
        self.assertEqual(self.call("POST", "/api/vpm/check-name", {"location": str(self.tmp), "name": "CON"})[0], 200)

        def refresh(what):   # Projects' work, as hoard/vpm says how it's going
            log("Fetching the repositories")
            log(logbook.Warn("Couldn't fetch Extra: it's gone"))
            return "Refreshed the repositories."
        self.srv.project_jobs.project_runner = refresh
        self.assertEqual(self.call("POST", "/api/vpm/refresh", {})[0], 200)
        self.wait()

        def broken(what):
            raise ProjectsError("The repositories couldn't be read.")
        self.srv.project_jobs.project_runner = broken
        self.assertEqual(self.call("POST", "/api/vpm/refresh", {})[0], 200)
        self.wait()
        got = self.call("GET", "/api/vpm/logs")[1]
        self.assertEqual([(e["level"], e["message"]) for e in got["entries"]], [
            ("info", f"Added Mochi to the list ({project})"),
            ("error", "Open in Unity: That project isn't on the list any more."),
            ("info", "Projects: Refresh the repositories"),
            ("info", "Fetching the repositories"),
            ("warning", "Couldn't fetch Extra: it's gone"),
            ("info", "Refreshed the repositories."),
            ("info", "Projects: Refresh the repositories"),
            ("error", "Projects: Refresh the repositories: The repositories couldn't be read.")],
            "a name checked as it's typed isn't logged")
        self.assertEqual([e["n"] for e in got["entries"]], list(range(1, 9)))
        self.assertTrue(all(e["time"][:4].isdigit() and "T" in e["time"] for e in got["entries"]))
        # only what's newer, for a page that has the rest
        newer = self.call("GET", "/api/vpm/logs?after=6")[1]
        self.assertEqual([e["n"] for e in newer["entries"]], [7, 8])
        self.assertEqual(newer["run"], got["run"])
        # and the file, a line an entry
        self.assertTrue(got["file"].startswith("projects-") and got["file"].endswith(".log"))
        lines = (self.tmp / "logs" / got["file"]).read_text("utf-8").splitlines()
        self.assertEqual(len(lines), 8)
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}[+-]\d\d:\d\d \[ INFO\] Added Mochi to the list")
        self.assertIn("[ WARN] Couldn't fetch Extra", lines[4])
        self.assertIn("[ERROR] Open in Unity:", lines[1])

    def test_what_a_product_needs_as_things_stand(self):
        """What a product needs, offered for a project: a repository you have already that gives a package is used,
        whatever address it was added with (in ALCOM, say), so it's never added twice; and what the project already
        has isn't offered again. Adding a repository that's already there, under another spelling of its address or
        another address with the same listing, is refused."""
        from hoard.vpm import repos as vpm_repos
        settings_file = self.vcc / "settings.json"
        settings = json.loads(settings_file.read_text())
        # VRCFury's, added elsewhere with its address spelled differently; and one giving lilToon, at an address of its own
        for file, url, listing in (
                ("vrcfury.json", "https://VCC.vrcfury.com/", {"name": "VRCFury Repo", "id": "com.vrcfury.vpm", "packages": {}}),
                ("mirror.json", "https://mirror.example/vpm.json", {"name": "A mirror", "id": "com.example.mirror", "url": "https://mirror.example/vpm.json",
                 "packages": {"jp.lilxyzw.liltoon": {"versions": {"1.0.0": {"name": "jp.lilxyzw.liltoon", "version": "1.0.0", "url": "https://mirror.example/l.zip"}}}}})):
            (self.vcc / "Repos" / file).write_text(json.dumps({"repo": listing}))
            settings["userRepos"].append({"localPath": str(self.vcc / "Repos" / file), "url": url, "name": listing["name"]})
        project = self.tmp / "Unity" / "Mochi"
        for sub in ("Assets", "ProjectSettings", "Packages"):
            (project / sub).mkdir(parents=True)
        (project / "Packages" / "vpm-manifest.json").write_text(json.dumps({
            "dependencies": {"com.vrchat.avatars": {"version": "3.10.5"}},
            "locked": {"com.vrchat.avatars": {"version": "3.10.5", "dependencies": {}}}}))
        settings["userProjects"] = [str(project)]
        settings_file.write_text(json.dumps(settings))
        self.srv.vpm.forget()
        needs = {"tools": [{"key": k} for k in ("vrcfury", "liltoon", "vrchat-sdk", "modular-avatar")]}
        got = {s["package"]: s for s in self.srv.vpm.product(self.asset, needs, str(project))["suggested"]}
        self.assertEqual((got["com.vrcfury.vrcfury"]["repo_added"], got["com.vrcfury.vrcfury"]["in_repo"]), (True, "VRCFury Repo"),
                         "the same address, spelled another way")
        self.assertEqual((got["jp.lilxyzw.liltoon"]["repo_added"], got["jp.lilxyzw.liltoon"]["in_repo"]), (True, "A mirror"),
                         "a repository that has the package already")
        self.assertEqual((got["nadena.dev.modular-avatar"]["repo_added"], got["nadena.dev.modular-avatar"]["in_repo"]), (False, None))
        self.assertEqual(got["com.vrchat.avatars"]["in_project"], "3.10.5")
        self.assertIsNone(got["jp.lilxyzw.liltoon"]["in_project"])
        # without a project (or one not on the list): what it has isn't known
        elsewhere = self.srv.vpm.product(self.asset, needs, str(self.tmp / "Elsewhere"))["suggested"]
        self.assertTrue(all(s["in_project"] is None for s in elsewhere))
        # and through the server, with the project
        status, answer = self.call("GET", f"/api/vpm/product?key=booth%2Fhoodie&path={quote(str(project))}")
        self.assertEqual(status, 200, answer)
        # a repository already there isn't added again: not under another spelling of its address...
        status, answer = self.call("POST", "/api/vpm/repos/add", {"url": "https://vcc.vrcfury.com"})
        self.assertEqual((status, answer.get("error")), (400, "That repository is already added."))
        # ...nor at another address whose listing is one already here (its id)
        _Repo.files["/mirror-again.json"] = json.dumps({"name": "Mirror", "id": "com.example.mirror", "packages": {}}).encode()
        status, answer = self.call("POST", "/api/vpm/repos/add", {"url": f"{self.origin}/mirror-again.json"})
        self.assertEqual((status, answer.get("error")), (400, "That repository is already added."))
        self.assertEqual(len(json.loads(settings_file.read_text())["userRepos"]), 3, "nothing added")
        # a new one is still added
        _Repo.files["/new.json"] = json.dumps({"name": "New", "id": "com.example.new", "packages": {}}).encode()
        self.assertEqual(self.call("POST", "/api/vpm/repos/add", {"url": f"{self.origin}/new.json"})[0], 200)
        self.assertTrue(vpm_repos.same_address("https://vcc.vrcfury.com", "https://VCC.vrcfury.com:443/"))

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

    def test_hoard_for_unity_in_a_new_project(self):
        """New project has Hoard for Unity in it unless you leave it out: its repository is added first when you
        haven't got it (and a project is still made when it can't be reached, without it)."""
        from hoard.vpm import api as vpm_api
        data = _zip({"package.json": json.dumps({"name": "soloflighter.hoard", "version": "0.9.0", "displayName": "Hoard for Unity"})})
        _Repo.files["/hoard.zip"] = data
        _Repo.files["/hoard.json"] = json.dumps({"name": "Hoard", "id": "link.furryup.hoard", "url": f"{self.origin}/hoard.json",
                                                 "packages": {"soloflighter.hoard": {"versions": {"0.9.0": {
                                                     "name": "soloflighter.hoard", "version": "0.9.0", "url": f"{self.origin}/hoard.zip",
                                                     "zipSHA256": hashlib.sha256(data).hexdigest()}}}}}).encode()
        overview = self.call("GET", "/api/vpm")[1]
        self.assertEqual(overview["hoard_for_unity"]["package"], "soloflighter.hoard")
        self.assertFalse(overview["hoard_for_unity"]["repo_added"])
        make = {"location": str(self.tmp / "Projects"), "template": "com.anatawa12.vrc-get.vrchat.avatars",
                "unity": "2022.3.22f1", "packages": {"soloflighter.hoard": "*"}}
        with mock.patch.object(vpm_api, "HOARD_REPO", f"{self.origin}/nowhere.json"):   # (can't be reached)
            self.assertEqual(self.call("POST", "/api/vpm/create", {**make, "name": "Offline"})[0], 200)
            done = self.wait()
        self.assertEqual(done["outcome"], "done", done)
        self.assertTrue((self.tmp / "Projects" / "Offline" / "Packages" / "com.vrchat.avatars").is_dir())
        self.assertIn("made without it", "\n".join(done["log"]))
        with mock.patch.object(vpm_api, "HOARD_REPO", f"{self.origin}/hoard.json"):
            self.assertEqual(self.call("POST", "/api/vpm/create", {**make, "name": "With Hoard"})[0], 200)
            done = self.wait()
            self.assertEqual(done["outcome"], "done", done)
            self.assertTrue(self.call("GET", "/api/vpm")[1]["hoard_for_unity"]["repo_added"])
        self.assertTrue((self.tmp / "Projects" / "With Hoard" / "Packages" / "soloflighter.hoard" / "package.json").is_file())

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

    def test_delete_a_project_from_this_computer(self):
        """Only a listed project, only with its name typed, backed up first unless you say not to; never one that
        holds Hoard's own folders (the backups folder, here)."""
        project = self.tmp / "Unity" / "Old Idea"
        for sub in ("Assets/Scenes", "Packages", "ProjectSettings"):
            (project / sub).mkdir(parents=True)
        (project / "Assets" / "Scenes" / "Main.unity").write_text("scene")
        (project / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.22f1\n")
        os.chmod(project / "Assets" / "Scenes" / "Main.unity", 0o444)   # (read-only, as Unity or git can leave one)
        body = {"path": str(project), "confirm": "Old Idea"}
        self.assertEqual(self.call("POST", "/api/vpm/delete-project", body)[0], 400, "not on the list")
        self.assertEqual(self.call("POST", "/api/vpm/add-project", {"path": str(project)})[0], 200)
        status, answer = self.call("POST", "/api/vpm/delete-project", {**body, "confirm": "old idea"})
        self.assertEqual((status, answer["error"]), (400, "Type the project's name to delete it."))
        # a backups folder inside the project would go with it: refused, and nothing deleted
        settings = json.loads((self.vcc / "settings.json").read_text())
        (self.vcc / "settings.json").write_text(json.dumps({**settings, "projectBackupPath": str(project / "Backups")}))
        status, answer = self.call("POST", "/api/vpm/delete-project", body)
        self.assertEqual(status, 400)
        self.assertIn("inside this project", answer["error"])
        backups = self.tmp / "Backups"
        (self.vcc / "settings.json").write_text(json.dumps({**settings, "projectBackupPath": str(backups)}))
        self.assertEqual(self.call("POST", "/api/vpm/delete-project", body)[1], {"ok": True, "queued": False})
        done = self.wait()
        self.assertEqual((done["outcome"], done["label"]), ("done", "Projects: Delete Old Idea from this computer"), done["message"])
        self.assertFalse(project.exists())
        self.assertEqual([z.name.startswith("Old Idea-") for z in backups.glob("*.zip")], [True], "backed up first")
        self.assertNotIn(str(project), [p["path"] for p in self.call("GET", "/api/vpm")[1]["projects"]])

    def test_a_deleted_project_listed_by_another_name_comes_off_the_list(self):
        """On Windows the list can hold a short name (C:\\Users\\RUNNER~1\\...) that resolves to a longer one: the
        project was deleted but stayed on the list. A link to its folder stands in for a short name here."""
        project = self.tmp / "Unity" / "Real Name"
        for sub in ("Assets", "Packages", "ProjectSettings"):
            (project / sub).mkdir(parents=True)
        (project / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.22f1\n")
        try:
            (self.tmp / "Linked").symlink_to(self.tmp / "Unity", target_is_directory=True)
        except OSError:
            self.skipTest("links can't be made here")
        listed = str(self.tmp / "Linked" / "Real Name")
        self.assertEqual(self.call("POST", "/api/vpm/add-project", {"path": listed})[0], 200)
        body = {"path": listed, "confirm": "Real Name", "backup": False}
        self.assertEqual(self.call("POST", "/api/vpm/delete-project", body)[1], {"ok": True, "queued": False})
        done = self.wait()
        self.assertEqual(done["outcome"], "done", done["message"])
        self.assertFalse(project.exists())
        self.assertEqual([p["path"] for p in self.call("GET", "/api/vpm")[1]["projects"] if "Real Name" in p["path"]], [])

    def test_projects_with_newer_packages(self):
        """Issue #253: the list says how many of each project's packages have a newer version, as its own page does
        (a stable one, unless it has a prerelease already or they're offered)."""
        status, made = self.call("POST", "/api/vpm/create", {
            "name": "Fox", "location": str(self.tmp / "Projects"), "template": "com.anatawa12.vrc-get.vrchat.avatars",
            "unity": "2022.3.22f1", "packages": {}, "picks": []})
        self.assertEqual(status, 200, made)
        self.assertEqual(self.wait()["outcome"], "done")
        project = str(self.tmp / "Projects" / "Fox")
        status, got = self.call("GET", "/api/vpm/updates")
        self.assertEqual((status, got["projects"][project]["packages"]), (200, 0))
        cache = self.vcc / "Repos" / "vrc-official.json"
        repo = json.loads(cache.read_text())
        for name in ("com.vrchat.base", "com.vrchat.avatars"):
            versions = repo["repo"]["packages"][name]["versions"]
            versions["3.11.0-beta.1"] = {**versions["3.10.5"], "version": "3.11.0-beta.1"}
        cache.write_text(json.dumps(repo))
        self.srv.vpm.forget()
        self.assertEqual(self.call("GET", "/api/vpm/updates")[1]["projects"][project]["packages"], 0, "a prerelease isn't one")
        versions = repo["repo"]["packages"]["com.vrchat.base"]["versions"]
        versions["3.10.6"] = {**versions["3.10.5"], "version": "3.10.6"}
        cache.write_text(json.dumps(repo))
        self.srv.vpm.forget()
        got = self.call("GET", "/api/vpm/updates")[1]["projects"][project]
        self.assertEqual(got, {"packages": 1, "names": ["com.vrchat.base"]})

    def test_a_projects_details(self):
        """A project's details beside the list: its size on disk, what's Unity's own cache apart from what's yours
        (and a link inside it not followed), its packages with any newer version, what Hoard put in it (a hidden
        product left out while the hidden library is locked), and its own backups, here and moved to another drive."""
        from hoard.marks import MarkStore
        from hoard.vpm import listing
        status, made = self.call("POST", "/api/vpm/create", {
            "name": "Fox", "location": str(self.tmp / "Projects"), "template": "com.anatawa12.vrc-get.vrchat.avatars",
            "unity": "2022.3.22f1", "packages": {}, "picks": []})
        self.assertEqual(status, 200, made)
        self.assertEqual(self.wait()["outcome"], "done")
        project = self.tmp / "Projects" / "Fox"
        (project / "Assets" / "big.bin").write_bytes(b"a" * 10_000)
        (project / "Library").mkdir(exist_ok=True)
        (project / "Library" / "cache.bin").write_bytes(b"c" * 50_000)
        (project / "Temp").mkdir(exist_ok=True)
        (project / "Temp" / "t.bin").write_bytes(b"t" * 3_000)
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "huge.bin").write_bytes(b"h" * 900_000)
        try:
            os.symlink(elsewhere, project / "Assets" / "linked", target_is_directory=True)
        except OSError:
            pass   # (Windows without the right to make links: nothing to follow)
        settings = json.loads((self.vcc / "settings.json").read_text())
        backups, away = self.tmp / "Backups", self.tmp / "E" / "Moved"
        (self.vcc / "settings.json").write_text(json.dumps({**settings, "projectBackupPath": str(backups)}))
        for folder, names in ((backups, ("Fox-2026-09-01T10-00-00.zip", "Fox-2026-10-01T10-00-00.zip", "Wolf-2026-10-02T10-00-00.zip")),
                              (away, ("Fox-2026-01-01T10-00-00.zip",))):
            folder.mkdir(parents=True)
            for name in names:
                (folder / name).write_bytes(b"PK" + b"0" * 98)
        listing.set_backup_prefs(moved_to=str(away))
        listing.add_preloaded(str(project), [{"tag_key": "booth:hoodie", "name": "Hoodie", "file": "Hoodie.unitypackage"},
                                             {"tag_key": "booth:secret", "name": "Secret", "file": "Secret.unitypackage"}])
        MarkStore().set_pin("2468")
        MarkStore().change("hidden", ["booth:secret"], True)
        status, got = self.call("GET", "/api/vpm/about?path=" + quote(str(project)))
        self.assertEqual(status, 200, got)
        size = got["size"]
        self.assertEqual((size["cache"], size["complete"]), (53_000, True), "Library and Temp: Unity's cache")
        self.assertGreaterEqual(size["assets"], 10_000)
        self.assertLess(size["assets"], 900_000, "a link inside it isn't followed")
        self.assertGreater(size["packages"], 0)
        self.assertEqual(size["total"], size["assets"] + size["packages"] + size["cache"] + size["other"])
        self.assertEqual(sorted(p["name"] for p in got["packages"]), ["com.vrchat.avatars", "com.vrchat.base"])
        self.assertTrue(all(p["latest"] is None for p in got["packages"]))
        self.assertEqual([p["name"] for p in got["preloaded"]], ["Hoodie"], "a hidden product isn't said while it's locked")
        self.assertEqual(got["backups"], {"count": 2, "size": 200, "newest": "2026-10-01T10:00:00", "moved": 1}, "its own, not Wolf's")
        self.assertEqual(self.call("GET", "/api/vpm/about?path=" + quote(str(self.tmp / "Nowhere")))[0], 400, "only a listed project")

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


class Addresses(unittest.TestCase):
    def test_the_same_repository_address(self):
        from hoard.vpm.repos import same_address
        for a, b in (("https://vcc.vrcfury.com", "https://vcc.vrcfury.com/"), ("https://VPM.nadena.dev/vpm.json", "https://vpm.nadena.dev/vpm.json"),
                     ("https://example.com:443/a/", "https://example.com/a"),
                     ("https://packages.vrchat.com/official?download", "https://packages.vrchat.com/official/?download")):
            self.assertTrue(same_address(a, b), (a, b))
        for a, b in (("https://example.com/a", "https://example.com/b"), ("https://example.com/vpm.json", "https://example.com/vpm.json?x=1"),
                     ("https://example.com:8443/a", "https://example.com/a"), ("http://example.com/a", "https://example.com/a"),
                     ("https://Example.com/A", "https://example.com/a"), ("", ""), (None, "https://example.com")):
            self.assertFalse(same_address(a, b), (a, b))


class Logbook(unittest.TestCase):
    """Projects' log on its own (hoard/vpm/logbook.py)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_whats_kept(self):
        from hoard.vpm import logbook
        with mock.patch.object(logbook, "SHOWN", 3):
            book = logbook.Logbook(self.tmp)
            for n in range(5):
                book.add("info", f"entry {n}")
        self.assertEqual([e["message"] for e in book.entries()], ["entry 2", "entry 3", "entry 4"], "the newest, to show")
        self.assertEqual(len(book.file.read_text("utf-8").splitlines()), 5, "and every one in the file")
        self.assertEqual(book.add("shouting", "  x  ")["level"], "info")
        self.assertEqual(book.add("error", "")["message"], "(nothing said)")
        self.assertEqual(len(book.add("info", "y" * 9000)["message"]), logbook.MAX_MESSAGE)
        self.assertEqual(logbook.level_of(logbook.Warn("careful")), "warning")
        self.assertEqual(logbook.level_of("fine"), "info")

    def test_the_newest_files_are_kept(self):
        from hoard.vpm import logbook
        for n in range(35):
            (self.tmp / f"projects-2026-01-{n + 1:02d}_10-00-00.log").write_text("x")
        (self.tmp / "hoard-2026-01-01_10-00-00.log").write_text("Hoard's own")
        book = logbook.Logbook(self.tmp)
        book.add("info", "started")
        left = sorted(p.name for p in self.tmp.glob("projects-*.log"))
        self.assertEqual(len(left), logbook.KEEP_FILES)
        self.assertIn(book.file.name, left)
        self.assertNotIn("projects-2026-01-01_10-00-00.log", left, "the oldest went")
        self.assertTrue((self.tmp / "hoard-2026-01-01_10-00-00.log").is_file(), "Hoard's own logs are left alone")

    def test_a_log_that_cant_be_written_is_still_shown(self):
        from hoard.vpm import logbook
        blocked = self.tmp / "file"
        blocked.write_text("not a folder")
        book = logbook.Logbook(blocked / "logs")
        book.add("error", "said anyway")
        self.assertEqual([e["message"] for e in book.entries()], ["said anyway"])
        self.assertIsNone(book.file)

    def test_sizes_and_counts(self):
        from hoard.vpm import logbook
        self.assertEqual([logbook.size_text(n) for n in (0, 1023, 1024, 5 * 1024 ** 2, 3 * 1024 ** 3, 5000 * 1024 ** 3)],
                         ["0 bytes", "1,023 bytes", "1.0 KB", "5.0 MB", "3.0 GB", "5000.0 GB"])
        self.assertEqual((logbook.count(1, "backup"), logbook.count(1200, "package")), ("1 backup", "1,200 packages"))
