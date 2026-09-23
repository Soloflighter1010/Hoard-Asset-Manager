"""Security regression tests for Hoard and Hoard Downloader.

Run from the repository root:  python -m unittest discover -s tests -v

They need the packages in requirements.txt but no network, no store accounts and no browser, so they
run the same on any computer and in GitHub Actions. Each test names the review finding it guards.
"""
from __future__ import annotations

import http.client
import inspect
import json
import os
import re
import socket
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Hoard"))
sys.path.insert(0, str(REPO / "HoardDownloader"))

import asset_browser  # noqa: E402  Hoard Downloader's browser
import asset_dl  # noqa: E402  Hoard Downloader
import library  # noqa: E402  Hoard

_TEST_HOME = Path(tempfile.mkdtemp(prefix="hoard-tests-"))
for _m in (asset_dl, library, asset_browser):
    _m._hoard_folder = lambda: _TEST_HOME / "Hoard"


def reset_keys():
    """Start with no sealing key and no record of sealed files (as on a fresh install)."""
    import shutil
    shutil.rmtree(_TEST_HOME / "Hoard", ignore_errors=True)
    for m in (asset_dl, library, asset_browser):
        m._integrity_key, m._sealed_ids = None, None


WEB_SAFETY = (library, asset_browser)       # both servers carry the web-safety code
SIGN_INS = (library, asset_dl)              # both tools carry the sign-in code
PAGES = (REPO / "Hoard" / "library.html", REPO / "HoardDownloader" / "browser.html")


def fake_addrinfo(*ips):
    """getaddrinfo results for the given addresses."""
    out = []
    for ip in ips:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        out.append((family, socket.SOCK_STREAM, 6, "", (ip, 443) if family == socket.AF_INET else (ip, 443, 0, 0)))
    return out


class SharedCodeStaysIdentical(unittest.TestCase):
    """The tools each carry a copy of the security code; the copies must not drift apart."""

    def test_sign_in_code_matches(self):
        for name in ("signins_root", "profile_dir", "_launch", "launch_context", "sign_out", "check_saved_signin",
                     "linux_keyring", "unprotected_cookie_count", "_migrate_old_signins", "ProfileLock"):
            self.assertEqual(inspect.getsource(getattr(library, name)), inspect.getsource(getattr(asset_dl, name)), name)

    def test_web_safety_code_matches(self):
        for name in ("safe_url", "_is_public", "_public_addresses", "_connect_public", "fetch_public",
                     "content_security_policy", "check_access", "network_tls", "TLSServerMixin"):
            self.assertEqual(inspect.getsource(getattr(library, name)), inspect.getsource(getattr(asset_browser, name)), name)

    def test_data_file_code_matches(self):
        for name in ("clean_text", "read_json_file", "set_aside", "write_file_safely", "DataFileError", "store_link",
                     "integrity_key", "_canonical", "seal", "check_seal", "remember_sealed", "_sealed_file_ids"):
            src = inspect.getsource(getattr(asset_dl, name))
            self.assertEqual(src, inspect.getsource(getattr(library, name)), name)
            self.assertEqual(src, inspect.getsource(getattr(asset_browser, name)), name)

    def test_tag_code_matches(self):
        for name in ("tag_key", "clean_tag", "name_has_word", "TagStore", "tag_overview"):
            self.assertEqual(inspect.getsource(getattr(library, name)), inspect.getsource(getattr(asset_browser, name)), name)


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
        self.assertTrue(asset_dl.store_url("https://booth.pm/downloadables/1", ["booth.pm"]))
        self.assertFalse(asset_dl.store_url("https://evil.example/downloadables/1", ["booth.pm"]))
        self.assertFalse(asset_dl.store_url("https://booth.pm.evil.example/x", ["booth.pm"]))
        self.assertFalse(asset_dl.store_url("javascript:alert(1)", ["payhip.com"]))


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
            csp = library.content_security_policy(body)
            self.assertIn("script-src 'sha256-", csp)
            self.assertNotIn("unsafe-inline' https", csp)
            self.assertNotRegex(csp.split("script-src")[1].split(";")[0], "unsafe-inline")
            self.assertIn("frame-ancestors 'none'", csp)
            self.assertIn("font-src 'self'", csp)

    def test_pages_have_no_inline_handlers_or_outside_resources(self):
        for page in PAGES:
            html = page.read_text("utf-8")
            markup = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
            self.assertNotRegex(markup, r"\son[a-z]+=", f"{page.name}: inline event handler")
            self.assertEqual(len(re.findall(r"<script\b", html)), 1, page.name)
            self.assertNotRegex(html, r'<(link|script)[^>]+(href|src)="https?://', f"{page.name} loads something from outside")

    def test_server_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            srv = asset_browser.BrowserServer(("127.0.0.1", 0), Path(tmp), lambda: [], lan=False, version="test")
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                port = srv.server_port
                def get(path, headers=None, method="GET", body=None):
                    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                    c.request(method, path, body=body, headers=headers or {})
                    r = c.getresponse()
                    r.read()
                    return r
                page = get("/")
                self.assertIn("script-src 'sha256-", page.getheader("Content-Security-Policy"))
                self.assertEqual(page.getheader("X-Frame-Options"), "DENY")
                self.assertEqual(get("/api/assets").getheader("Content-Security-Policy"), "default-src 'none'; sandbox")
                self.assertEqual(get("/", {"Host": "evil.example"}).status, 403)              # DNS rebinding of the page
                self.assertEqual(get("/files/..%2F..%2Fetc%2Fpasswd").status, 404)            # path traversal
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

    def _access(self, m, *, key, path="/", cookie=None, client="192.0.2.7", tls=False):
        sent = {"status": None, "headers": {}}
        handler = mock.Mock()
        handler.headers = {"Host": "hoard.lan:8766", **({"Cookie": cookie} if cookie else {})}
        handler.client_address = (client, 50000)
        handler.path = path
        handler.server = mock.Mock(tls=tls)
        handler.send_response.side_effect = lambda code: sent.update(status=code)
        handler.send_header.side_effect = lambda k, v: sent["headers"].update({k: v})
        allowed = m.check_access(handler, True, key)
        return allowed, sent

    def test_other_devices_need_the_key(self):
        for m in WEB_SAFETY:
            allowed, sent = self._access(m, key="s3cret")
            self.assertFalse(allowed)
            self.assertEqual(sent["status"], 401)
            allowed, sent = self._access(m, key="s3cret", path="/?key=wrong")
            self.assertEqual(sent["status"], 401)
            allowed, _ = self._access(m, key="s3cret", cookie="hoard_key=s3cret")
            self.assertTrue(allowed)

    def test_cookie_is_secure_over_https(self):
        for m in WEB_SAFETY:
            _, sent = self._access(m, key="s3cret", path="/?key=s3cret", tls=True)
            self.assertEqual(sent["status"], 303)
            self.assertIn("; Secure", sent["headers"]["Set-Cookie"])
            self.assertIn("HttpOnly", sent["headers"]["Set-Cookie"])


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
        self.assertNotIn("session_cookie", asset_dl.DEFAULT_CONFIG["gumroad"])
        cfg = json.loads(json.dumps(asset_dl.DEFAULT_CONFIG))
        cfg["gumroad"]["session_cookie"] = "stolen-looking-value"
        with mock.patch.dict(os.environ, {"HOARD_GUMROAD_SESSION": "another"}), \
                mock.patch.object(asset_dl, "browser_cookies", return_value=([], "UA")) as from_browser:
            with self.assertRaises(asset_dl.NotLoggedIn):
                asset_dl.gumroad_session(cfg)
        from_browser.assert_called_once()


class Files(unittest.TestCase):
    """Names from stores can't escape the download folder or hit reserved Windows names."""

    def test_safe_names(self):
        for bad in ("..", "../..", "a/b\\c", "CON", "nul.txt", "a:b*c?d", " .hidden. "):
            name = asset_dl.safe_name(bad)
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)
            self.assertNotIn("..", name.strip("_"))
            self.assertNotEqual(name.split(".")[0].upper(), "CON")

    def test_downloads_browser_stays_inside_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for attempt in ("../../etc/passwd", "..\\..\\windows\\win.ini", "/etc/passwd", "a/../../b"):
                joined = asset_browser.safe_join(root, attempt)
                self.assertTrue(joined is None or joined == root or root in joined.parents, attempt)


class Tags(unittest.TestCase):
    """Tag names are cleaned, and two programs saving at once lose nothing."""

    def test_clean_tag(self):
        self.assertEqual(library.clean_tag("  #Rusk, Outfits  "), "rusk outfits")
        self.assertEqual(len(library.clean_tag("x" * 100)), 40)

    def test_concurrent_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = library.TagStore(Path(tmp) / "tags.json")
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
            name = asset_dl.safe_name(bad)
            self.assertFalse(any(__import__("unicodedata").category(c)[0] == "C" for c in name), repr(name))
        self.assertEqual(asset_dl.safe_name(self.SPOOF), "Cute Hoodiegpj.exe")
        self.assertEqual(asset_dl.safe_name("【VRChat想定】パーカー"), "【VRChat想定】パーカー")

    def test_clean_text(self):
        for m in (asset_dl, library, asset_browser):
            self.assertEqual(m.clean_text("  A\u202eB\u200bC\x07D\n\tE  "), "AB C D E".replace("B C", "BC ") if False else "ABC D E")
            self.assertEqual(len(m.clean_text("x" * 1000, 300)), 300)
            self.assertEqual(m.clean_text(None), "")


class Paths(unittest.TestCase):
    """Paths read from data files can never lead outside their folder."""

    def test_only_plain_relative_paths(self):
        for bad in ("../x", "a/../../b", "/etc/passwd", "C:/Windows", "a\\b", "a:stream", "a/./b", "a//b", " a", "",
                    None, 5, "a/\u202eb", "x" * 1001):
            self.assertFalse(asset_dl.valid_rel(bad), repr(bad))
        for good in ("Kitsu Studio/Rusk Avatar Base", "Creator/Name (2)/sub/file.zip", "作者/パーカー"):
            self.assertTrue(asset_dl.valid_rel(good), good)

    def test_rel_to_path_refuses_escapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "downloads"
            (root / "Booth").mkdir(parents=True)
            with self.assertRaises(asset_dl.UnsafePath):
                asset_dl.rel_to_path(root, "../outside")
            self.assertEqual(asset_dl.rel_to_path(root, "Booth/x"), root / "Booth" / "x")

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs symlinks")
    def test_rel_to_path_refuses_links_that_lead_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, outside = Path(tmp) / "downloads", Path(tmp) / "elsewhere"
            (root / "Booth").mkdir(parents=True)
            outside.mkdir()
            os.symlink(outside, root / "Booth" / "Trap")
            with self.assertRaises(asset_dl.UnsafePath):
                asset_dl.rel_to_path(root, "Booth/Trap/file.zip")


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
        man = asset_dl.Manifest(self.root / "Booth")
        self.assertEqual(list(man.assets), ["1"])
        rec = man.assets["1"]
        self.assertEqual(rec["name"], "GoodItem")
        self.assertIsNone(rec["url"])
        self.assertEqual(list(rec["files"]), ["f"])

    def test_damaged_manifest_is_kept_aside(self):
        (self.root / "Booth" / "_manifest.json").write_text("{not json")
        man = asset_dl.Manifest(self.root / "Booth")
        self.assertEqual(man.assets, {})
        self.assertTrue(list((self.root / "Booth").glob("_manifest.damaged-*.json")))

    def test_catalog_keeps_its_promises(self):
        self._tampered_manifest()
        cfg = json.loads(json.dumps(asset_dl.DEFAULT_CONFIG))
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": self.tmp.name, "LOCALAPPDATA": self.tmp.name}):
            asset_dl.build_catalog(cfg, self.root)
        catalog = json.loads((self.root / "catalog.json").read_text("utf-8"))
        self.assertEqual((catalog["format"], catalog["version"]), ("hoard-catalog", 3))
        self.assertEqual(len(catalog["assets"]), 1)
        for entry in catalog["assets"]:
            self.assertEqual(asset_dl.validate_catalog_entry(entry), [])
        asset = json.loads((self.root / "Booth" / "Good Creator" / "Good Item" / "asset.json").read_text("utf-8"))
        self.assertEqual(asset["format"], "hoard-asset")
        self.assertFalse((Path(self.tmp.name) / "Startup").exists(), "nothing may be written outside the downloads")
        tags = json.loads((self.root / "tags.json").read_text("utf-8"))
        self.assertEqual(tags["format"], "hoard-tags")

    def test_validator_catches_broken_entries(self):
        bad = {"store": "Booth", "name": "A\u202eB", "creator": "C", "folder": "Booth/../x", "files": ["../y"],
               "url": "javascript:x", "tags": ["<b>"], "suggested_tags": []}
        self.assertGreaterEqual(len(asset_dl.validate_catalog_entry(bad)), 5)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs symlinks")
    def test_writes_replace_planted_links(self):
        victim = Path(self.tmp.name) / "victim.txt"
        victim.write_text("keep me")
        link = self.root / "catalog.json"
        os.symlink(victim, link)
        asset_dl.write_file_safely(link, "{}", self.root)
        self.assertEqual(victim.read_text(), "keep me")
        self.assertFalse(link.is_symlink())
        with self.assertRaises(PermissionError):
            asset_dl.write_file_safely(Path(self.tmp.name) / "out.json", "{}", self.root)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs symlinks")
    def test_partial_downloads_never_follow_links(self):
        victim = Path(self.tmp.name) / "victim.bin"
        victim.write_text("keep me")
        part = self.root / "file.zip.part"
        os.symlink(victim, part)
        asset_dl.no_link(part)
        self.assertFalse(part.exists())
        self.assertEqual(victim.read_text(), "keep me")

    def test_oversized_and_deep_json_are_refused(self):
        big = Path(self.tmp.name) / "big.json"
        big.write_text("[" * 100000 + "]" * 100000)
        with self.assertRaises(asset_dl.DataFileError):
            asset_dl.read_json_file(big)
        with self.assertRaises(asset_dl.DataFileError):
            asset_dl.read_json_file(big, max_bytes=1000)

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
        for m in (library, asset_browser):
            self.assertEqual(m.clean_tag("<script>alert(1)</script>"), "script alert 1 script")
            self.assertEqual(m.clean_tag("rusk\u202efits"), "rusk fits")
            self.assertEqual(m.clean_tag("パーカー"), "パーカー")
            for name in ("__proto__", "constructor", "prototype", "__defineGetter__"):
                self.assertNotIn(m.clean_tag(name), m.TAG_RESERVED, name)
            self.assertEqual(m.clean_tag('a"b`c'), "a b c")

    def test_product_keys_must_be_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = library.TagStore(Path(tmp) / "tags.json")
            for bad in ("booth:../../x", "evil:item", "booth:", "booth:<b>", "booth:a b"):
                with self.assertRaises(ValueError):
                    store.change({"action": "assign", "keys": [bad], "add": ["x"]})
            store.change({"action": "assign", "keys": [library.tag_key("booth", "Rusk Avatar Base")], "add": ["x"]})
            self.assertEqual(len(store.load()["items"]), 1)
            self.assertTrue(library.TAG_KEY_RX.match(library.tag_key("booth", "♡♡♡")))

    def test_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = library.TagStore(Path(tmp) / "tags.json")
            data = store.empty()
            data["tags"] = {f"tag{i}": {"match": None} for i in range(library.TAG_LIMITS["tags"])}
            store._save(data)
            with self.assertRaises(ValueError):
                store.change({"action": "create", "name": "one too many"})
            with self.assertRaises(ValueError):
                store.change({"action": "assign", "keys": ["booth:a"] * (library.TAG_LIMITS["keys_per_change"] + 1), "add": ["x"]})

    def test_tampered_file_is_cleaned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.json"
            path.write_text(json.dumps({"tags": {"ok": {"match": "ok"}, "<b>": {}, "__proto__": {}, "bad\u202e": None,
                                                 "fine": "not a dict"},
                                        "items": {"booth:item": ["ok", "<b>", 5], "../x": ["ok"], "booth:y": "ok"},
                                        "excluded": [], "hidden": ["good", "<bad>", 7]}))
            data = library.TagStore(path).load()
            for name in data["tags"]:
                self.assertEqual(library.clean_tag(name), name)
                self.assertNotIn(name, library.TAG_RESERVED)
            self.assertEqual(sorted(data["tags"]), ["b", "bad", "fine", "ok", "proto"])  # converted, never raw
            self.assertEqual(data["items"], {"booth:item": ["b", "ok"]})
            self.assertEqual(data["hidden"], ["good"])

    def test_old_tag_names_are_converted_not_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.json"
            path.write_text(json.dumps({"tags": {"fox/dog": {"match": None}, "fox dog": {"match": "fox"}},
                                        "items": {"booth:a": ["fox/dog"], "booth:b": ["fox dog"]}}))
            data = library.TagStore(path).load()
            self.assertEqual(data["tags"], {"fox dog": {"match": "fox"}})
            self.assertEqual(data["items"], {"booth:a": ["fox dog"], "booth:b": ["fox dog"]})

    def test_damaged_file_is_kept_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.json"
            path.write_text("{this is damaged")
            store = library.TagStore(path)
            store.change({"action": "create", "name": "new"})
            self.assertEqual(sorted(store.load()["tags"]), ["new"])
            aside = list(Path(tmp).glob("tags.damaged-*.json"))
            self.assertEqual(len(aside), 1)
            self.assertEqual(aside[0].read_text(), "{this is damaged")

    @unittest.skipUnless(os.name == "posix", "file modes are a Linux and macOS feature")
    def test_tags_file_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = library.TagStore(Path(tmp) / "Hoard" / "tags.json")
            store.change({"action": "create", "name": "x"})
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)

    def test_requests_are_small_and_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            srv = asset_browser.BrowserServer(("127.0.0.1", 0), Path(tmp), lambda: [], lan=False)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                def post(body, claimed=None):
                    c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
                    c.putrequest("POST", "/api/tags")
                    c.putheader("Content-Type", "application/json")
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
        for m in (asset_dl, library, asset_browser):
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
            self.assertEqual({k: tuple(v) for k, v in sites.items()}, asset_dl.STORE_LINK_SITES, page.name)
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
        for m in (asset_dl, library, asset_browser):
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

    def test_key_is_private_and_shared_by_the_tools(self):
        key = asset_dl.integrity_key()
        self.assertEqual(library.integrity_key(), key)
        self.assertEqual(asset_browser.integrity_key(), key)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE((_TEST_HOME / "Hoard" / "integrity.key").stat().st_mode), 0o600)

    def _download_folder(self):
        root = self.dir / "downloads"
        folder = root / "Booth" / "Kitsu Studio" / "Rusk"
        folder.mkdir(parents=True)
        (folder / "rusk.zip").write_bytes(b"zip")
        man = asset_dl.Manifest(root / "Booth")
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
        cfg = json.loads(json.dumps(asset_dl.DEFAULT_CONFIG))
        self.assertEqual(asset_dl.cmd_verify(cfg, root), 1, "verify reports the change")
        self.assertEqual(asset_dl.cmd_verify(cfg, root), 0, "and settles it: records kept, links dropped, sealed again")
        man = asset_dl.Manifest(root / "Booth")
        self.assertIsNone(man.assets["111"]["url"], "a changed manifest's links must not be used")
        self.assertIn("rusk.zip", [f["path"] for f in man.assets["111"]["files"].values()], "records are kept")
        self.assertTrue(list((root / "Booth").glob("_manifest.changed-*.json")), "a copy is kept to look at")

    def test_older_unsealed_manifests_keep_only_store_links(self):
        root = self.dir / "downloads"
        (root / "Booth" / "A" / "B").mkdir(parents=True)
        (root / "Booth" / "_manifest.json").write_text(json.dumps({"assets": {
            "1": {"folder": "A/B", "name": "Good", "creator": "A", "url": "https://booth.pm/ja/items/1", "files": {}},
            "2": {"folder": "A/B", "name": "Phish", "creator": "A", "url": "https://booth-login.example/", "files": {}}}}))
        man = asset_dl.Manifest(root / "Booth")
        self.assertEqual(man.assets["1"]["url"], "https://booth.pm/ja/items/1")
        self.assertIsNone(man.assets["2"]["url"])

    def test_a_tool_changing_asset_json_is_caught_and_repaired(self):
        root = self._download_folder()
        cfg = json.loads(json.dumps(asset_dl.DEFAULT_CONFIG))
        asset_dl.build_catalog(cfg, root)
        asset_path = root / "Booth" / "Kitsu Studio" / "Rusk" / "asset.json"
        for name in ("catalog.json", "tags.json"):
            self.assertEqual(asset_dl.check_seal(json.loads((root / name).read_text("utf-8"))), "sealed", name)
        asset = json.loads(asset_path.read_text("utf-8"))
        self.assertEqual(asset_dl.check_seal(asset), "sealed")
        asset["url"] = "https://booth-login.example/"
        asset_path.write_text(json.dumps(asset))
        self.assertEqual(asset_dl.check_seal(json.loads(asset_path.read_text("utf-8"))), "changed")
        self.assertEqual(asset_dl.cmd_verify(cfg, root), 1, "verify reports the change")
        repaired = json.loads(asset_path.read_text("utf-8"))
        self.assertEqual(repaired["url"], "https://booth.pm/ja/items/111")
        self.assertEqual(asset_dl.check_seal(repaired), "sealed")
        self.assertEqual(asset_dl.cmd_verify(cfg, root), 0)

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
        for tool in ("Hoard", "HoardDownloader"):
            text = (REPO / tool / "requirements.txt").read_text("utf-8")
            packages = re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", text, re.M)
            self.assertTrue(packages, tool)
            blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text)
            for block in blocks:
                if re.match(r"[A-Za-z0-9_.-]+==", block):
                    self.assertIn("--hash=sha256:", block, f"{tool}: {block.splitlines()[0]} has no hash")
        versions = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", (REPO / "HoardDownloader" / "requirements.txt").read_text(), re.M))
        major, minor, patch = (int(x) for x in versions["requests"].split(".")[:3])
        self.assertGreaterEqual((major, minor, patch), (2, 32, 4), "requests below 2.32.4 has known vulnerabilities")

    def test_setup_checks_hashes(self):
        for tool in ("Hoard", "HoardDownloader"):
            self.assertIn("--require-hashes", (REPO / tool / "Setup.bat").read_text("utf-8"))
            self.assertIn("--require-hashes", (REPO / tool / "setup.sh").read_text("utf-8"))

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


if __name__ == "__main__":
    unittest.main()
