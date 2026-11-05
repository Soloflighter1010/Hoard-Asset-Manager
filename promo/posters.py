"""Make Hoard's posters (issue #292): square, 2048 x 2048 (the most VRChat's poster frames take, and fine for social
sites), from promo/posters.json, in English, Japanese and Korean.

    python promo/posters.py [POSTER...] [--lang=en,ja,ko] [--shots=build/shots] [--out=build/promo/posters] [--draft]

With no POSTER, every one in promo/posters.json. Make the screenshots first, as for the videos (promo/build.py says
how). Each is drawn by promo/video/still.html, as the thumbnails are: build/promo/posters/hoard-poster-<name>-<lang>.jpg.

A poster's words are the films' own, so they're said the same way everywhere and in every language: the main one
("hero") has the short promo's opening and end card (what Hoard is, the stores, where to get it); each of the others
("feature") is one of the long promo's screens ("scene"), with its name, title and words, its screen ringed round
"box", and a lens on "lens" (a thing on it, or several together; null: none). The fine print says whose the products shown are, and that Hoard isn't the
stores' or VRChat's.

Each is checked as it's drawn: words too long for their room, anything off the poster, a lens over what it shows or
over the words, and it isn't made (--draft makes it anyway, to look at).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import BUILD, PROMO, REPO, grain, heap_parts   # noqa: E402
from thumbs import draw, regions   # noqa: E402

LIMIT = 8 * 1024 * 1024   # (VRChat's image loader takes up to 2048 x 2048; the file just needn't be huge)


def film(name: str) -> dict:
    return json.loads((PROMO / "films" / f"{name}.json").read_text("utf-8"))   # one of promo/films/


def words(poster: dict) -> dict:
    """A poster's words in each language, from the films: {"en": {...}, "ja": {...}, "ko": {...}}."""
    short, long = film("promo-short"), film("promo-long")
    intro = next(s["text"] for s in short["scenes"] if s["type"] == "intro")
    end = next(s["text"] for s in short["scenes"] if s["type"] == "end")
    out = {}
    for lang in ("en", "ja", "ko"):
        if poster["look"] == "hero":   # (no product shows on it: only that Hoard isn't the stores' or VRChat's)
            i, e = intro[lang], end[lang]
            out[lang] = {"tagline": i["tagline"], "chip": i["chip"], "projectsChip": i["projectsChip"], "tag": i["tag"],
                         "line": e["line"], "platforms": e["platforms"], "fine": e["fine"].split("\n")[-1]}
        else:
            t = long["scenes"][poster["scene"]]["text"][lang]
            out[lang] = {"kicker": t["kicker"], "title": t["title"], "body": t["body"], "fine": end[lang]["fine"]}
    return out


def config(poster: dict, site: str, lang: str, shots: Path) -> dict:
    """What still.html needs: the poster (its screen, and its words), the Heap, and where the screenshots are."""
    p = {**poster, "site": site, "text": words(poster)}
    boxes = {}
    if poster["look"] == "feature":
        p["image"] = film("promo-long")["scenes"][poster["scene"]]["image"]
        boxes[p["image"]] = regions(p["image"], "dark", lang, shots)
    return {"poster": p, "lang": lang, "shape": "square", "heap": heap_parts(), "regions": boxes,
            "shots": shots.resolve().as_uri()}


def main(argv: list[str]) -> None:
    """Every poster (or those named), in each language asked for."""
    spec = json.loads((PROMO / "posters.json").read_text("utf-8"))
    names = [a for a in argv if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in argv if a.startswith("--"))
    shots = Path(opts.get("shots", REPO / "build" / "shots"))
    out = Path(opts.get("out", BUILD / "posters"))
    out.mkdir(parents=True, exist_ok=True)
    grain()
    from playwright.sync_api import sync_playwright
    failed, size = [], (spec["size"], spec["size"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-lcd-text", "--font-render-hinting=none"])
        page = browser.new_page(device_scale_factor=2)
        page.on("pageerror", lambda e: failed.append(f"page error: {e}"))
        for poster in spec["posters"]:
            if names and poster["name"] not in names:
                continue
            for lang in opts.get("lang", "en,ja,ko").split(","):
                tag = f"poster-{poster['name']}-{lang}"
                failed += draw(page, config(poster, spec["site"], lang, shots), tag, (1080, 1080), size,
                               out / f"hoard-{tag}.jpg", "draft" in opts, LIMIT)
        browser.close()
    if failed:
        sys.exit(f"Not made: {', '.join(failed)}")


if __name__ == "__main__":
    main(sys.argv[1:])
