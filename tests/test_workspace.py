import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent0.config import Config
from agent0.workspace import WorkspaceManager


def _make_config(tmp_path: Path) -> Config:
    """
    Compute test configuration with temp data directory.

    Args:
        tmp_path (Path): Pytest temporary directory

    Returns:
        Config: Test config
    """

    return Config(
        github_token='ghp_test123',
        anthropic_api_key='test',
        github_user='test-bot',
        claude_model='test-model',
        whitelisted_orgs=('testorg',),
        data_dir=tmp_path,
    )


class TestWorkspacePath:
    def test_path_construction(self, tmp_path: Path) -> None:
        """
        Compute that workspace path follows owner/repo structure.

        Returns:
            None
        """

        mgr = WorkspaceManager(_make_config(tmp_path))
        path = mgr._workspace_path('myorg', 'myrepo')
        assert path == tmp_path / 'workspaces' / 'myorg' / 'myrepo'


class TestCloneUrl:
    def test_token_embedded(self, tmp_path: Path) -> None:
        """
        Compute that clone URL contains the token.

        Returns:
            None
        """

        mgr = WorkspaceManager(_make_config(tmp_path))
        url = mgr._clone_url('myorg', 'myrepo')
        assert url == 'https://x-access-token:ghp_test123@github.com/myorg/myrepo.git'


class TestPrepare:
    @pytest.mark.asyncio
    async def test_clone_new_repo(self, tmp_path: Path) -> None:
        """
        Compute that a new repo triggers git clone.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        with patch.object(mgr, '_run_git', new_callable=AsyncMock) as mock_git:
            mock_git.return_value = (0, '', '')

            result = await mgr.prepare('myorg', 'myrepo')

            assert result == tmp_path / 'workspaces' / 'myorg' / 'myrepo'
            calls = mock_git.call_args_list
            assert len(calls) == 1
            args = calls[0][0][0]
            assert args[0] == 'clone'

    @pytest.mark.asyncio
    async def test_update_existing_repo(self, tmp_path: Path) -> None:
        """
        Compute that existing repo triggers fetch and reset.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        workspace = tmp_path / 'workspaces' / 'myorg' / 'myrepo'
        workspace.mkdir(parents=True)

        with patch.object(mgr, '_run_git', new_callable=AsyncMock) as mock_git:
            mock_git.return_value = (0, 'origin/main', '')

            result = await mgr.prepare('myorg', 'myrepo')

            assert result == workspace
            call_args = [c[0][0] for c in mock_git.call_args_list]

            assert call_args[0] == ['fetch', 'origin']
            assert call_args[1] == ['rev-parse', '--abbrev-ref', 'origin/HEAD']
            assert call_args[2] == ['checkout', 'main']
            assert call_args[3] == ['reset', '--hard', 'origin/main']
            assert call_args[4] == ['clean', '-fd']

    @pytest.mark.asyncio
    async def test_clone_failure_raises(self, tmp_path: Path) -> None:
        """
        Compute that clone failure raises RuntimeError.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        with patch.object(mgr, '_run_git', new_callable=AsyncMock) as mock_git:
            mock_git.return_value = (128, '', 'fatal: repository not found')

            with pytest.raises(RuntimeError, match='git clone failed'):
                await mgr.prepare('myorg', 'myrepo')

    @pytest.mark.asyncio
    async def test_fetch_failure_raises(self, tmp_path: Path) -> None:
        """
        Compute that fetch failure raises RuntimeError.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        workspace = tmp_path / 'workspaces' / 'myorg' / 'myrepo'
        workspace.mkdir(parents=True)

        with patch.object(mgr, '_run_git', new_callable=AsyncMock) as mock_git:
            mock_git.return_value = (1, '', 'network error')

            with pytest.raises(RuntimeError, match='git fetch failed'):
                await mgr.prepare('myorg', 'myrepo')

    @pytest.mark.asyncio
    async def test_default_branch_fallback(self, tmp_path: Path) -> None:
        """
        Compute that rev-parse failure falls back to origin/main.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        workspace = tmp_path / 'workspaces' / 'myorg' / 'myrepo'
        workspace.mkdir(parents=True)

        call_count = 0

        async def side_effect(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
            nonlocal call_count
            call_count += 1
            if args[0] == 'rev-parse':
                return (1, '', 'fatal: not found')
            return (0, '', '')

        with patch.object(mgr, '_run_git', side_effect=side_effect):
            await mgr.prepare('myorg', 'myrepo')

        assert call_count == 5


class TestCleanupStale:
    @pytest.mark.asyncio
    async def test_no_workspaces_dir(self, tmp_path: Path) -> None:
        """
        Compute that missing workspaces directory returns empty list.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        result = await mgr.cleanup_stale()
        assert result == []

    @pytest.mark.asyncio
    async def test_removes_stale_workspace(self, tmp_path: Path) -> None:
        """
        Compute that workspace older than threshold is removed.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        workspace = tmp_path / 'workspaces' / 'myorg' / 'oldrepo'
        workspace.mkdir(parents=True)
        (workspace / 'file.txt').write_text('data')

        old_time = time.time() - (8 * 86400)
        import os

        os.utime(workspace, (old_time, old_time))

        with patch.object(mgr, '_run_git', new_callable=AsyncMock) as mock_git:
            mock_git.return_value = (0, '', '')
            result = await mgr.cleanup_stale(max_age_days=7)

        assert 'myorg/oldrepo' in result
        assert not workspace.exists()

    @pytest.mark.asyncio
    async def test_keeps_fresh_workspace(self, tmp_path: Path) -> None:
        """
        Compute that recently accessed workspace is kept.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        workspace = tmp_path / 'workspaces' / 'myorg' / 'freshrepo'
        workspace.mkdir(parents=True)
        (workspace / 'file.txt').write_text('data')

        result = await mgr.cleanup_stale(max_age_days=7)

        assert result == []
        assert workspace.exists()

    @pytest.mark.asyncio
    async def test_removes_empty_owner_dir(self, tmp_path: Path) -> None:
        """
        Compute that empty owner directory is removed after cleanup.

        Returns:
            None
        """

        config = _make_config(tmp_path)
        mgr = WorkspaceManager(config)

        owner_dir = tmp_path / 'workspaces' / 'myorg'
        workspace = owner_dir / 'oldrepo'
        workspace.mkdir(parents=True)
        (workspace / 'file.txt').write_text('data')

        old_time = time.time() - (8 * 86400)
        import os

        os.utime(workspace, (old_time, old_time))

        with patch.object(mgr, '_run_git', new_callable=AsyncMock) as mock_git:
            mock_git.return_value = (0, '', '')
            await mgr.cleanup_stale(max_age_days=7)

        assert not owner_dir.exists()
