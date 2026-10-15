"""D-0098's scoped G3 is issued for exactly one store shape, and the verdict honours it narrowly.

``header_scope`` returns a scoped result only when the ingest MEASURED the textual header
as undecodable and the store carries no ``segy_file_header``. ``verdict_for`` lets a
``ROUNDTRIP-SCOPED`` G3 reach EQUIVALENT only under that ruling, and then only on all five
planes and G7 passing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
import zarr

from sdip.equivalence.certificate import GATES, PLANE_KEYS, verdict_for
from sdip.export.roundtrip import HEADER_SCOPE_RULING, HeaderScopedRoundTrip, header_scope


@dataclass(frozen=True)
class _Decode:
    decoded: bool
    offending: tuple[tuple[int, int], ...] = ((5, 76),)
    reason: str = "1 character(s) are non-ASCII or non-printable"
    encoding: str = "ebcdic"


def _store(tmp_path: Path, *, with_file_header: bool) -> Path:
    store = tmp_path / "s.mdio"
    group = zarr.open_group(str(store), mode="w")
    if with_file_header:
        group.create_array("segy_file_header", shape=(), dtype="uint8")
    return store


def test_scoped_only_for_a_measured_failure_on_a_store_without_the_file_header(tmp_path):
    store = _store(tmp_path, with_file_header=False)
    scope = header_scope(_Decode(decoded=False), store)
    assert isinstance(scope, HeaderScopedRoundTrip)
    assert "card 6 column 77" in scope.non_conformance, "1-based, named exactly"
    block = scope.to_json()
    assert block["performed"] is False
    assert block["scoped"]["ruling"] == HEADER_SCOPE_RULING
    assert scope.passed is False


@pytest.mark.parametrize(
    ("decode", "with_file_header"),
    [(None, False), (_Decode(decoded=True), False), (_Decode(decoded=False), True)],
    ids=["unmeasured", "decoded", "file-header-present"],
)
def test_every_other_shape_goes_through_the_export(tmp_path, decode, with_file_header):
    assert header_scope(decode, _store(tmp_path, with_file_header=with_file_header)) is None


def _gates(**override: str) -> dict[str, str]:
    return dict.fromkeys(GATES, "PASS") | override


PLANES = dict.fromkeys(PLANE_KEYS, "PASS")


def test_unruled_scoped_g3_stays_provisional():
    gates = _gates(G3="ROUNDTRIP-SCOPED")
    assert verdict_for(PLANES, gates, lossy=False) == "PROVISIONAL"


def test_ruled_scoped_g3_reaches_equivalent_on_planes_and_g7():
    gates = _gates(G3="ROUNDTRIP-SCOPED")
    assert verdict_for(PLANES, gates, lossy=False, g3_scope_ruled=True) == "EQUIVALENT"


def test_ruled_scope_cannot_rescue_a_failing_plane_or_an_unrun_g7():
    gates = _gates(G3="ROUNDTRIP-SCOPED")
    failing = PLANES | {"plane_4": "FAIL"}
    assert verdict_for(failing, gates, lossy=False, g3_scope_ruled=True) == "NON-EQUIVALENT"
    unrun = _gates(G3="ROUNDTRIP-SCOPED", G7="NOT_RUN")
    assert verdict_for(PLANES, unrun, lossy=False, g3_scope_ruled=True) == "PROVISIONAL"
    assert verdict_for(PLANES, gates, lossy=True, g3_scope_ruled=True) == "NON-EQUIVALENT"
