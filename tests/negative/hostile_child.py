"""One hostile-input run, in its own process. Debt **D8**, specification §11.4.

Run as a script, never imported by the suite. Three reasons it has to be a subprocess:

**1. Peak RSS is a process property.** "No unbounded allocation" is a claim about how
much memory the run reached, and a pytest process that has already ingested other
fixtures cannot answer that about any single one of them.

**2. A crash has to be observable as a crash.** §11.4 bars a crash, and an assertion
inside the same interpreter cannot survive a segmentation fault or an OOM kill to
report one. A parent that reads a missing report and a negative return code can.

**3. The `__main__` guard is the thing under test as well.** MDIO's header parser uses a
`spawn` context (specification §11.1), so an entry point that can reach ingestion must sit
behind ``if __name__ == "__main__":``. This file does, and it reaches ingestion.

The child runs **two phases against the same source**, because the two questions §11.4
asks are answered at different layers:

``api``
    :func:`sdip.ingest.ingest` directly - does the library raise a typed
    :class:`~sdip.errors.SdipError`, or does an unhandled ``struct.error`` /
    ``ValueError`` / ``MemoryError`` escape?
``cli``
    :func:`sdip.cli.main.main` through ``sys.argv`` - does the console entry point exit
    non-zero, and does it do so by reporting rather than by unwinding a traceback?

Both write into the **declared output directory** and nowhere else. The parent watches
the filesystem around the whole run; this file deliberately does no cleanup, so anything
that escapes is still there to be found.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import resource
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

EXIT_REPORT_WRITTEN = 0
"""The child finished and wrote a report. The *report* carries the verdict, not this."""


def _peak_rss_bytes() -> int:
    """Peak resident set size of this process and every child it waited on.

    ``ru_maxrss`` is bytes on Darwin and kibibytes on Linux. Getting that wrong by a
    factor of 1024 in either direction turns the memory ceiling into either a
    formality or a permanent failure, so it is converted here, once, explicitly.
    """
    scale = 1 if sys.platform == "darwin" else 1024
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale
    kids = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * scale
    return max(own, kids)


def _describe(exc: BaseException) -> dict[str, Any]:
    """Type, defining module and message of an exception, for the parent to judge."""
    return {
        "type": type(exc).__name__,
        "module": type(exc).__module__,
        "message": str(exc)[:400],
        "is_sdip_error": _is_sdip_error(exc),
    }


def _is_sdip_error(exc: BaseException) -> bool:
    """True when the exception is one SDIP raises deliberately.

    Imported here rather than at module scope so that a failure to import ``sdip`` at
    all is itself reported as an outcome instead of killing the child before it can
    write anything.
    """
    from sdip.errors import SdipError

    return isinstance(exc, SdipError)


def _raised_in(exc: BaseException) -> str:
    """The top-level package of the frame that actually raised.

    **This is how "validated before allocating" is measured**, and it is a better
    instrument than a memory number. A refusal raised in ``sdip`` happened before the
    source ever reached a parser; the same refusal raised in ``segy`` or ``mdio``
    happened after upstream had already read, sized and decoded from
    attacker-controlled counts. The two are indistinguishable by exception type on a
    small fixture and unmistakable here.
    """
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    parts = Path(frames[-1].filename).parts
    if "site-packages" in parts:
        return parts[parts.index("site-packages") + 1]
    if "src" in parts:
        return parts[parts.index("src") + 1]
    return Path(frames[-1].filename).stem


def _run_api(source: Path, output: Path) -> dict[str, Any]:
    """Call the library entry point and record exactly what came back out."""
    from sdip.ingest import ingest

    try:
        result = ingest(source, output)
    except BaseException as exc:  # recording the type IS the measurement
        frames = len(traceback.format_exc().splitlines())
        return {
            "outcome": "raised",
            "traceback_lines": frames,
            "raised_in": _raised_in(exc),
        } | _describe(exc)
    return {"outcome": "returned", "output_path": result.output_path}


def _run_cli(source: Path, output: Path) -> dict[str, Any]:
    """Invoke the console entry point and record its exit code and what escaped it.

    ``main`` is called rather than a subprocess so the whole child stays inside one
    RSS measurement. Its output is captured: a console entry point that reports a
    hostile file by printing a 20-frame traceback has not produced a *clean* error,
    and the only way to see that is to keep the text.
    """
    from sdip.cli.main import main

    argv = ["sdip", "ingest", str(source), str(output)]
    out, err = io.StringIO(), io.StringIO()
    escaped: dict[str, Any] | None = None
    code: int | None = None
    previous = sys.argv
    sys.argv = argv
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                main()
            except SystemExit as exc:
                code = 0 if exc.code is None else int(exc.code) if isinstance(exc.code, int) else 1
            except BaseException as exc:  # recording the type IS the measurement
                escaped = _describe(exc)
    finally:
        sys.argv = previous
    return {
        "exit_code": code,
        "escaped": escaped,
        "stdout": out.getvalue()[-2000:],
        "stderr": err.getvalue()[-2000:],
    }


def main() -> int:
    """Run both phases against one source and write the report."""
    parser = argparse.ArgumentParser(description="Run one hostile SEG-Y through SDIP.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--cwd", required=True, type=Path)
    args = parser.parse_args()

    os.chdir(args.cwd)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {"source": str(args.source)}
    report["api"] = _run_api(args.source, args.output_dir / "api.mdio")
    report["cli"] = _run_cli(args.source, args.output_dir / "cli.mdio")
    report["peak_rss_bytes"] = _peak_rss_bytes()
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True))
    return EXIT_REPORT_WRITTEN


if __name__ == "__main__":  # pragma: no cover - spec 11.1
    sys.exit(main())
