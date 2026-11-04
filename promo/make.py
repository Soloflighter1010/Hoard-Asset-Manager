"""Make all of Hoard's videos, posters and music in one go (issues #273, #274, #289, #291, #292).

    python3 promo/make.py [PRODUCTS] [OUT] [--lang=en,ja,ko] [--jobs=3]

PRODUCTS is a library of products to show, as scripts/screenshots.py takes one (a folder of pictures and its
products.json): promo/products, or your own from scripts/export_screenshot_products.py, with the made-up ones
promo/art.py draws added for any store it has few of. Without it, only made-up products are shown. OUT (promo/out
unless given) gets (PRODUCTS "-": made-up ones only, with OUT given):

    hoard-loop.wav, .m4a, .ogg     the music
    screens/                       Hoard's own screens, in each language (promo/capture.py)
    videos/                        the videos (promo/render.py)
    posters/                       the posters (promo/posters.py)

Needs Playwright and ffmpeg. Each step is its own script, and can be run on its own.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PER_STORE = 4   # (a store with fewer of the products given gets made-up ones too, so every tab has something)


def run(*args: str) -> None:
    print("$ python3 " + " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], check=True)


def library(products: Path | None, out: Path) -> Path:
    """The products to show: those given, and the made-up ones for the stores they have few of."""
    drawn = out / "drawn"
    run(str(HERE / "art.py"), str(drawn))
    made_up = json.loads((drawn / "products.json").read_text("utf-8"))
    if not products:
        return drawn
    given = json.loads((products / "products.json").read_text("utf-8"))
    lib = out / "library"
    if lib.exists():
        shutil.rmtree(lib)
    lib.mkdir(parents=True)
    for folder, items in ((products, given), (drawn, made_up)):
        for i in items:
            shutil.copy2(folder / i["image"], lib / i["image"])
    count = {s: sum(1 for i in given if i["store"] == s) for s in {i["store"] for i in made_up}}
    # (never a made-up product on a wishlist beside real ones: the given products' wishlists are theirs)
    extra = [i for i in made_up if count.get(i["store"], 0) < PER_STORE and not i.get("wishlist")]
    (lib / "products.json").write_text(json.dumps(given + extra, ensure_ascii=False, indent=1), "utf-8")
    return lib


def main(argv: list[str]) -> int:
    given = [a for a in argv if not a.startswith("--")]
    flags = [a for a in argv if a.startswith("--")]
    if given and given[0] == "-":   # (made-up products only)
        products = None
    else:
        products = Path(given[0]) if given else (HERE / "products" if (HERE / "products" / "products.json").exists() else None)
    out = Path(given[1]) if len(given) > 1 else HERE / "out"
    out.mkdir(parents=True, exist_ok=True)
    lib = library(products, out)
    run(str(HERE / "music.py"), str(out))
    run(str(HERE / "capture.py"), str(lib), str(out / "screens"), *[f for f in flags if f.startswith("--lang=")])
    run(str(HERE / "render.py"), str(out / "screens"), str(lib), str(out / "videos"), *flags)
    run(str(HERE / "posters.py"), str(out / "screens"), str(out / "posters"))
    print(f"Done: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
