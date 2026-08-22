"""Survey spec overrides. Specification §6.4, open debt **D21**.

Three probes stopped at this one missing mechanism — P6 (rev 0 cannot ingest), P7 (no
prestack geometry can ingest), P5 (a little-endian file cannot be declared) — so the
tests here are organised around what each of them needs rather than around the module's
call graph.

Two properties carry most of the weight and are worth naming before the code:

**Evidence is the condition of acceptance, not documentation.** §6.4 says an override
with no cited evidence is rejected at review. Review is a person, and a person can be
tired, so it is also rejected at load. The tests below fix the boundary rather than
asserting that *some* rejection happens.

**An override may not introduce `ibm32`.** This is the one place a caller could put that
format into a header, `DECISIONS.md` D-0003 having measured zero `ibm32` fields in every
standard trace header the pinned `segy` exposes. Probe P2 **failed** (D-0034), so the
refusal is on a fired falsifier — not a deferral pending one — and the error has to say
so, because an operator who reads "not yet supported" will come back in a month and ask
again.

The G1 test at the end ships with its negative control in the same file, per §5 of the
operating contract. The assertion is not "G1 still passes on a good override"; it is
"a *narrower* redeclaration is caught", because that is the failure mode which is
otherwise silent — ``HeaderSpec.customize`` removes every field the new declarations
intersect and raises nothing when the replacement covers less than what it displaced.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
from segy import SegyFile

from sdip._pins import SEGY_TRACE_HEADER_BYTES
from sdip.spec import (
    ALL_BYTES,
    EVIDENCE_MIN_CHARS,
    build_gap_free_spec,
    g1_for_spec,
    load_override,
    parse_override,
)
from sdip.spec.overrides import ENDIANNESS_INFER, SurveyOverrideError, apply_override

OVERRIDES_DIR = Path(__file__).resolve().parents[2] / "overrides"
"""The committed registry. §6.4 makes it a shared asset, so it is checked as one."""

COMMITTED = ("segy-rev0-poststack3d", "rev1-offset-alias", "rev1-cdp-alias")
"""Every override this repository ships. Named, so a deletion is a test failure."""

REV0_GEOMETRY = {"cdp_x": 181, "cdp_y": 185, "inline": 189, "crossline": 193}
"""What the rev 0 override declares. The rev 1 canonical positions, 4-byte int32 each."""

REV0_GAP_FREE_FIELDS = 131
REV0_OVERRIDDEN_FIELDS = 119
"""131 gap-free fields, minus the 16 uint8 fillers over 181-196, plus 4 int32.

The second number is `DECISIONS.md` D-0037's own measured diagnosis of the rev 0
blocker, reproduced here through the mechanism rather than through a test-local
``customize`` call.
"""


def _document(**overrides: object) -> dict[str, object]:
    """A minimal valid override document, with keys replaced for the case under test."""
    document: dict[str, object] = {
        "name": "unit-fixture",
        "version": "1",
        "evidence": "Fixture for the unit tests; states nothing about real data.",
        "field": [{"name": "cdp_x", "byte": 181, "format": "int32"}],
    }
    document.update(overrides)
    return document


# ---------------------------------------------------------------------------
# The committed registry
# ---------------------------------------------------------------------------


def test_the_registry_directory_exists_and_is_not_empty():
    """§6.4 specifies a registry. An empty one is a mechanism with nothing in it."""
    assert OVERRIDES_DIR.is_dir()
    assert sorted(p.stem for p in OVERRIDES_DIR.glob("*.toml")) == sorted(COMMITTED)


@pytest.mark.parametrize("name", COMMITTED)
def test_every_committed_override_loads(name):
    """A file in the registry that does not load is worse than one that is absent.

    The registry is contributed to by users (§6.4). This is the check that turns a
    malformed contribution into a CI failure instead of a runtime one.
    """
    override = load_override(OVERRIDES_DIR / f"{name}.toml")
    assert override.name == name
    assert override.version
    assert override.fields


@pytest.mark.parametrize("name", COMMITTED)
def test_every_committed_override_cites_a_source(name):
    """An override with no cited evidence is rejected at review — **spec §6.4**.

    The 20-character floor in the loader stops a blank; it cannot tell a citation from a
    sentence. This asserts the stronger property for the registry specifically: each
    entry points at either the standard that defines the bytes or the measurement that
    found the need. Prose without a source is an assertion, and assertions get sent back
    (**SP8**).
    """
    evidence = load_override(OVERRIDES_DIR / f"{name}.toml").evidence
    assert "SEG-Y rev" in evidence, "must name the standard that defines the bytes"
    assert "DECISIONS.md" in evidence, "must name the measurement that found the need"
    assert "SCOPE" in evidence, "must state where the mapping stops being correct"


def test_the_rev0_override_declares_exactly_the_four_canonical_positions():
    """The four fields `PostStack3DTime` binds on, at the bytes rev 1 standardised."""
    override = load_override(OVERRIDES_DIR / "segy-rev0-poststack3d.toml")
    assert {f.name: f.byte for f in override.fields} == REV0_GEOMETRY
    assert {f.format for f in override.fields} == {"int32"}
    assert {f.size for f in override.fields} == {4}


@pytest.mark.parametrize(
    ("name", "field", "byte"),
    [("rev1-offset-alias", "offset", 37), ("rev1-cdp-alias", "cdp", 21)],
)
def test_the_rev1_aliases_land_on_the_standard_field_they_rename(name, field, byte):
    """P7's finding: for `offset` and `cdp` the bytes exist under another name.

    Asserted against the pinned standard rather than against a constant, so a pin bump
    that moved either field would fail here instead of shipping an alias onto the wrong
    bytes.
    """
    from segy.standards import get_segy_standard

    standard = {f.name: (f.byte, f.format.value) for f in get_segy_standard(1).trace.header.fields}
    displaced = {"offset": "source_to_receiver_distance", "cdp": "ensemble_num"}[field]

    override = load_override(OVERRIDES_DIR / f"{name}.toml")
    (declaration,) = override.fields
    assert declaration.name == field
    assert (declaration.byte, declaration.format) == standard[displaced]
    assert byte == standard[displaced][0]
    assert field not in standard, "an alias for a name the standard already uses is not an alias"


# ---------------------------------------------------------------------------
# Evidence is the condition of acceptance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "evidence",
    ["", "   ", "legacy survey", "x" * (EVIDENCE_MIN_CHARS - 1), " " * 40 + "short" + " " * 40],
)
def test_an_unevidenced_override_is_refused(evidence):
    """Including the whitespace cases: the bound is on content, not on length.

    ``"legacy survey"`` is the entry this rule exists for. A mechanism that only rejects
    the empty string rejects nothing anybody would actually write.
    """
    with pytest.raises(SurveyOverrideError, match="evidence"):
        parse_override(_document(evidence=evidence))


def test_evidence_of_exactly_the_minimum_length_is_accepted():
    """The boundary in the other direction. A rule nobody can satisfy is not a rule."""
    override = parse_override(_document(evidence="x" * EVIDENCE_MIN_CHARS))
    assert len(override.evidence) == EVIDENCE_MIN_CHARS


def test_missing_evidence_is_refused_and_the_error_cites_the_section():
    """An operator who hits this needs to know it is a specification rule, not a lint."""
    document = _document()
    del document["evidence"]
    with pytest.raises(SurveyOverrideError, match=r"6\.4"):
        parse_override(document)


def test_the_evidence_reaches_the_certificate_verbatim():
    """Recording only the override's name would leave a reader unable to judge it.

    The certificate schema requires ``spec_override.evidence`` with ``minLength: 20``;
    carrying the note itself is what makes the certificate self-contained (§4.7).
    """
    override = parse_override(_document(evidence="Observer report, line 12, 1998 survey."))
    assert override.to_json()["evidence"] == "Observer report, line 12, 1998 survey."


# ---------------------------------------------------------------------------
# ibm32 is refused on a FAILED probe, not deferred pending one
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("declared", ["ibm32", "IBM32", "Ibm32", "ibm"])
def test_an_override_declaring_ibm32_is_refused(declared):
    """**The refusal P2's failure requires.** Case-folded, and covering the short spelling.

    ``ibm32`` is a legal ``ScalarType``, so nothing upstream would stop this. It is the
    only route by which an ``ibm32`` header field could enter an SDIP spec at all.
    """
    with pytest.raises(SurveyOverrideError) as raised:
        parse_override(_document(field=[{"name": "cdp_x", "byte": 181, "format": declared}]))
    assert "REFUSED" in str(raised.value)


def test_the_ibm32_refusal_names_the_probe_and_says_the_falsifier_fired():
    """A refusal an operator reads as "not yet" will be asked for again next month.

    The message has to carry three things: that it is P2, that P2 **fired**, and what
    the alternative is. ``uint8`` is the declaration that claims nothing about bytes
    whose numeric format is unknown (**SP5**).
    """
    with pytest.raises(SurveyOverrideError) as raised:
        parse_override(_document(field=[{"name": "cdp_x", "byte": 181, "format": "ibm32"}]))
    message = str(raised.value)
    assert "P2" in message
    assert "FIRED" in message
    assert "not a deferral" in message
    assert "uint8" in message


def test_a_format_the_pinned_segy_does_not_define_is_refused():
    """Neither guessed nor passed through. An unresolvable width cannot be covered."""
    with pytest.raises(SurveyOverrideError, match="pinned segy"):
        parse_override(_document(field=[{"name": "cdp_x", "byte": 181, "format": "float128"}]))


# ---------------------------------------------------------------------------
# Malformed declarations, refused before they reach `customize`
# ---------------------------------------------------------------------------


def test_an_unknown_top_level_key_is_refused():
    """A misspelled key that is silently ignored is an override that did not apply."""
    with pytest.raises(SurveyOverrideError, match="unknown key"):
        parse_override(_document(revision=0))


def test_an_unknown_field_key_is_refused():
    """Same reason, one level down. ``bytes = 181`` must not read as ``byte = 181``."""
    with pytest.raises(SurveyOverrideError, match="unknown key"):
        parse_override(_document(field=[{"name": "x", "bytes": 181, "format": "int32"}]))


@pytest.mark.parametrize(
    ("byte", "fmt"),
    [
        (0, "int32"),
        (-1, "int32"),
        (241, "uint8"),
        (239, "int32"),
        (SEGY_TRACE_HEADER_BYTES, "int16"),
    ],
)
def test_a_declaration_outside_the_240_byte_header_is_refused(byte, fmt):
    """Both ends, and the straddle. Byte 239 as ``int32`` runs to 242 and is out."""
    with pytest.raises(SurveyOverrideError, match="outside"):
        parse_override(_document(field=[{"name": "x", "byte": byte, "format": fmt}]))


def test_a_non_integer_byte_is_refused():
    """TOML has real types; ``byte = "181"`` is a different document."""
    with pytest.raises(SurveyOverrideError, match="integer"):
        parse_override(_document(field=[{"name": "x", "byte": "181", "format": "int32"}]))


def test_two_declarations_of_the_same_name_are_refused():
    """Upstream would keep the last one silently. Which one was meant is unknowable."""
    with pytest.raises(SurveyOverrideError, match="declared twice"):
        parse_override(
            _document(
                field=[
                    {"name": "inline", "byte": 189, "format": "int32"},
                    {"name": "inline", "byte": 9, "format": "int32"},
                ]
            )
        )


def test_declarations_that_overlap_each_other_are_refused():
    """Caught here rather than inside ``customize``, which reports it as a header fault.

    By the time upstream raises, the base spec has already been mutated, and the message
    names header fields rather than the file the operator has to go and fix.
    """
    with pytest.raises(SurveyOverrideError, match="both claim byte 191"):
        parse_override(
            _document(
                field=[
                    {"name": "inline", "byte": 189, "format": "int32"},
                    {"name": "crossline", "byte": 191, "format": "int32"},
                ]
            )
        )


def test_an_override_that_changes_nothing_is_refused():
    """No field, no endianness. Applying it would produce a spec identical to the base.

    Accepting it would put a name and a version on the certificate for a mapping that
    did not happen, which is worse than the absence of an override.
    """
    document = _document()
    del document["field"]
    with pytest.raises(SurveyOverrideError, match="not an override"):
        parse_override(document)


def test_a_file_that_is_not_valid_toml_is_refused_cleanly(tmp_path):
    """§11.4 in miniature: a malformed input produces a typed error, not a traceback."""
    path = tmp_path / "broken.toml"
    path.write_text('name = "x"\nversion = ')
    with pytest.raises(SurveyOverrideError, match="not valid TOML"):
        load_override(path)


def test_a_missing_file_is_refused_cleanly(tmp_path):
    with pytest.raises(SurveyOverrideError, match="cannot be read"):
        load_override(tmp_path / "absent.toml")


# ---------------------------------------------------------------------------
# G1 after the override — and the control that must fail it
# ---------------------------------------------------------------------------


def test_g1_still_passes_after_the_rev0_override_is_applied():
    """D-0037's measured diagnosis, reproduced through the mechanism: 119 fields.

    The rev 0 override displaces 16 ``uint8`` fillers with 4 ``int32``, so a spec that
    was gap-free stays gap-free and the field count is the one D-0037 recorded.
    """
    base = build_gap_free_spec(0)
    assert base.field_count == REV0_GAP_FREE_FIELDS

    built = build_gap_free_spec(
        0, override=load_override(OVERRIDES_DIR / "segy-rev0-poststack3d.toml")
    )
    assert g1_for_spec(built).status == "PASS"
    assert built.field_count == REV0_OVERRIDDEN_FIELDS
    assert built.itemsize == SEGY_TRACE_HEADER_BYTES
    assert built.coverage.covered == ALL_BYTES


def test_a_narrower_redeclaration_breaks_gap_freeness_and_is_caught():
    """**NEGATIVE CONTROL.** The silent failure the G1 re-run exists to catch.

    ``cdp_x`` occupies rev 1 bytes 181-184. Declaring an ``int16`` at 181 removes it —
    ``customize`` drops every field the new declaration intersects — and covers only
    181-182, leaving 183-184 addressable by nothing. Upstream raises nothing: the spec
    is simply no longer gap-free, and two bytes stop being recoverable while everything
    still looks built.

    The error must say the override did it. "G1 FAIL: 2 uncovered bytes" sends an
    operator to the generator, which is not where the fault is.
    """
    document = _document(name="narrower", field=[{"name": "half", "byte": 181, "format": "int16"}])
    override = parse_override(document)

    with pytest.raises(SurveyOverrideError) as raised:
        build_gap_free_spec(1, override=override)

    message = str(raised.value)
    assert "narrower@1" in message
    assert "broke gap-freeness" in message
    assert "183-184" in message


def test_the_negative_control_fails_only_gap_freeness():
    """Only its gate (§5), one level down. The declaration is otherwise well-formed.

    If the narrower declaration were rejected by the parser too, the test above would
    pass for the wrong reason and the G1 re-run would never have been exercised.
    """
    override = parse_override(
        _document(name="narrower", field=[{"name": "half", "byte": 181, "format": "int16"}])
    )
    assert override.fields[0].size == 2
    assert override.identifier == "narrower@1"


def test_a_wider_redeclaration_that_stays_gap_free_is_accepted():
    """Not every departure from the standard's widths is a fault.

    Bytes 181-188 are ``cdp_x`` and ``cdp_y`` in rev 1. One ``int64`` over both covers
    exactly what it displaced, so G1 holds. Whether that is a *sensible* thing to
    declare is a review question, and §6.4 puts it in front of a reviewer with the
    evidence attached rather than in front of this gate.
    """
    override = parse_override(_document(field=[{"name": "pair", "byte": 181, "format": "int64"}]))
    built = build_gap_free_spec(1, override=override)
    assert g1_for_spec(built).status == "PASS"
    assert built.coverage.covered == ALL_BYTES


# ---------------------------------------------------------------------------
# Byte content is never changed
# ---------------------------------------------------------------------------


def test_the_override_reads_exactly_the_bytes_the_fillers_covered(tmp_path):
    """Overrides change labels and numeric interpretation, **never byte content** (§6.4).

    Measured, not argued. The same rev 0 file is read twice — once under the gap-free
    base spec, where bytes 181-196 are sixteen ``uint8`` fillers, and once under the
    override, where they are four ``int32``. For each declared field, the value read
    through the override must equal the big-endian integer assembled from the four
    filler bytes the base spec read at the same positions.

    That is the whole claim, and it is stronger than comparing the file to itself: it
    shows the override reinterprets *those bytes and only those*, in the file's declared
    byte order, adding nothing (**SP12**).

    A raw ``.view(np.uint8)`` comparison would be the wrong instrument here — the reader
    byte-swaps integers to native order, so the two views differ by decode even when
    every byte in the file is untouched.
    """
    from tests.fixtures.generators.irregular import make_rev0_minimal

    fixture = make_rev0_minimal(tmp_path / "rev0.sgy")
    before = fixture.path.read_bytes()

    base = build_gap_free_spec(0)
    built = build_gap_free_spec(
        0, override=load_override(OVERRIDES_DIR / "segy-rev0-poststack3d.toml")
    )

    base_headers = SegyFile(str(fixture.path), spec=base.segy_spec).header[:]
    over_headers = SegyFile(str(fixture.path), spec=built.segy_spec).header[:]

    for name, byte in REV0_GEOMETRY.items():
        assembled = np.array(
            [
                int.from_bytes(
                    bytes(int(base_headers[f"pad_{byte + k}"][i]) for k in range(4)),
                    "big",
                    signed=True,
                )
                for i in range(len(over_headers))
            ],
            dtype=np.int32,
        )
        assert np.array_equal(np.asarray(over_headers[name]), assembled), name

    # Every field both specs still declare must read identically: the override displaced
    # bytes 181-196 and must have left the other 224 alone.
    shared = set(base_headers.dtype.names or ()) & set(over_headers.dtype.names or ())
    assert len(shared) == REV0_GAP_FREE_FIELDS - 16
    for name in sorted(shared):
        assert np.array_equal(np.asarray(base_headers[name]), np.asarray(over_headers[name])), name

    assert fixture.path.read_bytes() == before, "reading a spec must not touch the file"


def test_the_byte_invariance_check_can_fail(tmp_path):
    """NEGATIVE CONTROL for the test above. A comparison never shown to fail is not one.

    Declaring ``inline`` at 190 rather than 189 reads a different four bytes, and the
    assembled-from-fillers expectation no longer matches. Nothing in the file changed;
    the *interpretation* did, which is precisely the error class an evidence note
    exists to prevent and which no gate in SDIP can catch on the operator's behalf.
    """
    from tests.fixtures.generators.irregular import make_rev0_minimal

    fixture = make_rev0_minimal(tmp_path / "rev0.sgy")
    base = build_gap_free_spec(0)
    shifted = build_gap_free_spec(
        0,
        override=parse_override(
            _document(field=[{"name": "inline", "byte": 190, "format": "int32"}])
        ),
    )

    base_headers = SegyFile(str(fixture.path), spec=base.segy_spec).header[:]
    over_headers = SegyFile(str(fixture.path), spec=shifted.segy_spec).header[:]

    assembled = np.array(
        [
            int.from_bytes(
                bytes(int(base_headers[f"pad_{189 + k}"][i]) for k in range(4)), "big", signed=True
            )
            for i in range(len(over_headers))
        ],
        dtype=np.int32,
    )
    assert not np.array_equal(np.asarray(over_headers["inline"]), assembled)


# ---------------------------------------------------------------------------
# Endianness — probe P5's blocker
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("declared", ["big", "little"])
def test_an_override_can_declare_the_files_byte_order(declared):
    """Declare the byte order the file is actually in. Probe **P5**.

    P5 could not declare a little-endian SEG-Y: the spec inherited ``big`` from the
    revision standard and ``ingest()`` had no surface to change it. This is that surface.
    """
    override = parse_override(_document(endianness=declared))
    built = build_gap_free_spec(1, override=override)
    assert built.segy_spec.endianness.value == declared
    # Assignment must reach the sub-specs, or only half the file is read in that order.
    assert built.segy_spec.trace.endianness.value == declared
    assert built.segy_spec.trace.header.endianness.value == declared


def test_infer_hands_the_decision_to_segy():
    """``segy`` reads the byte order from the binary header when the spec declares none.

    Inferring is a real answer for an operator who does not know, and it is *not* the
    same as declaring ``big``: a declaration that happens to be wrong is read as data.
    """
    built = build_gap_free_spec(1, override=parse_override(_document(endianness=ENDIANNESS_INFER)))
    assert built.segy_spec.endianness is None
    assert built.segy_spec.trace.header.endianness is None


def test_an_endianness_only_override_needs_no_field():
    """The P5 case declares no field at all, so an override must be valid without one."""
    document = _document(endianness="little")
    del document["field"]
    override = parse_override(document)
    assert override.fields == ()
    assert override.endianness == "little"


def test_an_unknown_endianness_is_refused():
    with pytest.raises(SurveyOverrideError, match="endianness"):
        parse_override(_document(endianness="network"))


def test_a_little_endian_file_reads_correctly_once_declared(tmp_path):
    """The end of P5's leg: declare the byte order and the values come back right.

    Without the declaration the same bytes decode to nonsense — asserted, because
    "little-endian now works" is a claim and a pair of readings is a measurement.
    """
    from tests.fixtures.generators.irregular import make_byte_swapped

    fixture = make_byte_swapped(tmp_path / "little.sgy", endianness="little")
    expected = np.array([inline for inline, _ in fixture.index_pairs], dtype=np.int32)

    declared = build_gap_free_spec(1, override=parse_override(_document(endianness="little")))
    headers = SegyFile(str(fixture.path), spec=declared.segy_spec).header[:]
    assert np.array_equal(np.asarray(headers["inline"]), expected)

    inferred = build_gap_free_spec(
        1, override=parse_override(_document(endianness=ENDIANNESS_INFER))
    )
    headers = SegyFile(str(fixture.path), spec=inferred.segy_spec).header[:]
    assert np.array_equal(np.asarray(headers["inline"]), expected)


# ---------------------------------------------------------------------------
# Wiring: the override travels with the spec it produced
# ---------------------------------------------------------------------------


def test_build_gap_free_spec_without_an_override_is_unchanged():
    """Every existing caller passes a revision and nothing else. That must keep working."""
    built = build_gap_free_spec(1)
    assert built.override is None
    assert built.spec_id == "segy-rev1-gapfree-8f"
    assert built.to_json()["spec_override"] is None
    assert g1_for_spec(built).status == "PASS"


def test_the_spec_id_distinguishes_an_overridden_spec_from_its_base():
    """Fillers are counted before the override, so revision and filler count collide.

    Two specs that address the header differently must not share an identifier — the
    certificate carries ``spec_id``, and a reader comparing two certificates has only
    that string and the hash.
    """
    base = build_gap_free_spec(0)
    built = build_gap_free_spec(
        0, override=load_override(OVERRIDES_DIR / "segy-rev0-poststack3d.toml")
    )

    assert base.spec_id == "segy-rev0-gapfree-60f"
    assert built.spec_id == "segy-rev0-gapfree-60f+segy-rev0-poststack3d@1"
    assert len(base.fillers) == len(built.fillers)
    assert base.sha256() != built.sha256()


def test_the_override_block_is_certificate_shaped():
    """§4.7 requires name, version and evidence; the fields make it reproducible."""
    built = build_gap_free_spec(
        0, override=load_override(OVERRIDES_DIR / "segy-rev0-poststack3d.toml")
    )
    block = built.to_json()["spec_override"]

    assert block["name"] == "segy-rev0-poststack3d"
    assert block["version"] == "1"
    assert len(block["evidence"]) >= EVIDENCE_MIN_CHARS
    assert [f["byte"] for f in block["fields"]] == [181, 185, 189, 193]
    assert [f["size"] for f in block["fields"]] == [4, 4, 4, 4]
    assert block["source_path"].endswith("segy-rev0-poststack3d.toml")


def test_apply_override_takes_a_raw_spec_and_leaves_the_caller_to_recompute():
    """The layer below ``build_gap_free_spec``, and the reason it is not the entry point.

    A ``GapFreeSpec`` caches coverage, filler names and field count. Mutating the spec
    underneath one would leave those numbers describing a spec that no longer exists,
    and a ``field_count`` that lies is worse than one that is absent.
    """
    built = build_gap_free_spec(0)
    apply_override(built.segy_spec, load_override(OVERRIDES_DIR / "segy-rev0-poststack3d.toml"))

    assert len(built.segy_spec.trace.header.fields) == REV0_OVERRIDDEN_FIELDS
    assert g1_for_spec(built.segy_spec).status == "PASS"
    assert built.field_count == REV0_GAP_FREE_FIELDS, "the cached count is deliberately stale"


# ---------------------------------------------------------------------------
# End to end — the debt this mechanism was raised to close
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rev0_ingests_with_the_override_and_round_trips_byte_identically():
    """**D21 closed for rev 0.** All five planes, and a byte-identical round trip.

    D-0037 measured rev 0 as one specified-but-unimplemented mechanism away from
    working, and named the mechanism: a §6.4 survey override declaring the four
    geometry fields. This runs that leg through the supported API — ``ingest`` with an
    override loaded from the committed registry — rather than through a test-local
    ``customize`` call, which is the difference between a diagnosis and a capability.

    **Plane 3 (G2c) is the byte-content re-verification §6.4 requires.** It compares all
    240 header bytes per trace against the source through the overridden spec; G3 then
    hashes the whole exported file against the source. An override that changed byte
    content fails both, whatever this module believes about itself.

    This does **not** satisfy probe P6, whose pre-registered method builds the spec with
    ``build_gap_free_spec`` and nothing else. Under that method rev 0 still does not
    ingest, and the P6 record stands until its own pre-registration is revisited.
    """
    from sdip.equivalence import plane_1, plane_2, plane_3, plane_4, plane_5
    from sdip.export import export
    from sdip.ingest import ingest
    from tests.fixtures.generators.irregular import make_rev0_minimal

    override = load_override(OVERRIDES_DIR / "segy-rev0-poststack3d.toml")
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        fixture = make_rev0_minimal(work / "rev0.sgy")
        store = work / "rev0.mdio"

        result = ingest(
            fixture.path, store, revision=0, template="PostStack3DTime", override=override
        )
        assert result.g1.status == "PASS"
        assert result.read_path_intact
        assert result.spec.field_count == REV0_OVERRIDDEN_FIELDS
        assert result.spec.override is not None
        assert result.to_json()["spec_override"]["name"] == "segy-rev0-poststack3d"

        spec = result.spec.segy_spec
        planes = (
            plane_1(fixture.path, store),
            plane_2(fixture.path, store),
            plane_3(fixture.path, store, spec, g1_passed=True),
            plane_4(fixture.path, store, spec),
            plane_5(fixture.path, store, spec),
        )
        assert [p.status for p in planes] == ["PASS"] * 5
        assert planes[2].gate == "G2c", "Plane 3 is the byte-content re-verification"

        roundtrip = export(store, work / "back.sgy", spec, source=fixture.path)
        assert roundtrip.byte_identical
        assert roundtrip.first_difference() is None
