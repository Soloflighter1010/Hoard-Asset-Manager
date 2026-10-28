"""Styles (Settings, Appearance; issue #159): Standard, Treasure and Workbench. The setting is checked, kept in
config.json through a restart and an update (and in a backup), and served with the page so it shows from the first
moment; Settings and the setup assistant change it at once."""
import json
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import backup, config, server, themes  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


class Setting(unittest.TestCase):
    def test_checked(self):
        self.assertEqual(themes.STYLES, ("standard", "treasure", "workbench"))
        self.assertEqual(server.display_settings({})["style"], "standard", "Hoard as it has always looked")
        for odd in ("<b>", 3, None, "Workbench", "../looks"):
            self.assertEqual(server.display_settings({"display": {"style": odd}})["style"], "standard")
        cfg = {**config.load_config()}
        for style in themes.STYLES:
            change = server.apply_settings(cfg, {"display": {"style": style}})
            self.assertEqual(change["display"], {"style": style})
            self.assertEqual(server.display_settings(change)["style"], style)
        for odd in ("gallery", "", 1, None):
            with self.assertRaises(ValueError):
                server.apply_settings(cfg, {"display": {"style": odd}})

    def test_kept_through_a_restart_and_an_update(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        cfg = config.load_config(path)
        config.deep_merge(cfg, server.apply_settings(cfg, {"display": {"style": "workbench"}}))
        config.deep_merge(cfg, server.apply_settings(cfg, {"display": {"theme": "geode"}}))   # another setting after it
        config.save_config(cfg, path)
        again = config.load_config(path)   # Hoard started again, or a newer Hoard reading the same file
        self.assertEqual(server.display_settings(again)["style"], "workbench")
        self.assertEqual(server.display_settings(again)["theme"], "geode")
        # a config.json from before styles: Standard; one a later Hoard wrote with a style this one hasn't: Standard
        path.write_text(json.dumps({"display": {"theme": "geode"}}), "utf-8")
        self.assertEqual(server.display_settings(config.load_config(path))["style"], "standard")
        path.write_text(json.dumps({"display": {"style": "gallery"}}), "utf-8")
        self.assertEqual(server.display_settings(config.load_config(path))["style"], "standard")

    def test_in_a_backup(self):
        self.assertIn("display", backup.SETTINGS)
        shown = server.public_settings({**config.load_config(), "display": {"style": "treasure"}})["display"]
        cfg = {**config.load_config(), "display": {}}
        config.deep_merge(cfg, server.apply_settings(cfg, {"display": shown}))   # as a restore puts it back
        self.assertEqual(cfg["display"]["style"], "treasure")


class Served(unittest.TestCase):
    def test_marked_from_the_first_moment(self):
        for page in server.PAGES.values():
            plain = server.page_source(page, {"display": {"language": "en"}}).decode("utf-8")
            self.assertIn('<html lang="en">', plain, "Standard: the page as written")
            looks = re.search(r'<style id="looks">(.*?)</style>', plain, re.S)
            self.assertIsNotNone(looks, page)
            self.assertIn('[data-style="workbench"]', looks.group(1))
            self.assertLess(plain.index('<style id="looks">'), plain.index('<style id="theme">'))
            self.assertGreater(plain.index('<style id="looks">'), plain.index("--cave: #211C18"), "after the page's own")
            for style in ("treasure", "workbench"):
                html = server.page_source(page, {"display": {"language": "en", "style": style}}).decode("utf-8")
                self.assertIn(f'<html lang="en" data-style="{style}">', html)
        ja = server.page_source("library.html", {"display": {"language": "ja", "font": "dyslexic", "style": "treasure"}}).decode()
        self.assertIn('<html lang="ja" data-font="dyslexic" data-style="treasure" data-i18n>', ja)
        odd = server.page_source("library.html", {"display": {"language": "en", "style": '"><script>'}}).decode()
        self.assertIn('<html lang="en">', odd)


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Chosen(unittest.TestCase):
    def serve(self, cfg_more, items=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(Path(tmp.name) / "dl"), **cfg_more},
                               lan=False)
        with srv.lib.lock:   # (in memory only)
            srv.lib.data["items"] = [] if not items else [{"store": "booth", "id": "1", "name": "Fox Hoodie", "creator": "Kitsu", "url": "https://booth.pm/en/items/1",
                                      "download_url": "https://accounts.booth.pm/library", "thumbnail": None, "files": [],
                                      "added": "2026-10-12T10:00:00+00:00"}]
            srv.lib.data["stores"]["booth"] = {"count": 1, "error": None}
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return srv

    def test_in_settings(self):
        from playwright.sync_api import expect, sync_playwright
        srv = self.serve({"setup_done": True, "display": {}, "ui": {"toured": True}})
        mark = "() => document.documentElement.dataset.style || ''"
        with sync_playwright() as p, mock.patch.object(server, "save_config"):
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.entry_url())
            page.locator("#grid .slot").first.wait_for()
            self.assertEqual(page.evaluate(mark), "")
            self.assertFalse(page.locator("#grid .row-meta").first.is_visible(), "Standard: tiles")
            page.click("#settingsBtn")
            expect(page.locator('input[name="setStyle"][value="standard"]')).to_be_checked()
            self.assertEqual(page.locator('input[name="setStyle"]').count(), 3)
            page.check('input[name="setStyle"][value="workbench"]')
            page.wait_for_function(f"() => ({mark})() === 'workbench'")
            self.assertEqual(srv.cfg["display"]["style"], "workbench", "saved")
            page.keyboard.press("Escape")
            expect(page.locator("#grid .row-meta").first).to_be_visible()   # a list: the store, where it is, when
            expect(page.locator("#grid .row-meta .rm-store").first).to_have_text("Booth")
            page.close()
            page = browser.new_page()   # opened again: in it from the first moment, on both pages
            page.goto(srv.entry_url().replace("/#", "/downloads#", 1))
            self.assertEqual(page.evaluate(mark), "workbench")
            page.click("#settingsBtn")
            expect(page.locator('input[name="setStyle"][value="workbench"]')).to_be_checked()
            page.check('input[name="setStyle"][value="treasure"]')
            page.wait_for_function(f"() => ({mark})() === 'treasure'")
            page.check('input[name="setStyle"][value="standard"]')
            page.wait_for_function(f"() => ({mark})() === ''")
            self.assertEqual(srv.cfg["display"]["style"], "standard")
            self.assertEqual(errors, [])
            browser.close()

    def test_in_setup(self):
        from playwright.sync_api import expect, sync_playwright
        srv = self.serve({"setup_done": False, "display": {}}, items=False)   # someone new: setup opens
        with sync_playwright() as p, mock.patch.object(server, "save_config"):
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.entry_url())
            page.locator("#setupTitle", has_text="Choose your language").wait_for()
            page.click("#setupNext")
            page.locator("#setupTitle", has_text="Make Hoard easier to use").wait_for()
            page.click("#setupNext")
            page.locator("#setupTitle", has_text="Choose a style").wait_for()   # right after, before the stores
            expect(page.locator('#setupBody input[name="setupStyle"][value="standard"]')).to_be_checked()
            page.locator('#setupBody .style-choice', has_text="Treasure").click()
            page.wait_for_function("() => document.documentElement.dataset.style === 'treasure'")
            self.assertEqual(srv.cfg["display"]["style"], "treasure")
            page.click("#setupNext")
            page.locator("#setupTitle", has_text="Welcome to Hoard").wait_for()
            page.click("#setupBack")
            expect(page.locator('#setupBody input[name="setupStyle"][value="treasure"]')).to_be_checked()
            self.assertEqual(errors, [])
            browser.close()


if __name__ == "__main__":
    unittest.main()


class CardOutlines(unittest.TestCase):
    """Issue #222 (Settings, Accessibility): each product's card can have an outline and a faint background of its own,
    so it stands apart from the page, everywhere cards show, in every style and theme. Kept as display.card_outlines,
    served with the page from its first moment, and changed at once in Settings and the setup assistant."""

    def test_checked_kept_and_served(self):
        self.assertIs(config.DEFAULT_CONFIG["display"]["card_outlines"], False)
        self.assertIs(server.display_settings({})["card_outlines"], False)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        cfg = config.load_config(path)
        config.deep_merge(cfg, server.apply_settings(cfg, {"display": {"card_outlines": 1}}))
        config.save_config(cfg, path)
        self.assertIs(server.display_settings(config.load_config(path))["card_outlines"], True, "kept through a restart")
        shown = server.public_settings(config.load_config(path))["display"]
        again = {**config.load_config(), "display": {}}
        config.deep_merge(again, server.apply_settings(again, {"display": shown}))   # as a restore puts it back
        self.assertIs(again["display"]["card_outlines"], True)
        for page in server.PAGES.values():
            on = server.page_source(page, {"display": {"language": "en", "card_outlines": True}}).decode("utf-8")
            self.assertIn('<html lang="en" data-cards="outlined">', on)
            self.assertIn('id="setCardOutlines"', on)
            self.assertIn('<html lang="en">', server.page_source(page, {"display": {"language": "en"}}).decode("utf-8"))
        self.assertIn('data-cards="outlined"', server.guide_source({"cards": ["outlined"]}).decode())
        self.assertIn('name="cards" value="outlined" checked', server.guide_source({"cards": ["outlined"]}).decode())

    def test_the_outline_is_clear_in_every_theme(self):
        """The outline (--dust) stands out at least 3:1 (WCAG's for a control's edge) from the card (--stone) and the
        page (--cave), and the card is a step lighter or darker than the page, in every theme, Light and Dark."""
        def lum(hex_):
            c = [int(hex_.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
            return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

        def ratio(a, b):
            hi, lo = sorted((lum(a), lum(b)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)
        looks = (server.WEB / "looks.css").read_text("utf-8")
        self.assertRegex(looks, r'\[data-cards="outlined"\] \.slot \{[^}]*background: var\(--stone\);[^}]*border: 1px solid var\(--dust\)')
        for name, theme in themes.THEMES.items():
            for mode, c in theme.items():
                if isinstance(c, dict) and "dust" in c:
                    with self.subTest(theme=name, mode=mode):
                        self.assertGreaterEqual(min(ratio(c["dust"], c["stone"]), ratio(c["dust"], c["cave"])), 3)
                        self.assertGreater(ratio(c["stone"], c["cave"]), 1.05)

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_in_settings_and_setup(self):
        from playwright.sync_api import expect, sync_playwright
        srv = Chosen.serve(self, {"setup_done": True, "display": {}, "ui": {"toured": True}})
        mark = "() => document.documentElement.dataset.cards || ''"
        card = "() => { const c = getComputedStyle(document.querySelector('#grid .slot')); return [c.borderTopWidth, c.paddingTop]; }"
        with sync_playwright() as p, mock.patch.object(server, "save_config"):
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.entry_url())
            page.locator("#grid .slot").first.wait_for()
            self.assertEqual((page.evaluate(mark), page.evaluate(card)), ("", ["0px", "0px"]), "as it's always looked")
            page.click("#settingsBtn")
            page.check("#setCardOutlines")
            page.wait_for_function(f"() => ({mark})() === 'outlined'")
            self.assertIs(srv.cfg["display"]["card_outlines"], True, "saved")
            self.assertEqual(page.evaluate(card), ["1px", "8px"], "an outline, with room inside it")
            for style in ("treasure", "workbench"):   # (in every style: looks.css's last word)
                page.evaluate(f"() => document.documentElement.dataset.style = '{style}'")
                self.assertEqual(page.evaluate(card)[0], "1px", style)
            page.close()
            page = browser.new_page()   # opened again: outlined from the first moment, on both pages
            page.goto(srv.entry_url().replace("/#", "/downloads#", 1))
            self.assertEqual(page.evaluate(mark), "outlined")
            page.click("#settingsBtn")
            expect(page.locator("#setCardOutlines")).to_be_checked()
            page.uncheck("#setCardOutlines")
            page.wait_for_function(f"() => ({mark})() === ''")
            self.assertIs(srv.cfg["display"]["card_outlines"], False)
            page.close()
            srv = Chosen.serve(self, {"setup_done": False, "display": {}}, items=False)   # someone new: setup offers it too
            page = browser.new_page()
            page.goto(srv.entry_url())
            page.locator("#setupTitle", has_text="Choose your language").wait_for()
            page.click("#setupNext")
            page.locator("#setupTitle", has_text="Make Hoard easier to use").wait_for()
            page.check("#setupCardOutlines")
            page.wait_for_function(f"() => ({mark})() === 'outlined'")
            self.assertIs(srv.cfg["display"]["card_outlines"], True)
            self.assertEqual(errors, [])
            browser.close()


class Guide(unittest.TestCase):
    """The style guide (/styleguide): every part of the pages, drawn with a page's own stylesheet, the styles and a
    theme as chosen in its address, so it keeps up with the pages; nothing of yours is in it."""

    def test_served_as_chosen(self):
        page = server.guide_source({"page": ["downloads"], "style": ["workbench"], "theme": ["geode"], "mode": ["light"],
                                    "font": ["dyslexic"], "size": ["130"], "colours": ["colourblind"], "spacing": ["wide"]}).decode()
        self.assertIn('<html lang="en" data-page="downloads" data-style="workbench" data-font="dyslexic" data-spacing="wide" '
                      'data-colours="colourblind" style="zoom: 1.3; --zoom: 1.3">', page)
        own = re.search(r"<style[^>]*>(.*?)</style>", (server.WEB / "downloads.html").read_text("utf-8"), re.S).group(1)
        self.assertIn(own, page, "the Downloads page's own stylesheet, as it is")
        self.assertIn((server.WEB / "looks.css").read_text("utf-8"), page)
        self.assertIn(themes.css("geode", "light"), page)
        self.assertIn('<option value="geode" selected>', page)
        self.assertNotIn("<!--@", page, "every part filled in")
        plain = server.guide_source({}).decode()
        self.assertIn('<html lang="en" data-page="library">', plain, "the Library, Standard, as served by default")
        for odd in ({"page": ["../config"]}, {"style": ["<b>"]}, {"size": ["999"]}, {"theme": ['"><script>']}):
            self.assertEqual(server.guide_source(odd), server.guide_source({}), f"{odd}: as if not chosen")

    def test_every_class_it_uses_is_the_pages(self):
        """An example's classes all come from the pages' stylesheets (or the guide's own sg-): a part renamed in the
        pages without the guide following would show here unstyled."""
        guide = (server.WEB / server.GUIDE).read_text("utf-8")
        css = "".join(re.search(r"<style[^>]*>(.*?)</style>", (server.WEB / f).read_text("utf-8"), re.S).group(1)
                      for f in server.GUIDE_PAGES.values()) + (server.WEB / "looks.css").read_text("utf-8")
        hooks = {"open", "show", "upd", "ok", "new", "sm", "add", "dup", "old", "gone", "run", "done-ok", "on-ledge",
                 "booth", "gumroad", "jinxxy", "payhip", "itch", "local", "sets", "settile", "wanted", "count"}
        body = guide[guide.index("<body>"):]
        used = {c for m in re.finditer(r'class="([^"]+)"', body) for c in m.group(1).split()}
        missing = sorted(c for c in used - hooks if not (c == "sg" or c.startswith("sg-"))
                         and not re.search(r"\." + re.escape(c) + r"(?![\w-])", css))
        self.assertEqual(missing, [])

    @unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
    def test_drawn_in_every_style(self):
        from playwright.sync_api import sync_playwright
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "setup_done": True}, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = srv.entry_url().split("/#")[0].rstrip("/")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1100, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            for style in themes.STYLES:
                page.goto(f"{base}/styleguide?style={style}&page=library")
                self.assertEqual(page.evaluate("document.documentElement.dataset.style || 'standard'"), style)
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - innerWidth"), 0, f"{style}: nothing past the window's side")
                self.assertGreater(page.locator(".sg-code").count(), 20, "each example's markup, to copy")
                self.assertEqual(page.locator("[data-token=gold]").inner_text().lower(), themes.THEMES["hoard"]["dark" if page.evaluate(
                    "matchMedia('(prefers-color-scheme: dark)').matches") else "light"]["gold"].lower())
            for font in ("standard", "dyslexic"):   # Workbench's list: each column's words whole, in either font,
                page.goto(f"{base}/styleguide?style=workbench&font={font}")
                for width in range(1300, 480, -20):   # and the name keeps its room as the list narrows
                    page.set_viewport_size({"width": width, "height": 800})
                    page.wait_for_timeout(30)
                    cut = page.evaluate("() => [...document.querySelectorAll('#tiles ~ .sg-item .row-meta > span')]"
                                        ".filter(s => s.offsetParent && s.scrollWidth > s.clientWidth + 1).map(s => s.textContent)")
                    self.assertEqual(cut, [], f"{font}, {width} wide")
                    squeezed = page.evaluate("() => [...document.querySelectorAll('#tiles ~ .sg-item .grid .slot')].filter(r => r.offsetParent)"
                                             ".filter(r => r.querySelector('.nm-t').clientWidth < r.clientWidth * 0.3).map(r => r.querySelector('.nm-t').textContent)")
                    self.assertEqual(squeezed, [], f"{font}, {width} wide: the names have room")
            page.select_option("select[name=style]", "treasure")   # the bar: chosen in the address
            page.wait_for_url("**style=treasure**")
            self.assertEqual(errors, [])
            browser.close()
