"""Tests for the error reporting system."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent0.errors import Agent0Error, ErrorCode, report_error


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_all_codes_are_strings(self) -> None:
        """All error codes should be usable as strings."""

        for code in ErrorCode:
            assert isinstance(code.value, str)
            assert code.value.startswith('E')

    def test_code_categories_complete(self) -> None:
        """All expected categories should have at least one code."""

        prefixes = {code.value[:2] for code in ErrorCode}
        assert prefixes == {'E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7'}


class TestAgent0Error:
    """Tests for Agent0Error dataclass."""

    def test_issue_title_format(self) -> None:
        """Issue title should follow conventional commit format."""

        error = Agent0Error(
            code=ErrorCode.E4002,
            summary='Execution timed out',
            detail='Timed out after 1800s',
        )
        title = error.issue_title()
        assert title == 'bug(executor): Execution timed out — E4002'

    def test_issue_title_config_scope(self) -> None:
        """Config errors should use config scope."""

        error = Agent0Error(
            code=ErrorCode.E1001,
            summary='Missing GITHUB_TOKEN',
            detail='',
        )
        assert 'bug(config)' in error.issue_title()

    def test_issue_body_contains_error_code(self) -> None:
        """Issue body should contain the error code."""

        error = Agent0Error(
            code=ErrorCode.E3001,
            summary='Git clone failed',
            detail='fatal: repo not found',
        )
        body = error.issue_body()
        assert '`E3001`' in body

    def test_issue_body_contains_related_url(self) -> None:
        """Issue body should include the related URL when present."""

        error = Agent0Error(
            code=ErrorCode.E4002,
            summary='Execution timed out',
            detail='Timed out after 1800s',
            related_url='https://github.com/Vaquum/someproject/pull/42',
        )
        body = error.issue_body()
        assert 'https://github.com/Vaquum/someproject/pull/42' in body

    def test_issue_body_contains_context_history(self) -> None:
        """Issue body should include numbered context steps."""

        error = Agent0Error(
            code=ErrorCode.E4002,
            summary='Execution timed out',
            detail='Timed out after 1800s',
            context_history=[
                'Received notification 12345',
                'Fetched PR context',
                'Spawned Claude Code CLI',
            ],
        )
        body = error.issue_body()
        assert '1. Received notification 12345' in body
        assert '2. Fetched PR context' in body
        assert '3. Spawned Claude Code CLI' in body

    def test_issue_body_contains_detail(self) -> None:
        """Issue body should contain the error detail in a code block."""

        error = Agent0Error(
            code=ErrorCode.E5001,
            summary='Audit write failed',
            detail='Permission denied: /data/audit/2026-03-11.jsonl',
        )
        body = error.issue_body()
        assert 'Permission denied' in body
        assert '```' in body

    def test_issue_body_without_optional_fields(self) -> None:
        """Issue body should work without related_url or context_history."""

        error = Agent0Error(
            code=ErrorCode.E7001,
            summary='Poll cycle error',
            detail='ConnectionError',
        )
        body = error.issue_body()
        assert '## Related' not in body
        assert '## Context History' not in body
        assert '`E7001`' in body

    def test_issue_body_contains_timestamp(self) -> None:
        """Issue body should include a timestamp section."""

        error = Agent0Error(
            code=ErrorCode.E2001,
            summary='Rate limited',
            detail='429 Too Many Requests',
        )
        body = error.issue_body()
        assert '## Timestamp' in body


class TestReportError:
    """Tests for report_error function."""

    def _mock_client(
        self,
        search_items: list | None = None,
        create_status: int = 201,
        create_url: str = 'https://github.com/Vaquum/Agent0/issues/99',
    ) -> MagicMock:
        """Build a mock GitHubClient with controllable responses."""

        client = MagicMock()

        search_response = MagicMock()
        search_response.status_code = 200
        search_response.json.return_value = {'items': search_items or []}

        create_response = MagicMock()
        create_response.status_code = create_status
        create_response.json.return_value = {'html_url': create_url}
        create_response.text = 'error text'

        async def mock_get(url: str, **kwargs: object) -> MagicMock:
            if '/search/issues' in url:
                return search_response
            return MagicMock()

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            return create_response

        client._client = MagicMock()
        client._client.get = AsyncMock(side_effect=mock_get)
        client._client.post = AsyncMock(side_effect=mock_post)

        return client

    @pytest.mark.asyncio
    async def test_creates_issue(self) -> None:
        """Should create a GitHub issue and return its URL."""

        client = self._mock_client()
        error = Agent0Error(
            code=ErrorCode.E4002,
            summary='Execution timed out',
            detail='Timed out after 1800s',
        )

        url = await report_error(error, client, 'Vaquum', 'Agent0')
        assert url == 'https://github.com/Vaquum/Agent0/issues/99'

        post_call = client._client.post.call_args
        payload = post_call.kwargs.get('json') or post_call[1].get('json')
        assert payload['labels'] == ['bug']
        assert 'E4002' in payload['title']
        assert 'bug(executor)' in payload['title']

    @pytest.mark.asyncio
    async def test_deduplicates_by_code_and_url(self) -> None:
        """Should skip creation if an open issue with same code and URL exists."""

        existing_issue = {
            'title': 'bug(executor): Execution timed out — E4002',
            'body': 'https://github.com/Vaquum/someproject/pull/42',
            'html_url': 'https://github.com/Vaquum/Agent0/issues/50',
        }
        client = self._mock_client(search_items=[existing_issue])
        error = Agent0Error(
            code=ErrorCode.E4002,
            summary='Execution timed out',
            detail='Timed out after 1800s',
            related_url='https://github.com/Vaquum/someproject/pull/42',
        )

        url = await report_error(error, client, 'Vaquum', 'Agent0')
        assert url == 'https://github.com/Vaquum/Agent0/issues/50'
        client._client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplicates_without_url(self) -> None:
        """Should deduplicate by code alone when no related_url."""

        existing_issue = {
            'title': 'bug(daemon): Poll cycle error — E7001',
            'body': '',
            'html_url': 'https://github.com/Vaquum/Agent0/issues/60',
        }
        client = self._mock_client(search_items=[existing_issue])
        error = Agent0Error(
            code=ErrorCode.E7001,
            summary='Poll cycle error',
            detail='ConnectionError',
        )

        url = await report_error(error, client, 'Vaquum', 'Agent0')
        assert url == 'https://github.com/Vaquum/Agent0/issues/60'
        client._client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_deduplicate_different_url(self) -> None:
        """Should create new issue if existing issue has different related URL."""

        existing_issue = {
            'title': 'bug(executor): Execution timed out — E4002',
            'body': 'https://github.com/Vaquum/other/pull/10',
            'html_url': 'https://github.com/Vaquum/Agent0/issues/50',
        }
        client = self._mock_client(search_items=[existing_issue])
        error = Agent0Error(
            code=ErrorCode.E4002,
            summary='Execution timed out',
            detail='Timed out after 1800s',
            related_url='https://github.com/Vaquum/someproject/pull/42',
        )

        url = await report_error(error, client, 'Vaquum', 'Agent0')
        assert url == 'https://github.com/Vaquum/Agent0/issues/99'
        client._client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_swallows_own_exceptions(self) -> None:
        """Should never raise, even if GitHub API fails completely."""

        client = MagicMock()
        client._client = MagicMock()
        client._client.get = AsyncMock(side_effect=RuntimeError('network down'))

        error = Agent0Error(
            code=ErrorCode.E7001,
            summary='Poll cycle error',
            detail='ConnectionError',
        )

        url = await report_error(error, client, 'Vaquum', 'Agent0')
        assert url is None

    @pytest.mark.asyncio
    async def test_handles_create_failure(self) -> None:
        """Should return None if issue creation returns non-201."""

        client = self._mock_client(create_status=403)
        error = Agent0Error(
            code=ErrorCode.E2002,
            summary='API request failed',
            detail='403 Forbidden',
        )

        url = await report_error(error, client, 'Vaquum', 'Agent0')
        assert url is None

    @pytest.mark.asyncio
    async def test_search_failure_falls_through_to_create(self) -> None:
        """Should attempt creation even if dedup search fails."""

        client = MagicMock()
        client._client = MagicMock()

        search_response = MagicMock()
        search_response.status_code = 500

        create_response = MagicMock()
        create_response.status_code = 201
        create_response.json.return_value = {
            'html_url': 'https://github.com/Vaquum/Agent0/issues/100'
        }

        async def mock_get(url: str, **kwargs: object) -> MagicMock:
            return search_response

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            return create_response

        client._client.get = AsyncMock(side_effect=mock_get)
        client._client.post = AsyncMock(side_effect=mock_post)

        error = Agent0Error(
            code=ErrorCode.E3001,
            summary='Git clone failed',
            detail='fatal: repo not found',
        )

        url = await report_error(error, client, 'Vaquum', 'Agent0')
        assert url == 'https://github.com/Vaquum/Agent0/issues/100'
