import asyncio
import logging
import time
from pathlib import Path

from agent0.config import Config

__all__ = ['WorkspaceManager']

log = logging.getLogger(__name__)


class WorkspaceManager:
    """
    Compute workspace state for repository clones on persistent disk.

    Args:
        config (Config): Application configuration

    Returns:
        WorkspaceManager: Manager for repo workspace lifecycle
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    def _workspace_path(self, owner: str, repo: str) -> Path:
        """
        Compute filesystem path for a repo workspace.

        Args:
            owner (str): Repository owner
            repo (str): Repository name

        Returns:
            Path: Absolute path to the workspace directory
        """

        return self._config.workspaces_dir / owner / repo

    def _clone_url(self, owner: str, repo: str) -> str:
        """
        Compute clone URL with embedded token for authentication.

        Args:
            owner (str): Repository owner
            repo (str): Repository name

        Returns:
            str: HTTPS clone URL with token
        """

        return f'https://x-access-token:{self._config.github_token}@github.com/{owner}/{repo}.git'

    async def _run_git(
        self,
        args: list[str],
        cwd: Path | None = None,
    ) -> tuple[int, str, str]:
        """
        Compute result of a git subprocess execution.

        Args:
            args (list[str]): Git command arguments
            cwd (Path | None): Working directory for the command

        Returns:
            tuple[int, str, str]: Return code, stdout, stderr
        """

        cmd = ['git', *args]
        log.debug('Running: %s (cwd=%s)', ' '.join(cmd), cwd)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        return (
            process.returncode or 0,
            stdout_bytes.decode().strip(),
            stderr_bytes.decode().strip(),
        )

    async def prepare(self, owner: str, repo: str) -> Path:
        """
        Compute a clean workspace ready for use.

        Clones the repo if not present. If already cloned, fetches latest
        and resets to the default branch.

        Args:
            owner (str): Repository owner
            repo (str): Repository name

        Returns:
            Path: Path to the prepared workspace directory
        """

        workspace = self._workspace_path(owner, repo)

        if not workspace.exists():
            log.info('Cloning %s/%s', owner, repo)
            workspace.parent.mkdir(parents=True, exist_ok=True)

            returncode, _stdout, stderr = await self._run_git(
                ['clone', self._clone_url(owner, repo), str(workspace)],
            )
            if returncode != 0:
                raise RuntimeError(f'E3001: git clone failed for {owner}/{repo}: {stderr}')

            log.info('Cloned %s/%s to %s', owner, repo, workspace)
        else:
            log.info('Updating %s/%s', owner, repo)

            returncode, _, stderr = await self._run_git(
                ['fetch', 'origin'],
                cwd=workspace,
            )
            if returncode != 0:
                raise RuntimeError(f'E3002: git fetch failed for {owner}/{repo}: {stderr}')

            returncode, default_branch, stderr = await self._run_git(
                ['rev-parse', '--abbrev-ref', 'origin/HEAD'],
                cwd=workspace,
            )
            if returncode != 0:
                default_branch = 'origin/main'

            branch = default_branch.removeprefix('origin/')

            returncode, _, stderr = await self._run_git(
                ['checkout', branch],
                cwd=workspace,
            )
            if returncode != 0:
                raise RuntimeError(f'E3003: git checkout failed for {owner}/{repo}: {stderr}')

            returncode, _, stderr = await self._run_git(
                ['reset', '--hard', f'origin/{branch}'],
                cwd=workspace,
            )
            if returncode != 0:
                raise RuntimeError(f'E3004: git reset failed for {owner}/{repo}: {stderr}')

            returncode, _, stderr = await self._run_git(
                ['clean', '-fd'],
                cwd=workspace,
            )
            if returncode != 0:
                log.warning('E3005: git clean failed for %s/%s: %s', owner, repo, stderr)

            log.info('Updated %s/%s to latest %s', owner, repo, branch)

        return workspace

    async def cleanup_stale(self, max_age_days: int = 7) -> list[str]:
        """
        Compute and remove workspace directories not accessed recently.

        Args:
            max_age_days (int): Maximum days since last access before removal

        Returns:
            list[str]: List of removed workspace paths as owner/repo strings
        """

        removed: list[str] = []
        workspaces_dir = self._config.workspaces_dir

        if not workspaces_dir.exists():
            return removed

        cutoff = time.time() - (max_age_days * 86400)

        for owner_dir in workspaces_dir.iterdir():
            if not owner_dir.is_dir():
                continue
            for repo_dir in owner_dir.iterdir():
                if not repo_dir.is_dir():
                    continue

                stat = repo_dir.stat()
                last_access = stat.st_atime

                if last_access < cutoff:
                    label = f'{owner_dir.name}/{repo_dir.name}'
                    log.info('Removing stale workspace: %s', label)

                    await self._run_git(
                        ['clean', '-fdx'],
                        cwd=repo_dir,
                    )

                    def _remove_tree(path: Path) -> None:
                        import shutil

                        shutil.rmtree(path)

                    await asyncio.to_thread(_remove_tree, repo_dir)
                    removed.append(label)

            if owner_dir.exists() and not any(owner_dir.iterdir()):
                owner_dir.rmdir()

        return removed
