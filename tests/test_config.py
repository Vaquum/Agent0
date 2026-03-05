from pathlib import Path

import pytest

from agent0.config import Config, load_config


class TestLoadConfig:
    def test_missing_github_token_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Compute that missing GITHUB_TOKEN causes SystemExit.

        Returns:
            None
        """

        monkeypatch.delenv('GITHUB_TOKEN', raising=False)
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
        with pytest.raises(SystemExit):
            load_config()

    def test_missing_anthropic_key_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Compute that missing ANTHROPIC_API_KEY causes SystemExit.

        Returns:
            None
        """

        monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
        monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
        with pytest.raises(SystemExit):
            load_config()

    def test_missing_github_user_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Compute that missing GITHUB_USER causes SystemExit.

        Returns:
            None
        """

        monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
        monkeypatch.delenv('GITHUB_USER', raising=False)
        with pytest.raises(SystemExit):
            load_config()

    def test_defaults_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Compute that default values are applied correctly.

        Returns:
            None
        """

        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_test123')
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test123')
        monkeypatch.setenv('GITHUB_USER', 'my-bot')
        monkeypatch.setenv('WHITELISTED_ORGS', 'myorg')
        for key in ('POLL_INTERVAL', 'EXECUTOR_TIMEOUT', 'MAX_TURNS', 'LOG_LEVEL', 'DATA_DIR'):
            monkeypatch.delenv(key, raising=False)

        config = load_config()
        assert config.poll_interval == 30
        assert config.whitelisted_orgs == ('myorg',)
        assert config.executor_timeout == 1800
        assert config.max_turns == 100
        assert config.log_level == 'INFO'
        assert config.data_dir == Path('/data')
        assert config.github_user == 'my-bot'

    def test_custom_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Compute that custom environment values are parsed correctly.

        Returns:
            None
        """

        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_custom')
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-custom')
        monkeypatch.setenv('GITHUB_USER', 'custom-bot')
        monkeypatch.setenv('POLL_INTERVAL', '60')
        monkeypatch.setenv('WHITELISTED_ORGS', 'orgA, orgB, orgC')
        monkeypatch.setenv('EXECUTOR_TIMEOUT', '300')
        monkeypatch.setenv('LOG_LEVEL', 'DEBUG')
        monkeypatch.setenv('DATA_DIR', '/tmp/agent0')

        config = load_config()
        assert config.poll_interval == 60
        assert config.whitelisted_orgs == ('orgA', 'orgB', 'orgC')
        assert config.executor_timeout == 300
        assert config.log_level == 'DEBUG'
        assert config.data_dir == Path('/tmp/agent0')

    def test_whitelisted_orgs_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Compute that whitespace in org list is handled correctly.

        Returns:
            None
        """

        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_test')
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test')
        monkeypatch.setenv('GITHUB_USER', 'test-bot')
        monkeypatch.setenv('WHITELISTED_ORGS', ' org1 , org2 , , org3 ')

        config = load_config()
        assert config.whitelisted_orgs == ('org1', 'org2', 'org3')

    def test_empty_whitelisted_orgs_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Compute that an empty WHITELISTED_ORGS raises ValueError.

        Returns:
            None
        """

        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_test')
        monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test')
        monkeypatch.setenv('GITHUB_USER', 'test-bot')
        monkeypatch.setenv('WHITELISTED_ORGS', ' , , ')

        with pytest.raises(
            ValueError, match='WHITELISTED_ORGS must contain at least one organization'
        ):
            load_config()


class TestConfig:
    def test_workspaces_dir(self) -> None:
        """
        Compute that workspaces_dir derives correctly from data_dir.

        Returns:
            None
        """

        config = Config(
            github_token='test',
            anthropic_api_key='test',
            github_user='test-bot',
            whitelisted_orgs=('testorg',),
            data_dir=Path('/mydata'),
        )
        assert config.workspaces_dir == Path('/mydata/workspaces')

    def test_audit_dir(self) -> None:
        """
        Compute that audit_dir derives correctly from data_dir.

        Returns:
            None
        """

        config = Config(
            github_token='test',
            anthropic_api_key='test',
            github_user='test-bot',
            whitelisted_orgs=('testorg',),
            data_dir=Path('/mydata'),
        )
        assert config.audit_dir == Path('/mydata/audit')

    def test_log_redacted_masks_secrets(self) -> None:
        """
        Compute that log_redacted masks sensitive values.

        Returns:
            None
        """

        config = Config(
            github_token='ghp_abcdef123456789',
            anthropic_api_key='sk-ant-abcdef123456789',
            github_user='test-bot',
            whitelisted_orgs=('testorg',),
        )
        redacted = config.log_redacted()
        assert 'ghp_abcdef123456789' not in redacted
        assert 'sk-ant-abcdef123456789' not in redacted
        assert 'ghp_...' in redacted
        assert 'sk-a...' in redacted

    def test_log_redacted_short_secret(self) -> None:
        """
        Compute that log_redacted handles short secrets.

        Returns:
            None
        """

        config = Config(
            github_token='short',
            anthropic_api_key='tiny',
            github_user='test-bot',
            whitelisted_orgs=('testorg',),
        )
        redacted = config.log_redacted()
        assert 'short' not in redacted
        assert 'tiny' not in redacted
        assert '****' in redacted

    def test_frozen(self) -> None:
        """
        Compute that Config is immutable.

        Returns:
            None
        """

        config = Config(
            github_token='test',
            anthropic_api_key='test',
            github_user='test-bot',
            whitelisted_orgs=('testorg',),
        )
        with pytest.raises(AttributeError):
            config.github_token = 'changed'  # type: ignore[misc]
