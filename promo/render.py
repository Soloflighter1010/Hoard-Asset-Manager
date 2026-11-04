"""Film Hoard's videos (issues #273, #274, #289): promo/player.html drawn frame by frame in Chromium (Playwright), each
frame handed to ffmpeg, with the looping track (promo/music.py) under it, faded out at the end. Nothing generated:
Hoard's own screens, the Heap, words and shapes drawn in code.

    python3 promo/render.py SCREENS LIBRARY OUT [--only=promo-short,troubleshooting-pin] [--lang=en] [--layout=landscape]
                            [--fps=30] [--check]

SCREENS is promo/capture.py's folder, LIBRARY the products it was given (for the sketch's tabs and the credits), OUT
where the videos go: <video>-<layout>-<lang>.mp4 (a video in one layout only leaves its layout out). --check draws one
frame of each scene as a PNG instead, to look over.

The Japanese words use the fonts Hoard has (Dela Gothic One, Zen Maru Gothic); the Korean ones Black Han
Sans and Gowun Dodum, from Google Fonts (just the letters the videos use), kept in OUT/fonts. All are under the SIL
Open Font License.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import scenes  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KOREAN = (("Black Han Sans", 400), ("Gowun Dodum", 400))


def _all_words(lang: str) -> str:
    """Every word the videos and posters say in lang (for the letters a font needs)."""
    bits = []

    def walk(v):
        if isinstance(v, dict):
            if lang in v and isinstance(v[lang], str):
                bits.append(scenes.say(v, lang))
            else:
                for x in v.values():
                    walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    for _, make, _, _ in scenes.videos():
        walk(make())
    walk(scenes.POSTERS)
    walk([scenes.CREDITS, scenes.CREDITS_NOTE, scenes.FREE, scenes.GET])
    from hoard import themes
    bits += [scenes.ui(lang, w) for w in ("Theme", "Style", "Dark", "Light", "Standard", "Treasure", "Workbench")]
    bits += [scenes.ui(lang, t["name"]) for t in themes.THEMES.values()]
    return "".join(bits)


def _korean_css(out: Path) -> str:
    """The Korean fonts, with just the letters the videos use, downloaded once into OUT/fonts."""
    text = "".join(sorted(set(re.sub(r"<[^>]+>", "", _all_words("ko")) + "0123456789")))
    key = hashlib.sha256(text.encode()).hexdigest()[:12]
    folder = out / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    css = []
    for family, weight in KOREAN:
        file = folder / f"{family.replace(' ', '')}-{key}.woff2"
        if not file.exists():
            q = urllib.parse.urlencode({"family": f"{family}:wght@{weight}", "text": text})
            req = urllib.request.Request(f"https://fonts.googleapis.com/css2?{q}", headers={"User-Agent": UA})
            sheet = urllib.request.urlopen(req, timeout=30).read().decode()
            url = re.search(r"url\((https://[^)]+)\)", sheet).group(1)
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()
            file.write_bytes(data)
        css.append(f"@font-face {{ font-family: '{family}'; font-weight: {weight}; src: url('{file.resolve().as_uri()}') format('woff2'); }}")
    return "\n".join(css)


def fonts_css(out: Path) -> str:
    """The fonts' @font-face rules: the website's, and the Korean ones."""
    f = REPO / "hoard" / "web" / "fonts"   # (the app's: with their Japanese letters, as the website's aren't)
    css = [f"@font-face {{ font-family: 'Dela Gothic One'; font-weight: 400; src: url('{(f / 'DelaGothicOne-Regular.woff2').as_uri()}') format('woff2'); }}",
           f"@font-face {{ font-family: 'Zen Maru Gothic'; font-weight: 500; src: url('{(f / 'ZenMaruGothic-Medium.woff2').as_uri()}') format('woff2'); }}",
           f"@font-face {{ font-family: 'Zen Maru Gothic'; font-weight: 700; src: url('{(f / 'ZenMaruGothic-Bold.woff2').as_uri()}') format('woff2'); }}"]
    try:
        css.append(_korean_css(out))
    except OSError as e:   # (offline: Korean falls back to the system's fonts)
        print(f"The Korean fonts couldn't be downloaded ({e}); using the system's")
    return "\n".join(css)


def player(out: Path) -> Path:
    """The player, with its fonts, beside the videos."""
    page = out / ".player.html"
    page.write_text((HERE / "player.html").read_text("utf-8").replace("/*FONTS*/", fonts_css(out)), "utf-8")
    return page


def music(out: Path) -> Path:
    """The looping track (made once)."""
    wav = out / "hoard-loop.wav"
    if not wav.exists():
        import music as m
        m.main([str(out)])
    return wav


def open_page(browser, page_file: Path, video: dict, scale: float = 1):
    """A page with the video loaded, and its length."""
    page = browser.new_page(viewport={"width": video["w"], "height": video["h"]}, device_scale_factor=scale)
    page.goto(page_file.as_uri())
    total = page.evaluate("v => load(v)", video)
    page.evaluate("t => draw(t)", 0)
    return page, total


def film(browser, page_file: Path, video: dict, wav: Path, dest: Path, fps: int) -> None:
    """One video: every frame drawn and photographed, into ffmpeg with the music."""
    page, total = open_page(browser, page_file, video)
    frames = round(total * fps)
    fade = min(2.5, total / 6)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
           "-stream_loop", "-1", "-i", str(wav),
           "-filter_complex", f"[1:a]atrim=0:{total:.3f},afade=t=in:d=0.4,afade=t=out:st={total - fade:.3f}:d={fade:.3f}[a]",
           "-map", "0:v", "-map", "[a]", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(fps),
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dest)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(frames):
            page.evaluate("t => draw(t)", i / fps)
            ff.stdin.write(page.screenshot(type="jpeg", quality=93))
    finally:
        ff.stdin.close()
        ff.wait()
        page.close()
    if ff.returncode:
        raise RuntimeError(f"ffmpeg failed on {dest.name}")


def check(browser, page_file: Path, video: dict, dest: Path) -> None:
    """One frame from the middle of each scene, side by side, to look over."""
    page, total = open_page(browser, page_file, video)
    at = 0.0
    for k, s in enumerate(video["shots"]):
        page.evaluate("t => draw(t)", at + s["dur"] * 0.62)
        page.screenshot(path=str(dest.with_name(f"{dest.stem}-{k:02d}.png")))
        at += s["dur"]
    page.close()


def main(argv: list[str]) -> int:
    from playwright.sync_api import sync_playwright
    given = [a for a in argv if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in argv if a.startswith("--"))
    if len(given) < 3:
        sys.exit(__doc__)
    screens, library, out = (Path(x) for x in given[:3])
    out.mkdir(parents=True, exist_ok=True)
    only = set(opts["only"].split(",")) if opts.get("only") else None
    langs = set(opts["lang"].split(",")) if opts.get("lang") else None
    layouts = set(opts["layout"].split(",")) if opts.get("layout") else None
    fps = int(opts.get("fps", 30))
    if not shutil.which("ffmpeg") and "check" not in opts:
        sys.exit("ffmpeg is needed")
    page_file = player(out)
    wav = None if "check" in opts else music(out)
    made = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, make, video_layouts, video_langs in scenes.videos():
            if only and name not in only:
                continue
            for layout in video_layouts:
                if layouts and layout not in layouts:
                    continue
                for lang in video_langs:
                    if langs and lang not in langs:
                        continue
                    video = scenes.build(make(), lang, layout, screens, library)
                    stem = f"{name}-{layout}-{lang}" if len(video_layouts) > 1 else f"{name}-{lang}"
                    if "check" in opts:
                        check(browser, page_file, video, out / f"{stem}.png")
                    else:
                        film(browser, page_file, video, wav, out / f"{stem}.mp4", fps)
                    made.append(stem)
                    print(stem, flush=True)
        browser.close()
    print(f"{len(made)} made, in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
