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

OVERRIDE_HELP = (
    "Survey spec override to apply over the gap-free base (spec 6.4). A committed TOML "
    "file, conventionally under overrides/. It renames and retypes bytes the base spec "
    "already covered and changes no byte content; G1 is re-asserted after it is applied "
    "and Plane 3 (G2c) re-verifies the bytes on every ingest."
)

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
@click.option(
    "--override",
    "override_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=OVERRIDE_HELP,
)
@click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable report.")
def spec_build(revision: str, override_path: Path | None, as_json: bool) -> None:
    """Generate and validate a gap-free spec; runs G1.

    Emits one uint8 filler per uncovered byte and asserts coverage of bytes 1-240 with
    zero gaps, zero overlaps, and no numpy void padding. Exits 1 if G1 fails - a
    failing G1 aborts ingestion before a single trace is read.

    With --override, the named survey override is applied over the gap-free base and G1
    is asserted again afterwards. An override that declares ibm32 is refused outright:
    probe P2 measured that transform as not exactly invertible (DECISIONS.md D-0034).
    """
    from sdip.spec import build_gap_free_spec, g1_for_spec, load_override

    number: float | int = float(revision) if "." in revision else int(revision)
    override = load_override(override_path) if override_path else None
    built = build_gap_free_spec(number, override=override)
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
        if built.override is not None:
            declared = ", ".join(
                f"{f.name}@{f.byte}:{f.format}"
                for f in sorted(built.override.fields, key=lambda f: f.byte)
            )
            click.echo(f"override      {built.override.identifier}  [{declared}]")
            endianness = built.override.endianness
            if endianness is not None:
                click.echo(f"endianness    {endianness}")
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
@click.option(
    "--override",
    "override_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=OVERRIDE_HELP,
)
@click.option("--json", "as_json", is_flag=True, help="Emit a machine-readable report.")
def ingest_cmd(
    source: Path,
    output: Path,
    revision: str,
    template: str,
    overwrite: bool,
    override_path: Path | None,
    as_json: bool,
) -> None:
    """SEG-Y to MDIO, against a gap-free spec.

    Runs G1 before a single trace is read, captures the raw textual and binary headers
    directly from the source, and records every warning and every filter the run
    installed. Exits 1 if G1 fails or the source hash changes during the run.

    --override supplies a survey spec override (spec 6.4) - the mechanism that lets a
    template find index fields the revision standard does not name, such as inline and
    crossline in a rev 0 file. It is applied before G1 and changes no byte content.
    """
    from sdip.ingest import ingest as run_ingest
    from sdip.spec import load_override

    number: float | int = float(revision) if "." in revision else int(revision)
    override = load_override(override_path) if override_path else None
    result = run_ingest(
        source,
        output,
        revision=number,
        template=template,
        overwrite=overwrite,
        override=override,
    )

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
    "--rss-ceiling-gib",
    type=float,
    default=None,
    help=(
        "Declared peak-RSS ceiling in GiB. Enables gate G5. There is no default: a "
        "ceiling this tool chose is not one you committed to before the run (SP9)."
    ),
)
@click.option(
    "--wall-ceiling-s",
    type=float,
    default=None,
    help="Declared wall-clock ceiling in seconds. Enables gate G5. No default, per SP9.",
)
@click.option(
    "--prereg",
    default=None,
    help="Where the ceilings were declared, e.g. 'prereg/P3-scale.md@690b05e'.",
)
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
    rss_ceiling_gib: float | None,
    wall_ceiling_s: float | None,
    prereg: str | None,
    certificates: Path,
) -> None:
    """Full chain: ingest, five planes, round trip, portability, certificate.

    Refuses to issue from a dirty working tree (spec 11.3). **There is no --force.**

    Gate G5 runs only when a ceiling is declared on the command line. That is not an
    oversight: G5 judges what a run cost against a limit somebody committed to
    beforehand, and a default ceiling would be a limit this tool invented (SP9). Without
    one, G5 is recorded NOT_RUN - which is honest, and which release_readiness treats as
    blocking.

    The best verdict reachable today is PROVISIONAL: G7 does not exist, and a store
    whose planes pass against an engine never shown capable of failing has not been
    checked (OPEN_DEBTS D11).
    """
    import datetime as _dt
    import resource
    import tempfile
    import time

    from sdip.equivalence import g4, g5, issue
    from sdip.equivalence.closure import roundtrip_closure
    from sdip.equivalence.determinism import g6
    from sdip.equivalence.nonvacuity import g3_control, g7
    from sdip.export import export as run_export
    from sdip.ingest import ingest as run_ingest
    from sdip.spec import g1_for_spec

    number: float | int = float(revision) if "." in revision else int(revision)
    started = time.monotonic()
    result = run_ingest(source, output, revision=number, template=template, overwrite=overwrite)
    spec = result.spec.segy_spec
    gate1 = g1_for_spec(result.spec)
    planes = _run_planes(source, output, spec, g1_passed=gate1.passed)
    portability = g4(output)

    with tempfile.TemporaryDirectory() as scratch:
        exported = Path(scratch) / "roundtrip.sgy"
        roundtrip = run_export(output, exported, spec, source=source)

        # G7 runs against the very store being certified, on COPIES of it - never
        # against a fixture from somewhere else. A non-vacuity result imported from
        # another store says nothing about this one.
        nonvacuity = g7(source, output, spec, workdir=Path(scratch) / "g7")
        g3_check = g3_control(exported)
        g7_status, g7_summary = nonvacuity.status, nonvacuity.summary()

        # Arrow 3: the exported SEG-Y validated as an artifact in its own right, not a
        # by-product. G3 proves it is byte-identical to the source; this proves it is a
        # well-formed SEG-Y that re-ingests to the same store (DECISIONS.md D-0031).
        closure = roundtrip_closure(exported, output, spec, workdir=Path(scratch) / "closure")
        closure_status, closure_summary = closure.status, closure.summary()

        # G6: two INDEPENDENT ingests of the same source, compared on chunk bytes and on
        # array values. Determinism cannot be shown by one run, so this is the only
        # place it can be established.
        determinism = g6(source, number, template=template, workdir=Path(scratch) / "g6")
        g6_status, g6_summary = determinism.status, determinism.summary()

        # G5 only when a ceiling was DECLARED. See the docstring: a default would be a
        # limit this tool invented rather than one the operator committed to (SP9).
        scale = None
        if rss_ceiling_gib is not None and wall_ceiling_s is not None:
            scale = g5(
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                wall_clock_s=time.monotonic() - started,
                trace_count=int(planes[4].evidence.get("n", 0)),
                planes_passed=all(p.passed for p in planes),
                declared_rss_ceiling_bytes=int(rss_ceiling_gib * 1024**3),
                declared_wall_ceiling_s=wall_ceiling_s,
                prereg_reference=prereg or "declared on the command line, not recorded",
            )
        g5_line = (
            f"[{scale.status}] G5        {scale.summary()}"
            if scale is not None
            else (
                "[ -- ] G5        NOT_RUN - no ceiling declared "
                "(--rss-ceiling-gib / --wall-ceiling-s)"
            )
        )

        issued_at = _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")
        certificate = issue(
            result,
            planes,
            roundtrip=roundtrip,
            portability=portability,
            nonvacuity=nonvacuity,
            closure=closure,
            determinism=determinism,
            scale=scale,
            issued_at=issued_at,
            issued_by=f"sdip {__version__}",
        )
        certificate.payload["nonvacuity"]["g3_control"] = g3_check

    certificates.mkdir(parents=True, exist_ok=True)
    stamp = issued_at.replace(":", "").replace("-", "")
    path = certificates / f"{result.source_sha256[:12]}-{stamp}.json"
    path.write_text(json.dumps(certificate.payload, indent=2, sort_keys=True))

    _print_planes(planes)
    click.echo(f"[{roundtrip.status}] G3        whole-file SHA-256")
    click.echo(f"[{portability.status}] G4        stock zarr+xarray without mdio")
    click.echo(f"[{g7_status}] G7        {g7_summary}")
    click.echo(g5_line)
    click.echo(f"[{g6_status}] G6        {g6_summary}")
    click.echo(f"[{closure_status}] closure   {closure_summary}")
    click.echo("")
    readiness = certificate.payload["release_readiness"]
    click.echo("")
    click.echo(f"verdict:     {certificate.verdict}")
    click.echo(
        f"release:     {'READY' if readiness['release_ready'] else 'NOT READY'}"
        + ("" if readiness["release_ready"] else f" - {len(readiness['blocking'])} blocking")
    )
    for item in readiness["blocking"][:6]:
        click.echo(f"               - {item}")
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
