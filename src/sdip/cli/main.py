"""``sdip`` entry point.

Six commands (spec section 7). Only ``doctor`` is implemented at roadmap phase F0.
The rest are declared and refuse: an unimplemented command that prints a plausible
result is worse than one that says it is not built yet.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

import click

from sdip import __version__
from sdip._pins import SPEC_VERSION
from sdip.cli.doctor import environment_block, run_doctor
from sdip.cli.result import Report, Status
from sdip.errors import PhaseNotAuthorisedError

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_GLYPH = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.NOT_RUN: " -- "}


def _emit(report: Report, *, as_json: bool, extra: Mapping[str, object] | None = None) -> int:
    if as_json:
        payload = report.to_json()
        if extra:
            payload |= dict(extra)
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        width = max(len(c.name) for c in report.checks)
        for check in report.checks:
            click.echo(f"[{_GLYPH[check.status]}] {check.name:<{width}}  {check.summary}")
        click.echo("")
        if report.ok:
            click.echo(f"doctor: PASS ({len(report.checks)} checks)")
        else:
            click.echo(
                f"doctor: FAIL ({len(report.failed)} of {len(report.checks)} checks) "
                f"-> {', '.join(c.clause for c in report.failed)}"
            )
    return EXIT_OK if report.ok else EXIT_FAIL


def _not_yet(command: str, phase: str, what: str) -> NoReturn:
    raise PhaseNotAuthorisedError(
        f"`sdip {command}` is roadmap phase {phase} (spec section 13). {what} "
        "The repository is at F0; nothing is stubbed out to look like it works."
    )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(
    __version__,
    "-V",
    "--version",
    message=f"sdip %(version)s (specification v{SPEC_VERSION})",
)
def cli() -> None:
    """SEG-Y to MDIO/Zarr v3 with a machine-checkable proof of 1-1 equivalence.

    The product is not the file. The product is the file plus the proof.
    """


@cli.command()
@click.option(
    "--root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path.cwd,
    help="Repository root to inspect for working-tree state.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable report.")
def doctor(root: Path, as_json: bool) -> None:
    """Environment sanity: barred vars, barred packages, pins, licences, tree.

    Runs first in CI and first in every runbook. If doctor fails, nothing else runs.
    Exits 0 when every check passes, 1 otherwise. There is no override flag.
    """
    report = run_doctor(root)
    extra = {"environment": environment_block()} if as_json else None
    sys.exit(_emit(report, as_json=as_json, extra=extra))


@cli.group()
def spec() -> None:
    """Gap-free trace-header specification (spec section 5). Phase F1."""


@spec.command("build")
@click.option(
    "--revision",
    type=click.Choice(["0", "1", "2", "2.1"]),
    default="1",
    show_default=True,
    help="SEG-Y revision to build the gap-free spec for.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable report.")
def spec_build(revision: str, as_json: bool) -> None:
    """Generate and validate a gap-free spec; runs G1.

    Emits one uint8 filler per uncovered byte and asserts coverage of bytes 1-240 with
    zero gaps, zero overlaps, and no numpy void padding. Exits 1 if G1 fails - a
    failing G1 aborts ingestion before a single trace is read.
    """
    from sdip.spec import build_gap_free_spec, g1_for_spec

    number: float | int = float(revision) if "." in revision else int(revision)
    built = build_gap_free_spec(number)
    result = g1_for_spec(built)

    if as_json:
        click.echo(
            json.dumps(
                {"command": "spec build", "spec": built.to_json(), "G1": result.to_json()},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        click.echo(f"revision      SEG-Y rev {built.revision}")
        click.echo(f"base fields   {built.base_field_count}")
        click.echo(
            f"fillers       {len(built.fillers)} uint8"
            + (
                f"  ({built.fillers[0]}..{built.fillers[-1]})"
                if built.fillers
                else "  (already gap-free)"
            )
        )
        click.echo(f"spec fields   {built.field_count}")
        click.echo(f"itemsize      {built.itemsize}")
        click.echo(f"spec_id       {built.spec_id}")
        click.echo(f"spec_sha256   {built.sha256()}")
        click.echo("")
        for condition in result.conditions:
            mark = "PASS" if condition.passed else "FAIL"
            click.echo(f"[{mark}] {condition.name:<13} {condition.detail}")
        click.echo("")
        click.echo(result.summary())

    sys.exit(EXIT_OK if result.passed else EXIT_FAIL)


@cli.command()
def ingest() -> NoReturn:
    """SEG-Y to MDIO. Must sit behind a ``__main__`` guard (spec 11.1). Phase F2."""
    _not_yet("ingest", "F2", "It orchestrates the MDIO converter over a gap-free spec.")


@cli.command()
def verify() -> NoReturn:
    """Run the Equivalence Engine against a store (G2, G4). Phase F3."""
    _not_yet("verify", "F3", "It checks the five planes with no tolerance anywhere.")


@cli.command()
def export() -> NoReturn:
    """MDIO to SEG-Y. Phase F3."""
    _not_yet("export", "F3", "It drives the round trip that G3 hashes.")


@cli.command()
def certify() -> NoReturn:
    """Full chain plus round trip; issue the certificate (G1-G7). Phase F3-F4."""
    _not_yet(
        "certify",
        "F3-F4",
        "Until G7 passes, every certificate the engine issues is unvalidated.",
    )


def main() -> None:
    """Console-script entry point."""
    try:
        cli.main(standalone_mode=False)
    except PhaseNotAuthorisedError as exc:
        click.echo(f"sdip: {exc}", err=True)
        sys.exit(EXIT_USAGE)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.Abort:  # pragma: no cover - user interrupt
        click.echo("sdip: aborted", err=True)
        sys.exit(EXIT_USAGE)


if __name__ == "__main__":  # pragma: no cover
    main()
