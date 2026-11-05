"""Screenshots of every part of Hoard, for the website and the README, made from real products you choose.

    python scripts/screenshots.py PRODUCTS_FOLDER [OUT_FOLDER] [--style=treasure] [--themes=dark] [--only=library,set]
                                  [--lang=ja] [--regions=promo/regions.json]

PRODUCTS_FOLDER holds each product's picture (PNG, JPEG, WebP or GIF) and products.json, listing them:

    [{"image": "fox-ears.png", "name": "Fox Ears", "creator": "Your Shop", "store": "jinxxy",
      "url": "https://jinxxy.com/...", "tags": ["ears", "accessory"]}, ...]

"store" is booth, gumroad, jinxxy, payhip or itch; "url" and "tags" are optional. Without products.json, every
picture in the folder is a product named after its file, from Jinxxy. A product whose picture isn't there is
skipped. scripts/export_screenshot_products.py makes this folder from your own Hoard library. A product can also be
on a wishlist instead of in the library: "wishlist": {"list": "Loved items", "price": ["¥2,500", 2500, "JPY"],
"was": ["¥3,000", 3000, "JPY"]} ("was" optional: an older, higher price, so it shows as cheaper now). Tags named in
KINDS get that kind (avatar, clothing...), which Mix and match picks from.

Hoard runs on a made-up data folder of its own (never yours): those products are your library, most of them
downloaded, with a Local item, sets and wishlists of them, two Unity projects (with VRChat's packages, backups, and
what Hoard put in them), a finished check and a few tasks. Then each part is photographed, in the dark and light
themes, at 1600x950: OUT_FOLDER/<part>-<theme>.png (and .webp, at 1600, 1200 and 800 wide, for the website).
--style takes them in the Treasure or Workbench style (Settings, Appearance), named
<part>-<style>-<theme>; --themes and --only take fewer of them. --lang takes them in Japanese (ja) or Korean (ko),
named <part>-<theme>-<lang> (the promo and help videos use them: promo/README.md). --regions names, for some
parts, things on the page ({"library": {"search": "#q"}}): each one's box (all it draws) is saved beside the
picture, in <picture>.json ({"search": [x, y, width, height]}), so the videos can point at it in every language; it
also takes a few pictures for the videos alone: help-booth-library, -stores and -fixed (Booth's sign-in ended, as
Hoard shows it, and then signed in again), and wishlist-prices and downloads-files, scrolled so what they look at
closely is whole. Nothing is fetched from the internet: the pictures come from the folder. Paths on the pages are
shown as C:\\Users\\you\\..., as a usual computer's would be.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix="hoard-shots-"))
os.environ["HOARD_DATA_DIR"] = str(WORK / "appdata")   # before Hoard is imported: its folders come from this
os.environ["HOARD_VCC_DIR"] = str(WORK / "vcc")        # the Creator Companion's folder, for Projects (never yours)
sys.path.insert(0, str(REPO))

from hoard import config, downloader, jobs, library, projects, server, sets  # noqa: E402
from hoard.paths import THUMB_DIR  # noqa: E402
from hoard.safety import safe_name  # noqa: E402
from hoard.vpm import backup, imports, listing, unity  # noqa: E402
sys.path.insert(0, str(REPO / "scripts"))
from export_screenshot_products import public_link  # noqa: E402
from hoard.tags import TagStore, tag_key  # noqa: E402

STORES = ("booth", "gumroad", "jinxxy", "payhip", "itch")
PICTURES = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp", ".gif": "gif"}
SIZE = {"width": 1600, "height": 950}
WIDTHS = (1200, 800)   # the website's smaller copies (srcset), beside the full 1600
KINDS = {"avatar": "avatar", "world": "world", "gimmick": "gimmick", "textures": "texture", "texture": "texture",
         "clothing": "clothing", "headphones": "clothing", "eyewear": "clothing", "headwear": "clothing",
         "wings": "clothing", "accessory": "other", "props": "other"}
PICTURE_HOST = {"booth": "https://booth.pximg.net/screens/", "gumroad": "https://public-files.gumroad.com/screens/"}
SETS = (("Photo studio", ("撮影スタジオ", "Mobile Studio", "VRChat Studio Lights", "PIXON400")),   # (name, products: words in their names)
        ("Night world", ("The Deep Dusk", "Moonlit Perch", "ClockCounter", "EDJ")),
        ("Rave look", ("AVIA X2", "Round Glasses", "Plumbob", "Flatcap")))


def products(folder: Path) -> list[dict]:
    """The products to show, from a folder of pictures (and its products.json, when there is one)."""
    listed = folder / "products.json"
    if listed.is_file():
        found = json.loads(listed.read_text("utf-8"))
    else:
        found = [{"image": p.name, "name": p.stem.replace("-", " ").replace("_", " ").title(), "creator": "Your shop",
                  "store": "jinxxy"} for p in sorted(folder.iterdir()) if p.suffix.lower() in PICTURES]
    out = []
    for n, p in enumerate(found):
        pic = folder / p["image"]
        if not pic.is_file():
            print(f"Skipping {p['name']}: its picture isn't in {folder} (deleted while reviewing?)")
            continue
        if pic.suffix.lower() not in PICTURES:
            sys.exit(f"{p['image']}: not a picture in {folder}")
        store = p.get("store", "jinxxy")
        if store not in STORES:
            sys.exit(f"{p['name']}: store must be one of {', '.join(STORES)}")
        if p.get("wishlist") and store not in PICTURE_HOST:
            sys.exit(f"{p['name']}: a wishlist's products here are Booth's or Gumroad's")
        out.append({**p, "store": store, "id": str(1000 + n), "picture": pic,
                    "url": public_link(store, p.get("url"))})   # never a receipt or account page
    if sum(1 for p in out if not p.get("wishlist")) < 4:
        sys.exit("Add at least 4 products, so the pages look like a library.")
    return out


def cache_picture(url: str, picture: Path) -> None:
    """The picture Hoard shows for this address, kept where Hoard keeps pictures it fetched: so it's never fetched."""
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(picture, THUMB_DIR / f"{hashlib.sha1(url.encode()).hexdigest()}.{PICTURES[picture.suffix.lower()]}")


def texture_package() -> bytes:
    """Your own texture set, as a real .unitypackage (Look inside reads it): folders, textures and materials, by name
    and size only (no pictures are made up for it: Hoard shows each file's kind)."""
    files = [("Assets/My Texture Set", None),
             ("Assets/My Texture Set/Fabric", None),
             ("Assets/My Texture Set/Fabric/Denim.png", 2_400_000),
             ("Assets/My Texture Set/Fabric/Wool.png", 2_100_000),
             ("Assets/My Texture Set/Fabric/Velvet.png", 1_900_000),
             ("Assets/My Texture Set/Metal", None),
             ("Assets/My Texture Set/Metal/Brushed Steel.png", 2_600_000),
             ("Assets/My Texture Set/Metal/Gold Leaf.png", 2_300_000),
             ("Assets/My Texture Set/Materials", None),
             ("Assets/My Texture Set/Materials/Denim.mat", 4_200),
             ("Assets/My Texture Set/Materials/Gold Leaf.mat", 4_100)]
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        def add(name: str, data: bytes):
            """Add a file to the made-up package's archive."""
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for path, size in files:
            guid = hashlib.md5(path.encode()).hexdigest()
            add(f"{guid}/pathname", path.encode())
            add(f"{guid}/asset.meta", b"fileFormatVersion: 2\nguid: " + guid.encode() + b"\n")
            if size is not None:
                add(f"{guid}/asset", bytes(size))
    return gzip.compress(raw.getvalue())


def unity_projects(now: datetime) -> dict:
    """Two Unity projects in the Creator Companion's list (with VRChat's packages, one with an update), their
    backups, VRChat's repository and a Unity editor, all in the made-up folder."""
    vcc, unity_dir, backups = WORK / "vcc", WORK / "Unity", WORK / "Backups"
    editor = WORK / "Editors" / "2022.3.22f1" / "Editor" / "Unity"
    editor.parent.mkdir(parents=True)
    editor.write_bytes(b"")
    hub = WORK / "UnityHub"
    hub.mkdir()
    (hub / "editors-v2.json").write_text(json.dumps({"data": [{"version": "2022.3.22f1", "location": [str(editor)]}]}), "utf-8")
    unity._hub_user_data = lambda: hub                   # (Unity Hub's own, as it would list this editor)
    unity._hub_install_folder = lambda: WORK / "Hub"
    unity._secondary_folder = lambda: None
    backup.room = lambda folder: {"free": 9_100_000_000, "total": 476_000_000_000, "low": True}   # (a usual drive's, nearly full)
    sdk = {"avatars": "VRChat SDK - Avatars", "worlds": "VRChat SDK - Worlds"}
    made = {}
    for name, kind in (("My Avatar", "avatars"), ("Night World", "worlds")):
        p = unity_dir / name
        for sub in ("Assets", "ProjectSettings", "Packages/com.vrchat.base", f"Packages/com.vrchat.{kind}"):
            (p / sub).mkdir(parents=True, exist_ok=True)
        (p / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.22f1\n", "utf-8")
        (p / "Packages" / "manifest.json").write_text(json.dumps({"dependencies": {}}), "utf-8")
        have = "3.7.0" if kind == "avatars" else "3.10.5"
        (p / "Packages" / "vpm-manifest.json").write_text(json.dumps({
            "dependencies": {f"com.vrchat.{kind}": {"version": have}},
            "locked": {f"com.vrchat.{kind}": {"version": have, "dependencies": {"com.vrchat.base": have}},
                       "com.vrchat.base": {"version": have, "dependencies": {}}}}), "utf-8")
        for pkg, label in (("com.vrchat.base", "VRChat SDK - Base"), (f"com.vrchat.{kind}", sdk[kind])):
            (p / "Packages" / pkg / "package.json").write_text(json.dumps(
                {"name": pkg, "version": have, "displayName": label}), "utf-8")
        made[name] = p
    packages = {}
    for pkg, label in (("com.vrchat.base", "VRChat SDK - Base"), ("com.vrchat.avatars", sdk["avatars"]),
                       ("com.vrchat.worlds", sdk["worlds"])):
        packages[pkg] = {"versions": {v: {"name": pkg, "version": v, "displayName": label, "unity": "2022.3",
                                          "url": f"https://packages.vrchat.com/{pkg}-{v}.zip",
                                          "vpmDependencies": {"com.vrchat.base": v} if pkg != "com.vrchat.base" else {}}
                                      for v in ("3.7.0", "3.9.0", "3.10.5")}}
    (vcc / "Repos").mkdir(parents=True)
    (vcc / "Repos" / "vrc-official.json").write_text(json.dumps({"repo": {
        "name": "Official", "id": "com.vrchat.repos.official", "url": "https://packages.vrchat.com/official?download",
        "packages": packages}}), "utf-8")
    (vcc / "Repos" / "vrc-curated.json").write_text(json.dumps({"repo": {
        "name": "Curated", "url": "https://packages.vrchat.com/curated?download", "packages": {}}}), "utf-8")
    backups.mkdir()
    for name, ages in (("My Avatar", (2, 9, 40, 75, 120, 200)), ("Night World", (5, 90))):
        for days in ages:
            when = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H-%M-%S")
            with open(backups / f"{name}-{when}.zip", "wb") as fh:
                fh.write(b"PK\x05\x06" + bytes(18))
                fh.truncate(1_400_000_000 if name == "My Avatar" else 600_000_000)   # sparse: the size shows
    (vcc / "settings.json").write_text(json.dumps({"userProjects": [str(p) for p in made.values()],
                                                   "projectBackupPath": str(backups),
                                                   "defaultProjectPath": str(unity_dir)}), "utf-8")
    return made


def build(items: list[dict]) -> tuple[Path, dict]:
    """The made-up data folder and downloads folder, with these products in them."""
    root = WORK / "Hoard"
    root.mkdir()
    now = datetime.now(timezone.utc)
    lib_items, tags, wishes = [], TagStore(), []
    for n, p in enumerate(items):
        if p.get("wishlist"):   # not yours: on a wishlist, with its store's picture (cached: never fetched)
            p["thumb"] = f"{PICTURE_HOST[p['store']]}{p['id']}{p['picture'].suffix.lower()}"
            cache_picture(p["thumb"], p["picture"])
            wishes.append(p)
            continue
        added = (now - timedelta(days=n * 3)).isoformat(timespec="seconds")
        thumb = f"https://hoard.invalid/screens/{p['id']}{p['picture'].suffix.lower()}"   # cached below: never fetched
        cache_picture(thumb, p["picture"])
        lib_items.append(library.item(p["store"], p["id"], name=p["name"], creator=p["creator"], url=p.get("url"),
                                      thumbnail=thumb, added=added))
        if p.get("tags"):
            tags.change({"action": "assign", "keys": [tag_key(p["store"], p["name"])], "add": list(p["tags"])})
        if n % 3 == 2 or p["store"] == "payhip":
            continue   # not downloaded: the library shows those too
        store_dir = root / downloader.STORE_DIRS[p["store"]]
        man = downloader.Manifest(store_dir)
        rec = man.record(p["id"], p["creator"], p["name"])
        rec.update(name=p["name"], url=p.get("url"))
        folder = store_dir / rec["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy(p["picture"], folder / f"_thumbnail{p['picture'].suffix.lower()}")
        for k, (fname, size) in enumerate(((f"{safe_name(p['name'])}.unitypackage", 48_000_000 + n * 3_100_000),
                                           ("Textures.zip", 12_000_000 + n * 700_000))):
            with open(folder / fname, "wb") as fh:
                fh.truncate(size)   # sparse: the size shows, nothing is written
            rec["files"][f"f{k}"] = {"path": fname, "size": size}
        man.save()
    for tag in {t for p in items if not p.get("wishlist") for t in p.get("tags") or ()}:   # what each tag is about
        if tag in KINDS:
            tags.change({"action": "type", "name": tag, "type": KINDS[tag]})
    spots = re.findall(r'\{ id: "([a-z0-9-]+)", at:', (REPO / "hoard" / "web" / "shared.js").read_text("utf-8"))
    cfg = {**config.load_config(), "root": str(root), "setup_done": True,
           "ui": {"toured": True, "spots_seen": spots}}   # (the "new here" notes: the pictures outlast them)
    own = WORK / "My Texture Set"   # your own: a texture set, copied into Local (with Hoard's own placeholder picture)
    (own / "Textures").mkdir(parents=True)
    (own / "My Texture Set.unitypackage").write_bytes(texture_package())
    (own / "Textures" / "README.txt").write_text("Fabric and metal textures, 2048px.", "utf-8")
    from hoard import local
    local.add(cfg, root, str(WORK / "My Texture Set"), note="A commission", copy=True)
    downloader.build_catalog(cfg, root)
    # sets of them, and wishlists from Booth and Gumroad: read twice, so one of each is cheaper now
    named = {p["name"]: p for p in items if not p.get("wishlist")}
    store = sets.SetStore()
    for name, words in SETS:
        keys = [tag_key(p["store"], p["name"]) for w in words for p in named.values() if w in p["name"]][:len(words)]
        if keys:
            store.change({"action": "create", "name": name, "items": keys})
    lists: dict[tuple, list] = {}
    for p in wishes:
        lists.setdefault((p["store"], p["wishlist"]["list"]), []).append(p)

    def price(pair):
        """A price as the library keeps one."""
        return {"text": pair[0], "amount": pair[1], "currency": pair[2]} if pair else None
    for when in ("was", "price"):
        store.put_wishlists([{"store": s, "list": lst, "products": [
            {"store": p["store"], "id": p["id"], "name": p["name"], "creator": p["creator"], "url": p.get("url"),
             "thumbnail": p["thumb"], "price": price(p["wishlist"].get(when) or p["wishlist"]["price"])} for p in got]}
            for (s, lst), got in lists.items()], (now - timedelta(days=12 if when == "was" else 0)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    # Unity projects, as the Creator Companion lists them; what Hoard for Unity reports about the first, and what Hoard
    # put in it from your library
    made = unity_projects(now)
    catalog = downloader.collect_catalog(cfg, root)[0]
    report = {"format": "hoard-project", "version": 1, "name": "My Avatar", "path": str(made["My Avatar"]),
              "unity": "2022.3.22f1", "updated": (now - timedelta(hours=2)).isoformat(timespec="seconds"),
              "assets": [{"store": e["store"], "name": e["name"], "creator": e["creator"], "folder": e["folder"],
                          "url": e["url"], "status": "yes" if n != 2 else "partly"} for n, e in enumerate(catalog[:5])],
              "credits": {"title": "Assets used", "style": "List", "left_out": [], "added": []}}
    projects.projects_dir().mkdir(parents=True, exist_ok=True)
    (projects.projects_dir() / "0123456789abcdef.json").write_text(json.dumps(report), "utf-8")
    put_in = [{"store": e["store"], "name": e["name"], "creator": e["creator"], "file": f"{safe_name(e['name'])}.unitypackage",
               "added": [f"Assets/{safe_name(e['creator'])}/{safe_name(e['name'])}"], "already_there": 3 if n == 1 else 0}
              for n, e in enumerate(catalog[:3])]
    imports.note(made["My Avatar"], put_in)
    listing.add_preloaded(str(made["My Avatar"]), [{"tag_key": tag_key(str(e["store"]).lower(), e["name"]), "name": e["name"],
                                                    "file": e["file"], "added": e["added"]} for e in put_in])
    git_project(made["My Avatar"])
    downloader.check_integrity(root)
    return root, {"items": lib_items, "cfg": cfg, "now": now}


def git_project(path: Path) -> None:
    """The project under source control (issue #296), with a commit and a change since, for its Source control tab.
    Without Git installed, the tab shows how to get it."""
    from hoard.vpm import git
    try:
        git.set_up(path)
        git.set_identity(path, "You", "you@example.com")
        git.stage(path, [f["path"] for f in git.state(path)["files"]])
        git.commit(path, "My avatar, with its outfit")
        (path / "Assets" / "Outfit.mat").write_text("color: pink\nshine: 0.4\n", "utf-8")
    except git.GitError as e:
        print(f"No Git repository for the project: {e}")


# Paths on the pages as a usual computer's (the made-up folder is in a temporary one): shown only, never saved
SHOW_PATHS = """work => {
  const fix = t => t.split(work).join("C:\\\\Users\\\\you").replace(/C:\\\\Users\\\\you\\S*/g, m => m.replace(/\\//g, "\\\\"));
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) if (n.nodeValue.includes(work)) n.nodeValue = fix(n.nodeValue);
  for (const i of document.querySelectorAll("input")) if (i.value.includes(work)) i.value = fix(i.value);
  const r = document.querySelector("#setRoot");
  if (r) r.value = "C:\\\\Users\\\\you\\\\Documents\\\\Hoard";
}"""
# Hoard's version isn't shown in the bar: the pictures outlast it
NO_VERSION = ("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); "
              "s.textContent = '#version, [data-version] { display: none !important; }'; document.head.appendChild(s); });")
SEEDED = "(() => { let s = 20261021; Math.random = () => (s = (s * 16807) % 2147483647) / 2147483647; })()"   # (Mix and match's picks, the same each time)


LOCALES = {"en": "en-US", "ja": "ja-JP", "ko": "ko-KR"}   # --lang: Hoard's language, and the window's, for dates


REGION_BOXES = """sels => {
  const rect = e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const cut = (a, b) => [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])];
  const clips = e => { const s = getComputedStyle(e); return s.overflowX !== "visible" || s.overflowY !== "visible"; };
  const shows = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
  // all it draws: its own box, and whatever inside it sticks out of it, but not what a scrolled or cut-off box hides
  const box = el => {
    let clip = [0, 0, innerWidth, innerHeight], u = null;
    for (let a = el.parentElement; a; a = a.parentElement) if (clips(a)) clip = cut(clip, rect(a));
    const walk = (n, c) => {
      const s = getComputedStyle(n);
      if (s.display === "none") return;
      const v = cut(rect(n), c);
      if (v[2] > v[0] && v[3] > v[1] && s.visibility !== "hidden")
        u = u ? [Math.min(u[0], v[0]), Math.min(u[1], v[1]), Math.max(u[2], v[2]), Math.max(u[3], v[3])] : v;
      for (const k of n.children) walk(k, clips(n) ? cut(c, rect(n)) : c);
    };
    walk(el, clip);
    return u && [Math.floor(u[0]), Math.floor(u[1]), Math.ceil(u[2]) - Math.floor(u[0]), Math.ceil(u[3]) - Math.floor(u[1])];
  };
  return Object.fromEntries(Object.entries(sels).map(([k, sel]) => {
    const el = [...document.querySelectorAll(sel)].find(shows);
    return [k, el ? box(el) : null];
  }));
}"""   # --regions: where each named thing is on the page, the first one that shows


BRING_INTO_VIEW = """sel => {
  const e = document.querySelector(sel);
  if (!e) return;
  let box = e.parentElement;   // what scrolls it
  while (box && !(box.scrollHeight > box.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(box).overflowY))) box = box.parentElement;
  const bottom = box ? Math.min(innerHeight, box.getBoundingClientRect().bottom) : innerHeight;
  const by = e.getBoundingClientRect().bottom - (bottom - 40);
  if (by > 0) (box || document.scrollingElement).scrollBy({ top: by, behavior: "instant" });
}"""   # --regions: some pictures for the videos, scrolled so the thing they look at closely isn't cut off


VIDEO_SHOTS = {"files", "updates", "hidden", "settings-apprise", "help-apprise-test", "help-payhip-stores",
               "help-itch-stores", "help-itch-key", "help-itch-fixed", "help-blocked-stores", "help-download-tasks",
               "help-nokey", "help-pin-unlock", "help-pin-recover", "help-pin-fixed", "help-pin-wait", "settings-look",
               "look-treasure", "look-workbench", "look-synthwave", "look-moss"}
LOOKS = (("look-treasure", "treasure", "dragonfire"), ("look-workbench", "workbench", "frost"),   # (picture, style, theme)
         ("look-synthwave", "standard", "synthwave"), ("look-moss", "standard", "moss"))
HIDDEN = {"pin": "2468", "phrase": None}   # the hidden library's PIN in the pictures, and its recovery words
PAYHIP_BLOCKED = ("Payhip blocked the automated browser (the check wasn't completed in time). Import your library "
                  "instead: open it in your usual browser, scroll to the bottom, press Ctrl+S and save it as "
                  "\"Webpage, Single File\" (each page of it, and for Payhip each shop's), then choose Import pages here.")


def video_shots(page, browser, srv, snap, click, theme: str, lang: str, made: dict) -> None:
    """The pictures only the videos use (issues #273, #274), taken after the website's, as they change what's in the
    made-up library: Hoard as it is in each help video's problem, and the parts the long promo shows (choosing
    files, updates, the hidden library, notifications)."""
    from hoard import alerts, marks, net, vault
    from hoard.asset_updates import AssetUpdates
    now, catalog = made["now"], downloader.collect_catalog(made["cfg"], Path(made["cfg"]["root"]))[0]
    booth = [e for e in catalog if str(e["store"]).lower() == "booth"]

    def library(url=None):
        """The Library (or another page), read again."""
        page.goto(srv.entry_url())
        page.reload()
        if url:
            page.goto(srv.url + url)
        page.locator(".slot").first.wait_for()
        page.wait_for_timeout(900)

    def store_row(store, **info):
        with srv.lib.lock:
            srv.lib.data["stores"][store] = {**srv.lib.data["stores"].get(store, {"count": 0, "source": "refresh"}), **info}

    def stores(name, settle=700):
        library()
        click("#storesBtn")
        snap(name, settle)
        page.keyboard.press("Escape")

    # What files do you want to save? (issue #225), with two of them left out
    e = booth[0]
    stem = safe_name(e["name"])
    names = [f"{stem}.unitypackage", f"{stem} (Quest).unitypackage", "Textures.zip", f"{stem}.psd", "Read me.pdf"]
    library()
    page.evaluate("p => askFiles(p, () => {})", {"key": tag_key("booth", e["name"]), "store": "booth", "name": e["name"],
                                                 "creator": e["creator"], "names": names})
    page.wait_for_timeout(700)
    page.locator("#filesPick").click()
    for n in (names[1], names[3]):   # the Quest version and the PSD, left out
        page.locator(f'#filesList input[data-file="{n}"]').uncheck()
    snap("files", 600)
    page.keyboard.press("Escape")
    # Asset updates: two downloads with newer files on Booth
    AssetUpdates().record_check(["booth"], None, [
        {"key": tag_key("booth", x["name"]), "store": "booth", "name": x["name"], "creator": x["creator"], "file": f, "kind": k}
        for x, f, k in ((booth[1], "Textures.zip", "changed"), (booth[1], "Extra colours.zip", "new"),
                        (booth[2], f"{safe_name(booth[2]['name'])}.unitypackage", "changed"))])
    library("downloads")
    click('#views [data-view="updates"]')
    page.wait_for_timeout(600)
    page.locator(".slot").first.click()
    page.wait_for_timeout(600)
    page.evaluate(BRING_INTO_VIEW, "#detail .update")
    snap("updates", 900)
    page.keyboard.press("Escape")
    # Hoard's looks: its other layouts (Treasure, Workbench) and some of its colour themes, then Settings' Appearance
    shown = dict(srv.cfg.get("display") or {})
    for name, style, colours in LOOKS:
        srv.cfg["display"] = {**shown, "style": style, "theme": colours}
        library()
        snap(name, 900)
    srv.cfg["display"] = shown
    library()
    click("#settingsBtn")
    page.wait_for_timeout(500)
    page.evaluate("document.getElementById('part-look').scrollIntoView({block: 'start'})")
    snap("settings-look", 700)
    page.keyboard.press("Escape")
    # Notifications through Apprise: two addresses kept (made up), and a test one of them didn't take
    fake = ["discord://000000000000000000/made-up-token", "ntfys://ntfy.sh/hoard-made-up"]
    alerts.available = lambda: True
    alerts.urls = lambda cfg: list(fake)
    alerts.described = lambda cfg: [alerts.describe(u) for u in fake]
    alerts.kept = lambda cfg: len(fake)
    alerts.deliver = lambda *a, **k: ("Discord didn't take it: Failed to send Discord notification: Unauthorized - 401. "
                                      "Check its address, and that it can be reached from this computer.")
    srv.cfg["apprise_events"] = ["new", "updates", "prices", "tasks"]
    library()
    click("#settingsBtn")
    page.wait_for_timeout(500)
    page.evaluate("document.getElementById('part-apprise').scrollIntoView({block: 'start'})")
    snap("settings-apprise", 700)
    page.locator("#appriseTest").click()
    page.wait_for_timeout(900)
    snap("help-apprise-test", 200)
    page.keyboard.press("Escape")
    # Stores: security software stopped Hoard reaching Booth; Payhip's bot check; itch.io's API key
    was = {s: dict(srv.lib.data["stores"].get(s) or {}) for s in ("booth", "payhip", "itch")}
    store_row("booth", error=net.blocked_message("booth.pm"))
    stores("help-blocked-stores")
    store_row("booth", error=None)
    store_row("payhip", error=PAYHIP_BLOCKED)
    stores("help-payhip-stores")
    store_row("payhip", error=None)
    has_key = vault.has_key
    vault.has_key = lambda cfg, name: name == "itch" or has_key(cfg, name)
    store_row("itch", error="itch.io didn't accept the API key")
    stores("help-itch-stores")
    library()
    click("#storesBtn")
    click("#storeRows [data-login=itch]", "#itchDialog[open]")
    page.locator("#itchKey").fill("made-up-key-for-the-pictures-0000000000")
    snap("help-itch-key", 500)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    store_row("itch", error=None, count=4, updated=now.isoformat())
    stores("help-itch-fixed")
    vault.has_key = has_key
    with srv.lib.lock:
        for s, info in was.items():
            if info:
                srv.lib.data["stores"][s] = info
            else:
                srv.lib.data["stores"].pop(s, None)
    # A download that partly failed, in Tasks: what didn't come, and why
    gum = [x for x in catalog if str(x["store"]).lower() == "gumroad"] or booth
    stopped = f"Booth: {booth[3]['creator']} / {booth[3]['name']} / {safe_name(booth[3]['name'])}.zip - the download stopped at 31457280 of 52428800 bytes; the next sync resumes it"
    no_page = f"Gumroad: {gum[0]['name']} - no download page (refunded or membership inactive)"
    if not any(h["id"] == "j0" for h in srv.jobs.history):
        srv.jobs.history.insert(0, {
            "id": "j0", "task": "download", "label": "Download: Booth, Gumroad", "stores": ["booth", "gumroad"],
            "started": (now - timedelta(minutes=12)).isoformat(), "ended": (now - timedelta(minutes=5)).isoformat(),
            "outcome": "partial", "message": "Done: 3 new, 1 updated, 1 couldn't be downloaded.",
            "report": {"new_assets": 3, "new_files": 5, "updated": 1, "skipped": 1, "failed": 1, "problems": [stopped],
                       "skipped_list": [no_page]},
            "log": ["Reading Booth", "Reading Gumroad", "Downloading 6 files", "", "=== Summary ===",
                    "New assets: 3   New files: 5   Updated files: 1   Skipped: 1   Failed: 1", "", "Skipped:",
                    f"  - {no_page}", "", "Failed:", f"  - {stopped}"]})
    library()
    click("#tasksTab")
    page.locator('#tasksBody details[data-id="j0"] summary').click()
    snap("help-download-tasks", 700)
    page.keyboard.press("Escape")
    # Hoard's page opened without this run's access key (an old bookmark): "Hoard didn't recognise this page"
    ctx = browser.new_context(viewport=SIZE, color_scheme=theme, locale=LOCALES[lang])
    other = ctx.new_page()
    other.add_init_script(NO_VERSION)
    other.goto(srv.url)
    other.locator("#splash").wait_for(state="detached")
    snap("help-nokey", 900, pg=other)
    ctx.close()
    # The hidden library: three products hidden behind a PIN; unlocked, its PIN forgotten and reset, and too many tries
    ms = marks.MarkStore()
    if not ms.load().get("pin"):
        HIDDEN["phrase"] = ms.set_pin(HIDDEN["pin"])
        hide = [tag_key(x["store"], x["name"]) for x in made["items"][4:7]]
        ms.change("hidden", set(hide), True, {i["key"]: k for i in made["items"] if (k := tag_key(i["store"], i["name"])) in hide})
    library()
    page.evaluate("pin => apiPost('/api/unlock', { pin })", HIDDEN["pin"])
    page.evaluate("load().then(() => showView('hidden'))")
    page.wait_for_timeout(900)
    snap("hidden", 700)
    page.evaluate("apiPost('/api/lock')")
    library()
    click('#views [data-view="hidden"]', "#pinDialog[open]")
    snap("help-pin-unlock", 500)
    page.locator("#pinForgot").click()
    page.locator("#recoverWords").fill(HIDDEN["phrase"] or "")
    new_pin = "1357" if HIDDEN["pin"] == "2468" else "2468"
    page.locator("#pinInput").fill(new_pin)
    page.locator("#pinAgain").fill(new_pin)
    snap("help-pin-recover", 500)
    page.locator("#pinOk").click()
    page.wait_for_timeout(1200)
    HIDDEN["pin"] = new_pin
    snap("help-pin-fixed", 300)
    page.evaluate("apiPost('/api/lock')")
    kept = ms.path.read_bytes()   # (the tries are undone after: the next theme's pictures start afresh)
    library()
    click('#views [data-view="hidden"]', "#pinDialog[open]")
    for _ in range(6):
        page.locator("#pinInput").fill("0000")
        page.locator("#pinOk").click()
        page.wait_for_timeout(350)
    snap("help-pin-wait", 300)
    page.keyboard.press("Escape")
    ms.path.write_bytes(kept)


def shoot(items: list[dict], out: Path, style: str = "standard", themes=("dark", "light"), only=None,
          lang: str = "en", regions: dict | None = None) -> None:
    """Take every screenshot, in each theme, from a made-up library of the products."""
    from playwright.sync_api import sync_playwright
    root, made = build(items)
    made["cfg"]["display"] = {**made["cfg"].get("display", {}), "style": style, "language": lang}
    # what a usual computer says (this one may have no keyring, and its folders are made up for the pictures)
    server.signin_protection = lambda cfg: "encrypted by your Windows account"
    from pathlib import PureWindowsPath
    server.signins_root = lambda cfg: PureWindowsPath(r"C:\Users\you\AppData\Local\Hoard\sign-ins")
    signed = set()   # the stores signed in, in the pictures (none, but for the help videos' Booth)
    server.signed_in = lambda cfg, store: store in signed
    srv = server.AppServer(("127.0.0.1", 0), made["cfg"], lan=False)
    now = made["now"]
    with srv.lib.lock:   # in memory only
        srv.lib.data["items"] = made["items"]
        for s in STORES:
            n = sum(1 for i in made["items"] if i["store"] == s)
            if n:
                srv.lib.data["stores"][s] = {"count": n, "error": None, "source": "refresh", "updated": now.isoformat(),
                                             "first_read": (now - timedelta(days=90)).isoformat()}
    srv.jobs.history = [
        {"id": "j1", "task": "sync", "label": "Sync: Booth, Gumroad, Jinxxy", "stores": ["booth", "gumroad", "jinxxy"],
         "started": (now - timedelta(minutes=40)).isoformat(), "ended": (now - timedelta(minutes=36)).isoformat(),
         "outcome": "done", "message": "Downloaded 3 new files.", "report": None, "log": ["Reading Booth", "Downloaded 3 new files."]},
        {"id": "j2", "task": "wishlists", "label": "Read wishlists: Booth, Gumroad", "stores": ["booth", "gumroad"],
         "started": (now - timedelta(minutes=34)).isoformat(), "ended": (now - timedelta(minutes=33)).isoformat(),
         "outcome": "done", "message": "Read 2 wishlists. 2 products are cheaper now.", "report": None, "log": []},
        {"id": "j3", "task": "verify", "label": "Check downloads (automatic)", "stores": [],
         "started": (now - timedelta(minutes=30)).isoformat(), "ended": (now - timedelta(minutes=29)).isoformat(),
         "outcome": "done", "message": "All files are as Hoard downloaded them.", "report": None, "log": []}]
    jobs.tasks_file = lambda: WORK / "tasks.json"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out.mkdir(parents=True, exist_ok=True)
    shots = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme in themes:
            page = browser.new_page(viewport=SIZE, color_scheme=theme, locale=LOCALES[lang])
            page.add_init_script(SEEDED)
            page.add_init_script(NO_VERSION)

            def snap(name, settle=500, pg=None):
                """Take one screenshot, after the page settles, with nothing hovered."""
                if only and name not in only:
                    return
                pg = pg or page
                pg.mouse.move(SIZE["width"] - 4, SIZE["height"] - 4)   # nothing hovered
                pg.wait_for_timeout(settle)
                pg.evaluate(SHOW_PATHS, str(WORK))
                path = out / ((f"{name}-{theme}" if style == "standard" else f"{name}-{style}-{theme}")
                              + ("" if lang == "en" else f"-{lang}") + ".png")
                pg.screenshot(path=str(path))
                shots.append(path)
                if regions and name in regions:
                    boxes = pg.evaluate(REGION_BOXES, regions[name])
                    missing = [k for k, v in boxes.items() if v is None]
                    if missing:
                        print(f"{path.name}: nothing shows for {', '.join(missing)}")
                    path.with_suffix(".json").write_text(json.dumps(boxes, indent=1), "utf-8")

            def video_snap(name, show, settle=900):
                """A picture for the videos only (taken with --regions): scrolled so that show (a selector), and
                what's round it, is whole on the page, for a video to look at closely."""
                if not regions and not (only and name in only):
                    return
                if only and name not in only:
                    return
                page.evaluate(BRING_INTO_VIEW, show)
                snap(name, settle)

            def click(selector, wait=None):
                """Click something, and wait for what it opens (from the bar's Menu, when it's in there)."""
                if selector in ("#tagsBtn", "#storesBtn", "#settingsBtn") and not page.locator(selector).first.is_visible():
                    page.click("#menuBtn")
                page.locator(selector).first.click()
                if wait:
                    page.locator(wait).first.wait_for()

            page.goto(srv.entry_url())
            page.locator(".slot").first.wait_for()
            page.wait_for_timeout(1200)   # pictures and the glow
            snap("library")
            click(".slot")
            snap("library-details", 700)
            page.keyboard.press("Escape")
            for button, name in (("#tagsBtn", "tags"), ("#storesBtn", "stores"), ("#settingsBtn", "settings"),
                                 ("#tasksTab", "tasks")):
                click(button)
                snap(name, 700)
                page.keyboard.press("Escape")
            # for the help videos (issue #274): Booth ended Hoard's sign-in, as Hoard shows it
            if (regions and not only) or {"help-booth-library", "help-booth-stores", "help-booth-fixed"} & set(only or ()):
                with srv.lib.lock:
                    srv.lib.data["stores"]["booth"] = {**srv.lib.data["stores"]["booth"], "error": "Not signed in to Booth"}
                page.goto(srv.entry_url())
                page.reload()   # (the same address: a reload, so the page reads the library again)
                page.locator(".slot").first.wait_for()
                page.wait_for_timeout(1200)
                snap("help-booth-library", 600)
                click("#storesBtn")
                snap("help-booth-stores", 700)
                page.keyboard.press("Escape")
                with srv.lib.lock:   # and signed in again: Booth's row as it is then
                    srv.lib.data["stores"]["booth"]["error"] = None
                signed.add("booth")
                page.goto(srv.entry_url())
                page.reload()
                page.locator(".slot").first.wait_for()
                page.wait_for_timeout(900)
                click("#storesBtn")
                snap("help-booth-fixed", 700)
                page.keyboard.press("Escape")
                signed.discard("booth")
                page.reload()
                page.locator(".slot").first.wait_for()
                page.wait_for_timeout(600)
            # Projects: the list, a project's details, its packages and its source control, a new project, the backups
            click("#projectsTab", ".pj-row")
            page.locator("#pjSplash").wait_for(state="hidden")   # (its splash, the first time it's opened)
            snap("projects", 900)
            page.locator(".pj-row", has_text="My Avatar").locator(".pj-open").first.click()
            page.locator(".pj-detail").first.wait_for()
            snap("project-details", 1500)   # (its size and packages, read as it opens)
            click(".pj-detail [data-pj=manage]", "[data-pj=back]")
            snap("project-manage", 900)
            click(".pj-subs [data-sub=git]", ".pj-git")
            snap("project-git", 1200)
            click("[data-pj=back]", ".pj-row")
            for button, name in (("[data-pj=new]", "project-new"), ("[data-pj=backups]", "project-backups")):
                click(button, "[data-pj=back]")
                snap(name, 900)
                click("[data-pj=back]", ".pj-row")
            page.keyboard.press("Escape")
            # Sets: every set and wishlist, a set opened, a wishlist with its prices, and Mix and match
            click('#storeSeg [data-store="Sets"]', "[data-setopen]")
            snap("sets", 1200)
            page.evaluate("setExtraOpen = false")   # (Note and photos, folded: the products first)
            page.locator("[data-setopen]", has_text=SETS[0][0]).first.click()
            page.locator("[data-setx=back]").first.wait_for()
            snap("set", 1200)
            click("[data-setx=back]", "[data-setopen]")
            page.locator("[data-setopen]", has_text="Booth").first.click()
            page.locator("[data-setx=back]").first.wait_for()
            snap("wishlist", 1200)
            video_snap("wishlist-prices", ".slot:has(.price.down)")
            click("[data-setx=back]", "[data-setopen]")
            page.evaluate("MIX.fit = false")   # (the sample's clothes aren't tagged for its avatar)
            click("[data-setx=mix]", "dialog.mixdlg")
            snap("mix", 900)
            page.keyboard.press("Escape")
            page.goto(srv.url + "downloads")
            page.locator(".slot").first.wait_for()
            snap("downloads", 1200)
            page.locator(".slot:not(:has-text('My Texture Set'))").first.click()   # a store's, not your own
            snap("downloads-details", 700)
            video_snap("downloads-files", "#detail ul.files li:has([data-act=inside])")
            page.keyboard.press("Escape")
            click('#views [data-view="space"]')
            snap("space", 1500)
            click('#views [data-view="downloads"]')
            page.goto(srv.url + "downloads#store=Local")
            page.locator(".slot").first.wait_for()
            snap("local", 900)
            page.locator(".slot", has_text="My Texture Set").first.click()
            click('#detail [data-act="inside"]', "#insideWin:not([hidden])")
            for folder in ("Assets", "My Texture Set", "Fabric", "Metal"):   # open, a folder at a time
                page.locator("#insideWin summary", has_text=folder).last.click()
                page.wait_for_timeout(250)
            snap("inside", 1200)
            page.keyboard.press("Escape")
            page.keyboard.press("Escape")
            click("#localAdd")
            snap("local-add", 600)
            page.keyboard.press("Escape")
            if (regions and not only) or VIDEO_SHOTS & set(only or ()):
                video_shots(page, browser, srv, snap, click, theme, lang, made)
            page.close()
        browser.close()
    srv.shutdown()
    try:
        from PIL import Image
        for p in shots:
            img = Image.open(p)
            img.save(p.with_suffix(".webp"), quality=86, method=6)
            for w in WIDTHS:
                img.resize((w, round(img.height * w / img.width)), Image.LANCZOS).save(
                    p.with_name(f"{p.stem}-{w}.webp"), quality=84, method=6)
    except ImportError:
        print("(Pillow isn't installed, so there are no .webp copies)")
    print(f"{len(shots)} screenshots in {out}")


if __name__ == "__main__":
    given = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    if not given or opts.get("style", "standard") not in server.themes.STYLES or opts.get("lang", "en") not in LOCALES:
        sys.exit(__doc__)
    try:
        shoot(products(Path(given[0])), Path(given[1]) if len(given) > 1 else REPO / "build" / "screenshots",
              opts.get("style", "standard"), tuple(opts.get("themes", "dark,light").split(",")),
              set(opts["only"].split(",")) if opts.get("only") else None, opts.get("lang", "en"),
              json.loads(Path(opts["regions"]).read_text("utf-8")) if opts.get("regions") else None)
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
