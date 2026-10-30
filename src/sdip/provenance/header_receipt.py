"""``sdip receipt``: the header evidence of a source, and of its store. ``DECISIONS.md`` D-0107.

A read-only report a consumer can attach to its own record: what the source's file headers
say, byte for byte, and whether a store still holds those headers and the content its
marker recorded. It is the evidence set of D-0104 and D-0105, produced by the executable
rather than by hand.

**It interprets nothing.** The ``mentions`` block is a mechanical keyword match on the
decoded cards, quoted verbatim, against lists fixed in D-0107; SDIP names no CRS, grades
nothing and states no EPSG code. ``not_stated`` is reliable only in the direction it is
named: no card contains any keyword for that topic.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
from pathlib import Path
from typing import Any, Final

SCHEMA: Final[str] = "sdip-header-receipt/1"

KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "datum": (
        "DATUM", "ED50", "ED-50", "WGS84", "WGS-84", "WGS 84", "ETRS89", "NAD27", "NAD83",
        "SPHEROID", "ELLIPSOID",
    ),
    "projection": ("PROJECTION", "UTM", "TRANSVERSE MERCATOR", "LAMBERT", "CRS"),
    "zone": ("ZONE",),
    "hemisphere": ("NORTH", "SOUTH"),
    "linear_units": ("METRE", "METRES", "METER", "METERS", "FEET", "FOOT", "FT"),
    "vertical_datum": (
        "MSL", "MEAN SEA LEVEL", "VERTICAL DATUM", "SEISMIC REFERENCE DATUM", "SRD",
    ),
}  # fmt: skip
"""Fixed by D-0107. Changing a list is a new schema version."""

_ZONE_LETTER = re.compile(r"\bZONE\s*:?\s*\d{1,2}\s*([NS])\b", re.IGNORECASE)

BINARY_FIELDS: Final[tuple[tuple[int, int, str], ...]] = (
    (3217, 2, "sample interval (us)"),
    (3221, 2, "samples per trace"),
    (3225, 2, "sample format code"),
    (3255, 2, "measurement system"),
    (3501, 2, "SEG-Y revision"),
    (3503, 2, "fixed-length trace flag"),
    (3505, 2, "extended textual headers"),
)
"""1-based file byte, width, name. Read big-endian, the standard's byte order."""

_MEASUREMENT: Final[dict[int, str]] = {1: "metres", 2: "feet"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _cards(raw: bytes, encoding: str) -> list[dict[str, Any]]:
    codec = "cp037" if encoding.lower().startswith("ebcdic") else "latin-1"
    text = raw.decode(codec)
    cards = []
    for row in range(40):
        line = text[row * 80 : (row + 1) * 80]
        bad = [
            {"column": col + 1, "byte": f"0x{raw[row * 80 + col]:02x}"}
            for col, ch in enumerate(line)
            if not 32 <= ord(ch) < 127
        ]
        shown = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in line).rstrip()
        cards.append({"card": row + 1, "text": shown, "nonprintable": bad})
    return cards


def _mentions(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for topic, words in KEYWORDS.items():
        pattern = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.I)
        hits = [
            {"card": c["card"], "text": c["text"]}
            for c in cards
            if pattern.search(c["text"])
            or (topic == "hemisphere" and _ZONE_LETTER.search(c["text"]))
        ]
        out[topic] = {"keywords": list(words), "cards": hits}
    return out


def _i16(blob: bytes, byte: int) -> int:
    return int.from_bytes(blob[byte - 1 : byte + 1], "big", signed=True)


def _i32(blob: bytes, byte: int) -> int:
    return int.from_bytes(blob[byte - 1 : byte + 3], "big", signed=True)


def _first_trace(source: Path, binary: bytes) -> dict[str, Any]:
    extended = _i16(binary, 3505 - 3200)
    if extended < 0:
        return {"read": False, "reason": "a variable number of extended textual headers"}
    offset = 3600 + extended * 3200
    with source.open("rb") as handle:
        handle.seek(offset)
        header = handle.read(240)
    if len(header) < 240:
        return {"read": False, "reason": "the file ends before a first trace header"}
    scalar = _i16(header, 71)
    factor = (1 / -scalar) if scalar < 0 else (scalar or 1)
    x, y = _i32(header, 181), _i32(header, 185)
    return {
        "read": True,
        "offset": offset,
        "coordinate_scalar_71_72": scalar,
        "coordinate_units_89_90": _i16(header, 89),
        "cdp_x_181_184": {"raw": x, "scaled": x * factor},
        "cdp_y_185_188": {"raw": y, "scaled": y * factor},
        "delay_109_110": _i16(header, 109),
        "inline_189_192": _i32(header, 189),
        "crossline_193_196": _i32(header, 193),
        "note": "inline and crossline at the SEG-Y rev 1 positions; a declaration may read others",
    }


def _store_block(store: Path, text_sha: str, binary_sha: str) -> dict[str, Any]:
    import zarr

    from sdip.provenance.git import repo_relative, repository_root
    from sdip.provenance.store_digest import check_content_digest, check_store_digest

    attrs = dict(zarr.open_group(str(store), mode="r").attrs)
    digest, content = check_store_digest(store), check_content_digest(store)
    recorded = (attrs.get("sdipRawTextHeaderSha256"), attrs.get("sdipRawBinaryHeaderSha256"))
    source_of_record = "marker sha256 attributes"
    if None in recorded:
        # A decodable source keeps its raw bytes on the header node, not hashes on the root.
        from sdip.errors import UntrustedInputError
        from sdip.ingest.file_headers import read_raw_file_headers_from_store

        try:
            held = read_raw_file_headers_from_store(store)
            recorded = (_sha256(held.textual), _sha256(held.binary))
            source_of_record = "raw bytes held on the store"
        except UntrustedInputError:  # absent or malformed raw bytes: reported, not raised
            source_of_record = "none"
    if None in recorded:
        bind = "ABSENT"
    else:
        bind = "MATCH" if recorded == (text_sha, binary_sha) else "MISMATCH"
    return {
        "path": str(store.resolve()),
        "path_repo_relative": repo_relative(store, repository_root(".")),
        "sdip_version": attrs.get("sdipVersion"),
        "store_digest": digest.to_json(),
        "content_digest": content.to_json(),
        "raw_headers_bind": {
            "status": bind,
            "recorded_text_sha256": recorded[0],
            "recorded_binary_sha256": recorded[1],
            "from": source_of_record,
        },
    }


def build_receipt(
    source: str | Path, text_spec: Any, store: str | Path | None = None
) -> dict[str, Any]:
    """The ``sdip-header-receipt/1`` receipt for ``source``, and ``store`` if given.

    Reads only. The caller runs the hostile-input preflight first (§3.6).
    """
    from sdip import __version__
    from sdip.ingest.file_headers import classify_textual_header, read_raw_file_headers
    from sdip.provenance.git import capture_git_state, repo_relative, repository_root

    source_path = Path(source).resolve()
    raw = read_raw_file_headers(source_path)
    decode = classify_textual_header(raw.textual, text_spec)
    cards = _cards(raw.textual, decode.encoding)
    mentions = _mentions(cards)
    measurement = _i16(raw.binary, 3255 - 3200)
    git = capture_git_state(".")
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "source": {
            "path": str(source_path),
            "path_repo_relative": repo_relative(source_path, repository_root(".")),
            "bytes": source_path.stat().st_size,
            "sha256": _file_sha256(source_path),
        },
        "textual_header": {
            "sha256": _sha256(raw.textual),
            "encoding": decode.encoding,
            "decode_status": decode.status,
            "cards": cards,
        },
        "binary_header": {
            "sha256": _sha256(raw.binary),
            "fields": [
                {
                    "bytes": f"{b}-{b + w - 1}",
                    "name": name,
                    "value": _i16(raw.binary, b - 3200),
                    "raw_hex": raw.binary[b - 3201 : b - 3201 + w].hex(),
                }
                for b, w, name in BINARY_FIELDS
            ],
            "measurement_system": _MEASUREMENT.get(measurement, "undeclared"),
        },
        "first_trace": _first_trace(source_path, raw.binary),
        "mentions": mentions,
        "not_stated": [topic for topic, m in mentions.items() if not m["cards"]],
        "issued": {
            "sdip_version": __version__,
            "sdip_commit": git.commit,
            "dirty": git.dirty,
            "at": _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds"),
        },
    }
    if store is not None:
        receipt["store"] = _store_block(
            Path(store), receipt["textual_header"]["sha256"], receipt["binary_header"]["sha256"]
        )
    return receipt


def receipt_ok(receipt: dict[str, Any]) -> bool:
    """Exit 0 only when, with a store, neither digest mismatches and the raw headers bind."""
    store = receipt.get("store")
    if store is None:
        return True
    digests_ok = all(
        store[k]["status"] in ("MATCH", "ABSENT") for k in ("store_digest", "content_digest")
    )
    return digests_ok and store["raw_headers_bind"]["status"] == "MATCH"


def to_markdown(receipt: dict[str, Any]) -> str:
    """The same receipt as Markdown: every value the JSON carries, nothing added."""
    src, text, binary = receipt["source"], receipt["textual_header"], receipt["binary_header"]
    lines = [
        f"# Header receipt — `{Path(src['path']).name}`",
        "",
        f"Schema `{receipt['schema']}` · sdip {receipt['issued']['sdip_version']} at "
        f"`{receipt['issued']['sdip_commit']}` (dirty: {receipt['issued']['dirty']}) · "
        f"{receipt['issued']['at']}",
        "",
        "## Source",
        "",
        f"- path: `{src['path']}` (repo-relative: `{src['path_repo_relative']}`)",
        f"- bytes: {src['bytes']:,}",
        f"- sha256: `{src['sha256']}`",
        "",
        "## Textual header (bytes 1-3200)",
        "",
        f"sha256 `{text['sha256']}` · encoding {text['encoding']} · {text['decode_status']}",
        "",
        "```",
        *[f"{c['card']:02d}| {c['text']}" for c in text["cards"]],
        "```",
        "",
    ]
    marks = [(c["card"], b) for c in text["cards"] for b in c["nonprintable"]]
    lines += [
        f"Non-printable: card {card} column {b['column']} raw {b['byte']} (shown `?`)"
        for card, b in marks
    ] or ["Non-printable: none"]
    lines += [
        "",
        "## Binary header (bytes 3201-3600)",
        "",
        f"sha256 `{binary['sha256']}` · measurement system: **{binary['measurement_system']}**",
        "",
        "| Bytes | Field | Value | Raw |",
        "|---|---|---|---|",
        *[
            f"| {f['bytes']} | {f['name']} | {f['value']} | `{f['raw_hex']}` |"
            for f in binary["fields"]
        ],
        "",
        "## First trace header",
        "",
        "```",
        *[f"{k}: {v}" for k, v in receipt["first_trace"].items()],
        "```",
        "",
        "## Mentions (keyword match, not interpretation)",
        "",
    ]
    for topic, m in receipt["mentions"].items():
        cards = "; ".join(f"card {c['card']}: `{c['text']}`" for c in m["cards"]) or "none"
        lines.append(f"- **{topic}**: {cards}")
    lines += ["", f"**No card mentions:** {', '.join(receipt['not_stated']) or 'nothing listed'}"]
    store = receipt.get("store")
    if store:
        lines += [
            "",
            "## Store",
            "",
            f"- path: `{store['path']}` (repo-relative: `{store['path_repo_relative']}`)",
            f"- sdip version: {store['sdip_version']}",
            f"- store digest: {store['store_digest']['status']} "
            f"`{store['store_digest']['computed_sha256']}`",
            f"- content digest: {store['content_digest']['status']} "
            f"`{store['content_digest']['computed_sha256']}`",
            f"- raw headers bind to the source: **{store['raw_headers_bind']['status']}**",
        ]
    return "\n".join(lines) + "\n"
