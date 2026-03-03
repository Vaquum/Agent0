# Configuration

All configuration is loaded from environment variables at startup via `config.load_config()`. The result is a frozen `Config` dataclass — immutable for the lifetime of the process.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT for the agent account. Needs `repo` and `notifications` scopes. |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key for Claude Code CLI. |
| `WHITELISTED_ORGS` | No | `vaquum` | Comma-separated list of GitHub orgs to respond to. Notifications from other orgs are silently dropped. |
| `POLL_INTERVAL` | No | `30` | Seconds between notification polls. Lower values mean faster response but more API usage. |
| `EXECUTOR_TIMEOUT` | No | `1800` | Maximum seconds per Claude Code session. Tasks exceeding this are killed. |
| `MAX_TURNS` | No | `100` | Maximum agentic turns per Claude Code session. Passed as `--max-turns` to the CLI. |
| `LOG_LEVEL` | No | `INFO` | Python logging level. Use `DEBUG` for development. |
| `DATA_DIR` | No | `/data` | Root directory for persistent data (workspaces and audit logs). |
| `GITHUB_USER` | No | `zero-bang` | GitHub username of the agent. Used for self-trigger detection and PR authorship checks. |
| `PORT` | No | `9999` | Port for the web server (FastAPI + dashboard). |

## Derived Paths

The `Config` dataclass exposes two computed properties:

| Property | Value | Contents |
|----------|-------|----------|
| `workspaces_dir` | `{DATA_DIR}/workspaces` | Local git clones organized as `{owner}/{repo}` |
| `audit_dir` | `{DATA_DIR}/audit` | Daily JSONL audit files as `YYYY-MM-DD.jsonl` |

## Production vs Development

| Concern | Production (Render) | Development (Local) |
|---------|-------------------|-------------------|
| `DATA_DIR` | `/data` (persistent disk) | `./data` (local directory) |
| `LOG_LEVEL` | `INFO` | `DEBUG` |
| `EXECUTOR_TIMEOUT` | `600` (Render config) | `1800` (default, more generous for debugging) |
| `POLL_INTERVAL` | `30` | `30` (or lower for faster feedback) |
| Secrets | Set via Render dashboard (sync: false) | Export in shell or `.env` file |

## Secret Safety

`GITHUB_TOKEN` and `ANTHROPIC_API_KEY` are required. If either is missing, the process exits with an error immediately.

On startup, the config is logged in redacted form via `config.log_redacted()`. Secrets are masked to show only the first and last 4 characters (e.g., `ghp_...abcd`). This makes it possible to verify which token is in use without exposing the full value.

## Startup Validation

After loading config, the daemon runs a startup check:

1. Calls `GET /user` on the GitHub API to verify the token works
2. Compares the authenticated username against `GITHUB_USER`
3. If they do not match, the process raises `RuntimeError` and exits
4. Creates `workspaces_dir` and `audit_dir` if they do not exist
