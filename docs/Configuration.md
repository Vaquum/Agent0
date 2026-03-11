# Configuration

**Status:** Stable

**Context:** All environment variables that control Agent0's behavior. Intended for users deploying or tuning Agent0.

**Outcome:** After reading, you can configure every aspect of Agent0's runtime behavior.

## Required Variables

These must be set before Agent0 starts. Missing values cause immediate exit with error code E1001.

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub Personal Access Token with `repo` and `notifications` scopes |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude Code CLI |
| `GITHUB_USER` | GitHub username of the agent account |
| `WHITELISTED_ORGS` | Comma-separated list of GitHub organizations to monitor |

## Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POLL_INTERVAL` | `30` | Seconds between notification polls |
| `EXECUTOR_TIMEOUT` | `1800` | Maximum seconds per Claude Code session |
| `MAX_TURNS` | `100` | Maximum agentic turns per Claude Code session |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `DATA_DIR` | `/data` | Root directory for workspaces and audit logs |
| `PORT` | `9999` | Port for the dashboard web server |
| `AGENT0_REPO` | `Agent0` | Repository name where Agent0 itself lives |

## Validation

- Non-integer values for numeric variables cause exit with error code E1002
- Empty `WHITELISTED_ORGS` causes exit with error code E1003
- GitHub token user mismatch causes exit with error code E1004

## Example `.env`

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_USER=zero-bang
WHITELISTED_ORGS=Vaquum
POLL_INTERVAL=30
EXECUTOR_TIMEOUT=1800
MAX_TURNS=100
LOG_LEVEL=INFO
PORT=9999
```
