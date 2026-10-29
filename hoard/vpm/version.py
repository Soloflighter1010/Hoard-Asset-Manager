"""Versions as VPM packages and Unity name them, and the ranges packages ask for.

A package's version is semver (1.2.3, 1.2.3-beta.1, 1.2.3+build). The ranges in a package's vpmDependencies and in a
project's vpm-manifest.json are npm's notation ("^1.2", "~1.2.3", ">=1.0.0 <2", "1.x", "1.0.0 - 2.0.0", "a || b").
This follows vrc-get (ALCOM's engine, MIT) exactly, prerelease rules included, so Hoard picks the same version
ALCOM and the Creator Companion would.
"""
from __future__ import annotations

import functools
import re

_SEGMENT_MAX = (1 << 63) - 1
_ID = re.compile(r"[0-9A-Za-z-]+")
_ID_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")


class VersionError(ValueError):
    """Text that isn't a version or a range."""


def _cmp_pre(a: str, b: str) -> int:
    """Prerelease order: none (a release) is greater than any; identifiers compare numerically when both are
    numbers, a number is less than text, text compares as ASCII, and with all equal the longer list is greater."""
    if a == b:
        return 0
    if not a:
        return 1
    if not b:
        return -1
    left, right = a.split("."), b.split(".")
    for x, y in zip(left, right):
        xd, yd = x.isdigit() and x.isascii(), y.isdigit() and y.isascii()
        if xd and yd:
            c = (len(x) > len(y)) - (len(x) < len(y)) or (x > y) - (x < y)
        elif xd:
            return -1
        elif yd:
            return 1
        else:
            c = (x > y) - (x < y)
        if c:
            return c
    return (len(left) > len(right)) - (len(left) < len(right))


def _number(text: str) -> int:
    """One of a version's numbers: digits only, no leading zero, and not past what vrc-get allows."""
    if not text.isascii() or not text.isdigit() or (len(text) > 1 and text[0] == "0"):
        raise VersionError(f"not a version number: {text!r}")
    value = int(text)
    if value > _SEGMENT_MAX:
        raise VersionError("a version number that's too large")
    return value


def _ids(text: str) -> str:
    """A version's prerelease or build label (beta.1): dot-separated letters, digits and hyphens."""
    if not text or any(not _ID.fullmatch(p) for p in text.split(".")):
        raise VersionError(f"not a version label: {text!r}")
    return text


@functools.total_ordering
class Version:
    """A semver version. Build metadata is kept but, as semver says, plays no part in order or equality."""
    __slots__ = ("major", "minor", "patch", "pre", "build")

    def __init__(self, major: int, minor: int, patch: int, pre: str = "", build: str = ""):
        self.major, self.minor, self.patch, self.pre, self.build = major, minor, patch, pre, build

    @classmethod
    def parse(cls, text) -> "Version":
        """A version from its text (1.2.3, 1.2.3-beta.1, 1.2.3+build); raises VersionError for anything else."""
        if not isinstance(text, str):
            raise VersionError("not a version")
        rest, _, build = text.partition("+")
        core, dash, pre = rest.partition("-")
        parts = core.split(".")
        if len(parts) != 3:
            raise VersionError(f"not a version: {text!r}")
        return cls(*(_number(p) for p in parts), _ids(pre) if dash else "", _ids(build) if build or "+" in text else "")

    @classmethod
    def maybe(cls, text) -> "Version | None":
        """parse, or None for text that isn't a version."""
        try:
            return cls.parse(text)
        except VersionError:
            return None

    def _key(self):
        """What versions sort by before their prerelease labels."""
        return (self.major, self.minor, self.patch)

    def __eq__(self, other):
        return isinstance(other, Version) and self._key() == other._key() and self.pre == other.pre

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        if self._key() != other._key():
            return self._key() < other._key()
        return _cmp_pre(self.pre, other.pre) < 0

    def __hash__(self):
        return hash((self.major, self.minor, self.patch, self.pre))

    def __repr__(self):
        return f"Version({str(self)!r})"

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}" + (f"-{self.pre}" if self.pre else "") + (
            f"+{self.build}" if self.build else "")

    @property
    def is_pre(self) -> bool:
        """Is this a prerelease (1.2.3-beta)?"""
        return bool(self.pre)

    def base(self) -> "Version":
        """The same version without its prerelease and build labels."""
        return Version(self.major, self.minor, self.patch)


# ---- ranges

# A part of a version in a range that isn't a number: missing ("1.2"), or a wildcard (x, X, *).
_NONE, _STAR, _UX, _LX = "none", "*", "X", "x"
_HUGE = (1 << 64) - 1


class _Partial:
    """A version as a range writes it, with parts left out (1.x, ^1.2): each missing part is _NONE, or x or *."""
    __slots__ = ("major", "minor", "patch", "pre", "build")

    def __init__(self, major, minor=_NONE, patch=_NONE, pre="", build=""):
        self.major, self.minor, self.patch, self.pre, self.build = major, minor, patch, pre, build

    @staticmethod
    def of(v: Version) -> "_Partial":
        """A full version, as a partial one (every part there)."""
        return _Partial(v.major, v.minor, v.patch, v.pre, v.build)

    def _n(self, part):
        """A part's number, or None for a missing or starred one."""
        return part if isinstance(part, int) else None

    def full(self) -> Version | None:
        """The version, when every part is there; None when one is missing or starred."""
        if all(isinstance(p, int) for p in (self.major, self.minor, self.patch)):
            return Version(self.major, self.minor, self.patch, self.pre, self.build)
        return None

    def full_or_next(self) -> tuple[Version, bool]:
        """The version with every part there, and True; or, with parts missing, the first version past it (1.x:
        2.0.0-0), and False."""
        major, minor, patch = self._n(self.major), self._n(self.minor), self._n(self.patch)
        if major is None:
            return Version(_HUGE, _HUGE, _HUGE, "0"), False
        if minor is None:
            return Version(major + 1, 0, 0, "0"), False
        if patch is None:
            return Version(major, minor + 1, 0, "0"), False
        return Version(major, minor, patch, self.pre, self.build), True

    def zeros(self) -> Version:
        """The version with missing parts as 0 (1.x: 1.0.0)."""
        return Version(self._n(self.major) or 0, self._n(self.minor) or 0, self._n(self.patch) or 0,
                       self.pre, self.build)

    def zeros_with_pre(self) -> Version:
        """zeros, with the lowest prerelease label (0) when it has none, so it's below every prerelease of that
        version."""
        v = self.zeros()
        return Version(v.major, v.minor, v.patch, v.pre or "0", v.build)

    def __str__(self):
        out = ""
        for prefix, part in (("", self.major), (".", self.minor), (".", self.patch)):
            if part != _NONE:
                out += prefix + str(part)
        return out + (f"-{self.pre}" if self.pre else "") + (f"+{self.build}" if self.build else "")

    def __eq__(self, other):
        return isinstance(other, _Partial) and str(self) == str(other)


class _Reader:
    """Reads a range's text a character at a time, as vrc-get's ParsingBuf does."""

    def __init__(self, text: str):
        self.text, self.at = text, 0

    def first(self, offset: int = 0) -> str | None:
        """The character offset characters ahead, or None past the end."""
        i = self.at + offset
        return self.text[i] if i < len(self.text) else None

    def skip(self, n: int = 1) -> "_Reader":
        """Move past n characters (and return the reader, to go on with it)."""
        self.at += n
        return self

    def skip_ws(self) -> None:
        """Move past any spaces."""
        while self.first() is not None and self.first() in " \t\r\n\f\v":
            self.at += 1

    def empty(self) -> bool:
        """Is all of the text read?"""
        return self.at >= len(self.text)

    def segment(self):
        """One part of a version in a range: a number (no leading zero), or x, X or *."""
        c = self.first()
        if c in ("x", "X", "*"):
            self.skip()
            return c
        if c is None or not ("0" <= c <= "9"):
            raise VersionError("not a version range")
        if c == "0":
            self.skip()
            if self.first() is not None and "0" <= self.first() <= "9":
                raise VersionError("not a version range")
            return 0
        start = self.at
        while self.first() is not None and "0" <= self.first() <= "9":
            self.skip()
        value = int(self.text[start:self.at])
        if value > _SEGMENT_MAX:
            raise VersionError("a version number that's too large")
        return value

    def ident(self) -> str:
        """A prerelease or build label, up to the next character that can't be in one."""
        start = self.at
        while True:
            c = self.first()
            if c is None or c not in _ID_START:
                raise VersionError("not a version range")
            while self.first() is not None and self.first() in _ID_START:
                self.skip()
            if self.first() == ".":
                self.skip()
                continue
            return self.text[start:self.at]

    def partial(self) -> _Partial:
        """A version as a range writes it (v1.2, 1.x, 1.2.3-beta+build)."""
        self.skip_ws()
        if self.first() == "v":
            self.skip()
        major = self.segment()
        minor = patch = _NONE
        pre = build = ""
        if self.first() == ".":
            self.skip()
            minor = self.segment()
            if self.first() == ".":
                self.skip()
                patch = self.segment()
                if self.first() == "-":
                    if self.first(1) not in (None, "."):
                        self.skip()
                    pre = self.ident()
                elif self.first() is not None and self.first() in _ID_START:
                    pre = self.ident()
                if self.first() == "+":
                    self.skip()
                    build = self.ident()
        return _Partial(major, minor, patch, pre, build)

    def comparator(self) -> "tuple[str, tuple]":
        """One comparison: an operator (~, ^, =, <, <=, >, >=) and its version, a hyphen range (1.0 - 2.0), or a bare
        version."""
        self.skip_ws()
        c = self.first()
        if c is None:
            raise VersionError("a version range that ends partway")
        if c in "~^=":
            return {"~": "tilde", "^": "caret", "=": "exact"}[c], (self.skip().partial(),)
        if c in "<>":
            self.skip()
            if self.first() == "=":
                self.skip()
                op = "ge" if c == ">" else "le"
            else:
                op = "gt" if c == ">" else "lt"
            self.skip_ws()
            return op, (self.partial(),)
        first = self.partial()
        self.skip_ws()
        if self.first() == "-":
            return "hyphen", (first, self.skip().partial())
        return "star", (first,)


def _gt(v: Version, p: _Partial) -> bool:
    """v > the partial version (>1.2 means 1.3.0 or later)."""
    full, is_full = p.full_or_next()
    return v > full if is_full else v >= full


def _ge(v: Version, p: _Partial) -> bool:
    """v >= the partial version (>=1.2 means 1.2.0 or later)."""
    full = p.full()
    return v >= full if full else v >= p.zeros_with_pre()


def _lt(v: Version, p: _Partial) -> bool:
    """v < the partial version (<1.2 means before 1.2.0)."""
    full = p.full()
    return v < full if full else v < p.zeros_with_pre()


def _le(v: Version, p: _Partial) -> bool:
    """v <= the partial version (<=1.2 means anything 1.2.x)."""
    full, is_full = p.full_or_next()
    return v <= full if is_full else v < full


def _matches_internal(op: str, parts: tuple, v: Version) -> bool:
    """Does v satisfy one comparison (~, ^, =, >, >=, <, <=, a bare or starred version, or a hyphen range), as vrc-get
    decides it, before the prerelease rules?"""
    p = parts[0]
    if op == "tilde":
        if v < p.zeros() or v.major != (p._n(p.major) or 0):
            return False
        return p._n(p.minor) is None or v.minor == p.minor
    if op == "caret":
        if v < p.zeros():
            return False
        if p._n(p.major) is None:
            return True
        if v.major != p.major:
            return False
        if p.major == 0 and p._n(p.minor) is not None:
            if v.minor != p.minor:
                return False
            if p._n(p.patch) is not None and p.minor == 0 and v.patch != p.patch:
                return False
        return True
    if op in ("star", "exact"):
        full, is_full = p.full_or_next()
        return full == v if is_full else p.zeros_with_pre() <= v < full
    if op == "gt":
        return _gt(v, p)
    if op == "ge":
        return _ge(v, p)
    if op == "lt":
        return _lt(v, p)
    if op == "le":
        return _le(v, p)
    return _ge(v, p) and _le(v, parts[1])   # hyphen


# How a range treats prerelease versions: never, always, or only when the range itself names one (npm's rule, as
# vrc-get applies it: each part of the range that a prerelease is checked against must name a prerelease itself).
DENY, ALLOW, MINIMUM = "deny", "allow", "minimum"


def allow_or_minimum(allow: bool) -> str:
    """The prerelease rule to match with: ALLOW when prereleases are wanted, MINIMUM (only where the range names one)
    otherwise."""
    return ALLOW if allow else MINIMUM


_SYMBOL = {"tilde": "~", "caret": "^", "exact": "=", "gt": ">", "ge": ">=", "lt": "<", "le": "<=", "star": ""}


class VersionRange:
    """A range: sets of comparisons joined by ||, any set of which a version may satisfy (all of its comparisons)."""
    __slots__ = ("sets",)

    def __init__(self, sets: list):
        self.sets = sets

    @classmethod
    def parse(cls, text) -> "VersionRange":
        """A range from its text (^1.2 || >=2.0.0 <3); raises VersionError for anything else."""
        if not isinstance(text, str) or len(text) > 500:
            raise VersionError("not a version range")
        sets = []
        for part in text.split("||"):
            r = _Reader(part)
            comparators = []
            while not r.empty():
                comparators.append(r.comparator())
                r.skip_ws()
            sets.append(comparators)
        return cls(sets)

    @classmethod
    def maybe(cls, text) -> "VersionRange | None":
        """parse, or None for text that isn't a range."""
        try:
            return cls.parse(text)
        except VersionError:
            return None

    @classmethod
    def same_or_later(cls, v: Version) -> "VersionRange":
        """The range of v and every version after it (>=v)."""
        return cls([[("ge", (_Partial.of(v),))]])

    @classmethod
    def specific(cls, v: Version) -> "VersionRange":
        """The range of v alone (=v)."""
        return cls([[("exact", (_Partial.of(v),))]])

    def contains_pre(self) -> bool:
        """Does the range name a prerelease anywhere (^1.2.0-beta)?"""
        return any(p.pre for s in self.sets for _, parts in s for p in parts)

    def matches(self, v: Version) -> bool:
        """Does v satisfy the range, a prerelease only where the range names one of its version?"""
        return self.match_pre(v, MINIMUM)

    def match_pre(self, v: Version, prerelease: str) -> bool:
        """Does v satisfy any one of the range's sets, with prerelease (DENY, ALLOW or MINIMUM) as the rule for
        prereleases?"""
        def one(op, parts):
            """Does v satisfy this one comparison, under the prerelease rule?"""
            if not _matches_internal(op, parts, v):
                return False
            if not v.pre:
                return True
            if prerelease == DENY:
                return False
            if prerelease == ALLOW:
                return True
            return any(p.zeros().pre for p in parts)
        return any(all(one(op, parts) for op, parts in s) for s in self.sets)

    def intersect(self, other: "VersionRange") -> "VersionRange":
        """The range of versions both ranges allow."""
        return VersionRange([a + b for a in self.sets for b in other.sets])

    def __str__(self):
        def comp(op, parts):
            """One comparison as it's written."""
            if op == "hyphen":
                return f"{parts[0]} - {parts[1]}"
            return _SYMBOL[op] + str(parts[0])
        return " || ".join(" ".join(comp(op, parts) for op, parts in s) for s in self.sets)

    def __repr__(self):
        return f"VersionRange({str(self)!r})"

    def __eq__(self, other):
        return isinstance(other, VersionRange) and str(self) == str(other)

    def __hash__(self):
        return hash(str(self))


class DependencyRange:
    """What a project's vpm-manifest.json asks for: a range, where a bare full version ("1.2.3") means that version
    or later, as the Creator Companion reads it."""
    __slots__ = ("range",)

    def __init__(self, r: VersionRange):
        self.range = r

    @classmethod
    def parse(cls, text) -> "DependencyRange":
        """A project's dependency from its text in vpm-manifest.json."""
        return cls(VersionRange.parse(text))

    @classmethod
    def version(cls, v: Version) -> "DependencyRange":
        """A dependency on a version as it's written bare (1.2.3: that version or later)."""
        return cls(VersionRange([[("star", (_Partial.of(v),))]]))

    @classmethod
    def from_version_range(cls, r: VersionRange) -> "DependencyRange":
        """A dependency from a range: a bare full version becomes exactly that version, any other range stays as it
        is."""
        single = cls(r).single_version()
        return cls(VersionRange.specific(single)) if single else cls(r)

    def single_version(self) -> Version | None:
        """The version, when the dependency is a bare full version (1.2.3); None for a real range."""
        if len(self.range.sets) == 1 and len(self.range.sets[0]) == 1:
            op, parts = self.range.sets[0][0]
            if op == "star":
                return parts[0].full()
        return None

    def matches(self, v: Version) -> bool:
        """Does v satisfy the dependency: a bare version or later, or the range, prereleases allowed?"""
        single = self.single_version()
        return single <= v if single else self.range.match_pre(v, ALLOW)

    def as_range(self) -> VersionRange:
        """The dependency as a range to resolve with: a bare version means it or later."""
        single = self.single_version()
        return VersionRange.same_or_later(single) if single else self.range

    def __str__(self):
        return str(self.range)

    def __eq__(self, other):
        return isinstance(other, DependencyRange) and self.range == other.range


# ---- Unity's versions: 2022.3.22f1

_RELEASE_ORDER = {"a": 0, "b": 1, "f": 2, "c": 2, "p": 3, "x": 4}


@functools.total_ordering
class UnityVersion:
    """A Unity editor's version: 2022.3.22f1 (major.minor.revision, release type, increment), and China's
    2022.3.22f1c1."""
    __slots__ = ("major", "minor", "revision", "type", "increment", "china")

    def __init__(self, major: int, minor: int, revision: int, type_: str = "f", increment: int = 1,
                 china: int | None = None):
        self.major, self.minor, self.revision, self.type, self.increment, self.china = (
            major, minor, revision, type_, increment, china)

    @classmethod
    def parse(cls, text) -> "UnityVersion | None":
        """A Unity version from its text (2022.3.22f1, 2022.3.22f1c1); None for anything else."""
        if not isinstance(text, str) or len(text) > 60:
            return None
        m = re.fullmatch(r"(\d{1,5})\.(\d{1,3})\.(\d{1,3})([abfcpx])(\d{1,3})(?:c(\d{1,3}))?(?:-.*)?", text.strip(),
                         re.S)
        if not m:
            return None
        major, minor, revision, type_, inc, china = m.groups()
        values = int(major), int(minor), int(revision), int(inc)
        if values[0] > 65535 or any(x > 255 for x in values[1:]) or (china is not None and not 0 < int(china) <= 255):
            return None
        return cls(values[0], values[1], values[2], type_, values[3], int(china) if china else None)

    @classmethod
    def parse_short(cls, text) -> "UnityVersion | None":
        """2022.3.22, which some files write without the release type, read as 2022.3.22f1."""
        m = re.fullmatch(r"(\d{1,5})\.(\d{1,3})\.(\d{1,3})", text.strip()) if isinstance(text, str) else None
        if not m or int(m.group(2)) > 255 or int(m.group(3)) > 255 or int(m.group(1)) > 65535:
            return None
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    def _key(self):
        """What Unity versions sort by: the numbers, then the release type (alpha, beta, final, patch, experimental),
        then the increment."""
        return (self.major, self.minor, self.revision, _RELEASE_ORDER[self.type], self.increment)

    def __eq__(self, other):
        return isinstance(other, UnityVersion) and self._key() == other._key()

    def __lt__(self, other):
        if not isinstance(other, UnityVersion):
            return NotImplemented
        return self._key() < other._key()

    def __hash__(self):
        return hash(self._key())

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.revision}{self.type}{self.increment}" + (
            f"c{self.china}" if self.china else "")

    def __repr__(self):
        return f"UnityVersion({str(self)!r})"

    def as_semver(self) -> Version:
        """The version as semver (2022.3.22), for the ranges packages give for Unity."""
        return Version(self.major, self.minor, self.revision)


def partial_unity(text) -> tuple[int, int] | None:
    """A package's "unity" field: "2022.3" or "2022", the oldest Unity it works in."""
    if not isinstance(text, str):
        return None
    major, dot, minor = text.partition(".")
    try:
        major_n, minor_n = int(major.strip()), int(minor.strip()) if dot else 0
    except ValueError:
        return None
    if not (0 <= major_n <= 65535 and 0 <= minor_n <= 255):
        return None
    return major_n, minor_n
