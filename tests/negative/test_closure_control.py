"""**Round-trip closure's negative control.** `OPEN_DEBTS.md` D19, `DECISIONS.md` D-0067.

    A check a corrupted artifact passes is not a check.

These are **permanent fixtures** (operating contract §5). They are not deleted now that the hole
they document is filled: a failed configuration becomes the permanent negative control
for its fix.

**What was measured, and why an existing function was not a closed debt.**
`roundtrip_closure` re-ingested the export, ran G1, ran all five planes and compared
every array — and still returned **PASS** on an export whose 400-byte binary file header
differed from the original store's. Two independent offsets, 3300 and 3450, both inside
the rev 1 unassigned region so that nothing parsed moved.

The mechanism is structural, not a slip. The five planes run *export against the store
built from that export*, so they are a **self-consistency** leg and cannot disagree with
the export about anything. The one leg that compared the export to the original walked
`group.arrays()` — and SDIP's authoritative raw file headers are base64 **attributes**
(D-0021), because §4.3's raw bytes are unreachable through MDIO without a barred
variable. Planes 1 and 2 — G2a and G2b, two of the five — were therefore checking
nothing at all in the `ROUNDTRIP-SCOPED` regime arrow ③ exists for.

`test_closure_passed_the_corruption_before_the_file_header_leg` is the reproducer, and it
asserts the **old** behaviour from a store with the leg's inputs removed. If someone
deletes the leg, that test starts failing along with the rest.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sdip.equivalence.closure import FILE_HEADER_ATTRS, roundtrip_closure
from sdip.equivalence.nonvacuity import (
    CLOSURE_CONTROL_NAME,
    CLOSURE_CONTROL_OFFSET,
    closure_control,
)
from sdip.export import export
from sdip.ingest import ingest
from sdip.ingest.file_headers import ATTR_RAW_BINARY, ATTR_RAW_TEXT
from sdip.provenance.hashing import sha256_file
from tests.fixtures.generators import make_poststack3d

pytestmark = [pytest.mark.negative, pytest.mark.integration]


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    """One ingest and one export, shared. Each control run re-ingests the export once."""
    root = tmp_path_factory.mktemp("closure_control")
    source = make_poststack3d(root / "src.sgy")
    result = ingest(source.path, root / "out.mdio")
    store = root / "out.mdio"
    path = root / "roundtrip.sgy"
    export(store, path, result.spec.segy_spec, source=source.path)
    return source, store, path, result.spec.segy_spec, root


@pytest.fixture(scope="module")
def baseline(exported):
    """Closure on the **clean** export. If this fails, nothing below proves anything."""
    _source, store, path, spec, root = exported
    return roundtrip_closure(path, store, spec, workdir=root / "baseline")


@pytest.fixture(scope="module")
def control(exported, baseline):
    """The control itself, run once."""
    _source, store, path, spec, root = exported
    return closure_control(path, store, spec, baseline=baseline, workdir=root / "control")


def test_the_baseline_is_clean(baseline):
    """A clean export must close. Otherwise "the corrupted one failed" proves nothing."""
    assert baseline.passed, baseline.summary()


def test_the_baseline_compared_both_file_headers(baseline):
    """Emptiness is not success: a leg that compared nothing is not a leg (**SP11**)."""
    assert len(baseline.file_headers) == len(FILE_HEADER_ATTRS)
    assert {h.attribute for h in baseline.file_headers} == {ATTR_RAW_TEXT, ATTR_RAW_BINARY}
    assert all(h.equal for h in baseline.file_headers)
    assert all(h.in_original and h.in_closure for h in baseline.file_headers)


def test_the_control_passes(control):
    """The whole assertion, in one line, reporting its own reasons on failure."""
    assert control["status"] == "PASS", "; ".join(control["failure_reasons"])


def test_the_corruption_is_detected(control):
    """A check a corrupted artifact passes is not a check."""
    assert control["detected"], control["corrupted_closure_summary"]


def test_the_file_header_leg_is_the_only_leg_that_fires(control):
    """§7 G7's *"and ONLY that gate"*, transposed from gates to closure's legs.

    This is the assertion that keeps the control from going vacuous. A control asserting
    only *"closure FAILed"* would keep passing if the file-header leg were deleted and
    some unrelated leg happened to catch the flip — which is the vacuity §7 G7 exists to
    prevent, one level up.
    """
    assert control["observed_legs"] == ["file_headers"], control["corrupted_closure_summary"]
    assert control["differing_file_headers"] == [ATTR_RAW_BINARY]
    assert control["leg_exact"]


def test_the_textual_header_is_reported_unchanged(control):
    """A leg that reported both headers moving could not localise a fault — D-0028.

    One byte of the *binary* header was flipped. A leg that also reported the textual
    header as differing would be §7 G7's other killer: a check that fires on somebody
    else's corruption gets silenced the first time it fires on something benign.
    """
    assert ATTR_RAW_TEXT not in control["differing_file_headers"]


def test_the_control_leaves_the_export_and_the_store_alone(control, exported):
    """The corruption goes to a copy under ``workdir``. Measured, not assumed."""
    assert control["export_unmodified"]
    assert control["store_unmodified"]
    _source, _store, path, _spec, _root = exported
    assert path.exists()


def test_the_declared_offset_is_a_binary_header_byte():
    """The offset is inside the binary file header, which is where the leg lives.

    3200 textual + 400 binary, at fixed offsets, in every revision — the one structural
    fact `read_raw_file_headers` relies on and the reason it needs no spec.
    """
    assert 3200 <= CLOSURE_CONTROL_OFFSET < 3600
    assert CLOSURE_CONTROL_NAME == "closure_binary_header_byte"


def test_a_dirty_baseline_makes_the_control_fail(exported):
    """A control interpreted against a failing baseline is not evidence.

    `g7` refuses to interpret its controls when the clean store already fails a gate. The
    same discipline, asserted rather than assumed: a baseline built from an unrelated
    export makes the control FAIL even though the corruption is still detected.
    """
    _source, store, path, spec, root = exported
    unrelated = root / "unrelated.sgy"
    payload = bytearray(path.read_bytes())
    payload[3600] ^= 0x01  # a trace-header byte: fails closure on the array leg
    unrelated.write_bytes(bytes(payload))
    dirty = roundtrip_closure(unrelated, store, spec, workdir=root / "dirty_baseline")
    assert not dirty.passed

    check = closure_control(path, store, spec, baseline=dirty, workdir=root / "control_dirty")
    assert check["status"] == "FAIL"
    assert not check["baseline_clean"]
    assert any("baseline is not clean" in reason for reason in check["failure_reasons"])
    # The corruption is still detected — only the baseline is what invalidates the run.
    assert check["detected"]


def test_closure_passed_the_corruption_before_the_file_header_leg(exported):
    """**The reproducer for D-0067**, kept as the permanent record of the hole.

    Reconstructs the pre-fix verdict on the same corrupted export by evaluating every
    leg *except* the file-header one, and asserts it was a PASS. That is the measurement
    D19 was open on: a `ROUNDTRIP-SCOPED` export could carry a mangled 400-byte binary
    header — §4.3's authoritative bytes — under a closure PASS, and no gate said so.

    It fails loudly if the leg is deleted, because the assertions below then describe the
    live verdict rather than a historical one.
    """
    _source, store, path, spec, root = exported
    corrupted = root / "reproducer.sgy"
    payload = bytearray(path.read_bytes())
    payload[CLOSURE_CONTROL_OFFSET] ^= 0x01
    corrupted.write_bytes(bytes(payload))

    result = roundtrip_closure(corrupted, store, spec, workdir=root / "reproducer_work")

    # Every pre-D-0067 leg, unchanged.
    assert result.error is None, "the corrupted export still re-ingests"
    assert result.g1 is not None and result.g1.passed, "G1 still passes on the rebuilt spec"
    assert result.failed_planes == [], "all five planes still hold — they are self-consistent"
    assert result.differing_arrays == [], "every array still matches"
    assert result.only_in_original == [] and result.only_in_closure == []

    # ...and the store really does disagree with the export about the header bytes.
    assert result.differing_headers == [ATTR_RAW_BINARY]
    assert not result.passed, "the file-header leg is what turns this into a FAIL"


def test_the_leg_reports_the_byte_that_moved(exported):
    """A comparison that says only *that* it failed is much less useful than *where*."""
    _source, store, path, spec, root = exported
    corrupted = root / "located.sgy"
    payload = bytearray(path.read_bytes())
    payload[CLOSURE_CONTROL_OFFSET] ^= 0x01
    corrupted.write_bytes(bytes(payload))

    result = roundtrip_closure(corrupted, store, spec, workdir=root / "located_work")
    binary = next(h for h in result.file_headers if h.attribute == ATTR_RAW_BINARY)
    expected_byte = CLOSURE_CONTROL_OFFSET - 3200 + 1
    assert f"byte {expected_byte}" in binary.detail, binary.detail
    assert "1 of 400 bytes differ" in binary.detail
    assert binary.original_bytes == 400
    assert binary.original_sha256 != binary.closure_sha256


def test_a_store_with_no_raw_headers_fails_rather_than_raising(exported, tmp_path):
    """A header SDIP cannot read is not a header that matched.

    "Could not read it" must never resolve to "skipped, therefore fine". The leg is
    asserted to degrade to a clean FAIL naming the absence, not to an exception out of a
    certificate run.
    """
    import zarr

    _source, store, path, spec, _root = exported
    stripped = tmp_path / "stripped.mdio"
    shutil.copytree(store, stripped)
    group = zarr.open_group(str(stripped), mode="r+")
    node = group["segy_file_header"]
    for attribute in (ATTR_RAW_TEXT, ATTR_RAW_BINARY):
        del node.attrs[attribute]

    result = roundtrip_closure(path, stripped, spec, workdir=tmp_path / "work")
    assert not result.passed
    assert result.differing_headers == [ATTR_RAW_TEXT, ATTR_RAW_BINARY]
    for header in result.file_headers:
        assert not header.in_original
        assert header.in_closure
        assert "the original store" not in header.detail


def test_the_control_does_not_modify_the_export_on_disk(exported, tmp_path):
    """Independent of the control's own self-report: hash the file either side."""
    _source, store, path, spec, _root = exported
    before = sha256_file(path)
    base = roundtrip_closure(path, store, spec, workdir=tmp_path / "base")
    closure_control(path, store, spec, baseline=base, workdir=tmp_path / "ctl")
    assert sha256_file(path) == before


def test_an_offset_past_the_end_is_refused(exported, tmp_path):
    """Never index into a buffer on an offset nobody checked (§3.6)."""
    _source, store, path, spec, _root = exported
    size = Path(path).stat().st_size
    base = roundtrip_closure(path, store, spec, workdir=tmp_path / "base")
    with pytest.raises(IndexError):
        closure_control(path, store, spec, baseline=base, workdir=tmp_path / "ctl", offset=size + 1)
