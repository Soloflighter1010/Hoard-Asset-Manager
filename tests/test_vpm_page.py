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
from tests.isolation import IsolatedTestCase
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from hoard import server  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


def pj_details(page, name):
    """A listed project's details (issue #246: its buttons are there, beside the list), opened from its row."""
    panel = page.locator("#projectsBody .pj-detail", has=page.locator(".pj-d-name", has_text=name))
    if not panel.count():
        page.locator(".pj-row", has_text=name).locator(".pj-open").click()
        panel.wait_for()
    return panel


def pj_saved(page, expr, arg=None):
    """Wait until a change made in Projects shows on the page. When it doesn't, the failure says what the page has
    instead (its list, a message it showed, requests that failed) and what Hoard saved, not just that time ran out:
    a change that never showed failed Folders and tags on Windows runners, and the timeout alone said nothing."""
    from playwright.sync_api import TimeoutError as TimedOut
    try:
        page.wait_for_function(expr, arg=arg)
    except TimedOut as e:
        from hoard.vpm import listing
        seen = page.evaluate("""() => ({busy: PJ.busy, view: PJ.view, typed: ($('#pjTagInput') || {}).value,
          projects: ((PJ.data || {}).projects || []).map(p => [p.name, p.path, p.folder, p.tags]),
          message: ($('#projectsBody > p.none') || {}).textContent || '', toast: ($('#toast') || {}).textContent || ''})""")
        try:
            saved, listed = listing.load_state()["projects"], listing.shared_paths()[0]
        except Exception as err:   # (what reading them says is worth knowing too)
            saved, listed = repr(err), None
        raise AssertionError(f"{e}\nthe page: {seen}\nsaved: {saved}\nlisted: {listed}\n"
                             f"requests that failed: {getattr(page, 'hoard_failed', [])}\n"
                             f"threads: {sorted(th.name for th in threading.enumerate())}") from None


def pj_folder(page, name, folder):
    """Put a listed project in a folder, in its details: one there is, a new one (named when it's chosen), or none ("")."""
    choose = pj_details(page, name).locator("#pjDFolder")
    if not folder:
        choose.select_option(value="")
    elif folder in choose.locator("option").all_inner_texts():
        choose.select_option(label=folder)
    else:
        choose.select_option(label="New folder...")
        page.fill("dialog[open] #askName", folder)
        page.keyboard.press("Enter")
    pj_saved(page, "f => PJ.data.projects.some(p => (p.folder || '') === f) && !PJ.busy", folder)


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class ProjectsPanel(IsolatedTestCase):
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
        self.page.hoard_failed = []   # (for pj_saved: what to say when a change doesn't show)
        self.page.on("response", lambda r: r.status >= 400 and self.page.hoard_failed.append(f"{r.request.method} {r.url} {r.status}"))
        self.page.on("requestfailed", lambda r: self.page.hoard_failed.append(f"{r.method} {r.url} {r.failure}"))
        self.page.add_init_script("sessionStorage.setItem('hoard-projects-opened', '1')")   # (its splash: test_the_splash)
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
        self.assertEqual(rows.nth(0).locator(".pj-chip").all_inner_texts(), ["Avatars", "Unity 2022.3.22f1"])
        # issue #198: in the Library's colours: each kind of project its own, down its row's side and on its chip
        self.assertIn("k-avatars", rows.nth(0).get_attribute("class"))
        side, chip = page.evaluate("""() => { const r = document.querySelector('.pj-row.k-avatars');
          return [getComputedStyle(r).boxShadow, getComputedStyle(r.querySelector('.pj-chip')).backgroundColor]; }""")
        self.assertIn("inset", side)
        self.assertNotIn(chip, ("rgba(0, 0, 0, 0)", "transparent"))
        self.assertEqual(page.locator(".pj-tab .dot").count(), 5, "each tab its colour")
        self.assertIn("The folder isn't there", rows.nth(1).inner_text(), "a project whose folder has gone")
        self.assertIn("Opened in Unity with Hoard, not on the list", page.locator("#projectsBody").inner_text())
        self.assertIn("1 asset from Hoard", rows.nth(2).inner_text())
        # issue #294: the project opened last is marked, on its row and in its details (none before one's opened)
        self.assertEqual(page.locator(".pj-last").count(), 0)
        from hoard.vpm import listing
        listing.note(str(self.tmp / "Unity" / "Old World"), opened="2026-10-01T10:00:00+00:00")
        listing.note(str(self.tmp / "Unity" / "Rusk Avatar"), opened="2026-10-30T10:00:00+00:00")
        page.evaluate("loadProjects()")
        page.locator(".pj-row.last").wait_for()
        last = page.evaluate("pjLastOpened().name")
        self.assertEqual(last, "Rusk Avatar")
        self.assertEqual(page.locator(".pj-row.last").count(), 1)
        self.assertEqual(page.locator(".pj-row.last .pj-name b").inner_text(), last)
        self.assertEqual(page.locator(".pj-row.last .pj-last").inner_text(), "Last opened")
        self.assertEqual(page.locator(".pj-row:not(.last) .pj-last").count(), 0)
        self.assertEqual(pj_details(page, last).locator(".pj-last").inner_text(), "Last opened")
        page.locator("[data-pj=undetail]").click()
        page.fill("#pjFind", "mochi")
        self.assertEqual(page.locator("#projectsBody .pj-row:visible").count(), 1)
        page.fill("#pjFind", "")
        # a favourite, kept in Hoard's own notes, goes first
        page.locator(".pj-row", has_text="Old World").locator("[data-pj=star]").click()
        page.wait_for_function("() => document.querySelector('.pj-row b').textContent === 'Old World'")
        self.assertTrue(page.locator(".pj-row", has_text="Old World").locator("[data-pj=star]").get_attribute("aria-pressed") == "true")
        # taken off the list: off the Creator Companion's too, its other settings kept
        pj_details(page, "Old World").locator("[data-pj=forget]").click()
        page.locator("dialog.ask .primary").click()
        page.wait_for_function("() => ![...document.querySelectorAll('.pj-row b')].some(b => b.textContent === 'Old World')")
        self.assertEqual([Path(p).name for p in self.settings()["userProjects"]], ["Rusk Avatar"])

    def test_a_projects_details(self):
        """Issue #246: a row says what's needed at a glance; choosing it opens its details beside the list, as a
        product's open beside the Library: its picture (its letters, in its kind's colour), what it is, its size on
        disk, Open in Unity, Manage and Show in folder, Organise, its folder and tags, what takes its room, its
        packages, what Hoard put in it, and its backups; Close puts them away."""
        page = self.page
        row = page.locator(".pj-row", has_text="Rusk Avatar")
        self.assertEqual(row.locator("[data-pj=unity], [data-pj=manage], [data-pj=backup]").count(), 0, "not on the row")
        panel = pj_details(page, "Rusk Avatar")
        self.assertEqual(panel.locator(".pj-d-art b").inner_text(), "RA")
        self.assertIn("k-avatars", panel.get_attribute("class"))
        self.assertEqual(panel.locator(".actions button").all_inner_texts(), ["Open in Unity", "Manage", "Show in folder"])
        self.assertEqual(panel.locator(".marks").first.locator("button").all_inner_texts(), ["Make it a favourite", "Back up...", "Rename...", "Take off the list"])
        self.assertIn("Unity 2022.3.22f1", panel.inner_text())
        self.assertEqual(row.locator(".pj-open").get_attribute("aria-pressed"), "true")
        # what's read once it's open: its size on disk (Unity's cache apart), its packages, and its backups
        panel.locator(".pj-sizes").wait_for()
        facts = dict(zip(panel.locator(".pj-facts dt").all_inner_texts(), panel.locator(".pj-facts dd").all_inner_texts()))
        about = page.evaluate("PJ.about")
        self.assertEqual(facts["Size on disk"], page.evaluate("n => sizeText(n)", about["size"]["total"]))
        self.assertGreater(about["size"]["total"], 0)
        self.assertEqual(facts["Packages"], str(len(about["packages"]) + about["own_packages"]))
        self.assertEqual(facts["Backups"], str(about["backups"]["count"]))
        self.assertEqual(panel.locator(".pj-sizes li span").all_inner_texts(), ["Assets", "Packages", "Unity's cache", "Everything else"])
        self.assertEqual(panel.locator(".pj-d-list").first.locator("li").count(), min(12, len(about["packages"])))
        backups = about["backups"]
        self.assertGreater(backups["count"], 1, "(the sample's)")
        self.assertIn(f"{backups['count']} backups, {page.evaluate('n => sizeText(n)', backups['size'])}, the newest made", panel.inner_text())
        panel.locator("[data-pj=undetail]").click()
        self.assertEqual(page.locator(".pj-detail").count(), 0)
        self.assertTrue(page.evaluate("document.activeElement.classList.contains('pj-open')"), "back to its row")
        gone = pj_details(page, "Old World")   # (its folder has gone: nothing to open, or read)
        self.assertEqual(gone.locator(".actions button").count(), 0)
        self.assertEqual(gone.locator(".marks button").all_inner_texts(), ["Make it a favourite", "Take off the list"])
        self.assertEqual(gone.locator(".pj-d-about").inner_text(), "")

    def test_drag_projects_into_folders(self):
        """Issue #281: a project dropped on another makes a folder of them, named as it's made; one dropped on a folder
        (its tile, or its button above the list) goes in it. What a drop will do shows as you drag."""
        page = self.page
        row = lambda name: page.locator("#projectsBody .pj-row", has_text=name)  # noqa: E731
        self.assertEqual(row("Rusk Avatar").get_attribute("draggable"), "true")
        row("Rusk Avatar").drag_to(row("Old World"))
        page.locator("dialog[open] #askName").wait_for()
        page.fill("dialog[open] #askName", "Duo")
        page.keyboard.press("Enter")
        page.wait_for_function("() => PJ.data.projects.filter(p => p.folder === 'Duo').length === 2")
        # out of it, then dropped on its button above the list: in it again
        pj_folder(page, "Rusk Avatar", "")
        chip = page.locator('#projectsBody .pj-folders [data-folder="Duo"]')
        chip.wait_for()
        page.wait_for_timeout(300)   # (the list drawn again once it's out)
        hint = page.evaluate("""() => { const dt = new DataTransfer(), from = [...document.querySelectorAll('#projectsBody .pj-row')].find(r => r.textContent.includes('Rusk Avatar'));
          const to = document.querySelector('#projectsBody .pj-folders [data-folder="Duo"]');
          from.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }));
          to.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
          const said = to.dataset.dropHint;
          document.dispatchEvent(new DragEvent('dragend', { bubbles: true }));
          return said; }""")
        self.assertEqual(hint, "Move into Duo")
        row("Rusk Avatar").drag_to(chip)
        page.wait_for_function("() => PJ.data.projects.find(p => p.name === 'Rusk Avatar').folder === 'Duo'")

    @unittest.skipUnless(__import__("shutil").which("git"), "needs Git installed")
    def test_source_control(self):
        """Issues #296, #297: a project's Source control tab: Git missing says how to get it; set up after its ignore
        rules are shown; changes chosen, staged and committed; the history, a commit's files and a file's changes."""
        from hoard.vpm import git
        conf = self.tmp / "gitconfig"
        conf.write_text("[user]\n\tname = Kitsu\n\temail = kitsu@example.com\n[init]\n\tdefaultBranch = main\n")
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(conf), "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        page = self.page
        pj_details(page, "Rusk Avatar").locator(".actions [data-pj=manage]").click()
        tab = page.locator(".pj-subs [data-sub=git]")
        self.assertEqual(tab.inner_text(), "Source control")
        with mock.patch.object(git, "_candidates", lambda: []):
            git.find(again=True)
            tab.click()
            page.locator(".pj-git-none h4", has_text="Git isn't installed").wait_for()
            self.assertEqual(page.locator(".pj-git-none a").get_attribute("href"), "https://git-scm.com/downloads")
        page.click("[data-pj=gitagain]")
        page.locator(".pj-git-none h4", has_text="Not set up").wait_for()
        page.click("[data-pj=gitsetup]")
        dlg = page.locator("dialog.pj-dlg", has_text="Set up Git for Rusk Avatar?")
        dlg.wait_for()
        self.assertIn(".gitignore", dlg.inner_text())
        self.assertIn("/[Ll]ibrary/", dlg.locator(".pj-plan").first.inner_text())
        self.assertIn("Assets", dlg.locator(".pj-plan-cols").inner_text())
        dlg.locator("button[value=yes]").click()
        page.locator(".pj-git-files li").first.wait_for()
        self.assertTrue((self.tmp / "Unity" / "Rusk Avatar" / ".git").is_dir())
        self.assertTrue(page.locator("[data-pj=gitcommit]").is_disabled(), "nothing staged yet")
        page.check("[data-gitall]")
        page.click("[data-pj=gitstage]")
        page.wait_for_function("() => PJG.data && PJG.data.counts && PJG.data.counts.staged > 0")
        page.fill("#pjGitMsg", "First: the avatar")
        page.click("[data-pj=gitcommit]")
        page.locator(".toast", has_text="Committed: First: the avatar").wait_for()
        page.locator(".pj-git-files + *, .pj-git .none", has_text="No changes").first.wait_for()
        self.assertIn("Last commit: First: the avatar", page.locator(".pj-git-head").inner_text())
        # a change, and its lines; the history, and a commit's files
        (self.tmp / "Unity" / "Rusk Avatar" / "Packages" / "manifest.json").write_text('{"dependencies": {"x": "1"}}')
        page.click("[data-pj=gitreload]")
        page.locator(".pj-git-files li", has_text="Packages/manifest.json").wait_for()
        page.locator(".pj-git-files li", has_text="Packages/manifest.json").locator("[data-pj=gitdiff]").click()
        page.locator(".pj-diff-text .add", has_text='"x": "1"').wait_for()
        page.click("[data-pj=githistory]")
        page.locator(".pj-git-log li", has_text="First: the avatar").locator("[data-pj=gitref]").click()
        page.locator(".pj-git-cfiles li", has_text="Packages/manifest.json").wait_for()
        # its details say so
        page.click("[data-pj=back]")
        page.locator("#pjFind").wait_for()
        page.wait_for_timeout(300)   # (the list drawn, with its details still open)
        pj_details(page, "Rusk Avatar")
        # (the details read again: until then they can say what was read before Git was set up)
        pj_details(page, "Rusk Avatar").locator(".pj-facts dd", has_text="main · 1 change").wait_for()
        facts = dict(zip(*(pj_details(page, "Rusk Avatar").locator(f".pj-facts {t}").all_inner_texts() for t in ("dt", "dd"))))
        self.assertEqual(facts["Source control"], "main · 1 change")

    def test_rename_a_project(self):
        """Issue #290: Rename... in a project's details renames its folder, and its details stay open under the new
        name; a name that can't be used is refused, and nothing changes."""
        page = self.page
        panel = pj_details(page, "Rusk Avatar")
        self.assertEqual(panel.locator(".marks").first.locator("button").all_inner_texts(),
                         ["Make it a favourite", "Back up...", "Rename...", "Take off the list"])
        panel.locator("[data-pj=rename]").click()
        page.locator("dialog[open] #askName").wait_for()
        self.assertEqual(page.input_value("dialog[open] #askName"), "Rusk Avatar")
        page.fill("dialog[open] #askName", "CON")
        page.keyboard.press("Enter")
        page.locator(".toast", has_text="can't be used as a folder name").wait_for()
        self.assertTrue((self.tmp / "Unity" / "Rusk Avatar").is_dir())
        pj_details(page, "Rusk Avatar").locator("[data-pj=rename]").click()
        page.fill("dialog[open] #askName", "Rusk Avatar 2")
        page.keyboard.press("Enter")
        page.locator(".toast", has_text="Renamed it Rusk Avatar 2.").wait_for()
        page.locator("#projectsBody .pj-detail .pj-d-name", has_text="Rusk Avatar 2").wait_for()
        self.assertTrue((self.tmp / "Unity" / "Rusk Avatar 2").is_dir())
        self.assertFalse((self.tmp / "Unity" / "Rusk Avatar").exists())
        self.assertIn("Rusk Avatar 2", page.locator(".pj-row b").all_inner_texts())

    def test_projects_as_tiles_with_folder_tiles(self):
        """Issue #250: projects as tiles (remembered), and a folder of them as one folder tile that opens to them."""
        page = self.page
        pj_folder(page, "Rusk Avatar", "Avatars WIP")
        page.locator("#projectsBody .pj-folders").wait_for()
        page.click("[data-pj=layout][data-v=tiles]")
        page.locator(".pj-tiles").wait_for()
        self.assertEqual(page.evaluate("UI.pj_layout"), "tiles")
        folder = page.locator(".pj-folder-tile")
        self.assertEqual(folder.locator(".nm-t").inner_text(), "Avatars WIP")
        self.assertIn("1 project", folder.inner_text())
        self.assertEqual(page.locator(".pj-tile:not(.pj-folder-tile) .nm-t").all_inner_texts(), ["Old World"], "its project inside it")
        for art in (".pj-folder-tile .pj-tile-art", ".pj-tile:not(.pj-folder-tile) .pj-tile-art"):   # twice as wide as tall
            box = page.locator(art).first.bounding_box()
            self.assertAlmostEqual(box["width"] / box["height"], 2, delta=0.05)
        page.click("[data-pj=undetail]")   # (its details were open from before: choosing it again would put them away)
        folder.click()
        page.wait_for_function("() => [...document.querySelectorAll('.pj-tile .nm-t')].map(e => e.textContent).join() === 'Rusk Avatar'")
        page.locator(".pj-tile", has_text="Rusk Avatar").click()
        page.locator(".pj-detail", has_text="Rusk Avatar").wait_for()
        page.fill("#pjFind", "zzz")
        self.assertEqual(page.locator(".pj-tile:visible").count(), 0, "Find a project looks at tiles too")
        page.fill("#pjFind", "")
        self.assertEqual(server.ui_settings({"ui": {"pj_layout": "tiles"}})["pj_layout"], "tiles")
        self.assertNotIn("pj_layout", server.ui_settings({"ui": {"pj_layout": "grid"}}))

    def test_whats_new_in_a_project(self):
        """Issue #253: a project's row says how many of its packages have newer versions, and, apart from that, how many
        products from your library in it have updates; its details lead to each."""
        page = self.page
        row = page.locator(".pj-row", has_text="Rusk Avatar")
        page.wait_for_function("() => PJ.updates !== null")
        packages = page.evaluate("PJ.updates[PJ.data.projects.find(p => p.name === 'Rusk Avatar').path].packages")
        self.assertGreater(packages, 0)
        self.assertEqual(row.locator(".pj-up.pkg").inner_text(), f"{packages} package update" + ("s" if packages > 1 else ""))
        self.assertEqual(row.locator(".pj-up.prod").count(), 0)
        report = page.evaluate("""() => { const p = PJ.data.projects.find(p => p.name === 'Rusk Avatar');
          let r = PJ.reports.find(r => r.path && pjSame(r.path, p.path));   // (what Hoard for Unity reported of it)
          if (!r) { r = { id: 'r1', name: p.name, path: p.path }; PJ.reports.push(r); }
          r.assets = [{ update: true }, { update: true }, { update: false }];
          drawProjects(); return r.id; }""")
        self.assertEqual(row.locator(".pj-up.prod").inner_text(), "2 products updated")
        pkg, prod = [row.locator(c).evaluate("e => [getComputedStyle(e).backgroundColor, getComputedStyle(e).boxShadow]")
                     for c in (".pj-up.pkg", ".pj-up.prod")]
        self.assertNotEqual(pkg, prod, "each its own way")
        panel = pj_details(page, "Rusk Avatar")
        panel.locator(".pj-up-go", has_text="2 products in it have updates").click()
        page.wait_for_function("id => PJ.view === 'report' && PJ.report && PJ.report.id === id", arg=report)
        page.evaluate("PJ.view = 'list'; drawProjects()")
        pj_details(page, "Rusk Avatar").locator(".pj-up-go", has_text="newer version").click()
        page.wait_for_function("() => PJ.view === 'project'")

    def test_a_tag_being_typed_stays_when_the_list_is_drawn_again(self):
        """The list is drawn again as its updates and a project's details come in, which emptied a tag being typed in
        the details (and, on a slow computer, the next one typed just after adding one)."""
        page = self.page
        pj_details(page, "Rusk Avatar")
        page.fill("#pjTagInput", "half-typed")
        page.evaluate("drawProjects()")
        self.assertEqual(page.input_value("#pjTagInput"), "half-typed")
        self.assertTrue(page.evaluate("document.activeElement.id === 'pjTagInput'"), "where you were typing")
        # and an empty box keeps where you are, so what's typed next goes in it
        page.evaluate("$('#pjTagInput').value = ''; drawProjects()")
        self.assertTrue(page.evaluate("document.activeElement.id === 'pjTagInput'"), "still there")
        page.keyboard.type("half-typed")
        page.press("#pjTagInput", "Enter")
        page.wait_for_function("() => PJ.data.projects.find(p => p.name === 'Rusk Avatar').tags.includes('half-typed') && !PJ.busy")
        # Enter while a change is still being saved: the tag is added once it's done, not dropped
        page.fill("#pjTagInput", "while-busy")
        page.evaluate("PJ.busy = true; setTimeout(() => { PJ.busy = false; }, 600)")
        page.press("#pjTagInput", "Enter")
        page.wait_for_function("() => PJ.data.projects.find(p => p.name === 'Rusk Avatar').tags.includes('while-busy') && !PJ.busy")
        self.assertEqual(page.input_value("#pjTagInput"), "", "added, so not kept as typed")

    def test_folders_and_tags(self):
        """Issue #190: Hoard's own folders and tags for the projects on the list (the Creator Companion and ALCOM have
        only a favourite): one folder shown at a time, a project's folder and tags changed in its details, and each tag
        shows those with it."""
        page = self.page
        pj_folder(page, "Rusk Avatar", "Avatars WIP")
        tags = page.locator(".pj-detail .tagpill .chip")
        for typed in ("Quest", "poiyomi", "quest"):   # (Enter adds one; a tag it has already isn't added twice)
            page.fill("#pjTagInput", typed)
            page.press("#pjTagInput", "Enter")
            pj_saved(page, "n => PJ.data.projects.find(p => p.name === 'Rusk Avatar').tags.length === n && !PJ.busy",
                     1 if typed == "Quest" else 2)   # (saved: one action at a time, as you'd see it)
        bar = page.locator("#projectsBody .pj-folders")
        bar.wait_for()
        self.assertEqual(bar.locator(".chip").all_inner_texts(), ["All projects2", "Avatars WIP1", "Not in a folder1"])
        rusk = page.locator(".pj-row", has_text="Rusk Avatar")
        self.assertEqual(tags.all_inner_texts(), ["quest", "poiyomi"], "as tags are kept")
        self.assertEqual(page.locator("#pjDFolder").input_value(), "Avatars WIP")
        self.assertIn("Avatars WIP", rusk.locator(".pj-what").inner_text())
        bar.locator(".chip", has_text="Avatars WIP").click()
        page.wait_for_function("() => document.querySelectorAll('.pj-items .pj-list .pj-row').length === 1")
        self.assertEqual(page.locator(".pj-list").first.locator(".pj-row b").all_inner_texts(), ["Rusk Avatar"])
        self.assertNotIn("Avatars WIP", rusk.locator(".pj-what").inner_text(), "not said again in its own folder")
        bar.locator(".chip", has_text="Not in a folder").click()
        page.wait_for_function("() => document.querySelector('.pj-items .pj-list .pj-row b').textContent === 'Old World'")
        bar.locator(".chip", has_text="All projects").click()
        # a tag: the projects that have it
        tags.filter(has_text="poiyomi").click()
        page.wait_for_function("() => document.querySelectorAll('.pj-items .pj-list .pj-row').length === 1")
        self.assertEqual(bar.locator(".chip[aria-pressed=true]").all_inner_texts(), ["All projects2", "poiyomi ×"])
        page.fill("#pjFind", "wip")   # Find a project looks at its folder and tags too
        self.assertEqual(page.locator(".pj-list").first.locator(".pj-row:visible").count(), 1)
        page.fill("#pjFind", "")
        bar.locator(".chip", has_text="poiyomi ×").click()
        page.wait_for_function("() => document.querySelectorAll('.pj-items .pj-list .pj-row').length === 2")
        # emptied: out of the folder, and with no folder left, no folders to choose from; its tags taken off one by one
        pj_folder(page, "Rusk Avatar", "")
        page.wait_for_function("() => !document.querySelector('#projectsBody .pj-folders')")
        for left in (1, 0):
            page.locator(".pj-detail .tagpill .untag").first.click()
            pj_saved(page, "n => PJ.data.projects.find(p => p.name === 'Rusk Avatar').tags.length === n", left)
        self.assertEqual(tags.count(), 0)
        self.assertIn("No tags yet", page.locator(".pj-detail").inner_text())

    def test_choosing_a_products_packages_in_steps(self):
        """Issue #199: a product with several packages: first which of them (each with its size, a variant marked,
        Select all or none), then, last, the packages it needs; a long package name breaks at its dots."""
        page = self.page
        page.evaluate("""() => { window.__got = undefined; pjChooseContents({ name: "Fox Outfits", key: "booth:foxoutfits", already: [],
          contents: [{ kind: "unitypackage", file: "Fox.zip", member: "Fox/Fox_PC.unitypackage", label: "Fox_PC.unitypackage", size: 2500000 },
                     { kind: "unitypackage", file: "Fox.zip", member: "Fox/Fox_Quest.unitypackage", label: "Fox_Quest.unitypackage", size: 1200000 },
                     { kind: "vpm", file: "Fox.zip", member: "Fox/tool.zip", label: "Fox Tool", size: 40000 }],
          suggested: [{ package: "com.vrcfury.vrcfury", repo: "https://vcc.vrcfury.com", repo_added: false }] }).then(g => window.__got = g); }""")
        dlg = page.locator("dialog.pj-dlg[open]")
        step1, step2 = dlg.locator("[data-step='1']"), dlg.locator("[data-step='2']")
        self.assertIn("Step 1 of 2: its packages", step1.inner_text())
        self.assertTrue(step2.is_hidden(), "what it needs comes last")
        rows = step1.locator(".pj-contents li")
        self.assertEqual(rows.count(), 3)
        self.assertEqual([rows.nth(n).locator(".pj-tag").all_inner_texts() for n in range(3)], [["PC"], ["Quest"], []])
        self.assertIn("Unity package · 2.4 MB", rows.nth(0).inner_text())
        self.assertEqual([rows.nth(n).locator("input").is_checked() for n in range(3)], [False, False, True],
                         "one of the variants to choose")
        nxt = step1.locator(".primary")
        step1.locator("[data-all='0']").click()
        self.assertTrue(nxt.is_disabled(), "nothing ticked: nothing to go on with")
        step1.locator("[data-all='1']").click()
        rows.nth(1).locator("input").uncheck()
        nxt.click()
        self.assertTrue(step1.is_hidden())
        self.assertIn("Step 2 of 2: what it needs", step2.inner_text())
        self.assertIn("com.<wbr>vrcfury.<wbr>vrcfury", step2.locator(".pj-picklist").inner_html())
        step2.locator("[data-step-go='1']").click()   # Back: the choice as it was
        self.assertFalse(rows.nth(1).locator("input").is_checked())
        nxt.click()
        step2.locator(".primary").click()
        page.wait_for_function("() => window.__got !== undefined")
        got = page.evaluate("window.__got")
        self.assertEqual([x["label"] for x in got["picks"]], ["Fox_PC.unitypackage", "Fox Tool"])
        self.assertEqual([x["package"] for x in got["suggested"]], ["com.vrcfury.vrcfury"])

    SAMPLE_SPLASH = """window.__splash = 0;   // how visible Projects' splash got, sampled while it's on show
        setInterval(() => { const e = document.getElementById("pjSplash");
                            if (e && !e.hidden) window.__splash = Math.max(window.__splash, +getComputedStyle(e).opacity); }, 25);"""

    def test_the_splash(self):
        """The logo shows over Projects while it first reads your projects, as the page shows it while it reads your
        library: the first time in a window straight away and for a moment, later only when reading takes a while;
        it goes even when reading fails, and it doesn't come back once Projects has been read."""
        page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(self.SAMPLE_SPLASH)
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        logo = page.locator("#pjSplash")
        self.assertTrue(logo.is_hidden(), "not before Projects is opened")
        page.click("#projectsTab")
        began = time.monotonic()
        self.assertIn("first", logo.get_attribute("class") or "")
        self.assertIn("Opening your projects", logo.inner_text())
        page.locator(".pj-row").first.wait_for(state="attached")   # drawn under it
        logo.wait_for(state="detached")
        self.assertGreater(time.monotonic() - began, 1.0, "on show for a moment, not a flicker")
        self.assertEqual(page.evaluate("window.__splash"), 1)
        box = page.locator("#projectsWin .win-bar").bounding_box()
        self.assertGreater(box["height"], 0, "Projects' own bar, with its Close, stays above it")
        page.locator(".pj-open").first.click()   # nothing in the way once it's gone
        page.locator(".pj-detail .actions [data-pj=manage]").click()
        page.locator("[data-pj=back]").first.wait_for()

        # the other page, in the same window: not straight away, and only once reading takes a while
        page.goto(f"{self.srv.url}downloads")
        page.click("#projectsTab")
        self.assertNotIn("first", logo.get_attribute("class") or "")
        page.locator(".pj-row").first.wait_for()
        logo.wait_for(state="detached")

        def slow(route):
            time.sleep(1.0)
            route.continue_()
        page.route("**/api/vpm*", slow)
        page.goto(self.srv.url)
        page.click("#projectsTab")
        logo.wait_for(state="detached", timeout=10000)
        self.assertEqual(page.evaluate("window.__splash"), 1, "shown while reading took a while")
        page.unroute("**/api/vpm*")
        page.click("#projectsTab")   # closed and opened again: read again, with no splash
        page.click("#projectsTab")
        page.locator(".pj-row").first.wait_for()
        self.assertEqual(logo.count(), 0)
        page.close()

        page = self.browser.new_page()   # a new window whose projects can't be read
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        page.route("**/api/vpm*", lambda route: route.abort())
        page.click("#projectsTab")
        page.locator("#pjSplash").wait_for(state="detached", timeout=10000)
        self.assertIn("Projects couldn't be read just now.", page.locator("#projectsBody").inner_text())
        page.close()
        self.assertEqual(errors, [])

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
        self.assertEqual(page.locator(".pj-tabs .pj-tab").all_inner_texts(), ["Projects", "Repositories", "Backups", "Unity and folders", "Logs"])
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
        pj_details(page, "Picked Project").locator(".actions [data-pj=manage]").click()
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
        pj_details(page, "Rusk Avatar").locator(".actions [data-pj=manage]").click()
        page.wait_for_function("() => PJ.view === 'project' && !PJ.busy")   # (a click while it's opening is ignored)
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
        pj_details(page, "Rusk Avatar").locator(".actions [data-pj=manage]").click()
        page.locator(".pj-pk").wait_for()
        text = page.locator("#projectsBody").inner_text()
        self.assertIn("Some packages aren't installed the way the project says.", text)
        self.assertIn("Unity 2022.3.22f1 isn't installed", text)
        # its packages' columns, named; and where each comes from
        self.assertEqual(page.locator(".pj-pk thead th").all_inner_texts(), ["Package", "Installed", "Update", "Comes from", "Remove"])
        self.assertEqual(page.locator(".pj-pk tr[data-name='com.vrchat.avatars'] td.from").inner_text(), "Official")
        # its tabs: Packages, Add packages, From your library, and what Hoard for Unity reported of it
        tabs = page.locator(".pj-subs .pj-tab")
        self.assertEqual(tabs.evaluate_all("l => l.map(b => b.dataset.sub)"), ["packages", "add", "library", "report", "git"])
        page.click(".pj-subs [data-sub=report]")
        page.locator(".proj", has_text="What Hoard for Unity found in it").wait_for()
        # what it found: as their library tiles, with how each is in it; choosing one shows it in the library
        tile = page.locator(".proj .pj-tile", has_text="Rusk")
        self.assertIn("In the project", tile.inner_text())
        self.assertEqual(tile.locator(".art img, .art .ph").count(), 1)
        tile.locator("button.ext-main").click()
        page.locator("#detail.open", has_text="Rusk").wait_for()
        self.assertTrue(page.locator("#projectsWin").is_hidden())
        page.keyboard.press("Escape")
        page.click("#projectsTab")
        page.locator(".pj-subs [data-sub=report]").wait_for()
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
        # a product from the library: chosen in Downloads (from the Library page, it goes there), then back to the
        # new project as it was, with it in
        self.assertEqual(page.locator("[data-pj=addprod]").inner_text(), "Add Assets")
        page.click("[data-pj=addprod]")
        page.wait_for_url("**/downloads*")
        page.locator("#bulk [data-main]", has_text="Add to project").wait_for()
        self.assertIn("for CON", page.locator("#bulkCount").inner_text())
        page.locator(".slot", has_text="Rusk").click()
        page.locator("#bulk [data-main]").click()
        page.locator(".pj-pre", has_text="rusk.unitypackage").wait_for()
        self.assertEqual(page.input_value("#pjName"), "CON")
        self.assertTrue(page.locator("#bulk").is_hidden(), "and choosing is over")
        # Hoard for Unity is in a new project unless you leave it out
        self.assertIn("Hoard for Unity", page.locator(".pj-chips").inner_text())
        # Add packages: a view of its own (not a window over the page), and back to the new project
        page.click("[data-pj=addpkg]")
        # in groups by the repository they come from, each folding away
        group = page.locator(".pj-repo", has_text="Official")
        self.assertEqual(" ".join(group.locator("summary").inner_text().split()), "Official 2")
        self.assertTrue(group.evaluate("d => d.open"))
        group.locator("summary").click()
        self.assertFalse(group.evaluate("d => d.open"))
        page.fill("#pjPkFind", "avatars")   # what you look for is shown, wherever it is
        page.wait_for_function("() => document.querySelector('.pj-repo').open")
        self.assertEqual(page.locator(".pj-addlist li:visible").count(), 1)
        page.fill("#pjPkFind", "nothing like it")
        self.assertTrue(group.is_hidden(), "a repository with nothing found is left out")
        page.fill("#pjPkFind", "")
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

    def test_put_in_products_from_your_library(self):
        """A project's Add Assets (issue #282) opens Downloads (from the Library page, it goes there) in Select mode for
        that project, where all there is to do is Add to project or Cancel; both go back to it. With nothing in it
        yet, its tab reads as an empty Library does (issue #283)."""
        page = self.page
        ran = []
        self.srv.project_jobs.project_runner = lambda what: ran.append(what) or "Done."
        pj_details(page, "Rusk Avatar").locator(".actions [data-pj=manage]").click()
        page.click("[data-pj=sub][data-sub=library]")
        empty = page.locator("#projectsWin .pj-empty")
        self.assertEqual(empty.locator("h2").inner_text(), "Nothing from your library in it yet")
        self.assertIn("Hoard puts them in the project", empty.inner_text())
        self.assertEqual(empty.locator("button.primary").inner_text(), "Add Assets")
        page.click("[data-pj=addprod]")
        page.wait_for_url("**/downloads*")
        bar = page.locator("#bulk")
        bar.locator("[data-main]").wait_for()
        self.assertTrue(page.locator("#projectsWin").is_hidden())
        self.assertEqual(bar.locator("button:visible").all_inner_texts(), ["Add to project", "Cancel"], "nothing else to do")
        self.assertTrue(page.locator("#selectBtn").is_hidden(), "not even Select's Done")
        self.assertTrue(bar.locator("[data-main]").is_disabled(), "until something's chosen")
        self.assertEqual(bar.locator("#bulkCount").inner_text(), "0 selected for Rusk Avatar")
        page.locator(".slot", has_text="Rusk").click()   # (a tap ticks: Select mode)
        self.assertEqual(bar.locator("#bulkCount").inner_text(), "1 selected for Rusk Avatar")
        self.assertEqual(page.locator("#detail.open").count(), 0)
        # right-click: the same, and nothing more
        page.locator(".slot", has_text="Rusk").click(button="right")
        self.assertEqual(page.locator(".selmenu [role=menuitem]").all_inner_texts(), ["Add to project"])
        page.keyboard.press("Escape")
        # Cancel: back to the project, as it was
        bar.locator("[data-pickcancel]").click()
        page.locator("#projectsWin .pj-h", has_text="Rusk Avatar").wait_for()
        self.assertEqual(page.locator(".pj-subs [aria-current=page]").inner_text(), "From your library")
        self.assertTrue(bar.is_hidden())
        self.assertEqual(page.locator("#selectBtn").inner_text(), "Select", "Select mode is over")
        self.assertTrue(page.locator("#selectBtn").is_visible())
        # again, on the Downloads page: chosen, shown before it goes in, and put in as a task
        page.click("[data-pj=addprod]")
        bar.locator("[data-main]").wait_for()
        page.locator(".slot", has_text="Rusk").click()
        bar.locator("[data-main]").click()
        sure = page.locator("dialog.pj-dlg", has_text="Put these in Rusk Avatar?")
        self.assertIn("rusk.unitypackage", sure.inner_text())
        sure.locator("button[value=yes]").click()
        page.locator("#projectsWin .pj-h", has_text="Rusk Avatar").wait_for()
        for _ in range(100):
            if ran:
                break
            page.wait_for_timeout(100)
        self.assertEqual((ran[0]["op"], ran[0]["name"]), ("preload", "Rusk Avatar"))
        self.assertEqual([x["file"] for x in ran[0]["picks"]], ["rusk.unitypackage"])
        # what went in, as their library tiles: each product once, with its files and when
        from hoard.vpm import listing
        key = page.evaluate("T.all().find(a => a.name === 'Rusk').tag_key")
        project = self.tmp / "Unity" / "Rusk Avatar"
        listing.add_preloaded(str(project), [{"tag_key": key, "name": "Rusk", "file": "rusk.unitypackage", "label": "rusk.unitypackage",
                                              "added": ["Assets/Rusk"]},
                                             {"tag_key": key, "name": "Rusk", "file": "rusk-quest.unitypackage", "label": "rusk-quest.unitypackage"}])
        page.evaluate("loadProjects()")
        tile = page.locator(".pj-part .pj-tile", has_text="Rusk")
        tile.wait_for()
        self.assertEqual(page.locator(".pj-part .pj-tile").count(), 1, "one tile a product")
        self.assertIn("2 packages · just now", tile.inner_text())
        self.assertEqual(tile.locator(".cr").inner_text(), page.evaluate("T.all().find(a => a.name === 'Rusk').creator"),
                         "the Library's own tile (#198): its creator as the Library shows it")
        tile.locator(".pj-files summary").click()   # its packages, in its details
        self.assertIn("rusk.unitypackage", tile.inner_text())
        self.assertIn("rusk-quest.unitypackage", tile.inner_text())
        self.assertEqual(tile.locator(".pj-file", has_text="rusk.unitypackage").first.get_attribute("title"), "Added: Assets/Rusk")
        # Escape, while choosing, goes back too
        page.click("[data-pj=addprod]")
        bar.locator("[data-main]").wait_for()
        page.keyboard.press("Escape")
        page.locator("#projectsWin .pj-h", has_text="Rusk Avatar").wait_for()
        self.assertTrue(bar.is_hidden())

    def test_what_products_need_as_the_project_stands(self):
        """Put in a project: what the products need that the project has already isn't offered again, only said; one a
        repository you have gives already says so, and that repository isn't added again; only one you don't have is."""
        page = self.page
        asked, added = [], []

        def product(route):   # (the sample's Rusk, as if it needed these)
            asked.append(route.request.url)
            reply = route.fetch()
            data = reply.json()
            data["suggested"] = [
                {"package": "com.vrchat.avatars", "repo": None, "repo_added": True, "in_repo": "Official", "in_project": "3.7.0"},
                {"package": "com.vrcfury.vrcfury", "repo": "https://vcc.vrcfury.com", "repo_added": True, "in_repo": "VRCFury Repo", "in_project": None},
                {"package": "nadena.dev.modular-avatar", "repo": "https://vpm.nadena.dev/vpm.json", "repo_added": False, "in_repo": None, "in_project": None}]
            route.fulfill(response=reply, json=data)
        page.route("**/api/vpm/product*", product)
        page.route("**/api/vpm/repos/add", lambda route: added.append(json.loads(route.request.post_data)["url"]) or route.fulfill(json={"ok": True}))
        page.route("**/api/vpm/preview", lambda route: route.fulfill(status=400, json={"error": "(not in the sample)"}))
        self.srv.project_jobs.project_runner = lambda what: "Done."
        pj_details(page, "Rusk Avatar").locator(".actions [data-pj=manage]").click()
        page.click("[data-pj=sub][data-sub=library]")
        page.click("[data-pj=addprod]")
        page.wait_for_url("**/downloads*")
        page.locator("#bulk [data-main]").wait_for()
        page.locator(".slot", has_text="Rusk").click()
        page.locator("#bulk [data-main]").click()
        sure = page.locator("dialog.pj-dlg", has_text="Put these in Rusk Avatar?")
        sure.wait_for()
        text = sure.inner_text()
        self.assertIn("path=", asked[0], "asked as the project stands")
        self.assertIn("Already in the project: com.vrchat.avatars 3.7.0.", text)
        self.assertEqual(sure.locator("input[data-sugg]").count(), 2, "not offered again")
        self.assertIn("(from VRCFury Repo)", text)
        self.assertNotIn("adds the repository https://vcc.vrcfury.com", text)
        self.assertIn("adds the repository https://vpm.nadena.dev/vpm.json", text)
        sure.locator("button[value=yes]").click()
        page.locator("#projectsWin .pj-h", has_text="Rusk Avatar").wait_for()
        self.assertEqual(added, ["https://vpm.nadena.dev/vpm.json"], "only the repository you don't have is added")

    def test_logs(self):
        """Projects' Logs, as ALCOM's and the Creator Companion's: what Hoard did and what went wrong, newest last,
        each with its time and level; found by its words and by level (which levels is kept); new entries come in
        while it's open; and Open logs folder opens the folder they're written to."""
        from hoard.vpm import logbook
        page = self.page
        book = logbook.Logbook(self.tmp / "logs")
        patch = mock.patch.object(logbook, "book", book)
        patch.start()
        self.addCleanup(patch.stop)
        opened = []
        reveal = mock.patch.object(server, "reveal", lambda p: opened.append(p) or str(p))
        reveal.start()
        self.addCleanup(reveal.stop)
        page.click(".pj-tabs [data-pj=logs]")
        page.locator("#pjLogNone", has_text="Nothing has been logged since Hoard started.").wait_for()
        book.add("info", "Projects: Make Rusk Avatar")
        book.add("warning", "Couldn't fetch Extra: it's gone")
        page.evaluate("loadProjects()")   # (as when a task ends: drawn again, still reading what's new)
        rows = page.locator("#pjLogRows tr")
        rows.nth(1).wait_for()
        # something that couldn't be done, from Projects itself
        page.evaluate("apiPost('/api/vpm/open', {path: '/not/a/project'})")
        page.locator("#pjLogRows tr", has_text="Open in Unity: That project isn't on the list any more.").wait_for()
        self.assertEqual(page.locator("#pjLogRows td.lv").all_inner_texts(), ["Info", "Warning", "Error"])
        self.assertEqual(page.locator(".pj-tabs [aria-current=page]").inner_text(), "Logs")
        colour = lambda n: rows.nth(n).locator("td.m").evaluate("e => getComputedStyle(e).color")  # noqa: E731
        self.assertEqual(len({colour(0), colour(1), colour(2)}), 3, "warnings and errors in their own colours")
        box = page.locator("#pjLogBox")
        self.assertTrue(box.evaluate("e => e.scrollTop + e.clientHeight >= e.scrollHeight - 2"), "the newest in view")
        # by level, and by words
        page.locator("[data-pjlevel=info]").uncheck()
        self.assertEqual(page.locator("#pjLogRows td.lv").all_inner_texts(), ["Warning", "Error"])
        page.fill("#pjLogFind", "UNITY list")
        self.assertEqual(rows.count(), 1)
        page.fill("#pjLogFind", "nothing like it")
        self.assertTrue(page.locator("#pjLogNone", has_text="Nothing in the log matches.").is_visible())
        page.fill("#pjLogFind", "")
        page.reload()   # which levels is kept
        page.click("#projectsTab")
        page.click(".pj-tabs [data-pj=logs]")
        rows.nth(1).wait_for()
        self.assertFalse(page.locator("[data-pjlevel=info]").is_checked())
        self.assertEqual(rows.count(), 2)
        page.locator("[data-pjlevel=info]").check()
        # Follow new entries: on, the newest comes into view; off, it's left where it is
        follow = page.locator("[data-pj=logfollow]")
        self.assertEqual(follow.get_attribute("aria-pressed"), "true")
        follow.click()
        self.assertEqual(follow.get_attribute("aria-pressed"), "false")
        book.add("info", "Took Old World off the list")
        page.locator("#pjLogRows tr", has_text="Took Old World off the list").wait_for()
        page.click("[data-pj=logfolder]")
        page.wait_for_function("() => document.querySelector('#toast').textContent.includes('Opened the logs folder')")
        self.assertEqual(opened[-1].name, "logs")

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

    def test_a_new_project_with_a_set(self):
        """Issue #195: a set's right-click menu, and its own page, offer New project with this set..., which opens New
        project with what's downloaded of the set in it. Issue #208: a set's page doesn't offer Add products by link
        (a wishlist's does: test_wishlists)."""
        page = self.page
        page.keyboard.press("Escape")
        page.locator("#projectsWin").wait_for(state="hidden")
        post = "([u, b]) => api(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(r => r.json())"
        key = page.evaluate("DATA.items.find(a => a.name === 'Rusk').tag_key")
        page.evaluate(post, ["/api/sets", {"action": "create", "name": "Rusk outfit", "items": [key]}])
        page.evaluate("load()")
        page.click("nav.apptabs a[href='/#store=Sets']")
        tile = page.locator("#setView .settile", has_text="Rusk outfit")
        tile.click()
        page.locator('[data-setx="project"]').wait_for()
        self.assertEqual(page.locator('[data-setx="addlinks"]').count(), 0, "a set: no Add products by link")
        page.click('[data-setx="back"]')
        tile.click(button="right")
        page.locator(".selmenu [role=menuitem]", has_text="New project with this set...").click()
        page.locator("#projectsWin #pjName").wait_for()
        self.assertIn("rusk.unitypackage", page.locator("#projectsWin .pj-pre").inner_text(), "the set's product, in it")


if __name__ == "__main__":
    unittest.main()
