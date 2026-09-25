"""The wiki: the pages in wiki/, which .github/workflows/wiki.yml publishes to the repository's GitHub wiki. Every
link leads somewhere, every page can be reached, and what the pages say about commands and settings matches the
code, so the wiki can't quietly drift from the app.
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

from hoard import config  # noqa: E402

WIKI = REPO / "wiki"
BLOB = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/"
LINK = re.compile(r"\]\(([^)\s]+)\)")


def pages() -> dict[str, str]:
    """Every page, by the name its address uses."""
    return {p.stem: p.read_text("utf-8") for p in sorted(WIKI.glob("*.md"))}


def slug(heading: str) -> str:
    """The anchor GitHub gives a heading: lower case, punctuation dropped, each space a hyphen."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(text: str) -> set:
    return {slug(h) for h in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, re.M)}


def cli_commands() -> set:
    return set(re.findall(r'add_parser\("([a-z-]+)"', (REPO / "hoard" / "cli.py").read_text("utf-8")))


class Wiki(unittest.TestCase):

    def test_links_between_pages(self):
        """Every link to another page, and to a heading on one, leads somewhere."""
        all_pages = pages()
        for name, text in all_pages.items():
            for target in LINK.findall(text):
                if re.match(r"[a-z]+:", target):   # an address elsewhere
                    continue
                page, _, anchor = target.partition("#")
                page = page or name
                self.assertIn(page, all_pages, f"{name}: a link to {target}")
                if anchor:
                    self.assertIn(anchor, anchors(all_pages[page]), f"{name}: a link to {target}")

    def test_links_into_the_repository(self):
        for name, text in pages().items():
            for target in LINK.findall(text):
                if target.startswith(BLOB):
                    path = target[len(BLOB):].partition("#")[0]
                    self.assertTrue((REPO / path).exists(), f"{name}: {target}")

    def test_every_page_is_in_the_sidebar(self):
        listed = {t.partition("#")[0] for t in LINK.findall((WIKI / "_Sidebar.md").read_text("utf-8"))}
        self.assertEqual(listed, {p for p in pages() if not p.startswith("_")})

    def test_commands_are_real(self):
        """Every command the wiki shows exists, and the Command line page lists every one."""
        commands = cli_commands()
        mention = re.compile(r"(?:hoard-cli(?:\.exe)?\"?|Hoard\.bat|run\.sh) ([a-z][a-z-]*)")
        for name, text in pages().items():
            for cmd in mention.findall(text):
                self.assertIn(cmd, commands, f"{name}: {cmd}")
        table = set(re.findall(r"^\| `([a-z-]+)", (WIKI / "Command-Line.md").read_text("utf-8"), re.M))
        self.assertEqual(table, commands)

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

    def test_the_wiki_is_published_from_main_only(self):
        wf = (REPO / ".github" / "workflows" / "wiki.yml").read_text("utf-8")
        self.assertIn('paths: ["wiki/**"', wf)
        self.assertIn(".wiki.git", wf)
        self.assertIn("permissions: {}", wf)
        self.assertIn("contents: write", wf)
        self.assertNotIn("pull_request", wf, "a write token never runs for a pull request")


if __name__ == "__main__":
    unittest.main()
