"""Runtime dependency-tree licence scan. Spec sections 3.6 and 9.4.

SDIP is distributed under Apache-2.0. A copyleft entry anywhere in the *runtime*
dependency tree is a distribution defect, so CI fails the build on any GPL or AGPL
entry. Development tooling is out of scope by construction: the walk starts at
``sdip``'s own ``Requires-Dist`` and never enters ``dependency-groups``.

Two measured hazards shape the design, both recorded in ``DECISIONS.md``:

**A naive substring scan over the ``License`` metadata field is a false-positive
generator.** ``pandas`` 2.3.3 embeds its full 63,416-byte licence file in that field,
including the bundled PSF licence text, which discusses GPL compatibility at length.
Scanning it for ``"GPL"`` flags pandas - which is BSD-3-Clause. A gate that fires on
prose is a gate that gets switched off, so this scanner reads only *authoritative*
declarations and treats a long ``License`` blob as no declaration at all.

**Environment markers must be evaluated or the walk invents dependencies.** Without
marker evaluation the walk of this tree reports ``colorama``, ``importlib_metadata``,
and ``inspect2`` as missing; all three are conditional on platforms or interpreter
versions that do not apply. ``packaging`` does the evaluation and is already a hard
runtime dependency of ``dask``, ``xarray``, and ``zarr``, so declaring it adds nothing
to the tree being scanned.

Evidence tiers, highest first. The first tier that yields anything is the one used:

1. ``License-Expression`` - PEP 639 SPDX. Short, structured, authoritative.
2. ``License ::`` trove classifiers. Structured, authoritative.
3. ``License`` free-text field, **only when it is a single line of at most 200
   characters** - i.e. a licence *name*, not a licence *text*.
4. Nothing. Status ``UNDETERMINED``, which fails the scan until the distribution is
   entered in ``LICENCE_ALLOWLIST`` with cited evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.metadata import Distribution, PackageNotFoundError
from importlib.metadata import distribution as _distribution
from typing import Final

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from sdip._pins import LICENCE_ALLOWLIST

MAX_LICENCE_NAME_CHARS: Final[int] = 200
"""Above this, the ``License`` field is a licence text and carries no signal."""

_BARRED_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    # Word-boundary tokens. "LGPL" does not match "GPL" here, and "GPL-compatible"
    # is excluded explicitly - it is a statement of compatibility, not of licence.
    ("GPL", re.compile(r"(?<![A-Za-z0-9-])A?GPL(?![A-Za-z0-9])(?!-compatible)", re.I)),
    ("GNU-GPL", re.compile(r"GNU\s+(Affero\s+|Lesser\s+)?General\s+Public\s+License", re.I)),
)


@dataclass(frozen=True, slots=True)
class LicenceRecord:
    """Licence evidence for one distribution in the runtime tree."""

    distribution: str
    version: str | None
    declarations: tuple[str, ...]
    evidence_tier: str
    barred_match: str | None = None
    allowlisted: bool = False
    allowlist_reason: str | None = None

    @property
    def undetermined(self) -> bool:
        """True when no authoritative declaration was found."""
        return self.evidence_tier == "none"

    @property
    def ok(self) -> bool:
        """True when this entry does not block distribution."""
        if self.allowlisted:
            return True
        return self.barred_match is None and not self.undetermined

    def to_json(self) -> dict[str, object]:
        """Certificate-shaped mapping."""
        return {
            "distribution": self.distribution,
            "version": self.version,
            "declarations": list(self.declarations),
            "evidence_tier": self.evidence_tier,
            "barred_match": self.barred_match,
            "allowlisted": self.allowlisted,
            "allowlist_reason": self.allowlist_reason,
            "ok": self.ok,
        }


@dataclass(slots=True)
class LicenceScan:
    """Result of walking the runtime dependency tree."""

    root: str
    records: list[LicenceRecord] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def violations(self) -> list[LicenceRecord]:
        """Records that block distribution."""
        return [r for r in self.records if not r.ok]

    @property
    def ok(self) -> bool:
        """True when nothing in the runtime tree blocks distribution."""
        return not self.violations and not self.unresolved

    def to_json(self) -> dict[str, object]:
        """Certificate-shaped mapping."""
        return {
            "root": self.root,
            "scanned": len(self.records),
            "ok": self.ok,
            "unresolved": list(self.unresolved),
            "violations": [r.to_json() for r in self.violations],
        }


def _declarations(dist: Distribution) -> tuple[tuple[str, ...], str]:
    """Return ``(declarations, tier)`` using the highest tier that yields anything."""
    meta = dist.metadata

    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return (expression,), "license-expression"

    classifiers = tuple(
        c.split("::", 1)[1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    )
    if classifiers:
        return classifiers, "classifier"

    free_text = (meta.get("License") or "").strip()
    if free_text and len(free_text) <= MAX_LICENCE_NAME_CHARS and "\n" not in free_text:
        return (free_text,), "license-field"

    return (), "none"


def _barred_match(declarations: tuple[str, ...]) -> str | None:
    blob = " ; ".join(declarations)
    for label, pattern in _BARRED_PATTERNS:
        if pattern.search(blob):
            return label
    return None


def _requirements(dist: Distribution, extras: frozenset[str]) -> list[str]:
    """Direct requirements of ``dist`` whose markers hold in this environment."""
    names: list[str] = []
    contexts = [{"extra": e} for e in extras] or [{"extra": ""}]
    for raw in dist.requires or []:
        try:
            req = Requirement(raw)
        except InvalidRequirement:  # pragma: no cover - malformed upstream metadata
            continue
        if req.marker is not None and not any(req.marker.evaluate(ctx) for ctx in contexts):
            continue
        names.append(req.name)
    return names


def check_runtime_licences(root: str = "sdip", extras: frozenset[str] = frozenset()) -> LicenceScan:
    """Walk the runtime dependency tree of ``root`` and record every licence.

    Args:
        root: Distribution to start from.
        extras: Extras of ``root`` to include. Extras of transitive dependencies are
            never followed: they are not installed unless something requested them,
            in which case they appear as direct requirements of that requester.

    Returns:
        A scan whose ``ok`` property is the CI verdict.
    """
    scan = LicenceScan(root=root)
    root_canonical = canonicalize_name(root)
    allowlist = {canonicalize_name(k): v for k, v in LICENCE_ALLOWLIST.items()}
    seen: set[str] = set()
    queue: list[tuple[str, frozenset[str]]] = [(root, extras)]

    while queue:
        name, name_extras = queue.pop(0)
        canonical = canonicalize_name(name)
        if canonical in seen:
            continue
        seen.add(canonical)

        try:
            dist = _distribution(name)
        except PackageNotFoundError:
            scan.unresolved.append(name)
            continue

        if canonical != root_canonical:
            declarations, tier = _declarations(dist)
            scan.records.append(
                LicenceRecord(
                    distribution=dist.metadata["Name"] or name,
                    version=dist.version,
                    declarations=declarations,
                    evidence_tier=tier,
                    barred_match=_barred_match(declarations),
                    allowlisted=canonical in allowlist,
                    allowlist_reason=allowlist.get(canonical),
                )
            )
        queue.extend((req, frozenset()) for req in _requirements(dist, name_extras))

    scan.records.sort(key=lambda r: canonicalize_name(r.distribution))
    return scan
