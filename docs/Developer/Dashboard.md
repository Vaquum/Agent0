# Dashboard

**Status:** Stable

**Context:** Dashboard architecture and API surface. Intended for engineers working on the frontend or API layer.

**Outcome:** After reading, you can modify the dashboard UI, extend the API, or debug live-streaming issues.

The dashboard is a single-page application that provides real-time visibility into Agent0's operations. It shows running tasks, queued tasks, execution history, and live logs.

## Frontend Stack

- **TypeScript** — Vanilla TS with direct DOM manipulation, no framework
- **Vite** — Build tool, outputs to `frontend/dist/`
- **CSS** — Single `style.css`, dark theme

The frontend build is served as static files by FastAPI via `StaticFiles(directory='frontend/dist', html=True)`.

## Layout

The dashboard has a two-panel layout with a draggable divider:

```
┌─────────────────────────────────────────────────┐
│                    Header                        │
├──────────────────────┬──┬───────────────────────┤
│   Running Tasks      │  │                       │
│   Queued Tasks       │  │   Log / Executor /    │
│   History            │  │   History Output      │
│                      │  │                       │
│   [pagination]       │  │                       │
├──────────────────────┴──┴───────────────────────┤
│                    Footer                        │
└─────────────────────────────────────────────────┘
```

**Left panel** — Three sections stacked vertically: running tasks, queued tasks, and history. Each renders as a table.

**Right panel** — Has three view modes controlled by user interaction:
- **Log** (default) — Live daemon log stream with level filter
- **Executor** — Live output from a running task (click a running task row)
- **History** — Saved output from a completed task (click a history row)

The divider position is persisted in `localStorage` under `agent0-split-ratio`.

## View Modes

### Log Mode

The default view. Polls `GET /api/logs` every 2 seconds with cursor-based pagination (`after` parameter). Each response returns new entries since the last cursor. The log level dropdown filters by minimum severity (DEBUG, INFO, WARNING, ERROR).

Auto-scroll keeps the view pinned to the bottom unless the user manually scrolls up. Maximum 1000 lines are retained in the DOM.

### Executor Mode

Activated by clicking a running task row. Polls `GET /api/tasks/running/{repo_key}/output` every 2 seconds. Shows live Claude Code output as the agent works — tool calls, text responses, and the final result.

If the task finishes (disappears from running tasks), the view automatically switches back to log mode.

### History Mode

Activated by clicking a history row. Makes a single `GET /api/tasks/history/{notification_id}/output` request. Shows the saved executor output from a completed task. No polling — history output is static.

## Polling Intervals

| Endpoint | Interval | Purpose |
|----------|----------|---------|
| `/api/tasks/running` | 10s | Running task list |
| `/api/tasks/queued` | 10s | Queued task list |
| `/api/tasks/history` | 10s | History table |
| `/api/logs` or executor output | 2s | Live streaming content |
| Elapsed time ticker | 1s | Updates elapsed time on running tasks client-side |

Tasks, queued, and history are fetched together in a single `Promise.all()` call.

## API Endpoints

### `GET /health`

Returns `{"status": "ok"}`. Used by Render health checks.

### `GET /api/tasks/running`

Returns an array of running tasks:

```json
[{
  "repo": "owner/repo",
  "event_type": "mention",
  "number": 42,
  "trigger_user": "someuser",
  "trigger_text": "First 100 chars...",
  "started_at": "2024-01-15T10:30:00+00:00",
  "elapsed_seconds": 45.2
}]
```

### `GET /api/tasks/queued`

Returns an array of queued tasks with their position in the queue.

### `GET /api/tasks/history?page=1&per_page=50`

Returns paginated audit entries, newest first. Each entry includes timestamp, event type, repo, status, tokens, cost, and duration.

### `GET /api/tasks/history/{notification_id}/output`

Returns saved executor output lines for a completed task:

```json
{
  "entries": [
    {"id": 1, "text": "> Read: src/main.py"},
    {"id": 2, "text": "Looking at the code..."},
    {"id": 3, "text": "> Edit: src/main.py"},
    {"id": 4, "text": "Done (12 turns, $0.0450)"}
  ]
}
```

### `GET /api/tasks/running/{repo_key}/output?after=0`

Returns live executor output lines with cursor-based pagination. The `after` parameter filters to entries with ID strictly greater than the given value. The response includes `last_id` for the next poll.

### `GET /api/logs?after=0&level=INFO`

Returns log entries from the in-memory ring buffer. Same cursor-based pattern as executor output. The `level` parameter sets the minimum severity.

## TypeScript Types

The frontend defines TypeScript interfaces that mirror the API responses:

- `RunningTask` — Running task metadata
- `QueuedTask` — Queued task metadata
- `HistoryEntry` — Audit entry with all fields
- `LogEntry` — Single log record (id, timestamp, level, logger, message)
- `LogResponse` — Log entries with cursor
- `ExecutorOutputEntry` — Single output line (id, text)
- `ExecutorOutputResponse` — Output entries with cursor

All API calls use `fetch()` with error throwing on non-2xx status codes.
