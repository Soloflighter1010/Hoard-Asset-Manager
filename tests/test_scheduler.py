"""Priority, cooperative pause/stop, owned shutdown and restart checkpoints."""
from __future__ import annotations

import threading
import json
import zipfile
from unittest import mock

from tests.isolation import IsolatedTestCase
from hoard.scheduler import Again, Scheduler


class Scheduling(IsolatedTestCase):
    def scheduler(self, **kwargs):
        scheduler = Scheduler(**kwargs)
        self.addCleanup(scheduler.close)
        return scheduler

    def test_invalid_saved_due_times_do_not_strand_work(self):
        for due in ("tomorrow", True, float("nan"), float("inf")):
            with self.subTest(due=due):
                path = self.test_home / "invalid-schedule.json"
                path.write_text(json.dumps({"tasks": {"reader": {"due": due}}}))
                scheduler = self.scheduler(path=path)
                ran = threading.Event()
                scheduler.add("reader", "Reading packages", lambda context: ran.set())
                self.assertTrue(ran.wait(5))
                scheduler.close()

    def test_a_transient_call_writes_nothing(self):
        """scheduler.json keeps durable tasks only: each job's own call (and its end) never rewrites it."""
        from hoard import storage
        scheduler = self.scheduler(path=self.test_home / "transient-schedule.json")
        ran = threading.Event()
        with mock.patch.object(storage, "write_document", wraps=storage.write_document) as wrote:
            for _ in range(3):
                ran.clear()
                scheduler.call("A job", ran.set)
                self.assertTrue(ran.wait(5))
            with scheduler._condition:   # (until each call has ended: its end is the other write it once made)
                while scheduler._tasks or scheduler._workers:
                    scheduler._condition.wait(0.1)
        self.assertEqual([c for c in wrote.call_args_list if "transient-schedule" in str(c.args[0])], [])

    def test_stopping_the_routine_event_prevents_later_checks(self):
        from hoard.jobs import Schedule
        routine = Schedule.__new__(Schedule)
        routine.tick = mock.Mock()
        stop = threading.Event()
        scheduler = mock.Mock()
        routine.register(scheduler, stop)
        callback = scheduler.add.call_args.args[2]
        callback(None)
        routine.tick.assert_called_once_with()
        stop.set()
        callback(None)
        routine.tick.assert_called_once_with()

    def test_close_finishes_a_state_write_and_prevents_later_writes(self):
        from hoard import scheduler as module
        scheduler = self.scheduler(path=self.test_home / "closing-schedule.json")
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()

        def write(*args):
            entered.set()
            release.wait(5)

        with mock.patch.object(module.storage, "write_document", side_effect=write) as save:
            writer = threading.Thread(target=scheduler._save)
            closer = threading.Thread(target=lambda: (scheduler.close(), closed.set()))
            writer.start()
            try:
                self.assertTrue(entered.wait(5))
                closer.start()
                self.assertFalse(closed.wait(0.1), "close must finish the write before returning ownership of the home")
            finally:
                release.set()
                writer.join(5)
                if closer.ident is not None:
                    closer.join(5)
            self.assertTrue(closed.is_set())
            scheduler._save()
            save.assert_called_once()

    def test_canvas_work_uses_the_same_foreground_and_pause_gate(self):
        scheduler = self.scheduler(persistent=False)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        scheduler.call("User work", lambda: (entered.set(), release.wait(5)))
        self.assertTrue(entered.wait(5))
        self.assertFalse(scheduler.external_progress("pictures", "Matching pictures", 0, 3))
        scheduler.action("pictures", "pause")
        release.set()
        self.assertFalse(scheduler.external_progress("pictures", "Matching pictures", 1, 3))
        self.assertEqual(scheduler.snapshot()[0]["status"], "paused")

    def test_real_package_reader_skips_completed_packages_after_restart(self):
        from hoard import needs
        folder = self.test_home / "packages"
        folder.mkdir(exist_ok=True)
        for name in ("first.zip", "second.zip"):
            with zipfile.ZipFile(folder / name, "w") as archive:
                archive.writestr("Assets/Sample.cs", "public class Sample {}")
        assets = [{"abs_folder": str(folder), "files": [{"path": name} for name in ("first.zip", "second.zip")]}]
        index_path = self.test_home / "needs.json"
        schedule_path = self.test_home / "reader-schedule.json"
        first = self.scheduler(path=schedule_path)
        reader = needs.NeedsReader(needs.NeedsIndex(index_path), lambda: assets, lambda: False)
        saved = threading.Event()

        def first_step(context):
            again = reader.step(context)
            first.action("package-reader", "pause")
            saved.set()
            return again

        first.add("package-reader", "Reading packages", first_step)
        self.assertTrue(saved.wait(5))
        first.close()
        self.assertTrue(needs.NeedsIndex(index_path).fresh(str(folder / "first.zip")))
        second = self.scheduler(path=schedule_path)
        reader = needs.NeedsReader(needs.NeedsIndex(index_path), lambda: assets, lambda: False)
        finished = threading.Event()
        reader.on_read = finished.set
        with mock.patch.object(needs, "read_file", wraps=needs.read_file) as read:
            reader.register(second)
            second.action("package-reader", "resume")
            self.assertTrue(finished.wait(5))
            second.close()
        self.assertEqual([call.args[0].name for call in read.call_args_list], ["second.zip"])
        self.assertEqual(second.snapshot()[0]["progress"]["done"], 2)

    def test_waiting_user_jobs_survive_a_restart_in_order(self):
        from hoard import config, jobs, library, storage
        from hoard.paths import data_dir
        storage.remove(data_dir() / "job-queue.json", missing_ok=True)
        cfg = config.load_config()
        lib = library.Library(self.test_home / "library.json")
        first = self.scheduler(path=self.test_home / "queue-schedule.json")
        queued = jobs.Jobs(cfg, lib, scheduler=first)
        queued.busy.acquire()   # another task owns this lane; neither request can start yet
        try:
            self.assertEqual(queued.start("download", ["booth"], only="First"), "queued")
            self.assertEqual(queued.start("download", ["gumroad"], only="Second"), "queued")
        finally:
            queued.busy.release()
        first.close()
        second = self.scheduler(path=self.test_home / "queue-schedule.json")
        restored = jobs.Jobs(cfg, lib, scheduler=second)
        self.assertEqual([entry["only"] for entry in restored._queue], ["First", "Second"])
        seen, done = [], threading.Event()

        def download(stores, only, *args, **kwargs):
            seen.append(only)
            if len(seen) == 2:
                done.set()

        with mock.patch.object(restored, "_download", download):
            restored.kick()
            self.assertTrue(done.wait(5))
            second.close()
        self.assertEqual(seen, ["First", "Second"])

    def test_what_deletes_isnt_started_again_unasked(self):
        """What changes or takes things away was confirmed when it was asked for, not when Hoard opens again: a
        waiting delete, Take out of Local, sign-out or a project's delete isn't started again; Tasks says so. A
        waiting refresh, or a project's backup, is."""
        from hoard import config, jobs, library, storage
        from hoard.paths import data_dir
        storage.remove(data_dir() / "job-queue.json", missing_ok=True)
        cfg = config.load_config()
        lib = library.Library(self.test_home / "library.json")
        first = self.scheduler(path=self.test_home / "queue-schedule-2.json")
        queued = jobs.Jobs(cfg, lib, scheduler=first)
        projects = jobs.Jobs(cfg, lib, lane=jobs.PROJECTS, scheduler=first)
        queued.busy.acquire()
        projects.busy.acquire()
        try:
            self.assertEqual(queued.start("delete-files", ["booth"], keys=["booth:1"]), "queued")
            self.assertEqual(queued.start("refresh", ["booth"]), "queued")
            self.assertEqual(queued.start("logout", ["gumroad"]), "queued")
            self.assertEqual(projects.start("project", [], project={"op": "delete", "path": "/p/Rusk", "name": "Rusk"}), "queued")
            self.assertEqual(projects.start("project", [], project={"op": "backup", "path": "/p/Rusk", "name": "Rusk"}), "queued")
        finally:
            queued.busy.release()
            projects.busy.release()
        first.close()
        second = self.scheduler(path=self.test_home / "queue-schedule-2.json")
        self.addCleanup(second.close)
        again, again_projects = jobs.Jobs(cfg, lib, scheduler=second), jobs.Jobs(cfg, lib, lane=jobs.PROJECTS, scheduler=second)
        self.assertEqual([q["task"] for q in again._queue], ["refresh"])
        self.assertEqual([q["project"]["op"] for q in again_projects._queue], ["backup"])
        said = [(h["task"], h["outcome"]) for h in again.history[-2:]]
        self.assertEqual(said, [("delete-files", "stopped"), ("logout", "stopped")])
        self.assertIn("Not started again", again.history[-1]["message"])
        self.assertEqual(again_projects.history[-1]["label"], "Projects: " + jobs.PROJECT_WORK["delete"].replace("{0}", "Rusk"))
        kept = [(h["task"], h["outcome"], h["message"]) for h in jobs.Jobs(cfg, lib, scheduler=second).history[-2:]]
        self.assertEqual(kept, [(h["task"], h["outcome"], h["message"]) for h in again.history[-2:]], "kept in Tasks")

    def test_user_work_pauses_a_reader_and_it_carries_on_afterwards(self):
        scheduler = self.scheduler(persistent=False)
        reading, next_unit, resumed = threading.Event(), threading.Event(), threading.Event()
        foreground, release = threading.Event(), threading.Event()
        self.addCleanup(next_unit.set)
        self.addCleanup(release.set)

        def reader(context):
            reading.set()
            next_unit.wait(5)
            context.checkpoint()
            resumed.set()

        def user_job():
            foreground.set()
            release.wait(5)

        scheduler.add("packages", "Reading packages", reader)
        self.assertTrue(reading.wait(5))
        scheduler.call("Download", user_job)
        self.assertTrue(foreground.wait(5))
        next_unit.set()
        self.assertFalse(resumed.wait(0.1), "the reader must not begin another unit while user work runs")
        release.set()
        self.assertTrue(resumed.wait(5))

    def test_a_reader_beside_your_tasks_carries_on(self):
        """One registered beside=True (Reading products' pages: it keeps off the stores your task uses itself) starts
        and carries on while your task runs; it's still one maintenance at a time, and Pause still pauses it."""
        scheduler = self.scheduler(persistent=False)
        foreground, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        steps, other = [], threading.Event()

        def user_job():
            foreground.set()
            release.wait(10)

        def pages(context):
            context.checkpoint()
            steps.append(1)
            return Again(0.01) if len(steps) < 3 else None

        scheduler.call("Download", user_job)
        self.assertTrue(foreground.wait(5))
        scheduler.add("store-pages", "Reading products' pages", pages, durable=False, beside=True)
        scheduler.add("packages", "Reading packages", lambda context: other.set(), durable=False)
        for _ in range(200):
            if len(steps) == 3:
                break
            threading.Event().wait(0.02)
        self.assertEqual(len(steps), 3, "all its steps while the download runs")
        self.assertFalse(other.is_set(), "other maintenance still waits for your task")
        release.set()
        self.assertTrue(other.wait(5))

    def test_restart_retains_pause_and_completed_work(self):
        scheduler = self.scheduler(path=self.test_home / "schedule.json")
        saved = threading.Event()

        def first(context):
            context.advance(done=1, total=3, message="Reading packages", saved={"next": 1, "private": "/private/file"})
            scheduler.action("packages", "pause")
            saved.set()
            return Again()

        scheduler.add("packages", "Reading packages", first)
        self.assertTrue(saved.wait(5))
        scheduler.close()
        restarted = self.scheduler(path=self.test_home / "schedule.json")
        seen, finished = [], threading.Event()

        def remaining(context):
            seen.append(context.saved["next"])
            context.advance(done=3, total=3, saved={"next": 3})
            finished.set()

        restarted.add("packages", "Reading packages", remaining)
        self.assertEqual(restarted.snapshot()[0]["status"], "paused")
        self.assertNotIn("/private/file", str(restarted.snapshot()))
        self.assertFalse(finished.wait(0.1))
        restarted.action("packages", "resume")
        self.assertTrue(finished.wait(5))
        self.assertEqual(seen, [1], "the completed first unit must not be repeated")

    def test_stop_wakes_a_paused_worker_without_losing_its_checkpoint(self):
        scheduler = self.scheduler(persistent=False)
        paused, returned = threading.Event(), threading.Event()

        def reader(context):
            context.advance(done=2, total=5, saved={"next": 2})
            scheduler.action("packages", "pause")
            paused.set()
            try:
                context.checkpoint()
                self.fail("Stop must interrupt the paused callback")
            finally:
                returned.set()

        scheduler.add("packages", "Reading packages", reader)
        self.assertTrue(paused.wait(5))
        scheduler.action("packages", "stop")
        self.assertTrue(returned.wait(5))
        state = scheduler.snapshot()[0]
        self.assertEqual((state["status"], state["progress"]["done"]), ("stopped", 2))
        self.assertEqual(state["error"], "")

    def test_shutdown_interrupts_preempted_readers(self):
        scheduler = self.scheduler(persistent=False)
        paused, ended = threading.Event(), threading.Event()

        def reader(context):
            scheduler.action("packages", "pause")
            paused.set()
            try:
                context.checkpoint()
            finally:
                ended.set()

        scheduler.add("packages", "Reading packages", reader)
        self.assertTrue(paused.wait(5))
        scheduler.close()
        self.assertTrue(ended.is_set())
        self.assertFalse(scheduler._workers)
