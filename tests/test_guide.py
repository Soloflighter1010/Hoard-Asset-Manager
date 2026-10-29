"""Issue #194: docs/HOW-HOARD-WORKS.md, the map of how Hoard fits together, names files and functions in backticks so
a contributor can go straight to them: every one of them exists (a file moved or a function renamed fails here, until
the guide says where it went), and the guide is where contributors look for it."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUIDE = REPO / "docs" / "HOW-HOARD-WORKS.md"
# what the repository's own paths start with (the guide also names app-data folders, which aren't here)
ROOTS = ("hoard/", "tests/", "docs/", "wiki/", "share/", "Packages/", ".github/", "scripts/", "packaging/")
ROOT_FILES = ("CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md")


def spans(text: str) -> list[str]:
    """What's in backticks, outside the fenced blocks (commands to type)."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.findall(r"`([^`\n]+)`", text)


def definitions() -> set[str]:
    """Every function, class and module-level name defined in Hoard's code, its pages' script and the share server."""
    names: set[str] = set()
    sources = [*REPO.glob("hoard/**/*.py"), *REPO.glob("hoard/web/*.js"), *REPO.glob("hoard/web/*.html"), *REPO.glob("share/*.mjs")]
    for path in sources:
        text = path.read_text("utf-8", errors="replace")
        names.update(re.findall(r"^\s*(?:async\s+)?(?:def|class|function)\s+([A-Za-z_]\w*)", text, re.M))
        names.update(re.findall(r"^([A-Za-z_]\w*)\s*(?::[^=\n]+)?=", text, re.M))          # module-level names
        names.update(re.findall(r"^(?:const|let)\s+([A-Za-z_]\w*)\s*=", text, re.M))   # the pages' constants
    return names


class TheGuide(unittest.TestCase):

    def test_every_file_it_names_is_there(self):
        named = [s for s in spans(GUIDE.read_text("utf-8")) if "<" not in s and " " not in s
                 and (s.startswith(ROOTS) or s in ROOT_FILES)]
        self.assertGreater(len(named), 30)
        for path in named:
            self.assertTrue((REPO / path.rstrip("/")).exists(), f"docs/HOW-HOARD-WORKS.md names {path}, which isn't there")

    def test_every_function_it_names_is_there(self):
        defined = definitions()
        checked = 0
        for span in spans(GUIDE.read_text("utf-8")):
            m = re.fullmatch(r"([A-Za-z_][\w.]*)(?:\[[^\]]*\])?\(.*\)", span) or re.fullmatch(r"([A-Z][A-Za-z]+(?:\.[_a-z]\w*)?|[A-Z][A-Z_]{3,})", span)
            if not m or re.search(r"\.(md|py|js|json|html|cs|mjs|yml|css)$", span):   # (a file, not a name)
                continue
            name = m.group(1).split(".")[-1]
            checked += 1
            self.assertTrue(name in defined, f"docs/HOW-HOARD-WORKS.md names {span}, which isn't defined anywhere")
        self.assertGreater(checked, 40)

    def test_contributors_find_it(self):
        for page in (REPO / "CONTRIBUTING.md", REPO / "wiki" / "Development.md", REPO / "docs" / "ARCHITECTURE.md"):
            self.assertIn("HOW-HOARD-WORKS.md", page.read_text("utf-8"), f"{page.name} links to the guide")


if __name__ == "__main__":
    unittest.main()
