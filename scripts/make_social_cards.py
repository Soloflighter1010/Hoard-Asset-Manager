"""The pictures a link to the website shows (Discord, X, Bluesky, messages): one card for each page, drawn as the app
looks, with the page's name on it. Hoard's logo, the page's tab, its title, the stores, and a shelf of tiles.

    python3 scripts/make_social_cards.py      draws site/img/social*.jpg (1200 × 630, as every site shows them)

Run it after changing a card's words below; the pictures are kept in the repository, so building the site needs
nothing more. Needs Playwright (as the tests do).
"""
from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_chrome import LOGO, REPO  # noqa: E402

SITE = REPO / "site"
OUT = SITE / "img"

# file: (the tab it shows, the title, the line under it). "" is the home page's card, social.jpg.
CARDS = {
    "": ("Library", "Every VRChat asset you own, in one hoard", "Lists, downloads and updates what you've bought. Free and open source."),
    "docs": ("Docs", "Hoard docs", "Installing, signing in, every setting, Hoard for Unity, and answers to common questions."),
    "how-it-works": ("How it works", "How Hoard works", "From signing in to your stores to bringing your assets into Unity."),
    "trust": ("Trust", "How you can trust Hoard", "Your sign-ins stay on your computer. Check every point for yourself."),
    "changelog": ("What's new", "What's new in Hoard", "Every release, newest first: what changed and what was fixed."),
    "testers": ("Testers", "Hoard's testers", "The people who tested Hoard before its releases."),
    "credits": ("Credits", "Picture credits", "The creators whose products appear in Hoard's screenshots."),
    "ai": ("AI", "AI disclosure", "How Hoard is built with the help of AI, and how it's checked."),
}

STORES = [("Booth", "#FF6259"), ("Gumroad", "#FF8AD8"), ("Jinxxy", "#56D1DC"), ("Payhip", "#95A0FF"), ("itch.io", "#7ED67A")]
# the shelf: (hue of the picture, its letters, its store, a badge)
TILES = [(14, "OL", "#FF6259", "New"), (186, "UN", "#56D1DC", "Update"), (320, "DF", "#FF8AD8", ""),
         (232, "TH", "#95A0FF", ""), (110, "SI", "#7ED67A", "New"), (40, "YC", "#FF6259", ""),
         (270, "AV", "#95A0FF", ""), (160, "PR", "#56D1DC", "Update"), (350, "WO", "#FF8AD8", ""),
         (200, "CL", "#56D1DC", ""), (60, "GE", "#7ED67A", "")]


def card(tab: str, title: str, line: str) -> str:
    def font(name: str) -> str:   # inline: a page drawn from a string can't load files
        return "data:font/woff2;base64," + base64.b64encode((SITE / "fonts" / name).read_bytes()).decode()
    stores = "".join(f'<span class="st"><i style="background:{c}"></i>{n}</span>' for n, c in STORES)
    tiles = "".join(
        f'<div class="tile"><div class="art" style="--h:{h}"><b>{t}</b>'
        f'{f"<span class=badge>{b}</span>" if b else ""}<i style="background:{c}"></i></div>'
        f'<div class="nm"></div><div class="cr"></div></div>' for h, t, c, b in TILES)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Dela; src: url({font('DelaGothicOne-Regular.woff2')}); }}
@font-face {{ font-family: Zen; font-weight: 700; src: url({font('ZenMaruGothic-Bold.woff2')}); }}
@font-face {{ font-family: Zen; font-weight: 500; src: url({font('ZenMaruGothic-Medium.woff2')}); }}
* {{ box-sizing: border-box; margin: 0; }}
body {{ width: 1200px; height: 630px; overflow: hidden; position: relative; color: #F4EDE3; font: 500 26px/1.4 Zen;
  --cave: #211C18; background: #211C18; }}
.glow {{ position: absolute; inset: 0;
  background: radial-gradient(ellipse 16% 70% at 6% 112%, #FF625988, transparent 75%),
    radial-gradient(ellipse 16% 70% at 24% 112%, #FF8AD888, transparent 75%),
    radial-gradient(ellipse 16% 70% at 42% 112%, #56D1DC88, transparent 75%),
    radial-gradient(ellipse 16% 70% at 60% 112%, #95A0FF88, transparent 75%),
    radial-gradient(ellipse 16% 70% at 78% 112%, #7ED67A88, transparent 75%),
    radial-gradient(ellipse 30% 50% at 96% -10%, #F0B42933, transparent 70%); }}
.left {{ position: absolute; left: 68px; top: 56px; bottom: 56px; width: 600px; display: flex; flex-direction: column; }}
.logo svg {{ width: 236px; height: auto; display: block; }}
.logo .word path {{ fill: #F4EDE3; }}
.tab {{ align-self: flex-start; margin-top: 40px; padding: 6px 16px; border-radius: 11px; background: #2B2520;
  box-shadow: inset 0 0 0 1.5px #4A4037; font: 700 22px Zen; color: #F4EDE3; }}
h1 {{ margin-top: 18px; font: 400 60px/1.12 Dela; letter-spacing: 0; text-wrap: balance; }}
p {{ margin-top: 18px; color: #C9BDAE; font-size: 25px; text-wrap: pretty; max-width: 560px; }}
.stores {{ margin-top: auto; display: flex; gap: 8px; }}
.st {{ display: inline-flex; align-items: center; gap: 9px; padding: 7px 13px; border-radius: 11px; background: #2B2520cc;
  box-shadow: inset 0 0 0 1.5px #4A4037; font: 700 19px Zen; }}
.st i {{ width: 10px; height: 10px; border-radius: 3px; transform: rotate(45deg); }}
.shelf {{ position: absolute; left: 700px; top: -36px; width: 560px; display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 24px 20px; transform: rotate(-8deg); transform-origin: 0 0; }}
.tile {{ display: flex; flex-direction: column; gap: 9px; }}
.tile:nth-child(3n+2) {{ transform: translateY(48px); }}
.art {{ position: relative; aspect-ratio: 1; border-radius: 16px; overflow: hidden; display: grid; place-items: center;
  background: linear-gradient(150deg, hsl(var(--h) 42% 44%), hsl(var(--h) 36% 26%));
  box-shadow: 0 18px 40px rgb(0 0 0 / .45), inset 0 0 0 1px rgb(255 255 255 / .06); }}
.art b {{ font: 400 50px/1 Dela; color: rgb(255 248 230 / .82); }}
.art i {{ position: absolute; left: 0; right: 0; bottom: 0; height: 6px; }}
.badge {{ position: absolute; left: 12px; top: 12px; padding: 2px 9px; border-radius: 7px; background: #F0B429;
  color: #2A1D00; font: 700 15px Zen; }}
.nm {{ height: 13px; width: 82%; border-radius: 6px; background: #F4EDE3; opacity: .85; }}
.cr {{ height: 10px; width: 54%; border-radius: 6px; background: #B3A695; opacity: .6; }}
</style></head><body><div class="glow"></div>
<div class="shelf">{tiles}</div>
<div class="left"><div class="logo">{LOGO}</div><div class="tab">{html.escape(tab)}</div>
<h1>{html.escape(title)}</h1><p>{html.escape(line)}</p><div class="stores">{stores}</div></div>
</body></html>"""


def main() -> int:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        for name, words in CARDS.items():
            page.set_content(card(*words), wait_until="load")
            page.evaluate("document.fonts.ready")
            out = OUT / (f"social-{name}.jpg" if name else "social.jpg")
            page.screenshot(path=str(out), type="jpeg", quality=88)
            print(out.relative_to(REPO), out.stat().st_size)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
