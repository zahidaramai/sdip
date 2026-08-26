"""**G7 — the gate on the gates.** Specification §7 G7, **SP11**.

    A gate a corrupted store passes is not a gate.

These are **permanent fixtures**. They are not deleted when the bug they caught is
fixed: a failed configuration becomes the permanent negative control for its fix
(operating contract §5).

**What G7 asserts is stricter than "the corruption was detected".** Each control
declares the **exact set** of gates it must fail, and the observed set must *equal* it.
That single assertion catches both failure modes at once:

* a **narrow** checker that misses the corruption — the gate that is not a gate;
* an **over-broad** checker that fails on somebody else's corruption — which cannot
  localise a fault and gets silenced the first time it fires on something benign.

The second is not hypothetical. On its very first run, G7 found that truncating the
*textual* header also failed **G2b**, because Plane 1 and Plane 2 shared a reader that
validated both halves together. §7 G7's killer is *"one that fails the wrong gate"*, and
that is precisely what it was. Fixed by giving each plane its own reader —
`DECISIONS.md` D-0028.
"""

from __future__ import annotations

import pytest

from sdip.equivalence.nonvacuity import ALL_GATES, CONTROLS, g3_control, g7
from sdip.export import export
from sdip.ingest import ingest
from tests.fixtures.generators import make_poststack3d

pytestmark = [pytest.mark.negative, pytest.mark.integration]


@pytest.fixture(scope="module")
def audited(tmp_path_factory):
    """One ingest, one full G7 audit. The audit copies the store per control."""
    root = tmp_path_factory.mktemp("g7")
    source = make_poststack3d(root / "src.sgy")
    result = ingest(source.path, root / "out.mdio")
    audit = g7(source.path, root / "out.mdio", result.spec.segy_spec, workdir=root / "work")
    return source, root, result, audit


def test_the_baseline_is_clean(audited):
    """If the clean store already fails a gate, "the corrupted one failed" proves nothing."""
    *_, audit = audited
    assert audit.baseline_clean, audit.baseline_detail


def test_g7_passes(audited):
    """Every corruption fails exactly the gates it declares, and no others."""
    *_, audit = audited
    assert audit.passed, audit.summary()


@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.name)
def test_each_control_fails_exactly_its_declared_gates(audited, control):
    """The core G7 assertion, reported per control so a failure names itself.

    A control that is **not applicable** to this fixture is asserted to be so explicitly
    and by name, rather than skipped: `fabricate_in_padding` has no padding cell in a
    full grid, and `flip_raw_ibm32_word` has nothing to flip in a store from an exact
    sample format. Neither is a pass. Both are covered where they DO apply by
    `test_the_padding_control_fires_where_padding_exists_and_is_skipped_where_it_cannot`,
    which is what keeps this branch from becoming a way for a control to disappear.
    """
    *_, audit = audited
    outcome = next(o for o in audit.outcomes if o.corruption.name == control.name)
    if outcome.not_applicable is not None:
        assert control.name in {"fabricated_value_in_padding", "flipped_raw_ibm32_word"}, (
            f"{control.name} declared itself not applicable to the standard fixture; "
            "only the two conditional controls may, and each is covered elsewhere"
        )
        assert outcome.failed_gates == frozenset()
        return
    assert outcome.error is None, outcome.error
    assert outcome.missed == [], (
        f"{control.name} PASSED {outcome.missed} - a gate a corrupted store passes is not a gate"
    )
    assert outcome.unexpected == [], (
        f"{control.name} also failed {outcome.unexpected} - an over-broad checker "
        "cannot localise a fault"
    )


def test_the_minimum_control_set_from_the_specification_is_present():
    """§7 G7 names six controls by name. None may quietly go missing."""
    names = {c.name for c in CONTROLS}
    assert {
        "flipped_header_byte",
        "flipped_sample_bit",
        "dropped_trace",
        "transposed_traces",
        "inverted_live_mask",
        "truncated_textual_header",
    } <= names


def test_every_gate_has_at_least_one_control():
    """A gate with no control has never been shown capable of failing."""
    covered: set[str] = set()
    for control in CONTROLS:
        covered |= control.must_fail
    uncovered = set(ALL_GATES) - covered - {"G3"}
    assert uncovered == set(), f"no control targets {sorted(uncovered)}"


def test_g3_has_its_own_control(audited):
    """G3 compares two FILES, so its control corrupts an export, not a store."""
    source, root, result, _ = audited
    exported = root / "exported.sgy"
    export(root / "out.mdio", exported, result.spec.segy_spec, source=source.path)
    check = g3_control(exported)
    assert check["detected"], "a flipped export byte must change the hash"
    assert check["restored_cleanly"], "the control must leave the file as it found it"
    assert check["status"] == "PASS"


def test_multi_gate_controls_declare_every_gate_they_hit():
    """Two corruptions genuinely touch more than one plane, and say so.

    Declaring a single gate for either would assert something false, and would be
    "fixed" by weakening a checker - the opposite of what G7 is for.
    """
    by_name = {c.name: c for c in CONTROLS}
    assert by_name["transposed_traces"].must_fail == {"G2c", "G2d"}
    assert by_name["dropped_trace"].must_fail == {"G2c", "G2d", "G2e"}


def test_g7_fails_loudly_when_a_checker_goes_blind(audited, monkeypatch):
    """NEGATIVE CONTROL FOR G7 ITSELF. A vacuous gate must make G7 FAIL.

    G7 is a gate, so SP11 applies to it too: an audit that has never been shown to fail
    is not an audit. Here Plane 4 is blinded, and G7 must notice that the flipped-sample
    control no longer fails G2d.
    """
    from sdip.equivalence.planes import PlaneResult

    source, root, result, _ = audited

    def blind_plane_4(*_args: object, **_kwargs: object) -> PlaneResult:
        return PlaneResult(plane=4, gate="G2d", title="blinded", status="PASS")

    import sdip.equivalence.planes as planes_module

    monkeypatch.setattr(planes_module, "plane_4", blind_plane_4)

    audit = g7(source.path, root / "out.mdio", result.spec.segy_spec, workdir=root / "blind")
    assert not audit.passed, "G7 passed while Plane 4 was blind - G7 is itself vacuous"
    blinded = next(o for o in audit.outcomes if o.corruption.name == "flipped_sample_bit")
    assert "G2d" in blinded.missed


def test_the_padding_control_fires_where_padding_exists_and_is_skipped_where_it_cannot(
    tmp_path,
):
    """**SP12 / D29.** Both halves, because only the pair shows the control is real.

    A control that is "not applicable" everywhere is indistinguishable from one that
    passes, so this asserts it actually FIRES on a store that has padding — and is
    recorded as **not applicable, by name**, on a store whose grid is full.

    Padding is excluded from every plane comparison, correctly: it has nothing to compare
    against. That is precisely why a fabricated value there was invisible until this
    control existed — Planes 3 and 4 iterate the trace map, and a padding cell is not in
    it.
    """
    from sdip.equivalence.nonvacuity import g7
    from sdip.ingest import ingest
    from tests.fixtures.generators.irregular import make_ragged_lines

    # (a) a ragged grid HAS padding: the control fires, and on G2e alone.
    ragged = make_ragged_lines(tmp_path / "ragged.sgy")
    ragged_store = tmp_path / "ragged.mdio"
    result = ingest(ragged.path, ragged_store)
    fired = g7(ragged.path, ragged_store, result.spec.segy_spec, workdir=tmp_path / "g7a")
    assert fired.status == "PASS"
    outcome = next(o for o in fired.outcomes if o.corruption.name == "fabricated_value_in_padding")
    assert outcome.not_applicable is None, "a ragged grid has padding; it must fire"
    assert outcome.failed_gates == frozenset({"G2e"})

    # (b) a full grid has none: recorded as not applicable, NAMED, never silently passed.
    full = make_poststack3d(tmp_path / "full.sgy")
    full_store = tmp_path / "full.mdio"
    full_result = ingest(full.path, full_store)
    skipped = g7(full.path, full_store, full_result.spec.segy_spec, workdir=tmp_path / "g7b")
    assert skipped.status == "PASS"
    payload = skipped.to_json()
    names = [entry["name"] for entry in payload["controls_not_applicable"]]
    assert "fabricated_value_in_padding" in names
    assert payload["controls_applied"] == payload["control_count"] - len(names)
    # the reason is on the record, not inferred
    reason = next(
        e["reason"]
        for e in payload["controls_not_applicable"]
        if e["name"] == "fabricated_value_in_padding"
    )
    assert "grid is full" in reason
