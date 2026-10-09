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
    "/": ["", "#settingsBtn", "#storesBtn", "#tagsBtn", "#tasksTab", "#projectsTab", "Escape", "#selectBtn", "#selectBtn",
          ".slot >> nth=0", "Escape", '[data-view="archive"]', '[data-view="hidden"]', '[data-view="library"]'],
    "/downloads": ["", ".slot >> nth=0", "Escape", '[data-view="updates"]', '[data-view="archive"]', '[data-view="removed"]',
                   '[data-view="space"]', '[data-view="downloads"]', "#selectBtn", "#selectBtn", "#tasksTab", "#projectsTab",
                   "Escape", "#settingsBtn"],
}


def sample_server(root: Path, lang: str) -> server.AppServer:
    srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True,
                                              "display": {"language": lang}}, lan=False)
    old = "2025-01-01T00:00:00+00:00"
    with srv.lib.lock:
        srv.lib.data["items"] = [
            library.item("booth", "1", name="Rusk", creator="Kitsu Studio", added=old),
            library.item("gumroad", "2", name="Mochi", creator="Mochi Works", added=common.now_iso()),
            library.item("jinxxy", "3", name="Anko", creator="Kitsu Studio", added=old),
            library.item("payhip", "4", name="Yuzu", creator="Citrus", added=old),
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
    srv.jobs.history = [{"id": "j1", "task": "sync", "label": "Sync: Booth", "stores": ["booth"], "started": old, "ended": old,
                         "outcome": "failed", "message": "Stopped: Booth went away", "report": None, "log": ["Reading Booth"]}]
    return srv


def collect(lang: str) -> list[str]:
    from playwright.sync_api import sync_playwright
    found: dict[str, None] = {}
    with tempfile.TemporaryDirectory() as tmp:
        srv = sample_server(Path(tmp), lang)
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
