"""Store sign-ins and the browser Hoard drives to read stores."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from .net import reachable
from .paths import HERE, data_dir


class Blocked(Exception):
    """The store showed a bot check or refused the automated browser."""


# ----------------------------------------------------------------------------- browser

def _playwright():
    """Import Playwright's sync API, or exit with a clear message when setup hasn't been run."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright isn't installed. Run Setup.bat (Windows) or ./setup.sh first.")
    return sync_playwright


# ----------------------------------------------------------------------------- sign-ins
#
# Each store's sign-in lives in its own browser profile, used by Hoard alone (never your everyday
# browser), in your user account's private app-data folder: Hoard/sign-ins/<store>. Keeping stores
# apart means one store's pages never share a browser with another store's sign-in, signing out of a
# store deletes that store's folder outright, and the two tools can work with different stores at once.
#
# The browser encrypts saved cookies with the operating system's protection: your Windows account
# (DPAPI), the macOS Keychain, or a Linux keyring (the Secret Service or KWallet). On a Linux computer
# without a keyring the browser would fall back to a publicly known key, so Hoard refuses to save
# sign-ins there unless you allow it in config.json ("allow_unprotected_signins").

LEGACY_PROFILE = HERE / ".browser-profile"   # before 1.2: one profile next to the program


STORE_SITES = {
    "booth": ["booth.pm", "pixiv.net"],        # Booth signs in through pixiv
    "gumroad": ["gumroad.com"],
    "jinxxy": ["jinxxy.com"],
    "payhip": ["payhip.com"],
}


STORE_ORIGINS = {
    "booth": ["https://booth.pm", "https://accounts.booth.pm", "https://www.pixiv.net", "https://accounts.pixiv.net"],
    "gumroad": ["https://gumroad.com", "https://app.gumroad.com"],
    "jinxxy": ["https://jinxxy.com", "https://www.jinxxy.com"],
    "payhip": ["https://payhip.com"],
}


# Pages that show whether you're signed in (a sign-in form means you're not), and where to sign out.
STORE_ACCOUNT_PAGES = {
    "booth": "https://accounts.booth.pm/library",
    "gumroad": "https://app.gumroad.com/library",
    "jinxxy": "https://jinxxy.com/my/inventory",
    "payhip": "https://payhip.com/account",
}


GUMROAD_SIGN_OUT = "https://app.gumroad.com/logout"   # Gumroad's own sign-out address


SIGN_OUT_JS = r"""
() => {
  const label = /^(log ?out|sign ?out|ログアウト)$/i;
  const items = [...document.querySelectorAll('a, button, [role="menuitem"], input[type="submit"]')];
  const el = items.find(e => label.test((e.innerText || e.value || e.getAttribute('aria-label') || '').trim()))
    || items.find(e => /log_?out|sign_?out/i.test(e.getAttribute('href') || ''));
  if (!el) return false;
  setTimeout(() => el.click(), 0);
  return true;
}
"""


# Playwright normally starts Chromium with a fixed, publicly known cookie key on Linux and macOS.
# Dropping these two switches lets Chromium use the real keyring or Keychain instead.
WEAK_KEY_SWITCHES = ["--password-store=basic", "--use-mock-keychain"]


class ProfileBusy(Exception):
    """The other Hoard tool is using this store's sign-in right now."""


class SigninsUnprotected(Exception):
    """This computer has no keyring to protect sign-ins, and unprotected ones aren't allowed."""


def app_data_dir() -> Path:
    """Hoard's folder in this user account's private app-data location, per operating system."""
    return data_dir()


def signins_root(cfg: dict) -> Path:
    """The folder holding one profile per store. config.json's profile_dir can move it."""
    value = (cfg.get("profile_dir") or "").strip()
    if value and Path(value).name != ".browser-profile":  # that name was the pre-1.2 default: ignore it
        p = Path(os.path.expandvars(value)).expanduser()
        return p if p.is_absolute() else HERE / p
    return app_data_dir() / "sign-ins"


def profile_dir(cfg: dict, store: str) -> Path:
    """Where one store's sign-in is kept."""
    return signins_root(cfg) / store


def _lock_down(path: Path) -> None:
    """Create a folder and, on Linux and macOS, make it and Hoard's folder readable only by you."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":  # Windows keeps app data private to your account already
        for p in (path, path.parent, path.parent.parent):
            if p.name in ("Hoard", "sign-ins") or p == path:
                os.chmod(p, 0o700)


class ProfileLock:
    """Keeps two Hoard programs from using one store's sign-in at once. The OS drops it if a program crashes."""

    def __init__(self, profile: Path):
        """Prepare a lock file next to the profile; nothing is locked until acquire()."""
        self.path = profile.parent / (profile.name + ".lock")
        self.fh = None

    def acquire(self) -> None:
        """Lock the sign-in for this program, or raise ProfileBusy if another program has it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            self.fh = None
            raise ProfileBusy(f"The other Hoard tool is using your {self.path.stem.title()} sign-in right now. "
                              "Try again when it has finished.")

    def release(self) -> None:
        """Unlock the sign-in. Safe to call more than once."""
        if self.fh:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.fh.seek(0)
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
                self.fh.close()
            except OSError:
                pass
            self.fh = None


def _remove_tree(path: Path) -> None:
    """Delete a folder tree, clearing read-only flags that would otherwise stop Windows deleting it."""
    def retry(func, p, _exc):
        os.chmod(p, 0o700)
        func(p)
    shutil.rmtree(path, onerror=retry)


def _dbus_names() -> set[str]:
    """Names on the desktop's D-Bus session bus, running or startable on demand. Empty without one."""
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return set()
    names: set[str] = set()
    for method in ("ListNames", "ListActivatableNames"):
        for cmd in (["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
                     "/org/freedesktop/DBus", "--method", f"org.freedesktop.DBus.{method}"],
                    ["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.DBus",
                     "/org/freedesktop/DBus", f"org.freedesktop.DBus.{method}"]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            names |= {a or b for a, b in re.findall(r"'([\w.]+)'|\"([\w.]+)\"", out)}
            break
    return names


def linux_keyring() -> str | None:
    """The keyring Chromium can use on this Linux desktop ("gnome-libsecret" or "kwallet5/6"), or None."""
    if not sys.platform.startswith("linux"):
        return None
    names = _dbus_names()
    if "org.freedesktop.secrets" in names:        # GNOME Keyring, KeePassXC and other Secret Service keyrings
        return "gnome-libsecret"
    if "org.kde.kwalletd6" in names:
        return "kwallet6"
    if "org.kde.kwalletd5" in names:
        return "kwallet5"
    return None


def signin_protection(cfg: dict) -> str:
    """How saved sign-ins are protected on this computer, in words."""
    if sys.platform == "win32":
        return "encrypted by your Windows account"
    if sys.platform == "darwin":
        return "encrypted with your macOS Keychain"
    keyring = linux_keyring()
    if keyring:
        return "encrypted with your " + ("KWallet" if keyring.startswith("kwallet") else "Secret Service keyring")
    if cfg.get("allow_unprotected_signins"):
        return "protected only by folder permissions, because this computer has no keyring"
    return "not saved, because this computer has no keyring to protect them"


def _cookie_rows(profile: Path, query: str) -> list:
    """Run a read-only query on a profile's cookie database (a copy, so a running browser isn't disturbed)."""
    import sqlite3
    import tempfile
    for rel in ("Default/Network/Cookies", "Default/Cookies"):
        db = profile / rel
        if db.is_file():
            with tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp) / "Cookies"
                shutil.copyfile(db, copy)
                con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
                try:
                    return con.execute(query).fetchall()
                except sqlite3.Error:
                    return []
                finally:
                    con.close()
    return []


def unprotected_cookie_count(profile: Path) -> int:
    """On Linux, how many saved cookies use the browser's fixed fallback key ("v10") instead of a keyring ("v11")."""
    if not sys.platform.startswith("linux"):
        return 0
    rows = _cookie_rows(profile, "SELECT encrypted_value, value FROM cookies")
    return sum(1 for enc, plain in rows if (bytes(enc or b"")[:3] == b"v10") or (plain or ""))


def _cookie_hosts(profile: Path) -> set[str]:
    """The sites a profile holds cookies for."""
    return {h.lstrip(".") for (h,) in _cookie_rows(profile, "SELECT DISTINCT host_key FROM cookies")}


def _on_sites(host: str, sites: list[str]) -> bool:
    """True when host is one of the sites, or a subdomain of one."""
    host = host.lstrip(".")
    return any(host == s or host.endswith("." + s) for s in sites)


def default_channel() -> str:
    """The browser Hoard uses unless you choose one: Microsoft Edge on Windows, where every PC has it and Windows
    Update keeps it patched; otherwise the Chromium that comes with Playwright."""
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base and (Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe").is_file():
                return "msedge"
    return "chromium"


def _launch(p, cfg: dict, profile: Path, headless: bool):
    """Start Chromium on a profile with the strongest cookie protection this computer offers."""
    kwargs = dict(user_data_dir=str(profile), headless=headless, accept_downloads=True,
                  viewport={"width": 1400, "height": 950}, ignore_default_args=WEAK_KEY_SWITCHES)
    if sys.platform.startswith("linux"):
        keyring = linux_keyring()
        if keyring:
            kwargs["args"] = [f"--password-store={keyring}"]
        elif cfg.get("allow_unprotected_signins"):
            kwargs["args"] = ["--password-store=basic"]   # the user chose this in config.json
        else:
            raise SigninsUnprotected(
                "This computer has no keyring to protect store sign-ins, so Hoard won't save them. Install and "
                "unlock one (GNOME Keyring, KeePassXC with Secret Service turned on, or KWallet), then try again. "
                "On a computer without a desktop you can instead set \"allow_unprotected_signins\": true in "
                "config.json; sign-ins are then protected only by your user account's folder permissions.")
    channel = cfg.get("browser_channel") or default_channel()
    if channel != "chromium":
        kwargs["channel"] = channel
    return p.chromium.launch_persistent_context(**kwargs)


_migrated = False


def _migrate_old_signins(p, cfg: dict) -> None:
    """Split sign-ins saved by older versions (one profile for every store) into a profile per store."""
    global _migrated
    if _migrated:
        return
    root = signins_root(cfg)
    old_places = []   # (folder, how it was started)
    if (root / "Local State").exists() or (root / "Default").exists():   # 1.2 to 1.5: one shared profile
        shared = root.parent / (root.name + ".old")
        guard = ProfileLock(root)                     # the lock those versions used
        guard.acquire()
        try:
            if shared.exists():
                _remove_tree(shared)
            staging = root.parent / (root.name + ".moving")
            os.replace(root, staging)
            root.mkdir(parents=True, exist_ok=True)
            os.replace(staging, shared)
        finally:
            guard.release()
        old_places.append((shared, "1.2"))
    elif (root.parent / (root.name + ".old")).exists():  # an earlier move that stopped part-way
        old_places.append((root.parent / (root.name + ".old"), "1.2"))
    value = (cfg.get("profile_dir") or "").strip()
    legacy = [LEGACY_PROFILE]
    if value and Path(value).name == ".browser-profile":
        v = Path(os.path.expandvars(value)).expanduser()
        legacy.append(v if v.is_absolute() else HERE / v)
    old_places += [(o, "1.0") for o in dict.fromkeys(x.resolve() for x in legacy) if o.is_dir()]

    for old, era in old_places:
        start = {} if era == "1.0" else {"ignore_default_args": WEAK_KEY_SWITCHES}  # read with the key it was saved under
        src = p.chromium.launch_persistent_context(str(old), headless=True, **start)
        try:
            cookies = src.cookies()
        finally:
            src.close()
        for store, sites in STORE_SITES.items():
            mine = [c for c in cookies if _on_sites(c["domain"], sites)]
            if not mine:
                continue
            target = profile_dir(cfg, store)
            lock = ProfileLock(target)
            lock.acquire()
            try:
                _lock_down(target)
                dst = _launch(p, cfg, target, headless=True)
                try:
                    dst.add_cookies(mine)
                finally:
                    dst.close()
            finally:
                lock.release()
        _remove_tree(old)
        print(f"Moved your sign-ins from {old} into a separate folder for each store under {root}", flush=True)
    _migrated = True


def launch_context(p, cfg: dict, headless: bool, store: str):
    """Open Hoard's browser with one store's saved sign-in. Close it with ctx.close()."""
    _migrate_old_signins(p, cfg)
    target = profile_dir(cfg, store)
    lock = ProfileLock(target)
    lock.acquire()
    try:
        _lock_down(target)
        ctx = _launch(p, cfg, target, headless)
    except BaseException:
        lock.release()
        raise
    ctx.on("close", lambda _ctx: lock.release())
    return ctx


def check_saved_signin(cfg: dict, store: str) -> None:
    """After signing in: make sure the saved sign-in really is encrypted, or delete it and say why."""
    target = profile_dir(cfg, store)
    if cfg.get("allow_unprotected_signins") or not unprotected_cookie_count(target):
        return
    _remove_tree(target)
    raise SigninsUnprotected(
        f"Your {store.title()} sign-in was saved without your keyring's protection (the keyring may be locked), so "
        "Hoard deleted it. Unlock your keyring and sign in again.")


def _signed_out_page(page) -> bool:
    """True when the open page is a sign-in page."""
    url = page.url.lower()
    return any(w in url for w in ("login", "sign_in", "signin")) or page.locator("input[type=password]").count() > 0


def _end_store_session(p, cfg: dict, profile: Path, store: str) -> bool:
    """Ask the store to end the session (best effort). True when the store then shows this browser as signed out."""
    try:
        ctx = _launch(p, cfg, profile, headless=True)
    except Exception:
        return False
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if store == "gumroad":
            page.goto(GUMROAD_SIGN_OUT, wait_until="domcontentloaded", timeout=20000)
        else:
            page.goto(STORE_ACCOUNT_PAGES[store], wait_until="domcontentloaded", timeout=20000)
            settle(page)
            if _signed_out_page(page):
                return True  # the store already treats this browser as signed out
            if not page.evaluate(SIGN_OUT_JS):
                return False
        settle(page, 1500)
        page.goto(STORE_ACCOUNT_PAGES[store], wait_until="domcontentloaded", timeout=20000)
        settle(page)
        return _signed_out_page(page)
    except Exception:
        return False
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def sign_out(p, cfg: dict, store: str, online: bool | None = None) -> str:
    """Sign out of a store (or "all"): end the session on the store's side when possible, delete the saved
    sign-in, check nothing is left behind, and say what was done."""
    if store == "all":
        done = [sign_out(p, cfg, s, online) for s in STORE_SITES]
        root = signins_root(cfg)
        for extra in (root.parent / (root.name + ".old"), LEGACY_PROFILE):
            if extra.exists():
                _remove_tree(extra)
        return "\n".join(done)
    label = store.title()
    target = profile_dir(cfg, store)
    if not target.exists():
        return f"{label}: no saved sign-in."
    if online is None:
        online = reachable(store)
    lock = ProfileLock(target)
    lock.acquire()
    try:
        count = (_cookie_rows(target, "SELECT COUNT(*) FROM cookies") or [(0,)])[0][0]
        remote = _end_store_session(p, cfg, target, store) if online else None
        _remove_tree(target)
    finally:
        lock.release()
    if target.exists():
        raise RuntimeError(f"Couldn't delete {target}. Close any Hoard window using it and try again.")
    # no other store's folder should hold this store's cookies; if one somehow does, clear them there too
    for other in STORE_SITES:
        other_dir = profile_dir(cfg, other)
        if other != store and other_dir.exists() and any(_on_sites(h, STORE_SITES[store]) for h in _cookie_hosts(other_dir)):
            ctx = launch_context(p, cfg, True, other)
            try:
                for site in STORE_SITES[store]:
                    ctx.clear_cookies(domain=re.compile(rf"(^|\.){re.escape(site)}$"))
            finally:
                ctx.close()
    said = f"{label}: deleted the saved sign-in ({count} {'cookie' if count == 1 else 'cookies'}, plus the store's site data)."
    if remote:
        return said + f" {label} also confirmed you're signed out."
    if remote is None:
        return said + f" You're offline, so {label} wasn't told; sign out on its website to end that session."
    return said + f" Couldn't sign out on {label}'s side; sign out on its website to end that session there too."


launch = launch_context


def settle(page, ms: int = 700) -> None:
    """Give a page time to finish loading: wait for the network to go quiet (at most 15 s), then ms more."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


BOT_CHECK_TITLES = ("just a moment", "attention required", "access denied", "verify you are human", "are you a robot")


def goto(page, url: str):
    """Navigate and fail loudly on an error or bot-check page, so it never looks like an empty library."""
    resp = page.goto(url, wait_until="domcontentloaded")
    status = resp.status if resp is not None else 200
    try:
        title = page.title().lower()
        challenge = page.locator("iframe[src*='challenges.cloudflare.com'], #challenge-form, "
                                 "#cf-wrapper, #cf-challenge-running").count() > 0
    except Exception:
        title, challenge = "", False
    if challenge or any(t in title for t in BOT_CHECK_TITLES) or status in (403, 429, 503):
        raise Blocked(f"{urlparse(url).hostname} answered HTTP {status}" if status >= 400 else "bot check")
    if status >= 400:
        raise RuntimeError(f"{urlparse(url).hostname} answered HTTP {status}")
    return resp


def has_password_field(page) -> bool:
    """True when the page shows a password box, which here means a sign-in form."""
    try:
        return page.locator("input[type=password]").count() > 0
    except Exception:
        return False
