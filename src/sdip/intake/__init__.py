"""Intake readers: seismic files dropped into the GeoSuite chat, QC'd from their headers.

Each reader emits one ``geosuite.intake.v1`` ``reader_report`` per file (the contract is
GeoGIS's; :mod:`sdip.intake.report` copies its rules). Nothing here ingests, converts or
deletes: a report says what the file is, what is wrong with it, what must be asked of the
user, and the route into an MDIO store through ``sdip ingest``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sdip.intake.report import DEFAULT_CLASS

__all__ = ["file_sha256", "qc_file"]


def file_sha256(path: str | Path) -> str:
    """Streamed sha256 of a whole file (custody, not QC: not counted against the header budget)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def qc_file(
    path: str | Path,
    *,
    upload_id: str,
    member: str,
    sha256: str | None = None,
    cls: str = DEFAULT_CLASS,
    cluster_markers: tuple[str, ...] = (),
    commit: str | None = None,
) -> Any:
    """Detect the seismic format by content and run its reader. Returns an ``Outcome``."""
    from sdip.intake.resqml import is_epc, qc_resqml
    from sdip.intake.segd import is_segd, qc_segd
    from sdip.intake.segy import qc_segy
    from sdip.intake.vds import is_vds, qc_vds
    from sdip.intake.zgy import is_zgy, qc_zgy

    digest = sha256 or file_sha256(path)
    with Path(path).open("rb") as handle:
        head = handle.read(32)
    if is_zgy(head):
        return qc_zgy(
            path, upload_id=upload_id, member=member, sha256=digest, cls=cls, commit=commit
        )
    if is_vds(head):
        return qc_vds(
            path, upload_id=upload_id, member=member, sha256=digest, cls=cls, commit=commit
        )
    if is_epc(path, head):
        return qc_resqml(
            path, upload_id=upload_id, member=member, sha256=digest, cls=cls, commit=commit
        )
    if is_segd(head):
        return qc_segd(
            path, upload_id=upload_id, member=member, sha256=digest, cls=cls, commit=commit
        )
    return qc_segy(
        path,
        upload_id=upload_id,
        member=member,
        sha256=digest,
        cls=cls,
        cluster_markers=cluster_markers,
        commit=commit,
    )
