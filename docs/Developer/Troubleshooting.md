# Troubleshooting

## Notifications Not Picked Up

**Symptom:** Agent0 is running but not responding to @mentions, assignments, or reviews.

**Check the poll log.** Look for `Poll returned 0 actionable notifications` in the dashboard log. If polls consistently return 0:

1. **Org not whitelisted** — The repo must belong to an org in `WHITELISTED_ORGS`. Check with `docker logs agent0 | grep 'non-whitelisted'`.

2. **Notification reason not actionable** — Only `mention`, `assign`, `review_requested`, `ci_activity`, and `author` are processed. Reasons like `subscribed` or `comment` are silently dropped.

3. **Already processed** — The poller deduplicates by `{notification_id: updated_at}`. If the notification's `updated_at` has not changed since last processing, it is skipped. A fresh poll (every 10th cycle) resets the `If-Modified-Since` cache but not the deduplication dict.

4. **GitHub 304 Not Modified** — If the `If-Modified-Since` header is too aggressive, GitHub returns 304 for every poll. This self-corrects every 10th cycle. Check for `304` in the logs.

5. **Bot activity** — GitHub does not generate notifications for bot users (e.g., Copilot reviews). To address bot feedback, @mention the agent in a comment.

## Self-Trigger Loop

**Symptom:** Agent0 keeps responding to its own actions.

This should not happen. The daemon checks `is_self_triggered()` and skips notifications where the actor matches `GITHUB_USER`. The only exception is CI failures, which bypass this check intentionally.

If you see a loop, check:
- Is `GITHUB_USER` set correctly? It must match the exact login of the PAT.
- Is the actor detection working? The actor is determined by the last comment's `user.login`.

## Task Stuck or Running Too Long

**Symptom:** A task shows in the running list for longer than expected.

1. **Check the executor output** — Click the running task in the dashboard to see live output. Claude Code may be stuck on a complex problem or waiting for a response.

2. **Timeout** — Tasks are killed after `EXECUTOR_TIMEOUT` seconds (default 1800s, 600s on Render). The result will be recorded as `timeout` in the audit.

3. **Per-repo lock** — If a task is queued, it is waiting for the current task on the same repo to finish. Check the queued tasks panel.

## Executor Fails Immediately

**Symptom:** Tasks fail with `claude CLI not found` error.

The Claude Code CLI must be installed and available in PATH. In Docker, it is installed globally via `npm install -g @anthropic-ai/claude-code@latest`. Locally, ensure `claude` is on your PATH.

**Symptom:** Tasks fail with authentication errors.

- Check `ANTHROPIC_API_KEY` is set correctly
- Check `GITHUB_TOKEN` has the required scopes (`repo`, `notifications`)
- Check `GH_TOKEN` is being passed through (it is set from `GITHUB_TOKEN` in the executor)

## Dashboard Not Loading

**Symptom:** The API works but the frontend shows a blank page.

1. **Frontend not built** — Run `cd frontend && npm run build` to produce `frontend/dist/`
2. **Static files not found** — The API looks for the frontend in `/app/frontend/dist` (Docker) or `{project}/frontend/dist` (local). Check the startup log for `Serving frontend from` or `Frontend dist not found`.

## Git Workspace Issues

**Symptom:** Tasks fail with git errors.

1. **Clone failed** — Check if the PAT has access to the repo. The clone URL embeds the token: `https://x-access-token:{token}@github.com/{owner}/{repo}.git`

2. **Dirty workspace** — The workspace manager runs `git reset --hard` and `git clean -fd` before each task. If this fails, delete the workspace manually: `rm -rf /data/workspaces/{owner}/{repo}`

3. **Safe directory error** — The entrypoint runs `git config --global --add safe.directory '*'`. If running outside Docker, you may need to run this manually.

## Rate Limiting

**Symptom:** Logs show `Rate limited, sleeping Ns`.

GitHub's notification API has rate limits. When hit, Agent0 sleeps for the `Retry-After` duration (from the 429 response header) and retries. This is automatic and self-healing.

To reduce API usage:
- Increase `POLL_INTERVAL` (fewer polls per minute)
- Reduce the number of whitelisted orgs (fewer notifications to process)

## Audit Files

**Location:** `{DATA_DIR}/audit/YYYY-MM-DD.jsonl`

Each line is a JSON object with the full task record. To inspect:

```bash
# Latest entries
tail -5 /data/audit/2024-01-15.jsonl | python -m json.tool

# Find failures
grep '"status": "failure"' /data/audit/*.jsonl

# Cost summary
grep -o '"cost_usd": [0-9.]*' /data/audit/*.jsonl
```

## Docker Port Conflict

**Symptom:** `Bind for 0.0.0.0:9999 failed: port is already allocated`

An old container is still running. Stop and remove it:

```bash
docker stop agent0 && docker rm agent0
```

Then start fresh.

## CI Failures Not Detected

**Symptom:** Agent0 creates a PR, CI fails, but no fix is attempted.

1. **Check the CI scan log** — Look for `CI scan: found failure on` in the logs. If absent, the active scanner is not finding any failures.

2. **Check suites still running** — The scanner waits until all check suites have `status == 'completed'`. If any suite is still `queued` or `in_progress`, the PR is skipped until the next scan cycle.

3. **Already processed** — The scanner deduplicates by `{owner/repo#number: head_sha}`. If the failure was already detected for that commit, it will not be reprocessed. Push a new commit to trigger a fresh scan.

4. **Stale SHA mismatch** — If a new commit was pushed after the check suite ran, the check suite's SHA will not match the PR's current head. The stale check suite is skipped. Wait for the new commit's checks to complete.

5. **Scan interval** — CI scanning runs every 5th poll cycle (~150 seconds at 30s interval). A failure may take up to 2.5 minutes to be detected after all checks complete.

6. **PR not authored by agent** — The scanner only looks at PRs authored by `GITHUB_USER`. If the PR was created by a different account, CI failures on it will not be picked up.

## Memory Usage

The in-memory state that grows over time:

- `Poller._processed_timestamps` — Capped at 500 entries, pruned to 200
- `Poller._ci_checked` — Grows with open agent-authored PRs, pruned when PRs close
- `LogBuffer._buffer` — Ring buffer capped at 1000 entries
- `Scheduler._output_buffers` — Cleared after each task completes

None of these should cause memory issues under normal operation. If memory grows unexpectedly, check for tasks that produce very large stdout (the raw output is held in memory until the task completes).
