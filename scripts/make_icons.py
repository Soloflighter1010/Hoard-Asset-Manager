"""The apps' icons and the favicons, from the Heap (hoard/heap.py, issue #280): drawn in Chromium at each size and put
together by hand, as each kind of file holds them (PNG pictures inside, which Windows, macOS and browsers all read).

    python3 scripts/make_icons.py

writes packaging/icons/hoard-128.png, -256.png and -512.png (Linux's, the Flatpak's), packaging/hoard.ico (Windows:
16 to 256), packaging/hoard.icns (macOS: 16 to 1024, with its table of contents), the website's and the VCC
listing's favicon.ico (64), the VCC listing's banner (Website/banner.png: the logo, "for Unity" and a line
under it, in the site's fonts), and Hoard for Unity's logo (its Look.cs, as base64: the package ships code only). The
files are kept in the repository: run it after the logo changes. Needs Playwright (as the tests do); with Pillow
too, Hoard for Unity's logo is made smaller, in 64 colours.
"""
from __future__ import annotations

import base64
import io
import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from hoard import heap  # noqa: E402

LOOK = REPO / "Packages" / "soloflighter.hoard" / "Editor" / "Look.cs"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS = (("ic11", 32), ("ic12", 64), ("ic07", 128), ("ic13", 256), ("ic08", 256), ("ic14", 512), ("ic09", 512), ("ic10", 1024))


def ico(pictures: dict[int, bytes]) -> bytes:
    """A Windows icon of these PNGs, by size (each its own entry: 256 is written as 0)."""
    sizes = sorted(pictures)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    at, entries, data = 6 + 16 * len(sizes), b"", b""
    for s in sizes:
        png = pictures[s]
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), at + len(data))
        data += png
    return head + entries + data


def icns(pictures: dict[int, bytes]) -> bytes:
    """A macOS icon of these PNGs (ICNS's types for each size), with its table of contents first."""
    parts = [(kind.encode(), pictures[size]) for kind, size in ICNS]
    toc = b"TOC " + struct.pack(">I", 8 + 8 * len(parts)) + b"".join(k + struct.pack(">I", 8 + len(d)) for k, d in parts)
    body = toc + b"".join(k + struct.pack(">I", 8 + len(d)) + d for k, d in parts)
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def banner_page() -> str:
    """The VCC listing's banner, as a page: the logo, a line, "for Unity" and what it is, on the site's cave."""
    font = lambda name: base64.b64encode((REPO / "site" / "fonts" / f"{name}.woff2").read_bytes()).decode()  # noqa: E731
    return f"""<!doctype html><html><head><style>
@font-face {{ font-family: Dela; src: url(data:font/woff2;base64,{font("DelaGothicOne-Regular")}); }}
@font-face {{ font-family: Zen; font-weight: 500; src: url(data:font/woff2;base64,{font("ZenMaruGothic-Medium")}); }}
html, body {{ margin: 0; width: 1280px; height: 256px; overflow: hidden; }}
body {{ display: flex; align-items: center; gap: 56px; padding: 0 80px; box-sizing: border-box;
  background: radial-gradient(ellipse 70% 140% at 100% 0%, #3A2C20, transparent 70%), #211C18; color: #F4EDE3; }}
.logo svg {{ width: 290px; height: auto; display: block; }}
.line {{ width: 2px; height: 120px; background: #4A4037; }}
h1 {{ margin: 0; font: 54px Dela, sans-serif; }} p {{ margin: 10px 0 0; font: 500 20px Zen, sans-serif; color: #D9CFC2; }}
</style></head><body><div class="logo">{heap.logo(words="#F4EDE3")}</div><div class="line"></div>
<div><h1>for Unity</h1><p>Your downloaded VRChat assets, inside Unity.</p></div></body></html>"""


def fewer_colours(png: bytes) -> bytes:
    """A PNG in 64 colours (its see-through edges kept), with Pillow; as it is without."""
    try:
        from PIL import Image
    except ImportError:
        return png
    out = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGBA").quantize(64, method=Image.Quantize.FASTOCTREE).save(out, "PNG", optimize=True)
    return out.getvalue()


def unity_logos(page) -> None:
    """Hoard for Unity's logo (Look.cs's LogoDarkPng and LogoLightPng): the logo at twice its size, 452 x 128, the
    word in Bone (Unity's dark skin) or the cave's ink (its light one), written into Look.cs as base64."""
    text = LOOK.read_text("utf-8")
    for name, words in (("LogoDarkPng", "#F4EDE3"), ("LogoLightPng", heap.CAVE)):
        page.set_viewport_size({"width": 452, "height": 128})
        svg = heap.logo(words=words).replace("<svg ", '<svg width="452" height="128" ', 1)
        page.set_content(f'<body style="margin:0;background:transparent">{svg}</body>')
        png = fewer_colours(page.screenshot(clip={"x": 0, "y": 0, "width": 452, "height": 128}, omit_background=True))
        text, n = re.subn(rf'(const string {name} = ")[^"]*(")', lambda m: m[1] + base64.b64encode(png).decode() + m[2], text)
        if n != 1:
            raise SystemExit(f"Look.cs has no {name} to write")
    LOOK.write_text(text, "utf-8")


def main() -> int:
    """Draw the icons and the banner, and write them."""
    from playwright.sync_api import sync_playwright
    sizes = sorted({*ICO_SIZES, *(s for _k, s in ICNS), 512})
    pictures: dict[int, bytes] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for s in sizes:
            page.set_viewport_size({"width": s, "height": s})
            page.set_content(f'<body style="margin:0;background:transparent">{heap.mark(size=s)}</body>')
            pictures[s] = page.screenshot(clip={"x": 0, "y": 0, "width": s, "height": s}, omit_background=True)
        page.set_viewport_size({"width": 1280, "height": 256})
        page.set_content(banner_page())
        page.evaluate("document.fonts.ready")
        (REPO / "Website" / "banner.png").write_bytes(page.screenshot(clip={"x": 0, "y": 0, "width": 1280, "height": 256}))
        unity_logos(page)
        browser.close()
    for s in (128, 256, 512):
        (REPO / "packaging" / "icons" / f"hoard-{s}.png").write_bytes(pictures[s])
    (REPO / "packaging" / "hoard.ico").write_bytes(ico({s: pictures[s] for s in ICO_SIZES}))
    (REPO / "packaging" / "hoard.icns").write_bytes(icns(pictures))
    for where in ("site", "Website"):
        (REPO / where / "favicon.ico").write_bytes(ico({64: pictures[64]}))
    print("Icons, favicons, the listing's banner and Hoard for Unity's logo written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
