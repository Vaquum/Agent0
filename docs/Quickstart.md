# Quickstart

**Status:** Stable

**Context:** Minimal steps to get Agent0 running. Intended for users setting up Agent0 for the first time.

**Outcome:** After reading, you can deploy Agent0 and have it responding to GitHub mentions.

## Prerequisites

- A GitHub account with a Personal Access Token (PAT) that has `repo` and `notifications` scopes
- An Anthropic API key
- Docker installed on your deployment machine

## 1. Clone the Repository

```bash
git clone https://github.com/Vaquum/Agent0.git
cd Agent0
```

## 2. Configure Environment

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub PAT with `repo` and `notifications` scopes |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude Code |
| `GITHUB_USER` | GitHub username for the agent account |
| `WHITELISTED_ORGS` | Comma-separated list of GitHub orgs to respond to |

## 3. Start Agent0

```bash
make dev
```

This builds the Docker image and starts the container. Agent0 will begin polling for GitHub notifications immediately.

## 4. Verify It Works

Check the health endpoint:

```bash
curl http://localhost:9999/health
```

Expected response:
```json
{"status": "ok", "version": "0.1.2"}
```

## 5. Trigger Agent0

In any repository owned by a whitelisted org, mention the agent in an issue or PR comment:

```
@your-agent-username please fix the typo in README.md
```

Agent0 will pick up the notification, clone the repo, run Claude Code, and post the results back.

## Next Steps

- [Configuration](Configuration.md) — all environment variables and tuning options
- [Error Codes](Error-Codes.md) — understanding error codes in logs
- [Self-Reflection](Self-Reflection.md) — how Agent0 learns from its reviews
