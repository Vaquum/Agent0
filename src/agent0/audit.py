import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from agent0.config import Config

__all__ = ['AuditEntry', 'log_entry', 'read_entry_output', 'read_history']

log = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """
    Compute audit trail entry for a completed task.

    Args:
        timestamp (str): ISO 8601 UTC timestamp
        notification_id (str): GitHub notification thread ID
        event_type (str): Type of event that triggered the task
        repo (str): Repository in owner/repo format
        reference (int): Issue or PR number
        trigger_user (str): GitHub user who triggered the notification
        trigger_text (str): Text content that triggered the task
        action_taken (str): Brief summary of what was done
        status (str): Task outcome - success, failure, or timeout
        response (str | None): Claude Code text response
        input_tokens (int): Input tokens consumed
        output_tokens (int): Output tokens consumed
        cost_usd (float): Estimated cost in USD
        duration_seconds (float): Wall clock time in seconds
        error (str | None): Error message if task failed
        executor_output (list[str] | None): Formatted executor output lines

    Returns:
        AuditEntry: Structured audit log entry
    """

    timestamp: str
    notification_id: str
    event_type: str
    repo: str
    reference: int
    trigger_user: str
    trigger_text: str
    action_taken: str
    status: str
    response: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_seconds: float
    error: str | None
    executor_output: list[str] | None = None


def _date_from_timestamp(timestamp: str) -> str:
    """
    Compute date string from ISO 8601 timestamp.

    Args:
        timestamp (str): ISO 8601 UTC timestamp

    Returns:
        str: Date in YYYY-MM-DD format
    """

    return timestamp[:10]


def _audit_file_path(config: Config, date: str) -> Path:
    """
    Compute audit file path for a given date.

    Args:
        config (Config): Application configuration
        date (str): Date in YYYY-MM-DD format

    Returns:
        Path: Absolute path to the audit JSONL file
    """

    return config.audit_dir / f'{date}.jsonl'


async def log_entry(entry: AuditEntry, config: Config) -> None:
    """
    Compute audit log write by appending entry to daily JSONL file.

    Args:
        entry (AuditEntry): The audit entry to log
        config (Config): Application configuration

    Returns:
        None
    """

    date = _date_from_timestamp(entry.timestamp)
    file_path = _audit_file_path(config, date)
    line = json.dumps(asdict(entry), ensure_ascii=False) + '\n'

    def _write() -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(line)

    await asyncio.to_thread(_write)
    log.debug('Audit entry written to %s', file_path)


async def read_history(
    config: Config,
    page: int = 1,
    per_page: int = 50,
) -> list[AuditEntry]:
    """
    Compute paginated audit history from JSONL files, newest first.

    Args:
        config (Config): Application configuration
        page (int): Page number, 1-indexed
        per_page (int): Number of entries per page

    Returns:
        list[AuditEntry]: Paginated list of audit entries
    """

    def _read() -> list[AuditEntry]:
        audit_dir = config.audit_dir
        if not audit_dir.exists():
            return []

        files = sorted(audit_dir.glob('*.jsonl'), reverse=True)
        entries: list[AuditEntry] = []
        skip = (page - 1) * per_page
        collected = 0
        skipped = 0

        for file_path in files:
            lines = file_path.read_text(encoding='utf-8').strip().split('\n')
            for line in reversed(lines):
                if not line.strip():
                    continue
                if skipped < skip:
                    skipped += 1
                    continue
                try:
                    data = json.loads(line)
                    entries.append(AuditEntry(**data))
                    collected += 1
                    if collected >= per_page:
                        return entries
                except (json.JSONDecodeError, TypeError) as exc:
                    log.warning('Skipping malformed audit line in %s: %s', file_path, exc)
                    continue

        return entries

    return await asyncio.to_thread(_read)


async def read_entry_output(
    config: Config,
    notification_id: str,
    timestamp: str | None = None,
) -> list[str] | None:
    """
    Compute executor output lines for a specific audit entry.

    Args:
        config (Config): Application configuration
        notification_id (str): GitHub notification thread ID
        timestamp (str | None): Entry timestamp for disambiguation

    Returns:
        list[str] | None: Executor output lines or None if not found
    """

    def _read() -> list[str] | None:
        audit_dir = config.audit_dir
        if not audit_dir.exists():
            return None

        for file_path in sorted(audit_dir.glob('*.jsonl'), reverse=True):
            for line in file_path.read_text(encoding='utf-8').strip().split('\n'):
                if not line.strip():
                    continue
                if notification_id not in line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get('notification_id') != notification_id:
                        continue
                    if timestamp and data.get('timestamp') != timestamp:
                        continue
                    output = data.get('executor_output')
                    if output is None:
                        return None
                    if not isinstance(output, list):
                        return None
                    return [str(entry) for entry in output]
                except (json.JSONDecodeError, TypeError):
                    continue

        return None

    return await asyncio.to_thread(_read)
