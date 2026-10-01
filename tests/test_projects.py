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
            page.locator("#projectsWin .proj[open]").wait_for()
            self.assertIn("My Avatar", page.locator("#projectsWin summary").inner_text())
            self.assertIn("Partly in the project", page.locator("#projectsWin table").inner_text())
            box = page.locator("#projectsWin textarea")
            self.assertIn("## Assets used", box.input_value(), "the style chosen in Unity")
            page.select_option("#projectsWin [data-proj-style]", "ByCreator")
            self.assertEqual(box.input_value(), "Assets used\nKitsu Studio: Rusk\nMia: Hair Pack\n")
            page.click("#projectsWin [data-proj='forget']")
            page.click("#askDialog[open] button[value=yes]")
            page.get_by_text("No projects yet").wait_for()
            self.assertEqual(errors, [])
            browser.close()


if __name__ == "__main__":
    unittest.main()
