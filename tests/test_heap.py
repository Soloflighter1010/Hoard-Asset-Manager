"""The Heap, Hoard's logo (issues #277 to #280): a box for each store you use, the Projects box always, and the gold
one on top; the same in the app (shared.js) as in every file that carries it (hoard/heap.py), moving as it should
and staying still with Reduce motion."""
import itertools
import os
import sys
import tempfile
import threading
import unittest
from tests.isolation import IsolatedTestCase
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from hoard import heap  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


class Layout(IsolatedTestCase):
    def test_a_heap_never_a_tower(self):
        """A pyramid, each row one fewer; a box that would be alone on top falls down beside the bottom row."""
        self.assertEqual([heap.rows(n) for n in range(9)], [[], [1], [2], [3], [4], [3, 2], [4, 2], [4, 3], [5, 3]])
        for n in range(2, 12):
            got = heap.rows(n)
            self.assertEqual(sum(got), n)
            self.assertFalse(len(got) > 1 and got[-1] == 1, f"{n}: a box alone on top")
            self.assertEqual(got, sorted(got, reverse=True), f"{n}: each row no wider than the one under it")

    def test_the_gold_on_top_and_everything_inside(self):
        for n in range(len(heap.ORDER) + 1):
            for boxes in itertools.combinations(heap.ORDER, n):
                placed = heap.layout(boxes)
                self.assertEqual([p["box"] for p in placed][-1], "gold")
                self.assertEqual(sorted(p["box"] for p in placed[:-1]), sorted(boxes))
                gold = placed[-1]
                self.assertTrue(all(gold["y"] < p["y"] for p in placed[:-1]), boxes)
                for p in placed:
                    self.assertTrue(1 <= p["x"] - p["size"] / 2 and p["x"] + p["size"] / 2 <= 63, (boxes, p))
                    self.assertTrue(1 <= p["y"] - p["size"] / 2 and p["y"] + p["size"] / 2 <= 63, (boxes, p))

    def test_today_s_two_stay_under_the_gold(self):
        placed = {p["box"]: p for p in heap.layout(heap.FULL)}
        top = min(p["y"] for b, p in placed.items() if b != "gold")
        self.assertEqual({b for b, p in placed.items() if p["y"] == top}, {"jinxxy", "gumroad"})
        self.assertEqual(heap.FULL, ("jinxxy", "gumroad", "payhip", "booth", "itch", "projects"),
                         "Hoard's own logo: every store, and Projects")

    def test_every_copy_is_the_heap(self):
        """The app's pages (bar, splashes, the tab's icon), the brand files and the website's mark, as heap.py draws it."""
        import heap_files
        for name, text in heap_files.wanted().items():
            self.assertEqual((REPO / name).read_text("utf-8"), text, f"{name}: run python3 scripts/heap_files.py --write")
        import site_chrome
        self.assertIn(heap.boxes_svg(heap.FULL, line_style="stroke: var(--cave)", indent="  "), site_chrome.LOGO)
        for old in ("rotate(-9 18.5 43.5)", "brand-tumble", "splash-hop"):   # (the old logo, and its animations)
            for name in ("hoard/web/library.html", "hoard/web/downloads.html", "site/styles.css", "site/index.html"):
                self.assertNotIn(old, (REPO / name).read_text("utf-8"), name)


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class InTheApp(IsolatedTestCase):
    @classmethod
    def setUpClass(cls):
        import i18n_strings
        from playwright.sync_api import sync_playwright
        from hoard import server
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(cls.tmp.name) / "data")})
        cls.env.start()
        cls.save = mock.patch.object(server, "save_config")
        cls.save.start()
        cls.srv = i18n_strings.sample_server(Path(cls.tmp.name) / "library", "en")
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.save.stop()
        cls.env.stop()
        cls.tmp.cleanup()

    def open(self):
        page = self.browser.new_page(viewport={"width": 1300, "height": 800})
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => DATA && DATA.version && document.querySelector('.brand .heap').dataset.boxes")
        return page

    def test_the_page_draws_what_heap_py_draws(self):
        page = self.open()
        combos = [list(c) for n in range(len(heap.ORDER) + 1) for c in itertools.combinations(heap.ORDER, n)]
        got = page.evaluate("cs => cs.map(c => heapMarkup(c))", combos)
        for boxes, text in zip(combos, got):
            self.assertEqual(text, heap.boxes_svg(boxes, line_style="stroke: var(--cave)"), boxes)
        page.close()

    def test_the_stores_you_use_and_projects(self):
        """Issue #278: a box for each store you use, Projects always, the gold one on top: one store, three, all five."""
        page = self.open()
        shown = "() => [...document.querySelectorAll('.brand .heap .hb')].map(b => b.dataset.box)"
        self.assertEqual(sorted(page.evaluate(shown)), sorted([*heap.FULL, "gold"]))
        for on in (["booth"], ["booth", "gumroad", "itch"], ["booth", "gumroad", "jinxxy", "payhip", "itch"]):
            with self.subTest(on=on):
                page.evaluate("on => { DATA.enabled = Object.fromEntries(['booth', 'gumroad', 'jinxxy', 'payhip', 'itch']"
                              ".map(s => [s, on.includes(s)])); drawHeap(); }", on)
                self.assertEqual(sorted(page.evaluate(shown)), sorted([*on, "projects", "gold"]))
                self.assertEqual(page.evaluate(shown)[-1], "gold", "drawn last, on top")
        page.close()

    def test_it_moves_and_stays_still_with_reduce_motion(self):
        """Issue #277: pointed at, the heap's boxes stack, fall over and build up again; with Reduce motion they don't.
        Issue #279: poked five times, they topple and build back up (the message all the same with Reduce motion),
        and the Konami code's confetti is the heap's boxes."""
        page = self.open()
        anim = "() => getComputedStyle(document.querySelector('.brand .heap .hb')).animationName"
        self.assertEqual(page.evaluate(anim), "none", "still until it's pointed at")
        page.hover(".brand")
        self.assertEqual(page.evaluate(anim), "heap-loop")
        page.mouse.move(700, 500)
        for _ in range(5):
            page.click(".brand")
        self.assertEqual(page.evaluate(anim), "heap-tumble")
        page.get_by_text("Careful: everything in here is somebody's treasure.").wait_for()
        page.wait_for_function("() => !document.querySelector('.brand').classList.contains('tumble')", timeout=6000)
        page.keyboard.press("Escape")
        for k in ("ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"):
            page.keyboard.press(k)
        page.locator(".heap-confetti i").first.wait_for(state="attached")
        colours = set(page.evaluate("() => [...document.querySelectorAll('.heap-confetti i')].map(i => i.style.background)"))
        self.assertIn("rgb(240, 180, 41)", colours, "the gold one among them")
        page.evaluate("() => document.body.classList.add('less-motion')")
        page.hover(".brand")
        self.assertEqual(page.evaluate(anim), "none")
        page.close()


if __name__ == "__main__":
    unittest.main()
