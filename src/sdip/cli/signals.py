"""What SIGTERM and SIGINT do to a running `sdip` command (issue #1 part (a), D-0093).

**The contract.** Either signal, delivered to the ``sdip`` process:

1. terminates every child process SDIP's run started — MDIO's spawn-based worker pools,
   which upstream builds and SDIP never holds, and ``verify``'s G4 grandchild;
2. waits for them, and kills any still alive after :data:`GRACE_S`;
3. exits with ``128 + signal number`` — **130** for SIGINT, **143** for SIGTERM — and says
   no verdict was reached.

**Why the children are terminated before anything unwinds.** MDIO enters its pools with
``with ProcessPoolExecutor(...)``. An exception unwinding through that block runs
``shutdown(wait=True)``, which waits for every block already queued: a cancelled ingest
would go on writing until it had finished. So the handler terminates the workers first,
through the standard library's own record of this process's children
(``multiprocessing.active_children``), and only then raises. Nothing in upstream is
touched (§3.3); the pool sees its workers die and breaks, which is what lets the
``with`` block exit.

**The G4 grandchild** is a ``subprocess.run`` child, which the standard library kills when
an exception passes through ``run``. :class:`TerminatedBySignal` is that exception.

**Never a verdict.** 130 and 143 are outside SDIP's verdict codes (0 PASS, 1 FAIL or a
refusal, 2 usage, 3 internal defect). A store an ``ingest`` was writing when the signal
arrived carries **no provenance marker**, because the marker is written last
(``ingest/orchestrator.py``), so it is detectable as incomplete without being judged.

**Parent only.** Handlers are installed by :func:`install` from the console entry point.
Spawn children start a fresh interpreter that never runs it, so a worker's own SIGINT —
a terminal's Ctrl-C reaches the whole process group — stays Python's default.
"""

from __future__ import annotations

import multiprocessing
import signal
from types import FrameType
from typing import Final

HANDLED: Final[tuple[signal.Signals, ...]] = (signal.SIGTERM, signal.SIGINT)

GRACE_S: Final[float] = 5.0
"""How long a terminated child has to exit before it is killed."""


class TerminatedBySignal(BaseException):
    """Raised in the main thread when ``sdip`` receives a handled signal.

    A ``BaseException`` so that no ``except Exception`` on the way out can turn a
    cancellation into a verdict or an internal error.
    """

    def __init__(self, signum: int) -> None:
        """Record which signal stopped the run."""
        self.signum = signum
        super().__init__(signal.Signals(signum).name)

    @property
    def exit_code(self) -> int:
        """``128 + signal number``, the shell's own convention for death by signal."""
        return 128 + self.signum


def stop_children(grace_s: float = GRACE_S) -> list[int]:
    """Terminate every child process this process started, wait, then kill stragglers.

    Returns:
        The PIDs that had to be killed after the grace period.
    """
    children = multiprocessing.active_children()
    for child in children:
        child.terminate()
    killed = []
    for child in children:
        child.join(grace_s)
        if child.is_alive():
            child.kill()
            child.join(grace_s)
            killed.append(child.pid or -1)
    return killed


_terminating = False


def _handler(signum: int, _frame: FrameType | None) -> None:
    global _terminating  # one process-wide fact: a stop is under way
    if _terminating:
        return
    _terminating = True
    stop_children()
    raise TerminatedBySignal(signum)


def install() -> None:
    """Install the handlers. Called once, from the console entry point only."""
    for sig in HANDLED:
        signal.signal(sig, _handler)
