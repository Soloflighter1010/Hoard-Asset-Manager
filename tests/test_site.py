"""Hoard's website (site/, issue #27), deployed to GitHub Pages in front of the VCC listing by build-listing.yml:
complete, loading nothing from elsewhere, pointing at the real listing and downloads, and laid out on deploy so
that VCC's addresses keep working."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
WORKFLOW = REPO / ".github" / "workflows" / "build-listing.yml"
RELEASES = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest"


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
        for tag, key, value in self.page.refs:
            if re.match(r"(https?|vcc|mailto):", value):
                continue
            if value.startswith("#"):
                self.assertIn(value[1:], self.page.ids, value)
                continue
            if value in ("./", "vcc/"):
                continue   # the site itself, and the listing's page put at vcc/ on deploy
            self.assertTrue((SITE / value.split("#")[0]).is_file(), value)
        css = (SITE / "styles.css").read_text("utf-8")
        for url in re.findall(r"url\(([^)]+)\)", css):
            self.assertTrue((SITE / url.strip("\"'")).is_file(), url)

    def test_it_loads_nothing_from_other_sites(self):
        self.assertEqual(self.page.external_loads, [])
        css = (SITE / "styles.css").read_text("utf-8")
        self.assertNotRegex(css, r"url\(\s*[\"']?https?://|@import")
        js = (SITE / "site.js").read_text("utf-8")
        self.assertEqual(set(re.findall(r"fetch\(`?([^`'\"]*)", js)), {"https://api.github.com/repos/${REPO}/releases/latest"},
                         "only asks GitHub which files the latest release has")
        self.assertNotIn("innerHTML", js, "nothing from GitHub's answer becomes page markup")

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

    def test_it_works_on_a_phone(self):
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', self.html)
        self.assertIn("@media (max-width: 760px)", (SITE / "styles.css").read_text("utf-8"))


class TheDeploy(unittest.TestCase):

    def setUp(self):
        self.text = WORKFLOW.read_text("utf-8")

    def test_it_deploys_when_the_site_changes(self):
        self.assertRegex(self.text, r'push:\n\s+branches: \[main\]\n\s+paths: \[[^\]]*"site/\*\*"')

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


if __name__ == "__main__":
    unittest.main()
