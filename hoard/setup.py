"""First-run setup: what Hoard's onboarding assistant checks and does.

The assistant (in the Library page) walks through: the browser Hoard uses to sign in to stores, which stores
you use, signing in to each, Payhip shops, the downloads folder, and bringing over an older Hoard. Everything it
does is also available on its own, so it can be run again from Settings at any time.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .browser import _cookie_hosts, _on_sites, _playwright, channel_installed, chosen_channel, profile_dir, STORE_SITES
from .config import payhip_shops, root_dir, save_config
from .library import STORES, Library
from .paths import LIBRARY_FILE, default_downloads
from .safety import DataFileError, read_json_file

BROWSER_NAMES = {"msedge": "Microsoft Edge", "chrome": "Google Chrome", "chromium": "Hoard's own browser"}


def own_browser_installed() -> bool:
    """Is Playwright's Chromium (Hoard's own browser) downloaded?"""
    try:
        with _playwright()() as p:
            return Path(p.chromium.executable_path).is_file()
    except Exception:
        return False


def browser_status(cfg: dict) -> dict:
    """Which browser Hoard will use to sign in to stores, and whether it's ready."""
    channel = chosen_channel(cfg)
    if channel in ("msedge", "chrome") and channel_installed(channel):
        return {"channel": channel, "name": BROWSER_NAMES[channel], "ready": True, "can_install": False, "note": ""}
    # Hoard's own browser: chosen, or standing in for a chosen browser that isn't installed (use_channel)
    ready = own_browser_installed()
    note = ""
    if channel != "chromium":
        note = (f"{BROWSER_NAMES[channel]} isn't installed on this computer, so Hoard uses its own browser"
                + ("." if ready else " once it's installed."))
    if not ready and sys.platform.startswith("linux"):
        note += (" " if note else "") + "On Linux the browser may also need system libraries: python -m playwright install-deps chromium"
    return {"channel": "chromium", "name": BROWSER_NAMES["chromium"], "ready": ready, "can_install": not ready, "note": note}


def install_browser(progress) -> None:
    """Download Hoard's own browser (Playwright's Chromium), reporting progress. The same as
    `python -m playwright install chromium`, without anyone needing a command line."""
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    node, cli = compute_driver_executable()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen([str(node), str(cli), "install", "chromium"], env=get_driver_env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=flags)
    buf = b""
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        *lines, buf = buf.replace(b"\r", b"\n").split(b"\n")   # progress bars redraw with \r
        for line in lines:
            text = line.decode("utf-8", "replace").strip()
            if text:
                progress(text)
    if proc.wait() != 0:
        raise RuntimeError("the browser download didn't finish. Check your connection and try again.")


def browser_problem(error: BaseException) -> str | None:
    """A plain explanation when an error means the sign-in browser is missing, or None."""
    text = str(error)
    if "Executable doesn't exist" in text or "playwright install" in text:
        return "Hoard's browser isn't installed yet. Open Settings, choose Set up Hoard, and install it; it takes a minute."
    if "distribution" in text and "is not found" in text:
        return ("The browser chosen in Settings isn't installed on this computer. Choose another in Settings, or open "
                "Set up Hoard to install Hoard's own browser.")
    return None


def signed_in(cfg: dict, store: str) -> bool:
    """Does Hoard hold a sign-in for this store? (Cookies for the store's site in its profile; whether the store
    still accepts them is only known when Hoard next reads the store.)"""
    profile = profile_dir(cfg, store)
    return profile.exists() and any(_on_sites(h, STORE_SITES[store]) for h in _cookie_hosts(profile))


def setup_status(cfg: dict) -> dict:
    """Everything the assistant shows, in one go."""
    return {
        "done": bool(cfg.get("setup_done")),
        "browser": browser_status(cfg),
        "stores": {s: {"label": STORES[s]["label"], "enabled": bool(cfg[s].get("enabled", True)),
                       "signed_in": signed_in(cfg, s)} for s in STORES},
        "payhip_shops": payhip_shops(cfg),
        "root": str(root_dir(cfg)), "default_root": str(default_downloads()),
    }


def migrate_from(cfg: dict, folder: Path, config_path: Path | None, lib: Library | None = None) -> str:
    """Bring a Hoard 1.x setup across: its library list and its downloads folder. (Sign-ins and tags already live
    in Hoard's app-data folder, so they carry over by themselves.) Returns what was done, in words."""
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        return f"There's no folder at {folder}."
    places = [folder, folder / "Hoard", folder / "HoardDownloader", folder.parent / "Hoard", folder.parent / "HoardDownloader"]
    done, notes = [], []
    old_list = next((p / "library.json" for p in places if (p / "library.json").is_file()), None)
    if old_list:
        new = lib or Library(LIBRARY_FILE)   # the running app's own list, when there is one
        if new.data["items"]:
            n = len(new.data["items"])
            notes.append(f"Hoard already has a library list ({n} {'item' if n == 1 else 'items'}), so the old one wasn't copied.")
        else:
            with new.lock:
                new.data = Library(old_list).data   # checked and cleaned as it's read
                new.save()
            n = len(new.data["items"])
            done.append(f"your library list ({n} {'item' if n == 1 else 'items'})")
    old_cfg = next((p / "config.json" for p in places if (p / "asset_dl.py").is_file() and (p / "config.json").is_file()), None)
    if old_cfg:
        try:
            old = read_json_file(old_cfg, 1024 * 1024)
        except DataFileError:
            old = {}
        value = str(old.get("root") or "downloads") if isinstance(old, dict) else "downloads"
        root = Path(value).expanduser()
        root = root if root.is_absolute() else (old_cfg.parent / root).resolve()
        if root.is_dir():
            cfg["root"] = str(root)
            for store in STORES:
                if isinstance(old.get(store), dict):
                    cfg[store].update({k: v for k, v in old[store].items()
                                       if k in ("enabled", "include_gifts", "include_archived") and isinstance(v, bool)})
            save_config(cfg, config_path)
            done.append(f"your downloads folder ({root})")
        else:
            notes.append(f"The old downloads folder ({root}) doesn't exist, so it wasn't used.")
    if done:
        return "Brought over " + " and ".join(done) + ". Sign-ins and tags carry over by themselves. " + " ".join(notes)
    return " ".join(notes) or f"Found no earlier Hoard in or next to {folder}. Choose the folder you ran Hoard 1.x from."
