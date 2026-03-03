# Agent0

Agent0 is an autonomous GitHub engineering daemon. It polls GitHub notifications,
classifies actionable events, runs Claude Code tasks in isolated workspaces,
and exposes a live operations dashboard via FastAPI.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env

cd frontend
npm ci
npm run build
cd ..

python -m agent0
```

The service runs on `http://localhost:9999` and health checks on `/health`.

## Docker and Render

- Docker image builds from `Dockerfile` (multi-stage frontend + Python runtime)
- Render deployment is defined in `render.yaml`
- Persistent runtime data is mounted at `/data`

## Configuration

Required:

- `GITHUB_TOKEN`
- `ANTHROPIC_API_KEY`

All variables are documented in `docs/Developer/Configuration.md`.

## Developer Docs

Start with `docs/Developer/README.md` for architecture, setup, deployment, and testing guides.
