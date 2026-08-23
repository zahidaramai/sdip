"""**Debt D17** — a textual header that cannot be decoded. Spec §4.2, §4.3, §7 G3.

    If bytes cannot be decoded, the raw 3200 bytes are preserved and the decode failure
    is recorded on the certificate. **Decode failure is not an ingestion failure; silent
    substitution is.**

D17 stood because neither upstream mode delivers that clause: mode 1 (STRICT) *raises*,
so the ingest is refused; mode 2 (LENIENT) *rewrites the header*, which §4.2 bars
outright (D-0020). SDIP took the safe half — refuse rather than corrupt — and the clause
went unsatisfied.

This module is the measurement behind ``DECISIONS.md`` D-0055. It is deliberately more
than a happy-path test of the fallback: it pins the **upstream behaviour** the fallback
is a response to, on both fixtures, so the day upstream's behaviour changes this file
fails instead of the fallback silently becoming unnecessary or wrong.

Every test here runs on N=1 non-conforming fixture of 12 traces, against the pinned
``multidimio`` 1.2.1 / ``segy`` 0.6.0. Nothing here is measured at survey scale.
"""

from __future__ import annotations

import base64
import json

import pytest
import zarr

from sdip.equivalence.certificate import issue
from sdip.equivalence.planes import plane_1, plane_2
from sdip.errors import RoundTripUnavailableError
from sdip.export import export
from sdip.ingest import ingest
from sdip.ingest.file_headers import (
    ATTR_RAW_TEXT,
    SAVE_FILE_HEADER_STRICT,
    UPSTREAM_FILE_HEADER_VARIABLE,
    classify_textual_header,
    file_headers_persisted,
    read_raw_file_headers,
    read_raw_textual_from_store,
)
from sdip.spec.generator import build_gap_free_spec
from tests.fixtures.generators import make_poststack3d
from tests.fixtures.generators.undecodable import (
    EXPECTED_OFFENDING_CELLS,
    make_undecodable_textual_header,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def article(tmp_path_factory):
    """One non-conforming source, ingested once. The store under test."""
    root = tmp_path_factory.mktemp("d17")
    source = make_undecodable_textual_header(root / "undecodable.sgy")
    result = ingest(source.path, root / "undecodable.mdio")
    return root, source, result


@pytest.fixture(scope="module")
def conforming(tmp_path_factory):
    """The control: the same article with its textual header left alone."""
    root = tmp_path_factory.mktemp("d17_ok")
    source = make_poststack3d(root / "ok.sgy", n_inline=3, n_crossline=4, n_samples=16)
    result = ingest(source.path, root / "ok.mdio")
    return root, source, result


# --- what upstream actually does, pinned ------------------------------------


def test_upstream_strict_mode_raises_on_this_fixture(tmp_path):
    """MODE 1. The measurement D17 rested on: upstream refuses the ingest.

    Asserted against the **public** entry point ``mdio.segy_to_mdio``, not against the
    validator, because the public entry point is the only surface SDIP is entitled to
    depend on (§3.3).
    """
    from mdio import segy_to_mdio
    from mdio.builder.template_registry import get_template

    source = make_undecodable_textual_header(tmp_path / "src.sgy")
    built = build_gap_free_spec(1)
    output = tmp_path / "strict.mdio"

    with file_headers_persisted(), pytest.raises(ValueError) as raised:
        segy_to_mdio(
            segy_spec=built.segy_spec,
            mdio_template=get_template("PostStack3DTime"),
            input_path=source.path,
            output_path=output,
            overwrite=True,
        )

    assert "Invalid text header characters" in str(raised.value)
    assert not output.exists(), (
        "upstream validates the text header before it initialises the Zarr store, so a "
        "refused ingest must leave nothing behind. A partial store here would mean the "
        "fallback has to clean up after it."
    )


def test_upstream_strict_mode_names_exactly_the_cells_sdip_names(tmp_path):
    """MODE 1's message and SDIP's classifier must agree, cell for cell.

    This is the drift check. SDIP decides the mode from its **own** predicate rather
    than by catching upstream's exception, so the two verdicts are independent — and an
    independent verdict that is never compared is an assumption. N=8 offending cells.
    """
    from mdio import segy_to_mdio
    from mdio.builder.template_registry import get_template

    source = make_undecodable_textual_header(tmp_path / "src.sgy")
    built = build_gap_free_spec(1)

    with file_headers_persisted(), pytest.raises(ValueError) as raised:
        segy_to_mdio(
            segy_spec=built.segy_spec,
            mdio_template=get_template("PostStack3DTime"),
            input_path=source.path,
            output_path=tmp_path / "strict.mdio",
            overwrite=True,
        )

    message = str(raised.value)
    decode = classify_textual_header(source.textual_header, built.segy_spec.text_header)
    assert decode.offending == EXPECTED_OFFENDING_CELLS
    for row, column in EXPECTED_OFFENDING_CELLS:
        assert f"row {row}: positions" in message
        assert str(column) in message.split(f"row {row}: positions")[1].split("]")[0]


def test_the_classifier_agrees_with_upstream_on_a_conforming_header(conforming):
    """The other direction of the same drift check.

    A predicate that says "undecodable" too readily would drop a perfectly good source
    into the lossy fallback and cost it its parsed headers and its export, silently.
    Measured by the ingest itself: a conforming source must run STRICT.
    """
    _root, _source, result = conforming
    assert result.textual_decode is not None
    assert result.textual_decode.decoded
    assert result.textual_decode.status == "decoded"
    assert result.textual_decode.offending == ()
    assert result.file_header_persistence == "strict"


def test_upstream_lenient_mode_would_rewrite_the_header(tmp_path, monkeypatch):
    """MODE 2, measured, so that "barred" is a finding and not an opinion.

    §4.2 bars silent substitution and D-0020 bars mode 2 on that basis. This runs it
    once, in a test and never in ``src``, and shows the substitution happening: the
    stored header is no longer the source's bytes.

    It also shows why mode 2 would not have rescued G3 either. Upstream's *exporter*
    sanitises anything that will not encode, so a store carrying the sanitised header
    exports 3200 bytes that are not the source's — a plausible file that fails the hash,
    which is strictly worse than a refusal.
    """
    from mdio import segy_to_mdio
    from mdio.builder.template_registry import get_template

    source = make_undecodable_textual_header(tmp_path / "src.sgy")
    built = build_gap_free_spec(1)
    output = tmp_path / "lenient.mdio"

    monkeypatch.setenv("MDIO__IMPORT__SAVE_SEGY_FILE_HEADER", "2")
    # Mode 2 logs a WARNING as it rewrites. `filterwarnings = ["error"]` governs the
    # warnings channel, not logging, so this is caught by reading the store instead.
    segy_to_mdio(
        segy_spec=built.segy_spec,
        mdio_template=get_template("PostStack3DTime"),
        input_path=source.path,
        output_path=output,
        overwrite=True,
    )

    stored = str(zarr.open_group(str(output), mode="r")["segy_file_header"].attrs["textHeader"])
    original = built.segy_spec.text_header.decode(source.textual_header)
    assert stored != original, "mode 2 must be shown substituting, or D-0020 has no basis"
    assert "�" not in stored, "mode 2 replaces the undecodable characters with spaces"
    assert "�" in original, "the source's decoded form does carry them"


# --- what SDIP does instead -------------------------------------------------


def test_the_ingest_completes(article):
    """§4.2: decode failure is not an ingestion failure. The half D17 was missing."""
    root, _source, result = article
    assert (root / "undecodable.mdio").is_dir()
    assert result.read_path_intact
    assert result.file_header_persistence == "off"


def test_the_decode_failure_is_measured_not_assumed(article):
    """The status on the certificate comes from this file's own 3200 bytes."""
    _root, source, result = article
    assert result.textual_decode is not None
    assert not result.textual_decode.decoded
    assert result.textual_decode.status == "raw_preserved_decode_failed"
    assert result.textual_decode.encoding == "ebcdic"
    assert result.textual_decode.offending == EXPECTED_OFFENDING_CELLS
    assert (
        classify_textual_header(source.textual_header, result.spec.segy_spec.text_header).offending
        == EXPECTED_OFFENDING_CELLS
    )


def test_the_store_carries_the_raw_bytes_verbatim(article):
    """§4.2's first requirement. Byte equality against the source, not a decode."""
    _root, source, result = article
    stored = read_raw_textual_from_store(result.output_path)
    assert stored == source.textual_header
    assert stored == read_raw_file_headers(source.path).textual
    assert stored != source.conforming_textual, (
        "the fixture must actually differ from the conforming article, or this test "
        "would pass on a file that was never corrupted"
    )


def test_plane_1_passes_against_the_raw_bytes(article):
    """G2a on a store upstream would not have written at all."""
    _root, source, result = article
    outcome = plane_1(source.path, result.output_path)
    assert outcome.passed, outcome.evidence
    assert outcome.evidence["first_difference"] is None
    assert outcome.evidence["n"] == 3200


def test_plane_2_passes_and_reports_the_missing_parsed_mapping(article):
    """G2b holds on the authoritative half; §4.3's *parsed mapping* half does not.

    Recorded rather than papered over. Mode 0 costs upstream's parsed ``binaryHeader``,
    and Plane 2's evidence is where a reader finds that out.
    """
    _root, source, result = article
    outcome = plane_2(source.path, result.output_path)
    assert outcome.passed, outcome.evidence
    assert outcome.evidence["parsed_mapping_present"] is False


def test_the_conforming_article_still_gets_the_parsed_mapping(conforming):
    """The control. Mode 0 must not leak onto a source that decodes."""
    _root, source, result = conforming
    outcome = plane_2(source.path, result.output_path)
    assert outcome.passed, outcome.evidence
    assert outcome.evidence["parsed_mapping_present"] is True
    assert UPSTREAM_FILE_HEADER_VARIABLE in zarr.open_group(str(result.output_path), mode="r")


def test_the_raw_attributes_live_on_the_root_group(article):
    """Where the bytes go when there is no ``segy_file_header`` to hang them on.

    Pinned because three things resolve this node independently — the writer, Plane 1's
    reader and G7's textual controls — and a disagreement between them is exactly the
    class of defect G7 caught on its first run (D-0028).
    """
    _root, source, result = article
    group = zarr.open_group(str(result.output_path), mode="r")
    assert UPSTREAM_FILE_HEADER_VARIABLE not in group
    assert base64.b64decode(str(dict(group.attrs)[ATTR_RAW_TEXT])) == source.textual_header


def test_the_environment_is_left_as_it_was_found(article, monkeypatch):
    """The mode is scoped to the call. A run must not reconfigure the process."""
    import os

    monkeypatch.setenv("MDIO__IMPORT__SAVE_SEGY_FILE_HEADER", SAVE_FILE_HEADER_STRICT)
    root, source, _result = article
    ingest(source.path, root / "scoped.mdio", overwrite=True)
    assert os.environ["MDIO__IMPORT__SAVE_SEGY_FILE_HEADER"] == SAVE_FILE_HEADER_STRICT


# --- what it costs, stated ---------------------------------------------------


def test_the_export_refuses_cleanly(article, tmp_path):
    """G3 is unreachable for this store, and says so as an SdipError.

    §11.4 requires a malformed source to produce a clean error rather than a crash. An
    upstream ``MDIOMissingVariableError`` about a missing variable is not that.
    """
    _root, source, result = article
    with pytest.raises(RoundTripUnavailableError) as raised:
        export(result.output_path, tmp_path / "out.sgy", result.spec.segy_spec, source=source.path)
    assert UPSTREAM_FILE_HEADER_VARIABLE in str(raised.value)
    assert "§4.2" in str(raised.value)


def test_the_certificate_carries_the_decode_status(article, tmp_path):
    """§4.7's ``detected_encoding`` block, and §4.2's *recorded on the certificate*."""
    _root, source, result = article
    certificate = issue(
        result,
        [plane_1(source.path, result.output_path), plane_2(source.path, result.output_path)],
        require_clean_tree=False,
        issued_at="2026-08-23T00:00:00+00:00",
        issued_by="test",
    )
    block = certificate.payload["detected_encoding"]
    assert block["decode_status"] == "raw_preserved_decode_failed"
    assert block["encoding"] == "ebcdic"
    assert "raw 3200 bytes are preserved" in block["detail"]
    assert certificate.verdict != "EQUIVALENT", (
        "a store that cannot round trip must not reach EQUIVALENT on planes alone"
    )


def test_the_certificate_still_validates_against_the_published_schema(article, repo_root):
    """The enum value was already in the schema; this is the check that it is reachable."""
    import jsonschema

    _root, source, result = article
    certificate = issue(
        result,
        [plane_1(source.path, result.output_path), plane_2(source.path, result.output_path)],
        require_clean_tree=False,
        issued_at="2026-08-23T00:00:00+00:00",
        issued_by="test",
    )
    schema = json.loads((repo_root / "src/sdip/schema/sdip-certificate-v0.schema.json").read_text())
    # `certify` refuses a dirty tree (§11.3), so a certificate in the wild was issued
    # from a clean one. This fixture bypasses that to run at all, and must not then
    # claim the schema is wrong for enforcing it - the same normalisation
    # `tests/integration/test_certificate_schema.py` makes, for the same reason.
    payload = certificate.payload
    payload["git"] = dict(payload["git"]) | {"dirty": False}
    jsonschema.validate(payload, schema)


def test_a_conforming_certificate_still_says_decoded(conforming):
    """The common path is unchanged, and is now measured rather than asserted."""
    _root, source, result = conforming
    certificate = issue(
        result,
        [plane_1(source.path, result.output_path)],
        require_clean_tree=False,
        issued_at="2026-08-23T00:00:00+00:00",
        issued_by="test",
    )
    assert certificate.payload["detected_encoding"]["decode_status"] == "decoded"
    assert certificate.payload["detected_encoding"]["encoding"] == "ebcdic"
