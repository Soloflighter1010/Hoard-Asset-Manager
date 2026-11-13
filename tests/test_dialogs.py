"""Hoard's pop-ups (ui/Dialog.svelte, through shared.js's ask, askName, askFolder and the set picker): one look for
all of them, a card like a product's details, its question as its title; and what each answers."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

from tests.isolation import IsolatedTestCase

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hoard import config, library, server  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _p.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

# What a pop-up opened from the page answers, kept on the page for the test to read when it has closed.
OPEN = "code => { window.answer = undefined; Promise.resolve(eval(code)).then(a => { window.answer = a; }); }"
ANSWERED = "() => window.answer !== undefined"


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Popups(IsolatedTestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": cls.tmp.name, "setup_done": True},
                                   lan=False)
        cls.ja = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": cls.tmp.name, "setup_done": True,
                                                     "display": {"language": "ja"}}, lan=False)
        for srv in (cls.srv, cls.ja):
            with srv.lib.lock:   # in memory only
                srv.lib.data["items"] = [library.item("booth", "111", name="Rusk", creator="Kitsu Studio"),
                                         library.item("booth", "112", name="Winter Hoodie", creator="Kitsu Studio")]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        for srv in (cls.srv, cls.ja):
            srv.shutdown()
            srv.server_close()
        cls.tmp.cleanup()

    def open(self, srv=None):
        """Hoard's page (in English, or as srv has it), its products drawn, noting any error on it."""
        page = self.browser.new_page()
        self.addCleanup(page.close)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto((srv or self.srv).entry_url())
        page.wait_for_selector("#grid .slot[data-key]")
        return page

    def answer(self, page):
        """What the pop-up answered, once it has closed; and it's gone from the page."""
        page.wait_for_function(ANSWERED)
        page.wait_for_function("() => !document.querySelector('dialog.hd')")
        return page.evaluate("window.answer")

    def test_a_question_is_titled_by_itself(self):
        page = self.open()
        page.evaluate(OPEN, "ask(\"Delete 2 backups (1.3 GB)? They can't be restored.\", tr('Delete'), true)")
        d = page.locator("#askDialog[open]")
        self.assertEqual(d.locator("h2").inner_text(), "Delete 2 backups (1.3 GB)?")
        self.assertEqual(d.locator(".hd-detail").inner_text(), "They can't be restored.")
        said = d.locator("#askText").inner_text()   # (what the pages and their tests read of a question)
        self.assertTrue("Delete 2 backups (1.3 GB)?" in said and "They can't be restored." in said, said)
        self.assertTrue(page.evaluate("document.querySelector('#askDialog').matches(':modal')"), "over the page")
        self.assertEqual(page.evaluate("document.activeElement.textContent"), "Cancel", "Enter never deletes by accident")
        self.assertIn("danger", d.locator("button[value=yes]").get_attribute("class"))
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('#askDialog')).backgroundColor"),
                         page.evaluate("(() => { const b = document.createElement('b'); b.style.color = 'var(--ledge)'; document.body.append(b);"
                                       " const c = getComputedStyle(b).color; b.remove(); return c; })()"),
                         "the details panel's ground")
        page.keyboard.press("Escape")
        self.assertIs(self.answer(page), False)
        self.assertEqual(self.errors, [])

    def test_its_answers(self):
        page = self.open()
        for how, said in (("button[value=yes]", True), ("button[value=no]", False), (".hd-x", False), ("outside", False)):
            page.evaluate(OPEN, "ask('Clear the list of finished tasks?')")
            d = page.locator("#askDialog[open]")
            d.wait_for()
            if how == "outside":
                page.mouse.click(5, 5)
            else:
                d.locator(how).click()
            self.assertIs(self.answer(page), said, how)
        page.evaluate(OPEN, "ask('Nothing new to bring in from KonoAsset.', 'OK', false, '')")
        d = page.locator("#askDialog[open]")
        self.assertEqual(d.locator("footer button").all_inner_texts(), ["OK"], "something to read, with one button")
        self.assertEqual(page.evaluate("document.activeElement.textContent"), "OK")
        page.keyboard.press("Enter")
        self.assertIs(self.answer(page), True)

    def test_a_title_and_what_follows_it(self):
        page = self.open()
        heading = lambda text, colon=False: page.evaluate("([t, c]) => HoardUI.dialogs.heading(t, c)", [text, colon])  # noqa: E731
        self.assertEqual(heading("Restore the backup from May? It has 2 files."),
                         {"title": "Restore the backup from May?", "detail": "It has 2 files.", "more": []})
        self.assertEqual(heading("Update to Hoard 5.2.0-beta.6?")["title"], "Update to Hoard 5.2.0-beta.6?")
        self.assertEqual(heading("バックアップを削除しますか？元に戻せません。"),
                         {"title": "バックアップを削除しますか？", "detail": "元に戻せません。", "more": []}, "a full-width question mark")
        self.assertEqual(heading("Mix and match picks an outfit. Give your tags a kind first."),
                         {"title": "Mix and match picks an outfit.", "detail": "Give your tags a kind first.", "more": []})
        self.assertEqual(heading("In KonoAsset: 5 products.\n\nNew Local products: 3."),
                         {"title": "In KonoAsset: 5 products.", "detail": "", "more": ["New Local products: 3."]},
                         "a question's colon stays in its title")
        self.assertEqual(heading("Rename Rusk: its folder is renamed.", True),
                         {"title": "Rename Rusk", "detail": "Its folder is renamed.", "more": []}, "a box's title, at its colon")

    def test_a_title_is_never_cut_inside_brackets_or_a_name(self):
        page = self.open()
        heading = lambda text, colon=False: page.evaluate("([t, c]) => HoardUI.dialogs.heading(t, c)", [text, colon])  # noqa: E731
        for text in ("The repository's address (https://... or git@...), without a password or token in it",
                     "Your Git app's program (its full path: GitHub Desktop, Fork, SourceTree...)"):
            self.assertEqual(heading(text, True)["title"], text, "a mark inside brackets")
        self.assertEqual(heading("Hoard waits... then it reads them. Nothing is sent."),
                         {"title": "Hoard waits... then it reads them.", "detail": "Nothing is sent.", "more": []}, "an ellipsis")
        self.assertEqual(heading("新しい復元フレーズを作りますか?古いワードは使えなくなります。"),
                         {"title": "新しい復元フレーズを作りますか?", "detail": "古いワードは使えなくなります。", "more": []},
                         "Japanese's question mark, with no space after it")
        page.evaluate(OPEN, "askName(\"Rename {0}: its folder is renamed, and the list and Hoard's notes on it follow it. "
                            "Unity Hub's list and its backups keep the old name.\", 'Q&A: Test', { max: 255, fill: ['Q&A: Test'] })")
        d = page.locator("dialog.hd-text[open]")
        self.assertEqual(d.locator("h2").inner_text(), "Rename Q&A: Test", "the name put in once it's cut")
        self.assertTrue(d.locator(".hd-detail").inner_text().startswith("Its folder is renamed"))
        self.assertEqual(page.evaluate("tr('Hello {0}')"), "Hello {0}", "words given no values are left as they are")
        page.keyboard.press("Escape")
        self.answer(page)

    def test_a_question_in_japanese(self):
        """The question is translated whole, as the catalog has it, then cut into its title and the line under it."""
        page = self.open(self.ja)
        page.evaluate(OPEN, "ask('Make a new recovery phrase? The old words will stop working.', 'Make a new phrase', true)")
        d = page.locator("#askDialog[open]")
        self.assertEqual(d.locator("h2").inner_text(), "新しい復元フレーズを作りますか?")
        self.assertEqual(d.locator(".hd-detail").inner_text(), "古いワードは使えなくなります。")
        self.assertNotIn("Make a new phrase", d.locator("footer").inner_text())
        page.keyboard.press("Escape")
        self.assertIs(self.answer(page), False)
        self.assertEqual(self.errors, [])

    def test_a_name(self):
        page = self.open()
        page.evaluate(OPEN, "askName('Name the new set', 'Winter')")
        box = page.locator("dialog.hd-text[open] #askName")
        self.assertEqual(page.evaluate("[document.activeElement.id, document.activeElement.selectionStart, document.activeElement.selectionEnd]"),
                         ["askName", 0, 6], "chosen, to type over")
        box.fill("  Fox base  ")
        page.evaluate("document.querySelector('#askName').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', isComposing: true, bubbles: true}))")
        page.wait_for_timeout(200)
        self.assertTrue(box.is_visible(), "not while an input method is putting a word together")
        page.evaluate("""() => { const e = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true });
            Object.defineProperty(e, 'keyCode', { get: () => 229 }); document.querySelector('#askName').dispatchEvent(e); }""")
        page.wait_for_timeout(200)
        self.assertTrue(box.is_visible(), "nor as WebKit says so, after compositionend (keyCode 229)")
        box.press("Enter")
        self.assertEqual(self.answer(page), "Fox base")
        page.evaluate(OPEN, "askName('Name the new set')")
        page.locator("dialog.hd-text[open] button[value=no]").click()
        self.assertEqual(self.answer(page), "")

    def test_a_tag_from_yours(self):
        page = self.open()
        page.evaluate("DATA.tagset = { tags: [{ name: 'winter', count: 3 }, { name: 'wings', count: 1 }, { name: 'boots', count: 2 }] }")
        page.locator(".slot", has_text="Rusk").click(button="right")
        page.locator(".selmenu [role=menuitem]", has_text="Add a tag...").click()
        d = page.locator("dialog.hd-text[open]")
        self.assertEqual(d.locator(".hd-detail").inner_text(), "1 selected")
        self.assertEqual(d.locator(".hd-chip").all_text_contents(), ["#winter3", "#wings1", "#boots2"], "your tags, as they come")
        self.assertEqual(page.locator("#tagList").get_attribute("id"), "tagList")
        self.assertIsNone(page.locator("#askName").get_attribute("list"), "Hoard's own list, not the browser's")
        d.locator("#askName").fill("wi")
        self.assertEqual(d.locator(".hd-chip").all_text_contents(), ["#winter3", "#wings1", "New tag #wi"])
        d.locator("#askName").fill("winter")
        self.assertEqual(d.locator(".hd-chip.new").count(), 0, "it's one of yours")
        d.locator("#askName").fill("w")
        d.locator(".hd-chip", has_text="#wings").click()
        page.locator(".toast", has_text="Added #wings to 1 item.").wait_for()

    def test_a_tag_typed(self):
        """Typed with its "#", or with other capitals than yours: your tag, as you wrote it. Taking one off: only one of
        the tags they have, so Enter and OK wait for one."""
        page = self.open()
        tags = "[{ name: 'Winter', count: 3 }, { name: 'boots', count: 2 }]"
        for typed, create, said in (("#winter", True, "Winter"), ("#Parka", True, "Parka"), ("win", False, "Winter")):
            page.evaluate(OPEN, f"askName('Add a tag', '', {{ suggest: {tags}, create: {str(create).lower()}, prefix: '#' }})")
            page.locator("dialog.hd-text[open] #askName").fill(typed)
            page.keyboard.press("Enter")
            self.assertEqual(self.answer(page), said, typed)
        page.evaluate(OPEN, f"askName('Take a tag off', '', {{ suggest: {tags}, create: false, prefix: '#' }})")
        d = page.locator("dialog.hd-text[open]")
        d.locator("#askName").fill("parka")
        self.assertTrue(d.locator("button[value=yes]").is_disabled(), "none of theirs")
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        self.assertTrue(d.is_visible(), "Enter takes nothing off")
        d.locator("#askName").fill("")
        self.assertTrue(d.locator("button[value=yes]").is_disabled(), "nothing typed, nothing taken off")
        page.keyboard.press("Escape")
        self.assertEqual(self.answer(page), "")

    def test_a_folder(self):
        page = self.open()
        page.evaluate(OPEN, "askFolder('Where is it?', 'The folder with metadata in it.', '/tmp')")
        d = page.locator("dialog.hd-folder[open]")
        self.assertEqual(d.locator(".hd-detail").inner_text(), "The folder with metadata in it.")
        self.assertEqual(d.locator("[data-browse]").count(), 1 if page.evaluate("canPick()") else 0, "Browse, where Hoard's window can")
        self.assertEqual(d.locator("button[value=yes]").inner_text(), "Next")
        d.locator("#askFolder").fill("/tmp/KonoAsset")
        d.locator("button[value=yes]").click()
        self.assertEqual(self.answer(page), "/tmp/KonoAsset")

    def test_one_of_a_list(self):
        page = self.open()
        page.evaluate(OPEN, """HoardUI.dialogs.open({ kind: 'pick', title: 'Add to which set?', find: 'Find a set', tr, norm,
            groups: [{ title: 'Your sets', items: [{ value: 'a', name: 'Fox base', sub: '3 products', pic: '/nowhere.png', letters: 'FB', hue: 10 },
                                                   { value: 'b', name: 'Winter outfit', sub: '2 products', letters: 'WO', hue: 200 }] },
                     { title: 'Wishlists', items: [{ value: 'c', name: 'Booth wishlist', letters: 'BW', hue: 80 }] }] })""")
        d = page.locator("dialog.hd-pick[open]")
        self.assertEqual(d.locator("h4").all_inner_texts(), ["Your sets", "Wishlists"])
        d.locator(".hd-row", has_text="Fox base").locator("b").wait_for()   # (a picture that doesn't load: its letters)
        self.assertEqual(page.evaluate("document.activeElement.type"), "search")
        page.keyboard.type("winter")
        self.assertEqual(d.locator(".hd-row .hd-name").all_inner_texts(), ["Winter outfit"])
        self.assertEqual(d.locator("h4").all_inner_texts(), ["Your sets"], "a group with none left is put away")
        page.keyboard.type("zzz")
        self.assertEqual(d.locator(".hd-none").inner_text(), "Nothing has that name.")
        page.keyboard.press("Backspace+Backspace+Backspace")
        page.keyboard.press("Backspace")
        page.keyboard.press("Backspace")
        page.keyboard.press("Backspace")
        page.keyboard.press("Enter")
        self.assertEqual(self.answer(page), "b", "Enter takes the first one shown")

    def test_a_form_in_steps(self):
        """Projects', Git's and the rest: a form's blocks, its steps (each with its own buttons), a list of ticks that
        needs one, a box that must say something, and what it answers."""
        page = self.open()
        page.evaluate(OPEN, """askForm({ title: 'Fox Avatar', nameTitle: true, ok: 'Put these in', steps: [
            { label: 'Step 1 of 2: its packages', blocks: [
              { type: 'checks', id: 'c', required: true, allNone: true, items: [{ label: 'Fox_PC.unitypackage', tags: [{ text: 'PC' }] },
                                                                                { label: 'Fox Tool', checked: true }] },
              { type: 'field', id: 'name', label: 'Its name', value: 'Fox' }] },
            { label: 'Step 2 of 2: what it needs', blocks: [
              { type: 'checks', id: 'sugg', items: [{ label: 'com.vrcfury.vrcfury', checked: true }] },
              { type: 'check', id: 'nested', label: 'Anyway' }, { type: 'pre', text: 'Library/', cls: 'pj-plan' }] }] })""")
        d = page.locator("dialog.hd-form[open]")
        one, two = d.locator("[data-step='1']"), d.locator("[data-step='2']")
        self.assertTrue(two.is_hidden())
        self.assertEqual(d.locator("h2").get_attribute("translate"), "no", "a name, never translated")
        nxt = one.locator(".primary")
        one.locator("[data-all='0']").click()
        self.assertTrue(nxt.is_disabled(), "nothing ticked: nothing to go on with")
        one.locator("li", has_text="Fox_PC").locator("input").check()
        one.locator("#name").press("Enter")   # (Enter in a box: Next)
        self.assertTrue(one.is_hidden())
        self.assertIn("com.<wbr>vrcfury.<wbr>vrcfury", two.locator(".hd-list").first.inner_html(), "a long name breaks at its dots")
        two.locator("[data-step-go='1']").click()   # Back: as it was
        self.assertTrue(one.locator("li", has_text="Fox_PC").locator("input").is_checked())
        self.assertFalse(one.locator("li", has_text="Fox Tool").locator("input").is_checked())
        nxt.click()
        two.locator("#nested").check()
        two.locator(".primary").click()
        self.assertEqual(self.answer(page), {"ok": True, "value": "yes",
                                             "fields": {"c": [True, False], "name": "Fox", "sugg": [True], "nested": True}})

    def test_a_form_that_needs_a_name_typed(self):
        page = self.open()
        page.evaluate(OPEN, """askForm({ title: 'Delete Picked Project from this computer?', danger: true, ok: 'Delete it', okId: 'go',
            blocks: [{ type: 'field', id: 'typed', label: 'Type its name', mustBe: 'Picked Project' }] })""")
        go = page.locator("#go")
        self.assertEqual(page.evaluate("document.activeElement.id"), "typed", "the box to type in first")
        self.assertTrue(go.is_disabled())
        page.keyboard.type("Picked")
        page.keyboard.press("Enter")
        self.assertTrue(go.is_visible(), "Enter does nothing while the name isn't right")
        page.keyboard.type(" Project")
        self.assertIn("danger", go.get_attribute("class"))
        go.click()
        self.assertEqual(self.answer(page)["fields"], {"typed": "Picked Project"})

    def test_a_window_drawn_by_the_page(self):
        """Mix and match, Share and marks on a photo: their inside drawn by the page, moved into the card; a button
        of its own that does something and stays open; and the page ending it from inside."""
        page = self.open()
        page.evaluate("""() => { window.box = document.createElement('div'); box.innerHTML = '<p>Inside</p><button type="button" id="mine">Mine</button>';
            window.control = {}; window.picks = 0; window.answer = undefined;
            HoardUI.dialogs.open({ kind: 'host', title: 'Mix and match', content: box, control, tr, cancel: 'Close', ok: 'Make a set of them',
              buttons: [{ label: 'Pick again', attrs: { 'data-mix': 'again' }, act: () => { picks++; } }] }).then(a => { window.answer = a; }); }""")
        d = page.locator("dialog.hd-host[open]")
        self.assertEqual(page.evaluate("document.activeElement.id"), "mine", "the keyboard starts inside it")
        d.locator("[data-mix=again]").click()
        d.locator("[data-mix=again]").click()
        self.assertEqual(page.evaluate("window.picks"), 2)
        self.assertTrue(d.is_visible(), "still open")
        page.evaluate("control.close('no')")
        self.assertEqual(self.answer(page), {"ok": False, "value": "no"})

    def test_a_list_with_another_way(self):
        """Put in a project: rows with no picture, and New project with these as another answer."""
        page = self.open()
        page.evaluate(OPEN, """HoardUI.dialogs.open({ kind: 'pick', title: 'Put in a project', tr, norm, cancel: 'Cancel',
            groups: [{ title: '', items: [{ value: '/p/rusk', name: 'Rusk Avatar', sub: 'Avatar · Unity 2022.3.22f1' }] }],
            buttons: [{ label: 'New project with these...', value: 'new' }] })""")
        d = page.locator("dialog.hd-pick[open]")
        self.assertTrue(page.evaluate("document.activeElement.classList.contains('hd-row')"), "the keyboard starts on its first row")
        self.assertEqual(d.locator(".hd-th").count(), 0, "no picture to show")
        self.assertEqual(d.locator("h4").count(), 0, "one group, no heading")
        self.assertEqual(d.locator("input[type=search]").count(), 0, "a short list: nothing to find it with")
        d.locator("button", has_text="New project with these...").click()
        self.assertEqual(self.answer(page), "new")

    def test_the_choice_made_is_in_view_with_its_find_box(self):
        page = self.open()
        page.evaluate(OPEN, """askForm({ title: 'Fox Tool', ok: 'Use this version', blocks: [{ type: 'radios', id: 'v', cls: 'pj-picklist pj-vers',
            value: '1.2.0', find: 'Find a version', findId: 'vf', items: Array.from({ length: 40 }, (_, i) => ({ value: `1.${41 - i}.0`, label: `1.${41 - i}.0` })) }] })""")
        page.locator("dialog.hd-form[open]").wait_for()
        page.wait_for_function("document.activeElement.id === 'vf'")
        seen = page.evaluate("""() => { const r = document.querySelector('dialog.hd input[type=radio]:checked').getBoundingClientRect(),
            box = document.querySelector('dialog.hd .pj-vers').getBoundingClientRect(); return r.top >= box.top && r.bottom <= box.bottom; }""")
        self.assertTrue(seen, "the version installed now, scrolled into view")
        page.keyboard.press("Escape")
        self.answer(page)

    def test_a_drag_out_of_it_isnt_a_click_outside(self):
        page = self.open()
        page.evaluate(OPEN, "ask('Clear the list of finished tasks?')")
        title = page.locator("#askDialog[open] h2").bounding_box()
        page.mouse.move(title["x"] + 4, title["y"] + 4)
        page.mouse.down()
        page.mouse.move(5, 5)
        page.mouse.up()   # (selecting its words, let go outside it)
        page.wait_for_timeout(200)
        self.assertTrue(page.locator("#askDialog[open]").is_visible(), "still asking")
        page.mouse.click(5, 5)
        self.assertIs(self.answer(page), False)

    def test_names_are_kept_from_translation(self):
        page = self.open()
        page.evaluate(OPEN, """askForm({ title: 'Delete Rusk Avatar from this computer?', keep: ['Rusk Avatar', '/p/Rusk Avatar'], ok: 'Delete it',
            blocks: [{ type: 'text', text: 'Its folder, and everything in it, is deleted: /p/Rusk Avatar' },
                     { type: 'checks', id: 'c', items: [{ label: 'Fox.unitypackage', sub: 'Unity package · fox/Fox.unitypackage', keep: ['fox/Fox.unitypackage'] }] }] })""")
        d = page.locator("dialog.hd-form[open]")
        self.assertEqual(d.locator("h2 [translate=no]").all_inner_texts(), ["Rusk Avatar"])
        self.assertEqual(d.locator(".hd-p [translate=no]").all_inner_texts(), ["/p/Rusk Avatar"])
        self.assertEqual(d.locator(".muted [translate=no]").all_inner_texts(), ["fox/Fox.unitypackage"])
        self.assertEqual(d.locator(".hd-p").inner_text(), "Its folder, and everything in it, is deleted: /p/Rusk Avatar")
        page.keyboard.press("Escape")
        self.answer(page)

    def test_one_question_after_another(self):
        """The next pop-up's ids are the only ones on the page, while the last one is taken away."""
        page = self.open()
        page.evaluate(OPEN, "ask('One?').then(() => { const next = ask('Two?'); window.ids = document.querySelectorAll('[id=askDialog], [id=askText]').length; return next; })")
        page.locator("#askDialog[open] button[value=yes]").click()
        page.locator("#askDialog[open] h2", has_text="Two?").wait_for()
        self.assertEqual(page.evaluate("window.ids"), 2, "one dialog and its text")
        page.locator("#askDialog[open] button[value=yes]").click()
        self.assertIs(self.answer(page), True)

    def test_the_styles_corners(self):
        page = self.open()
        radius = lambda sel: page.evaluate(f"getComputedStyle(document.querySelector('{sel}')).borderTopLeftRadius")  # noqa: E731
        for style, card, box in ((None, "18px", "12px"), ("treasure", "24px", "12px"), ("workbench", "10px", "6px")):
            page.evaluate("s => s ? document.documentElement.dataset.style = s : delete document.documentElement.dataset.style", style)
            page.evaluate(OPEN, "askName('Name the new set')")
            page.locator("dialog.hd[open]").wait_for()
            self.assertEqual((radius("dialog.hd"), radius("#askName")), (card, box), style)
            page.keyboard.press("Escape")
            self.answer(page)

    def test_the_style_guide_draws_them(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{self.srv.url}styleguide")
        examples = page.locator(".sg-ex dialog.hd")
        examples.first.wait_for()
        self.assertEqual(examples.count(), 2)
        self.assertEqual(page.locator(".sg-ex dialog.hd h2").all_inner_texts(), ["Delete 2 backups (1.3 GB)?", "Add a tag to the selected"])
        self.assertFalse(page.evaluate("[...document.querySelectorAll('.sg-ex dialog.hd')].some(d => d.matches(':modal'))"), "in the page, not over it")
        self.assertEqual(errors, [])


class ThePagesScripts(IsolatedTestCase):
    def test_no_lookbehind(self):
        """WebKit before Safari 16.4 (a Mac on macOS 11 that hasn't updated, say) can't read a regular expression's
        lookbehind: the whole script the page is made of would stop, and Hoard's window would stay blank."""
        for js in sorted((REPO / "hoard" / "web").glob("*.js")):
            with self.subTest(js.name):
                self.assertNotRegex(js.read_text("utf-8"), r"\(\?<[=!]")


if __name__ == "__main__":
    unittest.main()
