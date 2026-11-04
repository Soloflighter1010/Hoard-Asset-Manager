"""Hoard's own screens, for the videos and posters (issues #273, #274, #292): Hoard runs on a made-up data folder (never
yours, as scripts/screenshots.py makes one), with a library of the products given, and each part of it is photographed
in each language, each in the theme and style its scene shows off, at 1920 x 1080.

    python3 promo/capture.py PRODUCTS_FOLDER OUT_FOLDER [--lang=en,ja,ko] [--only=library,stores]

PRODUCTS_FOLDER is a library as scripts/screenshots.py takes one (scripts/export_screenshot_products.py makes one from
your own Hoard, and promo/art.py draws made-up ones). OUT_FOLDER gets <shot>-<lang>.png for each shot in SHOTS, and
shots.json: what each one is, the theme it's in (for the video's lower third), and where its parts are, in each
language (for the video's rings and camera: FOCUS). Needs Playwright.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "scripts"))
import screenshots as shots  # noqa: E402   (first: it gives Hoard a made-up data folder before Hoard is imported)
from hoard import alerts, jobs, server  # noqa: E402
from hoard.marks import MarkStore  # noqa: E402
from hoard.tags import tag_key  # noqa: E402

VIEW = {"width": 1600, "height": 900}
SCALE = 1.2   # (1920 x 1080 pictures)
# the sets the made-up library has: (name, words in its products' names)
SETS = (("Winter outfit", ("Duffle Coat", "冬コート", "Ugly", "Santa Hat")),
        ("Photo kit", ("pixOcam", "PIXON400", "スナップカメラ", "eco camera", "VRCLens:", "Jelly Cam")),
        ("Night world", ("Moonlit Perch", "Deep Dusk", "Luminous Oasis", "ClockCounter", "EDJ")),
        ("Novabeast look", ("Novabeast Onesie", "Casual Clothes for the Novabeast", "Pound Tech Visor", "Candy Curls")))
ADDRESSES = [{"id": "a1b2c3d4e5f60718", "service": "Discord", "label": "webhook …4821"},
             {"id": "0f1e2d3c4b5a6978", "service": "ntfy", "label": "ntfy.sh, topic …ard"}]
BOOTH_SIGNED_OUT = "Not signed in. Choose Sign in, then close the browser window when you're done."
PAYHIP_BLOCKED = ("Payhip blocked the automated browser (a bot check). Import your library instead: open it in your usual "
                  "browser, scroll to the bottom, press Ctrl+S and save it as \"Webpage, Single File\" (each page of it, "
                  "and for Payhip each shop's), then choose Import pages here.")
FAILED_TASK = {"id": "jf", "task": "download", "label": "Download: Gumroad", "stores": ["gumroad"], "outcome": "partial",
               "message": "Downloaded 4 files. 1 couldn't be downloaded: see its line in the log.", "report": None,
               "log": ["Gumroad: Cybershader: no download page (a refund, or a membership that ended)", "Downloaded 4 files."]}

# Hoard's version isn't shown in the bar: the videos outlast it
NO_VERSION = ("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); "
              "s.textContent = '#version { display: none !important; }'; document.head.appendChild(s); });")
# name: (theme, light or dark, style, what to do on the page first)
SHOTS = {
    "library": ("hoard", "dark", "standard", "library"),
    "search": ("synthwave", "dark", "standard", "search"),
    "details": ("sakura", "light", "standard", "details"),
    "stores": ("frost", "dark", "standard", "stores"),
    "tasks": ("dragonfire", "dark", "standard", "tasks"),
    "downloads": ("geode", "dark", "standard", "downloads"),
    "downloads-details": ("moss", "light", "standard", "downloads-details"),
    "space": ("midnight", "dark", "standard", "space"),
    "inside": ("contrast", "dark", "standard", "inside"),
    "sets": ("sakura", "dark", "treasure", "sets"),
    "set": ("winter", "dark", "standard", "set"),
    "wishlist": ("spooky", "dark", "standard", "wishlist"),
    "mix": ("synthwave", "light", "standard", "mix"),
    "projects": ("frost", "light", "workbench", "projects"),
    "project": ("hoard", "dark", "treasure", "project"),
    "project-git": ("geode", "dark", "workbench", "project-git"),
    "project-new": ("moss", "dark", "standard", "project-new"),
    "settings-look": ("hoard", "light", "workbench", "settings-look"),
    "settings-apprise": ("dragonfire", "dark", "standard", "settings-apprise"),
    "hidden": ("midnight", "dark", "standard", "hidden"),
    "setup-notify": ("sakura", "dark", "standard", "setup-notify"),
    # for the sketch (#289): every store, searched at once
    "search-hoodie": ("hoard", "dark", "standard", "search-hoodie"),
    # for the troubleshooting videos: Hoard's own look
    "t-library": ("hoard", "dark", "standard", "library"),
    "t-booth": ("hoard", "dark", "standard", "booth-signed-out"),
    "t-payhip": ("hoard", "dark", "standard", "payhip-blocked"),
    "t-itch": ("hoard", "dark", "standard", "itch-key"),
    "t-stores": ("hoard", "dark", "standard", "stores"),
    "t-failed": ("hoard", "dark", "standard", "failed-task"),
    "t-apprise": ("hoard", "dark", "standard", "settings-apprise"),
    "t-key": ("hoard", "dark", "standard", "no-key"),
    "t-pin": ("hoard", "dark", "standard", "hidden"),
}

# the parts of each shot the video points at (rings, and the camera's moves): CSS selectors, the first one shown
# ("sel*": all of them shown, together). Where they are is measured in each language, as words differ in length.
FOCUS = {
    "library": {"tabs": "#storeSeg", "grid": "#grid", "filters": "#filters", "sync": "#syncBtn", "first": "#grid .slot",
                "row": "#grid .slot*"},
    "search": {"box": "#q", "menu": "#qMenu"},
    "details": {"panel": "#detail", "grid": "#grid"},
    "stores": {"win": "#stores", "rows": "#storeRows", "quick": "#quickRefresh", "all": "#refreshAll"},
    "tasks": {"win": "#tasksWin", "body": "#tasksBody"},
    "downloads": {"grid": "#grid", "views": "#views"},
    "downloads-details": {"panel": "#detail", "grid": "#grid"},
    "space": {"grid": "#grid", "views": "#views", "count": "#count"},
    "inside": {"win": "#insideWin"},
    "sets": {"sets": "[data-setopen]*", "mix": "[data-setx=mix]"},
    "set": {"head": ".sethead", "share": "[data-setx=share]", "grid": "#grid"},
    "wishlist": {"prices": ".ext-price*", "down": ".ext-price .price.down"},
    "mix": {"win": "dialog.mixdlg"},
    "projects": {"win": "#projectsWin", "rows": ".pj-row*"},
    "project": {"win": "#projectsWin", "subs": ".pj-subs"},
    "project-git": {"win": "#projectsWin", "git": ".pj-git"},
    "project-new": {"win": "#projectsWin"},
    "settings-look": {"panel": "#settingsPanel", "themes": "#themeChoices", "styles": "#styleChoices"},
    "settings-apprise": {"panel": "#settingsPanel", "list": "#appriseList", "events": "#appriseEvents"},
    "hidden": {"pin": "#pinDialog"},
    "setup-notify": {"win": "#setup", "fields": "#setupNotifyFields"},
    "search-hoodie": {"box": "#q", "grid": "#grid", "tabs": "#storeSeg", "count": "#count"},
    "t-library": {"grid": "#grid"},
    "t-booth": {"win": "#stores", "row": ".store-row:has(.dot.booth)", "note": ".store-row:has(.dot.booth) .err",
                "signin": ".store-row:has(.dot.booth) [data-login]"},
    "t-payhip": {"win": "#stores", "row": ".store-row:has(.dot.payhip)", "note": ".store-row:has(.dot.payhip) .err",
                 "import": ".store-row:has(.dot.payhip) [data-import]"},
    "t-itch": {"dialog": "#itchDialog", "key": "#itchKey", "save": "#itchSave"},
    "t-stores": {"win": "#stores", "rows": "#storeRows"},
    "t-failed": {"win": "#tasksWin", "body": "#tasksBody"},
    "t-apprise": {"list": "#appriseList", "events": "#appriseEvents", "panel": "#settingsPanel"},
    "t-key": {"page": "main"},
    "t-pin": {"pin": "#pinDialog", "forgot": "#pinForgot"},
}
MEASURE = """(want) => {
  const shown = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
  const out = {};
  for (const [name, sel] of Object.entries(want)) {
    const all = sel.endsWith("*"), found = [...document.querySelectorAll(all ? sel.slice(0, -1) : sel)].filter(shown);
    if (!found.length) continue;
    const rs = (all ? found : found.slice(0, 1)).map(e => e.getBoundingClientRect());
    const x = Math.max(0, Math.min(...rs.map(r => r.left))), y = Math.max(0, Math.min(...rs.map(r => r.top)));
    const x2 = Math.min(innerWidth, Math.max(...rs.map(r => r.right))), y2 = Math.min(innerHeight, Math.max(...rs.map(r => r.bottom)));
    if (x2 > x && y2 > y) out[name] = [x, y, x2 - x, y2 - y];
  }
  return out;
}"""


def git_project(path: Path) -> None:
    """A project under source control, with a commit and a change since (for its Git tab)."""
    from hoard.vpm import git
    git.set_up(path)
    git.stage(path, [f["path"] for f in git.state(path)["files"]])
    if not git.identity(path).get("name"):
        git.set_identity(path, "You", "you@example.com")
    git.commit(path, "My avatar, with its outfit")
    assets = path / "Assets"
    assets.mkdir(exist_ok=True)
    (assets / "Outfit.mat").write_text("color: pink\nshine: 0.4\n", "utf-8")


def main(argv: list[str]) -> int:
    """Photograph every shot, in every language asked for."""
    from playwright.sync_api import sync_playwright
    given = [a for a in argv if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    if len(given) < 2:
        sys.exit(__doc__)
    folder, out = Path(given[0]), Path(given[1])
    langs = opts.get("lang", "en,ja,ko").split(",")
    only = set(opts["only"].split(",")) if opts.get("only") else None
    out.mkdir(parents=True, exist_ok=True)
    shots.SETS = SETS
    items = shots.products(folder)
    root, made = shots.build(items)
    from hoard.vpm import listing
    for p in listing.projects():
        if p["name"] == "My Avatar":
            try:
                git_project(Path(p["path"]))
            except Exception as e:   # (Git isn't installed: the Git tab shows how to set it up)
                print(f"No Git repository for the project: {e}")
    pinned = [i for i in made["items"] if "Water Gun" in i["name"]][:1]
    marks = MarkStore()
    marks.set_pin("2468")
    if pinned:
        marks.change("hidden", [tag_key(pinned[0]["store"], pinned[0]["name"])], True)
    server.signin_protection = lambda cfg: "encrypted by your Windows account"
    from pathlib import PureWindowsPath
    server.signins_root = lambda cfg: PureWindowsPath(r"C:\Users\you\AppData\Local\Hoard\sign-ins")
    cfg = made["cfg"]
    # the "new here" notes (issue #244) count as seen: the videos outlast them
    spots = re.findall(r'\{ id: "([a-z0-9-]+)", at:', (REPO / "hoard" / "web" / "shared.js").read_text("utf-8"))
    cfg["ui"] = {**cfg.get("ui", {}), "spots_seen": spots}
    cfg["apprise_events"] = ["new", "updates", "prices"]
    srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
    now = made["now"]
    with srv.lib.lock:
        srv.lib.data["items"] = made["items"]
        for s in shots.STORES:
            n = sum(1 for i in made["items"] if i["store"] == s)
            if n:
                srv.lib.data["stores"][s] = {"count": n, "error": None, "source": "refresh", "updated": now.isoformat(),
                                             "first_read": (now - timedelta(days=90)).isoformat()}
    when = lambda minutes: (now - timedelta(minutes=minutes)).isoformat()  # noqa: E731
    srv.jobs.history = [
        {"id": "j1", "task": "sync", "label": "Sync: Booth, Gumroad, Jinxxy", "stores": ["booth", "gumroad", "jinxxy"],
         "started": when(40), "ended": when(36), "outcome": "done", "message": "Downloaded 3 new files.", "report": None,
         "log": ["Reading Booth", "Downloaded 3 new files."]},
        {"id": "j2", "task": "quick-refresh", "label": "Quick refresh: Booth, Gumroad", "stores": ["booth", "gumroad"],
         "started": when(25), "ended": when(24), "outcome": "done", "message": "Library updated. 2 wishlists read", "report": None, "log": []},
        {"id": "j3", "task": "verify", "label": "Check downloads (automatic)", "stores": [],
         "started": when(20), "ended": when(19), "outcome": "done", "message": "All files are as Hoard downloaded them.", "report": None, "log": []}]
    jobs.tasks_file = lambda: shots.WORK / "tasks.json"
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    patches = [mock.patch.object(alerts, "available", lambda: True), mock.patch.object(alerts, "described", lambda c: list(ADDRESSES))]
    for p in patches:
        p.start()
    record = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for lang in langs:
            page = browser.new_page(viewport=VIEW, device_scale_factor=SCALE)
            page.add_init_script(shots.SEEDED)
            page.add_init_script(NO_VERSION)
            page.goto(srv.entry_url())
            page.locator(".slot").first.wait_for()
            for name, (theme, mode, style, state) in SHOTS.items():
                if only and name not in only:
                    continue
                cfg["display"] = {**cfg.get("display", {}), "theme": theme, "mode": mode, "style": style, "language": lang,
                                  "seasonal": True}
                try:
                    shot = take(page, browser, srv, state, lang)
                except Exception as e:
                    print(f"{name} ({lang}): couldn't be taken: {str(e).splitlines()[0][:200]}")
                    continue
                page.mouse.move(VIEW["width"] - 4, VIEW["height"] - 4)
                (shot or page).evaluate(shots.SHOW_PATHS, str(shots.WORK))
                path = out / f"{name}-{lang}.png"
                (shot or page).screenshot(path=str(path))
                boxes = (shot or page).evaluate(MEASURE, FOCUS.get(name, {}))
                if shot:
                    shot.close()
                record.setdefault(name, {"theme": theme, "mode": mode, "style": style, "boxes": {}})
                record[name]["boxes"][lang] = {k: [round(v * SCALE) for v in box] for k, box in boxes.items()}
                print(f"{path.name}")
            page.close()
        browser.close()
    for p in patches:
        p.stop()
    srv.shutdown()
    old = json.loads((out / "shots.json").read_text("utf-8")) if (out / "shots.json").exists() else {}
    for name, rec in record.items():   # (a few shots retaken: the rest are kept)
        rec["boxes"] = {**old.get(name, {}).get("boxes", {}), **rec["boxes"]}
    (out / "shots.json").write_text(json.dumps({**old, **record}, indent=1), "utf-8")
    return 0


def take(page, browser, srv, state: str, lang: str):
    """Put the page in a state to photograph (or open another page and return it, to photograph instead)."""
    def go(path: str = "", wait: str = ".slot"):
        """Open a page of Hoard's afresh (in the theme now set), and wait for it. (From a blank page first: going to
        an address that differs only after its # wouldn't load the page again, and it would keep its theme.)"""
        page.goto("about:blank")
        page.goto(srv.url + path)
        page.locator(wait).first.wait_for()
        page.wait_for_timeout(900)

    def menu(item: str, wait: str | None = None):
        """Choose something from the bar's Menu."""
        if not page.locator(item).is_visible():
            page.click("#menuBtn")
        page.click(item)
        if wait:
            page.locator(wait).first.wait_for()
        page.wait_for_timeout(600)

    def click(selector: str, wait: str | None = None, settle: int = 700):
        """Click something, and wait for what it opens."""
        page.locator(selector).first.click()
        if wait:
            page.locator(wait).first.wait_for()
        page.wait_for_timeout(settle)

    def store_note(store: str, note: str | None):
        """A note on a store's row (what the last refresh said), or none."""
        with srv.lib.lock:
            srv.lib.data["stores"][store]["error"] = note

    store_note("booth", None)
    store_note("payhip", None)
    srv.jobs.history = [h for h in srv.jobs.history if h["id"] != "jf"]
    if state == "library":
        go()
    elif state == "search":
        go()
        page.click("#q")
        page.locator("#qMenu:not([hidden])").wait_for()
        page.wait_for_timeout(500)
    elif state == "search-hoodie":
        go()
        page.fill("#q", "hoodie")
        page.wait_for_timeout(1200)   # (the search box's pause, then the results)
        page.evaluate("document.activeElement.blur()")
        page.wait_for_timeout(500)
    elif state == "details":
        go()
        click(".slot >> nth=3", "#detail")
    elif state == "stores":
        go()
        menu("#storesBtn", "#quickRefresh")
    elif state == "tasks":
        go()
        click("#tasksTab", "#tasksWin:not([hidden])")
    elif state == "downloads":
        go("downloads")
    elif state == "downloads-details":
        go("downloads")
        click(".slot:not(:has-text('My Texture Set')) >> nth=2", "#detail")
    elif state == "space":
        go("downloads")
        click('#views [data-view="space"]', settle=1500)
    elif state == "inside":
        go("downloads#store=Local")
        page.locator(".slot", has_text="My Texture Set").first.click()
        click('#detail [data-act="inside"]', "#insideWin:not([hidden])")
        for folder in ("Assets", "My Texture Set", "Fabric", "Metal"):
            page.locator("#insideWin summary", has_text=folder).last.click()
            page.wait_for_timeout(250)
    elif state in ("sets", "set", "wishlist", "mix"):
        go("#store=Sets", "[data-setopen]")
        if state == "set":
            page.evaluate("setExtraOpen = false")
            page.locator("[data-setopen]", has_text="Winter outfit").first.click()
            page.locator("[data-setx=back]").first.wait_for()
            page.wait_for_timeout(1000)
        elif state == "wishlist":
            page.locator("[data-setopen]", has_text="Booth").first.click()
            page.locator("[data-setx=back]").first.wait_for()
            page.wait_for_timeout(1000)
            # down to its products, with their prices (one cheaper than before)
            page.evaluate("() => { const p = document.querySelector('.ext-price'); if (p) p.scrollIntoView({ block: 'center' }); }")
            page.wait_for_timeout(600)
        elif state == "mix":
            page.evaluate("MIX.fit = false")
            click("[data-setx=mix]", "dialog.mixdlg", 900)
    elif state.startswith("project"):
        go()
        click("#projectsTab", ".pj-row")
        page.locator("#pjSplash").wait_for(state="hidden")
        page.wait_for_timeout(700)
        if state in ("project", "project-git"):   # (a project's details, beside the list, then Manage)
            page.locator(".pj-row", has_text="My Avatar").locator(".pj-open").first.click()
            click(".pj-detail [data-pj=manage]", "[data-pj=back]", 900)
            if state == "project-git":
                click(".pj-subs [data-sub=git]", ".pj-git", 1200)
        elif state == "project-new":
            click("[data-pj=new]", "[data-pj=back]", 900)
    elif state in ("settings-look", "settings-apprise"):
        go()
        menu("#settingsBtn", "#settingsPanel:not([hidden])")
        part = "#part-look" if state == "settings-look" else "#part-apprise"
        page.evaluate("p => document.querySelector(p).scrollIntoView({ block: 'start' })", part)
        page.wait_for_timeout(700)
    elif state == "hidden":
        go()
        click('[data-view="hidden"]', "#pinDialog[open]")
    elif state == "setup-notify":
        go()
        page.evaluate("openSetup().then(() => { SETUP.step = setupSteps().indexOf('notifications'); renderSetup(); })")
        page.locator("#setupNotifyService").wait_for()
        page.fill('#setupNotifyFields [data-apprise-field="hook"]', "https://discord.com/api/webhooks/…")
        page.wait_for_timeout(500)
    elif state == "booth-signed-out":
        store_note("booth", BOOTH_SIGNED_OUT)
        go()
        menu("#storesBtn", "#quickRefresh")
    elif state == "payhip-blocked":
        store_note("payhip", PAYHIP_BLOCKED)
        go()
        menu("#storesBtn", "#quickRefresh")
    elif state == "itch-key":
        go()
        menu("#storesBtn", "#quickRefresh")
        click('[data-login="itch"]', "#itchDialog[open]")
    elif state == "failed-task":
        now = srv.jobs.history[0]["ended"]
        srv.jobs.history = [*srv.jobs.history, {**FAILED_TASK, "started": now, "ended": now}]
        go()
        click("#tasksTab", "#tasksWin:not([hidden])")
    elif state == "no-key":   # a page opened without this run's key: an old bookmark, say
        other = browser.new_page(viewport=VIEW, device_scale_factor=SCALE)
        other.add_init_script(NO_VERSION)
        other.goto(srv.url)
        other.wait_for_timeout(1500)
        return other
    else:
        raise ValueError(f"no such state: {state}")
    return None


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        import shutil
        shutil.rmtree(shots.WORK, ignore_errors=True)
