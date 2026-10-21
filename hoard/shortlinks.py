"""Short links for shared sets (Sets, Share..., Make a short link): a set's code kept on Hoard's share server
(share/worker.mjs, a Cloudflare Worker at SERVER) for LIFETIME_DAYS, locked, so its link is short.

Hoard's page locks the code (AES-GCM, with a new random 128-bit key, in the browser: web/shared.js) and gives Hoard
only the locked set to send. The server keeps it under a new id, and answers with a token. The link is the set
viewer's address and "#S1.<id>.<key>": the key is only ever in the link (and in sets.json, to show the link again),
never sent to the server, so the server can't read the set. The token, in sets.json too, is what lets this Hoard
update the set behind the link or delete it; the server keeps only its hash. Opening a short link in Hoard goes the
other way: fetch() gets the locked set, and the page unlocks it.

Every request goes through egress.send (https, public addresses only, no system proxies), with no cookies.
"""
from __future__ import annotations

import re

import requests

from . import __version__, egress

SERVER = "https://hoard-share.furryup.link"
LIFETIME_DAYS = 14
PREFIX = "S1."
ID = re.compile(r"[0-9A-Za-z]{10}")
KEY = re.compile(r"[A-Za-z0-9_-]{22}")              # 128 bits, base64url
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")            # 256 bits, base64url
DATA = re.compile(r"[A-Za-z0-9_-]{42,65536}")       # a locked set, base64url: 31 bytes to 48 KiB
CODE = re.compile(r"S1\.([0-9A-Za-z]{10})\.([A-Za-z0-9_-]{22})")
OFFLINE = "Couldn't reach Hoard's share server. Check your connection, and try again."
TOO_BIG = "This set is too big to share: a short link holds up to about 500 products."


class ShortLinkError(Exception):
    """Why a short link couldn't be made, read, updated or deleted, in words for the page."""


class Gone(ShortLinkError):
    """The server has no set at that id: it ran out, or its sharer deleted it."""


def parse(text) -> tuple[str, str] | None:
    """(id, key) from a short link, or from its code ("S1.<id>.<key>"); None for anything else."""
    if not isinstance(text, str) or len(text) > 2000:
        return None
    text = re.sub(r"\s+", "", text)
    m = CODE.fullmatch(text.split("#", 1)[1] if "#" in text else text)
    return (m[1], m[2]) if m else None


def code(sid: str, key: str) -> str:
    return f"{PREFIX}{sid}.{key}"


def _request(method: str, path: str, *, token: str | None = None, data: str | None = None) -> dict:
    headers = {"Accept": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    try:
        r = egress.send(method, SERVER + path, f"Hoard/{__version__}", headers=headers, timeout=30,
                        json=None if data is None else {"data": data})
    except (requests.RequestException, egress.UnsafeRequest, OSError):   # (refused: a private address for it)
        raise ShortLinkError(OFFLINE) from None
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {}
    if r.status_code == 404:
        raise Gone("That short link has run out (short links last 14 days), or whoever shared it deleted it.")
    if r.status_code == 403:
        raise ShortLinkError("That short link was made by another copy of Hoard, so this one can't change it.")
    if r.status_code == 413:
        raise ShortLinkError(TOO_BIG)
    if r.status_code == 429 or r.status_code >= 500:
        raise ShortLinkError("Hoard's share server is busy. Try again later.")
    if not 200 <= r.status_code < 300 or not isinstance(body, dict):
        raise ShortLinkError(f"Hoard's share server didn't take that ({r.status_code}). Try again later.")
    return body


def _expires(body: dict) -> int:
    e = body.get("expires")
    if not isinstance(e, int) or isinstance(e, bool) or not 0 < e < 2 ** 40:
        raise ShortLinkError(OFFLINE)
    return e


def make(data: str) -> dict:
    """Keep a locked set (base64url) on the server: {"id", "token", "expires" (Unix seconds)}."""
    if not isinstance(data, str) or not DATA.fullmatch(data):
        raise ShortLinkError(TOO_BIG)
    body = _request("POST", "/v1/sets", data=data)
    sid, token = body.get("id"), body.get("token")
    if not (isinstance(sid, str) and ID.fullmatch(sid) and isinstance(token, str) and TOKEN.fullmatch(token)):
        raise ShortLinkError(OFFLINE)
    return {"id": sid, "token": token, "expires": _expires(body)}


def replace(sid: str, token: str, data: str) -> int:
    """The set behind a short link of this Hoard's, as it is now: kept LIFETIME_DAYS from now. Returns when it
    runs out. Raises Gone when the link has already."""
    if not isinstance(data, str) or not DATA.fullmatch(data):
        raise ShortLinkError(TOO_BIG)
    return _expires(_request("PUT", f"/v1/sets/{sid}", token=token, data=data))


def delete(sid: str, token: str) -> None:
    """Delete a short link of this Hoard's now. One that's already gone is fine."""
    try:
        _request("DELETE", f"/v1/sets/{sid}", token=token)
    except Gone:
        pass


def fetch(sid: str) -> dict:
    """The locked set behind a short link: {"data" (base64url), "expires"}. Raises Gone for one that's run out."""
    if not isinstance(sid, str) or not ID.fullmatch(sid):
        raise Gone("That short link has run out (short links last 14 days), or whoever shared it deleted it.")
    body = _request("GET", f"/v1/sets/{sid}")
    data = body.get("data")
    if not isinstance(data, str) or not DATA.fullmatch(data):
        raise ShortLinkError("That short link's set is damaged. Ask whoever shared it for a new one.")
    return {"data": data, "expires": _expires(body)}
