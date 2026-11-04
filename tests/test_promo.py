"""Hoard's videos, posters and music (promo/): every scene has its words in English, Japanese and Korean, the
screens and parts it names are ones promo/capture.py takes, a video builds into what the player draws, the player
draws the same frame every time, the music loops, and each troubleshooting video is linked from the wiki section that
explains its problem."""
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "promo"))
import scenes  # noqa: E402


def _capture_tables() -> tuple[dict, dict]:
    """capture.py's SHOTS and FOCUS, read without importing it (importing it makes a made-up data folder)."""
    tree = ast.parse((REPO / "promo" / "capture.py").read_text("utf-8"))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ("SHOTS", "FOCUS"):
            found[node.targets[0].id] = ast.literal_eval(node.value)
    return found["SHOTS"], found["FOCUS"]


SHOTS, FOCUS = _capture_tables()


def _words(v):
    """Every set of words (a dict with en, ja and ko) in a scene."""
    if isinstance(v, dict):
        if set(v) == set(scenes.LANGS):
            yield v
        else:
            for x in v.values():
                yield from _words(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _words(x)


class Scenes(unittest.TestCase):
    def test_every_word_in_every_language(self):
        for name, make, _, _ in scenes.videos():
            for w in _words(make()):
                for lang in scenes.LANGS:
                    self.assertTrue(w[lang].strip(), f"{name}: no {lang} for {w['en']!r}")
        for w in _words(scenes.POSTERS):
            for lang in scenes.LANGS:
                self.assertTrue(w[lang].strip())

    def test_hoards_own_words_are_translated(self):
        # a {Name} is one of Hoard's own words: the app has it in Japanese and Korean, so the video names it as Hoard does
        for name, make, _, _ in scenes.videos():
            for w in _words(make()):
                for lang in ("ja", "ko"):
                    for word in re.findall(r"\{([^{}]+)\}", w[lang]):
                        self.assertNotEqual(scenes.ui(lang, word), word, f"{name}: Hoard has no {lang} for {word!r}")
                    self.assertNotIn("{", scenes.say(w, lang))

    def test_screens_and_parts_are_ones_capture_takes(self):
        for name, make, _, _ in scenes.videos():
            for s in make():
                if s["kind"] != "screen":
                    continue
                self.assertIn(s["shot"], SHOTS, name)
                parts = set(FOCUS.get(s["shot"], {})) | {"all", None}
                for p in s["cam"]:
                    self.assertIn(p, parts, f"{name}: {s['shot']} has no part {p!r}")
                for p, _, _ in s["rings"]:
                    self.assertIn(p, parts, f"{name}: {s['shot']} has no part {p!r}")
                for _, p, _ in s["cursor"] or ():
                    self.assertIn(p, parts, f"{name}: {s['shot']} has no part {p!r}")
        for p in scenes.POSTERS:
            self.assertIn(p["shot"], SHOTS)

    def test_every_shot_has_a_theme(self):
        from hoard import themes
        for name, (theme, mode, style, _) in SHOTS.items():
            self.assertIn(theme, themes.THEMES, name)
            self.assertIn(mode, ("light", "dark"), name)
            self.assertIn(style, themes.STYLES, name)

    def test_lengths(self):
        lengths = {name: scenes.total(make()) for name, make, _, _ in scenes.videos()}
        self.assertTrue(60 <= lengths["promo-long"] <= 180, lengths["promo-long"])   # (#273: 1 to 3 minutes)
        self.assertTrue(25 <= lengths["promo-short"] <= 40, lengths["promo-short"])  # (about 30 seconds)
        for name, n in lengths.items():
            if name.startswith("troubleshooting-"):
                self.assertLessEqual(n, 40, name)

    def test_the_twelve_promos_and_the_troubleshooting_videos(self):
        made = {(name, layout, lang) for name, _, layouts, langs in scenes.videos() for layout in layouts for lang in langs}
        self.assertEqual(sum(1 for n, _, _ in made if n.startswith("promo-")), 12)
        self.assertEqual(len(scenes.TROUBLESHOOTING), 9)
        for key in scenes.TROUBLESHOOTING:
            for lang in scenes.LANGS:
                self.assertIn((f"troubleshooting-{key}", "landscape", lang), made)


class Build(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="hoard-promo-"))
        self.screens, self.library = self.dir / "screens", self.dir / "library"
        self.screens.mkdir()
        self.library.mkdir()
        boxes = {name: {lang: {part: [100 + 10 * k, 120, 400, 200] for k, part in enumerate(parts)} for lang in scenes.LANGS}
                 for name, parts in FOCUS.items()}
        (self.screens / "shots.json").write_text(json.dumps(
            {name: {"theme": t, "mode": m, "style": st, "boxes": boxes.get(name, {})} for name, (t, m, st, _) in SHOTS.items()}), "utf-8")
        items = [{"image": f"p{i}.jpg", "name": f"Product {i}", "creator": f"Maker {i}", "store": s, "tags": []}
                 for i, s in enumerate(("booth", "gumroad", "jinxxy", "payhip", "itch"))]
        (self.library / "products.json").write_text(json.dumps(items), "utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_build(self):
        for name, make, layouts, langs in scenes.videos():
            for layout in layouts:
                for lang in langs:
                    v = scenes.build(make(), lang, layout, self.screens, self.library)
                    self.assertEqual((v["w"], v["h"]), (1920, 1080) if layout == "landscape" else (1080, 1920))
                    self.assertAlmostEqual(sum(s["dur"] for s in v["shots"]), scenes.total(make()))
                    aspect = 1180 / 664 if layout == "landscape" else 1.0
                    for s in v["shots"]:
                        if s["kind"] != "screen":
                            continue
                        self.assertTrue(s["src"].startswith("file://") and s["src"].endswith(f"-{lang}.png"))
                        for r in (s["from"], s["to"]):   # (the camera: the window's shape, on the screen)
                            x, y, w, h = r
                            self.assertTrue(0 <= x and 0 <= y and x + w <= 1920 + 1 and y + h <= 1080 + 1, (name, r))
                            self.assertAlmostEqual(w / h, aspect, delta=0.02)
                        if s["shot"].startswith("t-"):
                            self.assertIsNone(s["chip"])   # (troubleshooting: Hoard's own look, no theme to show)
                        else:
                            self.assertEqual(len(s["chip"]["swatches"]), 4)
                    self.assertIn("<svg", v["logo"])

    def test_credits_leave_out_the_made_up(self):
        import art
        name, made_up = art.PRODUCTS[0][0], art.PRODUCTS[0][1]
        items = json.loads((self.library / "products.json").read_text("utf-8"))
        items.append({"image": "x.png", "name": name, "creator": made_up, "store": "booth", "tags": []})
        (self.library / "products.json").write_text(json.dumps(items), "utf-8")
        names = scenes.credit_names(self.library)
        self.assertIn("Maker 0", names)
        self.assertNotIn(made_up, names)
        # a real product by a creator who happens to share a made-up one's name is credited
        items.append({"image": "y.jpg", "name": "A real product", "creator": made_up, "store": "booth", "tags": []})
        (self.library / "products.json").write_text(json.dumps(items), "utf-8")
        self.assertIn(made_up, scenes.credit_names(self.library))

    def test_posters(self):
        for p in scenes.POSTERS:
            for layout in ("portrait", "landscape"):
                for lang in scenes.LANGS:
                    v = scenes.build_poster(p, lang, layout, self.screens)
                    self.assertEqual(v["shots"][0]["kind"], "poster")


class Player(unittest.TestCase):
    page = (REPO / "promo" / "player.html").read_text("utf-8")

    def test_the_same_frame_every_time(self):
        # each frame is drawn from t alone: no randomness, no clock, no animations running on their own
        for bad in ("Math.random", "Date.now", "new Date", "requestAnimationFrame", "@keyframes", "transition"):
            self.assertFalse(bad in self.page, f"player.html has {bad}")

    def test_nothing_from_elsewhere(self):
        self.assertIsNone(re.search(r"(src|href)=\"https?://", self.page))
        self.assertNotIn("@import", self.page)


class Music(unittest.TestCase):
    def test_notes(self):
        import music
        self.assertAlmostEqual(music.hz("A4"), 440.0)
        self.assertAlmostEqual(music.hz("A5"), 880.0)
        self.assertAlmostEqual(music.hz("C4"), 261.63, places=1)
        self.assertAlmostEqual(music.LOOP, 40.0)

    def test_a_bar_loops_without_a_click(self):
        import music
        left, right = music.master(music.render(bars=2))
        self.assertEqual(len(left), round(2 * 4 * music.BEAT * music.RATE))
        self.assertLessEqual(max(map(abs, left + right)), 1.0)
        self.assertLess(music.seam(left), 1.0)


class Wiki(unittest.TestCase):
    PAGES = {"en": ("Troubleshooting.md", "FAQ.md"), "ja": ("ja/トラブルシューティング.md", "ja/よくある質問.md"),
             "ko": ("ko/문제-해결.md", "ko/자주-묻는-질문.md")}

    def test_each_troubleshooting_video_is_linked(self):
        base = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/download/media/"
        for lang, (trouble, faq) in self.PAGES.items():
            text = (REPO / "wiki" / trouble).read_text("utf-8")
            for key in scenes.TROUBLESHOOTING:
                self.assertIn(f"{base}troubleshooting-{key}-{lang}.mp4", text, f"{trouble}: no link to {key}")
            self.assertIn(f"{base}troubleshooting-windows-{lang}.mp4", (REPO / "wiki" / faq).read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
