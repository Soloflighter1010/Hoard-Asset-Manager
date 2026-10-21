"""Screenshots of every part of Hoard, for the website and the README, made from real products you choose.

    python scripts/screenshots.py PRODUCTS_FOLDER [OUT_FOLDER]

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
Nothing is fetched from the internet: the pictures come from the folder. Paths on the pages are shown as
C:\\Users\\you\\..., as a usual computer's would be.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
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


def swatch(rgb: tuple, size: int = 128) -> bytes:
    """A plain square picture (a texture's preview, in the sample's own package)."""
    try:
        from PIL import Image
    except ImportError:
        return b""
    out = io.BytesIO()
    Image.new("RGB", (size, size), rgb).save(out, "PNG")
    return out.getvalue()


def swatches(colours: tuple, size: int = 512) -> bytes:
    """Your texture set's own picture: its colours, side by side."""
    try:
        from PIL import Image
    except ImportError:
        return b""
    img, w = Image.new("RGB", (size, size)), size // 2
    for n, c in enumerate(colours[:4]):
        img.paste(Image.new("RGB", (w, w), c), ((n % 2) * w, (n // 2) * w))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def texture_package() -> bytes:
    """Your own texture set, as a real .unitypackage (Look inside reads it): folders, textures with previews and
    materials. Made up here, so no one else's work is shown inside."""
    files = [("Assets/My Texture Set", None, None),
             ("Assets/My Texture Set/Fabric", None, None),
             ("Assets/My Texture Set/Fabric/Denim.png", 2_400_000, (52, 78, 120)),
             ("Assets/My Texture Set/Fabric/Wool.png", 2_100_000, (168, 120, 96)),
             ("Assets/My Texture Set/Fabric/Velvet.png", 1_900_000, (110, 40, 72)),
             ("Assets/My Texture Set/Metal", None, None),
             ("Assets/My Texture Set/Metal/Brushed Steel.png", 2_600_000, (150, 156, 162)),
             ("Assets/My Texture Set/Metal/Gold Leaf.png", 2_300_000, (196, 160, 72)),
             ("Assets/My Texture Set/Materials", None, None),
             ("Assets/My Texture Set/Materials/Denim.mat", 4_200, None),
             ("Assets/My Texture Set/Materials/Gold Leaf.mat", 4_100, None)]
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        def add(name: str, data: bytes):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for n, (path, size, colour) in enumerate(files):
            guid = hashlib.md5(path.encode()).hexdigest()
            add(f"{guid}/pathname", path.encode())
            add(f"{guid}/asset.meta", b"fileFormatVersion: 2\nguid: " + guid.encode() + b"\n")
            if size is not None:
                add(f"{guid}/asset", bytes(size))
            if colour:
                preview = swatch(colour)
                if preview:
                    add(f"{guid}/preview.png", preview)
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
    cfg = {**config.load_config(), "root": str(root), "setup_done": True, "ui": {"toured": True}}
    own = WORK / "My Texture Set"   # your own: a texture set, copied into Local (no one else's picture)
    (own / "Textures").mkdir(parents=True)
    (own / "My Texture Set.unitypackage").write_bytes(texture_package())
    (own / "Textures" / "README.txt").write_text("Fabric and metal textures, 2048px.", "utf-8")
    from hoard import local
    local.add(cfg, root, str(WORK / "My Texture Set"), note="A commission", copy=True)
    picture = swatches(((52, 78, 120), (196, 160, 72), (110, 40, 72), (150, 156, 162)))
    if picture:   # its picture, chosen as you would (Choose a picture...)
        key = next(iter(downloader.Manifest(local.local_dir(root)).assets))
        local.choose_picture(cfg, root, key, base64.b64encode(picture).decode())
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
    downloader.check_integrity(root)
    return root, {"items": lib_items, "cfg": cfg, "now": now}


# Paths on the pages as a usual computer's (the made-up folder is in a temporary one): shown only, never saved
SHOW_PATHS = """work => {
  const fix = t => t.split(work).join("C:\\\\Users\\\\you").replace(/C:\\\\Users\\\\you\\S*/g, m => m.replace(/\\//g, "\\\\"));
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) if (n.nodeValue.includes(work)) n.nodeValue = fix(n.nodeValue);
  for (const i of document.querySelectorAll("input")) if (i.value.includes(work)) i.value = fix(i.value);
  const r = document.querySelector("#setRoot");
  if (r) r.value = "C:\\\\Users\\\\you\\\\Documents\\\\Hoard";
}"""
SEEDED = "(() => { let s = 20261021; Math.random = () => (s = (s * 16807) % 2147483647) / 2147483647; })()"   # (Mix and match's picks, the same each time)


def shoot(items: list[dict], out: Path) -> None:
    from playwright.sync_api import sync_playwright
    root, made = build(items)
    # what a usual computer says (this one may have no keyring, and its folders are made up for the pictures)
    server.signin_protection = lambda cfg: "encrypted by your Windows account"
    from pathlib import PureWindowsPath
    server.signins_root = lambda cfg: PureWindowsPath(r"C:\Users\you\AppData\Local\Hoard\sign-ins")
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
        for theme in ("dark", "light"):
            page = browser.new_page(viewport=SIZE, color_scheme=theme)
            page.add_init_script(SEEDED)

            def snap(name, settle=500):
                page.mouse.move(SIZE["width"] - 4, SIZE["height"] - 4)   # nothing hovered
                page.wait_for_timeout(settle)
                page.evaluate(SHOW_PATHS, str(WORK))
                path = out / f"{name}-{theme}.png"
                page.screenshot(path=str(path))
                shots.append(path)

            def click(selector, wait=None):
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
            # Projects: the list, a project's packages, a new project, and the backups
            click("#projectsTab", "[data-pj=manage]")
            snap("projects", 900)
            for button, name in (("[data-pj=manage]", "project-manage"), ("[data-pj=new]", "project-new"),
                                 ("[data-pj=backups]", "project-backups")):
                click(button, "[data-pj=back]")
                snap(name, 900)
                click("[data-pj=back]", "[data-pj=manage]")
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
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        shoot(products(Path(sys.argv[1])), Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "build" / "screenshots")
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
