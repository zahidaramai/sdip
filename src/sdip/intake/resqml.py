"""Intake QC of one RESQML package (``.epc``: an Open Packaging zip of XML parts plus HDF5 arrays).

Reads the zip's central directory and the XML parts (bounded), never an HDF5 array. Checks:

- the package is safe to open: no absolute or ``..`` member path (``PATH_TRAVERSAL``), no
  symbolic link (``SYMLINK``), no decompression bomb (``ARCHIVE_BOMB``), no DTD or entity in any
  XML part (``XML_ENTITY``), all refused before any XML is parsed;
- what it holds: RESQML version, objects by type (IJK grids and their cell counts, 2D-grid and
  triangulated surfaces, horizon and fault interpretations, wellbore trajectories, properties,
  seismic lattices and lines);
- the local CRS objects: a stated EPSG code is reported as stated; an unknown or local-authority
  projected CRS is asked (``CRS_UNRESOLVED``), never inferred; units and the time or depth domain
  come from the CRS objects themselves;
- the HDF5 companions the package names: present beside it in the upload, and starting with the
  HDF5 signature; a missing companion leaves the arrays unreadable (``SDIP_RESQML_HDF5_MISSING``);
- references to objects the package does not hold (counted, information).
"""

from __future__ import annotations

import re
import stat
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Final
from xml.etree import ElementTree as ET

from sdip.intake import report as rpt
from sdip.intake.segy import Outcome

TOOL: Final[str] = "sdip.intake.resqml"
HEADER_BUDGET: Final[int] = 16 << 20
MAX_MEMBERS: Final[int] = 20000
MAX_PART: Final[int] = 4 << 20
MAX_TOTAL_UNCOMPRESSED: Final[int] = 1 << 30
MAX_RATIO: Final[int] = 200
HDF5_SIGNATURE: Final[bytes] = b"\x89HDF\r\n\x1a\n"
TYPE_RE: Final = re.compile(r"type=obj_(\w+)")
VERSION_RE: Final = re.compile(r"x-resqml\+xml;version=([0-9.]+)")
UUID_RE: Final = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "ijk_grids": ("IjkGridRepresentation",),
    "grid_surfaces": ("Grid2dRepresentation",),
    "triangulated_surfaces": ("TriangulatedSetRepresentation",),
    "horizons": ("HorizonInterpretation", "GeneticBoundaryFeature"),
    "faults": ("FaultInterpretation", "TectonicBoundaryFeature"),
    "wellbore_trajectories": ("WellboreTrajectoryRepresentation",),
    "properties": (
        "ContinuousProperty",
        "DiscreteProperty",
        "CategoricalProperty",
        "PointsProperty",
    ),
    "seismic_surveys": ("SeismicLatticeFeature", "SeismicLineFeature", "SeismicLineSetFeature"),
    "local_crs": ("LocalDepth3dCrs", "LocalTime3dCrs"),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def is_epc(path: str | Path, head: bytes) -> bool:
    """A zip whose content types declare a RESQML part."""
    if not head.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(path) as z:
            info = z.getinfo("[Content_Types].xml")
            if info.file_size > MAX_PART:
                return False
            return b"x-resqml+xml" in z.read(info)
    except (zipfile.BadZipFile, KeyError, OSError, NotImplementedError, RuntimeError):
        return False


def qc_resqml(
    path: str | Path,
    *,
    upload_id: str,
    member: str,
    sha256: str,
    cls: str = rpt.DEFAULT_CLASS,
    commit: str | None = None,
) -> Outcome:
    """Header-only intake QC of one RESQML package. Never raises on file content."""
    path = Path(path)
    size = path.stat().st_size
    findings: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    detail: dict[str, Any] = {"member": member, "class": cls, "kind": "resqml"}
    commit = commit or rpt.reader_commit()
    structural: dict[str, Any] = {
        "format": "resqml-epc",
        "version": None,
        "counts": counts,
        "hasCrs": None,
        "hasUnits": None,
        "hasNulls": None,
        "domain": "unknown",
    }
    detect: dict[str, Any] = {"format": "resqml-epc", "by": f"{TOOL}@{commit[:12]}"}
    read = [0]

    def done() -> Outcome:
        rep = rpt.reader_report(
            upload_id=upload_id,
            member=member,
            sha256=sha256,
            nbytes=size,
            cls=cls,
            detect=detect,
            tool=TOOL,
            commit=commit,
            structural=structural,
            findings=findings,
            questions=questions,
            header_bytes_read=read[0],
            header_budget=HEADER_BUDGET,
        )
        return Outcome(rep, detail)

    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        detect["format"] = structural["format"] = "unknown"
        findings.append(
            rpt.finding("UNSUPPORTED_FORMAT", "refuse", f"not a readable zip package: {exc}"[:300])
        )
        return done()
    with z:
        infos = z.infolist()
        read[0] += min(
            size, 22 + 46 * len(infos)
        )  # end record and central directory, approximately
        if cls == "cluster-derived":
            findings.append(
                rpt.finding(
                    "CLUSTER_RAW_REFUSED",
                    "refuse",
                    "the upload is classed cluster-derived; it is deleted and only its hash "
                    "and size are kept",
                )
            )
            return done()
        # Safety, before any XML is parsed.
        if len(infos) > MAX_MEMBERS:
            findings.append(
                rpt.finding("ARCHIVE_BOMB", "refuse", f"{len(infos)} members (limit {MAX_MEMBERS})")
            )
            return done()
        for info in infos:
            posix = PurePosixPath(info.filename)
            if (
                posix.is_absolute()
                or ".." in posix.parts
                or "\\" in info.filename
                or ":" in info.filename
            ):
                findings.append(
                    rpt.finding("PATH_TRAVERSAL", "refuse", "a member path leaves the package")
                )
                return done()
            if stat.S_ISLNK(info.external_attr >> 16):
                findings.append(rpt.finding("SYMLINK", "refuse", "a member is a symbolic link"))
                return done()
        total = sum(i.file_size for i in infos)
        packed = sum(i.compress_size for i in infos) or 1
        if total > MAX_TOTAL_UNCOMPRESSED or total / packed > MAX_RATIO:
            findings.append(
                rpt.finding(
                    "ARCHIVE_BOMB",
                    "refuse",
                    f"{total} bytes uncompressed from {packed} (ratio {total / packed:.0f})",
                )
            )
            return done()

        def part(info: zipfile.ZipInfo) -> bytes | None:
            if info.file_size > MAX_PART or read[0] + info.file_size > HEADER_BUDGET:
                return None
            data = z.read(info)
            read[0] += len(data)
            return data

        xml_parts: dict[str, bytes] = {}
        skipped = 0
        for info in infos:
            if info.filename.endswith((".xml", ".rels")):
                data = part(info)
                if data is None:
                    skipped += 1
                    continue
                if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                    findings.append(
                        rpt.finding(
                            "XML_ENTITY",
                            "refuse",
                            "an XML part declares a DTD or an entity; not parsed",
                        )
                    )
                    return done()
                xml_parts[info.filename] = data
        if skipped:
            findings.append(
                rpt.finding(
                    "HEADER_BUDGET",
                    "info",
                    f"{skipped} XML parts over the size budget were not read",
                )
            )

        ct = xml_parts.get("[Content_Types].xml", b"").decode("utf-8", "replace")
        versions = sorted(set(VERSION_RE.findall(ct)))
        types = Counter(TYPE_RE.findall(ct))
        detail["types"] = dict(types)
        if not versions:
            detect["format"] = structural["format"] = "unknown"
            findings.append(
                rpt.finding("UNSUPPORTED_FORMAT", "refuse", "a zip with no RESQML part")
            )
            return done()
        structural["version"] = versions[-1]
        detect["version"] = versions[-1]
        detect["evidence"] = f"[Content_Types].xml declares RESQML {', '.join(versions)}"
        suffix = Path(member).suffix.lower()
        if suffix and suffix != ".epc":
            detect["contradiction"] = f"extension {suffix}; content is a RESQML package"
            findings.append(
                rpt.finding(
                    "EXTENSION_CONTRADICTION", "info", f"the extension {suffix} is not .epc"
                )
            )
        counts["objects"] = sum(types.values())
        for group, names in GROUPS.items():
            n = sum(types.get(t, 0) for t in names)
            if n:
                counts[group] = n

        # Parse the XML parts (DTD-free, bounded).
        trees: dict[str, ET.Element] = {}
        for name, data in xml_parts.items():
            try:
                trees[name] = ET.fromstring(data)  # noqa: S314 - DTDs and entities refused above
            except ET.ParseError as exc:
                findings.append(
                    rpt.finding(
                        "HEADER_INVALID",
                        "quarantine",
                        f"XML part {name[:80]} does not parse: {exc}"[:300],
                    )
                )
        cells = 0
        for name, root in trees.items():
            if "IjkGridRepresentation" in name and not name.endswith(".rels"):
                dims = {_local(e.tag): e.text for e in root if _local(e.tag) in ("Ni", "Nj", "Nk")}
                try:
                    cells += int(dims["Ni"]) * int(dims["Nj"]) * int(dims["Nk"])  # type: ignore[arg-type]
                except (KeyError, TypeError, ValueError):
                    findings.append(
                        rpt.finding(
                            "HEADER_INVALID", "quarantine", "an IJK grid without Ni, Nj, Nk"
                        )
                    )
        if cells:
            counts["grid_cells"] = cells

        # Local CRS objects: stated, asked, never inferred.
        crs_rows, epsg, local_names, domains, units_ok = [], [], [], set(), True
        for name, root in trees.items():
            kind = next((k for k in ("LocalDepth3dCrs", "LocalTime3dCrs") if k in name), None)
            if kind is None or name.endswith(".rels"):
                continue
            domains.add("depth" if kind == "LocalDepth3dCrs" else "time")
            fields = {_local(e.tag): e for e in root.iter()}
            title = fields.get("Title")
            projected = fields.get("ProjectedCrs")
            p_type = (
                projected.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
                if projected is not None
                else ""
            )
            code = fields.get("EpsgCode")
            if code is not None and code.text and code.text.strip().isdigit():
                epsg.append(code.text.strip())
            elif "LocalAuthority" in p_type and fields.get("LocalAuthorityCrsName") is not None:
                local_names.append((fields["LocalAuthorityCrsName"].text or "").strip())
            if not all(
                fields.get(k) is not None and (fields[k].text or "").strip()
                for k in ("ProjectedUom", "VerticalUom")
            ):
                units_ok = False
            crs_rows.append(
                {
                    "kind": kind,
                    "title": title.text if title is not None else "",
                    "projected": p_type,
                }
            )
        detail["crs"] = crs_rows
        structural["hasUnits"] = bool(crs_rows) and units_ok
        structural["domain"] = domains.pop() if len(domains) == 1 else "unknown"
        if len(crs_rows) and not units_ok:
            questions.append(
                rpt.question(
                    "UNITS_AMBIGUOUS",
                    "A local CRS in the package does not state its horizontal or vertical "
                    "unit. Which is it?",
                    [{"id": "m", "label": "metres"}, {"id": "ft", "label": "feet"}],
                    subject="local CRS",
                )
            )
        if epsg:
            structural["hasCrs"] = True
            findings.append(
                rpt.finding(
                    "SDIP_RESQML_CRS_STATED",
                    "info",
                    f"the package states EPSG:{', EPSG:'.join(sorted(set(epsg)))}",
                )
            )
        elif crs_rows:
            structural["hasCrs"] = bool(local_names)
            choices = [
                {"id": f"cand{i}", "label": n[:200], "source": "RESQML local authority CRS name"}
                for i, n in enumerate(local_names)
            ]
            choices += [
                {"id": "epsg", "label": "Enter an EPSG code"},
                {"id": "unknown", "label": "I don't know"},
            ]
            questions.append(
                rpt.question(
                    "CRS_UNRESOLVED",
                    "The package's local CRS names no EPSG projected CRS. Which coordinate "
                    "system is it in?",
                    choices,
                    subject="RESQML local CRS",
                )
            )
        else:
            structural["hasCrs"] = False
            findings.append(
                rpt.finding("SDIP_RESQML_NO_CRS", "info", "the package holds no local CRS object")
            )

        # HDF5 companions.
        externals = set()
        for name, root in trees.items():
            if name.endswith(".rels"):
                for rel in root:
                    if rel.get("TargetMode") == "External" and rel.get("Target"):
                        externals.add(rel.get("Target", ""))
        missing, bad = [], []
        for target in sorted(externals):
            leaf = PurePosixPath(target.replace("\\", "/")).name
            companion = path.parent / leaf
            if not leaf.lower().endswith((".h5", ".hdf5")) or not companion.is_file():
                missing.append(leaf)
                continue
            with companion.open("rb") as handle:
                sig = handle.read(8)
            read[0] += len(sig)
            if sig != HDF5_SIGNATURE:
                bad.append(leaf)
        counts["hdf_companions"] = len(externals)
        detail["hdf5"] = {"named": sorted(externals), "missing": missing, "not hdf5": bad}
        if missing:
            findings.append(
                rpt.finding(
                    "SDIP_RESQML_HDF5_MISSING",
                    "quarantine",
                    f"{len(missing)} of {len(externals)} HDF5 companions the package names are not "
                    "beside it in the upload; its arrays cannot be read",
                )
            )
        if bad:
            findings.append(
                rpt.finding(
                    "HEADER_INVALID",
                    "quarantine",
                    f"{len(bad)} HDF5 companions do not start with the HDF5 signature",
                )
            )

        # References to objects the package does not hold.
        held = {m.group(0).lower() for n in xml_parts for m in [UUID_RE.search(n)] if m}
        referenced: set[str] = set()
        for name, root in trees.items():
            if name.endswith(".rels") or name.startswith("[") or "docProps" in name:
                continue
            for e in root.iter():
                if _local(e.tag) == "UUID" and e.text:
                    referenced.add(e.text.strip().lower())
        dangling = len(referenced - held)
        counts["dangling_references"] = dangling
        if dangling:
            findings.append(
                rpt.finding(
                    "SDIP_RESQML_DANGLING_REFS",
                    "info",
                    f"{dangling} referenced objects are not in this package",
                )
            )
        findings.append(
            rpt.finding(
                "SDIP_GEOMETRY",
                "info",
                "RESQML package: "
                + ", ".join(f"{v} {k}" for k, v in counts.items() if k in GROUPS)
                + f"; {cells} grid cells",
            )
        )
        findings.append(
            rpt.finding(
                "SDIP_NO_MDIO_ROUTE",
                "info",
                "SDIP stores seismic traces only: grids and surfaces go to the engines that "
                "read RESQML",
            )
        )
    return done()
