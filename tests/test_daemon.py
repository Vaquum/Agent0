"""Tests for Agent0 daemon module."""

import asyncio
import time
from datetime import UTC, datetime

import pytest

from agent0.config import Config
from agent0.daemon import Scheduler, _RunningTask
from agent0.router import TaskContext


def _make_config() -> Config:
    return Config(
        github_token='test',
        anthropic_api_key='test',
        github_user='test-bot',
        whitelisted_orgs=('testorg',),
    )


def _make_context(owner: str = 'org', repo: str = 'repo', number: int = 1) -> TaskContext:
    return TaskContext(
        event_type='review_request',
        owner=owner,
        repo=repo,
        number=number,
        subject_type='PullRequest',
        trigger_user='alice',
        trigger_text='review please',
        issue_body='some body',
        diff='diff text',
        comments=[],
        labels=[],
        head_ref='feature',
        base_ref='main',
        notification_id='123',
    )


class TestSchedulerHasTaskFor:
    def test_no_tasks(self) -> None:
        scheduler = Scheduler(_make_config())
        assert not scheduler.has_task_for('org', 'repo', 1)

    def test_running_task_matches(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(number=42)
        scheduler._running['org/repo'] = _RunningTask(
            context=ctx,
            started_at=time.monotonic(),
            started_at_utc=datetime.now(UTC).isoformat(),
        )
        assert scheduler.has_task_for('org', 'repo', 42)

    def test_running_task_different_number(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(number=42)
        scheduler._running['org/repo'] = _RunningTask(
            context=ctx,
            started_at=time.monotonic(),
            started_at_utc=datetime.now(UTC).isoformat(),
        )
        assert not scheduler.has_task_for('org', 'repo', 99)

    def test_queued_task_matches(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(number=42)
        scheduler._queued['org/repo'] = [ctx]
        assert scheduler.has_task_for('org', 'repo', 42)

    def test_queued_task_different_number(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(number=42)
        scheduler._queued['org/repo'] = [ctx]
        assert not scheduler.has_task_for('org', 'repo', 99)

    def test_different_repo(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(owner='org', repo='repo-a', number=1)
        scheduler._queued['org/repo-a'] = [ctx]
        assert not scheduler.has_task_for('org', 'repo-b', 1)


class TestSchedulerGetRunning:
    def test_empty(self) -> None:
        scheduler = Scheduler(_make_config())
        assert scheduler.get_running() == []

    def test_returns_running_task_metadata(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(number=42)
        scheduler._running['org/repo'] = _RunningTask(
            context=ctx,
            started_at=time.monotonic(),
            started_at_utc='2026-03-11T10:00:00+00:00',
        )
        tasks = scheduler.get_running()
        assert len(tasks) == 1
        assert tasks[0]['repo'] == 'org/repo'
        assert tasks[0]['number'] == 42
        assert tasks[0]['trigger_user'] == 'alice'
        assert tasks[0]['started_at'] == '2026-03-11T10:00:00+00:00'
        assert 'elapsed_seconds' in tasks[0]


class TestSchedulerGetQueued:
    def test_empty(self) -> None:
        scheduler = Scheduler(_make_config())
        assert scheduler.get_queued() == []

    def test_returns_queued_task_metadata(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(number=7)
        scheduler._queued['org/repo'] = [ctx]
        tasks = scheduler.get_queued()
        assert len(tasks) == 1
        assert tasks[0]['repo'] == 'org/repo'
        assert tasks[0]['number'] == 7
        assert tasks[0]['position'] == 1

    def test_multiple_queued_positions(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx1 = _make_context(number=1)
        ctx2 = _make_context(number=2)
        scheduler._queued['org/repo'] = [ctx1, ctx2]
        tasks = scheduler.get_queued()
        assert len(tasks) == 2
        assert tasks[0]['position'] == 1
        assert tasks[1]['position'] == 2


class TestSchedulerGetExecutorOutput:
    def test_no_buffer(self) -> None:
        scheduler = Scheduler(_make_config())
        result = scheduler.get_executor_output('org/repo')
        assert result == {'entries': [], 'last_id': 0}

    def test_with_buffer(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._output_buffers['org/repo'] = ['line1', 'line2']
        result = scheduler.get_executor_output('org/repo')
        assert len(result['entries']) == 2
        assert result['entries'][0] == {'id': 1, 'text': 'line1'}
        assert result['last_id'] == 2

    def test_after_cursor(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._output_buffers['org/repo'] = ['a', 'b', 'c']
        result = scheduler.get_executor_output('org/repo', after=1)
        assert len(result['entries']) == 2
        assert result['entries'][0] == {'id': 2, 'text': 'b'}


class TestSchedulerGetRepoLock:
    def test_creates_lock(self) -> None:
        scheduler = Scheduler(_make_config())
        lock = scheduler.get_repo_lock('org/repo')
        assert isinstance(lock, asyncio.Lock)

    def test_returns_same_lock(self) -> None:
        scheduler = Scheduler(_make_config())
        lock1 = scheduler.get_repo_lock('org/repo')
        lock2 = scheduler.get_repo_lock('org/repo')
        assert lock1 is lock2

    def test_different_repos_different_locks(self) -> None:
        scheduler = Scheduler(_make_config())
        lock1 = scheduler.get_repo_lock('org/repo-a')
        lock2 = scheduler.get_repo_lock('org/repo-b')
        assert lock1 is not lock2


class TestSchedulerSubmit:
    @pytest.mark.asyncio
    async def test_submit_queues_task(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(number=5)
        task = scheduler.submit(ctx)
        assert isinstance(task, asyncio.Task)
        assert 'org/repo' in scheduler._queued
        assert ctx in scheduler._queued['org/repo']
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
