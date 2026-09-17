"""The hostile-input preflight reads the binary header in the DECLARED byte order.

**Regression guard for D28 (DECISIONS.md D-0087).** D28 closed at 07:44 on 2026-08-23:
a survey override could declare ``endianness``. At 09:49 the same day the preflight
arrived, reading the binary header big-endian without ever being given the declaration.
From then on a little-endian SEG-Y was refused *with* its override — and the refusal told
the operator SDIP does not read little-endian, which was no longer true. No test failed,
because D28's only test read headers through ``SegyFile`` directly and never ingested.

Every test here drives the preflight itself, which is the layer that regressed.
"""

from __future__ import annotations

import pytest

from sdip.errors import UntrustedInputError
from sdip.ingest.orchestrator import validate_source
from sdip.ingest.preflight import validate_segy_structure
from sdip.spec import parse_override
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators.irregular import make_byte_swapped


@pytest.fixture
def little(tmp_path):
    return make_byte_swapped(tmp_path / "little.sgy", endianness="little")


@pytest.fixture
def big(tmp_path):
    return make_byte_swapped(tmp_path / "big.sgy", endianness="big")


def _size(fixture) -> int:
    return fixture.path.stat().st_size


def test_an_undeclared_little_endian_file_is_still_refused(little):
    """Nothing is guessed. Big-endian stays the default, as the revision standard says."""
    with pytest.raises(UntrustedInputError):
        validate_segy_structure(little.path, _size(little))


def test_the_refusal_names_the_declaration_that_would_admit_the_file(little):
    """The old hint said SDIP 'does not guess byte order' — a dead end once D28 closed.

    It must now say how to declare it, because the operator's next action is to do so.
    """
    with pytest.raises(UntrustedInputError) as caught:
        validate_segy_structure(little.path, _size(little))
    message = str(caught.value)
    assert "little-endian" in message
    assert "endianness" in message
    assert "--override" in message


@pytest.mark.parametrize("declared", ["little", "infer"])
def test_a_declared_little_endian_file_passes(little, declared):
    layout = validate_segy_structure(little.path, _size(little), endianness=declared)
    assert layout.endianness == "little"
    assert layout.samples_per_trace == little.samples_per_trace
    assert layout.sample_interval_us == little.sample_interval_us


@pytest.mark.parametrize("declared", [None, "big", "infer"])
def test_a_big_endian_file_passes_as_big(big, declared):
    layout = validate_segy_structure(big.path, _size(big), endianness=declared)
    assert layout.endianness == "big"
    assert layout.samples_per_trace == big.samples_per_trace


def test_a_wrong_declaration_is_refused_and_says_which_order_fits(big):
    """Declaring little-endian over a big-endian file is an operator error, named as one."""
    with pytest.raises(UntrustedInputError) as caught:
        validate_segy_structure(big.path, _size(big), endianness="little")
    assert "big-endian" in str(caught.value)


def test_an_unknown_byte_order_is_refused_before_anything_is_read(big):
    with pytest.raises(UntrustedInputError, match="endianness"):
        validate_segy_structure(big.path, _size(big), endianness="middle")


def _declared(endianness: str | None) -> SurveyDeclaration:
    if endianness is None:
        return SurveyDeclaration(revision=1, template="PostStack3DTime")
    override = parse_override(
        {
            "name": f"preflight-{endianness}",
            "version": "1",
            "evidence": "Synthetic byte-swapped fixture for the preflight tests; not real data.",
            "endianness": endianness,
        }
    )
    return SurveyDeclaration(revision=1, template="PostStack3DTime", override=override)


@pytest.mark.parametrize("endianness", ["little", "infer"])
def test_the_orchestrator_entry_point_reads_the_declared_byte_order(little, endianness):
    """``validate_source`` is what ``ingest`` and ``verify`` call; the regression lived here.

    It takes the declaration whole (OPEN_DEBTS D62's class): while the byte order was a
    keyword defaulting to big-endian, leaving it out was silent.
    """
    assert validate_source(little.path, _declared(endianness)).endianness == "little"


def test_the_orchestrator_entry_point_refuses_the_file_under_another_declaration(little):
    """The other half: the declaration is read, not ignored. Nothing is guessed."""
    with pytest.raises(UntrustedInputError):
        validate_source(little.path, _declared(None))
    with pytest.raises(UntrustedInputError):
        validate_source(little.path, _declared("big"))


def test_an_uninferable_byte_order_is_a_clean_refusal_not_a_traceback(tmp_path):
    """``segy`` raises ``EndiannessInferenceError`` — a ``SegyError``, NOT a ``ValueError``.

    A catch written for ``ValueError`` looks right and lets it escape as a traceback,
    which is exactly the §3.6 defect this work exists to remove. Zeroed binary header:
    no byte-order constant, nothing for the heuristic to hold on to.
    """
    path = tmp_path / "blank.sgy"
    path.write_bytes(bytes(3600 + 240 + 4))
    with pytest.raises(UntrustedInputError, match="infer"):
        validate_segy_structure(path, path.stat().st_size, endianness="infer")


def test_an_undefined_sample_format_names_d22_and_why_it_cannot_be_declared_yet(tmp_path):
    """An undefined format code is refused with D22 named.

    D22 stays open by ruling (Ruling 7: no real file has needed it). The refusal must say so,
    rather than leave an operator to discover that no override can supply a format.
    """
    import struct

    from tests.fixtures.generators.poststack3d import make_poststack3d

    fixture = make_poststack3d(tmp_path / "f.sgy", n_inline=2, n_crossline=2, n_samples=4)
    data = bytearray(fixture.path.read_bytes())
    data[3224:3226] = struct.pack(">h", 0)
    path = tmp_path / "code0.sgy"
    path.write_bytes(bytes(data))
    with pytest.raises(UntrustedInputError) as caught:
        validate_segy_structure(path, path.stat().st_size)
    message = str(caught.value)
    assert "D22" in message
    assert "override" in message
