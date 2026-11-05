"""The Heap, Hoard's logo (issues #277, #278): its gold box with the sparkle on top of a box for each store, in the
store's colour, and the Projects box with a small cube on it, always there (Projects isn't something you switch off).
The full heap (every store, and Projects) is the logo everywhere Hoard's logo is: the brand files, the website, the
press kit, the apps' icons. In the app, the heap has the stores you use; shared.js draws it the same way
(heapMarkup), and a test holds the two to the same boxes.

Every box is drawn in a 64 x 64 square: a box is a <g> placed where it lands (translate and tilt) holding a <g
class="hb"> that the page's animations move (stacking up, falling over and building up again), so an animation never
loses where the box sits."""
from __future__ import annotations

import math
from html import escape

GOLD, SPARK, CAVE = "#F0B429", "#FFF8E6", "#211C18"
COLOURS = {"jinxxy": "#56D1DC", "gumroad": "#FF8AD8", "payhip": "#95A0FF", "booth": "#FF6259", "itch": "#7ED67A",
           "projects": "#EDE4D3"}
ORDER = ("jinxxy", "gumroad", "payhip", "booth", "itch", "projects")   # nearest the gold first: today's two under it
FULL = ORDER   # the logo as Hoard's own: every store, and Projects
TILT = {"jinxxy": -9, "gumroad": 7, "payhip": -8, "booth": 3, "itch": -5, "projects": 5, "gold": -4}   # each its own
BOX, GOLD_BOX, LINE, ROUND = 17.0, 18.0, 2.6, 4.6   # a box's side, the gold one's, the outline, the corners
PITCH, RISE = 18.8, 15.4   # from one box to the next in a row, and from one row to the one above
MOST = 1.6   # a small heap is drawn larger, but never more than this


def rows(n: int) -> list[int]:
    """How many boxes in each row, the bottom first, for n boxes under the gold one: a pyramid, each row one fewer
    than the one under it, the top one as full as it can be (5: 3 and 2; 6: 4 and 2). A box that would be alone on
    top falls down beside the bottom row instead, so the gold rests on two and the heap never stands up as a tower
    (4: 4 side by side, not 3 and 1)."""
    bottom = 1
    while bottom * (bottom + 1) // 2 - 1 < n:
        bottom += 1
    out, left, size = [], n, bottom
    while left > 0:
        out.append(min(size, left))
        left -= out[-1]
        size -= 1
    if len(out) > 1 and out[-1] == 1:
        out = [out[0] + 1, *out[1:-1]]
    return out


def layout(boxes) -> list[dict]:
    """Where each box lands, the bottom row first and the gold one last: [{"box", "x", "y", "size", "tilt"}], in the
    64 x 64 square, the heap in its middle. boxes: which of ORDER (the others are left out), in any order."""
    chosen = [b for b in ORDER if b in set(boxes)]
    sizes = rows(len(chosen))
    placed, taken = [], 0
    by_row: list[list[str]] = [[] for _ in sizes]
    for r in range(len(sizes) - 1, -1, -1):   # the top row takes the first: Jinxxy's and Gumroad's under the gold
        by_row[r] = chosen[taken:taken + sizes[r]]
        taken += sizes[r]
    for r, row in enumerate(by_row):
        for j, b in enumerate(row):
            placed.append({"box": b, "x": (j - (len(row) - 1) / 2) * PITCH, "y": -r * RISE, "size": BOX, "tilt": TILT[b]})
    placed.append({"box": "gold", "x": 0.0, "y": -len(sizes) * RISE - (GOLD_BOX - BOX) / 2, "size": GOLD_BOX, "tilt": TILT["gold"]})

    def reach(p):
        """Half a box's width as it's tilted, with its outline."""
        t = p["tilt"] * (math.pi / 180)
        return p["size"] / 2 * (abs(math.cos(t)) + abs(math.sin(t))) + LINE / 2
    left = min(p["x"] - reach(p) for p in placed)
    right = max(p["x"] + reach(p) for p in placed)
    top = min(p["y"] - reach(p) for p in placed)
    bottom = max(p["y"] + reach(p) for p in placed)
    scale = min(60 / (right - left), 60 / (bottom - top), MOST)
    mid_x, mid_y = (left + right) / 2, (top + bottom) / 2
    return [{**p, "x": 32 + (p["x"] - mid_x) * scale, "y": 32 + (p["y"] - mid_y) * scale, "size": p["size"] * scale,
             "scale": scale} for p in placed]   # (rounded only as they're written: shared.js does the same)


def _n(v: float) -> str:
    """A number as SVG has it: no trailing zeros."""
    out = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if out == "-0" else out


def _sparkle(s: float) -> str:
    """The gold box's sparkle, in the box's own coordinates (its middle at 0, 0) for a box of side s."""
    cx, cy, a, w = 0.2 * s, -0.12 * s, 0.2 * s, 0.055 * s
    pts = [(cx, cy - a), (cx + w, cy - w), (cx + a, cy), (cx + w, cy + w), (cx, cy + a), (cx - w, cy + w), (cx - a, cy), (cx - w, cy - w)]
    return "M" + " L".join(f"{_n(x)} {_n(y)}" for x, y in pts) + "Z"


def _cube(s: float) -> str:
    """The small cube on the Projects box, in the box's own coordinates."""
    r, h = 0.27 * s, 0.27 * s * math.cos(30 * (math.pi / 180))
    top, ur, lr, bot, ll, ul = (0, -r), (h, -r / 2), (h, r / 2), (0, r), (-h, r / 2), (-h, -r / 2)
    ring = " L".join(f"{_n(x)} {_n(y)}" for x, y in (top, ur, lr, bot, ll, ul))
    return f"M{ring}Z M{_n(ul[0])} {_n(ul[1])} L0 0 L{_n(ur[0])} {_n(ur[1])} M0 0 L0 {_n(r)}"


def boxes_svg(boxes=FULL, line: str = CAVE, line_style: str | None = None, indent: str = "") -> str:
    """The heap's boxes as SVG elements, for a 64 x 64 square. line: the outlines' colour; line_style: a style for
    them instead (the app's "stroke: var(--cave)", so the outline is the page's own background). The cube on the
    Projects box is always drawn dark, to show on its light box. shared.js's heapMarkup writes the same text."""
    out = []
    for i, p in enumerate(layout(boxes)):
        s, scale = p["size"], p["scale"]
        drift = -1 if p["x"] < 31 else 1   # (which way it falls over)
        stroke = f' style="{line_style}"' if line_style else f' stroke="{line}"'
        extra = ""
        if p["box"] == "gold":
            extra = f'<path class="spark" d="{_sparkle(s)}" fill="{SPARK}"/>'
        elif p["box"] == "projects":
            extra = (f'<path d="{_cube(s)}" fill="none" stroke="{CAVE}" stroke-width="{_n(1.5 * scale)}" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        fill = GOLD if p["box"] == "gold" else COLOURS[p["box"]]
        out.append(f'{indent}<g transform="translate({_n(p["x"])} {_n(p["y"])}) rotate({p["tilt"]})">'
                   f'<g class="hb" data-box="{p["box"]}" style="--i:{i};--fx:{drift * 9}px;--fr:{drift * 55}deg">'
                   f'<rect x="{_n(-s / 2)}" y="{_n(-s / 2)}" width="{_n(s)}" height="{_n(s)}" rx="{_n(ROUND * scale)}" '
                   f'fill="{fill}"{stroke} stroke-width="{_n(LINE * scale)}"/>{extra}</g></g>')
    return "\n".join(out)


# the wordmark, "hoard", beside the boxes: its letters as paths (brand/wordmark.svg), so it looks the same without the font
_WORD: list[str] = []


def word() -> str:
    """The wordmark's paths, as brand/wordmark.svg has them (for the brand files, the website and the press kit)."""
    if not _WORD:
        import re
        from pathlib import Path
        text = (Path(__file__).resolve().parent.parent / "brand" / "wordmark.svg").read_text("utf-8")
        _WORD.append(re.search(r"<g[^>]*>(.*)</g>", text, re.S).group(1).strip())
    return _WORD[0]


def mark(boxes=FULL, line: str = CAVE, size: int | None = None, background: str | None = None, label: str | None = None) -> str:
    """The heap on its own, as an SVG file (the brand's mark, the favicon, the apps' icons)."""
    dims = f' width="{size}" height="{size}"' if size else ""
    aria = f' role="img" aria-label="{escape(label)}"' if label else ""
    bg = f'<rect width="64" height="64" rx="14" fill="{background}"/>' if background else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"{dims}{aria}>{bg}<g class="boxes">\n'
            f'{boxes_svg(boxes, line, indent="  ")}\n</g></svg>\n')


def logo(boxes=FULL, line: str = CAVE, words: str = "#F2EDE4", label: str = "Hoard") -> str:
    """The heap and the wordmark, as an SVG file (226 x 64): the brand's logo, on dark (words light) or on light."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 226 64" role="img" aria-label="{escape(label)}">'
            f'<g class="boxes">\n{boxes_svg(boxes, line, indent="  ")}\n</g><g class="word" fill="{words}">{word()}</g></svg>\n')
