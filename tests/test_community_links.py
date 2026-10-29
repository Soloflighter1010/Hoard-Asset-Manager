"""Issues #204 and #226: Hoard's Discord in every footer (both pages, the website and the wiki), and a Tip on Ko-fi
button in Settings. Each opens in your browser (Hoard's window sends a link that opens a new one there), and only
ever goes to Discord's or Ko-fi's own site."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import site_chrome  # noqa: E402

DISCORD = re.compile(r'<a href="https://discord\.gg/[A-Za-z0-9]+" target="_blank" rel="noopener noreferrer"[^>]*>Discord</a>')
KOFI = re.compile(r'<a class="ghost sm" id="tipKofi" href="https://ko-fi\.com/[A-Za-z0-9_]+" target="_blank" '
                  r'rel="noopener noreferrer">Tip on Ko-fi</a>')
PAGES = [REPO / "hoard" / "web" / n for n in ("library.html", "downloads.html")]


class CommunityLinks(unittest.TestCase):

    def test_discord_in_the_pages_footers(self):
        for page in PAGES:
            footer = page.read_text("utf-8").split('<footer class="foot">', 1)[1].split("</footer>", 1)[0]
            self.assertRegex(footer, DISCORD, page.name)

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
            self.assertIn('<button data-jump="part-tip">Support Hoard</button>', text, "listed down Settings' side")
            self.assertLess(text.index('id="part-tip"'), text.index('id="part-thanks"'))

    def test_every_part_of_settings_is_listed_down_its_side(self):
        for page in PAGES:
            text = page.read_text("utf-8")
            parts = re.findall(r'<h3 id="(part-[a-z]+)"', text)
            listed = re.findall(r'data-jump="(part-[a-z]+)"', text)
            self.assertEqual(listed, parts, page.name)


if __name__ == "__main__":
    unittest.main()
