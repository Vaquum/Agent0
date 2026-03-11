# Executor

**Status:** Stable

**Context:** Executor module internals — prompt building, subprocess management, output parsing. Intended for engineers debugging task execution or modifying CLI integration.

**Outcome:** After reading, you can trace a task from prompt construction through CLI execution to result parsing.

The executor is the bridge between Agent0's notification pipeline and Claude Code CLI. It builds prompts, spawns subprocesses, streams output, and parses results.

## Claude Code CLI

The executor invokes the Claude Code CLI with these flags:

```
claude --print --verbose --output-format stream-json --dangerously-skip-permissions --max-turns N
```

| Flag | Purpose |
|------|---------|
| `--print` | Non-interactive mode — reads prompt from stdin, writes result to stdout |
| `--verbose` | Includes token counts, cost, and turn metadata in output |
| `--output-format stream-json` | One JSON object per line, streaming as the agent works |
| `--dangerously-skip-permissions` | Skips tool permission prompts (required for unattended execution) |
| `--max-turns N` | Limits agentic turns to prevent runaway sessions |

The prompt is piped through stdin. Three environment variables are set:

- `ANTHROPIC_API_KEY` — For Claude Code to call the Anthropic API
- `GH_TOKEN` — For Claude Code to use `gh` CLI for GitHub operations
- `CLAUDE_CODE_ACCEPT_TOS` — Set to `true` to skip the terms acceptance prompt

## Prompt Templates

Every prompt starts with a shared preamble that establishes identity and rules:

**Preamble** — Tells Claude it is `zero-bang`, working on a specific repo, with specific safety rules (never force push, never merge PRs, never delete branches, never modify CI config, never act outside whitelisted orgs).

Then a task-specific template is appended based on `event_type`:

| Event Type | Template | Key Context Included |
|-----------|---------|---------------------|
| `mention` (Issue) | `_MENTION_ISSUE` | Issue body, comments, the mention text |
| `mention` (PR) | `_MENTION_PR` | PR body, diff, comments, the mention text |
| `assignment` | `_ASSIGNED_ISSUE` | Issue body, labels, comments, step-by-step instructions to branch/implement/PR |
| `review_request` | `_REVIEW_PR` | PR body, diff, comments, review instructions with `gh pr review` commands |
| `ci_failure` | `_CI_FAILURE` | Failed check output, PR diff, comments, fix instructions |

Each template includes the full conversation history (formatted by `router.format_comments()`) and instructs Claude Code on how to respond using `gh` CLI commands.

## PTY Streaming

Claude Code CLI runs on Node.js. When Node detects stdout is a pipe, it switches to full buffering (~64KB chunks). This makes real-time streaming impossible — the dashboard would see nothing until the entire session completes.

The solution is a pseudo-terminal (PTY):

```python
master_fd, slave_fd = pty.openpty()
process = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=slave_fd,     # Node sees a terminal, uses line buffering
    stderr=asyncio.subprocess.PIPE,
    ...
)
os.close(slave_fd)       # Parent only needs the master end
```

A background coroutine reads from `master_fd` via `loop.run_in_executor()` (blocking I/O offloaded to a thread). Each newline-delimited chunk is parsed as JSON and formatted for the dashboard.

The master file descriptor is explicitly closed in all exit paths (normal completion, timeout, error) to prevent fd leaks.

## Stream-JSON Format

Each line from Claude Code is a JSON object with a `type` field:

| Type | Meaning | Dashboard Display |
|------|---------|------------------|
| `assistant` | Claude's text response | First 300 chars of text content |
| `tool_use` | Claude invoked a tool | Tool name + key argument (command, file_path, etc.) |
| `result` | Session complete | Turn count and total cost |

The `_format_stream_line()` function converts each JSON object into a human-readable string that is appended to `output_lines` — a list buffer shared with the Scheduler for live dashboard access.

## Output Parsing

When the session ends, the raw stdout (all JSON lines joined by newlines) is parsed by `_parse_output()`:

1. Try parsing as a single JSON object (standard mode)
2. Try parsing as a JSON array (verbose mode without streaming)
3. Fall back to scanning lines in reverse for one containing a `result` key (stream-json mode)

The parser extracts: `result` (text response), `is_error`, `total_cost_usd`, `total_input_tokens`, `total_output_tokens`, `num_turns`.

## ExecutorResult

Every execution returns an `ExecutorResult` dataclass:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `success`, `failure`, or `timeout` |
| `response` | `str \| None` | Claude's text response |
| `error` | `str \| None` | Error message if failed |
| `input_tokens` | `int` | Total input tokens consumed |
| `output_tokens` | `int` | Total output tokens consumed |
| `cost_usd` | `float` | Estimated cost in USD |
| `num_turns` | `int` | Number of agentic turns taken |
| `duration_seconds` | `float` | Wall clock time |
| `raw_output` | `str` | Full raw stdout for audit |

## Timeout Handling

If the session exceeds `EXECUTOR_TIMEOUT` seconds, the process is killed and an `ExecutorResult` with `status='timeout'` is returned. The partially collected stdout is preserved in `raw_output` for debugging.

## Workspace Preparation

Before spawning Claude Code, the executor receives a workspace path from `WorkspaceManager.prepare()`. This ensures:

1. The repo is cloned if not already present
2. If already cloned, `git fetch` + `git reset --hard origin/{branch}` + `git clean -fd`
3. Claude Code runs in a clean, up-to-date checkout
