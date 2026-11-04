"""The made-up products Hoard's videos and posters show (issues #273, #274, #292): their names, creators and stores,
and each one's picture, drawn here in SVG (shapes and gradients: no photos, no one's artwork, no diffusion or any
other generated picture). They're a library as scripts/screenshots.py takes one: a folder of pictures and its
products.json.

    python3 promo/art.py OUT_FOLDER       writes OUT_FOLDER/products.json and a PNG for each product

Needs Playwright (as the tests do), to draw the SVGs as PNGs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# (name, creator, store, kind, colours (background top, bottom, the thing's own), tags, wishlist or None)
PRODUCTS = [
    ("Kitsune Base Avatar", "Kitsu Studio", "booth", "fox", ("#FFB36B", "#E8572F", "#FFF1E0"), ["avatar"], None),
    ("Mochi Hoodie", "Mochi Works", "booth", "hoodie", ("#F7D6E6", "#C98BB9", "#FFFFFF"), ["clothing", "headwear"], None),
    ("Cat Ear Headphones", "Neko Audio", "jinxxy", "headphones", ("#8EE3EA", "#2E8FA6", "#1D2433"), ["headphones", "accessory"], None),
    ("Moon Garden", "Hoshi Lab", "booth", "world", ("#2B2E6E", "#121436", "#F6E7A1"), ["world"], None),
    ("Neon Glow Shader", "Citrus Labs", "gumroad", "shader", ("#3A1A5E", "#140A24", "#FF5FD2"), ["shader"], None),
    ("Starlit Boots", "Mochi Works", "booth", "boots", ("#C4D3FF", "#6C7FD8", "#2A2F5A"), ["clothing"], None),
    ("Sakura Wings", "Hana Atelier", "jinxxy", "wings", ("#FFE3EC", "#F49BB8", "#FFFFFF"), ["wings", "accessory"], None),
    ("Round Glasses", "Citrus Labs", "gumroad", "glasses", ("#FFE9A8", "#F2B33D", "#2A1D00"), ["eyewear", "accessory"], None),
    ("Ember Dragon Avatar", "Kitsu Studio", "jinxxy", "dragon", ("#FF8A5B", "#8E1F2F", "#FFD37A"), ["avatar"], None),
    ("Fabric Texture Pack", "Soy", "gumroad", "textures", ("#D7C7B0", "#8D7A62", "#F4EDE3"), ["textures"], None),
    ("Comfy Socks", "Ame Atelier", "payhip", "socks", ("#C9F2D0", "#5DBB72", "#FFFFFF"), ["clothing"], None),
    ("Lantern Gimmick", "Hoshi Lab", "jinxxy", "lantern", ("#3B2A4F", "#1A1226", "#FFC65C"), ["gimmick", "props"], None),
    ("Usagi Avatar", "Usagi Den", "booth", "bunny", ("#E7E1FF", "#9C8CE6", "#FFFFFF"), ["avatar"], None),
    ("Rain Room", "Ame Atelier", "payhip", "rain", ("#4C6B8A", "#1E2F44", "#BFE3FF"), ["world"], None),
    ("Pixel Props Kit", "Soy", "itch", "props", ("#B6F0A8", "#3E9A4F", "#FFFFFF"), ["props"], None),
    ("Dango Hat", "Mochi Works", "booth", "hat", ("#FFD9C2", "#E58C67", "#7A3E2B"), ["headwear", "clothing"], None),
    ("Cozy Cafe", "Kumo Works", "itch", "cafe", ("#F2D7B6", "#9A6A44", "#FFF6EA"), ["world"], None),
    ("Holo Visor", "Neko Audio", "jinxxy", "visor", ("#A8F5FF", "#5266FF", "#FFFFFF"), ["eyewear", "accessory"], None),
    # on your wishlists: not yours, with their prices (one cheaper than before)
    ("Frost Fox Avatar", "Kitsu Studio", "booth", "fox", ("#DDF4FF", "#7FB8E0", "#FFFFFF"), [],
     {"list": "Loved items", "price": ["¥3,500", 3500, "JPY"], "was": ["¥4,200", 4200, "JPY"]}),
    ("Velvet Ribbon", "Hana Atelier", "booth", "ribbon", ("#FFD0D8", "#C0394F", "#FFFFFF"), [],
     {"list": "Loved items", "price": ["¥800", 800, "JPY"]}),
    ("Crystal Earrings", "Geode Goods", "gumroad", "gem", ("#E6D6FF", "#7D4FD1", "#FFFFFF"), [],
     {"list": "Wishlist", "price": ["$12", 12, "USD"], "was": ["$15", 15, "USD"]}),
    ("Comet Tail", "Hoshi Lab", "gumroad", "tail", ("#FFE9C2", "#E8A33D", "#FFFFFF"), [],
     {"list": "Wishlist", "price": ["$9", 9, "USD"]}),
]
SETS = (("Winter outfit", ("Mochi Hoodie", "Starlit Boots", "Dango Hat", "Comfy Socks")),   # (name, its products)
        ("Night world", ("Moon Garden", "Rain Room", "Lantern Gimmick", "Cozy Cafe")),
        ("Rave look", ("Neon Glow Shader", "Round Glasses", "Cat Ear Headphones", "Holo Visor")))


def _face(c: str, ears: str, eyes: str = "#1D1A2E") -> str:
    """An animal's face: a round head, its ears and its eyes (a fox, a bunny, a dragon)."""
    return (f'{ears}<circle cx="256" cy="290" r="128" fill="{c}"/>'
            f'<circle cx="208" cy="282" r="16" fill="{eyes}"/><circle cx="304" cy="282" r="16" fill="{eyes}"/>'
            f'<circle cx="214" cy="276" r="5" fill="#fff"/><circle cx="310" cy="276" r="5" fill="#fff"/>'
            f'<ellipse cx="256" cy="330" rx="16" ry="11" fill="{eyes}"/>'
            f'<circle cx="176" cy="326" r="20" fill="#FF8FA8" opacity=".55"/><circle cx="336" cy="326" r="20" fill="#FF8FA8" opacity=".55"/>')


SHAPES = {
    "fox": lambda c: _face(c, f'<path d="M150 230 L176 96 L250 196 Z M362 230 L336 96 L262 196 Z" fill="{c}"/>'
                              '<path d="M172 200 L182 132 L224 188 Z M340 200 L330 132 L288 188 Z" fill="#FF9F7A"/>'),
    "bunny": lambda c: _face(c, f'<rect x="178" y="40" width="54" height="190" rx="27" fill="{c}"/>'
                                f'<rect x="280" y="40" width="54" height="190" rx="27" fill="{c}"/>'
                                '<rect x="192" y="62" width="26" height="140" rx="13" fill="#FFB7CB"/>'
                                '<rect x="294" y="62" width="26" height="140" rx="13" fill="#FFB7CB"/>'),
    "dragon": lambda c: _face(c, f'<path d="M180 196 L130 90 L232 176 Z M332 196 L382 90 L280 176 Z" fill="{c}"/>'
                                 '<path d="M226 168 L256 120 L286 168 Z" fill="#FF7A45"/>', "#4A1020"),
    "hoodie": lambda c: (f'<path d="M150 176 Q256 96 362 176 L408 236 L370 268 L346 246 L346 420 L166 420 L166 246 '
                         f'L142 268 L104 236 Z" fill="{c}"/><path d="M196 180 Q256 260 316 180 Q256 140 196 180 Z" '
                         'fill="#E9A9CF"/><rect x="216" y="320" width="80" height="56" rx="14" fill="#F2C2DD"/>'
                         '<line x1="236" y1="214" x2="232" y2="270" stroke="#B0679A" stroke-width="6" stroke-linecap="round"/>'
                         '<line x1="276" y1="214" x2="280" y2="270" stroke="#B0679A" stroke-width="6" stroke-linecap="round"/>'),
    "headphones": lambda c: (f'<path d="M136 300 Q136 132 256 132 Q376 132 376 300" fill="none" stroke="{c}" stroke-width="30" '
                             'stroke-linecap="round"/><path d="M150 168 L176 100 L214 150 Z M362 168 L336 100 L298 150 Z" '
                             f'fill="{c}"/><rect x="106" y="270" width="78" height="120" rx="34" fill="{c}"/>'
                             f'<rect x="328" y="270" width="78" height="120" rx="34" fill="{c}"/>'
                             '<rect x="122" y="292" width="46" height="76" rx="22" fill="#56D1DC"/>'
                             '<rect x="344" y="292" width="46" height="76" rx="22" fill="#56D1DC"/>'),
    "world": lambda c: (f'<circle cx="352" cy="150" r="62" fill="{c}"/><circle cx="376" cy="136" r="54" fill="#2B2E6E"/>'
                        + "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#FFF6CF"/>' for x, y, r in
                                  ((90, 100, 4), (150, 160, 3), (220, 80, 5), (260, 190, 3), (120, 230, 3), (430, 250, 4), (300, 110, 2)))
                        + '<path d="M0 360 Q120 280 240 350 Q360 420 512 330 L512 512 L0 512 Z" fill="#2E5B4E"/>'
                          '<path d="M0 420 Q160 360 300 420 Q420 470 512 420 L512 512 L0 512 Z" fill="#1F3F36"/>'
                          '<circle cx="150" cy="380" r="16" fill="#FFB7E0"/><circle cx="330" cy="410" r="14" fill="#FFF0A0"/>'),
    "shader": lambda c: ('<defs><radialGradient id="sh" cx=".35" cy=".3" r=".75"><stop offset="0" stop-color="#FFFFFF"/>'
                         f'<stop offset=".28" stop-color="{c}"/><stop offset="1" stop-color="#3A0F55"/></radialGradient></defs>'
                         '<ellipse cx="256" cy="430" rx="150" ry="22" fill="#000" opacity=".35"/>'
                         '<circle cx="256" cy="262" r="150" fill="url(#sh)"/>'
                         f'<circle cx="256" cy="262" r="176" fill="none" stroke="{c}" stroke-width="6" opacity=".5"/>'),
    "boots": lambda c: (f'<path d="M140 120 L230 120 L232 330 L330 360 Q360 372 360 404 L360 420 L130 420 Z" fill="{c}"/>'
                        '<rect x="130" y="404" width="232" height="24" rx="10" fill="#14172E"/>'
                        + "".join(f'<path d="M{x} {y} l6 14 15 6 -15 6 -6 14 -6 -14 -15 -6 15 -6z" fill="#FFF1A8"/>'
                                  for x, y in ((180, 170), (200, 260), (300, 380)))),
    "wings": lambda c: (f'<path d="M248 300 Q120 120 60 190 Q100 250 80 300 Q140 290 140 340 Q200 320 248 330 Z" fill="{c}"/>'
                        f'<path d="M264 300 Q392 120 452 190 Q412 250 432 300 Q372 290 372 340 Q312 320 264 330 Z" fill="{c}"/>'
                        + "".join(f'<circle cx="{x}" cy="{y}" r="12" fill="#F7A8C4"/>' for x, y in ((140, 230), (372, 230), (190, 290), (322, 290)))),
    "glasses": lambda c: (f'<circle cx="176" cy="270" r="76" fill="#FFFFFF" fill-opacity=".35" stroke="{c}" stroke-width="18"/>'
                          f'<circle cx="336" cy="270" r="76" fill="#FFFFFF" fill-opacity=".35" stroke="{c}" stroke-width="18"/>'
                          f'<path d="M238 252 Q256 232 274 252" fill="none" stroke="{c}" stroke-width="14"/>'
                          f'<line x1="100" y1="250" x2="46" y2="226" stroke="{c}" stroke-width="14" stroke-linecap="round"/>'
                          f'<line x1="412" y1="250" x2="466" y2="226" stroke="{c}" stroke-width="14" stroke-linecap="round"/>'),
    "textures": lambda c: "".join(f'<rect x="{96 + (i % 3) * 112}" y="{96 + (i // 3) * 112}" width="100" height="100" rx="18" '
                                  f'fill="{col}"/>' for i, col in enumerate(("#C9B79C", "#8D7A62", "#E8DCCB", "#6F5B45", c,
                                                                             "#B19A7A", "#D9C8AE", "#9C866A", "#7E6A52"))),
    "socks": lambda c: (f'<path d="M150 90 L230 90 L230 300 Q230 380 170 400 Q110 410 100 360 Q96 320 150 300 Z" fill="{c}"/>'
                        f'<path d="M282 110 L362 110 L362 320 Q362 400 302 420 Q242 430 232 380 Q228 340 282 320 Z" fill="{c}"/>'
                        '<rect x="150" y="90" width="80" height="40" fill="#5DBB72"/><rect x="282" y="110" width="80" height="40" fill="#5DBB72"/>'),
    "lantern": lambda c: ('<line x1="256" y1="60" x2="256" y2="130" stroke="#C9A86B" stroke-width="8"/>'
                          f'<circle cx="256" cy="290" r="150" fill="{c}" opacity=".18"/>'
                          f'<rect x="186" y="140" width="140" height="240" rx="56" fill="{c}"/>'
                          '<rect x="176" y="126" width="160" height="26" rx="10" fill="#7A4E1E"/>'
                          '<rect x="176" y="370" width="160" height="26" rx="10" fill="#7A4E1E"/>'
                          '<path d="M256 200 Q296 260 256 320 Q216 260 256 200 Z" fill="#FFF3C4"/>'),
    "rain": lambda c: ('<rect x="120" y="110" width="272" height="260" rx="18" fill="#9EC3E6" opacity=".35" stroke="#D8ECFF" stroke-width="10"/>'
                       '<line x1="256" y1="110" x2="256" y2="370" stroke="#D8ECFF" stroke-width="8"/>'
                       '<line x1="120" y1="240" x2="392" y2="240" stroke="#D8ECFF" stroke-width="8"/>'
                       + "".join(f'<line x1="{x}" y1="{y}" x2="{x - 8}" y2="{y + 26}" stroke="{c}" stroke-width="5" stroke-linecap="round"/>'
                                 for x, y in ((150, 140), (200, 190), (300, 150), (350, 210), (170, 280), (320, 300), (230, 320)))
                       + '<rect x="96" y="390" width="320" height="40" rx="14" fill="#2C4258"/>'),
    "props": lambda c: ('<rect x="110" y="250" width="130" height="130" fill="#F2C14E"/><rect x="110" y="250" width="130" height="30" fill="#D9A441"/>'
                        '<rect x="270" y="190" width="130" height="190" fill="#4E9AF2"/><rect x="270" y="190" width="130" height="30" fill="#3E7CC4"/>'
                        f'<rect x="190" y="130" width="110" height="110" fill="{c}"/><rect x="190" y="130" width="110" height="26" fill="#D8F5D0"/>'),
    "hat": lambda c: (f'<ellipse cx="256" cy="350" rx="180" ry="44" fill="{c}"/><path d="M146 350 Q150 170 256 160 Q362 170 366 350 Z" fill="{c}"/>'
                      '<rect x="150" y="300" width="212" height="34" fill="#F7E0D2"/>'
                      + "".join(f'<circle cx="{x}" cy="128" r="26" fill="{col}"/>' for x, col in ((206, "#FFB3C7"), (256, "#FFF4E8"), (306, "#A8E6A1")))
                      + '<line x1="190" y1="128" x2="322" y2="128" stroke="#8A5A3A" stroke-width="6"/>'),
    "cafe": lambda c: (f'<path d="M150 230 L362 230 L340 400 Q256 430 172 400 Z" fill="{c}"/>'
                       '<path d="M362 260 Q430 270 410 330 Q392 370 346 360" fill="none" stroke="#FFF6EA" stroke-width="20"/>'
                       '<ellipse cx="256" cy="232" rx="106" ry="18" fill="#7A4E2E"/>'
                       '<path d="M220 200 Q200 160 230 130 Q250 110 236 80 M290 200 Q270 160 300 130 Q320 110 306 80" fill="none" '
                       'stroke="#FFF6EA" stroke-width="10" stroke-linecap="round" opacity=".8"/>'),
    "visor": lambda c: ('<path d="M96 240 Q256 150 416 240 L400 320 Q256 360 112 320 Z" fill="#14172E"/>'
                        f'<path d="M126 248 Q256 176 386 248 L374 306 Q256 338 138 306 Z" fill="{c}" opacity=".85"/>'
                        '<path d="M150 250 Q256 200 360 250" fill="none" stroke="#FFFFFF" stroke-width="8" opacity=".7"/>'),
    "ribbon": lambda c: (f'<path d="M256 250 L120 160 Q100 250 120 340 Z" fill="{c}"/><path d="M256 250 L392 160 Q412 250 392 340 Z" fill="{c}"/>'
                         '<path d="M240 260 L190 420 L230 400 L256 440 L256 270 Z M272 260 L322 420 L282 400 L256 440 L256 270 Z" fill="#9C2B3E"/>'
                         '<circle cx="256" cy="250" r="34" fill="#FFE1E6"/>'),
    "gem": lambda c: (f'<path d="M180 160 L332 160 L392 230 L256 420 L120 230 Z" fill="{c}"/>'
                      '<path d="M180 160 L220 230 L256 160 L292 230 L332 160 M120 230 L392 230 M220 230 L256 420 L292 230" '
                      'fill="none" stroke="#5A2FB0" stroke-width="6" stroke-linejoin="round"/>'),
    "tail": lambda c: (f'<path d="M120 420 Q90 260 230 200 Q330 160 360 80 Q420 200 360 290 Q300 380 120 420 Z" fill="{c}"/>'
                       '<path d="M360 80 Q400 150 380 210 Q350 170 340 120 Z" fill="#FFF8E6"/>'),
}


def svg(kind: str, colours: tuple) -> str:
    """A product's picture: its thing on a soft gradient, 512 x 512."""
    top, bottom, own = colours
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
            f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
            f'<stop offset="1" stop-color="{bottom}"/></linearGradient></defs><rect width="512" height="512" fill="url(#bg)"/>'
            f'<circle cx="420" cy="80" r="120" fill="#FFFFFF" opacity=".10"/><circle cx="70" cy="470" r="140" fill="#000000" opacity=".08"/>'
            f'{SHAPES[kind](own)}</svg>')


def slug(name: str) -> str:
    """A file name for a product's picture."""
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")


def main(argv: list[str]) -> int:
    """Draw every product's picture, and write products.json."""
    from playwright.sync_api import sync_playwright
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    listed = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 512, "height": 512})
        for name, creator, store, kind, colours, tags, wish in PRODUCTS:
            page.set_content(f'<body style="margin:0">{svg(kind, colours)}</body>')
            page.screenshot(path=str(out / f"{slug(name)}.png"), clip={"x": 0, "y": 0, "width": 512, "height": 512})
            listed.append({"image": f"{slug(name)}.png", "name": name, "creator": creator, "store": store, "tags": tags,
                           **({"wishlist": wish} if wish else {})})
        browser.close()
    (out / "products.json").write_text(json.dumps(listed, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(listed)} products in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
