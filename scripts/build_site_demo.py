"""Try Hoard on the website (issue #394): Hoard's own pages, running in the visitor's browser with a stand-in for
Hoard's local server (site/demo/demo.js), built from the app's pages each time the website is built, so the demo
never drifts from the app.

    python3 scripts/build_site_demo.py <folder>           builds the demo into <folder> (the website's demo/)
    python3 scripts/build_site_demo.py --read-products    reads site/demo/products.json's products again, from their
                                                          stores' public pages

What it writes:
- index.html and downloads.html: the app's page, as Hoard's server makes it (server.page_source), with the stand-in
  before the app's own script and what Hoard's server answered its pages inside it (data, as JSON that's never run).
  Its policy lets it load pictures from the stores' image hosts (and a shared set's photos from the photo sites Hoard
  takes), and fetch nothing but a short link's locked set from Hoard's share server, when one's added: nothing else a
  visitor does can leave their browser.
- fonts/: the app's fonts.

The answers are a real Hoard's: a server with a data folder of its own (the products in products.json, two tags, a
set, a wishlist and a made-up project), its pages walked through in a browser (Library, a product's details,
Downloads, Sets and Wishlists, Projects, Settings, Stores, Tags, Tasks) and every answer the pages were given kept.
Pictures aren't fetched: the demo loads them from the stores themselves, as the website's set viewer does.

products.json lists the products to show (the maintainer's own, or ones whose creators agreed: issue #394), as their
stores' pages say them: name, creator, price, and the picture's address on the store's own image host. Needs
Hoard's requirements and Playwright's Chromium (as the tests do).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qsl, urlencode, urlparse

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
PRODUCTS = REPO / "site" / "demo" / "products.json"
STAND_IN = "demo.js"   # site/demo/demo.js, beside the pages it's built into
# where the stores keep their products' pictures (the set viewer's own list: site/set.html): the only places the demo
# loads anything from, but the website itself
IMAGE_HOSTS = ("https://booth.pximg.net", "https://public-files.gumroad.com", "https://jinxxy-c.jinxxy-cdn.com",
               "https://images.payhip.com", "https://img.itch.zone")
# a shared set's photos may be on these (the set viewer's, and Hoard's, list: site/set.js, hoard/sets.py)
PHOTO_HOSTS = ("https://i.imgur.com", "https://i.gyazo.com", "https://pbs.twimg.com", "https://cdn.bsky.app", "https://i.redd.it",
               "https://i.postimg.cc", "https://i.ibb.co", "https://cdn.discordapp.com", "https://media.discordapp.net")
SHARE_SERVER = "https://hoard-share.furryup.link"   # a short link's locked set, fetched when one's added (demo.js)
OLD = "2026-09-01T10:00:00+00:00"   # when the demo's products were bought (and its stores first read)
SHOWN_HOME = "C:/Users/You"   # where the demo's folders seem to be (the build's own folder is never shown)
READS = ("/api/local/sync",)   # what the pages ask for with a POST and nothing in it, only to read (demo.js answers them)
# what the walk through the pages does on each, as scripts/i18n_strings.py does: a selector to click, "Escape", or ""
STEPS = {
    "/": ["", ".slot >> nth=0", "Escape", ".slot >> nth=3", "Escape", "#menuBtn", "#tagsBtn", "Escape", "#menuBtn",
          "#storesBtn", "Escape", "#menuBtn", "#settingsBtn", "Escape", "#tasksTab", "Escape",
          '#storeSeg [data-store="Sets"]', "[data-setopen] >> nth=0", "Escape", '#storeSeg [data-store="Sets"]',
          "[data-setopen] >> nth=1", "Escape", '#storeSeg [data-store=""]', '[data-view="archive"]',
          '[data-view="library"]', "#projectsTab", "[data-hay] >> nth=0", "[data-pj=manage] >> nth=0",
          "[data-pj=back]", "Escape"],
    "/downloads": ["", ".slot >> nth=0", "Escape", '[data-view="updates"]', '[data-view="space"]',
                   '[data-view="downloads"]', '#storeSeg [data-store="Sets"]', "[data-setopen] >> nth=0", "Escape"],
}


def lighter(url: str) -> str:
    """A store picture's address asking for one no bigger than the demo shows it, where the store's image host can make
    one (Jinxxy's: Cloudflare's image resizing, which it already asks for its format): a phone opening Try Hoard loads
    a fraction of each picture. Gumroad's have no size to ask for."""
    u = urlparse(url)
    prefix = "/cdn-cgi/image/"
    if u.hostname == "jinxxy-c.jinxxy-cdn.com" and u.path.startswith(prefix) and "/" in u.path[len(prefix):]:
        options = u.path[len(prefix):].split("/", 1)[0]
        if "width=" not in options:
            return url.replace(f"{prefix}{options}/", f"{prefix}width=640,{options}/", 1)
    return url


def products() -> list[dict]:
    """The demo's products (products.json), each checked: a store Hoard reads, a link to its own page there."""
    from hoard import library
    out = []
    for p in json.loads(PRODUCTS.read_text("utf-8"))["products"]:
        if library.store_link(p["store"], p["url"]) != p["url"] or not library.safe_url(p.get("thumbnail")):
            raise SystemExit(f"products.json: {p.get('url')} isn't a store page with a picture on its store's host")
        out.append({**p, "thumbnail": lighter(p["thumbnail"])})
    return out


def read_products() -> int:
    """Read each product in products.json again from its store's public page (as Add products by link does), keeping
    where it goes (place), and write them back."""
    import urllib.request
    from hoard import wishlists

    def fetch(url, hosts):
        """A public page, from those hosts only, as a browser asks for it."""
        if urlparse(url).hostname not in hosts:
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace"), r.headers.get("Content-Type", "")

    doc = json.loads(PRODUCTS.read_text("utf-8"))
    for p in doc["products"]:
        got = wishlists.from_product_page(p["url"], fetch)
        p.update({k: got[k] for k in ("name", "creator", "price", "thumbnail") if got.get(k)},
                 store_tags=got.get("store_tags") or [])
        print(f"{p['store']}: {p['name']} ({p['creator']})")
    PRODUCTS.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return 0


def seed(root: Path, chosen: list[dict]):
    """A Hoard to record: the products in its library and on a wishlist, two products downloaded, two tags, a set and
    a made-up project. Returns the server (not yet serving)."""
    from hoard import common, config, downloader, library, server, sets, tags
    srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root / "Hoard"), "setup_done": True,
                                              "ui": {"toured": True}}, lan=False)
    owned = [p for p in chosen if p["place"] == "library"]
    with srv.lib.lock:
        srv.lib.data["items"] = [library.item(p["store"], p["id"], name=p["name"], creator=p["creator"], url=p["url"],
                                              thumbnail=p["thumbnail"], added=OLD, store_tags=p["store_tags"])
                                 for p in owned]
        for s in {p["store"] for p in owned}:
            srv.lib.data["stores"][s] = {"count": sum(p["store"] == s for p in owned), "error": None,
                                         "source": "refresh", "first_read": OLD, "updated": common.now_iso()}
    for p in owned[:2] + [p for p in owned if p["store"] == "gumroad"][:1]:   # downloaded: their files in place
        store = downloader.STORE_DIRS[p["store"]]   # (the store's own folder, as Hoard keeps its downloads)
        man = downloader.Manifest(root / "Hoard" / store)
        rec = man.record(f"{p['store']}:{p['id']}", p["creator"], p["name"])
        folder = root / "Hoard" / store / rec["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^\w.-]+", "-", p["id"]) + ".unitypackage"
        with open(folder / name, "wb") as f:   # (as big as a real one, without taking the room: sparse)
            f.truncate(24 * 1024 * 1024)
        rec["files"]["f"] = {"path": name, "size": 24 * 1024 * 1024}
        man.save()
    srv.lib.save()   # (sealed, as Hoard keeps it: its links and pictures are trusted)
    tag_key = {p["url"]: tags.tag_key(p["store"], p["name"], p["id"]) for p in owned}
    avatars = [tag_key[p["url"]] for p in owned if re.search(r"avatar", p["name"], re.I)]
    tools = [tag_key[p["url"]] for p in owned if re.search(r"substance|filter|brush|gradient", p["name"], re.I)]
    store = tags.TagStore()
    for name, chosen_keys in (("Avatars", avatars), ("Texturing", tools)):
        store.change({"action": "create", "name": name})
        if chosen_keys:
            store.change({"action": "assign", "keys": chosen_keys, "add": [name]})
    keys = {p["url"]: tags.tag_key(p["store"], p["name"], p["id"]) for p in chosen}   # (as sets keep them)
    detail = {keys[p["url"]]: {"store": p["store"], "id": p["id"], "name": p["name"], "creator": p["creator"],
                               "url": p["url"], "thumbnail": p["thumbnail"], "price": p["price"]} for p in chosen}
    sets_ = sets.SetStore()
    sets_.change({"action": "create", "name": "Spooky night", "note": "For the Halloween world.",
                  "items": [keys[p["url"]] for p in owned if re.search(r"warg|pazuzu|aqua tail", p["name"], re.I)]},
                 details=detail.get)
    sets_.change({"action": "create", "name": "Wishlist", "kind": "wishlist",
                  "items": [keys[p["url"]] for p in chosen if p["place"] == "wishlist"]}, details=detail.get)
    return srv


def made_up_project(root: Path, chosen: list[dict]) -> dict:
    """Projects' made-up project, as the Creator Companion would list it (VRChat's SDK, one update to it), and what
    Hoard for Unity said of it: two of the products in it. Returns the environment to run with."""
    vcc, project = root / "vcc", root / "Unity" / "My Avatar"
    for sub in ("Assets", "ProjectSettings", "Packages/com.vrchat.base", "Packages/com.vrchat.avatars"):
        (project / sub).mkdir(parents=True, exist_ok=True)
    (project / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.22f1\n", "utf-8")
    (project / "Packages" / "manifest.json").write_text(json.dumps({"dependencies": {}}), "utf-8")
    (project / "Packages" / "vpm-manifest.json").write_text(json.dumps({
        "dependencies": {"com.vrchat.avatars": {"version": "3.7.0"}},
        "locked": {"com.vrchat.avatars": {"version": "3.7.0", "dependencies": {"com.vrchat.base": "3.7.0"}},
                   "com.vrchat.base": {"version": "3.7.0", "dependencies": {}}}}), "utf-8")
    labels = {"com.vrchat.base": "VRChat SDK - Base", "com.vrchat.avatars": "VRChat SDK - Avatars"}
    for name, label in labels.items():
        (project / "Packages" / name / "package.json").write_text(json.dumps(
            {"name": name, "version": "3.7.0", "displayName": label}), "utf-8")
    packages = {name: {"versions": {v: {"name": name, "version": v, "displayName": label, "unity": "2022.3",
                                        "url": f"https://packages.vrchat.com/{name}-{v}.zip",
                                        "vpmDependencies": {"com.vrchat.base": v} if name != "com.vrchat.base" else {}}
                                    for v in ("3.7.0", "3.10.5")}} for name, label in labels.items()}
    (vcc / "Repos").mkdir(parents=True, exist_ok=True)
    (vcc / "Repos" / "vrc-official.json").write_text(json.dumps({"repo": {
        "name": "Official", "id": "com.vrchat.repos.official", "url": "https://packages.vrchat.com/official?download",
        "packages": packages}}), "utf-8")
    (vcc / "settings.json").write_text(json.dumps({"userProjects": [str(project)]}), "utf-8")
    used = [p for p in chosen if p["place"] == "library" and p["store"] == "jinxxy"][:2]
    reports = Path(os.environ["HOARD_DATA_DIR"]) / "projects"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "aaaaaaaaaaaaaaaa.json").write_text(json.dumps({
        "format": "hoard-project", "version": 1, "name": "My Avatar", "path": str(project), "unity": "2022.3.22f1",
        "updated": OLD, "credits": {"style": "List"},
        "assets": [{"store": "Jinxxy", "name": p["name"], "creator": p["creator"],
                    "folder": f"Jinxxy/{p['creator']}/{p['name']}", "status": "yes"} for p in used]}), "utf-8")
    return {"HOARD_VCC_DIR": str(vcc)}


def homed(value, forms: list[str]):
    """value (an answer: a text, or lists and dicts of them) with the build's folder (each of its forms: as given, with
    /, and its real path, as a Mac's /var is /private/var) shown as SHOWN_HOME in each text, and the rest of a path in
    it written with /, on every system. (Never in an answer's JSON, where a Windows path's backslashes are doubled.)"""
    at_root = re.compile("(?:" + "|".join(map(re.escape, sorted(set(forms), key=len, reverse=True))) +
                         r")((?:[\\/][^\\/\"'<>\n:]*)*)")
    def walk(v):
        """v, shown."""
        if isinstance(v, str):
            return at_root.sub(lambda m: SHOWN_HOME + m.group(1).replace("\\", "/"), v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {walk(k) if isinstance(k, str) else k: walk(x) for k, x in v.items()}
        return v
    return walk(value)


def texts(value):
    """Every text in an answer, its keys too."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from texts(v)
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from texts(k)
            yield from texts(v)


def answer_key(url: str) -> str:
    """How the stand-in finds an answer: its path, and its query in order, without the access key."""
    u = urlparse(url)
    query = sorted((k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k != "k")
    return u.path + ("?" + urlencode(query) if query else "")


def record(srv) -> dict:
    """Walk the pages (STEPS) against the server, in a browser, and keep every answer it gave them ({key: answer});
    no picture is fetched (the demo loads them from the stores)."""
    from playwright.sync_api import sync_playwright
    answers: dict[str, object] = {}

    def kept(response):
        """One answer to a page's request: kept when it's Hoard's JSON, to a GET or to a read that's sent as a POST
        with nothing in it (READS: Settings' Local sync folder)."""
        req = response.request
        path = urlparse(req.url).path
        read = req.method == "GET" or (req.method == "POST" and path in READS and (req.post_data or "{}").strip() == "{}")
        if not read or not path.startswith("/api/") or response.status != 200:
            return
        try:
            answers[answer_key(req.url)] = response.json()
        except Exception:   # (not JSON: nothing the stand-in gives)
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for path, steps in STEPS.items():
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.route(re.compile(r".*/(thumb|setpic|setphoto)/.*"), lambda route: route.abort())
            page.on("response", kept)
            page.goto(srv.entry_url().replace("/#", path + "#", 1) if path != "/" else srv.entry_url())
            page.wait_for_timeout(2000)
            for step in steps:
                if step == "Escape":
                    page.keyboard.press("Escape")
                elif step:
                    try:
                        page.locator(step).first.click(timeout=3000)
                    except Exception as e:   # (a step the page doesn't offer: said, and the walk goes on)
                        print(f"  {path}: couldn't click {step}: {type(e).__name__}", file=sys.stderr)
                        continue
                page.wait_for_timeout(600)
            page.close()
        browser.close()
    return answers


def page(name: str, cfg: dict, data: dict) -> bytes:
    """The demo's page: the app's own (server.page_source), its pictures' addresses given by the stand-in, its fonts
    beside it, the stand-in and its data before the app's script, and a policy that lets nothing leave the browser but
    a short link's set, asked for."""
    from hoard import server
    from hoard.safety import content_security_policy
    src = server.page_source(name, cfg)
    given = b"const keyed = url => "
    if src.count(given) != 1:
        raise SystemExit("The page's keyed() isn't as the demo expects (scripts/build_site_demo.py)")
    src = src.replace(given, b"const keyed = url => window.HOARD_DEMO ? window.HOARD_DEMO.keyed(url) : ", 1)
    src = src.replace(b'url("/fonts/', b'url("fonts/')
    # the page's own scripts, by their hashes as Hoard's server gives them (safety.content_security_policy): the
    # stand-in is a file, and its data is JSON that's never run
    hashes = re.search(r"script-src ([^;]+);", content_security_policy(src)).group(1).replace("'none'", "").strip()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    head = (f'<script type="application/json" id="demo-data">{blob}</script>\n'
            f'<script src="{STAND_IN}"></script>\n').encode()
    if src.count(b"\n<script>\n") != 1:
        raise SystemExit("The page's script isn't where the demo expects it (scripts/build_site_demo.py)")
    src = src.replace(b"\n<script>\n", b"\n" + head + b"<script>\n", 1)
    policy = (f"default-src 'none'; script-src 'self' {hashes}; style-src 'self' 'unsafe-inline'; font-src 'self'; "
              f"img-src 'self' data: {' '.join(IMAGE_HOSTS + PHOTO_HOSTS)}; connect-src {SHARE_SERVER}; "
              "base-uri 'none'; form-action 'none'")
    hosts = sorted({urlparse(p["thumbnail"]).hostname for p in data.get("products", []) if p.get("thumbnail")})
    early = "".join(f'<link rel="preconnect" href="https://{h}">\n' for h in hosts)   # (the pictures' hosts, ahead of them)
    meta = (f'<meta http-equiv="Content-Security-Policy" content="{policy}">\n'
            '<meta name="robots" content="noindex">\n' + early).encode()
    src = src.replace(b'<meta charset="utf-8">', b'<meta charset="utf-8">\n' + meta, 1)
    return re.sub(rb"<title>[^<]*</title>", b"<title>Try Hoard</title>", src, count=1)


def build(out: Path, root: Path) -> None:
    """Build the demo into out, with root for the Hoard it records (its data folder: HOARD_DATA_DIR, set before any of
    Hoard is imported, as Hoard fixes where its data is when it's first imported)."""
    from hoard import alerts, server
    chosen = products()
    out.mkdir(parents=True, exist_ok=True)
    with mock.patch.object(server, "save_config"), mock.patch.object(alerts, "available", lambda: False), \
            mock.patch.object(server.Jobs, "start", return_value="started"):
        os.environ.update(made_up_project(root, chosen))
        srv = seed(root, chosen)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            answers = record(srv)
        finally:
            srv.shutdown()
            srv.server_close()
        cfg = srv.cfg
    for need in ("/api/library", "/api/sets", "/api/settings", "/api/vpm"):
        if need not in answers:
            raise SystemExit(f"The walk through the pages never asked for {need}: see STEPS (scripts/build_site_demo.py)")
    forms = [str(root), root.as_posix(), str(root.resolve()), root.resolve().as_posix()]

    def home(text: str) -> str:
        """The build's folder, in what's shown, as SHOWN_HOME."""
        return homed(text, forms)

    def rekeyed(key: str) -> str:
        """An answer's key with the build's folder in its query (as a page asks for it) as SHOWN_HOME."""
        u = urlparse(key)
        query = sorted((k, home(v)) for k, v in parse_qsl(u.query, keep_blank_values=True))
        return u.path + ("?" + urlencode(query) if query else "")

    shown = {rekeyed(k): homed(v, forms) for k, v in answers.items()}
    if any(root.name in t for t in texts(shown)):   # (its name: hoard-demo-..., in any of its forms)
        raise SystemExit("The build's own folder is still in the demo's answers (scripts/build_site_demo.py)")
    # "New here" notes (shared.js's NEW_SPOTS) are for someone who's updated Hoard: seen, in the demo
    spots = re.findall(r'\{ id: "([a-z0-9-]+)", at:', (REPO / "hoard" / "web" / "shared.js").read_text("utf-8"))
    for got in (shown.get("/api/library"), shown.get("/api/assets")):
        if isinstance(got, dict) and isinstance(got.get("ui"), dict):
            got["ui"]["spots_seen"] = spots
    # Downloads' pictures are files in each product's folder, which the demo hasn't: each downloaded product's is its
    # store picture instead (demo.js gives _demo/<n> its address)
    pictures = {i["tag_key"]: i["thumbnail"] for i in shown["/api/library"]["items"] if i.get("thumbnail")}
    for n, a in enumerate((shown.get("/api/assets") or {}).get("assets") or []):
        if not a.get("thumb") and pictures.get(a.get("tag_key")):
            a["thumb"], a["thumb_v"] = f"_demo/{n}", None
            pictures[f"_demo/{n}"] = pictures[a["tag_key"]]
    from hoard import themes
    data = {"answers": shown, "products": chosen, "pictures": pictures,
            "themes": {t: {m: themes.css(t, m) for m in themes.MODES} for t in themes.THEMES},
            "signin": [{"store": s, "label": label} for s, label in (("jinxxy", "Jinxxy"), ("gumroad", "Gumroad"))
                       if any(p["store"] == s for p in chosen)]}
    for name, file in (("library.html", "index.html"), ("downloads.html", "downloads.html")):
        (out / file).write_bytes(page(name, cfg, data))
    # the app's fonts, as the website has them where it does: the Latin letters only (about 15 KB each, where the
    # app's, with Japanese and Korean, are over 1 MB: the demo is in English, and mostly opened on a phone)
    fonts = out / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in (REPO / "hoard" / "web" / "fonts").iterdir():
        if f.suffix in (".woff2", ".txt"):
            site = REPO / "site" / "fonts" / f.name
            shutil.copy2(site if site.is_file() else f, fonts / f.name)
    shutil.copy2(REPO / "site" / "demo" / STAND_IN, out / STAND_IN)
    print(f"Try Hoard: {len(answers)} answers, {len(chosen)} products, in {out}")


def main(argv: list[str]) -> int:
    """Build the demo, or read its products again."""
    if argv[:1] == ["--read-products"]:
        return read_products()
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="hoard-demo-") as tmp:
        os.environ.update(HOARD_DATA_DIR=str(Path(tmp) / "data"), HOARD_VCC_DIR="")
        if "hoard.paths" in sys.modules:
            raise SystemExit("Hoard was imported before its data folder was chosen (scripts/build_site_demo.py)")
        try:
            build(Path(argv[0]).resolve(), Path(tmp))
        finally:   # (its database closed before its folder goes: Windows won't delete a file that's open)
            if "hoard.storage" in sys.modules:
                sys.modules["hoard.storage"].close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
