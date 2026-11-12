"""Owned background work, cooperative priority, and durable progress checkpoints.

Only this module starts task workers or waits for their next scheduled run.
Readers register small steps and checkpoint between expensive operations. User
work gets priority over maintenance; foreground lanes can still run together.
Callback code is registered by the application, never deserialized from disk.
"""
from __future__ import annotations

import copy
import json
import math
import threading
import time
import weakref
from dataclasses import dataclass
from pathlib import Path

from . import storage
from .paths import data_dir

USER = 0
ROUTINE = 10
MAINTENANCE = 20
PACKAGES = 30
_local = threading.local()
_instances = weakref.WeakSet()


class TaskStopped(BaseException):
    """Stop or shutdown, deliberately outside ordinary per-file error handling."""


@dataclass(frozen=True)
class Again:
    """Continue a bounded step after this delay; its Context owns the saved cursor."""
    after: float = 0.0


def checkpoint() -> None:
    """A cheap cancellation/preemption point; a normal request or CLI call is unaffected."""
    context = getattr(_local, "context", None)
    if context is not None:
        context.checkpoint()


def close_all() -> None:
    """Release standalone schedulers too, including those owned by class-scoped tests."""
    for scheduler in list(_instances):
        scheduler.close()


class Context:
    """A task's cooperative Stop/Pause boundary and durable progress cursor."""

    def __init__(self, scheduler: "Scheduler", key: str):
        self.scheduler, self.key = scheduler, key

    @property
    def saved(self):
        """The last committed cursor, copied so updates only happen through advance()."""
        with self.scheduler._condition:
            return copy.deepcopy(self.scheduler._tasks[self.key]["checkpoint"])

    def checkpoint(self) -> None:
        """Pause maintenance while foreground work runs; Stop also wakes a paused task."""
        scheduler = self.scheduler
        with scheduler._condition:
            task = scheduler._tasks[self.key]
            while True:
                if task.get("cancel") and task["cancel"]():
                    from .common import Cancelled
                    raise Cancelled()
                if scheduler._closed or task["stopped"]:
                    if task.get("cancel"):
                        from .common import Cancelled
                        raise Cancelled()
                    raise TaskStopped()
                waiting = not task["foreground"] and not task.get("beside") and scheduler._foreground_waiting()
                if not task["paused"] and not waiting:
                    task["status"] = "running"
                    return
                task["status"] = "paused" if task["paused"] else "waiting"
                scheduler._condition.wait(0.25)

    def advance(self, *, done: int, total: int, message: str = "", saved=None) -> None:
        """Commit completed work before the next checkpoint; completed units survive a restart."""
        scheduler = self.scheduler
        with scheduler._condition:
            task = scheduler._tasks[self.key]
            task["progress"] = {"done": max(0, int(done)), "total": max(0, int(total)), "message": str(message)[:300]}
            if saved is not None:
                task["checkpoint"] = copy.deepcopy(saved)
        scheduler._save()
        self.checkpoint()


class Scheduler:
    """One clock and worker owner for an app's foreground lanes and maintenance.

    At most one maintenance callback runs at a time. A foreground callback can
    start immediately; maintenance yields at its next checkpoint, but for one
    registered beside=True, which keeps out of your tasks' way itself (reading
    products' public pages from stores a task isn't using). Timer-only control
    callbacks may run alongside both, for stuck-job monitoring and Stop.
    Registered durable keys recover their progress, pause state and next run.
    """

    def __init__(self, path: Path | None = None, *, persistent: bool = True):
        self.path = path or data_dir() / "scheduler.json"
        self.persistent = persistent
        self._condition = threading.Condition(threading.RLock())
        self._persist_lock = threading.Lock()
        self._tasks: dict[str, dict] = {}
        self._workers: set[threading.Thread] = set()
        self._clock: threading.Thread | None = None
        self._closed = False
        self._sequence = 0
        self._last_saved = 0.0
        raw = storage.read_document(self.path) if persistent and storage.exists(self.path) else {}
        self._saved = raw.get("tasks", {}) if isinstance(raw, dict) else {}
        if not isinstance(self._saved, dict):
            self._saved = {}
        _instances.add(self)

    def add(self, key: str, label: str, callback, *, priority: int = MAINTENANCE,
            delay: float = 0, every: float | None = None, foreground: bool = False,
            durable: bool = True, visible: bool = True, control: bool = False, cancel=None, external: bool = False,
            beside: bool = False) -> str:
        """Register trusted code and its schedule; repeating registration never duplicates a worker."""
        with self._condition:
            if self._closed:
                raise RuntimeError("scheduler is closed")
            if key in self._tasks:
                return key
            old = self._saved.get(key, {}) if durable else {}
            if not isinstance(old, dict):
                old = {}
            due = old.get("due", time.time() + max(0, delay))
            progress = old.get("progress", {})
            self._sequence += 1
            self._tasks[key] = {
                "key": key, "label": label, "callback": callback, "priority": priority,
                "foreground": foreground, "control": control, "durable": durable, "visible": visible,
                "external": external, "beside": beside,
                "every": every, "due": due if isinstance(due, (int, float)) and not isinstance(due, bool) and math.isfinite(due) else time.time() + max(0, delay),
                "checkpoint": old.get("checkpoint", {}),
                "progress": progress if isinstance(progress, dict) else {},
                "paused": old.get("paused") is True, "stopped": old.get("stopped") is True,
                "finished": old.get("finished") is True, "running": False, "rerun": False,
                "status": "waiting", "sequence": self._sequence, "error": "", "cancel": cancel,
            }
            self._condition.notify_all()
        if durable:   # (a transient call is never kept: nothing new for scheduler.json)
            self._save()
        self.start()
        return key

    def call(self, label: str, callback, *, priority: int = USER, delay: float = 0,
             foreground: bool = True, control: bool = False, cancel=None, visible: bool = False) -> str:
        """Schedule an owned, transient call (foreground work keeps its queue in Jobs)."""
        with self._condition:
            self._sequence += 1
            key = f"call-{self._sequence}"
        return self.add(key, label, lambda context: callback(), priority=priority, delay=delay,
                        foreground=foreground, control=control, durable=False, visible=visible, cancel=cancel)

    def start(self) -> None:
        """Start the sole scheduling clock once, after at least one callback is registered."""
        with self._condition:
            if self._clock is None and not self._closed:
                self._clock = threading.Thread(target=self._run, name="hoard-scheduler", daemon=True)
                self._clock.start()

    @property
    def closed(self) -> bool:
        """Job queues stay queued once shutdown begins."""
        return self._closed

    def wake(self, key: str) -> None:
        """New work arrived; preserve an explicit Pause/Stop, and coalesce repeated wakeups."""
        with self._condition:
            task = self._tasks.get(key)
            if task is None:
                return
            task.update(due=time.time(), finished=False, rerun=task["running"])
            durable = task["durable"]
            self._condition.notify_all()
        if durable:
            self._save()

    def action(self, key: str, action: str) -> None:
        """Apply Tasks' Pause, Resume or Stop without discarding a completed-work checkpoint."""
        if action not in ("pause", "resume", "stop"):
            raise ValueError("unknown background task action")
        with self._condition:
            task = self._tasks.get(key)
            if task is None or not task["visible"]:
                raise ValueError("unknown background task")
            if action == "resume":
                task.update(paused=False, stopped=False, finished=False, due=time.time())
            elif action == "pause":
                task["paused"] = True
            else:
                task["stopped"] = True
            self._condition.notify_all()
        self._save()

    def snapshot(self) -> list[dict]:
        """Only presentation fields; cursors, file paths and callback arguments remain private."""
        with self._condition:
            return [{"id": task["key"], "label": task["label"], "priority": task["priority"],
                     "status": "stopped" if task["stopped"] else "paused" if task["paused"] else
                               "waiting" if task["external"] and self._foreground_waiting() else task["status"],
                     "progress": copy.deepcopy(task["progress"]), "error": task["error"]}
                    for task in sorted(self._tasks.values(), key=lambda task: (task["priority"], task["sequence"]))
                    if task["visible"]]

    def external_progress(self, key: str, label: str, done: int, total: int) -> bool:
        """Gate a renderer-owned step (canvas image hashing) with the same Pause and priority rules.

        The browser asks before each image and commits its results through the
        existing picture endpoint. No image URL or access token is persisted.
        Returning False leaves the remaining images for the next view refresh.
        """
        self.add(key, label, None, external=True)
        with self._condition:
            task = self._tasks[key]
            task["progress"] = {"done": done, "total": total, "message": label}
            task.update(finished=done >= total, status="complete" if done >= total else "running")
            allowed = not task["paused"] and not task["stopped"] and not self._foreground_waiting()
            if not allowed and not task["finished"]:
                task["status"] = "waiting"
        self._save(throttle=done < total)
        return allowed

    def _foreground_waiting(self) -> bool:
        """Called under the condition: queued user work counts before its worker begins."""
        now = time.time()
        return any(task["foreground"] and not task["control"] and not task["finished"]
                   and not task["paused"] and not task["stopped"] and task["due"] <= now
                   for task in self._tasks.values())

    def _run(self) -> None:
        """Dispatch due tasks by priority; all timer waits and worker creation live here."""
        while True:
            with self._condition:
                if self._closed:
                    return
                now = time.time()
                maintenance = any(t["running"] and not t["foreground"] and not t["control"] for t in self._tasks.values())
                ready = [t for t in self._tasks.values() if not any(t[k] for k in ("running", "paused", "stopped", "finished", "external"))
                         and t["due"] <= now and (t["foreground"] or t["control"]
                                                  or not maintenance and (t["beside"] or not self._foreground_waiting()))]
                if not ready or len(self._workers) >= 4:
                    self._condition.wait(0.1)
                    continue
                task = min(ready, key=lambda t: (t["priority"], t["due"], t["sequence"]))
                task.update(running=True, status="running", rerun=False)
                worker = threading.Thread(target=self._execute, args=(task["key"],), name="hoard-" + task["key"], daemon=True)
                self._workers.add(worker)
                worker.start()

    def _execute(self, key: str) -> None:
        """Run one step, keep its cursor on failure, and publish its next due time."""
        context = Context(self, key)
        _local.context = context
        again, failed = None, False
        try:
            # Jobs establishes its own Cancelled handler before the first check,
            # so even a job stopped before it starts releases its lane's lock.
            if self._tasks[key]["cancel"] is None:
                context.checkpoint()
            again = self._tasks[key]["callback"](context)
        except TaskStopped:
            pass
        except Exception as error:
            failed = True
            # A status can be shown while hidden products are locked. Raw exception
            # text may contain a private path; diagnostics owns detailed reports.
            from . import diagnostics
            diagnostics.record_exception(error, area="scheduler", task=key, include_traceback=True)
        finally:
            _local.context = None
            with self._condition:
                task = self._tasks[key]
                task["running"] = False
                task["error"] = "Background task could not finish. Retry or create a diagnostic report." if failed else ""
                if self._closed or task["stopped"]:
                    task["status"] = "waiting"
                elif task["rerun"] or isinstance(again, Again) or task["every"] is not None or failed:
                    delay = 0 if task["rerun"] else again.after if isinstance(again, Again) else task["every"]
                    task.update(due=time.time() + (max(60, delay or 0) if failed else max(0, delay or 0)), status="waiting")
                else:
                    task.update(finished=True, status="complete")
                durable = task["durable"]
                if not durable and task["finished"]:
                    del self._tasks[key]
                self._condition.notify_all()
            try:
                if durable:   # (a transient call's end changes nothing kept in scheduler.json)
                    self._save()
            finally:
                with self._condition:
                    self._workers.discard(threading.current_thread())
                    self._condition.notify_all()

    def _save(self, *, throttle: bool = False) -> None:
        """Write snapshots in order without holding the scheduling lock during SQLite I/O."""
        if not self.persistent or self._closed:
            return
        with self._persist_lock:
            if self._closed:
                return
            if throttle and time.monotonic() - self._last_saved < 1:
                return
            with self._condition:
                saved = {**self._saved, **{key: {field: copy.deepcopy(task[field]) for field in
                              ("due", "checkpoint", "progress", "paused", "stopped", "finished")}
                         for key, task in self._tasks.items() if task["durable"]}}
            storage.write_document(self.path, json.dumps({"version": 1, "tasks": saved}))
            self._last_saved = time.monotonic()

    def close(self) -> None:
        """Finish state writes, wake paused workers and wait up to ten seconds for owned threads."""
        # Match _save's lock order and finish an in-flight write before closing. A worker queued for this lock
        # must recheck _closed, so it cannot reopen a data home after its owner has released it.
        with self._persist_lock:
            with self._condition:
                if self._closed:
                    return
                self._closed = True
                self._condition.notify_all()
                workers = list(self._workers) + ([self._clock] if self._clock else [])
        deadline = time.monotonic() + 10
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=max(0, deadline - time.monotonic()))
