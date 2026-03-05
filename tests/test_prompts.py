from agent0 import prompts


class TestPromptsModule:
    def test_all_templates_exported(self) -> None:
        """
        Compute that all expected prompt templates are defined in the module.

        Returns:
            None
        """

        expected = [
            'PREAMBLE',
            'MENTION_ISSUE',
            'MENTION_PR',
            'ASSIGNED_ISSUE',
            'REVIEW_PR',
            'CI_FAILURE',
        ]
        for name in expected:
            assert hasattr(prompts, name), f'{name} not found in prompts module'
            value = getattr(prompts, name)
            assert isinstance(value, str), f'{name} should be a string'
            assert len(value) > 50, f'{name} appears too short to be a prompt'

    def test_preamble_has_format_placeholders(self) -> None:
        """
        Compute that preamble contains expected format placeholders.

        Returns:
            None
        """

        assert '{owner}' in prompts.PREAMBLE
        assert '{repo}' in prompts.PREAMBLE
        assert '{whitelisted_orgs}' in prompts.PREAMBLE

    def test_review_pr_has_inline_comment_instructions(self) -> None:
        """
        Compute that REVIEW_PR template instructs inline review comments.

        Returns:
            None
        """

        assert 'inline' in prompts.REVIEW_PR.lower()
        assert 'NEVER use `gh pr comment`' in prompts.REVIEW_PR
        assert '{owner}' in prompts.REVIEW_PR
        assert '{repo}' in prompts.REVIEW_PR
        assert '{github_user}' in prompts.REVIEW_PR

    def test_review_pr_has_rereview_logic(self) -> None:
        """
        Compute that REVIEW_PR template includes re-review instructions.

        Returns:
            None
        """

        assert 'RE-REVIEW' in prompts.REVIEW_PR
        assert 'Do NOT look for new issues' in prompts.REVIEW_PR
        assert 'already reviewed' in prompts.REVIEW_PR.lower()

    def test_review_pr_has_thread_dedup(self) -> None:
        """
        Compute that REVIEW_PR template prevents duplicate threads.

        Returns:
            None
        """

        assert 'NEVER open a new thread if another reviewer' in prompts.REVIEW_PR

    def test_review_pr_single_review(self) -> None:
        """
        Compute that REVIEW_PR template instructs exactly one review.

        Returns:
            None
        """

        assert 'Submit exactly ONE review' in prompts.REVIEW_PR

    def test_review_pr_request_changes_requires_inline(self) -> None:
        """
        Compute that REVIEW_PR enforces REQUEST_CHANGES only with inline comments.

        Returns:
            None
        """

        assert 'REQUEST_CHANGES' in prompts.REVIEW_PR
        assert 'requires inline comments' in prompts.REVIEW_PR.lower()
        assert 'COMMENT' in prompts.REVIEW_PR

    def test_mention_issue_has_gh_issue_comment(self) -> None:
        """
        Compute that mention in issue uses gh issue comment.

        Returns:
            None
        """

        assert 'gh issue comment' in prompts.MENTION_ISSUE

    def test_mention_pr_has_gh_pr_comment(self) -> None:
        """
        Compute that mention in PR uses gh pr comment.

        Returns:
            None
        """

        assert 'gh pr comment' in prompts.MENTION_PR

    def test_ci_failure_has_fix_instructions(self) -> None:
        """
        Compute that CI failure prompt has fix instructions.

        Returns:
            None
        """

        assert 'Fix the failing checks' in prompts.CI_FAILURE
        assert '{check_failures}' in prompts.CI_FAILURE

    def test_all_templates_format_without_error(self) -> None:
        """
        Compute that all templates can be formatted without KeyError.

        Returns:
            None
        """

        # Test that format placeholders are valid by formatting with dummy values
        prompts.PREAMBLE.format(
            owner='testorg',
            repo='testrepo',
            whitelisted_orgs='testorg',
        )
        prompts.MENTION_ISSUE.format(
            number=1,
            title='test',
            issue_body='body',
            formatted_comments='comments',
            trigger_text='text',
        )
        prompts.MENTION_PR.format(
            number=1,
            title='test',
            pr_body='body',
            diff='diff',
            formatted_comments='comments',
            trigger_text='text',
        )
        prompts.ASSIGNED_ISSUE.format(
            number=1,
            title='test',
            issue_body='body',
            labels='bug',
            formatted_comments='comments',
        )
        prompts.REVIEW_PR.format(
            number=1,
            title='test',
            pr_body='body',
            head_ref='feature',
            base_ref='main',
            diff='diff',
            formatted_comments='comments',
            owner='testorg',
            repo='testrepo',
            github_user='zero-bang',
        )
        prompts.CI_FAILURE.format(
            number=1,
            title='test',
            head_ref='feature',
            base_ref='main',
            check_failures='failures',
            diff='diff',
            formatted_comments='comments',
        )
