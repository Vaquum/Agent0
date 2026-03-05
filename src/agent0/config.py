import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = ['Config', 'load_config']

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """
    Compute configuration from environment variables.

    Args:
        github_token (str): PAT for Agent0 with repo and notifications scopes
        anthropic_api_key (str): API key for Claude Code
        github_user (str): GitHub username for the agent
        whitelisted_orgs (tuple[str, ...]): Organizations to respond to
        poll_interval (int): Seconds between notification polls
        executor_timeout (int): Max seconds per Claude Code session
        max_turns (int): Max agentic turns per Claude Code session
        log_level (str): Python logging level
        data_dir (Path): Root directory for persistent data
        port (int): Port for the web server

    Returns:
        Config: Frozen configuration dataclass
    """

    github_token: str
    anthropic_api_key: str
    github_user: str
    whitelisted_orgs: tuple[str, ...]
    poll_interval: int = 30
    executor_timeout: int = 1800
    max_turns: int = 100
    log_level: str = 'INFO'
    data_dir: Path = Path('/data')
    port: int = 9999

    @property
    def workspaces_dir(self) -> Path:
        """
        Compute path to workspaces directory.

        Returns:
            Path: The workspaces directory path
        """

        return self.data_dir / 'workspaces'

    @property
    def audit_dir(self) -> Path:
        """
        Compute path to audit logs directory.

        Returns:
            Path: The audit directory path
        """

        return self.data_dir / 'audit'

    def log_redacted(self) -> str:
        """
        Compute redacted string representation of config for logging.

        Returns:
            str: Config values with secrets masked
        """

        def _mask(value: str) -> str:
            if len(value) <= 8:
                return '****'
            return f'{value[:4]}...{value[-4:]}'

        return (
            f'github_token={_mask(self.github_token)} '
            f'anthropic_api_key={_mask(self.anthropic_api_key)} '
            f'poll_interval={self.poll_interval} '
            f'whitelisted_orgs={",".join(self.whitelisted_orgs)} '
            f'executor_timeout={self.executor_timeout} '
            f'max_turns={self.max_turns} '
            f'log_level={self.log_level} '
            f'data_dir={self.data_dir} '
            f'github_user={self.github_user} '
            f'port={self.port}'
        )


def load_config() -> Config:
    """
    Compute Config from environment variables.

    Returns:
        Config: Validated configuration loaded from environment
    """

    github_token = os.environ.get('GITHUB_TOKEN', '')
    anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    github_user = os.environ.get('GITHUB_USER', '')

    if not github_token:
        log.error('GITHUB_TOKEN environment variable is required')
        sys.exit(1)

    if not anthropic_api_key:
        log.error('ANTHROPIC_API_KEY environment variable is required')
        sys.exit(1)

    if not github_user:
        log.error('GITHUB_USER environment variable is required')
        sys.exit(1)

    orgs_raw = os.environ.get('WHITELISTED_ORGS', '')
    whitelisted_orgs = tuple(org.strip() for org in orgs_raw.split(',') if org.strip())

    if not whitelisted_orgs:
        raise ValueError(
            'WHITELISTED_ORGS must contain at least one organization. '
            'Set it to a comma-separated list of GitHub org names (e.g. WHITELISTED_ORGS=myorg).'
        )

    poll_interval = int(os.environ.get('POLL_INTERVAL', '30'))
    executor_timeout = int(os.environ.get('EXECUTOR_TIMEOUT', '1800'))
    max_turns = int(os.environ.get('MAX_TURNS', '100'))
    log_level = os.environ.get('LOG_LEVEL', 'INFO')
    data_dir = Path(os.environ.get('DATA_DIR', '/data'))
    port = int(os.environ.get('PORT', '9999'))

    return Config(
        github_token=github_token,
        anthropic_api_key=anthropic_api_key,
        github_user=github_user,
        whitelisted_orgs=whitelisted_orgs,
        poll_interval=poll_interval,
        executor_timeout=executor_timeout,
        max_turns=max_turns,
        log_level=log_level,
        data_dir=data_dir,
        port=port,
    )
