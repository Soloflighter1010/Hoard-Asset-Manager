"""The Tauri build's Windows installer art (shell/tauri.conf.json's NSIS settings): its sidebar, on the welcome and
finish pages, and its header, on the others, drawn in Chromium from the Heap (hoard/heap.py) and the site's fonts, as
scripts/make_icons.py draws the VCC listing's banner.

    python3 scripts/make_installer_art.py [CHROMIUM]

writes shell/installer/sidebar.bmp (164 x 314) and shell/installer/header.bmp (150 x 57), the sizes NSIS shows them
at: each drawn twice as large and made smaller, for smooth edges. CHROMIUM is a Chromium program to draw with, when
Playwright has none of its own. Needs Playwright and Pillow. The files are kept in the repository: run it after the
logo changes.
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from hoard import heap

OUT = REPO / "shell" / "installer"
SIDEBAR, HEADER = (164, 314), (150, 57)
SCALE = 2
# The wordmark's paths sit where the logo has them, right of the Heap: the sidebar's own wordmark is cut to them.
FIT = """async () => {
  await document.fonts.ready;
  for (const svg of document.querySelectorAll('.word svg')) {
    const b = svg.getBBox();
    svg.setAttribute('viewBox', `${b.x} ${b.y} ${b.width} ${b.height}`);
  }
}"""


def font(name: str) -> str:
    """One of the site's fonts, as a data address."""
    return "data:font/woff2;base64," + base64.b64encode((REPO / "site" / "fonts" / f"{name}.woff2").read_bytes()).decode()


def sidebar_page() -> str:
    """The sidebar: the Heap large on the site's cave, the wordmark, and what Hoard is, low down."""
    w, h = SIDEBAR
    return f"""<!doctype html><html><head><style>
@font-face {{ font-family: Zen; font-weight: 500; src: url({font("ZenMaruGothic-Medium")}); }}
html, body {{ margin: 0; width: {w}px; height: {h}px; overflow: hidden; }}
body {{ position: relative; color: #F4EDE3; font: 500 11px/1.45 Zen, sans-serif;
  background: radial-gradient(ellipse 120% 70% at 50% 18%, #4A3726, transparent 72%),
              radial-gradient(ellipse 90% 50% at 100% 100%, #2E2A40, transparent 70%), #211C18; }}
.mark {{ position: absolute; left: 0; right: 0; top: 46px; display: flex; justify-content: center; }}
.mark svg {{ width: 104px; height: 104px; display: block; }}
.word {{ position: absolute; left: 0; right: 0; top: 160px; display: flex; justify-content: center; }}
.word svg {{ width: 108px; height: auto; display: block; }}
.word svg * {{ fill: #F4EDE3; }}
.line {{ position: absolute; left: 22px; right: 22px; bottom: 74px; height: 1px; background: #4A4037; }}
p {{ position: absolute; left: 22px; right: 22px; bottom: 22px; margin: 0; color: #D9CFC2; }}
</style></head><body>
<div class="mark">{heap.mark()}</div>
<div class="word"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 226 64">{heap.word()}</svg></div>
<div class="line"></div>
<p>Your VRChat assets<br>and Unity projects,<br>in one place.</p>
</body></html>"""


def header_page() -> str:
    """The header: the logo, on the white the installer's header has (to the left of each page's title)."""
    w, h = HEADER
    return f"""<!doctype html><html><head><style>
html, body {{ margin: 0; width: {w}px; height: {h}px; overflow: hidden; background: #FFFFFF; }}
body {{ display: flex; align-items: center; justify-content: center; }}
svg {{ width: 112px; height: auto; display: block; }}
</style></head><body>{heap.logo(words="#211C18")}</body></html>"""


def main(argv: list[str]) -> int:
    """Draw both, and write them as the 24-bit BMPs NSIS takes."""
    from PIL import Image
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=argv[0]) if argv else p.chromium.launch()
        page = browser.new_page(device_scale_factor=SCALE)
        for name, (w, h), html in (("sidebar", SIDEBAR, sidebar_page()), ("header", HEADER, header_page())):
            page.set_viewport_size({"width": w, "height": h})
            page.set_content(html)
            page.evaluate(FIT)
            shot = Image.open(io.BytesIO(page.screenshot(clip={"x": 0, "y": 0, "width": w, "height": h})))
            shot.convert("RGB").resize((w, h), Image.LANCZOS).save(OUT / f"{name}.bmp", "BMP")
        browser.close()
    print(f"Written: {OUT / 'sidebar.bmp'} and {OUT / 'header.bmp'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
