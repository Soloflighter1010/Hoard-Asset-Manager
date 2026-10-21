"""Build the website's docs (docs/ on the site) from the wiki's pages (wiki/*.md), so the docs and the GitHub wiki
are the same pages, written once, in wiki/. The wiki's Japanese and Korean pages (wiki/ja/, wiki/ko/: see
scripts/wiki_translations.py) become docs/ja/ and docs/ko/, each page at its English page's address there.

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
from urllib.parse import quote

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "wiki"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_chrome import GITHUB, footer, header, preloads  # noqa: E402
from wiki_translations import FIRST, ISSUE, LANGS  # noqa: E402

SITE = "https://hoard.furryup.link/docs/"
# The docs' own words in each language the wiki is in (the site's bar and footer are in English)
UI = {
    "en": {"name": "English", "docs": "Hoard docs", "skip": "Skip to the page", "search": "Search the docs",
           "none": "Nothing in the docs matches that.", "pages": "Docs pages", "toc": "On this page",
           "anchor": "Link to this section",
           "edit": "These docs are written in the repository's <code>wiki/</code> folder, and are also\n"
                   '        <a href="{wiki}">on GitHub\'s wiki</a>.\n        <a href="{source}">Suggest a change to this page</a>.'},
    "ja": {"docs": "Hoardドキュメント", "skip": "本文へ移動", "search": "ドキュメントを検索",
           "none": "一致するものがありません。", "pages": "ドキュメントのページ", "toc": "このページの内容",
           "anchor": "このセクションへのリンク",
           "edit": 'このページはリポジトリの <code>wiki/ja/</code> フォルダーで書かれていて、<a href="{wiki}">GitHubのwiki</a>にもあります。'
                   'AIの助けを借りて<a href="{english}">英語版</a>から翻訳したので、内容が違うときは英語版が正しい情報です。'
                   '<a href="{issue}">翻訳の修正</a>で教えてください。'},
    "ko": {"docs": "Hoard 문서", "skip": "본문으로 건너뛰기", "search": "문서 검색",
           "none": "맞는 것이 없어요.", "pages": "문서 페이지", "toc": "이 페이지의 내용",
           "anchor": "이 섹션으로 가는 링크",
           "edit": '이 페이지는 저장소의 <code>wiki/ko/</code> 폴더에서 쓰고, <a href="{wiki}">GitHub wiki</a>에도 있어요. '
                   'AI의 도움을 받아 <a href="{english}">영어판</a>에서 번역해서, 내용이 다르면 영어판이 맞는 정보예요. '
                   '<a href="{issue}">번역 수정</a>으로 알려 주세요.'},
}
for _code, _info in LANGS.items():
    UI[_code]["name"] = _info["name"]

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
    """The wiki's pages in one language, by the name their address uses, and the headings on each, for checking
    links. A translation's pages (english: the English ones) each go at its English page's address, and can link to
    an English page that has no translation."""

    def __init__(self, folder: Path = WIKI, english: Pages | None = None):
        self.text = {p.stem: p.read_text("utf-8") for p in sorted(folder.glob("*.md"))}
        self.anchors = {n: {slug(h) for h in re.findall(r"^#{1,6}\s+(.+?)\s*$", t, re.M)} for n, t in self.text.items()}
        self.english = english
        self.source = {}   # each page's English page, by its own name
        for name, text in self.text.items():
            m = FIRST.match(text) if english else None
            self.source[name] = m.group("page") if m else name
        self.named = {en: name for name, en in self.source.items() if not name.startswith("_")}   # and back

    def href(self, target: str, here: str) -> str:
        """Where a link in a wiki page goes, on the site: another page (and a heading on it), a heading on this one,
        or an https address. Anything else is a broken link."""
        if re.match(r"https://[^\s\"<>]+$", target):
            return target
        name, _, anchor = target.partition("#")
        name = name or here
        pages, up = self, ""
        if (name not in self.text or name.startswith("_")) and self.english:   # an English page with no translation
            pages, up = self.english, "../"
        if name not in pages.text or name.startswith("_"):
            raise BrokenLink(f"{here}: a link to {target}: no page {name}")
        if anchor and anchor not in pages.anchors[name]:
            raise BrokenLink(f"{here}: a link to {target}: no heading #{anchor} on {name}")
        return (up + page_file(pages.source[name]) if name != here else "") + (f"#{anchor}" if anchor else "")


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
    def __init__(self, link, anchor_label: str = UI["en"]["anchor"]):
        self.link = link
        self.anchor_label = anchor_label
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
                           f'<a class="anchor" href="#{html.escape(anchor, quote=True)}" aria-label="{self.anchor_label}">#</a></h{level}>')
                i += 1
                continue
            if line.lstrip().startswith("|") and i + 1 < n and SEPARATOR.match(lines[i + 1]):
                head, i, rows = cells(line), i + 2, []
                while i < n and lines[i].lstrip().startswith("|"):
                    rows.append(cells(lines[i]))
                    i += 1
                # each cell names its column (data-label): on a phone, a row is a card with its values under them
                labels = [html.escape(plain(self.inline(c)), quote=True) for c in head]
                out.append('<div class="table"><table><thead><tr>' + "".join(f"<th>{self.inline(c)}</th>" for c in head)
                           + "</tr></thead><tbody>" + "".join(
                               "<tr>" + "".join((f'<td data-label="{labels[k]}">' if k < len(labels) and labels[k] else "<td>")
                                                + f"{self.inline(c)}</td>" for k, c in enumerate(r)) + "</tr>" for r in rows)
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


def sidebar(pages: Pages, current: str, lang: str = "en") -> tuple[str, dict[str, str]]:
    """The docs' sidebar, from wiki/_Sidebar.md: its groups and links, with the page you're on marked (current: its
    English name). In a translation, each page under its own name, and an English page it has no translation of from
    the English docs. Also each page's title, as the sidebar names it, by English name."""
    english = pages.english or pages
    titles, groups, group = {}, [], None
    for line in english.text.get("_Sidebar", "").splitlines():
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
    href = {n: page_file(n) for n in titles}
    if pages.english:
        for name in titles:
            if name in pages.named:
                titles[name] = LANGS[lang]["home"] if name == "Home" else pages.named[name].replace("-", " ")
            else:
                href[name] = "../" + href[name]
    parts = []
    for label, names in groups:
        if label:
            parts.append(f"<h2>{html.escape(LANGS[lang]['groups'].get(label, label) if pages.english else label)}</h2>")
        here = ' aria-current="page"'
        parts.append("<ul>" + "".join(
            f'<li><a href="{href[n]}"{here if n == current else ""}>{html.escape(titles[n])}</a></li>'
            for n in names) + "</ul>")
    return "\n".join(parts), titles


def languages(lang: str, page: str, have: dict[str, set[str]]) -> tuple[str, str]:
    """This page in each language the docs are in (that language's first page, where it has no such page): links for
    the sidebar, and the <link rel="alternate"> lines for search engines."""
    links, alternates = [], []
    for code in have:
        there = (page_file(page) if page in have[code] else "index.html")
        path = ("" if code == "en" else f"{code}/") + there
        if page in have[code]:
            alternates.append(f'  <link rel="alternate" hreflang="{code}" href="{SITE}{path}">\n')
        if code == lang:
            links.append(f'<b lang="{code}">{UI[code]["name"]}</b>')
        else:
            links.append(f'<a href="{"" if lang == "en" else "../"}{path}" lang="{code}" hreflang="{code}">{UI[code]["name"]}</a>')
    if len(alternates) > 1:
        alternates.append(f'  <link rel="alternate" hreflang="x-default" href="{SITE}{page_file(page)}">\n')
    else:
        alternates = []
    return f'<p class="docs-langs">{" · ".join(links)}</p>', "".join(alternates)


PAGE = """<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{headtitle}</title>
  <meta name="description" content="{description}">
  <meta property="og:site_name" content="Hoard">
  <meta property="og:title" content="{headtitle}">
  <meta property="og:description" content="{description}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{SITE}{file}">
  <meta property="og:image" content="https://hoard.furryup.link/img/social-docs.jpg">
  <meta property="og:image:type" content="image/jpeg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Hoard's logo and “Hoard docs”, beside a shelf of tiles in each store's colour">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="theme-color" content="#F0B429">
  <meta name="color-scheme" content="dark light">
{alternates}  <link rel="icon" href="{up}favicon.ico">
{preloads}  <link rel="stylesheet" href="{up}styles.css">
</head>
<body>
  <div class="glow" aria-hidden="true"><div class="glow-in"></div></div>
  <a class="skip" href="#main">{skip}</a>
  {header}

  <div class="docs">
    <aside class="docs-side" aria-label="{docs}">
      {langs}
      <div class="docs-search" role="search">
        <input id="docSearch" type="search" placeholder="{search}" aria-label="{search}" autocomplete="off" data-none="{none}">
        <ol id="docResults" hidden></ol>
      </div>
      <nav aria-label="{pages}">
{sidebar}
      </nav>
    </aside>
    <main id="main" class="doc">
      <h1>{title}</h1>
{body}
      <p class="doc-edit small">{edit}</p>
    </main>
    <nav class="doc-toc" aria-label="{toc}">{tocs}</nav>
  </div>

  {footer}
  <script src="{up}site.js" defer></script>
</body>
</html>
"""


def plain(fragment: str) -> str:
    """Text of an HTML fragment, for search and the description."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def build(out: Path, folder: Path = WIKI) -> list[str]:
    """Write every page to out (a folder: docs/ on the site) with search.json, and each translation's to its own
    folder in it (docs/ja/). Returns the pages written. Raises BrokenLink for a link to a page or heading that isn't
    there."""
    english = Pages(folder)
    every = {"en": english}
    every.update({lang: Pages(folder / lang, english) for lang in LANGS if (folder / lang).is_dir()})
    have = {lang: set(pages.named) for lang, pages in every.items()}
    written = []
    for lang, pages in every.items():
        where = "" if lang == "en" else f"{lang}/"
        written += [where + f for f in _build(lang, pages, out / where, have)]
    return written


def _build(lang: str, pages: Pages, out: Path, have: dict[str, set[str]]) -> list[str]:
    ui, up = UI[lang], "../" if lang == "en" else "../../"
    out.mkdir(parents=True, exist_ok=True)
    index, written = [], []
    for name, text in pages.text.items():
        if name.startswith("_"):
            continue
        page = pages.source[name]
        r = Renderer(lambda target, here=name: pages.href(target, here), ui["anchor"])
        body = r.blocks(text.splitlines())
        side, titles = sidebar(pages, page, lang)
        title = ui["docs"] if page == "Home" else titles.get(page, name.replace("-", " "))
        intro = plain(body.split("<h2", 1)[0])[:200] or f"{title}: Hoard's documentation."
        toc = "".join(f'<a class="l{lvl}" href="#{html.escape(a, quote=True)}">{html.escape(t)}</a>'
                      for lvl, a, t in r.headings if lvl <= 3)
        toc = f"<h2>{ui['toc']}</h2>{toc}" if toc else ""
        where = "" if lang == "en" else f"{lang}/"
        langs, alternates = languages(lang, page, have)
        edit = ui["edit"].format(wiki=f"{GITHUB}/wiki/{quote(name)}", source=f"{GITHUB}/blob/main/wiki/{where}{quote(name)}.md",
                                 english=f"../{page_file(page)}", issue=html.escape(ISSUE, quote=True))
        text = (PAGE.replace("{header}", header("docs/", up=up)).replace("{footer}", footer(up=up))
                .replace("{preloads}", preloads(up)).replace("{alternates}", alternates).replace("{up}", up)
                .replace("{langs}", langs).replace("{sidebar}", side).replace("{tocs}", toc).replace("{edit}", edit)
                .replace("{lang}", lang).replace("{skip}", ui["skip"]).replace("{docs}", ui["docs"])
                .replace("{search}", ui["search"]).replace("{none}", ui["none"]).replace("{pages}", ui["pages"])
                .replace("{toc}", ui["toc"]).replace("{SITE}", SITE).replace("{file}", where + page_file(page))
                .replace("{description}", html.escape(intro, quote=True))
                .replace("{headtitle}", html.escape(title if page == "Home" else f"{title} · {ui['docs']}"))
                .replace("{title}", html.escape(title))
                .replace("{body}", body))
        (out / page_file(page)).write_text(text, "utf-8")
        written.append(page_file(page))
        # search: each section, by its heading, with its words
        sections = re.split(r'(?=<h[23] id=")', body)
        for sec in sections:
            m = re.match(r'<h[23] id="([^"]+)">(.*?)<a class="anchor"', sec)
            index.append({"page": page_file(page), "title": title, "anchor": m.group(1) if m else "",
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
