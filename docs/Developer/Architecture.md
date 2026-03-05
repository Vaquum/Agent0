# Architecture

## System Layers

Agent0 has four layers, each with a single responsibility:

```
┌────────────────────────────────────────────┐
│              Dashboard (TypeScript)         │  ← browser
├────────────────────────────────────────────┤
│              API (FastAPI)                  │  ← HTTP
├────────────────────────────────────────────┤
│              Daemon (Scheduler + Poll Loop) │  ← orchestration
├────────┬───────────┬───────────┬───────────┤
│ Poller │  Router   │ Executor  │ Workspace  │  ← domain
└────────┴───────────┴───────────┴───────────┘
         │                       │
    GitHub API              Claude Code CLI
```

**Dashboard** — TypeScript + Vite SPA. Polls API endpoints for running tasks, history, and live logs. No framework — vanilla TS with direct DOM manipulation.

**API** — FastAPI application serving REST endpoints and the static frontend build. Created by `api.create_app()` and served by Uvicorn.

**Daemon** — Two responsibilities. The `Daemon` class runs the poll loop and manages lifecycle (start, shutdown). The `Scheduler` class enforces per-repo concurrency and tracks running/queued state.

**Domain modules** — `Poller` fetches notifications from GitHub. `Router` classifies them into task contexts. `Executor` spawns Claude Code CLI. `WorkspaceManager` keeps local git clones fresh.

## Data Flow

```
GitHub Notification API                    GitHub Search API
        │                                         │
        ▼                                         ▼
    Poller.poll()                     Poller.scan_ci_failures()
    Filter by org, deduplicate        Search agent's open PRs,
        │                             check suites for failures
        ▼                                         │
    should_process()                               │
    Filter by notification reason                  │
        │                                         │
        ▼                                         ▼
    Poller.fetch_context() ◄──────────────────────┘
    Fetch issue/PR body, comments, diff
        │
        ▼
    is_self_triggered()   Skip if agent triggered (except CI)
        │
        ▼
    classify()            Build TaskContext dataclass
        │
        ▼
    Scheduler.submit()    Acquire per-repo lock, create asyncio task
        │
        ▼
    executor.run()        Spawn Claude Code CLI with PTY
        │
        ├──→ GitHub (via gh CLI)   Claude Code pushes, comments, creates PRs
        │
        ▼
    audit.log_entry()     Persist result to daily JSONL file
```

The left path handles human-triggered notifications (mentions, assignments, reviews). The right path handles CI failures on agent-authored PRs via active scanning every 5th poll cycle. Both paths converge at `fetch_context()` and follow the same execution pipeline.

## Concurrency Model

Agent0 processes **one task per repository at a time**. Different repositories run in parallel. This is enforced by `asyncio.Lock` instances keyed by `owner/repo` in the Scheduler.

When multiple notifications arrive for the same repo, they queue up. The Scheduler maintains both `_running` and `_queued` dictionaries, exposed to the dashboard API for visibility.

The poll loop and web server run concurrently via `asyncio.gather()` in the main entry point. Signal handlers (SIGTERM, SIGINT) set a shutdown event that gracefully stops the poll loop and waits up to 60 seconds for running tasks to finish.

## Persistent State

All persistent state lives under `DATA_DIR` (default `/data`):

```
/data/
├── workspaces/
│   └── {owner}/
│       └── {repo}/        # Full git clone
└── audit/
    └── YYYY-MM-DD.jsonl   # One audit file per day
```

Workspaces are git clones managed by `WorkspaceManager`. On each task, the workspace is fetched and reset to the default branch head. Stale workspaces (not accessed in 7 days) can be cleaned up.

Audit files are append-only JSONL. Each entry records the notification, event type, executor result, tokens, cost, and duration. History output (the formatted executor stdout) is stored inline in the audit entry.

## In-Memory State

- `Scheduler._running` — Currently executing tasks, keyed by repo
- `Scheduler._queued` — Waiting tasks, keyed by repo
- `Scheduler._output_buffers` — Live executor stdout lines for dashboard streaming
- `Poller._processed_timestamps` — Maps notification ID → updated_at for deduplication
- `Poller._last_modified` — HTTP `Last-Modified` header for conditional polling
- `Poller._ci_checked` — Maps `owner/repo#number` → head SHA for CI scan deduplication
- `LogBuffer._buffer` — Ring buffer of recent log records (default 1000)

All in-memory state is rebuilt naturally on restart. The only durable state is workspaces and audit files.

## Design Decisions

**Why poll instead of webhooks?** Agent0 runs on Render behind HTTPS. GitHub webhooks require a public endpoint with signature verification, secret rotation, and replay protection. Polling the notifications API is simpler, stateless, and works identically in development and production.

**Why one task per repo?** Claude Code CLI operates on a local git checkout. Concurrent tasks on the same repo would cause conflicts (branch switching, file edits, git state). The per-repo lock eliminates this class of problems entirely.

**Why PTY for subprocess stdout?** Node.js (which Claude Code runs on) detects when stdout is a pipe and switches to full buffering (~64KB chunks). This makes live streaming impossible. A PTY makes Node.js think it is writing to a terminal, which forces line buffering — each line arrives as soon as it is written.

**Why JSONL for audit?** Append-only writes are fast and crash-safe. No database dependency. Easy to grep, tail, and process with standard tools. Daily file rotation keeps individual files manageable.

**Why frozen Config dataclass?** Configuration is loaded once at startup from environment variables and never mutated. A frozen dataclass enforces this at the type level and prevents accidental modification.
