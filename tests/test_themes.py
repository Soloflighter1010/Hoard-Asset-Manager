"""The app's themes (hoard/themes.py): every one keeps the promises the default makes, in both modes, and reaches
the pages."""
import math
import re
import unittest

from hoard import server, themes


def _rgb(h):
    n = int(h[1:], 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]


def _lum(h):
    c = [v / 255 for v in _rgb(h)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    """WCAG's contrast ratio of two colours."""
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def distance(a, b):
    """How far apart two colours look (CIE76: under about 20, easily taken for each other)."""
    def lab(h):
        r, g, b = [(v / 255) / 12.92 if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in _rgb(h)]
        f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
        x, y, z = f((r * .4124 + g * .3576 + b * .1805) / .95047), f(r * .2126 + g * .7152 + b * .0722), f((r * .0193 + g * .1192 + b * .9505) / 1.08883)
        return 116 * y - 16, 500 * (x - y), 200 * (y - z)
    return math.dist(lab(a), lab(b))


class EveryTheme(unittest.TestCase):

    def test_complete(self):
        self.assertIn(themes.DEFAULT, themes.THEMES)
        self.assertEqual(len(themes.THEMES), 10)
        for name, t in themes.THEMES.items():
            for mode in ("dark", "light"):
                self.assertEqual(set(t[mode]), set(themes.KEYS), f"{name} {mode}")
                for k, v in t[mode].items():
                    self.assertRegex(v, r"^(#[0-9A-F]{6}|\d+%)$", f"{name} {mode} {k}")

    def test_readable(self):
        """Text 4.5:1 on every background it's set on; the accent as text 4.5:1; text on the accent 4.5:1."""
        for name, t in themes.THEMES.items():
            for mode in ("dark", "light"):
                c = t[mode]
                at = f"{name} ({mode})"
                for fg, grounds in (("bone", ("cave", "ledge", "stone")), ("dust", ("cave", "ledge")),
                                    ("gold-text", ("cave", "ledge")), ("warn", ("cave", "ledge"))):
                    for ground in grounds:
                        self.assertGreaterEqual(contrast(c[fg], c[ground]), 4.5, f"{at}: {fg} on {ground}")
                self.assertGreaterEqual(contrast(c["gold-ink"], c["gold"]), 4.5, f"{at}: text on the accent")

    def test_stores_stay_stores(self):
        """Each store's colour shows on the page (3:1, as a line or a dot) and isn't taken for the accent."""
        for name, t in themes.THEMES.items():
            for mode in ("dark", "light"):
                c = t[mode]
                for s in themes.STORES:
                    self.assertGreaterEqual(contrast(c[s], c["cave"]), 3, f"{name} ({mode}): {s}")
                    if s != "local":   # (Local is your own: gold-like on purpose)
                        self.assertGreaterEqual(distance(c[s], c["gold"]), 20, f"{name} ({mode}): {s} looks like the accent")

    def test_css(self):
        css = themes.css("frost", "dark")
        self.assertIn("--cave: #11171F", css)
        self.assertIn("color-scheme: dark", css)
        self.assertNotIn("prefers-color-scheme", css, "Dark is dark whatever the computer says")
        both = themes.css("frost", "system")
        self.assertIn("@media (prefers-color-scheme: light)", both)
        self.assertIn("--cave: #EDF2F6", both)
        self.assertIn(':root[data-colours="colourblind"]', both, "colour blindness's colours, in the mode shown")
        self.assertEqual(themes.css("nonsense", "nonsense"), themes.css("hoard", "system"))
        self.assertNotRegex(themes.css("hoard", "light"), r"[<>{]\s*/?style", "nothing that could end the page's style")


class ThePages(unittest.TestCase):

    def test_served_with_the_chosen_theme(self):
        cfg = {"display": {"theme": "geode", "mode": "light"}}
        for page in server.PAGES.values():
            html = server.page_source(page, cfg).decode("utf-8")
            style = re.search(r'<style id="theme">(.*?)</style>', html, re.S)
            self.assertIsNotNone(style, page)
            self.assertIn("--cave: #F1EDF6", style.group(1))
            self.assertLess(html.index('<style id="theme">'), html.index("</head>"))
            self.assertGreater(html.index('<style id="theme">'), html.index("--cave: #211C18"), "after the page's own colours")

    def test_settings(self):
        d = server.display_settings({"display": {"theme": "sakura", "mode": "dark"}})
        self.assertEqual((d["theme"], d["mode"]), ("sakura", "dark"))
        self.assertIn("--cave: #1D1418", d["theme_css"])
        self.assertEqual([c["id"] for c in d["themes"]], list(themes.THEMES))
        d = server.display_settings({"display": {"theme": "<b>", "mode": 3}})
        self.assertEqual((d["theme"], d["mode"]), ("hoard", "system"))


if __name__ == "__main__":
    unittest.main()
