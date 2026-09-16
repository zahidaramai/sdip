"""The survey declaration: how a SEG-Y is to be read, as one bound, hashable value.

**Root cause this closes (D47, DECISIONS.md D-0087).** Every SDIP command rebuilt its
reading of a source from whatever it was handed — ``--revision`` defaulting to 1, byte
order defaulting to big-endian, an override only where someone had remembered to add
the option — and nothing recorded which reading had written a store. Each new input
(the §6.4 override, its byte order) therefore reached some commands and not others, and
the ones it missed were silently wrong rather than loudly incapable:

* ``--override`` was added to 2 of the 5 commands that read a source or a store;
* the hostile-input preflight read the binary header big-endian two hours after the
  byte order became declarable, regressing D28 without a failing test;
* ``sdip verify`` on a byte-correct revision 0 store returned **FAIL** under its defaults
  and a traceback with the revision retyped. No invocation gave the right answer.

A declaration is everything that determines how the source's bytes are read into a
store: the revision whose base spec applies, the MDIO template, the survey override, and
any grid overrides. Commands take it whole, ingest records its digest in the store, and a
command handed a different declaration refuses with both named instead of producing a
verdict about a reading nobody performed (maintainer ruling, D-0087).

**The digest is not ``spec_sha256``.** That hash covers field names, byte positions and
widths — deliberately, for G6 — and is blind to field types and byte order: a big-endian
and a little-endian reading of one layout share it. The declaration digest covers every
input that changes the reading.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from sdip.provenance.hashing import sha256_bytes
from sdip.spec.generator import GapFreeSpec, build_gap_free_spec
from sdip.spec.overrides import SurveyOverride

DECLARATION_SCHEMA: Final[str] = "sdip.survey-declaration/1"
"""Versioned so a future change to what is hashed cannot collide with this one."""


def _revision_text(revision: float | int) -> str:
    """``1`` and ``1.0`` are one revision; ``2.1`` stays ``2.1``."""
    if isinstance(revision, float) and revision.is_integer():
        return str(int(revision))
    return str(revision)


@dataclass(frozen=True, slots=True)
class SurveyDeclaration:
    """How a source is read. Compared by digest, never by the path it was loaded from."""

    revision: float | int
    template: str
    override: SurveyOverride | None = None
    grid_overrides: Mapping[str, Any] | None = None

    @property
    def endianness(self) -> str | None:
        """The declared byte order, or ``None`` to inherit the revision's (big-endian)."""
        return self.override.endianness if self.override is not None else None

    def canonical(self) -> dict[str, Any]:
        """The hashed form.

        The override's ``source_path`` is excluded: the same content read from two
        locations is the same declaration, and a path in an identifier leaks the machine
        it was issued on (the D46 class). Its evidence is included: an override edited
        without a version bump is a different declaration wearing the same name.
        """
        override: dict[str, Any] | None = None
        if self.override is not None:
            override = self.override.to_json()
            override.pop("source_path", None)
        grid = dict(sorted(self.grid_overrides.items())) if self.grid_overrides else None
        return {
            "schema": DECLARATION_SCHEMA,
            "revision": _revision_text(self.revision),
            "template": self.template,
            "override": override,
            "grid_overrides": grid,
        }

    def sha256(self) -> str:
        """Digest of :meth:`canonical`, serialised with sorted keys and no whitespace."""
        payload = json.dumps(
            self.canonical(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return sha256_bytes(payload.encode("utf-8"))

    def summary(self) -> str:
        """What an operator needs in order to retype this declaration exactly."""
        override = self.override.identifier if self.override is not None else "no override"
        text = f"revision {_revision_text(self.revision)}, template {self.template}, {override}"
        if self.grid_overrides:
            text += f", grid overrides {', '.join(sorted(self.grid_overrides))}"
        return text

    def build_spec(self) -> GapFreeSpec:
        """The gap-free spec this declaration names."""
        return build_gap_free_spec(self.revision, override=self.override)

    def to_json(self) -> dict[str, Any]:
        """Certificate- and marker-shaped mapping: digest and summary, not the content."""
        return {"schema": DECLARATION_SCHEMA, "sha256": self.sha256(), "summary": self.summary()}
