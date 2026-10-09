"""Hoard in Japanese and Korean: the catalogs (hoard/web/i18n), choosing the language, serving it with the page, and
both pages drawn in each language with nothing left in English but names. The browser part is skipped when
Playwright's Chromium isn't installed, as in test_pages.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from hoard import config, i18n, server  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _p.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

WEB = REPO / "hoard" / "web"
PLACES = re.compile(r"\{\d+\}")
TAGS = re.compile(r"</?\d+/?>")


def catalog(lang: str) -> dict:
    return json.loads((WEB / "i18n" / f"{lang}.json").read_text("utf-8"))


def script_keys() -> set[str]:
    """The words the pages' scripts pass to tr() and trHTML(): each string the first argument can be (either side of
    a ?:, and "a" + "b" joined), as tr() looks them up."""
    keys = set()
    for name in ("shared.js", "library.html", "downloads.html"):
        src = (WEB / name).read_text("utf-8")
        for m in re.finditer(r"(?<![\w.$])(?:tr|trHTML)\(", src):
            if "//" in src[src.rfind("\n", 0, m.start()):m.start()]:
                continue   # an example in a comment
            i, depth, parts, joined = m.end(), 0, [], False
            while i < len(src):
                c = src[i]
                if c in "\"'":
                    j = i + 1
                    while src[j] != c:
                        j += 2 if src[j] == "\\" else 1
                    text = json.loads('"' + src[i + 1:j].replace("\\'", "'").replace('"', '\\"') + '"') if c == "'" else json.loads(src[i:j + 1])
                    if joined and parts:
                        parts[-1] += text
                    else:
                        parts.append(text)
                    joined, i = False, j + 1
                    continue
                if c == "`":   # a template: only one without ${} is a key of its own
                    j = src.index("`", i + 1)
                    if "${" not in src[i:j]:
                        parts.append(src[i + 1:j])
                    i = j + 1
                    continue
                if c in "([{":
                    depth += 1
                elif c in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                elif c == "," and depth == 0:
                    break
                elif c == "+" and depth == 0:
                    joined = True
                elif not c.isspace():
                    joined = False
                i += 1
            keys.update(re.sub(r"\s+", " ", p).strip() for p in parts)
    keys.discard("")
    return keys


class Catalogs(unittest.TestCase):
    def test_every_language_has_every_key(self):
        ja, ko = catalog("ja"), catalog("ko")
        self.assertEqual(set(ja), set(ko))
        self.assertGreater(len(ja), 1000)

    def test_translations_keep_the_placeholders_and_elements(self):
        for lang in ("ja", "ko"):
            for en, text in catalog(lang).items():
                with self.subTest(lang=lang, en=en):
                    self.assertIsInstance(text, str)
                    self.assertTrue(text.strip())
                    self.assertEqual(sorted(PLACES.findall(en)), sorted(PLACES.findall(text)))
                    self.assertEqual(sorted(TAGS.findall(en)), sorted(TAGS.findall(text)))

    def test_keys_are_written_as_the_page_reads_them(self):
        # one space between words, none at either end, as shared.js's norm() makes what it reads
        for en in catalog("ja"):
            self.assertEqual(en, re.sub(r"\s+", " ", en).strip(), en)

    def test_what_the_scripts_ask_for_is_translated(self):
        keys = script_keys()
        self.assertGreater(len(keys), 150)
        for lang in ("ja", "ko"):
            missing = sorted(k for k in keys if k not in catalog(lang))
            self.assertEqual(missing, [], f"{lang}: tr() words with no translation")


class ChoosingTheLanguage(unittest.TestCase):
    def test_from_the_browser(self):
        self.assertEqual(i18n.from_header("ja-JP,ja;q=0.9,en;q=0.8"), "ja")
        self.assertEqual(i18n.from_header("ko-KR,ko;q=0.9"), "ko")
        self.assertEqual(i18n.from_header("en-US,en;q=0.9,ja;q=0.5"), "en")
        self.assertEqual(i18n.from_header("fr-FR,ko;q=0.4"), "ko")
        self.assertEqual(i18n.from_header("de-DE"), "en")
        self.assertEqual(i18n.from_header(None), "en")
        self.assertEqual(i18n.from_header("ja;q=0"), "en")

    def test_setting_wins_over_the_browser(self):
        for chosen in ("en", "ja", "ko"):
            self.assertEqual(i18n.language({"display": {"language": chosen}}, "ko-KR" if chosen != "ko" else "ja"), chosen)
        self.assertEqual(i18n.language({"display": {"language": "system"}}, "ko-KR"), "ko")
        self.assertEqual(i18n.language({"display": {"language": "xx"}}, "ja"), "ja")   # not one of the choices
        self.assertEqual(i18n.language({}, None), "en")

    def test_only_hoards_own_catalogs_are_read(self):
        # what a window asks for picks a catalog, never names a file
        for asked in ("../config", "ja/../../x", "ja.json", "JA", "", "en", "fr"):
            self.assertEqual(i18n.catalog(asked), {}, asked)
        self.assertEqual(set(i18n.CATALOG_FILES), {"ja", "ko"})
        self.assertEqual(i18n.from_header("JA-jp"), "ja")

    def test_the_setting_is_checked(self):
        self.assertEqual(config.DEFAULT_CONFIG["display"]["language"], "system")
        self.assertEqual(set(i18n.SETTINGS), {"system", "en", "ja", "ko"})


class Served(unittest.TestCase):
    def test_page_carries_its_language(self):
        for lang in ("ja", "ko"):
            html = server.page_source("library.html", {"display": {"language": lang}}).decode("utf-8")
            self.assertIn(f'<html lang="{lang}" data-i18n>', html)
            data = re.search(r'<script type="application/json" id="i18n">(.*?)</script>', html, re.S)
            self.assertIsNotNone(data)
            self.assertNotIn("<", data.group(1))   # nothing in it can end the script early
            self.assertEqual(json.loads(data.group(1)), i18n.catalog(lang))
            self.assertLess(html.index('id="i18n"'), html.index("\n<script>\n"))   # read before the page's script runs

    def test_english_is_the_page_as_written(self):
        html = server.page_source("downloads.html", {"display": {"language": "en"}}).decode("utf-8")
        self.assertIn('<html lang="en">', html)
        self.assertNotIn('id="i18n"', html)
        self.assertEqual(server.page_source("downloads.html", {"display": {"language": "system"}}, "de-DE").decode("utf-8"), html)


@unittest.skipUnless(BROWSER, "Playwright's Chromium isn't installed")
class Drawn(unittest.TestCase):
    """Both pages, stepped through their panels and views (scripts/i18n_strings.py): what's left untranslated is only
    the sample's names, stores, paths and file names, and Hoard's own name."""
    NAMES = {"Booth", "Gumroad", "Jinxxy", "Payhip", "itch.io", "Hoard", "GitHub", "Microsoft Edge", "Google Chrome",
             "PIN", "OK", ".unitypackage", "rusk.unitypackage", "D:\\Packages\\My Textures"}
    SAMPLE = re.compile(r"^(Rusk|Mochi|Anko|Yuzu|Kinako)\(|^/|^[A-Z]:\\")

    def test_nothing_left_in_english(self):
        import i18n_strings
        for lang in ("ja", "ko"):
            with self.subTest(lang=lang):
                left = [k for k in i18n_strings.collect(lang) if k not in self.NAMES and not self.SAMPLE.search(k)]
                self.assertEqual(left, [])


@unittest.skipUnless(BROWSER, "Playwright's Chromium isn't installed")
class SetupAsks(unittest.TestCase):
    def test_the_first_step_is_the_language(self):
        """Someone new, whose computer is in Korean: the assistant opens on the language, in Korean and written in
        all three; choosing Japanese saves it and brings the assistant back in Japanese, one step on."""
        import threading
        from unittest import mock
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": tmp.name, "setup_done": False,
                                                  "display": {"language": "system"}}, lan=False)
        with srv.lib.lock:
            srv.lib.data["items"], srv.lib.data["stores"] = [], {}
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with sync_playwright() as p, mock.patch.object(server, "save_config"):
            browser = p.chromium.launch()
            page = browser.new_context(locale="ko-KR").new_page()
            page.goto(srv.entry_url())
            page.locator("#setup:not([hidden])").wait_for()
            self.assertEqual(page.evaluate("document.documentElement.lang"), "ko")
            self.assertEqual(page.locator("#setupTitle").inner_text(), "언어를 선택하세요")
            self.assertIn("言語を選んでください", page.locator("#setupBody").inner_text())
            self.assertTrue(page.locator('#setupBody input[value="system"]').is_checked())
            page.check('#setupBody input[value="ja"]')
            page.click("#setupNext")
            page.wait_for_function("() => document.documentElement.lang === 'ja'")
            page.locator("#setup:not([hidden])").wait_for()
            self.assertEqual(page.locator("#setupTitle").inner_text(), "Hoardへようこそ")
            self.assertEqual(srv.cfg["display"]["language"], "ja")
            page.click("#setupBack")
            self.assertTrue(page.locator('#setupBody input[value="ja"]').is_checked())
            browser.close()


if __name__ == "__main__":
    unittest.main()
