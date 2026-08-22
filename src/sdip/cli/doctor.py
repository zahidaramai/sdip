"""``sdip doctor`` - environment sanity. Spec sections 7.8 and 9.

Runs first in CI and first in every runbook. If doctor fails, nothing else runs.

Every check is FAIL-severity. There is no ``--force`` and no ``--allow-dirty``: the
working-tree check is the same check ``sdip certify`` enforces, and a doctor that can
be talked out of a finding is not a doctor.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from sdip._pins import BARRED_ENV_VARS, BARRED_MODULES, PINS
from sdip.cli.result import Check, Report, Status
from sdip.guard.env import check_barred_env_vars
from sdip.guard.licences import check_runtime_licences
from sdip.guard.packages import check_barred_packages
from sdip.guard.pins import check_pins
from sdip.provenance.environment import capture_environment
from sdip.provenance.git import capture_git_state

MIN_PYTHON = (3, 12)
MAX_PYTHON_EXCLUSIVE = (3, 14)

NEVER_PUBLISH = (
    "docs",
    "CLAUDE.md",
    "CLAUDE.local.md",
    "AGENTS.md",
    ".claude",
    ".claude-session-sync.md",
    ".cursor",
    ".github/copilot-instructions.md",
)
"""Paths that must never be tracked in this repository. It is published on GitHub.

``docs/`` in full. The governing specification, the internal companion, the
pre-registrations, the runbooks, and the certificate schema are maintained outside
the published repository: they exist on the working copy and are used locally, and
they are never distributed. The companion in particular carries programme names and
consumer coupling that must not appear in any external artifact.

Every AI-assistant artifact. These carry working context and internal framing that is
not part of the public product.

``.gitignore`` covers the same set, but ``git add -f`` defeats a gitignore and an
ignore rule added after a file was already tracked does nothing at all. This check
inspects **what git is actually tracking**, which is the only question that matters
before a push.
"""


def _check_python() -> Check:
    v = sys.version_info
    ok = MIN_PYTHON <= (v.major, v.minor) < MAX_PYTHON_EXCLUSIVE
    return Check(
        name="python-version",
        status=Status.PASS if ok else Status.FAIL,
        clause="pins: multidimio>=3.12,<3.15 intersect segy>=3.11,<3.14",
        summary=(
            f"Python {v.major}.{v.minor}.{v.micro} is inside the supported window"
            if ok
            else (
                f"Python {v.major}.{v.minor}.{v.micro} is outside >=3.12,<3.14; "
                "the pinned upstreams cannot both be satisfied"
            )
        ),
        evidence={
            "running": f"{v.major}.{v.minor}.{v.micro}",
            "window": ">=3.12,<3.14",
            "measured_baseline": "3.12.3 (spec Appendix A)",
        },
    )


def _check_env() -> Check:
    findings = check_barred_env_vars()
    return Check(
        name="barred-env-vars",
        status=Status.PASS if not findings else Status.FAIL,
        clause="spec 9.1",
        summary=(
            f"none of {len(BARRED_ENV_VARS)} barred variables are set"
            if not findings
            else "barred variable set: " + ", ".join(f.name for f in findings)
        ),
        evidence={
            "barred": sorted(BARRED_ENV_VARS),
            "set": [f.name for f in findings],
            "reasons": {f.name: f.reason for f in findings},
        },
    )


def _check_packages() -> Check:
    findings = check_barred_packages()
    return Check(
        name="barred-packages",
        status=Status.PASS if not findings else Status.FAIL,
        clause="spec 9.2 / SP3",
        summary=(
            f"none of {len(BARRED_MODULES)} barred modules are importable"
            if not findings
            else "barred module importable: " + ", ".join(f.module for f in findings)
        ),
        evidence={
            "barred": sorted(BARRED_MODULES),
            "importable": [f.module for f in findings],
            "origins": {f.module: f.origin for f in findings},
        },
    )


def _check_pins() -> Check:
    statuses = check_pins()
    bad = [s for s in statuses if not s.ok]
    return Check(
        name="upstream-pins",
        status=Status.PASS if not bad else Status.FAIL,
        clause="spec 3.3",
        summary=(
            f"all {len(PINS)} binding pins match" if not bad else "; ".join(s.detail for s in bad)
        ),
        evidence={
            "pins": [
                {
                    "distribution": s.distribution,
                    "expected": s.expected_version,
                    "installed": s.installed_version,
                    "declared_commit_sha": s.declared_commit_sha,
                    "commit_sha_verified": s.commit_sha_verified,
                    "ok": s.ok,
                }
                for s in statuses
            ],
            "note": (
                "Commit SHAs are declared, not runtime-verified: a wheel does not "
                "carry the SHA it was built from. Open debt D9."
            ),
        },
    )


def _check_licences() -> Check:
    scan = check_runtime_licences()
    allowlisted = [r for r in scan.records if r.allowlisted]
    return Check(
        name="runtime-licences",
        status=Status.PASS if scan.ok else Status.FAIL,
        clause="spec 3.6 / 9.4",
        summary=(
            f"{len(scan.records)} runtime distributions scanned, no GPL/AGPL entry"
            + (f", {len(allowlisted)} allowlisted with cited evidence" if allowlisted else "")
            if scan.ok
            else "blocked: "
            + ", ".join(
                [
                    f"{r.distribution} ({r.barred_match or 'undetermined licence'})"
                    for r in scan.violations
                ]
                + [f"{n} (not installed)" for n in scan.unresolved]
            )
        ),
        evidence=scan.to_json()
        | {
            "allowlisted": [
                {"distribution": r.distribution, "reason": r.allowlist_reason} for r in allowlisted
            ],
            "evidence_tiers": {
                tier: sum(1 for r in scan.records if r.evidence_tier == tier)
                for tier in ("license-expression", "classifier", "license-field", "none")
            },
        },
    )


def _check_tree(root: Path) -> Check:
    state = capture_git_state(root)
    if not state.is_repository:
        summary = f"{root} is not a git repository; provenance cannot be captured"
    elif state.dirty:
        shown = list(state.dirty_paths[:10])
        summary = (
            f"working tree is dirty ({len(state.dirty_paths)} path(s)); "
            f"sdip certify will refuse. First: {', '.join(shown)}"
        )
    else:
        summary = f"working tree clean at {state.commit[:12] if state.commit else '?'}"
    return Check(
        name="working-tree",
        status=Status.PASS if state.certifiable else Status.FAIL,
        clause="spec 11.3 - a certificate from a dirty tree is invalid",
        summary=summary,
        evidence=state.to_json(),
    )


def tracked_unpublishable(root: Path) -> list[str]:
    """Return every path git is tracking that must never be published.

    Asks git what is in the index and in ``HEAD``, not what is on disk and not what
    ``.gitignore`` says. A file added with ``git add -f``, or added before an ignore
    rule existed, is invisible to every other mechanism and is exactly the case this
    has to catch.

    Args:
        root: Repository root.

    Returns:
        Tracked paths, sorted and deduplicated. Empty means the firewall holds.
    """
    exe = shutil.which("git")
    if exe is None:  # pragma: no cover - git absent
        return []
    found: set[str] = set()
    for ref in ("--cached", "HEAD"):
        args = (
            ["ls-files", "--cached", "--", *NEVER_PUBLISH]
            if ref == "--cached"
            else ["ls-tree", "-r", "--name-only", "HEAD", "--", *NEVER_PUBLISH]
        )
        proc = subprocess.run(  # noqa: S603 - argv list, no shell, resolved executable
            [exe, *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        found.update(line for line in proc.stdout.splitlines() if line.strip())
    return sorted(found)


def _check_firewall(root: Path) -> Check:
    """Assert nothing unpublishable is tracked. This repository is public."""
    state = capture_git_state(root)
    if not state.is_repository:
        return Check(
            name="publication-firewall",
            status=Status.NOT_RUN,
            clause="publication firewall",
            summary="not a git repository; nothing is tracked",
            evidence={"never_publish": list(NEVER_PUBLISH)},
        )
    tracked = tracked_unpublishable(root)
    return Check(
        name="publication-firewall",
        status=Status.PASS if not tracked else Status.FAIL,
        clause="publication firewall - this repository is published on GitHub",
        summary=(
            f"nothing unpublishable is tracked ({len(NEVER_PUBLISH)} patterns checked, "
            "index and HEAD)"
            if not tracked
            else f"TRACKED AND WOULD BE PUBLISHED: {', '.join(tracked[:6])}"
            + (f" (+{len(tracked) - 6} more)" if len(tracked) > 6 else "")
        ),
        evidence={
            "never_publish": list(NEVER_PUBLISH),
            "tracked": tracked,
            "scope": "index and HEAD - a git rm --cached alone leaves history intact",
        },
    )


def run_doctor(root: str | Path = ".") -> Report:
    """Run every environment check and return the report.

    Args:
        root: Repository root to inspect for working-tree state.

    Returns:
        A report whose ``ok`` property is the exit verdict.
    """
    root_path = Path(root).resolve()
    report = Report(command="doctor")
    report.checks.extend(
        [
            _check_python(),
            _check_env(),
            _check_packages(),
            _check_pins(),
            _check_licences(),
            _check_tree(root_path),
            _check_firewall(root_path),
        ]
    )
    return report


def environment_block() -> dict[str, object]:
    """The environment capture doctor prints under ``--json``."""
    return capture_environment().to_json()
