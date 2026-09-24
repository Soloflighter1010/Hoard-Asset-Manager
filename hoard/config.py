"""Hoard's settings: one set for everything, kept in config.json in Hoard's app-data folder."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import CONFIG_FILE, default_downloads
import ipaddress
import re
from urllib.parse import urlparse

from .safety import DataFileError, read_json_file, set_extra_sites, write_file_safely

DEFAULT_CONFIG = {
    "setup_done": False,           # set once the onboarding assistant has been completed (or skipped)
    "root": "",                    # where downloads go; "" = a Hoard folder in Documents
    "request_delay": 1.0,          # seconds between page loads on a store, to stay polite
    "browser_channel": "",         # "" = automatic (Microsoft Edge on Windows); "chromium", "msedge" or "chrome"
    "profile_dir": "",             # "" = Hoard's private sign-in folder (one profile per store)
    "allow_unprotected_signins": False,  # Linux without a keyring only: keep sign-ins protected by folder permissions
    "offline_images": True,        # save every product image after a refresh, so the library works offline
    "gumroad": {"enabled": True, "include_archived": True, "save_thumbnails": True},
    "booth": {"enabled": True, "include_gifts": True, "include_free": True, "save_thumbnails": True},
    "jinxxy": {"enabled": True, "item_link_pattern": "^/my/(inventory|purchases|library)/[^/]+/?$",
               "save_thumbnails": True, "download_start_timeout": 90},
    "payhip": {"enabled": True, "shops": [], "library_url": "", "headed": True, "bot_check_wait": 180,
               "download_start_timeout": 90, "save_thumbnails": True},
    "tags": {"min_count": 3, "max_share": 0.4, "min_length": 2, "extra_stopwords": [], "blocklist": []},
}


def clean_payhip_shop(value) -> str | None:
    """A Payhip shop's address as Hoard keeps it, or None if it isn't one.

    Payhip keeps your purchases in each shop you bought from, not in one library. A shop is either on its own
    domain ("myshop.store", kept as https://myshop.store) or on Payhip ("payhip.com/SomeShop", kept as
    https://payhip.com/SomeShop). Only plain https web addresses are accepted: no IP addresses, ports, names
    without a dot, or user names.
    """
    text = str(value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        u = urlparse(text)
        port = u.port
    except ValueError:
        return None
    host = (u.hostname or "").rstrip(".").lower()
    if u.scheme not in ("https", "http") or u.username or u.password or port not in (None, 443, 80) or "." not in host:
        return None
    if not re.fullmatch(r"[a-z0-9.-]+", host) or host.startswith(("-", ".")) or host in ("localhost",):
        return None
    try:
        ipaddress.ip_address(host)
        return None               # a raw IP address isn't a shop
    except ValueError:
        pass
    parts = [p for p in u.path.split("/") if p]
    if parts and parts[-1] in ("b-account", "b-account.html"):
        parts = parts[:-1]
    if host in ("payhip.com", "www.payhip.com"):
        if len(parts) != 1 or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", parts[0]):
            return None           # on payhip.com, a shop is payhip.com/<ShopName>
        return f"https://payhip.com/{parts[0]}"
    return f"https://{host}"


def payhip_shops(cfg: dict) -> list[str]:
    """The Payhip shops in your settings, as clean addresses, without repeats."""
    shops = cfg.get("payhip", {}).get("shops") or []
    return list(dict.fromkeys(s for s in (clean_payhip_shop(x) for x in shops if isinstance(x, str)) if s))


def apply_store_sites(cfg: dict) -> None:
    """Count the Payhip shops in these settings as Payhip's own sites (for links, downloads and checks)."""
    set_extra_sites("payhip", [urlparse(s).hostname for s in payhip_shops(cfg) if urlparse(s).hostname != "payhip.com"])


def deep_merge(dst: dict, src: dict) -> dict:
    """Copy src into dst, merging nested dicts instead of replacing them. Returns dst."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_config(path: Path | None = None) -> dict:
    """The built-in defaults, overlaid with config.json when it exists (and can be read)."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = path or CONFIG_FILE
    if path.exists():
        try:
            saved = read_json_file(path, 1024 * 1024)
            if isinstance(saved, dict):
                deep_merge(cfg, saved)
        except DataFileError as e:
            print(f"Settings: {e}. Using the defaults.", flush=True)
    apply_store_sites(cfg)
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    """Write the settings to config.json."""
    write_file_safely(path or CONFIG_FILE, json.dumps(cfg, indent=2, ensure_ascii=False))


def root_dir(cfg: dict) -> Path:
    """Where downloads go: the chosen folder, or Documents/Hoard. A relative path is taken from your home folder."""
    value = str(cfg.get("root") or "").strip()
    if not value:
        return default_downloads()
    root = Path(os.path.expandvars(value)).expanduser()
    return root if root.is_absolute() else Path.home() / root
