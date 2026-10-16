"""A VPM package's package.json: as a repository lists each version, and as a package folder in a project holds it.

A repository is a file anyone can publish, so every field is checked before it's used. A version a repository
describes badly is left out (as vrc-get does); a package folder's package.json is read leniently, a bad optional
field counting as missing, since the package is already there. A package's name becomes a folder name (in a
project's Packages and in the download cache), so names are held to the characters package names really use.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..safety import clean_text
from .version import UnityVersion, Version, VersionError, VersionRange, partial_unity

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,213}")
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
MAX_LEGACY = 2000
MAX_DEPENDENCIES = 500


def valid_name(name) -> bool:
    """A package name that's safe as a folder name everywhere: letters, digits, dots, dashes and underscores, never
    "..", and never a name Windows keeps for itself."""
    return (isinstance(name, str) and bool(NAME.fullmatch(name)) and ".." not in name
            and name.split(".")[0].lower() not in _RESERVED and not name.endswith("."))


def _url(value) -> str | None:
    """A package's link, or None for an empty one (some packages write "" or " " for none)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or len(value) > 2000 or any(c.isspace() or ord(c) < 32 for c in value.strip()):
        raise ValueError("not a link")
    u = urlsplit(value.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("not a web link")
    return value.strip()


def _text(value, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("not text")
    return clean_text(value, limit)


def _str_map(value, limit: int) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > limit:
        raise ValueError("not a list of names")
    out = {}
    for k, v in value.items():
        if not isinstance(k, str) or not (v is None or isinstance(v, str)) or len(k) > 1000 or len(v or "") > 1000:
            raise ValueError("not a list of names")
        out[k] = v
    return out


class Package:
    """One version of a package, as its package.json describes it."""
    __slots__ = ("name", "version", "display_name", "description", "unity", "url", "zip_sha256", "dependencies",
                 "legacy_folders", "legacy_files", "legacy_packages", "headers", "changelog_url",
                 "documentation_url", "keywords", "yanked", "author")

    @classmethod
    def parse(cls, raw, loose: bool = False) -> "Package | None":
        """The package a package.json describes, or None when it isn't one (a missing or bad name or version, or,
        unless loose, any field that isn't what it should be)."""
        if not isinstance(raw, dict) or not valid_name(raw.get("name")):
            return None
        version = Version.maybe(raw.get("version"))
        if version is None:
            return None
        p = cls()
        p.name, p.version = raw["name"], version

        def field(fn, default):
            try:
                return fn()
            except (ValueError, VersionError, TypeError, AttributeError):
                if loose:
                    return default
                raise

        try:
            p.display_name = field(lambda: _text(raw.get("displayName"), 200), "")
            p.description = field(lambda: _text(raw.get("description"), 2000), "")
            p.unity = field(lambda: _unity(raw.get("unity")), None)
            p.url = field(lambda: _url(raw.get("url")), None)
            p.zip_sha256 = field(lambda: _sha(raw.get("zipSHA256")), None)
            p.dependencies = field(lambda: _ranges(raw.get("vpmDependencies")), {})
            p.legacy_folders = field(lambda: _str_map(raw.get("legacyFolders"), MAX_LEGACY), {})
            p.legacy_files = field(lambda: _str_map(raw.get("legacyFiles"), MAX_LEGACY), {})
            p.legacy_packages = field(lambda: _names(raw.get("legacyPackages")), [])
            p.headers = field(lambda: _headers(raw.get("headers")), {})
            p.changelog_url = _soft_url(raw.get("changelogUrl"))
            p.documentation_url = _soft_url(raw.get("documentationUrl"))
            p.keywords = field(lambda: _keywords(raw.get("keywords")), [])
            p.yanked = field(lambda: _yanked(raw.get("vrc-get")), False)
            p.author = field(lambda: _author(raw.get("author")), "")
        except (ValueError, VersionError, TypeError, AttributeError):
            return None
        return p

    def __repr__(self):
        return f"Package({self.name}@{self.version})"

    def label(self) -> str:
        return self.display_name or self.name


def _keywords(value) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("not a list of keywords")
    return [_text(k, 60) for k in value[:50]]


def _soft_url(value):
    # changelogUrl and documentationUrl are only ever shown as links, so a bad one is just left out (vrc-get drops
    # the whole version for one; there's no need to)
    try:
        return _url(value)
    except ValueError:
        return None


def _unity(value):
    if value is None:
        return None
    parsed = partial_unity(value)
    if parsed is None:
        raise ValueError("not a Unity version")
    return parsed


def _sha(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value.strip()):
        raise ValueError("not a SHA-256")
    return value.strip().lower()


def _ranges(value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > MAX_DEPENDENCIES:
        raise ValueError("not a list of dependencies")
    out = {}
    for name, text in value.items():
        if not valid_name(name):
            raise ValueError("not a package name")
        out[name] = VersionRange.parse(text)
    return out


def _names(value) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_DEPENDENCIES or not all(valid_name(n) for n in value):
        raise ValueError("not a list of package names")
    return list(dict.fromkeys(value))


def _headers(value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 50:
        raise ValueError("not a list of headers")
    out = {}
    for k, v in value.items():
        if not (isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,100}", k)
                and len(v) <= 4000 and not any(c in v for c in "\r\n\0")):
            raise ValueError("not a header")
        out[k] = v
    return out


def _yanked(value) -> bool:
    if not isinstance(value, dict):
        return False
    y = value.get("yanked", False)
    if isinstance(y, bool):
        return y
    if isinstance(y, str):
        return True   # a reason, so yanked
    raise ValueError("not a yanked flag")


def _author(value) -> str:
    if isinstance(value, dict):
        return _text(value.get("name") if isinstance(value.get("name"), str) else None, 200)
    if isinstance(value, str):
        return _text(value, 200)
    return ""


# ---- which Unity a package works in (vrc-get's unity_compatible, kept the same as ALCOM's)

_SDK = ("com.vrchat.avatars", "com.vrchat.worlds", "com.vrchat.base")


def unity_compatible(p: Package, unity: UnityVersion) -> bool:
    v = p.version
    if p.name in _SDK and v.major == 3 and v.minor <= 4:
        return unity.major == 2019   # this VRChat SDK is for Unity 2019 only
    if p.name == "com.vrchat.core.vpm-resolver" and v.major == 0 and v.minor == 1 and v.patch <= 26:
        return unity.major == 2019
    if p.name in _SDK and p.unity is not None:
        # the VRChat SDK is held to its own Unity's minor version (not part of the VPM rules: it keeps the SDK for
        # 2022 out of Unity 6)
        return p.unity == (unity.major, unity.minor)
    if p.unity is not None:
        return unity >= UnityVersion(p.unity[0], p.unity[1], 0, "a", 0)
    return True
