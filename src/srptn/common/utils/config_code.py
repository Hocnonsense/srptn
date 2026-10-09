"""Executing maintainer-provided config transformation code.

The code is top-level Python (not a function); it runs with the runner config
injected as ``config`` and may read and write files relative to ``cwd``.
"""

from __future__ import annotations

import tempfile

from contextlib import chdir, contextmanager
from pathlib import Path


@contextmanager
def config_workdir():
    """A throw-away working directory for running the config code."""
    with tempfile.TemporaryDirectory() as temporary:
        yield Path(temporary)


def run_config_code(code: str, config: dict, cwd: Path) -> dict:
    """Execute the maintainer code with ``config`` injected and return it.

    The code runs with the working directory set to ``cwd`` (a temp dir for
    preview, the workspace data folder at run time).  Only the transformed
    ``config`` is returned; use :func:`collect_files` for anything it created.
    """
    namespace = {"config": config}
    with chdir(cwd):
        exec(code, namespace)  # noqa: S102 deliberate execution of curator code
    return namespace["config"]


def collect_files(root: Path):
    """Read every file under ``root`` as ``relative path -> bytes``."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
