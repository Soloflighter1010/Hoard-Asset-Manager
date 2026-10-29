"""Issue #230: notifications through Apprise, for the news you choose: the addresses kept as API keys are (never in
config.json), what's sent saying how many and never a product's name, and nothing sent unless chosen."""
from __future__ import annotations

import json
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


class FakeApprise:
    """A stand-in for the apprise package: what was added and sent, and what it answers."""
    sent: list = []
    accept = True

    def __init__(self):
        self.added = []

    def add(self, url):
        ok = "://" in url and not url.startswith("nope://")
        if ok:
            self.added.append(url)
        return ok

    def notify(self, body, title):
        FakeApprise.sent.append((list(self.added), title, body))
        return FakeApprise.accept


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

    def test_what_a_service_answers(self):
        self.assertIsNone(alerts.deliver(["json://example.com/hook"], "hi"))
        FakeApprise.accept = False
        self.assertIn("didn't take it", alerts.deliver(["json://example.com/hook"], "hi"))
        FakeApprise.accept = True
        self.assertEqual(alerts.deliver(["nope://x"], "hi"), "None of the addresses is one Apprise knows.")
        said = alerts.deliver(["nope://secret-token", "json://example.com/hook"], "hi")
        self.assertIn("1 of the addresses", said)
        self.assertNotIn("secret-token", said, "an address is never said: it holds a token")

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


if __name__ == "__main__":
    unittest.main()
