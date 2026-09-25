"""API keys you give Hoard (itch.io's), kept with your operating system's protection, never in config.json.

- Windows: encrypted with your Windows account (DPAPI), in keys/ in Hoard's app-data folder. Only your account on
  this computer can decrypt it.
- macOS: in your login Keychain.
- Linux: in your keyring (the Secret Service: GNOME Keyring, KeePassXC, KWallet's), through secret-tool. Without a
  keyring a key isn't kept, unless you've allowed unprotected sign-ins in config.json
  (allow_unprotected_signins): then it's a file only your account can read, like the sign-ins.

A key never goes on a command line (other accounts can read those on some systems): it's handed over on stdin.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .browser import SigninsUnprotected, linux_keyring
from .paths import data_dir
from .safety import write_file_safely

SERVICE = "Hoard"
KEY_FORMAT = re.compile(r"[A-Za-z0-9_-]{16,200}")


def clean_key(value) -> str | None:
    """An API key as typed or pasted (spaces and quotes around it dropped), or None if it can't be one."""
    text = str(value or "").strip().strip("\"'").strip()
    return text if KEY_FORMAT.fullmatch(text) else None


def _keys_dir() -> Path:
    return data_dir() / "keys"


def _file(name: str, suffix: str) -> Path:
    return _keys_dir() / f"{name}.{suffix}"


# ----------------------------------------------------------------------------- Windows: DPAPI

_ENTROPY = b"Hoard API key"


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Encrypt (or decrypt) with DPAPI, for the signed-in Windows account only."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b: bytes):
        buf = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    source, _keep = blob(data)
    entropy, _keep2 = blob(_ENTROPY)
    out = Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(out)):  # UI_FORBIDDEN
        raise OSError(f"Windows couldn't {'protect' if protect else 'read'} the key (error {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


# ----------------------------------------------------------------------------- the operating systems' stores

def _run(cmd: list[str], stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=30)


def _where(cfg: dict) -> str:
    """Which store keeps keys on this computer: windows, keychain, keyring or file. Raises SigninsUnprotected when
    there's nowhere safe and unprotected keeping isn't allowed."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "keychain"
    if linux_keyring() == "gnome-libsecret" and shutil.which("secret-tool"):
        return "keyring"
    if cfg.get("allow_unprotected_signins"):
        return "file"
    raise SigninsUnprotected(
        "This computer has no keyring to protect your API key, so Hoard won't keep it. Install and unlock one "
        "(GNOME Keyring, or KeePassXC with its Secret Service turned on) with secret-tool, then try again. On a "
        "computer without a desktop you can instead set \"allow_unprotected_signins\": true in config.json.")


def save_key(cfg: dict, name: str, key: str) -> None:
    """Keep an API key (see the module's notes on where)."""
    where = _where(cfg)
    if where == "windows":
        write_file_safely(_file(name, "dpapi"), _dpapi(key.encode(), True))
    elif where == "keychain":
        # `security -i` reads its commands from stdin, so the key never appears on a command line
        r = _run(["security", "-i"], f'add-generic-password -U -s "{SERVICE}" -a "{name}" -w "{key}"\n')
        if r.returncode != 0 or "error" in (r.stderr or "").lower():
            raise OSError(f"the Keychain didn't keep the key ({(r.stderr or '').strip()[:200]})")
    elif where == "keyring":
        r = _run(["secret-tool", "store", f"--label={SERVICE}: {name} API key", "application", "hoard", "key", name], key)
        if r.returncode != 0:
            raise OSError(f"the keyring didn't keep the key ({(r.stderr or '').strip()[:200]})")
    else:
        path = _file(name, "key")
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        write_file_safely(path, key)
        os.chmod(path, 0o600)


def load_key(cfg: dict, name: str) -> str | None:
    """The API key kept under name, or None when there isn't one (or it can't be read)."""
    try:
        where = _where(cfg)
    except SigninsUnprotected:
        return None
    try:
        if where == "windows":
            path = _file(name, "dpapi")
            return _dpapi(path.read_bytes(), False).decode() if path.is_file() else None
        if where == "keychain":
            r = _run(["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"])
            return clean_key(r.stdout) if r.returncode == 0 else None
        if where == "keyring":
            r = _run(["secret-tool", "lookup", "application", "hoard", "key", name])
            return clean_key(r.stdout) if r.returncode == 0 else None
        path = _file(name, "key")
        return clean_key(path.read_text("utf-8")) if path.is_file() else None
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError):
        return None


def forget_key(cfg: dict, name: str) -> bool:
    """Delete the API key kept under name, wherever it is. True when there was one."""
    had = load_key(cfg, name) is not None
    for suffix in ("dpapi", "key"):
        _file(name, suffix).unlink(missing_ok=True)
    try:
        if sys.platform == "darwin":
            _run(["security", "delete-generic-password", "-s", SERVICE, "-a", name])
        elif shutil.which("secret-tool"):
            _run(["secret-tool", "clear", "application", "hoard", "key", name])
    except (OSError, subprocess.SubprocessError):
        pass
    return had


def key_protection(cfg: dict) -> str:
    """How API keys are protected on this computer, in words."""
    try:
        where = _where(cfg)
    except SigninsUnprotected:
        return "not kept, because this computer has no keyring to protect it"
    return {"windows": "encrypted by your Windows account", "keychain": "in your macOS Keychain",
            "keyring": "in your keyring", "file": "protected only by folder permissions"}[where]
