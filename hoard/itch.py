"""itch.io, through its API, with an API key you create on itch.io: what you own, each project's files, and the files
themselves. itch.io puts a Cloudflare check in front of automated browsers that never lets them through, so Hoard
uses the API itch.io's own desktop app uses instead of its website.

The key is kept by vault.py, never in config.json. Every request goes through egress.py, and the key goes in one
header that's only ever sent to api.itch.io: a file's download address redirects to a file host, which egress
reaches with a session that carries nothing of yours.
"""
from __future__ import annotations

import time
import uuid
from urllib.parse import urlencode, urlparse

import requests

from . import __version__, egress
from .common import NotLoggedIn

API = "https://api.itch.io"
KEYS_PAGE = "https://itch.io/user/settings/api-keys"   # where you make one
SYSTEMS = (("p_windows", "Windows"), ("p_osx", "macOS"), ("p_linux", "Linux"), ("p_android", "Android"))


class KeyRefused(NotLoggedIn):
    """itch.io didn't accept the API key (mistyped, or deleted on itch.io)."""


def sites() -> list[str]:
    """The only host that ever gets the key."""
    return [urlparse(API).hostname]


def session(key: str) -> requests.Session:
    """A session that sends the key to api.itch.io, and only there (see egress)."""
    s = egress.session(f"Hoard/{__version__}")
    s.headers.update({"Authorization": f"Bearer {key}", "Accept": "application/json"})
    return s


def call(sess: requests.Session, path: str, **params) -> dict:
    """One API request. Raises KeyRefused when itch.io turns the key away."""
    r = egress.get(sess, API + path, sites(), params=params or None, timeout=60)
    if r.status_code in (401, 403):
        raise KeyRefused("itch.io didn't accept the API key")
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError("itch.io's answer wasn't the data Hoard asked for") from None
    if not isinstance(data, dict):
        raise RuntimeError("itch.io's answer wasn't the data Hoard asked for")
    errors = data.get("errors")
    if errors:
        text = "; ".join(str(e) for e in errors)[:300] if isinstance(errors, list) else str(errors)[:300]
        if "key" in text.lower() or "auth" in text.lower():
            raise KeyRefused(f"itch.io didn't accept the API key ({text})")
        raise RuntimeError(f"itch.io said: {text}")
    return data


def profile(sess: requests.Session) -> dict:
    """The account the key belongs to."""
    user = call(sess, "/profile").get("user")
    return user if isinstance(user, dict) else {}


def owned_keys(sess: requests.Session, delay: float = 0.0, progress=lambda m: None) -> list[dict]:
    """Everything you own on itch.io, bought or claimed: one download key per project."""
    found: dict = {}
    for page in range(1, 2000):
        data = call(sess, "/profile/owned-keys", page=page)
        keys = [k for k in (data.get("owned_keys") or []) if isinstance(k, dict) and isinstance(k.get("game"), dict)]
        new = [k for k in keys if k.get("id") not in found]
        for k in new:
            found[k.get("id")] = k
        progress(f"Library, {len(found)} items")
        try:
            per_page = int(data.get("per_page") or 50)
        except (TypeError, ValueError):
            per_page = 50
        if not new or len(data.get("owned_keys") or []) < per_page:
            break
        time.sleep(delay)
    return list(found.values())


def game_of(key: dict) -> dict:
    """The project a download key is for, with its creator."""
    game = key.get("game") if isinstance(key.get("game"), dict) else {}
    user = game.get("user") if isinstance(game.get("user"), dict) else {}
    return {"id": game.get("id") or key.get("game_id"), "title": game.get("title"), "url": game.get("url"),
            "cover": game.get("still_cover_url") or game.get("cover_url"),
            "creator": user.get("display_name") or user.get("username"), "creator_url": user.get("url")}


def uploads(sess: requests.Session, game_id, key_id) -> list[dict]:
    """A project's files, as your download key opens them."""
    data = call(sess, f"/games/{int(game_id)}/uploads", download_key_id=int(key_id))
    return [u for u in (data.get("uploads") or []) if isinstance(u, dict) and u.get("id")]


def systems(upload: dict) -> list[str]:
    """The operating systems a file is marked for, as a game build (asset files hardly ever are)."""
    traits = set(upload.get("traits") or []) if isinstance(upload.get("traits"), list) else set()
    return [name for flag, name in SYSTEMS if flag in traits or upload.get(flag) is True]


def download_address(upload_id, key_id) -> str:
    """Where a file downloads from: api.itch.io, which redirects to the file itself."""
    return f"{API}/uploads/{int(upload_id)}/download?" + urlencode({"download_key_id": int(key_id), "uuid": str(uuid.uuid4())})
