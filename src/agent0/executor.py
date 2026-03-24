import asyncio
import json
import logging
import os
import pty
import time
from dataclasses import dataclass
from typing import Any

from agent0 import prompts
from agent0.config import Config
from agent0.router import TaskContext, format_comments

__all__ = ['ExecutorResult', 'run']

log = logging.getLogger(__name__)


@dataclass
class ExecutorResult:
    """
    Compute structured result from a Claude Code execution.

    Args:
        status (str): Execution outcome - success, failure, or timeout
        response (str | None): Claude Code text response
        error (str | None): Error message if failed
        input_tokens (int): Input tokens consumed
        output_tokens (int): Output tokens consumed
        cost_usd (float): Cost in USD
        num_turns (int): Number of agentic turns
        duration_seconds (float): Wall clock time
        raw_output (str): Full raw stdout for audit

    Returns:
        ExecutorResult: Structured execution result
    """

    status: str
    response: str | None
    error: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    num_turns: int
    duration_seconds: float
    raw_output: str


def _build_prompt(context: TaskContext, config: Config) -> str:
    """
    Compute full prompt for the Claude Code CLI.

    Args:
        context (TaskContext): Structured task context
        config (Config): Application configuration

    Returns:
        str: Complete prompt with preamble and event-specific instructions
    """

    preamble = prompts.PREAMBLE.format(
        owner=context.owner,
        repo=context.repo,
        whitelisted_orgs=', '.join(config.whitelisted_orgs),
    )

    title = context.trigger_text[:100] if context.trigger_text else ''
    formatted = format_comments(context.comments)

    if context.event_type == 'mention':
        if context.subject_type == 'PullRequest':
            body = prompts.MENTION_PR.format(
                number=context.number,
                title=title,
                pr_body=context.issue_body or '(no description)',
                diff=context.diff or '(no diff available)',
                formatted_comments=formatted,
                trigger_text=context.trigger_text,
            )
        else:
            body = prompts.MENTION_ISSUE.format(
                number=context.number,
                title=title,
                issue_body=context.issue_body or '(no description)',
                formatted_comments=formatted,
                trigger_text=context.trigger_text,
            )
    elif context.event_type == 'assignment':
        body = prompts.ASSIGNED_ISSUE.format(
            number=context.number,
            title=title,
            issue_body=context.issue_body or '(no description)',
            labels=', '.join(context.labels) if context.labels else '(none)',
            formatted_comments=formatted,
        )
    elif context.event_type == 'review_request':
        body = prompts.REVIEW_PR.format(
            number=context.number,
            title=title,
            pr_body=context.issue_body or '(no description)',
            head_ref=context.head_ref or '(unknown)',
            base_ref=context.base_ref or '(unknown)',
            diff=context.diff or '(no diff available)',
            formatted_comments=formatted,
            owner=context.owner,
            repo=context.repo,
            github_user=config.github_user,
        )
    elif context.event_type == 're_review':
        body = prompts.RE_REVIEW_PR.format(
            number=context.number,
            title=title,
            diff=context.diff or '(no diff available)',
            formatted_comments=formatted,
            owner=context.owner,
            repo=context.repo,
            github_user=config.github_user,
        )
    elif context.event_type == 'ci_failure':
        body = prompts.CI_FAILURE.format(
            number=context.number,
            title=context.issue_body[:100] if context.issue_body else '',
            head_ref=context.head_ref or '(unknown)',
            base_ref=context.base_ref or '(unknown)',
            check_failures=context.trigger_text or '(no failure details available)',
            diff=context.diff or '(no diff available)',
            formatted_comments=formatted,
        )
    elif context.event_type in ('self_reflection', 'self_reflection_rfc'):
        body = context.trigger_text
    else:
        body = (
            f'Notification received with event type: {context.event_type}'
            f'\n\n{context.trigger_text}'
        )

    return f'{preamble}\n\n{body}'


_RESULT_DEFAULTS: dict[str, object] = {
    'result': '',
    'is_error': False,
    'total_cost_usd': 0.0,
    'total_input_tokens': 0,
    'total_output_tokens': 0,
    'num_turns': 0,
}

_ERROR_DEFAULTS: dict[str, object] = {
    'result': '',
    'is_error': True,
    'total_cost_usd': 0.0,
    'total_input_tokens': 0,
    'total_output_tokens': 0,
    'num_turns': 0,
}


def _extract_result_from_list(data: list[Any]) -> dict[str, Any]:
    """
    Compute result dict from verbose JSON array output.

    Args:
        data (list): JSON array from Claude Code verbose mode

    Returns:
        dict: Extracted result with tokens, cost, and turn count
    """

    for msg in reversed(data):
        if isinstance(msg, dict) and 'result' in msg:
            return {k: msg.get(k, v) for k, v in _RESULT_DEFAULTS.items()}

    if data and isinstance(data[-1], dict):
        last = data[-1]
        return {k: last.get(k, v) for k, v in _RESULT_DEFAULTS.items()}

    return dict(_ERROR_DEFAULTS)


def _parse_output(raw: str) -> dict[str, Any]:
    """
    Compute structured data from Claude Code JSON output.

    Handles three formats: single dict (standard), list (verbose),
    and stream-json (one JSON object per line).

    Args:
        raw (str): Raw stdout from the Claude Code process

    Returns:
        dict: Parsed output with result, tokens, cost, and turn count
    """

    if not raw or not raw.strip():
        return dict(_ERROR_DEFAULTS, result=raw)

    try:
        data = json.loads(raw)

        if isinstance(data, list):
            return _extract_result_from_list(data)

        if isinstance(data, dict):
            return {k: data.get(k, v) for k, v in _RESULT_DEFAULTS.items()}

        return dict(_ERROR_DEFAULTS, result=raw)

    except (json.JSONDecodeError, TypeError):
        pass

    lines = raw.strip().splitlines()
    for line in reversed(lines):
        try:
            msg = json.loads(line)
            if isinstance(msg, dict) and 'result' in msg:
                return {k: msg.get(k, v) for k, v in _RESULT_DEFAULTS.items()}
        except (json.JSONDecodeError, TypeError):
            continue

    return dict(_ERROR_DEFAULTS, result=raw)


def _format_stream_line(data: dict[str, Any]) -> str | None:
    """
    Compute human-readable text from a stream-json line.

    Args:
        data (dict): Parsed JSON object from stream-json output

    Returns:
        str | None: Formatted text or None if line should be skipped
    """

    msg_type = data.get('type', '')

    if msg_type == 'assistant':
        message = data.get('message', {})
        content = message.get('content', [])
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'text':
                text_raw = block.get('text', '')
                text = text_raw.strip() if isinstance(text_raw, str) else ''
                if text:
                    return text[:300]
        return None

    if msg_type == 'tool_use':
        tool = data.get('tool', {})
        name_raw = tool.get('name', 'unknown')
        name = name_raw if isinstance(name_raw, str) else 'unknown'
        inp = tool.get('input', {})
        if isinstance(inp, dict):
            for key in ('command', 'file_path', 'pattern', 'path', 'url'):
                if key in inp:
                    return f'> {name}: {str(inp[key])[:200]}'
        return f'> {name}'

    if msg_type == 'result':
        turns = data.get('num_turns', 0)
        cost = data.get('total_cost_usd', 0.0)
        return f'Done ({turns} turns, ${cost:.4f})'

    return None


_PTY_READ_SIZE = 4096


def _pty_read(fd: int | None) -> bytes:
    """
    Compute a blocking read from a PTY file descriptor.

    Args:
        fd (int): PTY master file descriptor

    Returns:
        bytes: Data read from the PTY, empty on EOF
    """

    if fd is None:
        return b''
    try:
        return os.read(fd, _PTY_READ_SIZE)
    except OSError:
        return b''


async def run(
    context: TaskContext,
    workspace_path: str,
    config: Config,
    output_lines: list[str] | None = None,
) -> ExecutorResult:
    """
    Compute execution result by spawning Claude Code CLI subprocess.

    Streams stdout line-by-line via stream-json for live dashboard visibility.

    Args:
        context (TaskContext): Structured task context
        workspace_path (str): Path to the repo workspace directory
        config (Config): Application configuration
        output_lines (list[str] | None): Buffer for live stdout streaming

    Returns:
        ExecutorResult: Structured result including response, tokens, and cost
    """

    prompt = _build_prompt(context, config)
    start_time = time.monotonic()

    log.info(
        'Executing task: %s for %s/%s#%d (timeout=%ds, max_turns=%d)',
        context.event_type,
        context.owner,
        context.repo,
        context.number,
        config.executor_timeout,
        config.max_turns,
    )
    log.debug('Prompt length: %d chars', len(prompt))

    env = {
        **os.environ,
        'ANTHROPIC_API_KEY': config.anthropic_api_key,
        'GH_TOKEN': config.github_token,
        'CLAUDE_CODE_ACCEPT_TOS': 'true',
    }

    cmd = [
        'claude',
        '--print',
        '--verbose',
        '--output-format',
        'stream-json',
        '--dangerously-skip-permissions',
        '--max-turns',
        str(config.max_turns),
    ]

    log.info('Spawning: %s (cwd=%s)', ' '.join(cmd), workspace_path)

    master_fd: int | None = None
    slave_fd: int | None = None

    try:
        master_fd, slave_fd = pty.openpty()

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=slave_fd,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_path,
            env=env,
        )

        os.close(slave_fd)
        slave_fd = None

        assert process.stdin is not None
        process.stdin.write(prompt.encode())
        await process.stdin.drain()
        process.stdin.close()

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        loop = asyncio.get_running_loop()

        async def _stream_stdout_pty() -> None:
            buf = b''
            while True:
                try:
                    chunk = await loop.run_in_executor(
                        None,
                        _pty_read,
                        master_fd,
                    )
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b'\n' in buf:
                    line_bytes, buf = buf.split(b'\n', 1)
                    text = line_bytes.decode(errors='replace').strip()
                    if not text:
                        continue
                    stdout_lines.append(text)
                    try:
                        data = json.loads(text)
                        formatted = _format_stream_line(data)
                        if formatted and output_lines is not None:
                            output_lines.append(formatted)
                    except (json.JSONDecodeError, TypeError):
                        if output_lines is not None:
                            output_lines.append(text)

            if buf:
                text = buf.decode(errors='replace').strip()
                if text:
                    stdout_lines.append(text)
                    try:
                        data = json.loads(text)
                        formatted = _format_stream_line(data)
                        if formatted and output_lines is not None:
                            output_lines.append(formatted)
                    except (json.JSONDecodeError, TypeError):
                        if output_lines is not None:
                            output_lines.append(text)

        async def _drain_stderr() -> None:
            assert process.stderr is not None
            async for raw_line in process.stderr:
                text = raw_line.decode(errors='replace').strip()
                if text:
                    log.info('Claude stderr: %s', text)
                    stderr_lines.append(text)

        try:
            await asyncio.wait_for(
                asyncio.gather(_stream_stdout_pty(), _drain_stderr()),
                timeout=config.executor_timeout,
            )
        except TimeoutError:
            duration = time.monotonic() - start_time
            log.error(
                'E4002: Execution timed out for %s/%s#%d after %.1fs',
                context.owner,
                context.repo,
                context.number,
                duration,
            )
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            if master_fd is not None:
                os.close(master_fd)
                master_fd = None
            return ExecutorResult(
                status='timeout',
                response=None,
                error=f'Timed out after {config.executor_timeout}s',
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                num_turns=0,
                duration_seconds=duration,
                raw_output='\n'.join(stdout_lines),
            )

        await process.wait()
        if master_fd is not None:
            os.close(master_fd)
            master_fd = None
        duration = time.monotonic() - start_time
        raw_output = '\n'.join(stdout_lines)

        parsed = _parse_output(raw_output)
        returncode = process.returncode if process.returncode is not None else -1

        if returncode != 0:
            stderr_text = '\n'.join(stderr_lines)
            error_msg = parsed.get('result', '') or stderr_text or 'unknown error'
            log.error(
                'E4003: Execution failed for %s/%s#%d (exit=%d): %s',
                context.owner,
                context.repo,
                context.number,
                returncode,
                str(error_msg)[:500],
            )
            return ExecutorResult(
                status='failure',
                response=parsed.get('result'),
                error=str(error_msg),
                input_tokens=parsed.get('total_input_tokens', 0),
                output_tokens=parsed.get('total_output_tokens', 0),
                cost_usd=parsed.get('total_cost_usd', 0.0),
                num_turns=parsed.get('num_turns', 0),
                duration_seconds=duration,
                raw_output=raw_output,
            )

        if parsed.get('is_error'):
            log.warning(
                'E4004: Execution completed for %s/%s#%d (exit=0, %.1fs) '
                'but result parsing failed; raw output: %d chars, %d lines',
                context.owner,
                context.repo,
                context.number,
                duration,
                len(raw_output),
                len(stdout_lines),
            )

        log.info(
            'Execution succeeded for %s/%s#%d (%.1fs, %d turns, $%.4f)',
            context.owner,
            context.repo,
            context.number,
            duration,
            parsed.get('num_turns', 0),
            parsed.get('total_cost_usd', 0.0),
        )
        return ExecutorResult(
            status='success',
            response=parsed.get('result'),
            error=None,
            input_tokens=parsed.get('total_input_tokens', 0),
            output_tokens=parsed.get('total_output_tokens', 0),
            cost_usd=parsed.get('total_cost_usd', 0.0),
            num_turns=parsed.get('num_turns', 0),
            duration_seconds=duration,
            raw_output=raw_output,
        )

    except FileNotFoundError:
        if master_fd is not None:
            os.close(master_fd)
        if slave_fd is not None:
            os.close(slave_fd)
        duration = time.monotonic() - start_time
        log.error('E4001: Claude Code CLI not found — is it installed?')
        return ExecutorResult(
            status='failure',
            response=None,
            error='claude CLI not found',
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            num_turns=0,
            duration_seconds=duration,
            raw_output='',
        )
