import logging
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

from agent0 import __version__
from agent0.audit import read_entry_output, read_history
from agent0.config import Config
from agent0.logbuffer import LogBuffer

__all__ = ['create_app']

log = logging.getLogger(__name__)


class _SchedulerLike(Protocol):

    def get_running(self) -> list[dict[str, Any]]:
        ...

    def get_queued(self) -> list[dict[str, Any]]:
        ...

    def get_executor_output(self, repo_key: str, after: int = 0) -> dict[str, Any]:
        ...


class _DaemonLike(Protocol):

    @property
    def scheduler(self) -> _SchedulerLike:
        ...


def create_app(
    daemon: _DaemonLike,
    config: Config,
    log_buffer: LogBuffer | None = None,
) -> FastAPI:

    '''
    Compute FastAPI application with API routes and static frontend.

    Args:
        daemon (Any): Daemon instance with scheduler attribute
        config (Config): Application configuration
        log_buffer (LogBuffer | None): In-memory log buffer for live log endpoint

    Returns:
        FastAPI: Configured FastAPI application
    '''

    app = FastAPI(title='Agent0', version=__version__)

    @app.get('/health')
    async def health() -> dict[str, str]:
        return {'status': 'ok', 'version': __version__}

    @app.get('/api/tasks/running')
    async def running_tasks() -> list[dict[str, Any]]:
        return daemon.scheduler.get_running()

    @app.get('/api/tasks/queued')
    async def queued_tasks() -> list[dict[str, Any]]:
        return daemon.scheduler.get_queued()

    @app.get('/api/tasks/history')
    async def task_history(
        page: int = Query(1, ge=1),
        per_page: int = Query(50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        entries = await read_history(config, page=page, per_page=per_page)
        return [
            {
                'timestamp': e.timestamp,
                'notification_id': e.notification_id,
                'event_type': e.event_type,
                'repo': e.repo,
                'reference': e.reference,
                'trigger_user': e.trigger_user,
                'trigger_text': e.trigger_text,
                'action_taken': e.action_taken,
                'status': e.status,
                'response': e.response,
                'input_tokens': e.input_tokens,
                'output_tokens': e.output_tokens,
                'cost_usd': e.cost_usd,
                'duration_seconds': e.duration_seconds,
                'error': e.error,
            }
            for e in entries
        ]

    @app.get('/api/tasks/history/{notification_id}/output')
    async def history_output(
        notification_id: str,
        timestamp: str | None = Query(None),
    ) -> dict[str, Any]:
        output = await read_entry_output(
            config, notification_id, timestamp,
        )
        if output is None:
            return {'entries': []}
        return {
            'entries': [{'id': i + 1, 'text': line} for i, line in enumerate(output)],
        }

    @app.get('/api/tasks/running/{repo_key:path}/output')
    async def executor_output(
        repo_key: str,
        after: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return daemon.scheduler.get_executor_output(repo_key, after)

    @app.get('/api/logs')
    async def logs(
        after: int = Query(0, ge=0),
        level: str = Query('DEBUG'),
    ) -> dict[str, Any]:
        if log_buffer is None:
            return {'entries': [], 'last_id': 0}
        return log_buffer.get_entries(after=after, level=level)

    _candidates = [
        Path('/app/frontend/dist'),
        Path(__file__).parent.parent.parent / 'frontend' / 'dist',
    ]
    frontend_dist = next((p for p in _candidates if p.exists()), None)

    if frontend_dist:
        log.info('Serving frontend from %s', frontend_dist)
        app.mount('/', StaticFiles(directory=str(frontend_dist), html=True), name='frontend')
    else:
        log.warning('Frontend dist not found in any candidate path')

    return app
