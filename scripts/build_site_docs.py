"""Build the website's docs (docs/ on the site) from the wiki's pages (wiki/*.md), so the docs and the GitHub wiki
are the same pages, written once, in wiki/.

Run on deploy by build-listing.yml; nothing generated is kept in the repository. Each page gets the site's bar and
footer (scripts/site_chrome.py), a sidebar from wiki/_Sidebar.md, a link on every heading, and the page's headings
beside it; search.json lets the docs' search box find any section. A link to a page or heading that isn't there
stops the build, so a broken link never reaches the site.

    python3 scripts/build_site_docs.py OUT_FOLDER

The wiki uses a small part of Markdown, and this reads just that: "## " and "### " headings, paragraphs, "- " and
"1. " lists (nested by indenting, with continuation lines indented), tables, ``` code blocks, **bold**, `code`,
[links](Page#heading) and [links](https://...). Everything is escaped first, so nothing in a page becomes markup of
its own; raw HTML (the logo at the top of Home) is left out. Standard library only.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "wiki"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_chrome import GITHUB, footer, header  # noqa: E402

LIST = re.compile(r"^( *)([-*]|\d+\.) +(.*)$")
FENCE = re.compile(r"^ *```")
HEADING = re.compile(r"^(#{1,6}) +(.+?) *#* *$")
SEPARATOR = re.compile(r"^ *\|? *:?-{3,}:? *(\| *:?-{3,}:? *)*\|? *$")


class BrokenLink(ValueError):
    pass


def slug(heading: str) -> str:
    """The anchor GitHub gives a heading (as tests/test_wiki.py checks the wiki's links by): lower case,
    punctuation dropped, each space a hyphen."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def page_file(name: str) -> str:
    return "index.html" if name == "Home" else f"{name}.html"


class Pages:
    """The wiki's pages, by the name their address uses, and the headings on each, for checking links."""

    def __init__(self, folder: Path = WIKI):
        self.text = {p.stem: p.read_text("utf-8") for p in sorted(folder.glob("*.md"))}
        self.anchors = {n: {slug(h) for h in re.findall(r"^#{1,6}\s+(.+?)\s*$", t, re.M)} for n, t in self.text.items()}

    def href(self, target: str, here: str) -> str:
        """Where a link in a wiki page goes, on the site: another page (and a heading on it), a heading on this one,
        or an https address. Anything else is a broken link."""
        if re.match(r"https://[^\s\"<>]+$", target):
            return target
        name, _, anchor = target.partition("#")
        name = name or here
        if name not in self.text or name.startswith("_"):
            raise BrokenLink(f"{here}: a link to {target}: no page {name}")
        if anchor and anchor not in self.anchors[name]:
            raise BrokenLink(f"{here}: a link to {target}: no heading #{anchor} on {name}")
        return (page_file(name) if name != here else "") + (f"#{anchor}" if anchor else "")


def inline(text: str, link) -> str:
    """One line as HTML: escaped, with `code`, **bold** and [links](...) (link: where each goes), and bare https
    addresses as links. Code is set aside while the rest is escaped and marked up."""
    parts = [text] if text.count("`") % 2 else text.split("`")
    codes = [f"<code>{html.escape(p)}</code>" for p in parts[1::2]]
    rest = "".join(html.escape(p.replace("\x00", ""), quote=True) + (f"\x00{n}\x00" if n < len(codes) else "")
                   for n, p in enumerate(parts[0::2]))
    rest = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rest)
    rest = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                  lambda m: f'<a href="{html.escape(link(html.unescape(m.group(2))), quote=True)}">{m.group(1)}</a>', rest)
    rest = "".join(part if part.startswith("<a ") else
                   re.sub(r'(?<![="\w>])(https://[^\s<>"\x00]*[^\s<>"\x00.,;:!?)])', r'<a href="\1">\1</a>', part)
                   for part in re.split(r"(<a [^>]*>.*?</a>)", rest))
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], rest)


def cells(row: str) -> list[str]:
    """A table row's cells: split on |, but not on one inside `code`."""
    row = row.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") and not row.endswith("\\|") else row
    out, cur, code = [], "", False
    for ch in row:
        if ch == "`":
            code = not code
        if ch == "|" and not code:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return out


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def starts_block(line: str) -> bool:
    return bool(LIST.match(line) or FENCE.match(line) or HEADING.match(line) or line.lstrip().startswith("|"))


class Renderer:
    def __init__(self, link):
        self.link = link
        self.headings: list[tuple[int, str, str]] = []   # (level, id, text), for the page's own contents

    def inline(self, text: str) -> str:
        return inline(text, self.link)

    def blocks(self, lines: list[str]) -> str:
        out, i, n = [], 0, len(lines)
        while i < n:
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if FENCE.match(line):   # a code block, as it is
                pad, i, code = indent_of(line), i + 1, []
                while i < n and not FENCE.match(lines[i]):
                    code.append(lines[i][min(pad, indent_of(lines[i])):])
                    i += 1
                i += 1
                out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
                continue
            if line.lstrip().startswith("<"):   # raw HTML (Home's logo): not on the site
                while i < n and lines[i].strip():
                    i += 1
                continue
            m = HEADING.match(line)
            if m:
                level, text = len(m.group(1)), m.group(2)
                anchor = slug(text)
                level = max(level, 2)   # (the page's title is its only <h1>)
                self.headings.append((level, anchor, re.sub(r"[*`]", "", text)))
                out.append(f'<h{level} id="{html.escape(anchor, quote=True)}">{self.inline(text)}'
                           f'<a class="anchor" href="#{html.escape(anchor, quote=True)}" aria-label="Link to this section">#</a></h{level}>')
                i += 1
                continue
            if line.lstrip().startswith("|") and i + 1 < n and SEPARATOR.match(lines[i + 1]):
                head, i, rows = cells(line), i + 2, []
                while i < n and lines[i].lstrip().startswith("|"):
                    rows.append(cells(lines[i]))
                    i += 1
                out.append('<div class="table"><table><thead><tr>' + "".join(f"<th>{self.inline(c)}</th>" for c in head)
                           + "</tr></thead><tbody>" + "".join(
                               "<tr>" + "".join(f"<td>{self.inline(c)}</td>" for c in r) + "</tr>" for r in rows)
                           + "</tbody></table></div>")
                continue
            m = LIST.match(line)
            if m:
                i = self.list(lines, i, out)
                continue
            para = []
            while i < n and lines[i].strip() and not (para and starts_block(lines[i])):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{self.inline(' '.join(para))}</p>")
        return "\n".join(out)

    def list(self, lines: list[str], i: int, out: list[str]) -> int:
        """A list from line i (its items, each with whatever is indented under it), and where it ends."""
        n = len(lines)
        first = LIST.match(lines[i])
        indent, ordered = len(first.group(1)), first.group(2)[0].isdigit()
        items = []
        while i < n:
            m = LIST.match(lines[i])
            if not m or len(m.group(1)) != indent or m.group(2)[0].isdigit() != ordered:
                break
            inner = indent + len(m.group(2)) + 1
            body, i = [m.group(3)], i + 1
            while i < n:
                line = lines[i]
                if not line.strip():   # a blank line: the item goes on if what follows is indented under it
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and indent_of(lines[j]) > indent:
                        body.extend([""] * (j - i))
                        i = j
                        continue
                    break
                if indent_of(line) <= indent:
                    break
                body.append(line[min(inner, indent_of(line)):])
                i += 1
            items.append(body)
        tag = "ol" if ordered else "ul"
        start = int(first.group(2)[:-1]) if ordered else 1
        out.append(f"<{tag}{f' start={start}' if ordered and start != 1 else ''}>")
        for body in items:
            inner_html = self.blocks(body)
            if inner_html.count("<p>") == 1 and inner_html.startswith("<p>"):   # a short item: no paragraph in it
                inner_html = inner_html[3:].replace("</p>", "", 1)
            out.append(f"<li>{inner_html}</li>")
        out.append(f"</{tag}>")
        return i


def sidebar(pages: Pages, current: str) -> tuple[str, dict[str, str]]:
    """The docs' sidebar, from _Sidebar.md: its groups and links, with the page you're on marked. Also each page's
    title, as the sidebar names it."""
    titles, groups, group = {}, [], None
    for line in pages.text.get("_Sidebar", "").splitlines():
        line = line.strip()
        m = re.match(r"^(?:- )?\*{0,2}\[([^\]]+)\]\(([^)#]+)\)\*{0,2}$", line)
        if m:
            name = m.group(2)
            titles[name] = m.group(1)
            if group is None:
                group = ("", [])
                groups.append(group)
            group[1].append(name)
            continue
        m = re.match(r"^\*\*(.+)\*\*$", line)
        if m:
            group = (m.group(1), [])
            groups.append(group)
    parts = []
    for label, names in groups:
        if label:
            parts.append(f"<h2>{html.escape(label)}</h2>")
        here = ' aria-current="page"'
        parts.append("<ul>" + "".join(
            f'<li><a href="{page_file(n)}"{here if n == current else ""}>{html.escape(titles[n])}</a></li>'
            for n in names) + "</ul>")
    return "\n".join(parts), titles


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{headtitle}</title>
  <meta name="description" content="{description}">
  <meta property="og:site_name" content="Hoard">
  <meta property="og:title" content="{headtitle}">
  <meta property="og:description" content="{description}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="https://hoard.furryup.link/docs/{file}">
  <meta property="og:image" content="https://hoard.furryup.link/img/social-docs.jpg">
  <meta property="og:image:type" content="image/jpeg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Hoard's logo and “Hoard docs”, beside a shelf of tiles in each store's colour">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="theme-color" content="#F0B429">
  <meta name="color-scheme" content="dark light">
  <link rel="icon" href="../favicon.ico">
  <link rel="stylesheet" href="../styles.css">
</head>
<body>
  <div class="glow" aria-hidden="true"><div class="glow-in"></div></div>
  <a class="skip" href="#main">Skip to the page</a>
  {header}

  <div class="docs">
    <aside class="docs-side" aria-label="Docs">
      <div class="docs-search" role="search">
        <input id="docSearch" type="search" placeholder="Search the docs" aria-label="Search the docs" autocomplete="off">
        <ol id="docResults" hidden></ol>
      </div>
      <nav aria-label="Docs pages">
{sidebar}
      </nav>
    </aside>
    <main id="main" class="doc">
      <h1>{title}</h1>
{body}
      <p class="doc-edit small">These docs are written in the repository's <code>wiki/</code> folder, and are also
        <a href="{GITHUB}/wiki/{name}">on GitHub's wiki</a>.
        <a href="{GITHUB}/blob/main/wiki/{name}.md">Suggest a change to this page</a>.</p>
    </main>
    <nav class="doc-toc" aria-label="On this page">{toc}</nav>
  </div>

  {footer}
  <script src="../site.js" defer></script>
</body>
</html>
"""


def plain(fragment: str) -> str:
    """Text of an HTML fragment, for search and the description."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def build(out: Path, folder: Path = WIKI) -> list[str]:
    """Write every page to out (a folder: docs/ on the site) with search.json. Returns the pages written. Raises
    BrokenLink for a link to a page or heading that isn't there."""
    pages = Pages(folder)
    out.mkdir(parents=True, exist_ok=True)
    index, written = [], []
    for name, text in pages.text.items():
        if name.startswith("_"):
            continue
        r = Renderer(lambda target, here=name: pages.href(target, here))
        body = r.blocks(text.splitlines())
        side, titles = sidebar(pages, name)
        title = "Hoard docs" if name == "Home" else titles.get(name, name.replace("-", " "))
        intro = plain(body.split("<h2", 1)[0])[:200] or f"{title}: Hoard's documentation."
        toc = "".join(f'<a class="l{lvl}" href="#{html.escape(a, quote=True)}">{html.escape(t)}</a>'
                      for lvl, a, t in r.headings if lvl <= 3)
        toc = f"<h2>On this page</h2>{toc}" if toc else ""
        page = (PAGE.replace("{header}", header("docs/", up="../")).replace("{footer}", footer(up="../"))
                .replace("{sidebar}", side).replace("{toc}", toc).replace("{GITHUB}", GITHUB)
                .replace("{name}", name).replace("{file}", page_file(name))
                .replace("{description}", html.escape(intro, quote=True))
                .replace("{headtitle}", html.escape(title if name == "Home" else f"{title} · Hoard docs"))
                .replace("{title}", html.escape(title))
                .replace("{body}", body))
        (out / page_file(name)).write_text(page, "utf-8")
        written.append(page_file(name))
        # search: each section, by its heading, with its words
        sections = re.split(r'(?=<h[23] id=")', body)
        for sec in sections:
            m = re.match(r'<h[23] id="([^"]+)">(.*?)<a class="anchor"', sec)
            index.append({"page": page_file(name), "title": title, "anchor": m.group(1) if m else "",
                          "heading": plain(m.group(2)) if m else title, "text": plain(sec)[:1200]})
    (out / "search.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), "utf-8")
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0].startswith("-"):
        print(__doc__.strip().split("\n\n")[1])
        return 2
    try:
        written = build(Path(argv[0]))
    except BrokenLink as e:
        print(f"The docs weren't built: {e}", file=sys.stderr)
        return 1
    print(f"Built {len(written)} pages into {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
