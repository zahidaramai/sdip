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


def _array_digest(array_dir: Path) -> str:
    """One array: every file under its directory, sorted by relative path, by content."""
    lines = []
    if array_dir.is_dir():
        for path in sorted(array_dir.rglob("*"), key=lambda p: p.relative_to(array_dir).as_posix()):
            if path.is_file():
                lines.append(f"{path.relative_to(array_dir).as_posix()}\0{sha256_file(path)}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def compute_store_digest(store: str | Path, *, marker_keys: tuple[str, ...]) -> dict[str, Any]:
    """The digest of ``store`` under :data:`SCHEME`.

    Args:
        store: A Zarr v3 store on local disk.
        marker_keys: Root attributes excluded from the digest - the marker's own.

    Returns:
        ``{"scheme", "nodes": {path: sha256}, "root": sha256, "sha256": ...}``. ``sha256``
        digests the rest and is the one value a consumer needs to record.
    """
    import zarr

    root = Path(store)
    group = zarr.open_group(str(root), mode="r")
    nodes: dict[str, str] = {}
    for _name, member in group.members(max_depth=None):
        node_dir = root / str(member.path)
        if isinstance(member, zarr.Array):
            nodes[str(member.path)] = _array_digest(node_dir)
        else:
            nodes[str(member.path) + "/"] = sha256_file(node_dir / METADATA_FILENAME)
    root_digest = sha256_bytes(_canonical(_root_document(root, marker_keys)))
    body = {"scheme": SCHEME, "nodes": dict(sorted(nodes.items())), "root": root_digest}
    return body | {"sha256": sha256_bytes(_canonical(body))}


@dataclass(frozen=True, slots=True)
class StoreDigestResult:
    """Outcome of recomputing a store's digest against the one its marker records."""

    status: str
    recorded: str | None = None
    computed: str | None = None
    changed: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        """False only on MISMATCH. An absent digest is not a failure (see ``describe``)."""
        return self.status != MISMATCH

    def describe(self) -> str:
        """One line for the operator."""
        if self.status == MATCH:
            return f"sha256 {(self.computed or '')[:12]}, as sdip ingest recorded it"
        if self.status == MISMATCH:
            return (
                "the store differs from what sdip ingest recorded when it finished writing: "
                f"{', '.join(self.changed) or 'unlocated'}"
            )
        if self.status == ABSENT:
            return "the store predates the store digest, so whether it changed cannot be checked"
        return "the store was not written by sdip ingest; no digest to compare"

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped ``store_digest`` block."""
        return {
            "status": self.status,
            "scheme": SCHEME,
            "recorded_sha256": self.recorded,
            "computed_sha256": self.computed,
            "changed": list(self.changed),
        }


def check_store_digest(store: str | Path) -> StoreDigestResult:
    """Recompute ``store``'s digest and compare it with the one its marker records."""
    import zarr

    from sdip.ingest.provenance_marker import MARKER_KEYS, recorded_store_digest, written_by_sdip

    group = zarr.open_group(str(store), mode="r")
    if not written_by_sdip(group):
        return StoreDigestResult(FOREIGN)
    recorded = recorded_store_digest(group)
    if recorded is None:
        return StoreDigestResult(ABSENT)
    computed = compute_store_digest(store, marker_keys=MARKER_KEYS)
    if recorded.get("scheme") == SCHEME and recorded.get("sha256") == computed["sha256"]:
        return StoreDigestResult(MATCH, recorded.get("sha256"), computed["sha256"])
    if recorded.get("scheme") != SCHEME:
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
    return StoreDigestResult(MISMATCH, recorded.get("sha256"), computed["sha256"], changed)
