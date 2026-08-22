"""Gap-free trace-header specification generator. Specification §5.1.

Construction, exactly as §5.1 states it:

1. Load the SEG-Y revision base spec.
2. Compute byte coverage of its declared fields.
3. Compute the uncovered byte set.
4. Emit one ``uint8`` filler per uncovered byte, named ``pad_<byte>`` (**SP5**).
5. Merge fillers into the base spec.
6. **Assert before use** — that is :func:`sdip.spec.gate.g1`, run separately so the
   assertion can also judge a spec this generator did not produce.

**One filler per byte, never a wider filler over a run.** Bytes 233-240 could be one
``uint64``, which is fewer fields and would look tidier. It would also be wrong: a
multi-byte integer carries byte-order semantics, so reading it commits to an endianness
for bytes whose meaning is undeclared. ``uint8`` is the only width that carries no
byte-order, sign, or numeric-format interpretation at all (**SP5**). The cost of being
right is 60 extra fields on the worst revision, which is nothing - see spec 5.2.

The base spec is deep-copied before customisation. ``get_segy_standard`` returns a
fresh object per call today, but relying on that would make a future upstream change to
caching silently corrupt the shared standard for every other caller in the process.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from segy.schema import ScalarType
from segy.schema.header import HeaderField
from segy.standards import get_segy_standard

from sdip._pins import SEGY_TRACE_HEADER_BYTES
from sdip.provenance.hashing import sha256_bytes
from sdip.spec.coverage import Coverage, compute_coverage

FILLER_PREFIX = "pad_"
"""Filler naming, per §5.1 step 4. ``pad_233`` is a byte, not a field with meaning."""

SUPPORTED_REVISIONS: tuple[float | int, ...] = (0, 1, 2, 2.1)
"""Revisions the pinned `segy` exposes a standard for. Probe P6 covers them end to end."""


@dataclass(slots=True)
class GapFreeSpec:
    """A trace-header specification covering bytes 1..240 with no gaps or overlaps."""

    revision: float | int
    segy_spec: Any
    fillers: tuple[str, ...]
    base_coverage: Coverage
    coverage: Coverage

    @property
    def field_count(self) -> int:
        """Fields after gap-free customisation."""
        return self.coverage.field_count

    @property
    def base_field_count(self) -> int:
        """Fields the revision standard declared before fillers were merged."""
        return self.base_coverage.field_count

    @property
    def itemsize(self) -> int:
        """Itemsize of the resulting structured dtype."""
        return int(self.segy_spec.trace.header.dtype.itemsize)

    @property
    def spec_id(self) -> str:
        """Stable identifier: revision plus filler count."""
        return f"segy-rev{self.revision}-gapfree-{len(self.fillers)}f"

    def field_manifest(self) -> tuple[tuple[str, int, int], ...]:
        """``(name, start_byte, size)`` for every field, in byte order.

        Byte order, not declaration order: the manifest is what gets hashed, and two
        specs that declare the same fields in a different order are the same spec.
        """
        return tuple(
            (e.name, e.start, e.size)
            for e in sorted(self.coverage.extents, key=lambda e: (e.start, e.name))
        )

    def sha256(self) -> str:
        """Hash of the field manifest. Recorded on every certificate as ``spec_sha256``.

        Covers names, byte positions, and widths — everything that determines how bytes
        are addressed. Two runs producing the same digest addressed the header
        identically, which is what G6 determinism needs from this layer.
        """
        payload = "\n".join(f"{n}\t{s}\t{z}" for n, s, z in self.field_manifest())
        return sha256_bytes(payload.encode("utf-8"))

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping for the ``spec_*`` block (§4.7)."""
        return {
            "spec_id": self.spec_id,
            "segy_revision": str(self.revision),
            "spec_field_count": self.field_count,
            "spec_base_field_count": self.base_field_count,
            "spec_filler_count": len(self.fillers),
            "spec_itemsize": self.itemsize,
            "spec_gap_free": self.coverage.gap_free,
            "spec_sha256": self.sha256(),
            "fillers": list(self.fillers),
            "coverage": self.coverage.to_json(),
        }


def filler_fields(uncovered: frozenset[int]) -> list[HeaderField]:
    """One ``uint8`` filler per uncovered byte, in ascending byte order (**SP5**)."""
    return [
        HeaderField(name=f"{FILLER_PREFIX}{byte}", byte=byte, format=ScalarType.UINT8)
        for byte in sorted(uncovered)
    ]


def build_gap_free_spec(revision: float | int = 1) -> GapFreeSpec:
    """Build a gap-free trace-header spec for a SEG-Y revision. Spec §5.1.

    Does **not** assert G1 — :func:`sdip.spec.gate.g1` does, deliberately separately, so
    that the assertion is not written by the thing it judges.

    Args:
        revision: SEG-Y revision. `0`, `1`, `2`, or `2.1`.

    Returns:
        The spec, its filler names, and coverage before and after customisation.

    Raises:
        ValueError: If the revision has no standard in the pinned ``segy``.
    """
    try:
        base = get_segy_standard(revision)
    except Exception as exc:
        msg = (
            f"no SEG-Y standard for revision {revision!r} in the pinned segy; "
            f"supported: {', '.join(str(r) for r in SUPPORTED_REVISIONS)}"
        )
        raise ValueError(msg) from exc

    spec = base.model_copy(deep=True)
    header = spec.trace.header

    base_coverage = compute_coverage(header.fields, itemsize=header.dtype.itemsize)
    fillers = filler_fields(base_coverage.uncovered)
    if fillers:
        header.customize(fillers)

    coverage = compute_coverage(spec.trace.header.fields, itemsize=spec.trace.header.dtype.itemsize)
    return GapFreeSpec(
        revision=revision,
        segy_spec=spec,
        fillers=tuple(f.name for f in fillers),
        base_coverage=base_coverage,
        coverage=coverage,
    )


def expected_filler_count(revision: float | int) -> int:
    """Bytes the revision standard leaves uncovered. Measured in DECISIONS.md D-0003."""
    return SEGY_TRACE_HEADER_BYTES - len(
        compute_coverage(get_segy_standard(revision).trace.header.fields).covered
    )
