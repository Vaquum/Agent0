import logging
from typing import Any, cast

import httpx

from agent0.config import Config

__all__ = ['GitHubClient', 'Poller', 'RateLimited']

log = logging.getLogger(__name__)

DIFF_TRUNCATION_LIMIT = 100_000
CHECK_FAILURE_TRUNCATION_LIMIT = 50_000


class RateLimited(Exception):
    """
    Compute rate limit exception with retry-after duration.

    Args:
        retry_after (int): Seconds to wait before retrying

    Returns:
        RateLimited: Exception indicating GitHub API rate limit hit
    """

    def __init__(self, retry_after: int) -> None:
        """
        Compute RateLimited exception.

        Args:
            retry_after (int): Seconds to wait before retrying

        Returns:
            None
        """

        super().__init__(f'Rate limited, retry after {retry_after}s')
        self.retry_after = retry_after


class GitHubClient:
    """
    Compute GitHub REST API interactions via async httpx.

    Args:
        token (str): GitHub Personal Access Token

    Returns:
        GitHubClient: Async GitHub API client
    """

    def __init__(self, token: str) -> None:
        """
        Compute GitHubClient instance.

        Args:
            token (str): GitHub PAT

        Returns:
            None
        """

        self._client = httpx.AsyncClient(
            base_url='https://api.github.com',
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            },
            timeout=30.0,
        )

    async def get_authenticated_user(self) -> dict[str, Any]:
        """
        Compute authenticated user info.

        Returns:
            dict[str, Any]: GitHub user object
        """

        response = await self._client.get('/user')
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_notifications(
        self,
        since: str | None = None,
        if_modified_since: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Compute unread participating notifications.

        Args:
            since (str | None): ISO 8601 timestamp to filter notifications
            if_modified_since (str | None): HTTP date for conditional request

        Returns:
            tuple[list[dict[str, Any]], str | None]: Notifications and Last-Modified header
        """

        params: dict[str, str] = {
            'all': 'false',
            'participating': 'true',
        }
        if since:
            params['since'] = since

        headers: dict[str, str] = {}
        if if_modified_since:
            headers['If-Modified-Since'] = if_modified_since

        response = await self._client.get('/notifications', params=params, headers=headers)

        if response.status_code == 304:
            return [], if_modified_since

        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', '60'))
            raise RateLimited(retry_after)

        response.raise_for_status()
        last_modified = response.headers.get('Last-Modified')
        payload = response.json()
        if not isinstance(payload, list):
            raise TypeError('Expected list payload from /notifications')
        if any(not isinstance(item, dict) for item in payload):
            raise TypeError('Expected notification objects in /notifications payload')
        return cast(list[dict[str, Any]], payload), last_modified

    async def mark_notification_read(self, thread_id: str) -> None:
        """
        Compute notification read status update.

        Args:
            thread_id (str): GitHub notification thread ID

        Returns:
            None
        """

        response = await self._client.patch(f'/notifications/threads/{thread_id}')
        response.raise_for_status()

    async def get_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """
        Compute issue details.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): Issue number

        Returns:
            dict[str, Any]: Issue object
        """

        response = await self._client.get(f'/repos/{owner}/{repo}/issues/{number}')
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_issue_comments(
        self,
        owner: str,
        repo: str,
        number: int,
    ) -> list[dict[str, Any]]:
        """
        Compute issue comments.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): Issue number

        Returns:
            list[dict[str, Any]]: List of comment objects
        """

        response = await self._client.get(f'/repos/{owner}/{repo}/issues/{number}/comments')
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """
        Compute pull request details.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): Issue number

        Returns:
            dict[str, Any]: Pull request object
        """

        response = await self._client.get(f'/repos/{owner}/{repo}/pulls/{number}')
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_pull_request_diff(self, owner: str, repo: str, number: int) -> str:
        """
        Compute pull request diff as raw text.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): PR number

        Returns:
            str: Raw diff text
        """

        response = await self._client.get(
            f'/repos/{owner}/{repo}/pulls/{number}',
            headers={'Accept': 'application/vnd.github.v3.diff'},
        )
        if response.status_code == 406:
            log.warning(
                'E2005: Diff unavailable (406) for %s/%s#%d',
                owner,
                repo,
                number,
            )
            return ''
        response.raise_for_status()
        return response.text

    async def get_pull_request_comments(
        self,
        owner: str,
        repo: str,
        number: int,
    ) -> list[dict[str, Any]]:
        """
        Compute pull request review comments.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): PR number

        Returns:
            list[dict[str, Any]]: List of review comment objects
        """

        response = await self._client.get(f'/repos/{owner}/{repo}/pulls/{number}/comments')
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_pull_request_reviews(
        self,
        owner: str,
        repo: str,
        number: int,
    ) -> list[dict[str, Any]]:
        """
        Compute pull request reviews.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            number (int): PR number

        Returns:
            list[dict[str, Any]]: List of review objects
        """

        response = await self._client.get(f'/repos/{owner}/{repo}/pulls/{number}/reviews')
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_comment(self, owner: str, repo: str, comment_id: int) -> dict[str, Any]:
        """
        Compute a specific issue comment.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            comment_id (int): Comment ID

        Returns:
            dict[str, Any]: Comment object
        """

        response = await self._client.get(
            f'/repos/{owner}/{repo}/issues/comments/{comment_id}',
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_check_suite(
        self,
        owner: str,
        repo: str,
        check_suite_id: int,
    ) -> dict[str, Any]:
        """
        Compute check suite details.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            check_suite_id (int): Check suite ID

        Returns:
            dict[str, Any]: Check suite object
        """

        response = await self._client.get(
            f'/repos/{owner}/{repo}/check-suites/{check_suite_id}',
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_check_runs_for_suite(
        self,
        owner: str,
        repo: str,
        check_suite_id: int,
    ) -> list[dict[str, Any]]:
        """
        Compute check runs belonging to a check suite.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            check_suite_id (int): Check suite ID

        Returns:
            list[dict[str, Any]]: List of check run objects
        """

        response = await self._client.get(
            f'/repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs',
        )
        response.raise_for_status()
        data = response.json()
        return data.get('check_runs', [])  # type: ignore[no-any-return]

    async def get_pull_requests_for_commit(
        self,
        owner: str,
        repo: str,
        sha: str,
    ) -> list[dict[str, Any]]:
        """
        Compute pull requests associated with a commit SHA.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            sha (str): Commit SHA

        Returns:
            list[dict[str, Any]]: List of pull request objects
        """

        response = await self._client.get(
            f'/repos/{owner}/{repo}/commits/{sha}/pulls',
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def search_open_prs_by_author(
        self,
        author: str,
        org: str,
    ) -> list[dict[str, Any]]:
        """
        Compute open PRs authored by a user within an organization.

        Args:
            author (str): GitHub username of the PR author
            org (str): GitHub organization or user to search in

        Returns:
            list[dict[str, Any]]: Search result items (issue-like objects)
        """

        response = await self._client.get(
            '/search/issues',
            params={'q': f'author:{author} type:pr is:open user:{org}'},
        )
        if response.status_code == 422:
            return []
        response.raise_for_status()
        data = response.json()
        return data.get('items', [])  # type: ignore[no-any-return]

    async def search_merged_prs_reviewed_by(
        self,
        reviewer: str,
        org: str,
    ) -> list[dict[str, Any]]:
        """
        Compute merged PRs reviewed by a user within an organization.

        Args:
            reviewer (str): GitHub username who submitted a review
            org (str): GitHub organization or user to search in

        Returns:
            list[dict[str, Any]]: Search result items (issue-like objects)
        """

        response = await self._client.get(
            '/search/issues',
            params={
                'q': f'reviewed-by:{reviewer} type:pr is:merged user:{org}',
                'sort': 'updated',
                'order': 'desc',
                'per_page': '100',
            },
        )
        if response.status_code == 422:
            return []
        response.raise_for_status()
        data = response.json()
        return data.get('items', [])  # type: ignore[no-any-return]

    async def get_check_suites_for_ref(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> list[dict[str, Any]]:
        """
        Compute check suites for a commit reference.

        Args:
            owner (str): Repository owner
            repo (str): Repository name
            ref (str): Commit SHA or branch name

        Returns:
            list[dict[str, Any]]: List of check suite objects
        """

        response = await self._client.get(
            f'/repos/{owner}/{repo}/commits/{ref}/check-suites',
        )
        response.raise_for_status()
        data = response.json()
        return data.get('check_suites', [])  # type: ignore[no-any-return]

    async def close(self) -> None:
        """
        Compute client shutdown.

        Returns:
            None
        """

        await self._client.aclose()


class Poller:
    """
    Compute GitHub notification polling with filtering and context fetching.

    Args:
        client (GitHubClient): GitHub API client
        config (Config): Application configuration

    Returns:
        Poller: Notification poller instance
    """

    def __init__(self, client: GitHubClient, config: Config) -> None:
        """
        Compute Poller instance.

        Args:
            client (GitHubClient): GitHub API client
            config (Config): Application configuration

        Returns:
            None
        """

        self._client = client
        self._config = config
        self._processed_timestamps: dict[str, str] = {}
        self._last_modified: str | None = None
        self._poll_count: int = 0
        self._ci_checked: dict[str, str] = {}

    async def poll(self) -> list[dict[str, Any]]:
        """
        Compute unread actionable notifications from GitHub.

        Resets the If-Modified-Since cache every 10 polls to avoid
        getting stuck on stale 304 responses from GitHub.

        Returns:
            list[dict[str, Any]]: Filtered notification objects
        """

        FRESH_POLL_INTERVAL = 10

        self._poll_count += 1
        use_cache = self._poll_count % FRESH_POLL_INTERVAL != 0

        notifications, last_modified = await self._client.get_notifications(
            if_modified_since=self._last_modified if use_cache else None,
        )
        if last_modified:
            self._last_modified = last_modified

        if not notifications:
            return []

        result: list[dict[str, Any]] = []
        for notification in notifications:
            notification_id = notification.get('id', '')
            updated_at = notification.get('updated_at', '')

            if self._processed_timestamps.get(notification_id) == updated_at:
                continue

            owner = notification.get('repository', {}).get('owner', {}).get('login', '')
            if owner.lower() not in {org.lower() for org in self._config.whitelisted_orgs}:
                log.debug('Skipping notification from non-whitelisted org: %s', owner)
                continue

            result.append(notification)
            self._processed_timestamps[notification_id] = updated_at

        if len(self._processed_timestamps) > 500:
            keep = dict(
                sorted(
                    self._processed_timestamps.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:200]
            )
            self._processed_timestamps = keep

        log.info('Poll returned %d actionable notifications', len(result))
        return result

    async def mark_read(self, thread_id: str) -> None:
        """
        Compute notification read status update.

        Args:
            thread_id (str): GitHub notification thread ID

        Returns:
            None
        """

        await self._client.mark_notification_read(thread_id)

    async def scan_ci_failures(self) -> list[dict[str, Any]]:
        """
        Compute synthetic notifications for CI failures on agent-authored open PRs.

        Searches for open PRs by the agent across whitelisted orgs, checks
        their CI status, and returns notification-shaped dicts for any new
        failures. Tracks checked SHAs to avoid reprocessing the same failure.

        Returns:
            list[dict[str, Any]]: Synthetic notification objects for failed CI checks
        """

        results: list[dict[str, Any]] = []
        current_keys: set[str] = set()

        for org in self._config.whitelisted_orgs:
            try:
                items = await self._client.search_open_prs_by_author(
                    self._config.github_user,
                    org,
                )
            except Exception:
                log.warning('E2002: CI scan: search failed for org %s', org)
                continue

            for item in items:
                repo_url = item.get('repository_url', '')
                parts = repo_url.rstrip('/').split('/')
                if len(parts) < 2:
                    continue
                owner, repo = parts[-2], parts[-1]
                number = item.get('number', 0)
                key = f'{owner}/{repo}#{number}'
                current_keys.add(key)

                try:
                    pr = await self._client.get_pull_request(owner, repo, number)
                except Exception:
                    log.warning('E2002: CI scan: failed to fetch PR %s/%s#%d', owner, repo, number)
                    continue

                head_sha = pr.get('head', {}).get('sha', '')
                if not head_sha:
                    continue

                if self._ci_checked.get(key) == head_sha:
                    continue

                try:
                    suites = await self._client.get_check_suites_for_ref(
                        owner,
                        repo,
                        head_sha,
                    )
                except Exception:
                    log.warning(
                        'E2002: CI scan: failed to fetch check suites for %s/%s@%s',
                        owner,
                        repo,
                        head_sha[:8],
                    )
                    continue

                if not suites:
                    continue

                all_completed = all(s.get('status') == 'completed' for s in suites)
                if not all_completed:
                    continue

                self._ci_checked[key] = head_sha

                failed = [s for s in suites if s.get('conclusion') == 'failure']
                if not failed:
                    continue

                suite_id = failed[0].get('id', 0)
                log.info('CI scan: found failure on %s (suite %d)', key, suite_id)

                results.append(
                    {
                        'id': f'ci-scan-{suite_id}',
                        'reason': 'ci_activity',
                        'subject': {
                            'type': 'CheckSuite',
                            'url': f'https://api.github.com/repos/{owner}/{repo}/check-suites/{suite_id}',
                        },
                        'repository': {
                            'full_name': f'{owner}/{repo}',
                            'owner': {'login': owner},
                        },
                        'updated_at': pr.get('updated_at', ''),
                    }
                )

        stale = set(self._ci_checked) - current_keys
        for k in stale:
            del self._ci_checked[k]

        return results

    async def fetch_context(self, notification: dict[str, Any]) -> dict[str, Any]:
        """
        Compute full context for a notification by fetching issue/PR details.

        Args:
            notification (dict[str, Any]): GitHub notification object

        Returns:
            dict[str, Any]: Context dict with issue/PR body, comments, diff, actor info
        """

        subject = notification.get('subject', {})
        subject_type = subject.get('type', '')
        subject_url = subject.get('url', '')
        repo_full = notification.get('repository', {}).get('full_name', '')
        owner, repo = repo_full.split('/', 1) if '/' in repo_full else ('', '')
        number = _extract_number_from_url(subject_url)

        context: dict[str, Any] = {
            'subject_type': subject_type,
            'owner': owner,
            'repo': repo,
            'number': number,
        }

        if subject_type == 'CheckSuite':
            return await self._fetch_check_suite_context(context, owner, repo, number)

        if subject_type == 'PullRequest':
            pr = await self._client.get_pull_request(owner, repo, number)
            context['title'] = pr.get('title', '')
            context['body'] = pr.get('body', '') or ''
            context['head_ref'] = pr.get('head', {}).get('ref', '')
            context['base_ref'] = pr.get('base', {}).get('ref', '')
            context['labels'] = [lb.get('name', '') for lb in pr.get('labels', [])]
            context['pr_author'] = pr.get('user', {}).get('login', '')

            diff = await self._client.get_pull_request_diff(owner, repo, number)
            if len(diff) > DIFF_TRUNCATION_LIMIT:
                diff = (
                    diff[:DIFF_TRUNCATION_LIMIT]
                    + f'\n\n[Diff truncated — {len(diff)} characters total, '
                    f'showing first {DIFF_TRUNCATION_LIMIT}]'
                )
            context['diff'] = diff

            issue_comments = await self._client.get_issue_comments(owner, repo, number)
            pr_comments = await self._client.get_pull_request_comments(owner, repo, number)
            reviews = await self._client.get_pull_request_reviews(owner, repo, number)
            review_comments = _reviews_to_comments(reviews)
            all_comments = issue_comments + pr_comments + review_comments
            all_comments.sort(key=lambda c: c.get('created_at', ''))
            context['comments'] = all_comments

        else:
            issue = await self._client.get_issue(owner, repo, number)
            context['title'] = issue.get('title', '')
            context['body'] = issue.get('body', '') or ''
            context['labels'] = [lb.get('name', '') for lb in issue.get('labels', [])]
            context['head_ref'] = None
            context['base_ref'] = None
            context['diff'] = None

            comments = await self._client.get_issue_comments(owner, repo, number)
            context['comments'] = comments

        last_comment = context['comments'][-1] if context['comments'] else {}
        context['actor'] = last_comment.get('user', {}).get('login', '')

        return context

    async def _fetch_check_suite_context(
        self,
        context: dict[str, Any],
        owner: str,
        repo: str,
        check_suite_id: int,
    ) -> dict[str, Any]:
        """
        Compute context for a CheckSuite notification by resolving the associated PR.

        Args:
            context (dict[str, Any]): Partially built context dict
            owner (str): Repository owner
            repo (str): Repository name
            check_suite_id (int): Check suite ID extracted from subject URL

        Returns:
            dict[str, Any]: Full context with PR details and check failure summaries
        """

        suite = await self._client.get_check_suite(owner, repo, check_suite_id)
        conclusion = suite.get('conclusion', '')
        head_sha = suite.get('head_sha', '')

        if conclusion != 'failure':
            log.debug('CheckSuite %d concluded with %s, skipping', check_suite_id, conclusion)
            context['skip'] = True
            return context

        prs = await self._client.get_pull_requests_for_commit(owner, repo, head_sha)
        agent_pr = None
        for pr in prs:
            pr_author = pr.get('user', {}).get('login', '')
            if pr_author.lower() == self._config.github_user.lower() and pr.get('state') == 'open':
                agent_pr = pr
                break

        if agent_pr is None:
            log.debug('No open PR by %s for SHA %s, skipping', self._config.github_user, head_sha)
            context['skip'] = True
            return context

        pr_head_sha = agent_pr.get('head', {}).get('sha', '')
        if head_sha != pr_head_sha:
            log.debug(
                'CheckSuite SHA %s does not match PR head %s, skipping',
                head_sha[:8],
                pr_head_sha[:8],
            )
            context['skip'] = True
            return context

        pr_number = agent_pr.get('number', 0)
        context['subject_type'] = 'PullRequest'
        context['number'] = pr_number
        context['title'] = agent_pr.get('title', '')
        context['body'] = agent_pr.get('body', '') or ''
        context['head_ref'] = agent_pr.get('head', {}).get('ref', '')
        context['base_ref'] = agent_pr.get('base', {}).get('ref', '')
        context['labels'] = [lb.get('name', '') for lb in agent_pr.get('labels', [])]

        diff = await self._client.get_pull_request_diff(owner, repo, pr_number)
        if len(diff) > DIFF_TRUNCATION_LIMIT:
            diff = (
                diff[:DIFF_TRUNCATION_LIMIT]
                + f'\n\n[Diff truncated — {len(diff)} characters total, '
                f'showing first {DIFF_TRUNCATION_LIMIT}]'
            )
        context['diff'] = diff

        issue_comments = await self._client.get_issue_comments(owner, repo, pr_number)
        pr_comments = await self._client.get_pull_request_comments(owner, repo, pr_number)
        reviews = await self._client.get_pull_request_reviews(owner, repo, pr_number)
        review_comments = _reviews_to_comments(reviews)
        all_comments = issue_comments + pr_comments + review_comments
        all_comments.sort(key=lambda c: c.get('created_at', ''))
        context['comments'] = all_comments

        check_runs = await self._client.get_check_runs_for_suite(owner, repo, check_suite_id)
        context['check_failures'] = _format_check_failures(check_runs)
        context['actor'] = ''

        return context


def _reviews_to_comments(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Compute comment-shaped dicts from pull request review objects.

    Args:
        reviews (list[dict[str, Any]]): GitHub review objects

    Returns:
        list[dict[str, Any]]: Comment-compatible dicts with user, body, created_at
    """

    result: list[dict[str, Any]] = []
    for review in reviews:
        body = review.get('body', '') or ''
        if not body.strip():
            continue
        state = review.get('state', '')
        result.append(
            {
                'user': review.get('user', {}),
                'body': f'[{state}] {body}',
                'created_at': review.get('submitted_at', ''),
            }
        )
    return result


def _extract_number_from_url(url: str) -> int:
    """
    Compute issue/PR number from GitHub API URL.

    Args:
        url (str): GitHub API URL ending in a number

    Returns:
        int: The issue or PR number
    """

    parts = url.rstrip('/').split('/')
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return 0


def _format_check_failures(check_runs: list[dict[str, Any]]) -> str:
    """
    Compute human-readable summary of failed check runs.

    Args:
        check_runs (list[dict[str, Any]]): Check run objects from GitHub API

    Returns:
        str: Formatted failure summary with check names and output
    """

    parts: list[str] = []
    total_len = 0

    for run in check_runs:
        conclusion = run.get('conclusion', '')
        if conclusion not in ('failure', 'timed_out', 'cancelled'):
            continue

        name = run.get('name', 'unknown')
        output = run.get('output', {}) or {}
        title = output.get('title', '') or ''
        summary = output.get('summary', '') or ''
        text = output.get('text', '') or ''

        entry = f'### {name} ({conclusion})\n'
        if title:
            entry += f'{title}\n'
        if summary:
            entry += f'{summary}\n'
        if text:
            entry += f'{text}\n'

        total_len += len(entry)
        if total_len > CHECK_FAILURE_TRUNCATION_LIMIT:
            parts.append(
                f'[Check failure output truncated at {CHECK_FAILURE_TRUNCATION_LIMIT} chars]'
            )
            break

        parts.append(entry)

    if not parts:
        return '(no failed check details available)'

    return '\n'.join(parts)
