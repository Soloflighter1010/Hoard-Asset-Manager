"""Hoard's version numbers: what a release tag or changelog heading looks like, how versions sort, and which are
betas. One definition for the updater, What's new in the app and the website's changelog page (standard library
only, so the site's build needs nothing installed)."""
from __future__ import annotations

import re

# Hoard's own releases (not unity-v..., not anything else): v3.1.0, and its betas, v3.1.0-beta.1
TAG = re.compile(r"v(\d{1,4})\.(\d{1,4})\.(\d{1,4})(?:-beta\.(\d{1,3}))?")


def version_of(text) -> tuple[int, int, int, int, int] | None:
    """"2.6.0", "v2.6.0" or "3.1.0-beta.2" as numbers that sort as the versions do (a beta comes before its
    release), or None when it isn't a Hoard version."""
    text = str(text or "")
    m = TAG.fullmatch(text if text.startswith("v") else "v" + text)
    if not m:
        return None
    return (int(m[1]), int(m[2]), int(m[3])) + ((0, int(m[4])) if m[4] else (1, 0))


def is_beta(text) -> bool:
    v = version_of(text)
    return bool(v and v[3] == 0)
