from datetime import UTC, datetime, timedelta

from agent0.config import Config
from agent0.router import (
    _format_timestamp,
    classify,
    format_comments,
    is_reviewer_noise,
    is_self_triggered,
    should_process,
)


def _make_config() -> Config:
    """
    Compute test configuration.

    Returns:
        Config: Test config
    """

    return Config(
        github_token='test',
        anthropic_api_key='test',
        github_user='test-bot',
        claude_model='test-model',
        whitelisted_orgs=('testorg',),
    )


class TestShouldProcess:
    def test_mention(self) -> None:
        """
        Compute that mention reason is actionable.

        Returns:
            None
        """

        assert should_process({'reason': 'mention'}, _make_config())

    def test_assign(self) -> None:
        """
        Compute that assign reason is actionable.

        Returns:
            None
        """

        assert should_process({'reason': 'assign'}, _make_config())

    def test_review_requested(self) -> None:
        """
        Compute that review_requested reason is actionable.

        Returns:
            None
        """

        assert should_process({'reason': 'review_requested'}, _make_config())

    def test_ci_activity(self) -> None:
        """
        Compute that ci_activity reason is actionable.

        Returns:
            None
        """

        assert should_process({'reason': 'ci_activity'}, _make_config())

    def test_subscribed_not_actionable(self) -> None:
        """
        Compute that subscribed reason is not actionable.

        Returns:
            None
        """

        assert not should_process({'reason': 'subscribed'}, _make_config())

    def test_empty_reason_not_actionable(self) -> None:
        """
        Compute that empty reason is not actionable.

        Returns:
            None
        """

        assert not should_process({'reason': ''}, _make_config())


class TestClassify:
    def test_mention_event(self) -> None:
        """
        Compute that mention notification maps to mention event type.

        Returns:
            None
        """

        config = _make_config()
        notification = {
            'id': '123',
            'reason': 'mention',
            'subject': {'title': 'Test issue', 'type': 'Issue'},
        }
        context = {
            'owner': 'testorg',
            'repo': 'myrepo',
            'number': 42,
            'subject_type': 'Issue',
            'body': 'Fix the bug',
            'labels': ['bug'],
            'comments': [
                {'user': {'login': 'someuser'}, 'body': '@zero-bang help me', 'created_at': ''},
            ],
            'actor': 'someuser',
            'diff': None,
            'head_ref': None,
            'base_ref': None,
        }
        task = classify(notification, context, config)
        assert task.event_type == 'mention'
        assert task.owner == 'testorg'
        assert task.repo == 'myrepo'
        assert task.number == 42
        assert task.notification_id == '123'

    def test_assign_event(self) -> None:
        """
        Compute that assign notification maps to assignment event type.

        Returns:
            None
        """

        config = _make_config()
        notification = {
            'id': '456',
            'reason': 'assign',
            'subject': {'title': 'Implement feature', 'type': 'Issue'},
        }
        context = {
            'owner': 'testorg',
            'repo': 'myrepo',
            'number': 10,
            'subject_type': 'Issue',
            'body': 'Please implement X',
            'labels': ['feature'],
            'comments': [],
            'actor': '',
            'diff': None,
            'head_ref': None,
            'base_ref': None,
        }
        task = classify(notification, context, config)
        assert task.event_type == 'assignment'

    def test_review_request_event(self) -> None:
        """
        Compute that review_requested maps to review_request event type.

        Returns:
            None
        """

        config = _make_config()
        notification = {
            'id': '789',
            'reason': 'review_requested',
            'subject': {'title': 'Add feature', 'type': 'PullRequest'},
        }
        context = {
            'owner': 'testorg',
            'repo': 'myrepo',
            'number': 5,
            'subject_type': 'PullRequest',
            'body': 'Added feature X',
            'labels': [],
            'comments': [],
            'actor': '',
            'diff': 'diff --git a/file.py',
            'head_ref': 'feature-branch',
            'base_ref': 'main',
        }
        task = classify(notification, context, config)
        assert task.event_type == 'review_request'
        assert task.diff == 'diff --git a/file.py'
        assert task.head_ref == 'feature-branch'

    def test_review_request_becomes_re_review_when_agent_reviewed(self) -> None:
        """
        Compute that review_requested maps to re_review when agent has
        already reviewed the PR.

        Returns:
            None
        """

        config = _make_config()
        notification = {
            'id': '789',
            'reason': 'review_requested',
            'subject': {'title': 'Add feature', 'type': 'PullRequest'},
        }
        context = {
            'owner': 'testorg',
            'repo': 'myrepo',
            'number': 5,
            'subject_type': 'PullRequest',
            'body': 'Added feature X',
            'labels': [],
            'comments': [],
            'actor': '',
            'diff': 'diff --git a/file.py',
            'head_ref': 'feature-branch',
            'base_ref': 'main',
            'has_agent_reviewed': True,
        }
        task = classify(notification, context, config)
        assert task.event_type == 're_review'

    def test_review_request_stays_review_request_when_not_reviewed(self) -> None:
        """
        Compute that review_requested stays review_request when agent has
        NOT reviewed the PR yet.

        Returns:
            None
        """

        config = _make_config()
        notification = {
            'id': '789',
            'reason': 'review_requested',
            'subject': {'title': 'Add feature', 'type': 'PullRequest'},
        }
        context = {
            'owner': 'testorg',
            'repo': 'myrepo',
            'number': 5,
            'subject_type': 'PullRequest',
            'body': 'Added feature X',
            'labels': [],
            'comments': [],
            'actor': '',
            'diff': 'diff --git a/file.py',
            'head_ref': 'feature-branch',
            'base_ref': 'main',
            'has_agent_reviewed': False,
        }
        task = classify(notification, context, config)
        assert task.event_type == 'review_request'

    def test_ci_activity_event(self) -> None:
        """
        Compute that ci_activity notification maps to ci_failure event type.

        Returns:
            None
        """

        config = _make_config()
        notification = {
            'id': '999',
            'reason': 'ci_activity',
            'subject': {'title': 'CI run', 'type': 'CheckSuite'},
        }
        context = {
            'owner': 'testorg',
            'repo': 'myrepo',
            'number': 15,
            'subject_type': 'PullRequest',
            'body': 'Fix linting errors',
            'labels': [],
            'comments': [],
            'actor': '',
            'diff': 'diff --git a/lint.py',
            'head_ref': 'agent0/fix-lint',
            'base_ref': 'main',
            'check_failures': '### lint (failure)\nFlake8 found 3 errors',
        }
        task = classify(notification, context, config)
        assert task.event_type == 'ci_failure'
        assert task.trigger_text == '### lint (failure)\nFlake8 found 3 errors'
        assert task.number == 15

    def test_comment_is_actionable(self) -> None:
        """
        Compute that comment reason is actionable.

        Returns:
            None
        """

        assert should_process({'reason': 'comment'}, _make_config())

    def test_author_is_actionable(self) -> None:
        """
        Compute that author reason is actionable.

        Returns:
            None
        """

        assert should_process({'reason': 'author'}, _make_config())

    def test_comment_event(self) -> None:
        """
        Compute that comment notification maps to mention event type.

        Returns:
            None
        """

        config = _make_config()
        notification = {
            'id': '555',
            'reason': 'comment',
            'subject': {'title': 'Review feedback', 'type': 'PullRequest'},
        }
        context = {
            'owner': 'testorg',
            'repo': 'myrepo',
            'number': 20,
            'subject_type': 'PullRequest',
            'body': 'Fix the thing',
            'labels': [],
            'comments': [
                {
                    'user': {'login': 'reviewer'},
                    'body': '[CHANGES_REQUESTED] You must update pyproject.toml',
                    'created_at': '2026-03-01T19:18:05Z',
                },
            ],
            'actor': 'reviewer',
            'diff': 'diff --git a/file.py',
            'head_ref': 'feature-branch',
            'base_ref': 'main',
        }
        task = classify(notification, context, config)
        assert task.event_type == 'mention'
        assert 'You must update pyproject.toml' in task.trigger_text


class TestIsSelfTriggered:
    def test_self_triggered(self) -> None:
        """
        Compute that agent's own actions are detected.

        Returns:
            None
        """

        config = _make_config()
        context = {'actor': 'test-bot'}
        assert is_self_triggered(context, config)

    def test_case_insensitive(self) -> None:
        """
        Compute that self-detection is case-insensitive.

        Returns:
            None
        """

        config = _make_config()
        context = {'actor': 'Test-Bot'}
        assert is_self_triggered(context, config)

    def test_not_self_triggered(self) -> None:
        """
        Compute that other users are not self-triggered.

        Returns:
            None
        """

        config = _make_config()
        context = {'actor': 'someuser'}
        assert not is_self_triggered(context, config)


class TestIsReviewerNoise:
    def test_not_in_requested_reviewers_is_noise(self) -> None:
        """
        Compute that a non-authored PR where agent is not in requested_reviewers is noise.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'review_requested'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'other-user',
            'requested_reviewers': [],
        }
        assert is_reviewer_noise(notification, context, config)

    def test_in_requested_reviewers_is_not_noise(self) -> None:
        """
        Compute that a non-authored PR where agent IS in requested_reviewers is actionable.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'review_requested'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'other-user',
            'requested_reviewers': ['test-bot'],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_in_requested_reviewers_among_multiple(self) -> None:
        """
        Compute that agent among multiple requested reviewers is actionable.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'review_requested'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'other-user',
            'requested_reviewers': ['reviewer-a', 'test-bot', 'reviewer-b'],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_thread_update_reasons_are_noise(self) -> None:
        """
        Compute that thread-update reasons are noise when agent is
        not in requested_reviewers. GitHub threads retain their original
        reason (e.g. review_requested) across commits and comments.

        Returns:
            None
        """

        config = _make_config()
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'other-user',
            'requested_reviewers': [],
        }
        for reason in ('review_requested', 'comment', 'author', 'ci_activity'):
            notification = {'reason': reason}
            assert is_reviewer_noise(notification, context, config)

    def test_mention_is_never_noise(self) -> None:
        """
        Compute that @mention on a non-authored PR is always actionable,
        even when agent is not in requested_reviewers.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'mention'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'other-user',
            'requested_reviewers': [],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_assign_is_never_noise(self) -> None:
        """
        Compute that assignment on a non-authored PR is always actionable,
        even when agent is not in requested_reviewers.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'assign'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'other-user',
            'requested_reviewers': [],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_self_authored_pr_is_never_noise(self) -> None:
        """
        Compute that activity on agent's own PR is never noise,
        regardless of requested_reviewers.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'comment'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'test-bot',
            'requested_reviewers': [],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_issue_subject_is_never_noise(self) -> None:
        """
        Compute that Issue notifications are never reviewer noise.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'comment'}
        context = {
            'subject_type': 'Issue',
            'pr_author': 'other-user',
            'requested_reviewers': [],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_empty_pr_author_is_not_noise(self) -> None:
        """
        Compute that empty pr_author defensively passes through.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'review_requested'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': '',
            'requested_reviewers': [],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_missing_pr_author_key_is_not_noise(self) -> None:
        """
        Compute that missing pr_author key defensively passes through.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'review_requested'}
        context = {'subject_type': 'PullRequest', 'requested_reviewers': []}
        assert not is_reviewer_noise(notification, context, config)

    def test_case_insensitive_requested_reviewers(self) -> None:
        """
        Compute that requested_reviewers match is case-insensitive.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'review_requested'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'other-user',
            'requested_reviewers': ['Test-Bot'],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_case_insensitive_self_authored(self) -> None:
        """
        Compute that pr_author comparison is case-insensitive.

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'review_requested'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'Test-Bot',
            'requested_reviewers': [],
        }
        assert not is_reviewer_noise(notification, context, config)

    def test_missing_requested_reviewers_key_is_noise(self) -> None:
        """
        Compute that missing requested_reviewers key defaults to noise
        on a non-authored PR (empty list fallback).

        Returns:
            None
        """

        config = _make_config()
        notification = {'reason': 'review_requested'}
        context = {
            'subject_type': 'PullRequest',
            'pr_author': 'other-user',
        }
        assert is_reviewer_noise(notification, context, config)


class TestFormatComments:
    def test_empty_comments(self) -> None:
        """
        Compute that empty list returns placeholder.

        Returns:
            None
        """

        assert format_comments([]) == '(no comments)'

    def test_single_comment(self) -> None:
        """
        Compute that single comment formats correctly.

        Returns:
            None
        """

        comments = [
            {
                'user': {'login': 'alice'},
                'body': 'Hello world',
                'created_at': '2020-01-01T00:00:00Z',
            },
        ]
        result = format_comments(comments)
        assert '**alice**' in result
        assert 'Hello world' in result

    def test_multiple_comments_separated(self) -> None:
        """
        Compute that multiple comments are separated by dividers.

        Returns:
            None
        """

        comments = [
            {'user': {'login': 'alice'}, 'body': 'First', 'created_at': '2020-01-01T00:00:00Z'},
            {'user': {'login': 'bob'}, 'body': 'Second', 'created_at': '2020-01-01T01:00:00Z'},
        ]
        result = format_comments(comments)
        assert '---' in result
        assert '**alice**' in result
        assert '**bob**' in result


class TestFormatTimestamp:
    def test_just_now(self) -> None:
        """
        Compute that very recent timestamps show as just now.

        Returns:
            None
        """

        now = datetime.now(UTC)
        ts = now.isoformat().replace('+00:00', 'Z')
        result = _format_timestamp(ts, now)
        assert result == 'just now'

    def test_minutes_ago(self) -> None:
        """
        Compute that timestamps within an hour show minutes.

        Returns:
            None
        """

        now = datetime.now(UTC)
        ts = (now - timedelta(minutes=15)).isoformat().replace('+00:00', 'Z')
        result = _format_timestamp(ts, now)
        assert '15 minutes ago' in result

    def test_hours_ago(self) -> None:
        """
        Compute that timestamps within a day show hours.

        Returns:
            None
        """

        now = datetime.now(UTC)
        ts = (now - timedelta(hours=3)).isoformat().replace('+00:00', 'Z')
        result = _format_timestamp(ts, now)
        assert '3 hours ago' in result

    def test_old_timestamp_absolute(self) -> None:
        """
        Compute that timestamps older than a week show absolute format.

        Returns:
            None
        """

        now = datetime.now(UTC)
        ts = (now - timedelta(days=30)).isoformat().replace('+00:00', 'Z')
        result = _format_timestamp(ts, now)
        assert 'UTC' in result

    def test_invalid_timestamp(self) -> None:
        """
        Compute that invalid timestamp returns unknown.

        Returns:
            None
        """

        now = datetime.now(UTC)
        assert _format_timestamp('not-a-date', now) == 'unknown time'
