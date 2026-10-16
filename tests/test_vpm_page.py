"""Projects on the page (shared.js): the list shared with ALCOM and the Creator Companion, a project's packages with
the changes shown before they're made, a project Hoard for Unity reported that isn't on the list, a new project's
form, and Unity and folders, all saved where ALCOM and the Creator Companion read them. The sample is
scripts/i18n_strings.py's (the language walkthrough steps through the same views)."""
import json
import os
import sys
import tempfile
import threading
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

    def test_a_project(self):
        page = self.page
        page.locator(".pj-row", has_text="Rusk Avatar").locator("[data-pj=manage]").click()
        page.locator(".pj-pk").wait_for()
        text = page.locator("#projectsBody").inner_text()
        self.assertIn("Some packages aren't installed the way the project says.", text)
        self.assertIn("Unity 2022.3.22f1 isn't installed", text)
        self.assertIn("What Hoard for Unity found in it", text, "its report, with its credits")
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
        page.click("[data-pj=addpkg]")
        page.locator("dialog.pj-dlg input[value='com.vrchat.avatars']").check()
        page.locator("dialog.pj-dlg button[value=yes]").click()
        page.locator(".pj-chips .pill", has_text="com.vrchat.avatars").wait_for()

    def test_unity_and_folders(self):
        page = self.page
        page.click("[data-pj=settings]")
        page.fill("#pjProjectsFolder", "relative")
        page.click("[data-pj=savesettings]")
        page.wait_for_function("() => document.querySelector('#toast').textContent.includes('full path')")
        folder = str(self.tmp / "New Projects")
        page.fill("#pjProjectsFolder", folder)
        page.check("#pjPrerelease")
        page.click("[data-pj=savesettings]")
        page.wait_for_function("() => document.querySelector('#toast').textContent === 'Saved.'")
        saved = self.settings()
        self.assertEqual((saved["defaultProjectPath"], saved["showPrereleasePackages"]), (folder, True))
        self.assertEqual(len(saved["userProjects"]), 2, "the rest of its settings kept")


if __name__ == "__main__":
    unittest.main()
