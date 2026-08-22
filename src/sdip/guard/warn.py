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
"""

from __future__ import annotations

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
class SuppressionRecord:
    """A warnings filter installed during a guarded call.

    Its presence is evidence that something chose not to show a warning. SDIP cannot
    always see the warning; it can always see this.
    """

    action: str
    category: str
    message_regex: str
    known_id: str | None

    @property
    def declared(self) -> bool:
        """True when this suppression is one SDIP has read and recorded upstream."""
        return self.known_id is not None

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "action": self.action,
            "category": self.category,
            "message_regex": self.message_regex,
            "known_id": self.known_id,
            "status": "declared" if self.declared else "UNDECLARED",
        }


@dataclass(slots=True)
class WarningLedger:
    """Everything SP6 puts on a certificate for one guarded call."""

    observed: list[WarningRecord] = field(default_factory=list)
    suppressions_installed: list[SuppressionRecord] = field(default_factory=list)

    @property
    def undeclared_suppressions(self) -> list[SuppressionRecord]:
        """Suppressions SDIP has not read and recorded. Each one is a finding."""
        return [s for s in self.suppressions_installed if not s.declared]

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping for ``warnings_raised`` and its companion."""
        return {
            "observed": [w.to_json() for w in self.observed],
            "observed_count": len(self.observed),
            "suppressions_installed": [s.to_json() for s in self.suppressions_installed],
            "undeclared_suppression_count": len(self.undeclared_suppressions),
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


def suppression_regexes() -> tuple[re.Pattern[str], ...]:
    """Compiled message regexes for every known upstream suppression."""
    return tuple(re.compile(e["message_regex"]) for e in KNOWN_UPSTREAM_SUPPRESSIONS)
