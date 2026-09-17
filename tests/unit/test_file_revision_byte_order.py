"""The file's own revision field is read in the declared byte order. OPEN_DEBTS D62's class.

D59 compares binary-header bytes 3501-3502 with the declared revision and records a
disagreement as a non-blocking finding. It was handed the declared **revision** and never
the declared **byte order**, and read the two bytes in file order. Below revision 2 the
field is one 16-bit word, so a little-endian file stores rev 1's ``0x0100`` as ``00 01`` -
and every correct little-endian revision 1 file was reported as recording revision 0.1.
Measured through ``sdip verify`` on the committed byte-swapped fixture. The declaration had
reached one input of the check and not the other, which is D62's shape.

``tests/unit/test_value_space_sweeps.py`` sweeps revision by revision by byte order, both
halves. Here: the measured case pinned to the committed fixture, ``infer``, and a word
written in one byte order and declared in the other - which is a disagreement, and must
still be named. Nothing here ingests.
"""

from __future__ import annotations

import pytest

from sdip.equivalence.planes import BIN_REVISION_OFFSET, _file_revision_finding, file_revision
from sdip.ingest.preflight import read_binary_header
from sdip.spec import parse_override
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators.irregular import make_byte_swapped


def _declared(revision: float | int, endianness: str | None) -> SurveyDeclaration:
    override = None
    if endianness is not None:
        override = parse_override(
            {
                "name": f"revision-word-{endianness}",
                "version": "1",
                "evidence": "Synthetic header bytes for the revision-word sweep; not real data.",
                "endianness": endianness,
            }
        )
    return SurveyDeclaration(revision=revision, template="PostStack3DTime", override=override)


def _header(word: bytes) -> bytes:
    binary = bytearray(400)
    binary[BIN_REVISION_OFFSET : BIN_REVISION_OFFSET + 2] = word
    return bytes(binary)


DISAGREEING = [
    # revision, declared byte order, bytes on disk, what the file then says about itself
    (1, "big", b"\x00\x01", "0.1"),  # a little-endian word under a big-endian declaration
    (1, None, b"\x00\x01", "0.1"),  # ... or under none, which inherits big-endian
    (1, "little", b"\x01\x00", "0.1"),  # a big-endian word under a little-endian one
    (2, "little", b"\x00\x02", "0.2"),  # from rev 2 the bytes are fields: never swapped back
]


@pytest.mark.parametrize(("revision", "endianness", "word", "recorded"), DISAGREEING)
def test_a_disagreeing_revision_word_is_named_and_does_not_block(
    revision, endianness, word, recorded
):
    finding = _file_revision_finding(_header(word), _declared(revision, endianness))
    assert finding is not None
    assert finding["code"] == "file_revision_differs"
    assert finding["file_revision"] == recorded
    assert finding["blocks_release"] is False


@pytest.mark.parametrize("written", ["big", "little"])
def test_an_inferred_byte_order_reads_the_word_as_the_preflight_would(tmp_path, written):
    """``infer`` is resolved from the header itself, by the function the preflight uses."""
    binary = read_binary_header(make_byte_swapped(tmp_path / "f.sgy", endianness=written).path)
    assert file_revision(binary, _declared(1, "infer")) == (1, 0)
    assert _file_revision_finding(binary, _declared(1, "infer")) is None


def test_the_committed_little_endian_fixture_is_the_measured_case(tmp_path):
    """Pin the reproducer to the fixture, so the sweep is not about invented bytes."""
    binary = read_binary_header(make_byte_swapped(tmp_path / "f.sgy", endianness="little").path)
    assert binary[BIN_REVISION_OFFSET : BIN_REVISION_OFFSET + 2] == b"\x00\x01"
    assert file_revision(binary, _declared(1, "little")) == (1, 0)
    # Read in file order - what shipped - the same bytes are "revision 0.1".
    assert file_revision(binary, _declared(1, None)) == (0, 1)
