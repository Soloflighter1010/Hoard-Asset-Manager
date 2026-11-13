"""Gumroad purchases added by their receipts (hoard/receipts.py): found in what you add (a receipt email, its page, a
purchase's saved page, a pasted link), kept on this computer (links in a sealed file, emails in the vault, neither in
what the page sees), read without your Gumroad sign-in from a stand-in Gumroad that asks for the purchase's email the
way the real one does, listed with your library, kept when it can't be read, and downloaded.

Every receipt, link and email here is made up."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlparse

from tests.isolation import IsolatedTestCase

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hoard import config, downloader, egress, jobs, library, receipts, server, wishlists  # noqa: E402,F401

TOKEN = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"
EMAIL = "buyer@example.com"
PRODUCT = "https://examplecreator.gumroad.com/l/testfluff"


def page_data(component: str, props: dict) -> str:
    """A page as Gumroad serves it: its data in the app div's data-page attribute."""
    from html import escape
    return (f'<!DOCTYPE html><html><head><meta name="csrf-token" content="csrf-meta"></head><body>'
            f'<div id="app" data-page="{escape(json.dumps({"component": component, "props": props}))}"></div></body></html>')


def download_page(token: str, name: str = "Test Fluff", email: str = EMAIL) -> str:
    """A purchase's download page (made up, shaped like Gumroad's)."""
    return page_data("UrlRedirects/DownloadPage", {
        "title": name, "token": token,
        "content": {"content_items": [{"type": "file", "id": "file1", "file_name": "TestFluff", "extension": "UNITYPACKAGE",
                                       "file_size": 5, "download_url": f"/r/{token}/product_files?product_file_ids%5B%5D=file1"}],
                    "rich_content_pages": []},
        "purchase": {"id": "purchase1==", "email": email, "seller_name": "examplecreator", "product_name": name,
                     "product_permalink": "testfluff", "product_id": "product1==", "variant_id": None,
                     "product_long_url": PRODUCT, "is_archived": False}})


RECEIPT_PAGE = f"""<!DOCTYPE html><html><body><div class="receipt"><span>Order ID:</span><span>purchase1==</span></div>
<h4><a href="{PRODUCT}">Test Fluff</a></h4>
<a class="button primary" href="https://gumroad.com/d/{TOKEN}">View content</a>
<a href="https://gumroad.com/purchases/purchase1==/invoice/new?email=buyer%40example.com">Generate invoice</a>
<a href="https://examplecreator.gumroad.com/l/other?layout=profile&amp;recommended_by=receipt">More from this creator</a>
</body></html>"""

# the same receipt as an email saved from an email program: quoted-printable, its link broken across lines
RECEIPT_EMAIL = ("From: Gumroad <noreply@gumroad.com>\r\nTo: Buyer <buyer@example.com>\r\nSubject: You bought Test Fluff!\r\n"
                 "Message-ID: <abc@example.com>\r\nMIME-Version: 1.0\r\nContent-Type: text/html; charset=UTF-8\r\n"
                 "Content-Transfer-Encoding: quoted-printable\r\n\r\n"
                 "<p>Thanks!</p><a href=3D\"https://gumroad.com/d/" + OTHER[:20] + "=\r\n" + OTHER[20:] + "\">View content</a>\r\n")

SAVED_PAGE = ("From: <Saved by Blink>\r\nSnapshot-Content-Location: https://gumroad.com/d/" + TOKEN + "\r\n"
              "MIME-Version: 1.0\r\nContent-Type: multipart/related;\r\n\ttype=\"text/html\";\r\n\tboundary=\"XX\"\r\n\r\n"
              "--XX\r\nContent-Type: text/html\r\nContent-Transfer-Encoding: 8bit\r\n"
              "Content-Location: https://gumroad.com/d/" + TOKEN + "\r\n\r\n" + download_page(TOKEN) + "\r\n--XX--\r\n")


class _Gumroad(BaseHTTPRequestHandler):
    """A stand-in gumroad.com: a purchase's download page shows at once to a session holding its confirmed cookie,
    and otherwise sends you to /confirm for the email it was bought with, as Gumroad does once a link has been seen."""
    purchases = {TOKEN: EMAIL, OTHER: EMAIL}
    posted: list = []
    seen: list = []

    def log_message(self, *a):
        pass

    def _cookies(self) -> dict:
        out = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k:
                out[k] = v
        return out

    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        _Gumroad.seen.append(u.path)
        parts = u.path.strip("/").split("/")
        if parts[0] == "d" and len(parts) == 2:
            token = parts[1]
            if token not in self.purchases:
                return self._send(404, b"not found")
            if self._cookies().get("confirmed_redirect") != "ok-" + token:
                return self._send(302, headers=[("Location", f"/confirm?id={token}&destination=download_page")])
            return self._send(200, download_page(token).encode())
        if u.path == "/confirm":
            token = parse_qs(u.query).get("id", [""])[0]
            return self._send(200, page_data("UrlRedirects/ConfirmPage", {
                "authenticity_token": "csrf-1", "confirmation_info": {"id": token, "destination": "download_page",
                                                                      "display": None, "email": None, "is_gift": False}}).encode(),
                headers=[("Set-Cookie", "_gumroad_app_session=s1; Path=/")])
        if parts[0] == "r" and parts[-1] == "product_files.json":
            return self._send(200, json.dumps({"files": [{"url": f"http://{self.headers['Host']}/files/file1"}]}).encode(),
                              "application/json")
        if u.path == "/files/file1":
            return self._send(200, b"fluff", "application/octet-stream")
        return self._send(404, b"no")

    def do_POST(self):
        u = urlparse(self.path)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()).items()}
        _Gumroad.posted.append(form)
        token = form.get("id", "")
        ok = (u.path == "/confirm-redirect" and form.get("authenticity_token") == "csrf-1"
              and self._cookies().get("_gumroad_app_session") == "s1"
              and form.get("email", "").lower() == self.purchases.get(token, "-"))
        if not ok:
            return self._send(302, headers=[("Location", "/confirm")])
        return self._send(302, headers=[("Location", f"/d/{token}"), ("Set-Cookie", f"confirmed_redirect=ok-{token}; Path=/")])


class _Vault:
    """The operating system's protection, as a dictionary (tests keep nothing in a real keyring)."""

    def __init__(self):
        self.kept = {}

    def patch(self, case):
        from hoard import vault
        for name, fn in (("save_secret", lambda cfg, n, text: self.kept.__setitem__(n, text)),
                         ("load_secret", lambda cfg, n: self.kept.get(n)),
                         ("forget_key", lambda cfg, n: self.kept.pop(n, None) is not None)):
            p = mock.patch.object(vault, name, fn)
            p.start()
            case.addCleanup(p.stop)


class Found(IsolatedTestCase):
    """Receipts in what you add."""

    def test_a_receipt_page_gives_its_link_and_the_email_it_was_bought_with(self):
        self.assertEqual(receipts.find("receipt.html", RECEIPT_PAGE), [{"token": TOKEN, "email": EMAIL, "name": None}])

    def test_a_receipt_email_gives_its_link_even_broken_across_lines(self):
        """An email program saves the email quoted-printable: its link is joined again, and the email it was sent to
        is the purchase's."""
        self.assertEqual(receipts.find("You bought Test Fluff.eml", RECEIPT_EMAIL), [{"token": OTHER, "email": EMAIL, "name": None}])

    def test_a_saved_download_page_gives_its_own_purchase(self):
        self.assertEqual(receipts.find("Gumroad.mhtml", SAVED_PAGE), [{"token": TOKEN, "email": EMAIL, "name": "Test Fluff"}])

    def test_pasted_links_and_wrapped_ones(self):
        text = (f"https://gumroad.com/d/{TOKEN} and app.gumroad.com/r/{OTHER}, and again https://gumroad.com/d/{TOKEN}\n"
                "https://safe.example/?url=https%3A%2F%2Fgumroad.com%2Fd%2F" + "a" * 32)
        self.assertEqual([f["token"] for f in receipts.find("", text)], [TOKEN, OTHER, "a" * 32])

    def test_nothing_else_is_taken_for_one(self):
        for text in ("https://gumroad.com/l/testfluff", "https://evil.example/d/" + TOKEN, f"https://notgumroad.com/d/{TOKEN}",
                     f"https://gumroad.com/d/{TOKEN[:10]}", "gumroad.com/d/../../etc/passwd" + "x" * 20):
            self.assertEqual(receipts.find("", text), [], text)

    def test_an_email_not_from_gumroad_gives_no_email(self):
        other = RECEIPT_EMAIL.replace("noreply@gumroad.com", "friend@example.org")
        self.assertEqual(receipts.find("fwd.eml", other)[0]["email"], None)


class Kept(IsolatedTestCase):
    """Kept on this computer: the links in a sealed file, the emails in the vault, the page given neither."""

    def setUp(self):
        self.vault = _Vault()
        self.vault.patch(self)
        self.cfg = config.load_config()
        receipts.save([])

    def test_added_once_with_the_email_in_the_vault(self):
        got = receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE) + receipts.find("", f"gumroad.com/d/{TOKEN}"))
        self.assertEqual((got["added"], got["already"]), (1, 1))
        self.assertEqual(receipts.emails(self.cfg), {receipts.email_id(EMAIL): EMAIL})
        on_disk = receipts.path().read_text("utf-8")
        self.assertIn(TOKEN, on_disk)
        self.assertNotIn(EMAIL, on_disk, "the email is in the vault, never in the file")
        self.assertIn("integrity", json.loads(on_disk), "sealed")

    def test_the_page_never_sees_a_link_or_an_email(self):
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))
        shown = json.dumps(receipts.listing())
        self.assertNotIn(TOKEN, shown)
        self.assertNotIn(EMAIL, shown)
        self.assertEqual(receipts.listing()[0]["ref"], receipts.ref(TOKEN))

    def test_a_file_changed_outside_hoard_is_not_used(self):
        receipts.add(self.cfg, receipts.find("", f"gumroad.com/d/{TOKEN}"))
        data = json.loads(receipts.path().read_text("utf-8"))
        data["receipts"].append({"token": OTHER, "added": "2026-01-01T00:00:00+00:00"})
        receipts.path().write_text(json.dumps(data), "utf-8")
        self.assertEqual(receipts.load(), [])

    def test_removing_the_last_forgets_the_emails(self):
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))
        gone = receipts.remove(self.cfg, receipts.ref(TOKEN))
        self.assertEqual(gone["tokens"], [TOKEN])
        self.assertEqual(receipts.load(), [])
        self.assertEqual(receipts.emails(self.cfg), {})
        self.assertIsNone(receipts.remove(self.cfg, receipts.ref(TOKEN)))

    def test_a_report_never_shows_a_download_link(self):
        from hoard.diagnostics import _redact_credentials
        self.assertNotIn(TOKEN, _redact_credentials(f"403 for url: https://gumroad.com/r/{TOKEN}/product_files?x"))


class _Stand(IsolatedTestCase):
    """A stand-in Gumroad on this computer, and receipts read from it."""

    def setUp(self):
        _Gumroad.posted, _Gumroad.seen = [], []
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Gumroad)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.origin = f"http://127.0.0.1:{self.srv.server_address[1]}"
        egress._TEST_ORIGINS.add(self.origin)
        self.addCleanup(egress._TEST_ORIGINS.discard, self.origin)
        for name, value in (("SITE", self.origin), ("SITES", ["127.0.0.1"])):
            p = mock.patch.object(receipts, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.vault = _Vault()
        self.vault.patch(self)
        self.cfg = config.load_config()
        self.cfg["request_delay"] = 0
        receipts.save([])


class Read(_Stand):

    def test_read_after_answering_gumroads_email_check_and_not_asked_again(self):
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))
        items, kept = receipts.read(self.cfg)
        self.assertEqual(kept, [])
        (got,) = items
        self.assertEqual((got["name"], got["creator"], got["id"]), ("Test Fluff", "examplecreator", "purchase1=="))
        self.assertEqual(got["page"], PRODUCT, "its public page, for sets and the picture")
        self.assertEqual(got["creator_url"], "https://examplecreator.gumroad.com")
        self.assertEqual(len(_Gumroad.posted), 1)
        self.assertEqual(_Gumroad.posted[0]["email"], EMAIL)
        self.assertEqual(receipts.listing()[0]["name"], "Test Fluff")
        self.assertIn("cookie", receipts.load()[0], "the purchase's own cookie is kept with it")
        receipts.read(self.cfg)
        self.assertEqual(len(_Gumroad.posted), 1, "the kept cookie answers: the email isn't sent again")

    def test_a_link_alone_says_to_add_the_receipt_email(self):
        receipts.add(self.cfg, receipts.find("", f"gumroad.com/d/{TOKEN}"))
        self.assertEqual(receipts.read(self.cfg), ([], []))
        self.assertEqual(receipts.listing()[0]["error"], receipts.NEEDS_EMAIL)
        self.assertEqual(_Gumroad.posted, [], "no email to send, so nothing is sent")
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))   # the receipt itself, later: its email
        self.assertEqual(len(receipts.read(self.cfg)[0]), 1)

    def test_a_wrong_email_is_said(self):
        _Gumroad.purchases = {**_Gumroad.purchases, TOKEN: "someone@example.net"}
        self.addCleanup(setattr, _Gumroad, "purchases", {TOKEN: EMAIL, OTHER: EMAIL})
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))
        receipts.read(self.cfg)
        self.assertIn("didn't take the email", receipts.listing()[0]["error"])

    def test_a_link_gumroad_doesnt_know(self):
        receipts.add(self.cfg, receipts.find("", "gumroad.com/d/" + "b" * 32))
        receipts.read(self.cfg)
        self.assertIn("doesn't know this link", receipts.listing()[0]["error"])

    def test_one_that_cant_be_reached_now_keeps_what_was_read_before(self):
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))
        receipts.read(self.cfg)
        with mock.patch.object(receipts.Reader, "page", side_effect=ConnectionError("down")):
            items, kept = receipts.read(self.cfg)
        self.assertEqual((items, kept), ([], ["gumroad:purchase1=="]))

    def test_a_quick_refresh_reads_only_new_ones_and_one_in_your_library_is_left_to_it(self):
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))
        receipts.read(self.cfg)
        receipts.add(self.cfg, receipts.find("x.eml", RECEIPT_EMAIL))
        self.assertEqual(len(receipts.read(self.cfg, only_new=True)[0]), 1)
        self.assertEqual(receipts.read(self.cfg, skip={TOKEN, OTHER}), ([], []))
        self.assertTrue(all(r["in_library"] for r in receipts.listing()))


class Refreshed(_Stand):
    """Gumroad's refresh lists them: signed in, beside your library; signed out, on their own, the rest kept."""

    def ctx(self, signed_in: bool, cards=()):
        def get(url, params=None, timeout=None):
            if not signed_in:
                return SimpleNamespace(url="https://app.gumroad.com/login", ok=True, status=200, text=lambda: "")
            body = page_data("Library/Index", {"results": list(cards), "pagination": {"pages": 1}})
            return SimpleNamespace(url=url, ok=True, status=200, text=lambda: body)
        return SimpleNamespace(request=SimpleNamespace(get=get), close=lambda: None)

    def setUp(self):
        super().setUp()
        picture = ('<html><head><meta property="og:title" content="Test Fluff">'
                   '<meta property="og:image" content="https://public-files.gumroad.com/cover1"></head></html>')
        p = mock.patch.object(wishlists, "read_store_page", lambda url, hosts: (picture, "text/html"))
        p.start()
        self.addCleanup(p.stop)
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))

    def test_signed_out_only_the_receipts_with_their_picture(self):
        run = {**self.cfg}
        items = library.fetch_gumroad(self.ctx(False), run, lambda m: None)
        self.assertEqual([i["name"] for i in items], ["Test Fluff"])
        self.assertEqual(items[0]["thumbnail"], "https://public-files.gumroad.com/cover1", "the picture its page shows")
        self.assertTrue(run["_gumroad_signed_out"])

    def test_signed_out_without_receipts_is_not_signed_in(self):
        receipts.save([])
        with self.assertRaises(library.NotLoggedIn):
            library.fetch_gumroad(self.ctx(False), {**self.cfg}, lambda m: None)

    def test_signed_in_a_purchase_your_library_has_is_listed_once(self):
        card = {"product": {"name": "Test Fluff", "creator": {"name": "examplecreator"}},
                "purchase": {"id": "purchase1==", "download_url": f"https://app.gumroad.com/d/{TOKEN}"}}
        items = library.fetch_gumroad(self.ctx(True, [card]), {**self.cfg}, lambda m: None)
        self.assertEqual(len(items), 1)
        self.assertEqual(_Gumroad.posted, [], "read from your library, not its receipt")
        self.assertTrue(receipts.listing()[0]["in_library"])

    def test_the_refresh_keeps_your_library_when_only_receipts_were_read(self):
        lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        lib.replace_store("gumroad", [library.item("gumroad", "old1", name="From my library",
                                                   download_url="https://app.gumroad.com/d/" + "c" * 32)])
        j = jobs.Jobs(self.cfg, lib)
        with mock.patch.object(jobs, "_playwright", lambda: lambda: _NoPlaywright()), \
                mock.patch.object(jobs, "launch", lambda *a, **k: self.ctx(False)), \
                mock.patch.object(jobs, "reachable", lambda s: True), \
                mock.patch.object(jobs, "cache_images", lambda *a, **k: None), \
                mock.patch.object(jobs.Jobs, "read_store_pages_later", lambda self: None), \
                mock.patch("hoard.downloader.build_catalog", lambda *a, **k: None):
            j._refresh(["gumroad"])
        names = sorted(i["name"] for i in lib.data["items"])
        self.assertEqual(names, ["From my library", "Test Fluff"])
        self.assertEqual(lib.data["stores"]["gumroad"]["error"], receipts.SIGNED_OUT)


class _NoPlaywright:
    def __enter__(self):
        return SimpleNamespace()

    def __exit__(self, *a):
        return False


class Downloaded(_Stand):

    def test_a_receipts_purchase_downloads_signed_out(self):
        receipts.add(self.cfg, receipts.find("r.html", RECEIPT_PAGE))
        root = Path(tempfile.mkdtemp())
        report = downloader.Report()
        args = SimpleNamespace(dry_run=False, only=None, keys=None, targets=None)
        with mock.patch.object(downloader, "gumroad_session", side_effect=downloader.NotLoggedIn("no")), \
                mock.patch.object(downloader, "save_thumbnail", lambda *a, **k: None):
            downloader.sync_gumroad(self.cfg, root, args, report)
        files = [p for p in (root / "Gumroad").rglob("*") if p.is_file() and not p.name.startswith("_")]
        self.assertEqual([p.read_bytes() for p in files], [b"fluff"], report.failed)
        self.assertEqual(len(_Gumroad.posted), 1)

    def test_signed_out_without_receipts_is_not_signed_in(self):
        with mock.patch.object(downloader, "gumroad_session", side_effect=downloader.NotLoggedIn("no")):
            with self.assertRaises(downloader.NotLoggedIn):
                downloader.sync_gumroad(self.cfg, Path(tempfile.mkdtemp()), SimpleNamespace(dry_run=False, targets=None),
                                        downloader.Report())


class Imported(_Stand):
    """Dropped on the window with saved pages: kept as receipts, never imported as a page."""

    def test_a_receipt_with_the_saved_pages(self):
        results = library.import_saved_pages(self.cfg, [("receipt.eml", RECEIPT_EMAIL), ("Gumroad.mhtml", SAVED_PAGE)])
        self.assertEqual([(r.get("receipts"), r.get("added")) for r in results], [(1, 1), (1, 1)])
        self.assertEqual({r["token"] for r in receipts.load()}, {TOKEN, OTHER})

    def test_an_email_with_no_receipt_is_said(self):
        (result,) = library.import_saved_pages(self.cfg, [("note.eml", "From: a@example.com\r\nTo: b@example.com\r\n"
                                                                       "Message-ID: <x>\r\n\r\nhello")])
        self.assertIn("no Gumroad receipt", result["error"])


class FromThePage(_Stand):
    """The page's endpoints: what's added comes back as names and refs, never a link or an email."""

    def setUp(self):
        super().setUp()
        from hoard.api import stores as api
        self.api = api
        self.lib = library.Library(Path(tempfile.mkdtemp()) / "library.json")
        self.me = SimpleNamespace(server=SimpleNamespace(cfg=self.cfg, cfg_lock=threading.Lock(), lib=self.lib),
                                  _json=lambda data, code=200: (code, data))

    def test_added_listed_and_removed(self):
        code, got = self.api.post_api_gumroad_receipts(self.me, "", {
            "text": f"https://gumroad.com/d/{TOKEN}", "files": [{"filename": "r.eml", "content": RECEIPT_EMAIL},
                                                               {"filename": "notes.txt", "content": "hello"}]}, {})
        self.assertEqual((code, got["added"]), (200, 2))
        self.assertEqual([p["filename"] for p in got["problems"]], ["notes.txt"])
        shown = json.dumps(got) + json.dumps(self.api.get_api_gumroad_receipts(self.me, "", {}, {})[1])
        for secret in (TOKEN, OTHER, EMAIL):
            self.assertNotIn(secret, shown)
        self.lib.replace_store("gumroad", [library.item("gumroad", "purchase1==", name="Test Fluff",
                                                       download_url=f"https://gumroad.com/d/{TOKEN}"),
                                           library.item("gumroad", "mine", name="From my library",
                                                       download_url="https://gumroad.com/d/" + "c" * 32)])
        code, gone = self.api.post_api_gumroad_receipts_remove(self.me, "", {"ref": receipts.ref(TOKEN)}, {})
        self.assertEqual((code, gone["removed"]), (200, 1))
        self.assertEqual([r["ref"] for r in gone["receipts"]], [receipts.ref(OTHER)])
        self.assertEqual([i["name"] for i in self.lib.data["items"]], ["From my library"])
        self.assertEqual(self.api.post_api_gumroad_receipts_remove(self.me, "", {"ref": "../../x"}, {})[0], 400)

    def test_nothing_to_add_is_said(self):
        code, got = self.api.post_api_gumroad_receipts(self.me, "", {"text": "no link here"}, {})
        self.assertEqual(code, 400)
        self.assertIn("View content link", got["problems"][0]["error"])
