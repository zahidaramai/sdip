"""The D8 child names the package a refusal was raised in from a file path (P17, D-0116).

That name is the measurement behind "validated before allocating", so it must not depend on
where the repository is checked out. P17's Linux container checked it out at ``/src``, and
the first ``src`` in ``/src/src/sdip/...`` named the package ``src`` on 28 corpus members.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.negative.hostile_child import _package_of


@pytest.mark.parametrize(
    ("filename", "package"),
    [
        ("/src/src/sdip/ingest/preflight.py", "sdip"),
        ("/Users/x/seis-mdio-zarr/src/sdip/ingest/preflight.py", "sdip"),
        ("/home/x/src/seis-mdio-zarr/src/sdip/cli/main.py", "sdip"),
        ("/src/.venv/lib/python3.12/site-packages/segy/file.py", "segy"),
        ("/opt/src/venv/lib/python3.12/site-packages/mdio/ingestion/x.py", "mdio"),
        ("/var/elsewhere/module.py", "module"),
    ],
)
def test_the_package_is_read_from_the_last_anchor(filename, package):
    assert _package_of(filename) == package


def test_the_first_anchor_rule_is_the_one_p17_found_wrong():
    """NEGATIVE CONTROL: the old rule, applied to the container path, gives ``src``."""
    parts = Path("/src/src/sdip/ingest/preflight.py").parts
    assert parts[parts.index("src") + 1] == "src"
    assert _package_of("/src/src/sdip/ingest/preflight.py") == "sdip"
