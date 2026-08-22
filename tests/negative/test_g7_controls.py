"""**G7 — the gate on the gates.** Specification §7 G7, **SP11**.

    A gate a corrupted store passes is not a gate.

These are **permanent fixtures**. They are not deleted when the bug they caught is
fixed: a failed configuration becomes the permanent negative control for its fix
(`CLAUDE.md` §5).

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
    """The core G7 assertion, reported per control so a failure names itself."""
    *_, audit = audited
    outcome = next(o for o in audit.outcomes if o.corruption.name == control.name)
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
