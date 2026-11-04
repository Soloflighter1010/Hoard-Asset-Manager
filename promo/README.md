# Hoard's videos, posters and music

Everything here is made in code: Hoard's own screens, photographed from a made-up data folder; the Heap and words,
drawn in HTML and SVG; and music written out note by note and synthesised. No diffusion, and no other generated
pictures, video or sound.

| Script | Makes | Issue |
|---|---|---|
| `make.py` | All of it, in one go | |
| `music.py` | `hoard-loop.wav` (and `.m4a`, `.ogg`): a 40-second track that loops with no seam | #291 |
| `art.py` | Made-up products, drawn in SVG, for any store the products you give have few of | #280 |
| `capture.py` | Hoard's screens, each in the theme its scene shows off, in English, Japanese and Korean, and where each part of them is | #273 |
| `scenes.py` | What each video shows and says, in each language | #273, #274, #289 |
| `player.html` | Draws any moment of a video (the Heap, Hoard's screens, the camera's moves, the lower third with the theme's name, the captions, the boxes tumbling between scenes) | |
| `render.py` | The videos: `player.html` photographed frame by frame into ffmpeg, with the music | |
| `posters.py` | The posters, for VRChat worlds' poster frames | #292 |
| `sketch.md` | The sketch's shot list, for recording it for real in VRChat | #289 |

## Making them

You need Python 3.11 or later, Hoard's requirements (`pip install -r requirements.txt`), Playwright with Chromium
(`python3 -m playwright install chromium`) and ffmpeg.

```
python3 promo/make.py [PRODUCTS] [OUT]
```

PRODUCTS is a folder of product pictures and their `products.json`, as `scripts/screenshots.py` takes one:
`promo/products` if it's there, or your own (`scripts/export_screenshot_products.py` makes one from your library).
Leave out the products' links: the videos never show them. Without any, the videos show only made-up products. OUT
(`promo/out` unless given; Git ignores it) gets the music, `screens/`, `videos/` and `posters/`.

Each step runs on its own too, and `render.py --check` draws one frame of each scene as a PNG, to look over quickly:

```
python3 promo/capture.py PRODUCTS OUT/screens --lang=en
python3 promo/render.py OUT/screens PRODUCTS OUT/videos --only=promo-short --lang=en --layout=landscape --check
```

## The videos

| Video | Length | Layouts | Languages |
|---|---|---|---|
| `promo-long` | about 2 minutes: every part of Hoard, each explained | landscape (1920 × 1080), portrait (1080 × 1920) | English, Japanese, Korean |
| `promo-short` | about 30 seconds | landscape, portrait | English, Japanese, Korean |
| `troubleshooting-…` | 15 to 25 seconds each, one for each problem the wiki's Troubleshooting page explains most | landscape | English, Japanese, Korean |
| `sketch-mockup` | about 35 seconds: the sketch's timing, to record for real | landscape | English |

They're put up on the `media` release, so their addresses don't change:
`https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/download/media/<file>`.

## Changing what they say

The words are in `scenes.py`, in each language. A name in braces (`{Sign in}`, `{Quick refresh}`) is one of Hoard's
own, and comes from the app's translations, so the videos name things as Hoard does. A troubleshooting video says
what the wiki's Troubleshooting page says: change both together. `tests/test_promo.py` checks every scene has its
words in all three languages, and that the screens and parts it names are ones `capture.py` takes.

## What's shown

Only made-up data: a data folder `scripts/screenshots.py` makes, never yours, with the products given. Nothing
that's anyone's to keep private appears (no account pages, purchase receipts, order numbers or email addresses),
the version number is left out of the bar so the videos don't go out of date, and wishlists show prices as `¥¥` or
`$$$` rather than real ones. The credits name the creators of the products shown; the made-up ones are drawn by
`art.py`.

The fonts: Dela Gothic One and Zen Maru Gothic (the ones Hoard has), and for Korean, Black Han Sans and Gowun Dodum
from Google Fonts. All are under the SIL Open Font License.
