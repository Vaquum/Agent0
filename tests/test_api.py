"""Tests for the FastAPI application routes."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from agent0.api import create_app
from agent0.config import Config
from agent0.logbuffer import LogBuffer


def _make_config(tmp_path: Path) -> Config:
    return Config(
        github_token='test-token',
        anthropic_api_key='test-key',
        github_user='zero-bang',
        claude_model='test-model',
        whitelisted_orgs=('Vaquum',),
        data_dir=tmp_path,
    )


def _make_daemon(
    running: list | None = None,
    queued: list | None = None,
) -> MagicMock:
    daemon = MagicMock()
    daemon.scheduler.get_running.return_value = running or []
    daemon.scheduler.get_queued.return_value = queued or []
    daemon.scheduler.get_executor_output.return_value = {'entries': [], 'last_id': 0}
    return daemon


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_returns_ok(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        app = create_app(_make_daemon(), config)

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'
        assert 'version' in data


class TestRunningTasksEndpoint:
    @pytest.mark.asyncio
    async def test_returns_running_tasks(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        tasks = [{'repo': 'Vaquum/Agent0', 'event_type': 'mention', 'number': 1}]
        app = create_app(_make_daemon(running=tasks), config)

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/tasks/running')

        assert response.status_code == 200
        assert response.json() == tasks

    @pytest.mark.asyncio
    async def test_returns_empty_when_none_running(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        app = create_app(_make_daemon(), config)

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/tasks/running')

        assert response.status_code == 200
        assert response.json() == []


class TestQueuedTasksEndpoint:
    @pytest.mark.asyncio
    async def test_returns_queued_tasks(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        tasks = [{'repo': 'Vaquum/Agent0', 'event_type': 'assign', 'number': 2}]
        app = create_app(_make_daemon(queued=tasks), config)

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/tasks/queued')

        assert response.status_code == 200
        assert response.json() == tasks


class TestHistoryEndpoint:
    @pytest.mark.asyncio
    async def test_returns_empty_history(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.audit_dir.mkdir(parents=True, exist_ok=True)
        app = create_app(_make_daemon(), config)

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/tasks/history')

        assert response.status_code == 200
        assert response.json() == []


class TestLogsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_empty_without_buffer(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        app = create_app(_make_daemon(), config, log_buffer=None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/logs')

        assert response.status_code == 200
        data = response.json()
        assert data == {'entries': [], 'last_id': 0}

    @pytest.mark.asyncio
    async def test_returns_buffered_entries(self, tmp_path: Path) -> None:
        import logging

        config = _make_config(tmp_path)
        buf = LogBuffer(maxlen=100)
        buf.emit(logging.LogRecord('test', logging.INFO, '', 0, 'hello', (), None))

        app = create_app(_make_daemon(), config, log_buffer=buf)

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/logs')

        assert response.status_code == 200
        data = response.json()
        assert len(data['entries']) == 1
        assert data['entries'][0]['message'] == 'hello'


class TestExecutorOutputEndpoint:
    @pytest.mark.asyncio
    async def test_returns_executor_output(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        daemon = _make_daemon()
        daemon.scheduler.get_executor_output.return_value = {
            'entries': [{'id': 1, 'text': 'line1'}],
            'last_id': 1,
        }
        app = create_app(daemon, config)

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/tasks/running/Vaquum/Agent0/output')

        assert response.status_code == 200
        data = response.json()
        assert data['entries'][0]['text'] == 'line1'
