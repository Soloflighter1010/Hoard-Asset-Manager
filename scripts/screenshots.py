"""Screenshots of every part of Hoard, for the website and the README, made from real products you choose.

    python scripts/screenshots.py PRODUCTS_FOLDER [OUT_FOLDER]

PRODUCTS_FOLDER holds each product's picture (PNG, JPEG, WebP or GIF) and products.json, listing them:

    [{"image": "fox-ears.png", "name": "Fox Ears", "creator": "Your Shop", "store": "jinxxy",
      "url": "https://jinxxy.com/...", "tags": ["ears", "accessory"]}, ...]

"store" is booth, gumroad, jinxxy, payhip or itch; "url" and "tags" are optional. Without products.json, every
picture in the folder is a product named after its file, from Jinxxy. A product whose picture isn't there is
skipped. scripts/export_screenshot_products.py makes this folder from your own Hoard library.

Hoard runs on a made-up data folder of its own (never yours): those products are your library, most of them
downloaded, with a Local item, a Unity project using some of them, a finished check and a few tasks. Then each part
is photographed, in the dark and light themes, at 1600x950: OUT_FOLDER/<part>-<theme>.png (and .webp, for the
website). Nothing is fetched from the internet: the pictures come from the folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix="hoard-shots-"))
os.environ["HOARD_DATA_DIR"] = str(WORK / "appdata")   # before Hoard is imported: its folders come from this
sys.path.insert(0, str(REPO))

from hoard import config, downloader, jobs, library, projects, server  # noqa: E402
from hoard.paths import THUMB_DIR  # noqa: E402
from hoard.safety import safe_name  # noqa: E402
from hoard.tags import TagStore, tag_key  # noqa: E402

STORES = ("booth", "gumroad", "jinxxy", "payhip", "itch")
PICTURES = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp", ".gif": "gif"}
SIZE = {"width": 1600, "height": 950}


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
        out.append({**p, "store": store, "id": str(1000 + n), "picture": pic})
    if len(out) < 4:
        sys.exit("Add at least 4 products, so the pages look like a library.")
    return out


def build(items: list[dict]) -> tuple[Path, dict]:
    """The made-up data folder and downloads folder, with these products in them."""
    root = WORK / "Hoard"
    root.mkdir()
    now = datetime.now(timezone.utc)
    lib_items, tags = [], TagStore()
    for n, p in enumerate(items):
        added = (now - timedelta(days=n * 3)).isoformat(timespec="seconds")
        thumb = f"https://hoard.invalid/screens/{p['id']}{p['picture'].suffix.lower()}"   # cached below: never fetched
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(p["picture"], THUMB_DIR / f"{hashlib.sha1(thumb.encode()).hexdigest()}.{PICTURES[p['picture'].suffix.lower()]}")
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
    cfg = {**config.load_config(), "root": str(root), "setup_done": True}
    own = WORK / "My Texture Set"   # your own: a texture set, copied into Local (no one else's picture)
    (own / "Textures").mkdir(parents=True)
    with open(own / "My Texture Set.unitypackage", "wb") as fh:
        fh.truncate(18_500_000)
    (own / "Textures" / "README.txt").write_text("Fabric and metal textures, 2048px.", "utf-8")
    from hoard import local
    local.add(cfg, root, str(WORK / "My Texture Set"), note="A commission", copy=True)
    downloader.build_catalog(cfg, root)
    # a Unity project using some of them, as Hoard for Unity reports it
    catalog = downloader.collect_catalog(cfg, root)[0]
    report = {"format": "hoard-project", "version": 1, "name": "My Avatar", "path": "C:\\Unity\\My Avatar",
              "unity": "2022.3.22f1", "updated": (now - timedelta(hours=2)).isoformat(timespec="seconds"),
              "assets": [{"store": e["store"], "name": e["name"], "creator": e["creator"], "folder": e["folder"],
                          "url": e["url"], "status": "yes" if n != 2 else "partly"} for n, e in enumerate(catalog[:5])],
              "credits": {"title": "Assets used", "style": "List", "left_out": [], "added": []}}
    projects.projects_dir().mkdir(parents=True, exist_ok=True)
    (projects.projects_dir() / "0123456789abcdef.json").write_text(json.dumps(report), "utf-8")
    downloader.check_integrity(root)
    return root, {"items": lib_items, "cfg": cfg, "now": now}


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
        {"id": "j2", "task": "verify", "label": "Check downloads (automatic)", "stores": [],
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
            page.goto(srv.entry_url())
            page.locator(".slot").first.wait_for()
            page.wait_for_timeout(1200)   # pictures and the glow

            def snap(name, settle=500):
                page.mouse.move(SIZE["width"] - 4, SIZE["height"] - 4)   # nothing hovered
                page.evaluate("v => { const r = document.querySelector('#setRoot'); if (r) r.value = v; }",
                              "C:\\Users\\you\\Documents\\Hoard")   # shown, never saved
                page.wait_for_timeout(settle)
                path = out / f"{name}-{theme}.png"
                page.screenshot(path=str(path))
                shots.append(path)

            snap("library")
            page.locator(".slot").first.click()
            snap("library-details", 700)
            page.keyboard.press("Escape")
            for button, name in (("#tagsBtn", "tags"), ("#storesBtn", "stores"), ("#settingsBtn", "settings"),
                                 ("#tasksTab", "tasks"), ("#projectsTab", "projects")):
                page.click(button)
                snap(name, 700)
                page.keyboard.press("Escape")
            page.goto(srv.url + "downloads")
            page.locator(".slot").first.wait_for()
            snap("downloads", 1200)
            page.locator(".slot:not(:has-text('My Texture Set'))").first.click()   # a store's, not your own
            snap("downloads-details", 700)
            page.keyboard.press("Escape")
            page.goto(srv.url + "downloads#store=Local")
            page.locator(".slot").first.wait_for()
            snap("local", 900)
            page.click("#localAdd")
            snap("local-add", 600)
            page.close()
        browser.close()
    srv.shutdown()
    try:
        from PIL import Image
        for p in shots:
            Image.open(p).save(p.with_suffix(".webp"), quality=86, method=6)
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
