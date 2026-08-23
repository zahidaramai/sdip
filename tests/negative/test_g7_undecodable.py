"""**G7 on a store whose textual header did not decode.** §7 G7, **SP11**, debt D17.

    A gate a corrupted store passes is not a gate.

``DECISIONS.md`` D-0055 gave the engine a **second store shape**: a source whose textual
header cannot be decoded is ingested with upstream's file-header persistence off, so the
store carries no ``segy_file_header`` variable and SDIP's authoritative raw headers live
on the **root group** instead.

A second shape is a second place for the gates to be vacuous, and the reason this file
exists rather than a note saying the existing audit covers it. Three separate pieces of
code resolve where the raw header bytes live — the writer, Plane 1's reader, and G7's
textual controls — and if the controls resolved it differently from the reader they
would raise instead of corrupting. G7 would then report a *control error* on a store it
had never actually corrupted: a green-looking failure over an audit that never ran.
That is the same class of defect G7 caught on its first run (D-0028), reached by a
different route.

**§5's `truncated textual header` control, on this shape.** The two textual controls
must fail **G2a and only G2a**, exactly as they do on a conforming store. If they also
failed G2b here, the two planes would be sharing a reader again on the new shape only —
which is precisely the "fails the wrong gate" killer §7 G7 names.

Measured on N=1 non-conforming fixture, 12 traces, pinned ``multidimio`` 1.2.1.
"""

from __future__ import annotations

import base64

import pytest
import zarr

from sdip.equivalence.nonvacuity import CONTROLS, g7
from sdip.equivalence.planes import plane_1, plane_2
from sdip.errors import UntrustedInputError
from sdip.ingest import ingest
from sdip.ingest.file_headers import ATTR_RAW_TEXT, UPSTREAM_FILE_HEADER_VARIABLE
from tests.fixtures.generators.undecodable import make_undecodable_textual_header

pytestmark = [pytest.mark.negative, pytest.mark.integration]

TEXTUAL_CONTROLS = ("flipped_textual_byte", "truncated_textual_header")
"""The two controls that corrupt the textual header. Both must fail G2a and only G2a."""


@pytest.fixture(scope="module")
def audited(tmp_path_factory):
    """One ingest of a non-conforming source, one full G7 audit of the result."""
    root = tmp_path_factory.mktemp("g7_undecodable")
    source = make_undecodable_textual_header(root / "undecodable.sgy")
    result = ingest(source.path, root / "undecodable.mdio")
    audit = g7(source.path, root / "undecodable.mdio", result.spec.segy_spec, workdir=root / "work")
    return source, root, result, audit


def test_the_store_really_is_the_second_shape(audited):
    """Guard against a vacuous file. If the store has the variable, nothing new is tested."""
    _source, root, _result, _audit = audited
    group = zarr.open_group(str(root / "undecodable.mdio"), mode="r")
    assert UPSTREAM_FILE_HEADER_VARIABLE not in group, (
        "this fixture no longer produces the fallback store shape, so every assertion "
        "below is being made about the shape the existing G7 suite already covers"
    )
    assert ATTR_RAW_TEXT in dict(group.attrs), "the raw bytes must be on the root group"


def test_the_baseline_is_clean(audited):
    """If the clean store already fails a gate, "the corrupted one failed" proves nothing."""
    *_, audit = audited
    assert audit.baseline_clean, audit.baseline_detail


def test_g7_passes_on_the_fallback_store(audited):
    """Every corruption fails exactly the gates it declares, on this shape too."""
    *_, audit = audited
    assert audit.passed, audit.summary()


def test_the_store_under_audit_was_not_modified(audited):
    """The raw headers now live in the root ``zarr.json``, which every copy shares.

    ``_materialise`` real-copies every ``zarr.json`` for exactly this reason. If it ever
    hard-linked them, the textual controls would corrupt the store being certified.
    """
    *_, audit = audited
    assert audit.original_store_intact, audit.original_store_detail


@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.name)
def test_each_control_fails_exactly_its_declared_gates(audited, control):
    """The core G7 assertion, reported per control so a failure names itself.

    A control not applicable to this fixture is asserted as such by name rather than
    skipped — see the sibling in ``test_g7_controls.py``. Only the two conditional
    controls may declare it, and each is covered where it does apply.
    """
    *_, audit = audited
    outcome = next(o for o in audit.outcomes if o.corruption.name == control.name)
    if outcome.not_applicable is not None:
        assert control.name in {"fabricated_value_in_padding", "flipped_raw_ibm32_word"}, (
            f"{control.name} declared itself not applicable; only the two conditional "
            "controls may, and each is covered where it does apply"
        )
        assert outcome.failed_gates == frozenset()
        return
    assert outcome.error is None, (
        f"{control.name} could not be applied to the fallback store: {outcome.error}. "
        "A control that errors has audited nothing."
    )
    assert outcome.missed == [], (
        f"{control.name} PASSED {outcome.missed} - a gate a corrupted store passes is not a gate"
    )
    assert outcome.unexpected == [], (
        f"{control.name} also failed {outcome.unexpected} - an over-broad checker "
        "cannot localise a fault"
    )


@pytest.mark.parametrize("name", TEXTUAL_CONTROLS)
def test_a_corrupted_textual_header_fails_plane_1_and_only_plane_1(audited, name):
    """§5's named control, restated for the shape D-0055 introduced.

    Asserted on the observed set rather than on ``passed`` so the failure message says
    *which* other gate fired — the diagnosis, not just the verdict.
    """
    *_, audit = audited
    outcome = next(o for o in audit.outcomes if o.corruption.name == name)
    assert outcome.failed_gates == {"G2a"}, (
        f"{name} failed {sorted(outcome.failed_gates)} on the fallback store; on this "
        "shape as on any other it must fail G2a alone. Anything else means Planes 1 "
        "and 2 are sharing a reader again (D-0028)."
    )


def test_plane_1_fails_when_the_root_group_bytes_are_corrupted(audited, tmp_path):
    """The direct, non-G7 statement of the same thing. One flipped byte, one FAIL.

    G7 runs the checkers through its own machinery; this runs Plane 1 against a
    corrupted store directly, so a defect in that machinery cannot make the plane look
    healthy.
    """
    import shutil

    source, root, result, _audit = audited
    copy = tmp_path / "corrupt.mdio"
    shutil.copytree(root / "undecodable.mdio", copy)

    group = zarr.open_group(str(copy), mode="r+")
    raw = bytearray(base64.b64decode(str(dict(group.attrs)[ATTR_RAW_TEXT])))
    raw[1600] ^= 0x01
    group.attrs.update({ATTR_RAW_TEXT: base64.b64encode(bytes(raw)).decode("ascii")})

    failed = plane_1(source.path, copy)
    assert not failed.passed
    assert failed.evidence["first_difference"] == {
        "kind": "byte",
        "offset": 1600,
        "expected": source.textual_header[1600],
        "observed": source.textual_header[1600] ^ 0x01,
    }
    assert plane_2(source.path, copy).passed, (
        "corrupting the textual header must not fail Plane 2, on any store shape"
    )
    assert plane_1(source.path, result.output_path).passed, "the original must be untouched"


def test_plane_1_refuses_a_store_with_the_raw_bytes_stripped(audited, tmp_path):
    """The vacuity control for the fallback shape itself.

    A store with no raw textual header is not a store Plane 1 may pass. On the fallback
    shape the attribute sits on the root group with MDIO's own metadata, so deleting it
    leaves a store that still opens and still looks complete — the failure mode this
    asserts against.
    """
    import shutil

    source, root, _result, _audit = audited
    copy = tmp_path / "stripped.mdio"
    shutil.copytree(root / "undecodable.mdio", copy)

    group = zarr.open_group(str(copy), mode="r+")
    attrs = dict(group.attrs)
    del attrs[ATTR_RAW_TEXT]
    group.attrs.clear()
    group.attrs.update(attrs)

    with pytest.raises(UntrustedInputError):
        plane_1(source.path, copy)
