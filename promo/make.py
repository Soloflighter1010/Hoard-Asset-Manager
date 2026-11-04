"""Make all of Hoard's videos, posters and music in one go (issues #273, #274, #289, #291, #292).

    python3 promo/make.py PRODUCTS [OUT] [--lang=en,ja,ko] [--jobs=3]

PRODUCTS is a library of products to show, as scripts/screenshots.py takes one (a folder of pictures and its
products.json): promo/products, or your own from scripts/export_screenshot_products.py. Only the products given are
shown: nothing is made up or drawn for them. OUT (promo/out unless given) gets:

    hoard-loop.wav, .m4a, .ogg     the music
    screens/                       Hoard's own screens, in each language (promo/capture.py)
    videos/                        the videos (promo/render.py)
    posters/                       the posters (promo/posters.py)

Needs Playwright and ffmpeg. Each step is its own script, and can be run on its own.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*args: str) -> None:
    print("$ python3 " + " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], check=True)


def main(argv: list[str]) -> int:
    given = [a for a in argv if not a.startswith("--")]
    flags = [a for a in argv if a.startswith("--")]
    products = Path(given[0]) if given else HERE / "products"
    if not (products / "products.json").is_file():
        sys.exit(f"No products to show in {products}: give a folder of them (see this script's notes).")
    out = Path(given[1]) if len(given) > 1 else HERE / "out"
    out.mkdir(parents=True, exist_ok=True)
    lib = products
    run(str(HERE / "music.py"), str(out))
    run(str(HERE / "capture.py"), str(lib), str(out / "screens"), *[f for f in flags if f.startswith("--lang=")])
    run(str(HERE / "render.py"), str(out / "screens"), str(lib), str(out / "videos"), *flags)
    run(str(HERE / "posters.py"), str(out / "screens"), str(out / "posters"))
    print(f"Done: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
