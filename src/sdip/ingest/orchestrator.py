"""Thin orchestration over the MDIO converter. Specification §6.3, §11.1.

**Thin is a requirement, not a description.** SDIP does not reimplement conversion; it
selects a gap-free spec, runs G1 before any I/O, calls the pinned public API, and
records what happened. Anything more would be a transform, and SDIP is an identity map
(§1.3, **SP1**).

The `__main__` guard
--------------------
MDIO's header parser uses a **`spawn`** multiprocessing context. Any entry point that
can reach :func:`ingest` **must** sit behind ``if __name__ == "__main__":``. Without it
the child interpreter re-imports the calling module, re-executes the ingest, and the
pool dies with ``BrokenProcessPool``. Measured, not theoretical — specification
Appendix A.5.

:func:`ingest` cannot enforce that from the inside: by the time it runs, a module-level
call has already been re-executed in the child. What it can do is **detect the hazard
before doing any work** and refuse with an error that names the fix, which is what
:func:`assert_main_guarded` does.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdip.errors import PhaseNotAuthorisedError, SdipError, UntrustedInputError
from sdip.guard.env import check_barred_env_vars
from sdip.guard.warn import WarningLedger, recording_log_records, recording_warnings
from sdip.ingest.file_headers import (
    RawFileHeaders,
    TextualHeaderDecode,
    attach_raw_file_headers,
    classify_textual_header,
    file_headers_not_persisted,
    file_headers_persisted,
    read_raw_file_headers,
)
from sdip.ingest.header_plane import HeaderPlane, attach_header_plane
from sdip.ingest.preflight import SourceLayout, validate_segy_structure
from sdip.ingest.provenance_marker import attach_provenance_marker
from sdip.ingest.raw_samples import RawSampleView, attach_raw_sample_view
from sdip.provenance.hashing import sha256_file
from sdip.spec.gate import G1Result, g1_for_spec
from sdip.spec.generator import GapFreeSpec, build_gap_free_spec
from sdip.spec.overrides import SurveyOverride

MIN_SEGY_BYTES = 3600 + 240
"""Textual (3200) + binary (400) header, plus one trace header. Smaller cannot be valid."""


class SpawnGuardError(SdipError):
    """An ingest was reached from an unguarded module scope. Spec §11.1."""


def assert_main_guarded() -> None:
    """Refuse to ingest from a module scope that is not ``__main__``-guarded.

    Detects the specific hazard: the process was launched as a script, and the call is
    happening at import time of that script rather than inside its ``__main__`` block.

    A false negative is possible — this cannot see every caller — so it is a guard, not
    a proof. The CI ``spawn-guard`` job runs a real unguarded script and is the check
    that actually settles it.

    Raises:
        SpawnGuardError: If the hazard is detected.
    """
    if os.environ.get("SDIP_SPAWN_CHILD") == "1":
        msg = (
            "ingest re-entered inside a spawned child process. The entry point that "
            'started this run is missing `if __name__ == "__main__":`. MDIO\'s header '
            "parser uses a spawn context, so the child re-executes the module and the "
            "pool dies with BrokenProcessPool (spec 11.1, Appendix A.5)."
        )
        raise SpawnGuardError(msg)


OUTPUT_URI_SCHEME = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]+):/")
"""A URI scheme at the head of an output path, in either form it can arrive in.

Two forms, because the same mistake reaches this module two ways. A library caller
passes ``s3://bucket/store.mdio`` intact. ``click.Path(path_type=Path)`` has already run
it through ``pathlib``, which collapses the doubled slash, so the CLI delivers
``s3:/bucket/store.mdio``. Matching ``:/`` rather than ``://`` catches both.

**The scheme must be at least two characters.** A single letter before a colon is a
Windows drive, not a scheme, and refusing ``C:/surveys/x.mdio`` would be a bug of the
same family as the one this exists to fix.

**The slash is required.** ``my:dir/store.mdio`` is a legal POSIX path and is not a URI;
a rule that fired on a bare colon would refuse real directories.
"""

OBJECT_STORE_SCHEMES = ("s3", "gs", "gcs", "az", "abfs", "abfss", "adl", "wasb", "wasbs")
"""Named in the refusal message, not used to decide it.

**Every** scheme is refused, because the failure being prevented is "SDIP silently wrote
somewhere else", and an allow-list of known-bad schemes would let the next one through.
These are listed so the message tells an operator reaching for a bucket what they have
actually hit, rather than making them infer it.
"""


def validate_output_path(output: str | Path) -> None:
    """Refuse an output that names a URI scheme. Spec §11.4, ``OPEN_DEBTS.md`` D7.

    **This is a refusal, not object-store support.** It does not make ``s3://`` work; it
    makes the fact that it does not work audible.

    Measured, not theoretical. Given ``s3://sdip-p8/store.mdio``, probe **P8** recorded
    :func:`ingest` returning **normally** and ``sdip ingest`` exiting **0** with
    ``G1 PASS`` — having written a complete 20-file store into a local directory literally
    named ``s3:`` under the working directory, with **0 objects** in the bucket
    (``DECISIONS.md`` D-0058).

    ``Path("s3://bucket/key")`` collapses the doubled slash into the *relative* path
    ``s3:/bucket/key``, which then resolves against the working directory. No scheme is
    recognised and nothing raises, so **a green run and an empty bucket are
    indistinguishable to the operator.** A crash would have been kinder: §11.4 bars a
    crash, and it equally bars a write outside the output path, which is what this was.

    Called **before the source is read, before the spec is built, and before anything is
    allocated** — the §11.4 ordering. A check that runs after a store has been written is
    not a check, it is a postmortem.

    Args:
        output: The requested output path exactly as the caller gave it. Both ``str`` and
            ``Path`` are accepted because the two arrive differently; see
            :data:`OUTPUT_URI_SCHEME`.

    Raises:
        PhaseNotAuthorisedError: If the output names any URI scheme. Object-store output
            is unimplemented and unmeasured — debt **D7**, probe **P8** — so this is a
            capability that does not exist yet rather than a malformed argument.
    """
    match = OUTPUT_URI_SCHEME.match(str(output))
    if match is None:
        return
    scheme = match.group("scheme")
    known = ", ".join(f"{name}://" for name in OBJECT_STORE_SCHEMES)
    msg = (
        f"output path names the URI scheme {scheme!r} ({output}). SDIP writes to the "
        f"local filesystem only; object-store output is NOT implemented (OPEN_DEBTS D7, "
        f"probe P8) and no scheme is supported, including {known} and http(s)://. "
        "Refusing before any work is done. This refusal exists because the alternative "
        "was measured and was worse: SDIP used to accept such a path, exit 0, report "
        "G1 PASS, and write the store to a local directory named after the scheme while "
        "the bucket stayed empty (DECISIONS.md D-0058). Pass a local path instead."
    )
    raise PhaseNotAuthorisedError(msg)


def validate_source(path: Path) -> SourceLayout:
    """Validate a SEG-Y source before anything is allocated. Spec §11.4.

    Header-declared lengths and counts are attacker-supplied until reconciled with the
    file on disk, so the *file* is checked first and nothing is read into memory here.

    Three layers, cheapest first, each a precondition of the next:

    1. the path is a regular file at all;
    2. it is at least the 3600 bytes of file headers plus one trace header;
    3. its declared counts reconcile with its size
       (:func:`~sdip.ingest.preflight.validate_segy_structure`).

    Layer 3 arrived with debt **D8**. Before it, 18 of the 33 hostile corpus members
    reached upstream and came back with an exception SDIP does not define — a
    ``ZeroDivisionError`` among them — and every one of those reached the console as a
    traceback (``DECISIONS.md`` D-0057).

    Args:
        path: Source SEG-Y.

    Returns:
        The reconciled layout, whose ``size`` is the size on disk.

    Raises:
        UntrustedInputError: If the path is not a readable regular file of plausible
            size, or if a header-declared count is one the file cannot satisfy.
    """
    if not path.is_file():
        msg = f"source is not a regular file: {path}"
        raise UntrustedInputError(msg)
    size = path.stat().st_size
    if size < MIN_SEGY_BYTES:
        msg = (
            f"source is {size} bytes; a SEG-Y cannot be smaller than {MIN_SEGY_BYTES} "
            "(3200 textual + 400 binary + one 240-byte trace header)"
        )
        raise UntrustedInputError(msg)
    return validate_segy_structure(path, size)


@dataclass(slots=True)
class IngestResult:
    """Everything one ingestion produced, in certificate shape."""

    source_path: str
    source_sha256: str
    source_sha256_post_read: str
    source_bytes: int
    output_path: str
    spec: GapFreeSpec
    g1: G1Result
    template: str
    raw_headers: RawFileHeaders
    warnings: WarningLedger = field(default_factory=WarningLedger)
    raw_samples: RawSampleView | None = None
    """The parallel raw ``uint32`` view, or ``None`` when the source is not ``ibm32``
    and the source bits are therefore recoverable from the decode itself."""
    header_plane: HeaderPlane | None = None
    """The parallel ``uint8`` trace-header plane. Written for **every** store — probe P4
    measured three Zarr readers disagreeing about the structured array's extension dtype,
    and the portability problem is not conditional on anything about the source.
    ``None`` only for a result built without one, never for a completed ingest."""
    textual_decode: TextualHeaderDecode | None = None
    """Whether the source's textual header decoded, measured on the raw bytes (§4.2).

    Drives the certificate's ``detected_encoding.decode_status``. ``None`` only for a
    result built without one, never for a completed ingest."""
    file_header_persistence: str = "strict"
    """Which upstream file-header mode the converter actually ran under.

    ``"strict"`` (mode 1) on every decodable source. ``"off"`` (mode 0) only where the
    textual header did not decode, which is the sole path §4.2 leaves open: mode 1 would
    refuse the ingest and mode 2 would rewrite the header (``DECISIONS.md`` D-0055).
    A store ingested ``"off"`` carries no ``segy_file_header`` variable, so it has no
    parsed views and cannot be exported."""

    @property
    def read_path_intact(self) -> bool:
        """True when the source hashed identically before and after ingestion.

        A mismatch means the file changed underneath the run, which invalidates every
        comparison made against it (spec §11.3).
        """
        return self.source_sha256 == self.source_sha256_post_read

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping for the ingest block."""
        return (
            {
                "source_path": self.source_path,
                "source_sha256": self.source_sha256,
                "source_sha256_post_read": self.source_sha256_post_read,
                "source_bytes": self.source_bytes,
                "read_path_intact": self.read_path_intact,
                "output_path": self.output_path,
                "template": self.template,
                "raw_file_headers": self.raw_headers.to_json(),
                "textual_header_decode": (
                    self.textual_decode.to_json() if self.textual_decode is not None else None
                ),
                "file_header_persistence": self.file_header_persistence,
                "raw_sample_view": (
                    self.raw_samples.to_json() if self.raw_samples is not None else None
                ),
                "header_plane": (
                    self.header_plane.to_json() if self.header_plane is not None else None
                ),
                "warnings": self.warnings.to_json(),
            }
            | self.spec.to_json()
            | {"G1": self.g1.to_json()}
        )


def ingest(
    source: str | Path,
    output: str | Path,
    *,
    revision: float | int = 1,
    template: str = "PostStack3DTime",
    overwrite: bool = False,
    override: SurveyOverride | None = None,
) -> IngestResult:
    """Convert a SEG-Y file to an MDIO store against a gap-free spec.

    Order of operations is load-bearing:

    1. Refuse if the spawn hazard is detectable (§11.1).
    2. Refuse if a barred environment variable is set (§9.1) — a run started with
       ``MDIO_IGNORE_CHECKS`` set is not a run whose result means anything.
    3. Refuse an output path that names a URI scheme, **before ``pathlib`` touches it**
       (§11.4, D7). Object-store output is unimplemented, and the failure mode it
       replaces was silent: exit 0 and an empty bucket (``DECISIONS.md`` D-0058).
    4. Validate the source **before allocating** (§11.4).
    5. Hash the source.
    6. Build the gap-free spec and **run G1 before a single trace is read** (§7 G1).
    7. Capture the raw textual and binary headers directly from the source (§4.2, §4.3),
       and **measure whether the textual header decodes** before anything is converted.
    8. Convert, recording every observable warning, every filter installed, and every log
       record upstream emits at WARNING or above — a different channel, reported
       separately (**SP6**, D26). File-header persistence is STRICT (mode 1) for a
       decodable header and **off** (mode 0) for one that did not decode; see below.
    9. Attach SDIP's authoritative raw headers to the store.
    10. Store the undecoded ``uint32`` sample view in parallel when — and only when — the
       source's sample format is ``ibm32``, whose decode probe **P2** measured as not
       exactly invertible (``OPEN_DEBTS`` D1).
    11. Store the parallel ``uint8`` trace-header plane, **unconditionally** — probe
        **P4** measured three Zarr readers giving three different answers about the
        structured array's extension dtype (``DECISIONS.md`` D-0047).
    12. Hash the source again, to detect read-path corruption (§11.3).

    An undecodable textual header is **not** an ingestion failure (§4.2)
    -------------------------------------------------------------------
    §4.2: *"If bytes cannot be decoded, the raw 3200 bytes are preserved and the decode
    failure is recorded on the certificate. Decode failure is not an ingestion failure;
    silent substitution is."* Neither upstream mode delivers that, measured against the
    pinned ``multidimio`` 1.2.1 (``DECISIONS.md`` D-0055):

    * mode 1 (STRICT) raises ``ValueError`` out of ``segy_to_mdio`` and writes no store,
      so the ingest is refused — the half §4.2 explicitly rules out;
    * mode 2 (LENIENT) completes by replacing the offending characters with spaces, which
      is the silent substitution §4.2 bars outright (D-0020). Never used.

    Mode 0 is the third door: upstream persists no file-header variable and validates
    nothing, so the conversion completes and never touches the header bytes. SDIP already
    holds the authoritative 3200 bytes from step 6 and writes them to the store itself, so
    Plane 1 is checked against the source's own bytes either way. The failure is recorded
    on the certificate as ``decode_status: raw_preserved_decode_failed``.

    The mode is chosen from :func:`~sdip.ingest.file_headers.classify_textual_header`,
    which decodes the raw bytes with the **same** ``TextHeaderSpec`` this call hands to
    ``segy_to_mdio``. Deciding up front rather than catching upstream's exception costs
    no second geometry scan and couples to no exception type. Being SDIP's own predicate
    it can disagree with upstream's, and both directions are safe rather than silent:
    predicate stricter, and the ingest completes with the loss recorded on the
    certificate; predicate looser, and mode 1 raises exactly as it does today. It is not
    *assumed* to agree — ``tests/integration/test_undecodable_textheader.py`` measures the
    two verdicts against each other on a conforming and a non-conforming fixture.

    **What mode 0 costs, recorded and not hidden.** The store carries no
    ``segy_file_header`` variable, so upstream's parsed ``binaryHeader`` mapping is absent
    - Plane 2 reports ``parsed_mapping_present: false`` and §4.3's *parsed mapping* half is
    unmet - and ``mdio_to_segy`` refuses to export it, so **G3 is unreachable for such a
    store**. :func:`sdip.export.roundtrip.export` refuses cleanly and says why.

    Args:
        source: Input SEG-Y.
        output: Output MDIO store path.
        revision: SEG-Y revision for the base spec.
        template: Registered MDIO template name.
        overwrite: Overwrite an existing store.
        override: A validated survey override (§6.4), applied over the gap-free base.
            It renames and retypes bytes the base spec already covered — it supplies the
            names a template binds on, never new content. Load one with
            :func:`sdip.spec.overrides.load_override`.

    Returns:
        The ingest result, in certificate shape.

    Raises:
        SpecCompletenessError: If G1 fails. Nothing is read.
        SurveyOverrideError: If the override leaves the spec not gap-free. Nothing is
            read; step 5 happens before any trace I/O and an override cannot reach a
            byte it did not survive.
        UntrustedInputError: If the source fails pre-allocation validation.
        PhaseNotAuthorisedError: If the output path names a URI scheme. Object-store
            output is unimplemented (D7). Nothing is read and nothing is written.
        SpawnGuardError: If the spawn hazard is detected.
    """
    assert_main_guarded()

    barred = check_barred_env_vars()
    if barred:
        names = ", ".join(f.name for f in barred)
        msg = f"barred environment variable set: {names} (spec 9.1). Refusing to ingest."
        raise SdipError(msg)

    # Before `Path(output)` touches it, because `pathlib` is what silently turns
    # `s3://bucket/key` into a relative local path (D-0058).
    validate_output_path(output)

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    layout = validate_source(source_path)
    before = sha256_file(source_path)

    built = build_gap_free_spec(revision, override=override)
    gate = g1_for_spec(built)
    gate.raise_for_status()

    raw_headers = read_raw_file_headers(source_path)
    decode = classify_textual_header(raw_headers.textual, built.segy_spec.text_header)

    # §4.2: decode failure is not an ingestion failure. See the docstring for the three
    # upstream modes and why mode 0 is the only one that satisfies the clause.
    persistence = file_headers_persisted() if decode.decoded else file_headers_not_persisted()

    ledger = WarningLedger()
    with (
        recording_warnings(ledger, reemit=False),
        recording_log_records(ledger),
        persistence,
    ):
        from mdio import segy_to_mdio
        from mdio.builder.template_registry import get_template

        segy_to_mdio(
            segy_spec=built.segy_spec,
            mdio_template=get_template(template),
            input_path=source_path,
            output_path=output_path,
            overwrite=overwrite,
        )

    # SDIP's own authoritative copy. Upstream's parsed view is kept alongside it;
    # these bytes are the ones Planes 1 and 2 are checked against (§4.3).
    attach_raw_file_headers(output_path, raw_headers)

    # Probe P2 measured ibm32 -> float32 as NOT exactly invertible, with 1,939 of 4,103
    # words losing the value outright. For such a source the decoded array is not a
    # recoverable copy of the source bits, so the undecoded words are stored in parallel
    # (OPEN_DEBTS D1). Returns None for any other sample format, and writes nothing.
    raw_samples = attach_raw_sample_view(output_path, source_path, built.segy_spec)

    # Probe P4 measured TensorStore accepting the structured `headers` array's `struct`
    # data_type, zarr-java refusing it, and zarr-python accepting it with a warning -
    # three readers, three answers, one store (D-0047). `struct` has no Zarr v3
    # specification, so a reader that declines it is conformant. The uint8 plane makes
    # the header bytes readable by any v3 reader. Written for EVERY store: every store
    # has headers, and the portability problem is not conditional.
    header_plane = attach_header_plane(output_path, source_path, built.segy_spec)

    # LAST, and that ordering is the point. The marker declares which mitigations this
    # writer always attaches, so the Equivalence Engine can tell a partially written SDIP
    # store from a foreign MDIO store it is merely inspecting (D-0063 ruling 3). Written
    # after the mitigations it vouches for, so an ingest that dies midway leaves NO
    # marker rather than a marker promising arrays that were never written - the failure
    # mode probe P8 measured, inverted.
    attach_provenance_marker(output_path)

    after = sha256_file(source_path)
    return IngestResult(
        source_path=str(source_path),
        source_sha256=before,
        source_sha256_post_read=after,
        source_bytes=layout.size,
        output_path=str(output_path),
        spec=built,
        g1=gate,
        template=template,
        raw_headers=raw_headers,
        warnings=ledger,
        raw_samples=raw_samples,
        header_plane=header_plane,
        textual_decode=decode,
        file_header_persistence="strict" if decode.decoded else "off",
    )


if __name__ == "__main__":  # pragma: no cover - see spec 11.1
    sys.exit("sdip.ingest.orchestrator is a library; use `sdip ingest`.")
