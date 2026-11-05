"""Hoard's posters, for VRChat worlds' poster frames (issue #292): the Heap and its name, what Hoard is, a few
points, Hoard's own screen and where to get it, drawn by promo/player.html and photographed. Portrait (1080 x 1920)
and landscape (1920 x 1080), in English, Japanese and Korean, at twice that size. No diffusion: Hoard's screens,
shapes and words.

    python3 promo/posters.py SCREENS OUT

SCREENS is promo/capture.py's folder. OUT gets <poster>-<layout>-<lang>.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render  # noqa: E402
import scenes  # noqa: E402


def main(argv: list[str]) -> int:
    from playwright.sync_api import sync_playwright
    if len(argv) < 2:
        sys.exit(__doc__)
    screens, out = Path(argv[0]), Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    page_file = render.player(out)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for poster in scenes.POSTERS:
            for layout in ("portrait", "landscape"):
                for lang in scenes.LANGS:
                    video = scenes.build_poster(poster, lang, layout, screens)
                    page, _ = render.open_page(browser, page_file, video, scale=2)
                    page.evaluate("t => draw(t)", 0.5)
                    dest = out / f"{poster['name']}-{layout}-{lang}.png"
                    page.screenshot(path=str(dest))
                    page.close()
                    print(dest.name, flush=True)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
