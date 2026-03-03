# Architecture Specification

## 1. Overview

Agent0 is a daemon that operates as an autonomous software engineer on GitHub. It runs
continuously, monitors its GitHub notification inbox, and responds to events across
whitelisted organizations. It uses Claude Code CLI as its brain, giving it the full
capability of a human engineer using Claude Code — reading code, editing files, running
commands, making commits, and interacting with GitHub.

### Identity

- GitHub user: `zero-bang`
- Acts under this identity for all GitHub interactions (comments, commits, reviews, PRs)

### Whitelisted Organizations

- `mikkokotila`
- `vaquum`

Notifications from any other org or user namespace are ignored.

## 2. System Architecture

```
┌─ Render Web Service (Frankfurt) ────────────────────────────────┐
│                                                                  │
│   ┌──────────┐    ┌──────────┐    ┌──────────────┐              │
│   │  Poller  │───▶│  Router  │───▶│  Workspace   │              │
│   │          │    │          │    │  Manager     │              │
│   └──────────┘    └──────────┘    └──────┬───────┘              │
│                                          │                       │
│                                   ┌──────▼───────┐              │
│                                   │   Executor   │              │
│                                   │ (claude CLI) │              │
│                                   └──────┬───────┘              │
│                                          │                       │
│                                   ┌──────▼───────┐              │
│                                   │    Audit     │              │
│                                   │    Logger    │              │
│                                   └──────────────┘              │
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐                          │
│   │   FastAPI    │    │  Dashboard   │                          │
│   │   (API)      │    │  (Vite+TS)   │                          │
│   │   :8000      │    │  static SPA  │                          │
│   └──────────────┘    └──────────────┘                          │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                  Persistent Disk                          │  │
│   │  /data/workspaces/   — cloned repos                      │  │
│   │  /data/audit/        — audit logs                        │  │
│   └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## 3. Components

### 3.1 Poller

Polls the GitHub Notifications API (`GET /notifications`) on a fixed interval.

- **Interval**: 30 seconds
- **Auth**: GitHub Personal Access Token (PAT) for `zero-bang`
- **Filtering**: Only processes notifications from whitelisted orgs
- **Self-filtering**: Ignores notifications triggered by `zero-bang` itself (loop prevention)
- **Mark as read**: After a notification is picked up and routed, mark it as read to prevent reprocessing
- **Deduplication**: Track processed notification IDs to handle edge cases

### 3.2 Router

Classifies each notification and determines the action type.

| GitHub Event | Action |
|---|---|
| Mentioned in issue/PR comment (`@zero-bang ...`) | Parse the text after the mention, execute the request |
| Assigned to issue | Read the issue, assess what's needed, act on it |
| Review requested on PR | Check out the PR, review the code, submit review |
| Assigned to PR | Same as review requested |

The router extracts:
- **Event type**: mention, assignment, review request
- **Repository**: owner/repo
- **Reference**: issue number, PR number, or comment URL
- **Context**: the text/body that triggered the notification

### 3.3 Workspace Manager

Manages local clones of repositories on the persistent disk.

- **Clone**: If the repo is not yet cloned, clone it to `/data/workspaces/{owner}/{repo}`
- **Update**: If already cloned, fetch and reset to the default branch
- **Branch**: For tasks that require commits, create a working branch
- **Cleanup**: Remove stale workspaces not accessed in 7+ days
- **Concurrency**: One task per repo at a time (avoids conflicting edits). If a task is
  already in progress for a repo, queue the new task. Different repos can be worked on
  in parallel — the daemon can have multiple Claude Code sessions running simultaneously
  across different repos.

### 3.4 Executor

Spawns Claude Code CLI as a subprocess pointed at the relevant workspace.

- **Invocation**: `claude --print --output-format json` with the prompt via stdin
- **Working directory**: Set to the repo workspace
- **Prompt construction**: Assembles a prompt from the event context — includes the issue
  body, PR diff, conversation history, and a system instruction describing what action
  to take
- **Tools available to Claude Code**: Full tool set — file read/write, bash, git, gh CLI
- **Timeout**: Maximum 10 minutes per task (configurable)
- **Output capture**: Capture full stdout/stderr for audit

The prompt given to Claude Code includes:
1. A system instruction explaining it is `zero-bang`, an engineer working on this repo
2. The GitHub context (issue body, PR details, conversation thread)
3. The specific task (respond to the mention, review the PR, implement the ticket, etc.)
4. Constraints (org whitelist, no force pushes, no merges without approval)

### 3.5 Dashboard

The dashboard is split into a FastAPI backend (JSON API) and a TypeScript + Vite frontend
(SPA served as static files).

**API layer (FastAPI)**:
- `GET /health` — returns 200, used by Render health checks
- `GET /api/tasks/running` — current running tasks from in-memory scheduler state
- `GET /api/tasks/queued` — queued tasks from in-memory scheduler state
- `GET /api/tasks/history` — past tasks from audit log files, paginated, newest first
- Runs on port 8000 within the same asyncio event loop as the daemon

**Frontend (TypeScript + Vite)**:
- Single-page application built with Vite
- Polls the API endpoints to display live state
- Built at Docker build time, served as static files by FastAPI
- No JavaScript framework — vanilla TypeScript
- **No authentication**: The Render service URL is not publicly discoverable, but if
  auth is needed later it can be added.

### 3.6 Audit Logger

Records every action with full traceability.

Each audit entry contains:
- **Timestamp** (UTC)
- **Notification ID**
- **Event type** (mention, assignment, review request)
- **Repository** (owner/repo)
- **Reference** (issue/PR number)
- **Trigger** (who triggered it, what they said)
- **Action taken** (what Claude Code did — comment, commit, review, etc.)
- **Claude Code output** (full response)
- **Token usage** (input tokens, output tokens, total tokens, cost estimate)
- **Duration** (wall clock time for the executor)
- **Status** (success, failure, timeout)

Storage: JSON lines (`.jsonl`) files on persistent disk at `/data/audit/`.
One file per day: `/data/audit/2026-02-28.jsonl`.

## 4. Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| HTTP client | `httpx` (async-capable, modern) |
| GitHub API | `httpx` directly against REST API (no wrapper library — keeps it simple and explicit) |
| API server | `fastapi` + `uvicorn` |
| Frontend | TypeScript + Vite (SPA, vanilla TS) |
| CLI subprocess | `asyncio.create_subprocess_exec` (standard library) |
| Configuration | Environment variables |
| Logging | `logging` (standard library) |
| Deployment | Render Web Service |
| Infra-as-code | `render.yaml` (Render Blueprint) |
| Container | Dockerfile (Python + Node.js for Claude Code CLI + gh CLI) |

## 5. Configuration (Environment Variables)

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | PAT for `zero-bang` with `repo`, `notifications` scopes |
| `ANTHROPIC_API_KEY` | API key for Claude Code |
| `POLL_INTERVAL` | Seconds between polls (default: 30) |
| `WHITELISTED_ORGS` | Comma-separated list (default: `mikkokotila,vaquum`) |
| `EXECUTOR_TIMEOUT` | Max seconds per Claude Code session (default: 600) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |
| `DATA_DIR` | Root for persistent data (default: `/data`) |

## 6. Project Structure

```
Agent0/
├── render.yaml                 # Render Blueprint
├── Dockerfile                  # Container definition
├── pyproject.toml              # Python project config
├── spec/                       # Specifications
│   ├── architecture.md         # This document
│   ├── daemon.md               # Daemon lifecycle
│   ├── github-integration.md   # GitHub API interactions
│   ├── executor.md             # Claude Code executor
│   ├── actions.md              # Action types
│   └── security.md             # Security model
├── src/
│   └── agent0/
│       ├── __init__.py
│       ├── main.py             # Entry point
│       ├── daemon.py           # Main polling loop
│       ├── poller.py           # GitHub notification polling
│       ├── router.py           # Event classification
│       ├── workspace.py        # Repo clone/pull management
│       ├── executor.py         # Claude Code CLI spawning
│       ├── audit.py            # Audit trail logging
│       ├── api.py              # FastAPI app + routes
│       └── config.py           # Configuration from env
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.ts             # Entry point
│       ├── api.ts              # API client
│       └── style.css           # Styles
└── tests/
    ├── __init__.py
    ├── test_poller.py
    ├── test_router.py
    ├── test_workspace.py
    ├── test_executor.py
    └── test_audit.py
```

## 7. Deployment

### Render Blueprint (`render.yaml`)

- **Service type**: Web Service
- **Region**: Frankfurt (`fra`)
- **Auto-deploy**: Yes (from `main` branch)
- **Persistent disk**: 10 GB mounted at `/data`
- **Build**: Docker
- **Port**: 8000
- **Health check**: `GET /health`

### Dockerfile

The container must include:
- Python 3.12+
- Node.js 20+ (required for Claude Code CLI)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- GitHub CLI (`gh`)
- Git

### Health & Lifecycle

- The daemon runs as a single process
- On crash, Render restarts the worker automatically
- Graceful shutdown on SIGTERM (finish current task, then exit)
- Startup: verify GitHub auth, verify Claude Code auth, then enter poll loop

## 8. Constraints

- Never force push
- Never merge PRs (only review and approve/request changes)
- Never act outside whitelisted orgs
- Never process notifications triggered by `zero-bang` itself
- One Claude Code session per repo at a time (no parallel edits to same repo)
- Multiple repos can be worked on in parallel
- All GitHub interactions must be traceable in the audit log
