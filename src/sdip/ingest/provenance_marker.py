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
from typing import TYPE_CHECKING, Any, Final

from sdip._pins import PINS

if TYPE_CHECKING:
    from sdip.spec.declaration import SurveyDeclaration

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

ATTR_DECLARATION: Final[str] = "sdipDeclaration"
"""Digest and summary of the survey declaration this store was written under (D-0087).

**The digest, not the declaration.** A command that reads this store is handed its own
declaration and builds its spec from that; this attribute only lets it detect that it was
handed a different one. Reading the store's interpretation back out of the store and
verifying the store against it would be circular — the artifact under test vouching for
how it should be read — and was ruled out for that reason.
"""

ATTR_STORE_DIGEST: Final[str] = "sdipStoreDigest"
"""Digest of everything else in the store, taken when the write finished (D-0093).

Computed by :func:`attach_provenance_marker` immediately before the marker is written, over
every node and the root metadata less the marker's own keys
(:mod:`sdip.provenance.store_digest`). ``verify`` recomputes it: a store changed after
ingest finished fails, a store that predates the digest is ``ABSENT`` and says so.
"""

ATTR_SAMPLE_AXIS_ORIGIN: Final[str] = "sdipSampleAxisOrigin"
"""Present only when this writer moved the ``time`` axis to the recording delay (D-0096).

Says which convention the writer followed, never the value Plane 4 checks against: Plane 4
derives the delay from the source itself (:mod:`sdip.ingest.sample_axis`).
"""

CONTENT_DIGEST_FIELD: Final[str] = "content"
"""Where the content digest lives: **inside** ``sdipStoreDigest``, not as a root attribute.

D-0101, scheme ``sdip-content-digest/1``: the store digest less per-ingest metadata, so two
ingests of one source under one declaration give the same value. **Nested deliberately.** A
verifier excludes exactly the marker keys IT knows from the root metadata it digests; a new root
attribute would be digested by every older verifier and read as a changed store. Every SDIP
since 1.3.0 excludes ``sdipStoreDigest`` and compares only its ``scheme`` and ``sha256``, so a
field inside it is invisible to them. Measured: a 1.5.0 verifier on a store carrying a root
``sdipContentDigest`` reported MISMATCH (D67). **New marker data nests; it never adds a key.**
"""

MARKER_KEYS: Final[tuple[str, ...]] = (
    ATTR_WRITER,
    ATTR_VERSION,
    ATTR_PINS,
    ATTR_MITIGATIONS,
    ATTR_DECLARATION,
    ATTR_STORE_DIGEST,
    ATTR_SAMPLE_AXIS_ORIGIN,
)
"""Every attribute the marker writes. The store digest excludes exactly these."""

MITIGATION_HEADER_PLANE: Final[str] = "headers_raw_uint8"
"""Written unconditionally by ``sdip ingest`` (D-0051)."""

MITIGATION_SOURCE_ORDER: Final[str] = "source_trace_ordinal"
"""Written unconditionally by ``sdip ingest`` since D72 (P19). A store marked before it
existed does not declare it, so its absence there is not a partial write."""

DEFAULT_MITIGATIONS: Final[tuple[str, ...]] = (MITIGATION_HEADER_PLANE, MITIGATION_SOURCE_ORDER)
"""What the current writer always attaches."""


def marker_attrs(
    *,
    declaration: SurveyDeclaration,
    store_digest: dict[str, Any],
    content_digest: dict[str, Any],
    sample_axis_origin: dict[str, Any] | None,
    mitigations: tuple[str, ...] = DEFAULT_MITIGATIONS,
) -> dict[str, Any]:
    """The attribute mapping ``sdip ingest`` writes onto the root group."""
    from sdip import __version__

    return {
        ATTR_WRITER: "sdip.ingest",
        ATTR_VERSION: __version__,
        ATTR_PINS: {pin.distribution: pin.version for pin in PINS},
        ATTR_MITIGATIONS: list(mitigations),
        ATTR_DECLARATION: declaration.to_json(),
        ATTR_STORE_DIGEST: store_digest
        | {
            CONTENT_DIGEST_FIELD: {key: content_digest[key] for key in ("scheme", "root", "sha256")}
        },
    } | ({ATTR_SAMPLE_AXIS_ORIGIN: sample_axis_origin} if sample_axis_origin else {})


def attach_provenance_marker(
    store_path: str | Path,
    *,
    declaration: SurveyDeclaration,
    sample_axis_origin: dict[str, Any] | None,
    mitigations: tuple[str, ...] = DEFAULT_MITIGATIONS,
) -> dict[str, Any]:
    """Write the marker onto the store's root group. Stock ``zarr``, no MDIO.

    Args:
        store_path: The MDIO store.
        declaration: The survey declaration the store was written under. **Required.** It
            was optional, and a writer that left it out produced an ``UNBOUND`` store
            without a word - one no command can check its declaration against and no
            certificate can release. ``UNBOUND`` is for stores written before binding
            existed, not a state this writer can produce (OPEN_DEBTS D62's class).
        sample_axis_origin: The block :class:`sdip.ingest.sample_axis.AxisOrigin` gives
            when the writer moved the time axis to the recording delay, else ``None``.
            **Required, with no default** (D62): an omission must be a decision, not an
            accident that leaves a shifted store without its declaration.
        mitigations: Which unconditional mitigations this writer attaches.

    Returns:
        The attributes written.

    The store digest is taken here, after every other write and immediately before the
    marker, so it covers everything the marker vouches for and nothing written later.
    """
    import zarr

    from sdip.provenance.store_digest import CONTENT_SCHEME, compute_store_digest

    digest = compute_store_digest(store_path, marker_keys=MARKER_KEYS)
    content = compute_store_digest(store_path, marker_keys=MARKER_KEYS, scheme=CONTENT_SCHEME)
    attrs = marker_attrs(
        mitigations=mitigations,
        declaration=declaration,
        store_digest=digest,
        content_digest=content,
        sample_axis_origin=sample_axis_origin,
    )
    zarr.open_group(str(store_path), mode="r+").attrs.update(attrs)
    return attrs


def written_by_sdip(group: Any) -> bool:
    """True when this store declares that ``sdip ingest`` wrote it.

    **False is not a failure.** A store without the marker is a store SDIP did not write,
    which is a perfectly ordinary thing for the engine to be asked to verify.
    """
    return dict(group.attrs).get(ATTR_WRITER) == "sdip.ingest"


def recorded_declaration(group: Any) -> dict[str, Any] | None:
    """The declaration block this store records, or ``None`` if it predates binding."""
    if not written_by_sdip(group):
        return None
    block = dict(group.attrs).get(ATTR_DECLARATION)
    return dict(block) if isinstance(block, dict) else None


def recorded_store_digest(group: Any) -> dict[str, Any] | None:
    """The store digest this store records, or ``None`` if it predates the digest."""
    if not written_by_sdip(group):
        return None
    block = dict(group.attrs).get(ATTR_STORE_DIGEST)
    return dict(block) if isinstance(block, dict) else None


def recorded_content_digest(group: Any) -> dict[str, Any] | None:
    """The content digest this store records, or ``None`` if it predates it (before 1.6.0).

    Returned with the store digest's per-node digests, which it shares: the two schemes cover
    the same nodes and differ only in the root metadata.
    """
    store = recorded_store_digest(group) or {}
    content = store.get(CONTENT_DIGEST_FIELD)
    if not isinstance(content, dict):
        return None
    return dict(content) | {"nodes": dict(store.get("nodes") or {})}


def recorded_sample_axis_origin(group: Any) -> dict[str, Any] | None:
    """The axis-origin block an SDIP writer recorded, or ``None`` if it applied none."""
    if not written_by_sdip(group):
        return None
    block = dict(group.attrs).get(ATTR_SAMPLE_AXIS_ORIGIN)
    return dict(block) if isinstance(block, dict) else None


def declared_mitigations(group: Any) -> tuple[str, ...]:
    """Mitigations the writer declared it always attaches. Empty when unmarked."""
    if not written_by_sdip(group):
        return ()
    declared = dict(group.attrs).get(ATTR_MITIGATIONS) or ()
    return tuple(str(m) for m in declared)
