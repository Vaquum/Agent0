# Executor Specification

## 1. Overview

The executor is the bridge between the daemon and Claude Code. It takes a classified
task (from the router), constructs a prompt, spawns a `claude` CLI subprocess in the
relevant repo workspace, captures the output, and returns structured results for the
audit logger.

## 2. Invocation

### CLI Command

```
claude --print --output-format json --verbose -p "{prompt}"
```

Flags:
- `--print` — non-interactive mode. Runs the prompt, executes all tools autonomously,
  then exits.
- `--output-format json` — returns structured JSON including response text, token usage,
  cost, and tool invocations.
- `--verbose` — includes detailed information about tool calls in the output.
- `-p` — pass the prompt. For long prompts, pipe via stdin instead:
  `echo "{prompt}" | claude --print --output-format json --verbose`

### Subprocess Configuration

```python
process = await asyncio.create_subprocess_exec(
    "claude", "--print", "--output-format", "json", "--verbose",
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=workspace_path,
    env={
        **os.environ,
        "ANTHROPIC_API_KEY": config.anthropic_api_key,
        "GH_TOKEN": config.github_token,
    },
)
stdout, stderr = await asyncio.wait_for(
    process.communicate(input=prompt.encode()),
    timeout=config.executor_timeout,
)
```

Key points:
- **Working directory** is the cloned repo workspace
- **Environment** includes `ANTHROPIC_API_KEY` for Claude Code and `GH_TOKEN` for `gh`
- **Timeout** is enforced at the asyncio level. On timeout, the process is killed.
- **Prompt** is passed via stdin to avoid shell escaping issues and argument length limits

## 3. Prompt Construction

The prompt is the most critical part. It tells Claude Code who it is, what happened,
and what to do. The prompt is assembled from templates filled with context data.

### 3.1 System Preamble

Every prompt starts with:

```
You are zero-bang, a software engineer. You are working on the repository {owner}/{repo}.

You have full autonomy to read code, edit files, run commands, commit, push, and interact
with GitHub via the gh CLI.

Rules:
- Never force push
- Never merge PRs
- Never act on repositories outside these organizations: {whitelisted_orgs}
- Always commit with clear, descriptive messages
- When creating a PR, write a clear title and description
- When reviewing a PR, be thorough — check logic, edge cases, style, and tests
- If a task is unclear, comment on the issue/PR asking for clarification rather than
  guessing
- If you need to make changes, create a branch named agent0/{short-description}
```

### 3.2 Event-Specific Context

Appended after the preamble, depending on the event type:

#### Mention in Issue Comment

```
You were mentioned in a comment on issue #{number}: "{title}"

Issue body:
{issue_body}

Conversation:
{formatted_comments}

The comment mentioning you:
@zero-bang {mention_text}

Respond to what was asked of you. If it's a question, answer it by commenting on the
issue. If it's a task, do the work and comment with what you did.
```

#### Mention in PR Comment

```
You were mentioned in a comment on PR #{number}: "{title}"

PR description:
{pr_body}

PR diff:
{diff}

Conversation:
{formatted_comments}

The comment mentioning you:
@zero-bang {mention_text}

Respond to what was asked of you. Use `gh pr comment {number} --body "..."` to reply.
```

#### Assigned to Issue

```
You have been assigned to issue #{number}: "{title}"

Issue body:
{issue_body}

Labels: {labels}

Conversation:
{formatted_comments}

Read the issue carefully. If the task is clear, do the work:
1. Create a branch named agent0/{short-description}
2. Implement the changes
3. Commit and push
4. Create a PR referencing this issue (use "Closes #{number}" in the PR body)
5. Comment on the issue with a summary of what you did

If the task is unclear or you need more information, comment on the issue asking for
clarification. Do not guess.
```

#### Review Requested on PR

```
You have been asked to review PR #{number}: "{title}"

PR description:
{pr_body}

Source branch: {head_ref} -> Target branch: {base_ref}

PR diff:
{diff}

Conversation:
{formatted_comments}

Review this PR thoroughly:
1. Read the diff carefully
2. Check the code in the repo for full context if needed
3. Look for bugs, logic errors, edge cases, missing tests, style issues
4. Submit your review using gh:
   - If the code is good: `gh pr review {number} --approve --body "..."`
   - If changes are needed: `gh pr review {number} --request-changes --body "..."`
   - For minor comments: `gh pr review {number} --comment --body "..."`
```

### 3.3 Conversation Formatting

Comments are formatted as a readable thread:

```
**{user}** ({timestamp}):
{comment_body}

---

**{user}** ({timestamp}):
{comment_body}
```

Timestamps are formatted as relative when recent ("2 hours ago") and absolute when
older ("2026-02-25 14:30 UTC").

## 4. Output Parsing

### 4.1 Success Case

Claude Code with `--output-format json` returns:

```json
{
  "result": "I reviewed the PR and submitted my feedback...",
  "is_error": false,
  "total_cost_usd": 0.0423,
  "total_input_tokens": 15234,
  "total_output_tokens": 2341,
  "num_turns": 5
}
```

Extract:
- `result` — the final text response (for audit log)
- `total_cost_usd` — cost in USD
- `total_input_tokens` — input token count
- `total_output_tokens` — output token count
- `num_turns` — number of agentic turns (tool call round-trips)

### 4.2 Error Case

If `is_error` is `true` or the process exits non-zero:
- Log the full stdout and stderr
- Record as failed in audit
- Do not retry — the notification is marked as read

### 4.3 Timeout Case

If the process exceeds `EXECUTOR_TIMEOUT`:
- Kill the process (`process.kill()`)
- Log as timeout in audit
- Any partial work (uncommitted files, unpushed branches) remains in the workspace
  and will be cleaned up on next `workspace.prepare()` for that repo

### 4.4 Invalid JSON Case

If stdout is not valid JSON:
- Log the raw stdout as a string
- Record as failed in audit with reason "invalid output format"

## 5. Executor Interface

```python
@dataclass
class TaskContext:
    event_type: str             # "mention", "assignment", "review_request"
    owner: str                  # repo owner
    repo: str                   # repo name
    number: int                 # issue or PR number
    subject_type: str           # "Issue" or "PullRequest"
    trigger_user: str           # who triggered the notification
    trigger_text: str           # the text that triggered it
    issue_body: str | None      # issue/PR body
    diff: str | None            # PR diff (only for PRs)
    comments: list[dict]        # conversation history
    labels: list[str]           # issue labels
    head_ref: str | None        # PR source branch
    base_ref: str | None        # PR target branch
    notification_id: str        # GitHub notification ID

@dataclass
class ExecutorResult:
    status: str                 # "success", "failure", "timeout"
    response: str | None        # Claude Code's text response
    error: str | None           # error message if failed
    input_tokens: int           # tokens used (input)
    output_tokens: int          # tokens used (output)
    cost_usd: float             # cost in USD
    num_turns: int              # number of agentic turns
    duration_seconds: float     # wall clock time
    raw_output: str             # full raw stdout for audit

async def run(context: TaskContext, workspace_path: str, config: Config) -> ExecutorResult:
    """Construct prompt, spawn claude CLI, parse output, return result."""
    ...
```

## 6. Concurrency

The executor itself is stateless. Concurrency is managed by the scheduler (per-repo
locking). The executor just spawns a subprocess and waits.

Multiple executors can run in parallel for different repos — each is an independent
asyncio task with its own subprocess.

## 7. Claude Code Permissions

In `--print` mode, Claude Code runs with full tool access by default. The Claude Code
session has access to:

- **File operations**: Read, write, edit any file in the workspace
- **Bash**: Run any shell command
- **Git**: Full git access (commit, push, branch, etc.)
- **gh CLI**: Full GitHub CLI access (comment, review, create PR, etc.)

The constraints (no force push, no merge) are enforced in the prompt, not at the tool
level. Claude Code follows these instructions reliably.

## 8. CLAUDE.md

Each repo workspace can contain a `CLAUDE.md` file at the root. Claude Code
automatically reads this file and follows the instructions in it. This allows
per-repo customization of behavior (coding style, test commands, review standards)
without modifying the executor.

The daemon does not need to handle `CLAUDE.md` — Claude Code does this natively.
