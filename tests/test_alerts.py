"""Issue #230: notifications through Apprise, for the news you choose: the addresses kept as API keys are (never in
config.json), what's sent saying how many and never a product's name, and nothing sent unless chosen."""
from __future__ import annotations

import http.server
import importlib.util
import json
import logging
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from tests.isolation import IsolatedTestCase
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoard import alerts, config, jobs, library, vault  # noqa: E402


class FakeService:
    """One service an address is for, as Apprise has it: what it's sent, and what it answers (a refusal, as Apprise's
    services do, said in Apprise's log with the address in it)."""

    def __init__(self, url):
        self.url, self.service_name = url, url.split("://")[0].title()

    attachment_support = True

    def notify(self, body, title, body_format=None, attach=None):
        FakeApprise.sent.append(([self.url], title, body))
        FakeApprise.files.append((self.url, attach, getattr(getattr(self, "asset", None), "image_url_mask", None)))
        if not FakeApprise.accept:
            logging.getLogger("apprise").warning(f"Failed to send {self.service_name} notification to {self.url}: "
                                                 "Unauthorized - error=401.")
        return FakeApprise.accept


class FakeApprise:
    """A stand-in for the apprise package: what was added and sent, and what it answers."""
    sent: list = []
    files: list = []   # (each message's address, the file sent with it, and the picture its service shows)
    accept = True

    def __init__(self, asset=None):
        self.added, self.asset = [], asset

    def add(self, url, asset=None):
        ok = "://" in url and not url.startswith("nope://")
        if ok:
            self.added.append(FakeService(url))
            self.added[-1].asset = asset or self.asset
        return ok

    def __iter__(self):
        return iter(self.added)


class FakeAsset:
    """Apprise's AppriseAsset, as Hoard sets it: its name, colours and icon."""

    def __init__(self, **kw):
        self.__dict__.update(kw, html_notify_map={"info": "#3AA3E3"})


def fake_apprise() -> types.ModuleType:
    """A stand-in apprise module."""
    fake = types.ModuleType("apprise")
    fake.Apprise, fake.AppriseAsset, fake.AppriseAttachment = FakeApprise, FakeAsset, lambda path: path
    fake.NotifyFormat = types.SimpleNamespace(MARKDOWN="markdown", TEXT="text")
    return fake


class Alerts(IsolatedTestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(self.tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        self.cfg = {**config.load_config(), "allow_unprotected_signins": True, "apprise_events": ["new", "tasks"]}
        FakeApprise.sent, FakeApprise.accept = [], True
        fake = fake_apprise()
        for patch in (mock.patch.dict(sys.modules, {"apprise": fake}), mock.patch.object(alerts, "available", lambda: True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(vault.forget_key, self.cfg, alerts.SECRET)

    def wait_sent(self, n):
        for _ in range(100):
            if len(FakeApprise.sent) >= n:
                return
            time.sleep(0.02)

    def test_the_addresses_are_kept_protected(self):
        self.assertEqual(alerts.clean_urls(" discord://123/abc \n\nntfys://ntfy.example/hoard\ndiscord://123/abc"),
                         ["discord://123/abc", "ntfys://ntfy.example/hoard"])
        for bad in ("not an address", "discord://" + "x" * 1001, "\n".join(f"json://h/{n}" for n in range(21))):
            with self.assertRaises(ValueError):
                alerts.clean_urls(bad)
        urls = ["tgram://bottoken/ChatID", "mailtos://user:pass@example.com?to=me@example.com"]
        alerts.save_urls(self.cfg, urls)
        self.assertEqual(alerts.urls(self.cfg), urls)
        self.assertNotIn("bottoken", json.dumps(self.cfg), "never in config.json")
        keys = self.tmp / "data" / "keys"
        if sys.platform == "win32":   # encrypted for this Windows account
            self.assertNotIn(b"bottoken", (keys / "apprise.dpapi").read_bytes(), "not as typed, either")
        elif vault._where(self.cfg) == "file":   # (no keyring here: a file only you can read)
            kept = keys / "apprise.key"
            self.assertEqual(kept.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("bottoken", kept.read_text(), "not as typed, either")
        alerts.save_urls(self.cfg, [])
        self.assertEqual(alerts.urls(self.cfg), [])

    def test_only_whats_chosen_is_sent(self):
        alerts.save_urls(self.cfg, ["json://example.com/hook"])
        self.assertTrue(alerts.send(self.cfg, "new", alerts.found_text({"new": 3, "updates": 0}, "new")))
        self.assertFalse(alerts.send(self.cfg, "prices", "cheaper"), "not chosen")
        self.assertIsNone(alerts.found_text({"new": 3, "updates": 0}, "updates"), "nothing to say")
        self.wait_sent(1)
        self.assertEqual(FakeApprise.sent, [(["json://example.com/hook"], "Hoard",
                                             "The routine check found **3 new products**. Open Hoard to choose what to download.")])
        alerts.save_urls(self.cfg, [])
        self.assertFalse(alerts.send(self.cfg, "new", "x"), "no addresses: nothing sent")

    def test_the_addresses_are_read_in_the_background(self):
        """Reading them starts a program (the Keychain's, the keyring's), so a task sending news as it finishes would
        wait on it: the worker reads them, never the task."""
        alerts.save_urls(self.cfg, ["json://example.com/hook"])
        read_by, real = [], alerts.urls
        with mock.patch.object(alerts, "urls", lambda cfg: read_by.append(threading.current_thread().name) or real(cfg)):
            self.assertTrue(alerts.send(self.cfg, "tasks", "A task finished."))
            self.wait_sent(1)
        self.assertEqual(read_by, ["apprise"])
        alerts.save_urls(self.cfg, [])

    def test_what_a_service_answers(self):
        """What each service answered is said, and noted in Hoard's log (issue #238), with its address taken out."""
        logged = []
        with mock.patch.object(alerts, "log", logged.append):
            self.assertIsNone(alerts.deliver(["json://example.com/hook"], "hi"))
            self.assertEqual(logged, ["A notification through Apprise (test) was sent: Json took it."])
            FakeApprise.accept = False
            said = alerts.deliver(["json://hooks.example.com/hook?token=SECRET1234"], "hi", event="new")
            self.assertIn("Json didn't take it: Failed to send Json notification to … Unauthorized - error=401.", said)
            self.assertIn("A notification through Apprise (new) wasn't sent: Json didn't take it", logged[-1])
            FakeApprise.accept = True
            self.assertEqual(alerts.deliver(["nope://x"], "hi"), "None of the addresses is one Apprise knows.")
            said = alerts.deliver(["nope://secret-token", "json://example.com/hook"], "hi")
            self.assertIn("1 of the addresses", said)
        for line in [said, *logged]:
            for secret in ("secret-token", "SECRET1234", "hooks.example.com"):
                self.assertNotIn(secret, line, "an address is never said: it holds a token")

    def test_a_service_that_breaks_doesnt_stop_the_rest(self):
        """A service that raises, or Apprise itself failing to start (as when the app didn't ship its services: issue
        #237), is said in Hoard's words; the background worker carries on with the next notification."""
        logged = []

        def broken(self, body, title, **kw):
            raise ConnectionError("https://example.com/hook?token=SECRET1234 refused")
        with mock.patch.object(alerts, "log", logged.append):
            with mock.patch.object(FakeService, "notify", broken):
                said = alerts.deliver(["json://example.com/hook?token=SECRET1234"], "hi")
            self.assertIn("Json didn't take it: ConnectionError.", said)
            with mock.patch.object(FakeApprise, "add", side_effect=FileNotFoundError("apprise/plugins")):
                self.assertIn("Apprise couldn't start (FileNotFoundError)", alerts.deliver(["json://example.com/hook"], "hi"))
                alerts.save_urls(self.cfg, ["json://example.com/hook"])
                self.assertTrue(alerts.send(self.cfg, "tasks", "A task finished."))
                for _ in range(100):
                    if any("(tasks)" in line for line in logged):
                        break
                    time.sleep(0.02)
            self.assertTrue(alerts.send(self.cfg, "new", "Found some."))
            self.wait_sent(1)
        self.assertEqual(FakeApprise.sent[-1][2], "Found some.", "the worker carried on")
        self.assertNotIn("SECRET1234", " ".join(logged + [said]))
        alerts.save_urls(self.cfg, [])


    def test_a_finished_task_says_how_it_went_in_counts(self):
        record = {"task": "download", "outcome": "partial", "label": "Download Secret Product",
                  "report": {"new_assets": 2, "updated": 1, "failed": 1, "problems": ["Secret Product: gone"]}}
        text = alerts.task_text(record)
        self.assertEqual(text, "**Download**: partly done (2 new, 1 updated, 1 couldn't be downloaded).")
        self.assertNotIn("Secret", text, "never a product's name")
        self.assertEqual(alerts.task_text({"task": "check-updates", "outcome": "done", "report": {"updates": 1}}),
                         "**Check for updates**: done (1 product with updates).")

    def test_every_task_says_how_many(self):
        """Issue #342: "Add to Local: done." didn't say how many. Each task's news has its counts, and never a name."""
        said = lambda task, report, outcome="done": alerts.task_text({"task": task, "outcome": outcome, "report": report})  # noqa: E731
        self.assertEqual(said("add-local", {"counts": {"added": 7, "already": 1, "left_out": 0}}),
                         "**Add to Local**: done (7 added, 1 already there).")
        self.assertEqual(said("add-local", {"counts": {"added": 1, "files": 38}}), "**Add to Local**: done (1 added, 38 files).")
        self.assertEqual(said("remove-local", {"counts": {"taken_out": 1}}), "**Take out of Local**: done (1 taken out).")
        self.assertEqual(said("delete-files", {"counts": {"deleted": 12}}), "**Delete downloaded files**: done (12 files deleted).")
        self.assertEqual(said("refresh", {"counts": {"read": 120, "new": 0}}), "**Refresh**: done (120 products read, 0 new).")
        self.assertEqual(said("wishlists", {"counts": {"lists": 3, "cheaper": 2}}),
                         "**Read wishlists**: done (3 wishlists read, 2 cheaper than before).")
        self.assertEqual(said("konoasset", {"counts": {"matched": 4, "local": 9, "notes": 2, "left_out": 1}}),
                         "**Bring in from KonoAsset**: done (4 matched to your library, 9 Local products, 2 notes, 1 left out).")
        self.assertEqual(said("download", {"new_assets": 0, "updated": 0, "failed": 0}), "**Download**: done (nothing new).")
        self.assertEqual(said("sync", {"new_assets": 2, "updated": 0, "failed": 0, "counts": {"read": 50, "new": 2}}),
                         "**Sync**: done (50 products read, 2 new).", "what a sync read, then what it downloaded: new, once")
        self.assertEqual(said("add-local", {"counts": {"added": True, "files": "many", "moved": -1}}), "**Add to Local**: done.",
                         "only numbers")
        self.assertEqual(said("login", None), "**Sign in**: done.", "nothing to count: as it was")

    def test_a_tasks_counts_are_kept_with_its_report(self):
        job = jobs.Jobs(self.cfg, library.Library(self.tmp / "library.json"))
        job._counted(added=7, already=1)
        job._counted(left_out=2, name="Secret Product")
        self.assertEqual(job.state["report"], {"counts": {"added": 7, "already": 1, "left_out": 2}})

    def test_a_discord_embed_shows_the_picture_itself(self):
        """Issue #330: on Discord a product's picture was posted as a file under the embed. The embed shows it itself,
        from the store, and is sent no file; a service that takes files still gets the file."""
        FakeApprise.files.clear()
        fetched = []
        picture = lambda: (fetched.append(1), (b"png", "image/png"))[1]   # noqa: E731
        where = "https://booth.pximg.net/c/300x300/fox.jpg"
        with mock.patch.dict(sys.modules, {"apprise": fake_apprise()}), mock.patch.object(alerts, "log"):
            alerts.deliver(["discord://1234/token"], "hi", picture=picture, picture_url=where)
            self.assertEqual(FakeApprise.files, [("discord://1234/token?format=markdown&footer=yes&image=yes", None, where)])
            self.assertEqual(fetched, [], "not fetched for nothing")
            FakeApprise.files.clear()
            alerts.deliver(["discord://1234/token", "tgram://bot/chat"], "hi", picture=picture, picture_url=where)
            (_, to_discord, shown), (_, to_telegram, icon) = FakeApprise.files
            self.assertIsNone(to_discord)
            self.assertEqual(shown, where)
            self.assertTrue(str(to_telegram).endswith(".png"), "a service that takes a file gets the file")
            self.assertEqual(icon, alerts.HOARD_ICON)
            FakeApprise.files.clear()
            alerts.deliver(["discord://1234/token"], "hi", picture=picture, picture_url="http://example.com/{TYPE}.png")
            self.assertEqual(FakeApprise.files[0][2], alerts.HOARD_ICON, "only an https address, as it is")

    def test_tasks_pass_their_news_on(self):
        job = jobs.Jobs(self.cfg, library.Library(self.tmp / "library.json"))
        news = []
        job.on_news = lambda kind, what: news.append((kind, what.get("task"), what.get("outcome")))
        gate = threading.Event()
        with mock.patch.object(job, "_refresh", lambda *a, **k: gate.wait(5) and []):
            self.assertEqual(job.start("refresh", ["booth"]), "started")
            gate.set()
            for _ in range(200):
                if news:
                    break
                time.sleep(0.02)
        self.assertEqual(news, [("finished", "refresh", "done")])
        job.on_news = lambda kind, what: 1 / 0   # a notification that fails never stops a task
        job._news("finished", {})


    def test_the_checks_news_is_sent_once(self):
        """The routine check runs every few hours: what it found missing is news once, not every time it's found
        missing again; what's new since then is news again."""
        job = jobs.Jobs(self.cfg, library.Library(self.tmp / "library.json"))
        news = []
        job.on_news = lambda kind, what: news.append((kind, what))
        found = [{"changed": ["a.zip"], "missing": ["b.zip", "c.zip"]}, {"changed": ["a.zip"], "missing": ["b.zip", "c.zip"]},
                 {"changed": ["a.zip"], "missing": ["b.zip", "c.zip", "d.zip"]}]
        last = [None]

        def check(*a, **k):
            last[0] = {"complete": True, "data_changed": [], "checked": "now", **found.pop(0)}
            return last[0]
        with mock.patch("hoard.downloader.check_integrity", check), \
                mock.patch("hoard.downloader.last_integrity", lambda: last[0]), \
                mock.patch("hoard.downloader.integrity_summary", lambda r: "summary"):
            for _ in range(3):
                job._verify(["booth"])
        self.assertEqual(news, [("checked", {"changed": 1, "missing": 2}), ("checked", {"changed": 0, "missing": 1})])


class AlertsInHoard(IsolatedTestCase):
    """The server's side: the addresses kept through /api/apprise (and never sent back), a test sent to them, what's
    sent chosen in Settings, and the tasks' news turned into what's sent."""

    def setUp(self):
        import http.client
        from hoard import server
        from hoard.safety import ACCESS_HEADER
        self.tmp = Path(tempfile.mkdtemp())
        for patch in (mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(self.tmp / "data")}),
                      mock.patch.object(server, "save_config"), mock.patch.object(alerts, "available", lambda: True),
                      mock.patch.object(alerts, "_kept", None), mock.patch.object(alerts, "_described", None)):
            patch.start()
            self.addCleanup(patch.stop)
        fake = fake_apprise()
        patch = mock.patch.dict(sys.modules, {"apprise": fake})
        patch.start()
        self.addCleanup(patch.stop)
        FakeApprise.sent, FakeApprise.accept = [], True
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"),
                                                       "allow_unprotected_signins": True}, lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.addCleanup(vault.forget_key, self.srv.cfg, alerts.SECRET)

        def call(method, path, body=None):
            c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=20)
            c.request(method, path, body=json.dumps(body) if body is not None else None,
                      headers={"Content-Type": "application/json", ACCESS_HEADER: self.srv.key})
            r = c.getresponse(); data = json.loads(r.read() or b"{}"); c.close()
            return r.status, data
        self.call = call

    def test_addresses_kept_and_tested(self):
        """Issue #287: added, tested, changed and removed one at a time; the page only ever sees each one's service and
        what tells it apart, never a token."""
        self.assertEqual(self.call("GET", "/api/settings")[1]["apprise"], {"available": True, "kept": 0, "addresses": [], "events": []})
        self.assertEqual(self.call("POST", "/api/apprise/test", {})[0], 400, "nothing kept yet")
        self.assertEqual(self.call("POST", "/api/apprise", {"urls": "not an address"})[0], 400)
        hook, chat = "json://example.com/hook?token=SECRET123", "tgram://123456:BOTSECRET99/-1001234567890"
        status, answer = self.call("POST", "/api/apprise", {"action": "add", "urls": hook})
        self.assertEqual((status, answer["kept"]), (200, 1))
        status, answer = self.call("POST", "/api/apprise", {"action": "add", "urls": chat + "\n" + hook})
        self.assertEqual([(a["service"], a["label"]) for a in answer["addresses"]], [("Webhook", "example.com"), ("Telegram", "chat …7890")])
        status, settings = self.call("GET", "/api/settings")
        for secret in ("SECRET123", "BOTSECRET99", "123456:"):
            self.assertNotIn(secret, json.dumps(settings), "never sent back")
            self.assertNotIn(secret, json.dumps(answer))
            self.assertNotIn(secret, json.dumps(self.srv.cfg), "never in config.json")
        hook_id, chat_id = (a["id"] for a in answer["addresses"])
        self.assertEqual(self.call("POST", "/api/apprise/test", {"id": chat_id}), (200, {"ok": True, "error": None}))
        self.assertEqual(FakeApprise.sent[-1][0], [chat], "only that one")
        self.assertEqual(FakeApprise.sent[-1][2], "This is a test from **Hoard**: notifications through Apprise work.")
        self.assertEqual(self.call("POST", "/api/apprise/test", {"id": "nonsense"})[0], 400)
        status, answer = self.call("POST", "/api/apprise", {"action": "replace", "id": hook_id, "urls": "ntfys://ntfy.example.com/hoard-news"})
        self.assertEqual([a["service"] for a in answer["addresses"]], ["ntfy", "Telegram"], "in its place")
        self.assertEqual(self.call("POST", "/api/apprise", {"action": "remove", "id": hook_id})[0], 400, "gone already")
        status, answer = self.call("POST", "/api/apprise", {"action": "remove", "id": chat_id})
        self.assertEqual(alerts.urls(self.srv.cfg), ["ntfys://ntfy.example.com/hoard-news"])
        self.assertEqual(self.call("POST", "/api/apprise/test", {}), (200, {"ok": True, "error": None}))
        self.assertEqual(self.call("POST", "/api/settings", {"apprise_events": ["tasks", "nonsense", "new"]})[0], 200)
        self.assertEqual(self.srv.cfg["apprise_events"], ["new", "tasks"], "known ones only, in order")
        self.assertEqual(self.call("POST", "/api/apprise", {"forget": True}), (200, {"ok": True, "kept": 0, "addresses": []}))
        self.assertEqual(alerts.urls(self.srv.cfg), [])

    def test_the_tasks_news(self):
        """What each kind of news says, sent only for what's ticked: counts, never names."""
        alerts.save_urls(self.srv.cfg, ["json://example.com/hook"])
        self.srv.cfg["apprise_events"] = list(alerts.EVENTS)
        self.srv._news("found", {"new": 2, "updates": 1})
        self.srv._news("cheaper", 1)
        self.srv._news("checked", {"changed": 1, "missing": 3})
        self.srv._news("finished", {"task": "routine", "outcome": "done", "report": {"routine": {"new": 2, "updates": 0}}})
        self.srv._news("finished", {"task": "download", "outcome": "done", "report": {"new_assets": 1}})
        self.srv._news("finished", {"task": "list-files", "outcome": "done"})   # (a look, not news)
        self.srv.updates.on_available("5.2.0")
        for _ in range(100):
            if len(FakeApprise.sent) >= 7:
                break
            time.sleep(0.02)
        self.assertEqual([body for _, _, body in FakeApprise.sent], [
            "The routine check found **2 new products**. Open Hoard to choose what to download.",
            "The routine check found **1 update**. Open Hoard to choose what to download.",
            "**1 product** on your wishlists is cheaper than before.",
            "The check of your downloads found **1 file changed and 3 files missing**. Open Hoard to see what it found.",
            "The routine check found **2 new products**.",
            "**Download**: done (1 new).",
            "**Hoard 5.2.0** is available. Open Hoard to update."])
        self.assertEqual([title for _, title, _ in FakeApprise.sent][:3], ["New products to download", "Updates to download",
                                                                            "Cheaper on your wishlists"], "each its title")
        FakeApprise.sent.clear()
        self.srv.cfg["apprise_events"] = ["prices"]
        self.srv._news("finished", {"task": "download", "outcome": "failed", "report": {}})
        time.sleep(0.1)
        self.assertEqual(FakeApprise.sent, [], "tasks aren't ticked: nothing sent")


class Addresses(IsolatedTestCase):
    """Issues #285, #287: what Settings is shown of an address (never a secret), and how one is sent to."""

    def test_described_without_secrets(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_pages import APPRISE_BUILT
        secrets = {"discord": ["AbC-dEf_123"], "telegram": ["ABC-def_ghi", "123456:"], "ntfy": ["my-hoard"],
                   "email": ["app%20pass", "app pass", "you:"], "pushover": ["fakeapptoken", "fakeuserkey"],
                   "slack": ["BFAKE", "notarealtoken"], "matrix": ["pw@", "bot:"], "gotify": ["AbCdEf123"], "webhook": ["abc%2Fd", "token"]}
        for service, _, address in APPRISE_BUILT:
            d = alerts.describe(address)
            self.assertRegex(d["id"], r"^[0-9a-f]{16}$")
            for secret in secrets[service]:
                self.assertNotIn(secret, json.dumps(d), f"{service}: {d}")
        self.assertEqual(alerts.describe("discord://123456789012345678/AbC")["label"], "webhook …5678")
        native = alerts.describe("https://discord.com/api/webhooks/123456789012345678/AbCdEf")   # (pasted as it is)
        self.assertEqual((native["service"], native["label"]), ("Discord", "webhook …5678"))
        self.assertEqual(alerts.describe("mailtos://you:pw@gmail.com?to=me%40example.org")["label"], "to m•••@example.org")
        self.assertEqual(alerts.describe("weird://user:pass@example.com/x")["label"], "example.com", "never its user and password")

    def test_a_discord_address_asks_for_an_embed(self):
        self.assertEqual(alerts.rich("discord://1/abc", "https://booth.pm/en/items/1"),
                         "discord://1/abc?format=markdown&footer=yes&image=yes&href=https%3A%2F%2Fbooth.pm%2Fen%2Fitems%2F1")
        self.assertEqual(alerts.rich("discord://1/abc?format=text&footer=no"), "discord://1/abc?format=text&footer=no&image=yes",
                         "what you set on it stays")
        self.assertEqual(alerts.rich("https://discord.com/api/webhooks/1/abc"), "https://discord.com/api/webhooks/1/abc?format=markdown&footer=yes&image=yes")
        self.assertEqual(alerts.rich("tgram://1:a/2", "https://booth.pm/x"), "tgram://1:a/2", "others as they are")
        self.assertEqual(alerts.rich("discord://1/abc", "javascript:alert(1)"), "discord://1/abc?format=markdown&footer=yes&image=yes")

    def test_a_wishlists_cheaper_products_named(self):
        text, link = alerts.cheaper_text(7, [{"store": "booth", "name": "Fox [Ears]", "url": "https://booth.pm/en/items/1", "was": "¥1,500", "now": "¥1,200"},
                                             {"store": "booth", "name": "Tail", "url": "https://evil.example/x", "was": "¥900", "now": "¥800"}])
        self.assertEqual(text.splitlines(), ["**7 products** on your wishlists are cheaper than before.",
                                             "- [Fox \\[Ears\\]](https://booth.pm/en/items/1): ~~¥1,500~~ **¥1,200**",
                                             "- Tail: ~~¥900~~ **¥800**", "- and 5 more"])
        self.assertEqual(link, "https://booth.pm/en/items/1", "only a store's own page")


@unittest.skipUnless(importlib.util.find_spec("apprise"), "Apprise isn't installed here")
class RealApprise(IsolatedTestCase):
    """Issue #237: Send a test, through Apprise itself, reaches a service (one on this computer, answering as a webhook
    would), and a service that refuses it says why, its address never in what's said."""

    def test_a_test_reaches_the_service(self):
        heard = []

        class Hook(http.server.BaseHTTPRequestHandler):
            """A webhook: takes what's sent to /ok, refuses the rest."""
            def do_POST(self):
                heard.append((self.path, json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))))
                self.send_response(200 if self.path.startswith("/ok") else 401)
                self.end_headers()

            def log_message(self, *args):
                pass
        hook = http.server.HTTPServer(("127.0.0.1", 0), Hook)
        threading.Thread(target=hook.serve_forever, daemon=True).start()
        self.addCleanup(hook.server_close)
        self.addCleanup(hook.shutdown)
        port = hook.server_port
        with mock.patch.object(alerts, "log"):
            self.assertIsNone(alerts.deliver([f"json://127.0.0.1:{port}/ok"], "This is a test from Hoard."))
            said = alerts.deliver([f"json://127.0.0.1:{port}/SECRET1234"], "hi")
        self.assertEqual(heard[0][0], "/ok")
        self.assertEqual((heard[0][1]["title"], heard[0][1]["message"]), ("Hoard", "This is a test from Hoard."))
        self.assertIn("didn't take it", said)
        self.assertIn("401", said, "what the service answered")
        self.assertNotIn("SECRET1234", said)

    def test_discord_gets_an_embed_and_a_plain_service_text(self):
        """Issue #285: a stand-in Discord webhook is sent an embed in Hoard's colour, with its title, what happened and
        the link; a plain webhook gets the same as text."""
        posted, heard = [], []

        class Answer:
            status_code, content, text, headers = 204, b"", "", {}

        def post(url, data=None, json=None, headers=None, **kw):
            posted.append((url, json if json is not None else data))
            return Answer()

        class Hook(http.server.BaseHTTPRequestHandler):
            """A plain webhook."""
            def do_POST(self):
                heard.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass
        hook = http.server.HTTPServer(("127.0.0.1", 0), Hook)
        threading.Thread(target=hook.serve_forever, daemon=True).start()
        self.addCleanup(hook.server_close)
        self.addCleanup(hook.shutdown)
        body, link = alerts.cheaper_text(1, [{"store": "booth", "name": "Fox Ears", "url": "https://booth.pm/en/items/1", "was": "¥1,500", "now": "¥1,200"}])
        with mock.patch("requests.post", post), mock.patch.object(alerts, "log"):
            said = alerts.deliver(["discord://123456789012345678/WebhookToken_abc", f"json://127.0.0.1:{hook.server_port}/ok"],
                                  body, title="Cheaper on your wishlists", event="prices", link=link)
        self.assertIsNone(said)
        (url, payload), = [x for x in posted if "discord" in x[0]]
        payload = payload if isinstance(payload, dict) else json.loads(payload)
        (embed,) = payload["embeds"]
        self.assertEqual((embed["title"], embed["color"], embed["url"]), ("Cheaper on your wishlists", int("F0B429", 16), link))
        self.assertIn("Fox Ears", embed["description"])
        self.assertEqual(embed["author"]["name"], "Hoard")
        self.assertIn("hoard-256.png", embed["thumbnail"]["url"])
        self.assertEqual(heard[0]["title"], "Cheaper on your wishlists")
        # issue #330: with a product's picture, the embed shows it itself, and no file is posted under the embed
        posted.clear()
        where = "https://booth.pximg.net/c/300x300/fox.jpg"
        with mock.patch("requests.post", post), mock.patch.object(alerts, "log"):
            self.assertIsNone(alerts.deliver(["discord://123456789012345678/WebhookToken_abc"], body, title="Cheaper on your wishlists",
                                             event="prices", link=link, picture=(b"\x89PNG\r\n", "image/png"), picture_url=where))
        self.assertEqual(len(posted), 1, "the embed alone: nothing posted beside it")
        payload = posted[0][1] if isinstance(posted[0][1], dict) else json.loads(posted[0][1])
        (embed,) = payload["embeds"]
        self.assertEqual(embed["thumbnail"]["url"], where)
        self.assertIn("hoard-256.png", embed["footer"]["icon_url"], "Hoard's icon stays in the footer")
        self.assertIn("Fox Ears", embed["description"])
        self.assertIn("Fox Ears", heard[0]["message"], "a webhook gets it too (as Markdown, which it takes)")
        # a service that shows only plain text gets it as text
        sent = []

        class TextOnly:
            service_name = "Text"

            def resolve_format(self, wanted):
                return types.SimpleNamespace(value="text")

            def notify(self, body, title, body_format=None, **kw):
                sent.append((body, body_format))
                return True
        import apprise
        with mock.patch.object(apprise.Apprise, "__iter__", lambda self: iter([TextOnly()])), \
                mock.patch.object(apprise.Apprise, "add", lambda self, u: True), mock.patch.object(alerts, "log"):
            alerts.deliver(["text://x"], body, title="Cheaper on your wishlists")
        self.assertEqual(sent[0][0].splitlines()[1], "- Fox Ears (https://booth.pm/en/items/1): ¥1,500 → ¥1,200")
        self.assertNotIn("**", sent[0][0])

    def test_built_addresses_are_ones_apprise_takes(self):
        """Issue #239: every address Build an address makes (tests/test_pages.py's APPRISE_BUILT) is one Apprise takes."""
        import apprise
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_pages import APPRISE_BUILT
        for service, _, address in APPRISE_BUILT:
            self.assertTrue(apprise.Apprise().add(address), f"{service}: {address}")


if __name__ == "__main__":
    unittest.main()
