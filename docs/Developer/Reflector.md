# Reflector

Status: **Stable**

Self-reflection engine that triggers post-mortem learning on merged PRs. This page covers the trigger mechanism, two-phase reflection process, and state persistence. Audience: engineers debugging or extending the reflection system.

After reading this, you will understand how the reflector decides when to reflect, what happens during each phase, and where state is stored.

## Overview

```
GitHub Search API  →  Reflector.scan()  →  count new merged PRs
                                                    │
                                            < REFLECTION_INTERVAL?
                                           ╱                      ╲
                                         yes                       no
                                          │                         │
                                        return               pick random target
                                                                    │
                                                          _reflect(owner, repo, number)
                                                           ╱                          ╲
                                                    Phase 1                      Phase 2
                                                  (reflection)               (RFC creation)
                                                                                    │
                                                                         record all as considered
```

## Trigger Mechanism

The daemon calls `Reflector.scan()` every `REFLECTION_SCAN_INTERVAL` polls (20 polls = ~10 minutes at 30s interval).

Each scan:

1. Queries GitHub Search API for merged PRs that Agent0 reviewed, once per whitelisted org
2. Filters out PRs already in the `_considered` set
3. If `len(new_prs) < REFLECTION_INTERVAL` (6), logs and returns
4. Picks a random target from the new PRs
5. Runs two-phase reflection on the target
6. Records **all** new PRs as considered (resets the counter)

This means at most one reflection is triggered per scan, and only when there are at least 6 new merged PRs; after that reflection, all new PRs from that scan are recorded as considered. The only randomness is which PR gets reflected on.

**Failure handling:** If `_reflect()` raises, the exception propagates and nothing is recorded. The same PRs will be re-discovered on the next scan, ensuring the reflection is retried.

## Two-Phase Reflection

### Phase 1: Open-ended reflection

Gathers full context for the target PR (metadata, reviews, inline comments, conversation, CI results, diff) and sends it to Claude Code with the `SELF_REFLECTION` prompt. No specific agenda — pure introspection.

### Phase 2: RFC creation

Takes the Phase 1 output plus the RFC template from `.github/ISSUE_TEMPLATE/rfc-template.md` and sends it to Claude Code with the `SELF_REFLECTION_RFC` prompt. Claude creates a GitHub issue on the Agent0 repository using the RFC template.

Both phases execute in the Agent0 workspace, holding the Scheduler's per-repo lock to prevent concurrent workspace access.

## State Persistence

**File:** `{DATA_DIR}/reflections.jsonl`

Each line is a JSON object:

```json
{"pr_key": "vaquum/confab#14", "timestamp": "2026-03-05T10:00:00+00:00", "reflected": false}
{"pr_key": "vaquum/confab#15", "timestamp": "2026-03-05T10:00:00+00:00", "reflected": true, "rfc_issue_url": "https://github.com/Vaquum/Agent0/issues/25"}
```

- `pr_key`: `owner/repo#number` format
- `reflected`: `true` for the PR that was reflected on, `false` for the rest in the batch
- `rfc_issue_url`: present only when `reflected` is `true` and Phase 2 produced a URL

On startup, `_load_considered()` reads this file into an in-memory `set[str]` for fast dedup lookups.

## GitHub API Query

```
GET /search/issues?q=reviewed-by:{user}+type:pr+is:merged+user:{org}&sort=updated&order=desc&per_page=100
```

This returns up to 100 merged PRs that the agent reviewed within a specific org. The search is repeated for each whitelisted org.

Search result items contain `repository_url` (`https://api.github.com/repos/owner/repo`) and `number`, from which the PR key is extracted.

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `REFLECTION_SCAN_INTERVAL` | 20 | Polls between scans (~10 min) |
| `REFLECTION_INTERVAL` | 6 | New merged PRs needed to trigger |

## Module API

`from agent0.reflector import REFLECTION_INTERVAL, REFLECTION_SCAN_INTERVAL, Reflector`

### `Reflector(config, client, scheduler)`

| Method | Returns | Description |
|--------|---------|-------------|
| `scan()` | `None` | Query GitHub, count new PRs, trigger reflection if threshold met |

### Internal helpers (not in `__all__`)

| Function | Returns | Description |
|----------|---------|-------------|
| `_pr_key_from_search_item(item)` | `str` | Extract `owner/repo#number` from search result |
| `_parse_search_item(item)` | `tuple[str, str, int]` | Extract (owner, repo, number) from search result |
| `_gather_context(owner, repo, number)` | `str` | Fetch full PR context as markdown |
| `_reflect(owner, repo, number)` | `str \| None` | Run two-phase reflection, return RFC URL |
| `_extract_issue_url(result)` | `str \| None` | Parse RFC URL from executor output |
| `_format_reviews(reviews)` | `str` | Format review objects as markdown |
| `_format_pr_comments(comments)` | `str` | Format inline review comments as markdown |
| `_format_issue_comments(comments)` | `str` | Format conversation comments as markdown |

## Integration Point

In `daemon.py`, the daemon creates a `Reflector` and calls `scan()` inside the poll loop:

```python
if self._poll_count % REFLECTION_SCAN_INTERVAL == 0:
    await self._reflector.scan()
```

The reflector shares the Scheduler's per-repo locks to avoid workspace contention.
