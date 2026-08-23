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
from sdip.equivalence.closure import ClosureResult
from sdip.equivalence.determinism import G6Result
from sdip.equivalence.nonvacuity import G7Result
from sdip.equivalence.planes import PlaneResult
from sdip.equivalence.portability import PortabilityResult
from sdip.equivalence.scale import G5Result
from sdip.errors import DirtyTreeError
from sdip.export.roundtrip import RoundTripResult
from sdip.guard.pins import check_pins
from sdip.ingest.orchestrator import IngestResult
from sdip.ingest.raw_samples import ARRAY_NAME as RAW_IBM32_ARRAY_NAME
from sdip.provenance.environment import capture_environment
from sdip.provenance.git import GitState, capture_git_state
from sdip.spec.transforms import (
    detect_coordinate_scalar,
    detect_lossy_decode,
    lossy_decode_blocks_equivalence,
)

GATES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7")
PLANE_KEYS = ("plane_1", "plane_2", "plane_3", "plane_4", "plane_5")

NOT_RUN = "NOT_RUN"


def verdict_for(
    planes: dict[str, str],
    gates: dict[str, str],
    *,
    lossy: bool,
    transform_blocked: bool = False,
) -> str:
    """Derive the verdict. There is no partial credit (§4.1).

    ``EQUIVALENT`` requires **all five planes PASS and G7 PASS**. Any plane failing
    makes it ``NON-EQUIVALENT``; anything merely unrun makes it ``PROVISIONAL``.

    G7 is in the condition because a gate a corrupted store passes is not a gate
    (**SP11**). A store whose five planes pass against an engine that has never been
    shown capable of failing has not been checked — it has been agreed with.

    ``transform_blocked`` carries probe **P2**'s result: the ``ibm32 → float32`` decode
    is **not** exactly invertible in general (2,447 of 4,103 words fail; 1,939 lose the
    value). **SP1** permits only an exactly invertible transform, so when a source
    declares ``ibm32`` and the round trip did not prove invertibility on that data by
    whole-file byte identity, ``EQUIVALENT`` is not available.
    """
    # Order matters. A measured FAILURE outranks an unproven claim: a store with a
    # failing plane is NON-EQUIVALENT whether or not the transform could be verified,
    # and returning PROVISIONAL there would soften a real defect into an open question.
    if lossy:
        return "NON-EQUIVALENT"
    if any(planes.get(k) == "FAIL" for k in PLANE_KEYS):
        return "NON-EQUIVALENT"
    if any(v == "FAIL" for v in gates.values()):
        return "NON-EQUIVALENT"
    if transform_blocked:
        return "PROVISIONAL"
    if gates.get("G3") == "ROUNDTRIP-SCOPED":
        # Permitted only with a written justification naming the non-conformance
        # (§7 G3). It is not byte-identity, so it is not an unqualified EQUIVALENT.
        return "PROVISIONAL"
    if all(planes.get(k) == "PASS" for k in PLANE_KEYS) and gates.get("G7") == "PASS":
        return "EQUIVALENT"
    return "PROVISIONAL"


def _detected_encoding(result: Any) -> dict[str, Any]:
    """The certificate's ``detected_encoding`` block. §4.2, §4.7.

    §4.2 requires the encoding *recorded, never silently normalised*, and a decode
    failure *recorded on the certificate* rather than raised as an ingestion failure.
    Both come from the ingest, which measured them on this file's raw 3200 bytes before
    the converter ran (``DECISIONS.md`` D-0055).

    A result carrying no measurement is reported as such rather than defaulted to
    ``decoded``: an unmeasured plane is ``NOT_RUN`` everywhere else in this module, and
    an unmeasured decode must not read as a passing one.
    """
    decode = getattr(result, "textual_decode", None)
    if decode is None:
        return {
            "encoding": "unknown",
            "decode_status": "raw_preserved_decode_failed",
            "detail": (
                "this ingest recorded no textual-header decode measurement, so the "
                "encoding is unknown. The raw 3200 bytes are preserved and Plane 1 is "
                "checked against them regardless (§4.2)."
            ),
        }
    block: dict[str, Any] = decode.to_json()
    return block


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
    nonvacuity: G7Result | None = None,
    closure: ClosureResult | None = None,
    determinism: G6Result | None = None,
    scale: G5Result | None = None,
    root: str | Path = ".",
    require_clean_tree: bool = True,
    baseline: GitState | None = None,
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
        closure: Round-trip closure result — the exported SEG-Y re-ingested and checked
            as an artifact in its own right (`DECISIONS.md` D-0031 arrow 3). Absent means
            ``NOT_RUN``.
        determinism: G6 result — two independent ingests compared on chunk bytes and
            array values. Absent means ``NOT_RUN``.
        scale: G5 result — a completed survey-scale run judged against ceilings declared
            **before** it (SP9). Absent means ``NOT_RUN``.
        nonvacuity: G7 result. **Absent means ``NOT_RUN``, and the verdict cannot reach
            ``EQUIVALENT``** - a store whose planes pass against an engine never shown
            capable of failing has not been checked.
        root: Repository root, for git state.
        require_clean_tree: Refuse to issue from a dirty tree (§11.3). **There is no
            ``--force``**; this parameter exists so tests can exercise the refusal, and
            the CLI never sets it to ``False``.
        baseline: Git state captured **before the measurements began**. When given, the
            commit must still match at issue time. A clean tree at issue time is not
            sufficient on its own: a run that starts dirty and is committed midway ends
            clean, and the certificate would then attest to a commit that is **not the
            code the measurements came from**. Checking both ends closes that.
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

    if require_clean_tree and baseline is not None and baseline.commit != git.commit:
        msg = (
            f"refusing to issue: HEAD moved during the run, from "
            f"{baseline.commit or 'no commit'} to {git.commit or 'no commit'}. The "
            "measurements on this certificate were produced by the code at the first "
            "commit, so attesting them to the second would be a false provenance claim. "
            "A clean tree at issue time does not establish that the tree was clean while "
            "the work was done (spec 11.3). There is no override."
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

    # SP1(a) / probes P2 and P9. The exposure is declared whether or not it blocks, and
    # now for EVERY sample format rather than ibm32 alone - including the exact ones.
    # An exact transform declared is what makes an undeclared one detectable: an empty
    # `transforms_declared` then means no decode ran, not that nobody looked (D-0063).
    exposure = detect_lossy_decode(result.spec.segy_spec)

    # Read from the store, not assumed: a constant here went stale the moment the raw
    # view was built, and put a false statement on every ibm32 certificate.
    raw_view_present = False
    try:
        import zarr

        raw_view_present = RAW_IBM32_ARRAY_NAME in zarr.open_group(
            str(result.output_path), mode="r"
        )
    except (KeyError, ValueError, OSError):  # pragma: no cover - unreadable store
        raw_view_present = False

    # SP1(a): every transform declared. Probe P5 found the coordinate scalar applied to
    # the derived cdp_x/cdp_y arrays and named nowhere on the certificate.
    coord_transform = None
    try:
        from segy import SegyFile

        handle = SegyFile(str(result.source_path), spec=result.spec.segy_spec)
        coord_transform = detect_coordinate_scalar(handle.header[:])
    except Exception:
        coord_transform = None
    byte_identical = bool(roundtrip is not None and roundtrip.byte_identical)
    transform_blocked, transform_reason = lossy_decode_blocks_equivalence(
        result.spec.segy_spec, roundtrip_byte_identical=byte_identical
    )

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
    if scale is not None:
        gate_block["G5"] = scale.status
    if determinism is not None:
        gate_block["G6"] = determinism.status
    if nonvacuity is not None:
        gate_block["G7"] = nonvacuity.status

    plane_status = {k: v["status"] for k, v in plane_block.items()}
    verdict = verdict_for(
        plane_status, gate_block, lossy=lossy, transform_blocked=transform_blocked
    )

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
        # MEASURED on this file's own 3200 bytes, never asserted. Before D-0055 this
        # block said `decoded` unconditionally - a fidelity claim with no number behind
        # it (SP8), and one that would have been false for exactly the non-conforming
        # legacy vintage §4.2 exists to rescue.
        "detected_encoding": _detected_encoding(result),
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
        "nonvacuity": nonvacuity.to_json() if nonvacuity is not None else None,
        "roundtrip_closure": closure.to_json() if closure is not None else None,
        "determinism": determinism.to_json() if determinism is not None else None,
        "scale": scale.to_json() if scale is not None else None,
        "transforms_declared": (
            ([exposure.to_json(raw_view_stored=raw_view_present)] if exposure is not None else [])
            + (
                [coord_transform.to_json()]
                if coord_transform is not None and not coord_transform.is_identity
                else []
            )
        ),
        "portable_headers": _portable_headers(result.output_path),
        "transform_scope_blocks_equivalence": transform_blocked,
        "transform_scope_reason": transform_reason or None,
        "warnings": result.warnings.to_json(),
        "codecs_used": codecs,
        "lossy_codec_present": lossy,
        "env": capture_environment().to_json() | {"pins": [s.to_json() for s in check_pins()]},
        "git": git.to_json() | {"sdip_version": __version__},
        "gates": gate_block,
        "verdict": verdict,
        "verdict_reason": _verdict_reason(
            verdict,
            plane_status,
            gate_block,
            transform_blocked=transform_blocked,
            transform_reason=transform_reason,
        ),
        "issued_at": issued_at,
        "issued_by": issued_by,
    }
    payload["release_readiness"] = release_readiness(payload)
    return Certificate(payload=payload)


def release_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a certificate against the **release** acceptance criterion (D-0031).

    **This is stricter than ``verdict``, deliberately, and the difference is the point.**

    ``verdict == "EQUIVALENT"`` requires all five planes and G7. It **tolerates G5 and G6
    being ``NOT_RUN``**, which is honest today — they are recorded ``NOT_RUN`` on the
    face of the certificate, and a reader can see exactly what did not run.

    At release that tolerance stops being honest, because the reader stops looking.
    **An unrun gate is not a passing one**, and a certificate with holes in it is the
    untrusted artifact §0 describes. So the release criterion is: **every gate ``PASS``,
    no gate ``NOT_RUN``, both outputs validated** — the MDIO store *and* the exported
    SEG-Y (arrow ③, round-trip closure).

    Reported alongside the verdict rather than replacing it, so that tightening the bar
    later is a change of *policy* and not a change of *measurement*: a certificate issued
    today already carries the answer to the stricter question.

    Args:
        payload: A certificate document.

    Returns:
        ``{"release_ready": bool, "blocking": [...], "criterion": ...}``.
    """
    # NOTE ON SCOPE, so this is not read as wider than it is: G4, G5 and G6 have no
    # negative controls at all. That is not an oversight here - §7 G7's declared remit is
    # G2a-G2e and G3, so those three sit outside it by specification. This function
    # blocks on controls that EXIST and RAN; it does not invent a requirement for
    # controls the specification never asked for.
    gates = payload.get("gates", {})
    planes = payload.get("planes", {})
    blocking: list[str] = []

    for gate in GATES:
        status = gates.get(gate, NOT_RUN)
        if status != "PASS":
            blocking.append(f"gate {gate} is {status}")
    for key in PLANE_KEYS:
        status = planes.get(key, {}).get("status", NOT_RUN)
        if status != "PASS":
            blocking.append(f"{key} is {status}")

    # D42 / SP11. The controls are consulted, not merely recorded. `g3_control` and
    # `closure_control` each demonstrate that a check is CAPABLE OF FAILING - they
    # corrupt an export and require the check to catch it. A control that came back
    # non-PASS means its check has been shown incapable of failing, which is the precise
    # definition of a vacuous check, and until now `release_readiness` never read either.
    #
    # G7's own controls need no clause here: G7 is in GATES and is already blocked on
    # above. These two live outside it because both need a corrupted EXPORT FILE rather
    # than a corrupted store, so they cannot share G7's machinery - and that is exactly
    # how they came to be recorded and never read.
    nonvacuity = payload.get("nonvacuity") or {}
    for control in ("g3_control", "closure_control"):
        outcome = nonvacuity.get(control)
        if outcome is None:
            blocking.append(
                f"{control} NOT_RUN - the check it audits has not been shown capable "
                "of failing (SP11)"
            )
            continue
        status = outcome.get("status", NOT_RUN)
        if status != "PASS":
            blocking.append(
                f"{control} is {status} - the check it audits was NOT caught out by a "
                "corruption it must catch, so that check is vacuous (SP11)"
            )

    closure = payload.get("roundtrip_closure")
    if closure is None:
        blocking.append("round-trip closure NOT_RUN - the exported SEG-Y is unvalidated")
    elif closure.get("status") != "PASS":
        blocking.append(f"round-trip closure is {closure.get('status')}")

    if payload.get("lossy_codec_present"):
        blocking.append("a lossy codec is present")
    if payload.get("transform_scope_blocks_equivalence"):
        blocking.append("a declared transform is not provably invertible on this data")
    if payload.get("git", {}).get("dirty"):
        blocking.append("issued from a dirty working tree")

    return {
        "release_ready": not blocking,
        "blocking": blocking,
        "criterion": (
            "Both outputs fully validated: every gate PASS with none NOT_RUN, all five "
            "planes PASS, and the exported SEG-Y validated as an artifact in its own "
            "right by round-trip closure. See DECISIONS.md D-0031."
        ),
    }


def _verdict_reason(
    verdict: str,
    planes: dict[str, str],
    gates: dict[str, str],
    *,
    transform_blocked: bool = False,
    transform_reason: str = "",
) -> str:
    if verdict == "EQUIVALENT":
        return "All five planes PASS and G7 PASS."
    if transform_blocked:
        return f"PROVISIONAL. {transform_reason}"
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
        f"gates {', '.join(unrun_gates) or 'none'}. An unrun gate is not a passing one - "
        "it is recorded NOT_RUN here rather than assumed, and release_readiness treats "
        "every NOT_RUN as blocking (D-0031)."
    )


def _portable_headers(store: str | Path) -> bool:
    """Whether the store carries the ``uint8`` header plane a stock v3 reader can use.

    Recorded on every certificate, **including when it is False** (D-0063 ruling 3). A
    store SDIP did not write may legitimately carry none; that is not a failure, and a
    reader should be able to see it on the face of the certificate rather than infer it
    from an absent field.
    """
    try:
        import zarr

        from sdip.ingest.header_plane import ARRAY_NAME

        return ARRAY_NAME in zarr.open_group(str(store), mode="r")
    except (KeyError, ValueError, OSError):  # pragma: no cover - unreadable store
        return False


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
