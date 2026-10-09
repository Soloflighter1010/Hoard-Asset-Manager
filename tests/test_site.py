"""Hoard's website (site/, issue #27), deployed to GitHub Pages in front of the VCC listing by build-listing.yml:
complete, loading nothing from elsewhere, pointing at the real listing and downloads, and laid out on deploy so
that VCC's addresses keep working."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
WORKFLOW = REPO / ".github" / "workflows" / "build-listing.yml"
RELEASES = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest"

sys.path.insert(0, str(REPO / "scripts"))
import build_site_changelog as changelog  # noqa: E402
import build_site_docs as docs  # noqa: E402
import site_chrome  # noqa: E402


def built_site() -> Path:
    """The site as deployed: site/ with its What's new page built from CHANGELOG.md, and the docs from wiki/."""
    out = Path(tempfile.mkdtemp()) / "site"
    shutil.copytree(SITE, out)
    changelog.main([str(out / "changelog.html")])
    docs.build(out / "docs")
    return out


PAGES = ("index.html", "testers.html", "changelog.html", "credits.html", "how-it-works.html", "trust.html", "ai.html")


def every_page(site: Path) -> list[str]:
    """Every page of the built site, the docs' too, by its path in the site."""
    return list(PAGES) + sorted(f"docs/{p.name}" for p in (site / "docs").glob("*.html"))


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids, self.external_loads = [], set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src", "srcset"):
            v = a.get(key)
            if not v:
                continue
            self.refs.append((tag, key, v))
            loads = tag in ("script", "img", "source") or (tag == "link" and a.get("rel") in ("stylesheet", "icon", "preload"))
            if loads and re.match(r"https?://", v):
                self.external_loads.append(v)


class TheSite(unittest.TestCase):

    def setUp(self):
        self.html = (SITE / "index.html").read_text("utf-8")
        self.page = Refs()
        self.page.feed(self.html)

    def test_everything_it_uses_is_here(self):
        import posixpath
        site = built_site()
        ids = {}
        for name in every_page(site):
            refs = Refs()
            refs.feed((site / name).read_text("utf-8"))
            ids[name] = refs.ids
        for name in every_page(site):
            page = Refs()
            page.feed((site / name).read_text("utf-8"))
            for tag, key, value in page.refs:
                if re.match(r"(https?|vcc|mailto):", value):
                    continue
                if value.startswith("#"):
                    self.assertIn(value[1:], page.ids, f"{name}: {value}")
                    continue
                path, _, anchor = value.partition("#")
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), path)) if path else name
                if target == "vcc":
                    continue   # the listing's page, put at vcc/ on deploy
                if target in (".", "docs") or path.endswith("/"):
                    target = posixpath.join("" if target == "." else target, "index.html")
                self.assertTrue((site / target).is_file(), f"{name}: {value}")
                if anchor and target in ids:   # a section of a page
                    self.assertIn(anchor, ids[target], f"{name}: {value}")
            self.assertEqual(page.external_loads, [], f"{name} loads nothing from other sites")
        css = (SITE / "styles.css").read_text("utf-8")
        for url in re.findall(r"url\(([^)]+)\)", css):
            self.assertTrue((SITE / url.strip("\"'")).is_file(), url)

    def test_it_loads_nothing_from_other_sites(self):
        self.assertEqual(self.page.external_loads, [])
        css = (SITE / "styles.css").read_text("utf-8")
        self.assertNotRegex(css, r"url\(\s*[\"']?https?://|@import")
        js = (SITE / "site.js").read_text("utf-8")
        self.assertEqual(set(re.findall(r"fetch\([`'\"]([^`'\"]*)", js)),
                         {"https://api.github.com/repos/${REPO}/releases/latest", "search.json"},
                         "only asks GitHub which files the latest release has (and the docs their own search list)")
        self.assertNotIn("innerHTML", js, "nothing from GitHub's answer becomes page markup")

    def test_the_glow_is_the_apps(self):
        """The app's glow behind the page: every store's colour, as the app has them, decorative, and still for
        anyone who asks their system for less motion."""
        css = (SITE / "styles.css").read_text("utf-8")
        app = (REPO / "hoard" / "web" / "library.html").read_text("utf-8")
        for store in ("booth", "gumroad", "jinxxy", "payhip", "itch"):
            standard = "\n".join(re.findall(r"^\s*:root \{.*?\n\s*\}", app, re.M | re.S))   # not the colour-blind set
            for colour in re.findall(rf"--{store}: (#[0-9A-F]{{6}})", standard):
                self.assertIn(f"--{store}: {colour}", css, f"{store}'s colour matches the app's")
            self.assertIn(f"var(--{store}) var(--glow)", css)
        self.assertIn('<div class="glow" aria-hidden="true">', self.html)
        self.assertRegex(css, r"@media \(prefers-reduced-motion: reduce\) \{ \.glow-in \{ animation: none; \} \}")
        self.assertRegex(css, r"\.glow \{[^}]*pointer-events: none")

    def test_downloads_work_without_its_script(self):
        buttons = re.findall(r'<a class="button[^"]*" data-file="([^"]+)" href="([^"]+)"', self.html)
        self.assertEqual({f for f, _ in buttons}, {"Hoard-Setup-", "-macos-apple-silicon.pkg", "-macos-intel.pkg", "-linux-x86_64.flatpak"})
        self.assertTrue(all(h == RELEASES for _, h in buttons), "each opens the latest release until the script finds its file")

    def test_it_adds_the_real_listing(self):
        listing = json.loads((REPO / "source.json").read_text("utf-8"))["url"]
        self.assertIn(f'value="{listing}"', self.html)
        from urllib.parse import quote
        self.assertIn(f'href="vcc://vpm/addRepo?url={quote(listing, safe="")}"', self.html)

    def test_its_fonts_and_pictures_are_small_and_licensed(self):
        for f in SITE.glob("fonts/*.woff2"):
            self.assertLess(f.stat().st_size, 100_000, f"{f.name}: cut down to the characters the site uses")
        self.assertTrue((SITE / "fonts" / "DelaGothicOne-OFL.txt").is_file())
        self.assertTrue((SITE / "fonts" / "ZenMaruGothic-OFL.txt").is_file())
        for f in SITE.glob("img/*.webp"):
            self.assertLess(f.stat().st_size, 300_000, f.name)
        self.assertIn('media="(prefers-color-scheme: light)"', self.html, "the screenshot matches your light or dark")

    def test_a_shared_link_shows_a_picture(self):
        """A link to the site shared on Discord, X and the like showed no picture: every page names one, by its full
        address (embeds don't follow relative ones), and it's here, the size those sites expect, and small."""
        def jpeg_size(data: bytes):
            """(width, height) from a JPEG's frame header, or None if it isn't a JPEG."""
            if data[:2] != b"\xff\xd8":
                return None
            i = 2
            while i + 9 < len(data):
                marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
                i += 2 + length
            return None
        base = "https://soloflighter1010.github.io/Hoard-Asset-Manager/"
        site = built_site()
        cards = set()
        for name in ("index.html", "testers.html", "changelog.html", "credits.html", "how-it-works.html", "trust.html", "ai.html",
                     "docs/index.html", "docs/Settings.html"):
            html = (site / name).read_text("utf-8")
            image = re.search(r'<meta property="og:image" content="([^"]+)">', html)
            self.assertIsNotNone(image, f"{name}: no og:image")
            self.assertTrue(image.group(1).startswith(base), f"{name}: the picture's full address")
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', html, name)
            for tag in ("og:title", "og:description", "og:url", "og:image:alt"):
                self.assertIn(f'<meta property="{tag}" content="', html, f"{name}: {tag}")
            picture = SITE / image.group(1)[len(base):]
            self.assertTrue(picture.is_file(), image.group(1))
            self.assertLess(picture.stat().st_size, 300_000)
            self.assertEqual(jpeg_size(picture.read_bytes()), (1200, 630), "a JPEG every site shows, at 1.91:1")
            self.assertIn('<meta name="theme-color" content="#F0B429">', html, f"{name}: the embed's edge in Hoard's gold")
            cards.add(image.group(1))
        self.assertEqual(len(cards), 8, "each page its own card, with its name on it (the docs share one)")
        self.assertEqual({p.name for p in SITE.glob("img/social*.jpg")}, {c.rsplit("/", 1)[1] for c in cards},
                         "scripts/make_social_cards.py draws just the cards the pages show")

    def test_the_chosen_store_tab_has_no_line_on_top(self):
        """The app took the coloured line off the chosen tab's top (with the Local tab); the site follows."""
        self.assertNotRegex((SITE / "styles.css").read_text("utf-8"), r'\.seg button\[aria-checked="true"\]::after')

    def test_it_works_on_a_phone(self):
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', self.html)
        self.assertIn("@media (max-width: 760px)", (SITE / "styles.css").read_text("utf-8"))


class TheOtherPages(unittest.TestCase):

    def test_every_tester_is_thanked(self):
        page = (SITE / "testers.html").read_text("utf-8")
        names = re.findall(r'<li class="tester (\w+)">([^<]+)</li>', page)
        self.assertEqual(len(names), 13)
        self.assertIn(("booth", "puzzlella"), names)
        self.assertIn("cheapthrill", [n for _, n in names])
        self.assertIn(("gumroad", "petra.synth"), names)
        self.assertIn(("jinxxy", "xkittygoddessx"), names)
        self.assertTrue({c for c, _ in names} <= {"booth", "gumroad", "jinxxy", "payhip", "itch"})

    def test_every_page_has_the_same_header_and_the_glow(self):
        site = built_site()
        for name in ("index.html", "testers.html", "changelog.html", "credits.html", "how-it-works.html", "trust.html", "ai.html"):
            page = (site / name).read_text("utf-8")
            self.assertIn('<div class="glow" aria-hidden="true">', page, name)
            self.assertIn('href="changelog.html"', page, name)
            self.assertIn('href="testers.html"', page, name)
            self.assertIn('href="how-it-works.html"', page, name)
            self.assertIn('href="trust.html"', page, name)
            self.assertIn('href="ai.html"', page, f"{name}: the AI disclosure, from every page")
            self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', page, name)

    def test_it_looks_like_the_app(self):
        """Every page has the app's bar (its logo, the pages as tabs, GitHub and a gold Download) and its footer, the
        same everywhere (scripts/site_chrome.py) but for which tab is the page you're on; the docs', one folder
        down, with their links going up one."""
        site = built_site()
        self.assertEqual(site_chrome.main([]), 0, "site/*.html carry scripts/site_chrome.py's bar and footer")
        for name in every_page(site):
            page = (site / name).read_text("utf-8")
            bar = re.search(r'<header class="bar">.*?</header>', page, re.S).group(0)
            foot = re.search(r'<footer class="foot">.*?</footer>', page, re.S).group(0)
            if name.startswith("docs/"):
                self.assertEqual(bar, site_chrome.header("docs/", up="../"), name)
                self.assertEqual(foot, site_chrome.footer(up="../"), name)
                self.assertIn('<a href="../docs/" aria-current="page">Docs</a>', bar)
            else:
                self.assertEqual(bar, site_chrome.header(site_chrome.CURRENT.get(name)), name)
                self.assertIn(foot, (site_chrome.footer(), site_chrome.footer(
                    ' This page is built from <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/CHANGELOG.md">CHANGELOG.md</a>.')), name)
            self.assertIn('class="boxes"', bar, f"{name}: the app's logo, whose boxes move")
        css = (SITE / "styles.css").read_text("utf-8")
        self.assertIn(".seg button[aria-checked=\"true\"]", css, "the store tabs are the app's folder tabs")
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)

    def test_the_docs_are_the_wikis_pages(self):
        """Every wiki page is a docs page, with the sidebar, a link on each heading, and search; raw HTML (Home's
        logo) stays out, and nothing in a page becomes markup of its own."""
        site = built_site()
        wiki = {p.stem for p in (REPO / "wiki").glob("*.md") if not p.name.startswith("_")}
        built = {p.stem for p in (site / "docs").glob("*.html")}
        self.assertEqual(built, (wiki - {"Home"}) | {"index"})
        settings = (site / "docs" / "Settings.html").read_text("utf-8")
        self.assertIn('<a href="Settings.html" aria-current="page">Settings</a>', settings, "the sidebar marks the page")
        self.assertIn('<div class="table"><table>', settings)
        self.assertRegex(settings, r'<h2 id="settings-only-in-configjson">Settings only in config\.json<a class="anchor"')
        cli = (site / "docs" / "Command-Line.html").read_text("utf-8")
        self.assertIn("<pre><code>hoard-cli sync --dry-run</code></pre>", cli)
        self.assertIn("<td><code>login &lt;store&gt;</code></td>", cli, "code in a table, escaped")
        home = (site / "docs" / "index.html").read_text("utf-8")
        self.assertNotIn("<picture>", home, "the wiki's raw HTML isn't the site's")
        self.assertIn('href="Installing-Hoard.html"', home, "wiki links go to the docs page")
        self.assertIn("<title>Hoard docs</title>", home, "the docs' home is named once")
        self.assertIn("<title>Settings · Hoard docs</title>", settings)
        index = json.loads((site / "docs" / "search.json").read_text("utf-8"))
        self.assertTrue(any(s["page"] == "Stores.html" and s["anchor"] == "payhip" for s in index))

    def test_a_broken_link_stops_the_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            wiki.mkdir()
            (wiki / "Home.md").write_text("See [Settings](Settings#nowhere).\n\n<script>alert(1)</script>\n\n"
                                          "A **<b>bold</b>** [link](javascript:alert(1)).\n", "utf-8")
            (wiki / "Settings.md").write_text("## Somewhere\n", "utf-8")
            with self.assertRaises(docs.BrokenLink):
                docs.build(Path(tmp) / "out", wiki)
            (wiki / "Home.md").write_text("See [Settings](Settings#somewhere).\n\n<script>alert(1)</script>\n\n"
                                          "A **<b>bold</b>** [link](javascript:alert(1)).\n", "utf-8")
            with self.assertRaises(docs.BrokenLink, msg="only pages, headings and https addresses"):
                docs.build(Path(tmp) / "out", wiki)
            (wiki / "Home.md").write_text("See [Settings](Settings#somewhere).\n\n<script>alert(1)</script>\n\n"
                                          "A **<b>bold</b>**.\n", "utf-8")
            docs.build(Path(tmp) / "out", wiki)
            page = (Path(tmp) / "out" / "index.html").read_text("utf-8")
            self.assertIn('<a href="Settings.html#somewhere">Settings</a>', page)
            self.assertNotIn("<script>alert", page)
            self.assertIn("<strong>&lt;b&gt;bold&lt;/b&gt;</strong>", page)

    def test_the_store_tabs_say_what_hoard_does_on_each(self):
        html = (SITE / "index.html").read_text("utf-8")
        tabs = re.findall(r'role="radio" aria-checked="(true|false)" data-store="(\w*)"', html)
        self.assertEqual([s for _, s in tabs], ["", "booth", "gumroad", "jinxxy", "payhip", "itch"])
        self.assertEqual([c for c, _ in tabs].count("true"), 1, "Everything, to start with")
        notes = re.findall(r'<p data-for="(\w*)">', html)
        self.assertEqual(sorted(notes), sorted(s for _, s in tabs), "each store has its line, shown when it's chosen")
        self.assertIn(".js .store-notes p:not(.here) { display: none; }", (SITE / "styles.css").read_text("utf-8"),
                      "without the script, every store's line shows")

    def test_how_it_works_covers_every_store_and_step(self):
        page = (SITE / "how-it-works.html").read_text("utf-8")
        for store in ("booth", "gumroad", "jinxxy", "payhip", "itch"):
            self.assertIn(f'class="store {store}"', page)
        steps = re.findall(r"<li>\s*<h3>([^<]+)</h3>", page)
        self.assertEqual(len(steps), 6, steps)
        self.assertIn('aria-current="page"', page)

    def test_trust_and_the_ai_disclosure_link_their_sources(self):
        """Each point on How you can trust Hoard, and on the AI disclosure, says where to check it."""
        for name, points in (("trust.html", 8), ("ai.html", 6)):
            page = (SITE / name).read_text("utf-8")
            cards = re.findall(r"<li>\s*<h3>.*?</li>", page, re.S)
            self.assertEqual(len(cards), points, name)
            for c in cards:
                self.assertIn('class="sources"><a href="', c, f"{name}: every point links where to check it")
        trust = (SITE / "trust.html").read_text("utf-8")
        for doc in ("SECURITY.md", "PRIVACY.md", "release.yml", "check.yml", "LICENSE", "ai.html"):
            self.assertIn(doc, trust)

    def test_the_changelog_has_every_release_newest_first(self):
        md = (REPO / "CHANGELOG.md").read_text("utf-8")
        versions = [v for v in re.findall(r"^## (.+)$", md, re.M) if "-beta." not in v]   # betas: on GitHub only
        page = changelog.page(md, {})
        self.assertEqual(re.findall(r'<h2><a href="#[^"]+">([^<]+)</a></h2>', page), versions)
        self.assertEqual(page.count('class="latest-badge"'), 1)
        self.assertLess(page.index("latest-badge"), page.index(f">{versions[1]}<"), "the newest is the one marked")
        self.assertNotIn("<time", page, "no dates without GitHub's list")

    def test_dates_come_from_the_releases(self):
        md = "## 2.11.1\n\n- One.\n\n## 2.11.0\n\n- Two.\n"
        page = changelog.page(md, {"v2.11.1": "2026-10-01T09:15:00Z"})
        self.assertIn('<time datetime="2026-10-01">October 1, 2026</time>', page)
        self.assertEqual(page.count("<time"), 1, "a release GitHub doesn't list has no date")

    def test_nothing_in_the_changelog_becomes_markup(self):
        md = ("## 9.9.9\n\nA <script>alert(1)</script> & **bold** `<b>code</b>` [link](https://example.com) "
              "[bad](javascript:alert(1))\n")
        page = changelog.page(md, {})
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; <strong>bold</strong>", page)
        self.assertIn("<code>&lt;b&gt;code&lt;/b&gt;</code>", page)
        self.assertIn('<a href="https://example.com">link</a>', page)
        self.assertNotIn('href="javascript:', page)

    def test_bold_around_code_and_bare_addresses(self):
        """As GitHub shows them: bold that contains code (2.9.2's install folder showed its asterisks), and a bare
        https address as a link, without the full stop after it."""
        line = changelog.inline("**Installs into `%LOCALAPPDATA%\\Programs\\Hoard` (#21),** see https://example.com/a.")
        self.assertEqual(line, "<strong>Installs into <code>%LOCALAPPDATA%\\Programs\\Hoard</code> (#21),</strong> see "
                               '<a href="https://example.com/a">https://example.com/a</a>.')
        self.assertEqual(changelog.inline("[the wiki](https://example.com/w)"), '<a href="https://example.com/w">the wiki</a>')
        self.assertEqual(changelog.inline("`**not bold**` and `<b>`"), "<code>**not bold**</code> and <code>&lt;b&gt;</code>")
        self.assertEqual(changelog.inline("a ` stray"), "a ` stray")
        # an address in a link's text stays text: a link inside a link isn't HTML
        self.assertEqual(changelog.inline("[see https://example.com/d](https://github.com/x)"),
                         '<a href="https://github.com/x">see https://example.com/d</a>')
        # the website, What's new and the updater agree on what's a beta
        from hoard import updater, versions
        for v in ("3.1.0-beta.2", "3.1.0", "3.1.0-beta.rc", "3.1.0-beta.1 (hotfix)"):
            self.assertEqual(changelog.is_beta(v), updater.is_beta(v), v)
            self.assertIs(changelog.is_beta, versions.is_beta)
        whole = changelog.page((REPO / "CHANGELOG.md").read_text("utf-8"), {})
        self.assertNotIn("**", re.sub(r"<code>.*?</code>", "", whole, flags=re.S), "every bold in the changelog closes")

    def test_lists_nest_and_carry_on_over_lines(self):
        md = "## 1.0.0\n\n- First\n  carried on.\n  - Inside\n- Second\n\nAfter.\n\n### Fixed\n\n- Third\n"
        body = changelog.blocks(md.split("\n")[2:])
        flat = re.sub(r"\s+", " ", body)
        self.assertIn("<ul> <li> First carried on. <ul> <li> Inside </li></ul> </li> <li> Second </li></ul>", flat)
        self.assertIn("<p>After.</p> <h4>Fixed</h4> <ul> <li> Third </li></ul>", flat)
        built = (built_site() / "changelog.html").read_text("utf-8")
        self.assertEqual(built.count("<ul>"), built.count("</ul>"))
        self.assertEqual(len(re.findall(r"<li[ >]", built)), built.count("</li>"))


class TheThreeZeroChangelog(unittest.TestCase):
    """3.0.0's changelog (the betas folded into one) uses only what the What's new page can show."""

    def test_3_0_0_reads_on_the_whats_new_page(self):
        text = (REPO / "CHANGELOG.md").read_text("utf-8")
        body = text.split("## 3.0.0\n", 1)[1].split("\n## ", 1)[0]
        page = changelog.page("## 3.0.0\n" + body, {})
        plain = re.sub(r"<code>.*?</code>", "", page, flags=re.S)
        self.assertNotIn("**", plain, "every bold closes")
        self.assertNotIn("`", plain, "every code span closes")
        self.assertEqual(page.count("<ul>"), page.count("</ul>"))
        self.assertEqual(len(re.findall(r"<li[ >]", page)), page.count("</li>"))
        self.assertNotRegex(body, r"^\s*(\d+\.|\||>|```)", "no numbered lists, tables, quotes or code blocks")
        for heading in ("Hoard on every computer", "Signing in, your way", "Downloads you can leave running",
                        "Upgrading from 2.8"):
            self.assertIn(f"<h4>{heading}</h4>", page)
        self.assertNotIn("## 3.0.0-beta", text, "the betas are folded into 3.0.0")


class TheDeploy(unittest.TestCase):

    def setUp(self):
        self.text = WORKFLOW.read_text("utf-8")

    def test_it_deploys_when_the_site_changes(self):
        self.assertRegex(self.text, r'push:\n\s+branches: \[main\]\n\s+paths: \[[^\]]*"site/\*\*"')
        paths = re.search(r"paths: \[([^\]]*)\]", self.text).group(1)
        self.assertIn('"CHANGELOG.md"', paths, "and when the changelog does, for its What's new page")
        self.assertIn('"scripts/build_site_changelog.py"', paths)
        for docs_source in ('"wiki/**"', '"scripts/build_site_docs.py"', '"scripts/site_chrome.py"'):
            self.assertIn(docs_source, paths, "and when the docs, or every page's bar, change")
        self.assertIn('python3 scripts/build_site_docs.py "${{ env.listPublishDirectory }}/docs"', self.text)
        for renderer in ('"hoard/changelog.py"', '"hoard/versions.py"'):   # the page is made by these too
            self.assertIn(renderer, paths)

    def test_the_listing_build_waits_out_a_release_being_made(self):
        """Hoard for Unity 0.3.0's listing builds failed twice ("Could not find valid zip file"): each ran while the
        release was still being made. The build is tried again, a few times, before it fails."""
        step = self.text.split("- name: Build the listing from every release", 1)[1].split("- name:", 1)[0]
        self.assertIn("for attempt in 1 2 3 4; do", step)
        self.assertIn("sleep 30", step)
        self.assertIn("exit 0", step, "it stops at the first success")
        self.assertRegex(step, r"echo \"::error::[^\n]*\"\n\s+exit 1", "and fails when every try fails")
        bash = shutil.which("bash")
        if not bash or os.name == "nt":
            self.skipTest("the step runs on Linux (needs bash)")
        script = step.split("run: |", 1)[1]
        script = "\n".join(line[10:] for line in script.splitlines() if line.strip())
        script = script.replace("${{ env.pathToCi }}", "./ci").replace("${{ env.listPublishDirectory }}", "Website") \
                       .replace("${{ github.repository_owner }}", "owner").replace("sleep 30", "sleep 0")
        for fails, ok in ((0, True), (2, True), (4, False)):
            work = Path(tempfile.mkdtemp())
            (work / "ci").mkdir()
            builder = work / "ci" / "build.cmd"   # fails its first `fails` runs, then works
            builder.write_text(f'#!/bin/bash\nn=$(cat count 2>/dev/null || echo 0); echo $((n+1)) > count\n[ "$n" -ge {fails} ]\n')
            builder.chmod(0o755)
            run = subprocess.run([bash, "-e", "-c", script], cwd=work, capture_output=True, text=True,
                                 env={**os.environ, "GITHUB_WORKSPACE": str(work), "PACKAGE_NAME": "p"})
            self.assertEqual(run.returncode == 0, ok, (fails, run.stdout, run.stderr))
            self.assertEqual(int((work / "count").read_text()), min(fails + 1, 4), "tries until it works, at most 4")

    def test_it_builds_the_whats_new_page(self):
        step = self.text.split("- name: Build the What's new page from the changelog", 1)[1].split("- uses:", 1)[0]
        self.assertIn("scripts/build_site_changelog.py", step)
        self.assertIn("--json tagName,publishedAt", step)
        self.assertIn('|| echo "[]"', step, "a failed lookup still builds the page, without dates")
        self.assertLess(self.text.index("Put Hoard's website in front"), self.text.index("Build the What's new page"))

    def test_the_listing_keeps_its_addresses(self):
        """The deploy step, run on a copy of the listing's files: the site takes the root, the listing's page moves
        to vcc/ with what it loads, and index.json, vpm/index.json and the banner stay where VCC finds them."""
        step = self.text.split("- name: Put Hoard's website in front, and the listing's page at vcc/", 1)[1]
        script = step.split("run: |", 1)[1].split("\n\n", 1)[0]
        script = "\n".join(line[10:] for line in script.splitlines() if line.strip())
        work = Path(tempfile.mkdtemp())
        pub = work / "Website"
        shutil.copytree(REPO / "Website", pub)
        (pub / "index.html").write_text("<p>rendered listing</p>")   # as the listing builder leaves it
        (pub / "index.json").write_text("{}")
        (pub / "vpm").mkdir()
        (pub / "vpm" / "index.json").write_text("{}")
        shutil.copytree(SITE, work / "site")
        bash = shutil.which("bash")
        if not bash or os.name == "nt":
            self.skipTest("the step runs on Linux (needs bash)")
        run = subprocess.run([bash, "-e", "-c", script], cwd=pub, env={**os.environ, "GITHUB_WORKSPACE": str(work)},
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((pub / "index.html").read_text("utf-8"), (SITE / "index.html").read_text("utf-8"))
        self.assertEqual((pub / "vcc" / "index.html").read_text(), "<p>rendered listing</p>")
        for f in ("app.js", "styles.css", "favicon.ico", "banner.png", "vendor"):
            self.assertTrue((pub / "vcc" / f).exists(), f)
        for f in ("index.json", "vpm/index.json", "banner.png", "site.js", "img/library-dark.webp"):
            self.assertTrue((pub / f).exists(), f)



def _browser() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:  # no Playwright browser here
        return False


@unittest.skipUnless(_browser(), "needs Playwright's Chromium (python -m playwright install chromium)")
class InABrowser(unittest.TestCase):
    """The front page's store tabs, as the app's: choosing one raises it and says what Hoard does there; and the
    things to find, as in the app. Opened from disk, so nothing is fetched (the download buttons keep their links)."""

    def test_the_store_tabs_and_things_to_find(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.route("https://**", lambda route: route.abort())   # (GitHub's list of downloads: not from a test)
            page.goto((SITE / "index.html").as_uri())
            visible = lambda: page.eval_on_selector_all(".store-notes p", "ps => ps.filter(p => p.offsetParent).map(p => p.dataset.for)")  # noqa: E731
            page.wait_for_function("() => document.documentElement.classList.contains('js')")
            self.assertEqual(visible(), [""], "Everything, to start with")
            page.click('.seg [data-store="payhip"]')
            self.assertEqual(visible(), ["payhip"])
            self.assertEqual(page.get_attribute('.seg [data-store="payhip"]', "aria-checked"), "true")
            self.assertIn("payhip", page.eval_on_selector(".glow-in", "g => g.style.backgroundImage"), "the glow takes its colour")
            page.keyboard.press("ArrowRight")
            self.assertEqual(visible(), ["itch"], "arrow keys move along the tabs")
            page.click("h1")
            for key in ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"]:
                page.keyboard.press(key)
            page.locator(".confetti i").first.wait_for(state="attached")
            page.get_by_text("A fine hoard.").wait_for()
            page.evaluate("scrollTo(0, 0)")
            for _ in range(5):
                page.click(".brand")
            page.get_by_text("somebody's treasure").wait_for()
            browser.close()

if __name__ == "__main__":
    unittest.main()
