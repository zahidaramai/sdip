"""SP6's two blind spots, measured end to end. ``OPEN_DEBTS.md`` D26.

Every test here runs a **real ingest**. That is not thoroughness for its own sake: both
blind spots are properties of *where the code runs*, and neither is reproducible in a
single process. A unit test can prove the recorder records; only an ingest can show what
never arrives.

The two are not symmetrical, and the file is arranged to keep that visible.

**Blind spot 2 is closed.** :func:`sdip.guard.warn.recording_log_records` records what
upstream sends through ``logging``, which ``warnings.catch_warnings`` cannot see by
construction. The sparse-grid fixture is the case P5 measured as ``observed: []``, and it
now produces a record naming the ratio and the trace counts.

**Blind spot 1 is narrowed, not closed, and these tests hold both halves apart.** A
warning raised inside a spawned worker still never reaches the parent's ledger as a
``Warning`` **object**, and no upstream hook under the binding pins can change that
(:data:`sdip.guard.warn.LEDGER_SCOPE` names every site searched). What the child does
share is file descriptor 2, so the **text** is recovered:
:func:`sdip.guard.warn.recovering_worker_stderr` tees that descriptor and scrapes lines
in ``warnings.formatwarning``'s shape.

So the assertions below pin two different things about the same ingest — an ingest that
destroys every sample it was given produces an empty ``observed`` *and* a recovered
``RuntimeWarning`` line. If the ``observed`` assertion ever fails, the remaining gap has
closed — read the failure message before "fixing" anything, because the honest response
is to rewrite ``LEDGER_SCOPE`` and flip ``worker_warnings_captured``, not the test.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip.ingest import ingest
from tests.fixtures.generators import make_poststack3d
from tests.fixtures.generators.irregular import make_sparse_grid

pytestmark = pytest.mark.integration

IBM32_OVERFLOW_WORD = 0x61800000
"""0.5 x 16**33, about 2.7e39 — comfortably past float32's 3.4e38 ceiling.

Planted as raw bytes rather than written through the factory, because an IBM word that
overflows float32 **cannot be produced by encoding a float32**: the value has no float32
to be encoded from. The overflow is a decode-side event, so the word has to be put in
the file directly.
"""

SEGY_FILE_HEADER_BYTES = 3600
TRACE_HEADER_BYTES = 240


def plant_overflow_words(path: Path, n_traces: int, n_samples: int) -> int:
    """Overwrite every sample word in a SEG-Y with :data:`IBM32_OVERFLOW_WORD`.

    Args:
        path: SEG-Y to rewrite in place.
        n_traces: Trace count, used to walk the file rather than guess at it.
        n_samples: Samples per trace.

    Returns:
        Number of sample words planted.
    """
    raw = bytearray(path.read_bytes())
    word = IBM32_OVERFLOW_WORD.to_bytes(4, "big")
    planted = 0
    offset = SEGY_FILE_HEADER_BYTES
    for _ in range(n_traces):
        offset += TRACE_HEADER_BYTES
        for sample in range(n_samples):
            start = offset + 4 * sample
            raw[start : start + 4] = word
            planted += 1
        offset += 4 * n_samples
    path.write_bytes(bytes(raw))
    return planted


@pytest.fixture(scope="module")
def overflowed(tmp_path_factory) -> tuple[object, int]:
    """One ingest of a file whose every sample overflows float32. P2's leg 4."""
    root = tmp_path_factory.mktemp("sp6_overflow")
    article = make_poststack3d(root / "overflow.sgy")
    planted = plant_overflow_words(article.path, article.trace_count, article.samples_per_trace)
    result = ingest(article.path, root / "overflow.mdio")
    return result, planted


@pytest.fixture(scope="module")
def sparse(tmp_path_factory) -> object:
    """One ingest of the ratio-3.0 grid P5 measured as ``observed: []``."""
    root = tmp_path_factory.mktemp("sp6_sparse")
    article = make_sparse_grid(root / "sparse.sgy")
    return ingest(article.path, root / "sparse.mdio")


# --------------------------------------------------------------------------------------
# Blind spot 2 — closed. The logging channel reaches the ledger.
# --------------------------------------------------------------------------------------


def test_the_grid_sparsity_notice_is_recorded(sparse):
    """MEASURED. P5's case: ratio 3.0, 81 grid cells for 27 traces, 54 of them padding.

    Upstream sends this through ``logger.warning`` at ``mdio/ingestion/grid_qc.py:66``.
    Before D26 it reached the terminal and nothing else; the ledger read ``observed: []``
    and a reader had no reason to look further.
    """
    sparsity = [r for r in sparse.warnings.logged if r.logger.endswith("grid_qc")]
    assert len(sparsity) == 1, [r.logger for r in sparse.warnings.logged]

    record = sparsity[0]
    assert record.level == "WARNING"
    assert "Ingestion grid is sparse" in record.message
    assert "SEG-Y trace count: 27, grid trace count: 81" in record.message


def test_the_warnings_channel_is_still_empty_for_that_store(sparse):
    """The point of recording the two channels separately.

    The sparsity notice was **never a Python warning**, so an empty ``observed`` is the
    correct answer from the warnings half and always was. What was wrong was reading it
    as "nothing happened". Both facts now sit on the certificate at once.
    """
    assert sparse.warnings.observed == []
    assert sparse.warnings.logged != []


def test_a_log_record_never_lands_in_the_warnings_list(sparse, overflowed):
    """Cross-channel contamination would misreport which mechanism produced what."""
    result, _ = overflowed
    for ledger in (sparse.warnings, result.warnings):
        payload = ledger.to_json()
        assert payload["observed_count"] == len(ledger.observed)
        assert payload["logged_count"] == len(ledger.logged)
        assert {r.message for r in ledger.logged}.isdisjoint({w.message for w in ledger.observed})


# --------------------------------------------------------------------------------------
# Blind spot 1 — open. The loss is total and the warnings ledger is empty.
# --------------------------------------------------------------------------------------


def test_every_sample_was_destroyed(overflowed):
    """SP11. Establishes that the empty ledger below is worth worrying about.

    Without this, "``observed`` is empty" is just a quiet run. With it, the store on disk
    holds 960 infinities where 960 finite IBM words were read, and the SP6 evidence for
    that is an empty list.
    """
    result, planted = overflowed
    assert planted == 960

    group = zarr.open_group(result.output_path, mode="r")
    amplitude = np.asarray(group["amplitude"][:])
    assert amplitude.size == planted
    assert int(np.isinf(amplitude).sum()) == planted
    assert int(np.isfinite(amplitude).sum()) == 0


def test_the_worker_warning_does_not_reach_the_ledger_as_an_object(overflowed):
    """MEASURED, D35. This asserts a **gap**, deliberately, and it is still open.

    ``numpy`` raises ``RuntimeWarning: overflow encountered in ibm2ieee`` while decoding
    those words, inside a ``spawn`` worker. No ``Warning`` object crosses the process
    boundary, and no public upstream seam under the binding pins can make one — see
    :data:`sdip.guard.warn.LEDGER_SCOPE`, which names every site searched.

    The *text* is recovered now (below). This is the stronger thing that is still
    missing. If this fails, worker warnings are being captured as objects and D35 has
    closed outright: rewrite ``LEDGER_SCOPE``, flip ``worker_warnings_captured``, and
    fix this test in the same commit — do not relax any one of the three.
    """
    result, _ = overflowed
    assert [w for w in result.warnings.observed if "ibm2ieee" in w.message] == [], (
        "a worker warning reached the parent ledger as an object — D35 has closed; "
        "LEDGER_SCOPE and worker_warnings_captured now understate the coverage"
    )


def test_the_worker_warning_text_is_recovered_from_the_descriptor(overflowed):
    """MEASURED, D35's narrowing. The loss now leaves evidence on the certificate.

    This is the exact case that made the debt serious: 960 of 960 samples destroyed, and
    the SP6 evidence for it was an empty list. The recovered line is text a child
    printed, not a warning object — but it is on the artifact, where before there was
    nothing.

    Both libraries are asserted on purpose. The gap was never a property of
    ``ibm2ieee``; a second warning escaped the same run out of ``pydantic``, and a
    recovery that only found the one everybody knew about would prove less than it looks.
    """
    result, _ = overflowed
    ledger = result.warnings

    assert ledger.stderr_watched is True
    assert ledger.stderr_bytes_scanned > 0

    messages = [r.message for r in ledger.stderr_recovered]
    overflow = [r for r in ledger.stderr_recovered if "ibm2ieee" in r.message]
    assert len(overflow) == 1, messages
    assert overflow[0].category == "RuntimeWarning"
    assert [r for r in ledger.stderr_recovered if "masked element to nan" in r.message], messages


def test_a_recovered_line_never_lands_in_the_warnings_list(overflowed, sparse):
    """Three channels, three lists. The mechanism is what a reader is establishing.

    A recovered line is weaker evidence than an observed warning — no object, no
    process attribution, one line per process rather than one per event. Folding it into
    ``observed`` would launder text into something it is not.
    """
    result, _ = overflowed
    for ledger in (result.warnings, sparse.warnings):
        recovered = {r.message for r in ledger.stderr_recovered}
        assert recovered.isdisjoint({w.message for w in ledger.observed})
        assert recovered.isdisjoint({r.message for r in ledger.logged})


def test_the_certificate_declares_the_gap_in_booleans(overflowed):
    """D35's narrowing, on the artifact: the gap is machine-checkable, not prose.

    A consumer must be able to **test** for what was not watched instead of reading for
    it. ``worker_warnings_captured`` is what SP6 would need; ``worker_stderr_text_``
    ``recovered`` is the weaker thing that was actually built. Both sit beside the count.
    """
    result, _ = overflowed
    payload = result.to_json()["warnings"]
    scope = payload["scope"]

    assert scope["worker_warnings_captured"] is False
    assert scope["worker_stderr_text_recovered"] is True
    assert scope["worker_stderr_bytes_scanned"] > 0
    assert scope["worker_log_records_captured"] is False
    assert payload["stderr_recovered_count"] == len(result.warnings.stderr_recovered)
    assert "file descriptor 2" in scope["covers"]
    assert "P2" in scope["empty_observed_means"]
