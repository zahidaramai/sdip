"""Correct data PASSES across the value space each value-dependent check computes with.

**OPEN_DEBTS D52, DECISIONS.md D-0088 — the specificity half of G7.** Every control proves a
check FAILS a corruption. These prove the check does not fail CORRECT inputs anywhere in the space
it depends on — the half whose absence let two derived checks ship failing correct stores.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from sdip.equivalence.planes import _file_revision_finding
from sdip.ingest.preflight import _supported_format_codes, validate_segy_structure
from sdip.spec import parse_override
from sdip.spec.declaration import SurveyDeclaration


def _file(
    path: Path, *, code: int, bytes_per_sample: int, samples: int = 8, traces: int = 3
) -> Path:
    binary = bytearray(400)
    struct.pack_into(">h", binary, 16, 4000)
    struct.pack_into(">h", binary, 20, samples)
    struct.pack_into(">h", binary, 24, code)
    trace = bytearray(240 + samples * bytes_per_sample)
    struct.pack_into(">h", trace, 70, 1)  # coordinate scalar 1
    path.write_bytes(bytes(3200) + bytes(binary) + bytes(trace) * traces)
    return path


@pytest.mark.parametrize(("code", "width"), sorted(_supported_format_codes().items()))
def test_preflight_accepts_a_well_formed_file_in_every_supported_format(tmp_path, code, width):
    path = _file(tmp_path / f"f{code}.sgy", code=code, bytes_per_sample=width)
    layout = validate_segy_structure(path, path.stat().st_size)
    assert (layout.sample_format_code, layout.bytes_per_sample, layout.trace_count) == (
        code,
        width,
        3,
    )


ENCODINGS = {"0": (0, 0), "1": (1, 0), "2": (2, 0), "2.1": (2, 1)}


def _declared(revision: str, byte_order: str | None) -> SurveyDeclaration:
    number = float(revision) if "." in revision else int(revision)
    override = None
    if byte_order is not None:
        override = parse_override(
            {
                "name": f"sweep-{byte_order}",
                "version": "1",
                "evidence": "Synthetic header bytes for the revision-word sweep; not real data.",
                "endianness": byte_order,
            }
        )
    return SurveyDeclaration(revision=number, template="PostStack3DTime", override=override)


@pytest.mark.parametrize("byte_order", [None, "big", "little"])
@pytest.mark.parametrize("declared", ["0", "1", "2", "2.1"])
@pytest.mark.parametrize("file_revision", list(ENCODINGS))
def test_the_revision_finding_fires_exactly_on_disagreement(declared, file_revision, byte_order):
    """Revision by revision **by byte order** - the axis this sweep shipped without.

    Below revision 2 the field is one 16-bit word, which a little-endian writer stores
    swapped; from revision 2 it is two separate bytes, which nobody swaps. Swept big-endian
    only, the check passed here and reported every correct little-endian revision 1 file as
    recording revision 0.1 (OPEN_DEBTS D62's class: the byte order never reached it).
    """
    major, minor = ENCODINGS[file_revision]
    binary = bytearray(400)
    swapped = byte_order == "little" and float(file_revision) < 2
    binary[300], binary[301] = (minor, major) if swapped else (major, minor)
    finding = _file_revision_finding(bytes(binary), _declared(declared, byte_order))
    assert (finding is None) is (file_revision == declared), (file_revision, declared, byte_order)


def test_every_registered_template_is_recorded_under_the_name_an_operator_types():
    """Every template is recorded under the name an operator passes as ``--template``.

    The binding's independent cross-check depends on it. Pinned for all, not measured once.
    """
    from mdio.builder.template_registry import TemplateRegistry, get_template

    names = TemplateRegistry().list_all_templates()
    assert names
    assert all(get_template(name).name == name for name in names)
