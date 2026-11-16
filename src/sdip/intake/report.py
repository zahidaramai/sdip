"""The ``reader_report`` document of the intake contract ``geosuite.intake.v1``.

The contract is owned and published by GeoGIS (schema
``packages/contracts/geosuite.intake.v1.schema.json``); SDIP copies the rules it needs and
imports nothing from GeoGIS. ``tests/unit/test_intake_segy.py`` validates every report this
module builds against a vendored copy of that schema, pinned by sha256.

A reader **reports**; it never decides the class of an upload (that comes from the custody
record) and it never deletes anything. A ``REFUSED`` report is the custodian's signal to delete
the upload and keep only the hash-and-size :func:`refusal` document.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

SCHEMA_ID: Final[str] = "geosuite.intake.v1"

CLASSES: Final[tuple[str, ...]] = (
    "public",
    "synthetic",
    "internal",
    "confidential",
    "restricted",
    "cluster-derived",
)
DEFAULT_CLASS: Final[str] = "confidential"
"""An upload of unknown origin is confidential."""

VERDICTS: Final[tuple[str, ...]] = (
    "PASS",
    "PASS_WITH_ASSUMPTIONS",
    "NEEDS_INPUT",
    "QUARANTINE",
    "REFUSED",
)
"""Least to most severe."""

SEVERITY_VERDICT: Final[dict[str, str]] = {
    "info": "PASS",
    "assumption": "PASS_WITH_ASSUMPTIONS",
    "needs_input": "NEEDS_INPUT",
    "quarantine": "QUARANTINE",
    "refuse": "REFUSED",
}

QUESTION_CODES: Final[tuple[str, ...]] = (
    "ORIGIN_UNKNOWN",
    "CRS_UNRESOLVED",
    "UNITS_AMBIGUOUS",
    "DOMAIN_UNKNOWN",
    "DATUM_UNKNOWN",
    "WELL_MAPPING",
    "NULL_SUSPECT",
)


def finding(code: str, severity: str, message: str, field: str | None = None) -> dict[str, Any]:
    """One finding. ``message`` is for the user only and never released to a model."""
    if severity not in SEVERITY_VERDICT:
        msg = f"unknown severity {severity!r}"
        raise ValueError(msg)
    out: dict[str, Any] = {"code": code, "severity": severity, "message": message[:500]}
    if field:
        out["field"] = field[:120]
    return out


def question(
    code: str,
    prompt: str,
    choices: list[dict[str, str]],
    subject: str | None = None,
) -> dict[str, Any]:
    """One structured question with fixed choices plus "other"."""
    if code not in QUESTION_CODES:
        msg = f"unknown question code {code!r}"
        raise ValueError(msg)
    out: dict[str, Any] = {
        "code": code,
        "prompt": prompt[:300],
        "choices": choices,
        "allowOther": True,
    }
    if subject:
        out["subject"] = subject[:120]
    return out


def verdict_from(
    findings: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    assumptions: list[dict[str, Any]],
) -> str:
    """The most severe part; a question lifts it to at least NEEDS_INPUT."""
    parts = [SEVERITY_VERDICT[f["severity"]] for f in findings] + ["PASS"]
    verdict = max(parts, key=VERDICTS.index)
    if questions and VERDICTS.index(verdict) < VERDICTS.index("NEEDS_INPUT"):
        verdict = "NEEDS_INPUT"
    if verdict == "PASS" and assumptions:
        verdict = "PASS_WITH_ASSUMPTIONS"
    return verdict


def now() -> str:
    """UTC, seconds, ISO 8601."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def reader_commit() -> str:
    """The commit of the SDIP checkout this reader runs from.

    A report names the commit that produced it. Outside a git checkout there is no honest
    value, so the reader refuses to report rather than invent one.
    """
    from sdip.provenance.git import capture_git_state

    state = capture_git_state(Path(__file__).resolve().parent)
    if not state.commit:
        msg = "the intake reader runs from a git checkout of SDIP; no commit was found"
        raise RuntimeError(msg)
    return state.commit


def reader_report(
    *,
    upload_id: str,
    member: str,
    sha256: str,
    nbytes: int,
    cls: str,
    detect: dict[str, Any],
    tool: str,
    commit: str,
    structural: dict[str, Any],
    findings: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    assumptions: list[dict[str, Any]] | None = None,
    header_bytes_read: int,
    header_budget: int,
    library: dict[str, str] | None = None,
    qc_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one ``reader_report``. ``structural`` gains the sorted set of codes."""
    if cls not in CLASSES:
        msg = f"unknown class {cls!r}"
        raise ValueError(msg)
    assumptions = list(assumptions or [])
    reader: dict[str, Any] = {"repo": "SDIP", "tool": tool, "commit": commit}
    if library:
        reader["library"] = library
    codes = sorted({f["code"] for f in findings} | {q["code"] for q in questions})
    report: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "kind": "reader_report",
        "uploadId": upload_id,
        "file": {"member": member, "sha256": sha256, "bytes": nbytes},
        "class": cls,
        "detect": detect,
        "reader": reader,
        "verdict": verdict_from(findings, questions, assumptions),
        "findings": findings,
        "questions": questions,
        "assumptions": assumptions,
        "structural": dict(structural, codes=codes),
        "headerBytesRead": header_bytes_read,
        "headerBudget": header_budget,
        "at": now(),
    }
    if qc_card:
        report["qcCard"] = qc_card
    return report
