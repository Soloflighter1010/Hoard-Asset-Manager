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
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoard import alerts, config, jobs, library, vault  # noqa: E402


class FakeService:
    """One service an address is for, as Apprise has it: what it's sent, and what it answers (a refusal, as Apprise's
    services do, said in Apprise's log with the address in it)."""

    def __init__(self, url):
        self.url, self.service_name = url, url.split("://")[0].title()

    def notify(self, body, title):
        FakeApprise.sent.append(([self.url], title, body))
        if not FakeApprise.accept:
            logging.getLogger("apprise").warning(f"Failed to send {self.service_name} notification to {self.url}: "
                                                 "Unauthorized - error=401.")
        return FakeApprise.accept


class FakeApprise:
    """A stand-in for the apprise package: what was added and sent, and what it answers."""
    sent: list = []
    accept = True

    def __init__(self):
        self.added = []

    def add(self, url):
        ok = "://" in url and not url.startswith("nope://")
        if ok:
            self.added.append(FakeService(url))
        return ok

    def __iter__(self):
        return iter(self.added)


class Alerts(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(self.tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        self.cfg = {**config.load_config(), "allow_unprotected_signins": True, "apprise_events": ["new", "tasks"]}
        FakeApprise.sent, FakeApprise.accept = [], True
        fake = types.ModuleType("apprise")
        fake.Apprise = FakeApprise
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
                                             "The routine check found 3 new products. Open Hoard to choose what to download.")])
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

        def broken(self, body, title):
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
        self.assertEqual(text, "Download: partly done (2 new, 1 updated, 1 couldn't be downloaded).")
        self.assertNotIn("Secret", text, "never a product's name")
        self.assertEqual(alerts.task_text({"task": "check-updates", "outcome": "done", "report": {"updates": 1}}),
                         "Check for updates: done (1 product with updates).")

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


class AlertsInHoard(unittest.TestCase):
    """The server's side: the addresses kept through /api/apprise (and never sent back), a test sent to them, what's
    sent chosen in Settings, and the tasks' news turned into what's sent."""

    def setUp(self):
        import http.client
        from hoard import server
        from hoard.safety import ACCESS_HEADER
        self.tmp = Path(tempfile.mkdtemp())
        for patch in (mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(self.tmp / "data")}),
                      mock.patch.object(server, "save_config"), mock.patch.object(alerts, "available", lambda: True),
                      mock.patch.object(alerts, "_kept", None)):
            patch.start()
            self.addCleanup(patch.stop)
        fake = types.ModuleType("apprise")
        fake.Apprise = FakeApprise
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
        self.assertEqual(self.call("GET", "/api/settings")[1]["apprise"], {"available": True, "kept": 0, "events": []})
        self.assertEqual(self.call("POST", "/api/apprise/test", {})[0], 400, "nothing kept yet")
        self.assertEqual(self.call("POST", "/api/apprise", {"urls": "not an address"})[0], 400)
        self.assertEqual(self.call("POST", "/api/apprise", {"urls": "json://example.com/hook?token=SECRET123\ntgram://bot/chat"}),
                         (200, {"ok": True, "kept": 2}))
        status, settings = self.call("GET", "/api/settings")
        self.assertEqual(settings["apprise"]["kept"], 2)
        self.assertNotIn("SECRET123", json.dumps(settings), "never sent back")
        self.assertNotIn("SECRET123", json.dumps(self.srv.cfg), "never in config.json")
        self.assertEqual(self.call("POST", "/api/apprise/test", {}), (200, {"ok": True, "error": None}))
        self.assertEqual(FakeApprise.sent[-1][2], "This is a test from Hoard: notifications through Apprise work.")
        self.assertEqual(self.call("POST", "/api/settings", {"apprise_events": ["tasks", "nonsense", "new"]})[0], 200)
        self.assertEqual(self.srv.cfg["apprise_events"], ["new", "tasks"], "known ones only, in order")
        self.assertEqual(self.call("POST", "/api/apprise", {"forget": True}), (200, {"ok": True, "kept": 0}))
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
            "The routine check found 2 new products. Open Hoard to choose what to download.",
            "The routine check found 1 update. Open Hoard to choose what to download.",
            "1 product on your wishlists is cheaper than before.",
            "The check of your downloads found 1 file changed and 3 files missing. Open Hoard to see what it found.",
            "The routine check found 2 new products.",
            "Download: done (1 new).",
            "Hoard 5.2.0 is available. Open Hoard to update."])
        FakeApprise.sent.clear()
        self.srv.cfg["apprise_events"] = ["prices"]
        self.srv._news("finished", {"task": "download", "outcome": "failed", "report": {}})
        time.sleep(0.1)
        self.assertEqual(FakeApprise.sent, [], "tasks aren't ticked: nothing sent")


@unittest.skipUnless(importlib.util.find_spec("apprise"), "Apprise isn't installed here")
class RealApprise(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
