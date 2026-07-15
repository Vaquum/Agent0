"""Tests for Agent0 daemon module."""

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from agent0.config import Config
from agent0.daemon import Daemon, Scheduler, _RunningTask
from agent0.executor import ExecutorResult
from agent0.router import TaskContext


def _make_config() -> Config:
    return Config(
        github_token='test',
        anthropic_api_key='test',
        github_user='test-bot',
        claude_model='test-model',
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


class TestIgnoreReviewRequest:
    @pytest.mark.asyncio
    async def test_mark_read_failure_still_ignores_review_request(self) -> None:
        daemon = Daemon(_make_config())
        await daemon._client.close()
        daemon._poller = AsyncMock()
        daemon._poller.mark_read.side_effect = RuntimeError('boom')

        ignored = await daemon._ignore_review_request(
            {'id': 'review-notification', 'reason': 'review_requested'}
        )

        assert ignored is True

    @pytest.mark.asyncio
    async def test_poll_loop_discards_review_request_and_routes_mention(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        daemon = Daemon(_make_config())
        await daemon._client.close()
        review = {'id': 'review-notification', 'reason': 'review_requested'}
        mention = {'id': 'mention-notification', 'reason': 'mention'}
        daemon._poller = AsyncMock()
        daemon._poller.poll.return_value = [review, mention]
        daemon._poller.fetch_context.return_value = {
            'owner': 'testorg',
            'repo': 'repo',
            'number': 42,
            'subject_type': 'Issue',
            'body': 'Help wanted',
            'labels': [],
            'comments': [],
            'actor': 'alice',
            'diff': None,
            'head_ref': None,
            'base_ref': None,
        }
        daemon._scheduler = Mock()
        daemon._scheduler.has_task_for.return_value = False

        async def stop_after_first_poll(_seconds: float) -> None:
            daemon._running = False

        monkeypatch.setattr(asyncio, 'sleep', stop_after_first_poll)

        await daemon.poll_loop()

        daemon._poller.mark_read.assert_awaited_once_with('review-notification')
        daemon._poller.fetch_context.assert_awaited_once_with(mention)
        daemon._scheduler.submit.assert_called_once()
        submitted = daemon._scheduler.submit.call_args.args[0]
        assert submitted.event_type == 'mention'
        assert submitted.number == 42


def _make_assignment(owner: str = 'org', repo: str = 'repo', number: int = 5) -> TaskContext:
    return TaskContext(
        event_type='assignment',
        owner=owner,
        repo=repo,
        number=number,
        subject_type='Issue',
        trigger_user='alice',
        trigger_text='do the thing',
        issue_body='body',
        diff=None,
        comments=[],
        labels=[],
        head_ref=None,
        base_ref=None,
        notification_id='n1',
    )


def _make_result(status: str = 'success') -> ExecutorResult:
    return ExecutorResult(
        status=status,
        response=None,
        error=None,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        num_turns=0,
        duration_seconds=0.0,
        raw_output='',
    )


class TestAssignmentPrExists:
    @pytest.mark.asyncio
    async def test_true_when_open_pr_exists(self) -> None:
        daemon = Daemon(_make_config())
        await daemon._client.close()
        daemon._client = AsyncMock()
        daemon._client.get_open_pulls_by_head.return_value = [{'number': 3}]

        assert await daemon._assignment_pr_exists('org', 'repo', 5) is True
        daemon._client.get_open_pulls_by_head.assert_awaited_once_with(
            'org', 'repo', 'agent0/issue-5'
        )

    @pytest.mark.asyncio
    async def test_false_when_no_pr(self) -> None:
        daemon = Daemon(_make_config())
        await daemon._client.close()
        daemon._client = AsyncMock()
        daemon._client.get_open_pulls_by_head.return_value = []

        assert await daemon._assignment_pr_exists('org', 'repo', 5) is False

    @pytest.mark.asyncio
    async def test_false_on_check_error(self) -> None:
        daemon = Daemon(_make_config())
        await daemon._client.close()
        daemon._client = AsyncMock()
        daemon._client.get_open_pulls_by_head.side_effect = RuntimeError('boom')

        assert await daemon._assignment_pr_exists('org', 'repo', 5) is False


class TestHandleAssignmentOutcome:
    @pytest.mark.asyncio
    async def test_failure_comments_on_issue(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._client = AsyncMock()

        await scheduler._handle_assignment_outcome(
            _make_assignment(number=7), _make_result('failure'), '2026-06-08T00:00:00+00:00'
        )

        scheduler._client.create_issue_comment.assert_awaited_once()
        args = scheduler._client.create_issue_comment.await_args[0]
        assert args[:3] == ('org', 'repo', 7)
        assert 'failure' in args[3]

    @pytest.mark.asyncio
    async def test_timeout_comments_on_issue(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._client = AsyncMock()

        await scheduler._handle_assignment_outcome(
            _make_assignment(), _make_result('timeout'), '2026-06-08T00:00:00+00:00'
        )

        scheduler._client.create_issue_comment.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_with_pr_stays_silent(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._client = AsyncMock()
        scheduler._client.get_open_pulls_by_head.return_value = [{'number': 9}]

        await scheduler._handle_assignment_outcome(
            _make_assignment(), _make_result('success'), '2026-06-08T00:00:00+00:00'
        )

        scheduler._client.create_issue_comment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_no_pr_no_comment_flags_noop(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._client = AsyncMock()
        scheduler._client.get_open_pulls_by_head.return_value = []
        scheduler._client.get_issue_comments.return_value = []

        await scheduler._handle_assignment_outcome(
            _make_assignment(), _make_result('success'), '2026-06-08T00:00:00+00:00'
        )

        scheduler._client.create_issue_comment.assert_awaited_once()
        assert 'no-op' in scheduler._client.create_issue_comment.await_args[0][3]

    @pytest.mark.asyncio
    async def test_success_no_pr_but_agent_commented_stays_silent(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._client = AsyncMock()
        scheduler._client.get_open_pulls_by_head.return_value = []
        scheduler._client.get_issue_comments.return_value = [
            {'user': {'login': 'test-bot'}, 'created_at': '2026-06-08T01:00:00Z'},
        ]

        await scheduler._handle_assignment_outcome(
            _make_assignment(), _make_result('success'), '2026-06-08T00:00:00+00:00'
        )

        scheduler._client.create_issue_comment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_stale_agent_comment_flags_noop(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._client = AsyncMock()
        scheduler._client.get_open_pulls_by_head.return_value = []
        scheduler._client.get_issue_comments.return_value = [
            {'user': {'login': 'test-bot'}, 'created_at': '2026-06-07T00:00:00Z'},
        ]

        await scheduler._handle_assignment_outcome(
            _make_assignment(), _make_result('success'), '2026-06-08T00:00:00+00:00'
        )

        scheduler._client.create_issue_comment.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_outcome_never_raises_on_api_error(self) -> None:
        scheduler = Scheduler(_make_config())
        scheduler._client = AsyncMock()
        scheduler._client.create_issue_comment.side_effect = RuntimeError('boom')

        await scheduler._handle_assignment_outcome(
            _make_assignment(), _make_result('failure'), '2026-06-08T00:00:00+00:00'
        )
