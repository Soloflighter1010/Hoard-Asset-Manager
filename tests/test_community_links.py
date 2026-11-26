"""Issues #204 and #226: Hoard's Discord in every footer (both pages, the website and the wiki), and a Tip on Ko-fi
button in Settings. Each opens in your browser (Hoard's window sends a link that opens a new one there), and only
ever goes to Discord's or Ko-fi's own site."""
from __future__ import annotations

import re
import sys
import unittest
from tests.isolation import IsolatedTestCase
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import site_chrome  # noqa: E402

DISCORD = re.compile(r'<a href="https://discord\.gg/[A-Za-z0-9]+" target="_blank" rel="noopener noreferrer"[^>]*>Discord</a>')
KOFI = re.compile(r'<a class="ghost sm" id="tipKofi" href="https://ko-fi\.com/[A-Za-z0-9_]+" target="_blank" '
                  r'rel="noopener noreferrer">Tip on Ko-fi</a>')
PAGES = [REPO / "hoard" / "web" / n for n in ("library.html",)]
SETTINGS_PARTS = REPO / "ui" / "settings.js"   # (Settings' cards, issue #421)


class CommunityLinks(IsolatedTestCase):

    def test_discord_in_the_pages_bars(self):
        # (#270: Hoard's own links are in the bar, before Menu and Sync, and in the Menu when the bar has no room)
        for page in PAGES:
            text = page.read_text("utf-8")
            bar = text.split('<nav class="bar-links"', 1)[1].split("</nav>", 1)[0]
            menu = text.split('<div class="barmenu-links"', 1)[1].split("</div>", 1)[0]
            self.assertRegex(bar, DISCORD, page.name)
            self.assertRegex(menu, DISCORD, page.name)

    def test_discord_on_the_website_and_the_wiki(self):
        self.assertTrue(site_chrome.DISCORD.startswith("https://discord.gg/"))
        self.assertIn(site_chrome.DISCORD, site_chrome.footer())
        for page in sorted((REPO / "site").glob("*.html")):
            self.assertIn(f'href="{site_chrome.DISCORD}"', page.read_text("utf-8"), page.name)
        self.assertIn(f"[Discord]({site_chrome.DISCORD})", (REPO / "wiki" / "_Footer.md").read_text("utf-8"))

    def test_a_tip_on_ko_fi_in_settings(self):
        for page in PAGES:
            text = page.read_text("utf-8")
            self.assertRegex(text, KOFI, page.name)
            self.assertLess(text.index('id="part-tip"'), text.index('id="part-thanks"'))
        self.assertIn("'part-help', 'part-tip', 'part-thanks'", SETTINGS_PARTS.read_text("utf-8"), "in Settings' Help card")

    def test_every_setting_is_in_one_of_settings_cards(self):
        # (#421: Settings' parts are cards, ui/settings.js's PARTS, each setting a row in one by its heading's id. A
        # setting in none would be lost from the page)
        parts = SETTINGS_PARTS.read_text("utf-8").split("export const PARTS", 1)[1].split("];", 1)[0]
        rows = [r for line in re.findall(r"rows: \[([^\]]*)\]", parts) for r in re.findall(r"'([a-z-]+)'", line)]
        for page in PAGES:
            text = page.read_text("utf-8")
            body = text.split('<div class="set-body"', 1)[1].split('</section>', 1)[0]
            headings = re.findall(r'<h4 id="([a-z-]+)"', body)
            self.assertGreater(len(headings), 20, page.name)
            self.assertEqual(sorted(rows), sorted(headings), "each setting in one card, once")


if __name__ == "__main__":
    unittest.main()
