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
        with cls.srv.lib.lock:   # in memory only
            cls.srv.lib.data["items"] = [library.item("booth", "111", name="Rusk", creator="Kitsu Studio"),
                                         library.item("booth", "112", name="Winter Hoodie", creator="Kitsu Studio")]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def open(self):
        """Hoard's page, its products drawn, noting any error on it."""
        page = self.browser.new_page()
        self.addCleanup(page.close)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.srv.entry_url())
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


if __name__ == "__main__":
    unittest.main()
