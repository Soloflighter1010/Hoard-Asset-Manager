"""Which products are for adults (issues #311, #337 and #338), so their pictures can be blurred, they and their sets
carry an 18+ mark, and a shared set with one in it asks its viewer's age first.

A product is for adults when, in this order:

- you said so, or said it isn't: marks.json's "adult" and "not_adult". Your word wins over everything else, and is
  the only way for a product of your own in Local, which no store describes.
- its store said so when Hoard read it: a library item's or a wishlist product's "adult" (Booth's is_adult, Jinxxy's
  content warnings Suggestive or Explicit, an R-18 or NSFW badge on a wishlist's card).
- its creator's tags, your own tags or its name say so: R-18, NSFW, 18+ and the like (TAGS, IN_A_NAME).

A set is for adults while any product in it is: that is worked out each time, never kept, so it goes when the last
adult product is taken out and can't be taken off by hand before then.

Hoard never asks anyone for ID. The set viewer's question is a question: its answer is kept in a cookie on the
viewer's own device and sent nowhere.
"""
from __future__ import annotations

import re

# Tags, as Hoard keeps them (tags.clean_tag: lower case, most punctuation gone), that say a product is for adults.
# "18" alone isn't one (clean_tag takes the + from "18+", and 18 is many things), and neither is "adult" alone, which
# creators also give an avatar that looks grown up.
TAGS = frozenset({
    "r18", "r-18", "r 18", "r18g", "r-18g", "r 18g", "nsfw", "nsfw r18", "adult only", "adults only", "adult content",
    "over 18", "18 only", "explicit", "hentai", "lewd", "erp",
    "18禁", "成人向け", "成人向", "アダルト", "r-18向け", "r18向け", "エロ",
    "성인용", "19금", "후방주의",
})
# ...and the same said in a product's name: "[R-18] Outfit", "Body (NSFW)", "18+ version".
IN_A_NAME = re.compile(r"(?<![a-z0-9])(?:r[-\s]?18g?|nsfw|18\+|18禁|成人向け|アダルト|19금|성인용)(?![a-z0-9])", re.I)
# A store's own word for it in a page's data, as a flag that's on (a page Hoard can't read the product's data from).
FLAG_ON_A_PAGE = re.compile(r'\\?"(?:nsfw|is_nsfw|isNsfw|is_adult|isAdult|adult|mature|is_mature)\\?"\s*:\s*true\b')
# Jinxxy rates a product by its content warnings, its "restrictions": Suggestive (suggestive poses, lingerie,
# revealing outfits) and Explicit are for adults; General Mature Themes alone (horror, intense scenes) isn't.
JINXXY_ADULT = frozenset({"CONTENT_SUGGESTIVE", "CONTENT_EXPLICIT"})
# A Jinxxy page's data, as Next.js streams it to the page: each chunk a JSON string in a script.
_NEXT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_PUBLIC_PRODUCT = re.compile(r'\{\s*"__typename"\s*:\s*"PublicProduct"')


def by_tags(tags) -> bool:
    """Whether one of these tags says a product is for adults."""
    return any(isinstance(t, str) and t.strip().lower() in TAGS for t in tags or ())


def by_name(name) -> bool:
    """Whether a product's name says it is for adults."""
    return bool(isinstance(name, str) and IN_A_NAME.search(name))


def jinxxy_rated(restrictions) -> bool | None:
    """What Jinxxy's content warnings for a product say: True (for adults) or False; None when it isn't a list of them
    (its data didn't say)."""
    if not isinstance(restrictions, list):
        return None
    return any(isinstance(r, str) and r.strip().upper() in JINXXY_ADULT for r in restrictions[:20])


def jinxxy_page_product(page: str) -> dict | None:
    """The product a Jinxxy product page is for (its PublicProduct), as the page's data has it, or None. Only that
    one: the page lists other products too (more from its creator), each with content warnings of its own. Read as
    JSON, never run."""
    import json
    if not isinstance(page, str) or len(page) > 16 << 20:
        return None
    parts = []
    for m in _NEXT_CHUNK.finditer(page):
        try:
            parts.append(json.loads(m.group(1)))
        except ValueError:
            continue
    text = "".join(p for p in parts if isinstance(p, str))
    at = _PUBLIC_PRODUCT.search(text)
    if not at:
        return None
    try:
        product, _ = json.JSONDecoder().raw_decode(text, at.start())
    except ValueError:
        return None
    return product if isinstance(product, dict) else None


def on_a_page(store: str, got) -> bool | None:
    """What a product's own page says: True or False where its store says, None where it doesn't (or its page didn't
    carry what it says). got is what wishlists.from_product_page read: Booth's item JSON (a dict), another store's
    page (its text). Jinxxy's says it by the product's content warnings (jinxxy_rated)."""
    if store == "booth" and isinstance(got, dict):
        return got.get("is_adult") is True
    if store == "jinxxy" and isinstance(got, str):
        product = jinxxy_page_product(got)
        said = jinxxy_rated(product.get("restrictions")) if product else None
        return True if said is None and FLAG_ON_A_PAGE.search(got) else said
    return None


def why(key: str, *, name: str = "", tags=(), flagged: bool = False, marks: dict | None = None) -> str | None:
    """Why a product is for adults: "you", "store" or "tags"; None when it isn't. key: its product key (tags.tag_key);
    tags: its creator's and your own; flagged: its store said so; marks: MarkStore's choices (adult, not_adult)."""
    if marks:
        if key in marks.get("not_adult", ()):
            return None
        if key in marks.get("adult", ()):
            return "you"
    if flagged:
        return "store"
    if by_tags(tags) or by_name(name):
        return "tags"
    return None
