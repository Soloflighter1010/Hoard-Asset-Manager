"""Smaller copies of the website's screenshots: python scripts/site_images.py

The screenshots (scripts/screenshots.py, copied to site/img/<part>-<theme>.webp) are 1600 pixels wide, sharp on a
wide screen at twice the pixels, but most of that is thrown away on a phone or in the two-column tour (Lighthouse:
"Improve image delivery", 450 KB more than needed on a phone). This writes <part>-<theme>-800.webp and -1200.webp
beside each, which the pages list in srcset, so the browser takes the smallest that's still sharp. It makes the
copies that are missing; after replacing a screenshot, run it with --all. --check says whether any is missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMG = REPO / "site" / "img"
WIDTHS = (800, 1200)


def screenshots() -> list[Path]:
    """The full-size screenshots: <part>-dark.webp and <part>-light.webp."""
    return sorted(p for p in IMG.glob("*.webp") if p.stem.endswith(("-dark", "-light")))


def copy_of(shot: Path, width: int) -> Path:
    return shot.with_name(f"{shot.stem}-{width}.webp")


def main(argv: list[str]) -> int:
    stale = [copy_of(s, w) for s in screenshots() for w in WIDTHS if "--all" in argv or not copy_of(s, w).is_file()]
    if "--check" in argv:
        if stale:
            print("Missing: " + ", ".join(p.name for p in stale) + ". Run python3 scripts/site_images.py.")
            return 1
        return 0
    from PIL import Image
    for out in stale:
        shot = out.with_name(out.stem.rsplit("-", 1)[0] + ".webp")
        width = int(out.stem.rsplit("-", 1)[1])
        with Image.open(shot) as im:
            im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS).save(out, quality=82, method=6)
        print(f"{out.name}: {out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
