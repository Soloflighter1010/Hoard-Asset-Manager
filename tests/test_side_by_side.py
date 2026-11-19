"""Issue #403: tasks side by side, when they don't get in each other's way. Each kind of task says what it uses
(jobs.claims); a small one (a product's list of files, Local's tasks, deleting files, checking downloads) runs in the
side lane beside what the main lane runs when they share nothing, and waits its turn when they do. A settings change
waits only for a task that uses what it changes."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase
from hoard import config, jobs, server


def wait_for(test, what, seconds=10.0):
    """Wait until what() is true (a task in another thread getting there)."""
    deadline = time.monotonic() + seconds
    while not what():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


class Claims(IsolatedTestCase):
    def test_what_each_task_uses(self):
        c = lambda task, stores=("booth",): jobs.claims({"task": task, "stores": list(stores)})  # noqa: E731
        self.assertEqual(c("list-files"), {"store:booth"})
        self.assertEqual(c("add-local", []), {"local"})
        self.assertEqual(c("download"), {"store:booth", "downloads"})
        self.assertEqual(c("refresh", ["all"]), {jobs.EVERY_STORE, "library"})
        self.assertEqual(c("verify", []), {"downloads", "local"})
        self.assertTrue({"downloads", "local", "library", "browser"} <= c("sync"), "a sync uses everything")
        self.assertTrue({"downloads", "local", "library"} <= c("something new"), "one not known uses everything")

    def test_what_clashes(self):
        clash = jobs.clash
        self.assertFalse(clash(frozenset({"store:booth", "downloads"}), frozenset({"store:gumroad"})))
        self.assertTrue(clash(frozenset({"store:booth", "downloads"}), frozenset({"store:booth"})))
        self.assertTrue(clash(frozenset({jobs.EVERY_STORE}), frozenset({"store:jinxxy"})), "every store takes in each")
        self.assertTrue(clash(frozenset({"store:jinxxy"}), frozenset({jobs.EVERY_STORE})))
        self.assertFalse(clash(frozenset({jobs.EVERY_STORE}), frozenset({"local"})))
        self.assertFalse(clash(frozenset(), frozenset({"downloads"})))


class SideBySide(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(self.tmp / "dl"), "setup_done": True},
                                    lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.download_gate = threading.Event()
        self.addCleanup(self.download_gate.set)
        self.ran = []

        def download(stores, *a, **k):
            self.ran.append(("download", tuple(stores)))
            self.download_gate.wait(20)
        self.local_gate = threading.Event()
        self.addCleanup(self.local_gate.set)

        def add_local(what):
            self.ran.append(("add-local", what.get("name")))
            self.local_gate.wait(20)
        for lane in (self.srv.jobs, self.srv.side_jobs):
            self.enterContext(mock.patch.object(lane, "_download", download))
            self.enterContext(mock.patch.object(lane, "_add_local", add_local))
            self.enterContext(mock.patch.object(lane, "_verify", lambda *a, **k: self.ran.append(("verify",))))

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}", json.dumps(body).encode(),
                                     {"X-Hoard-Key": self.srv.key, "Content-Type": "application/json",
                                      "Origin": f"http://127.0.0.1:{self.srv.server_address[1]}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_a_small_task_runs_beside_a_download(self):
        self.assertEqual(self.srv.jobs.start("download", ["booth"]), "started")
        self.assertTrue(wait_for(self, lambda: ("download", ("booth",)) in self.ran))
        self.assertEqual(self.srv.jobs.start("add-local", [], local={"name": "Mine"}), "started", "Local: nothing it shares")
        self.assertTrue(wait_for(self, lambda: ("add-local", "Mine") in self.ran))
        self.assertTrue(self.srv.side_jobs.state["running"] and self.srv.jobs.state["running"], "both at once")
        self.assertEqual(self.srv.jobs.start("list-files", ["gumroad"], keys=["gumroad:x"]), "queued",
                         "the side lane does one at a time")
        self.local_gate.set()
        self.assertTrue(wait_for(self, lambda: ("download", ("gumroad",)) in self.ran), "then the next, still beside it")
        self.assertTrue(self.srv.jobs.state["running"], "the download is still running")
        # each in Tasks and /api/status, the side lane's with ids of its own
        tasks = self.srv.tasks()
        self.assertEqual(tasks["current"]["task"], "download")
        self.assertTrue(all(h["id"].startswith("s") for h in self.srv.side_jobs.history))
        self.assertIn("side_job", self.get_status())

    def get_status(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}/api/status", headers={"X-Hoard-Key": self.srv.key})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def test_two_that_use_the_same_wait_for_each_other(self):
        self.assertEqual(self.srv.jobs.start("download", ["booth"]), "started")
        self.assertTrue(wait_for(self, lambda: self.ran))
        self.assertEqual(self.srv.jobs.start("list-files", ["booth"], keys=["booth:1"]), "queued", "the same store")
        self.assertEqual(self.srv.jobs.start("verify", []), "queued", "the downloads it's writing")
        self.assertEqual([q["task"] for q in self.srv.jobs.state["queue"]], ["list-files", "verify"],
                         "waiting in the main lane, as before, behind the download")
        self.assertFalse(self.srv.side_jobs.state["running"])
        self.download_gate.set()
        self.assertTrue(wait_for(self, lambda: ("verify",) in self.ran))
        self.assertEqual([r[0] for r in self.ran], ["download", "download", "verify"], "in turn, after it")

    def test_a_task_waits_for_the_side_lanes_when_they_clash(self):
        self.assertEqual(self.srv.jobs.start("add-local", [], local={"name": "Mine"}), "started")
        self.assertTrue(wait_for(self, lambda: self.srv.side_jobs.state["running"]), "beside an empty main lane")
        self.assertEqual(self.srv.jobs.start("verify", []), "queued", "it reads Local, which the side lane is changing")
        time.sleep(0.3)
        self.assertNotIn(("verify",), self.ran)
        self.assertEqual([q["task"] for q in self.srv.side_jobs.state["queue"]], ["verify"], "behind it, in the side lane")
        self.assertEqual(self.srv.jobs.start("download", ["booth"]), "started", "a download shares nothing with Local")
        self.local_gate.set()
        time.sleep(0.3)
        self.assertNotIn(("verify",), self.ran, "and the check waits for the download too: it reads what that writes")
        self.download_gate.set()
        self.assertTrue(wait_for(self, lambda: ("verify",) in self.ran), "then it runs")

    def test_a_setting_waits_only_for_a_task_that_uses_it(self):
        with mock.patch.object(server, "save_config"):
            self.assertEqual(self.srv.jobs.start("download", ["booth"]), "started")
            self.assertTrue(wait_for(self, lambda: self.ran))
            status, got = self.post("/api/settings", {"stores": {"gumroad": {"enabled": False}}})
            self.assertEqual(status, 200, got)
            self.assertFalse(self.srv.cfg["gumroad"]["enabled"], "a store the download isn't from")
            self.assertEqual(self.post("/api/settings", {"stores": {"booth": {"include_free": False}}})[0], 409,
                             "the store it's downloading from")
            self.assertEqual(self.post("/api/settings", {"browser_channel": "chromium"})[0], 409, "the store browser")
            self.assertEqual(self.post("/api/settings", {"root": str(self.tmp / "elsewhere")})[0], 409, "where it downloads to")
            self.assertEqual(self.post("/api/settings", {"payhip_shops": []})[0], 200, "Payhip's, which it isn't using")
            self.download_gate.set()
            self.assertTrue(wait_for(self, lambda: not self.srv.jobs.state["running"]))
            self.assertEqual(self.post("/api/settings", {"stores": {"booth": {"include_free": False}}})[0], 200, "after it")

    def test_a_setting_changes_while_the_catalog_is_written(self):
        """The catalog being written holds the main lane's runner without a task: a setting doesn't wait for it."""
        with mock.patch.object(server, "save_config"):
            self.assertTrue(self.srv.jobs.busy.acquire(timeout=5))
            try:
                self.assertEqual(self.post("/api/settings", {"stores": {"gumroad": {"enabled": False}}})[0], 200)
                self.assertEqual(self.srv.jobs.start("add-local", [], local={"name": "Mine"}), "queued",
                                 "but a task waits for it: it doesn't say what it uses")
            finally:
                self.srv.jobs.busy.release()
                self.srv.jobs.kick()
            self.assertTrue(wait_for(self, lambda: ("add-local", "Mine") in self.ran), "and starts once it's done")

    def test_the_local_sync_folder_waits_for_a_local_task_beside(self):
        from hoard import localsync
        self.srv.cfg["local_sync"] = str(self.tmp / "sync")
        self.assertEqual(self.srv.jobs.start("add-local", [], local={"name": "Mine"}), "started")
        self.assertTrue(wait_for(self, lambda: self.srv.side_jobs.state["running"]))
        with mock.patch.object(localsync, "scan", lambda *a: self.fail("never while Local's task runs beside")):
            self.assertIsNone(localsync.tick(self.srv))
        self.assertFalse(self.srv.jobs.busy.locked(), "the main lane's runner let go again")
        self.local_gate.set()
        self.assertTrue(wait_for(self, lambda: not self.srv.side_jobs.state["running"]))
        with mock.patch.object(localsync, "scan", lambda *a: {"added": [], "gone": []}):
            self.assertEqual(localsync.tick(self.srv), {"added": [], "gone": []})
