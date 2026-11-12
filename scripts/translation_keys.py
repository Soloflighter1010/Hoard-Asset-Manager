"""Find literal translation keys with Acorn and suggest old translations after English edits.

HTML is parsed before JavaScript; JSON script elements are not executable source.
Dynamic labels are covered by the existing browser-based translation check.
"""
from __future__ import annotations

import difflib
import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "hoard" / "web"


class Scripts(HTMLParser):
    """Collect executable inline scripts while preserving their line numbers."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts, self.current = [], None

    def handle_starttag(self, tag, attrs):
        """Ignore external scripts and data-only JSON elements."""
        attrs = dict(attrs)
        if tag == "script" and not attrs.get("src") and attrs.get("type", "") in ("", "text/javascript"):
            self.current = ["\n" * (self.getpos()[0] - 1)]

    def handle_data(self, data):
        """Keep JavaScript intact; HTMLParser does not interpret its strings."""
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        """Finish one script when its closing tag is reached."""
        if tag == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None


def calls(files=None) -> list[dict]:
    """Parse translation calls, failing clearly if development dependencies are missing."""
    inputs = []
    for path in files or [*sorted(p for p in WEB.glob("*.js") if not p.name.endswith(".generated.js")),
                          *sorted((ROOT / "ui").glob("*.svelte")), WEB / "library.html", WEB / "downloads.html"]:
        source = path.read_text("utf-8")
        if path.suffix == ".html":
            parser = Scripts()
            parser.feed(source)
            sources = parser.scripts
        else:
            sources = [source]
        inputs.extend({"source": text, "file": str(path)} for text in sources)
    try:
        result = subprocess.run(["node", str(ROOT / "scripts" / "i18n_keys.mjs")], input=json.dumps(inputs),
                                text=True, encoding="utf-8", capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise RuntimeError(f"Translation parsing needs Node.js 20+ and npm ci.\n{detail}") from exc
    return json.loads(result.stdout)


def missing_message(missing: list[str], catalog: dict, used: set[str]) -> str:
    """Name likely replaced keys and their existing translations; never move them automatically."""
    old = sorted(set(catalog) - used)
    lines = ["tr() words with no translation:"]
    for key in missing:
        lines.append(f"  {key!r}")
        for previous in difflib.get_close_matches(key, old, n=2, cutoff=0.65):
            lines.append(f"    Possibly replaces {previous!r}: {catalog[previous]!r}")
    return "\n".join(lines)
