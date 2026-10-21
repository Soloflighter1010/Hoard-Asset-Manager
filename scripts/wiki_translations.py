"""The wiki in Japanese and Korean: wiki/ja/ and wiki/ko/, a page for each of the English pages in wiki/ (but those
for people working on Hoard itself, who read the code's English anyway).

A translated page has its own name, in its own language (GitHub's wiki takes a page's title from its name, and keeps
every page in one folder, so no two can share one), and starts with a line saying which English page it's from, and
that page as it was then (git's id for the file). So when an English page changes, its translations show as behind,
and git can show what changed since:

    python3 scripts/wiki_translations.py               checks every page has its translations, each up to date
    python3 scripts/wiki_translations.py --diff        shows what changed in each English page since it was translated
    python3 scripts/wiki_translations.py --done ja Settings
                                                       says ja's Settings now says what the English page does
    python3 scripts/wiki_translations.py --write       writes each translation's first lines (its languages) again

Standard library only.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "wiki"
ISSUE = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml"

# Pages for people working on Hoard itself: they stay in English, and the translations link to them.
UNTRANSLATED = {"Development", "Releasing"}

LANGS = {
    "ja": {
        "name": "日本語",
        "home": "ホーム",
        "note": "AIの助けを借りて英語版から翻訳したページです。英語版と内容が違うときは、英語版が正しい情報です。"
                f'おかしな訳を見つけたら<a href="{ISSUE}">翻訳の修正</a>で教えてください。',
        "groups": {"Using Hoard": "Hoardを使う", "More": "その他", "Working on Hoard": "Hoardの開発(英語)"},
    },
    "ko": {
        "name": "한국어",
        "home": "홈",
        "note": "AI의 도움을 받아 영어판에서 번역한 페이지예요. 영어판과 내용이 다르면 영어판이 맞는 정보예요. "
                f'이상한 번역을 찾으면 <a href="{ISSUE}">번역 수정</a>으로 알려 주세요.',
        "groups": {"Using Hoard": "Hoard 쓰기", "More": "더 보기", "Working on Hoard": "Hoard 개발(영어)"},
    },
}

FIRST = re.compile(r"\A<!-- Translated from (?P<page>[A-Za-z-]+) \(English (?P<blob>[0-9a-f]{12})\)\.[^\n]*-->\n"
                   r"(?P<bar><p>[^\n]*</p>)\n\n")
NAME = re.compile(r"^[^\s/\\:*?\"<>|#%_][^\s/\\:*?\"<>|#%]*$")


def blob(path: Path) -> str:
    """git's id for the file as it is (abbreviated), so `git diff OLD NEW` shows what changed since."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()[:12]


def english() -> list[str]:
    """The English pages that have translations."""
    return [p.stem for p in sorted(WIKI.glob("*.md")) if not p.stem.startswith("_") and p.stem not in UNTRANSLATED]


def translations(lang: str) -> dict[str, tuple[str, str]]:
    """lang's pages: {English page: (its name in lang, the English page's blob it was translated from)}. A page
    without its first line is under "" (with its name), for check() to name."""
    out = {}
    for p in sorted((WIKI / lang).glob("*.md")):
        m = FIRST.match(p.read_text("utf-8"))
        key = m.group("page") if m else ""
        if key in out:
            key = f"{key} (twice)"
        out[key] = (p.stem, m.group("blob") if m else "")
    return out


def names() -> dict[str, dict[str, str]]:
    """{lang: {English page: its name in lang}}, Home included."""
    return {lang: {en: name for en, (name, _) in translations(lang).items()} for lang in LANGS}


def first_lines(lang: str, page: str, source_blob: str, all_names: dict[str, dict[str, str]]) -> str:
    """A translation's first lines: where it's from, and the page in each language (raw HTML, so the docs site, which
    has its own, leaves them out)."""
    links = [f'<a href="{page}">English</a>'] + [
        f"<b>{info['name']}</b>" if code == lang else f'<a href="{all_names[code].get(page, page)}">{info["name"]}</a>'
        for code, info in LANGS.items()]
    return (f"<!-- Translated from {page} (English {source_blob}). When the English page changes: "
            f"python3 scripts/wiki_translations.py --diff -->\n"
            f"<p><sub>{' · '.join(links)} · {LANGS[lang]['note']}</sub></p>\n\n")


def check() -> list[str]:
    """What isn't as it should be: a page with no translation, one that's behind its English page, a name GitHub's
    wiki can't have or two pages share, first lines not as written here."""
    problems, all_names, taken = [], names(), {p.stem for p in WIKI.glob("*.md")}
    pages = english()
    for lang in LANGS:
        found = translations(lang)
        for en, (name, source_blob) in found.items():
            where = f"wiki/{lang}/{name}.md"
            if en.endswith(" (twice)"):
                problems.append(f"{where}: a second translation of wiki/{en[:-8]}.md")
                continue
            if en not in pages:
                problems.append(f"{where}: not a translation of any English page (its first line says which)")
                continue
            if not NAME.match(name):
                problems.append(f"{where}: a wiki page's name can't have spaces, _ first, or any of / \\ : * ? \" < > | # %")
            if name in taken:
                problems.append(f"{where}: another page is already called {name} (the wiki keeps every page in one folder)")
            taken.add(name)
            text = (WIKI / lang / f"{name}.md").read_text("utf-8")
            if not text.startswith(first_lines(lang, en, source_blob, all_names)):
                problems.append(f"{where}: its first lines aren't as written here: python3 scripts/wiki_translations.py --write")
            now = blob(WIKI / f"{en}.md")
            if source_blob != now:
                problems.append(f"{where}: behind wiki/{en}.md, which changed since (git diff {source_blob} {now}); "
                                f"translate what changed, then: python3 scripts/wiki_translations.py --done {lang} {en}")
        for en in pages:
            if en not in found:
                problems.append(f"wiki/{lang}: no translation of wiki/{en}.md")
    return problems


def write() -> int:
    all_names, changed = names(), 0
    for lang in LANGS:
        for en, (name, source_blob) in translations(lang).items():
            if not en or "(" in en:
                continue
            path = WIKI / lang / f"{name}.md"
            text = path.read_text("utf-8")
            new = first_lines(lang, en, source_blob, all_names) + FIRST.sub("", text, count=1)
            if new != text:
                path.write_text(new, "utf-8")
                changed += 1
    return changed


def done(lang: str, page: str) -> str:
    found = translations(lang).get(page)
    if not found:
        raise SystemExit(f"wiki/{lang} has no translation of {page}")
    path = WIKI / lang / f"{found[0]}.md"
    text = path.read_text("utf-8")
    path.write_text(first_lines(lang, page, blob(WIKI / f"{page}.md"), names()) + FIRST.sub("", text, count=1), "utf-8")
    return str(path.relative_to(WIKI.parent))


def main(argv: list[str]) -> int:
    if argv[:1] == ["--write"]:
        print(f"Wrote the first lines of {write()} pages.")
        return 0
    if argv[:1] == ["--done"] and len(argv) == 3 and argv[1] in LANGS:
        print(f"{done(argv[1], argv[2])} now says what wiki/{argv[2]}.md does.")
        return 0
    if argv[:1] == ["--diff"]:
        for lang in LANGS:
            for en, (name, source_blob) in translations(lang).items():
                if en in english() and source_blob != blob(WIKI / f"{en}.md"):
                    print(f"## wiki/{lang}/{name}.md, from wiki/{en}.md", flush=True)
                    subprocess.run(["git", "diff", source_blob, blob(WIKI / f"{en}.md")], cwd=REPO)
        return 0
    if argv:
        print(__doc__.strip().split("\n\n")[2])
        return 2
    problems = check()
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
