# Error Reporting

**Status:** Stable

**Context:** This page covers the structured error reporting system that Agent0 uses to surface operational failures as GitHub issues. Intended for engineers debugging production incidents or extending error handling.

**Outcome:** After reading, you can add new error codes, wire them into modules, and understand how duplicate issues are prevented.

## Overview

Every runtime error in Agent0 is tagged with a typed error code (E1xxx–E7xxx) that maps to a module scope. When critical errors occur during task execution, Agent0 automatically creates a bug-labeled GitHub issue in its own repository with full context.

## Error Code Taxonomy

| Range | Scope | Module |
|-------|-------|--------|
| E1xxx | config | `config.py` — startup, env vars |
| E2xxx | poller | `poller.py` — GitHub API |
| E3xxx | workspace | `workspace.py` — git operations |
| E4xxx | executor | `executor.py` — Claude Code CLI |
| E5xxx | audit | `audit.py`, `reflector.py` — persistence |
| E6xxx | reflector | `reflector.py` — self-reflection |
| E7xxx | daemon | `daemon.py` — poll loop |

All codes are defined in `src/agent0/errors.py` as a `StrEnum`.

## Key Components

### `ErrorCode` (StrEnum)

```python
from agent0.errors import ErrorCode

ErrorCode.E4002  # Execution timed out
ErrorCode.E4002.value  # 'E4002'
```

### `Agent0Error` (dataclass)

Structured error with context for issue creation:

```python
from agent0.errors import Agent0Error, ErrorCode

error = Agent0Error(
    code=ErrorCode.E4003,
    summary='Task execution failed for Vaquum/myrepo#42',
    detail=traceback_string[:2000],
    related_url='https://github.com/Vaquum/myrepo/issues/42',
    context_history=[
        'Received pull_request event for Vaquum/myrepo#42',
        'Triggered by user alice',
        'Task execution raised an unhandled exception',
    ],
)
```

### `report_error()` (async function)

Creates a deduplicated, bug-labeled GitHub issue:

```python
from agent0.errors import report_error

url = await report_error(error, github_client, 'Vaquum', 'Agent0')
# Returns issue URL or None (never raises)
```

Deduplication: searches for an existing open issue with the same error code in the title and the same `related_url` in the body. If found, returns the existing issue URL without creating a duplicate.

## Issue Format

**Title:** `bug(<scope>): <summary> — <code>`
Example: `bug(executor): Task execution failed for Vaquum/myrepo#42 — E4003`

**Labels:** `['bug']`

**Body sections:**
1. Error Code
2. What Agent0 Was Doing
3. Related (URL to the PR/issue/action)
4. Context History (numbered steps)
5. Error Detail (code block with traceback)
6. Timestamp

## Adding a New Error Code

1. Add the code to `ErrorCode` in `src/agent0/errors.py`
2. Prefix the corresponding `log.error()` or `log.warning()` with the code
3. If the error is critical, call `report_error()` to create a GitHub issue
4. Add a test in `tests/test_errors.py`

## References

- Source: `src/agent0/errors.py`
- Tests: `tests/test_errors.py`
- Wiring: `src/agent0/daemon.py` (`Scheduler._report()`)
