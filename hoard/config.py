"""Hoard's settings: one set for everything, kept in config.json in Hoard's app-data folder."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import CONFIG_FILE, default_downloads
from .safety import DataFileError, read_json_file, write_file_safely

DEFAULT_CONFIG = {
    "root": "",                    # where downloads go; "" = a Hoard folder in Documents
    "request_delay": 1.0,          # seconds between page loads on a store, to stay polite
    "browser_channel": "",         # "" = automatic (Microsoft Edge on Windows); "chromium", "msedge" or "chrome"
    "profile_dir": "",             # "" = Hoard's private sign-in folder (one profile per store)
    "allow_unprotected_signins": False,  # Linux without a keyring only: keep sign-ins protected by folder permissions
    "offline_images": True,        # save every product image after a refresh, so the library works offline
    "gumroad": {"enabled": True, "include_archived": True, "save_thumbnails": True},
    "booth": {"enabled": True, "include_gifts": True, "save_thumbnails": True},
    "jinxxy": {"enabled": True, "item_link_pattern": "^/my/(inventory|purchases|library)/[^/]+/?$",
               "save_thumbnails": True, "download_start_timeout": 90},
    "payhip": {"enabled": True, "library_url": "", "headed": True, "bot_check_wait": 180,
               "download_start_timeout": 90, "save_thumbnails": True},
    "tags": {"min_count": 3, "max_share": 0.4, "min_length": 2, "extra_stopwords": [], "blocklist": []},
}


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
