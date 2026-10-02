"""Releases: the app, its betas and Hoard for Unity share one Releases page, told apart by tag and title, with
Latest kept on the app (scripts/release_info.py), and older releases brought in line (scripts/tidy_releases.py)."""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_site_changelog as changelog  # noqa: E402
import release_info  # noqa: E402
import tidy_releases  # noqa: E402


def rel(id_, tag, name=None, prerelease=False, draft=False):
    return {"id": id_, "tag_name": tag, "name": name, "prerelease": prerelease, "draft": draft}


class Kinds(unittest.TestCase):

    def test_each_kind_of_tag(self):
        cases = {"v3.1.0": ("app", "Hoard 3.1.0", False, True),
                 "v3.1.0-beta.2": ("beta", "Hoard 3.1.0 beta 2", True, False),
                 "unity-v0.6.0": ("unity", "Hoard for Unity 0.6.0", False, False),
                 "unity-v0.6.0-beta.1": ("unity-beta", "Hoard for Unity 0.6.0 beta 1", True, False)}
        for tag, (kind, title, pre, latest) in cases.items():
            got = release_info.info(tag)
            self.assertEqual((got["kind"], got["title"], got["prerelease"], got["latest"]), (kind, title, pre, latest), tag)
        for bad in ("3.1.0", "v3.1", "v3.1.0-rc.1", "v3.1.0-beta", "unity-3.0.0", "v3.1.0 ", ""):
            self.assertIsNone(release_info.info(bad), bad)
        self.assertLess(release_info.info("v3.1.0-beta.9")["version"], release_info.info("v3.1.0")["version"])
        self.assertLess(release_info.info("v3.0.9")["version"], release_info.info("v3.1.0-beta.1")["version"])

    def test_for_the_workflows(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(release_info.main(["--github-env", "v3.1.0-beta.2"]), 0)
        self.assertEqual(out.getvalue().split("\n")[:4],
                         ["KIND=beta", "TITLE=Hoard 3.1.0 beta 2", "PRERELEASE=true", "LATEST=false"])
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(release_info.main(["--github-env", "v3.1"]), 1, "an odd tag stops the release")

    def test_the_workflows_use_it(self):
        app = (REPO / ".github/workflows/release.yml").read_text("utf-8")
        self.assertIn('scripts/release_info.py --github-env "$TAG" >> "$GITHUB_ENV"', app)
        self.assertIn('--title "$TITLE" --prerelease="$PRERELEASE"', app)
        self.assertIn('--draft=false --latest="$latest"', app)
        self.assertIn('"/DFileVersion=$numbers"', app, "Windows' file version is numbers only")
        unity = (REPO / ".github/workflows/unity-release.yml").read_text("utf-8")
        self.assertIn("--latest=false", unity, "a Unity release never takes Latest from the app")
        tidy = (REPO / ".github/workflows/tidy-releases.yml").read_text("utf-8")
        self.assertIn("workflow_dispatch", tidy)
        self.assertIn("default: false", tidy, "it only lists the changes unless asked")
        self.assertIn("EARLY_BEFORE: ${{ inputs.early_before }}", tidy, "inputs reach the script through the environment")


class Tidying(unittest.TestCase):

    LISTED = [rel(1, "v2.11.1", "Hoard v2.11.1"), rel(2, "unity-v0.3.0", "Hoard for Unity 0.3.0"),
              rel(3, "v2.4.1", None, prerelease=True), rel(4, "unity-v0.1.0", "Hoard for Unity 0.1.0", prerelease=True),
              rel(5, "v3.0.0-beta.1", "Hoard v3.0.0-beta.1"), rel(6, "v3.0.0", "Hoard 3.0.0", draft=True),
              rel(7, "nightly", "Nightly"), rel(8, "v1.0.0", "Hoard 1.0.0")]

    def test_the_plan(self):
        changes, latest, skipped = tidy_releases.plan(self.LISTED)
        by_tag = {c["tag"]: c["to"] for c in changes}
        self.assertEqual(by_tag, {"v2.11.1": {"name": "Hoard 2.11.1"},
                                  "v2.4.1": {"name": "Hoard 2.4.1", "prerelease": False},
                                  "unity-v0.1.0": {"prerelease": False},
                                  "v3.0.0-beta.1": {"name": "Hoard 3.0.0 beta 1", "prerelease": True}})
        self.assertEqual(latest["tag_name"], "v2.11.1", "the newest app release; not a beta, Unity or a draft")
        self.assertEqual(len(skipped), 2)
        self.assertTrue(any("v3.0.0: a draft" in s for s in skipped))
        self.assertTrue(any("nightly" in s for s in skipped))

    def test_early_releases(self):
        changes, _, _ = tidy_releases.plan(self.LISTED, tidy_releases.early_version("2.5.0"))
        names = {c["tag"]: c["to"].get("name") for c in changes}
        self.assertEqual(names["v2.4.1"], "Hoard 2.4.1 (early)")
        self.assertEqual(names["v1.0.0"], "Hoard 1.0.0 (early)")
        self.assertEqual(names["v2.11.1"], "Hoard 2.11.1")
        with self.assertRaises(SystemExit):
            tidy_releases.early_version("soon")

    def test_it_only_looks_unless_asked(self):
        class Fake:
            calls = []

            def __init__(self, repo, token):
                self.token = token

            def releases(self):
                return Tidying.LISTED

            def latest_id(self):
                return 2   # a Unity release took Latest

            def call(self, method, path, body=None):
                Fake.calls.append((method, path, body))
        with mock.patch.object(tidy_releases, "GitHub", Fake), mock.patch.dict(os.environ, {}, clear=True), \
                redirect_stdout(io.StringIO()) as out:
            self.assertEqual(tidy_releases.main([]), 0)
        self.assertEqual(Fake.calls, [], "nothing changed")
        self.assertIn("v2.11.1: make it Latest", out.getvalue())
        with mock.patch.object(tidy_releases, "GitHub", Fake), mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(tidy_releases.main(["--apply"]), 2, "changing needs a token, from the environment")
        with mock.patch.object(tidy_releases, "GitHub", Fake), mock.patch.dict(os.environ, {"GH_TOKEN": "t"}, clear=True), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(tidy_releases.main(["--apply"]), 0)
        self.assertEqual(len(Fake.calls), 5)
        self.assertEqual(Fake.calls[-1], ("PATCH", "/releases/1", {"make_latest": "true"}), "Latest goes back to the app, last")
        self.assertTrue(all(c[2].get("make_latest") == "false" for c in Fake.calls[:-1]))


class Notes(unittest.TestCase):

    def test_whats_new_leaves_betas_out(self):
        page = changelog.page("## 3.1.0-beta.1\n\n- Testing.\n\n## 3.0.0\n\n- Released.\n", {})
        self.assertIn("3.0.0", page)
        self.assertNotIn("beta", page)

    def test_the_unity_package_can_have_betas(self):
        import build_vpm
        for version, ok in (("0.6.0", True), ("0.6.0-beta.1", True), ("0.6.0-rc.1", False), ("0.6", False)):
            self.assertEqual(bool(build_vpm.PACKAGE_VERSION.fullmatch(version)), ok, version)


if __name__ == "__main__":
    unittest.main()
