# Background work

`hoard/scheduler.py` owns task workers and the clock deciding when to run them.
`AppServer` owns one scheduler and closes it with the server. The existing main
and Projects queues keep their independent foreground lanes, but launch through
that owner. Jobs created on their own (for command-line services and tests) use
an explicitly nonpersistent scheduler.

Priority is user work, routine checks, general maintenance, then package
reading. Only one maintenance callback runs at a time. Foreground work may
start alongside it; maintenance yields at its next checkpoint. Package parsing
checks between archive members, and network readers check at progress and wait
boundaries. A single blocking system or network call cannot be interrupted by
a Python checkpoint; its existing timeout and Force stop remain in effect.
Shutdown wakes paused workers and waits up to ten seconds for owned threads.
A callback stuck in an external blocking call can outlive that bound; it must
reach a checkpoint or its transport timeout before returning. Scheduler state
is not written after closure.

The scheduler owns the routine timer, Hoard update checks, package reading,
catalog maintenance, imported-picture caching, share-link cleanup and each
job's watchdog. Short timers opening/closing a native window, HTTP request
threads, notification transports and subprocess pipe readers are transport or
window plumbing, not independent maintenance schedules.

Picture comparison stays in the renderer because it uses the browser's canvas
decoder. Before each image, the renderer obtains permission from the same
scheduler. A user task, Pause or Stop prevents the next comparison. Completed
hashes are saved in batches of 32; unfinished comparisons are requested by the
next view refresh. Resume refreshes the current view. This uses no separate
background timer and persists neither image URLs nor access tokens.

## Progress and restart

The private SQLite document `scheduler.json` contains registered durable task
keys, next due times, pause/stop state, progress and cursors. Code supplies the
callbacks at startup; nothing executable is read from disk. A saved key with no
registered callback cannot run. Transient maintenance, such as rebuilding an
export, is reconstructible and is not replayed as an arbitrary saved callable.

The package reader saves each completed package in `package-needs.json` before
publishing progress. After a restart it compares size and modification time
and reads only changed or unfinished packages. An interrupted package is read
again; packages completed before it are retained. Pause and Stop preserve this
index. Tasks shows completed/total packages and Resume, Pause and Stop controls.

`job-queue.json` retains waiting user intents separately for the main and
Projects lanes. They are restored in order and started only after the server's
services are ready. Only intents that read, download or add are restored (`jobs.RESUMED`, and the Projects ops in
`RESUMED_PROJECT`): one that deletes or takes out, signs in or out, moves the library or changes a project was
confirmed in the earlier run, so it is recorded in Tasks as stopped ("Not started again...") instead of run. A foreground operation already running at process death is
not blindly replayed: its existing download records or project recovery files
remain authoritative, and the user can retry it. Background cursors and queued
intents do not bypass the normal request validation or file safety boundaries.

Only display fields reach `/api/tasks`; private cursors and arguments do not.
The new `/api/tasks/background` and `/api/tasks/pictures` actions require the
same local access key and POST boundary as other changing API calls. Detailed
exceptions go to diagnostics; the background status uses a fixed message that
cannot expose a hidden product's filename.

`test_scheduler.py` checks priority, Pause/Stop, owned shutdown, durable queue
order and the real package reader across a restart. API and browser tests cover
the Tasks controls, and the existing job, desktop and updater tests exercise
the migrated worker paths.
