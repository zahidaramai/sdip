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
from sdip.ingest.header_plane import (
    ARRAY_NAME as HEADER_PLANE_ARRAY_NAME,
)
from sdip.ingest.header_plane import (
    HeaderPlane,
    attach_header_plane,
    open_header_plane,
    read_source_header_bytes,
)
from sdip.ingest.orchestrator import (
    MIN_SEGY_BYTES,
    IngestResult,
    SpawnGuardError,
    assert_main_guarded,
    ingest,
    validate_source,
)
from sdip.ingest.raw_samples import (
    ARRAY_NAME as RAW_SAMPLE_ARRAY_NAME,
)
from sdip.ingest.raw_samples import (
    RawSampleView,
    attach_raw_sample_view,
    open_raw_sample_view,
    read_source_words,
)

__all__ = [
    "HEADER_PLANE_ARRAY_NAME",
    "MIN_SEGY_BYTES",
    "RAW_SAMPLE_ARRAY_NAME",
    "HeaderPlane",
    "IngestResult",
    "RawFileHeaders",
    "RawSampleView",
    "SpawnGuardError",
    "assert_main_guarded",
    "attach_header_plane",
    "attach_raw_file_headers",
    "attach_raw_sample_view",
    "file_headers_persisted",
    "ingest",
    "open_header_plane",
    "open_raw_sample_view",
    "read_raw_binary_from_store",
    "read_raw_file_headers",
    "read_raw_file_headers_from_store",
    "read_raw_textual_from_store",
    "read_source_header_bytes",
    "read_source_words",
    "validate_source",
]
