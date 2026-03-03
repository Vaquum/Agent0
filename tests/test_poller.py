from typing import Any

import httpx
import pytest

from agent0.config import Config
from agent0.poller import (
    GitHubClient,
    Poller,
    RateLimited,
    _extract_number_from_url,
    _format_check_failures,
    _reviews_to_comments,
)


def _make_config() -> Config:

    '''
    Compute test configuration.

    Returns:
        Config: Test config with dummy tokens
    '''

    return Config(
        github_token='test-token',
        anthropic_api_key='test-key',
        whitelisted_orgs=('testorg', 'otherorg'),
    )


def _make_notification(
    notification_id: str = '1',
    reason: str = 'mention',
    owner: str = 'testorg',
    repo: str = 'myrepo',
    subject_type: str = 'Issue',
    subject_url: str = 'https://api.github.com/repos/testorg/myrepo/issues/42',
) -> dict[str, Any]:

    '''
    Compute test notification object.

    Args:
        notification_id (str): Notification ID
        reason (str): Notification reason
        owner (str): Repository owner
        repo (str): Repository name
        subject_type (str): Issue or PullRequest
        subject_url (str): API URL for the subject

    Returns:
        dict[str, Any]: GitHub notification object
    '''

    return {
        'id': notification_id,
        'reason': reason,
        'subject': {
            'title': 'Test issue',
            'url': subject_url,
            'type': subject_type,
        },
        'repository': {
            'full_name': f'{owner}/{repo}',
            'owner': {
                'login': owner,
            },
        },
        'updated_at': '2026-02-28T12:00:00Z',
    }


class TestExtractNumber:

    def test_issue_url(self) -> None:

        '''
        Compute number extraction from issue URL.

        Returns:
            None
        '''

        url = 'https://api.github.com/repos/owner/repo/issues/42'
        assert _extract_number_from_url(url) == 42

    def test_pull_url(self) -> None:

        '''
        Compute number extraction from PR URL.

        Returns:
            None
        '''

        url = 'https://api.github.com/repos/owner/repo/pulls/99'
        assert _extract_number_from_url(url) == 99

    def test_trailing_slash(self) -> None:

        '''
        Compute number extraction with trailing slash.

        Returns:
            None
        '''

        url = 'https://api.github.com/repos/owner/repo/issues/7/'
        assert _extract_number_from_url(url) == 7

    def test_no_number_returns_zero(self) -> None:

        '''
        Compute fallback when no number found.

        Returns:
            None
        '''

        url = 'https://api.github.com/repos/owner/repo'
        assert _extract_number_from_url(url) == 0


class TestPoller:

    @pytest.mark.asyncio
    async def test_filters_non_whitelisted_orgs(self) -> None:

        '''
        Compute that notifications from non-whitelisted orgs are dropped.

        Returns:
            None
        '''

        config = _make_config()

        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=[
                    _make_notification(owner='testorg', notification_id='1'),
                    _make_notification(owner='evilorg', notification_id='2'),
                ],
            ),
        )
        client = GitHubClient.__new__(GitHubClient)
        client._client = httpx.AsyncClient(transport=transport, base_url='https://api.github.com')

        poller = Poller(client, config)
        result = await poller.poll()

        assert len(result) == 1
        assert result[0]['id'] == '1'

    @pytest.mark.asyncio
    async def test_deduplication(self) -> None:

        '''
        Compute that already-processed notifications are skipped.

        Returns:
            None
        '''

        config = _make_config()
        notifications = [_make_notification(notification_id='1')]

        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=notifications),
        )
        client = GitHubClient.__new__(GitHubClient)
        client._client = httpx.AsyncClient(transport=transport, base_url='https://api.github.com')

        poller = Poller(client, config)
        result1 = await poller.poll()
        result2 = await poller.poll()

        assert len(result1) == 1
        assert len(result2) == 0

    @pytest.mark.asyncio
    async def test_304_returns_empty(self) -> None:

        '''
        Compute that 304 Not Modified returns empty list.

        Returns:
            None
        '''

        config = _make_config()

        transport = httpx.MockTransport(
            lambda request: httpx.Response(304),
        )
        client = GitHubClient.__new__(GitHubClient)
        client._client = httpx.AsyncClient(transport=transport, base_url='https://api.github.com')

        poller = Poller(client, config)
        result = await poller.poll()
        assert result == []

    @pytest.mark.asyncio
    async def test_429_raises_rate_limited(self) -> None:

        '''
        Compute that 429 response raises RateLimited with retry_after.

        Returns:
            None
        '''

        config = _make_config()

        transport = httpx.MockTransport(
            lambda request: httpx.Response(429, headers={'Retry-After': '120'}),
        )
        client = GitHubClient.__new__(GitHubClient)
        client._client = httpx.AsyncClient(transport=transport, base_url='https://api.github.com')

        poller = Poller(client, config)
        with pytest.raises(RateLimited) as exc_info:
            await poller.poll()
        assert exc_info.value.retry_after == 120

    @pytest.mark.asyncio
    async def test_case_insensitive_org_filter(self) -> None:

        '''
        Compute that org filtering is case-insensitive.

        Returns:
            None
        '''

        config = _make_config()

        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=[_make_notification(owner='TestOrg', notification_id='1')],
            ),
        )
        client = GitHubClient.__new__(GitHubClient)
        client._client = httpx.AsyncClient(transport=transport, base_url='https://api.github.com')

        poller = Poller(client, config)
        result = await poller.poll()
        assert len(result) == 1


class TestReviewsToComments:

    def test_converts_reviews_to_comments(self) -> None:

        '''
        Compute that reviews with bodies are converted to comment-shaped dicts.

        Returns:
            None
        '''

        reviews = [
            {
                'user': {'login': 'reviewer'},
                'body': 'You must update pyproject.toml',
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2026-03-01T19:18:05Z',
            },
        ]
        result = _reviews_to_comments(reviews)
        assert len(result) == 1
        assert result[0]['user']['login'] == 'reviewer'
        assert '[CHANGES_REQUESTED]' in result[0]['body']
        assert 'You must update pyproject.toml' in result[0]['body']
        assert result[0]['created_at'] == '2026-03-01T19:18:05Z'

    def test_skips_empty_body_reviews(self) -> None:

        '''
        Compute that reviews with empty bodies are excluded.

        Returns:
            None
        '''

        reviews = [
            {
                'user': {'login': 'reviewer'},
                'body': '',
                'state': 'APPROVED',
                'submitted_at': '2026-03-01T20:00:00Z',
            },
            {
                'user': {'login': 'reviewer'},
                'body': None,
                'state': 'COMMENTED',
                'submitted_at': '2026-03-01T20:01:00Z',
            },
        ]
        result = _reviews_to_comments(reviews)
        assert len(result) == 0

    def test_multiple_reviews(self) -> None:

        '''
        Compute that multiple reviews with bodies are all included.

        Returns:
            None
        '''

        reviews = [
            {
                'user': {'login': 'alice'},
                'body': 'LGTM',
                'state': 'APPROVED',
                'submitted_at': '2026-03-01T19:00:00Z',
            },
            {
                'user': {'login': 'bob'},
                'body': 'Needs changes',
                'state': 'CHANGES_REQUESTED',
                'submitted_at': '2026-03-01T19:30:00Z',
            },
        ]
        result = _reviews_to_comments(reviews)
        assert len(result) == 2
        assert result[0]['user']['login'] == 'alice'
        assert result[1]['user']['login'] == 'bob'


class TestFormatCheckFailures:

    def test_failed_runs(self) -> None:

        '''
        Compute that failed check runs are formatted with name and output.

        Returns:
            None
        '''

        check_runs = [
            {
                'name': 'lint',
                'conclusion': 'failure',
                'output': {
                    'title': 'Flake8 errors',
                    'summary': '3 errors found',
                    'text': 'E501 line too long',
                },
            },
            {
                'name': 'tests',
                'conclusion': 'success',
                'output': {'title': 'All passed', 'summary': '', 'text': ''},
            },
        ]
        result = _format_check_failures(check_runs)

        assert '### lint (failure)' in result
        assert 'Flake8 errors' in result
        assert '3 errors found' in result
        assert 'E501 line too long' in result
        assert 'tests' not in result

    def test_no_failures(self) -> None:

        '''
        Compute that all-success runs return placeholder.

        Returns:
            None
        '''

        check_runs = [
            {'name': 'tests', 'conclusion': 'success', 'output': {}},
        ]
        result = _format_check_failures(check_runs)
        assert result == '(no failed check details available)'

    def test_empty_runs(self) -> None:

        '''
        Compute that empty list returns placeholder.

        Returns:
            None
        '''

        result = _format_check_failures([])
        assert result == '(no failed check details available)'

    def test_timed_out_included(self) -> None:

        '''
        Compute that timed_out conclusion is included in failures.

        Returns:
            None
        '''

        check_runs = [
            {
                'name': 'build',
                'conclusion': 'timed_out',
                'output': {'title': 'Build timed out', 'summary': '', 'text': ''},
            },
        ]
        result = _format_check_failures(check_runs)
        assert '### build (timed_out)' in result
