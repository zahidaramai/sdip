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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdip.errors import SdipError, UntrustedInputError
from sdip.guard.env import check_barred_env_vars
from sdip.guard.warn import WarningLedger, recording_log_records, recording_warnings
from sdip.ingest.file_headers import (
    RawFileHeaders,
    attach_raw_file_headers,
    file_headers_persisted,
    read_raw_file_headers,
)
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


def validate_source(path: Path) -> int:
    """Validate a SEG-Y source before anything is allocated. Spec §11.4.

    Header-declared lengths and counts are attacker-supplied until reconciled with the
    file on disk, so the *file* is checked first and nothing is read into memory here.

    Args:
        path: Source SEG-Y.

    Returns:
        Size in bytes.

    Raises:
        UntrustedInputError: If the path is not a readable regular file of plausible size.
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
    return size


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
                "raw_sample_view": (
                    self.raw_samples.to_json() if self.raw_samples is not None else None
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
    3. Validate the source **before allocating** (§11.4).
    4. Hash the source.
    5. Build the gap-free spec and **run G1 before a single trace is read** (§7 G1).
    6. Capture the raw textual and binary headers directly from the source (§4.2, §4.3).
    7. Convert with file-header persistence enabled in STRICT mode, recording every
       observable warning, every filter installed, and every log record upstream emits
       at WARNING or above — a different channel, reported separately (**SP6**, D26).
    8. Attach SDIP's authoritative raw headers to the store.
    9. Store the undecoded ``uint32`` sample view in parallel when — and only when — the
       source's sample format is ``ibm32``, whose decode probe **P2** measured as not
       exactly invertible (``OPEN_DEBTS`` D1).
    10. Hash the source again, to detect read-path corruption (§11.3).

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
        SpawnGuardError: If the spawn hazard is detected.
    """
    assert_main_guarded()

    barred = check_barred_env_vars()
    if barred:
        names = ", ".join(f.name for f in barred)
        msg = f"barred environment variable set: {names} (spec 9.1). Refusing to ingest."
        raise SdipError(msg)

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    size = validate_source(source_path)
    before = sha256_file(source_path)

    built = build_gap_free_spec(revision, override=override)
    gate = g1_for_spec(built)
    gate.raise_for_status()

    raw_headers = read_raw_file_headers(source_path)

    ledger = WarningLedger()
    with (
        recording_warnings(ledger, reemit=False),
        recording_log_records(ledger),
        file_headers_persisted(),
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

    after = sha256_file(source_path)
    return IngestResult(
        source_path=str(source_path),
        source_sha256=before,
        source_sha256_post_read=after,
        source_bytes=size,
        output_path=str(output_path),
        spec=built,
        g1=gate,
        template=template,
        raw_headers=raw_headers,
        warnings=ledger,
        raw_samples=raw_samples,
    )


if __name__ == "__main__":  # pragma: no cover - see spec 11.1
    sys.exit("sdip.ingest.orchestrator is a library; use `sdip ingest`.")
