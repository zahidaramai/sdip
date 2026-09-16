"""D27: a coordinate scalar MDIO will refuse is refused first, cleanly, and explained.

Before this, ``sdip ingest`` on a revision 0 or 1 file whose first trace carries a zero
coordinate scalar died with ``ValueError: Invalid coordinate scalar: 0`` raised out of
``mdio/segy/scalar.py`` as a traceback — the crash §3.6 bars — on a value that is common in
real data.

**What the industry does, measured (DECISIONS.md D-0087).** SEG-Y rev 2.0 and 2.1 define a
zero scalar as 1; rev 1 is silent. segyio, Seismic Unix, segysak, OpenVDS and OpendTect all
read zero as 1 at every revision. The pinned MDIO alone refuses it below revision 2. SDIP
writes through MDIO's public API and does not route around it (§3.3), so the file cannot be
ingested at revision 0 or 1 today — but the operator is owed that sentence, not a stack.

The rule mirrored is MDIO's, exactly: trace 0 only; zero accepted from revision 2; any
magnitude outside 1, 10, 100, 1000, 10000 refused at every revision.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdip.errors import UntrustedInputError
from sdip.ingest import ingest
from sdip.ingest.preflight import validate_segy_structure
from tests.fixtures.generators.irregular import make_irregular

PAIRS = [(100 + i, 200 + j) for i in range(3) for j in range(4)]


def _file(
    tmp_path: Path, scalar: int, revision: int = 1, first: int | None = None
) -> tuple[Path, int]:
    scalars = None if first is None else [first] + [scalar] * (len(PAIRS) - 1)
    fixture = make_irregular(
        tmp_path / f"s{scalar}r{revision}.sgy",
        index_pairs=PAIRS,
        revision=revision,
        coordinate_scalar=scalar,
        coordinate_scalars=scalars,
    )
    return fixture.path, fixture.path.stat().st_size


@pytest.mark.parametrize("revision", [0, 1])
def test_a_zero_scalar_below_revision_2_is_refused_with_the_reason(tmp_path, revision):
    path, size = _file(tmp_path, 0, revision)
    with pytest.raises(UntrustedInputError) as caught:
        validate_segy_structure(path, size, revision=revision)
    message = str(caught.value)
    assert "bytes 71-72" in message
    assert "D27" in message
    assert "rev 2" in message


def test_a_zero_scalar_at_revision_2_is_accepted_as_mdio_accepts_it(tmp_path):
    path, size = _file(tmp_path, 0, 1)
    validate_segy_structure(path, size, revision=2)


@pytest.mark.parametrize("scalar", [5, -3, 1001])
def test_a_scalar_outside_the_standard_set_is_refused_at_every_revision(tmp_path, scalar):
    path, size = _file(tmp_path, scalar, 1)
    for revision in (1, 2):
        with pytest.raises(UntrustedInputError, match="bytes 71-72"):
            validate_segy_structure(path, size, revision=revision)


@pytest.mark.parametrize("scalar", [1, -1, 10, -100, 1000, -10000])
def test_every_standard_scalar_passes(tmp_path, scalar):
    path, size = _file(tmp_path, scalar, 1)
    validate_segy_structure(path, size, revision=1)


def test_only_the_first_trace_is_judged_because_only_it_reaches_mdio(tmp_path):
    """A zero on a later trace is not what MDIO validates; Plane 3 judges those traces."""
    path, size = _file(tmp_path, 0, 1, first=-100)
    validate_segy_structure(path, size, revision=1)


def test_ingest_refuses_before_writing_anything(tmp_path):
    path, _ = _file(tmp_path, 0, 1)
    store = tmp_path / "never.mdio"
    with pytest.raises(UntrustedInputError, match="D27"):
        ingest(path, store)
    assert not store.exists()
