"""Give every release on GitHub the title and status its tag calls for (scripts/release_info.py), and keep Latest on
the newest release of the app.

    python scripts/tidy_releases.py                          # shows what it would change; changes nothing
    python scripts/tidy_releases.py --apply                  # changes it
    python scripts/tidy_releases.py --early-before 2.5.0     # also titles app releases before 2.5.0 "(early)"

Or run it from GitHub, with nothing to install or sign in to: Actions > Tidy releases > Run workflow.

What it changes, release by release: the title (Hoard 3.1.0, Hoard 3.1.0 beta 2, Hoard for Unity 0.6.0), and whether
it's a pre-release (only betas are). Then it makes the newest app release Latest, so the website's download buttons
offer the app. Never the files, the notes or the tags: published releases here are immutable, and their files and
tags can't change anyway. Drafts, and tags that aren't Hoard's, are left alone and listed.

It needs a GitHub token that can write this repository's releases, in the GH_TOKEN (or GITHUB_TOKEN) environment
variable: the workflow's own, or one from `gh auth token`. Never on the command line. (Only to make changes: looking
needs none, as the releases are public.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_info import info  # noqa: E402

REPO = "Soloflighter1010/Hoard-Asset-Manager"
API = "https://api.github.com"


def plan(releases: list[dict], early_before: tuple | None = None) -> tuple[list[dict], dict | None, list[str]]:
    """(the changes, the release to make Latest or None when it already is, what's left alone and why).
    Each change is {"id", "tag", "from": {...}, "to": {...}} with only the fields that differ."""
    changes, skipped, newest = [], [], None
    for r in releases:
        tag = str(r.get("tag_name") or "")
        if r.get("draft"):
            skipped.append(f"{tag}: a draft (left for its release run to finish)")
            continue
        found = info(tag)
        if not found:
            skipped.append(f"{tag or '(no tag)'}: not one of Hoard's release tags")
            continue
        title = found["title"]
        if early_before and found["kind"] == "app" and found["version"] < early_before:
            title += " (early)"
        want = {"name": title, "prerelease": found["prerelease"]}
        have = {"name": r.get("name") or "", "prerelease": bool(r.get("prerelease"))}
        diff = {k: v for k, v in want.items() if have[k] != v}
        if diff:
            changes.append({"id": r["id"], "tag": tag, "from": {k: have[k] for k in diff}, "to": diff})
        if found["latest"] and (newest is None or found["version"] > newest[0]):
            newest = (found["version"], r)
    latest = newest[1] if newest else None
    return changes, latest, skipped


def early_version(text: str | None) -> tuple | None:
    if not text:
        return None
    found = info(f"v{text}")
    if not found or found["kind"] != "app":
        raise SystemExit(f"--early-before takes a version such as 2.5.0, not {text}")
    return found["version"]


class GitHub:
    def __init__(self, repo: str, token: str | None):
        self.repo, self.token = repo, token

    def call(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(f"{API}/repos/{self.repo}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                                              **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
                                              "User-Agent": "hoard-tidy-releases",
                                              **({"Content-Type": "application/json"} if body is not None else {})})
        with urllib.request.urlopen(req, timeout=30) as r:   # noqa: S310 - api.github.com only
            return json.loads(r.read() or b"null")

    def releases(self) -> list[dict]:
        out, page = [], 1
        while True:
            batch = self.call("GET", f"/releases?per_page=100&page={page}")
            out += batch
            if len(batch) < 100:
                return out
            page += 1

    def latest_id(self) -> int | None:
        try:
            return self.call("GET", "/releases/latest").get("id")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise


def why(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        try:
            detail = json.loads(e.read() or b"{}").get("message") or ""
        except ValueError:
            detail = ""
        return f"GitHub said {e.code}{f': {detail}' if detail else ''}"
    return f"{type(e).__name__}: {e}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Tidy the titles and status of Hoard's releases on GitHub.")
    ap.add_argument("--apply", action="store_true", help="make the changes (without it, only show them)")
    ap.add_argument("--early-before", metavar="VERSION", help='add "(early)" to app releases older than this')
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or REPO)
    args = ap.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if args.apply and not token:   # (looking needs none: the releases are public)
        print("Set GH_TOKEN to a token that can write this repository's releases (gh auth token gives yours).",
              file=sys.stderr)
        return 2
    gh = GitHub(args.repo, token)
    changes, latest, skipped = plan(gh.releases(), early_version(args.early_before))

    for c in changes:
        parts = [f'title "{c["from"]["name"]}" -> "{c["to"]["name"]}"' if "name" in c["to"] else "",
                 ("pre-release -> release" if c["from"]["prerelease"] else "release -> pre-release")
                 if "prerelease" in c["to"] else ""]
        print(f"{c['tag']}: " + "; ".join(p for p in parts if p))
    current = gh.latest_id()
    make_latest = latest is not None and latest["id"] != current
    if make_latest:
        print(f"{latest['tag_name']}: make it Latest")
    for line in skipped:
        print(f"left alone: {line}")
    if not changes and not make_latest:
        print("Every release is already as it should be.")
        return 0
    if not args.apply:
        print(f"\n{len(changes) + make_latest} change(s) to make. Run again with --apply to make them.")
        return 0

    failed = 0
    for c in changes:
        try:
            gh.call("PATCH", f"/releases/{c['id']}", {**c["to"], "make_latest": "false"})
        except Exception as e:  # noqa: BLE001 - each release is tried; what failed is listed
            failed += 1
            print(f"{c['tag']}: not changed ({why(e)})", file=sys.stderr)
    if latest is not None:   # last, so nothing changed above can take Latest from it
        try:
            gh.call("PATCH", f"/releases/{latest['id']}", {"make_latest": "true"})
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"{latest['tag_name']}: not made Latest ({why(e)})", file=sys.stderr)
    print(f"Done: {len(changes) + make_latest - failed} change(s) made" + (f", {failed} failed (above)." if failed else "."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
