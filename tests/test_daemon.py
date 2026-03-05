"""Tests for Agent0 daemon module."""

import time
from datetime import datetime, timezone

from agent0.config import Config
from agent0.daemon import Scheduler, _RunningTask
from agent0.router import TaskContext


def _make_config() -> Config:
    return Config(github_token='test', anthropic_api_key='test', github_user='test-bot', whitelisted_orgs=('testorg',))


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
            started_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        assert scheduler.has_task_for('org', 'repo', 42)

    def test_running_task_different_number(self) -> None:
        scheduler = Scheduler(_make_config())
        ctx = _make_context(number=42)
        scheduler._running['org/repo'] = _RunningTask(
            context=ctx,
            started_at=time.monotonic(),
            started_at_utc=datetime.now(timezone.utc).isoformat(),
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
