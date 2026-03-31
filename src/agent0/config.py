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
        claude_model (str): Model identifier for Claude Code CLI --model flag
        whitelisted_orgs (tuple[str, ...]): Organizations to respond to
        agent0_repo (str): Repository name for Agent0 itself (e.g. 'Agent0')
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
    claude_model: str
    whitelisted_orgs: tuple[str, ...]
    agent0_repo: str = 'Agent0'
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
            f'claude_model={self.claude_model} '
            f'poll_interval={self.poll_interval} '
            f'whitelisted_orgs={",".join(self.whitelisted_orgs)} '
            f'agent0_repo={self.agent0_repo} '
            f'executor_timeout={self.executor_timeout} '
            f'max_turns={self.max_turns} '
            f'log_level={self.log_level} '
            f'data_dir={self.data_dir} '
            f'github_user={self.github_user} '
            f'port={self.port}'
        )


def _parse_int_env(name: str, default: str) -> int:
    """
    Compute integer value from environment variable with clear error on invalid input.

    Args:
        name (str): Environment variable name
        default (str): Default value if not set

    Returns:
        int: Parsed integer value
    """

    raw = os.environ.get(name, default)
    try:
        return int(raw)
    except ValueError:
        log.error('E1002: %s must be an integer, got %r', name, raw)
        sys.exit(1)


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
        log.error('E1001: GITHUB_TOKEN environment variable is required')
        sys.exit(1)

    if not anthropic_api_key:
        log.error('E1001: ANTHROPIC_API_KEY environment variable is required')
        sys.exit(1)

    if not github_user:
        log.error('E1001: GITHUB_USER environment variable is required')
        sys.exit(1)

    claude_model = os.environ.get('CLAUDE_MODEL', '')
    if not claude_model:
        log.error('E1001: CLAUDE_MODEL environment variable is required')
        sys.exit(1)

    orgs_raw = os.environ.get('WHITELISTED_ORGS', '')
    whitelisted_orgs = tuple(org.strip() for org in orgs_raw.split(',') if org.strip())

    if not whitelisted_orgs:
        raise ValueError(
            'E1003: WHITELISTED_ORGS must contain at least one organization. '
            'Set it to a comma-separated list of GitHub org names (e.g. WHITELISTED_ORGS=myorg).'
        )

    poll_interval = _parse_int_env('POLL_INTERVAL', '30')
    executor_timeout = _parse_int_env('EXECUTOR_TIMEOUT', '1800')
    max_turns = _parse_int_env('MAX_TURNS', '100')
    log_level = os.environ.get('LOG_LEVEL', 'INFO')
    data_dir = Path(os.environ.get('DATA_DIR', '/data'))
    port = _parse_int_env('PORT', '9999')
    agent0_repo = os.environ.get('AGENT0_REPO', 'Agent0')

    return Config(
        github_token=github_token,
        anthropic_api_key=anthropic_api_key,
        github_user=github_user,
        claude_model=claude_model,
        whitelisted_orgs=whitelisted_orgs,
        agent0_repo=agent0_repo,
        poll_interval=poll_interval,
        executor_timeout=executor_timeout,
        max_turns=max_turns,
        log_level=log_level,
        data_dir=data_dir,
        port=port,
    )
