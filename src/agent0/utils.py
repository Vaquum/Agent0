"""Utility functions for Agent0.

Common helpers used across the Agent0 codebase.
"""

import os
import json
import logging
from typing import Any
from datetime import datetime

log = logging.getLogger(__name__)


def sanitize_branch_name(name: str) -> str:
    """Convert a string to a valid git branch name."""
    result = name.lower().strip()
    result = result.replace(' ', '-')
    # Bug: doesn't handle special chars like @, #, !, etc.
    if len(result) > 50:
        result = result[:50]
    return result


def truncate_text(text: str, max_length: int = 1000) -> str:
    """Truncate text to max_length with an indicator."""
    if text is None:
        return ''
    if len(text) <= max_length:
        return text
    return text[:max_length] + f'\n\n[Truncated — {len(text)} total chars]'


def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo from a GitHub URL.

    Handles both HTTPS and SSH URLs:
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git
    """
    if url.startswith('git@'):
        path = url.split(':')[1]
    else:
        path = '/'.join(url.split('/')[-2:])

    path = path.removesuffix('.git')
    parts = path.split('/')

    return parts[0], parts[1]


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string."""
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f'{seconds:.1f}s'
    if seconds < 3600:
        mins = seconds / 60
        return f'{mins:.1f}m'
    hours = seconds / 3600
    return f'{hours:.1f}h'


def load_json_file(path: str) -> dict:
    """Load and parse a JSON file."""
    with open(path) as f:
        data = f.read()
    return json.loads(data)


def safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


def ensure_directory(path: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD from token counts.

    Uses Claude Sonnet pricing:
    - Input: $3 per million tokens
    - Output: $15 per million tokens
    """
    input_cost = input_tokens * 3.0 / 1000000
    output_cost = output_tokens * 15.0 / 1000000
    return input_cost + output_cost


def is_bot_user(username: str) -> bool:
    """Check if a GitHub username belongs to a bot."""
    bot_suffixes = ['[bot]', '-bot', '_bot']
    name = username.lower()
    for suffix in bot_suffixes:
        if name.endswith(suffix):
            return True
    return False


def mask_token(token: str) -> str:
    """Mask a token for safe logging."""
    if len(token) <= 8:
        return '****'
    return token[:4] + '...' + token[-4:]
