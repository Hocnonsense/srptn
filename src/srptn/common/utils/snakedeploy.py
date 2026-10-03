"""Reuse repository downloads while deploying from isolated temporary copies."""

from collections.abc import Callable
import fcntl
from pathlib import Path
import subprocess
import tempfile

from snakedeploy.deploy import WorkflowDeployer
from snakedeploy.providers import Local


def _git(repo: Path, *args: str):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _default_branch(repo: Path):
    return _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD").removeprefix(
        "refs/remotes/origin/"
    )


class CachedWorkflowDeployer(WorkflowDeployer):
    """Cache by source URL; leave cache timestamps and expiry to the callback."""

    def __init__(
        self,
        source: str,
        dest: Path,
        tag: str | None = None,
        branch: str | None = None,
        force: bool = False,
        *,
        cache: Callable[[str], Path] | None = None,
    ):
        super().__init__(source, dest, tag=tag, branch=branch, force=force)
        self.cache = cache
        self._cache_path: Path | None = None

    def __exit__(self, exc, value, tb):
        if self._cloned is not None:
            self._cloned.cleanup()
            self._cloned = None

    @property
    def repo_clone(self):
        if (
            self._cloned is not None
            or isinstance(self.provider, Local)
            or self.cache is None
        ):
            return super().repo_clone
        try:
            self._cache_path = self.cache(self.provider.source_url)
        except Exception:
            return super().repo_clone
        self._cache_path.mkdir(parents=True, exist_ok=True)
        # Serialize repository updates and snapshots, independently of cache expiry.
        repo = self._cache_path / "repo"
        with (self._cache_path / ".repo.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            provider = self.provider
            if not (repo / ".git").is_dir():
                provider.clone(repo)
            else:
                _git(repo, "remote", "set-url", "origin", provider.source_url)
                _git(
                    repo,
                    "fetch",
                    "--prune",
                    "--tags",
                    "origin",
                    "+refs/heads/*:refs/remotes/origin/*",
                )
            if self.tag is not None:
                provider.checkout(str(repo), f"refs/tags/{self.tag}")
            else:
                branch = self.branch or _default_branch(repo)
                _git(repo, "checkout", "-B", branch, f"origin/{branch}")
            name = None
            try:
                self.provider = Local(str(repo))
                name = super().repo_clone
            finally:
                self.provider = provider
                if name is None:
                    if self._cloned is not None:
                        self._cloned.cleanup()
                        self._cloned = None
                    name = super().repo_clone
        return name
