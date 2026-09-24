"""Keeping data and the web safe: clean text, careful reads and writes, seals, links and the local pages' rules."""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import stat
import ssl
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .paths import data_dir


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


# ----------------------------------------------------------------------------- data files
#
# Everything these tools write (manifests, catalog.json, tags.json, asset.json, the library list, your
# tags, images) may be read back later, by these tools or by other programs such as a Unity plugin, and
# may sit somewhere others can reach, like a shared drive. So text from stores is cleaned before it's
# stored, data files are read defensively, and files are written in a way that can't be redirected.

MAX_DATA_FILE = 64 * 1024 * 1024  # no data file these tools write is anywhere near this


class DataFileError(ValueError):
    """A data file that's too large, isn't valid JSON, or is nested absurdly deep."""


def clean_text(value, limit: int = 300) -> str:
    """Text from a store or a data file, made safe to show and to store.

    Control characters and invisible formatting characters (such as right-to-left overrides and
    zero-width spaces, which can make a name look like something else) are removed, runs of
    whitespace become single spaces, and the result is at most `limit` characters.
    """
    s = unicodedata.normalize("NFC", value if isinstance(value, str) else "" if value is None else str(value))
    s = "".join(" " if unicodedata.category(c) == "Cc" else "" if unicodedata.category(c)[0] == "C" else c for c in s)
    return re.sub(r"\s+", " ", s).strip()[:limit].strip()


def read_json_file(path: Path, max_bytes: int = MAX_DATA_FILE):
    """Read a JSON data file defensively, raising DataFileError when it's too big or damaged."""
    size = path.stat().st_size
    if size > max_bytes:
        raise DataFileError(f"{path.name} is unexpectedly large ({size // 1048576} MB)")
    try:
        return json.loads(path.read_text("utf-8"))
    except (ValueError, RecursionError, UnicodeDecodeError) as e:
        raise DataFileError(f"{path.name} is damaged ({e.__class__.__name__})") from None


def set_aside(path: Path) -> Path:
    """Rename a damaged data file out of the way (keeping it, in case it matters) and return its new path."""
    aside = path.with_name(f"{path.stem}.damaged-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}")
    os.replace(path, aside)
    return aside


def write_file_safely(path: Path, data, root: Path | None = None) -> None:
    """Write a file through a new temporary file in the same folder, then swap it into place.

    A reader never sees half a file, and a symlink planted where the file goes is replaced rather than
    followed. With root, the file's folder must also really be inside root (checked after resolving links).
    """
    if root is not None:
        base, folder = root.resolve(), path.parent.resolve()
        if folder != base and base not in folder.parents:
            raise PermissionError(f"refused to write {path}: its folder leads outside {root}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)  # created new, so never a planted link
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode("utf-8") if isinstance(data, str) else data)
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Windows: another program is reading the old file this instant
                if attempt == 9:
                    raise
                time.sleep(0.2)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# Every link to a store must lead to that store's own website (or a subdomain of it, such as a Booth
# shop's <shop>.booth.pm), over HTTPS. Hoard never downloads from a stored link; they're only for you to
# open, so this is what stops an edited record turning "Open on Booth" into a lookalike sign-in page.
STORE_LINK_SITES = {"booth": ("booth.pm",), "gumroad": ("gumroad.com",), "jinxxy": ("jinxxy.com",), "payhip": ("payhip.com",)}


# Sites you've added for a store (Payhip shops on their own domains), on top of the store's own website.
_EXTRA_SITES: dict[str, tuple] = {}


def set_extra_sites(store: str, hosts) -> None:
    """Also count these hosts as the store's own website (the Payhip shops listed in your settings)."""
    _EXTRA_SITES[store] = tuple(sorted({h.lower() for h in hosts}))


def store_sites() -> dict:
    """Every store's own sites, including any you've added, for the pages' link check."""
    return {s: list(sites) + list(_EXTRA_SITES.get(s, ())) for s, sites in STORE_LINK_SITES.items()}


def store_link(store, url) -> str | None:
    """url if it's an https address on the given store's own website (or a site you added for it), otherwise None."""
    if not isinstance(url, str) or not isinstance(store, str):
        return None
    url = url.strip()
    try:
        u = urlparse(url)
        port = u.port
    except ValueError:
        return None
    host = (u.hostname or "").rstrip(".")
    if u.scheme != "https" or u.username or u.password or port not in (None, 443) or not host.isascii():
        return None
    sites = STORE_LINK_SITES.get(store.lower(), ()) + _EXTRA_SITES.get(store.lower(), ())
    return url if any(host == s or host.endswith("." + s) for s in sites) else None


# Seals. The tools seal each data file they write (manifests, the catalog files, Hoard's library list)
# with an HMAC-SHA256 keyed by a random key kept private to your user account. Reading a file back, a
# broken or missing seal means something else edited it, so its links aren't trusted until they're
# fetched from the store again. docs/DATA-FORMATS.md describes the seal for other programs.
_integrity_key: bytes | None = None


_sealed_ids: set | None = None


def _hoard_folder() -> Path:
    """Hoard's private folder in this user account's app data."""
    return data_dir()


def integrity_key() -> bytes:
    """This install's sealing key: 32 random bytes, made on first use, readable only by your account."""
    global _integrity_key
    if _integrity_key:
        return _integrity_key
    path = _hoard_folder() / "integrity.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    for _attempt in range(3):
        try:
            key = bytes.fromhex(path.read_text("ascii").strip())
            if len(key) == 32:
                _integrity_key = key
                return key
            set_aside(path)  # not a key these tools made: keep it, and make a new one
        except FileNotFoundError:
            pass
        except (ValueError, UnicodeDecodeError):
            set_aside(path)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(secrets.token_hex(32))
        except FileExistsError:
            pass  # the other tool made one a moment ago: use theirs
    raise OSError(f"Couldn't read or create {path}")


def _canonical(obj) -> bytes:
    """The exact bytes a seal covers: JSON with sorted keys, no spaces, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:16]


def seal(obj: dict) -> dict:
    """obj plus an "integrity" field sealing everything else in it."""
    body = {k: v for k, v in obj.items() if k != "integrity"}
    key = integrity_key()
    return {**body, "integrity": {"alg": "HMAC-SHA256", "key_id": _key_id(key),
                                  "mac": hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()}}


def _path_id(path: Path) -> str:
    return hashlib.sha256(os.path.normcase(os.path.realpath(path)).encode("utf-8", "surrogatepass")).hexdigest()[:32]


def _sealed_file_ids() -> set:
    """Which files this install has sealed (by a hash of their location), so a removed seal is noticed."""
    global _sealed_ids
    if _sealed_ids is None:
        try:
            data = read_json_file(_hoard_folder() / "sealed-files.json", 4 * 1024 * 1024)
            _sealed_ids = {x for x in data.get("files", []) if isinstance(x, str)} if isinstance(data, dict) else set()
        except (OSError, DataFileError):
            _sealed_ids = set()
    return _sealed_ids


def remember_sealed(path: Path) -> None:
    """Note that this install has sealed the file at path."""
    ids = _sealed_file_ids()
    pid = _path_id(path)
    if pid not in ids:
        ids.add(pid)
        write_file_safely(_hoard_folder() / "sealed-files.json", json.dumps({"files": sorted(ids)[-20000:]}))


def check_seal(obj, path: Path | None = None) -> str:
    """How far to trust a data file just read.

    "sealed": this install wrote it and nothing has changed it. "unsealed": it has no seal and this install
    never sealed it (written by an older version). "foreign": another install sealed it (say, Hoard on a
    second computer sharing the folder). "changed": edited after this install sealed it, or its seal removed.
    """
    if not isinstance(obj, dict) or not isinstance(obj.get("integrity"), dict):
        return "changed" if path is not None and _path_id(path) in _sealed_file_ids() else "unsealed"
    info, key = obj["integrity"], integrity_key()
    if info.get("key_id") != _key_id(key):
        return "foreign"
    body = {k: v for k, v in obj.items() if k != "integrity"}
    expected = hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()
    return "sealed" if hmac.compare_digest(expected, str(info.get("mac"))) else "changed"


# ----------------------------------------------------------------------------- web safety
#
# The page runs on your own computer, but the text and links it shows come from store pages and
# from saved pages you import, so none of it is trusted:
#   - links are only kept when they are ordinary http(s) addresses (no javascript: or file:),
#   - server-side fetches only go to public internet addresses, never your home network or this PC,
#   - every page is sent with a Content-Security-Policy that only runs the page's own script, and
#     with headers that stop other sites from framing it or reading its responses,
#   - on your network (--host 0.0.0.0) other devices need the access key printed at start-up.

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}


_csp_cache: dict = {}


def safe_url(value) -> str | None:
    """Return value if it's a plain http(s) address, otherwise None."""
    if not isinstance(value, str):
        return None
    u = urlparse(value.strip())
    return value.strip() if u.scheme in ("http", "https") and u.netloc else None


def _is_public(ip) -> bool:
    """True for addresses on the public internet (not this computer, your network, or reserved ranges)."""
    return ip.is_global and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                                 or ip.is_reserved or ip.is_unspecified)


def _public_addresses(host: str, port: int) -> list[tuple]:
    """Look host up once and return its addresses, provided every one of them is public."""
    found = []
    for family, _type, _proto, _name, sockaddr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        if not _is_public(ipaddress.ip_address(sockaddr[0].split("%")[0])):
            raise PermissionError(f"{host} points at an address on this computer or your network")
        found.append((family, sockaddr))
    if not found:
        raise OSError(f"{host} has no address")
    return found


def public_http_url(url: str) -> bool:
    """True when url is http(s) and its host currently resolves only to public addresses."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        _public_addresses(u.hostname, u.port or (443 if u.scheme == "https" else 80))
        return True
    except (OSError, UnicodeError, ValueError):
        return False


def _connect_public(host: str, port: int, timeout) -> socket.socket:
    """Connect to one of the public addresses host resolved to, using exactly the address that was checked.

    Checking a name and then letting the connection look it up again would leave a gap that DNS rebinding
    can use (a name that answers with a public address for the check and a private one for the connection).
    """
    last: Exception | None = None
    for family, sockaddr in _public_addresses(host, port):
        sock = socket.socket(family, socket.SOCK_STREAM)
        if timeout is not None and timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
            sock.settimeout(timeout)
        try:
            sock.connect(sockaddr)
            return sock
        except OSError as e:
            last = e
            sock.close()
    raise last or OSError(f"couldn't connect to {host}")


class _PublicHTTPConnection(http.client.HTTPConnection):
    """An HTTP connection that only ever reaches a checked public address."""

    def connect(self):
        """Connect to a checked public address instead of looking the host up again."""
        self.sock = _connect_public(self.host, self.port, self.timeout)


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection that only ever reaches a checked public address, with the certificate checked for the host."""

    def connect(self):
        """Connect to a checked public address, then start TLS for the original host name."""
        sock = _connect_public(self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    """urllib's http:// handler, using the public-only connection."""

    def http_open(self, req):
        """Open http:// addresses through the public-only connection."""
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    """urllib's https:// handler, using the public-only connection."""

    def https_open(self, req):
        """Open https:// addresses through the public-only connection, verifying certificates."""
        return self.do_open(_PublicHTTPSConnection, req, context=ssl.create_default_context())


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to another http(s) address; the connection itself then checks it's public."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Refuse redirects to anything but http(s)."""
        if urlparse(newurl).scheme not in ("http", "https"):
            raise urllib.error.URLError(f"refused a redirect to {urlparse(newurl).scheme}:")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url: str, headers: dict, max_bytes: int, timeout: int = 20) -> tuple[bytes, str] | None:
    """Download a small file from a public http(s) address. Returns (data, content type) or None.

    Every connection, including each redirect, goes only to an address that was checked to be public.
    """
    if urlparse(url).scheme not in ("http", "https"):
        return None
    opener = urllib.request.OpenerDirector()  # http(s) only: no file://, ftp:// or data: handlers, no proxies
    for handler in (_PublicHTTPHandler(), _PublicHTTPSHandler(), _PublicRedirects(),
                    urllib.request.HTTPErrorProcessor(), urllib.request.HTTPDefaultErrorHandler()):
        opener.add_handler(handler)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None
            return data, r.headers.get_content_type()
    except Exception:
        return None


def network_tls(host: str, tls_cert: str | None, tls_key: str | None, plain_http: bool) -> "ssl.SSLContext | None":
    """What to use when serving beyond this computer: an HTTPS context from your certificate, or None for
    plain HTTP when you've said the network is already encrypted. Stops with an explanation otherwise."""
    if host in LOOPBACK:
        return None
    if tls_cert and tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            context.load_cert_chain(tls_cert, tls_key)
        except (OSError, ssl.SSLError) as e:
            sys.exit(f"Couldn't load the certificate or its key: {e}")
        return context
    if plain_http:
        return None
    sys.exit("Showing this to other devices sends your library and its access key across your network, so it needs "
             "HTTPS. Start it with --tls-cert and --tls-key (a certificate for this computer; the free tool mkcert "
             "makes one). If the other devices reach this computer over an encrypted VPN such as Tailscale or "
             "WireGuard, add --plain-http instead.")


class TLSServerMixin:
    """Adds HTTPS to a ThreadingHTTPServer. The TLS handshake happens in each request's own thread."""
    tls_context = None
    tls = False

    def finish_request(self, request, client_address):
        """Wrap the connection in TLS (when enabled) before handling it."""
        if self.tls_context:
            request.settimeout(30)
            try:
                request = self.tls_context.wrap_socket(request, server_side=True)
            except (ssl.SSLError, OSError):
                return
        super().finish_request(request, client_address)


def content_security_policy(page: bytes) -> str:
    """A policy that runs only the page's own inline script (by its hash) and loads nothing unexpected."""
    key = hashlib.sha256(page).hexdigest()
    if key not in _csp_cache:
        scripts = re.findall(rb"<script>(.*?)</script>", page, re.S)
        hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s).digest()).decode() + "'" for s in scripts)
        script_src = hashes or "'none'"
        _csp_cache[key] = ("default-src 'none'; "
                           f"script-src {script_src}; "
                           "style-src 'self' 'unsafe-inline'; "
                           "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
                           "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return _csp_cache[key]


def check_access(handler, lan: bool, key: str | None) -> bool:
    """On the network (--host 0.0.0.0), let a device in only with the access key. True when allowed.

    The key arrives once in the address (?key=...); after that it's kept in a cookie. Sends the reply
    itself (a redirect that sets the cookie, or a refusal) when it returns False.
    """
    if not lan or not key:
        return True
    host = (handler.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
    if handler.client_address[0] in LOOPBACK and host in LOOPBACK:
        return True  # this computer itself
    cookies = SimpleCookie(handler.headers.get("Cookie") or "")
    if "hoard_key" in cookies and hmac.compare_digest(cookies["hoard_key"].value, key):
        return True
    given = (parse_qs(urlparse(handler.path).query).get("key") or [""])[0]
    if given and hmac.compare_digest(given, key):
        handler.send_response(303)
        handler.send_header("Location", urlparse(handler.path).path or "/")
        secure = "; Secure" if getattr(handler.server, "tls", False) else ""
        handler.send_header("Set-Cookie", f"hoard_key={key}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000{secure}")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return False
    body = (b"<!doctype html><meta charset=utf-8><title>Access key needed</title>"
            b"<p style='font:16px system-ui;margin:40px'>Open the address shown in the Hoard window on the computer "
            b"running it. It includes the access key.</p>")
    handler.send_response(401)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    for k, v in SECURITY_HEADERS.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)
    return False


WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(value, maxlen: int = 80) -> str:
    """Make a string safe as a single Windows/Linux path component."""
    s = unicodedata.normalize("NFC", str(value or ""))
    # Invisible formatting characters go entirely: a right-to-left override could make "photo\u202egpj.exe"
    # show as "photoexe.jpg". Control characters and characters Windows forbids become "_".
    s = "".join(c for c in s if unicodedata.category(c) == "Cc" or unicodedata.category(c)[0] != "C")
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', "_", s)
    s = re.sub(r"\s+", " ", s).strip().strip(".").strip()
    if not s:
        s = "_"
    if s.split(".")[0].upper() in WIN_RESERVED:
        s = "_" + s
    if len(s) > maxlen:
        stem, dot, ext = s.rpartition(".")
        if dot and stem and 0 < len(ext) <= 16:
            s = stem[: maxlen - len(ext) - 1].rstrip(" .") + "." + ext
        else:
            s = s[:maxlen].rstrip(" .")
    return s


class UnsafePath(ValueError):
    """A path from a data file that isn't a plain relative path inside its folder."""


def valid_rel(rel) -> bool:
    """True for a relative path written with /, made only of plain names: no "..", drives, streams or hidden characters."""
    if not isinstance(rel, str) or not rel or len(rel) > 1000 or rel.startswith("/"):
        return False
    for part in rel.split("/"):
        if (part in ("", ".", "..") or part != part.strip() or re.search(r'[<>:"\\|?*\x00-\x1f\x7f-\x9f]', part)
                or any(unicodedata.category(c)[0] == "C" for c in part)):
            return False
    return True


def rel_to_path(base: Path, rel: str) -> Path:
    """Turn a path from a data file (always written with /) into a real path inside base.

    Raises UnsafePath when the path isn't plain, or leads outside base, including through a symlink.
    """
    if not valid_rel(rel):
        raise UnsafePath(f"refused the path {rel!r}")
    path = base.joinpath(*rel.split("/"))
    inside, target = base.resolve(), path.resolve()
    if target != inside and inside not in target.parents:
        raise UnsafePath(f"refused {rel!r}: it leads outside {base}")
    return path


# ----------------------------------------------------------------------------- opening files without being redirected
#
# Checking "is this a link?" and then opening the path leaves a gap in which another process with write access to
# the folder could swap in a link. These functions make the decision and the opening one step (POSIX: O_NOFOLLOW,
# O_EXCL, and folder handles), and on Windows, where os.open can't refuse links, confirm afterwards where the open
# file really is (GetFinalPathNameByHandle) and refuse it if that isn't the expected place.

_REPARSE = 0x400   # FILE_ATTRIBUTE_REPARSE_POINT: Windows links and junctions


def _is_link(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & _REPARSE)


def _final_path(fd: int) -> str | None:
    """Windows: the real, fully resolved path of an open file. None elsewhere, or if it can't be found."""
    if sys.platform != "win32":
        return None
    import ctypes
    import msvcrt
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(fd), buf, 32768, 0)
    if not n:
        return None
    path = buf.value
    if path.startswith("\\\\?\\UNC\\"):      # \\?\UNC\server\share\... -> \\server\share\...
        return "\\\\" + path[8:]
    return path.removeprefix("\\\\?\\")


def _same_place(a: str, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(str(b)))


def open_part(path: Path, resume: bool):
    """Open a download's .part file for writing: a fresh file created exclusively, or (resume) the existing one.
    Never follows a link. Returns (file object, identity), identity being what move_into_place checks."""
    base = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    if resume:
        flags = base | os.O_APPEND
    else:
        try:
            os.unlink(path)     # whatever is there, a link included, is removed, never followed
        except FileNotFoundError:
            pass
        flags = base | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as e:
        raise UnsafePath(f"{path.name} couldn't be opened safely ({e.strerror or e})") from None
    try:
        st, here = os.fstat(fd), os.stat(path, follow_symlinks=False)
        real = _final_path(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or _is_link(here)
                or (st.st_dev, st.st_ino) != (here.st_dev, here.st_ino)
                or (real is not None and not _same_place(real, path.resolve()))):
            raise UnsafePath(f"{path.name} isn't a plain file of its own, so it wasn't written")
    except BaseException:
        os.close(fd)
        raise
    return os.fdopen(fd, "ab" if resume else "wb"), (st.st_dev, st.st_ino)


def move_into_place(part: Path, dest: Path, identity: tuple) -> None:
    """Rename a finished .part file to its final name, provided it's still the very file that was written."""
    here = os.stat(part, follow_symlinks=False)
    if _is_link(here) or (here.st_dev, here.st_ino) != identity:
        raise UnsafePath(f"{part.name} was replaced while downloading, so it wasn't used")
    os.replace(part, dest)
    now = os.stat(dest, follow_symlinks=False)
    if _is_link(now) or (now.st_dev, now.st_ino) != identity:
        os.unlink(dest)   # something was swapped in between the check and the rename: remove it, never follow it
        raise UnsafePath(f"{dest.name} was replaced while being saved, so it was removed")


def open_under(root: Path, rel: str):
    """Open a plain file inside root for reading, without following a link anywhere below root.
    Returns a binary file object, or raises UnsafePath."""
    parts = [p for p in rel.split("/") if p]
    if not parts or not valid_rel(rel):
        raise UnsafePath("not a plain relative path")
    if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"):
        folder = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for name in parts[:-1]:
                inner = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
                os.close(folder)
                folder = inner
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=folder)
        except OSError:
            raise UnsafePath("not a plain file inside the folder") from None
        finally:
            os.close(folder)
    else:   # Windows: open, then confirm the file really is where it should be
        path = Path(root).resolve().joinpath(*parts)
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        except OSError:
            raise UnsafePath("not a plain file inside the folder") from None
        real = _final_path(fd)
        if real is None or not _same_place(real, path):
            os.close(fd)
            raise UnsafePath("that file is somewhere else than it appears")
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise UnsafePath("not a plain file")
    return os.fdopen(fd, "rb")


# ----------------------------------------------------------------------------- pages you saved

_ACTIVE = [
    re.compile(r"<script\b[^>]*>.*?</script\s*>", re.S | re.I),
    re.compile(r"<(iframe|frame|object|embed)\b[^>]*>.*?</\1\s*>", re.S | re.I),
    re.compile(r"<(iframe|frame|object|embed|base|meta\s+http-equiv)\b[^>]*>", re.I),
]
_HANDLERS = re.compile(r"""\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_JS_LINKS = re.compile(r"""(\s(?:href|src|action|formaction|xlink:href)\s*=\s*["']?)\s*javascript:""", re.I)


def inert_html(page_html: str) -> str:
    """A saved page with everything that could run removed: scripts, frames and plugins, inline event handlers
    (onerror=, onload=, ...), and javascript: links. Imported pages are also opened with scripts switched off;
    this is the second layer."""
    for pattern in _ACTIVE:
        page_html = pattern.sub("", page_html)
    page_html = _HANDLERS.sub("", page_html)
    return _JS_LINKS.sub(r"\1about:blank#", page_html)


def offline_page(browser):
    """A page for reading a saved file: scripts off, and no network at all."""
    page = browser.new_context(java_script_enabled=False, service_workers="block").new_page()
    page.route("**/*", lambda route: route.abort())
    return page


# ----------------------------------------------------------------------------- diagnostics

_SCRUB = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    (re.compile(r'(?i)(<input\b[^>]*?\bvalue=)(["\'])[^"\']*\2'), r"\1\2[value]\2"),     # form values: keys, codes
    (re.compile(r'(?i)(<meta\b[^>]*?name=["\']csrf[^"\']*["\'][^>]*?content=)(["\'])[^"\']*\2'), r"\1\2[token]\2"),
    (re.compile(r'(?i)([?&][\w.%-]+=)[^&"\'\s<>#]+'), r"\1[value]"),                    # every URL query value
    (re.compile(r'(?i)(data-[\w-]*(?:key|token|id|encrypted)[\w-]*=)(["\'])[^"\']*\2'), r"\1\2[value]\2"),
    (re.compile(r"\b[A-Za-z0-9_-]{32,}\b"), "[token]"),                                 # long opaque tokens
]


def scrub(text: str) -> str:
    """A page with the personal and secret parts replaced: email addresses, form values (license keys, codes),
    security tokens, every URL query value (signed download addresses) and long opaque tokens. The page's
    structure, which is what troubleshooting needs, is kept."""
    for pattern, replacement in _SCRUB:
        text = pattern.sub(replacement, text)
    return text


def save_browser_download(dl, folder: Path, fname: str) -> Path:
    """Save a download the browser made, into folder/fname. The browser writes it into a new private folder first
    (created by Hoard with only-you permissions), and only that very file is then moved into place."""
    folder.mkdir(parents=True, exist_ok=True)
    private = Path(tempfile.mkdtemp(prefix=".hoard-", dir=folder))
    try:
        staged = private / "download"
        dl.save_as(str(staged))
        if dl.failure():
            raise RuntimeError(f"the download failed ({dl.failure()})")
        here = os.stat(staged, follow_symlinks=False)
        if _is_link(here) or not stat.S_ISREG(here.st_mode):
            raise UnsafePath(f"{fname} wasn't saved as a plain file")
        move_into_place(staged, folder / fname, (here.st_dev, here.st_ino))
        return folder / fname
    finally:
        for leftover in private.glob("*"):
            leftover.unlink(missing_ok=True)
        private.rmdir()


def no_link(path: Path) -> Path:
    """Remove a symlink planted where a file is about to be written, so writing can't follow it."""
    if path.is_symlink():
        path.unlink()
    return path


def safe_join(root: Path, rel: str) -> Path | None:
    """Resolve a /-separated path inside root; None if it would escape root."""
    parts = [s for s in rel.replace("\\", "/").split("/") if s not in ("", ".", "..")]
    try:
        base = root.resolve()
        p = base.joinpath(*parts).resolve()
    except (OSError, ValueError):
        return None
    return p if p == base or base in p.parents else None
