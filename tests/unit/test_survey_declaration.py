"""The survey declaration: one definition of how a source is read, bound to its store.

**Why this exists (D47, DECISIONS.md D-0087).** Every command rebuilt its interpretation
of a SEG-Y from whatever it was handed, with silent defaults (revision 1, big-endian), and
nothing recorded which interpretation had written a store. Adding a declaration input to
one command therefore left every other command silently wrong: ``--override`` reached
2 of 5 commands, the preflight never saw the declared byte order at all, and ``verify``
on a correct revision 0 store returned FAIL under its defaults and a traceback when the
revision was retyped.

The declaration is the unit that fixes that. These tests pin its identity: what the
digest covers, what it deliberately does not, and that equal content hashes equal no
matter where the override file happens to live.
"""

from __future__ import annotations

import pytest

from sdip.spec import SurveyOverride, build_gap_free_spec, parse_override
from sdip.spec.declaration import DECLARATION_SCHEMA, SurveyDeclaration


def _document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "name": "unit-declaration",
        "version": "1",
        "evidence": "Fixture for the declaration unit tests; states nothing about real data.",
        "field": [{"name": "cdp_x", "byte": 181, "format": "int32"}],
    }
    document.update(changes)
    return document


def _override(**changes: object) -> SurveyOverride:
    return parse_override(_document(**changes))


def test_the_digest_is_deterministic():
    declaration = SurveyDeclaration(revision=0, template="PostStack3DTime", override=_override())
    assert declaration.sha256() == declaration.sha256()
    assert len(declaration.sha256()) == 64


def test_where_the_override_file_lives_is_not_part_of_the_identity():
    """Same content read from two paths is the same declaration.

    The override's certificate block carries ``source_path``. Hashing it would make a
    store written on one machine refuse to verify on another, and would leak the issuing
    machine's path into an identifier (the D46 class).
    """
    here = parse_override(_document(), source="/a/one.toml")
    there = parse_override(_document(), source="/b/two.toml")
    assert here.path != there.path
    first = SurveyDeclaration(revision=1, template="PostStack3DTime", override=here)
    second = SurveyDeclaration(revision=1, template="PostStack3DTime", override=there)
    assert first.sha256() == second.sha256()
    assert "/a/one.toml" not in repr(first.canonical())


@pytest.mark.parametrize(
    ("label", "other"),
    [
        (
            "revision",
            SurveyDeclaration(revision=1, template="PostStack3DTime", override=_override()),
        ),
        (
            "template",
            SurveyDeclaration(revision=0, template="PostStack3DDepth", override=_override()),
        ),
        ("no override", SurveyDeclaration(revision=0, template="PostStack3DTime")),
        (
            "field format",
            SurveyDeclaration(
                revision=0,
                template="PostStack3DTime",
                override=_override(field=[{"name": "cdp_x", "byte": 181, "format": "uint32"}]),
            ),
        ),
        (
            "endianness",
            SurveyDeclaration(
                revision=0, template="PostStack3DTime", override=_override(endianness="little")
            ),
        ),
        (
            "evidence",
            SurveyDeclaration(
                revision=0,
                template="PostStack3DTime",
                override=_override(
                    evidence="Edited without a version bump, which must still change identity."
                ),
            ),
        ),
        (
            "grid overrides",
            SurveyDeclaration(
                revision=0,
                template="PostStack3DTime",
                override=_override(),
                grid_overrides={"HasDuplicates": True},
            ),
        ),
    ],
)
def test_every_input_that_changes_how_bytes_are_read_changes_the_digest(label, other):
    """``spec_sha256`` covers names, positions and widths — not types or byte order.

    A big-endian and a little-endian reading of one layout share a ``spec_sha256``, so it
    cannot serve as the binding. The declaration digest must cover everything that
    changes the reading, including the evidence: an override edited in place without a
    version bump is a different declaration wearing the same name.
    """
    base = SurveyDeclaration(revision=0, template="PostStack3DTime", override=_override())
    assert base.sha256() != other.sha256(), label


def test_spec_sha256_really_is_blind_to_byte_order():
    """The premise of the test above, measured rather than asserted."""
    big = build_gap_free_spec(1, override=_override(endianness="big"))
    little = build_gap_free_spec(1, override=_override(endianness="little"))
    assert big.sha256() == little.sha256()
    big_decl = SurveyDeclaration(
        revision=1, template="PostStack3DTime", override=_override(endianness="big")
    )
    little_decl = SurveyDeclaration(
        revision=1, template="PostStack3DTime", override=_override(endianness="little")
    )
    assert big_decl.sha256() != little_decl.sha256()


def test_an_integral_float_revision_is_the_same_revision():
    """``--revision 1`` parses to ``1``; an API caller may pass ``1.0``. One identity."""
    assert (
        SurveyDeclaration(revision=1, template="PostStack3DTime").sha256()
        == SurveyDeclaration(revision=1.0, template="PostStack3DTime").sha256()
    )
    assert (
        SurveyDeclaration(revision=2.1, template="PostStack3DTime").sha256()
        != SurveyDeclaration(revision=2, template="PostStack3DTime").sha256()
    )


def test_the_canonical_form_names_its_schema():
    canonical = SurveyDeclaration(revision=1, template="PostStack3DTime").canonical()
    assert canonical["schema"] == DECLARATION_SCHEMA


def test_the_summary_is_what_an_operator_needs_to_retype_it():
    declaration = SurveyDeclaration(revision=0, template="PostStack3DDepth", override=_override())
    summary = declaration.summary()
    assert "revision 0" in summary
    assert "PostStack3DDepth" in summary
    assert "unit-declaration@1" in summary
    assert "no override" in SurveyDeclaration(revision=1, template="PostStack3DTime").summary()


def test_the_declaration_builds_exactly_the_spec_it_names():
    override = _override()
    declaration = SurveyDeclaration(revision=0, template="PostStack3DTime", override=override)
    assert declaration.build_spec().sha256() == build_gap_free_spec(0, override=override).sha256()
    assert declaration.build_spec().spec_id == build_gap_free_spec(0, override=override).spec_id
