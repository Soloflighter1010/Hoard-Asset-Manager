"""Issue #209: every module, class and function says what it's for, so the code can be read by someone new to it.

Python: a docstring, or a comment on its line or right above it (a dunder like __init__ says nothing its class
doesn't, so it needs none). The tests' own modules say what they test; their test methods' names say the rest.
The pages' scripts (and the website's, and the share server's): a comment on a function's line or right above it.
Hoard for Unity: a /// <summary> (or a comment) above each class and method, above its attributes. The workflows:
a comment at the top (under its name) saying what each is for.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = ("hoard", "scripts", "packaging")
SCRIPTS = ("hoard/web/*.js", "hoard/web/*.html", "site/*.js", "share/*.mjs", "Website/*.js")
CSHARP = ("Packages/soloflighter.hoard/**/*.cs", "tests/unity/*.cs")   # (com.vrchat.core.bootstrap is VRChat's own)
# a function: declared, or a const/let/var given an arrow function or a function expression
JS_FUNCTION = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(|"
                         r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?"
                         r"(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")
# a class, struct or enum, or a method: modifiers, then a type and a name and its (
CS_MEMBER = re.compile(r"^\s*(?:(?:public|private|internal|protected|static|readonly|sealed|abstract|override|virtual|"
                       r"async|partial|unsafe|extern|new)\s+)+(?:(?:class|struct|enum|interface|record)\s+([A-Za-z_]\w*)|"
                       r"[\w<>\[\],.? ]+?\s+([A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*\()")


def commented(lines: list[str], node: ast.AST) -> bool:
    """A docstring, a comment on the def line, or a comment right above it (above its decorators)."""
    if ast.get_docstring(node):
        return True
    if "#" in lines[node.lineno - 1]:
        return True
    first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return first >= 2 and lines[first - 2].strip().startswith("#")


def undocumented(path: Path) -> list[str]:
    """What in a Python file says nothing about what it's for."""
    text = path.read_text("utf-8")
    lines, tree = text.splitlines(), ast.parse(text)
    rel = path.relative_to(REPO).as_posix()
    out = [] if ast.get_docstring(tree) else [f"{rel}: the module"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not commented(lines, node) \
                and not (node.name.startswith("__") and node.name.endswith("__")):
            out.append(f"{rel}:{node.lineno} {node.name}")
    return out


def said_above(lines: list[str], i: int, skip: str = "") -> bool:
    """A comment on line i, or ending right above it (above any lines starting with skip: C#'s attributes)."""
    if "//" in lines[i] or "/*" in lines[i]:
        return True
    j = i - 1
    while skip and j >= 0 and lines[j].strip().startswith(skip):
        j -= 1
    above = lines[j].strip() if j >= 0 else ""
    return above.startswith(("//", "*")) or above.endswith("*/")


def uncommented(path: Path, pattern: re.Pattern, skip: str = "") -> list[str]:
    """The functions (or C#'s classes and methods) in a file with no comment saying what they're for."""
    lines = path.read_text("utf-8-sig").splitlines()
    rel = path.relative_to(REPO).as_posix()
    out = []
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if not m or (pattern is CS_MEMBER and re.search(r"\b(return|new)\b|=", line.split("(")[0])):
            continue   # (a C# statement, as "static readonly Foo x = new Foo(", isn't a method)
        if not said_above(lines, i, skip):
            out.append(f"{rel}:{i + 1} {m.group(1) or m.group(2)}")
    return out


class EverythingSaysWhatItsFor(unittest.TestCase):

    def test_python(self):
        files = [p for d in PYTHON for p in sorted((REPO / d).rglob("*.py"))]
        self.assertGreater(len(files), 80)
        missing = [m for p in files for m in undocumented(p)]
        self.assertEqual(missing, [], "say what each is for, in a docstring or a comment above it")

    def test_the_tests_say_what_they_test(self):
        for p in sorted((REPO / "tests").glob("*.py")):
            self.assertTrue(ast.get_docstring(ast.parse(p.read_text("utf-8"))), f"{p.name}: say what it tests")

    def test_the_pages_scripts(self):
        files = [p for g in SCRIPTS for p in sorted(REPO.glob(g))]
        self.assertGreater(len(files), 8)
        missing = [m for p in files for m in uncommented(p, JS_FUNCTION)]
        self.assertEqual(missing, [], "say what each function is for, in a comment above it")

    def test_hoard_for_unity(self):
        files = [p for g in CSHARP for p in sorted(REPO.glob(g))]
        self.assertGreater(len(files), 20)
        missing = [m for p in files for m in uncommented(p, CS_MEMBER, skip="[")]
        self.assertEqual(missing, [], "say what each is for, in a /// <summary> above it")

    def test_the_workflows(self):
        for p in sorted((REPO / ".github" / "workflows").glob("*.yml")):
            top = p.read_text("utf-8").split("\non:", 1)[0]   # (its name, then what it's for)
            self.assertRegex(top, r"(?m)^# \S", f"{p.name}: say what it's for at its top")


if __name__ == "__main__":
    unittest.main()
