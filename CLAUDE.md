---
alwaysApply: true
---

## General Contracts

- No workarounds. Find the root cause, and fix it.
- No fallbacks. Let things break and make noise.
- No silent failures. If something goes wrong, let it break.
- No swallowing exceptions. If it's caught, it's handled.

## Environment Contract

Deployment-specific variables shall never be hard-coded.

1. root .env.example is the single contract for required runtime secrets/config
2. deployment-specific values must come from env vars (no hard-coded defaults)
3. missing or empty required env vars fail loudly
4. every sub-slice closeout asks: "was any deployment-specific value hard-coded?"

## Documentation Contract

Every slice ends with two mandatory guardrail sub-slices, in order:
1. Developer docs update in `docs/developer/`
2. User docs update in `docs/`

**All docs**
- One topic per file. No omnibus documents.
- Section nouns: Overview, Quickstart, How-to Guides, Concepts/Architecture, API Reference, FAQ, Glossary
- Status: `Stable | Experimental | Deprecated` (top of page)
- Context: what this page covers and who it's for (one paragraph)
- Outcome: what the reader can do or understand after reading
- Content: concise steps, diagrams, or explanations — no environment assumptions
- References: links to relevant code, ADRs, and related pages

**Developer docs**
- Audience: engineers building and debugging the project
- A newcomer skimming the root `README.md` in under 90 seconds must be able to locate: high-level overview, API surfaces, task-oriented guides, and design decisions
- A doc entry is complete only when a new engineer can implement and debug the topic without tribal knowledge

**User docs**
- Audience: external users and integrators consuming the project
- No implementation detail, no internal concepts, no references to internal tooling
- A doc entry is complete only when a user can integrate and use the feature without asking anyone

## Version Control Contract

Commits follow Conventional Commits format: `<type>(<scope>): <description>`

**When to commit**
- After every sub-slice closeout (mandatory)
- After any meaningful unit of work between sub-slices (intermittent, use judgment)
- Never batch unrelated changes into one commit

**Scope** is the module or area: `daemon`, `router`, `executor`, `poller`, `config`, `prompts`, `dashboard`, `docker`, etc.

Examples:
- `feat(router): add post-mortem self-reflection on PR close`
- `fix(executor): prevent workspace leak on timeout`
- `test(prompts): verify REQUEST_CHANGES requires inline comments`
- `docs(config): document CONFAB_API_KEY in .env.example`

## Repo Contracts

Every repo must have these files. They are maintained from initial setup forward.

| File | Purpose |
|---|---|
| `.env.example` | All required env vars. No deployment-specific values in code. |
| `CLAUDE.md` | Agent execution rules. Read before every task. |
| `CHANGELOG.md` | Release and slice summaries. Updated at every closeout. |
| `pyproject.toml` | Tooling config. Ruff and Pyright are the style and type contracts. |
| `render.yaml` | Render Blueprint. All secrets `sync: false`, non-secrets with values. |
| `Dockerfile` | Multi-stage build. Frontend + Python runtime. |
| `Makefile` | Local dev workflow. `make dev`, `make stop`, `make logs`. |
| `docs/Developer/` | Developer docs. Architecture, contracts, configuration. |
| `tests/` | Behavioral tests. Every atomic behavior has contract-based coverage. |

## Static Analysis Contract

`ruff` and `pyright` are the enforcers. Both must pass clean before any sub-slice is marked done.

| Tool | Purpose | Config |
|---|---|---|
| `ruff check` | Linting | `pyproject.toml` |
| `ruff format` | Formatting, single quotes | `pyproject.toml` |