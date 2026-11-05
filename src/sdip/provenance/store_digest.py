"""Is this the store `sdip ingest` wrote? A digest of its contents, recorded in the marker.

**Why.** The provenance marker says which SDIP wrote a store, under which pins and which
declaration. Until this digest existed it said nothing about *what* was written, so a
reader holding a store could not tell whether it held the store ``verify`` certified or
one changed since (issue #1 part (b), ``DECISIONS.md`` D-0093).

**What it covers, and why that much.**

* **Every node stock ``zarr`` lists**, at any depth. For an array, every file under its
  directory, ``zarr.json`` included; for a nested group, its ``zarr.json``. Including the
  array metadata is load-bearing: SDIP's authoritative raw textual and binary headers live
  in the attributes of ``segy_file_header`` (:func:`sdip.ingest.file_headers.raw_header_node`),
  so a digest of chunk bytes alone — G6's comparison, which skips ``zarr.json`` because it
  carries a timestamp — would leave out the very bytes Planes 1 and 2 certify. G6 asks
  whether two runs agree; this asks whether one store is still itself, and a timestamp is
  part of itself.
* **The root group's metadata, minus the marker's own attributes.** The marker lives in
  the root ``zarr.json``; a digest cannot contain itself. The root document is compared as
  canonical JSON (sorted keys, no whitespace) because writing the marker rewrites that file,
  and its formatting is the writer's business while its content is not.

**What it does not cover.** A file under the store that belongs to no node — a stray file
a reader never opens — changes nothing a reader sees and is not digested. A reader is not
shown it, and a digest that failed on a desktop metadata file would teach operators to
ignore it.

**What a digest proves, stated narrowly.** MATCH means the store holds exactly what
``sdip ingest`` recorded when it finished writing. It is not a statement about the source;
that is what the planes are for. A MISMATCH is a store changed after it was written, which
is a fact about the store and fails ``verify``. **It is not a signature:** whoever can
rewrite the store can rewrite the marker. It detects change, not intent.

Hashing is streamed (§11.4): a store is untrusted input to ``verify``, and no file is read
whole except a node's own ``zarr.json``, which ``zarr`` has already read to open it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from sdip.provenance.hashing import sha256_bytes, sha256_file

SCHEME: Final[str] = "sdip-store-digest/1"
"""Names the definition above. A change to what is covered is a new scheme, never an edit."""

CONTENT_SCHEME: Final[str] = "sdip-content-digest/1"
"""The **content** digest (D-0101): the store digest less the per-ingest metadata.

The store digest proves a store is unchanged since it was written; it cannot show a re-ingest
reproduced it, because MDIO writes a creation time into the root metadata. The content digest
covers exactly what the store digest covers except :data:`CONTENT_EXCLUDED_ROOT_ATTRIBUTES`, so
two ingests of one source under one declaration give the same value - **except** where MDIO's
``amplitude`` ``statsV1.sumSquares`` differs between runs by a few float64 ulps, measured on a
1.60 GB source (OPEN_DEBTS D75). :data:`CONTENT_SCHEME_V2` excludes it (D-0135) and is the
reproducibility claim; ``/1`` stays the identity of a bound store.
"""

CONTENT_EXCLUDED_ROOT_ATTRIBUTES: Final[tuple[str, ...]] = ("createdOn",)
"""Exactly the keys probe P13 measured varying between ingests, and nothing else.

Five store shapes (ibm32, IEEE, a recording delay, an undecodable textual header, rev 0), three
fresh ingests each: every chunk byte and every array's ``zarr.json`` identical; MDIO's root
``createdOn`` the only key that differed (``prereg/P13-store-content-variance.md``). A key is
added here only on a measurement of the same kind, as a new scheme.
"""

CONTENT_SCHEME_V2: Final[str] = "sdip-content-digest/2"
"""The content digest that reproduces at survey scale (D-0134, D-0135; ``OPEN_DEBTS`` D75).

``/1`` with exactly one more exclusion: the ``sumSquares`` member of ``amplitude``'s ``statsV1``
attribute. Probe P31 ingested 1.60 and 4.81 GB sources 13 times. No chunk file differed, and the
only keys that varied were root ``createdOn`` and that member: a float64 sum MDIO accumulates in
an order that changes between runs (3 ulps, P28). ``statsV1``'s other members (``count``, ``sum``,
``min``, ``max``) never varied and stay covered. ``/1`` stays recorded beside it, unchanged: it
identifies a bound store; ``/2`` is the value a re-ingest reproduces.
"""

CONTENT_V2_EXCLUDED_ARRAY_MEMBERS: Final[dict[str, tuple[str, str]]] = {
    "amplitude": ("statsV1", "sumSquares"),
}
"""Array path -> (attribute holding a JSON string, member removed from it). Exactly P31's."""

METADATA_FILENAME: Final[str] = "zarr.json"

MATCH: Final[str] = "MATCH"
MISMATCH: Final[str] = "MISMATCH"
ABSENT: Final[str] = "ABSENT"
FOREIGN: Final[str] = "FOREIGN"


def _canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _root_document(store: Path, marker_keys: tuple[str, ...]) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((store / METADATA_FILENAME).read_bytes())
    attributes = dict(document.get("attributes") or {})
    for key in marker_keys:
        attributes.pop(key, None)
    document["attributes"] = attributes
    return document


def _metadata_without_member(path: Path, attribute: str, member: str) -> str:
    """sha256 of an array's ``zarr.json`` in canonical form, one JSON-string member removed.

    The attribute is a JSON **string** (MDIO writes ``statsV1`` that way), so it is parsed, the
    member dropped, and the rest kept as canonical JSON. Anything that is not such a string is
    digested as it stands, so a store without ``statsV1`` loses nothing.
    """
    document: dict[str, Any] = json.loads(path.read_bytes())
    attributes = dict(document.get("attributes") or {})
    value = attributes.get(attribute)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            parsed.pop(member, None)
            attributes[attribute] = _canonical(parsed).decode()
    document["attributes"] = attributes
    return sha256_bytes(_canonical(document))


def _array_digest(array_dir: Path, without: tuple[str, str] | None = None) -> str:
    """One array: every file under its directory, sorted by relative path, by content.

    ``without`` names an attribute member :data:`CONTENT_SCHEME_V2` leaves out of this array's
    ``zarr.json``; every other file, chunks included, is digested byte for byte.
    """
    lines = []
    if array_dir.is_dir():
        for path in sorted(array_dir.rglob("*"), key=lambda p: p.relative_to(array_dir).as_posix()):
            if path.is_file():
                rel = path.relative_to(array_dir).as_posix()
                if without is not None and rel == METADATA_FILENAME:
                    digest = _metadata_without_member(path, *without)
                else:
                    digest = sha256_file(path)
                lines.append(f"{rel}\0{digest}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def compute_store_digest(
    store: str | Path, *, marker_keys: tuple[str, ...], scheme: str = SCHEME
) -> dict[str, Any]:
    """The digest of ``store`` under :data:`SCHEME`, or :data:`CONTENT_SCHEME`.

    Args:
        store: A Zarr v3 store on local disk.
        marker_keys: Root attributes excluded from the digest - the marker's own.
        scheme: :data:`SCHEME` (the default); :data:`CONTENT_SCHEME`, which also excludes
            :data:`CONTENT_EXCLUDED_ROOT_ATTRIBUTES` from the root metadata; or
            :data:`CONTENT_SCHEME_V2`, which excludes those and
            :data:`CONTENT_V2_EXCLUDED_ARRAY_MEMBERS` too.

    Returns:
        ``{"scheme", "nodes": {path: sha256}, "root": sha256, "sha256": ...}``. ``sha256``
        digests the rest and is the one value a consumer needs to record.
    """
    import zarr

    root = Path(store)
    group = zarr.open_group(str(root), mode="r")
    if scheme not in (SCHEME, CONTENT_SCHEME, CONTENT_SCHEME_V2):
        msg = f"unknown digest scheme {scheme!r}"
        raise ValueError(msg)
    members = CONTENT_V2_EXCLUDED_ARRAY_MEMBERS if scheme == CONTENT_SCHEME_V2 else {}
    nodes: dict[str, str] = {}
    for _name, member in group.members(max_depth=None):
        node_dir = root / str(member.path)
        if isinstance(member, zarr.Array):
            nodes[str(member.path)] = _array_digest(node_dir, members.get(str(member.path)))
        else:
            nodes[str(member.path) + "/"] = sha256_file(node_dir / METADATA_FILENAME)
    content = scheme in (CONTENT_SCHEME, CONTENT_SCHEME_V2)
    excluded = marker_keys + (CONTENT_EXCLUDED_ROOT_ATTRIBUTES if content else ())
    root_digest = sha256_bytes(_canonical(_root_document(root, excluded)))
    body = {"scheme": scheme, "nodes": dict(sorted(nodes.items())), "root": root_digest}
    return body | {"sha256": sha256_bytes(_canonical(body))}


@dataclass(frozen=True, slots=True)
class StoreDigestResult:
    """Outcome of recomputing a store's digest against the one its marker records."""

    status: str
    recorded: str | None = None
    computed: str | None = None
    changed: tuple[str, ...] = field(default_factory=tuple)
    scheme: str = SCHEME

    @property
    def passed(self) -> bool:
        """False only on MISMATCH. An absent digest is not a failure (see ``describe``)."""
        return self.status != MISMATCH

    def describe(self) -> str:
        """One line for the operator."""
        what = {CONTENT_SCHEME: "content", CONTENT_SCHEME_V2: "content /2"}.get(
            self.scheme, "store"
        )
        if self.status == MATCH:
            return f"sha256 {(self.computed or '')[:12]}, as sdip ingest recorded it"
        if self.status == MISMATCH:
            return (
                f"the {what} differs from what sdip ingest recorded when it finished writing: "
                f"{', '.join(self.changed) or 'unlocated'}"
            )
        if self.status == ABSENT:
            return f"the store predates the {what} digest, so it cannot be checked"
        return "the store was not written by sdip ingest; no digest to compare"

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped ``store_digest`` or ``content_digest`` block."""
        return {
            "status": self.status,
            "scheme": self.scheme,
            "recorded_sha256": self.recorded,
            "computed_sha256": self.computed,
            "changed": list(self.changed),
        }


def check_store_digest(store: str | Path) -> StoreDigestResult:
    """Recompute ``store``'s digest and compare it with the one its marker records."""
    from sdip.ingest.provenance_marker import recorded_store_digest

    return _check(store, SCHEME, recorded_store_digest)


def check_content_digest(store: str | Path) -> StoreDigestResult:
    """Recompute ``store``'s content digest and compare it with the one its marker records."""
    from sdip.ingest.provenance_marker import recorded_content_digest

    return _check(store, CONTENT_SCHEME, recorded_content_digest)


def check_content_digest_v2(store: str | Path) -> StoreDigestResult:
    """Recompute ``store``'s ``/2`` content digest and compare it with the one its marker records.

    ``ABSENT`` for a store written before ``/2`` existed: its marker is never rewritten to add one
    (D-0135), so such a store keeps ``/1`` alone.
    """
    from sdip.ingest.provenance_marker import recorded_content_digest_v2

    return _check(store, CONTENT_SCHEME_V2, recorded_content_digest_v2)


def _check(store: str | Path, scheme: str, read_recorded: Any) -> StoreDigestResult:
    import zarr

    from sdip.ingest.provenance_marker import MARKER_KEYS, written_by_sdip

    group = zarr.open_group(str(store), mode="r")
    if not written_by_sdip(group):
        return StoreDigestResult(FOREIGN, scheme=scheme)
    recorded = read_recorded(group)
    if recorded is None:
        return StoreDigestResult(ABSENT, scheme=scheme)
    computed = compute_store_digest(store, marker_keys=MARKER_KEYS, scheme=scheme)
    if recorded.get("scheme") == scheme and recorded.get("sha256") == computed["sha256"]:
        return StoreDigestResult(MATCH, recorded.get("sha256"), computed["sha256"], scheme=scheme)
    if recorded.get("scheme") != scheme:
        changed: tuple[str, ...] = (f"recorded under scheme {recorded.get('scheme')!r}",)
    else:
        before = dict(recorded.get("nodes") or {})
        after = computed["nodes"]
        differing = [name for name in before if name in after and before[name] != after[name]]
        changed = tuple(
            sorted(
                [f"{name} changed" for name in differing]
                + [f"{name} removed" for name in before if name not in after]
                + [f"{name} added" for name in after if name not in before]
            )
        )
        if recorded.get("root") != computed["root"]:
            changed = (*changed, "root metadata changed")
    return StoreDigestResult(
        MISMATCH, recorded.get("sha256"), computed["sha256"], changed, scheme=scheme
    )
