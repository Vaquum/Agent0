# Security Specification

## 1. Overview

Agent0 operates with significant privileges — it can read code, write code, push
commits, and interact on GitHub as `zero-bang`. This spec defines the boundaries,
authentication model, and safeguards that prevent misuse or accidental damage.

## 2. Authentication

### 2.1 GitHub PAT

A Personal Access Token for `zero-bang` with scopes:
- `repo` — read/write access to repositories
- `notifications` — read/manage notifications

Storage: `GITHUB_TOKEN` environment variable on Render (encrypted at rest by Render).

Used by:
- Daemon Python code (`httpx` requests to GitHub API)
- `gh` CLI inside Claude Code subprocesses (via `GH_TOKEN` env var)
- `git` clone/push (embedded in clone URL)

### 2.2 Anthropic API Key

Storage: `ANTHROPIC_API_KEY` environment variable on Render.

Used by:
- Claude Code CLI (reads it from environment automatically)

### 2.3 Secret Handling

- Secrets are never logged, even at DEBUG level
- Secrets are never included in audit log entries
- Secrets are never committed to the repository
- Config logging on startup redacts secrets: `GITHUB_TOKEN=ghp_****...abcd`
- The Dockerfile does not embed secrets — they are injected at runtime by Render

## 3. Organization Whitelist

### 3.1 Enforcement

The whitelist is the primary access control. It determines which repos Agent0 will
interact with.

- Configured via `WHITELISTED_ORGS` environment variable
- Default: `mikkokotila,vaquum`
- Checked at the poller level — notifications from non-whitelisted orgs are dropped
  before any processing occurs
- The check compares `notification.repository.owner.login` against the whitelist
- Case-insensitive comparison

### 3.2 What It Prevents

- Agent0 will not read, clone, or interact with repos outside whitelisted orgs
- Even if `zero-bang` has access to other repos, Agent0 ignores them
- If someone forks a whitelisted repo to a non-whitelisted org and pings `zero-bang`,
  it is ignored

## 4. Self-Loop Prevention

Agent0 must never respond to its own actions.

### 4.1 Mechanisms

1. **Actor check** — when fetching the event that triggered a notification, check if
   the actor is `zero-bang`. If so, skip.
2. **Notification reason filter** — skip notifications with `reason: "subscribed"`
   unless there is also a direct mention or assignment.
3. **Processed ID tracking** — track notification IDs that have been processed in
   memory. If a notification ID is seen again, skip.

### 4.2 Failure Mode

If self-loop prevention fails (bug in the logic), the worst case is:
- Agent0 comments on something, gets notified, comments again, etc.
- This is bounded by the poll interval (30s) and GitHub rate limits
- The audit log would show rapid repeated actions on the same issue/PR
- Manual intervention: revoke the PAT or stop the Render service

## 5. Action Constraints

These constraints are enforced in the Claude Code prompt:

| Constraint | Reason |
|---|---|
| Never force push | Prevents history rewriting and data loss |
| Never merge PRs | Merging is a human decision |
| Never delete branches | Prevents accidental cleanup of in-progress work |
| Never modify GitHub settings | Repo settings, webhooks, etc. are admin territory |
| Never act outside whitelisted orgs | Enforced by whitelist, reinforced in prompt |
| Never create or delete repos | Out of scope |
| Never modify CI/CD config | Pipeline changes require human review |

These are prompt-level instructions. Claude Code follows them reliably. If additional
enforcement is needed later, it can be added via Claude Code's `--allowedTools`
flag to restrict available tools.

## 6. Workspace Isolation

- Each repo gets its own workspace directory: `/data/workspaces/{owner}/{repo}`
- Workspaces are isolated from each other
- Claude Code subprocesses have their `cwd` set to the specific workspace
- No symlinks or shared state between workspaces
- The `PATH` and other environment variables are clean — no leakage between sessions

## 7. Subprocess Sandboxing

Claude Code subprocesses run as the same OS user as the daemon (no privilege
escalation). They have access to:

- The workspace directory (read/write)
- Network access (for `gh` CLI and git push)
- The `ANTHROPIC_API_KEY` and `GH_TOKEN` environment variables
- Standard CLI tools (git, gh, python, node, etc.)

They do NOT have access to:
- Other workspaces (enforced by `cwd`, though not a hard sandbox)
- The daemon's internal state (separate process)
- The persistent disk's audit directory (though not enforced at the OS level)

If stronger isolation is needed later, each Claude Code subprocess could run in a
separate container (Docker-in-Docker). This is not implemented in v1.

## 8. Network Security

- All GitHub API calls use HTTPS
- All git operations use HTTPS (not SSH)
- The Render service is accessible via its `.onrender.com` URL
- The dashboard has no authentication in v1 — the URL is not publicly listed but
  is not truly secret. If the dashboard needs protection, add HTTP Basic Auth or
  an API key header later.

## 9. Audit Trail as Security Control

The audit log is the primary mechanism for detecting misuse or unexpected behavior.
Every action is logged with:

- Who triggered it
- What was done
- Token usage (detects unexpected cost spikes)
- Full Claude Code output (enables post-hoc review)

Review the audit log regularly. Anomalies to watch for:
- Actions outside expected repos
- Unusually high token usage for a single task
- Rapid repeated actions on the same issue/PR (possible loop)
- Tasks from unexpected users

## 10. Token and Cost Controls

- `EXECUTOR_TIMEOUT` limits how long a single Claude Code session can run (default:
  10 minutes). This bounds token usage per task.
- The audit log tracks `total_cost_usd` per task. Use this to set budget alerts.
- There is no hard cost cap in v1. If needed, add a daily budget check that pauses
  the daemon when cumulative daily cost exceeds a threshold.

## 11. Dependency Security

- Python dependencies are pinned in `pyproject.toml` with exact versions
- Node.js dependencies (Claude Code CLI) are installed globally at Docker build time
  with a pinned version
- The Dockerfile uses specific base image tags, not `latest`
- No unnecessary packages in the container
- Periodically audit dependencies for known vulnerabilities
