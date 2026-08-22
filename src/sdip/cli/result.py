"""Check results shared by the CLI commands.

Every check states what it asserted, what it observed, and which specification
clause it came from. A check that cannot say what killed it is not a check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    """Outcome of a single check. There is no ``WARN`` - gates are binary (spec 7)."""

    PASS = "PASS"  # noqa: S105 - a gate verdict, not a credential
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


@dataclass(slots=True)
class Check:
    """One named assertion with its evidence."""

    name: str
    status: Status
    clause: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Machine-readable form."""
        return {
            "name": self.name,
            "status": self.status.value,
            "clause": self.clause,
            "summary": self.summary,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class Report:
    """A set of checks and the single verdict derived from them."""

    command: str
    checks: list[Check] = field(default_factory=list)

    @property
    def failed(self) -> list[Check]:
        """Checks that did not pass."""
        return [c for c in self.checks if c.status is Status.FAIL]

    @property
    def ok(self) -> bool:
        """True only when every check passed."""
        return not self.failed and bool(self.checks)

    def to_json(self) -> dict[str, Any]:
        """Machine-readable form, suitable for a CI artifact."""
        return {
            "command": self.command,
            "verdict": "PASS" if self.ok else "FAIL",
            "failed": [c.name for c in self.failed],
            "checks": [c.to_json() for c in self.checks],
        }
