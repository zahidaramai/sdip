"""D58: zarr's and dask's configuration, from ANY channel, is classified before a run reads a byte.

**Measured (DECISIONS.md D-0088).** zarr and dask are configured through donfig, which reads
``ZARR_*`` / ``DASK_*`` environment variables *and* YAML or JSON files (``/etc/<name>``,
``~/.config/<name>``, ``<NAME>_CONFIG``, ``<NAME>_ROOT_CONFIG``). ``ZARR_DEFAULT_ZARR_FORMAT=2``
made MDIO write a Zarr **v2** store; codec entries map a codec NAME on a store to whatever
implementation class the configuration names. A list of variable names cannot see a file, so
the guard compares each library's **effective configuration with its shipped defaults** — the
channel does not matter, the deviation does. In a clean run there are 0 deviations in zarr's
48 keys and dask's 30, measured after importing everything a run imports.

These run in a fresh interpreter each time, because donfig reads configuration at import.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = """
import json, sys
from sdip.guard.library_config import deviations, refusals, recorded_library_config
out = {"refusals": [r["key"] for r in refusals()], "recorded": recorded_library_config()}
print(json.dumps(out))
"""


def _probe(home: Path, extra_env: dict[str, str]) -> dict:
    """Run the guard in a fresh interpreter with a clean ZARR_/DASK_ environment and HOME."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ZARR_", "DASK_"))}
    env |= {"HOME": str(home)} | extra_env
    proc = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, env=env, check=True
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_a_clean_environment_has_nothing_to_refuse_or_record(tmp_path):
    result = _probe(tmp_path, {})
    assert result == {"refusals": [], "recorded": {}}


@pytest.mark.parametrize(
    ("variable", "value", "key"),
    [
        ("ZARR_DEFAULT_ZARR_FORMAT", "2", "default_zarr_format"),
        ("ZARR_CODECS__ZSTD", "zarr.codecs.gzip.GzipCodec", "codecs.zstd"),
        ("ZARR_CODEC_PIPELINE__PATH", "some.other.Pipeline", "codec_pipeline.path"),
        ("ZARR_ARRAY__WRITE_EMPTY_CHUNKS", "True", "array.write_empty_chunks"),
        ("ZARR_SOMETHING_NEW", "1", "something_new"),
    ],
)
def test_a_zarr_setting_that_can_change_a_store_is_refused(tmp_path, variable, value, key):
    result = _probe(tmp_path, {variable: value})
    assert key in result["refusals"], result


def test_a_config_file_is_caught_as_surely_as_a_variable(tmp_path):
    """The channel a list of variable names cannot see."""
    config = tmp_path / "zarr.yaml"
    config.write_text("default_zarr_format: 2\n")
    result = _probe(tmp_path, {"ZARR_CONFIG": str(config)})
    assert "default_zarr_format" in result["refusals"], result


@pytest.mark.parametrize(
    ("variable", "value", "key"),
    [
        ("ZARR_ASYNC__CONCURRENCY", "1", "zarr:async.concurrency"),
        ("ZARR_THREADING__MAX_WORKERS", "1", "zarr:threading.max_workers"),
        ("DASK_ARRAY__CHUNK_SIZE", "'1KiB'", "dask:array.chunk-size"),
        ("DASK_SCHEDULER", "'synchronous'", "dask:scheduler"),
    ],
)
def test_resource_settings_are_recorded_not_refused(tmp_path, variable, value, key):
    result = _probe(tmp_path, {variable: value})
    assert result["refusals"] == [], result
    assert key in result["recorded"], result


def test_every_zarr_default_key_is_classified():
    """Drift, fail closed: a zarr upgrade that adds a setting fails here until it is ruled on."""
    from sdip.guard.library_config import classification_gaps

    assert classification_gaps() == []
