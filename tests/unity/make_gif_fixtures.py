"""Make tests/unity/gifs/: GIFs for the Unity package's GIF decoder (Editor/Core/GifDecoder.cs), and what a browser
shows for each frame, for CoreTests.cs to compare against.

Run by hand only when the fixtures need changing (needs Pillow, which Hoard doesn't use, and Playwright's Chromium):
    python tests/unity/make_gif_fixtures.py
The pictures are made by Pillow, not by Hoard's own code, and the expected frames come from Chromium's own decoder
(WebCodecs ImageDecoder), so the test checks the decoder against a real browser.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "gifs"


def frames_anim() -> None:
    """Three frames, transparency, a frame that clears itself (disposal 2), and delays of 0, 50 and 300 ms."""
    size = (40, 30)
    frames = []
    for n, colour in enumerate([(255, 0, 0), (0, 160, 255), (40, 200, 40)]):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        for y in range(size[1]):
            for x in range(size[0]):
                if (x + y + n * 7) % 5 and x > n * 6:
                    im.putpixel((x, y), colour + (255,))
        frames.append(im)
    frames[0].save(OUT / "anim.gif", save_all=True, append_images=frames[1:], duration=[0, 50, 300], loop=0,
                   disposal=[1, 2, 1], optimize=False)


def frames_restore() -> None:
    """Frames drawn in part of the picture, one restoring what was there before it (disposal 3)."""
    base = Image.new("RGB", (32, 32), (250, 250, 250))
    frames = [base]
    for n in range(4):
        im = base.copy()
        for y in range(8 + n * 4, 20 + n * 2):
            for x in range(4 + n * 5, 14 + n * 5):
                im.putpixel((x, y), (30 * n, 255 - 40 * n, 90))
        frames.append(im)
    frames[0].save(OUT / "restore.gif", save_all=True, append_images=frames[1:], duration=80, loop=0,
                   disposal=[1, 3, 1, 3, 2], optimize=True)


def interlaced() -> None:
    im = Image.new("RGB", (33, 17))
    for y in range(17):
        for x in range(33):
            im.putpixel((x, y), ((x * 7) % 256, (y * 15) % 256, ((x ^ y) * 9) % 256))
    im.convert("P", palette=Image.Palette.ADAPTIVE, colors=64).save(OUT / "interlaced.gif", interlace=True)


def noisy() -> None:
    """256 colours of noise: codes up to 12 bits, and a full code table."""
    rnd = random.Random(51)
    im = Image.new("P", (160, 120))
    im.putpalette([rnd.randrange(256) for _ in range(768)])
    im.putdata([rnd.randrange(256) for _ in range(160 * 120)])
    im.save(OUT / "noisy.gif")


BROWSER_FRAMES_JS = """async (b64) => {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const dec = new ImageDecoder({ data: bytes, type: "image/gif" });
  await dec.tracks.ready;
  await dec.completed;
  const count = dec.tracks.selectedTrack.frameCount, out = [];
  for (let i = 0; i < count; i++) {
    const { image } = await dec.decode({ frameIndex: i });
    const c = new OffscreenCanvas(image.displayWidth, image.displayHeight);
    const g = c.getContext("2d");
    g.drawImage(image, 0, 0);
    const px = g.getImageData(0, 0, c.width, c.height).data;
    let s = "";
    for (let j = 0; j < px.length; j += 8192) s += String.fromCharCode.apply(null, px.subarray(j, j + 8192));
    out.push({ w: c.width, h: c.height, ms: Math.round((image.duration || 0) / 1000), rgba: btoa(s) });
    image.close();
  }
  return out;
}"""


def main() -> None:
    OUT.mkdir(exist_ok=True)
    frames_anim()
    frames_restore()
    interlaced()
    noisy()
    expected = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        # ImageDecoder is only on secure pages: a stand-in https page, served here
        page.route("https://gifs.test/", lambda route: route.fulfill(body="<!doctype html><title>gifs</title>", content_type="text/html"))
        page.goto("https://gifs.test/")
        for gif in sorted(OUT.glob("*.gif")):
            got = page.evaluate(BROWSER_FRAMES_JS, base64.b64encode(gif.read_bytes()).decode())
            rows = []
            for f in got:
                rgba = base64.b64decode(f["rgba"])
                # a fully transparent pixel is only "transparent": its colour doesn't matter (and canvases drop it)
                norm = bytearray(rgba)
                for i in range(0, len(norm), 4):
                    if norm[i + 3] == 0:
                        norm[i:i + 4] = b"\0\0\0\0"
                rows.append({"width": f["w"], "height": f["h"], "ms": f["ms"], "sha256": hashlib.sha256(bytes(norm)).hexdigest()})
            expected[gif.name] = rows
        browser.close()
    (OUT / "expected.json").write_text(json.dumps(expected, indent=1, sort_keys=True) + "\n", "utf-8")
    for name, rows in expected.items():
        print(name, len(rows), "frames", rows[0]["width"], "x", rows[0]["height"], [r["ms"] for r in rows])


if __name__ == "__main__":
    main()
