# The sketch: shot list (issue #289)

A rough mockup of a short sketch to record for real in VRChat: over someone's shoulder as they scroll through their
libraries, every store in a tab of its own, struggling to find the asset they need to finish a project; then Hoard,
every store in one place, searched all at once. The mockup (`sketch-mockup-en.mp4`, made by `promo/render.py`)
shows the timing and the words. Everything in it is drawn in code: the figure is shapes, the store tabs are boxes
with product pictures, and the rest is Hoard's own screens.

About 36 seconds, landscape (1920 × 1080). The music is Hoard's looping track (`promo/music.py`).

| # | Time | Shot | What's seen | Words | Notes for the real recording |
|---|---|---|---|---|---|
| 1 | 0:00 to 0:09 | Over the shoulder, medium close | An avatar at a desk, seen from behind, facing a big browser window in a world with a desk and a screen. Tabs for Booth, Gumroad, Jinxxy, Payhip and itch.io along the top. They click from tab to tab, each library scrolling by. | Speech bubble, then said aloud: "I need that hoodie to finish my avatar…", then "Which store was it on?!" | Use a world with a desk and a big screen or a video player showing a browser (a recorded screen of your own libraries, with nothing personal in view: no order numbers, emails or receipt pages). Shoulder height, slightly above. Small head turns between tabs; a sigh on the second line. |
| 2 | 0:09 to 0:12.6 | Title card | Dark, warm background. | "Can't find the asset to finish your project?" / "Five stores. Five libraries. Five tabs." | A cut to black with the words, or the avatar turning to camera and saying it. |
| 3 | 0:12.6 to 0:16.4 | The Heap | Hoard's boxes drop in one by one, the gold one last with its sparkle; then the word "hoard". | "Every store, in one place." | The turn of the sketch: a beat of the music. In VRChat, a poster of the Heap (`promo/posters.py`) on the wall works as the cut. |
| 4 | 0:16.4 to 0:21.2 | Hoard's Library | The Library, the tabs ringed: Everything, Booth, Gumroad, Jinxxy, Payhip, itch.io. | "All your stores, one library" / "Booth, Gumroad, Jinxxy, Payhip and itch.io" | The same screen in the world, now showing Hoard. The avatar leans in. |
| 5 | 0:21.2 to 0:26.7 | Hoard's search | "hoodie" typed in the search box (ringed), then the three hoodies, from Booth and Gumroad together (ringed). | "Searched all at once" / "“hoodie”: Booth and Gumroad, together" | Type it live; the avatar's relieved reaction, a thumbs up. |
| 6 | 0:26.7 to 0:31.7 | The end card | The Heap, "Get Hoard", hoard.furryup.link, "Free · Windows, macOS and Linux". | | Hold for at least 4 seconds so the address can be read. |
| 7 | 0:31.7 to 0:35.7 | Credits | The creators of the products shown. | "Products shown, by …" | Credit the creators of whatever appears on screen in the real recording, and the world's creator. |

**On screen:** only made-up or your own library, and nothing that's yours to keep private (store account pages,
purchase receipts, order numbers, email addresses). Hoard's `promo/capture.py` takes its screens from a made-up data
folder for that reason.

**In Japanese and Korean:** the words are in `promo/scenes.py` (`sketch_video`) in all three languages; the mockup
is rendered in English only (`python3 promo/render.py ... --only=sketch-mockup` renders it, and the `videos()` list
in `scenes.py` says which languages).
