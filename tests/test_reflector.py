"""Tests for Agent0 reflector module."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent0.config import Config
from agent0.reflector import (
    Reflector,
    _extract_issue_url,
    _format_issue_comments,
    _format_pr_comments,
    _format_reviews,
    _parse_pr_key,
)


def _make_config(tmp_path: Path) -> Config:
    return Config(
        github_token='test-token',
        anthropic_api_key='test-key',
        github_user='zero-bang',
        whitelisted_orgs=('vaquum',),
        data_dir=tmp_path,
    )


def _make_audit_entry(
    event_type: str = 'review_request',
    repo: str = 'vaquum/confab',
    reference: int = 14,
) -> dict:
    return {
        'timestamp': '2026-03-05T10:00:00+00:00',
        'notification_id': 'notif-123',
        'event_type': event_type,
        'repo': repo,
        'reference': reference,
        'trigger_user': 'alice',
        'trigger_text': 'review please',
        'action_taken': event_type,
        'status': 'success',
        'response': 'LGTM',
        'input_tokens': 1000,
        'output_tokens': 500,
        'cost_usd': 0.05,
        'duration_seconds': 30.0,
        'error': None,
    }


class TestParsePrKey:
    def test_valid_key(self) -> None:
        owner, repo, number = _parse_pr_key('vaquum/confab#14')
        assert owner == 'vaquum'
        assert repo == 'confab'
        assert number == 14

    def test_no_hash(self) -> None:
        owner, _repo, number = _parse_pr_key('vaquum/confab')
        assert owner == ''
        assert number == 0

    def test_no_slash(self) -> None:
        owner, _repo, number = _parse_pr_key('confab#14')
        assert owner == ''
        assert number == 0

    def test_non_numeric_number(self) -> None:
        owner, _repo, number = _parse_pr_key('vaquum/confab#abc')
        assert owner == ''
        assert number == 0

    def test_empty_string(self) -> None:
        owner, _repo, number = _parse_pr_key('')
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
            json.dumps({'pr_key': 'vaquum/confab#14', 'dice_landed': False})
            + '\n'
            + json.dumps({'pr_key': 'vaquum/agent0#22', 'dice_landed': True})
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

        reflector._record_considered('vaquum/confab#14', dice_landed=False)
        reflector._record_considered('vaquum/confab#14', dice_landed=False)

        assert len(reflector._considered) == 1

        lines = (tmp_path / 'reflections.jsonl').read_text(encoding='utf-8').strip().splitlines()
        assert len(lines) == 2  # written twice, but set has 1 entry


class TestRecordConsideredWritesJsonl:
    def test_writes_to_file(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        reflector = Reflector(config, AsyncMock(), AsyncMock())

        reflector._record_considered('vaquum/confab#14', dice_landed=False)

        file_path = tmp_path / 'reflections.jsonl'
        assert file_path.exists()
        data = json.loads(file_path.read_text(encoding='utf-8').strip())
        assert data['pr_key'] == 'vaquum/confab#14'
        assert data['dice_landed'] is False
        assert 'timestamp' in data

    def test_writes_rfc_url(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        reflector = Reflector(config, AsyncMock(), AsyncMock())

        reflector._record_considered(
            'vaquum/confab#14',
            dice_landed=True,
            rfc_issue_url='https://github.com/Vaquum/Agent0/issues/25',
        )

        data = json.loads((tmp_path / 'reflections.jsonl').read_text(encoding='utf-8').strip())
        assert data['rfc_issue_url'] == 'https://github.com/Vaquum/Agent0/issues/25'


class TestSkipNonReviewEntries:
    def test_only_review_request_entries(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        audit_dir = tmp_path / 'audit'
        audit_dir.mkdir()

        entries = [
            _make_audit_entry(event_type='mention', repo='vaquum/confab', reference=10),
            _make_audit_entry(event_type='review_request', repo='vaquum/confab', reference=14),
            _make_audit_entry(event_type='assignment', repo='vaquum/confab', reference=15),
            _make_audit_entry(event_type='ci_failure', repo='vaquum/confab', reference=14),
        ]

        audit_file = audit_dir / '2026-03-05.jsonl'
        audit_file.write_text(
            '\n'.join(json.dumps(e) for e in entries) + '\n',
            encoding='utf-8',
        )

        reflector = Reflector(config, AsyncMock(), AsyncMock())
        pr_keys = reflector._find_review_pr_keys()

        assert pr_keys == ['vaquum/confab#14']


class TestSkipOpenPR:
    @pytest.mark.asyncio
    async def test_does_not_reflect_on_open_pr(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        audit_dir = tmp_path / 'audit'
        audit_dir.mkdir()

        entry = _make_audit_entry(event_type='review_request', repo='vaquum/confab', reference=14)
        audit_file = audit_dir / '2026-03-05.jsonl'
        audit_file.write_text(json.dumps(entry) + '\n', encoding='utf-8')

        mock_client = AsyncMock()
        mock_client.get_pull_request = AsyncMock(return_value={'state': 'open'})

        reflector = Reflector(config, mock_client, AsyncMock())

        with patch('agent0.reflector.random') as mock_random:
            await reflector.scan()
            mock_random.randint.assert_not_called()

        assert 'vaquum/confab#14' not in reflector._considered


class TestReflectionTriggered:
    @pytest.mark.asyncio
    async def test_closed_pr_dice_lands_calls_reflect(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        audit_dir = tmp_path / 'audit'
        audit_dir.mkdir()

        entry = _make_audit_entry(event_type='review_request', repo='vaquum/confab', reference=14)
        audit_file = audit_dir / '2026-03-05.jsonl'
        audit_file.write_text(json.dumps(entry) + '\n', encoding='utf-8')

        mock_client = AsyncMock()
        mock_client.get_pull_request = AsyncMock(return_value={'state': 'closed'})

        reflector = Reflector(config, mock_client, AsyncMock())

        with (
            patch('agent0.reflector.random') as mock_random,
            patch.object(
                reflector, '_reflect', new_callable=AsyncMock, return_value=None
            ) as mock_reflect,
        ):
            mock_random.randint.return_value = 1
            await reflector.scan()

            mock_reflect.assert_called_once_with('vaquum', 'confab', 14)

        assert 'vaquum/confab#14' in reflector._considered


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
