"""Self-reflection engine for post-mortem learning on merged PRs.

Queries GitHub Search API for merged PRs that Agent0 reviewed,
counts new ones since the last scan, and triggers a two-phase
reflection every REFLECTION_INTERVAL merged PRs. Creates an
RFC issue on the Agent0 repository.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent0 import prompts
from agent0.config import Config
from agent0.executor import ExecutorResult
from agent0.executor import run as executor_run
from agent0.poller import GitHubClient
from agent0.router import TaskContext
from agent0.workspace import WorkspaceManager

if TYPE_CHECKING:
    from agent0.daemon import Scheduler

__all__ = ['REFLECTION_INTERVAL', 'REFLECTION_SCAN_INTERVAL', 'Reflector']

log = logging.getLogger(__name__)

REFLECTION_SCAN_INTERVAL = 20
"""Run reflection scan every N polls (~10 min at 30s interval)."""

REFLECTION_INTERVAL = 6
"""Trigger one reflection for every N new merged PRs reviewed."""

_RFC_TEMPLATE_PATH = '.github/ISSUE_TEMPLATE/rfc-template.md'


class Reflector:
    """
    Compute post-mortem self-reflection on merged PRs.

    Queries GitHub for merged PRs that Agent0 reviewed, accumulates
    new ones, and triggers a two-phase reflection every
    REFLECTION_INTERVAL merged PRs.

    Args:
        config (Config): Application configuration
        client (GitHubClient): GitHub API client for PR status checks
        scheduler (Scheduler): Task scheduler for per-repo locking

    Returns:
        Reflector: Self-reflection engine
    """

    def __init__(self, config: Config, client: GitHubClient, scheduler: Scheduler) -> None:
        self._config = config
        self._client = client
        self._scheduler = scheduler
        self._workspace_mgr = WorkspaceManager(config)
        self._reflections_file = config.data_dir / 'reflections.jsonl'
        self._considered: set[str] = set()
        self._load_considered()

    def _load_considered(self) -> None:
        """
        Compute in-memory set of already-considered PR keys from disk.

        Returns:
            None
        """

        if not self._reflections_file.exists():
            return

        try:
            text = self._reflections_file.read_text(encoding='utf-8')
            for line in text.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    pr_key = entry.get('pr_key', '')
                    if pr_key:
                        self._considered.add(pr_key)
                except (json.JSONDecodeError, TypeError):
                    continue
        except OSError:
            log.warning('Could not read reflections file: %s', self._reflections_file)

    def _record_considered(
        self,
        pr_key: str,
        reflected: bool,
        rfc_issue_url: str | None = None,
    ) -> None:
        """
        Compute append of a considered PR to the reflections file.

        Args:
            pr_key (str): PR identifier in owner/repo#number format
            reflected (bool): Whether reflection was triggered for this PR
            rfc_issue_url (str | None): URL of the created RFC issue, if any

        Returns:
            None
        """

        entry: dict[str, Any] = {
            'pr_key': pr_key,
            'timestamp': datetime.now(UTC).isoformat(),
            'reflected': reflected,
        }
        if rfc_issue_url:
            entry['rfc_issue_url'] = rfc_issue_url

        self._considered.add(pr_key)

        try:
            self._reflections_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._reflections_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except OSError:
            log.warning('Could not write to reflections file: %s', self._reflections_file)

    async def scan(self) -> None:
        """
        Compute scan for reflection candidates via GitHub Search API.

        Queries merged PRs that Agent0 reviewed across whitelisted orgs,
        filters out already-considered PRs, and triggers reflection when
        REFLECTION_INTERVAL new merged PRs have accumulated.

        Returns:
            None
        """

        merged_prs: list[dict[str, Any]] = []
        for org in self._config.whitelisted_orgs:
            items = await self._client.search_merged_prs_reviewed_by(self._config.github_user, org)
            merged_prs.extend(items)

        new_prs = [pr for pr in merged_prs if _pr_key_from_search_item(pr) not in self._considered]

        if len(new_prs) < REFLECTION_INTERVAL:
            log.info(
                'Reflection scan: %d new merged PRs, need %d to trigger',
                len(new_prs),
                REFLECTION_INTERVAL,
            )
            return

        target = random.choice(new_prs)
        target_key = _pr_key_from_search_item(target)
        owner, repo, number = _parse_search_item(target)

        if not owner:
            log.warning('Reflection scan: could not parse target PR from search results')
            return

        log.info(
            'Reflection scan: %d new merged PRs >= %d, reflecting on %s',
            len(new_prs),
            REFLECTION_INTERVAL,
            target_key,
        )

        rfc_url = await self._reflect(owner, repo, number)

        for pr in new_prs:
            key = _pr_key_from_search_item(pr)
            is_target = key == target_key
            self._record_considered(
                key,
                reflected=is_target,
                rfc_issue_url=rfc_url if is_target else None,
            )

    async def _gather_context(self, owner: str, repo: str, number: int) -> str:
        """
        Compute full interaction context for a closed PR.

        Fetches PR metadata, reviews, comments, CI status, and diff
        to build a comprehensive markdown record.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): PR number

        Returns:
            str: Formatted markdown context
        """

        pr = await self._client.get_pull_request(owner, repo, number)

        title = pr.get('title', '')
        body = pr.get('body', '') or '(no description)'
        merged = pr.get('merged', False)
        merged_at = pr.get('merged_at', '')
        closed_at = pr.get('closed_at', '')
        head_ref = pr.get('head', {}).get('ref', '')
        base_ref = pr.get('base', {}).get('ref', '')

        reviews = await self._client.get_pull_request_reviews(owner, repo, number)
        pr_comments = await self._client.get_pull_request_comments(owner, repo, number)
        issue_comments = await self._client.get_issue_comments(owner, repo, number)

        diff = await self._client.get_pull_request_diff(owner, repo, number)
        if len(diff) > 50_000:
            diff = diff[:50_000] + '\n\n[Diff truncated]'

        head_sha = pr.get('head', {}).get('sha', '')
        ci_summary = ''
        if head_sha:
            try:
                suites = await self._client.get_check_suites_for_ref(owner, repo, head_sha)
                ci_parts: list[str] = []
                for suite in suites:
                    app_name = suite.get('app', {}).get('name', 'unknown')
                    conclusion = suite.get('conclusion', 'pending')
                    ci_parts.append(f'- {app_name}: {conclusion}')
                ci_summary = '\n'.join(ci_parts) if ci_parts else '(no CI data)'
            except Exception:
                ci_summary = '(could not fetch CI data)'

        outcome = 'merged' if merged else 'closed without merge'
        outcome_time = merged_at if merged else closed_at

        sections = [
            f'# PR #{number}: {title}',
            f'**Repository:** {owner}/{repo}',
            f'**Branch:** {head_ref} → {base_ref}',
            f'**Outcome:** {outcome} ({outcome_time})',
            '',
            '## PR Description',
            body,
            '',
            '## Reviews',
            _format_reviews(reviews),
            '',
            '## Inline Review Comments',
            _format_pr_comments(pr_comments),
            '',
            '## Conversation',
            _format_issue_comments(issue_comments),
            '',
            '## CI Results',
            ci_summary,
            '',
            '## Diff',
            f'```diff\n{diff}\n```',
        ]

        return '\n\n'.join(sections)

    async def _reflect(self, owner: str, repo: str, number: int) -> str | None:
        """
        Compute two-phase self-reflection on a closed PR.

        Phase 1: Pure open-ended reflection (no RFC agenda).
        Phase 2: Channel reflection into a structured RFC issue.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): PR number

        Returns:
            str | None: URL of created RFC issue, or None
        """

        log.info('Starting self-reflection on %s/%s#%d', owner, repo, number)

        # Gather context from the reviewed repo (no workspace needed yet)
        full_context = await self._gather_context(owner, repo, number)

        agent0_owner, agent0_repo = _agent0_repo_parts(self._config)
        repo_key = f'{agent0_owner}/{agent0_repo}'
        lock = self._scheduler.get_repo_lock(repo_key)

        # Hold the Scheduler's per-repo lock for the entire reflection.
        # This guarantees no concurrent workspace access with scheduled tasks.
        async with lock:
            workspace = await self._workspace_mgr.prepare(agent0_owner, agent0_repo)

            # --- Phase 1: Pure reflection ---

            phase1_prompt = prompts.SELF_REFLECTION.format(
                number=number,
                owner=owner,
                repo=repo,
                full_context=full_context,
            )

            phase1_context = TaskContext(
                event_type='self_reflection',
                owner=agent0_owner,
                repo=agent0_repo,
                number=number,
                subject_type='PullRequest',
                trigger_user='self',
                trigger_text=phase1_prompt,
                issue_body=None,
                diff=None,
                comments=[],
                labels=[],
                head_ref=None,
                base_ref=None,
                notification_id=f'reflection-{owner}-{repo}-{number}',
            )

            log.info('Phase 1: reflecting on %s/%s#%d', owner, repo, number)
            phase1_result = await executor_run(
                phase1_context,
                str(workspace),
                self._config,
            )

            reflection_output = phase1_result.response or phase1_result.raw_output
            if not reflection_output or not reflection_output.strip():
                log.warning('Phase 1 produced no output for %s/%s#%d', owner, repo, number)
                return None

            log.info(
                'Phase 1 complete for %s/%s#%d (%.1fs, $%.4f)',
                owner,
                repo,
                number,
                phase1_result.duration_seconds,
                phase1_result.cost_usd,
            )

            # --- Phase 2: RFC creation ---

            rfc_template = _read_rfc_template(workspace)
            agent0_repo_full = f'{agent0_owner}/{agent0_repo}'

            phase2_prompt = prompts.SELF_REFLECTION_RFC.format(
                reflection_output=reflection_output,
                rfc_template=rfc_template,
                agent0_repo=agent0_repo_full,
            )

            phase2_context = TaskContext(
                event_type='self_reflection_rfc',
                owner=agent0_owner,
                repo=agent0_repo,
                number=number,
                subject_type='PullRequest',
                trigger_user='self',
                trigger_text=phase2_prompt,
                issue_body=None,
                diff=None,
                comments=[],
                labels=[],
                head_ref=None,
                base_ref=None,
                notification_id=f'reflection-rfc-{owner}-{repo}-{number}',
            )

            log.info('Phase 2: creating RFC from reflection on %s/%s#%d', owner, repo, number)
            phase2_result = await executor_run(
                phase2_context,
                str(workspace),
                self._config,
            )

        log.info(
            'Phase 2 complete for %s/%s#%d (%.1fs, $%.4f)',
            owner,
            repo,
            number,
            phase2_result.duration_seconds,
            phase2_result.cost_usd,
        )

        rfc_url = _extract_issue_url(phase2_result)
        if rfc_url:
            log.info('RFC created: %s', rfc_url)
        else:
            log.warning('Could not extract RFC issue URL from phase 2 output')

        return rfc_url


def _parse_pr_key(pr_key: str) -> tuple[str, str, int]:
    """
    Compute owner, repo, and number from a PR key.

    Args:
        pr_key (str): PR key in owner/repo#number format

    Returns:
        tuple[str, str, int]: Owner, repo, number (empty/0 on parse failure)
    """

    if '#' not in pr_key:
        return '', '', 0

    repo_part, number_str = pr_key.rsplit('#', 1)

    if '/' not in repo_part:
        return '', '', 0

    owner, repo = repo_part.split('/', 1)

    try:
        number = int(number_str)
    except ValueError:
        return '', '', 0

    return owner, repo, number


def _pr_key_from_search_item(item: dict[str, Any]) -> str:
    """
    Compute PR key from a GitHub Search API issue item.

    Args:
        item (dict[str, Any]): Search result item from /search/issues

    Returns:
        str: PR key in owner/repo#number format, or empty string on failure
    """

    repo_url = item.get('repository_url', '')
    number = item.get('number', 0)
    if not repo_url or not number:
        return ''

    parts = repo_url.rstrip('/').split('/')
    if len(parts) < 2:
        return ''

    owner = parts[-2]
    repo = parts[-1]
    return f'{owner}/{repo}#{number}'


def _parse_search_item(item: dict[str, Any]) -> tuple[str, str, int]:
    """
    Compute owner, repo, and number from a GitHub Search API issue item.

    Args:
        item (dict[str, Any]): Search result item from /search/issues

    Returns:
        tuple[str, str, int]: Owner, repo, number (empty/0 on parse failure)
    """

    repo_url = item.get('repository_url', '')
    number = item.get('number', 0)
    if not repo_url or not number:
        return '', '', 0

    parts = repo_url.rstrip('/').split('/')
    if len(parts) < 2:
        return '', '', 0

    return parts[-2], parts[-1], number


def _agent0_repo_parts(config: Config) -> tuple[str, str]:
    """
    Compute the owner and repo for Agent0 itself.

    Uses the first whitelisted org as the owner and config.agent0_repo
    as the repo name.

    Args:
        config (Config): Application configuration

    Returns:
        tuple[str, str]: Owner and repo name for Agent0
    """

    owner = config.whitelisted_orgs[0] if config.whitelisted_orgs else ''
    return owner, config.agent0_repo


def _read_rfc_template(workspace: Path) -> str:
    """
    Compute RFC template content from the workspace.

    Args:
        workspace (Path): Path to the Agent0 workspace

    Returns:
        str: RFC template content or fallback message
    """

    template_path = workspace / _RFC_TEMPLATE_PATH
    if template_path.exists():
        return template_path.read_text(encoding='utf-8')
    return '(RFC template not found — create a free-form RFC instead)'


def _extract_issue_url(result: ExecutorResult) -> str | None:
    """
    Compute RFC issue URL from executor output.

    Looks for a GitHub issue URL in the executor response or raw output.

    Args:
        result (ExecutorResult): Phase 2 executor result

    Returns:
        str | None: GitHub issue URL or None
    """

    text = result.response or result.raw_output or ''

    for line in text.splitlines():
        stripped = line.strip()
        if 'github.com' in stripped and '/issues/' in stripped:
            for word in stripped.split():
                if 'github.com' in word and '/issues/' in word:
                    url = word.strip('`"\'<>()[]')
                    if url.startswith('https://'):
                        return url

    return None


def _format_reviews(reviews: list[dict[str, Any]]) -> str:
    """
    Compute formatted review summary.

    Args:
        reviews (list[dict[str, Any]]): GitHub review objects

    Returns:
        str: Formatted review text
    """

    if not reviews:
        return '(no reviews)'

    parts: list[str] = []
    for review in reviews:
        user = review.get('user', {}).get('login', 'unknown')
        state = review.get('state', '')
        body = review.get('body', '') or ''
        submitted = review.get('submitted_at', '')
        entry = f'**{user}** [{state}] ({submitted})'
        if body.strip():
            entry += f'\n{body}'
        parts.append(entry)

    return '\n\n'.join(parts)


def _format_pr_comments(comments: list[dict[str, Any]]) -> str:
    """
    Compute formatted inline PR review comments.

    Args:
        comments (list[dict[str, Any]]): GitHub PR review comment objects

    Returns:
        str: Formatted comment text
    """

    if not comments:
        return '(no inline comments)'

    parts: list[str] = []
    for comment in comments:
        user = comment.get('user', {}).get('login', 'unknown')
        path = comment.get('path', '')
        line = comment.get('line') or comment.get('original_line', '')
        body = comment.get('body', '')
        parts.append(f'**{user}** on `{path}:{line}`:\n{body}')

    return '\n\n'.join(parts)


def _format_issue_comments(comments: list[dict[str, Any]]) -> str:
    """
    Compute formatted issue conversation comments.

    Args:
        comments (list[dict[str, Any]]): GitHub issue comment objects

    Returns:
        str: Formatted conversation text
    """

    if not comments:
        return '(no conversation)'

    parts: list[str] = []
    for comment in comments:
        user = comment.get('user', {}).get('login', 'unknown')
        body = comment.get('body', '')
        created = comment.get('created_at', '')
        parts.append(f'**{user}** ({created}):\n{body}')

    return '\n\n'.join(parts)
