r"""SP6 - no suppressed warnings.

A suppressed warning is a hidden liability transferred to the user. SDIP records
every warning it can observe, and - where a warning cannot be observed - records the
*suppression itself* so the liability appears on the certificate rather than
disappearing.

WHAT WAS MEASURED (2026-08-22, against the binding pins; see DECISIONS.md D-0004)
--------------------------------------------------------------------------------
``multidimio`` 1.2.1 suppresses two Zarr warnings in ``mdio/core/zarr_io.py``::

    @contextmanager
    def zarr_warnings_suppress_unstable_structs_v3():
        warn = r"The data type \\((.*?)\\) does not have a Zarr V3 specification\\."
        warnings.filterwarnings("ignore", message=warn,
                                category=UnstableSpecificationWarning)
        try:
            yield
        finally:
            pass          # <- the filter is NEVER restored

Two consequences, both verified by running the pinned code, not by reading it:

1. The ``ignore`` filter is inserted at the front of ``warnings.filters`` and, because
   the context manager neither uses ``warnings.catch_warnings()`` nor restores state,
   it **leaks process-globally** for the remainder of the interpreter's life. Entering
   both context managers once takes the filter list from 10 entries to 12 and leaves
   it there.
2. An outer ``catch_warnings(record=True)`` plus ``simplefilter("always")`` observes
   **zero** of the suppressed warnings, because the upstream filter is inserted after
   ours and matches first.

Therefore SP6 cannot be satisfied by re-raising, and reaching in to defeat the filter
would be monkeypatching, which spec 3.3 forbids. What this module does instead is
strictly more informative than a re-raise:

* **Observe** every warning that is not suppressed, with no deduplication, so a
  warning raised once per trace is counted once per trace.
* **Detect the suppression** by diffing ``warnings.filters`` across the guarded call.
  A filter that appears during the call is evidence that a suppression was installed,
  and it is recorded on the certificate with its action, category, and message regex.
* **Classify** each detected suppression as ``known`` - matching an entry in
  ``KNOWN_UPSTREAM_SUPPRESSIONS``, read out of the pinned source - or ``UNDECLARED``.
  An undeclared suppression appearing after a pin bump is a finding, not a surprise.
* **Restore** the filter list on exit, containing the upstream leak to the guarded
  call. SDIP does not leave the interpreter quieter than it found it.

The condition behind the known suppression is additionally detected without warnings
at all: the portability checker (G4) reads ``zarr.json`` and reports any array whose
``data_type`` is outside the Zarr v3 core specification. The warning is a signal; the
store is the evidence.

TWO BLIND SPOTS THAT ARE NOT SUPPRESSION (2026-08-22; ``OPEN_DEBTS.md`` D26)
----------------------------------------------------------------------------
Everything above concerns a warning that was raised and then silenced. There are two
ways a warning never reaches this ledger *at all*, and neither involves a filter.

**These are the worse case.** A suppression can be detected and declared, which is what
D-0004 does. An arrival that never happens leaves behind an honestly empty list that
reads exactly like a quiet run. The ledger is not lying; it is answering a question
nobody asked it.

Blind spot 1 - the warning is raised in another process
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
MDIO scans headers and reads traces in a **`spawn`** pool. A warning raised inside a
worker is raised in a different interpreter, and ``warnings.catch_warnings`` is
process-local, so **the warning object never arrives**. The same spawn context that
forces the ``__main__`` guard (spec 11.1) is what puts these warnings out of reach.

Measured end to end, not inferred, on a 30-trace fixture whose 960 sample words were all
``0x61800000`` - squarely in the float32 overflow regime:

* ``numpy`` raised ``RuntimeWarning: overflow encountered in ibm2ieee``, and the text
  reached the terminal, because a spawned child inherits the parent's ``stderr``.
* ``ledger.observed`` was ``[]``. Every stored sample was ``inf``, and the SP6 evidence
  for that loss was an empty list.
* A second warning escaped the same run from a second library - ``UserWarning: Warning:
  converting a masked element to nan``, out of ``pydantic`` while the worker built its
  ``SummaryStatistics``. Two libraries, one empty ledger. The gap is structural, not a
  property of ``ibm2ieee``.

That ingest is a permanent test - ``tests/integration/test_sp6_blindspots.py``.

**No upstream hook exists to turn those into warning objects.** Searched under the
binding pins, re-verified 2026-08-23 against the installed source, and recorded so
nobody has to search again:

* ``mdio/segy/blocked_io.py:104`` constructs its ``ProcessPoolExecutor`` inline, and the
  ``initializer`` slot is already taken by ``trace_worker_init``, hardcoded.
* ``mdio/segy/parsers.py:61`` constructs its pool with no initializer at all.
* ``segy_to_mdio`` takes a spec, a template, two paths, ``overwrite``,
  ``grid_overrides`` and ``segy_header_overrides``. None of them reaches a worker.
* ``MDIOSettings`` exposes exactly eight fields - ``cloud_native``, ``export_cpus``,
  ``grid_sparsity_ratio_limit``, ``grid_sparsity_ratio_warn``, ``ignore_checks``,
  ``import_cpus``, ``raw_headers``, ``save_segy_file_header``. Two of those are barred
  (spec 9.1) and none is a worker callback.
* The workers return fixed schemas - ``SummaryStatistics | None`` and ``HeaderArray`` -
  with nowhere to carry a warning back.

Installing a hook anyway would be monkeypatching, which spec 3.3 forbids without
exception, and no fork is authorised.

**What is recovered instead, and what is still lost.** A spawned child inherits file
descriptor 2, so the *text* is within reach even though the object is not.
:func:`recovering_worker_stderr` duplicates descriptor 2 into a pipe and runs a drain
thread that copies every byte straight back to the real descriptor - **a tee, not a
redirect** - while scanning the stream for lines in ``warnings.formatwarning``'s shape.
Measured on that same 960-word fixture: 1,129 bytes teed, **both** warnings recovered,
and the progress bar still rendering live on the terminal. Nothing is swallowed; the run
looks and sounds exactly as it did before, and the text is now also data. That is the
same discipline :func:`recording_log_records` follows for ``logging.lastResort``.

This is **text recovery, not warning capture**, and the four ways it is weaker are
stated rather than glossed:

* There is no ``Warning`` object - no arguments, no ``__cause__``, no stack. Only the
  four fields the default format prints: filename, line number, category name, message.
* **The originating process is not recoverable.** A recovered line is known *not* to
  have come from this process's ``warnings.warn``, because :func:`recording_warnings` is
  recording rather than emitting for the duration of the guarded call. Which child
  produced it is not knowable from the text.
* **It counts lines, not events.** Python's per-process ``__warningregistry__`` prints a
  given (message, category, module, lineno) once per worker under the default action, so
  960 overflowing words produced **one** line. The line proves the loss occurred; it does
  not measure how much.
* A worker's ``logger.warning`` reaches the same descriptor through
  ``logging.lastResort``, but arrives as a bare message with no
  ``file:lineno: Category:`` prefix and is indistinguishable from any other stderr text.
  Worker log records are therefore still **not** captured.

So D35 is **narrowed, not closed**. The scope block says which of the two happened in
machine-checkable booleans - ``worker_warnings_captured`` is a hardcoded ``False`` and
``worker_stderr_text_recovered`` is ``True`` only when the tee actually ran - so a
consumer tests for the gap rather than reading for it.

``PYTHONWARNINGS`` was considered and rejected, recorded so nobody re-derives it. It
*is* inherited by a spawned child, but it changes the child's *filters*, not the
*destination* - the warning still goes to the child's ``stderr`` - and
``PYTHONWARNINGS=error`` would kill the worker on any unrelated warning too, which is a
behaviour change rather than a measurement.

Blind spot 2 - the message was never a Python warning
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``logger.warning`` is a different channel, and ``catch_warnings`` cannot see it by
construction. MDIO's grid-sparsity notice, its coordinate-unit notice and its
text-header repair notice all go through ``logging``. Measured by P5: a store with 54
padding cells produced ``observed: []``.

Re-measured after the change, on that same P5 fixture. ``observed`` is still ``[]`` -
correctly, because no Python warning was ever raised - and ``logged`` now carries the
notice upstream actually emitted, verbatim: *"Ingestion grid is sparse. Sparsity ratio:
3.00. Ingestion grid: {'inline': 9, 'crossline': 9, 'time': 16}. SEG-Y trace count: 27,
grid trace count: 81."* 81 - 27 is the 54 padding cells, now stated on the certificate by
the run that made them instead of inferred from Plane 5 by a reader who thought to look.

**This one is closed outright.** :func:`recording_log_records` attaches a
``logging.Handler`` to the root logger for the duration of the guarded call and records
every record at WARNING and above. It does not touch any logger's level, so it changes
what is *recorded* and never what is *emitted* - a recorder, like the warning half, and
not a filter.

One detail is load-bearing and was nearly a defect. ``Logger.callHandlers`` falls back to
``logging.lastResort`` - which prints to ``stderr`` - **only when it finds no handler at
all** in the chain. SDIP configures no logging, and neither does MDIO, so during an
ingest the root logger is bare and upstream's warnings reach the terminal by that
fallback alone. Attaching a recorder makes ``found`` non-zero and would therefore
**silence them**: an SP6 module quietening the run it is measuring. So the handler
re-emits to ``lastResort`` whenever it was the only handler on the root logger. The run
looks and sounds exactly as it did before; the difference is that the text is now also
data.

What this half cannot see is stated rather than glossed: a record the process's logging
configuration discards is never constructed, and a recorder cannot record what was never
made. That is in :data:`LEDGER_SCOPE` beside the worker gap.

The two channels are reported **separately**: ``observed`` for ``warnings``, ``logged``
for ``logging``. Merging them would be tidier and would misreport which mechanism
produced which message - and the mechanism is the point, because one of the two is
suppressible by a filter and the other is not.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Final

KNOWN_UPSTREAM_SUPPRESSIONS: Final[tuple[dict[str, str], ...]] = (
    {
        "id": "mdio-1.2.1-unstable-structs-v3",
        "package": "multidimio",
        "version": "1.2.1",
        "site": "mdio/core/zarr_io.py:20",
        "category": "UnstableSpecificationWarning",
        "message_regex": r"The data type \((.*?)\) does not have a Zarr V3 specification\.",
        "condition": (
            "The headers array is written with data_type {'name': 'struct'}, which is "
            "not in the Zarr v3 core specification."
        ),
        "detected_independently_by": "G4 portability check, reading zarr.json",
        "probe": "P4",
        "leaks_globally": "yes - finally: pass, no catch_warnings()",
    },
    {
        "id": "mdio-1.2.1-unstable-numcodecs-v3",
        "package": "multidimio",
        "version": "1.2.1",
        "site": "mdio/core/zarr_io.py:31",
        "category": "ZarrUserWarning",
        "message_regex": "Numcodecs codecs are not in the Zarr version 3 specification",
        "condition": "A numcodecs codec was used that Zarr v3 does not specify.",
        "detected_independently_by": "G4 codec manifest read from zarr.json",
        "probe": "P4",
        "leaks_globally": "yes - finally: pass, no catch_warnings()",
    },
    {
        "id": "xarray-decode-timedelta-once",
        "package": "xarray",
        "version": "2026.7.0",
        "site": "xarray/conventions.py:371",
        "category": "FutureWarning",
        "message_regex": "decode_timedelta",
        "condition": (
            "xarray deduplicates its own decode_timedelta FutureWarning. Action is "
            "'once', not 'ignore': the first occurrence is still shown."
        ),
        "detected_independently_by": "not required - no information is lost",
        "probe": "-",
        "leaks_globally": "yes - module-scope filterwarnings, never restored",
    },
    {
        "id": "numcodecs-crc32c-deprecation-once",
        "package": "numcodecs",
        "version": "0.16.5",
        "site": "numcodecs/checksum32.py:18",
        "category": "DeprecationWarning",
        "message_regex": "crc32c usage is deprecated.*",
        "condition": (
            "numcodecs deduplicates its own crc32c deprecation notice at IMPORT time, "
            "at module scope. Action is 'once', not 'ignore'."
        ),
        "detected_independently_by": "codec manifest read from zarr.json (G4)",
        "probe": "-",
        "leaks_globally": "yes - module-scope filterwarnings, never restored",
    },
    {
        "id": "mdio-1.2.1-chunk-separation",
        "package": "multidimio",
        "version": "1.2.1",
        "site": "mdio/segy/creation.py:92",
        "category": "UserWarning",
        "message_regex": "The specified chunks separate the stored chunks along dimension",
        "condition": (
            "Export re-chunks the store. Upstream analysis: "
            "https://github.com/TGSAI/mdio-python/issues/657"
        ),
        "detected_independently_by": "chunk shape recorded on every certificate",
        "probe": "P7",
        "leaks_globally": "no - uses catch_warnings()",
    },
)
"""Suppression sites read out of the pinned upstream source, verbatim.

Recorded on every certificate so the suppression is declared rather than inherited.
A pin bump that changes this set is a maintainer decision (spec 3.3).
"""

_KNOWN_BY_PATTERN: Final[dict[str, dict[str, str]]] = {
    entry["message_regex"]: entry for entry in KNOWN_UPSTREAM_SUPPRESSIONS
}


@dataclass(frozen=True, slots=True)
class WarningRecord:
    """One observed warning, in a form that serialises onto a certificate."""

    category: str
    message: str
    filename: str
    lineno: int

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "category": self.category,
            "message": self.message,
            "filename": self.filename,
            "lineno": self.lineno,
        }


@dataclass(frozen=True, slots=True)
class LoggedRecord:
    """One log record emitted during a guarded call, at WARNING or above.

    Deliberately **not** a :class:`WarningRecord`. The two arrive by different mechanisms
    and only one of them can be silenced by a ``warnings`` filter, so flattening them
    into one list would report the wrong mechanism for half the entries - and the
    mechanism is what a reader of the certificate is trying to establish.

    The message is stored already interpolated (``record.getMessage()``): upstream logs
    with ``%s`` arguments, and holding the raw objects would put arbitrary values that do
    not serialise into a certificate.
    """

    logger: str
    level: str
    levelno: int
    message: str
    module: str

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "logger": self.logger,
            "level": self.level,
            "levelno": self.levelno,
            "message": self.message,
            "module": self.module,
        }


@dataclass(frozen=True, slots=True)
class StderrWarningRecord:
    """One warning-shaped line recovered from file descriptor 2. ``OPEN_DEBTS`` D35.

    Deliberately **not** a :class:`WarningRecord`. A :class:`WarningRecord` is a
    ``Warning`` object the ``warnings`` machinery handed over; this is four fields parsed
    out of text that something printed. It is weaker in ways a certificate reader must be
    able to see, so it is a different type in a different list:

    * the process of origin is not recoverable from the text;
    * the parsed ``category`` is a *name*, not a class - nothing was imported to check it;
    * one record means one printed line, and Python prints a given warning once per
      process under the default action, so the count is not an event count.

    What it is good for is exactly what the empty list was not: an ``ibm32`` overflow that
    destroyed every sample in a store now leaves evidence **on the certificate** instead
    of in terminal scrollback.
    """

    category: str
    message: str
    filename: str
    lineno: int

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping.

        ``channel`` and ``process`` are carried on every record rather than left to the
        scope block, because a record copied out of a certificate and pasted somewhere
        else must still say what it is.
        """
        return {
            "category": self.category,
            "message": self.message,
            "filename": self.filename,
            "lineno": self.lineno,
            "channel": "stderr-text",
            "process": "not this one - see scope.worker_stderr_attribution",
        }


SUPPRESSING_ACTIONS: Final[frozenset[str]] = frozenset({"ignore"})
"""Actions that destroy information. Only these are suppressions in SP6's sense."""

DEDUPLICATING_ACTIONS: Final[frozenset[str]] = frozenset({"once", "default", "module", "always"})
"""Actions that change how often a warning is shown, never whether it is shown at all."""


@dataclass(frozen=True, slots=True)
class SuppressionRecord:
    """A warnings filter installed during a guarded call.

    Its presence is evidence that something changed what the process will report. SDIP
    cannot always see the warning; it can always see this.

    **The action matters and is not flattened away.** ``ignore`` destroys information —
    that is a suppression, and SP6's concern. ``once`` shows the first occurrence and
    deduplicates the rest, so nothing is hidden; calling that a suppression would cry
    wolf, and a ledger that cries wolf gets ignored exactly when it matters. Both are
    recorded; only ``ignore`` counts as suppression.
    """

    action: str
    category: str
    message_regex: str
    known_id: str | None

    @property
    def declared(self) -> bool:
        """True when this filter is one SDIP has read and recorded upstream."""
        return self.known_id is not None

    @property
    def suppresses(self) -> bool:
        """True when this filter destroys information rather than deduplicating it."""
        return self.action in SUPPRESSING_ACTIONS

    @property
    def kind(self) -> str:
        """``"suppression"``, ``"deduplication"``, or ``"other"``."""
        if self.action in SUPPRESSING_ACTIONS:
            return "suppression"
        if self.action in DEDUPLICATING_ACTIONS:
            return "deduplication"
        return "other"

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "action": self.action,
            "kind": self.kind,
            "category": self.category,
            "message_regex": self.message_regex,
            "known_id": self.known_id,
            "status": "declared" if self.declared else "UNDECLARED",
        }


LEDGER_SCOPE: Final[dict[str, str]] = {
    "covers": (
        "parent-process Python warnings, parent-process log records, and warning-shaped "
        "text recovered from file descriptor 2 during the guarded call"
    ),
    "worker_process_warnings": (
        "NOT CAPTURED AS WARNING OBJECTS - text only, when "
        "worker_stderr_text_recovered is true. See OPEN_DEBTS D35."
    ),
    "worker_process_log_records": "NOT CAPTURED - see OPEN_DEBTS D35",
    "empty_observed_means": (
        "No warning arrived in this process. That is NOT evidence that none was raised. "
        "MDIO scans headers and reads traces in a spawn pool, and both "
        "warnings.catch_warnings and logging handlers are process-local, so a worker's "
        "warning goes to the child's stderr and never becomes a warning object here. "
        "Measured by P2: an ingest whose every sample overflowed to inf produced "
        "observed == []. Read stderr_recovered[] beside it, and read "
        "worker_stderr_text_recovered to know whether anything was watching at all."
    ),
    "stderr_recovered_means": (
        "A line printed to file descriptor 2, in warnings.formatwarning's shape, while "
        "the guarded call ran. It is TEXT, not a Warning object: no arguments, no cause, "
        "no stack, and the category is a parsed name rather than a class. Python prints "
        "a given warning once per process under the default action, so a record is one "
        "printed LINE and not one event - 960 overflowing sample words produced one line."
    ),
    "worker_stderr_attribution": (
        "The originating process is NOT recoverable from the text. What is known is that "
        "a recovered line did not come from this process's warnings.warn, because "
        "recording_warnings records rather than emits for the duration of the call."
    ),
    "log_records_below_effective_level": (
        "NOT CAPTURED - a record the process's logging configuration discards is never "
        "constructed, and a recorder cannot record what was never made."
    ),
    "why_workers_are_not_captured": (
        "No upstream hook reaches a worker under the binding pins. "
        "mdio/segy/blocked_io.py:104 hardcodes initializer=trace_worker_init; "
        "mdio/segy/parsers.py:61 passes no initializer; segy_to_mdio takes a spec, a "
        "template, two paths, overwrite, grid_overrides and segy_header_overrides, none "
        "of which reaches a worker; MDIOSettings exposes eight fields - cloud_native, "
        "export_cpus, grid_sparsity_ratio_limit, grid_sparsity_ratio_warn, "
        "ignore_checks, import_cpus, raw_headers, save_segy_file_header - two of them "
        "barred by spec 9.1 and none a worker callback; and the workers return "
        "HeaderArray and SummaryStatistics | None, with nowhere to carry a warning back. "
        "Installing a hook anyway would be monkeypatching, which spec 3.3 forbids "
        "without exception. The child does inherit file descriptor 2, which is why the "
        "TEXT is reachable when the object is not."
    ),
    "channels": (
        "observed[] is the warnings module; logged[] is the logging module; "
        "stderr_recovered[] is text scraped off file descriptor 2. Three lists, never "
        "merged: only the first is suppressible by a filter, and only the first two are "
        "objects the emitting library handed over rather than lines it printed."
    ),
}
"""What the ledger watched, how well, and what it still could not watch.

Serialised onto every certificate, beside a set of booleans computed per ledger by
:meth:`WarningLedger.to_json` - ``worker_warnings_captured`` (a hardcoded ``False``),
``worker_stderr_text_recovered``, ``worker_stderr_bytes_scanned``,
``worker_log_records_captured``. **The booleans are the machine-checkable part**: a
consumer asserts on them rather than parsing these sentences, and the sentences say why.

**This exists so that an empty ``observed`` stops reading as a quiet run.** SP6's promise
is that a silenced warning becomes a recorded liability; a warning raised in a spawned
worker is not silenced, it simply never arrives as an object, and the resulting empty
list looks identical to the honest one.

``worker_warnings_captured`` is a literal ``False`` rather than a computed value, and
that is deliberate: a future change that genuinely captures worker warnings as objects
must edit it by hand, in the same commit as the capability. The claim and the capability
ship together or neither does.
"""


@dataclass(slots=True)
class WarningLedger:
    """Everything SP6 puts on a certificate for one guarded call."""

    observed: list[WarningRecord] = field(default_factory=list)
    suppressions_installed: list[SuppressionRecord] = field(default_factory=list)
    logged: list[LoggedRecord] = field(default_factory=list)
    stderr_recovered: list[StderrWarningRecord] = field(default_factory=list)
    stderr_watched: bool = False
    """True only when :func:`recovering_worker_stderr` actually installed its tee.

    Distinguishes "nothing was printed" from "nobody was listening", which is the same
    distinction :data:`LEDGER_SCOPE` exists to draw for ``observed``.
    """

    stderr_bytes_scanned: int = 0
    stderr_recovery_truncated: bool = False
    """True when the recovered list hit :data:`MAX_STDERR_RECORDS` and stopped appending."""

    @property
    def suppressions(self) -> list[SuppressionRecord]:
        """Filters that destroy information. Deduplication is excluded."""
        return [s for s in self.suppressions_installed if s.suppresses]

    @property
    def undeclared_suppressions(self) -> list[SuppressionRecord]:
        """Information-destroying filters SDIP has not read and recorded.

        **Each one is a finding.** A `once` filter appearing after a pin bump is a
        change; an undeclared `ignore` is a liability nobody has looked at.
        """
        return [s for s in self.suppressions if not s.declared]

    @property
    def undeclared_filters(self) -> list[SuppressionRecord]:
        """Every new filter SDIP has not recorded, whatever its action.

        Weaker than :attr:`undeclared_suppressions` and reported separately: a new
        `once` filter after a pin bump is worth seeing without being alarming.
        """
        return [s for s in self.suppressions_installed if not s.declared]

    @property
    def scope(self) -> dict[str, Any]:
        """:data:`LEDGER_SCOPE` plus the booleans a consumer can test rather than read.

        The prose says *why*; these say *whether*. ``worker_warnings_captured`` is a
        literal ``False`` - see :data:`LEDGER_SCOPE` for why it is not computed.
        """
        return {
            **LEDGER_SCOPE,
            "worker_warnings_captured": False,
            "worker_log_records_captured": False,
            "log_records_below_effective_level_captured": False,
            "worker_stderr_text_recovered": self.stderr_watched,
            "worker_stderr_bytes_scanned": self.stderr_bytes_scanned,
            "worker_stderr_recovery_truncated": self.stderr_recovery_truncated,
        }

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping for ``warnings_raised`` and its companion."""
        return {
            "observed": [w.to_json() for w in self.observed],
            "observed_count": len(self.observed),
            "logged": [r.to_json() for r in self.logged],
            "logged_count": len(self.logged),
            "stderr_recovered": [r.to_json() for r in self.stderr_recovered],
            "stderr_recovered_count": len(self.stderr_recovered),
            "scope": self.scope,
            "suppressions_installed": [s.to_json() for s in self.suppressions_installed],
            "suppression_count": len(self.suppressions),
            "undeclared_suppression_count": len(self.undeclared_suppressions),
            "undeclared_filter_count": len(self.undeclared_filters),
            "known_upstream_suppressions": [dict(entry) for entry in KNOWN_UPSTREAM_SUPPRESSIONS],
            "sp6_scope_note": (
                "A warning suppressed by a filter installed inside a dependency cannot "
                "be re-raised without monkeypatching, which spec 3.3 forbids. The "
                "suppression itself is recorded instead, and the underlying condition "
                "is detected independently by G4."
            ),
        }


def _filter_key(entry: tuple[Any, ...]) -> tuple[str, str, str]:
    action, message, category, _module, _lineno = entry
    pattern = getattr(message, "pattern", message)
    return (
        str(action),
        getattr(category, "__name__", str(category)),
        "" if pattern is None else str(pattern),
    )


@contextmanager
def recording_warnings(
    ledger: WarningLedger | None = None, *, reemit: bool = True
) -> Iterator[WarningLedger]:
    """Record observable warnings and any suppression installed during the call.

    The warnings filter list is restored on exit, which also contains the known
    upstream leak (OPEN_DEBTS D10) to the duration of the guarded call.

    Args:
        ledger: Ledger to append to. A fresh one is created when omitted, so a caller
            can either accumulate across phases of one ingestion or take each phase
            separately.
        reemit: Re-raise every observed warning after the block, preserving its exact
            category and origin, so this is a recorder and not a swallower. Set to
            ``False`` only where the caller displays the ledger itself - a test
            asserting on the ledger, or a CLI that prints it - never to quieten a run.

    Yields:
        The ledger being written to.
    """
    result = WarningLedger() if ledger is None else ledger
    caught_messages: list[warnings.WarningMessage] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        baseline = {_filter_key(f) for f in warnings.filters}
        try:
            yield result
        finally:
            for key in (_filter_key(f) for f in warnings.filters):
                if key in baseline:
                    continue
                baseline.add(key)
                action, category, pattern = key
                known = _KNOWN_BY_PATTERN.get(pattern)
                result.suppressions_installed.append(
                    SuppressionRecord(
                        action=action,
                        category=category,
                        message_regex=pattern,
                        known_id=known["id"] if known else None,
                    )
                )
            caught_messages = list(caught)
            for w in caught_messages:
                result.observed.append(
                    WarningRecord(
                        category=w.category.__name__,
                        message=str(w.message),
                        filename=w.filename,
                        lineno=w.lineno,
                    )
                )
    if reemit:
        # ``w.message`` is the original Warning instance, so the category, args, and
        # origin are preserved exactly rather than reconstructed from a name.
        for w in caught_messages:
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)


class _RecordingHandler(logging.Handler):
    """Appends every record it is handed to a ledger, and passes it on.

    ``fallback`` is the handler that *would* have run had this one not been attached -
    ``logging.lastResort`` when the root logger was otherwise bare. Re-emitting to it is
    what keeps this a recorder rather than a filter; see the module docstring.
    """

    def __init__(
        self, ledger: WarningLedger, fallback: logging.Handler | None, *, level: int
    ) -> None:
        super().__init__(level=level)
        self._ledger = ledger
        self._fallback = fallback

    def emit(self, record: logging.LogRecord) -> None:
        """Record one log record, then re-emit it to the displaced fallback."""
        self._ledger.logged.append(
            LoggedRecord(
                logger=record.name,
                level=record.levelname,
                levelno=record.levelno,
                message=record.getMessage(),
                module=record.module,
            )
        )
        if self._fallback is not None:
            self._fallback.handle(record)


@contextmanager
def recording_log_records(
    ledger: WarningLedger | None = None, *, level: int = logging.WARNING
) -> Iterator[WarningLedger]:
    """Record what upstream *logs*, alongside what it *warns*. ``OPEN_DEBTS`` D26.

    Closes SP6's second blind spot: ``logger.warning`` is not a Python warning, and
    :func:`recording_warnings` cannot see it by construction. MDIO's grid-sparsity
    notice, its coordinate-unit notices and its text-header repair notice all take this
    route.

    No logger's level is changed, and the handler is removed and closed in a ``finally``
    - this module must not leak global state, which is exactly what it criticises
    upstream for (``OPEN_DEBTS`` D10).

    Args:
        ledger: Ledger to append to. A fresh one is created when omitted. Pass the same
            ledger given to :func:`recording_warnings` to keep both channels of one run
            together; they stay in separate lists.
        level: Minimum level to record. WARNING and above by default, because that is
            what SP6 is about. Lowering it records more; it can never record a message
            the process's logging configuration already discarded.

    Yields:
        The ledger being written to.
    """
    result = WarningLedger() if ledger is None else ledger
    root = logging.getLogger()
    # Bare root logger => upstream's warnings currently reach stderr via lastResort, and
    # attaching any handler would suppress that. Carry it, rather than silence it.
    fallback = None if root.handlers else logging.lastResort
    handler = _RecordingHandler(result, fallback, level=level)
    root.addHandler(handler)
    try:
        yield result
    finally:
        root.removeHandler(handler)
        handler.close()


WARNING_TEXT_LINE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<filename>.+?):(?P<lineno>\d+): (?P<category>\w*Warning): (?P<message>.*)$"
)
"""``warnings.formatwarning``'s first line, as text.

Conservative on purpose. Requiring a ``file:lineno: SomethingWarning:`` prefix keeps
ordinary stderr chatter - progress bars, ``logging.lastResort`` output, tracebacks - out
of the recovered list. The cost is that a warning category whose name does not end in
``Warning`` is not recognised; every builtin category does.
"""

MAX_STDERR_LINE_BYTES: Final[int] = 8192
"""Longer lines are copied through but not scanned.

Warning text can embed content derived from a file SDIP did not create (spec 3.6), so the
scanner's per-line work is bounded rather than trusting the source.
"""

MAX_STDERR_RECORDS: Final[int] = 1024
"""Ceiling on recovered records, so a hostile or pathological run cannot grow a
certificate without bound. Reaching it sets ``stderr_recovery_truncated``.

Far above the realistic count: Python's per-process registry prints a given warning once
per worker under the default action, so the true ceiling is workers x distinct sites.
"""


class _Fd2Tee:
    """Copy file descriptor 2 through a pipe, scanning for warning-shaped lines.

    Every byte read is written straight back to the original descriptor, so this is a
    **tee** and not a redirect: the terminal sees what it saw before, carriage returns
    and progress bars included. SDIP must not leave the process quieter than it found it
    - the same rule :class:`_RecordingHandler` follows for ``logging.lastResort``.

    The drain runs on a thread because a pipe holds about 64 KiB: if nobody read it, a
    chatty worker would block on ``write`` and the ingest would hang. The thread swallows
    OS errors rather than dying for the same reason - a dead drain is a deadlock.
    """

    def __init__(self, ledger: WarningLedger) -> None:
        self._ledger = ledger
        self._saved = -1
        self._read = -1
        self._write = -1
        self._thread: threading.Thread | None = None
        self._pending = bytearray()

    def _consume(self, line: bytes) -> None:
        if len(line) > MAX_STDERR_LINE_BYTES:
            return
        match = WARNING_TEXT_LINE.match(line.decode("utf-8", errors="replace").strip())
        if match is None:
            return
        if len(self._ledger.stderr_recovered) >= MAX_STDERR_RECORDS:
            self._ledger.stderr_recovery_truncated = True
            return
        self._ledger.stderr_recovered.append(
            StderrWarningRecord(
                category=match.group("category"),
                message=match.group("message"),
                filename=match.group("filename"),
                lineno=int(match.group("lineno")),
            )
        )

    def _feed(self, chunk: bytes) -> None:
        # Split on both terminators: tqdm ends its frames with \r, and a warning printed
        # immediately after one would otherwise be glued to the tail of a progress bar.
        self._pending.extend(chunk)
        while True:
            cut = min(
                (i for i in (self._pending.find(b"\n"), self._pending.find(b"\r")) if i >= 0),
                default=-1,
            )
            if cut < 0:
                break
            line = bytes(self._pending[:cut])
            del self._pending[: cut + 1]
            self._consume(line)
        if len(self._pending) > MAX_STDERR_LINE_BYTES:
            del self._pending[:-MAX_STDERR_LINE_BYTES]

    def _drain(self) -> None:
        try:
            while True:
                try:
                    chunk = os.read(self._read, 65536)
                except OSError:
                    return
                if not chunk:
                    return
                self._ledger.stderr_bytes_scanned += len(chunk)
                try:
                    os.write(self._saved, chunk)
                except OSError:
                    pass
                self._feed(chunk)
        finally:
            self._consume(bytes(self._pending))
            for fd in (self._read, self._saved):
                try:
                    os.close(fd)
                except OSError:
                    pass

    def start(self) -> bool:
        """Install the tee. Returns False if descriptor 2 could not be duplicated."""
        try:
            sys.stderr.flush()
        except (ValueError, OSError):
            pass
        try:
            self._saved = os.dup(2)
            self._read, self._write = os.pipe()
            os.dup2(self._write, 2)
        except OSError:
            for fd in (self._saved, self._read, self._write):
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            return False
        self._thread = threading.Thread(target=self._drain, name="sdip-fd2-tee", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Restore descriptor 2 and let the drain finish.

        ``_read`` and ``_saved`` are closed by the drain thread, not here: a worker that
        outlived the pool would still hold the write end, and closing a descriptor the
        thread is blocked on is how this becomes an ``EBADF`` in someone else's ingest.
        """
        try:
            sys.stderr.flush()
        except (ValueError, OSError):
            pass
        os.dup2(self._saved, 2)
        try:
            os.close(self._write)
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=10.0)


@contextmanager
def recovering_worker_stderr(ledger: WarningLedger | None = None) -> Iterator[WarningLedger]:
    """Recover warning-shaped **text** printed to descriptor 2. ``OPEN_DEBTS`` D35.

    Narrows SP6's first blind spot. A warning raised inside one of MDIO's ``spawn``
    workers cannot reach this process as an object - ``warnings.catch_warnings`` is
    process-local and no upstream hook reaches a worker under the binding pins
    (:data:`LEDGER_SCOPE`). The child does inherit descriptor 2, so the *text* is within
    reach, and this recovers it into :attr:`WarningLedger.stderr_recovered`.

    **A tee, not a capture, and not a redirect.** Every byte is copied back to the real
    descriptor unchanged, so nothing is swallowed and the live display is untouched; and
    what lands in the ledger is four parsed fields, not a ``Warning``. Both limits are
    declared on the certificate in booleans - see :data:`LEDGER_SCOPE`.

    Pair it with :func:`recording_warnings`. That one is what makes a recovered line
    attributable at all: while it is recording rather than emitting, a warning-shaped
    line on descriptor 2 did not come from this process.

    Safe to nest inside another capture: it duplicates whatever descriptor 2 currently
    is, which under ``pytest``'s ``capfd`` is already a redirect. If the duplication
    fails the block still runs, with ``stderr_watched`` left ``False`` - measurement must
    never be the reason an ingest does not happen.

    Args:
        ledger: Ledger to append to. A fresh one is created when omitted. Pass the same
            ledger given to :func:`recording_warnings` and
            :func:`recording_log_records` to keep all three channels of one run together;
            they stay in separate lists.

    Yields:
        The ledger being written to.
    """
    result = WarningLedger() if ledger is None else ledger
    tee = _Fd2Tee(result)
    if not tee.start():
        yield result
        return
    result.stderr_watched = True
    try:
        yield result
    finally:
        tee.stop()


def suppression_regexes() -> tuple[re.Pattern[str], ...]:
    """Compiled message regexes for every known upstream suppression."""
    return tuple(re.compile(e["message_regex"]) for e in KNOWN_UPSTREAM_SUPPRESSIONS)
