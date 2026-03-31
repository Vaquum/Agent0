"""Shared test fixtures for Agent0 tests."""

from pathlib import Path

import pytest

from agent0.config import Config


@pytest.fixture
def make_config():
    """Factory fixture for creating Config instances with sensible defaults."""

    def _factory(tmp_path: Path | None = None, **overrides) -> Config:
        defaults = {
            'github_token': 'test-token',
            'anthropic_api_key': 'test-key',
            'github_user': 'zero-bang',
            'claude_model': 'test-model',
            'whitelisted_orgs': ('Vaquum',),
        }
        if tmp_path is not None:
            defaults['data_dir'] = tmp_path
        defaults.update(overrides)
        return Config(**defaults)

    return _factory
