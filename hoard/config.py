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
    "library_folders": [],         # other library folders, besides root, read as one library (hoard/libraries.py)
    "edits_root": "",              # where editable copies go (issue #82); "" = "Hoard Edits" beside the downloads
    "local_copy": True,            # Local (issue #80): copy what you add into Hoard (False: list it where it is); your last choice
    "request_delay": 1.0,          # seconds between page loads on a store, to stay polite
    "browser_channel": "",         # "" = automatic (Microsoft Edge on Windows); "chromium", "msedge" or "chrome"
    "profile_dir": "",             # "" = Hoard's private sign-in folder (one profile per store)
    "advanced_signin_location": False,   # only then is profile_dir used; never a network location
    "allow_unprotected_signins": False,  # Linux without a keyring only: keep sign-ins protected by folder permissions
    "automated_sign_in": False,    # sign in in a window Hoard drives, as before 2.11 (Google and Discord refuse those)
    "offline_images": True,        # save every product image after a refresh, so the library works offline
    "check_for_updates": False,    # ask GitHub once a day, when Hoard starts, whether there's a newer version
    "close_to_taskbar": True,   # closing Hoard's window minimizes it to the taskbar (the Dock), and Hoard carries on
    "auto_sync_hours": 0,          # while Hoard is open, sync by itself this often (0 = only when you choose Sync)
    "new_days": 7,                 # how long something that just appeared in your library is marked New (0 = never)
    "download_retries": 2,         # a file download that fails is tried again this many more times
    "integrity_check_days": 7,     # check the downloads are as downloaded this often (issue #83); 0 = only when asked
    "display": {"text_size": 100, "pause_animations": False, "reduce_motion": False},   # accessibility
    "ui": {},                      # how you left the pages: the sidebar folded, the tile size
    "gumroad": {"enabled": True, "include_archived": True, "save_thumbnails": True},
    "booth": {"enabled": True, "include_gifts": True, "include_free": True, "save_thumbnails": True},
    "jinxxy": {"enabled": True, "item_link_pattern": "^/my/(inventory|purchases|library)/[^/]+/?$",
               "save_thumbnails": True, "download_start_timeout": 90},
    "payhip": {"enabled": True, "shops": [], "headed": True, "bot_check_wait": 180},   # read only: never downloaded
    "itch": {"enabled": True, "skip_game_builds": True, "save_thumbnails": True},   # through its API, with your key
    "tags": {"min_count": 3, "max_share": 0.4, "min_length": 2, "extra_stopwords": [], "blocklist": []},
}


# Stores added since Hoard was first released. An install that was set up before one came keeps the stores it
# chose: the new store starts switched off there (Settings turns it on), rather than showing up unasked, with a
# "not signed in" warning after the next sync. New installs choose in the setup assistant, where it's ticked.
NEW_STORES = ("itch",)


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
    if any(label.startswith("xn--") for label in host.split(".")):
        return None               # internationalised names can be made to look like other names
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in host.split(".")):
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


class NewShop(Exception):
    """A saved page came from a Payhip shop that isn't in your list; adding it needs your say-so."""

    def __init__(self, shop: str):
        self.shop = shop
        super().__init__(f"This page is from the Payhip shop {shop.split('://', 1)[1]}, which isn't in your list. "
                         "Confirm to add it, or add it in Settings first.")


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
                for store in NEW_STORES:
                    if saved.get("setup_done") and store not in saved:
                        cfg[store]["enabled"] = False   # set up before this store came: off until you turn it on
        except DataFileError as e:
            print(f"Settings: {e}. Using the defaults.", flush=True)
    apply_store_sites(cfg)
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    """Write the settings to config.json."""
    write_file_safely(path or CONFIG_FILE, json.dumps(cfg, indent=2, ensure_ascii=False))


def edits_dir(cfg: dict) -> Path:
    """Where editable copies of downloads go (issue #82): the chosen folder, else "Hoard Edits" beside the downloads
    folder. Never inside the downloads folder, which Hoard checks and keeps as the stores sent it."""
    value = str(cfg.get("edits_root") or "").strip()
    root = root_dir(cfg)
    if value:
        chosen = Path(os.path.expandvars(value)).expanduser()
        return chosen if chosen.is_absolute() else Path.home() / chosen
    return root.parent / "Hoard Edits"


def root_dir(cfg: dict) -> Path:
    """Where downloads go: the chosen folder, or Documents/Hoard. A relative path is taken from your home folder."""
    value = str(cfg.get("root") or "").strip()
    if not value:
        return default_downloads()
    root = Path(os.path.expandvars(value)).expanduser()
    return root if root.is_absolute() else Path.home() / root
