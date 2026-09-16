"""The release criterion, and what it refuses. `DECISIONS.md` D-0031, D-0063, D-0072."""

from __future__ import annotations

from typing import Any

from sdip.equivalence.certificate import GATES, PLANE_KEYS, release_readiness


def _green() -> dict[str, Any]:
    """A payload that is release-ready in every respect. The baseline for one-at-a-time."""
    return {
        "gates": dict.fromkeys(GATES, "PASS"),
        "planes": {key: {"status": "PASS"} for key in PLANE_KEYS},
        "roundtrip_closure": {"status": "PASS"},
        "nonvacuity": {
            "g3_control": {"status": "PASS"},
            "closure_control": {"status": "PASS"},
        },
        "lossy_codec_present": False,
        "transform_scope_blocks_equivalence": False,
        "git": {"dirty": False},
        "declaration": {"status": "BOUND", "sha256": "0" * 64, "summary": "revision 1"},
    }


def test_the_baseline_is_actually_ready_or_every_other_test_here_is_vacuous():
    """Non-vacuity for this whole module.

    Every test below removes exactly one thing from a payload and asserts it blocks. If
    the baseline did not pass, they would all "pass" against a function that refuses
    everything, and the module would assert nothing at all.
    """
    verdict = release_readiness(_green())
    assert verdict["release_ready"] is True, verdict["blocking"]
    assert verdict["blocking"] == []


def test_a_failing_g3_control_blocks_release():
    """**D42.** A control that came back FAIL means its check cannot fail — SP11 vacuity.

    `g3_control` corrupts an exported file and requires G3 to catch it. When it reports
    `FAIL`, G3 has been shown **incapable of failing**, and a `G3: PASS` on the same
    certificate is then worth nothing. `release_readiness` read `gates` and never this.
    """
    payload = _green()
    payload["nonvacuity"]["g3_control"] = {"status": "FAIL"}
    verdict = release_readiness(payload)
    assert verdict["release_ready"] is False
    assert any("g3_control is FAIL" in reason for reason in verdict["blocking"])
    assert any("vacuous" in reason for reason in verdict["blocking"])
    # G3 itself still says PASS - which is the point: the gate and its audit disagree.
    assert payload["gates"]["G3"] == "PASS"


def test_a_failing_closure_control_blocks_release():
    """Same shape as the hole D19 closed, one level up (D-0067's final section)."""
    payload = _green()
    payload["nonvacuity"]["closure_control"] = {"status": "FAIL"}
    verdict = release_readiness(payload)
    assert verdict["release_ready"] is False
    assert any("closure_control is FAIL" in reason for reason in verdict["blocking"])


def test_an_absent_control_blocks_rather_than_being_treated_as_passing():
    """`NOT_RUN` is not a pass — the lesson three separate tests had to relearn."""
    payload = _green()
    del payload["nonvacuity"]["closure_control"]
    verdict = release_readiness(payload)
    assert verdict["release_ready"] is False
    assert any("closure_control NOT_RUN" in reason for reason in verdict["blocking"])

    missing_block = _green()
    del missing_block["nonvacuity"]
    blocked = release_readiness(missing_block)
    assert blocked["release_ready"] is False
    assert len([r for r in blocked["blocking"] if "control" in r]) == 2


def test_g4_g5_g6_are_not_required_to_have_controls():
    """Scope, asserted so the rule is not read as wider than it is.

    §7 G7's declared remit is G2a-G2e and G3. G4, G5 and G6 have no negative controls,
    and that is by specification rather than oversight — so a payload carrying none of
    them for those gates is still ready. This function blocks on controls that EXIST and
    RAN; it does not invent a requirement the specification never made.
    """
    verdict = release_readiness(_green())
    assert verdict["release_ready"] is True
    assert not any(g in " ".join(verdict["blocking"]) for g in ("G4 control", "G5 control"))


def test_a_certificate_that_does_not_say_which_reading_it_covers_is_not_release_ready():
    """**D-0087.** A certificate that does not say which reading it covers is not ready.

    Without a declaration block it does not say which reading of the source it names, and
    D47 measured what that costs: the same byte-correct store was FAIL under one reading
    and a traceback under another.
    """
    payload = _green()
    del payload["declaration"]
    verdict = release_readiness(payload)
    assert verdict["release_ready"] is False
    assert any("declaration" in item for item in verdict["blocking"])


def test_an_unbound_declaration_blocks_release():
    """UNBOUND and FOREIGN block release.

    Such a store is still verifiable, and the output says so - but a release claim cannot
    rest on a reading the store could not be checked against.
    """
    for status in ("UNBOUND", "FOREIGN"):
        payload = _green()
        payload["declaration"]["status"] = status
        verdict = release_readiness(payload)
        assert verdict["release_ready"] is False, status
        assert any(status in item for item in verdict["blocking"]), status


def test_a_blocking_plane_finding_blocks_release_without_failing_the_plane():
    """**D-0087.** A blocking finding stops release while the plane still passes.

    A nonzero recording delay: the store is what the writer wrote, so Plane 4 passes - but
    industry readers start the axis at the delay and the store does not, so a release claim
    cannot rest on it.
    """
    payload = _green()
    payload["planes"]["plane_4"]["evidence"] = {
        "findings": [
            {"code": "nonzero_recording_delay", "blocks_release": True, "message": "delay 100 ms"}
        ]
    }
    verdict = release_readiness(payload)
    assert payload["planes"]["plane_4"]["status"] == "PASS"
    assert verdict["release_ready"] is False
    assert any("nonzero_recording_delay" in item for item in verdict["blocking"])


def test_a_non_blocking_finding_does_not_block_release():
    payload = _green()
    payload["planes"]["plane_4"]["evidence"] = {
        "findings": [
            {"code": "trace_interval_unspecified", "blocks_release": False, "message": "zero"}
        ]
    }
    assert release_readiness(payload)["release_ready"] is True
