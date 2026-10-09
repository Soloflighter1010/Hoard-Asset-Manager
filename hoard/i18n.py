"""The languages Hoard's pages come in (Settings, Appearance): English, as they're written, and the catalogs in
hoard/web/i18n/ (<language>.json: the English as it shows, to its translation). The server puts the chosen
language's catalog into each page as it serves it, and the page translates itself as it's drawn (web/shared.js),
Hoard's own messages included. Match my computer follows the language the window asks for (Accept-Language).
Standard library only.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .paths import PACKAGE

LANGUAGES = {"en": "English", "ja": "日本語", "ko": "한국어"}   # each in its own words, as Settings lists them
SETTINGS = ("system",) + tuple(LANGUAGES)
CATALOGS = PACKAGE / "web" / "i18n"
# each catalog's file, fixed here: a language a window asks for only ever picks one of these, never names a path
CATALOG_FILES = {code: CATALOGS / f"{code}.json" for code in LANGUAGES if code != "en"}


def setting(value) -> str:
    """The language setting as it's kept: system (match my computer) or a language Hoard has."""
    return value if isinstance(value, str) and value in SETTINGS else "system"


def from_header(accept_language: str | None) -> str:
    """The first language Hoard has among those the window asks for, by their order of preference; English if none."""
    asked = []
    for i, part in enumerate((accept_language or "").split(",")[:20]):
        tag, _, params = part.strip().partition(";")
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.strip().partition("=")
            if k == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        code = tag.strip().lower().split("-")[0]
        if code and q > 0:
            asked.append((-q, i, code))
    for _, _, code in sorted(asked):
        for known in LANGUAGES:   # Hoard's own word for it, not the window's
            if code == known:
                return known
    return "en"


def language(cfg: dict | None, accept_language: str | None = None) -> str:
    """The language a page is shown in: the one chosen in Settings, or the window's own."""
    d = (cfg or {}).get("display") if isinstance((cfg or {}).get("display"), dict) else {}
    chosen = setting(d.get("language"))
    return from_header(accept_language) if chosen == "system" else chosen


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict:
    """A language's catalog: {English: translation}. English (or a language without a file) has none."""
    path = CATALOG_FILES.get(lang)
    if path is None:   # English, or a language Hoard hasn't a catalog for
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v and not k.startswith("//")}


def say(lang: str, english: str, *values) -> str:
    """Hoard's own words in a language, for what isn't on a page (a notification from the system): the catalog's
    translation of the English, with {0}, {1} filled in; the English when there's none."""
    text = catalog(lang).get(english, english)
    return re.sub(r"\{(\d+)\}", lambda m: str(values[int(m.group(1))]) if int(m.group(1)) < len(values) else m.group(0), text)


def page_script(lang: str) -> str:
    """The catalog as the page reads it: JSON in a script element that's never run (type application/json), with
    nothing in it that could end the element early."""
    text = json.dumps(catalog(lang), ensure_ascii=False, separators=(",", ":"))
    return '<script type="application/json" id="i18n">' + text.replace("<", "\\u003c") + "</script>\n"
