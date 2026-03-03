# Setup

## Prerequisites

- Python 3.12+
- Node.js 20+
- Git
- A GitHub Personal Access Token with `repo` and `notifications` scopes
- An Anthropic API key
- Claude Code CLI installed globally (`npm install -g @anthropic-ai/claude-code`)
- GitHub CLI installed (`gh`)

## Clone and Install

```bash
git clone git@github.com:vaquum/agent0.git
cd agent0

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

## Frontend Build

```bash
cd frontend
npm ci
npm run build
cd ..
```

The build output lands in `frontend/dist/` and is served by FastAPI at `/`.

## Environment Variables

Start from the template and then export values in your shell:

```bash
cp .env.example .env

export GITHUB_TOKEN="ghp_..."
export ANTHROPIC_API_KEY="sk-ant-..."
export WHITELISTED_ORGS="vaquum"
export POLL_INTERVAL="30"
export EXECUTOR_TIMEOUT="600"
export MAX_TURNS="100"
export DATA_DIR="./data"
export LOG_LEVEL="DEBUG"
export GITHUB_USER="zero-bang"
```

See [Configuration](Configuration.md) for the full list with defaults.

## Run Locally

```bash
python -m agent0
```

This starts the daemon (poll loop) and web server on port 9999. Open `http://localhost:9999` for the dashboard.

## Run with Docker

```bash
docker build -t agent0 .

docker run -d \
  --name agent0 \
  -p 9999:9999 \
  -e GITHUB_TOKEN="ghp_..." \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -e WHITELISTED_ORGS="vaquum" \
  -e DATA_DIR="/data" \
  -v agent0-data:/data \
  agent0
```

## Run Tests

```bash
pytest tests/ -q
```

Or with the full dev toolchain:

```bash
pytest tests/ -q && ruff check src/ tests/ && mypy src/
```

See [Testing](Testing.md) for details on test structure and writing new tests.

## Verify Everything Works

1. Start the daemon locally
2. Check `http://localhost:9999/health` returns `{"status": "ok"}`
3. Check the dashboard at `http://localhost:9999`
4. Watch the log panel — you should see poll activity
5. @mention the agent on an issue in a whitelisted org to trigger a task
