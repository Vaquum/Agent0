# Changelog

## [0.1.2] - 2026-03-05

### Changed
- `__version__` in `__init__.py` is now read from package metadata via `importlib.metadata` instead of being hardcoded

## [0.1.1] - 2026-03-05

### Changed
- `/health` endpoint now returns `{"status": "ok", "version": "<version>"}` for easier debugging and monitoring
- Version sourced from `agent0.__version__` (set at module load time, not per-request)
- `FastAPI` app version metadata now also driven from `__version__` instead of a hardcoded string
