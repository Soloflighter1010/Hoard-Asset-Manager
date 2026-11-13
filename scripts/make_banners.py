"""Hoard's banners for social sites and VRChat: landscape pictures with Hoard's logo (the Heap), its words and its
stores, drawn in code as the website's social cards are (scripts/make_social_cards.py), at each site's own size, with
what matters inside the part each site always shows.

    python3 scripts/make_banners.py              draws brand/banners/hoard-banner-*.png
    python3 scripts/make_banners.py --guides     and, beside them, each drawn with its site's safe area marked
                                                 (build/banners/, to check them by eye; not kept)

Every one is the Heap, Hoard's words and shapes: no product's picture, made-up or real. Needs Playwright (as the
tests do).

    vrchat-group   1920 x 1080  a VRChat group's banner. Shown whole only in its gallery: members' nameplates show a
                                band across its middle (y 430 to 597 always; more with a short name or the menu open),
                                with their profile picture over the left and their name over the rest, and the group's
                                page a taller band (y 335 to 745), its icon at the bottom left. So the logo sits at the
                                band's right end, the middle is kept quiet for names, and the words are under the
                                band, where the group's page shows them and a nameplate doesn't.
    x-bluesky      1500 x 500   X's header, and Bluesky's: the profile picture covers the bottom left, and phones trim
                                the top and bottom.
    youtube        2560 x 1440  a YouTube channel's: only the middle 1546 x 423 shows everywhere (TVs show it all).
    discord        960 x 540    a Discord server's banner, under the server's name, small.
    github         1280 x 640   GitHub's social preview, the picture a link to the repository shows.
"""
from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from hoard import heap  # noqa: E402

OUT = REPO / "brand" / "banners"
GUIDES = REPO / "build" / "banners"
FONTS = REPO / "site" / "fonts"
CAVE, BONE, DUST, LEDGE, SEAM = "#211C18", "#F4EDE3", "#C9BDAE", "#2B2520", "#4A4037"
STORES = [("Booth", "booth"), ("Gumroad", "gumroad"), ("Jinxxy", "jinxxy"), ("Payhip", "payhip"), ("itch.io", "itch")]
TAGLINE = ("Your assets and projects,", "in one hoard")
LINE = "Downloads what you've bought, and manages your Unity projects. Free."
SITE = "hoard.furryup.link"

# name: (width, height, the part every view shows (x, y, w, h), or None when it's shown whole)
SIZES = {
    "vrchat-group": (1920, 1080, (560, 430, 1300, 167)),
    "x-bluesky": (1500, 500, (260, 70, 1220, 360)),
    "youtube": (2560, 1440, (507, 508, 1546, 423)),
    "discord": (960, 540, None),
    "github": (1280, 640, None),
}


def font(name: str) -> str:
    """A font as a data address: a page drawn from a string can't load files."""
    return "data:font/woff2;base64," + base64.b64encode((FONTS / name).read_bytes()).decode()


def box(x: float, y: float, size: float, kind: str, tilt: float, opacity: float = 1.0) -> str:
    """One of the Heap's boxes, as the logo draws it (its outline and corners in proportion), standing at x, y: a
    store's in its colour, the gold one with its sparkle, or Projects' with its cube."""
    scale = size / heap.BOX
    fill = heap.GOLD if kind == "gold" else heap.COLOURS[kind]
    extra = ""
    if kind == "gold":
        extra = f'<path d="{heap._sparkle(size)}" fill="{heap.SPARK}"/>'
    elif kind == "projects":
        extra = (f'<path d="{heap._cube(size)}" fill="none" stroke="{CAVE}" stroke-width="{1.5 * scale:.2f}" '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')
    return (f'<g transform="translate({x:.1f} {y:.1f}) rotate({tilt})" opacity="{opacity}">'
            f'<rect x="{-size / 2:.1f}" y="{-size / 2:.1f}" width="{size:.1f}" height="{size:.1f}" '
            f'rx="{heap.ROUND * scale:.1f}" fill="{fill}" stroke="{CAVE}" stroke-width="{heap.LINE * scale:.2f}"/>{extra}</g>')


def scatter(width: int, height: int, boxes: list[tuple]) -> str:
    """Boxes strewn about the picture (x, y, size, kind, tilt[, opacity]), behind everything else."""
    return (f'<svg class="layer" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
            + "".join(box(*b) for b in boxes) + "</svg>")


def logo(height: float) -> str:
    """The logo (the Heap and the wordmark), this tall."""
    return heap.logo(words=BONE).replace("<svg ", f'<svg style="height:{height}px;width:{height * 226 / 64:.1f}px" ', 1)


def mark(size: float) -> str:
    """The Heap on its own, this big."""
    return heap.mark(size=round(size))


def chips(size: float) -> str:
    """The stores, each with its colour, as the website's cards show them."""
    return '<div class="chips">' + "".join(
        f'<span class="chip" style="font-size:{size}px"><i style="background:{heap.COLOURS[key]}"></i>{html.escape(name)}</span>'
        for name, key in STORES) + "</div>"


def page(width: int, height: int, body: str, glow: str) -> str:
    """A banner, as HTML to draw: the cave's ground and a glow of the stores' colours under what's on it."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Dela; src: url({font('DelaGothicOne-Regular.woff2')}); }}
@font-face {{ font-family: Zen; font-weight: 700; src: url({font('ZenMaruGothic-Bold.woff2')}); }}
@font-face {{ font-family: Zen; font-weight: 500; src: url({font('ZenMaruGothic-Medium.woff2')}); }}
* {{ box-sizing: border-box; margin: 0; }}
body {{ width: {width}px; height: {height}px; overflow: hidden; position: relative; background: {CAVE}; color: {BONE};
  font: 500 26px/1.35 Zen; }}
.glow {{ position: absolute; inset: 0; background: {glow}; }}
.layer {{ position: absolute; left: 0; top: 0; }}
.at {{ position: absolute; }}
.at svg {{ display: block; }}
h1 {{ font: 400 1em/1.12 Dela; letter-spacing: 0; }}
.line {{ color: {DUST}; }}
.site {{ color: {DUST}; font-weight: 700; letter-spacing: .02em; }}
.chips {{ display: flex; gap: .45em; }}
.chip {{ display: inline-flex; align-items: center; gap: .5em; padding: .3em .7em; border-radius: .55em;
  background: {LEDGE}cc; box-shadow: inset 0 0 0 1.5px {SEAM}; font-weight: 700; line-height: 1.2; }}
.chip i {{ width: .5em; height: .5em; border-radius: .15em; transform: rotate(45deg); }}
</style></head><body><div class="glow"></div>{body}</body></html>"""


def glow(spots: list[tuple]) -> str:
    """Soft light in the stores' colours, and the gold's: (colour, x%, y%, width%, height%, strength 0 to 255)."""
    return ", ".join(f"radial-gradient(ellipse {w}% {h}% at {x}% {y}%, {c}{a:02x}, transparent 75%)"
                     for c, x, y, w, h, a in spots)


def store_glow(y: float = 112, strength: int = 0x77, width: float = 16, height: float = 70) -> list[tuple]:
    """The stores' colours along the bottom, as the website's cards have them."""
    keys = ["booth", "gumroad", "jinxxy", "payhip", "itch"]
    return [(heap.COLOURS[k], 6 + 18 * i, y, width, height, strength) for i, k in enumerate(keys)]


def vrchat_group() -> str:
    w, h = 1920, 1080
    boxes = [   # around the edges: the gallery shows them all, a nameplate with a short name the top ones
        (150, 150, 120, "booth", -10), (330, 245, 84, "gumroad", 8), (90, 345, 64, "payhip", -6),
        (1770, 140, 110, "jinxxy", 9), (1600, 255, 78, "itch", -7), (1835, 330, 58, "projects", 5),
        (980, 175, 70, "gold", -5, 0.9), (720, 285, 46, "payhip", 12, 0.8), (1250, 300, 52, "booth", -9, 0.8),
        (210, 860, 150, "jinxxy", 7), (430, 960, 100, "projects", -6), (90, 1010, 80, "gold", 5),
        (1710, 900, 140, "gumroad", -8), (1500, 990, 96, "itch", 6), (1870, 1010, 70, "booth", -4),
        (900, 950, 72, "payhip", 9, 0.85), (1180, 880, 54, "jinxxy", -11, 0.8),
    ]
    body = (scatter(w, h, boxes)
            + f'<div class="at" style="left:1386px;top:449px">{logo(126)}</div>'
            + f'<div class="at" style="right:66px;top:612px;font-size:33px;text-align:right">'
              f'<h1>{html.escape(" ".join(TAGLINE))}</h1>'
              f'<p class="site" style="font-size:24px;margin-top:10px">{SITE}</p></div>')
    spots = [(heap.GOLD, 86, 52, 30, 26, 0x2a)] + store_glow(y=104, strength=0x55, height=40)
    return page(w, h, body, glow(spots))


def x_bluesky() -> str:
    w, h = 1500, 500
    boxes = [(80, 70, 70, "jinxxy", -8, 0.9), (205, 140, 46, "gold", 6, 0.9), (60, 215, 40, "payhip", 10, 0.8)]
    body = (scatter(w, h, boxes)
            + f'<div class="at" style="left:1040px;top:46px">{mark(420)}</div>'
            + f'<div class="at" style="left:330px;top:86px;font-size:52px">{logo(70)}'
              f'<h1 style="margin-top:28px">{TAGLINE[0]}<br>{TAGLINE[1]}</h1>'
              f'<div style="margin-top:28px">{chips(22)}</div></div>')
    return page(w, h, body, glow(store_glow(strength=0x66)))


def youtube() -> str:
    w, h = 2560, 1440
    boxes = [   # outside the middle: only a TV, or a wide window, shows these
        (180, 200, 190, "booth", -9), (430, 330, 120, "gumroad", 7), (130, 480, 96, "payhip", -6),
        (2380, 190, 170, "jinxxy", 8), (2170, 320, 110, "itch", -7), (2440, 470, 90, "projects", 6),
        (1280, 210, 100, "gold", -5, 0.85), (900, 330, 70, "payhip", 11, 0.7), (1700, 330, 76, "booth", -10, 0.7),
        (260, 1220, 200, "jinxxy", 6), (560, 1330, 120, "projects", -8), (2300, 1240, 210, "gumroad", -7),
        (2010, 1340, 110, "itch", 9), (1280, 1290, 90, "gold", 4, 0.85),
    ]
    body = (scatter(w, h, boxes)
            + f'<div class="at" style="left:1610px;top:505px">{mark(430)}</div>'
            + f'<div class="at" style="left:560px;top:530px;font-size:72px">{logo(96)}'
              f'<h1 style="margin-top:28px">{TAGLINE[0]}<br>{TAGLINE[1]}</h1>'
              f'<div style="margin-top:28px">{chips(30)}</div></div>')
    spots = [(heap.GOLD, 80, 30, 26, 30, 0x24)] + store_glow(y=96, strength=0x55, height=36)
    return page(w, h, body, glow(spots))


def discord() -> str:
    w, h = 960, 540
    boxes = [(70, 80, 64, "booth", -9), (180, 150, 40, "gumroad", 8, 0.9), (890, 90, 58, "jinxxy", 8),
             (800, 170, 36, "itch", -6, 0.9), (60, 470, 50, "projects", 6), (900, 460, 48, "payhip", -8)]
    body = (scatter(w, h, boxes)
            + f'<div class="at" style="left:50%;top:150px;transform:translateX(-50%)">{logo(140)}</div>'
            + f'<div class="at" style="left:0;right:0;top:330px;text-align:center;font-size:34px">'
              f'<h1>{html.escape(" ".join(TAGLINE))}</h1></div>')
    return page(w, h, body, glow(store_glow(strength=0x66, height=50)))


def github() -> str:
    w, h = 1280, 640
    body = (f'<div class="at" style="left:770px;top:110px">{mark(470)}</div>'
            + f'<div class="at" style="left:72px;top:70px;width:700px;font-size:60px">{logo(74)}'
              f'<h1 style="margin-top:44px">Your assets<br>and projects,<br>{TAGLINE[1]}</h1>'
              f'<p class="line" style="font-size:26px;margin-top:22px;max-width:620px">{html.escape(LINE)}</p>'
              f'<div style="margin-top:34px">{chips(21)}</div></div>')
    return page(w, h, body, glow(store_glow(strength=0x77)))


DRAW = {"vrchat-group": vrchat_group, "x-bluesky": x_bluesky, "youtube": youtube, "discord": discord, "github": github}


def guided(png: Path, safe: tuple | None, width: int, height: int) -> str:
    """The banner with its site's safe area outlined and what's outside it dimmed, to check it by eye."""
    data = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()
    if not safe:
        return f'<body style="margin:0"><img src="{data}"></body>'
    x, y, w, h = safe
    return (f'<body style="margin:0;position:relative"><img src="{data}" style="display:block">'
            f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'box-shadow:0 0 0 4000px rgb(0 0 0 / .55), inset 0 0 0 3px #00E5FF"></div></body>')


def main(argv: list[str]) -> int:
    """Draw each banner, and with --guides each with its safe area marked."""
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, draw in DRAW.items():
            width, height, safe = SIZES[name]
            tab = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            tab.set_content(draw(), wait_until="load")
            tab.evaluate("document.fonts.ready")
            out = OUT / f"hoard-banner-{name}-{width}x{height}.png"
            tab.screenshot(path=str(out), type="png")
            print(out.relative_to(REPO), out.stat().st_size)
            if "--guides" in argv:
                GUIDES.mkdir(parents=True, exist_ok=True)
                tab.set_content(guided(out, safe, width, height), wait_until="load")
                tab.screenshot(path=str(GUIDES / f"{name}-guide.png"), type="png")
            tab.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
