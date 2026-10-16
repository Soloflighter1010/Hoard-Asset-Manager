"""The VPM pieces under Projects (hoard/vpm): the Creator Companion's files, repositories, packages and projects.

Repositories are served by a stand-in server on this computer (reached as both 127.0.0.1 and localhost, two hosts),
let through egress's https and public-address checks for the tests only.
"""
import gzip
import hashlib
import http.server
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import egress
from hoard.vpm import environment, fetch, litedb, repos, resolve
from hoard.vpm.manifest import Package, unity_compatible, valid_name
from hoard.vpm.project import AVATARS, UNKNOWN, VPM_STARTER, WORLDS, UnityProject
from hoard.vpm.version import UnityVersion, Version

DATA = Path(__file__).parent / "data"


class _Server(http.server.BaseHTTPRequestHandler):
    routes: dict = {}
    seen: list = []

    def do_GET(self):
        _Server.seen.append((self.headers.get("Host"), self.path, dict(self.headers)))
        status, headers, body = _Server.routes.get(self.path, (404, {}, b"no"))
        if callable(body):
            status, headers, body = body(self)
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


class Served(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Server)
        cls.srv.daemon_threads = True
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.a = f"http://127.0.0.1:{cls.srv.server_port}"
        cls.b = f"http://localhost:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        egress._TEST_ORIGINS.clear()
        egress._TEST_ORIGINS.update({self.a, self.b})
        self.addCleanup(egress._TEST_ORIGINS.clear)
        _Server.routes, _Server.seen = {}, []
        self.vcc = Path(tempfile.mkdtemp()) / "VRChatCreatorCompanion"
        self.addCleanup(shutil.rmtree, self.vcc.parent, True)
        self.env = mock.patch.dict(os.environ, {"HOARD_VCC_DIR": str(self.vcc)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def listing(self, packages: dict, repo_id="com.example.repo", url=None):
        return {"name": "Example", "id": repo_id, "url": url or f"{self.a}/index.json",
                "packages": {n: {"versions": {v: m for v, m in vs.items()}} for n, vs in packages.items()}}


class Settings(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_everything_else_is_kept(self):
        raw = {"pathToUnityExe": "", "userProjects": ["C:\\A", "C:\\B"], "unknownFutureKey": {"x": [1, 2]},
               "userRepos": [{"localPath": "C:\\R.json", "url": "https://r", "headers": {}}], "showPrereleasePackages": True}
        (self.folder / "settings.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(raw).encode())
        s = environment.Settings.load(self.folder)
        self.assertEqual(s.user_projects(), ["C:\\A", "C:\\B"])
        self.assertTrue(s.show_prerelease())
        s.set_projects(["C:\\New"] + s.user_projects())
        s.save()
        again = json.loads((self.folder / "settings.json").read_text("utf-8"))
        self.assertEqual(again["unknownFutureKey"], {"x": [1, 2]})
        self.assertEqual(again["userProjects"], ["C:\\New", "C:\\A", "C:\\B"])
        self.assertEqual(list(again), list(raw), "keys stay in their order")

    def test_missing_list_is_none_not_empty(self):
        (self.folder / "settings.json").write_text("{}")
        self.assertIsNone(environment.Settings.load(self.folder).user_projects())

    def test_alcom_backup_is_read_when_settings_are_missing(self):
        (self.folder / "vrc-get").mkdir()
        (self.folder / "vrc-get" / "vcc-settings-backup.json").write_text(json.dumps({"userProjects": ["X"], "defaultProjectPath": "D"}))
        s = environment.Settings.load(self.folder)
        self.assertEqual(s.default_project_path(), "D")
        self.assertIsNone(s.user_projects(), "as ALCOM: the list comes from the database then")

    def test_blank_and_damaged(self):
        (self.folder / "settings.json").write_bytes(b"\x00" * 64)
        self.assertEqual(environment.Settings.load(self.folder).raw, {})
        (self.folder / "settings.json").write_text("{not json")
        with self.assertRaises(environment.DataFileError):
            environment.Settings.load(self.folder)


class LiteDB(unittest.TestCase):
    """vcc-sample.liteDb.gz was written by vrc-get's own LiteDB writer (vrc-get-litedb 0.3.0-beta.8): 41 projects,
    one larger than a page (split over blocks), and one Unity editor."""

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "vcc.liteDb"
        self.addCleanup(shutil.rmtree, self.path.parent, True)
        self.path.write_bytes(gzip.decompress((DATA / "vcc-sample.liteDb.gz").read_bytes()))

    def test_reads_the_collections(self):
        found = litedb.read(self.path, ("projects", "UNITYVERSIONS", "missing"))
        self.assertEqual(len(found["projects"]), 41)
        first = found["projects"][0]
        self.assertEqual(first["Path"], "C:\\Users\\Someone\\ALCOM\\Projects\\Project 00")
        self.assertEqual((first["UnityVersion"], first["Type"], first["Favorite"]), ("2019.4.31f1", 8, False))
        self.assertEqual(first["CreatedAt"], 1700000000000)
        self.assertEqual(first["vrc-get"]["unity_revision"], "887be4894c44")
        big = next(p for p in found["projects"] if "Note" in p)
        self.assertEqual((big["Path"], len(big["Note"])), ("/home/someone/Projects/Big ☃ Project", 12000))
        self.assertEqual(found["UNITYVERSIONS"][0]["Version"], "2022.3.22f1")
        self.assertEqual(found["missing"], [])

    def test_damage_is_refused_not_guessed(self):
        data = bytearray(self.path.read_bytes())
        data[32:40] = b"XXXXXXXX"
        self.path.write_bytes(bytes(data))
        with self.assertRaises(litedb.DatabaseError):
            litedb.read(self.path, ("projects",))
        good = gzip.decompress((DATA / "vcc-sample.liteDb.gz").read_bytes())
        for cut in (8192, 8192 * 3 + 100):
            self.path.write_bytes(good[:cut])
            try:
                litedb.read(self.path, ("projects",))
            except litedb.DatabaseError:
                pass
        self.assertEqual(environment.database(self.path.parent), {"projects": [], "unityVersions": []},
                         "a damaged database reads as empty")


class Manifests(unittest.TestCase):
    def test_names(self):
        for good in ("com.vrchat.avatars", "nadena.dev.modular-avatar", "jp.lilxyzw.liltoon", "a_b"):
            self.assertTrue(valid_name(good), good)
        for bad in ("../evil", "..", "com/evil", "con", "aux.x", "", "a" * 300, "x.", "C:evil", 5, ".hidden"):
            self.assertFalse(valid_name(bad), bad)

    def test_strict_and_loose(self):
        raw = {"name": "com.example.tool", "version": "1.2.0", "unity": "2022.3", "displayName": "Tool",
               "vpmDependencies": {"com.vrchat.base": ">=3.5.0"}, "url": "https://example.com/t.zip",
               "zipSHA256": "A" * 64, "changelogUrl": " ", "documentationUrl": "not a url",
               "legacyFolders": {"Assets\\Tool": "0123"}, "vrc-get": {"yanked": "broken build"},
               "author": {"name": "Someone"}, "keywords": ["a", "b"]}
        p = Package.parse(raw)
        self.assertEqual((p.name, str(p.version), p.unity, p.label(), p.author), ("com.example.tool", "1.2.0", (2022, 3), "Tool", "Someone"))
        self.assertEqual(p.zip_sha256, "a" * 64)
        self.assertIsNone(p.changelog_url)
        self.assertIsNone(p.documentation_url)
        self.assertTrue(p.yanked)
        bad = dict(raw, vpmDependencies={"com.vrchat.base": "not a range!!"})
        self.assertIsNone(Package.parse(bad), "a repository's bad version is left out")
        self.assertEqual(Package.parse(bad, loose=True).dependencies, {}, "an installed package's bad field is just missing")
        self.assertIsNone(Package.parse(dict(raw, name="../../evil"), loose=True))
        self.assertIsNone(Package.parse(dict(raw, vpmDependencies={"../x": "1.0.0"})))
        self.assertEqual(Package.parse(dict(raw, vpmDependencies=None)).dependencies, {})

    def test_unity_rules(self):
        u2022, u2019, u6 = (UnityVersion.parse(v) for v in ("2022.3.22f1", "2019.4.31f1", "6000.0.23f1"))
        sdk2019 = Package.parse({"name": "com.vrchat.avatars", "version": "3.4.2", "unity": "2019.4"})
        sdk2022 = Package.parse({"name": "com.vrchat.avatars", "version": "3.10.5", "unity": "2022.3"})
        tool = Package.parse({"name": "com.example.tool", "version": "1.0.0", "unity": "2022.3"})
        self.assertTrue(unity_compatible(sdk2019, u2019))
        self.assertFalse(unity_compatible(sdk2019, u2022))
        self.assertTrue(unity_compatible(sdk2022, u2022))
        self.assertFalse(unity_compatible(sdk2022, u6), "the 2022 SDK isn't for Unity 6")
        self.assertTrue(unity_compatible(tool, u6))
        self.assertFalse(unity_compatible(tool, u2019))


class Repositories(Served):
    def test_refresh_uses_the_etag_and_keeps_the_cache(self):
        listing = self.listing({"com.example.tool": {"1.0.0": {"name": "com.example.tool", "version": "1.0.0"}}})
        body = json.dumps(listing).encode()

        def answer(handler):
            if handler.headers.get("If-None-Match") == '"v1"':
                return 304, {}, b""
            return 200, {"ETag": '"v1"'}, body
        _Server.routes["/index.json"] = (200, {}, answer)
        settings = environment.Settings({}, self.vcc)
        repo = repos.add_repo(settings, f"{self.a}/index.json", headers={"X-Key": "secret"})
        self.assertEqual((repo.id, repo.etag), ("com.example.repo", '"v1"'))
        saved = json.loads((self.vcc / "Repos" / "com.example.repo.json").read_text())
        self.assertEqual(saved["vrc-get"], {"etag": '"v1"'})
        self.assertEqual(saved["headers"], {"X-Key": "secret"})
        self.assertEqual(json.loads((self.vcc / "settings.json").read_text())["userRepos"][0]["id"], "com.example.repo")
        with self.assertRaisesRegex(repos.RepoError, "already"):
            repos.add_repo(settings, f"{self.a}/index.json")
        again = repos.Collection.load(environment.Settings.load(self.vcc))
        mine = next(r for r in again.repos if r.id == "com.example.repo")
        self.assertFalse(mine.refresh(), "unchanged: not fetched again")
        self.assertEqual(_Server.seen[-1][2].get("If-None-Match"), '"v1"')
        self.assertTrue(repos.remove_repo(settings, str(mine.path)))
        self.assertFalse(mine.path.exists())

    def test_a_key_never_follows_a_redirect_to_another_host(self):
        _Server.routes["/index.json"] = (302, {"Location": f"{self.b}/real.json"}, b"")
        _Server.routes["/real.json"] = (200, {}, json.dumps(self.listing({})).encode())
        repos.add_repo(environment.Settings({}, self.vcc), f"{self.a}/index.json", headers={"Authorization": "Bearer k"})
        (first_host, _, first), (second_host, _, second) = _Server.seen
        self.assertEqual(first.get("Authorization"), "Bearer k")
        self.assertIsNone(second.get("Authorization"), "localhost is another host")
        self.assertIn("Hoard/", first.get("User-Agent"))

    def test_what_is_refused(self):
        settings = environment.Settings({}, self.vcc)
        for url in ("http://example.com/index.json", "ftp://x", "", "https://exa mple.com"):
            with self.assertRaises(repos.RepoError):
                repos.add_repo(settings, url)
        with self.assertRaises(repos.RepoError):
            repos.add_repo(settings, f"{self.a}/index.json", headers={"Bad\nHeader": "x"})
        _Server.routes["/page.html"] = (200, {}, b"<html>not a listing</html>")
        with self.assertRaisesRegex(repos.RepoError, "listing"):
            repos.add_repo(settings, f"{self.a}/page.html")
        egress._TEST_ORIGINS.clear()
        with self.assertRaises(repos.RepoError):
            repos.add_repo(settings, "https://127.0.0.1:1/index.json")   # this computer: never contacted

    def test_choosing_versions(self):
        c = repos.Collection([], [])
        r = repos.Repo(self.vcc / "x.json", None, {})
        r._take(self.listing({"com.example.tool": {
            "1.0.0": {"name": "com.example.tool", "version": "1.0.0"},
            "1.1.0": {"name": "com.example.tool", "version": "1.1.0", "unity": "2022.3"},
            "1.2.0-beta.1": {"name": "com.example.tool", "version": "1.2.0-beta.1"},
            "1.1.5": {"name": "com.example.tool", "version": "1.1.5", "vrc-get": {"yanked": True}},
            "2.0.0": {"name": "other.name", "version": "2.0.0"}}}))
        c.repos = [r]
        u2019, u2022 = UnityVersion.parse("2019.4.31f1"), UnityVersion.parse("2022.3.22f1")
        self.assertEqual(str(c.find("com.example.tool", repos.Selector.latest(u2022, False)).version), "1.1.0")
        self.assertEqual(str(c.find("com.example.tool", repos.Selector.latest(u2019, False)).version), "1.0.0")
        self.assertEqual(str(c.find("com.example.tool", repos.Selector.latest(u2022, True)).version), "1.2.0-beta.1")
        self.assertEqual(str(c.find("com.example.tool", repos.Selector.specific(Version.parse("1.1.5"))).version), "1.1.5",
                         "an exact version is found even when it's yanked")
        self.assertEqual(len(r.packages["com.example.tool"]), 4, "the version filed under another name is left out")


class Downloads(Served):
    def info(self, zipped: bytes, sha: str | None):
        manifest = {"name": "com.example.tool", "version": "1.0.0", "url": f"{self.a}/tool.zip"}
        if sha:
            manifest["zipSHA256"] = sha
        repo = repos.Repo(self.vcc / "Repos" / "r.json", f"{self.a}/index.json", {"X-Key": "k"})
        repo._take(self.listing({"com.example.tool": {"1.0.0": manifest}}))
        return repos.Info(repo.packages["com.example.tool"][Version.parse("1.0.0")], repo=repo)

    def test_download_check_and_cache(self):
        zipped = _zip({"package.json": '{"name":"com.example.tool","version":"1.0.0"}', "Runtime/A.cs": "//"})
        _Server.routes["/tool.zip"] = (200, {}, zipped)
        info = self.info(zipped, hashlib.sha256(zipped).hexdigest())
        path = resolve.package_zip(self.vcc, info)
        self.assertEqual(path, self.vcc / "Repos" / "com.example.tool" / "vrc-get-com.example.tool-1.0.0.zip")
        self.assertEqual(_Server.seen[-1][2].get("X-Key"), "k", "the repository's key goes to its own host")
        self.assertTrue(path.with_name(path.name + ".sha256").read_text().startswith(hashlib.sha256(zipped).hexdigest()))
        _Server.seen.clear()
        resolve.package_zip(self.vcc, info)
        self.assertEqual(_Server.seen, [], "the second time it comes from the cache")
        out = Path(tempfile.mkdtemp())
        resolve.unzip(path, out / "x")
        self.assertEqual((out / "x" / "Runtime" / "A.cs").read_text(), "//")

    def test_a_tampered_download_is_refused(self):
        zipped = _zip({"package.json": "{}"})
        _Server.routes["/tool.zip"] = (200, {}, zipped)
        with self.assertRaisesRegex(resolve.ResolveError, "SHA-256"):
            resolve.package_zip(self.vcc, self.info(zipped, "0" * 64))
        self.assertFalse(any((self.vcc / "Repos" / "com.example.tool").glob("*.zip")))

    def test_a_cached_file_that_changed_is_fetched_again(self):
        zipped = _zip({"package.json": "{}"})
        _Server.routes["/tool.zip"] = (200, {}, zipped)
        info = self.info(zipped, hashlib.sha256(zipped).hexdigest())
        path = resolve.package_zip(self.vcc, info)
        path.write_bytes(b"something else")
        _Server.seen.clear()
        self.assertEqual(resolve.package_zip(self.vcc, info).read_bytes(), zipped)
        self.assertEqual(len(_Server.seen), 1)

    def test_zip_names_that_escape_are_refused(self):
        for name in ("../evil.txt", "/abs.txt", "C:/x.txt", "a/../../b.txt", "a\\..\\..\\b.txt", "ads.txt:stream"):
            with self.subTest(name=name):
                path = Path(tempfile.mkdtemp()) / "p.zip"
                path.write_bytes(_zip({"ok.txt": "1", name: "2"}))
                with self.assertRaises(resolve.ResolveError):
                    resolve.unzip(path, path.parent / "out")
                self.assertFalse((path.parent / "evil.txt").exists())


class Projects(unittest.TestCase):
    def make(self, manifest=None, upm=None, files=None):
        folder = Path(tempfile.mkdtemp()) / "Project"
        self.addCleanup(shutil.rmtree, folder.parent, True)
        (folder / "Packages").mkdir(parents=True)
        (folder / "ProjectSettings").mkdir()
        (folder / "Assets").mkdir()
        (folder / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.22f1\nm_EditorVersionWithRevision: 2022.3.22f1 (887be4894c44)\n")
        if manifest is not None:
            (folder / "Packages" / "vpm-manifest.json").write_text(json.dumps(manifest))
        if upm is not None:
            (folder / "Packages" / "manifest.json").write_text(json.dumps({"dependencies": upm}))
        for name, text in (files or {}).items():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text(text)
        return folder

    def test_reading(self):
        folder = self.make({"dependencies": {"com.vrchat.avatars": {"version": "3.10.5"}},
                            "locked": {"com.vrchat.avatars": {"version": "3.10.5", "dependencies": {"com.vrchat.base": "3.10.5"}},
                                       "com.vrchat.base": {"version": "3.10.5"}}, "extra": 1},
                           files={"Packages/com.vrchat.avatars/package.json": '{"name":"com.vrchat.avatars","version":"3.10.5"}',
                                  "Packages/mine/package.json": '{"name":"com.me.thing","version":"0.1.0"}',
                                  "Packages/notapackage/readme.txt": "x"})
        p = UnityProject.load(folder)
        self.assertEqual((str(p.unity), p.revision), ("2022.3.22f1", "887be4894c44"))
        self.assertEqual(p.project_type(), AVATARS)
        self.assertEqual(list(p.installed), ["com.vrchat.avatars"])
        self.assertEqual([(n, x and x.name) for n, x in p.unlocked], [("mine", "com.me.thing"), ("notapackage", None)])
        p.save()
        saved = json.loads((folder / "Packages" / "vpm-manifest.json").read_text())
        self.assertEqual(saved["extra"], 1, "anything else in the manifest stays")
        self.assertEqual(saved["locked"]["com.vrchat.base"], {"version": "3.10.5", "dependencies": {}})

    def test_kinds(self):
        self.assertEqual(UnityProject.load(self.make({"locked": {"com.vrchat.worlds": {"version": "3.0.0"}}})).project_type(), WORLDS)
        self.assertEqual(UnityProject.load(self.make({"dependencies": {"x.y": {"version": "1.0.0"}}})).project_type(), VPM_STARTER)
        self.assertEqual(UnityProject.load(self.make()).project_type(), UNKNOWN)

    def test_not_a_project(self):
        from hoard.vpm.project import ProjectError
        with self.assertRaises(ProjectError):
            UnityProject.load(Path(tempfile.mkdtemp()))
        bad = self.make()
        (bad / "Packages" / "vpm-manifest.json").write_text("{nope")
        with self.assertRaises(ProjectError):
            UnityProject.load(bad)


if __name__ == "__main__":
    unittest.main()
