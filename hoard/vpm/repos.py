"""Repositories: where VPM packages come from, and choosing a version of one.

VRChat's official and curated repositories are always there (unless ALCOM's own settings leave them out), with the
ones you've added (settings.json's userRepos), each kept in Repos/ in the Creator Companion's folder as
{"repo": the listing, "headers": ..., "vrc-get": {"etag": ...}}: the file ALCOM and the Creator Companion keep, so
a listing refreshed by any of them is fresh for all. Package folders you've added (userPackageFolders) count as
packages too.

Choosing a version follows vrc-get: the newest that the range allows, that isn't withdrawn ("yanked"), and that
works in the project's Unity; across repositories, the newest of them.
"""
from __future__ import annotations

import itertools
import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .. import egress
from ..safety import DataFileError, clean_text
from . import environment, fetch
from .environment import Settings
from .manifest import Package, unity_compatible
from .version import DENY, UnityVersion, Version, VersionRange

OFFICIAL_URL = "https://packages.vrchat.com/official?download"
CURATED_URL = "https://packages.vrchat.com/curated?download"
OFFICIAL_ID, CURATED_ID = "com.vrchat.repos.official", "com.vrchat.repos.curated"
BUILTIN_NAMES = {OFFICIAL_URL: "Official", CURATED_URL: "Curated"}   # (their own names, before they're first fetched)
MAX_LISTING = 64 << 20
MAX_PACKAGES = 20_000
MAX_VERSIONS = 2_000


class RepoError(Exception):
    """A repository that can't be added, refreshed or removed, in words to show."""


class Repo:
    """One repository, as its cache file has it."""

    def __init__(self, path: Path, url: str | None, headers: dict, setting_name: str | None = None,
                 builtin: bool = False):
        self.path, self.url, self.headers, self.builtin = path, url, headers, builtin
        self.setting_name = setting_name
        self.id: str | None = None
        self.name: str | None = None
        self.etag = ""
        self.raw: dict | None = None      # the listing, as fetched (kept whole, so the cache is written back intact)
        self.packages: dict[str, dict[Version, Package]] = {}
        self.error: str | None = None

    @property
    def loaded(self) -> bool:
        """Has its listing been read?"""
        return self.raw is not None

    def label(self) -> str:
        """The repository's name, as you, its listing or VRChat call it, or its address."""
        return (self.setting_name or self.name or BUILTIN_NAMES.get(self.url) or self.url or self.path.stem)

    def load(self) -> None:
        """Read the repository's kept listing (Repos/), noting why when it can't be."""
        try:
            cache = environment.read_json(self.path, MAX_LISTING)
        except (DataFileError, OSError) as e:
            self.error = str(e)
            return
        if cache is None:
            return
        if self.url is None:   # a local repository: the file is the listing itself
            listing = cache
        else:
            listing = cache.get("repo") if isinstance(cache, dict) else None
            vg = cache.get("vrc-get") if isinstance(cache, dict) else None
            self.etag = vg.get("etag", "") if isinstance(vg, dict) and isinstance(vg.get("etag"), str) else ""
        self._take(listing)

    def _take(self, listing) -> None:
        """Take a listing as this repository's: its id, name and packages, each package checked as it's read."""
        if not isinstance(listing, dict):
            self.error = "its listing isn't one"
            return
        self.raw = listing
        self.id = listing.get("id") if isinstance(listing.get("id"), str) else None
        self.name = clean_text(listing["name"], 200) if isinstance(listing.get("name"), str) else None
        if self.url and not isinstance(listing.get("url"), str):
            listing["url"] = self.url
        if self.id is None:
            self.id = listing.get("url") if isinstance(listing.get("url"), str) else self.url
        packages = listing.get("packages")
        self.packages = {}
        for name, entry in itertools.islice(packages.items() if isinstance(packages, dict) else (), MAX_PACKAGES):
            versions = entry.get("versions") if isinstance(entry, dict) else None
            if not isinstance(versions, dict):
                continue
            found = {}
            for text, raw in itertools.islice(versions.items(), MAX_VERSIONS):
                p = Package.parse(raw)   # (a version described badly is left out, as vrc-get does)
                if p is not None and p.name == name and Version.maybe(text) == p.version:
                    found[p.version] = p
            if found:
                self.packages[name] = found

    def save(self) -> None:
        """Keep the listing in Repos/, as ALCOM and the Creator Companion keep it, with its headers and ETag."""
        cache = {"repo": self.raw}
        if self.headers:
            cache["headers"] = self.headers
        if self.etag:
            cache["vrc-get"] = {"etag": self.etag}
        environment.write_json(self.path, cache)

    def refresh(self) -> bool:
        """Fetch the listing again (unless it hasn't changed): True when it changed."""
        if not self.url:
            return False
        try:
            data, etag = fetch.get_json_bytes(self.url, self.headers, self.etag or None if self.loaded else None,
                                              MAX_LISTING)
        except fetch.FetchError as e:
            self.error = str(e)
            return False
        if data is None:
            return False
        listing = _parse_listing(data)
        if listing is None:
            self.error = "it didn't send a package listing"
            return False
        old_id = self.id
        self._take(listing)
        if old_id and not isinstance(listing.get("id"), str):
            listing["id"] = self.id = old_id
        self.etag = etag or ""
        self.error = None
        self.save()
        return True


def _parse_listing(data: bytes):
    """A repository's listing from its bytes (a byte-order mark allowed); None when it isn't JSON with packages."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        listing = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    return listing if isinstance(listing, dict) and isinstance(listing.get("packages"), dict) else None


class Selector:
    """Which versions of a package will do: one exact version, the newest (stable only, or prereleases too), or
    those a range (or several ranges) allows; for a project's Unity, when one is given."""

    def __init__(self, kind: str, unity: UnityVersion | None = None, version: Version | None = None,
                 ranges: tuple = (), prerelease: str = DENY, include_pre: bool = False):
        self.kind, self.unity, self.version, self.ranges = kind, unity, version, ranges
        self.prerelease, self.include_pre = prerelease, include_pre

    @classmethod
    def specific(cls, version: Version) -> "Selector":
        """Choose exactly this version."""
        return cls("specific", version=version)

    @classmethod
    def latest(cls, unity: UnityVersion | None, include_pre: bool) -> "Selector":
        """Choose the newest version that works in this Unity (a prerelease only with include_pre)."""
        return cls("latest", unity=unity, include_pre=include_pre)

    @classmethod
    def range(cls, unity: UnityVersion | None, r: VersionRange, prerelease: str) -> "Selector":
        """Choose the newest version in range r that works in this Unity, under the prerelease rule."""
        return cls("range", unity=unity, ranges=(r,), prerelease=prerelease)

    @classmethod
    def all_of(cls, unity: UnityVersion | None, ranges, prerelease: str) -> "Selector":
        """Choose the newest version in every one of these ranges that works in this Unity."""
        return cls("range", unity=unity, ranges=tuple(ranges), prerelease=prerelease)

    def satisfies(self, p: Package) -> bool:
        """Is this package version one the selector chooses (not withdrawn, right for the Unity, in range)?"""
        if self.kind == "specific":
            return p.version == self.version
        if p.yanked or (self.unity is not None and not unity_compatible(p, self.unity)):
            return False
        if self.kind == "latest":
            return self.include_pre or not p.version.is_pre
        return all(r.match_pre(p.version, self.prerelease) for r in self.ranges)


class Info:
    """A version of a package and where it's from: a repository, or a package folder of yours."""
    __slots__ = ("package", "repo", "folder")

    def __init__(self, package: Package, repo: Repo | None = None, folder: Path | None = None):
        self.package, self.repo, self.folder = package, repo, folder

    @property
    def name(self) -> str:
        """The package's name."""
        return self.package.name

    @property
    def version(self) -> Version:
        """The package's version."""
        return self.package.version

    def __repr__(self):
        return f"Info({self.name}@{self.version} from {self.repo.label() if self.repo else self.folder})"


def same_address(a, b) -> bool:
    """Two repository addresses that lead to the same listing, told apart only by the case of the scheme and host, a
    port that's the scheme's own, or a slash at the end: https://vcc.vrcfury.com and https://VCC.vrcfury.com/ are one."""
    return isinstance(a, str) and isinstance(b, str) and bool(a.strip()) and _address(a) == _address(b)


def _address(url: str) -> str:
    """A repository's address, written one way (lower-case host, no default port, no trailing slash), to tell whether
    two addresses are the same repository."""
    try:
        u = urlsplit(url.strip())
        port = u.port
    except ValueError:
        return url.strip().rstrip("/")
    scheme = u.scheme.lower()
    host = (u.hostname or "").lower() + (f":{port}" if port and port != {"https": 443, "http": 80}.get(scheme) else "")
    return f"{scheme}://{host}{u.path.rstrip('/')}" + (f"?{u.query}" if u.query else "")


class Collection:
    """Every package Hoard can install: the repositories' and your package folders'."""

    def __init__(self, repos: list[Repo], local: list[tuple[Path, Package]]):
        self.repos, self.local = repos, local

    @classmethod
    def load(cls, settings: Settings) -> "Collection":
        """Every repository's kept listing, and the packages in your package folders."""
        repos = [r for r in _sources(settings)]
        for r in repos:
            r.load()
        local = []
        for folder in settings.user_package_folders():
            try:
                raw = environment.read_json(Path(folder) / "package.json", 4 << 20)
            except (DataFileError, OSError):
                continue
            p = Package.parse(raw, loose=True)
            if p is not None:
                local.append((Path(folder), p))
        return cls(repos, local)

    def refresh(self) -> list[str]:
        """Fetch every repository's listing again: the ones that couldn't be, with why."""
        failed = []
        for r in self.repos:
            if r.url:
                r.refresh()
                if r.error:
                    failed.append(f"{r.label()}: {r.error}")
        return failed

    def fetch_missing(self) -> list[str]:
        """Fetch the repositories with no listing kept here yet (VRChat's, on a computer where neither ALCOM nor the
        Creator Companion has fetched it): the ones that couldn't be, with why."""
        failed = []
        for r in self.repos:
            if r.url and not r.loaded:
                r.refresh()
                if r.error:
                    failed.append(f"{r.label()}: {r.error}")
        return failed

    def loaded(self) -> list[Repo]:
        """The repositories whose listings could be read."""
        return [r for r in self.repos if r.loaded]

    def has_repo(self, url: str | None, repo_id: str | None = None) -> Repo | None:
        """The repository already here at this address (as it's listed, or as its listing gives its own), or with
        this id: so one added in ALCOM or the Creator Companion under another spelling isn't added again."""
        for r in self.repos:
            own = r.raw.get("url") if r.raw else None
            if same_address(url, r.url) or same_address(url, own) or (repo_id and r.id == repo_id):
                return r
        return None

    def provides(self, name: str) -> Repo | None:
        """A repository here that has this package, if any does."""
        return next((r for r in self.loaded() if name in r.packages), None)

    def versions(self, name: str) -> list[Info]:
        """Every version of a package there is, from every repository and package folder."""
        out = [Info(p, repo=r) for r in self.loaded() for p in r.packages.get(name, {}).values()]
        out += [Info(p, folder=f) for f, p in self.local if p.name == name]
        return out

    def find(self, name: str, selector: Selector) -> Info | None:
        """The version to use: across every repository and package folder, the newest the selector allows (for one
        exact version, that one even if it's yanked)."""
        best = None
        for r in self.loaded():
            versions = r.packages.get(name)
            if not versions:
                continue
            if selector.kind == "specific":
                p = versions.get(selector.version)
            else:
                fits = [p for p in versions.values() if selector.satisfies(p)]
                p = max(fits, key=lambda p: p.version) if fits else None
            if p is not None and (best is None or p.version >= best.version):
                best = Info(p, repo=r)
        for folder, p in self.local:
            if p.name == name and selector.satisfies(p) and (best is None or p.version >= best.version):
                best = Info(p, folder=folder)
        return best

    def names(self) -> set[str]:
        """Every package name there is, in any repository or package folder."""
        return {n for r in self.loaded() for n in r.packages} | {p.name for _, p in self.local}

    def newest(self, unity: UnityVersion | None, include_pre: bool) -> list[Info]:
        """Each package's newest version for this Unity (or, when none works in it, its newest at all)."""
        out = []
        for name in sorted(self.names()):
            found = self.find(name, Selector.latest(unity, include_pre)) or self.find(name, Selector.latest(None, include_pre))
            if found is None and not include_pre:
                found = self.find(name, Selector.latest(None, True))
            if found is not None:
                out.append(found)
        return out


def _sources(settings: Settings) -> list[Repo]:
    """Every repository the Creator Companion and ALCOM use: VRChat's official and curated ones (unless ALCOM's settings
    leave them out), then yours, each with its kept listing's file."""
    folder = settings.folder
    own = environment.vrc_get_settings(folder)
    out = []
    if own.get("ignoreOfficialRepository") is not True:
        out.append(Repo(folder / "Repos" / "vrc-official.json", OFFICIAL_URL, {}, builtin=True))
    if own.get("ignoreCuratedRepository") is not True:
        out.append(Repo(folder / "Repos" / "vrc-curated.json", CURATED_URL, {}, builtin=True))
    for entry in settings.user_repos():
        headers = entry.get("headers") if isinstance(entry.get("headers"), dict) else {}
        headers = {k: v for k, v in headers.items() if isinstance(k, str) and isinstance(v, str)}
        url = entry.get("url") if isinstance(entry.get("url"), str) else None
        name = entry.get("name") if isinstance(entry.get("name"), str) else None
        out.append(Repo(Path(entry["localPath"]), url, headers, name and clean_text(name, 200)))
    return out


# ---- adding and removing repositories (settings.json's userRepos), as ALCOM does

_HEADER_NAME = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,100}")


def check_headers(headers) -> dict:
    """The headers a repository asks Hoard to send (a key, say), checked: at most 20, plain names, no line breaks;
    raises RepoError otherwise."""
    if not headers:
        return {}
    if not isinstance(headers, dict) or len(headers) > 20:
        raise RepoError("Those headers can't be used.")
    out = {}
    for k, v in headers.items():
        if not (isinstance(k, str) and _HEADER_NAME.fullmatch(k) and isinstance(v, str) and len(v) <= 4000
                and not any(c in v for c in "\r\n\0")):
            raise RepoError(f"The header {str(k)[:40]!r} can't be used.")
        out[k] = v
    return out


def add_repo(settings: Settings, url: str, name: str | None = None, headers: dict | None = None) -> Repo:
    """Fetch a repository's listing and add it, as ALCOM's "Add repository" does. Raises RepoError (already
    added, unreachable, not a listing)."""
    url = (url or "").strip()
    if not (url.startswith("https://") or egress._test_origin(url)) or len(url) > 2000 or any(c.isspace() for c in url):
        raise RepoError("Enter the repository's address, starting https://.")
    headers = check_headers(headers)
    if any(same_address(url, u) for u in (OFFICIAL_URL, CURATED_URL)) or any(same_address(e.get("url"), url) for e in settings.user_repos()):
        raise RepoError("That repository is already added.")
    try:
        data, etag = fetch.get_json_bytes(url, headers, None, MAX_LISTING)
    except fetch.FetchError as e:
        raise RepoError(f"The repository couldn't be fetched: {e}.") from None
    listing = _parse_listing(data or b"")
    if listing is None:
        raise RepoError("That address doesn't lead to a VPM repository listing.")
    if not isinstance(listing.get("url"), str):
        listing["url"] = url
    repo_id = listing.get("id") if isinstance(listing.get("id"), str) else url
    listing.setdefault("id", repo_id)
    if repo_id in (OFFICIAL_ID, CURATED_ID) or any(e.get("id") == repo_id for e in settings.user_repos()) \
            or Collection.load(settings).has_repo(listing["url"], repo_id):   # (its listing's own address, or id)
        raise RepoError("That repository is already added.")
    folder = settings.folder / "Repos"
    folder.mkdir(parents=True, exist_ok=True)
    file_name = f"{repo_id}.json" if re.fullmatch(r"[0-9A-Za-z._-]{1,150}", repo_id) and repo_id not in (
        "vrc-official", "vrc-curated", "package-cache") else f"{uuid.uuid4()}.json"
    while (folder / file_name).exists():
        file_name = f"{uuid.uuid4()}.json"
    repo = Repo(folder / file_name, url, headers, name and clean_text(name, 200))
    repo._take(listing)
    repo.etag = etag or ""
    repo.save()
    entry = {"localPath": str(repo.path), "url": url, "id": repo_id, "headers": headers}
    shown = (name and clean_text(name, 200)) or repo.name
    if shown:
        entry["name"] = shown
    settings.add_repo(entry)
    settings.save()
    return repo


def remove_repo(settings: Settings, local_path: str) -> bool:
    """Take a repository out of the list, and delete its cache file when it's one in Repos/."""
    gone = settings.remove_repos({local_path})
    if not gone:
        return False
    settings.save()
    cache = Path(gone[0]["localPath"])   # (the settings' own copy of it)
    try:
        if cache.parent.resolve() == (settings.folder / "Repos").resolve() and cache.suffix == ".json" and cache.is_file():
            cache.unlink()
    except OSError:
        pass
    return True
