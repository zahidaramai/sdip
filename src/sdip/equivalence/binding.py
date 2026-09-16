"""Is this the declaration that wrote this store? Checked before any plane runs.

**Maintainer ruling, DECISIONS.md D-0087 (from D47).** Every command that reads a store is
handed a survey declaration and builds its spec from it. The store records only the
declaration's digest, written by ingest. This module compares the two:

* ``BOUND`` — the digests match. The verdict that follows is about the reading that
  actually wrote the store.
* ``UNBOUND`` — SDIP wrote the store before binding existed, so there is no digest to
  compare. The command proceeds and says so; the certificate cannot be release-ready.
* ``FOREIGN`` — SDIP did not write the store. Nothing of SDIP's to compare against.
* mismatch — refused with :class:`~sdip.errors.DeclarationMismatchError`, naming both.

**The template is also checked against MDIO's own ``name`` attribute**, which the upstream
writer records independently of SDIP. That check applies to all three states, including
foreign stores: it is the one part of the declaration a non-SDIP writer also records.

**What this deliberately does not do: read the declaration back out of the store and use
it.** A verifier that asks the artifact under test how it should be read is not
independent of it. The ruling rejected that design for exactly that reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from sdip.errors import DeclarationMismatchError
from sdip.ingest.provenance_marker import recorded_declaration, written_by_sdip
from sdip.spec.declaration import SurveyDeclaration

BOUND: Final[str] = "BOUND"
UNBOUND: Final[str] = "UNBOUND"
FOREIGN: Final[str] = "FOREIGN"

MDIO_TEMPLATE_ATTR: Final[str] = "name"
"""The root-group attribute ``mdio`` 1.2.1 writes the template name into.

Measured, not assumed: for all 22 templates in the pinned registry the registry key an
operator passes as ``--template`` equals the template's ``name``.
"""


@dataclass(frozen=True, slots=True)
class BindingResult:
    """Outcome of comparing a supplied declaration with a store's record."""

    status: str
    supplied: SurveyDeclaration
    recorded: dict[str, Any] | None
    store_template: str | None

    @property
    def bound(self) -> bool:
        """True only when the store's recorded digest matched the supplied declaration."""
        return self.status == BOUND

    def describe(self) -> str:
        """One line for the operator."""
        if self.status == BOUND:
            digest = self.supplied.sha256()[:12]
            return f"{self.supplied.summary()} (sha256 {digest}), matches the store"
        if self.status == UNBOUND:
            return (
                f"{self.supplied.summary()} - the store predates declaration binding, so "
                "whether it was written under this declaration cannot be checked"
            )
        return (
            f"{self.supplied.summary()} - the store was not written by sdip ingest; only "
            "its template could be checked"
        )

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped ``declaration`` block."""
        return {
            **self.supplied.to_json(),
            "status": self.status,
            "recorded_sha256": (self.recorded or {}).get("sha256"),
            "store_template": self.store_template,
        }


def check_binding(store: str | Path, declaration: SurveyDeclaration) -> BindingResult:
    """Compare ``declaration`` with what ``store`` records. Refuse on any contradiction.

    Args:
        store: An MDIO store on local disk.
        declaration: The declaration the calling command was handed.

    Returns:
        The binding status, when nothing contradicts the declaration.

    Raises:
        DeclarationMismatchError: If the store's template or recorded digest disagrees
            with ``declaration``.
    """
    import zarr

    group = zarr.open_group(str(store), mode="r")
    raw_template = dict(group.attrs).get(MDIO_TEMPLATE_ATTR)
    store_template = str(raw_template) if raw_template is not None else None

    if store_template is not None and store_template != declaration.template:
        msg = (
            f"the store records template {store_template} (MDIO's own record); this "
            f"command was given {declaration.summary()}. Pass --template {store_template} "
            "and the --revision and --override used at ingest."
        )
        raise DeclarationMismatchError(msg)

    if not written_by_sdip(group):
        return BindingResult(FOREIGN, declaration, None, store_template)

    recorded = recorded_declaration(group)
    if recorded is None:
        return BindingResult(UNBOUND, declaration, None, store_template)

    if recorded.get("sha256") != declaration.sha256():
        recorded_summary = str(recorded.get("summary", "an unrecorded summary"))
        same_names = recorded_summary == declaration.summary()
        cause = (
            " The identifiers are identical, so the override's content has changed since "
            "ingest without its version being bumped."
            if same_names
            else " Pass the same --revision, --template and --override used at ingest."
        )
        msg = (
            f"the store was written under {recorded_summary} (declaration sha256 "
            f"{str(recorded.get('sha256'))[:12]}); this command was given "
            f"{declaration.summary()} (sha256 {declaration.sha256()[:12]}).{cause}"
        )
        raise DeclarationMismatchError(msg)

    return BindingResult(BOUND, declaration, recorded, store_template)
