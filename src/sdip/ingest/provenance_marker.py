"""The group-level marker that says **`sdip ingest` wrote this store**.

**Why a store needs to say who built it.** SDIP's Equivalence Engine runs against two
kinds of store, and until this marker existed it could not tell them apart:

1. a store **`sdip ingest` produced**, which carries SDIP's mitigations unconditionally;
2. a store **someone else produced** — upstream ``segy_to_mdio``, an older SDIP, another
   tool — which SDIP is merely inspecting.

The difference decides what *absence* means. A missing ``headers_raw_uint8`` in case 1 is
a **partially written store**: the write died between steps, or someone removed it. The
same absence in case 2 is **nothing at all** — that store was never going to have one.

**Probe P8 measured why this matters.** An ingest that died mid-write left a store
missing its mitigations, and it certified ``EQUIVALENT``. Requiring the array
unconditionally was the obvious fix and it was **wrong**: it failed seven prestack
geometries that were entirely correct, because SDIP's own ingest cannot express those
geometries at all (``OPEN_DEBTS`` D25) and their stores are built upstream. The
requirement has to be **conditional on who wrote the store**, which is what this marker
supplies. See ``DECISIONS.md`` D-0061 and D-0063 ruling 3.

**It earns its store-format change twice.** The second job is provenance for retroactive
audit: a store found on disk years from now can say which SDIP wrote it, against which
upstream pins, and therefore which certificate semantics apply. A pin bump invalidates
every certificate issued under the previous pin (§3.3), and without a marker there is no
way to tell from the store alone which side of a bump it came from.

**Group level, not array level, and that is load-bearing.** The attributes that describe
the header plane live on the header plane, so they are deleted with it — a marker that
vanishes with the thing it vouches for cannot detect the thing's absence. This one lives
on the root group and survives the deletion of every array beneath it: the same shape as
the ``coordinates`` attribute Plane 3 keys on, and for the same reason. **A claim that
outlives its content.**

Written with stock ``zarr``, never MDIO: a consumer must be able to read it with MDIO
uninstalled (§10.3, gate **G4**).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from sdip._pins import PINS

ATTR_WRITER: Final[str] = "sdipWriter"
"""Which tool wrote this store. Always the string ``sdip.ingest``."""

ATTR_VERSION: Final[str] = "sdipVersion"
"""The SDIP version that wrote it."""

ATTR_PINS: Final[str] = "sdipUpstreamPins"
"""The binding upstream pins in force at write time.

A pin bump invalidates every certificate issued under the previous pin (§3.3). Recording
the pins **in the store** is what lets a reader tell, from the artifact alone, which side
of a bump it came from.
"""

ATTR_MITIGATIONS: Final[str] = "sdipMitigations"
"""Which unconditional mitigations this writer attaches.

**Not "which arrays are present" — which arrays this writer ALWAYS writes.** The
distinction is the whole point: the completeness check compares this declaration against
what is actually on disk, and a difference is a partially written store. A list of what
is present would be a tautology.
"""

MITIGATION_HEADER_PLANE: Final[str] = "headers_raw_uint8"
"""Written unconditionally by ``sdip ingest`` (D-0051)."""


def marker_attrs(*, mitigations: tuple[str, ...] = (MITIGATION_HEADER_PLANE,)) -> dict[str, Any]:
    """The attribute mapping ``sdip ingest`` writes onto the root group."""
    from sdip import __version__

    return {
        ATTR_WRITER: "sdip.ingest",
        ATTR_VERSION: __version__,
        ATTR_PINS: {pin.distribution: pin.version for pin in PINS},
        ATTR_MITIGATIONS: list(mitigations),
    }


def attach_provenance_marker(
    store_path: str | Path, *, mitigations: tuple[str, ...] = (MITIGATION_HEADER_PLANE,)
) -> dict[str, Any]:
    """Write the marker onto the store's root group. Stock ``zarr``, no MDIO.

    Args:
        store_path: The MDIO store.
        mitigations: Which unconditional mitigations this writer attaches.

    Returns:
        The attributes written.
    """
    import zarr

    attrs = marker_attrs(mitigations=mitigations)
    zarr.open_group(str(store_path), mode="r+").attrs.update(attrs)
    return attrs


def written_by_sdip(group: Any) -> bool:
    """True when this store declares that ``sdip ingest`` wrote it.

    **False is not a failure.** A store without the marker is a store SDIP did not write,
    which is a perfectly ordinary thing for the engine to be asked to verify.
    """
    return dict(group.attrs).get(ATTR_WRITER) == "sdip.ingest"


def declared_mitigations(group: Any) -> tuple[str, ...]:
    """Mitigations the writer declared it always attaches. Empty when unmarked."""
    if not written_by_sdip(group):
        return ()
    declared = dict(group.attrs).get(ATTR_MITIGATIONS) or ()
    return tuple(str(m) for m in declared)
