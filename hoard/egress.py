"""Every request Hoard makes for a store's pages, data or files goes through here.

The rules, checked for every hop, including each redirect, which is followed one at a time rather than automatically:

- https only. No plain http, no other schemes, no user names in addresses, no system proxies or .netrc logins.
- Public addresses only. The host is looked up once, every address it gives must be public (not this computer,
  your network, link-local or reserved), and the connection goes to exactly the address that was checked, so a
  name can't answer the check with one address and the connection with another (DNS rebinding).
- A store's cookies only go to that store's own sites. Any other host (a file CDN, a storage bucket) is fetched
  with a separate session that has no cookies at all.

Images from stores' public CDNs have their own small fetcher with the same address rules (safety.fetch_public).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool

from .browser import _on_sites
from .safety import _connect_public, move_into_place, open_part

try:
    from tqdm import tqdm
except ImportError:  # progress bars are optional
    tqdm = None

MAX_HOPS = 8

# Tests only: origins ("http://127.0.0.1:9300") excused from the https and public-address checks, so stand-in stores
# on this computer can be used. The store-site and cookie rules still apply to them. Never set by Hoard itself; a
# security test checks it's empty.
_TEST_ORIGINS: set[str] = set()


class UnsafeRequest(Exception):
    """A request, or a redirect, that Hoard refuses to make."""


class _PublicConnection(HTTPSConnection):
    """An HTTPS connection that reaches only an address checked to be public, then verifies the certificate
    for the host name as usual."""

    def _new_conn(self):
        """Connect to exactly the checked public address."""
        return _connect_public(self._dns_host, self.port, self.timeout)


class _PublicPool(HTTPSConnectionPool):
    ConnectionCls = _PublicConnection


class _PublicAdapter(HTTPAdapter):
    """requests' adapter, with every https connection going through the public-only connection."""

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"https": _PublicPool}


class _Refuse(HTTPAdapter):
    """For every scheme but https: refuse."""

    def send(self, request, **kwargs):
        raise UnsafeRequest(f"refused a plain {urlparse(request.url).scheme} request")


def session(user_agent: str = "") -> requests.Session:
    """A new session that only makes https requests to public addresses, ignoring system proxies and .netrc."""
    s = requests.Session()
    s.trust_env = False
    # (Redirects are never followed by requests itself: every call passes allow_redirects=False and follows them
    # one checked hop at a time. Don't set max_redirects = 0 here: requests checks it even then, and would refuse
    # every redirect answer outright.)
    s.mount("https://", _PublicAdapter())
    s.mount("http://", _Refuse())
    if user_agent:
        s.headers["User-Agent"] = user_agent
    return s


def _test_origin(url: str) -> bool:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}" in _TEST_ORIGINS


def check_hop(url: str) -> None:
    """Refuse anything but a plain https address (addresses themselves are checked when connecting)."""
    if _test_origin(url):
        return
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise UnsafeRequest(f"refused {u.scheme or 'an'} address {u.hostname or url[:60]!r}: only https is allowed")


def _send(store_sess: requests.Session, anon: requests.Session, url: str, sites, **kwargs) -> requests.Response:
    """One hop: the store's session for its own sites, the cookie-free one for anything else."""
    check_hop(url)
    host = urlparse(url).hostname or ""
    sess = store_sess if _on_sites(host, sites) else anon
    if _test_origin(url):   # tests only: stand-in stores on this computer, plain http
        plain = requests.Session()
        plain.trust_env = False
        plain.cookies = sess.cookies
        plain.headers.update(sess.headers)
        sess = plain
    return sess.get(url, allow_redirects=False, **kwargs)


def get(store_sess: requests.Session, url: str, sites, *, stay_on_sites: bool = True, follow: bool = True,
        **kwargs) -> requests.Response:
    """GET a store page or API, following redirects one checked hop at a time. With stay_on_sites (the default for
    pages and APIs), a redirect off the store's own sites is refused rather than followed. With follow=False,
    the first answer is returned as it is, redirect or not."""
    anon = session(store_sess.headers.get("User-Agent", ""))
    timeout = kwargs.pop("timeout", 60)
    for _ in range(MAX_HOPS):
        r = _send(store_sess, anon, url, sites, timeout=timeout, **kwargs)
        if not r.is_redirect or not follow:
            return r
        nxt = urljoin(url, r.headers.get("Location", ""))
        r.close()
        if stay_on_sites and not _on_sites(urlparse(nxt).hostname or "", sites):
            raise UnsafeRequest(f"{urlparse(url).hostname} redirected off its own site, to {urlparse(nxt).hostname}")
        kwargs.pop("params", None)   # the redirect's address already says what it wants
        url = nxt
    raise UnsafeRequest("too many redirects")


def _content_range(r: requests.Response) -> tuple[int, int, int | None] | None:
    """A 206 answer's Content-Range, as (first byte, last byte, the whole file's size or None), or None when it has
    none that makes sense."""
    m = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", (r.headers.get("Content-Range") or "").strip())
    if not m:
        return None
    first, last, whole = int(m[1]), int(m[2]), None if m[3] == "*" else int(m[3])
    return None if last < first or (whole is not None and last >= whole) else (first, last, whole)


def _whole_size(r: requests.Response) -> int | None:
    """The file's size from a 416 answer's Content-Range ("bytes */1234"), or None."""
    m = re.fullmatch(r"bytes \*/(\d+)", (r.headers.get("Content-Range") or "").strip())
    return int(m[1]) if m else None


def _length(r: requests.Response) -> int | None:
    try:
        n = int(r.headers.get("Content-Length") or "")
    except ValueError:
        return None
    return n if n >= 0 else None


def download(store_sess: requests.Session, url: str, dest: Path, sites, desc: str = "") -> int:
    """Download url to dest through a .part file (resuming one left from last time), following redirects one checked
    hop at a time. Returns the file's size. Refuses anything that isn't https to a public address.

    A .part file is only added to when the store answers with exactly the part that follows it (206, Content-Range
    starting where the .part file ends), and only counts as finished when the store says the file ends there (416,
    Content-Range naming that size). Anything else starts the file again rather than joining two different ones. A
    file is only put in place once it's as long as the store said it would be; otherwise the .part file is kept, and
    the next sync resumes it. The file's own bytes are asked for (no compression), so every size is exact."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    anon = session(store_sess.headers.get("User-Agent", ""))
    try:
        have = os.stat(part, follow_symlinks=False).st_size if part.is_file() and not part.is_symlink() else 0
    except OSError:
        have = 0
    for _ in range(MAX_HOPS):
        r = _send(store_sess, anon, url, sites, stream=True, timeout=(20, 300),
                  headers={"Accept-Encoding": "identity", **({"Range": f"bytes={have}-"} if have else {})})
        with r:
            if r.is_redirect:
                url = urljoin(url, r.headers.get("Location", ""))
                continue
            if have and r.status_code == 416:   # nothing past the end of the .part file
                if _whole_size(r) == have:      # and the store says the file ends there: the .part file is all of it
                    fh, identity = open_part(part, resume=True)
                    fh.close()
                    move_into_place(part, dest, identity)
                    return dest.stat().st_size
                have = 0    # the file on the store isn't the one the .part file was part of: start again
                continue
            encoded = r.headers.get("Content-Encoding", "identity").lower() != "identity"
            span = _content_range(r) if r.status_code == 206 else None
            if r.status_code == 206 and (span is None or span[0] != have or encoded):
                if not have:
                    raise RuntimeError("the store sent only part of the file, in a way that can't be checked")
                have = 0    # not the part that follows the .part file: never added to it; the whole file is asked for
                continue
            resume = r.status_code == 206 and have > 0
            if r.status_code != 206:
                r.raise_for_status()
                have = 0    # the whole file, from the start
            if r.headers.get("Content-Type", "").startswith("text/html") and not dest.suffix.lower().startswith(".htm"):
                raise RuntimeError("store returned a web page instead of the file (file may be unavailable)")
            length = _length(r)
            if encoded:
                expected = None     # compressed on the way despite asking not to: its length isn't the file's
            elif span and span[2] is not None:
                expected = span[2]
            else:
                expected = have + length if length is not None else None
            bar = tqdm(total=expected, initial=have, unit="B", unit_scale=True, unit_divisor=1024,
                       desc=desc[:40], leave=False) if tqdm else None
            written = have
            fh, identity = open_part(part, resume=resume)
            with fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    written += len(chunk)
                    if bar:
                        bar.update(len(chunk))
            if bar:
                bar.close()
            if expected is not None and written != expected:
                raise RuntimeError(f"the download stopped at {written} of {expected} bytes; the next sync resumes it")
            move_into_place(part, dest, identity)
            return dest.stat().st_size
    raise UnsafeRequest("too many redirects")
