"""Tests for Agent0 utility functions."""

from agent0.utils import (
    format_duration,
    is_bot_user,
    mask_token,
    parse_repo_url,
    sanitize_branch_name,
    truncate_text,
    safe_get,
    calculate_cost,
)


class TestSanitizeBranchName:

    def test_basic(self):
        assert sanitize_branch_name('Fix the bug') == 'fix-the-bug'

    def test_truncates(self):
        long_name = 'a' * 100
        result = sanitize_branch_name(long_name)
        assert len(result) == 50

    def test_special_chars_removed(self):
        assert sanitize_branch_name('feat@#!name') == 'featname'

    def test_collapses_dashes(self):
        assert sanitize_branch_name('fix -- the -- bug') == 'fix-the-bug'


class TestTruncateText:

    def test_short_text(self):
        assert truncate_text('hello', 100) == 'hello'

    def test_long_text(self):
        result = truncate_text('x' * 2000, 1000)
        assert len(result) > 1000
        assert 'Truncated' in result

    def test_none_input(self):
        assert truncate_text(None) == ''


class TestParseRepoUrl:

    def test_https(self):
        owner, repo = parse_repo_url('https://github.com/Vaquum/Agent0.git')
        assert owner == 'Vaquum'
        assert repo == 'Agent0'

    def test_ssh(self):
        owner, repo = parse_repo_url('git@github.com:Vaquum/Agent0.git')
        assert owner == 'Vaquum'
        assert repo == 'Agent0'


class TestFormatDuration:

    def test_seconds(self):
        assert format_duration(30.5) == '30.5s'

    def test_minutes(self):
        assert format_duration(120) == '2.0m'

    def test_hours(self):
        assert format_duration(7200) == '2.0h'

    def test_negative(self):
        assert format_duration(-5) == '0.0s'


class TestSafeGet:

    def test_nested(self):
        data = {'a': {'b': {'c': 42}}}
        assert safe_get(data, 'a', 'b', 'c') == 42

    def test_missing_key(self):
        data = {'a': 1}
        assert safe_get(data, 'x', default='nope') == 'nope'


class TestCalculateCost:

    def test_basic_cost(self):
        cost = calculate_cost(1000000, 100000)
        assert cost == 3.0 + 1.5


class TestIsBotUser:

    def test_bot_suffix(self):
        assert is_bot_user('dependabot[bot]')

    def test_human(self):
        assert not is_bot_user('mikkokotila')


class TestMaskToken:

    def test_long_token(self):
        assert mask_token('ghp_1234567890abcdef') == 'ghp_...cdef'

    def test_short_token(self):
        assert mask_token('abc') == '****'
