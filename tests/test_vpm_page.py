"""Projects on the page (shared.js): the list shared with ALCOM and the Creator Companion, a project's packages with
the changes shown before they're made, a project Hoard for Unity reported that isn't on the list, a new project's
form, and Unity and folders, all saved where ALCOM and the Creator Companion read them. The sample is
scripts/i18n_strings.py's (the language walkthrough steps through the same views)."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from hoard import server  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class ProjectsPanel(unittest.TestCase):
    def setUp(self):
        import i18n_strings
        from playwright.sync_api import sync_playwright
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(self.tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        saving = mock.patch.object(server, "save_config")
        saving.start()
        self.addCleanup(saving.stop)
        self.srv = i18n_strings.sample_server(self.tmp / "library", "en")
        env2 = mock.patch.dict(os.environ, i18n_strings.sample_projects(self.tmp))
        env2.start()
        self.addCleanup(env2.stop)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.pw = sync_playwright().start()
        self.addCleanup(self.pw.stop)
        self.browser = self.pw.chromium.launch()
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(self.srv.entry_url())
        self.page.wait_for_function("() => localStorage.getItem('hoard-key')")
        self.page.click("#projectsTab")
        self.page.locator(".pj-row").first.wait_for()

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def settings(self) -> dict:
        return json.loads((self.tmp / "vcc" / "settings.json").read_text("utf-8"))

    def test_the_list(self):
        page = self.page
        rows = page.locator("#projectsBody .pj-row")
        self.assertEqual(rows.count(), 3)
        self.assertIn("Avatars · Unity 2022.3.22f1", rows.nth(0).inner_text())
        self.assertIn("The folder isn't there", rows.nth(1).inner_text(), "a project whose folder has gone")
        self.assertIn("Opened in Unity with Hoard, not on the list", page.locator("#projectsBody").inner_text())
        self.assertIn("1 asset from Hoard", rows.nth(2).inner_text())
        page.fill("#pjFind", "mochi")
        self.assertEqual(page.locator("#projectsBody .pj-row:visible").count(), 1)
        page.fill("#pjFind", "")
        # a favourite, kept in Hoard's own notes, goes first
        page.locator(".pj-row", has_text="Old World").locator("[data-pj=star]").click()
        page.wait_for_function("() => document.querySelector('.pj-row b').textContent === 'Old World'")
        self.assertTrue(page.locator(".pj-row", has_text="Old World").locator("[data-pj=star]").get_attribute("aria-pressed") == "true")
        # taken off the list: off the Creator Companion's too, its other settings kept
        page.locator(".pj-row", has_text="Old World").locator("[data-pj=forget]").click()
        page.locator("dialog.ask .primary").click()
        page.wait_for_function("() => ![...document.querySelectorAll('.pj-row b')].some(b => b.textContent === 'Old World')")
        self.assertEqual([Path(p).name for p in self.settings()["userProjects"]], ["Rusk Avatar"])

    def test_the_whole_window_and_its_tabs(self):
        """Projects is a place of its own, the whole window below the bar, with its views as tabs; its rows alternate;
        Add a repository comes before the list; Add a project opens the system's folder picker; a project can be
        deleted from this computer, only with its name typed; and its task shows at the top, with Stop."""
        page = self.page
        box = page.locator("#projectsWin").bounding_box()
        bar = page.evaluate("() => document.querySelector('header').getBoundingClientRect().bottom")
        self.assertEqual((box["x"], box["width"]), (0, 1280), "the whole width")
        self.assertLessEqual(abs(box["y"] - bar), 2, "from the bar down")
        self.assertGreaterEqual(box["y"] + box["height"], 899, "to the bottom")
        self.assertEqual(page.locator(".pj-tabs .pj-tab").all_inner_texts(), ["Projects", "Repositories", "Backups", "Unity and folders"])
        rows = page.locator("#projectsBody .pj-list > li")
        colour = lambda n: rows.nth(n).evaluate("e => getComputedStyle(e).backgroundColor")  # noqa: E731
        self.assertNotEqual(colour(0), colour(1), "rows alternate")
        page.set_viewport_size({"width": 2000, "height": 900})   # a wide window: its rows use all of it, not a column
        self.assertGreater(page.locator("#projectsBody .pj-list").first.bounding_box()["width"], 1900)
        page.set_viewport_size({"width": 1280, "height": 900})
        page.click(".pj-tabs [data-pj=repos]")
        page.locator("#pjRepoUrl").wait_for()
        order = page.evaluate("() => [document.querySelector('#pjRepoUrl'), document.querySelector('#projectsBody .pj-list')]"
                              ".map(e => e.getBoundingClientRect().top)")
        self.assertLess(order[0], order[1], "Add a repository first, then the list")
        page.click(".pj-tabs [data-pj=back]")
        # Add a project...: the system's own folder picker, opening in the projects folder
        mine = self.tmp / "Unity" / "Picked Project"
        for sub in ("Assets", "Packages", "ProjectSettings"):
            (mine / sub).mkdir(parents=True)
        asked = []
        self.srv.pick_path = lambda kind, start: asked.append((kind, start)) or str(mine)
        page.reload()
        page.wait_for_function("() => DATA && DATA.can_pick")
        page.click("#projectsTab")
        page.click("[data-pj=add]")
        page.locator(".pj-row", has_text="Picked Project").wait_for()
        self.assertEqual(asked[0][0], "folder")
        # Delete from this computer: the button waits for its name
        ran = []
        self.srv.project_jobs.project_runner = lambda what: ran.append(what) or "Done."
        page.locator(".pj-row", has_text="Picked Project").locator("[data-pj=manage]").click()
        page.click("[data-pj=delete]")
        sure = page.locator("dialog.pj-dlg", has_text="Delete Picked Project from this computer?")
        self.assertTrue(sure.locator("#pjDelBackup").is_checked(), "backed up first, unless you untick it")
        self.assertTrue(sure.locator("#pjDelGo").is_disabled())
        sure.locator("#pjDelName").fill("Picked")
        self.assertTrue(sure.locator("#pjDelGo").is_disabled())
        sure.locator("#pjDelName").fill("Picked Project")
        sure.locator("#pjDelGo").click()
        for _ in range(100):
            if ran:
                break
            page.wait_for_timeout(100)
        self.assertEqual((ran[0]["op"], ran[0]["name"], ran[0]["backup"]), ("delete", "Picked Project", True))
        # what Projects' own lane is doing: at the top, with Stop
        from hoard.common import log
        going = threading.Event()

        def slow(what):
            while not going.is_set():
                log("Backing up, slowly")
                time.sleep(0.05)
            return "Done."
        self.addCleanup(going.set)
        self.srv.project_jobs.project_runner = slow
        page.locator(".pj-row", has_text="Rusk Avatar").locator("[data-pj=manage]").click()
        page.click("[data-pj=backup]")
        page.locator("dialog.pj-dlg button[value=yes]").click()
        strip = page.locator("#pjJob")
        # (its message, not only Stop: the delete before may still show as it ended, until the next look 1.5s on)
        strip.locator(".pj-job-msg", has_text="Backing up, slowly").wait_for()
        self.assertTrue(strip.locator("[data-pj=stopjob]").is_visible())
        strip.locator("[data-pj=stopjob]").click()
        strip.wait_for(state="hidden")
        self.assertEqual(self.srv.project_jobs.history[-1]["outcome"], "stopped")

    def test_a_project(self):
        page = self.page
        page.locator(".pj-row", has_text="Rusk Avatar").locator("[data-pj=manage]").click()
        page.locator(".pj-pk").wait_for()
        text = page.locator("#projectsBody").inner_text()
        self.assertIn("Some packages aren't installed the way the project says.", text)
        self.assertIn("Unity 2022.3.22f1 isn't installed", text)
        # its tabs: Packages, Add packages, From your library, and what Hoard for Unity reported of it
        tabs = page.locator(".pj-subs .pj-tab")
        self.assertEqual(tabs.evaluate_all("l => l.map(b => b.dataset.sub)"), ["packages", "add", "library", "report"])
        page.click(".pj-subs [data-sub=report]")
        page.locator(".proj", has_text="What Hoard for Unity found in it").wait_for()
        page.click(".pj-subs [data-sub=packages]")
        page.locator(".pj-pk").wait_for()
        avatars = page.locator(".pj-pk tr", has_text="com.vrchat.avatars")
        self.assertIn("Not installed", avatars.inner_text())
        self.assertIn("Update to 3.10.5", avatars.inner_text())
        # what a change does is shown first: nothing is changed by looking
        page.click("[data-pj=repair]")
        dialog = page.locator("dialog.pj-dlg")
        dialog.wait_for()
        self.assertIn("VRChat SDK - Avatars 3.7.0", dialog.inner_text())
        dialog.locator("button[value=no]").click()
        page.locator(".pj-pk tr", has_text="VRChat SDK - Base").locator("[data-pj=remove]").click()
        dialog.wait_for()
        self.assertIn("com.vrchat.base", dialog.inner_text())
        dialog.locator("button[value=no]").click()
        self.assertTrue((self.tmp / "Unity" / "Rusk Avatar" / "Packages" / "com.vrchat.base").is_dir())
        # another version of a package (#160): every one that works in its Unity, the one installed chosen to start with
        self.assertEqual(avatars.locator("[data-pj=versions]").count(), 0, "one that isn't installed has none to change")
        page.locator(".pj-pk tr", has_text="VRChat SDK - Base").locator("[data-pj=versions]").click()
        versions = page.locator("dialog.pj-dlg", has_text="Choose the version to install")
        versions.wait_for()
        self.assertEqual(versions.locator(".pj-vers input").evaluate_all("l => l.map(i => i.value)"), ["3.10.5", "3.7.0"])
        self.assertTrue(versions.locator(".pj-vers input[value='3.7.0']").is_checked())
        self.assertIn("Installed now", versions.locator(".pj-vers li", has_text="3.7.0").inner_text())
        versions.locator(".pj-vers input[value='3.10.5']").check()
        versions.locator("button[value=yes]").click()
        changes = page.locator("dialog.pj-dlg", has_text="These changes will be made")
        changes.wait_for()
        self.assertIn("VRChat SDK - Base 3.10.5", changes.inner_text())
        changes.locator("button[value=no]").click()
        page.click("[data-pj=back]")
        page.locator("#pjFind").wait_for()

    def test_a_reported_project_and_a_new_one(self):
        page = self.page
        page.locator(".pj-row", has_text="Mochi World").locator("[data-pj=report]").click()
        page.locator(".proj textarea").wait_for()
        self.assertIn("Rusk by Kitsu Studio", page.locator(".proj textarea").input_value())
        page.click("[data-pj=back]")
        page.click("[data-pj=new]")
        page.locator("#pjName").wait_for()
        self.assertEqual(page.locator("#pjTemplate").input_value(), "com.anatawa12.vrc-get.vrchat.avatars")
        self.assertEqual(page.locator("#pjUnity").input_value(), "2022.3.22f1")
        page.fill("#pjName", "CON")
        page.wait_for_function("() => document.querySelector('#pjNameNote').textContent.includes(\"can't be used\")")
        # a product from the library, chosen file by file
        page.click("[data-pj=addprod]")
        page.locator("dialog.pj-dlg .linkish", has_text="Rusk").click()
        page.locator("dialog.pj-dlg", has_text="rusk.unitypackage").locator("button[value=yes]").click()
        page.locator(".pj-pre", has_text="rusk.unitypackage").wait_for()
        # Hoard for Unity is in a new project unless you leave it out
        self.assertIn("Hoard for Unity", page.locator(".pj-chips").inner_text())
        # Add packages: a view of its own (not a window over the page), and back to the new project
        page.click("[data-pj=addpkg]")
        page.locator(".pj-addlist input[value='com.vrchat.avatars']").check()
        self.assertEqual(page.locator("dialog[open]").count(), 0)
        # the newest unless another version is chosen (#160)
        pick = page.locator(".pj-addlist .pj-pick-ver")
        page.locator(".pj-addlist .pj-pick-ver option[value='3.7.0']").wait_for(state="attached")
        self.assertEqual(pick.locator("option").evaluate_all("l => l.map(o => o.value)"), ["", "3.10.5", "3.7.0"])
        pick.select_option("3.7.0")
        self.assertIn("1 chosen", page.locator(".pj-addbar").inner_text())
        page.click("[data-pj=addchosen]")
        self.assertIn("3.7.0", page.locator(".pj-chips .pill", has_text="com.vrchat.avatars").inner_text())
        self.assertEqual(page.input_value("#pjName"), "CON", "what was typed is kept")

    def test_unity_and_folders(self):
        page = self.page
        page.click("[data-pj=settings]")
        page.fill("#pjProjectsFolder", "relative")
        page.click("[data-pj=savesettings]")
        page.wait_for_function("() => document.querySelector('#toast').textContent.includes('full path')")
        self.assertEqual(page.input_value("#pjProjectsFolder"), "relative", "a refused save keeps what was typed, to put right")
        page.evaluate("loadProjects()")   # (as when a task ends, while you're typing)
        page.wait_for_timeout(300)
        self.assertEqual(page.input_value("#pjProjectsFolder"), "relative", "and drawing it again keeps it too")
        folder = str(self.tmp / "New Projects")
        page.fill("#pjProjectsFolder", folder)
        page.check("#pjPrerelease")
        page.click("[data-pj=savesettings]")
        page.wait_for_function("() => document.querySelector('#toast').textContent === 'Saved.'")
        saved = self.settings()
        self.assertEqual((saved["defaultProjectPath"], saved["showPrereleasePackages"]), (folder, True))
        self.assertEqual(len(saved["userProjects"]), 2, "the rest of its settings kept")

    def test_put_products_in_a_project_from_their_menu(self):
        """Right-click a downloaded product (or choose several with Select): Projects, Put in a project..."""
        page = self.page
        ran = []
        self.srv.project_jobs.project_runner = lambda what: ran.append(what) or "Done."   # (Projects' own lane)
        page.keyboard.press("Escape")
        page.locator("#projectsWin").wait_for(state="hidden")
        page.locator(".slot", has_text="Rusk").first.click(button="right")
        page.locator(".selmenu [role=menuitem]", has_text="Put in a project...").click()
        chooser = page.locator("dialog.pj-dlg")
        self.assertNotIn("Old World", chooser.inner_text(), "only projects whose folder is there")
        chooser.locator(".linkish", has_text="Rusk Avatar").click()
        sure = page.locator("dialog.pj-dlg", has_text="Put these in Rusk Avatar?")
        self.assertIn("rusk.unitypackage", sure.inner_text())
        sure.locator("button[value=yes]").click()
        for _ in range(200):
            if ran:
                break
            page.wait_for_timeout(100)
        self.assertEqual((ran[0]["op"], Path(ran[0]["path"]).name), ("preload", "Rusk Avatar"))
        self.assertEqual([(p["kind"], p["file"]) for p in ran[0]["picks"]], [("unitypackage", "rusk.unitypackage")])

    def test_a_new_project_with_products_from_the_menu(self):
        page = self.page
        page.keyboard.press("Escape")
        page.locator("#projectsWin").wait_for(state="hidden")
        page.click("nav.apptabs a[href='/downloads']")
        page.locator("#grid .slot", has_text="Rusk").first.click(button="right")
        page.locator(".selmenu [role=menuitem]", has_text="New project with these...").click()
        page.locator("#projectsWin #pjName").wait_for()
        self.assertIn("rusk.unitypackage", page.locator("#projectsWin .pj-pre").inner_text(), "already in the new project")


if __name__ == "__main__":
    unittest.main()
