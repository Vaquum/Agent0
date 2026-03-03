# Daemon Specification

## 1. Overview

The daemon is the long-running process that keeps Agent0 alive. It manages the poll loop,
coordinates concurrent tasks, handles errors gracefully, and ensures clean startup and
shutdown.

## 2. Entry Point

`src/agent0/main.py` is the entry point. It:

1. Loads configuration from environment variables
2. Runs startup checks
3. Enters the main loop
4. Handles shutdown on SIGTERM/SIGINT

```
python -m agent0
```

This is what Render's Web Service executes.

## 3. Startup Sequence

On startup, the daemon runs these checks in order. If any fail, it logs the error and
exits with a non-zero code (Render will restart it).

1. **Load config** — read all environment variables, validate required ones are set
2. **Verify GitHub auth** — call `GET /user` with the token, confirm the response is
   `zero-bang`. If not, fail.
3. **Verify Claude Code** — run `claude --version`, confirm it exits 0. Then run a
   trivial `claude --print -p "respond with ok"` to confirm the API key works.
4. **Verify gh CLI** — run `gh auth status`, confirm it exits 0.
5. **Initialize data directories** — ensure `/data/workspaces/` and `/data/audit/` exist.
6. **Log startup** — log the daemon version, config values (redacted secrets), timestamp.
7. **Start dashboard** — start the `FastAPI` web server on port 8000.
8. **Enter main loop**.

## 4. Main Loop

The main loop is a single `asyncio` event loop running in the main thread.

```
while running:
    notifications = poller.poll()
    for notification in notifications:
        if router.should_process(notification):
            task = router.classify(notification)
            scheduler.submit(task)
    await asyncio.sleep(poll_interval)
```

### 4.1 Loop Mechanics

- The loop runs every `POLL_INTERVAL` seconds (default: 30).
- `poller.poll()` is a synchronous HTTP call (fast, <1 second).
- `router.classify()` is pure logic, no I/O.
- `scheduler.submit()` hands the task off for execution — does not block the loop.
- The loop itself is never blocked by task execution.

### 4.2 Scheduler

The scheduler manages concurrent task execution with per-repo locking. It also exposes
its state for the dashboard to read.

- Maintains a dict of `repo -> asyncio.Lock`
- Maintains a dict of `repo -> Task` for running tasks (dashboard: "running")
- Maintains a dict of `repo -> list[Task]` for queued tasks (dashboard: "queued")
- When a task is submitted:
  - If no lock exists for that repo, create one
  - Add to the queued list for that repo
  - Acquire the lock (or wait if another task for that repo is running)
  - Move from queued to running
  - Run the task (workspace setup + Claude Code execution) in an asyncio task
  - Remove from running when done
  - Release the lock
- Tasks for different repos run in parallel with no limit (bounded naturally by
  notification volume)

### 4.3 Task Execution Flow

Each task, once scheduled:

1. **Workspace setup** — clone or update the repo via `workspace.prepare()`
2. **Prompt construction** — build the Claude Code prompt from the event context
3. **Execution** — spawn `claude` CLI subprocess via `executor.run()`
4. **Audit** — log the result via `audit.log()`
5. **Mark notification read** — via `poller.mark_read()`

If any step fails, the error is logged in the audit trail and the notification is still
marked as read (to prevent infinite retry loops on permanently failing notifications).

## 5. Shutdown

On receiving SIGTERM or SIGINT:

1. Set `running = False` — the main loop exits after the current sleep.
2. Stop the `FastAPI` web server.
3. Wait for all in-progress tasks to complete (up to 60 seconds grace period).
4. If tasks are still running after grace period, send SIGTERM to their Claude Code
   subprocesses, wait 10 seconds, then SIGKILL.
5. Flush audit logs.
6. Exit 0.

Render sends SIGTERM before stopping a worker and allows a grace period before SIGKILL.

## 6. Error Handling

### 6.1 Poll Failures

If `poller.poll()` raises an exception (network error, GitHub API down, rate limit):

- Log the error at WARNING level
- Continue the loop — next iteration will retry
- If GitHub returns 429 (rate limited), respect the `Retry-After` header and sleep
  that long instead of the normal interval

### 6.2 Task Failures

If a task fails at any stage:

- Log the error at ERROR level in the audit trail
- Mark the notification as read (prevent retry loop)
- Do not crash the daemon — continue processing other notifications
- Include the full traceback in the audit entry

### 6.3 Claude Code Subprocess Failures

If the `claude` CLI subprocess:

- **Exits non-zero**: Log stderr, record as failed in audit
- **Times out**: Kill the process, log as timeout in audit
- **Produces invalid JSON**: Log raw output, record as failed in audit

### 6.4 Crash Recovery

If the daemon process crashes entirely:

- Render restarts it automatically
- On restart, the startup sequence runs again
- No state is lost — notifications not yet marked as read will be re-polled
- Audit logs are on persistent disk and survive restarts
- In-progress git operations may leave dirty workspaces — the workspace manager
  resets to the default branch on `prepare()`, which cleans this up

## 7. Logging

Uses Python's `logging` module with structured output.

- **Format**: `%(asctime)s %(levelname)s %(name)s %(message)s`
- **Level**: Configurable via `LOG_LEVEL` env var (default: `INFO`)
- **Output**: stdout (Render captures this in its log viewer)
- **Components**: Each module uses its own logger (`agent0.poller`, `agent0.router`, etc.)

What gets logged at each level:

| Level | Examples |
|---|---|
| DEBUG | Raw notification payloads, full prompts sent to Claude Code |
| INFO | Poll results ("3 new notifications"), task starts/completions, startup/shutdown |
| WARNING | Poll failures, rate limits, task queue waits |
| ERROR | Task failures, subprocess crashes, invalid responses |

## 8. Dashboard

The dashboard consists of a FastAPI backend (JSON API) and a TypeScript + Vite frontend
(SPA). Both run within the same process — FastAPI serves the API and the built static
files.

### API Routes

| Route | Description |
|---|---|
| `GET /health` | Returns 200 with `{"status": "ok"}`. Used by Render health checks. |
| `GET /api/tasks/running` | Returns running tasks from in-memory scheduler state. |
| `GET /api/tasks/queued` | Returns queued tasks from in-memory scheduler state. |
| `GET /api/tasks/history?page=1&per_page=50` | Returns past tasks from audit logs, paginated, newest first. |
| `GET /` | Serves the Vite-built SPA (`index.html`). |
| `GET /{path}` | Serves static frontend assets (JS, CSS). |

### Frontend

The frontend is a TypeScript SPA built with Vite. It polls the API every 10 seconds
and renders three sections:

**Running tasks** section shows:
- Repository (owner/repo)
- Event type (mention, assignment, review request)
- Trigger (who triggered, brief summary)
- Started at (UTC timestamp)
- Elapsed time

**Queued tasks** section shows:
- Repository (owner/repo)
- Event type
- Trigger
- Queued at (UTC timestamp)
- Position in queue

**Past tasks** section shows (paginated, 50 per page, newest first):
- Timestamp (UTC)
- Repository (owner/repo)
- Event type
- Trigger
- Action taken
- Status (success / failure / timeout)
- Duration
- Token usage (input + output + total)
- Cost estimate

## 9. Process Model

Single process, single event loop, multiple concurrent asyncio tasks.

- No multiprocessing — subprocess spawning for Claude Code is sufficient
- No threading — asyncio handles concurrency for I/O-bound work
- Claude Code subprocesses are the actual workhorses — they run in separate OS processes
- FastAPI + uvicorn runs in the same event loop — lightweight, no extra processes
- The daemon itself is lightweight — its job is coordination, not computation
