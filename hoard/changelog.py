"""Hoard's changelog (CHANGELOG.md) as HTML: for What's new in the app, and the website's changelog page
(scripts/build_site_changelog.py). CHANGELOG.md uses a small part of Markdown: "## <version>" for each release,
"### " for a heading inside one, paragraphs, "- " lists (nested by two spaces, with continuation lines indented),
**bold**, `code` and [links](https://...). Everything is escaped first, so nothing in the changelog becomes markup
of its own. Standard library only.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from .paths import PACKAGE
from .versions import is_beta   # the same rule as the updater's and the website's

def inline(text: str) -> str:
    """One line of changelog text as HTML: escaped, with `code`, **bold** (around code too), [links](https://...)
    and bare https addresses as links, as GitHub shows them."""
    if text.count("`") % 2:   # an unmatched backtick: leave the line's backticks as they are
        parts = [text]
    else:
        parts = text.split("`")
    codes = [f"<code>{html.escape(p)}</code>" for p in parts[1::2]]
    # Code is set aside (as \x00n\x00, which can't be in the text) while the rest is escaped and marked up.
    rest = "".join(html.escape(p.replace("\x00", ""), quote=True) + (f"\x00{n}\x00" if n < len(codes) else "")
                   for n, p in enumerate(parts[0::2]))
    rest = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rest)
    rest = re.sub(r"\[([^\]]+)\]\((https://[^)\s\"<>\x00]+)\)", r'<a href="\2">\1</a>', rest)
    # bare addresses as links, but not inside a link already made (a link's text may hold an address: a link
    # inside a link isn't HTML, and browsers break it apart)
    rest = "".join(part if part.startswith("<a ") else
                   re.sub(r'(?<![="\w>])(https://[^\s<>"\x00]*[^\s<>"\x00.,;:!?)])', r'<a href="\1">\1</a>', part)
                   for part in re.split(r"(<a [^>]*>.*?</a>)", rest))
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], rest)


def blocks(lines: list[str]) -> str:
    """A release's lines as HTML: paragraphs, headings and nested lists."""
    out: list[str] = []
    para: list[str] = []
    stack: list[int] = []        # the indent of each open list
    item: list[str] | None = None  # the text of the list item being read

    def flush_para():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    def flush_item():
        nonlocal item
        if item is not None:
            out.append(inline(" ".join(item)))
            item = None

    def close_lists(to: int = -1):
        flush_item()
        while stack and stack[-1] > to:
            stack.pop()
            out.append("</li></ul>")

    for raw in lines:
        line = raw.rstrip()
        bullet = re.match(r"^( *)- (.*)$", line)
        if not line.strip():
            flush_para()
            continue
        if bullet:
            flush_para()
            indent, text = len(bullet.group(1)), bullet.group(2)
            if stack and indent > stack[-1]:      # a list inside the item being read
                flush_item()
                out.append("<ul>")
                stack.append(indent)
            else:
                close_lists(indent)
                if stack and stack[-1] == indent:
                    out.append("</li>")
                else:
                    out.append("<ul>")
                    stack.append(indent)
            out.append("<li>")
            item = [text.strip()]
            continue
        if item is not None and line.startswith(" "):   # an item's next line
            item.append(line.strip())
            continue
        close_lists()
        heading = re.match(r"^#{3,6} (.*)$", line)
        if heading:
            flush_para()
            out.append(f"<h4>{inline(heading.group(1).strip())}</h4>")
        else:
            para.append(line.strip())
    flush_para()
    close_lists()
    return "\n".join(out)


def releases(markdown: str) -> list[tuple[str, list[str]]]:
    """(version, its lines) for each "## " section, newest first, as the changelog lists them."""
    found, current = [], None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = (line[3:].strip(), [])
            found.append(current)
        elif current:
            current[1].append(line)
    return found


def changelog_file() -> Path:
    """CHANGELOG.md beside the hoard package: in a checkout or the release zip, the Flatpak (packaging/flatpak),
    and the built app (packaging/hoard.spec puts it there)."""
    return PACKAGE.parent / "CHANGELOG.md"


def whats_new(betas: bool, limit: int = 200) -> list[dict]:
    """The releases, newest first, as {"version", "beta", "html"}: betas left out unless betas (Settings: Get beta
    updates), as the website's page leaves them out. Empty when the changelog isn't there."""
    try:
        text = changelog_file().read_text("utf-8")
    except OSError:
        return []
    out = []
    for version, lines in releases(text):
        beta = is_beta(version)
        if beta and not betas:
            continue
        out.append({"version": version, "beta": beta, "html": blocks(lines)})
        if len(out) >= limit:
            break
    return out
