"""Tests for Agent0 reflector module."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent0.config import Config
from agent0.reflector import (
    REFLECTION_INTERVAL,
    Reflector,
    _extract_issue_url,
    _format_issue_comments,
    _format_pr_comments,
    _format_reviews,
    _parse_search_item,
    _pr_key_from_search_item,
)


def _make_config(tmp_path: Path) -> Config:
    return Config(
        github_token='test-token',
        anthropic_api_key='test-key',
        github_user='zero-bang',
        whitelisted_orgs=('vaquum',),
        data_dir=tmp_path,
    )


def _make_search_item(
    owner: str = 'vaquum',
    repo: str = 'confab',
    number: int = 14,
) -> dict:
    return {
        'number': number,
        'repository_url': f'https://api.github.com/repos/{owner}/{repo}',
        'title': f'Test PR #{number}',
        'html_url': f'https://github.com/{owner}/{repo}/pull/{number}',
    }



class TestPrKeyFromSearchItem:
    def test_valid_item(self) -> None:
        item = _make_search_item(owner='vaquum', repo='confab', number=14)
        assert _pr_key_from_search_item(item) == 'vaquum/confab#14'

    def test_missing_repo_url(self) -> None:
        assert _pr_key_from_search_item({'number': 14}) == ''

    def test_missing_number(self) -> None:
        item = {'repository_url': 'https://api.github.com/repos/vaquum/confab'}
        assert _pr_key_from_search_item(item) == ''


class TestParseSearchItem:
    def test_valid_item(self) -> None:
        item = _make_search_item(owner='vaquum', repo='confab', number=14)
        owner, repo, number = _parse_search_item(item)
        assert owner == 'vaquum'
        assert repo == 'confab'
        assert number == 14

    def test_missing_data(self) -> None:
        owner, _repo, number = _parse_search_item({})
        assert owner == ''
        assert number == 0


class TestLoadConsideredFromEmpty:
    def test_starts_empty(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        reflector = Reflector(config, AsyncMock(), AsyncMock())
        assert len(reflector._considered) == 0

    def test_no_file_no_error(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        reflector = Reflector(config, AsyncMock(), AsyncMock())
        assert reflector._considered == set()


class TestLoadConsideredFromExisting:
    def test_populates_from_file(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)

        reflections_file = tmp_path / 'reflections.jsonl'
        reflections_file.write_text(
            json.dumps({'pr_key': 'vaquum/confab#14', 'reflected': False})
            + '\n'
            + json.dumps({'pr_key': 'vaquum/agent0#22', 'reflected': True})
            + '\n',
            encoding='utf-8',
        )

        reflector = Reflector(config, AsyncMock(), AsyncMock())
        assert 'vaquum/confab#14' in reflector._considered
        assert 'vaquum/agent0#22' in reflector._considered
        assert len(reflector._considered) == 2


class TestDeduplication:
    def test_same_pr_key_only_considered_once(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        reflector = Reflector(config, AsyncMock(), AsyncMock())

        reflector._record_considered('vaquum/confab#14', reflected=False)
        reflector._record_considered('vaquum/confab#14', reflected=False)

        assert len(reflector._considered) == 1

        lines = (tmp_path / 'reflections.jsonl').read_text(encoding='utf-8').strip().splitlines()
        assert len(lines) == 2  # written twice, but set has 1 entry


class TestRecordConsideredWritesJsonl:
    def test_writes_to_file(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        reflector = Reflector(config, AsyncMock(), AsyncMock())

        reflector._record_considered('vaquum/confab#14', reflected=False)

        file_path = tmp_path / 'reflections.jsonl'
        assert file_path.exists()
        data = json.loads(file_path.read_text(encoding='utf-8').strip())
        assert data['pr_key'] == 'vaquum/confab#14'
        assert data['reflected'] is False
        assert 'timestamp' in data

    def test_writes_rfc_url(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        reflector = Reflector(config, AsyncMock(), AsyncMock())

        reflector._record_considered(
            'vaquum/confab#14',
            reflected=True,
            rfc_issue_url='https://github.com/Vaquum/Agent0/issues/25',
        )

        data = json.loads((tmp_path / 'reflections.jsonl').read_text(encoding='utf-8').strip())
        assert data['rfc_issue_url'] == 'https://github.com/Vaquum/Agent0/issues/25'


class TestScanBelowThreshold:
    @pytest.mark.asyncio
    async def test_no_reflection_below_interval(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mock_client = AsyncMock()
        mock_client.search_merged_prs_reviewed_by = AsyncMock(
            return_value=[_make_search_item(number=i) for i in range(1, 4)]
        )

        reflector = Reflector(config, mock_client, AsyncMock())

        with patch.object(reflector, '_reflect', new_callable=AsyncMock) as mock_reflect:
            await reflector.scan()
            mock_reflect.assert_not_called()

        assert len(reflector._considered) == 0


class TestScanTriggersAtThreshold:
    @pytest.mark.asyncio
    async def test_reflects_at_interval(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mock_client = AsyncMock()
        items = [_make_search_item(number=i) for i in range(1, REFLECTION_INTERVAL + 1)]
        mock_client.search_merged_prs_reviewed_by = AsyncMock(return_value=items)

        reflector = Reflector(config, mock_client, AsyncMock())

        with patch.object(
            reflector, '_reflect', new_callable=AsyncMock, return_value=None
        ) as mock_reflect:
            await reflector.scan()
            mock_reflect.assert_called_once()

        assert len(reflector._considered) == REFLECTION_INTERVAL


class TestScanMarksAllConsidered:
    @pytest.mark.asyncio
    async def test_all_prs_considered_after_trigger(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mock_client = AsyncMock()
        items = [_make_search_item(number=i) for i in range(1, 10)]
        mock_client.search_merged_prs_reviewed_by = AsyncMock(return_value=items)

        reflector = Reflector(config, mock_client, AsyncMock())

        with patch.object(reflector, '_reflect', new_callable=AsyncMock, return_value=None):
            await reflector.scan()

        assert len(reflector._considered) == 9


class TestScanSkipsAlreadyConsidered:
    @pytest.mark.asyncio
    async def test_already_considered_not_counted(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mock_client = AsyncMock()
        items = [_make_search_item(number=i) for i in range(1, 7)]
        mock_client.search_merged_prs_reviewed_by = AsyncMock(return_value=items)

        reflector = Reflector(config, mock_client, AsyncMock())
        # Pre-mark 4 as already considered
        for i in range(1, 5):
            reflector._considered.add(f'vaquum/confab#{i}')

        with patch.object(reflector, '_reflect', new_callable=AsyncMock) as mock_reflect:
            await reflector.scan()
            # Only 2 new (5 and 6), below threshold of 6
            mock_reflect.assert_not_called()


class TestScanReflectFailureDoesNotRecord:
    @pytest.mark.asyncio
    async def test_reflect_exception_leaves_prs_unconsidered(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mock_client = AsyncMock()
        items = [_make_search_item(number=i) for i in range(1, REFLECTION_INTERVAL + 1)]
        mock_client.search_merged_prs_reviewed_by = AsyncMock(return_value=items)

        reflector = Reflector(config, mock_client, AsyncMock())

        with (
            patch.object(
                reflector,
                '_reflect',
                new_callable=AsyncMock,
                side_effect=RuntimeError('executor crashed'),
            ),
            pytest.raises(RuntimeError, match='executor crashed'),
        ):
            await reflector.scan()

        assert len(reflector._considered) == 0


class TestScanMultipleOrgs:
    @pytest.mark.asyncio
    async def test_searches_each_whitelisted_org(self, tmp_path: Path) -> None:
        config = Config(
            github_token='test-token',
            anthropic_api_key='test-key',
            github_user='zero-bang',
            whitelisted_orgs=('orgA', 'orgB'),
            data_dir=tmp_path,
        )
        mock_client = AsyncMock()
        mock_client.search_merged_prs_reviewed_by = AsyncMock(return_value=[])

        reflector = Reflector(config, mock_client, AsyncMock())
        await reflector.scan()

        assert mock_client.search_merged_prs_reviewed_by.call_count == 2
        calls = mock_client.search_merged_prs_reviewed_by.call_args_list
        assert calls[0].args == ('zero-bang', 'orgA')
        assert calls[1].args == ('zero-bang', 'orgB')


class TestScanRecordsRfcUrl:
    @pytest.mark.asyncio
    async def test_rfc_url_recorded_for_target(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mock_client = AsyncMock()
        items = [_make_search_item(number=i) for i in range(1, REFLECTION_INTERVAL + 1)]
        mock_client.search_merged_prs_reviewed_by = AsyncMock(return_value=items)

        reflector = Reflector(config, mock_client, AsyncMock())
        rfc_url = 'https://github.com/Vaquum/Agent0/issues/99'

        with patch.object(reflector, '_reflect', new_callable=AsyncMock, return_value=rfc_url):
            await reflector.scan()

        lines = (tmp_path / 'reflections.jsonl').read_text(encoding='utf-8').strip().splitlines()
        entries = [json.loads(line) for line in lines]
        reflected_entries = [e for e in entries if e.get('reflected')]
        assert len(reflected_entries) == 1
        assert reflected_entries[0]['rfc_issue_url'] == rfc_url


class TestExtractIssueUrl:
    def test_extracts_url_from_response(self) -> None:
        from agent0.executor import ExecutorResult

        result = ExecutorResult(
            status='success',
            response='Created issue: https://github.com/Vaquum/Agent0/issues/25',
            error=None,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            num_turns=5,
            duration_seconds=10.0,
            raw_output='',
        )
        url = _extract_issue_url(result)
        assert url == 'https://github.com/Vaquum/Agent0/issues/25'

    def test_returns_none_for_no_url(self) -> None:
        from agent0.executor import ExecutorResult

        result = ExecutorResult(
            status='success',
            response='Done reflecting.',
            error=None,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            num_turns=5,
            duration_seconds=10.0,
            raw_output='',
        )
        url = _extract_issue_url(result)
        assert url is None

    def test_extracts_from_raw_output(self) -> None:
        from agent0.executor import ExecutorResult

        result = ExecutorResult(
            status='success',
            response=None,
            error=None,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            num_turns=5,
            duration_seconds=10.0,
            raw_output='Created https://github.com/Vaquum/Agent0/issues/30 successfully',
        )
        url = _extract_issue_url(result)
        assert url == 'https://github.com/Vaquum/Agent0/issues/30'


class TestFormatHelpers:
    def test_format_reviews_empty(self) -> None:
        assert _format_reviews([]) == '(no reviews)'

    def test_format_reviews_with_data(self) -> None:
        reviews = [
            {
                'user': {'login': 'alice'},
                'state': 'APPROVED',
                'body': 'LGTM',
                'submitted_at': '2026-03-05T10:00:00Z',
            }
        ]
        result = _format_reviews(reviews)
        assert 'alice' in result
        assert 'APPROVED' in result
        assert 'LGTM' in result

    def test_format_pr_comments_empty(self) -> None:
        assert _format_pr_comments([]) == '(no inline comments)'

    def test_format_pr_comments_with_data(self) -> None:
        comments = [
            {
                'user': {'login': 'bob'},
                'path': 'src/main.py',
                'line': 42,
                'body': 'Fix this',
            }
        ]
        result = _format_pr_comments(comments)
        assert 'bob' in result
        assert 'src/main.py:42' in result
        assert 'Fix this' in result

    def test_format_issue_comments_empty(self) -> None:
        assert _format_issue_comments([]) == '(no conversation)'

    def test_format_issue_comments_with_data(self) -> None:
        comments = [
            {
                'user': {'login': 'carol'},
                'body': 'Thanks!',
                'created_at': '2026-03-05T12:00:00Z',
            }
        ]
        result = _format_issue_comments(comments)
        assert 'carol' in result
        assert 'Thanks!' in result


class TestGatherContextStructure:
    @pytest.mark.asyncio
    async def test_all_sections_present(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)

        mock_client = AsyncMock()
        mock_client.get_pull_request = AsyncMock(
            return_value={
                'title': 'Test PR',
                'body': 'A test pull request',
                'state': 'closed',
                'merged': True,
                'merged_at': '2026-03-05T12:00:00Z',
                'closed_at': '2026-03-05T12:00:00Z',
                'head': {'ref': 'feature', 'sha': 'abc123'},
                'base': {'ref': 'main'},
            }
        )
        mock_client.get_pull_request_reviews = AsyncMock(return_value=[])
        mock_client.get_pull_request_comments = AsyncMock(return_value=[])
        mock_client.get_issue_comments = AsyncMock(return_value=[])
        mock_client.get_pull_request_diff = AsyncMock(return_value='diff content')
        mock_client.get_check_suites_for_ref = AsyncMock(return_value=[])

        reflector = Reflector(config, mock_client, AsyncMock())
        context = await reflector._gather_context('vaquum', 'confab', 14)

        assert '# PR #14: Test PR' in context
        assert 'vaquum/confab' in context
        assert 'feature' in context
        assert 'main' in context
        assert 'merged' in context
        assert '## PR Description' in context
        assert '## Reviews' in context
        assert '## Inline Review Comments' in context
        assert '## Conversation' in context
        assert '## CI Results' in context
        assert '## Diff' in context
