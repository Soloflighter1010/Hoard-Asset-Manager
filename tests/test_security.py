"""Security regression tests for Hoard and Hoard Downloader.

Run from the repository root:  python -m unittest discover -s tests -v

They need the packages in requirements.txt but no network, no store accounts and no browser, so they
run the same on any computer and in GitHub Actions. Each test names the review finding it guards.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import sqlite3
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
_TEST_HOME = Path(tempfile.mkdtemp(prefix="hoard-tests-"))
os.environ["HOARD_DATA_DIR"] = str(_TEST_HOME / "Hoard")   # tests never touch your real Hoard data
sys.path.insert(0, str(REPO))

from hoard import browser, common, config, downloader, library, safety, server, tags  # noqa: E402


def reset_keys():
    """Start with no sealing key and no record of sealed files (as on a fresh install)."""
    import shutil
    shutil.rmtree(_TEST_HOME / "Hoard", ignore_errors=True)
    safety._integrity_key, safety._sealed_ids = None, None


WEB_SAFETY = (safety,)
SIGN_INS = (browser,)
PAGES = (REPO / "hoard" / "web" / "library.html", REPO / "hoard" / "web" / "downloads.html")


def fake_addrinfo(*ips):
    """getaddrinfo results for the given addresses."""
    out = []
    for ip in ips:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        out.append((family, socket.SOCK_STREAM, 6, "", (ip, 443) if family == socket.AF_INET else (ip, 443, 0, 0)))
    return out


class OneCopy(unittest.TestCase):
    """Every piece of security code exists exactly once, so a fix can never miss a copy."""

    def test_each_is_defined_once(self):
        import ast as _ast
        seen = {}
        for f in (REPO / "hoard").glob("*.py"):
            for n in _ast.parse(f.read_text("utf-8")).body:
                if isinstance(n, (_ast.FunctionDef, _ast.ClassDef)):
                    seen.setdefault(n.name, []).append(f.stem)
        for name in ("safe_url", "_connect_public", "fetch_public", "content_security_policy", "check_access",
                     "network_tls", "store_link", "seal", "check_seal", "write_file_safely", "read_json_file",
                     "clean_text", "safe_name", "rel_to_path", "launch_context", "sign_out", "check_saved_signin",
                     "TagStore", "clean_tag", "tag_key"):
            self.assertEqual(len(seen.get(name, [])), 1, f"{name} is defined in {seen.get(name)}")


class Links(unittest.TestCase):
    """Store text and links are untrusted: only plain web addresses become links."""

    def test_only_http_links(self):
        for m in WEB_SAFETY:
            for bad in ("javascript:alert(1)", "JaVaScRiPt:alert(1)", "file:///etc/passwd", "data:text/html,x",
                        "/relative", "", None, 42, "https://"):
                self.assertIsNone(m.safe_url(bad), (m.__name__, bad))
            self.assertEqual(m.safe_url("https://booth.pm/ja/items/1"), "https://booth.pm/ja/items/1")

    def test_pages_only_link_checked_addresses(self):
        for page in PAGES:
            html = page.read_text("utf-8")
            unchecked = re.findall(r'href="\$\{esc\((?!safeUrl|storeUrl)[^)]*\)\}"', html)
            self.assertEqual(unchecked, [], f"{page.name} builds links without safeUrl: {unchecked}")
            self.assertNotRegex(html, r'rel="noopener"(?! noreferrer)', f"{page.name}: links should use noopener noreferrer")

    def test_downloader_only_follows_store_links(self):
        self.assertTrue(downloader.store_url("https://booth.pm/downloadables/1", ["booth.pm"]))
        self.assertFalse(downloader.store_url("https://evil.example/downloadables/1", ["booth.pm"]))
        self.assertFalse(downloader.store_url("https://booth.pm.evil.example/x", ["booth.pm"]))
        self.assertFalse(downloader.store_url("javascript:alert(1)", ["payhip.com"]))


class PublicOnlyFetching(unittest.TestCase):
    """H-01: server-side fetches only reach public addresses, with no gap for DNS rebinding."""

    def test_private_addresses_are_not_public(self):
        import ipaddress
        for m in WEB_SAFETY:
            for ip in ("127.0.0.1", "10.1.2.3", "192.168.1.1", "172.16.0.1", "169.254.169.254", "0.0.0.0",
                       "::1", "fc00::1", "fe80::1", "100.64.0.1", "224.0.0.1"):
                self.assertFalse(m._is_public(ipaddress.ip_address(ip)), (m.__name__, ip))
            self.assertTrue(m._is_public(ipaddress.ip_address("93.184.216.34")))

    def test_any_private_answer_blocks_the_host(self):
        for m in WEB_SAFETY:
            with mock.patch.object(m.socket, "getaddrinfo", return_value=fake_addrinfo("93.184.216.34", "10.0.0.5")):
                with self.assertRaises(PermissionError):
                    m._public_addresses("mixed.example", 443)

    def test_connection_uses_the_address_that_was_checked(self):
        """A rebinding name answers public first, then private. The connection must use the first answer."""
        for m in WEB_SAFETY:
            answers = [fake_addrinfo("93.184.216.34"), fake_addrinfo("127.0.0.1")]
            connected = []

            class FakeSocket:
                def __init__(self, *a, **k): pass
                def settimeout(self, t): pass
                def connect(self, addr): connected.append(addr[0])
                def close(self): pass

            with mock.patch.object(m.socket, "getaddrinfo", side_effect=lambda *a, **k: answers.pop(0)), \
                    mock.patch.object(m.socket, "socket", FakeSocket):
                m._connect_public("rebind.example", 443, 5)
            self.assertEqual(connected, ["93.184.216.34"], m.__name__)
            self.assertEqual(len(answers), 1, f"{m.__name__} looked the name up more than once")

    def test_refuses_this_computer_and_other_schemes(self):
        server = _test_server()
        try:
            for m in WEB_SAFETY:
                self.assertIsNone(m.fetch_public(f"http://127.0.0.1:{server.server_port}/x.png", {}, 1000), m.__name__)
                self.assertIsNone(m.fetch_public(f"http://localhost:{server.server_port}/x.png", {}, 1000), m.__name__)
                self.assertIsNone(m.fetch_public("file:///etc/hostname", {}, 1000), m.__name__)
        finally:
            server.shutdown()
            server.server_close()

    def test_redirects_to_other_schemes_are_refused(self):
        for m in WEB_SAFETY:
            with self.assertRaises(urllib.error.URLError):
                m._PublicRedirects().redirect_request(urllib.request.Request("https://a.example/"), None, 302, "Found",
                                                      {}, "file:///etc/passwd")


class Pages(unittest.TestCase):
    """The pages run only their own script, and nothing else from the server runs as a page."""

    def test_policy_allows_only_the_pages_own_script(self):
        for page in PAGES:
            body = page.read_bytes()
            csp = safety.content_security_policy(body)
            self.assertIn("script-src 'sha256-", csp)
            self.assertNotIn("unsafe-inline' https", csp)
            self.assertNotRegex(csp.split("script-src")[1].split(";")[0], "unsafe-inline")
            self.assertIn("frame-ancestors 'none'", csp)
            self.assertIn("font-src 'self'", csp)

    def test_every_request_carries_the_key(self):
        """S-01: the pages reach Hoard's server only through api() (the key in a header) and keyed() (images)."""
        for page in PAGES:
            script = re.search(r"<script>(.*?)</script>", page.read_text("utf-8"), re.S).group(1)
            self.assertEqual(len(re.findall(r"\bfetch\(", script)), 2, f"{page.name}: api() and the one-time link only")
            self.assertIn(f'"{safety.ACCESS_HEADER}": ACCESS.key', script, page.name)
            self.assertNotRegex(script, r"""src=["'`]/(thumb|files)/""", f"{page.name}: an image without the key")

    def test_pages_have_no_inline_handlers_or_outside_resources(self):
        for page in PAGES:
            html = page.read_text("utf-8")
            markup = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
            self.assertNotRegex(markup, r"\son[a-z]+=", f"{page.name}: inline event handler")
            self.assertEqual(len(re.findall(r"<script\b", html)), 1, page.name)
            self.assertNotRegex(html, r'<(link|script)[^>]+(href|src)="https?://', f"{page.name} loads something from outside")

    def test_server_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": tmp}, lan=False)
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                port = srv.server_port
                key = {safety.ACCESS_HEADER: srv.key}
                def get(path, headers=None, method="GET", body=None):
                    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                    c.request(method, path, body=body, headers=headers or {})
                    r = c.getresponse()
                    r.read()
                    return r
                page = get("/")
                self.assertIn("script-src 'sha256-", page.getheader("Content-Security-Policy"))
                self.assertEqual(page.getheader("X-Frame-Options"), "DENY")
                self.assertEqual(get("/api/assets", key).getheader("Content-Security-Policy"), "default-src 'none'; sandbox")
                self.assertEqual(get("/", {"Host": "evil.example"}).status, 403)              # DNS rebinding of the page
                self.assertEqual(get("/files/..%2F..%2Fetc%2Fpasswd", key).status, 404)       # path traversal
                self.assertEqual(get("/api/open", {"Content-Type": "application/x-www-form-urlencoded"},
                                     "POST", "path=x").status, 403)                            # cross-site form post
            finally:
                srv.shutdown()
                srv.server_close()


class NetworkMode(unittest.TestCase):
    """H-02: sharing on the network needs HTTPS or an explicit statement that the network is encrypted."""

    def test_network_mode_needs_https_or_plain_http_opt_in(self):
        for m in WEB_SAFETY:
            self.assertIsNone(m.network_tls("127.0.0.1", None, None, False))
            with self.assertRaises(SystemExit):
                m.network_tls("0.0.0.0", None, None, False)
            self.assertIsNone(m.network_tls("0.0.0.0", None, None, True))

    def _access(self, m, *, key, path="/api/library", header=None, cookie=None, in_address=False):
        handler = mock.Mock()
        handler.headers = {"Host": "hoard.lan:8766", **({m.ACCESS_HEADER: header} if header is not None else {}),
                           **({"Cookie": cookie} if cookie else {})}
        handler.client_address = ("192.0.2.7", 50000)
        handler.path = path
        return m.check_access(handler, key, in_address=in_address)

    def test_other_devices_need_the_key(self):
        for m in WEB_SAFETY:
            self.assertFalse(self._access(m, key="s3cret"))
            self.assertFalse(self._access(m, key="s3cret", header="wrong"))
            self.assertFalse(self._access(m, key="s3cret", header="s3cre"))
            self.assertFalse(self._access(m, key="s3cret", header="s3crét"))   # not ASCII: refused, no error
            self.assertTrue(self._access(m, key="s3cret", header="s3cret"))
            self.assertFalse(self._access(m, key=None, header=""), "no key made: nothing gets in")

    def test_the_key_never_comes_from_a_cookie(self):
        """A browser sends a cookie for 127.0.0.1 to every program listening there, whatever its port."""
        for m in WEB_SAFETY:
            self.assertFalse(self._access(m, key="s3cret", cookie="hoard_key=s3cret"))

    def test_only_images_carry_the_key_in_their_address(self):
        for m in WEB_SAFETY:
            self.assertFalse(self._access(m, key="s3cret", path="/api/library?k=s3cret"))
            self.assertTrue(self._access(m, key="s3cret", path="/files/a.png?k=s3cret", in_address=True))
            self.assertFalse(self._access(m, key="s3cret", path="/files/a.png?k=wrong", in_address=True))


class LocalAccess(unittest.TestCase):
    """S-01 (2.3.1 review): being on this computer isn't enough. Other programs, and other people's accounts on a
    shared computer, can reach 127.0.0.1 too, so every request for data, images or an action needs this run's
    access key. Without it, nothing can read your library or, say, point Hoard's downloads folder elsewhere."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        Path(self.tmp.name, "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": self.tmp.name}, lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, key=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={**({"Content-Type": "application/json"} if body is not None else {}),
                           **({safety.ACCESS_HEADER: key} if key else {}), **(headers or {})})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_data_needs_the_key(self):
        for path in ("/api/library", "/api/assets", "/api/settings", "/api/status", "/api/setup"):
            self.assertEqual(self.call("GET", path)[0], 401, path)
            self.assertEqual(self.call("GET", path, key="wrong")[0], 401, path)
            self.assertEqual(self.call("GET", path, key=self.srv.key)[0], 200, path)

    def test_actions_need_the_key(self):
        root = self.srv.cfg["root"]
        self.assertEqual(self.call("POST", "/api/settings", {"root": str(Path(self.tmp.name, "elsewhere"))})[0], 401)
        self.assertEqual(self.srv.cfg["root"], root, "the downloads folder stays where it was")
        for path in ("/api/sync", "/api/logout", "/api/tags", "/api/open", "/api/quit", "/api/unlock"):
            self.assertEqual(self.call("POST", path, {})[0], 401, path)
        self.assertEqual(self.call("POST", "/api/cancel", {}, key=self.srv.key)[0], 200)

    def test_not_from_a_cookie_or_the_address(self):
        """A browser sends a cookie for 127.0.0.1 to every port there, and addresses end up in histories."""
        self.assertEqual(self.call("GET", "/api/settings", headers={"Cookie": f"hoard_key={self.srv.key}"})[0], 401)
        self.assertEqual(self.call("GET", f"/api/settings?k={self.srv.key}")[0], 401)
        self.assertEqual(self.call("GET", f"/api/settings?key={self.srv.key}")[0], 401)

    def test_images_carry_the_key_in_their_address(self):
        self.assertEqual(self.call("GET", "/files/a.png")[0], 401)
        self.assertEqual(self.call("GET", "/files/a.png?k=wrong")[0], 401)
        self.assertEqual(self.call("GET", f"/files/a.png?k={self.srv.key}")[0], 200)
        self.assertEqual(self.call("GET", "/thumb/booth%3A1")[0], 401)
        self.assertEqual(self.call("GET", f"/thumb/booth%3A1?k={self.srv.key}")[0], 404)

    def test_pages_and_fonts_hold_nothing_private(self):
        for path in ("/", "/downloads", "/fonts/DelaGothicOne-Regular.woff2"):
            self.assertEqual(self.call("GET", path)[0], 200, path)

    def test_one_time_links(self):
        link = self.srv.entry_url()
        self.assertTrue(link.startswith(self.srv.url + "#enter="), link)
        self.assertNotIn(self.srv.key, link, "the key itself never appears in a link Hoard opens")
        token = link.split("#enter=", 1)[1]
        status, data = self.call("POST", "/api/enter", {"token": token})
        self.assertEqual((status, json.loads(data)["key"]), (200, self.srv.key))
        self.assertEqual(self.call("POST", "/api/enter", {"token": token})[0], 403, "each link works once")
        for bad in ({"token": "guess"}, {"token": ""}, {"token": 7}, {}):
            self.assertEqual(self.call("POST", "/api/enter", bad)[0], 403, bad)
        old = self.srv.entry_url().split("#enter=", 1)[1]
        self.srv._entries[old] = time.time() - 1   # as if it had waited longer than ENTRY_SECONDS
        self.assertEqual(self.call("POST", "/api/enter", {"token": old})[0], 403, "an unused link runs out")

    def test_a_new_key_each_start(self):
        other = server.AppServer(("127.0.0.1", 0), config.load_config(), lan=False)
        try:
            self.assertNotEqual(other.key, self.srv.key)
            self.assertGreaterEqual(len(self.srv.key), 43)   # 32 random bytes
        finally:
            other.server_close()


class PayhipToDo(unittest.TestCase):
    """S-04/B-04 (2.3.1 review): when Payhip blocks the automated browser, the page listing products for you to
    download yourself links only to Payhip and your shops, whatever a record says, and is written like every other
    file Hoard writes: whole, and never through a link planted where it goes."""

    PRODUCTS = [
        {"id": "a1", "name": "First", "creator": "Kitsu", "url": "https://payhip.com/b/a1", "download_url": "https://payhip.com/d/a1"},
        {"id": "x1", "name": "Trap", "creator": "Kitsu", "url": "https://payhip.com/b/x1",
         "download_url": "javascript:alert(document.cookie)"},
        {"id": "x2", "name": "Lookalike", "creator": "Kitsu", "url": "https://payhip.com/b/x2",
         "download_url": "https://payhip.com.evil.example/d/x2"},
        {"id": "b2", "name": "Second", "creator": "Kitsu", "url": "https://payhip.com/b/b2", "download_url": "https://payhip.com/d/b2"},
    ]

    def sync(self, root: Path) -> tuple[list, "downloader.Report"]:
        """sync_payhip with the browser stood in for: Payhip blocks the first product it's asked to open."""
        import contextlib
        import types
        opened = []

        class Context:
            pages = [object()]

            def close(self):
                pass

        def bot_check(page, url, wait_s, headed):
            opened.append(url)
            raise downloader.Blocked("Payhip showed a bot check")
        report = downloader.Report()
        with mock.patch.multiple(downloader, _playwright=lambda: (lambda: contextlib.nullcontext(None)),
                                 launch_context=lambda *a, **k: Context(), open_past_bot_check=bot_check,
                                 payhip_products=lambda *a, **k: [dict(p) for p in self.PRODUCTS]):
            downloader.sync_payhip(config.load_config(), root, types.SimpleNamespace(
                headed=False, only=None, dry_run=False, payhip_page=None), report)
        return opened, report

    def test_links_are_checked_even_after_payhip_blocks(self):
        root = Path(tempfile.mkdtemp())
        opened, report = self.sync(root)
        self.assertEqual(opened, ["https://payhip.com/d/a1"], "the first is tried; after that Payhip is blocking")
        page = (root / "Payhip" / "_download-yourself.html").read_text("utf-8")
        self.assertIn('href="https://payhip.com/d/a1"', page)
        self.assertIn('href="https://payhip.com/d/b2"', page, "listed after the block, and checked")
        self.assertNotIn("javascript:", page)
        self.assertNotIn("evil.example", page)
        self.assertEqual(sorted(s.split(" - ")[0] for s in report.skipped), ["Payhip: Lookalike", "Payhip: Trap"])

    def test_the_page_itself_only_links_to_payhip(self):
        """Checked again where the page is written, in case anything else ever lists a product."""
        root = Path(tempfile.mkdtemp())
        pending = [(p, root / "Payhip" / p["name"]) for p in self.PRODUCTS]
        page = downloader.write_payhip_todo(root / "Payhip", pending, ["payhip.com"]).read_text("utf-8")
        self.assertEqual(page.count("<a href="), 2)
        self.assertNotIn("javascript:", page)
        self.assertEqual(page.count("left out"), 2)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs symlinks")
    def test_a_planted_link_is_replaced_not_followed(self):
        root = Path(tempfile.mkdtemp())
        outside = Path(tempfile.mkdtemp()) / "yours.txt"
        outside.write_text("keep me")
        (root / "Payhip").mkdir()
        (root / "Payhip" / "_download-yourself.html").symlink_to(outside)
        downloader.write_payhip_todo(root / "Payhip", [(self.PRODUCTS[0], root / "Payhip" / "First")], ["payhip.com"])
        self.assertEqual(outside.read_text(), "keep me")
        self.assertFalse((root / "Payhip" / "_download-yourself.html").is_symlink())


class Thumbnails(unittest.TestCase):
    """H-07: only raster images are kept; SVG is never fetched into the cache or served."""

    def test_svg_is_refused_and_old_svg_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = mock.Mock()
            lib.thumbnail_for.return_value = ("https://img.example/a.svg", "https://booth.pm/")
            with mock.patch.object(library, "THUMB_DIR", Path(tmp)), \
                    mock.patch.object(library, "fetch_public", return_value=(b"<svg onload=alert(1)/>", "image/svg+xml")):
                self.assertIsNone(library.fetch_thumbnail("booth:1", lib))
            with mock.patch.object(library, "THUMB_DIR", Path(tmp)), \
                    mock.patch.object(library, "fetch_public", return_value=(b"\x89PNG....", "image/png")):
                self.assertEqual(library.fetch_thumbnail("booth:1", lib)[1], "image/png")
            import hashlib
            old = Path(tmp) / (hashlib.sha1(b"https://img.example/b.svg").hexdigest() + ".svg")
            old.write_text("<svg/>")
            lib.thumbnail_for.return_value = ("https://img.example/b.svg", "https://booth.pm/")
            with mock.patch.object(library, "THUMB_DIR", Path(tmp)), mock.patch.object(library, "fetch_public", return_value=None):
                self.assertIsNone(library.fetch_thumbnail("booth:2", lib))
            self.assertFalse(old.exists())


class SignIns(unittest.TestCase):
    """CRED-01, CRED-03, CRED-06: sign-ins are per store, protected, locked and verifiably removed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = {"profile_dir": str(Path(self.tmp.name) / "sign-ins")}

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_store_has_its_own_folder(self):
        for m in SIGN_INS:
            dirs = {m.profile_dir(self.cfg, s) for s in m.STORE_SITES}
            self.assertEqual(len(dirs), 4)
            self.assertEqual(m.signins_root({"profile_dir": ".browser-profile"}), m.app_data_dir() / "sign-ins")

    @unittest.skipUnless(os.name == "posix", "folder modes are a Linux and macOS feature")
    def test_folders_are_private(self):
        for m in SIGN_INS:
            target = m.profile_dir(self.cfg, "booth")
            m._lock_down(target)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)

    def test_one_program_at_a_time(self):
        for m in SIGN_INS:
            target = m.profile_dir(self.cfg, "gumroad")
            first, other, again = (m.ProfileLock(target), m.ProfileLock(m.profile_dir(self.cfg, "booth")),
                                   m.ProfileLock(target))
            first.acquire()
            try:
                with self.assertRaises(m.ProfileBusy):
                    m.ProfileLock(target).acquire()
                other.acquire()  # another store is independent
            finally:
                first.release()
                other.release()
            again.acquire()      # free again once released
            again.release()

    def test_linux_without_keyring_refuses_to_save(self):
        for m in SIGN_INS:
            with mock.patch.object(m.sys, "platform", "linux"), mock.patch.object(m, "linux_keyring", return_value=None):
                with self.assertRaises(m.SigninsUnprotected):
                    m._launch(None, self.cfg, m.profile_dir(self.cfg, "booth"), True)
                self.assertIn("not saved", m.signin_protection(self.cfg))

    def _cookie_db(self, profile, values):
        db = profile / "Default" / "Network" / "Cookies"
        db.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE cookies (host_key TEXT, encrypted_value BLOB, value TEXT)")
        con.executemany("INSERT INTO cookies VALUES (?, ?, ?)", values)
        con.commit()
        con.close()

    def test_unprotected_cookies_are_detected_and_deleted(self):
        for m in SIGN_INS:
            target = m.profile_dir(self.cfg, "booth")
            self._cookie_db(target, [(".booth.pm", b"v10fixedkey", ""), (".booth.pm", b"v11keyring", "")])
            with mock.patch.object(m.sys, "platform", "linux"):
                self.assertEqual(m.unprotected_cookie_count(target), 1)
                with self.assertRaises(m.SigninsUnprotected):
                    m.check_saved_signin(self.cfg, "booth")
            self.assertFalse(target.exists(), "an unprotected sign-in must not be kept")

    def test_sign_out_deletes_and_reports(self):
        for m in SIGN_INS:
            target = m.profile_dir(self.cfg, "jinxxy")
            self._cookie_db(target, [(".jinxxy.com", b"v11a", ""), (".jinxxy.com", b"v11b", "")])
            with mock.patch.object(m, "_end_store_session", return_value=False):
                said = m.sign_out(None, self.cfg, "jinxxy", online=True)
            self.assertFalse(target.exists())
            self.assertIn("2 cookies", said)
            self.assertIn("sign out on its website", said)
            self.assertIn("no saved sign-in", m.sign_out(None, self.cfg, "jinxxy", online=True))


class GumroadCookie(unittest.TestCase):
    """H-03 / CRED-02: a copied Gumroad session cookie is never read from files or the environment."""

    def test_config_and_environment_cookies_are_ignored(self):
        self.assertNotIn("session_cookie", config.DEFAULT_CONFIG["gumroad"])
        cfg = json.loads(json.dumps(config.DEFAULT_CONFIG))
        cfg["gumroad"]["session_cookie"] = "stolen-looking-value"
        with mock.patch.dict(os.environ, {"HOARD_GUMROAD_SESSION": "another"}), \
                mock.patch.object(downloader, "browser_cookies", return_value=([], "UA")) as from_browser:
            with self.assertRaises(common.NotLoggedIn):
                downloader.gumroad_session(cfg)
        from_browser.assert_called_once()


class Files(unittest.TestCase):
    """Names from stores can't escape the download folder or hit reserved Windows names."""

    def test_safe_names(self):
        for bad in ("..", "../..", "a/b\\c", "CON", "nul.txt", "a:b*c?d", " .hidden. "):
            name = safety.safe_name(bad)
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)
            self.assertNotIn("..", name.strip("_"))
            self.assertNotEqual(name.split(".")[0].upper(), "CON")

    def test_downloads_browser_stays_inside_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for attempt in ("../../etc/passwd", "..\\..\\windows\\win.ini", "/etc/passwd", "a/../../b"):
                joined = safety.safe_join(root, attempt)
                self.assertTrue(joined is None or joined == root or root in joined.parents, attempt)


class Tags(unittest.TestCase):
    """Tag names are cleaned, and two programs saving at once lose nothing."""

    def test_clean_tag(self):
        self.assertEqual(tags.clean_tag("  #Rusk, Outfits  "), "rusk outfits")
        self.assertEqual(len(tags.clean_tag("x" * 100)), 40)

    def test_concurrent_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = tags.TagStore(Path(tmp) / "tags.json")
            def work(n):
                for i in range(25):
                    store.change({"action": "assign", "keys": [f"booth:item{n}x{i}"], "add": [f"t{n}"]})
            threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(len(store.load()["items"]), 100)


class Names(unittest.TestCase):
    """File, folder and item names can't hide their real meaning or contents."""

    SPOOF = "Cute Hoodie\u202egpj.exe"   # shows as "Cute Hoodieexe.jpg" where the override is honoured

    def test_invisible_characters_never_reach_file_names(self):
        for bad in (self.SPOOF, "zero\u200bwidth", "bom\ufeffname", "private\ue000use"):
            name = safety.safe_name(bad)
            self.assertFalse(any(__import__("unicodedata").category(c)[0] == "C" for c in name), repr(name))
        self.assertEqual(safety.safe_name(self.SPOOF), "Cute Hoodiegpj.exe")
        self.assertEqual(safety.safe_name("【VRChat想定】パーカー"), "【VRChat想定】パーカー")

    def test_clean_text(self):
        for m in (safety,):
            self.assertEqual(m.clean_text("  A\u202eB\u200bC\x07D\n\tE  "), "AB C D E".replace("B C", "BC ") if False else "ABC D E")
            self.assertEqual(len(m.clean_text("x" * 1000, 300)), 300)
            self.assertEqual(m.clean_text(None), "")


class Paths(unittest.TestCase):
    """Paths read from data files can never lead outside their folder."""

    def test_only_plain_relative_paths(self):
        for bad in ("../x", "a/../../b", "/etc/passwd", "C:/Windows", "a\\b", "a:stream", "a/./b", "a//b", " a", "",
                    None, 5, "a/\u202eb", "x" * 1001):
            self.assertFalse(safety.valid_rel(bad), repr(bad))
        for good in ("Kitsu Studio/Rusk Avatar Base", "Creator/Name (2)/sub/file.zip", "作者/パーカー"):
            self.assertTrue(safety.valid_rel(good), good)

    def test_rel_to_path_refuses_escapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "downloads"
            (root / "Booth").mkdir(parents=True)
            with self.assertRaises(safety.UnsafePath):
                safety.rel_to_path(root, "../outside")
            self.assertEqual(safety.rel_to_path(root, "Booth/x"), root / "Booth" / "x")

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs symlinks")
    def test_rel_to_path_refuses_links_that_lead_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, outside = Path(tmp) / "downloads", Path(tmp) / "elsewhere"
            (root / "Booth").mkdir(parents=True)
            outside.mkdir()
            os.symlink(outside, root / "Booth" / "Trap")
            with self.assertRaises(safety.UnsafePath):
                safety.rel_to_path(root, "Booth/Trap/file.zip")


class DataFiles(unittest.TestCase):
    """Manifests, the catalog, tags and the library list are read defensively and written safely."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "downloads"
        (self.root / "Booth" / "Good Creator" / "Good Item").mkdir(parents=True)
        (self.root / "Booth" / "Good Creator" / "Good Item" / "item.zip").write_bytes(b"zip")

    def tearDown(self):
        self.tmp.cleanup()

    def _tampered_manifest(self):
        good = {"folder": "Good Creator/Good Item", "name": "Good\u202eItem", "creator": "Good Creator",
                "url": "javascript:alert(1)", "files": {"f": {"path": "item.zip"}, "g": {"path": "../../evil.zip"}}}
        evil = {"folder": "../../../Startup", "name": "Evil", "creator": "X", "files": {"f": {"path": "a.exe"}}}
        (self.root / "Booth" / "_manifest.json").write_text(json.dumps({"assets": {"1": good, "2": evil, "3": "nonsense"}}))

    def test_tampered_manifest_is_cleaned(self):
        self._tampered_manifest()
        man = downloader.Manifest(self.root / "Booth")
        self.assertEqual(list(man.assets), ["1"])
        rec = man.assets["1"]
        self.assertEqual(rec["name"], "GoodItem")
        self.assertIsNone(rec["url"])
        self.assertEqual(list(rec["files"]), ["f"])

    def test_damaged_manifest_is_kept_aside(self):
        (self.root / "Booth" / "_manifest.json").write_text("{not json")
        man = downloader.Manifest(self.root / "Booth")
        self.assertEqual(man.assets, {})
        self.assertTrue(list((self.root / "Booth").glob("_manifest.damaged-*.json")))

    def test_catalog_keeps_its_promises(self):
        self._tampered_manifest()
        cfg = json.loads(json.dumps(config.DEFAULT_CONFIG))
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": self.tmp.name, "LOCALAPPDATA": self.tmp.name}):
            downloader.build_catalog(cfg, self.root)
        catalog = json.loads((self.root / "catalog.json").read_text("utf-8"))
        self.assertEqual((catalog["format"], catalog["version"]), ("hoard-catalog", 3))
        self.assertEqual(len(catalog["assets"]), 1)
        for entry in catalog["assets"]:
            self.assertEqual(downloader.validate_catalog_entry(entry), [])
        asset = json.loads((self.root / "Booth" / "Good Creator" / "Good Item" / "asset.json").read_text("utf-8"))
        self.assertEqual(asset["format"], "hoard-asset")
        self.assertFalse((Path(self.tmp.name) / "Startup").exists(), "nothing may be written outside the downloads")
        tags = json.loads((self.root / "tags.json").read_text("utf-8"))
        self.assertEqual(tags["format"], "hoard-tags")

    def test_validator_catches_broken_entries(self):
        bad = {"store": "Booth", "name": "A\u202eB", "creator": "C", "folder": "Booth/../x", "files": ["../y"],
               "url": "javascript:x", "tags": ["<b>"], "suggested_tags": []}
        self.assertGreaterEqual(len(downloader.validate_catalog_entry(bad)), 5)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs symlinks")
    def test_writes_replace_planted_links(self):
        victim = Path(self.tmp.name) / "victim.txt"
        victim.write_text("keep me")
        link = self.root / "catalog.json"
        os.symlink(victim, link)
        safety.write_file_safely(link, "{}", self.root)
        self.assertEqual(victim.read_text(), "keep me")
        self.assertFalse(link.is_symlink())
        with self.assertRaises(PermissionError):
            safety.write_file_safely(Path(self.tmp.name) / "out.json", "{}", self.root)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs symlinks")
    def test_partial_downloads_never_follow_links(self):
        victim = Path(self.tmp.name) / "victim.bin"
        victim.write_text("keep me")
        part = self.root / "file.zip.part"
        os.symlink(victim, part)
        safety.no_link(part)
        self.assertFalse(part.exists())
        self.assertEqual(victim.read_text(), "keep me")

    def test_oversized_and_deep_json_are_refused(self):
        big = Path(self.tmp.name) / "big.json"
        big.write_text("[" * 100000 + "]" * 100000)
        with self.assertRaises(safety.DataFileError):
            safety.read_json_file(big)
        with self.assertRaises(safety.DataFileError):
            safety.read_json_file(big, max_bytes=1000)

    def test_library_list_is_cleaned_and_damage_kept_aside(self):
        path = Path(self.tmp.name) / "library.json"
        path.write_text(json.dumps({"items": [
            {"store": "booth", "id": "1", "name": "Hood\u202eie", "url": "javascript:alert(1)", "files": [{"url": "file:///x"}]},
            {"store": "nowhere", "id": "2"}, "junk"], "stores": {"booth": {"count": "lots", "error": "x\u200by"}}}))
        lib = library.Library(path)
        self.assertEqual(len(lib.data["items"]), 1)
        self.assertEqual(lib.data["items"][0]["name"], "Hoodie")
        self.assertIsNone(lib.data["items"][0]["url"])
        self.assertEqual(lib.data["items"][0]["files"], [])
        self.assertEqual(lib.data["stores"]["booth"]["count"], 0)
        path.write_text("{damaged")
        self.assertEqual(library.Library(path).data["items"], [])
        self.assertTrue(list(Path(self.tmp.name).glob("library.damaged-*.json")))


class TagHardening(unittest.TestCase):
    """Tags can't carry markup, invisible characters or object-breaking names, and tags.json is checked."""

    def test_tag_characters(self):
        for m in (tags,):
            self.assertEqual(m.clean_tag("<script>alert(1)</script>"), "script alert 1 script")
            self.assertEqual(m.clean_tag("rusk\u202efits"), "rusk fits")
            self.assertEqual(m.clean_tag("パーカー"), "パーカー")
            for name in ("__proto__", "constructor", "prototype", "__defineGetter__"):
                self.assertNotIn(m.clean_tag(name), m.TAG_RESERVED, name)
            self.assertEqual(m.clean_tag('a"b`c'), "a b c")

    def test_product_keys_must_be_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = tags.TagStore(Path(tmp) / "tags.json")
            for bad in ("booth:../../x", "evil:item", "booth:", "booth:<b>", "booth:a b"):
                with self.assertRaises(ValueError):
                    store.change({"action": "assign", "keys": [bad], "add": ["x"]})
            store.change({"action": "assign", "keys": [tags.tag_key("booth", "Rusk Avatar Base")], "add": ["x"]})
            self.assertEqual(len(store.load()["items"]), 1)
            self.assertTrue(tags.TAG_KEY_RX.match(tags.tag_key("booth", "♡♡♡")))

    def test_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = tags.TagStore(Path(tmp) / "tags.json")
            data = store.empty()
            data["tags"] = {f"tag{i}": {"match": None} for i in range(tags.TAG_LIMITS["tags"])}
            store._save(data)
            with self.assertRaises(ValueError):
                store.change({"action": "create", "name": "one too many"})
            with self.assertRaises(ValueError):
                store.change({"action": "assign", "keys": ["booth:a"] * (tags.TAG_LIMITS["keys_per_change"] + 1), "add": ["x"]})

    def test_tampered_file_is_cleaned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.json"
            path.write_text(json.dumps({"tags": {"ok": {"match": "ok"}, "<b>": {}, "__proto__": {}, "bad\u202e": None,
                                                 "fine": "not a dict"},
                                        "items": {"booth:item": ["ok", "<b>", 5], "../x": ["ok"], "booth:y": "ok"},
                                        "excluded": [], "hidden": ["good", "<bad>", 7]}))
            data = tags.TagStore(path).load()
            for name in data["tags"]:
                self.assertEqual(tags.clean_tag(name), name)
                self.assertNotIn(name, tags.TAG_RESERVED)
            self.assertEqual(sorted(data["tags"]), ["b", "bad", "fine", "ok", "proto"])  # converted, never raw
            self.assertEqual(data["items"], {"booth:item": ["b", "ok"]})
            self.assertEqual(data["hidden"], ["good"])

    def test_old_tag_names_are_converted_not_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.json"
            path.write_text(json.dumps({"tags": {"fox/dog": {"match": None}, "fox dog": {"match": "fox"}},
                                        "items": {"booth:a": ["fox/dog"], "booth:b": ["fox dog"]}}))
            data = tags.TagStore(path).load()
            self.assertEqual(data["tags"], {"fox dog": {"match": "fox"}})
            self.assertEqual(data["items"], {"booth:a": ["fox dog"], "booth:b": ["fox dog"]})

    def test_damaged_file_is_kept_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.json"
            path.write_text("{this is damaged")
            store = tags.TagStore(path)
            store.change({"action": "create", "name": "new"})
            self.assertEqual(sorted(store.load()["tags"]), ["new"])
            aside = list(Path(tmp).glob("tags.damaged-*.json"))
            self.assertEqual(len(aside), 1)
            self.assertEqual(aside[0].read_text(), "{this is damaged")

    @unittest.skipUnless(os.name == "posix", "file modes are a Linux and macOS feature")
    def test_tags_file_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = tags.TagStore(Path(tmp) / "Hoard" / "tags.json")
            store.change({"action": "create", "name": "x"})
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)

    def test_requests_are_small_and_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": tmp}, lan=False)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                def post(body, claimed=None):
                    c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
                    c.putrequest("POST", "/api/tags")
                    c.putheader("Content-Type", "application/json")
                    c.putheader(safety.ACCESS_HEADER, srv.key)
                    c.putheader("Content-Length", str(claimed or len(body)))
                    c.endheaders(body)
                    r = c.getresponse(); r.read(); c.close()
                    return r.status
                self.assertEqual(post(b"{}", claimed=2 * 1024 * 1024), 413)  # refused from its size, unread
                self.assertEqual(post(b"[" * 50000 + b"]" * 50000), 400)
                self.assertEqual(post(b"[1, 2]"), 400)
            finally:
                srv.shutdown()
                srv.server_close()


class StoreLinks(unittest.TestCase):
    """An edited record can't send you anywhere but the item's own store."""

    def test_rule(self):
        for m in (safety,):
            ok = [("booth", "https://booth.pm/ja/items/1"), ("Booth", "https://kitsu.booth.pm/items/2"),
                  ("gumroad", "https://app.gumroad.com/d/abc"), ("gumroad", "https://creator.gumroad.com/l/x"),
                  ("jinxxy", "https://jinxxy.com/creator/item"), ("payhip", "https://payhip.com/b/AbC1")]
            bad = [("booth", "https://booth.pm.evil.example/"), ("booth", "https://evil.example/booth.pm"),
                   ("booth", "https://booth.pm@evil.example/"), ("booth", "http://booth.pm/items/1"),
                   ("booth", "https://b\u043e\u043eth.pm/"), ("booth", "https://xn--bth-ted.pm/"),
                   ("booth", "https://app.gumroad.com/d/x"), ("payhip", "https://payhip.com:8443/b/x"),
                   ("booth", "javascript:alert(1)"), ("nowhere", "https://booth.pm/"), ("booth", None)]
            for store, url in ok:
                self.assertEqual(m.store_link(store, url), url, (m.__name__, url))
            for store, url in bad:
                self.assertIsNone(m.store_link(store, url), (m.__name__, store, url))

    def test_pages_use_the_same_rule(self):
        for page in PAGES:
            html = page.read_text("utf-8")
            js = re.search(r"const STORE_SITES = (\{.*?\});", html).group(1)
            sites = json.loads(re.sub(r"(\w+):", r'"\1":', js))
            self.assertEqual({k: tuple(v) for k, v in sites.items()}, safety.STORE_LINK_SITES, page.name)
            for field in ("a.url", "a.download_url", "a.creator_url", "f.url"):
                for use in re.findall(r"href=\"\$\{esc\((\w+)\([^)]*" + re.escape(field) + r"\)\)\}", html):
                    self.assertEqual(use, "storeUrl", f"{page.name}: {field} must be checked with storeUrl")


class Seals(unittest.TestCase):
    """Edits made by other programs are noticed, and their links aren't trusted."""

    def setUp(self):
        reset_keys()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_states(self):
        for m in (safety,):
            reset_keys()
            path = self.dir / f"{m.__name__}.json"
            sealed = m.seal({"assets": {"1": {"url": "https://booth.pm/ja/items/1"}}})
            self.assertEqual(m.check_seal(sealed, path), "sealed")
            edited = json.loads(json.dumps(sealed))
            edited["assets"]["1"]["url"] = "https://booth.pm/ja/items/666"
            self.assertEqual(m.check_seal(edited, path), "changed")
            stripped = {k: v for k, v in sealed.items() if k != "integrity"}
            self.assertEqual(m.check_seal(stripped, path), "unsealed")   # never sealed there: an older version's file
            m.remember_sealed(path)
            self.assertEqual(m.check_seal(stripped, path), "changed")    # sealed there before: the seal was removed
            other = json.loads(json.dumps(sealed))
            other["integrity"]["key_id"] = "0" * 16
            self.assertEqual(m.check_seal(other, path), "foreign")

    def test_nothing_sealed_is_forgotten(self):
        """S-05 (2.3.1 review): the list of sealed files kept only its 20,000 alphabetically last entries, so any
        other could be dropped, and a seal later removed from that file would pass as an older version's file."""
        reset_keys()
        self.addCleanup(reset_keys)
        first = self.dir / "first.json"
        safety.remember_sealed(first)
        safety._sealed_file_ids().update(f"z{n:031x}" for n in range(20000))   # 20,000 more, all sorting after it
        safety.remember_sealed(self.dir / "latest.json")
        safety._sealed_ids = None   # read back from the file, as the next start would
        stripped = {"assets": {}}
        self.assertEqual(safety.check_seal(stripped, first), "changed", "still known as sealed: its seal was removed")

    def test_key_is_private_and_shared_by_the_tools(self):
        key = safety.integrity_key()
        self.assertEqual(safety.integrity_key(), key)
        self.assertEqual(safety.integrity_key(), key)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE((_TEST_HOME / "Hoard" / "integrity.key").stat().st_mode), 0o600)

    def _download_folder(self):
        root = self.dir / "downloads"
        folder = root / "Booth" / "Kitsu Studio" / "Rusk"
        folder.mkdir(parents=True)
        (folder / "rusk.zip").write_bytes(b"zip")
        man = downloader.Manifest(root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Rusk")
        rec.update(name="Rusk", creator="Kitsu Studio", url="https://booth.pm/ja/items/111")
        rec["files"]["f1"] = {"path": "rusk.zip", "size": 3}
        man.save()
        return root

    def test_a_tool_changing_a_manifest_link_is_caught(self):
        root = self._download_folder()
        path = root / "Booth" / "_manifest.json"
        data = json.loads(path.read_text("utf-8"))
        data["assets"]["111"]["url"] = "https://booth.pm/ja/items/666"   # same store, different page: only the seal notices
        path.write_text(json.dumps(data))
        cfg = json.loads(json.dumps(config.DEFAULT_CONFIG))
        self.assertEqual(downloader.cmd_verify(cfg, root), 1, "verify reports the change")
        self.assertEqual(downloader.cmd_verify(cfg, root), 0, "and settles it: records kept, links dropped, sealed again")
        man = downloader.Manifest(root / "Booth")
        self.assertIsNone(man.assets["111"]["url"], "a changed manifest's links must not be used")
        self.assertIn("rusk.zip", [f["path"] for f in man.assets["111"]["files"].values()], "records are kept")
        self.assertTrue(list((root / "Booth").glob("_manifest.changed-*.json")), "a copy is kept to look at")

    def test_older_unsealed_manifests_keep_only_store_links(self):
        root = self.dir / "downloads"
        (root / "Booth" / "A" / "B").mkdir(parents=True)
        (root / "Booth" / "_manifest.json").write_text(json.dumps({"assets": {
            "1": {"folder": "A/B", "name": "Good", "creator": "A", "url": "https://booth.pm/ja/items/1", "files": {}},
            "2": {"folder": "A/B", "name": "Phish", "creator": "A", "url": "https://booth-login.example/", "files": {}}}}))
        man = downloader.Manifest(root / "Booth")
        self.assertEqual(man.assets["1"]["url"], "https://booth.pm/ja/items/1")
        self.assertIsNone(man.assets["2"]["url"])

    def test_a_tool_changing_asset_json_is_caught_and_repaired(self):
        root = self._download_folder()
        cfg = json.loads(json.dumps(config.DEFAULT_CONFIG))
        downloader.build_catalog(cfg, root)
        asset_path = root / "Booth" / "Kitsu Studio" / "Rusk" / "asset.json"
        for name in ("catalog.json", "tags.json"):
            self.assertEqual(safety.check_seal(json.loads((root / name).read_text("utf-8"))), "sealed", name)
        asset = json.loads(asset_path.read_text("utf-8"))
        self.assertEqual(safety.check_seal(asset), "sealed")
        asset["url"] = "https://booth-login.example/"
        asset_path.write_text(json.dumps(asset))
        self.assertEqual(safety.check_seal(json.loads(asset_path.read_text("utf-8"))), "changed")
        self.assertEqual(downloader.cmd_verify(cfg, root), 1, "verify reports the change")
        repaired = json.loads(asset_path.read_text("utf-8"))
        self.assertEqual(repaired["url"], "https://booth.pm/ja/items/111")
        self.assertEqual(safety.check_seal(repaired), "sealed")
        self.assertEqual(downloader.cmd_verify(cfg, root), 0)

    def test_a_tool_changing_hoards_list_is_caught(self):
        path = self.dir / "library.json"
        lib = library.Library(path)
        lib.data["items"] = [library.item("booth", "1", name="Rusk", url="https://booth.pm/ja/items/1",
                                          download_url="https://accounts.booth.pm/orders/1", thumbnail="https://booth.pximg.net/x.jpg")]
        lib.data["stores"] = {"booth": {"count": 1}}
        lib.save()
        self.assertEqual(library.Library(path).data["items"][0]["url"], "https://booth.pm/ja/items/1")
        data = json.loads(path.read_text("utf-8"))
        data["items"][0]["download_url"] = "https://booth.pm/ja/items/666"
        path.write_text(json.dumps(data))
        reloaded = library.Library(path)
        item = reloaded.data["items"][0]
        self.assertEqual((item["url"], item["download_url"], item["thumbnail"]), (None, None, None))
        self.assertIn("changed by something other than Hoard", reloaded.data["stores"]["booth"]["error"])

    def test_hoard_drops_links_to_other_sites_even_in_old_lists(self):
        path = self.dir / "old-library.json"
        path.write_text(json.dumps({"items": [{"store": "booth", "id": "1", "name": "X",
                                               "url": "https://booth-login.example/", "download_url": "https://booth.pm/ja/items/1"}]}))
        item = library.Library(path).data["items"][0]
        self.assertIsNone(item["url"])
        self.assertEqual(item["download_url"], "https://booth.pm/ja/items/1")


class SupplyChain(unittest.TestCase):
    """H-04, H-05, H-06: dependencies are locked with hashes, and workflow actions pinned to commits."""

    def test_requirements_are_locked(self):
        text = (REPO / "requirements.txt").read_text("utf-8")
        blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text)
        pinned = [b for b in blocks if re.match(r"[A-Za-z0-9_.-]+==", b)]
        self.assertTrue(pinned)
        for block in pinned:
            self.assertIn("--hash=sha256:", block, f"{block.splitlines()[0]} has no hash")
        versions = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", text, re.M))
        self.assertGreaterEqual(tuple(int(x) for x in versions["requests"].split(".")[:3]), (2, 32, 4),
                                "requests below 2.32.4 has known vulnerabilities")

    def test_setup_checks_hashes(self):
        self.assertIn("--require-hashes", (REPO / "Setup.bat").read_text("utf-8"))
        self.assertIn("--require-hashes", (REPO / "setup.sh").read_text("utf-8"))

    def test_no_hidden_characters_in_the_project(self):
        """Invisible formatting characters can make code or text read differently from how it runs ("Trojan Source")."""
        import unicodedata
        found = []
        for path in REPO.rglob("*"):
            if (path.is_file() and path.suffix in (".py", ".html", ".md", ".yml", ".bat", ".sh", ".json", ".in", ".txt")
                    and not {"dist", ".git", ".venv", "__pycache__"} & set(path.parts)):
                for n, line in enumerate(path.read_text("utf-8", errors="replace").splitlines(), 1):
                    found += [f"{path.relative_to(REPO)}:{n} U+{ord(c):04X}" for c in line if unicodedata.category(c) == "Cf"]
        self.assertEqual(found, [], "hidden characters found")

    def test_actions_are_pinned_to_commits(self):
        for wf in (REPO / ".github" / "workflows").glob("*.yml"):
            for ref in re.findall(r"uses:\s*(\S+)", wf.read_text("utf-8")):
                self.assertRegex(ref, r"@[0-9a-f]{40}$", f"{wf.name}: {ref} isn't pinned to a commit")


def _test_server():
    """A tiny local web server, to prove fetches refuse this computer."""
    import http.server as hs

    class H(hs.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(b"\x89PNG")

        def log_message(self, *a):
            pass

    srv = hs.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ----------------------------------------------------------------------------- the 2.1.0 audit (H-01 to H-12)

import http.server  # noqa: E402

from hoard import downloads, egress  # noqa: E402


class _Hops(http.server.BaseHTTPRequestHandler):
    """A test server: /go?to=<address> redirects there; /file sends a file; every request is recorded."""
    seen: list = []

    def do_GET(self):
        type(self).seen.append((self.server.server_port, self.path, self.headers.get("Cookie")))
        if self.path.startswith("/go?to="):
            self.send_response(302)
            self.send_header("Location", urllib.parse.unquote(self.path[len("/go?to="):]))
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"DATA")

    def log_message(self, *a):
        pass


def _hop_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hops)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Egress(unittest.TestCase):
    """Every store download and request goes through one checked path (H-01, H-02, H-03)."""

    @classmethod
    def setUpClass(cls):
        cls.store, cls.other = _hop_server(), _hop_server()
        cls.store_origin = f"http://127.0.0.1:{cls.store.server_port}"

    @classmethod
    def tearDownClass(cls):
        for srv in (cls.store, cls.other):
            srv.shutdown()
            srv.server_close()

    def setUp(self):
        egress._TEST_ORIGINS.clear()
        egress._TEST_ORIGINS.add(self.store_origin)   # only the stand-in store itself; everything else is real
        _Hops.seen.clear()
        self.addCleanup(egress._TEST_ORIGINS.clear)
        self.dest = Path(tempfile.mkdtemp()) / "file.bin"

    def redirect(self, *targets):
        url = targets[-1]
        for hop in reversed(targets[:-1]):
            url = f"{hop}/go?to={urllib.parse.quote(url, safe='')}"
        return url

    def test_no_test_origins_in_normal_use(self):
        self.assertEqual(egress._TEST_ORIGINS - {self.store_origin}, set())
        egress._TEST_ORIGINS.clear()
        import importlib
        self.assertEqual(importlib.reload(egress)._TEST_ORIGINS, set())

    def test_redirects_to_this_computer_or_network_are_refused(self):
        other = self.other.server_port
        for target in (f"http://127.0.0.1:{other}/secret", f"https://127.0.0.1:{other}/secret", "https://localhost/secret",
                       "https://169.254.169.254/latest/meta-data/", "https://10.0.0.1/", "https://[::1]/", "https://192.168.1.1/",
                       "file:///etc/passwd", "ftp://example.com/x"):
            for chain in ((self.store_origin, target), (self.store_origin, self.store_origin, self.store_origin, target)):
                with self.subTest(target=target, hops=len(chain)):
                    _Hops.seen.clear()
                    with self.assertRaises(Exception):
                        egress.download(egress.session(), self.redirect(*chain), self.dest, ["127.0.0.1"])
                    self.assertFalse(self.dest.exists(), "nothing is written")
                    self.assertFalse([s for s in _Hops.seen if s[0] == other], "the refused address is never contacted")

    def test_store_cookies_never_leave_the_store(self):
        other_origin = f"http://localhost:{self.other.server_port}"
        egress._TEST_ORIGINS.add(other_origin)      # a stand-in "CDN" the store redirects to
        sess = egress.session()
        sess.cookies.set("store_session", "secret", domain="127.0.0.1", path="/")
        size = egress.download(sess, self.redirect(self.store_origin, f"{other_origin}/file"), self.dest, ["127.0.0.1"])
        self.assertEqual(size, 4)
        cookies = {port: cookie for port, _path, cookie in _Hops.seen}
        self.assertIn("store_session=secret", cookies[self.store.server_port] or "")
        self.assertIsNone(cookies[self.other.server_port], "the file host gets no cookies at all")

    def test_api_redirects_stay_on_the_store(self):
        other_origin = f"http://localhost:{self.other.server_port}"
        egress._TEST_ORIGINS.add(other_origin)
        with self.assertRaises(egress.UnsafeRequest):
            egress.get(egress.session(), self.redirect(self.store_origin, f"{other_origin}/api"), ["127.0.0.1"])

    def test_plain_http_and_credentials_are_refused(self):
        egress._TEST_ORIGINS.clear()
        for url in ("http://booth.pm/downloadables/1", "https://user:pw@booth.pm/x"):
            with self.assertRaises(egress.UnsafeRequest):
                egress.check_hop(url)
            with self.assertRaises(Exception):
                egress.session().get(url.replace("https://user:pw@", "http://"), timeout=5)
        self.assertFalse(downloader.store_url("http://booth.pm/downloadables/1", ["booth.pm"]), "store links are https only")
        self.assertTrue(downloader.store_url("https://booth.pm/downloadables/1", ["booth.pm"]))

    def test_no_other_way_out(self):
        """No module makes its own requests: only egress (store traffic) and safety.fetch_public (public images)."""
        for f in (REPO / "hoard").glob("*.py"):
            if f.name in ("egress.py", "safety.py"):
                continue
            text = f.read_text("utf-8")
            if f.name == "app.py":   # Hoard talking to itself: one call, behind a check that it's this computer only
                self.assertEqual(text.count("urlopen("), 1)
                self.assertIn("if not re_local.match(url):", text)
                text = text.replace("urllib.request.urlopen(req, timeout=timeout)", "")
            self.assertNotRegex(text, r"requests\.(get|post|Session)\(|\bsess\.get\(|urlopen\(", f.name)
        from hoard import app
        for url in ("https://example.com/", "http://127.0.0.1.evil.example/", "http://localhost:80/", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                app.local_request(url)


FILE = bytes(range(256)) * 4   # 1024 bytes: any misplaced part shows


class _Ranges(http.server.BaseHTTPRequestHandler):
    """A test server for resumed downloads: /file sends `file`, answering a Range the way `mode` says."""
    file, mode, asked = FILE, "honest", []

    def do_GET(self):
        body, rng, mode = type(self).file, self.headers.get("Range"), type(self).mode
        type(self).asked.append(rng)
        if not rng:
            return self.reply(200, body)
        start = int(rng[len("bytes="):-1])
        whole = len(body)
        if start >= whole:
            return self.reply(416, b"", {} if mode == "416 without a size" else {"Content-Range": f"bytes */{whole}"})
        if mode == "the wrong part":
            start //= 2
        end = min(start + 100, whole) if mode == "a short part" else whole
        headers = {} if mode == "no Content-Range" else {"Content-Range": f"bytes {start}-{end - 1}/{whole}"}
        return self.reply(206, body[start:end], headers)

    def reply(self, status, body, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class Resuming(unittest.TestCase):
    """B-03 (2.3.1 review): a .part file left from last time is only added to with the part that follows it, and only
    counts as finished when the store says the file ends there. Otherwise the file starts again, rather than being
    joined from two different ones; and a file shorter than the store said is never put in place."""

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Ranges)
        cls.srv.daemon_threads = True
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.origin = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        egress._TEST_ORIGINS.clear()
        egress._TEST_ORIGINS.add(self.origin)
        self.addCleanup(egress._TEST_ORIGINS.clear)
        _Ranges.file, _Ranges.mode, _Ranges.asked = FILE, "honest", []
        self.dest = Path(tempfile.mkdtemp()) / "file.bin"
        self.part = self.dest.with_name("file.bin.part")

    def download(self):
        return egress.download(egress.session(), f"{self.origin}/file", self.dest, ["127.0.0.1"])

    def test_the_rest_is_added(self):
        self.part.write_bytes(FILE[:300])
        self.assertEqual(self.download(), len(FILE))
        self.assertEqual(self.dest.read_bytes(), FILE)
        self.assertEqual(_Ranges.asked, ["bytes=300-"])

    def test_the_wrong_part_is_never_added(self):
        for mode in ("the wrong part", "no Content-Range"):
            with self.subTest(mode):
                _Ranges.mode, _Ranges.asked = mode, []
                self.part.write_bytes(FILE[:600])
                self.dest.unlink(missing_ok=True)
                self.download()
                self.assertEqual(self.dest.read_bytes(), FILE)
                self.assertEqual(_Ranges.asked, ["bytes=600-", None], "started again, from the beginning")

    def test_a_finished_part_is_used(self):
        self.part.write_bytes(FILE)
        self.assertEqual(self.download(), len(FILE))
        self.assertEqual(self.dest.read_bytes(), FILE)
        self.assertEqual(_Ranges.asked, ["bytes=1024-"], "nothing downloaded again")

    def test_an_old_part_of_a_changed_file_isnt_used(self):
        """The creator uploaded a smaller version: the store has nothing past the .part file, but it isn't this file."""
        _Ranges.file = b"new version" * 10
        self.part.write_bytes(FILE)
        self.download()
        self.assertEqual(self.dest.read_bytes(), b"new version" * 10)
        self.assertEqual(_Ranges.asked, ["bytes=1024-", None])

    def test_a_finished_part_needs_the_store_to_say_so(self):
        _Ranges.mode = "416 without a size"
        self.part.write_bytes(FILE)
        self.download()
        self.assertEqual(self.dest.read_bytes(), FILE)
        self.assertEqual(_Ranges.asked, ["bytes=1024-", None])

    def test_a_short_answer_waits_for_next_time(self):
        _Ranges.mode = "a short part"
        self.part.write_bytes(FILE[:300])
        with self.assertRaises(RuntimeError):
            self.download()
        self.assertFalse(self.dest.exists(), "never put in place while it's short")
        self.assertEqual(self.part.read_bytes(), FILE[:400], "what arrived is kept")
        _Ranges.mode = "honest"
        self.download()
        self.assertEqual(self.dest.read_bytes(), FILE)
        self.assertEqual(_Ranges.asked[-1], "bytes=400-")

    def test_downloads_ask_for_the_files_own_bytes(self):
        """Compression would make sizes and byte ranges mean something else."""
        seen = []
        real = egress._send
        with mock.patch.object(egress, "_send", lambda *a, **k: seen.append(k["headers"]) or real(*a, **k)):
            self.download()
        self.assertEqual(seen[0].get("Accept-Encoding"), "identity")


class EgressOverHTTPS(unittest.TestCase):
    """The real HTTPS path (not the tests' plain-http stand-ins): a store redirecting to its file host, as Gumroad
    and Booth do. Names ending .localhost stand for public hosts; every other name is checked as usual."""

    @classmethod
    def setUpClass(cls):
        import ssl
        data = REPO / "tests" / "data"
        cls.cert = str(data / "localhost-cert.pem")
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hops)
        tls = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        tls.load_cert_chain(cls.cert, str(data / "localhost-key.pem"))
        srv.socket = tls.wrap_socket(srv.socket, server_side=True)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        cls.srv, cls.port = srv, srv.server_port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        import socket
        real_lookup, real_session = safety._public_addresses, egress.session

        def lookup(host, port):
            if host.endswith(".localhost"):   # stands for a public host, served by the test server
                return [(socket.AF_INET, ("127.0.0.1", port))]
            return real_lookup(host, port)

        def trusting(user_agent=""):
            sess = real_session(user_agent)
            sess.verify = self.cert
            return sess
        safety._public_addresses, egress.session = lookup, trusting
        self.addCleanup(setattr, safety, "_public_addresses", real_lookup)
        self.addCleanup(setattr, egress, "session", real_session)
        _Hops.seen.clear()
        self.dest = Path(tempfile.mkdtemp()) / "file.bin"

    def test_a_store_redirecting_to_its_file_host(self):
        """What Gumroad does for every file: 2.1.1 refused the redirect outright ("Exceeded 0 redirects")."""
        sess = egress.session()
        sess.cookies.set("store_session", "secret", domain="store.localhost", path="/")
        cdn = urllib.parse.quote(f"https://cdn.localhost:{self.port}/file", safe="")
        self.assertEqual(egress.download(sess, f"https://store.localhost:{self.port}/go?to={cdn}", self.dest, ["store.localhost"]), 4)
        self.assertEqual(self.dest.read_bytes(), b"DATA")
        cookies = [cookie for _port, path, cookie in _Hops.seen]
        self.assertEqual(cookies, ["store_session=secret", None], "the store gets its cookie; the file host none")
        r = egress.get(sess, f"https://store.localhost:{self.port}/go?to=" +
                       urllib.parse.quote(f"https://store.localhost:{self.port}/page", safe=""), ["store.localhost"])
        self.assertEqual(r.status_code, 200, "pages and APIs follow redirects on the store's own site")

    def test_redirects_home_are_still_refused(self):
        home = urllib.parse.quote(f"https://localhost:{self.port}/secret", safe="")
        with self.assertRaises(Exception):
            egress.download(egress.session(), f"https://store.localhost:{self.port}/go?to={home}", self.dest, ["store.localhost"])
        self.assertEqual([path for _port, path, _c in _Hops.seen if path == "/secret"], [], "never contacted")
        self.assertFalse(self.dest.exists())

    def test_session_settings(self):
        sess = egress.session()
        self.assertFalse(sess.trust_env)
        self.assertGreater(sess.max_redirects, 0, "requests refuses every redirect answer at 0, even when not following")


@unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs symlinks")
class FileRaces(unittest.TestCase):
    """Files are written and served without being redirected by a link or a swap (H-04, H-05)."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.outside = Path(tempfile.mkdtemp()) / "victim.txt"
        self.outside.write_text("keep me")

    def test_a_planted_link_is_never_written_through(self):
        part = self.dir / "file.zip.part"
        part.symlink_to(self.outside)
        with self.assertRaises(safety.UnsafePath):
            safety.open_part(part, resume=True)          # resuming never follows a link
        fh, identity = safety.open_part(part, resume=False)   # starting fresh removes the link, never follows it
        with fh:
            fh.write(b"new")
        self.assertEqual(self.outside.read_text(), "keep me")
        safety.move_into_place(part, self.dir / "file.zip", identity)
        self.assertEqual((self.dir / "file.zip").read_bytes(), b"new")

    def test_a_swapped_part_file_is_not_used(self):
        part = self.dir / "file.zip.part"
        fh, identity = safety.open_part(part, resume=False)
        with fh:
            fh.write(b"real")
        part.unlink()
        part.symlink_to(self.outside)                    # swapped for a link after writing
        with self.assertRaises(safety.UnsafePath):
            safety.move_into_place(part, self.dir / "file.zip", identity)
        self.assertFalse((self.dir / "file.zip").exists())
        self.assertEqual(self.outside.read_text(), "keep me")

    def test_served_files_never_follow_links(self):
        (self.dir / "Booth" / "Creator" / "Item").mkdir(parents=True)
        (self.dir / "Booth" / "Creator" / "Item" / "_thumbnail.png").write_bytes(b"PNG")
        with safety.open_under(self.dir, "Booth/Creator/Item/_thumbnail.png") as fh:
            self.assertEqual(fh.read(), b"PNG")
        (self.dir / "Booth" / "Creator" / "Leak").symlink_to(self.outside.parent)
        (self.dir / "Booth" / "Creator" / "Item" / "_link.png").symlink_to(self.outside)
        for rel in ("Booth/Creator/Leak/victim.txt", "Booth/Creator/Item/_link.png", "../x", "Booth/../../x"):
            with self.subTest(rel=rel), self.assertRaises(safety.UnsafePath):
                safety.open_under(self.dir, rel).close()


class NameCollisions(unittest.TestCase):
    """Names that clean up alike never share a folder or overwrite each other (H-08)."""

    def test_folders(self):
        man = downloader.Manifest(Path(tempfile.mkdtemp()) / "Booth")
        a = man.record("1", "Creator", "My:Asset")
        b = man.record("2", "Creator", "My?Asset")
        c = man.record("3", "creator", "MY_ASSET")      # the same folder on Windows and macOS
        self.assertEqual(len({x["folder"].casefold() for x in (a, b, c)}), 3)
        self.assertEqual(man.record("2", "Creator", "My?Asset")["folder"], b["folder"], "stable across runs")

    def test_files(self):
        rec = {"files": {"101": {"path": "Model_v1.zip"}}}
        self.assertEqual(downloader.distinct_name("model_v1.zip", "101", rec, {"101", "102"}), "model_v1.zip")
        tagged = downloader.distinct_name("Model:v1.zip".replace(":", "_"), "102", rec, {"101", "102"})
        self.assertNotEqual(tagged.casefold(), "model_v1.zip", "both files are still offered: keep both")
        self.assertTrue(tagged.endswith(".zip"))
        self.assertEqual(downloader.distinct_name("Model_v1.zip", "103", rec, {"103"}), "Model_v1.zip",
                         "the old file is no longer offered: this is the creator's update, which replaces it")


class Diagnostics(unittest.TestCase):
    """What the troubleshooting commands save is scrubbed by default (H-09)."""

    def test_scrub(self):
        page = ('<meta name="csrf-token" content="abcDEF123"><input value="QWERT-12345-ASDFG-67890">'
                '<p>me@example.com</p><a href="https://cdn.example/f.zip?X-Amz-Signature=deadbeef&Expires=99">f</a>'
                '<div data-transaction-key="0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"></div>')
        clean = safety.scrub(page)
        for secret in ("abcDEF123", "QWERT-12345", "me@example.com", "deadbeef", "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"):
            self.assertNotIn(secret, clean)
        self.assertIn("X-Amz-Signature=", clean, "the page's structure stays")
        from hoard import cli
        self.assertEqual(cli.reader_summary([{"name": "Secret Purchase", "files": [1, 2]}, {"name": ""}]),
                         {"items": 2, "fields_filled": {"name": 1, "files": 1}, "files": 2})


class SmallerFindings(unittest.TestCase):
    """H-07 (shop names), H-10 (manifests), H-11 (server limits), H-12 (sign-in location)."""

    def test_deceptive_shop_names_are_refused(self):
        for bad in ("xn--pypal-4ve.store", "shop.xn--p1ai", "-shop.store", "shop-.store", "a..b.store"):
            self.assertIsNone(config.clean_payhip_shop(bad), bad)

    def test_odd_manifests_dont_break_the_index(self):
        root = Path(tempfile.mkdtemp())
        for store, text in (("Booth", '{"assets": []}'), ("Gumroad", "[1, 2]"), ("Jinxxy", '{"assets": {"a": "x"}}'),
                            ("Payhip", "[" * 100000)):
            (root / store).mkdir()
            (root / store / "_manifest.json").write_text(text)
        status = downloads.library_status(root)
        self.assertTrue(all(s["assets"] in (0, -1) for s in status["stores"].values()))

    def test_server_limits(self):
        self.assertTrue(0 < server.Handler.timeout <= 60)
        self.assertTrue(0 < server.MAX_CONNECTIONS <= 256)

    def test_sign_in_location(self):
        cfg = {**config.load_config(), "profile_dir": str(Path(tempfile.mkdtemp()) / "elsewhere")}
        self.assertEqual(browser.signins_root(cfg), browser.app_data_dir() / "sign-ins", "ignored without advanced mode")
        cfg["advanced_signin_location"] = True
        self.assertEqual(browser.signins_root(cfg), Path(cfg["profile_dir"]))
        self.assertIn("folder you chose", browser.signin_protection(cfg))
        cfg["profile_dir"] = "//fileserver/share/signins"
        with self.assertRaises(browser.SigninsUnprotected):
            browser.signins_root(cfg)


if __name__ == "__main__":
    unittest.main()
