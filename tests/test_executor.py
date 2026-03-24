import json

from agent0.config import Config
from agent0.executor import (
    ExecutorResult,
    _build_prompt,
    _extract_result_from_list,
    _format_stream_line,
    _parse_output,
)
from agent0.router import TaskContext


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
        whitelisted_orgs=('testorg',),
    )


def _make_context(**overrides) -> TaskContext:
    """
    Compute test TaskContext with sensible defaults.

    Args:
        **overrides: Fields to override

    Returns:
        TaskContext: Test context
    """

    defaults = {
        'event_type': 'mention',
        'owner': 'testorg',
        'repo': 'myrepo',
        'number': 42,
        'subject_type': 'Issue',
        'trigger_user': 'someuser',
        'trigger_text': '@zero-bang help me',
        'issue_body': 'Fix the bug',
        'diff': None,
        'comments': [
            {'user': {'login': 'someuser'}, 'body': '@zero-bang help me', 'created_at': ''},
        ],
        'labels': ['bug'],
        'head_ref': None,
        'base_ref': None,
        'notification_id': '123',
    }
    defaults.update(overrides)
    return TaskContext(**defaults)


class TestBuildPrompt:
    def test_preamble_present(self) -> None:
        """
        Compute that prompt contains preamble with repo info.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context()
        prompt = _build_prompt(ctx, config)

        assert 'You are Agent0' in prompt
        assert 'testorg/myrepo' in prompt
        assert 'Never force push' in prompt

    def test_whitelisted_orgs_in_preamble(self) -> None:
        """
        Compute that whitelisted orgs appear in the prompt preamble.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context()
        prompt = _build_prompt(ctx, config)

        assert 'testorg' in prompt

    def test_mention_issue_prompt(self) -> None:
        """
        Compute that mention in issue generates correct prompt structure.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='mention',
            subject_type='Issue',
            issue_body='Something is broken',
            trigger_text='@zero-bang what is wrong?',
        )
        prompt = _build_prompt(ctx, config)

        assert 'mentioned in a comment on issue #42' in prompt
        assert 'Something is broken' in prompt
        assert '@zero-bang what is wrong?' in prompt
        assert 'gh issue comment' in prompt

    def test_mention_pr_prompt(self) -> None:
        """
        Compute that mention in PR generates correct prompt structure.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='mention',
            subject_type='PullRequest',
            issue_body='Added new feature',
            diff='diff --git a/file.py b/file.py',
            trigger_text='@zero-bang looks good?',
        )
        prompt = _build_prompt(ctx, config)

        assert 'mentioned in a comment on PR #42' in prompt
        assert 'Added new feature' in prompt
        assert 'diff --git a/file.py' in prompt
        assert 'gh pr comment' in prompt

    def test_assignment_prompt(self) -> None:
        """
        Compute that assignment generates correct prompt structure.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='assignment',
            subject_type='Issue',
            issue_body='Please implement dark mode',
            labels=['feature', 'ui'],
        )
        prompt = _build_prompt(ctx, config)

        assert 'assigned to issue #42' in prompt
        assert 'Please implement dark mode' in prompt
        assert 'feature, ui' in prompt
        assert 'Create a branch named agent0/' in prompt
        assert 'Closes #42' in prompt

    def test_review_request_prompt(self) -> None:
        """
        Compute that review request generates correct prompt structure.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='review_request',
            subject_type='PullRequest',
            issue_body='Refactored auth module',
            diff='diff --git a/auth.py b/auth.py',
            head_ref='feature-auth',
            base_ref='main',
        )
        prompt = _build_prompt(ctx, config)

        assert 'asked to review PR #42' in prompt
        assert 'Refactored auth module' in prompt
        assert 'feature-auth' in prompt
        assert 'main' in prompt
        assert 'gh pr review' in prompt
        assert '--approve' in prompt

    def test_review_request_uses_inline_comments(self) -> None:
        """
        Compute that review request prompt instructs inline review comments.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='review_request',
            subject_type='PullRequest',
            issue_body='Added feature',
            diff='diff --git a/file.py b/file.py',
            head_ref='feature-branch',
            base_ref='main',
        )
        prompt = _build_prompt(ctx, config)

        assert 'inline review comments' in prompt.lower() or 'inline comment' in prompt.lower()
        assert 'NEVER use `gh pr comment`' in prompt
        assert 'reviews --method POST --input' in prompt

    def test_re_review_uses_dedicated_prompt(self) -> None:
        """
        Compute that re_review event type uses the RE_REVIEW_PR prompt.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='re_review',
            subject_type='PullRequest',
            issue_body='Added feature',
            diff='diff --git a/file.py b/file.py',
            head_ref='feature-branch',
            base_ref='main',
        )
        prompt = _build_prompt(ctx, config)

        assert 're-review' in prompt.lower()
        assert 'without any additional comments' in prompt
        assert 'gh pr review' in prompt

    def test_review_request_has_no_rereview_logic(self) -> None:
        """
        Compute that review_request prompt does NOT contain re-review logic.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='review_request',
            subject_type='PullRequest',
            issue_body='Added feature',
            diff='diff --git a/file.py b/file.py',
            head_ref='feature-branch',
            base_ref='main',
        )
        prompt = _build_prompt(ctx, config)

        assert 'RE-REVIEW' not in prompt
        assert 'Do NOT look for new issues' not in prompt

    def test_review_request_includes_owner_repo(self) -> None:
        """
        Compute that review prompt includes owner/repo for API calls.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='review_request',
            subject_type='PullRequest',
            issue_body='Added feature',
            diff='diff --git a/file.py b/file.py',
            head_ref='feature-branch',
            base_ref='main',
        )
        prompt = _build_prompt(ctx, config)

        assert 'repos/testorg/myrepo/pulls/42/reviews' in prompt
        assert 'zero-bang' in prompt

    def test_no_body_fallback(self) -> None:
        """
        Compute that missing issue body shows placeholder.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(issue_body=None)
        prompt = _build_prompt(ctx, config)

        assert '(no description)' in prompt

    def test_no_labels_fallback(self) -> None:
        """
        Compute that empty labels list shows placeholder.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(event_type='assignment', labels=[])
        prompt = _build_prompt(ctx, config)

        assert '(none)' in prompt

    def test_ci_failure_prompt(self) -> None:
        """
        Compute that ci_failure event generates correct prompt structure.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(
            event_type='ci_failure',
            subject_type='PullRequest',
            issue_body='Fix linting errors',
            diff='diff --git a/lint.py b/lint.py',
            trigger_text='### lint (failure)\nFlake8 found 3 errors',
            head_ref='agent0/fix-lint',
            base_ref='main',
        )
        prompt = _build_prompt(ctx, config)

        assert 'CI checks have failed' in prompt
        assert '#42' in prompt
        assert 'agent0/fix-lint' in prompt
        assert 'Flake8 found 3 errors' in prompt
        assert 'gh pr comment' in prompt
        assert 'Fix the failing checks' in prompt

    def test_unknown_event_type(self) -> None:
        """
        Compute that unknown event type produces fallback prompt.

        Returns:
            None
        """

        config = _make_config()
        ctx = _make_context(event_type='unknown_type')
        prompt = _build_prompt(ctx, config)

        assert 'unknown_type' in prompt


class TestParseOutput:
    def test_valid_json(self) -> None:
        """
        Compute that valid JSON output is parsed correctly.

        Returns:
            None
        """

        data = {
            'result': 'I fixed the bug',
            'is_error': False,
            'total_cost_usd': 0.05,
            'total_input_tokens': 1000,
            'total_output_tokens': 500,
            'num_turns': 3,
        }
        parsed = _parse_output(json.dumps(data))

        assert parsed['result'] == 'I fixed the bug'
        assert parsed['is_error'] is False
        assert parsed['total_cost_usd'] == 0.05
        assert parsed['total_input_tokens'] == 1000
        assert parsed['total_output_tokens'] == 500
        assert parsed['num_turns'] == 3

    def test_error_response(self) -> None:
        """
        Compute that error response is parsed correctly.

        Returns:
            None
        """

        data = {
            'result': 'Something went wrong',
            'is_error': True,
            'total_cost_usd': 0.01,
            'total_input_tokens': 100,
            'total_output_tokens': 10,
            'num_turns': 1,
        }
        parsed = _parse_output(json.dumps(data))

        assert parsed['is_error'] is True
        assert parsed['result'] == 'Something went wrong'

    def test_invalid_json(self) -> None:
        """
        Compute that invalid JSON returns error result with raw text.

        Returns:
            None
        """

        parsed = _parse_output('not valid json at all')

        assert parsed['is_error'] is True
        assert parsed['result'] == 'not valid json at all'
        assert parsed['total_cost_usd'] == 0.0
        assert parsed['total_input_tokens'] == 0

    def test_empty_string(self) -> None:
        """
        Compute that empty string returns error result.

        Returns:
            None
        """

        parsed = _parse_output('')

        assert parsed['is_error'] is True

    def test_missing_fields_default(self) -> None:
        """
        Compute that missing fields get default values.

        Returns:
            None
        """

        parsed = _parse_output('{}')

        assert parsed['result'] == ''
        assert parsed['is_error'] is False
        assert parsed['total_cost_usd'] == 0.0
        assert parsed['total_input_tokens'] == 0
        assert parsed['total_output_tokens'] == 0
        assert parsed['num_turns'] == 0

    def test_verbose_list_output(self) -> None:
        """
        Compute that verbose JSON array output is parsed correctly.

        Returns:
            None
        """

        data = [
            {'type': 'assistant', 'message': {'content': 'thinking'}},
            {'type': 'tool_use', 'name': 'bash'},
            {
                'type': 'result',
                'result': 'Fixed the lint errors',
                'is_error': False,
                'total_cost_usd': 0.12,
                'total_input_tokens': 5000,
                'total_output_tokens': 2000,
                'num_turns': 5,
            },
        ]
        parsed = _parse_output(json.dumps(data))

        assert parsed['result'] == 'Fixed the lint errors'
        assert parsed['is_error'] is False
        assert parsed['total_cost_usd'] == 0.12
        assert parsed['total_input_tokens'] == 5000
        assert parsed['total_output_tokens'] == 2000
        assert parsed['num_turns'] == 5

    def test_verbose_list_no_result_key(self) -> None:
        """
        Compute that verbose array without result key uses last element.

        Returns:
            None
        """

        data = [
            {'type': 'assistant', 'message': 'hello'},
            {'type': 'done', 'total_cost_usd': 0.01, 'num_turns': 1},
        ]
        parsed = _parse_output(json.dumps(data))

        assert parsed['total_cost_usd'] == 0.01
        assert parsed['num_turns'] == 1

    def test_verbose_empty_list(self) -> None:
        """
        Compute that empty JSON array returns error result.

        Returns:
            None
        """

        parsed = _parse_output('[]')

        assert parsed['is_error'] is True

    def test_stream_json_multiline(self) -> None:
        """
        Compute that stream-json format with one JSON per line is parsed.

        Returns:
            None
        """

        lines = [
            json.dumps({'type': 'assistant', 'message': 'working'}),
            json.dumps(
                {
                    'type': 'result',
                    'result': 'All done',
                    'is_error': False,
                    'total_cost_usd': 0.03,
                    'total_input_tokens': 800,
                    'total_output_tokens': 200,
                    'num_turns': 2,
                }
            ),
        ]
        raw = '\n'.join(lines)
        parsed = _parse_output(raw)

        assert parsed['result'] == 'All done'
        assert parsed['is_error'] is False
        assert parsed['total_cost_usd'] == 0.03
        assert parsed['num_turns'] == 2


class TestExtractResultFromList:
    def test_finds_result_message(self) -> None:
        """
        Compute that result message is extracted from verbose array.

        Returns:
            None
        """

        data = [
            {'type': 'assistant'},
            {'result': 'done', 'is_error': False, 'total_cost_usd': 0.05, 'num_turns': 3},
        ]
        result = _extract_result_from_list(data)

        assert result['result'] == 'done'
        assert result['total_cost_usd'] == 0.05

    def test_empty_list_returns_error(self) -> None:
        """
        Compute that empty list returns error defaults.

        Returns:
            None
        """

        result = _extract_result_from_list([])

        assert result['is_error'] is True

    def test_non_dict_elements_skipped(self) -> None:
        """
        Compute that non-dict elements in list are skipped.

        Returns:
            None
        """

        data = ['string', 123, {'result': 'ok', 'is_error': False}]
        result = _extract_result_from_list(data)

        assert result['result'] == 'ok'


class TestExecutorResult:
    def test_dataclass_fields(self) -> None:
        """
        Compute that ExecutorResult has all expected fields.

        Returns:
            None
        """

        result = ExecutorResult(
            status='success',
            response='Done',
            error=None,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05,
            num_turns=3,
            duration_seconds=12.5,
            raw_output='{"result": "Done"}',
        )

        assert result.status == 'success'
        assert result.response == 'Done'
        assert result.error is None
        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        assert result.cost_usd == 0.05
        assert result.num_turns == 3
        assert result.duration_seconds == 12.5


class TestFormatStreamLine:
    def test_assistant_text(self) -> None:
        """
        Compute that assistant text content is extracted.

        Returns:
            None
        """

        data = {
            'type': 'assistant',
            'message': {
                'content': [{'type': 'text', 'text': 'Let me look at the code'}],
            },
        }
        result = _format_stream_line(data)

        assert result == 'Let me look at the code'

    def test_assistant_thinking_skipped(self) -> None:
        """
        Compute that assistant thinking blocks are skipped.

        Returns:
            None
        """

        data = {
            'type': 'assistant',
            'message': {
                'content': [{'type': 'thinking', 'thinking': 'internal thought'}],
            },
        }
        result = _format_stream_line(data)

        assert result is None

    def test_tool_use_bash(self) -> None:
        """
        Compute that Bash tool use shows command.

        Returns:
            None
        """

        data = {
            'type': 'tool_use',
            'tool': {
                'name': 'Bash',
                'input': {'command': 'git status'},
            },
        }
        result = _format_stream_line(data)

        assert result == '> Bash: git status'

    def test_tool_use_read(self) -> None:
        """
        Compute that Read tool use shows file path.

        Returns:
            None
        """

        data = {
            'type': 'tool_use',
            'tool': {
                'name': 'Read',
                'input': {'file_path': '/src/main.py'},
            },
        }
        result = _format_stream_line(data)

        assert result == '> Read: /src/main.py'

    def test_tool_use_grep(self) -> None:
        """
        Compute that Grep tool use shows pattern.

        Returns:
            None
        """

        data = {
            'type': 'tool_use',
            'tool': {
                'name': 'Grep',
                'input': {'pattern': 'def main'},
            },
        }
        result = _format_stream_line(data)

        assert result == '> Grep: def main'

    def test_tool_use_no_input(self) -> None:
        """
        Compute that tool use without input shows name only.

        Returns:
            None
        """

        data = {
            'type': 'tool_use',
            'tool': {'name': 'TodoRead', 'input': {}},
        }
        result = _format_stream_line(data)

        assert result == '> TodoRead'

    def test_result_line(self) -> None:
        """
        Compute that result line shows turns and cost.

        Returns:
            None
        """

        data = {
            'type': 'result',
            'result': 'All done',
            'num_turns': 5,
            'total_cost_usd': 0.1234,
        }
        result = _format_stream_line(data)

        assert result == 'Done (5 turns, $0.1234)'

    def test_system_returns_none(self) -> None:
        """
        Compute that system messages are skipped.

        Returns:
            None
        """

        data = {'type': 'system', 'subtype': 'init'}

        assert _format_stream_line(data) is None

    def test_tool_result_returns_none(self) -> None:
        """
        Compute that tool results are skipped.

        Returns:
            None
        """

        data = {'type': 'tool_result', 'tool': {'content': 'file contents...'}}

        assert _format_stream_line(data) is None

    def test_text_truncated(self) -> None:
        """
        Compute that long assistant text is truncated to 300 chars.

        Returns:
            None
        """

        long_text = 'x' * 500
        data = {
            'type': 'assistant',
            'message': {
                'content': [{'type': 'text', 'text': long_text}],
            },
        }
        result = _format_stream_line(data)

        assert result is not None
        assert len(result) == 300
