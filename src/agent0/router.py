import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent0.config import Config

__all__ = ['TaskContext', 'classify', 'is_reviewer_noise', 'should_process']

log = logging.getLogger(__name__)

ACTIONABLE_REASONS = {
    'mention',
    'assign',
    'review_requested',
    'ci_activity',
    'author',
    'comment',
}


@dataclass
class TaskContext:
    """
    Compute structured task context from a GitHub notification.

    Args:
        event_type (str): Type of event - mention, assignment, or review_request
        owner (str): Repository owner
        repo (str): Repository name
        number (int): Issue or PR number
        subject_type (str): Issue or PullRequest
        trigger_user (str): GitHub user who triggered the notification
        trigger_text (str): Text content that triggered the task
        issue_body (str | None): Issue or PR body in markdown
        diff (str | None): PR diff text, only for PullRequests
        comments (list[dict[str, Any]]): Conversation history
        labels (list[str]): Issue or PR labels
        head_ref (str | None): PR source branch
        base_ref (str | None): PR target branch
        notification_id (str): GitHub notification thread ID

    Returns:
        TaskContext: Structured context for the executor
    """

    event_type: str
    owner: str
    repo: str
    number: int
    subject_type: str
    trigger_user: str
    trigger_text: str
    issue_body: str | None
    diff: str | None
    comments: list[dict[str, Any]]
    labels: list[str]
    head_ref: str | None
    base_ref: str | None
    notification_id: str


def should_process(notification: dict[str, Any], config: Config) -> bool:
    """
    Compute whether a notification should be processed.

    Args:
        notification (dict[str, Any]): GitHub notification object
        config (Config): Application configuration

    Returns:
        bool: True if the notification is actionable
    """

    reason = notification.get('reason', '')
    subject_title = notification.get('subject', {}).get('title', '')
    if reason not in ACTIONABLE_REASONS:
        log.info('Skipping notification reason=%s subject=%s', reason, subject_title[:80])
        return False

    return True


def classify(
    notification: dict[str, Any],
    context: dict[str, Any],
    config: Config,
) -> TaskContext:
    """
    Compute TaskContext from notification and fetched context.

    Args:
        notification (dict[str, Any]): GitHub notification object
        context (dict[str, Any]): Fetched context from Poller.fetch_context
        config (Config): Application configuration

    Returns:
        TaskContext: Structured task context for the executor
    """

    reason = notification.get('reason', '')
    event_type = _reason_to_event_type(reason)

    actor = context.get('actor', '')
    trigger_text = _extract_trigger_text(notification, context, config)

    return TaskContext(
        event_type=event_type,
        owner=context.get('owner', ''),
        repo=context.get('repo', ''),
        number=context.get('number', 0),
        subject_type=context.get('subject_type', ''),
        trigger_user=actor,
        trigger_text=trigger_text,
        issue_body=context.get('body'),
        diff=context.get('diff'),
        comments=context.get('comments', []),
        labels=context.get('labels', []),
        head_ref=context.get('head_ref'),
        base_ref=context.get('base_ref'),
        notification_id=notification.get('id', ''),
    )


def is_self_triggered(context: dict[str, Any], config: Config) -> bool:
    """
    Compute whether the notification was triggered by the agent itself.

    Args:
        context (dict[str, Any]): Fetched context with actor info
        config (Config): Application configuration

    Returns:
        bool: True if the agent triggered this notification
    """

    actor = _as_str(context.get('actor', ''))
    return actor.lower() == config.github_user.lower()


def is_reviewer_noise(
    notification: dict[str, Any],
    context: dict[str, Any],
    config: Config,
) -> bool:
    """
    Compute whether a notification is ambient thread noise on a PR the agent reviews but did not author.

    On PRs authored by others, only formal review requests, explicit @mentions, and
    assignments are actionable. Everything else (comment, author, ci_activity) is
    thread noise that would cause duplicate re-reviews.

    Args:
        notification (dict[str, Any]): GitHub notification object
        context (dict[str, Any]): Fetched context with pr_author info
        config (Config): Application configuration

    Returns:
        bool: True if the notification is reviewer noise and should be skipped
    """

    if context.get('subject_type', '') != 'PullRequest':
        return False

    pr_author = _as_str(context.get('pr_author', ''))
    if not pr_author:
        return False

    if pr_author.lower() == config.github_user.lower():
        return False

    reason = notification.get('reason', '')
    return reason not in ('review_requested', 'mention', 'assign')


def format_comments(comments: list[dict[str, Any]]) -> str:
    """
    Compute formatted conversation thread from comment objects.

    Args:
        comments (list[dict[str, Any]]): List of GitHub comment objects

    Returns:
        str: Formatted conversation thread
    """

    if not comments:
        return '(no comments)'

    parts: list[str] = []
    now = datetime.now(UTC)

    for comment in comments:
        user = comment.get('user', {}).get('login', 'unknown')
        body = comment.get('body', '')
        created_at = comment.get('created_at', '')

        timestamp = _format_timestamp(created_at, now)
        parts.append(f'**{user}** ({timestamp}):\n{body}')

    return '\n\n---\n\n'.join(parts)


def _reason_to_event_type(reason: str) -> str:
    """
    Compute event type from notification reason.

    Args:
        reason (str): GitHub notification reason

    Returns:
        str: Normalized event type
    """

    mapping = {
        'mention': 'mention',
        'assign': 'assignment',
        'review_requested': 'review_request',
        'ci_activity': 'ci_failure',
        'author': 'mention',
        'comment': 'mention',
    }
    return mapping.get(reason, reason)


def _extract_trigger_text(
    notification: dict[str, Any],
    context: dict[str, Any],
    config: Config,
) -> str:
    """
    Compute trigger text from the notification context.

    Args:
        notification (dict[str, Any]): GitHub notification object
        context (dict[str, Any]): Fetched context
        config (Config): Application configuration

    Returns:
        str: The text that triggered the notification
    """

    reason = notification.get('reason', '')
    comments_raw = context.get('comments', [])
    comments = (
        [c for c in comments_raw if isinstance(c, dict)] if isinstance(comments_raw, list) else []
    )

    if reason == 'mention' and comments:
        last_comment_body = _as_str(comments[-1].get('body', ''))
        mention = f'@{config.github_user}'
        if mention.lower() in last_comment_body.lower():
            return last_comment_body

    if reason == 'author' and comments:
        return _as_str(comments[-1].get('body', '')) or _subject_title(notification)

    if reason == 'assign':
        return _as_str(context.get('body', '')) or _subject_title(notification)

    if reason == 'review_requested':
        return _as_str(context.get('body', '')) or _subject_title(notification)

    if reason == 'comment' and comments:
        return _as_str(comments[-1].get('body', '')) or _subject_title(notification)

    if reason == 'ci_activity':
        check_failures = _as_str(context.get('check_failures', ''))
        return check_failures or _subject_title(notification)

    return _subject_title(notification)


def _as_str(value: Any) -> str:
    """
    Compute a safe string from an untyped value.

    Args:
        value (Any): Arbitrary input value

    Returns:
        str: The value if already a string, otherwise empty string
    """

    return value if isinstance(value, str) else ''


def _subject_title(notification: dict[str, Any]) -> str:
    """
    Compute subject title from a GitHub notification dict.

    Args:
        notification (dict[str, Any]): GitHub notification object

    Returns:
        str: Subject title or empty string
    """

    subject = notification.get('subject', {})
    if not isinstance(subject, dict):
        return ''
    return _as_str(subject.get('title', ''))


def _format_timestamp(iso_timestamp: str, now: datetime) -> str:
    """
    Compute human-readable timestamp.

    Args:
        iso_timestamp (str): ISO 8601 timestamp
        now (datetime): Current time for relative formatting

    Returns:
        str: Formatted timestamp - relative if recent, absolute if older
    """

    if not iso_timestamp:
        return 'unknown time'

    try:
        dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        delta = now - dt
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return 'just now'
        if seconds < 3600:
            minutes = seconds // 60
            return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
        if seconds < 86400:
            hours = seconds // 3600
            return f'{hours} hour{"s" if hours != 1 else ""} ago'
        if seconds < 604800:
            days = seconds // 86400
            return f'{days} day{"s" if days != 1 else ""} ago'

        return dt.strftime('%Y-%m-%d %H:%M UTC')
    except (ValueError, AttributeError):
        return 'unknown time'
