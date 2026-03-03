# GitHub Integration Specification

## 1. Overview

Agent0 interacts with GitHub through two channels:

1. **REST API via `httpx`** — the daemon's Python code uses this to poll notifications,
   fetch issue/PR context, and mark notifications as read.
2. **`gh` CLI via Claude Code** — when Claude Code is executing a task, it uses `gh` to
   comment on issues, submit reviews, create PRs, etc. This happens inside the Claude
   Code subprocess, not in the daemon's Python code.

The daemon handles the input side (what should I work on?). Claude Code handles the
output side (take action on GitHub).

## 2. Authentication

### GitHub PAT

A Personal Access Token for `zero-bang` with these scopes:

- `repo` — full access to repositories (read code, push commits, manage PRs/issues)
- `notifications` — read and manage notifications

The token is stored in the `GITHUB_TOKEN` environment variable.

It is used in two places:
- **Daemon Python code**: Passed as `Authorization: Bearer {token}` header in `httpx`
  requests to the GitHub REST API.
- **`gh` CLI**: Set as `GH_TOKEN` environment variable in the Claude Code subprocess
  so `gh` authenticates automatically.
- **Git operations**: Set as part of the clone URL
  (`https://x-access-token:{token}@github.com/{owner}/{repo}.git`) so git push works
  without SSH keys.

## 3. Notification Polling

### Endpoint

```
GET https://api.github.com/notifications
```

### Parameters

| Parameter | Value | Purpose |
|---|---|---|
| `all` | `false` | Only unread notifications |
| `participating` | `true` | Only where `zero-bang` is directly involved (mentioned, assigned, review requested) |

### Response Handling

Each notification object contains:

```json
{
  "id": "1234567890",
  "reason": "mention" | "assign" | "review_requested" | ...,
  "subject": {
    "title": "Fix the login bug",
    "url": "https://api.github.com/repos/owner/repo/issues/42",
    "type": "Issue" | "PullRequest"
  },
  "repository": {
    "full_name": "owner/repo",
    "owner": {
      "login": "owner"
    }
  },
  "updated_at": "2026-02-28T12:00:00Z"
}
```

### Processing Steps

For each notification:

1. **Org check** — extract `repository.owner.login`. If not in `WHITELISTED_ORGS`, skip.
2. **Self-check** — if the notification was triggered by `zero-bang` itself, skip. This
   is determined by fetching the triggering event and checking the actor.
3. **Dedup check** — if `notification.id` was already processed (tracked in memory),
   skip.
4. **Route** — pass to the router for classification.
5. **Mark as read** — `PATCH /notifications/threads/{id}` to mark the notification as
   read.

### Rate Limiting

GitHub's REST API allows 5,000 requests per hour for authenticated users.

- Polling every 30 seconds = 120 requests/hour for the poll itself
- Each notification requires 1-3 additional API calls to fetch context
- Well within limits even with moderate activity

If a 429 response is received:
- Read the `Retry-After` header (seconds)
- Sleep for that duration instead of the normal poll interval
- Log a warning

### Conditional Requests

Use the `If-Modified-Since` header to avoid wasting rate limit on polls with no new
notifications. GitHub returns 304 Not Modified if nothing changed, which costs less
against the rate limit.

```
GET /notifications
If-Modified-Since: {last_poll_timestamp}
```

On 304, skip processing entirely.

## 4. Fetching Context

When a notification is picked up, the daemon needs to fetch enough context for Claude
Code to understand what to do.

### 4.1 Issue Assigned

Fetch the full issue:

```
GET /repos/{owner}/{repo}/issues/{number}
```

Extract:
- `title`
- `body` (the issue description in markdown)
- `labels` (list of label names)
- `assignees` (to confirm `zero-bang` is assigned)
- `comments_url` (to fetch the conversation)

Then fetch all comments:

```
GET /repos/{owner}/{repo}/issues/{number}/comments
```

Extract each comment's `user.login`, `body`, and `created_at`.

### 4.2 Mentioned in Comment

The notification `subject.url` points to the issue or PR. The notification
`subject.latest_comment_url` points to the specific comment where `zero-bang` was
mentioned.

Fetch the specific comment to find the mention text:

```
GET /repos/{owner}/{repo}/issues/comments/{comment_id}
```

Also fetch the full issue/PR for context (same as 4.1).

### 4.3 Review Requested on PR

Fetch the full PR:

```
GET /repos/{owner}/{repo}/pulls/{number}
```

Extract:
- `title`
- `body` (PR description)
- `head.ref` (source branch)
- `base.ref` (target branch)
- `diff_url`

Fetch the PR diff:

```
GET /repos/{owner}/{repo}/pulls/{number}
Accept: application/vnd.github.v3.diff
```

This returns the raw diff as text. Include it in the Claude Code prompt so it can
review the actual code changes.

Fetch PR comments (review comments + issue comments):

```
GET /repos/{owner}/{repo}/pulls/{number}/comments
GET /repos/{owner}/{repo}/issues/{number}/comments
```

### 4.4 Context Size Limits

PR diffs can be very large. To avoid blowing up the Claude Code prompt:

- If the diff exceeds 100,000 characters, truncate with a note:
  `"[Diff truncated — {total_chars} characters total, showing first 100,000]"`
- Claude Code can still read the full diff from the filesystem once it has the repo
  cloned, so this truncation only affects the initial prompt context.

## 5. Self-Loop Prevention

When Claude Code takes action (comments, reviews, pushes), those actions generate
notifications for `zero-bang`. Without prevention, Agent0 would respond to its own
actions infinitely.

### Strategy

1. **`participating=true`** in the poll — this already filters to direct involvement
   only, but `zero-bang`'s own actions still trigger notifications.
2. **Actor check** — when fetching the triggering event context, check if the actor
   is `zero-bang`. If so, skip the notification.
3. **Notification reason** — notifications with `reason: "subscribed"` (auto-subscribed
   because `zero-bang` participated) are skipped unless the notification also has a
   direct mention or assignment.

### Actor Check Implementation

For issue comments: the comment object has `user.login` — check if it's `zero-bang`.
For PR reviews: the review object has `user.login` — check if it's `zero-bang`.
For assignments: the event that triggered the notification has an actor — if the actor
assigned `zero-bang` to themselves, skip (this shouldn't happen in normal workflow but
is a safety check).

## 6. What Claude Code Does via `gh` CLI

Once Claude Code is running in the repo workspace, it uses `gh` to interact with GitHub.
These are not called by the daemon's Python code — they happen inside the Claude Code
subprocess.

| Action | Command |
|---|---|
| Comment on issue | `gh issue comment {number} --body "..."` |
| Comment on PR | `gh pr comment {number} --body "..."` |
| Submit PR review (approve) | `gh pr review {number} --approve --body "..."` |
| Submit PR review (request changes) | `gh pr review {number} --request-changes --body "..."` |
| Submit PR review (comment only) | `gh pr review {number} --comment --body "..."` |
| Create PR | `gh pr create --title "..." --body "..." --base main` |
| Push commits | `git push origin {branch}` (via git, not gh) |

Claude Code has full autonomy to decide which of these actions to take based on the
task context.

## 7. GitHub API Client

The daemon's `httpx`-based GitHub client is a thin wrapper:

```python
class GitHubClient:
    base_url = "https://api.github.com"

    def __init__(self, token: str):
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def get_notifications(self, since: str | None) -> list[dict]: ...
    async def mark_notification_read(self, thread_id: str) -> None: ...
    async def get_issue(self, owner: str, repo: str, number: int) -> dict: ...
    async def get_issue_comments(self, owner: str, repo: str, number: int) -> list[dict]: ...
    async def get_pull_request(self, owner: str, repo: str, number: int) -> dict: ...
    async def get_pull_request_diff(self, owner: str, repo: str, number: int) -> str: ...
    async def get_pull_request_comments(self, owner: str, repo: str, number: int) -> list[dict]: ...
    async def get_comment(self, owner: str, repo: str, comment_id: int) -> dict: ...
```

Async throughout. No retries — if a call fails, the task fails and is logged in audit.
The next poll cycle picks up new notifications naturally.
