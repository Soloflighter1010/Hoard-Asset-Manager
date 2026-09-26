"""Updating Hoard: is there a newer release on GitHub, and, for the installed Windows app, getting and running it.

What it asks, and when: GitHub's list of Hoard's releases (api.github.com), when you choose Check for updates in
Settings, or once a day when Hoard starts if you've turned on "Check for updates automatically" (off unless you
do). GitHub sees your IP address and "Hoard/<version>", as with any page you open there; nothing else is sent.

Updating (only in the app installed with Hoard-Setup, on Windows): the new version's Hoard-Setup-<version>.exe is
downloaded through egress (https to public addresses only, redirects checked one at a time) into updates/ in
Hoard's app-data folder, and only kept when its SHA-256 matches both the one GitHub lists for the file and the
release's SHA256SUMS-windows.txt. Hoard then quits cleanly (a download in progress resumes next time), runs it,
and the installer opens the new Hoard when it's done. Your settings, library, sign-ins and downloads aren't
touched: an update replaces only the program files.

Everything else (the portable zip, pip, other systems) is told there's a newer version, with a link to it.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, egress
from .paths import data_dir
from .safety import DataFileError, read_json_file, write_file_safely

REPO = "Soloflighter1010/Hoard-Asset-Manager"
API = "https://api.github.com"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
TAG = re.compile(r"v(\d{1,4})\.(\d{1,4})\.(\d{1,4})")    # Hoard's own releases (not unity-v..., not anything else)
SETUP_NAME = "Hoard-Setup-{}.exe"
SUMS_NAME = "SHA256SUMS-windows.txt"
MAX_SETUP = 400 * 1024 * 1024
MAX_SUMS = 64 * 1024
DAY = 24 * 60 * 60
INSTALLER_ARGS = ("/SILENT", "/SP-", "/NORESTART", "/RELAUNCH=1")   # see packaging/hoard.iss: RelaunchAfterUpdate


class UpdateRefused(Exception):
    """A download that isn't the file the release says it is, or a release Hoard can't use."""


def version_of(text) -> tuple[int, int, int] | None:
    """"2.6.0" or "v2.6.0" as numbers, or None when it isn't a Hoard version."""
    text = str(text or "")
    m = TAG.fullmatch(text if text.startswith("v") else "v" + text)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def newer(candidate: str, than: str = __version__) -> bool:
    a, b = version_of(candidate), version_of(than)
    return bool(a and b and a > b)


def _file_path() -> Path:
    return data_dir() / "update.json"


def updates_dir() -> Path:
    return data_dir() / "updates"


def installed_copy() -> bool:
    """Is this the app Hoard-Setup installed on Windows (not the portable zip, pip or source)? The installer
    leaves its uninstaller next to Hoard.exe; the portable zip never has one."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    return any(Path(sys.executable).parent.glob("unins*.exe"))


def _session():
    s = egress.session(f"Hoard/{__version__}")
    s.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    return s


def complete(release: dict) -> bool:
    """A release as the release workflow makes it: with its Windows installer and the checksums to check it by.
    One without them (say, published by hand from the Releases page) is never offered: it couldn't be installed,
    and as the highest version it would hide the release that can."""
    v = version_of(release.get("tag_name"))
    return bool(v and _asset(release, SETUP_NAME.format(".".join(map(str, v)))) and _asset(release, SUMS_NAME))


def pick_latest(releases) -> dict | None:
    """The newest published Hoard release in GitHub's list: not a draft, not a pre-release, tagged vX.Y.Z, and
    complete (see complete())."""
    best = None
    for r in releases if isinstance(releases, list) else []:
        if not isinstance(r, dict) or r.get("draft") or r.get("prerelease"):
            continue
        v = version_of(r.get("tag_name")) if str(r.get("tag_name") or "").startswith("v") else None
        if v and complete(r) and (best is None or v > best[0]):
            best = (v, r)
    return best[1] if best else None


def _asset(release: dict, name: str) -> dict | None:
    return next((a for a in release.get("assets") or [] if isinstance(a, dict) and a.get("name") == name), None)


def describe(release: dict) -> dict:
    """What the page shows about a release."""
    version = ".".join(map(str, version_of(release["tag_name"])))
    url = str(release.get("html_url") or "")
    return {"version": version, "notes": str(release.get("body") or "")[:4000],
            "url": url if url.startswith(f"https://github.com/{REPO}/") else RELEASES_PAGE,
            "published": str(release.get("published_at") or "")[:40],
            "has_installer": bool(_asset(release, SETUP_NAME.format(version)) and _asset(release, SUMS_NAME))}


def fetch_latest() -> dict | None:
    """Ask GitHub for Hoard's releases (one request) and return the newest, or None when there's none."""
    r = egress.get(_session(), f"{API}/repos/{REPO}/releases", [urlparse(API).hostname], params={"per_page": 30},
                   timeout=20)
    if r.status_code == 403 or r.status_code == 429:
        raise RuntimeError("GitHub asked Hoard to slow down. Try again in an hour.")
    r.raise_for_status()
    try:
        return pick_latest(r.json())
    except ValueError:
        raise RuntimeError("GitHub's answer wasn't the list of releases Hoard asked for") from None


def parse_sums(text: str) -> dict[str, str]:
    """SHA256SUMS lines ("<64 hex>  <name>") as {name: hash}."""
    sums = {}
    for line in text.splitlines():
        m = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(\S.*?)\s*", line.strip().lstrip("\ufeff"))
        if m:
            sums[m[2]] = m[1].lower()
    return sums


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_hash(release: dict, name: str, sums_text: str) -> str:
    """The SHA-256 a release's file must have: the one in its SHA256SUMS file, and the one GitHub lists for the file
    (when it does) must agree. Raises UpdateRefused when there's no hash, or they don't."""
    from_sums = parse_sums(sums_text).get(name)
    if not from_sums:
        raise UpdateRefused(f"the release's {SUMS_NAME} doesn't list {name}, so it can't be checked")
    digest = str((_asset(release, name) or {}).get("digest") or "")
    if digest.startswith("sha256:") and digest[7:].lower() != from_sums:
        raise UpdateRefused(f"GitHub and the release's {SUMS_NAME} disagree about {name}")
    return from_sums


def download_installer(release: dict, progress=lambda m: None) -> Path:
    """Download a release's Hoard-Setup and check it (see the module's notes). Returns where it is. A file that
    doesn't check out is deleted, never run."""
    info = describe(release)
    name = SETUP_NAME.format(info["version"])
    setup, sums = _asset(release, name), _asset(release, SUMS_NAME)
    if not setup or not sums:
        raise UpdateRefused(f"Hoard {info['version']} has no Windows installer to update with")
    size = setup.get("size")
    if not isinstance(size, int) or not 0 < size <= MAX_SETUP:
        raise UpdateRefused("the installer isn't a size Hoard expects")
    sess = egress.session(f"Hoard/{__version__}")   # files come from GitHub's file hosts: nothing but the name
    progress("Checking the release")
    r = egress.get(sess, str(sums.get("browser_download_url") or ""), [], stay_on_sites=False, timeout=30)
    r.raise_for_status()
    if len(r.content) > MAX_SUMS:
        raise UpdateRefused(f"the release's {SUMS_NAME} is too large")
    want = expected_hash(release, name, r.content.decode("utf-8", "replace"))
    folder = updates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    progress(f"Downloading Hoard {info['version']}")
    try:
        egress.download(sess, str(setup.get("browser_download_url") or ""), dest, [], desc=name)
        if dest.stat().st_size != size:
            raise UpdateRefused("the installer isn't the size GitHub lists for it")
        if sha256_of(dest) != want:
            raise UpdateRefused("the installer doesn't match the release's checksum, so Hoard deleted it")
    except BaseException:
        dest.unlink(missing_ok=True)
        dest.with_name(dest.name + ".part").unlink(missing_ok=True)
        raise
    write_file_safely(dest.with_name(dest.name + ".sha256"), want)
    return dest


def ready_installer(path: Path) -> bool:
    """Is path a downloaded installer that still matches the checksum it was checked against?"""
    try:
        want = path.with_name(path.name + ".sha256").read_text("utf-8").strip()
        return (path.parent == updates_dir() and path.is_file() and not path.is_symlink()
                and re.fullmatch(r"[0-9a-f]{64}", want) is not None and sha256_of(path) == want)
    except OSError:
        return False


def run_installer(path: Path) -> bool:
    """Start a checked installer, on its own, after Hoard has stopped. It closes nothing of yours (Hoard has already
    quit) and opens the new Hoard when it's finished. Returns whether it started."""
    if not ready_installer(path):
        print(f"Didn't run {path.name}: it no longer matches its checksum.")
        return False
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([str(path), *INSTALLER_ARGS], close_fds=True, creationflags=flags, cwd=str(path.parent))
    except OSError as e:
        print(f"Couldn't start the update ({e}). It's in {path.parent}: run it yourself.")
        return False
    print(f"Updating with {path.name}")
    return True


def tidy() -> None:
    """Delete installers for this version or older: an update that finished leaves its installer behind."""
    folder = updates_dir()
    if not folder.is_dir():
        return
    for f in folder.iterdir():
        m = re.fullmatch(r"Hoard-Setup-(\d+\.\d+\.\d+)\.exe(\.sha256|\.part)?", f.name)
        if m and not newer(m[1]):
            try:
                f.unlink()
            except OSError:
                pass


class Updates:
    """The server's view of updates: the last check, and an update being downloaded. One at a time."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._lock = threading.Lock()
        try:
            saved = read_json_file(_file_path()) if _file_path().is_file() else {}
        except (DataFileError, OSError):
            saved = {}
        saved = saved if isinstance(saved, dict) else {}
        latest = saved.get("latest")
        latest = latest if isinstance(latest, dict) and version_of(latest.get("version")) else None
        checked = saved.get("checked")
        checked = float(checked) if isinstance(checked, (int, float)) else 0.0
        self.state = {"current": __version__, "checked": checked, "latest": latest, "busy": False, "message": "",
                      "error": ""}
        self.pending: Path | None = None   # checked and waiting to run once Hoard has stopped

    def view(self, can_install: bool) -> dict:
        latest = self.state["latest"]
        available = bool(latest and newer(latest.get("version", "")))
        return {**self.state, "available": available, "can_install": bool(can_install and available
                and latest.get("has_installer")), "auto": bool(self.cfg.get("check_for_updates")),
                "releases_page": RELEASES_PAGE}

    def _save(self) -> None:
        try:
            write_file_safely(_file_path(), json.dumps({"checked": self.state["checked"], "latest": self.state["latest"]}))
        except OSError:
            pass

    def check(self) -> dict:
        """Ask GitHub now. Raises when it can't be reached or answers strangely; the last answer is kept."""
        release = fetch_latest()
        with self._lock:
            self.state.update(checked=time.time(), latest=describe(release) if release else None, error="")
            self._save()
        return self.state

    def due(self) -> bool:
        return bool(self.cfg.get("check_for_updates")) and time.time() - self.state["checked"] > DAY

    def check_in_background(self) -> None:
        """At start, when automatic checks are on and the last was over a day ago."""
        if not self.due():
            return

        def run():
            try:
                self.check()
            except Exception as e:
                print(f"Couldn't check for updates ({type(e).__name__}: {e})")
        threading.Thread(target=run, daemon=True, name="update-check").start()

    def start_install(self, on_ready) -> str | None:
        """Download and check the newest release's installer in the background, then call on_ready() (which quits
        Hoard, so it runs). Returns why it can't start, or None."""
        with self._lock:
            if self.state["busy"]:
                return "Hoard is already getting the update."
            self.state.update(busy=True, message="Starting", error="")

        def run():
            try:
                release = fetch_latest()
                if not release or not newer(describe(release)["version"]):
                    raise UpdateRefused("Hoard is up to date.")
                self.state["latest"] = describe(release)
                path = download_installer(release, lambda m: self.state.update(message=m))
                self.pending = path
                self.state.update(message="Closing Hoard to update")
                on_ready()
            except Exception as e:
                why = str(e) if isinstance(e, (UpdateRefused, egress.UnsafeRequest)) else f"{type(e).__name__}: {e}"
                print(f"The update didn't download ({why})")
                self.state.update(busy=False, message="", error=f"The update didn't download: {why}"[:400])
        threading.Thread(target=run, daemon=True, name="update").start()
        return None


def finish(updates: "Updates | None") -> bool:
    """After Hoard has stopped: run the installer that was downloaded, if there is one."""
    path = getattr(updates, "pending", None)
    return bool(path) and run_installer(path)


__all__ = ["Updates", "finish", "tidy", "installed_copy", "newer", "pick_latest", "RELEASES_PAGE"]
