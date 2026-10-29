"""Issue #227: Acknowledgements, in the app (Settings) and on the website: everything Hoard uses or ships is credited
with its license, and the license texts Hoard ships with its parts can be shown."""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hoard import credits  # noqa: E402

LOCKS = ("requirements.txt", "requirements-app.txt", "requirements-mac.txt", "requirements-flatpak.txt")
norm = lambda name: re.sub(r"[-_.]+", "-", name).lower()  # noqa: E731


class Acknowledgements(unittest.TestCase):

    def test_every_locked_package_is_credited(self):
        """Every package any of Hoard's lock files pins (what Setup installs, and what each app ships or is built
        with) is in the list, by its package name."""
        pinned = {norm(n) for lock in LOCKS for n in re.findall(r"^([A-Za-z0-9_.-]+)==", (REPO / lock).read_text("utf-8"), re.M)}
        credited = {norm(i["package"]) for i in credits.items() if i.get("package")}
        self.assertEqual(pinned - credited, set(), "add these to hoard/credits.json")
        self.assertEqual(credited - pinned, set(), "credited but no longer used")

    def test_each_has_a_license_a_link_and_a_place(self):
        names = [i["name"] for i in credits.items()]
        self.assertEqual(len(names), len(set(names)), "each once")
        for i in credits.items():
            self.assertTrue(i["license"], i["name"])
            self.assertTrue(i["url"].startswith("https://"), i["name"])
            self.assertTrue(set(i["in"].split()) <= {"all", "windows", "mac", "linux", "build"}, i["name"])
        for name in ("Python", "Chromium (Playwright's build)", "Microsoft Edge WebView2", "Dela Gothic One",
                     "Zen Maru Gothic", "OpenDyslexic", "vrc-get's VRChat project templates (Projects)"):
            self.assertIn(name, names, "not a package, but shipped or used all the same")

    def test_the_license_texts_hoard_ships(self):
        for i in credits.items():
            if i.get("text"):
                self.assertTrue((REPO / i["text"]).is_file(), i["text"])
                self.assertIn("License", credits.license_text(i["name"]) or "", i["name"])
        self.assertIn("Apache License", credits.license_text("Requests") or "", "a package's own, from its details")
        self.assertIsNone(credits.license_text("Not a thing Hoard uses"))
        view = credits.view()
        self.assertEqual(sum(len(g["items"]) for g in view["groups"]), len(credits.items()))

    def test_the_website_says_the_same(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "build_acknowledgements.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        page = (REPO / "site" / "acknowledgements.html").read_text("utf-8")
        for i in credits.items():
            self.assertIn(i["name"].replace("'", "&#x27;"), page)


if __name__ == "__main__":
    unittest.main()
