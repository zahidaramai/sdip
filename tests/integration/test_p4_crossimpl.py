"""Probe **P4** — cross-implementation portability. Pre-registration ``prereg/P4-portability.md``.

Gate **G4** proves an SDIP store opens with stock ``zarr`` and stock ``xarray`` in a
process that never imports ``mdio``. That is a real result, and it is a result *inside
Python*. §10.3 makes a broader promise — adopting SDIP is reversible because the data is
already in an open format — and a promise that only holds for one language ecosystem is
narrower than the one being made. Whether it holds outside Python is open debt **D3**,
and this module is the measurement that closes it.

What is actually at risk
------------------------
Eight of the ten arrays carry Zarr v3 **core-spec** ``data_type`` values (``float32``,
``uint32``, ``int32``, ``int8``, ``float64``). Nothing can go wrong there that is SDIP's
fault: a reader that fails on ``float32`` has a bug, and the pre-registration says so —
**a non-Python implementation failing on a core-spec array is not a falsifier.** The
probe tests SDIP's output, not other people's readers.

Two arrays carry **extension** ``data_type`` values with no Zarr v3 specification behind
them:

- ``headers`` — ``{"name": "struct"}``, the 240-byte trace header as 97 named fields.
- ``segy_file_header`` — ``{"name": "fixed_length_utf32"}``.

The pre-registered falsifier is **"headers unreadable outside Python"**, and it is
``headers`` that carries the data. So the question this module answers is narrow and
sharp: does a Zarr implementation that shares no code with ``zarr-python`` get the same
bytes out of the structured array?

Why TensorStore
---------------
The pre-registration names zarr-java, zarr-rs and TensorStore. TensorStore is a C++
implementation with Python bindings: the bindings are a thin shim over a compiled
extension, and the ``zarr.json`` parsing, chunk decoding and codec pipeline are all C++
that shares nothing with ``zarr-python``. Importing it from pytest is a convenience of
packaging, not a shortcut in the measurement, and
:func:`test_the_reader_under_test_is_a_compiled_non_python_implementation` pins that —
**SP11**: a probe that quietly re-ran ``zarr-python`` would measure nothing.

zarr-java needs a JVM and zarr-rs needs a Rust toolchain; CI has no network beyond the
pinned package index, so neither can be fetched. They stay unmeasured, and the Results
section of the pre-registration says so rather than implying coverage this module does
not have.

Comparison discipline
---------------------
Every comparison here is :func:`numpy.array_equal` **and** equality of the raw buffers
via ``ndarray.tobytes()``. Byte equality is the stricter of the two — it separates NaN
payloads and it fails on a dtype that merely compares equal — and it is what the
pre-registration registered. There is no tolerance anywhere, and there is no room for
one: a cross-implementation read that is *nearly* right is a corrupted read.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr

from sdip.ingest import ingest
from sdip.ingest.file_headers import (
    ATTR_RAW_BINARY,
    ATTR_RAW_BINARY_SHA,
    ATTR_RAW_TEXT,
    ATTR_RAW_TEXT_SHA,
)
from tests.fixtures.generators import PLANTED_BYTES, SyntheticSegy, make_poststack3d

pytestmark = pytest.mark.integration

ts = pytest.importorskip(
    "tensorstore",
    reason=(
        "P4 needs a non-zarr-python Zarr implementation. Without one the probe is "
        "unmeasured, not passing - see prereg/P4-portability.md."
    ),
)

CORE_SPEC_ARRAYS: tuple[str, ...] = (
    "amplitude",
    "amplitude_raw_ibm32",
    "inline",
    "crossline",
    "time",
    "trace_mask",
    "cdp_x",
    "cdp_y",
)
"""Arrays whose ``data_type`` is in the Zarr v3 core specification.

A failure on any of these is a bug in the reader, reported upstream, **not** a finding
against SDIP. They are checked anyway: the pre-registered success criterion is that
every core-spec array reads bit-identically, and an unchecked criterion is not a
criterion.

``amplitude_raw_ibm32`` is **conditional**: :mod:`sdip.ingest.raw_samples` writes it only
when the source's sample format is ``ibm32``, which the Appendix A.1 article is. It is
listed here rather than special-cased because its ``data_type`` is the plain string
``uint32`` — core-spec, so it changes the count and nothing else. If the fixture's sample
format ever changes, the array disappears and
:func:`test_the_store_is_the_one_the_probe_registered` is what says so.
"""

EXTENSION_ARRAYS: tuple[str, ...] = ("headers", "segy_file_header")
"""Arrays whose ``data_type`` is an extension with no Zarr v3 specification."""

EXPECTED_HEADER_FIELDS = 97
"""The gap-free spec's field count. Anything else means the store is not what G1 built."""


@pytest.fixture(scope="module")
def article_and_store(tmp_path_factory: pytest.TempPathFactory) -> tuple[SyntheticSegy, Path]:
    """One real ingest of the Appendix A.1 article, reused across the module.

    The SEG-Y is returned alongside the store because the strongest comparison available
    here does not go through ``zarr-python`` at all: it runs the non-Python read back
    against the ground truth the generator planted into the source file.
    """
    root = tmp_path_factory.mktemp("p4")
    article = make_poststack3d(root / "src.sgy")
    ingest(article.path, root / "out.mdio")
    return article, root / "out.mdio"


def _open_with_tensorstore(store: Path, name: str, *, field: str | None = None) -> Any:
    """Open one array through TensorStore's ``zarr3`` driver.

    Args:
        store: The MDIO store root.
        name: Array name within the store.
        field: For a ``struct`` ``data_type``, the single field to project. TensorStore
            models a structured array as a set of separately addressable fields and
            refuses to open one without a selection.

    Returns:
        An open TensorStore handle.
    """
    spec: dict[str, Any] = {
        "driver": "zarr3",
        "kvstore": {"driver": "file", "path": str(store / name)},
    }
    if field is not None:
        spec["field"] = field
    return ts.open(spec, open=True, read=True).result()


def _read_with_tensorstore(store: Path, name: str, *, field: str | None = None) -> np.ndarray:
    """Read one array (or one field of one array) through TensorStore into numpy."""
    return np.asarray(_open_with_tensorstore(store, name, field=field).read().result())


def _identical(left: np.ndarray, right: np.ndarray) -> bool:
    """True only when two arrays are the same values *and* the same raw bytes.

    Two checks rather than one because each catches what the other misses.
    :func:`numpy.array_equal` compares values but ignores dtype, so an ``int32`` read
    back as ``int64`` would satisfy it. ``tobytes()`` compares the buffers, which is the
    pre-registered criterion and the one that survives NaN payloads.

    **No tolerance, and none is possible here.** The whole claim under test is that the
    bytes crossed the implementation boundary unchanged.
    """
    return (
        left.dtype == right.dtype
        and left.shape == right.shape
        and bool(np.array_equal(left, right))
        and left.tobytes() == right.tobytes()
    )


def test_the_reader_under_test_is_a_compiled_non_python_implementation():
    """SP11 non-vacuity. A probe that re-ran ``zarr-python`` would measure nothing.

    TensorStore's Python package is a shim; the implementation is a compiled extension.
    If that ever stopped being true — a pure-Python fallback, a vendored ``zarr-python``
    — every result in this module would silently become a restatement of G4, and the
    Results section of the pre-registration would be reporting coverage it does not have.
    """
    core = pytest.importorskip("tensorstore._tensorstore")
    assert Path(core.__file__).suffix in {".so", ".pyd", ".dylib"}


def test_the_store_is_the_one_the_probe_registered(article_and_store):
    """Guards the fixture, not the reader: a changed store makes the table below a lie."""
    _, store = article_and_store
    group = zarr.open_group(str(store), mode="r")
    names = sorted(name for name, _ in group.arrays())
    assert names == sorted(CORE_SPEC_ARRAYS + EXTENSION_ARRAYS)
    assert len(group["headers"].dtype.names) == EXPECTED_HEADER_FIELDS


def test_the_extension_arrays_are_the_only_non_core_ones(article_and_store):
    """Reads the risk straight out of ``zarr.json``, which is where the evidence is.

    A ``data_type`` that is a JSON string is a core-spec name; one that is an object is
    an extension. No warning from anybody is needed to establish this (``DECISIONS.md``
    D-0004): the store is the evidence.
    """
    _, store = article_and_store
    extensions = []
    for name in CORE_SPEC_ARRAYS + EXTENSION_ARRAYS:
        data_type = json.loads((store / name / "zarr.json").read_text())["data_type"]
        if not isinstance(data_type, str):
            extensions.append(name)
    assert sorted(extensions) == sorted(EXTENSION_ARRAYS)


@pytest.mark.parametrize("name", CORE_SPEC_ARRAYS)
def test_core_spec_arrays_cross_the_boundary_byte_identically(article_and_store, name):
    """The pre-registered success criterion, array by array.

    Failure here would be a TensorStore bug to report upstream rather than a finding
    against SDIP — the pre-registration is explicit that a core-spec array is not the
    falsifier. It is still measured, because "everything except the headers is portable"
    is a claim, and claims get numbers.
    """
    _, store = article_and_store
    group = zarr.open_group(str(store), mode="r")
    assert _identical(_read_with_tensorstore(store, name), np.asarray(group[name][...]))


def test_the_structured_headers_array_will_not_open_without_a_field_selector(article_and_store):
    """Records the exact operation that fails, which is the method the probe registered.

    This is **not** the falsifier firing. TensorStore models a ``struct`` ``data_type``
    as a set of separately addressable fields and declines to guess which one is wanted;
    the error enumerates all 97 by name, which means the metadata parsed and the fields
    were understood. A reader that could not comprehend the dtype could not list it.
    """
    _, store = article_and_store
    with pytest.raises(ValueError) as raised:
        _open_with_tensorstore(store, "headers")
    message = str(raised.value)
    assert "Must specify a" in message
    assert "field" in message
    assert "trace_seq_num_line" in message


def test_every_header_field_crosses_the_boundary_byte_identically(article_and_store):
    """**The falsifier's own test.** All 97 fields, read by C++, compared byte-for-byte.

    Field-at-a-time is TensorStore's access model, not a workaround: the whole record is
    reachable, one projection per field. What matters for §10.3 is whether the bytes are
    recoverable outside Python, and the answer is measured here rather than assumed.
    """
    _, store = article_and_store
    group = zarr.open_group(str(store), mode="r")
    python_read = group["headers"][...]
    fields = list(python_read.dtype.names)
    assert len(fields) == EXPECTED_HEADER_FIELDS

    mismatched = [
        field
        for field in fields
        if not _identical(
            _read_with_tensorstore(store, "headers", field=field),
            np.ascontiguousarray(python_read[field]),
        )
    ]
    assert mismatched == []


def test_the_planted_tail_bytes_survive_the_crossing(article_and_store):
    """Ties the non-Python read back to the **source file**, not to ``zarr-python``.

    Bytes 233-240 are uncovered by the rev 1 standard, which is exactly why the generator
    plants distinct seeded values there: they are what a sparse spec silently drops. A
    C++ reader recovering them from the store, and matching what was written into the
    SEG-Y, is evidence rather than two Python readers agreeing with each other.
    """
    article, store = article_and_store
    group = zarr.open_group(str(store), mode="r")
    mask = np.asarray(group["trace_mask"][...]).astype(bool)

    for position, column in enumerate(PLANTED_BYTES):
        crossed = _read_with_tensorstore(store, "headers", field=f"pad_{column}")
        assert crossed.dtype == np.uint8
        expected = article.planted[:, position].reshape(mask.shape)
        assert _identical(crossed[mask], expected[mask])


def test_the_file_header_array_will_not_open_at_all(article_and_store):
    """``fixed_length_utf32`` is an extension TensorStore does not implement.

    Recorded as measured, with the operation and the error, because the pre-registration
    asks for exactly that. The next test establishes what it costs a consumer.
    """
    _, store = article_and_store
    with pytest.raises(ValueError) as raised:
        _open_with_tensorstore(store, "segy_file_header")
    message = str(raised.value)
    assert "fixed_length_utf32" in message
    assert "not one of the supported data types" in message


def test_the_file_header_array_carries_no_payload_to_lose(article_and_store):
    """Why the failure above costs nothing: the array data is an empty scalar string.

    MDIO's parsed view and SDIP's authoritative raw bytes both live in the node's
    **attributes**, not in its chunks. So the unreadable dtype guards an empty box.
    """
    _, store = article_and_store
    group = zarr.open_group(str(store), mode="r")
    node = group["segy_file_header"]
    assert node.shape == ()
    assert str(node[()]) == ""


def test_the_raw_file_headers_are_reachable_without_zarr_python(article_and_store):
    """Planes 1 and 2 recover fully outside Python, through TensorStore's own key-value store.

    ``segy_file_header``'s array driver is closed to TensorStore, but the bytes §4.3 calls
    authoritative are base64 in ``zarr.json`` — JSON, which every language already reads.
    They are pulled here through ``ts.KvStore`` rather than through a Python file read, so
    the claim is that *TensorStore* reaches them, not merely that a JSON file exists.

    Both hashes are verified. The store records what it claims the bytes are; an
    unverified recovery would be a decode, not a measurement (**SP8**).
    """
    article, store = article_and_store
    kvstore = ts.KvStore.open({"driver": "file", "path": str(store) + "/"}).result()
    attributes = json.loads(kvstore.read("segy_file_header/zarr.json").result().value)["attributes"]

    textual = base64.b64decode(attributes[ATTR_RAW_TEXT])
    binary = base64.b64decode(attributes[ATTR_RAW_BINARY])

    assert textual == article.textual_header
    assert binary == article.binary_header
    assert hashlib.sha256(textual).hexdigest() == attributes[ATTR_RAW_TEXT_SHA]
    assert hashlib.sha256(binary).hexdigest() == attributes[ATTR_RAW_BINARY_SHA]


def test_a_changed_header_field_is_visible_to_the_non_python_reader(article_and_store, tmp_path):
    """NEGATIVE CONTROL (§5). A comparison that cannot fail is not a comparison.

    Every assertion above has the shape "the two reads agree". That shape is satisfied
    by several ways of being wrong: TensorStore quietly delegating to ``zarr-python``,
    :func:`_identical` being vacuous, or the reader returning zeros for a field that
    happens to be zero in the fixture — and most of the 97 SEG-Y header fields *are*
    zero here. So the control changes one field in a copy of the store, through
    ``zarr-python`` so the chunk is legitimately re-encoded rather than corrupted, and
    demands that the C++ reader sees the change.

    It must fail for **that** field and pass for its neighbour: a control that fires on
    everything localises nothing (§7 G7's killer, ``DECISIONS.md`` D-0028).
    """
    _, store = article_and_store
    changed_field, untouched_field = "trace_seq_num_line", "crossline"

    mutated = tmp_path / "mutated.mdio"
    shutil.copytree(store, mutated)
    group = zarr.open_group(str(mutated), mode="r+")
    block = group["headers"][...]
    block[changed_field][0, 0] = np.int32(-424242)
    group["headers"][...] = block

    assert not _identical(
        _read_with_tensorstore(mutated, "headers", field=changed_field),
        _read_with_tensorstore(store, "headers", field=changed_field),
    )
    assert _identical(
        _read_with_tensorstore(mutated, "headers", field=untouched_field),
        _read_with_tensorstore(store, "headers", field=untouched_field),
    )
