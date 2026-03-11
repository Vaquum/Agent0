# Agent0 Developer Docs

**Status:** Stable

**Context:** Entry point for the developer documentation. Intended for engineers building, debugging, or extending Agent0.

**Outcome:** After reading, you can locate the right doc for any development topic — architecture, modules, deployment, testing, or troubleshooting.

Agent0 is a daemon that operates as an autonomous software engineer on GitHub. It polls for notifications, classifies them, and dispatches work to Claude Code CLI — then posts the results back to GitHub. Python backend, TypeScript dashboard, deployed on Render via Docker.

## How It Works

1. **Poll** — The daemon polls GitHub's notifications API for activity on whitelisted orgs
2. **Route** — Each notification is classified into an event type (mention, assignment, review request, CI failure)
3. **Execute** — Claude Code CLI receives a structured prompt, works in a repo workspace, and interacts with GitHub via `gh`
4. **Report** — Results are audited to JSONL files and surfaced through the dashboard

## Documentation Map

| Document | What You Will Learn |
|----------|-------------------|
| [Architecture](Architecture.md) | System layers, data flow, concurrency model, design decisions |
| [Setup](Setup.md) | Local development from zero to running |
| [Configuration](Configuration.md) | Every environment variable, defaults, production vs development |
| [Pipeline](Pipeline.md) | Notification lifecycle from GitHub webhook to executed task |
| [Executor](Executor.md) | Claude Code CLI integration, prompt templates, PTY streaming, output parsing |
| [Dashboard](Dashboard.md) | Frontend architecture, API endpoints, real-time streaming |
| [Modules](Modules.md) | Module-by-module public API reference |
| [Deployment](Deployment.md) | Docker build, Render configuration, persistent storage |
| [Testing](Testing.md) | Test structure, running tests, writing new tests |
| [Troubleshooting](Troubleshooting.md) | Common issues, debugging techniques, log analysis |

## Quick Reference

```
src/agent0/
├── __init__.py        # Version
├── main.py            # Entry point — starts daemon + web server
├── config.py          # Environment → frozen Config dataclass
├── daemon.py          # Scheduler (per-repo locks) + Daemon (poll loop)
├── poller.py          # GitHubClient (REST API) + Poller (notification filtering)
├── router.py          # TaskContext + classification logic
├── executor.py        # Claude Code CLI subprocess with PTY streaming
├── workspace.py       # Git clone/fetch/reset management
├── audit.py           # JSONL audit trail
├── logbuffer.py       # In-memory ring buffer for live log API
└── api.py             # FastAPI routes + static frontend serving

frontend/src/
├── main.ts            # Dashboard UI with three view modes
└── api.ts             # TypeScript fetch wrappers for all API endpoints
```

## Start Here

If you are setting up a development environment, go to [Setup](Setup.md).

If you want to understand how the system works end-to-end, start with [Architecture](Architecture.md) then read [Pipeline](Pipeline.md).

If you are debugging a specific issue, jump to [Troubleshooting](Troubleshooting.md).
