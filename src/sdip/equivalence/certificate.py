"""Equivalence Certificate assembly. Specification §4.7.

**The certificate is the product.** An MDIO store without a passing certificate is an
untrusted artifact, not an SDIP deliverable (§0). Everything here exists to make the
strongest claim the project can make — ``verdict: EQUIVALENT`` — impossible to emit
unless the evidence for it is present in the same document.

At phase F2 that claim is **unreachable by construction**, and deliberately so:

- Planes 3, 4 and 5 are not implemented, so they are ``NOT_RUN``.
- G3, G4, G5, G6 and **G7** are not implemented, so they are ``NOT_RUN``.
- :func:`verdict_for` returns ``EQUIVALENT`` only when every plane is ``PASS`` **and**
  G7 is ``PASS``. G7 cannot be ``PASS`` at F2.

So an F2 certificate is `PROVISIONAL` at best. That is the honest answer, and it is
enforced in code rather than left to the operator's discretion — **until G7 passes,
every certificate the engine issues is unvalidated** (`OPEN_DEBTS.md` D11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdip import __version__
from sdip._pins import CERTIFICATE_SCHEMA_VERSION, LOSSY_CODECS, SPEC_VERSION
from sdip.equivalence.planes import PlaneResult
from sdip.equivalence.portability import PortabilityResult
from sdip.errors import DirtyTreeError
from sdip.export.roundtrip import RoundTripResult
from sdip.guard.pins import check_pins
from sdip.ingest.orchestrator import IngestResult
from sdip.provenance.environment import capture_environment
from sdip.provenance.git import capture_git_state

GATES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7")
PLANE_KEYS = ("plane_1", "plane_2", "plane_3", "plane_4", "plane_5")

NOT_RUN = "NOT_RUN"


def verdict_for(planes: dict[str, str], gates: dict[str, str], *, lossy: bool) -> str:
    """Derive the verdict. There is no partial credit (§4.1).

    ``EQUIVALENT`` requires **all five planes PASS and G7 PASS**. Any plane failing
    makes it ``NON-EQUIVALENT``; anything merely unrun makes it ``PROVISIONAL``.

    G7 is in the condition because a gate a corrupted store passes is not a gate
    (**SP11**). A store whose five planes pass against an engine that has never been
    shown capable of failing has not been checked — it has been agreed with.
    """
    if lossy:
        return "NON-EQUIVALENT"
    if any(planes.get(k) == "FAIL" for k in PLANE_KEYS):
        return "NON-EQUIVALENT"
    if any(v == "FAIL" for v in gates.values()):
        return "NON-EQUIVALENT"
    if gates.get("G3") == "ROUNDTRIP-SCOPED":
        # Permitted only with a written justification naming the non-conformance
        # (§7 G3). It is not byte-identity, so it is not an unqualified EQUIVALENT.
        return "PROVISIONAL"
    if all(planes.get(k) == "PASS" for k in PLANE_KEYS) and gates.get("G7") == "PASS":
        return "EQUIVALENT"
    return "PROVISIONAL"


def read_codec_manifest(store: str | Path) -> list[str]:
    """Read every codec name on disk, with stock ``zarr``. SP3.

    Read from the store rather than from what the writer intended: the manifest is what
    a consumer will actually decode with, and a lossy entry there voids the store no
    matter what the ingest configuration said.
    """
    import zarr

    group = zarr.open_group(str(store), mode="r")
    names: set[str] = set()
    for _, array in group.arrays():
        # zarr returns a tuple here, not a list; accept any non-str sequence so a
        # metadata shape change cannot silently empty the manifest.
        codecs = array.metadata.to_dict().get("codecs", ())
        if isinstance(codecs, str) or not isinstance(codecs, Sequence):
            continue  # pragma: no cover - malformed metadata
        for codec in codecs:
            name = codec.get("name") if isinstance(codec, dict) else str(codec)
            if name:
                names.add(str(name))
    return sorted(names)


@dataclass(slots=True)
class Certificate:
    """A machine-readable Equivalence Certificate, schema v0."""

    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        """The verdict a consumer reads (§10.1)."""
        return str(self.payload["verdict"])

    def to_json(self) -> dict[str, Any]:
        """The certificate document."""
        return self.payload


def issue(
    result: IngestResult,
    planes: list[PlaneResult],
    *,
    roundtrip: RoundTripResult | None = None,
    portability: PortabilityResult | None = None,
    root: str | Path = ".",
    require_clean_tree: bool = True,
    issued_at: str,
    issued_by: str,
) -> Certificate:
    """Assemble a certificate from an ingest and whatever planes were run.

    Args:
        result: The ingest.
        planes: Plane results actually produced. Planes absent from this list are
            recorded ``NOT_RUN`` — never assumed to pass.
        roundtrip: G3 result, when a round trip was performed. Absent means
            ``NOT_RUN`` - never assumed to pass.
        portability: G4 result, when the portability check was run.
        root: Repository root, for git state.
        require_clean_tree: Refuse to issue from a dirty tree (§11.3). **There is no
            ``--force``**; this parameter exists so tests can exercise the refusal, and
            the CLI never sets it to ``False``.
        issued_at: ISO-8601 UTC timestamp. Passed in rather than read from the clock so
            a certificate is reproducible from the committed record (§11.3, G6).
        issued_by: Who issued it.

    Returns:
        The certificate.

    Raises:
        DirtyTreeError: If the working tree is dirty and ``require_clean_tree``.
    """
    git = capture_git_state(root)
    if require_clean_tree and not git.certifiable:
        detail = (
            "not a git repository"
            if not git.is_repository
            else f"{len(git.dirty_paths)} uncommitted path(s)"
        )
        msg = (
            f"refusing to issue a certificate from a dirty working tree ({detail}). "
            "A certificate that cannot be reproduced from the committed record is not "
            "evidence (spec 11.3). There is no override."
        )
        raise DirtyTreeError(msg)

    plane_block: dict[str, Any] = {
        key: {"status": NOT_RUN, "evidence": {"reason": "not implemented at this phase"}}
        for key in PLANE_KEYS
    }
    for plane in planes:
        plane_block[f"plane_{plane.plane}"] = plane.to_json()

    codecs = read_codec_manifest(result.output_path)
    lossy = bool(set(codecs) & LOSSY_CODECS)

    gate_block = dict.fromkeys(GATES, NOT_RUN)
    gate_block["G1"] = result.g1.status
    if planes:
        # G2 is the conjunction of G2a-G2e. It is PASS only when ALL FIVE planes ran
        # and passed: four passing planes and one unrun is not a passing G2, because
        # the unrun one is exactly where a defect would hide.
        if len(planes) == len(PLANE_KEYS) and all(p.passed for p in planes):
            gate_block["G2"] = "PASS"
        elif any(not p.passed for p in planes):
            gate_block["G2"] = "FAIL"
    if roundtrip is not None:
        gate_block["G3"] = roundtrip.status
    if portability is not None:
        gate_block["G4"] = portability.status

    plane_status = {k: v["status"] for k, v in plane_block.items()}
    verdict = verdict_for(plane_status, gate_block, lossy=lossy)

    store_path = Path(result.output_path)
    output_bytes = sum(f.stat().st_size for f in store_path.rglob("*") if f.is_file())

    payload: dict[str, Any] = {
        "certificate_schema_version": CERTIFICATE_SCHEMA_VERSION,
        "spec_version": SPEC_VERSION,
        "source_path": result.source_path,
        "source_sha256": result.source_sha256,
        "source_sha256_post_read": result.source_sha256_post_read,
        "source_bytes": result.source_bytes,
        "segy_revision": str(result.spec.revision),
        "detected_encoding": {
            "encoding": "ebcdic",
            "decode_status": "decoded",
            "detail": (
                "SDIP stores the raw 3200 bytes and compares them as bytes; the "
                "encoding is recorded, never used to normalise (§4.2)."
            ),
        },
        "spec_id": result.spec.spec_id,
        "spec_field_count": result.spec.field_count,
        "spec_itemsize": result.spec.itemsize,
        "spec_gap_free": result.spec.coverage.gap_free,
        "spec_sha256": result.spec.sha256(),
        "output_path": result.output_path,
        "output_zarr_format": 3,
        "output_bytes": output_bytes,
        "output_array_manifest": _array_manifest(result.output_path),
        "planes": plane_block,
        "roundtrip": (
            roundtrip.to_json()
            if roundtrip is not None
            else {"performed": False, "byte_identical": False}
        ),
        "portability": portability.to_json() if portability is not None else None,
        "transforms_declared": [],
        "warnings": result.warnings.to_json(),
        "codecs_used": codecs,
        "lossy_codec_present": lossy,
        "env": capture_environment().to_json() | {"pins": [s.to_json() for s in check_pins()]},
        "git": git.to_json() | {"sdip_version": __version__},
        "gates": gate_block,
        "verdict": verdict,
        "verdict_reason": _verdict_reason(verdict, plane_status, gate_block),
        "issued_at": issued_at,
        "issued_by": issued_by,
    }
    return Certificate(payload=payload)


def _verdict_reason(verdict: str, planes: dict[str, str], gates: dict[str, str]) -> str:
    if verdict == "EQUIVALENT":
        return "All five planes PASS and G7 PASS."
    unrun_planes = [k for k in PLANE_KEYS if planes.get(k) == NOT_RUN]
    unrun_gates = [g for g in GATES if gates.get(g) == NOT_RUN]
    if verdict == "NON-EQUIVALENT":
        failed = [k for k in PLANE_KEYS if planes.get(k) == "FAIL"]
        failed += [g for g in GATES if gates.get(g) == "FAIL"]
        return "Failed: " + ", ".join(failed)
    if not unrun_planes and "G7" in unrun_gates:
        return (
            "PROVISIONAL. Every plane passed, but G7 has not run "
            f"(also unrun: {', '.join(g for g in unrun_gates if g != 'G7') or 'none'}). "
            "A gate a corrupted store passes is not a gate (SP11), so "
            "an engine that has never been shown capable of failing cannot certify "
            "equivalence. OPEN_DEBTS D11."
        )
    return (
        f"PROVISIONAL. Not run: planes {', '.join(unrun_planes) or 'none'}; "
        f"gates {', '.join(unrun_gates) or 'none'}. Until G7 passes, every certificate "
        "the engine issues is unvalidated (OPEN_DEBTS D11)."
    )


def _array_manifest(store: str | Path) -> list[dict[str, Any]]:
    import zarr

    group = zarr.open_group(str(store), mode="r")
    manifest: list[dict[str, Any]] = []
    for name, array in sorted(group.arrays()):
        meta = array.metadata.to_dict()
        data_type = meta.get("data_type")
        # A plain string is a Zarr v3 core-spec dtype; a mapping is an extension, which
        # is what the structured `headers` array uses. Measured, spec Appendix A.1.
        core = isinstance(data_type, str)
        codec_list = meta.get("codecs", ())
        usable = (
            ()
            if isinstance(codec_list, str) or not isinstance(codec_list, Sequence)
            else codec_list
        )
        codec_names = sorted(str(c.get("name")) for c in usable if isinstance(c, dict))
        manifest.append(
            {
                "name": name,
                "data_type": data_type,
                "zarr_v3_core_spec": core,
                "shape": list(array.shape),
                "chunks": list(getattr(array, "chunks", ()) or ()),
                "codecs": codec_names,
            }
        )
    return manifest
