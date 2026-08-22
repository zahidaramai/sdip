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
from typing import Any, NoReturn

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


@cli.command("ingest")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("output", type=click.Path(path_type=Path))
@click.option(
    "--revision",
    type=click.Choice(["0", "1", "2", "2.1"]),
    default="1",
    show_default=True,
    help="SEG-Y revision for the base spec.",
)
@click.option("--template", default="PostStack3DTime", show_default=True, help="MDIO template.")
@click.option("--overwrite", is_flag=True, help="Overwrite an existing store.")
@click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable report.")
def ingest_cmd(
    source: Path, output: Path, revision: str, template: str, overwrite: bool, as_json: bool
) -> None:
    """SEG-Y to MDIO, against a gap-free spec.

    Runs G1 before a single trace is read, captures the raw textual and binary headers
    directly from the source, and records every warning and every filter the run
    installed. Exits 1 if G1 fails or the source hash changes during the run.
    """
    from sdip.ingest import ingest as run_ingest

    number: float | int = float(revision) if "." in revision else int(revision)
    result = run_ingest(source, output, revision=number, template=template, overwrite=overwrite)

    if as_json:
        click.echo(json.dumps(result.to_json(), indent=2, sort_keys=True))
    else:
        click.echo(f"source        {result.source_path}")
        click.echo(f"source bytes  {result.source_bytes}")
        click.echo(f"source sha256 {result.source_sha256}")
        click.echo(f"spec          {result.spec.spec_id} ({result.spec.field_count} fields)")
        click.echo(f"G1            {result.g1.status}")
        click.echo(f"output        {result.output_path}")
        click.echo(
            f"read path     {'intact' if result.read_path_intact else 'CORRUPTED'} "
            "(source re-hashed after ingest)"
        )
        ledger = result.warnings
        click.echo(
            f"warnings      {len(ledger.observed)} observed, "
            f"{len(ledger.suppressions)} suppression(s), "
            f"{len(ledger.undeclared_suppressions)} UNDECLARED"
        )

    sys.exit(EXIT_OK if result.read_path_intact else EXIT_FAIL)


def _run_planes(source: Path, store: Path, spec: object, *, g1_passed: bool) -> list[Any]:
    from sdip.equivalence import plane_1, plane_2, plane_3, plane_4, plane_5

    return [
        plane_1(source, store),
        plane_2(source, store),
        plane_3(source, store, spec, g1_passed=g1_passed),
        plane_4(source, store, spec),
        plane_5(source, store, spec),
    ]


def _print_planes(planes: list[Any]) -> None:
    for plane in planes:
        mark = "PASS" if plane.passed else "FAIL"
        click.echo(f"[{mark}] Plane {plane.plane} ({plane.gate})  {plane.title}")
        difference = plane.evidence.get("first_difference")
        if difference:
            click.echo(f"       first difference: {difference}")


@cli.command("verify")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("store", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--revision", type=click.Choice(["0", "1", "2", "2.1"]), default="1", show_default=True
)
@click.option("--skip-portability", is_flag=True, help="Skip G4 (it spawns a subprocess).")
@click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable report.")
def verify_cmd(
    source: Path, store: Path, revision: str, skip_portability: bool, as_json: bool
) -> None:
    """Run the Equivalence Engine against a store: five planes plus G4.

    Compares the store on disk against the source on disk. Exits 1 if any plane fails
    or G4 fails.
    """
    from sdip.equivalence import g4
    from sdip.spec import build_gap_free_spec, g1_for_spec

    number: float | int = float(revision) if "." in revision else int(revision)
    built = build_gap_free_spec(number)
    gate1 = g1_for_spec(built)
    planes = _run_planes(source, store, built.segy_spec, g1_passed=gate1.passed)
    portability = None if skip_portability else g4(store)

    ok = (
        gate1.passed
        and all(p.passed for p in planes)
        and (portability is None or portability.passed)
    )

    if as_json:
        click.echo(
            json.dumps(
                {
                    "command": "verify",
                    "G1": gate1.to_json(),
                    "planes": {f"plane_{p.plane}": p.to_json() for p in planes},
                    "G4": portability.to_json() if portability else None,
                    "verdict": "PASS" if ok else "FAIL",
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        click.echo(f"[{gate1.status}] G1        {gate1.summary()}")
        _print_planes(planes)
        if portability is not None:
            click.echo(
                f"[{portability.status}] G4        stock zarr+xarray, mdio never "
                f"imported: {portability.mdio_absent}; non-core dtypes: "
                f"{', '.join(portability.non_core_arrays) or 'none'}"
            )
        click.echo("")
        click.echo(f"verify: {'PASS' if ok else 'FAIL'}")

    sys.exit(EXIT_OK if ok else EXIT_FAIL)


@cli.command("export")
@click.argument("store", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output", type=click.Path(path_type=Path))
@click.option(
    "--source",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Original SEG-Y, for the G3 hash comparison.",
)
@click.option(
    "--revision", type=click.Choice(["0", "1", "2", "2.1"]), default="1", show_default=True
)
@click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable report.")
def export_cmd(store: Path, output: Path, source: Path, revision: str, as_json: bool) -> None:
    """MDIO to SEG-Y, then run G3 against the source.

    G3 passes only on whole-file SHA-256 equality. Exits 1 on any mismatch.
    """
    from sdip.export import export as run_export
    from sdip.spec import build_gap_free_spec

    number: float | int = float(revision) if "." in revision else int(revision)
    built = build_gap_free_spec(number)
    result = run_export(store, output, built.segy_spec, source=source)

    if as_json:
        click.echo(json.dumps(result.to_json(), indent=2, sort_keys=True))
    else:
        click.echo(f"source  {result.source_sha256}  {result.source_bytes} bytes")
        click.echo(f"export  {result.export_sha256}  {result.export_bytes} bytes")
        difference = result.first_difference()
        if difference:
            click.echo(f"first difference: {difference}")
        click.echo("")
        click.echo(f"G3: {result.status}")

    sys.exit(EXIT_OK if result.passed else EXIT_FAIL)


@cli.command("certify")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("output", type=click.Path(path_type=Path))
@click.option(
    "--revision", type=click.Choice(["0", "1", "2", "2.1"]), default="1", show_default=True
)
@click.option("--template", default="PostStack3DTime", show_default=True)
@click.option("--overwrite", is_flag=True)
@click.option(
    "--certificates",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("certificates"),
    show_default=True,
    help="Where to write the certificate JSON.",
)
def certify_cmd(
    source: Path,
    output: Path,
    revision: str,
    template: str,
    overwrite: bool,
    certificates: Path,
) -> None:
    """Full chain: ingest, five planes, round trip, portability, certificate.

    Refuses to issue from a dirty working tree (spec 11.3). **There is no --force.**

    The best verdict reachable today is PROVISIONAL: G7 does not exist, and a store
    whose planes pass against an engine never shown capable of failing has not been
    checked (OPEN_DEBTS D11).
    """
    import datetime as _dt
    import tempfile

    from sdip.equivalence import g4, issue
    from sdip.export import export as run_export
    from sdip.ingest import ingest as run_ingest
    from sdip.spec import g1_for_spec

    number: float | int = float(revision) if "." in revision else int(revision)
    result = run_ingest(source, output, revision=number, template=template, overwrite=overwrite)
    spec = result.spec.segy_spec
    gate1 = g1_for_spec(result.spec)
    planes = _run_planes(source, output, spec, g1_passed=gate1.passed)
    portability = g4(output)

    with tempfile.TemporaryDirectory() as scratch:
        roundtrip = run_export(output, Path(scratch) / "roundtrip.sgy", spec, source=source)
        issued_at = _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")
        certificate = issue(
            result,
            planes,
            roundtrip=roundtrip,
            portability=portability,
            issued_at=issued_at,
            issued_by=f"sdip {__version__}",
        )

    certificates.mkdir(parents=True, exist_ok=True)
    stamp = issued_at.replace(":", "").replace("-", "")
    path = certificates / f"{result.source_sha256[:12]}-{stamp}.json"
    path.write_text(json.dumps(certificate.payload, indent=2, sort_keys=True))

    _print_planes(planes)
    click.echo(f"[{roundtrip.status}] G3        whole-file SHA-256")
    click.echo(f"[{portability.status}] G4        stock zarr+xarray without mdio")
    click.echo("")
    click.echo(f"verdict:     {certificate.verdict}")
    click.echo(f"reason:      {certificate.payload['verdict_reason']}")
    click.echo(f"certificate: {path}")

    sys.exit(EXIT_OK if certificate.verdict == "EQUIVALENT" else EXIT_FAIL)


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
