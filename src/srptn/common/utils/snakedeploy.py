"""Reuse repository downloads while deploying from isolated temporary copies."""

import hashlib
import shutil
import subprocess
import tarfile
import tempfile
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from snakedeploy.deploy import WorkflowDeployer
from snakedeploy.providers import Local, Provider, get_provider

if TYPE_CHECKING:
    from ..data import Address
    from ..data.fs import FSDataStore


def _git(repo: Path, *args: str):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def get_git_url(path: Path):
    """Inspect cached origin configuration without renewing its timestamp."""
    repo = path / "repo"
    if not (repo / ".git").is_dir():
        return None
    try:
        return _git(repo, "config", "--get", "remote.origin.url")
    except subprocess.CalledProcessError:
        return None


def hash_url(url: str):
    """Generate a hash for a given URL."""
    return hashlib.sha256(url.encode()).hexdigest()


def git_refresh(repo: Path, url: str):
    _git(repo, "remote", "set-url", "origin", url)
    _git(
        repo,
        "fetch",
        "--filter=tree:0",
        "--no-recurse-submodules",
        "--prune",
        "origin",
        "+refs/heads/*:refs/remotes/origin/*",
        "+refs/tags/*:refs/tags/*",
    )
    _git(repo, "remote", "set-head", "origin", "--auto")


class Version(NamedTuple):
    """A repository and the Git refs that pin a workflow deployment."""

    url: str
    tag: str | None = None
    branch: str | None = None
    commit: str | None = None
    """Commit is None if the workflow is a plain local directory (no Git)."""

    def selection(self, address: "Address"):
        return self.url, self.commit, str(address)

    @property
    def ref(self):
        if self.tag:
            return self.tag
        if self.branch:
            return self.branch
        return self.commit


class RepoRefs(NamedTuple):
    commits: dict[str, tuple[str, datetime]]  # sha -> (subject, commit datetime)
    tags: dict[str, str]  # tag name -> sha
    branches: dict[str, str]  # branch name -> sha
    head: str

    @property
    def default_commit(self):
        """Prefer the newest tagged commit, then the newest commit."""
        if self.tags:
            return next(iter(self.tags.values()))
        if self.commits:
            return next(iter(self.commits))
        raise ValueError("This Git repository contains no commits")

    @classmethod
    def from_repo(cls, repo: Path, *, remote: bool = False):
        """Read refs and commit history locally, without accessing trees or blobs."""

        def refs(prefix: str):
            items: list[tuple[str, str]] = []
            out = _git(
                repo,
                "for-each-ref",
                "--format=%(refname)%09%(objectname)%09%(*objectname)",
                prefix,
            )
            for line in out.splitlines():
                name, _, objects = line.partition("\t")
                objectname, _, deref = objects.partition("\t")
                if name.endswith("/HEAD"):
                    continue
                sha = deref or objectname
                items.append((name.removeprefix(prefix + "/"), sha))
            items.sort(key=lambda item: order.get(item[1], len(order)))
            return dict(items)

        commits: dict[str, tuple[str, datetime]] = {}
        for line in _git(
            repo, "log", "--topo-order", "--all", "HEAD", "--format=%H%x09%ct%x09%s"
        ).splitlines():
            sha, date, subject = line.split("\t", 2)
            commits[sha] = (
                subject,
                datetime.fromtimestamp(int(date), tz=timezone.utc),
            )
        commits = dict(
            sorted(commits.items(), key=lambda item: item[1][1], reverse=True)
        )
        order = {sha: index for index, sha in enumerate(commits)}
        if remote:
            branchref = "refs/remotes/origin"
        else:
            branchref = "refs/heads"
        return cls(
            commits,
            refs("refs/tags"),
            refs("refs/remotes/origin" if remote else branchref),
            _git(repo, "rev-parse", "HEAD^{commit}"),
        )


def export_commit(
    repo: Path,
    commit: str,
    dest: str,
    *,
    require_clean: bool = True,
):
    """Export a resolved commit without .git and return its full SHA."""
    repo = repo.resolve()

    if _git(repo, "rev-parse", "--is-bare-repository") == "true":
        top = Path(_git(repo, "rev-parse", "--absolute-git-dir")).resolve()
    else:
        if require_clean:
            dirty = _git(repo, "status", "--porcelain")
            if dirty:
                raise RuntimeError(f"{repo} is not a clean git repository:\n{dirty}")
        top = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    if top != repo:
        raise RuntimeError(f"{repo} is not a git repository (found {top})")

    sha = _git(repo, "rev-parse", "--verify", commit + "^{commit}")
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "archive", "--format=tar", sha],
        stdout=subprocess.PIPE,
    )
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            tar.extractall(dest, filter="data")
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, proc.args)
    return sha


class CachedWorkflowManager:
    """Own repository caching, synchronization, version queries and deployment."""

    def __init__(self, data_store: "FSDataStore"):
        self.data_store = data_store

    def available_workflows(self):
        # TODO: local urls
        for url, time in self.data_store.cache_entries(filter=get_git_url):
            yield url

    @contextmanager
    def _cached_repository(self, provider: Provider):
        with ExitStack() as stack:
            try:
                entry = stack.enter_context(
                    self.data_store.cache_access(hash_url(provider.source_url))
                )
            except (FileNotFoundError, BlockingIOError):
                entry = Path(stack.enter_context(tempfile.TemporaryDirectory()))

            repo = entry / "repo"
            if not (repo / ".git").is_dir():
                with tempfile.TemporaryDirectory(dir=entry) as staging:
                    _git(
                        entry,
                        "clone",
                        "--filter=tree:0",
                        "--no-checkout",
                        "--no-local",
                        provider.source_url,
                        staging,
                    )
                    git_refresh(Path(staging), provider.source_url)
                    Path(staging).rename(repo)
            yield repo

    def read_workflow_refs(self, url: str, *, refresh: bool = False):
        """Read Git's cached history; synchronize explicitly without file objects."""
        provider: Provider = get_provider(url)
        if isinstance(provider, Local):
            repo = Path(url)
            if (repo / ".git").exists():
                return RepoRefs.from_repo(repo)
            return None
        with self._cached_repository(provider) as repo:
            if refresh:
                git_refresh(repo, provider.source_url)
            return RepoRefs.from_repo(repo, remote=True)

    def resolve_ref(self, url: str, *, tag=None, branch=None):
        """Resolve a named ref against the cached versions without refreshing."""
        refs = self.read_workflow_refs(url)
        if refs is None:
            raise ValueError(f"Workflow {url} is not a Git repository")
        if tag is not None:
            if tag in refs.tags:
                return refs.tags[tag]
            raise ValueError(f"Unknown workflow ref: {tag}")
        elif branch is not None:
            if branch in refs.branches:
                return refs.branches[branch]
            raise ValueError(f"Unknown workflow ref: {branch}")
        raise ValueError("Either tag or branch must be specified for ref resolution")

    def deploy(
        self, data_path: Path, name: str, url: str, *, commit: str | None = None
    ):
        """Deploy ``url`` at ``commit`` into the workspace's data path.

        Previous content is cleared first; the caller rolls back on failure.
        """
        with self.deployer(url, data_path, commit=commit) as deployer:
            deployer.deploy(name)
            schema_path = Path(deployer.repo_clone) / "workflow" / "schemas"
            if schema_path.exists():
                shutil.copytree(schema_path, data_path / "workflow" / "schemas")

    def deployer(self, url: str, dest: Path, *, commit: str | None = None, force=False):
        """Prepare one isolated clone and let snakedeploy use it directly."""
        deployer = WorkflowDeployer(url, dest, force=force)
        provider = deployer.provider
        if isinstance(provider, Local) and not (Path(url) / ".git").exists():
            if commit is not None:
                raise ValueError(f"Workflow {url} is not a Git repository")
            return deployer
        cloned = tempfile.TemporaryDirectory()
        try:
            if isinstance(provider, Local):
                deployer.tag = export_commit(Path(url), commit or "HEAD", cloned.name)
            else:
                with self._cached_repository(provider) as cached:
                    deployer.tag = export_commit(
                        cached,
                        commit or "refs/remotes/origin/HEAD",
                        cloned.name,
                        require_clean=False,
                    )
        except BaseException:
            cloned.cleanup()
            raise
        deployer._cloned = cloned
        return deployer
