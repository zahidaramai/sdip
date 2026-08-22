"""Git state capture. Spec section 11.3 - a certificate from a dirty tree is invalid.

There is no ``--force``. If the tree is dirty the run is not reproducible from the
committed record, and a certificate that cannot be reproduced is not evidence.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TIMEOUT = 30


def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    """Run git and return ``(returncode, raw_stdout)``.

    stdout is returned **unstripped**. ``git status --porcelain=v1`` encodes the
    status in the first two columns, so a leading space is significant: stripping it
    turns ``" M a.txt"`` into ``"M a.txt"`` and shifts every path by one character.
    Callers that want a single token strip it themselves.
    """
    exe = shutil.which("git")
    if exe is None:  # pragma: no cover - git absent
        return 127, ""
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell, resolved executable
            [exe, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:  # pragma: no cover
        return 124, ""
    return proc.returncode, proc.stdout


@dataclass(slots=True)
class GitState:
    """Repository state at the moment of capture."""

    is_repository: bool
    commit: str | None
    branch: str | None
    dirty: bool
    dirty_paths: tuple[str, ...]
    describe: str | None

    @property
    def certifiable(self) -> bool:
        """True only when a certificate may be issued from this state."""
        return self.is_repository and not self.dirty and self.commit is not None

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping for the ``git`` block."""
        return {
            "is_repository": self.is_repository,
            "sdip_commit": self.commit,
            "branch": self.branch,
            "dirty": self.dirty,
            "dirty_paths": list(self.dirty_paths),
            "describe": self.describe,
        }


def capture_git_state(root: str | Path = ".") -> GitState:
    """Capture the working-tree state of the repository containing ``root``.

    Untracked files count as dirty. An untracked file can change a run's behaviour
    just as easily as a modified one, and neither is in the committed record.
    """
    cwd = Path(root).resolve()
    rc, _ = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if rc != 0:
        return GitState(
            is_repository=False,
            commit=None,
            branch=None,
            dirty=True,
            dirty_paths=(),
            describe=None,
        )

    rc_commit, commit = _git(["rev-parse", "HEAD"], cwd)
    rc_branch, branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    _, status = _git(["status", "--porcelain=v1", "--untracked-files=all", "-z"], cwd)
    rc_desc, describe = _git(["describe", "--tags", "--always", "--dirty"], cwd)

    # -z gives NUL-separated records with no quoting or path mangling, so a path
    # containing a space, a quote, or a non-ASCII byte survives intact. Each record
    # is "XY PATH"; a rename additionally emits its source path as its own record,
    # which is still a dirty path and is kept.
    paths = tuple(
        record[3:] for record in status.split("\0") if len(record) > 3 and record[2] == " "
    )
    return GitState(
        is_repository=True,
        commit=commit.strip() if rc_commit == 0 else None,
        branch=branch.strip() if rc_branch == 0 else None,
        dirty=bool(paths),
        dirty_paths=paths,
        describe=describe.strip() if rc_desc == 0 else None,
    )
