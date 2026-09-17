"""Round-trip closure under every reading a store can be written under. OPEN_DEBTS D62.

**What was measured.** ``sdip certify`` 1.2.0 ran the round-trip closure - and its
negative control - without the survey declaration. ``roundtrip_closure`` took a revision
and a template that defaulted to 1 and ``PostStack3DTime``, took no override, and
``certify`` passed none of them. The export of a correct store was therefore re-ingested
under a different reading from the one that wrote the store, and closure FAILed:

- revision 1, ``PostStack3DDepth``: the closure store named its axis ``time``, the
  original ``depth``;
- revision 0 with its override: the ``headers`` array differed and closure's Plane 3
  failed, the closure store having been read under a revision 1 spec;
- the closure control then FAILed on that dirty baseline, and release readiness blocked on
  both, while the verdict read EQUIVALENT and G3 PASS.

Found by a consumer re-certifying real revision 0 depth surveys; reproduced here on
synthetic files. Every closure test before this one used the defaults, so the defaults
could not be told apart from the declaration.

**Both halves (operating contract §5).** For each declaration: a correct export closes, and
the closure control - one flipped binary-header byte - is caught by the file-header leg
and by nothing else. Then the two reproducers. Closure handed the old defaults is
**refused**, with both readings named, instead of returning a FAIL about a reading nobody
performed (D-0087) - the wrong call can no longer produce a verdict at all. And the
re-ingest that refusal stands in front of is measured: the same correct export read under
the old defaults does not build the store it came from, so the declaration is shown to be
load-bearing in each case rather than assumed to be.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from sdip.equivalence.closure import _compare_stores, roundtrip_closure
from sdip.equivalence.nonvacuity import closure_control
from sdip.errors import DeclarationMismatchError, SdipError
from sdip.export import export
from sdip.ingest import ingest_declared
from sdip.spec import load_override, parse_override
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators.irregular import make_byte_swapped
from tests.fixtures.generators.revisions import make_revision_poststack3d

pytestmark = [pytest.mark.negative, pytest.mark.integration]

REPO = Path(__file__).resolve().parents[2]
REV0_OVERRIDE = load_override(REPO / "overrides" / "segy-rev0-poststack3d.toml")
LITTLE_ENDIAN = parse_override(
    {
        "name": "closure-little-endian",
        "version": "1",
        "evidence": "Synthetic byte-swapped fixture for the D62 closure tests; not real data.",
        "endianness": "little",
    }
)

OLD_DEFAULTS = SurveyDeclaration(revision=1, template="PostStack3DTime")
"""What 1.2.0's closure silently re-ingested under, whatever the store had been written under."""


@dataclass(frozen=True)
class Case:
    """One reading a store is written under, and the file generator that fits it."""

    name: str
    declaration: SurveyDeclaration
    source: str  # which generator writes the file
    under_old_defaults: str  # measured: what re-ingesting the correct export under them does


REFUSED, DIFFERENT_STORE = "the file is refused", "a different store is built"

CASES = [
    Case(
        "rev0-override-time",
        SurveyDeclaration(0, "PostStack3DTime", REV0_OVERRIDE),
        "rev0",
        DIFFERENT_STORE,
    ),
    Case("rev1-depth", SurveyDeclaration(1, "PostStack3DDepth"), "rev1", DIFFERENT_STORE),
    Case(
        "rev0-override-depth",
        SurveyDeclaration(0, "PostStack3DDepth", REV0_OVERRIDE),
        "rev0",
        DIFFERENT_STORE,
    ),
    Case(
        "little-endian-override",
        SurveyDeclaration(1, "PostStack3DTime", LITTLE_ENDIAN),
        "le",
        REFUSED,
    ),
]


@pytest.fixture(scope="module", params=CASES, ids=lambda case: case.name)
def exported(request, tmp_path_factory):
    """One ingest under the declaration, one export, one clean closure - per case."""
    case: Case = request.param
    root = tmp_path_factory.mktemp(case.name)
    source = root / "src.sgy"
    if case.source == "le":
        make_byte_swapped(source, endianness="little")
    else:
        make_revision_poststack3d(source, revision=0 if case.source == "rev0" else 1)
    store = root / "out.mdio"
    result = ingest_declared(source, store, case.declaration)
    assert result.declaration is case.declaration, "the declaration is passed on, not rebuilt"
    path = root / "roundtrip.sgy"
    export(store, path, result.spec.segy_spec, source=source)
    baseline = roundtrip_closure(
        path, store, declaration=case.declaration, workdir=root / "baseline"
    )
    return case, store, path, root, baseline


def test_a_correct_export_closes_under_the_declaration_it_was_written_under(exported):
    _case, _store, _path, _root, baseline = exported
    assert baseline.passed, baseline.summary()
    assert baseline.only_in_original == [] and baseline.only_in_closure == []
    assert baseline.differing_arrays == []
    assert baseline.failed_planes == []
    # Plane 2 was handed the declaration, byte order included: a correct revision word is
    # not a finding in any of these readings, the little-endian one among them.
    assert baseline.planes[1].evidence["findings"] == []


def test_the_closure_control_is_caught_by_the_file_header_leg_alone(exported):
    case, store, path, root, baseline = exported
    check = closure_control(
        path, store, declaration=case.declaration, baseline=baseline, workdir=root / "ctl"
    )
    assert check["status"] == "PASS", check.get("failure_reasons")
    assert check["detected"]
    assert check["baseline_clean"]


def test_closure_handed_the_old_defaults_is_refused_not_failed(exported):
    """D62's symptom was a FAIL about correct data. The wrong declaration is now a refusal.

    Refused before anything is written: a comparison against a re-ingest performed under
    another reading says nothing about the export, whichever way it comes out.
    """
    case, store, path, root, _baseline = exported
    with pytest.raises(DeclarationMismatchError) as refusal:
        roundtrip_closure(path, store, declaration=OLD_DEFAULTS, workdir=root / "refused")
    message = str(refusal.value)
    assert OLD_DEFAULTS.summary() in message, "the reading that was handed over is named"
    written_under = (case.declaration.summary(), f"template {case.declaration.template} (MDIO")
    assert any(text in message for text in written_under), "and so is the store's"
    assert not (root / "refused").exists(), "a refused closure must write nothing"


def test_the_closure_control_handed_the_old_defaults_is_refused_too(exported):
    _case, store, path, root, baseline = exported
    with pytest.raises(DeclarationMismatchError):
        closure_control(
            path, store, declaration=OLD_DEFAULTS, baseline=baseline, workdir=root / "ctl_old"
        )


def test_the_old_defaults_do_not_rebuild_the_store_the_export_came_from(exported):
    """The reproducer. Without this the cases above could pass with the argument ignored.

    What 1.2.0's closure did, one step at a time: re-ingest the correct export under the
    old defaults and compare. Either the file is refused under that reading (the
    little-endian case - not a close), or it builds a different store.
    """
    case, store, path, root, _baseline = exported
    stale = root / "stale.mdio"
    if case.under_old_defaults == REFUSED:
        with pytest.raises(SdipError):
            ingest_declared(path, stale, OLD_DEFAULTS)
        return
    ingest_declared(path, stale, OLD_DEFAULTS)
    arrays = _compare_stores(store, stale)
    assert any(not a.equal or a.only_in_one for a in arrays), (
        f"{case.name}: the declaration made no difference to the re-ingested store"
    )


def test_closure_names_a_revision_word_that_disagrees_with_the_declaration(tmp_path):
    """The failing half of the assertion above: closure's Plane 2 does read the declaration.

    Before it was handed one, the evidence closure recorded about the export could not
    carry D59's finding at all, while the same check on the byte-identical source did.
    Non-blocking, so the export still closes.
    """
    declaration = SurveyDeclaration(revision=1, template="PostStack3DTime")
    good = make_revision_poststack3d(tmp_path / "r1.sgy", revision=1).path
    data = bytearray(good.read_bytes())
    data[3500:3502] = b"\x00\x00"
    source = tmp_path / "zero_word.sgy"
    source.write_bytes(bytes(data))
    store = tmp_path / "zero_word.mdio"
    result = ingest_declared(source, store, declaration)
    path = tmp_path / "roundtrip.sgy"
    export(store, path, result.spec.segy_spec, source=source)

    closure = roundtrip_closure(path, store, declaration=declaration, workdir=tmp_path / "work")
    assert closure.passed, closure.summary()
    [finding] = closure.planes[1].evidence["findings"]
    assert finding["code"] == "file_revision_differs"
    assert finding["file_revision"] == "0.0"
    assert finding["blocks_release"] is False
