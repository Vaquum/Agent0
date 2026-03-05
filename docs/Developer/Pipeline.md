# Pipeline

This document traces the full lifecycle of a GitHub notification from arrival to executed task.

## Overview

```
GitHub API  →  Poller  →  Router  →  Scheduler  →  Executor  →  GitHub
                                                        │
                                                    Audit Trail
```

## Step 1: Polling

`Poller.poll()` calls `GET /notifications?participating=true&all=false` on the GitHub API.

**Conditional requests:** The poller sends an `If-Modified-Since` header with the `Last-Modified` value from the previous response. GitHub returns `304 Not Modified` when nothing has changed, saving API quota. Every 10th poll resets this cache to avoid getting stuck on stale 304s.

**Deduplication:** Each notification has an `id` and an `updated_at` timestamp. The poller tracks `{id: updated_at}` in memory. A notification is only processed if its `updated_at` differs from the stored value. This allows multi-round PR reviews — each new review updates the timestamp, triggering reprocessing.

**Org filtering:** Only notifications from repos owned by `WHITELISTED_ORGS` are passed through. Others are silently dropped.

**Memory cap:** The processed timestamps dict is capped at 500 entries. When exceeded, it prunes to the 200 most recent by timestamp.

## Step 2: Reason Filtering

`router.should_process()` checks the notification `reason` field:

| Reason | Passes filter | Meaning |
|--------|:---:|---------|
| `mention` | ✓ | Someone @mentioned the agent |
| `assign` | ✓ | Agent was assigned to an issue |
| `review_requested` | ✓ | Someone requested the agent's review |
| `ci_activity` | ✓ | CI checks completed on a thread the agent participates in |
| `author` | ✓ | Activity on something the agent authored (e.g., review on agent's PR) |
| `subscribed` | ✗ | Watching the repo — not actionable |
| `comment` | ✓ | New comment in a thread involving the agent |

## Step 3: Context Fetching

`Poller.fetch_context()` fetches the full context needed to understand the notification:

**For Issues:**
- Issue body, title, labels
- All issue comments
- Actor (last commenter)

**For Pull Requests:**
- PR body, title, labels, head/base refs
- PR diff (truncated at 100,000 characters)
- Issue comments + PR review comments (merged)
- Actor (last commenter)

**For CheckSuites (CI failures):**
1. Fetch the check suite by ID → verify `conclusion == 'failure'` (skip otherwise)
2. Find the commit SHA → look up associated open PRs
3. Find the PR authored by the agent (skip if none found)
4. Fetch PR details, diff, comments (same as PullRequest above)
5. Fetch failed check runs → format failure summaries (truncated at 50,000 characters)

## Step 4: Self-Trigger Check

When the agent pushes code or leaves comments, GitHub generates notifications for that activity. `router.is_self_triggered()` detects when the actor matches `GITHUB_USER` and skips the notification.

**Exception:** CI failures (`reason == 'ci_activity'`) bypass this check. Even though the agent triggered the CI run by pushing, a failing check still needs to be fixed.

## Step 5: Classification

`router.classify()` builds a `TaskContext` dataclass from the notification and fetched context:

| Notification reason | Event type | Prompt template used |
|-------------------|-----------|---------------------|
| `mention` | `mention` | `_MENTION_ISSUE` or `_MENTION_PR` |
| `assign` | `assignment` | `_ASSIGNED_ISSUE` |
| `review_requested` | `review_request` | `_REVIEW_PR` |
| `ci_activity` | `ci_failure` | `_CI_FAILURE` |
| `author` | `mention` | `_MENTION_ISSUE` or `_MENTION_PR` |
| `comment` | `mention` | `_MENTION_ISSUE` or `_MENTION_PR` |

The `author` and `comment` reasons map to `mention` because the agent treats activity on its own PRs and threads the same way it treats being mentioned — read the latest context and respond.

## Step 6: Scheduling

`Scheduler.submit()` creates an asyncio task that acquires the per-repo lock before executing. If another task is already running for the same repo, the new task waits in the queue.

## Step 7: Execution

See [Executor](Executor.md) for full details. In brief:

1. `WorkspaceManager.prepare()` clones or updates the repo
2. `executor.run()` builds the prompt and spawns Claude Code CLI
3. Claude Code reads code, makes changes, commits, pushes, and comments on GitHub
4. The executor captures stdout (via PTY) for live streaming and final audit

## Step 8: Audit

After execution completes, the `Scheduler._audit()` method writes an `AuditEntry` to the daily JSONL file. The entry includes:

- Notification metadata (ID, event type, repo, PR/issue number)
- Trigger context (user, text)
- Execution results (status, tokens, cost, duration)
- Formatted executor output lines (for history replay in the dashboard)

The notification is then marked as read via `PATCH /notifications/threads/{id}`.

## Active CI Scanning

GitHub does not reliably deliver `ci_activity` notifications through the REST notifications API. To ensure the agent detects its own failing CI checks, Agent0 uses active scanning instead of relying on passive notifications.

Every 5th poll cycle (~150 seconds at the default 30s interval), the daemon calls `Poller.scan_ci_failures()`:

1. Search GitHub for open PRs authored by the agent across all whitelisted orgs
2. For each PR, fetch the head SHA and its check suites
3. If all check suites have completed and any have `conclusion == 'failure'`, create a synthetic notification
4. Skip PRs where the head SHA has already been checked (prevents reprocessing the same failure)
5. Clean up tracking entries for PRs that are no longer open

The synthetic notifications flow through the same pipeline as real notifications: `fetch_context()` → `classify()` → `Scheduler.submit()`. The only difference is the `is_self_triggered()` check is bypassed for `ci_activity` reason — the agent is always the author of these PRs, and that is intentional.

**Stale SHA safety:** When fetching check suite context, the poller verifies that the check suite's commit SHA matches the PR's current head SHA. If a new commit was pushed after the check suite was created, the stale check suite is skipped. This prevents the agent from processing outdated failures.

## Bot Reviews

GitHub does not generate notifications for bot activity (e.g., Copilot reviews). The agent only processes notifications triggered by human users. To have the agent address a bot review, @mention it in a comment on the PR.
