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


def test_the_orchestrator_entry_point_forwards_the_declaration(little):
    """``validate_source`` is what ``ingest`` calls. The regression lived at this seam."""
    assert validate_source(little.path, endianness="little").endianness == "little"


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
