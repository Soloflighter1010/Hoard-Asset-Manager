"""Hoard's videos (promo/: issues #273, #274, #291): every scene is one promo/video/film.html draws, a whole or half
number of bars long, so its cuts land on the beat; what a film points at is something promo/regions.json finds on a
screen scripts/screenshots.py takes; a film has every word in each language it has; the videos' Heap is the one
hoard/heap.py draws everywhere; the music's loop wraps round with no seam; a thing's box on a screen holds all it
draws, so a close-up of it never cuts it off; and every video has a thumbnail, its title (in Japanese) broken only
between phrases."""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROMO = REPO / "promo"
FILMS = {p.stem: json.loads(p.read_text("utf-8")) for p in sorted((PROMO / "films").glob("*.json"))}
REGIONS = json.loads((PROMO / "regions.json").read_text("utf-8"))
BAR = 4 * 60 / 100   # the music is 100 beats a minute, four to a bar
SHOTS_PY = (REPO / "scripts" / "screenshots.py").read_text("utf-8")

try:
    import numpy  # noqa: F401
    import scipy  # noqa: F401
    MUSIC = True
except ImportError:   # (promo/requirements.txt: not in the app's own requirements)
    MUSIC = False
try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def words(v, where=""):
    """Every set of words in a film (a dict with "en"), and where it is."""
    if isinstance(v, dict):
        if "en" in v:
            yield where, v
        else:
            for k, x in v.items():
                yield from words(x, f"{where}.{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from words(x, f"{where}[{i}]")


class Films(unittest.TestCase):
    def test_every_scene_is_drawn(self):
        page = (PROMO / "video" / "film.html").read_text("utf-8")
        drawn = set(re.findall(r"^BUILD\.(\w+) =", page, re.M)) & set(re.findall(r"^DRAW\.(\w+) =", page, re.M))
        self.assertTrue(FILMS)
        for name, film in FILMS.items():
            for s in film["scenes"]:
                self.assertIn(s["type"], drawn, name)

    def test_cuts_on_the_beat(self):
        for name, film in FILMS.items():
            self.assertEqual(film.get("bpm", 100), 100, name)
            for s in film["scenes"]:
                self.assertEqual(s["bars"] * 2, int(s["bars"] * 2), f"{name}: {s['type']} is {s['bars']} bars")
            self.assertEqual(sum(1 for s in film["scenes"] if s.get("ending")), 1, f"{name}: one scene has the ending chord")
            self.assertTrue(film["scenes"][-1].get("ending"), f"{name}: the ending chord is on its last scene")

    def test_lengths(self):
        for name, film in FILMS.items():
            seconds = sum(s["bars"] for s in film["scenes"]) * BAR
            if name == "promo-short":
                self.assertTrue(25 <= seconds <= 40, seconds)   # (#273: about 30 seconds)
            elif name == "promo-long":
                self.assertTrue(60 <= seconds <= 180, seconds)  # (#273: 1 to 3 minutes)
            else:
                self.assertTrue(20 <= seconds <= 90, f"{name}: {seconds}")

    def test_what_a_film_points_at_is_found(self):
        for name, film in FILMS.items():
            for s in film["scenes"]:
                if "image" not in s:
                    continue
                self.assertIn(s["image"], REGIONS, f"{name}: regions.json has nothing on {s['image']}")
                for f in s.get("focus", []):
                    box, lens = (f[1], f[3] if len(f) > 3 else None) if isinstance(f, list) else (f["box"], f.get("lens"))
                    self.assertIn(box, REGIONS[s["image"]], f"{name}: {s['image']} has no {box}")
                    if isinstance(lens, str):
                        self.assertIn(lens, REGIONS[s["image"]], f"{name}: {s['image']} has no {lens}")

    def test_every_screen_is_taken(self):
        # each screen regions.json names, and each a film shows, is one scripts/screenshots.py photographs: on the
        # way round the website's pictures, or among the videos' own (VIDEO_SHOTS)
        video = _literal("VIDEO_SHOTS")
        shown = set(REGIONS) | {i for f in FILMS.values() for s in f["scenes"] for i in s.get("images", [])}
        shown |= {i for f in FILMS.values() for i in [f["thumb"].get("image"), *f["thumb"].get("images", [])] if i}
        for image in shown:
            if image not in video:
                self.assertRegex(SHOTS_PY, rf'snap\(\s*"{re.escape(image)}"|"{re.escape(image)}"\)', image)

    def test_every_word_in_each_language(self):
        for name, film in FILMS.items():
            for where, w in words(film):
                en = w["en"]
                for lang, said in w.items():
                    self.assertIn(lang, ("en", "ja", "ko"), f"{name}{where}")
                    if isinstance(en, dict):
                        self.assertEqual(set(said), set(en), f"{name}{where}: {lang} hasn't the same words as en")
                        for k, v in said.items():
                            self.assertTrue(v if isinstance(v, list) else str(v).strip(), f"{name}{where}.{k}: no {lang}")
                            if isinstance(v, list):
                                self.assertEqual(len(v), len(en[k]), f"{name}{where}.{k}: {lang}")
                    else:
                        self.assertTrue(str(said).strip(), f"{name}{where}: no {lang}")

    def test_the_heap_is_hoards(self):
        from hoard import heap
        parts = load("promo_build", PROMO / "build.py").heap_parts()
        self.assertEqual([b["box"] for b in parts["boxes"]], [p["box"] for p in heap.layout(heap.FULL)])
        self.assertEqual(parts["boxes"][-1]["box"], "gold")   # your own files, on top
        self.assertIn("projects", [b["box"] for b in parts["boxes"]])
        self.assertEqual(parts["svg"], heap.boxes_svg(heap.FULL))


class Thumbnails(unittest.TestCase):
    def test_every_video_has_one(self):
        page = (PROMO / "video" / "thumb.html").read_text("utf-8")
        looks = set(re.findall(r"^LOOK\.(\w+) =", page, re.M))
        for name, film in FILMS.items():
            self.assertIn("thumb", film, f"{name}: no thumbnail")
            self.assertIn(film["thumb"]["look"], looks, name)
            self.assertEqual(film["thumb"]["look"] == "help", film.get("style") == "help", f"{name}: a help video's has the help look")

    def test_a_help_thumbnail_shows_one_of_its_steps(self):
        for name, film in FILMS.items():
            th = film["thumb"]
            if th["look"] != "help":
                continue
            s = film["scenes"][th["scene"]]
            self.assertIn(s["type"], ("hshot", "hwindow"), name)
            if s["type"] == "hshot":
                self.assertLess(th.get("focus", 0), len(s["focus"]), name)
            else:
                for lang, tx in s["text"].items():
                    self.assertLess(th.get("state", 0), len(tx["win"]), f"{name} ({lang})")

    def test_named_like_its_video(self):
        thumbs = load("promo_thumbs", PROMO / "thumbs.py")
        self.assertEqual(thumbs.SIZES["landscape"], (1280, 720))   # YouTube's size for a video's
        self.assertEqual(thumbs.SIZES["portrait"], (1080, 1920))   # a Short's
        self.assertIn('f"hoard-{tag}.jpg"', (PROMO / "thumbs.py").read_text("utf-8"))
        self.assertIn('f"hoard-{tag}.mp4"', (PROMO / "build.py").read_text("utf-8"))

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_a_japanese_title_breaks_between_phrases(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto((PROMO / "video" / "thumb.html").as_uri())
            got = {t: page.evaluate("t => jaPhrases(t)", t) for t in
                   ("「Boothにサインインしていません」", "itch.ioがAPIキーを受け付けない", "ダウンロードが何度も失敗する")}
            browser.close()
        self.assertEqual(got["「Boothにサインインしていません」"], ["「", "Boothに", "サインインして", "いません」"])
        self.assertEqual(got["itch.ioがAPIキーを受け付けない"], ["itch.ioが", "APIキーを", "受け付けない"])
        self.assertEqual(got["ダウンロードが何度も失敗する"], ["ダウンロードが", "何度も", "失敗する"])


@unittest.skipUnless(MUSIC, "needs numpy and SciPy (pip install -r promo/requirements.txt)")
class Music(unittest.TestCase):
    def test_a_note_past_the_end_lands_on_the_start(self):
        import numpy as np
        loop = load("promo_loop", PROMO / "music" / "loop.py")
        self.assertAlmostEqual(loop.L / loop.SR, 32 * BAR, places=3)   # 32 bars
        bus = loop.Bus()
        bus.add(np.ones(loop.SR), (loop.L - loop.SR // 2) / loop.SR)   # a second long, half a second from the end
        self.assertGreater(abs(bus.L[: loop.SR // 4]).max(), 0.5)
        self.assertGreater(abs(bus.L[-loop.SR // 4:]).max(), 0.5)

    def test_filters_and_echoes_run_round(self):
        import numpy as np
        loop = load("promo_loop", PROMO / "music" / "loop.py")
        x = np.sin(2 * np.pi * 3 * np.arange(loop.L) / loop.L) + np.random.default_rng(1).normal(0, .1, loop.L)
        y = loop.circular(lambda v: loop.lp(v, 400), x)
        jump = abs(y[0] - y[-1])   # across the seam, no bigger than from one sample to the next anywhere else
        self.assertLessEqual(jump, abs(np.diff(y)).max() + 1e-9)
        z = loop.wrap_convolve(np.r_[np.zeros(loop.L - 10), np.ones(10)], np.exp(-np.arange(loop.SR) / 2000.0))
        self.assertGreater(z[:100].max(), .5)   # the echo of the last samples is heard at the start


def _literal(name: str):
    """One of screenshots.py's constants (read without importing it: importing it makes a made-up data folder)."""
    for node in ast.parse(SHOTS_PY).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"no {name} in scripts/screenshots.py")


def _region_boxes() -> str:
    return _literal("REGION_BOXES")


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Boxes(unittest.TestCase):
    def test_a_box_holds_all_it_draws(self):
        from playwright.sync_api import sync_playwright
        page_html = """<body style="margin:0">
          <div id="row" style="position:absolute;left:100px;top:100px;width:300px;height:40px">
            <button style="position:absolute;left:250px;top:0;width:90px;height:30px;border:2px solid">Show</button></div>
          <div id="cut" style="position:absolute;left:100px;top:300px;width:200px;height:40px;overflow:hidden">
            <span style="position:absolute;left:150px;width:200px;height:20px;display:block">hidden past the edge</span></div>
          <div id="low" style="position:absolute;left:10px;top:580px;width:100px;height:100px"></div></body>"""
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.set_content(page_html)
            boxes = page.evaluate(_region_boxes(), {"row": "#row", "cut": "#cut", "low": "#low", "none": "#nothing"})
            browser.close()
        self.assertEqual(boxes["row"], [100, 100, 340, 40])   # the button that sticks out, with its border
        self.assertEqual(boxes["cut"], [100, 300, 200, 40])   # not what its own edge hides
        self.assertEqual(boxes["low"], [10, 580, 100, 20])    # only what's on the page
        self.assertIsNone(boxes["none"])


if __name__ == "__main__":
    unittest.main()
