import asyncio
import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent0.audit import AuditEntry, log_entry
from agent0.config import Config
from agent0.executor import ExecutorResult
from agent0.executor import run as executor_run
from agent0.poller import GitHubClient, Poller, RateLimited
from agent0.router import TaskContext, classify, is_self_triggered, should_process
from agent0.workspace import WorkspaceManager

__all__ = ['Scheduler', 'Daemon']

log = logging.getLogger(__name__)

CI_SCAN_INTERVAL = 5


@dataclass
class _RunningTask:

    '''
    Compute in-memory representation of a running task.

    Args:
        context (TaskContext): Task being executed
        started_at (float): Monotonic start time
        started_at_utc (str): UTC ISO timestamp

    Returns:
        _RunningTask: Running task metadata
    '''

    context: TaskContext
    started_at: float
    started_at_utc: str


class Scheduler:

    '''
    Compute per-repo task scheduling with concurrency control.

    One task per repo at a time. Different repos run in parallel.

    Args:
        config (Config): Application configuration

    Returns:
        Scheduler: Task scheduler with dashboard state exposure
    '''

    def __init__(self, config: Config) -> None:
        self._config = config
        self._locks: dict[str, asyncio.Lock] = {}
        self._running: dict[str, _RunningTask] = {}
        self._queued: dict[str, list[TaskContext]] = {}
        self._output_buffers: dict[str, list[str]] = {}
        self._workspace_mgr = WorkspaceManager(config)
        self._poller: Poller | None = None

    def set_poller(self, poller: Poller) -> None:

        '''
        Compute poller reference for marking notifications as read.

        Args:
            poller (Poller): The notification poller

        Returns:
            None
        '''

        self._poller = poller

    def has_task_for(self, owner: str, repo: str, number: int) -> bool:

        '''
        Check if a task for the same PR/issue is already running or queued.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): PR/issue number

        Returns:
            bool: True if a matching task exists
        '''

        repo_key = f'{owner}/{repo}'

        running = self._running.get(repo_key)
        if running and running.context.number == number:
            return True

        for queued_ctx in self._queued.get(repo_key, []):
            if queued_ctx.number == number:
                return True

        return False

    def submit(self, context: TaskContext) -> asyncio.Task[None]:

        '''
        Compute an asyncio task that executes the given task context.

        Args:
            context (TaskContext): Task to schedule

        Returns:
            asyncio.Task[None]: The scheduled asyncio task
        '''

        repo_key = f'{context.owner}/{context.repo}'

        if repo_key not in self._locks:
            self._locks[repo_key] = asyncio.Lock()

        if repo_key not in self._queued:
            self._queued[repo_key] = []
        self._queued[repo_key].append(context)

        return asyncio.create_task(self._execute(context, repo_key))

    async def _execute(self, context: TaskContext, repo_key: str) -> None:

        '''
        Compute task execution with per-repo locking and audit logging.

        Args:
            context (TaskContext): Task to execute
            repo_key (str): Owner/repo key for locking

        Returns:
            None
        '''

        lock = self._locks[repo_key]

        async with lock:
            if repo_key in self._queued and context in self._queued[repo_key]:
                self._queued[repo_key].remove(context)
                if not self._queued[repo_key]:
                    del self._queued[repo_key]

            now = datetime.now(timezone.utc).isoformat()
            self._running[repo_key] = _RunningTask(
                context=context,
                started_at=time.monotonic(),
                started_at_utc=now,
            )
            self._output_buffers[repo_key] = []

            result: ExecutorResult | None = None
            try:
                workspace = await self._workspace_mgr.prepare(context.owner, context.repo)
                result = await executor_run(
                    context,
                    str(workspace),
                    self._config,
                    output_lines=self._output_buffers.get(repo_key),
                )
            except Exception:
                tb = traceback.format_exc()
                log.error('Task failed for %s: %s', repo_key, tb)
                result = ExecutorResult(
                    status='failure',
                    response=None,
                    error=tb,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    num_turns=0,
                    duration_seconds=time.monotonic() - self._running[repo_key].started_at,
                    raw_output='',
                )
            finally:
                if result:
                    output = self._output_buffers.get(repo_key, [])
                    await self._audit(context, result, output if output else None)

                if self._poller:
                    try:
                        await self._poller.mark_read(context.notification_id)
                    except Exception:
                        log.warning(
                            'Failed to mark notification %s as read',
                            context.notification_id,
                        )

                self._output_buffers.pop(repo_key, None)
                self._running.pop(repo_key, None)

    async def _audit(
        self,
        context: TaskContext,
        result: ExecutorResult,
        output_lines: list[str] | None = None,
    ) -> None:

        '''
        Compute and persist audit entry from task result.

        Args:
            context (TaskContext): Task context
            result (ExecutorResult): Execution result
            output_lines (list[str] | None): Formatted executor output lines

        Returns:
            None
        '''

        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            notification_id=context.notification_id,
            event_type=context.event_type,
            repo=f'{context.owner}/{context.repo}',
            reference=context.number,
            trigger_user=context.trigger_user,
            trigger_text=context.trigger_text[:200],
            action_taken=context.event_type,
            status=result.status,
            response=result.response[:1000] if result.response else None,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
            duration_seconds=result.duration_seconds,
            error=result.error[:500] if result.error else None,
            executor_output=output_lines,
        )

        try:
            await log_entry(entry, self._config)
        except Exception:
            log.error('Failed to write audit entry: %s', traceback.format_exc())

    def get_running(self) -> list[dict[str, Any]]:

        '''
        Compute list of running tasks for dashboard.

        Returns:
            list[dict[str, Any]]: Running task metadata
        '''

        tasks = []
        now = time.monotonic()
        for repo_key, rt in self._running.items():
            tasks.append({
                'repo': repo_key,
                'event_type': rt.context.event_type,
                'number': rt.context.number,
                'trigger_user': rt.context.trigger_user,
                'trigger_text': rt.context.trigger_text[:100],
                'started_at': rt.started_at_utc,
                'elapsed_seconds': round(now - rt.started_at, 1),
            })
        return tasks

    def get_queued(self) -> list[dict[str, Any]]:

        '''
        Compute list of queued tasks for dashboard.

        Returns:
            list[dict[str, Any]]: Queued task metadata
        '''

        tasks = []
        for repo_key, contexts in self._queued.items():
            for i, ctx in enumerate(contexts):
                tasks.append({
                    'repo': repo_key,
                    'event_type': ctx.event_type,
                    'number': ctx.number,
                    'trigger_user': ctx.trigger_user,
                    'trigger_text': ctx.trigger_text[:100],
                    'position': i + 1,
                })
        return tasks

    def get_executor_output(self, repo_key: str, after: int = 0) -> dict[str, Any]:

        '''
        Compute buffered executor output lines for live dashboard view.

        Args:
            repo_key (str): Owner/repo key
            after (int): Return entries with id strictly greater than this value

        Returns:
            dict[str, Any]: Dict with entries list and last_id cursor
        '''

        lines = self._output_buffers.get(repo_key, [])
        entries = [
            {'id': i + 1, 'text': line}
            for i, line in enumerate(lines)
            if i + 1 > after
        ]
        return {'entries': entries, 'last_id': len(lines)}


class Daemon:

    '''
    Compute main daemon lifecycle: startup, poll loop, shutdown.

    Args:
        config (Config): Application configuration

    Returns:
        Daemon: The main daemon orchestrator
    '''

    def __init__(self, config: Config) -> None:
        self._config = config
        self._running = False
        self._poll_count = 0
        self._client = GitHubClient(config.github_token)
        self._poller = Poller(self._client, config)
        self._scheduler = Scheduler(config)
        self._scheduler.set_poller(self._poller)

    @property
    def scheduler(self) -> Scheduler:

        '''
        Compute scheduler reference for API layer.

        Returns:
            Scheduler: The task scheduler
        '''

        return self._scheduler

    async def start(self) -> None:

        '''
        Compute startup checks and initialize data directories.

        Returns:
            None
        '''

        log.info('Running startup checks...')

        user = await self._client.get_authenticated_user()
        username = user.get('login', '')
        if username.lower() != self._config.github_user.lower():
            raise RuntimeError(
                f'GitHub token is for {username}, expected {self._config.github_user}',
            )
        log.info('GitHub auth verified: %s', username)

        self._config.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self._config.audit_dir.mkdir(parents=True, exist_ok=True)
        log.info('Data directories initialized')

    async def poll_loop(self) -> None:

        '''
        Compute main polling loop that processes notifications.

        Returns:
            None
        '''

        self._running = True
        log.info('Entering poll loop (interval=%ds)', self._config.poll_interval)

        while self._running:
            self._poll_count += 1

            try:
                notifications = await self._poller.poll()

                if notifications:
                    log.info('Received %d notification(s)', len(notifications))

                for notification in notifications:
                    if not should_process(notification, self._config):
                        continue

                    try:
                        context = await self._poller.fetch_context(notification)
                    except Exception:
                        log.warning(
                            'Failed to fetch context for notification %s: %s',
                            notification.get('id'),
                            traceback.format_exc(),
                        )
                        continue

                    if context.get('skip'):
                        log.debug(
                            'Context flagged skip for notification %s',
                            notification.get('id'),
                        )
                        try:
                            await self._poller.mark_read(notification.get('id', ''))
                        except Exception:
                            pass
                        continue

                    reason = notification.get('reason', '')
                    skip_self_check = reason in ('ci_activity', 'review_requested')
                    if not skip_self_check and is_self_triggered(context, self._config):
                        log.info('Skipping self-triggered notification for %s', reason)
                        try:
                            await self._poller.mark_read(notification.get('id', ''))
                        except Exception:
                            pass
                        continue

                    task = classify(notification, context, self._config)

                    if self._scheduler.has_task_for(task.owner, task.repo, task.number):
                        log.info(
                            'Skipping duplicate task for %s/%s#%d (already running/queued)',
                            task.owner,
                            task.repo,
                            task.number,
                        )
                        continue

                    self._scheduler.submit(task)

            except RateLimited as e:
                log.warning('Rate limited, sleeping %ds', e.retry_after)
                await asyncio.sleep(e.retry_after)
                continue

            except Exception:
                log.warning('Poll error: %s', traceback.format_exc())

            if self._poll_count % CI_SCAN_INTERVAL == 0:
                try:
                    ci_notifications = await self._poller.scan_ci_failures()
                    for notification in ci_notifications:
                        try:
                            context = await self._poller.fetch_context(notification)
                        except Exception:
                            log.warning(
                                'CI scan: failed to fetch context for %s: %s',
                                notification.get('id'),
                                traceback.format_exc(),
                            )
                            continue

                        if context.get('skip'):
                            continue

                        task = classify(notification, context, self._config)
                        self._scheduler.submit(task)

                except RateLimited as e:
                    log.warning('CI scan rate limited, sleeping %ds', e.retry_after)
                    await asyncio.sleep(e.retry_after)

                except Exception:
                    log.warning('CI scan error: %s', traceback.format_exc())

            await asyncio.sleep(self._config.poll_interval)

    async def shutdown(self) -> None:

        '''
        Compute graceful shutdown: stop loop, wait for tasks, close client.

        Returns:
            None
        '''

        log.info('Shutting down...')
        self._running = False

        running = self._scheduler.get_running()
        if running:
            log.info('Waiting for %d running task(s) to complete...', len(running))
            for _ in range(60):
                if not self._scheduler.get_running():
                    break
                await asyncio.sleep(1)

        await self._client.close()
        log.info('Shutdown complete')
