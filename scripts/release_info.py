"""What a release tag is, and how its GitHub release should look: one place for the release workflows and
scripts/tidy_releases.py.

    python scripts/release_info.py v3.1.0-beta.2       ->  kind=beta, title=Hoard 3.1.0 beta 2, prerelease=true, latest=false
    python scripts/release_info.py --github-env TAG    ->  the same, as KIND=..., TITLE=... lines for $GITHUB_ENV

Hoard's releases share this repository's Releases page, told apart by their tags:

    v3.1.0               Hoard 3.1.0                the app            a normal release, and Latest
    v3.1.0-beta.2        Hoard 3.1.0 beta 2         a beta of the app  a pre-release (never Latest)
    unity-v0.6.0         Hoard for Unity 0.6.0      the Unity package  a normal release, never Latest
    unity-v0.6.0-beta.1  Hoard for Unity 0.6.0 beta 1                  a pre-release

Latest stays on the app, because the website's download buttons, and the Releases page's "Latest" badge, follow it.
"""
from __future__ import annotations

import re
import sys

_VERSION = r"(\d{1,4})\.(\d{1,4})\.(\d{1,4})(?:-beta\.(\d{1,3}))?"
APP = re.compile(rf"v{_VERSION}")
UNITY = re.compile(rf"unity-v{_VERSION}")


def info(tag: str) -> dict | None:
    """kind (app, beta, unity, unity-beta), title, prerelease, latest and version (as numbers that sort as the versions
    do), for a release tag; None for a tag that isn't one of Hoard's."""
    for rx, kind, name in ((APP, "app", "Hoard"), (UNITY, "unity", "Hoard for Unity")):
        m = rx.fullmatch(str(tag or ""))
        if not m:
            continue
        beta = m[4] is not None
        numbers = ".".join(m.groups()[:3])
        return {"tag": tag, "kind": f"{'beta' if kind == 'app' else 'unity-beta'}" if beta else kind,
                "title": f"{name} {numbers}" + (f" beta {int(m[4])}" if beta else ""),
                "prerelease": beta, "latest": kind == "app" and not beta,
                "version": tuple(int(x) for x in m.groups()[:3]) + ((0, int(m[4])) if beta else (1, 0))}
    return None


def main(argv: list[str]) -> int:
    env = argv[:1] == ["--github-env"]
    args = argv[1:] if env else argv
    if len(args) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    found = info(args[0])
    if not found:
        print(f"{args[0]} isn't one of Hoard's release tags (v3.1.0, v3.1.0-beta.1, unity-v0.6.0, ...)", file=sys.stderr)
        return 1
    pairs = {"KIND": found["kind"], "TITLE": found["title"], "PRERELEASE": str(found["prerelease"]).lower(),
             "LATEST": str(found["latest"]).lower()}
    print("\n".join(f"{k}={v}" for k, v in pairs.items()) if env else
          ", ".join(f"{k.lower()}={v}" for k, v in pairs.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
