"""Structured error reporting with GitHub issue creation.

Provides error codes, structured error context, and automatic
issue creation in the Agent0 repository for operational errors.
"""

import logging
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent0.poller import GitHubClient

__all__ = ['Agent0Error', 'ErrorCode', 'report_error']

log = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    """
    Compute error code enum covering all Agent0 failure categories.

    Returns:
        ErrorCode: Typed error code string
    """

    # E1xxx — Config / Startup
    E1001 = 'E1001'  # Missing required env var
    E1002 = 'E1002'  # Invalid env var value
    E1003 = 'E1003'  # Empty org whitelist
    E1004 = 'E1004'  # GitHub auth mismatch

    # E2xxx — GitHub API
    E2001 = 'E2001'  # Rate limited
    E2002 = 'E2002'  # API request failed
    E2003 = 'E2003'  # Unexpected API response
    E2004 = 'E2004'  # Notification mark-read failed

    # E3xxx — Workspace / Git
    E3001 = 'E3001'  # Git clone failed
    E3002 = 'E3002'  # Git fetch failed
    E3003 = 'E3003'  # Git checkout failed
    E3004 = 'E3004'  # Git reset failed
    E3005 = 'E3005'  # Git clean failed

    # E4xxx — Executor / Claude Code
    E4001 = 'E4001'  # Claude CLI not found
    E4002 = 'E4002'  # Execution timed out
    E4003 = 'E4003'  # Execution failed (non-zero exit)
    E4004 = 'E4004'  # Output parse failed

    # E5xxx — Audit / Persistence
    E5001 = 'E5001'  # Audit write failed
    E5002 = 'E5002'  # Reflections file read failed
    E5003 = 'E5003'  # Reflections file write failed
    E5004 = 'E5004'  # Malformed audit entry

    # E6xxx — Reflector
    E6001 = 'E6001'  # Phase 1 produced no output
    E6002 = 'E6002'  # RFC issue URL not extracted
    E6003 = 'E6003'  # Reflection target unparseable

    # E7xxx — Poll Loop
    E7001 = 'E7001'  # Poll cycle error
    E7002 = 'E7002'  # CI scan error
    E7003 = 'E7003'  # Reflection scan error
    E7004 = 'E7004'  # Context fetch failed


# Map error codes to their scope for conventional commit titles
_CODE_SCOPES: dict[str, str] = {
    'E1': 'config',
    'E2': 'poller',
    'E3': 'workspace',
    'E4': 'executor',
    'E5': 'audit',
    'E6': 'reflector',
    'E7': 'daemon',
}


@dataclass
class Agent0Error:
    """
    Compute structured error with context for issue reporting.

    Args:
        code (ErrorCode): Categorized error code
        summary (str): One-line description of what went wrong
        detail (str): Full error message or traceback
        related_url (str | None): URL to the related PR/Issue/Action
        context_history (list[str]): Steps leading to the failure

    Returns:
        Agent0Error: Structured error ready for reporting
    """

    code: ErrorCode
    summary: str
    detail: str
    related_url: str | None = None
    context_history: list[str] = field(default_factory=list)

    def issue_title(self) -> str:
        """
        Compute GitHub issue title in conventional commit format.

        Returns:
            str: Issue title like 'bug(executor): Execution timed out — E4002'
        """

        scope = _CODE_SCOPES.get(self.code.value[:2], 'agent0')
        return f'bug({scope}): {self.summary} — {self.code.value}'

    def issue_body(self) -> str:
        """
        Compute GitHub issue body with full error context.

        Returns:
            str: Markdown-formatted issue body
        """

        sections = [
            f'## Error Code\n`{self.code.value}`',
            f'## What Agent0 Was Doing\n{self.summary}',
        ]

        if self.related_url:
            sections.append(f'## Related\n{self.related_url}')

        if self.context_history:
            steps = '\n'.join(f'{i + 1}. {step}' for i, step in enumerate(self.context_history))
            sections.append(f'## Context History\n{steps}')

        sections.append(f'## Error Detail\n```\n{self.detail}\n```')
        sections.append(f'## Timestamp\n{datetime.now(UTC).isoformat()}')

        return '\n\n'.join(sections)


async def report_error(
    error: Agent0Error,
    client: 'GitHubClient',
    owner: str,
    repo: str,
) -> str | None:
    """
    Compute GitHub issue creation for an Agent0 error.

    Creates a bug-labeled issue in the Agent0 repository. Deduplicates
    by checking for an existing open issue with the same error code and
    related URL. Never raises — catches its own exceptions to avoid
    cascading failures.

    Args:
        error (Agent0Error): Structured error to report
        client (GitHubClient): GitHub API client
        owner (str): Repository owner for issue creation
        repo (str): Repository name for issue creation

    Returns:
        str | None: URL of the created or existing issue, or None on failure
    """

    try:
        existing = await _find_existing_issue(error, client, owner, repo)
        if existing:
            log.info(
                'Skipping duplicate error report for %s, existing issue: %s',
                error.code.value,
                existing,
            )
            return existing

        issue_url = await _create_issue(error, client, owner, repo)
        if issue_url:
            log.info('Error report created: %s (%s)', issue_url, error.code.value)
        return issue_url

    except Exception:
        log.warning(
            'Failed to report error %s: %s',
            error.code.value,
            traceback.format_exc(),
        )
        return None


async def _find_existing_issue(
    error: Agent0Error,
    client: 'GitHubClient',
    owner: str,
    repo: str,
) -> str | None:
    """
    Compute search for an existing open issue matching this error.

    Args:
        error (Agent0Error): Error to check for duplicates
        client (GitHubClient): GitHub API client
        owner (str): Repository owner
        repo (str): Repository name

    Returns:
        str | None: URL of existing issue or None
    """

    search_query = f'repo:{owner}/{repo} is:issue is:open "{error.code.value}" in:title'

    response = await client._client.get(
        '/search/issues',
        params={'q': search_query, 'per_page': '5'},
    )

    if response.status_code != 200:
        return None

    data: dict[str, Any] = response.json()
    items = data.get('items', [])

    for item in items:
        title = item.get('title', '')
        if error.code.value not in title:
            continue

        if error.related_url:
            body = item.get('body', '') or ''
            if error.related_url in body:
                return item.get('html_url', '')
        else:
            return item.get('html_url', '')

    return None


async def _create_issue(
    error: Agent0Error,
    client: 'GitHubClient',
    owner: str,
    repo: str,
) -> str | None:
    """
    Compute GitHub issue creation.

    Args:
        error (Agent0Error): Error to report
        client (GitHubClient): GitHub API client
        owner (str): Repository owner
        repo (str): Repository name

    Returns:
        str | None: URL of the created issue or None
    """

    payload: dict[str, Any] = {
        'title': error.issue_title(),
        'body': error.issue_body(),
        'labels': ['bug'],
    }

    response = await client._client.post(
        f'/repos/{owner}/{repo}/issues',
        json=payload,
    )

    if response.status_code in (201, 200):
        data: dict[str, Any] = response.json()
        return data.get('html_url')

    log.warning(
        'Failed to create error issue (status=%d): %s',
        response.status_code,
        response.text[:500],
    )
    return None
