# Changelog

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
