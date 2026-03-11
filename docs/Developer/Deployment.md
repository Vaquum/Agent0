# Deployment

**Status:** Stable

**Context:** Deployment architecture and configuration for Agent0 on Render. Intended for engineers managing production deployments.

**Outcome:** After reading, you can deploy, update, and troubleshoot Agent0 in a Render environment.

Agent0 is deployed on Render (Frankfurt region) as a Docker web service with persistent disk storage.

## Docker Build

The Dockerfile uses a two-stage build:

### Stage 1: Frontend Build

```
FROM node:20-slim AS frontend-build
```

- Installs npm dependencies via `npm ci`
- Runs `npm run build` to produce `frontend/dist/`

### Stage 2: Runtime

```
FROM python:3.12-slim
```

Installs:
- **Node.js 20** — Required by Claude Code CLI (which runs on Node)
- **Claude Code CLI** — `npm install -g @anthropic-ai/claude-code@latest`
- **GitHub CLI** — For `gh` commands used by Claude Code
- **gosu** — For privilege dropping in the entrypoint
- **Git** — For workspace management

Then:
- Installs the Python package via `pip install .`
- Copies the frontend build from stage 1
- Creates a non-root `agent0` user (Claude Code CLI refuses `--dangerously-skip-permissions` as root)
- Creates `/data/workspaces` and `/data/audit` directories

### Entrypoint

`entrypoint.sh` does three things:

1. `chown -R agent0:agent0 /data` — Fix ownership of the persistent disk (mounted as root)
2. `gosu agent0 git config --global --add safe.directory '*'` — Allow git operations in any directory
3. `exec gosu agent0 "$@"` — Drop to the `agent0` user and run the CMD

## Render Configuration

Defined in `render.yaml`:

```yaml
services:
  - type: web
    name: agent0
    runtime: docker
    region: frankfurt
    plan: starter
    healthCheckPath: /health
    autoDeploy: true
    branch: main
    disk:
      name: agent0-data
      mountPath: /data
      sizeGB: 10
```

### Environment Variables on Render

| Variable | Render Setting |
|----------|---------------|
| `GITHUB_TOKEN` | Secret (sync: false) — set via Render dashboard |
| `ANTHROPIC_API_KEY` | Secret (sync: false) — set via Render dashboard |
| `WHITELISTED_ORGS` | `vaquum` |
| `POLL_INTERVAL` | `30` |
| `EXECUTOR_TIMEOUT` | `600` |
| `MAX_TURNS` | `100` |
| `LOG_LEVEL` | `INFO` |
| `DATA_DIR` | `/data` |
| `GITHUB_USER` | `zero-bang` |

Secrets are marked `sync: false` so they are never committed to the repo or synced from `render.yaml`.

### Persistent Disk

The 10GB disk at `/data` survives container restarts and redeployments. It holds:

- Git clones in `/data/workspaces/{owner}/{repo}`
- Audit logs in `/data/audit/YYYY-MM-DD.jsonl`

Workspace clones avoid re-cloning on every task. The disk is the only persistent state — all in-memory state rebuilds on restart.

### Health Check

Render pings `GET /health` to verify the service is running. The endpoint returns `{"status": "ok"}` immediately. If health checks fail, Render restarts the container.

### Auto-Deploy

Pushing to the `main` branch triggers an automatic rebuild and deploy. The Docker image is rebuilt from scratch (no layer cache on Render), so deploys take a few minutes.

## Manual Docker Operations

### Build and Run Locally

```bash
docker build -t agent0 .

docker run -d \
  --name agent0 \
  -p 9999:9999 \
  -e GITHUB_TOKEN="ghp_..." \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -v agent0-data:/data \
  agent0
```

### View Logs

```bash
docker logs -f agent0
```

### Stop and Remove

```bash
docker stop agent0 && docker rm agent0
```

### Rebuild After Changes

```bash
docker stop agent0 && docker rm agent0
docker build -t agent0 .
docker run -d --name agent0 -p 9999:9999 \
  -e GITHUB_TOKEN="ghp_..." \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -v agent0-data:/data \
  agent0
```

## Graceful Shutdown

On SIGTERM (sent by Docker/Render during redeploys):

1. The signal handler sets a shutdown event
2. The poll loop stops accepting new work
3. Running tasks are given up to 60 seconds to complete
4. The HTTP client is closed
5. The process exits

This prevents tasks from being killed mid-execution during redeployments.
