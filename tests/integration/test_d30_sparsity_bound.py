"""D30 (probe P21): MDIO's sparsity bound, measured through the ``sdip`` executable.

Both halves (D-0088): every grid at or below ratio 10 ingests and verifies; every grid above it
is refused with one line naming ``GridTraceSparsityError``, never a traceback.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sdip._pins import UPSTREAM_SETTINGS
from tests.fixtures.generators.sparsity import LIMIT, MEMBERS, SparsityMember, build_member

pytestmark = [pytest.mark.integration]

SDIP = str(Path(sys.executable).with_name("sdip"))


def _sdip(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SDIP, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env
    )


def test_the_members_sit_where_they_were_registered():
    ratios = {m.name: round(m.ratio, 3) for m in MEMBERS}
    assert ratios == {
        "below_9_09": 9.091,
        "diag_10_00": 10.0,
        "swath_L36_w4": 9.75,
        "diag_10_08": 10.083,
        "swath_L40_w4": 10.75,
        "swath_L40_w3": 14.0,
        "diag_100": 100.0,
    }
    for member in MEMBERS:
        assert member.accepted == (member.ratio <= LIMIT), member.name


def test_both_bound_settings_are_barred():
    barred = {s.env: s.action for s in UPSTREAM_SETTINGS}
    assert "MDIO__GRID__SPARSITY_RATIO_LIMIT" in barred
    assert "MDIO__GRID__SPARSITY_RATIO_WARN" in barred


@pytest.mark.parametrize("member", [m for m in MEMBERS if m.accepted], ids=lambda m: m.name)
def test_an_accepted_grid_ingests_and_verifies(tmp_path, member: SparsityMember):
    source = build_member(member, tmp_path / f"{member.name}.sgy").path
    store = tmp_path / "store.mdio"
    ingest = _sdip("ingest", "--json", str(source), str(store))
    assert ingest.returncode == 0, ingest.stderr[-800:]
    verify = _sdip("verify", "--json", str(source), str(store))
    assert verify.returncode == 0, verify.stdout[-800:]


@pytest.mark.parametrize("member", [m for m in MEMBERS if not m.accepted], ids=lambda m: m.name)
def test_a_refused_grid_is_refused_in_one_line(tmp_path, member: SparsityMember):
    source = build_member(member, tmp_path / f"{member.name}.sgy").path
    ingest = _sdip("ingest", "--json", str(source), str(tmp_path / "store.mdio"))
    assert ingest.returncode == 1
    assert ingest.stdout == ""
    assert "Traceback" not in ingest.stderr
    last = ingest.stderr.strip().splitlines()[-1]
    # ONE line (README): MDIO's message carries its own line breaks, joined since P21.
    assert last.startswith("sdip: UpstreamRefusal: GridTraceSparsityError"), last
    assert "SEG-Y trace count" in last, "the joined line must keep upstream's whole message"
    assert sum(line.startswith("sdip: ") for line in ingest.stderr.splitlines()) == 1


def test_setting_the_limit_is_refused_before_the_file_is_read(tmp_path):
    """The only route past the bound is the barred setting, and it is closed."""
    member = next(m for m in MEMBERS if m.name == "diag_10_08")
    source = build_member(member, tmp_path / "s.sgy").path
    env = {**os.environ, "MDIO__GRID__SPARSITY_RATIO_LIMIT": "1000"}
    ingest = _sdip("ingest", str(source), str(tmp_path / "store.mdio"), env=env)
    assert ingest.returncode == 2, ingest.stderr[-600:]
    assert not (tmp_path / "store.mdio").exists()
