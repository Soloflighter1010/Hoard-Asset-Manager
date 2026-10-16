"""Fetching repositories and packages: https to public addresses only, as every request Hoard makes.

A repository can ask for headers (a key for a private repository, say), and a package can add its own. They go to
the repository's own host only: a redirect to another host (GitHub sends its release files to a storage host) is
followed without them, so a key never reaches a host it wasn't meant for. Each redirect is checked like the first
request (egress.check_hop), one hop at a time.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from .. import __version__, egress

MAX_HOPS = 8
USER_AGENT = f"Hoard/{__version__} (Hoard Asset Manager; +https://github.com/Soloflighter1010/Hoard-Asset-Manager)"
# (VRChat's package server refuses a request whose user agent doesn't name the program, its version and where to find it)
STALL_SECONDS = 120


class FetchError(Exception):
    """A repository or package that couldn't be fetched, in words to show."""


def _session() -> requests.Session:
    return egress.session(USER_AGENT)


def _send(sess, url: str, headers: dict, **kwargs) -> requests.Response:
    egress.check_hop(url)
    if egress._test_origin(url):   # tests only: a stand-in repository on this computer
        plain = requests.Session()
        plain.trust_env = False
        plain.headers.update(sess.headers)
        sess = plain
    return sess.get(url, headers=headers, allow_redirects=False, **kwargs)


def _hops(sess, url: str, headers: dict, plain: dict | None = None, **kwargs) -> tuple[requests.Response, str]:
    """GET url, following redirects; headers go to its own host only, plain ones to every host."""
    host = urlparse(url).hostname
    for _ in range(MAX_HOPS):
        own = urlparse(url).hostname == host
        r = _send(sess, url, {**(plain or {}), **(headers if own else {})}, **kwargs)
        if not r.is_redirect:
            return r, url
        nxt = urljoin(url, r.headers.get("Location", ""))
        r.close()
        url = nxt
    raise FetchError("it redirected too many times")


def get_json_bytes(url: str, headers: dict | None = None, etag: str | None = None,
                   max_bytes: int = 64 << 20, timeout: int = 60) -> tuple[bytes | None, str | None]:
    """A repository's listing: (its bytes, its ETag), or (None, the ETag) when it hasn't changed since etag."""
    want = dict(headers or {})
    if etag:
        want["If-None-Match"] = etag
    try:
        with _session() as sess:
            r, _ = _hops(sess, url, want, stream=True, timeout=(20, timeout))
            with r:
                if etag and r.status_code == 304:
                    return None, etag
                if r.status_code >= 400:
                    raise FetchError(f"the server answered {r.status_code}")
                data = bytearray()
                for chunk in r.iter_content(1 << 16):
                    data += chunk
                    if len(data) > max_bytes:
                        raise FetchError("the listing is larger than any real one")
                return bytes(data), r.headers.get("ETag")
    except egress.UnsafeRequest as e:
        raise FetchError(str(e)) from None
    except requests.RequestException as e:
        raise FetchError(_why(e)) from None


def download(url: str, dest: Path, headers: dict | None = None, max_bytes: int = 4 << 30, progress=None) -> str:
    """Download a package's zip to dest (through dest.part), returning its SHA-256. progress(bytes, whole or None)
    is called as it comes in, and may raise to stop."""
    part = dest.with_name(dest.name + ".part")
    sha = hashlib.sha256()
    try:
        with _session() as sess:
            r, _ = _hops(sess, url, dict(headers or {}), {"Accept-Encoding": "identity"}, stream=True,
                         timeout=(20, STALL_SECONDS))
            with r:
                if r.status_code >= 400:
                    raise FetchError(f"the server answered {r.status_code}")
                try:
                    whole = int(r.headers.get("Content-Length") or "")
                except ValueError:
                    whole = None
                if whole is not None and whole > max_bytes:
                    raise FetchError("the package is larger than any real one")
                dest.parent.mkdir(parents=True, exist_ok=True)
                got, said = 0, 0.0
                with open(part, "wb") as fh:
                    for chunk in r.iter_content(1 << 18):
                        fh.write(chunk)
                        sha.update(chunk)
                        got += len(chunk)
                        if got > max_bytes:
                            raise FetchError("the package is larger than any real one")
                        if progress and time.monotonic() - said >= 0.5:
                            said = time.monotonic()
                            progress(got, whole)
                if whole is not None and got != whole:
                    raise FetchError(f"the download stopped at {got} of {whole} bytes")
        os.replace(part, dest)
    except egress.UnsafeRequest as e:
        raise FetchError(str(e)) from None
    except requests.RequestException as e:
        raise FetchError(_why(e)) from None
    finally:
        if part.exists():
            part.unlink(missing_ok=True)
    return sha.hexdigest()


def _why(e: Exception) -> str:
    from ..net import is_network_error, plain_error
    if is_network_error(e):
        return "it couldn't be reached (is this computer online?)"
    return plain_error(e)
