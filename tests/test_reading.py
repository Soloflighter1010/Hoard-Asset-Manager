"""Easier reading: OpenDyslexic and more spacing (Settings, Accessibility), checked and served with the page so it
never shows in the other font first; and the setup assistant's step for them, right after the language."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import config, server  # noqa: E402

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


class Setting(unittest.TestCase):
    def test_checked(self):
        self.assertEqual(server.display_settings({})["font"], "standard")
        self.assertFalse(server.display_settings({})["spacing"])
        self.assertEqual(server.display_settings({"display": {"font": "comic-sans"}})["font"], "standard")
        cfg = {**config.load_config()}
        change = server.apply_settings(cfg, {"display": {"font": "dyslexic", "spacing": True}})
        self.assertEqual(change["display"], {"font": "dyslexic", "spacing": True})
        self.assertEqual(server.display_settings(change)["font"], "dyslexic")
        self.assertTrue(server.display_settings(change)["spacing"])
        with self.assertRaises(ValueError):
            server.apply_settings(cfg, {"display": {"font": "../fonts"}})

    def test_served_with_the_page(self):
        plain = server.page_source("library.html", {"display": {"language": "en"}}).decode()
        self.assertIn('<html lang="en">', plain)
        both = server.page_source("downloads.html", {"display": {"language": "en", "font": "dyslexic", "spacing": True}}).decode()
        self.assertIn('<html lang="en" data-font="dyslexic" data-spacing="wide">', both)
        ja = server.page_source("library.html", {"display": {"language": "ja", "font": "dyslexic"}}).decode()
        self.assertIn('<html lang="ja" data-font="dyslexic" data-i18n>', ja, "with your language too")

    def test_the_font_is_bundled(self):
        for name in ("OpenDyslexic-Regular.woff2", "OpenDyslexic-Bold.woff2"):
            path = server.font_path(name)
            self.assertIsNotNone(path, name)
            self.assertEqual(path.read_bytes()[:4], b"wOF2")
        self.assertTrue((server.WEB / "fonts" / "OpenDyslexic-OFL.txt").is_file(), "its license beside it")


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class InSetup(unittest.TestCase):
    def test_chosen_in_setup_and_shown_at_once(self):
        from playwright.sync_api import sync_playwright
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(Path(tmp.name) / "dl"),
                                                  "setup_done": False, "display": {}}, lan=False)
        with srv.lib.lock:   # someone new: nothing in the library yet (in memory only)
            srv.lib.data["items"] = []
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with sync_playwright() as p, mock.patch.object(server, "save_config"):
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.entry_url())
            page.locator("#setupTitle", has_text="Choose your language").wait_for()   # someone new: setup opens
            page.click("#setupNext")
            page.locator("#setupTitle", has_text="Make Hoard easier to use").wait_for()
            font = "() => getComputedStyle(document.body).fontFamily"
            self.assertNotIn("OpenDyslexic", page.evaluate(font).split(",")[0])
            page.select_option("#setupFont", "dyslexic")
            page.wait_for_function(f"() => ({font})().startsWith('\"OpenDyslexic\"') || ({font})().startsWith('OpenDyslexic')")
            page.check("#setupSpacing")
            page.select_option("#setupTextSize", "130")
            page.wait_for_function("() => document.documentElement.style.zoom === '1.3'")
            page.wait_for_function("() => document.documentElement.dataset.spacing === 'wide'")
            self.assertEqual({k: srv.cfg["display"][k] for k in ("font", "spacing", "text_size")},
                             {"font": "dyslexic", "spacing": True, "text_size": 130}, "saved as chosen")
            page.wait_for_function("() => document.fonts.check('16px OpenDyslexic')")   # the bundled file loaded
            page.click("#setupNext")
            page.locator("#setupTitle", has_text="Choose a style").wait_for()   # (tests/test_styles.py)
            page.click("#setupBack")
            self.assertTrue(page.locator("#setupSpacing").is_checked(), "as chosen, coming back")
            page.goto(srv.entry_url().replace("/#", "/downloads#", 1))
            page.wait_for_function("() => document.documentElement.dataset.font === 'dyslexic'")
            page.click("#settingsBtn")
            page.wait_for_function("() => document.querySelector('#setFont').value === 'dyslexic'", timeout=5000)   # and in Settings
            page.select_option("#setFont", "standard")
            page.wait_for_function("() => !document.documentElement.dataset.font")
            self.assertEqual(errors, [])
            browser.close()


if __name__ == "__main__":
    unittest.main()
