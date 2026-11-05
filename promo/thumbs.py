"""Make the videos' thumbnails, for YouTube: one for each video promo/build.py makes, from each film's "thumb".

    python promo/thumbs.py [FILM...] [--lang=en,ja,ko] [--shape=landscape,portrait] [--shots=build/shots]
                           [--out=build/promo/thumbs] [--draft]

With no FILM, every film in promo/films/. Make the screenshots first, as for the videos (promo/build.py says how).
Each is drawn by promo/video/thumb.html in Chromium, twice as large and then made smaller, so its edges are smooth:
build/promo/thumbs/hoard-<film>-<lang>-<shape>.jpg, named like its video. A landscape one is 1280 x 720 (YouTube's
size for a video's thumbnail); a portrait one, for a Short, 1080 x 1920. Each is under 2 MB, YouTube's limit.

Each is checked as it's drawn: one with words too long for their room, or off the picture, or a lens that cuts off
what it's about, isn't made, and this says why (and goes on to the next). --draft makes it anyway, to look at.

A film's "thumb" says which look and what it says: "short" (the Heap over Hoard's library, from "image"), "tour" (a
fan of Hoard's screens, "images", and what Hoard does, "features": the film's own words) or "help" (the problem and
a lens on the film's "scene": on a screen, its first focus or "focus"; on a drawn window, its state "state").
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import BUILD, FONTS, PROMO, REPO, grain, heap_parts, speaks   # noqa: E402

SIZES = {"landscape": (1280, 720), "portrait": (1080, 1920)}
LIMIT = 2 * 1024 * 1024   # YouTube's most for a thumbnail


def config(film: dict, lang: str, shape: str, shots: Path) -> dict:
    """What thumb.html needs: the film, the Heap, where the screenshots are, the boxes on the help look's screen, and
    the opening's words for the chips."""
    th, regions = film["thumb"], {}
    if th["look"] == "help":
        s = film["scenes"][th["scene"]]
        if s.get("image"):
            box = shots / f"{s['image']}-light{'' if lang == 'en' else '-' + lang}.json"
            if not box.is_file():
                sys.exit(f"{box} isn't there: make the screenshots with --regions=promo/regions.json first")
            regions[s["image"]] = json.loads(box.read_text("utf-8"))
    intro = next((s["text"] for s in film["scenes"] if s["type"] == "intro"), None)
    return {"film": film, "lang": lang, "shape": shape, "heap": heap_parts(), "regions": regions, "intro": intro,
            "shots": shots.resolve().as_uri()}


def make(page, name: str, lang: str, shape: str, shots: Path, out: Path, draft: bool = False) -> list[str]:
    """One thumbnail: what was wrong with it, if anything (then it isn't made)."""
    from PIL import Image
    film = json.loads((PROMO / "films" / f"{name}.json").read_text("utf-8"))
    tag = f"{name}-{lang}-{shape}"
    w, h = SIZES[shape]
    page.set_viewport_size({"width": w, "height": h})
    page.goto((PROMO / "video" / "thumb.html").as_uri())
    page.evaluate(FONTS)
    page.evaluate("cfg => window.setup(cfg)", config(film, lang, shape, shots))
    page.evaluate("Promise.all([...document.images].map(i => i.decode().catch(() => null)))")
    problems = page.evaluate("window.check()")
    if problems:
        print(f"{tag}: {'(a draft) ' if draft else 'not made: '}\n  " + "\n  ".join(problems))
        if not draft:
            return [tag]
    big = Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGB")
    img = big.resize((w, h), Image.LANCZOS)
    path = out / f"hoard-{tag}.jpg"
    for q in (92, 88, 84, 80):
        img.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if path.stat().st_size < LIMIT:
            break
    else:
        print(f"{tag}: not made: over 2 MB")
        path.unlink()
        return [tag]
    print(f"{tag}: {path} ({path.stat().st_size // 1024} KB)")
    return []


def main(argv: list[str]) -> None:
    """Every film's thumbnails (or those named), in each language and shape asked for."""
    names = [a for a in argv if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in argv if a.startswith("--"))
    names = names or sorted(p.stem for p in (PROMO / "films").glob("*.json"))
    shots = Path(opts.get("shots", REPO / "build" / "shots"))
    out = Path(opts.get("out", BUILD / "thumbs"))
    out.mkdir(parents=True, exist_ok=True)
    grain()
    from playwright.sync_api import sync_playwright
    failed = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-lcd-text", "--font-render-hinting=none"])
        page = browser.new_page(device_scale_factor=2)
        page.on("pageerror", lambda e: failed.append(f"page error: {e}"))
        for name in names:
            film = json.loads((PROMO / "films" / f"{name}.json").read_text("utf-8"))
            if "thumb" not in film:
                print(f"{name}: no thumbnail (it has no \"thumb\")")
                continue
            for lang in opts.get("lang", "en,ja,ko").split(","):
                if not speaks(film, lang):
                    print(f"{name}-{lang}: not made, its words aren't in that language yet")
                    continue
                for shape in opts.get("shape", "landscape,portrait").split(","):
                    if shape in film.get("shapes", ("landscape", "portrait")):
                        failed += make(page, name, lang, shape, shots, out, "draft" in opts)
        browser.close()
    if failed:
        sys.exit(f"Not made: {', '.join(failed)}")


if __name__ == "__main__":
    main(sys.argv[1:])
