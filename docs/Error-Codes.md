# Error Codes

**Status:** Stable

**Context:** Reference of all Agent0 error codes. Use this to identify what went wrong when an error appears in logs or as a GitHub issue.

**Outcome:** After reading, you can look up any error code and understand its meaning, source module, and typical cause.

## Error Code Format

All codes follow the pattern `E<category><number>`:
- Category digit identifies the module
- Three-digit number identifies the specific error

## Codes

### E1xxx — Configuration / Startup

| Code | Description | Typical Cause |
|------|-------------|---------------|
| E1001 | Missing required environment variable | `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, or `GITHUB_USER` not set |
| E1002 | Invalid environment variable value | Non-integer value for `POLL_INTERVAL`, `PORT`, etc. |
| E1003 | Empty organization whitelist | `WHITELISTED_ORGS` is empty or not set |
| E1004 | GitHub auth mismatch | Token belongs to a different user than `GITHUB_USER` |

### E2xxx — GitHub API

| Code | Description | Typical Cause |
|------|-------------|---------------|
| E2001 | Rate limited | GitHub API returned 429 or rate limit headers indicate exhaustion |
| E2002 | API request failed | Non-200 response from GitHub API |
| E2003 | Unexpected API response | Response body doesn't match expected schema |
| E2004 | Notification mark-read failed | Could not mark a notification thread as read |

### E3xxx — Workspace / Git

| Code | Description | Typical Cause |
|------|-------------|---------------|
| E3001 | Git clone failed | Network issue, auth failure, or repo doesn't exist |
| E3002 | Git fetch failed | Network issue or auth token expired |
| E3003 | Git checkout failed | Branch doesn't exist or workspace is corrupted |
| E3004 | Git reset failed | Workspace is in a bad state |
| E3005 | Git clean failed | Permission issue on workspace files |

### E4xxx — Executor / Claude Code

| Code | Description | Typical Cause |
|------|-------------|---------------|
| E4001 | Claude CLI not found | `claude` binary not installed or not in PATH |
| E4002 | Execution timed out | Task exceeded `EXECUTOR_TIMEOUT` seconds |
| E4003 | Execution failed | Claude Code CLI exited with non-zero status |
| E4004 | Output parse failed | CLI exited successfully but output couldn't be parsed |

### E5xxx — Audit / Persistence

| Code | Description | Typical Cause |
|------|-------------|---------------|
| E5001 | Audit write failed | Could not append to daily JSONL audit file |
| E5002 | Reflections file read failed | Could not read `reflections.jsonl` |
| E5003 | Reflections file write failed | Could not append to `reflections.jsonl` |
| E5004 | Malformed audit entry | JSONL line could not be parsed as valid JSON |

### E6xxx — Reflector

| Code | Description | Typical Cause |
|------|-------------|---------------|
| E6001 | Phase 1 produced no output | Self-reflection executor returned empty response |
| E6002 | RFC issue URL not extracted | Phase 2 output didn't contain a recognizable GitHub issue URL |
| E6003 | Reflection target unparseable | Could not extract owner/repo/number from search result |

### E7xxx — Poll Loop

| Code | Description | Typical Cause |
|------|-------------|---------------|
| E7001 | Poll cycle error | Unhandled exception during notification polling |
| E7002 | CI scan error | Unhandled exception during CI failure scanning |
| E7003 | Reflection scan error | Unhandled exception during reflection scanning |
| E7004 | Context fetch failed | Could not fetch PR/issue context for a notification |
