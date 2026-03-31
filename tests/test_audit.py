import json
from pathlib import Path

import pytest

from agent0.audit import AuditEntry, log_entry, read_entry_output, read_history
from agent0.config import Config


def _make_config(tmp_path: Path) -> Config:
    """
    Compute test config with tmp_path as data directory.

    Args:
        tmp_path (Path): Pytest temporary directory

    Returns:
        Config: Test configuration
    """

    return Config(
        github_token='test',
        anthropic_api_key='test',
        github_user='test-bot',
        claude_model='test-model',
        whitelisted_orgs=('testorg',),
        data_dir=tmp_path,
    )


def _make_entry(
    timestamp: str = '2026-02-28T12:00:00Z',
    notification_id: str = '123',
    status: str = 'success',
) -> AuditEntry:
    """
    Compute test audit entry with sensible defaults.

    Args:
        timestamp (str): ISO 8601 UTC timestamp
        notification_id (str): Notification ID
        status (str): Task status

    Returns:
        AuditEntry: Test audit entry
    """

    return AuditEntry(
        timestamp=timestamp,
        notification_id=notification_id,
        event_type='mention',
        repo='mikkokotila/test-repo',
        reference=42,
        trigger_user='someuser',
        trigger_text='@zero-bang help',
        action_taken='Commented on issue',
        status=status,
        response='Done',
        input_tokens=1000,
        output_tokens=200,
        cost_usd=0.01,
        duration_seconds=5.5,
        error=None,
    )


class TestLogEntry:
    @pytest.mark.asyncio
    async def test_creates_file_and_writes(self, tmp_path: Path) -> None:
        """
        Compute that log_entry creates the audit file and writes a valid JSON line.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        entry = _make_entry()
        await log_entry(entry, config)

        file_path = config.audit_dir / '2026-02-28.jsonl'
        assert file_path.exists()
        lines = file_path.read_text().strip().split('\n')
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data['notification_id'] == '123'
        assert data['status'] == 'success'

    @pytest.mark.asyncio
    async def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        """
        Compute that log_entry appends to an existing audit file.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        entry1 = _make_entry(notification_id='100')
        entry2 = _make_entry(notification_id='200')
        await log_entry(entry1, config)
        await log_entry(entry2, config)

        file_path = config.audit_dir / '2026-02-28.jsonl'
        lines = file_path.read_text().strip().split('\n')
        assert len(lines) == 2
        assert json.loads(lines[0])['notification_id'] == '100'
        assert json.loads(lines[1])['notification_id'] == '200'

    @pytest.mark.asyncio
    async def test_different_dates_separate_files(self, tmp_path: Path) -> None:
        """
        Compute that entries with different dates go to different files.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        entry1 = _make_entry(timestamp='2026-02-27T10:00:00Z')
        entry2 = _make_entry(timestamp='2026-02-28T10:00:00Z')
        await log_entry(entry1, config)
        await log_entry(entry2, config)

        assert (config.audit_dir / '2026-02-27.jsonl').exists()
        assert (config.audit_dir / '2026-02-28.jsonl').exists()


class TestReadHistory:
    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_path: Path) -> None:
        """
        Compute that read_history returns empty list when no audit files exist.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        result = await read_history(config)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_newest_first(self, tmp_path: Path) -> None:
        """
        Compute that read_history returns entries newest first.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        await log_entry(_make_entry(timestamp='2026-02-27T10:00:00Z', notification_id='1'), config)
        await log_entry(_make_entry(timestamp='2026-02-27T11:00:00Z', notification_id='2'), config)
        await log_entry(_make_entry(timestamp='2026-02-28T09:00:00Z', notification_id='3'), config)

        result = await read_history(config)
        ids = [e.notification_id for e in result]
        assert ids == ['3', '2', '1']

    @pytest.mark.asyncio
    async def test_pagination(self, tmp_path: Path) -> None:
        """
        Compute that read_history paginates correctly.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        for i in range(5):
            await log_entry(
                _make_entry(
                    timestamp=f'2026-02-28T{10 + i:02d}:00:00Z',
                    notification_id=str(i),
                ),
                config,
            )

        page1 = await read_history(config, page=1, per_page=2)
        assert len(page1) == 2
        assert page1[0].notification_id == '4'
        assert page1[1].notification_id == '3'

        page2 = await read_history(config, page=2, per_page=2)
        assert len(page2) == 2
        assert page2[0].notification_id == '2'
        assert page2[1].notification_id == '1'

        page3 = await read_history(config, page=3, per_page=2)
        assert len(page3) == 1
        assert page3[0].notification_id == '0'

    @pytest.mark.asyncio
    async def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        """
        Compute that malformed JSON lines are skipped gracefully.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        await log_entry(_make_entry(notification_id='good'), config)

        file_path = config.audit_dir / '2026-02-28.jsonl'
        with open(file_path, 'a') as f:
            f.write('not valid json\n')

        result = await read_history(config)
        assert len(result) == 1
        assert result[0].notification_id == 'good'


class TestReadEntryOutput:
    @pytest.mark.asyncio
    async def test_returns_output_lines(self, tmp_path: Path) -> None:
        """
        Compute that read_entry_output returns stored executor output.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        entry = _make_entry(notification_id='abc')
        entry.executor_output = ['> Bash: git status', 'Let me check', 'Done (3 turns, $0.05)']
        await log_entry(entry, config)

        result = await read_entry_output(config, 'abc')

        assert result is not None
        assert len(result) == 3
        assert result[0] == '> Bash: git status'
        assert result[2] == 'Done (3 turns, $0.05)'

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, tmp_path: Path) -> None:
        """
        Compute that read_entry_output returns None for unknown notification.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        await log_entry(_make_entry(notification_id='existing'), config)

        result = await read_entry_output(config, 'nonexistent')

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_entry_without_output(self, tmp_path: Path) -> None:
        """
        Compute that read_entry_output returns None for entry without executor_output.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        entry = _make_entry(notification_id='no-output')
        await log_entry(entry, config)

        result = await read_entry_output(config, 'no-output')

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_audit_dir(self, tmp_path: Path) -> None:
        """
        Compute that read_entry_output returns None when audit dir is empty.

        Returns:
            None
        """

        config = _make_config(tmp_path)

        result = await read_entry_output(config, 'anything')

        assert result is None
