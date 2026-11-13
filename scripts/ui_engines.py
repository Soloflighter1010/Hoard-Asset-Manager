"""Hoard's Svelte parts (ui/: the pop-ups and Look inside) in the engines the desktop apps run them in: WebKit (the
Mac app's, and the Linux apps' WebKitGTK) and Edge's Chromium (WebView2's, on Windows). The tests run in Playwright's
Chromium; this opens Hoard's page in another engine, checks each pop-up answers as it should, and times them.

    python scripts/ui_engines.py webkit          # Playwright's WebKit
    python scripts/ui_engines.py msedge          # the Edge installed on this computer
    python scripts/ui_engines.py chromium        # Playwright's Chromium, to compare

It prints a Markdown table (the engines workflow adds it to the run's summary) and exits 1 if a pop-up misbehaves.
Nothing of yours is used: Hoard runs on a made-up library in a folder of its own, deleted afterwards."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

TEMP = tempfile.TemporaryDirectory()
os.environ["HOARD_DATA_DIR"] = str(Path(TEMP.name) / "data")   # (before Hoard is imported: never your own)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from playwright.sync_api import sync_playwright  # noqa: E402

from hoard import config, library, server  # noqa: E402

ROUNDS = 40
# A pop-up opened and closed ROUNDS times: the time its call takes to make it and show it (the component mounted, its
# styles in, the dialog open, all before the call returns), the first time apart (the component's first mount and
# styles), then the middle and the 90th percentile of the rest; and to its next frame, once, after the first.
TIMING = """async rounds => {
  const times = [];
  let painted = 0;
  for (let i = 0; i < rounds; i++) {
    const began = performance.now();
    const answer = askName('Name the new set', 'Winter');
    times.push(performance.now() - began);
    if (i === 1) painted = await new Promise(r => requestAnimationFrame(() => r(performance.now() - began)));
    document.querySelector('dialog.hd button[value=no]').click();
    await answer;
    await new Promise(r => setTimeout(r, 0));
  }
  const rest = times.slice(1).sort((a, b) => a - b);
  return { first: times[0], median: rest[Math.floor(rest.length / 2)], p90: rest[Math.floor(rest.length * .9)], painted };
}"""
# What each pop-up answers, in this engine: [what, expected, got]
CHECKS = """async () => {
  const out = [], wait = ms => new Promise(r => setTimeout(r, ms));
  const shown = sel => new Promise(r => { const t = setInterval(() => { const d = document.querySelector(sel); if (d && d.open) { clearInterval(t); r(d); } }, 10); });
  let d, a;
  a = ask("Delete 2 backups? They can't be restored.", 'Delete', true); d = await shown('#askDialog');
  out.push(['a question: its title', 'Delete 2 backups?', d.querySelector('h2').textContent]);
  out.push(['a question: Cancel first', 'Cancel', document.activeElement.textContent]);
  d.querySelector('button[value=yes]').click(); out.push(['a question: yes', true, await a]);
  a = ask('Clear the list of finished tasks?'); d = await shown('#askDialog');
  d.dispatchEvent(new Event('cancel')); d.close(); out.push(['a question: Escape', false, await a]);
  a = askName('Name the new set'); d = await shown('dialog.hd-text');
  const box = d.querySelector('#askName'); box.value = '  Fox base  '; box.dispatchEvent(new Event('input'));
  box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true })); await wait(50);
  out.push(['a name: not while composing', true, d.open]);
  box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); out.push(['a name: Enter', 'Fox base', await a]);
  a = askName('Add a tag to the selected', '', { suggest: [{ name: 'winter', count: 3 }, { name: 'wings', count: 1 }], prefix: '#' });
  d = await shown('dialog.hd-text');
  out.push(['a tag: your tags', '#winter3,#wings1', [...d.querySelectorAll('.hd-chip')].map(c => c.textContent).join(',')]);
  d.querySelector('.hd-chip').click(); out.push(['a tag: chosen', 'winter', await a]);
  a = HoardUI.dialogs.open({ kind: 'pick', title: 'Add to which set?', find: 'Find a set', tr, norm,
    groups: [{ title: 'Your sets', items: [{ value: 'a', name: 'Fox base', letters: 'FB', hue: 10 }, { value: 'b', name: 'Winter outfit', letters: 'WO', hue: 200 }] }] });
  d = await shown('dialog.hd-pick');
  const find = d.querySelector('input[type=search]'); find.value = 'winter'; find.dispatchEvent(new Event('input')); await wait(50);
  out.push(['a choice: found', 'Winter outfit', [...d.querySelectorAll('.hd-name')].map(n => n.textContent).join(',')]);
  find.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); out.push(['a choice: Enter', 'b', await a]);
  await wait(50);
  out.push(['all gone afterwards', 0, document.querySelectorAll('dialog.hd').length]);
  return out;
}"""


def main(engine: str) -> int:
    """Check and time the pop-ups in this engine; 0 when they all answered as they should."""
    root = Path(TEMP.name) / "downloads"
    root.mkdir(parents=True)
    srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
    with srv.lib.lock:   # in memory only
        srv.lib.data["items"] = [library.item("booth", "1", name="Rusk", creator="Kitsu Studio")]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bundle = (REPO / "hoard" / "web" / "ui.generated.js").read_text("utf-8")
    try:
        with sync_playwright() as p:
            browser = (p.webkit.launch() if engine == "webkit" else
                       p.chromium.launch(channel="msedge") if engine == "msedge" else p.chromium.launch())
            page = browser.new_page()
            # the bundle on its own, read and run once in an empty page (as the page does, nothing cached)
            page.goto("about:blank")
            parse = page.evaluate("src => { const s = performance.now(); (0, eval)(src); return performance.now() - s; }", bundle)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.entry_url())
            page.wait_for_selector("#grid .slot[data-key]")
            timing = page.evaluate(TIMING, ROUNDS)
            checks = page.evaluate(CHECKS)
            version = browser.version
            browser.close()
    finally:
        srv.shutdown()
        srv.server_close()
    wrong = [c for c in checks if c[1] != c[2]] + [["no errors on the page", [], errors]] * bool(errors)
    print(f"### {engine} {version}\n")
    print("| | ms |\n| --- | --- |")
    print(f"| Bundle read and run ({len(bundle.encode()):,} bytes) | {parse:.1f} |")
    print(f"| A pop-up made and shown, the first time | {timing['first']:.1f} |")
    print(f"| A pop-up made and shown, middle of {ROUNDS - 1} | {timing['median']:.1f} |")
    print(f"| A pop-up made and shown, 90th percentile | {timing['p90']:.1f} |")
    print(f"| To its next frame on screen | {timing['painted']:.1f} |\n")
    print(f"Checks: all {len(checks)} as they should be." if not wrong else "Checks that failed:")
    for what, want, got in wrong:
        print(f"- {what}: expected {want!r}, got {got!r}")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "chromium"))
