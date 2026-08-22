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
process-local, so nothing arrives. The same spawn context that forces the ``__main__``
guard (spec 11.1) is what puts these warnings out of reach.

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

That ingest is now a permanent test - ``tests/integration/test_sp6_blindspots.py`` - and
it asserts the **gap**: 960 of 960 samples ``inf`` on disk, ``observed`` empty. If the
worker leg ever starts failing, the gap has closed, and the honest response is to rewrite
:data:`LEDGER_SCOPE` rather than the assertion.

**No upstream hook exists to close it.** Searched under the binding pins, and recorded
so nobody has to search again:

* ``mdio/segy/blocked_io.py:104`` constructs its ``ProcessPoolExecutor`` inline, and the
  ``initializer`` slot is already taken by ``trace_worker_init``, hardcoded.
* ``mdio/segy/parsers.py:61`` constructs its pool with no initializer at all.
* ``segy_to_mdio`` takes a spec, a template, two paths, ``overwrite``,
  ``grid_overrides`` and ``segy_header_overrides``. None of them reaches a worker.
* ``MDIOSettings`` exposes CPU counts and thresholds. There is no worker callback.
* The workers return fixed schemas - ``SummaryStatistics | None`` and ``HeaderArray`` -
  with nowhere to carry a warning back.

Installing a hook anyway would be monkeypatching, which spec 3.3 forbids without
exception, and no fork is authorised. So SDIP does the one honest thing left: **the
ledger declares its own scope** (:data:`LEDGER_SCOPE`, serialised onto every
certificate). An empty ``observed`` stops reading as evidence of a quiet run, because
the words beside it say which processes were watched and which were not. That converts a
silent gap into a declared one. It is not capture, and it is not claimed to be.

Two routes were considered and rejected; they are recorded so nobody re-derives them.
``PYTHONWARNINGS`` *is* inherited by a spawned child, but it changes the child's
*filters*, not the *destination* - the warning still goes to the child's ``stderr`` and
never becomes data - and ``PYTHONWARNINGS=error`` would kill the worker on any unrelated
warning too, which is a behaviour change rather than a measurement. Capturing file
descriptor 2 would see the text, since the child inherits the descriptor, but it yields
unattributed lines with the progress bar interleaved and swallows the live display for
the duration of the ingest. Neither is capture. D26 stays open.

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
import re
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
    "covers": "parent-process Python warnings and parent-process log records only",
    "worker_process_warnings": "NOT CAPTURED - see OPEN_DEBTS D26",
    "worker_process_log_records": "NOT CAPTURED - see OPEN_DEBTS D26",
    "empty_observed_means": (
        "No warning arrived in this process. That is NOT evidence that none was raised. "
        "MDIO scans headers and reads traces in a spawn pool, and both "
        "warnings.catch_warnings and logging handlers are process-local, so a worker's "
        "warning goes to the child's stderr and never becomes data. Measured by P2: an "
        "ingest whose every sample overflowed to inf produced observed == []."
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
        "of which reaches a worker; MDIOSettings exposes CPU counts and thresholds but "
        "no worker callback; and the workers return HeaderArray and "
        "SummaryStatistics | None, with nowhere to carry a warning back. Installing a "
        "hook anyway would be monkeypatching, which spec 3.3 forbids without exception."
    ),
    "channels": (
        "observed[] is the warnings module; logged[] is the logging module. They are "
        "reported separately because only the first is suppressible by a filter."
    ),
}
"""What the ledger watched, and what it could not watch. Serialised onto every certificate.

**This exists so that an empty ``observed`` stops reading as a quiet run.** SP6's promise
is that a silenced warning becomes a recorded liability; a warning raised in a spawned
worker is not silenced, it simply never arrives, and the resulting empty list looks
identical to the honest one. Declaring the boundary does not capture anything and is not
claimed to. It converts a silent gap into a stated one, which is the difference between
an unknown and an unknown nobody was told about.

A future change that genuinely closes the worker gap must edit these strings, which is
deliberate: the claim and the capability are in the same commit or neither is.
"""


@dataclass(slots=True)
class WarningLedger:
    """Everything SP6 puts on a certificate for one guarded call."""

    observed: list[WarningRecord] = field(default_factory=list)
    suppressions_installed: list[SuppressionRecord] = field(default_factory=list)
    logged: list[LoggedRecord] = field(default_factory=list)

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

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping for ``warnings_raised`` and its companion."""
        return {
            "observed": [w.to_json() for w in self.observed],
            "observed_count": len(self.observed),
            "logged": [r.to_json() for r in self.logged],
            "logged_count": len(self.logged),
            "scope": dict(LEDGER_SCOPE),
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


def suppression_regexes() -> tuple[re.Pattern[str], ...]:
    """Compiled message regexes for every known upstream suppression."""
    return tuple(re.compile(e["message_regex"]) for e in KNOWN_UPSTREAM_SUPPRESSIONS)
