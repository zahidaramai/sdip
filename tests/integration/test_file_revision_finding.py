"""D59: the revision a file declares about itself is compared with the revision it was read as.

SEG-Y binary header bytes 3501-3502 are mandatory in every revision: rev 1 writes 0x0100, rev 2.x
writes the major and minor numbers as two unsigned bytes, and **zero means the 1975 standard**.
SDIP read the revision from the operator's declaration only. Ruling (DECISIONS.md D-0088): a
disagreement is a **named finding that does not block release**, because conformant rev 1 files
commonly carry 0 there.
"""

from __future__ import annotations

from pathlib import Path

from sdip.equivalence.planes import plane_2
from sdip.ingest import ingest, ingest_declared
from sdip.spec import load_override, parse_override
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators.irregular import make_byte_swapped
from tests.fixtures.generators.revisions import make_revision_poststack3d

REPO = Path(__file__).resolve().parents[2]
REV1 = SurveyDeclaration(revision=1, template="PostStack3DTime")
REV0 = SurveyDeclaration(
    revision=0,
    template="PostStack3DTime",
    override=load_override(REPO / "overrides" / "segy-rev0-poststack3d.toml"),
)


def _findings(result) -> dict[str, dict]:
    return {f["code"]: f for f in result.evidence.get("findings", [])}


def test_a_file_that_agrees_with_its_declaration_has_no_finding(tmp_path):
    source = make_revision_poststack3d(tmp_path / "r1.sgy", revision=1).path
    store = tmp_path / "r1.mdio"
    ingest(source, store)
    result = plane_2(source, store, declaration=REV1)
    assert result.status == "PASS"
    assert "file_revision_differs" not in _findings(result)


def test_a_zero_revision_field_read_as_revision_1_is_named_and_does_not_block(tmp_path):
    good = make_revision_poststack3d(tmp_path / "r1.sgy", revision=1).path
    data = bytearray(good.read_bytes())
    data[3500:3502] = b"\x00\x00"
    source = tmp_path / "zero_field.sgy"
    source.write_bytes(bytes(data))
    store = tmp_path / "zero_field.mdio"
    ingest(source, store)

    result = plane_2(source, store, declaration=REV1)
    assert result.status == "PASS", "the bytes were preserved; the finding is not a failure"
    finding = _findings(result)["file_revision_differs"]
    assert finding["blocks_release"] is False
    assert finding["file_revision"] == "0.0"
    assert finding["declared_revision"] == "1"
    assert "1975" in finding["message"]


def test_a_revision_0_file_read_as_revision_0_has_no_finding(tmp_path):
    source = make_revision_poststack3d(tmp_path / "r0.sgy", revision=0).path
    store = tmp_path / "r0.mdio"
    ingest_declared(source, store, REV0)
    assert "file_revision_differs" not in _findings(plane_2(source, store, declaration=REV0))


def _little_endian(name: str) -> SurveyDeclaration:
    override = parse_override(
        {
            "name": name,
            "version": "1",
            "evidence": "Synthetic byte-swapped fixture for the D59 byte-order tests; not real.",
            "endianness": "little",
        }
    )
    return SurveyDeclaration(revision=1, template="PostStack3DTime", override=override)


def test_a_correct_little_endian_file_has_no_finding(tmp_path):
    """The pass half the check shipped without (OPEN_DEBTS D62's class).

    Below revision 2 the field is a 16-bit word, so a little-endian file stores rev 1's
    0x0100 as ``00 01``. The check was handed the declared revision and never the declared
    byte order, read the two bytes in file order, and reported every correct little-endian
    file as recording revision 0.1 - measured through ``sdip verify``.
    """
    declaration = _little_endian("revision-word-little")
    source = make_byte_swapped(tmp_path / "little.sgy", endianness="little").path
    assert source.read_bytes()[3500:3502] == b"\x00\x01", "the fixture is the measured case"
    store = tmp_path / "little.mdio"
    ingest_declared(source, store, declaration)

    result = plane_2(source, store, declaration=declaration)
    assert result.status == "PASS"
    assert _findings(result) == {}


def test_a_zero_revision_field_in_a_little_endian_file_is_still_named(tmp_path):
    """The failing half, in the same byte order: the fix did not silence the check."""
    declaration = _little_endian("revision-word-little-zero")
    good = make_byte_swapped(tmp_path / "little.sgy", endianness="little").path
    data = bytearray(good.read_bytes())
    data[3500:3502] = b"\x00\x00"
    source = tmp_path / "little_zero.sgy"
    source.write_bytes(bytes(data))
    store = tmp_path / "little_zero.mdio"
    ingest_declared(source, store, declaration)

    result = plane_2(source, store, declaration=declaration)
    assert result.status == "PASS"
    finding = _findings(result)["file_revision_differs"]
    assert finding["file_revision"] == "0.0"
    assert finding["blocks_release"] is False


def test_without_a_declared_revision_nothing_is_claimed(tmp_path):
    """G7 re-runs planes without a declaration; absence of the comparison is not a finding."""
    source = make_revision_poststack3d(tmp_path / "r1.sgy", revision=1).path
    store = tmp_path / "r1.mdio"
    ingest(source, store)
    assert _findings(plane_2(source, store)) == {}
