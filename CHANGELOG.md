# Changelog

## Unreleased

### Removed
- Disabled `review_requested` routing so Agent0 cannot submit pull-request reviews. Ignored requests are marked read; mention, assignment, author, comment, and CI-failure handling are unchanged.

## [0.1.5] - 2026-06-08

### Changed
- Hardened the assigned-issue behaviour so it is safe to run more than once, closing the gap with the battle-tested PR-review path (PR review itself is unchanged):
  - Idempotent: assignments use a deterministic branch `agent0/issue-<n>` and are skipped when an open PR for that issue already exists, so a restart or redelivered notification no longer opens a duplicate PR.
  - Visible failures: a failed or timed-out assignment now comments on the issue instead of being silently marked read and dropped.
  - Outcome check: a "successful" assignment that opened no PR and left no comment is flagged on the issue as a likely silent no-op.
  - Stronger prompt: read surrounding code first, stay in scope, run the test suite and `ruff` before pushing, and always leave a comment describing the outcome.

### Added
- Error codes `E2005` (assignment outcome comment failed) and `E7005` (assignment idempotency check failed)

## [0.1.4] - 2026-06-06

### Changed
- `REVIEW_PR` prompt now requires an open-threads ledger before any verdict: the reviewer must take an explicit position (agree / disagree-with-reason / defer-with-reason) on every other-reviewer objection and every CI check, and treat a red check as a finding rather than approving over it (RFC-0070, #107)

## [0.1.3] - 2026-03-11

### Added
- Structured error reporting system with typed error codes (E1xxx–E7xxx) and automatic GitHub issue creation for operational errors
- Error codes wired into all modules: config, poller, workspace, executor, audit, reflector, daemon
- Developer docs for error reporting architecture (`docs/Developer/Error-Reporting.md`)
- User-facing error code reference (`docs/Error-Codes.md`)
- User-facing Quickstart, Configuration, and CI Failure docs
- Status/Context/Outcome headers on all documentation files

### Fixed
- Silent exception swallowing in daemon poll loop and poller CI scan — all 7 sites now log warnings
- README dashboard port 9998 → 9999 to match actual config default
- README broken link to non-existent `Get-Started.md` → `Setup.md`

### Removed
- Dead `_parse_pr_key` function from reflector module

## [0.1.2] - 2026-03-05

### Changed
- `load_config` now raises `ValueError` at startup if `WHITELISTED_ORGS` resolves to an empty list, providing a clear error message instead of silently operating with no allowed organizations
- `__version__` in `__init__.py` is now read from package metadata via `importlib.metadata` instead of being hardcoded

## [0.1.1] - 2026-03-05

### Changed
- `/health` endpoint now returns `{"status": "ok", "version": "<version>"}` for easier debugging and monitoring
- Version sourced from `agent0.__version__` (set at module load time, not per-request)
- `FastAPI` app version metadata now also driven from `__version__` instead of a hardcoded string
