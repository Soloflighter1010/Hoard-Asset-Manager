"""Pick products from your Hoard library for the screenshots (scripts/screenshots.py), with their pictures.

    python scripts/export_screenshot_products.py OUT_FOLDER [--limit 24] [--store jinxxy] [--tag avatar] [--include-archived]

Run it on your own computer, where Hoard keeps your library. It reads your library (never changes it) and writes
OUT_FOLDER with, for each product chosen, its picture and an entry in products.json (name, creator, store, its store
page and your tags), plus review.html: every picture with its name, to look through before you share the folder.

What's left out, always:
- your hidden and removed items (and archived ones, unless --include-archived);
- anything whose name or tags have an adult marker (R-18, NSFW, 18+ and the like, in English and Japanese). Stores
  don't say which products are for adults, so this can't catch everything: look through review.html, and delete
  any picture you don't want shown (screenshots.py skips a product whose picture is gone);
- anything without a picture Hoard already saved (in its picture cache, or a download's _thumbnail): nothing is
  fetched from the internet.

Nothing about your accounts goes in: no sign-ins, emails, order numbers, receipts or download links, only what the
store shows everyone on the product's page. A link is kept only when it's the product's public page (Gumroad's
library links are your purchase receipts, which can download what you bought; Payhip's and Jinxxy's are pages of
your account). Newest first.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hoard import config, downloader, library  # noqa: E402
from hoard.marks import MarkStore, is_archived  # noqa: E402
from hoard.paths import LIBRARY_FILE, THUMB_DIR  # noqa: E402
from hoard.tags import TagStore, tag_key  # noqa: E402

PICTURES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
ADULT = re.compile(r"(?<![a-z0-9])(r-?18g?|r18|nsfw|18\+|18禁|adult|lewd|nude|nudity|naked|hentai|ecchi|erotic|ero|porn|"
                   r"sexy|futa|lingerie|nipples?|genitals?|explicit|uncensored|xxx)(?![a-z0-9])|成人向け|アダルト|エロ|裸",
                   re.IGNORECASE)


# Only a product's public store page is kept. What a library links to is often private: Gumroad's link is your
# purchase receipt (gumroad.com/d/..., which can download what you bought), Payhip's and Jinxxy's are pages of your
# account. Those never go in the folder you share.
PUBLIC_PAGES = {
    "booth": re.compile(r"https://([a-z0-9-]+\.)?booth\.pm/([a-z]{2}/)?items/\d+"),
    "gumroad": re.compile(r"https://[a-z0-9-]+\.gumroad\.com/l/[A-Za-z0-9_-]+"),
    "itch": re.compile(r"https://[a-z0-9-]+\.itch\.io/[a-z0-9_-]+"),
}


def public_link(store: str, url) -> str | None:
    """url if it's a product's public page on its store, else None (see PUBLIC_PAGES)."""
    rx = PUBLIC_PAGES.get(store)
    return url if isinstance(url, str) and rx and rx.fullmatch(url) else None


def adult(*texts: str) -> bool:
    return any(ADULT.search(t or "") for t in texts)


def cached_picture(item: dict) -> Path | None:
    """The picture Hoard saved for an item (its picture cache), if any."""
    url = item.get("thumbnail")
    if not url:
        return None
    for p in THUMB_DIR.glob(hashlib.sha1(url.encode()).hexdigest() + ".*"):
        if p.suffix.lower() in PICTURES:
            return p
    return None


def downloaded_pictures(root: Path) -> dict[str, Path]:
    """Each downloaded product's _thumbnail, by its tag key."""
    found = {}
    for rec in downloader.read_manifests(root):
        try:
            folder = downloader.record_folder(root / rec["store"], rec)
        except downloader.UnsafePath:
            continue
        for p in sorted(folder.glob("_thumbnail.*")) if folder.is_dir() else []:
            if p.suffix.lower() in PICTURES and not p.is_symlink():
                found[tag_key(rec["store"], rec.get("name") or "")] = p
                break
    return found


def slug(text: str) -> str:
    s = re.sub(r"[^\w]+", "-", text.lower()).strip("-")
    return s[:40] or "product"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--limit", type=int, default=24, help="how many products (default 24)")
    ap.add_argument("--store", action="append", choices=list(library.STORES), help="only these stores")
    ap.add_argument("--tag", action="append", help="only products with one of these tags of yours")
    ap.add_argument("--include-archived", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} isn't empty. Choose a new folder.")
    out.mkdir(parents=True, exist_ok=True)

    cfg = config.load_config()
    items = library.Library(LIBRARY_FILE).snapshot()[0]
    marks, tags = MarkStore().load(), TagStore().load()
    from_downloads = downloaded_pictures(config.root_dir(cfg))
    items.sort(key=lambda i: i.get("added") or "", reverse=True)
    chosen, skipped = [], {"hidden or removed": 0, "archived": 0, "adult marker": 0, "no picture": 0, "filtered": 0}
    for i in items:
        if len(chosen) >= args.limit:
            break
        key = tag_key(i["store"], i["name"])
        mine = TagStore.tags_for(tags, key, i["name"])
        if key in marks["hidden"] or key in marks["removed"]:
            skipped["hidden or removed"] += 1
        elif not args.include_archived and is_archived({**i, "tag_key": key}, marks):
            skipped["archived"] += 1
        elif adult(i["name"], i.get("variants") or "", *mine):
            skipped["adult marker"] += 1
        elif (args.store and i["store"] not in args.store) or (args.tag and not set(args.tag) & set(mine)):
            skipped["filtered"] += 1
        else:
            pic = cached_picture(i) or from_downloads.get(key)
            if not pic:
                skipped["no picture"] += 1
                continue
            name = f"{len(chosen) + 1:02d}-{slug(i['name'])}{pic.suffix.lower()}"
            shutil.copy(pic, out / name)
            chosen.append({"image": name, "name": i["name"], "creator": i["creator"], "store": i["store"],
                           "url": public_link(i["store"], i.get("url")), "tags": mine[:5]})
    (out / "products.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=1), "utf-8")
    cards = "".join(f'<figure><img src="{html.escape(p["image"])}" alt=""><figcaption><b>{html.escape(p["name"])}</b><br>'
                    f'{html.escape(p["creator"])} · {html.escape(p["store"])}<br><code>{html.escape(p["image"])}</code>'
                    f'</figcaption></figure>' for p in chosen)
    (out / "review.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>Check before sharing</title>
<style>body{{font:14px system-ui;margin:24px;background:#222;color:#eee}}main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}}
figure{{margin:0}}img{{width:100%;aspect-ratio:1;object-fit:cover;border-radius:10px;background:#444}}code{{color:#aaa}}</style>
<h1>{len(chosen)} products for the screenshots</h1>
<p>Look through every picture. Delete the picture file of any you don't want shown (the screenshots skip it), then
zip the folder, review.html included or not.</p><main>{cards}</main>""", "utf-8")
    print(f"Chose {len(chosen)} products into {out}. Left out: " + ", ".join(f"{n} {why}" for why, n in skipped.items() if n))
    print(f"Now open {out / 'review.html'} and look through every picture before sharing the folder.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
