"""Tasks endpoints and their domain helpers.

The server module is the service facade during this extraction: explicit app.*
references keep dependency overrides working while HTTP plumbing stays in server.
"""
from __future__ import annotations

from .. import server as app
from .routing import Route


def _queued(self, started: str | None):
    """The answer for something asked while a job ran: it waits its turn (or started, if that job just ended)."""
    if not started:
        return self._json({"error": "That's already waiting its turn."}, 409)
    return self._json({"ok": True, "queued": started == "queued", "job": True})


def get_api_tasks(self, path, body, query):
    """GET /api/tasks. the Tasks tab: running, waiting and finished jobs"""
    srv = self.server
    u = app.urlparse(self.path)
    tasks, hidden = srv.tasks(), self._hidden_names()
    if hidden:
        def mask(job):
            """A job as the page may see it: hidden products' names masked while Hoard is locked."""
            return {**job, **app.public_job({k: job.get(k) for k in ("message", "log", "report", "label", "transfer") if k in job}, hidden)}
        tasks = {**tasks, "current": mask(tasks["current"]) if tasks["current"] else None,
                 "project": mask(tasks["project"]) if tasks["project"] else None,
                 "queue": [mask(q) for q in tasks["queue"]], "history": [mask(h) for h in tasks["history"]]}
    return self._json(tasks, compress=True)


def get_api_loading(self, path, body, query):
    """GET /api/loading. issue #200: how far reading what a page shows first has got, for its splash"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json(app.loading.view((app.parse_qs(u.query).get("part") or [""])[0]))


def get_api_status(self, path, body, query):
    """GET /api/status. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json({"job": app.public_job(srv.jobs.state, self._hidden_names()), "stores": srv.lib.snapshot()[1],
                       "project_job": app.public_job(srv.project_jobs.state, self._hidden_names()),
                       "routine": app.routine_record()["found"]})


def post_api_cancel(self, path, body, query):
    """POST /api/cancel. lane: projects for Projects' task"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json({"ok": srv.lane(body.get("lane")).cancel()})


def post_api_force_stop(self, path, body, query):
    """POST /api/force-stop. any task, now (Tasks: Force stop)"""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json({"ok": srv.lane(body.get("lane")).force_stop()})


def post_api_queue_remove(self, path, body, query):
    """POST /api/queue/remove. a job waiting its turn (issue #49); Projects' ids start with p"""
    srv = self.server
    u = app.urlparse(self.path)
    job_id = str(body.get("id") or "")[:20]
    return self._json({"ok": srv.lane(app.PROJECTS if job_id.startswith("p") else None).remove(job_id)})


def post_api_queue_clear(self, path, body, query):
    """POST /api/queue/clear. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    return self._json({"ok": True, "removed": sum(jobs.clear_queue() for jobs in srv.lanes())})


def post_api_tasks_clear(self, path, body, query):
    """POST /api/tasks/clear. Serve this endpoint through the shared HTTP boundary."""
    srv = self.server
    u = app.urlparse(self.path)
    for jobs in srv.lanes():
        jobs.clear_history()
    return self._json({"ok": True})


def post_api_background(self, path, body, query):
    """Pause, resume or stop a registered background reader without losing completed work."""
    key, action = body.get("id"), body.get("action")
    if not isinstance(key, str) or not isinstance(action, str):
        return self._json({"error": "Choose a background task and an action."}, 400)
    try:
        self.server.scheduler.action(key, action)
    except ValueError as error:
        return self._json({"error": str(error)}, 400)
    return self._json({"ok": True, "background": self.server.scheduler.snapshot()})


def post_api_picture_work(self, path, body, query):
    """Admit one canvas hashing step under the shared scheduler's foreground and pause rules."""
    done, total = body.get("done"), body.get("total")
    if type(done) is not int or type(total) is not int or not 0 <= done <= total <= 500:
        return self._json({"error": "Invalid picture progress."}, 400)
    allowed = self.server.scheduler.external_progress("picture-matching", "Matching pictures", done, total)
    return self._json({"ok": True, "allowed": allowed})


def post_api_routine_seen(self, path, body, query):
    """POST /api/routine/seen. issue #113: you've looked at what the routine check found"""
    srv = self.server
    u = app.urlparse(self.path)
    app.save_routine(found=None)
    return self._json({"ok": True})



METHODS = {'_queued': _queued}

ROUTES = [
    Route('POST', '/api/tasks/pictures', post_api_picture_work, changes=True, auth='key',
          request=(('done', 'number'), ('total', 'number')), response='object'),
    Route('POST', '/api/tasks/background', post_api_background, changes=True, auth='key',
          request=(('id', 'string'), ('action', 'string')), response='object'),
    Route('GET', '/api/tasks', get_api_tasks, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/loading', get_api_loading, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('GET', '/api/status', get_api_status, changes=False, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/cancel', post_api_cancel, changes=True, auth='key', image_key=False, max_body=1048576, request=(('lane', 'any'),), response='object'),
    Route('POST', '/api/force-stop', post_api_force_stop, changes=True, auth='key', image_key=False, max_body=1048576, request=(('lane', 'any'),), response='object'),
    Route('POST', '/api/queue/remove', post_api_queue_remove, changes=True, auth='key', image_key=False, max_body=1048576, request=(('id', 'string'),), response='object'),
    Route('POST', '/api/queue/clear', post_api_queue_clear, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/tasks/clear', post_api_tasks_clear, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
    Route('POST', '/api/routine/seen', post_api_routine_seen, changes=True, auth='key', image_key=False, max_body=1048576, request=(), response='object'),
]
