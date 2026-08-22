"""Survey spec overrides. Specification §6.4.

    A registry of named, versioned overrides mapping a survey identifier to field
    renames and retypes over the gap-free base. Overrides are **declarative data**,
    committed and reviewable — never code branches. Each carries a provenance note
    stating the evidence for the remapping. **An override with no cited evidence is
    rejected at review.** Overrides change labels and numeric interpretation, never
    byte content — re-verified by re-running **G2c**.

What an override is for
-----------------------
An override does not add information to a file. It **names bytes the base spec already
covered** and says how to read them. Three independent probes stopped at the same
missing sentence:

- **P6** — SEG-Y rev 0 standardises no field above byte 180, so a gap-free rev 0 spec
  covers 181-240 with ``uint8`` fillers (correct under **SP5**) and ``PostStack3DTime``
  finds no ``cdp_x``/``cdp_y``/``inline``/``crossline`` to index on. The bytes are in the
  file at the positions rev 1 later standardised; only the labels are absent.
- **P7** — every prestack template binds names the rev 1 standard does not use. For
  ``offset`` and ``cdp`` the bytes exist under other names: byte 37 is
  ``source_to_receiver_distance``, byte 21 is ``ensemble_num``.
- **P5** — a little-endian file cannot be declared, because the spec inherits
  ``endianness = big`` from the revision standard and nothing could change it.

Why TOML and not JSON
---------------------
``tomllib`` is standard library from 3.11, so the choice adds no dependency either way.
TOML wins on the thing §6.4 actually cares about: **the evidence note is the point of
the file, and a reviewer reads it in a diff.** TOML has multi-line strings and comments;
JSON has neither, so an evidence paragraph becomes one unreadable line or an array of
string fragments, and the reasoning a reviewer is supposed to weigh becomes the hardest
part of the file to read. An override is reviewed by a person before it is loaded by a
program, and the format should serve that order.

What is refused, and why it is a refusal rather than a deferral
--------------------------------------------------------------
An override may declare a field ``format``, which makes it the one place a caller could
introduce an ``ibm32`` header field — `DECISIONS.md` D-0003 measured **zero** in every
standard trace header the pinned ``segy`` exposes. **Probe P2 has failed** (D-0034):
2,447 of 4,103 words fail bit-identity and 1,939 lose the value outright. **SP1** permits
exactly one transform and requires it exactly invertible, so an override declaring
``ibm32`` is refused at load — not deferred, not warned about. See
:mod:`sdip.spec.transforms` for what P2 measured.

Byte content is never changed
-----------------------------
Applying an override calls ``HeaderSpec.customize``, which replaces the fields whose byte
ranges the new declarations intersect. The declared extent must therefore cover exactly
what it displaces, or bytes fall out of coverage — which is why **G1 is re-run after
every override** and a narrower redeclaration is rejected there rather than papered over
with fresh fillers. The stronger statement is empirical, not structural: the 240 raw
bytes per trace are compared against the source by **G2c** on every ingest, so an
override that did change byte content fails Plane 3 whatever this module believes.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from segy.schema import ScalarType
from segy.schema.base import Endianness
from segy.schema.header import HeaderField

from sdip._pins import SEGY_TRACE_HEADER_BYTES
from sdip.errors import SdipError
from sdip.spec.coverage import format_itemsize
from sdip.spec.gate import g1
from sdip.spec.transforms import IBM32_NAMES

EVIDENCE_MIN_CHARS = 20
"""Shortest evidence note that is not a placeholder.

§6.4 rejects an unevidenced override at review, and the published certificate schema
already encodes ``minLength: 20`` on ``spec_override.evidence``. A bound is crude, but
``evidence = "legacy survey"`` is exactly the entry a reviewer would send back, and a
mechanism that only rejects the empty string rejects nothing anyone would actually write.
"""

ENDIANNESS_INFER = "infer"
"""Hand the byte-order decision to ``segy``, which reads it from the binary header."""

ENDIANNESS_VALUES: tuple[str, ...] = ("big", "little", ENDIANNESS_INFER)
"""Accepted values of the optional ``endianness`` key."""

_TOP_LEVEL_KEYS = frozenset({"name", "version", "evidence", "endianness", "field"})
_FIELD_KEYS = frozenset({"name", "byte", "format"})
_SCALAR_TYPES: frozenset[str] = frozenset(member.value for member in ScalarType)


class SurveyOverrideError(SdipError):
    """An override is malformed, unevidenced, or declares a refused format. Spec §6.4."""


@dataclass(frozen=True, slots=True)
class OverrideField:
    """One declaration: a name, a start byte, and a numeric format."""

    name: str
    byte: int
    format: str

    @property
    def size(self) -> int:
        """Width in bytes of the declared format."""
        return format_itemsize(self.format)

    @property
    def last_byte(self) -> int:
        """Final byte this declaration occupies, inclusive."""
        return self.byte + self.size - 1

    def to_header_field(self) -> HeaderField:
        """The upstream field object ``HeaderSpec.customize`` takes."""
        return HeaderField(name=self.name, byte=self.byte, format=ScalarType(self.format))

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {"name": self.name, "byte": self.byte, "format": self.format, "size": self.size}


@dataclass(frozen=True, slots=True)
class SurveyOverride:
    """A named, versioned set of declarations over a gap-free base spec.

    ``evidence`` is not documentation. §6.4 makes it the condition of acceptance, so it
    is validated on load rather than left to a reviewer's attention: an override that
    cannot say why a byte means what it claims has not established that it does.
    """

    name: str
    version: str
    evidence: str
    fields: tuple[OverrideField, ...] = ()
    endianness: str | None = None
    path: str | None = None

    @property
    def identifier(self) -> str:
        """``name@version``. Recorded on the certificate and in ``spec_id``."""
        return f"{self.name}@{self.version}"

    def header_fields(self) -> list[HeaderField]:
        """Every declaration as an upstream ``HeaderField``, in byte order."""
        return [f.to_header_field() for f in sorted(self.fields, key=lambda f: f.byte)]

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped ``spec_override`` block (§4.7, §6.4).

        Carries the evidence verbatim. A certificate that recorded only the override's
        name would leave a reader unable to judge the remapping without the file, which
        defeats the point of requiring the note at all.
        """
        return {
            "name": self.name,
            "version": self.version,
            "evidence": self.evidence,
            "fields": [f.to_json() for f in sorted(self.fields, key=lambda f: f.byte)],
            "endianness": self.endianness,
            "source_path": self.path,
        }


def _require_str(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{where}: key {key!r} is required and must be a non-empty string"
        raise SurveyOverrideError(msg)
    return value.strip()


def _parse_field(entry: Any, index: int, where: str) -> OverrideField:
    if not isinstance(entry, dict):
        msg = f"{where}: [[field]] entry {index} is not a table"
        raise SurveyOverrideError(msg)
    unknown = sorted(set(entry) - _FIELD_KEYS)
    if unknown:
        msg = (
            f"{where}: [[field]] entry {index} has unknown key(s) {', '.join(unknown)}; "
            f"a field declares exactly {', '.join(sorted(_FIELD_KEYS))}"
        )
        raise SurveyOverrideError(msg)

    name = _require_str(entry, "name", f"{where} [[field]] {index}")
    if any(character.isspace() for character in name):
        msg = f"{where}: field name {name!r} contains whitespace"
        raise SurveyOverrideError(msg)

    byte = entry.get("byte")
    if not isinstance(byte, int) or isinstance(byte, bool):
        msg = f"{where}: field {name!r} needs an integer 'byte'"
        raise SurveyOverrideError(msg)

    fmt = _require_str(entry, "format", f"{where} [[field]] {index}")
    if fmt.lower() in IBM32_NAMES:
        msg = (
            f"{where}: field {name!r} declares format {fmt!r}, which is REFUSED. Probe "
            "P2 measured ibm32 -> float32 as not exactly invertible - 2,447 of 4,103 "
            "words fail bit-identity and 1,939 lose the value, not merely its spelling "
            "(DECISIONS.md D-0034). The falsifier FIRED; this is a refusal on a failed "
            "probe, not a deferral pending one. SP1 permits only an exactly invertible "
            "declared transform, so an override may not introduce ibm32. Where the "
            "numeric format of a byte range is unknown, uint8 is the declaration that "
            "claims nothing about it (SP5)."
        )
        raise SurveyOverrideError(msg)
    if fmt not in _SCALAR_TYPES:
        msg = (
            f"{where}: field {name!r} declares format {fmt!r}, which the pinned segy "
            f"does not define; accepted: {', '.join(sorted(_SCALAR_TYPES))}"
        )
        raise SurveyOverrideError(msg)

    field = OverrideField(name=name, byte=byte, format=fmt)
    if field.byte < 1 or field.last_byte > SEGY_TRACE_HEADER_BYTES:
        msg = (
            f"{where}: field {name!r} occupies bytes {field.byte}-{field.last_byte}, "
            f"outside the trace header's 1-{SEGY_TRACE_HEADER_BYTES}"
        )
        raise SurveyOverrideError(msg)
    return field


def _check_internally_consistent(fields: tuple[OverrideField, ...], where: str) -> None:
    """Reject an override that contradicts itself before it reaches ``customize``.

    Upstream validates non-overlap too, but it raises from inside the merge with a
    message about header fields rather than about this file, and by then the base spec
    has already been mutated.
    """
    seen: dict[str, OverrideField] = {}
    for field in fields:
        if field.name in seen:
            msg = f"{where}: field {field.name!r} is declared twice"
            raise SurveyOverrideError(msg)
        seen[field.name] = field

    claimed: dict[int, str] = {}
    for field in sorted(fields, key=lambda f: f.byte):
        for position in range(field.byte, field.last_byte + 1):
            other = claimed.get(position)
            if other is not None:
                msg = (
                    f"{where}: fields {other!r} and {field.name!r} both claim byte "
                    f"{position}; declarations within one override must not overlap"
                )
                raise SurveyOverrideError(msg)
            claimed[position] = field.name


def parse_override(data: dict[str, Any], *, source: str | None = None) -> SurveyOverride:
    """Validate a decoded override mapping. Spec §6.4.

    Args:
        data: The decoded TOML document.
        source: Path the document came from, for error messages and the certificate.

    Returns:
        The validated override.

    Raises:
        SurveyOverrideError: On any missing, unknown, malformed, or refused entry.
    """
    where = f"survey override {source or '<inline>'}"

    unknown = sorted(set(data) - _TOP_LEVEL_KEYS)
    if unknown:
        msg = (
            f"{where}: unknown key(s) {', '.join(unknown)}; an override declares "
            f"{', '.join(sorted(_TOP_LEVEL_KEYS))} and nothing else"
        )
        raise SurveyOverrideError(msg)

    name = _require_str(data, "name", where)
    version = _require_str(data, "version", where)

    evidence = data.get("evidence")
    if not isinstance(evidence, str) or len(evidence.strip()) < EVIDENCE_MIN_CHARS:
        msg = (
            f"{where}: 'evidence' must be at least {EVIDENCE_MIN_CHARS} characters "
            "stating why these bytes carry these meanings - an observer report, a "
            "contractor specification, or the file's own textual header. Spec 6.4: an "
            "override with no cited evidence is rejected at review, so it is rejected "
            "at load."
        )
        raise SurveyOverrideError(msg)

    endianness = data.get("endianness")
    if endianness is not None and endianness not in ENDIANNESS_VALUES:
        msg = (
            f"{where}: 'endianness' is {endianness!r}; accepted values are "
            f"{', '.join(repr(v) for v in ENDIANNESS_VALUES)}. {ENDIANNESS_INFER!r} "
            "leaves the byte order for segy to read from the binary header."
        )
        raise SurveyOverrideError(msg)

    raw_fields = data.get("field", [])
    if not isinstance(raw_fields, list):
        msg = f"{where}: 'field' must be an array of tables ([[field]])"
        raise SurveyOverrideError(msg)
    fields = tuple(_parse_field(entry, i, where) for i, entry in enumerate(raw_fields))
    _check_internally_consistent(fields, where)

    if not fields and endianness is None:
        msg = (
            f"{where}: declares neither a [[field]] nor an endianness, so it changes "
            "nothing. An override that alters no interpretation is not an override."
        )
        raise SurveyOverrideError(msg)

    return SurveyOverride(
        name=name,
        version=version,
        evidence=evidence.strip(),
        fields=fields,
        endianness=endianness,
        path=source,
    )


def load_override(path: str | Path) -> SurveyOverride:
    """Load and validate a committed override file.

    Args:
        path: Path to a TOML override, conventionally under ``overrides/``.

    Returns:
        The validated override.

    Raises:
        SurveyOverrideError: If the file is unreadable, is not valid TOML, or fails
            validation.
    """
    resolved = Path(path)
    try:
        with resolved.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        msg = f"survey override {resolved}: cannot be read ({exc})"
        raise SurveyOverrideError(msg) from exc
    except tomllib.TOMLDecodeError as exc:
        msg = f"survey override {resolved}: not valid TOML ({exc})"
        raise SurveyOverrideError(msg) from exc
    return parse_override(data, source=str(resolved))


def apply_override(segy_spec: Any, override: SurveyOverride) -> None:
    """Apply an override to a SegySpec in place, then re-assert G1. Spec §6.4.

    Takes the **raw** ``SegySpec`` rather than a
    :class:`~sdip.spec.generator.GapFreeSpec` deliberately. A ``GapFreeSpec`` caches its
    coverage, filler names and field count; mutating the spec underneath it would leave
    those cached numbers describing a spec that no longer exists, and a ``field_count``
    that lies is worse than one that is absent. The supported entry point is
    :func:`sdip.spec.generator.build_gap_free_spec` with ``override=``, which recomputes
    them. This function is the layer below that.

    G1 is re-run here rather than left to the caller because the failure mode is quiet:
    ``HeaderSpec.customize`` removes every existing field whose byte range the new
    declarations intersect, so a declaration *narrower* than what it displaces uncovers
    the difference. Nothing raises; the spec is simply no longer gap-free, and bytes that
    were addressable stop being so.

    Args:
        segy_spec: The gap-free ``SegySpec`` to customise.
        override: The validated override.

    Raises:
        SurveyOverrideError: If the spec is not gap-free after the override is applied.
    """
    # Byte order first, fields second. Assigning ``endianness`` on the SegySpec reaches
    # the trace-header sub-spec through two pydantic model validators, and that is the
    # step with the wider blast radius; declaring the fields afterwards means a future
    # upstream that rebuilt the sub-model on assignment would fail loudly here rather
    # than silently discarding the declarations.
    if override.endianness is not None:
        segy_spec.endianness = (
            None if override.endianness == ENDIANNESS_INFER else Endianness(override.endianness)
        )
    header = segy_spec.trace.header
    if override.fields:
        header.customize(override.header_fields())

    result = g1(header.fields, dtype=header.dtype)
    if not result.passed:
        msg = (
            f"survey override {override.identifier} broke gap-freeness: "
            f"{result.summary()}. An override renames and retypes bytes the base spec "
            "already covered, so bytes 1-240 must still be covered exactly once after "
            "it is applied. Customising removes every existing field the declarations "
            "intersect: a declaration narrower than what it displaces leaves the "
            "difference uncovered (spec 6.4, G1)."
        )
        raise SurveyOverrideError(msg)
