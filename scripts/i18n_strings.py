"""The English Hoard's pages show that a language's catalog doesn't translate yet: opens both pages in a browser with
a sample library (as tests/test_pages.py does), steps through their panels and views, and lists what the page's
own translator (web/shared.js, I18N.untranslated) found no translation for, in every state it reached.

    python scripts/i18n_strings.py ja            what's missing from hoard/web/i18n/ja.json, one per line
    python scripts/i18n_strings.py ja --json     the same as JSON, {English: ""}, to fill in

Messages a page only shows now and then (a failed download, a store's error) are added to the catalogs from the
code that makes them; tests/test_i18n.py checks the states this reaches stay translated. Needs Playwright.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-i18n-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import common, config, downloader, i18n, library, server  # noqa: E402

# what to do on each page, in turn: open a panel or a view, then read what it shows
STEPS = {
    "/": ["", "#settingsBtn", "#storesBtn", "#tagsBtn", "#tasksTab", "#projectsTab",
          # Projects: a project, its changes and backup asked about, one Hoard for Unity reported, a new project with
          # the packages and products to choose from, the repositories, and Unity and folders
          "[data-pj=manage] >> nth=0", "[data-pj=repair]", "dialog.pj-dlg button[value=no]", "[data-pj=backup]",
          "dialog.pj-dlg button[value=no]", "[data-pj=back]", "[data-pj=report] >> nth=0", "[data-pj=back]", "[data-pj=new]",
          "[data-pj=addpkg]", "dialog.pj-dlg button[value=no]", "[data-pj=addprod]", "dialog.pj-dlg .linkish >> nth=0",
          "dialog.pj-dlg button[value=no]", "[data-pj=back]", "[data-pj=repos]", ".pj-more summary", "[data-pj=back]",
          "[data-pj=settings]", "[data-pj=back]", "Escape", '#storeSeg [data-store="Sets"]',
          "[data-setopen] >> nth=0", ".setextra summary", '#storeSeg [data-store=""]', "#selectBtn", "#selectBtn",
          ".slot >> nth=0", "Escape", '[data-view="archive"]', '[data-view="hidden"]', '[data-view="library"]',
          # the setup assistant, each step up to the last (not Finish, which would start reading the stores)
          "#settingsBtn", "#setupAgain", *["#setupNext"] * 8, "Escape"],
    "/downloads": ["", ".slot >> nth=0", "Escape", '[data-view="updates"]', '[data-view="archive"]', '[data-view="removed"]',
                   '[data-view="space"]', '[data-view="downloads"]', "#selectBtn", "#selectBtn", "#tasksTab", "#projectsTab",
                   "Escape", '#stores [data-store="Sets"]', "[data-setopen] >> nth=0", '#stores [data-store=""]', "#settingsBtn"],
}


def sample_server(root: Path, lang: str) -> server.AppServer:
    """The sample library, served. It writes a set to Hoard's data folder (HOARD_DATA_DIR): give it one of its own."""
    srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True,
                                              "display": {"language": lang}}, lan=False)
    old = "2025-01-01T00:00:00+00:00"
    with srv.lib.lock:
        srv.lib.data["items"] = [
            library.item("booth", "1", name="Rusk", creator="Kitsu Studio", added=old),
            library.item("gumroad", "2", name="Mochi", creator="Mochi Works", added=common.now_iso()),
            library.item("jinxxy", "3", name="Anko", creator="Kitsu Studio", added=old),
            library.item("payhip", "citrus.store:4", name="Yuzu", creator="Citrus", added=old),   # (a shop not added)
            library.item("itch", "5", name="Kinako", creator="Soy", added=old)]
        for s in ("booth", "gumroad", "jinxxy"):
            srv.lib.data["stores"][s] = {"count": 1, "error": None, "source": "refresh", "first_read": old, "updated": common.now_iso()}
    folder = root / "Booth" / "Kitsu Studio" / "Rusk"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "rusk.unitypackage").write_bytes(b"pkg")
    man = downloader.Manifest(root / "Booth")
    rec = man.record("1", "Kitsu Studio", "Rusk")
    rec["files"]["f"] = {"path": "rusk.unitypackage", "size": 3}
    man.save()
    from hoard import sets   # a set: one product downloaded, one yours to download, one to buy (shared with you)
    sets.SetStore().change({"action": "import", "code": sets.share_code({
        "name": "Rusk, winter", "note": "Rusk(winter)", "photos": ["https://i.imgur.com/abc.png"],
        "items": ["booth:rusk", "gumroad:mochi", "jinxxy:yuzu"],
        "products": {"booth:rusk": {"store": "booth", "name": "Rusk", "creator": "Kitsu Studio"},
                     "gumroad:mochi": {"store": "gumroad", "name": "Mochi", "creator": "Mochi Works"},
                     "jinxxy:yuzu": {"store": "jinxxy", "name": "Yuzu", "creator": "Citrus", "url": "https://jinxxy.com/citrus/yuzu"}}})[0]})
    srv.jobs.history = [{"id": "j1", "task": "sync", "label": "Sync: Booth", "stores": ["booth"], "started": old, "ended": old,
                         "outcome": "failed", "message": "Stopped: Booth went away", "report": None, "log": ["Reading Booth"]}]
    return srv


def sample_projects(root: Path) -> dict:
    """Projects' sample: the Creator Companion's folder (HOARD_VCC_DIR) listing a project with VRChat's packages (one
    with an update, one not installed), and one whose folder has gone; VRChat's repository; and what Hoard for Unity
    reported about the first project and about one not on the list. Returns the environment to run with."""
    vcc, unity = root / "vcc", root / "Unity"
    avatar = unity / "Rusk Avatar"
    for sub in ("Assets", "ProjectSettings", "Packages/com.vrchat.base"):
        (avatar / sub).mkdir(parents=True, exist_ok=True)
    (avatar / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.22f1\n", "utf-8")
    (avatar / "Packages" / "manifest.json").write_text(json.dumps({"dependencies": {}}), "utf-8")
    (avatar / "Packages" / "vpm-manifest.json").write_text(json.dumps({
        "dependencies": {"com.vrchat.avatars": {"version": "3.7.0"}},
        "locked": {"com.vrchat.avatars": {"version": "3.7.0", "dependencies": {"com.vrchat.base": "3.7.0"}},
                   "com.vrchat.base": {"version": "3.7.0", "dependencies": {}}}}), "utf-8")
    (avatar / "Packages" / "com.vrchat.base" / "package.json").write_text(json.dumps(
        {"name": "com.vrchat.base", "version": "3.7.0", "displayName": "VRChat SDK - Base"}), "utf-8")
    packages = {}
    for name, label in (("com.vrchat.base", "VRChat SDK - Base"), ("com.vrchat.avatars", "VRChat SDK - Avatars")):
        packages[name] = {"versions": {v: {"name": name, "version": v, "displayName": label, "unity": "2022.3",
                                           "url": f"https://packages.vrchat.com/{name}-{v}.zip",
                                           "vpmDependencies": {"com.vrchat.base": v} if name != "com.vrchat.base" else {}}
                                       for v in ("3.7.0", "3.10.5")}}
    (vcc / "Repos").mkdir(parents=True, exist_ok=True)
    (vcc / "Repos" / "vrc-official.json").write_text(json.dumps({"repo": {
        "name": "Official", "id": "com.vrchat.repos.official", "url": "https://packages.vrchat.com/official?download",
        "packages": packages}}), "utf-8")
    (vcc / "settings.json").write_text(json.dumps({"userProjects": [str(avatar), str(unity / "Old World")]}), "utf-8")
    reports = Path(os.environ["HOARD_DATA_DIR"]) / "projects"
    reports.mkdir(parents=True, exist_ok=True)
    for pid, name, path in (("aaaaaaaaaaaaaaaa", "Rusk Avatar", avatar), ("bbbbbbbbbbbbbbbb", "Mochi World", unity / "Mochi World")):
        (reports / f"{pid}.json").write_text(json.dumps({
            "format": "hoard-project", "version": 1, "name": name, "path": str(path), "unity": "2022.3.22f1",
            "updated": "2025-01-01T00:00:00+00:00", "credits": {"style": "List"},
            "assets": [{"store": "Booth", "name": "Rusk", "creator": "Kitsu Studio", "folder": "Booth/Kitsu Studio/Rusk",
                        "status": "yes"}]}), "utf-8")
    return {"HOARD_VCC_DIR": str(vcc)}


def collect(lang: str) -> list[str]:
    from playwright.sync_api import sync_playwright
    found: dict[str, None] = {}
    from unittest import mock
    # the setup assistant saves settings on its way through: kept in memory, so the sample's never become yours; and
    # the sample's own files (its set) go in a data folder of its own
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server, "save_config"), \
            mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(tmp) / "data"), "HOARD_VCC_DIR": ""}):
        srv = sample_server(Path(tmp) / "library", lang)
        os.environ.update(sample_projects(Path(tmp)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                for path, steps in STEPS.items():
                    page = browser.new_page(viewport={"width": 1400, "height": 900})
                    page.goto(srv.entry_url().replace("/#", path + "#", 1) if path != "/" else srv.entry_url())
                    page.wait_for_timeout(1500)
                    for step in steps:
                        if step == "Escape":
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(300)
                        elif step:
                            try:
                                page.locator(step).first.click(timeout=2000)
                                page.wait_for_timeout(500)
                            except Exception:
                                continue
                        for key in page.evaluate("I18N.untranslated()"):
                            found.setdefault(key)
                    page.close()
                browser.close()
        finally:
            srv.shutdown()
            srv.server_close()
    return list(found)


def main(argv: list[str]) -> int:
    lang = argv[0] if argv else "ja"
    if lang not in i18n.LANGUAGES or lang == "en":
        print(f"Choose one of: {', '.join(k for k in i18n.LANGUAGES if k != 'en')}", file=sys.stderr)
        return 2
    keys = collect(lang)
    if "--json" in argv:
        print(json.dumps({k: "" for k in keys}, ensure_ascii=False, indent=1))
    else:
        print("\n".join(keys))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
