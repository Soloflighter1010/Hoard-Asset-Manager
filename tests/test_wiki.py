"""The wiki: the pages in wiki/, which .github/workflows/wiki.yml publishes to the repository's GitHub wiki, and their
Japanese and Korean translations in wiki/ja/ and wiki/ko/. Every link leads somewhere, every page can be reached,
every translation says what its English page says now, and what the pages say about commands and settings matches
the code, so the wiki can't quietly drift from the app.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import wiki_translations  # noqa: E402
from hoard import config  # noqa: E402

WIKI = REPO / "wiki"
BLOB = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/"
LINK = re.compile(r"\]\(([^)\s]+)\)")


def pages() -> dict[str, str]:
    """Every page, by the name its address uses."""
    return {p.stem: p.read_text("utf-8") for p in sorted(WIKI.glob("*.md"))}


def translated(lang: str) -> dict[str, str]:
    """A translation's pages, by the name each one's address uses."""
    return {p.stem: p.read_text("utf-8") for p in sorted((WIKI / lang).glob("*.md"))}


def every_page() -> dict[str, str]:
    """The English pages and every translation's, by where each is (Settings, ja/設定)."""
    out = dict(pages())
    for lang in wiki_translations.LANGS:
        out.update({f"{lang}/{name}": text for name, text in translated(lang).items()})
    return out


def slug(heading: str) -> str:
    """The anchor GitHub gives a heading: lower case, punctuation dropped, each space a hyphen."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(text: str) -> set:
    return {slug(h) for h in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, re.M)}


def cli_commands() -> set:
    return set(re.findall(r'add_parser\("([a-z-]+)"', (REPO / "hoard" / "cli.py").read_text("utf-8")))


class Wiki(unittest.TestCase):

    def test_links_between_pages(self):
        """Every link to another page, and to a heading on one, leads somewhere. A translation links to its own
        language's pages, or to an English page it has no translation of."""
        english = pages()
        for lang in ("", *wiki_translations.LANGS):
            own = translated(lang) if lang else english
            for name, text in own.items():
                for target in LINK.findall(text):
                    if re.match(r"[a-z]+:", target):   # an address elsewhere
                        continue
                    page, _, anchor = target.partition("#")
                    page = page or name
                    there = own if page in own else english
                    self.assertIn(page, there, f"{lang}/{name}: a link to {target}")
                    if anchor:
                        self.assertIn(anchor, anchors(there[page]), f"{lang}/{name}: a link to {target}")

    def test_links_into_the_repository(self):
        for name, text in every_page().items():
            for target in LINK.findall(text):
                if target.startswith(BLOB):
                    path = target[len(BLOB):].partition("#")[0]
                    self.assertTrue((REPO / path).exists(), f"{name}: {target}")

    def test_every_page_is_in_the_sidebar(self):
        """The English sidebar lists every English page, and leads to each translation's first page, which lists
        the rest (GitHub's wiki has one sidebar, and the docs site makes each language's from it)."""
        sidebar = (WIKI / "_Sidebar.md").read_text("utf-8")
        listed = {t.partition("#")[0] for t in LINK.findall(sidebar)}
        self.assertEqual(listed, {p for p in pages() if not p.startswith("_")})
        for lang, info in wiki_translations.LANGS.items():
            home = wiki_translations.names()[lang]["Home"]
            self.assertIn(f'<a href="{home}" lang="{lang}">{info["name"]}</a>', sidebar)
            linked = {t.partition("#")[0] for t in LINK.findall(translated(lang)[home]) if "://" not in t}
            self.assertEqual(linked - set(pages()), set(translated(lang)) - {home}, f"{lang}: its first page lists the rest")

    def test_every_translation_is_there_and_up_to_date(self):
        """Every English page (but those for working on Hoard itself) has a Japanese and a Korean translation, each
        saying what the English page does now: when an English page changes, its translations change with it
        (python3 scripts/wiki_translations.py --diff shows what changed)."""
        self.assertEqual(wiki_translations.check(), [])
        for lang in wiki_translations.LANGS:
            self.assertEqual(set(wiki_translations.translations(lang)), set(wiki_translations.english()), lang)
        self.assertEqual(wiki_translations.UNTRANSLATED, {"Development", "Releasing"})

    def test_a_changed_english_page_shows_its_translations_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            shutil.copytree(WIKI, wiki)
            with mock.patch.object(wiki_translations, "WIKI", wiki):
                self.assertEqual(wiki_translations.check(), [])
                with open(wiki / "Tags.md", "a", encoding="utf-8") as f:
                    f.write("\nA new sentence.\n")
                behind = wiki_translations.check()
                self.assertEqual(len(behind), 2, behind)
                self.assertTrue(all("behind wiki/Tags.md" in b and "--done" in b for b in behind), behind)
                wiki_translations.done("ja", "Tags")
                wiki_translations.done("ko", "Tags")
                self.assertEqual(wiki_translations.check(), [])
                (wiki / "ko" / "태그.md").unlink()
                self.assertIn("wiki/ko: no translation of wiki/Tags.md", wiki_translations.check())
                (wiki / "ja" / "Tags.md").write_text((wiki / "ja" / "タグ.md").read_text("utf-8"), "utf-8")
                self.assertTrue(any("another page is already called Tags" in p for p in wiki_translations.check()))

    def test_a_translation_starts_with_where_it_is_from(self):
        """Its first lines say which English page it's from (for the check above), and link the same page in each
        language, with a note that it was translated with AI's help and the English page is the one to trust. They're
        raw HTML, which the docs site leaves out for its own."""
        names = wiki_translations.names()
        for lang in wiki_translations.LANGS:
            for en, (name, blob) in wiki_translations.translations(lang).items():
                text = translated(lang)[name]
                first = wiki_translations.FIRST.match(text)
                self.assertIsNotNone(first, f"{lang}/{name}")
                self.assertIn(f'<a href="{en}">English</a>', first.group("bar"))
                for other in wiki_translations.LANGS:
                    if other != lang:
                        self.assertIn(f'<a href="{names[other][en]}">', first.group("bar"))
                self.assertIn("translation.yml", first.group("bar"))

    def test_commands_are_real(self):
        """Every command the wiki shows exists, and the Command line page lists every one."""
        commands = cli_commands()
        mention = re.compile(r"(?:hoard-cli(?:\.exe)?\"?|Hoard\.bat|run\.sh) ([a-z][a-z-]*)")
        for name, text in every_page().items():
            for cmd in mention.findall(text):
                self.assertIn(cmd, commands, f"{name}: {cmd}")
        names = wiki_translations.names()
        for page in ["Command-Line.md"] + [f"{lang}/{names[lang]['Command-Line']}.md" for lang in names]:
            table = set(re.findall(r"^\| `([a-z-]+)", (WIKI / page).read_text("utf-8"), re.M))
            self.assertEqual(table, commands, page)

    def test_settings_are_real(self):
        """Every config.json setting the Settings page names exists, with the default it gives."""
        for row in re.findall(r"^\| (`[a-z_.]+`.*)$", (WIKI / "Settings.md").read_text("utf-8"), re.M):
            names, defaults = row.split(" | ")[:2]
            keys, values = re.findall(r"`([a-z_.]+)`", names), re.findall(r"`([^`]+)`", defaults)
            for i, key in enumerate(keys):
                node = config.DEFAULT_CONFIG
                for part in key.split("."):
                    self.assertIn(part, node, f"Settings: {key}")
                    node = node[part]
                if len(values) == len(keys):
                    self.assertEqual(json.loads(values[i]), node, f"Settings: {key}'s default")

    def test_translated_settings_name_the_same_settings(self):
        """A translated Settings page's table names each setting, and its default, as the English one does: only
        what they mean is translated."""
        def rows(text):   # each row's setting, and its default (a row with none has its meaning second)
            cells = [row.split(" | ")[:2] for row in re.findall(r"^\| (`[a-z_.]+`.*)$", text, re.M)]
            return [(name, default if default.startswith("`") else "") for name, default in cells]
        english = rows((WIKI / "Settings.md").read_text("utf-8"))
        self.assertGreater(len(english), 20)
        for lang, names in wiki_translations.names().items():
            self.assertEqual(rows(translated(lang)[names["Settings"]]), english, lang)

    def test_the_wiki_is_published_from_main_only(self):
        wf = (REPO / ".github" / "workflows" / "wiki.yml").read_text("utf-8")
        self.assertIn('paths: ["wiki/**"', wf)
        self.assertIn(".wiki.git", wf)
        self.assertIn("permissions: {}", wf)
        self.assertIn("contents: write", wf)
        self.assertNotIn("pull_request", wf, "a write token never runs for a pull request")

    def test_the_wiki_is_copied_outside_the_checkout(self):
        """The wiki was cloned into ./site, which broke publishing once the website arrived in site/ ("destination
        path 'site' already exists"). It goes to the runner's temporary folder, so no folder here can clash."""
        wf = (REPO / ".github" / "workflows" / "wiki.yml").read_text("utf-8")
        dest = re.search(r'clone --quiet "https://github.com/\$GITHUB_REPOSITORY\.wiki\.git" (\S+);', wf).group(1)
        self.assertEqual(dest, '"$RUNNER_TEMP/wiki"')
        self.assertIn('cd "$RUNNER_TEMP/wiki"', wf)
        self.assertNotRegex(wf, r"\bcd site\b|cp -R wiki/\. site/")

    def test_translations_are_published_beside_the_english_pages(self):
        """GitHub's wiki keeps every page in one folder (and one sidebar), so the translations are copied in beside
        the English pages, each under its own name."""
        wf = (REPO / ".github" / "workflows" / "wiki.yml").read_text("utf-8")
        self.assertIn('cp wiki/*.md "$RUNNER_TEMP/wiki/"', wf)
        self.assertIn('for lang in wiki/*/; do cp "$lang"*.md "$RUNNER_TEMP/wiki/"; done', wf)
        everything = [p.name for p in WIKI.rglob("*.md")]
        self.assertEqual(len(everything), len(set(everything)), "no two pages share a name")


if __name__ == "__main__":
    unittest.main()
