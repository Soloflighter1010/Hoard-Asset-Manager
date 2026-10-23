"""Issue #86: Projects, the Unity projects that use your assets (as Hoard for Unity reports them), in Hoard."""
from __future__ import annotations

import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import config, downloader, projects, server  # noqa: E402
from hoard.safety import ACCESS_HEADER  # noqa: E402
from hoard.tags import tag_key as tags_key  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _pw:
        _pw.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False


def report(**extra) -> dict:
    """A report as Hoard for Unity writes one."""
    return {"format": "hoard-project", "version": 1, "name": "My Avatar", "path": "/home/me/My Avatar", "unity": "2022.3.22f1",
            "updated": "2026-10-01T12:00:00+00:00",
            "assets": [{"store": "Booth", "name": "Rusk", "creator": "Kitsu Studio", "folder": "Booth/Kitsu Studio/Rusk",
                        "url": "https://booth.pm/ja/items/111", "status": "yes"},
                       {"store": "Gumroad", "name": "Mochi", "creator": "Mochi Works", "folder": "Gumroad/Mochi Works/Mochi",
                        "url": None, "status": "partly"}],
            "credits": {"title": "Assets used", "style": "List", "left_out": [], "added": []}, **extra}


def write(project_id: str, data) -> Path:
    projects.projects_dir().mkdir(parents=True, exist_ok=True)
    path = projects.projects_dir() / f"{project_id}.json"
    path.write_text(json.dumps(data), "utf-8")
    return path


class Reports(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(projects.projects_dir(), ignore_errors=True)
        self.addCleanup(shutil.rmtree, projects.projects_dir(), True)

    def test_a_report_is_read(self):
        write("0123456789abcdef", report())
        [p] = projects.read_all()
        self.assertEqual((p["id"], p["name"], [a["status"] for a in p["assets"]]), ("0123456789abcdef", "My Avatar", ["yes", "partly"]))
        self.assertEqual(projects.credits_text(p), "Assets used\n- Rusk by Kitsu Studio (Booth) https://booth.pm/ja/items/111\n",
                         "only what's all in the project is credited (issue #79)")
        self.assertEqual(projects.used_in([p]), {"Booth/Kitsu Studio/Rusk": ["My Avatar"], "Gumroad/Mochi Works/Mochi": ["My Avatar"]})

    def test_by_creator_whatever_the_case(self):
        """A creator whose name's case differs between stores is one line, as in Hoard for Unity."""
        assets = [{"store": "Booth", "name": "Rusk", "creator": "Kitsu", "folder": "Booth/Kitsu/Rusk", "url": None, "status": "yes"},
                  {"store": "Jinxxy", "name": "Tail", "creator": "Mia", "folder": "Jinxxy/Mia/Tail", "url": None, "status": "yes"},
                  {"store": "Gumroad", "name": "Ears", "creator": "kitsu", "folder": "Gumroad/kitsu/Ears", "url": None, "status": "yes"}]
        write("0123456789abcdef", report(assets=assets, credits={"title": "", "style": "ByCreator", "left_out": [], "added": []}))
        [p] = projects.read_all()
        self.assertEqual(projects.credits_text(p), "kitsu: Ears, Rusk\nMia: Tail\n", "sorted, then one line a creator")

    def test_written_by_another_program_so_checked_as_such(self):
        hostile = report(name="Evil\u202eName" + "x" * 500, assets=[
            {"store": "Steam", "name": "Unknown store", "folder": "Steam/x", "status": "yes"},
            {"store": "Booth", "name": "Escaping", "folder": "../../etc", "status": "yes"},
            {"store": "Booth", "name": "Odd status", "folder": "Booth/a", "status": "owned"},
            {"store": "Booth", "name": "Odd link", "creator": "<script>", "folder": "Booth/b",
             "url": "https://booth.pm.evil.example/x", "status": "yes"},
            "not an object"],
            credits={"title": 5, "style": "Weird", "left_out": [7], "added": [{"name": "Mine", "url": "javascript:alert(1)"}]})
        write("aaaaaaaaaaaaaaaa", hostile)
        write("not-an-id", report())
        write("bbbbbbbbbbbbbbbb", {"format": "something else"})
        (projects.projects_dir() / "cccccccccccccccc.json").write_text("{broken", "utf-8")
        [p] = projects.read_all()
        self.assertNotIn("\u202e", p["name"])
        self.assertLessEqual(len(p["name"]), 200)
        self.assertEqual([(a["name"], a["url"]) for a in p["assets"]], [("Odd link", None)])
        self.assertEqual((p["credits"]["style"], p["credits"]["left_out"]), ("List", []))
        self.assertEqual(p["credits"]["added"][0]["url"], None)

    def test_forget(self):
        path = write("0123456789abcdef", report())
        self.assertFalse(projects.forget("../config"))
        self.assertFalse(projects.forget("0123456789abcdef\n"), "a trailing newline isn't part of an id")
        self.assertFalse(projects.forget("fedcba9876543210"), "no such report")
        self.assertTrue(projects.forget("0123456789abcdef"))
        self.assertFalse(path.exists())


class ProjectsServer(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(projects.projects_dir(), ignore_errors=True)
        self.addCleanup(shutil.rmtree, projects.projects_dir(), True)
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        folder = self.root / "Booth" / "Kitsu Studio" / "Rusk"
        folder.mkdir(parents=True)
        (folder / "rusk.zip").write_bytes(b"zip")
        man = downloader.Manifest(self.root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Rusk")
        rec["files"]["f1"] = {"path": "rusk.zip", "size": 3}
        man.save()
        write("0123456789abcdef", report())
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.root)}, lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=20)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Content-Type": "application/json", ACCESS_HEADER: self.srv.key, "Accept-Encoding": "identity"})
        r = c.getresponse()
        data = json.loads(r.read() or b"{}")
        c.close()
        return r.status, data

    def test_projects_and_their_downloads(self):
        _, data = self.call("GET", "/api/projects")
        [p] = data["projects"]
        rusk = p["assets"][0]
        self.assertIsNotNone(rusk["download"], "linked to its download")
        self.assertIsNone(p["assets"][1]["download"], "not downloaded here")
        self.assertEqual(set(p["credits_text"]), {"List", "Markdown", "ByCreator"})
        self.assertEqual(p["counts"], {"yes": 1, "partly": 1, "imported": 0})
        self.assertEqual([a["tag_key"] for a in p["assets"]], [tags_key("Booth", "Rusk"), tags_key("Gumroad", "Mochi")],
                         "each as a set names it (Make a set)")
        _, assets = self.call("GET", "/api/assets")
        self.assertEqual(assets["assets"][0]["used_in"], ["My Avatar"], "Downloads says which projects use it")
        self.assertEqual(self.call("POST", "/api/projects/forget", {"id": p["id"]}), (200, {"ok": True}))
        self.assertEqual(self.call("GET", "/api/projects")[1]["projects"], [])

    def test_hidden_products_stay_hidden(self):
        from hoard import marks, tags
        st = marks.MarkStore()
        st.set_pin("4821")
        st.change("hidden", {tags.tag_key("Booth", "Rusk")}, True)
        self.addCleanup(lambda: st.path.unlink(missing_ok=True))
        status, data = self.call("GET", "/api/projects")
        self.assertNotIn("Rusk", json.dumps(data), "a hidden product's name never leaves the server while locked")
        self.assertTrue(data["hidden_left_out"])


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class ProjectsPage(unittest.TestCase):
    """A project Hoard for Unity reported, in Projects: not on the Creator Companion's list (an empty one of its own
    here, so a real one is never read), it's listed below it, with what it uses and its credits."""

    def setUp(self):
        from unittest import mock
        vcc = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, vcc, True)
        env = mock.patch.dict(os.environ, {"HOARD_VCC_DIR": str(vcc)})
        env.start()
        self.addCleanup(env.stop)

    def test_the_projects_panel(self):
        shutil.rmtree(projects.projects_dir(), ignore_errors=True)
        self.addCleanup(shutil.rmtree, projects.projects_dir(), True)
        write("0123456789abcdef", report(credits={"title": "Assets used", "style": "Markdown", "left_out": [],
                                                  "added": [{"name": "Hair Pack", "creator": "Mia", "url": None}]}))
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1300, "height": 860})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.entry_url())
            page.click("#projectsTab")
            row = page.locator("#projectsWin .pj-row", has_text="My Avatar")
            self.assertIn("2 assets from Hoard", row.inner_text())
            row.locator("[data-pj=report]").click()
            page.locator("#projectsWin .proj").wait_for()
            self.assertIn("My Avatar", page.locator("#projectsWin .pj-h").inner_text())
            self.assertIn("Partly in the project", page.locator("#projectsWin .pj-tiles").inner_text())
            box = page.locator("#projectsWin textarea")
            self.assertIn("## Assets used", box.input_value(), "the style chosen in Unity")
            page.select_option("#projectsWin [data-proj-style]", "ByCreator")
            self.assertEqual(box.input_value(), "Assets used\nKitsu Studio: Rusk\nMia: Hair Pack\n")
            page.click("#projectsWin [data-pj='back']")
            page.click("#projectsWin [data-pj='forgetreport']")
            page.click("#askDialog[open] button[value=yes]")
            # (the list says "No projects yet" all along here, the Creator Companion's being empty: wait for the row)
            page.locator("#projectsWin .pj-row", has_text="My Avatar").wait_for(state="detached")
            self.assertEqual(projects.read_all(), [])
            self.assertEqual(errors, [])
            browser.close()


    def test_make_a_set_of_a_project(self):
        from hoard.sets import SetStore
        shutil.rmtree(projects.projects_dir(), ignore_errors=True)
        self.addCleanup(shutil.rmtree, projects.projects_dir(), True)
        self.addCleanup(lambda: SetStore().path.unlink(missing_ok=True))
        gone = {"store": "Booth", "name": "Old Hat", "creator": "Mia", "folder": "Booth/Mia/Old Hat", "url": None,
                "status": "imported"}
        write("0123456789abcdef", report(assets=report()["assets"] + [gone]))
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1300, "height": 860})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.click("nav.apptabs a[href='/downloads']")
            page.click("#projectsTab")
            page.click("#projectsWin [data-pj='report']")
            page.click("#projectsWin [data-proj='set']")
            name = page.locator("dialog[open] #askName")
            self.assertEqual(name.input_value(), "My Avatar", "named for the project, to change if you like")
            name.fill("My Avatar, as worn")
            page.locator("dialog[open] button", has_text="OK").click()
            page.get_by_text("Made the set My Avatar, as worn, with 2 products in it.").wait_for()
            page.locator('#stores [data-store="Sets"] .n', has_text="1").wait_for()   # Downloads shows it straight away
            [made] = SetStore().load()["sets"]
            self.assertEqual(made["items"], [tags_key("Booth", "Rusk"), tags_key("Gumroad", "Mochi")],
                             "what's in it now: not what was imported once and is gone")
            page.goto(page.url.split("/downloads")[0] + "/")   # and from the Library page
            page.click("#projectsTab")
            page.click("#projectsWin [data-pj='report']")
            page.click("#projectsWin [data-proj='set']")
            page.locator("dialog[open] button", has_text="OK").click()
            page.get_by_text("Made the set My Avatar, with 2 products in it.").wait_for()
            self.assertEqual(len(SetStore().load()["sets"]), 2)
            self.assertEqual(errors, [])
            browser.close()


class PublicPages(unittest.TestCase):
    """A credits list is for sharing, so each product in it links to its public page: never the link Hoard keeps for
    you as its buyer (Jinxxy's inventory, or a Gumroad download page, which opens its files for whoever has it)."""

    INVENTORY = "https://jinxxy.com/my/inventory/3988217771405083873"
    PAGE = "https://jinxxy.com/antistar/RedLine"
    DOWNLOAD = "https://app.gumroad.com/d/0123456789abcdef"

    def setUp(self):
        shutil.rmtree(projects.projects_dir(), ignore_errors=True)
        self.addCleanup(shutil.rmtree, projects.projects_dir(), True)

    def library(self) -> Path:
        """library.json, with the Jinxxy product's public page that a refresh found (4.3.1)."""
        from hoard import library
        path = Path(tempfile.mkdtemp()) / "library.json"
        self.addCleanup(shutil.rmtree, path.parent, True)
        lib = library.Library(path)
        lib.data["items"] = [library.item("jinxxy", "3988217771405083873", name="Red Line", creator="Antistar",
                                          url=self.INVENTORY, page=self.PAGE),
                             library.item("gumroad", "g1", name="Mochi", creator="Mochi Works", url=self.DOWNLOAD,
                                          creator_url="https://mochi.gumroad.com")]
        lib.save()
        return path

    def downloads(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for store, key, creator, name, url in (("Jinxxy", "3988217771405083873", "Antistar", "Red Line", self.INVENTORY),
                                               ("Gumroad", "g1", "Mochi Works", "Mochi", self.DOWNLOAD),
                                               ("Gumroad", "g2", "Kitsu", "Ears", "https://app.gumroad.com/d/fedcba9876543210"),
                                               ("Booth", "111", "Kitsu Studio", "Rusk", "https://booth.pm/ja/items/111")):
            man = downloader.Manifest(root / store)
            rec = man.record(key, creator, name)
            rec.update(name=name, creator=creator, url=url)
            (root / store / rec["folder"]).mkdir(parents=True, exist_ok=True)
            (root / store / rec["folder"] / "a.unitypackage").write_bytes(b"x")
            rec["files"]["f1"] = {"path": "a.unitypackage", "size": 1}
            man.save()
        return root

    def test_the_catalog_gives_each_download_its_public_page(self):
        from unittest import mock
        from hoard import paths
        root = self.downloads()
        with mock.patch.object(paths, "LIBRARY_FILE", self.library()):
            catalog, _tags = downloader.collect_catalog(config.load_config(), root)
        pages = {e["name"]: e.get("page") for e in catalog}
        self.assertEqual(pages, {"Red Line": self.PAGE, "Mochi": "https://mochi.gumroad.com", "Ears": None,
                                 "Rusk": "https://booth.pm/ja/items/111"},
                         "the library's page; its creator's when it has none; never a download page; a public link as it is")
        self.assertEqual([downloader.validate_catalog_entry(e) for e in catalog], [[]] * 4)
        self.assertEqual(next(e for e in catalog if e["name"] == "Red Line")["url"], self.INVENTORY, "url is still yours")
        rusk = next(e for e in catalog if e["name"] == "Rusk")
        self.assertTrue(downloader.validate_catalog_entry({**rusk, "page": self.DOWNLOAD.replace("app.", "")}),
                        "a catalog never says a download page is public")

    def test_a_list_hoard_didnt_write_here_gives_no_pages(self):
        from hoard import library
        path = self.library()
        self.assertEqual(library.public_pages(path)[self.INVENTORY], self.PAGE)
        raw = json.loads(path.read_text("utf-8"))
        raw["items"][0]["page"] = "https://jinxxy.com/someone/else"
        path.write_text(json.dumps(raw), "utf-8")
        self.assertEqual(library.public_pages(path), {}, "edited after Hoard saved it")
        path.write_text("{not json", "utf-8")
        self.assertEqual(library.public_pages(path), {})
        self.assertTrue(path.exists(), "left for Library to set aside")

    def test_credits_link_each_products_public_page(self):
        assets = [{"store": "Jinxxy", "name": "Red Line", "creator": "Antistar", "folder": "Jinxxy/Antistar/Red Line",
                   "url": self.INVENTORY, "status": "yes"},
                  {"store": "Gumroad", "name": "Ears", "creator": "Kitsu", "folder": "Gumroad/Kitsu/Ears",
                   "url": self.DOWNLOAD, "status": "yes"},
                  {"store": "Booth", "name": "Rusk", "creator": "Kitsu Studio", "folder": "Booth/Kitsu Studio/Rusk",
                   "url": "https://booth.pm/ja/items/111", "status": "yes"}]
        write("0123456789abcdef", report(assets=assets, credits={"title": "Assets used", "style": "Markdown", "left_out": [],
                                                                  "added": [{"name": "Hair", "creator": "Mia", "url": "https://mia.example/hair"}]}))
        [p] = projects.read_all()
        index = {"assets": [{"id": 1, "folder": "Jinxxy/Antistar/Red Line", "catalog_folder": "Jinxxy/Antistar/Red Line",
                             "tag_key": "jinxxy:redline", "page": self.PAGE}]}
        [shown] = projects.view([p], index, set())
        md = shown["credits_text"]["Markdown"]
        self.assertIn(f"[Red Line]({self.PAGE})", md, "its public page, from the catalog")
        self.assertIn("- Ears by Kitsu (Gumroad)", md, "no link rather than its download page")
        self.assertIn("[Rusk](https://booth.pm/ja/items/111)", md, "a public link as it is")
        self.assertIn("[Hair](https://mia.example/hair)", md, "one written in by hand as it was")
        for text in shown["credits_text"].values():
            self.assertNotIn("/my/inventory", text)
            self.assertNotIn("/d/", text)
        self.assertNotIn("/my/inventory", projects.credits_text(p), "without a download here, still never yours")


if __name__ == "__main__":
    unittest.main()
