# Modules

**Status:** Stable

**Context:** API reference for all modules in the `agent0` package. Intended for engineers who need to understand the public interface of each module.

**Outcome:** After reading, you can look up the public API of any module and understand its exports.

Module-by-module reference for the `agent0` package. Each section covers the public API exposed via `__all__`.

---

## config

`from agent0.config import Config, load_config`

### `Config`

Frozen dataclass holding all configuration. Created once at startup, never mutated.

| Field | Type | Default |
|-------|------|---------|
| `github_token` | `str` | — |
| `anthropic_api_key` | `str` | — |
| `poll_interval` | `int` | `30` |
| `whitelisted_orgs` | `tuple[str, ...]` | `('vaquum',)` |
| `executor_timeout` | `int` | `1800` |
| `max_turns` | `int` | `100` |
| `log_level` | `str` | `'INFO'` |
| `data_dir` | `Path` | `Path('/data')` |
| `github_user` | `str` | `'zero-bang'` |
| `port` | `int` | `9999` |

**Properties:**
- `workspaces_dir -> Path` — `data_dir / 'workspaces'`
- `audit_dir -> Path` — `data_dir / 'audit'`

**Methods:**
- `log_redacted() -> str` — Config string with secrets masked

### `load_config() -> Config`

Reads environment variables, validates required secrets, returns `Config`. Exits with error if `GITHUB_TOKEN` or `ANTHROPIC_API_KEY` is missing.

---

## poller

`from agent0.poller import GitHubClient, Poller, RateLimited`

### `GitHubClient`

Async HTTP client for the GitHub REST API. Uses `httpx.AsyncClient` with bearer token auth.

| Method | Returns | Description |
|--------|---------|-------------|
| `get_authenticated_user()` | `dict` | `GET /user` |
| `get_notifications(since, if_modified_since)` | `tuple[list, str\|None]` | `GET /notifications` with conditional headers |
| `mark_notification_read(thread_id)` | `None` | `PATCH /notifications/threads/{id}` |
| `get_issue(owner, repo, number)` | `dict` | `GET /repos/{o}/{r}/issues/{n}` |
| `get_issue_comments(owner, repo, number)` | `list[dict]` | `GET /repos/{o}/{r}/issues/{n}/comments` |
| `get_pull_request(owner, repo, number)` | `dict` | `GET /repos/{o}/{r}/pulls/{n}` |
| `get_pull_request_diff(owner, repo, number)` | `str` | `GET /repos/{o}/{r}/pulls/{n}` with diff accept header |
| `get_pull_request_comments(owner, repo, number)` | `list[dict]` | `GET /repos/{o}/{r}/pulls/{n}/comments` |
| `get_comment(owner, repo, comment_id)` | `dict` | `GET /repos/{o}/{r}/issues/comments/{id}` |
| `get_check_suite(owner, repo, check_suite_id)` | `dict` | `GET /repos/{o}/{r}/check-suites/{id}` |
| `get_check_runs_for_suite(owner, repo, check_suite_id)` | `list[dict]` | `GET /repos/{o}/{r}/check-suites/{id}/check-runs` |
| `get_pull_requests_for_commit(owner, repo, sha)` | `list[dict]` | `GET /repos/{o}/{r}/commits/{sha}/pulls` |
| `search_open_prs_by_author(author, org)` | `list[dict]` | Search API for open PRs by author within an org |
| `search_merged_prs_reviewed_by(reviewer, org)` | `list[dict]` | Search API for merged PRs reviewed by user within an org |
| `get_check_suites_for_ref(owner, repo, ref)` | `list[dict]` | `GET /repos/{o}/{r}/commits/{ref}/check-suites` |
| `close()` | `None` | Close the HTTP client |

### `Poller`

Polls GitHub notifications with deduplication and context fetching.

| Method | Returns | Description |
|--------|---------|-------------|
| `poll()` | `list[dict]` | Fetch unread notifications, filter by org, deduplicate by timestamp |
| `mark_read(thread_id)` | `None` | Mark a notification as read |
| `fetch_context(notification)` | `dict` | Fetch full context (body, comments, diff) for a notification |
| `scan_ci_failures()` | `list[dict]` | Actively scan for CI failures on agent-authored open PRs |

### `RateLimited`

Exception raised when GitHub returns HTTP 429. Contains `retry_after` (int) seconds.

---

## router

`from agent0.router import TaskContext, should_process, classify`

### `TaskContext`

Dataclass carrying all context needed for execution.

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | `str` | `mention`, `assignment`, `review_request`, or `ci_failure` |
| `owner` | `str` | Repository owner |
| `repo` | `str` | Repository name |
| `number` | `int` | Issue or PR number |
| `subject_type` | `str` | `Issue` or `PullRequest` |
| `trigger_user` | `str` | GitHub user who triggered the notification |
| `trigger_text` | `str` | Text content that triggered the task |
| `issue_body` | `str \| None` | Issue or PR body |
| `diff` | `str \| None` | PR diff (only for PullRequests) |
| `comments` | `list[dict]` | Conversation history |
| `labels` | `list[str]` | Issue or PR labels |
| `head_ref` | `str \| None` | PR source branch |
| `base_ref` | `str \| None` | PR target branch |
| `notification_id` | `str` | GitHub notification thread ID |

### `should_process(notification, config) -> bool`

Returns `True` if the notification reason is actionable (`mention`, `assign`, `review_requested`, `ci_activity`, `author`).

### `classify(notification, context, config) -> TaskContext`

Builds a `TaskContext` from the raw notification and fetched context.

### Other Functions (not in `__all__` but used internally)

- `is_self_triggered(context, config) -> bool` — Checks if the actor matches the agent's username
- `format_comments(comments) -> str` — Formats comment list into markdown conversation thread

---

## executor

`from agent0.executor import ExecutorResult, run`

### `ExecutorResult`

Dataclass containing the outcome of a Claude Code session.

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `success`, `failure`, or `timeout` |
| `response` | `str \| None` | Claude's text response |
| `error` | `str \| None` | Error message |
| `input_tokens` | `int` | Input tokens consumed |
| `output_tokens` | `int` | Output tokens consumed |
| `cost_usd` | `float` | Estimated cost |
| `num_turns` | `int` | Agentic turns taken |
| `duration_seconds` | `float` | Wall clock time |
| `raw_output` | `str` | Full raw stdout |

### `run(context, workspace_path, config, output_lines) -> ExecutorResult`

Spawns Claude Code CLI as a subprocess with PTY stdout. Builds the prompt from context, streams output to `output_lines` buffer, parses the final result.

---

## daemon

`from agent0.daemon import Scheduler, Daemon`

### `Scheduler`

Per-repo task scheduling with concurrency control.

| Method | Returns | Description |
|--------|---------|-------------|
| `set_poller(poller)` | `None` | Set poller reference for marking notifications read |
| `submit(context)` | `asyncio.Task` | Submit a task for execution |
| `get_running()` | `list[dict]` | Running tasks for dashboard |
| `get_queued()` | `list[dict]` | Queued tasks for dashboard |
| `get_executor_output(repo_key, after)` | `dict` | Live output buffer for dashboard |

### `Daemon`

Main daemon lifecycle: startup, poll loop, shutdown.

| Method | Returns | Description |
|--------|---------|-------------|
| `start()` | `None` | Run startup checks, create data directories |
| `poll_loop()` | `None` | Main polling loop with CI scanning every 5th cycle |
| `shutdown()` | `None` | Stop loop, wait for tasks, close client |

**Property:** `scheduler -> Scheduler`

---

## workspace

`from agent0.workspace import WorkspaceManager`

### `WorkspaceManager`

Manages local git clones on persistent disk.

| Method | Returns | Description |
|--------|---------|-------------|
| `prepare(owner, repo)` | `Path` | Clone or update repo, return workspace path |
| `cleanup_stale(max_age_days)` | `list[str]` | Remove workspaces not accessed recently |

---

## reflector

`from agent0.reflector import REFLECTION_INTERVAL, REFLECTION_SCAN_INTERVAL, Reflector`

### `Reflector`

Self-reflection engine that triggers post-mortem learning on merged PRs. Queries GitHub Search API, counts new merged PRs, and fires a two-phase reflection every `REFLECTION_INTERVAL` (6) merged PRs.

| Method | Returns | Description |
|--------|---------|-------------|
| `scan()` | `None` | Query GitHub for merged PRs, trigger reflection if threshold met |

### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `REFLECTION_SCAN_INTERVAL` | `20` | Polls between scans (~10 min) |
| `REFLECTION_INTERVAL` | `6` | New merged PRs needed to trigger |

See [Reflector](Reflector.md) for full architecture details.

---

## audit

`from agent0.audit import AuditEntry, log_entry, read_history, read_entry_output`

### `AuditEntry`

Dataclass for a completed task audit record. Fields match the JSONL schema.

### `log_entry(entry, config) -> None`

Append an audit entry to the daily JSONL file. Async (offloads I/O to thread).

### `read_history(config, page, per_page) -> list[AuditEntry]`

Read paginated audit history, newest first. Scans daily files in reverse date order.

### `read_entry_output(config, notification_id) -> list[str] | None`

Find and return executor output lines for a specific notification ID.

---

## logbuffer

`from agent0.logbuffer import LogBuffer`

### `LogBuffer`

`logging.Handler` subclass that maintains an in-memory ring buffer of recent log records.

| Method | Returns | Description |
|--------|---------|-------------|
| `emit(record)` | `None` | Append formatted record to buffer |
| `get_entries(after, level)` | `dict` | Entries newer than cursor, filtered by minimum level |

Default capacity: 1000 entries. Thread-safe via `threading.Lock`.

---

## api

`from agent0.api import create_app`

### `create_app(daemon, config, log_buffer) -> FastAPI`

Creates and returns the FastAPI application with all routes and static file serving. See [Dashboard](Dashboard.md) for endpoint details.
