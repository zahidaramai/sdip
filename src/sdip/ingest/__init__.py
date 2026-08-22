"""Thin orchestration over the MDIO converter.

Every entry point that can trigger ingestion must sit behind
``if __name__ == "__main__":``. MDIO's header parser uses a ``spawn`` context, so
without the guard the child re-executes the ingest and the pool dies with
``BrokenProcessPool`` (spec §11.1, Appendix A.5).
"""

from __future__ import annotations

from sdip.ingest.file_headers import (
    RawFileHeaders,
    attach_raw_file_headers,
    file_headers_persisted,
    read_raw_binary_from_store,
    read_raw_file_headers,
    read_raw_file_headers_from_store,
    read_raw_textual_from_store,
)
from sdip.ingest.orchestrator import (
    MIN_SEGY_BYTES,
    IngestResult,
    SpawnGuardError,
    assert_main_guarded,
    ingest,
    validate_source,
)

__all__ = [
    "MIN_SEGY_BYTES",
    "IngestResult",
    "RawFileHeaders",
    "SpawnGuardError",
    "assert_main_guarded",
    "attach_raw_file_headers",
    "file_headers_persisted",
    "ingest",
    "read_raw_binary_from_store",
    "read_raw_file_headers",
    "read_raw_file_headers_from_store",
    "read_raw_textual_from_store",
    "validate_source",
]
