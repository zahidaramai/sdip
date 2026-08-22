"""File-header capture. Planes 1 and 2 depend on this being right.

These pin the three measured upstream facts recorded in DECISIONS.md. A pin bump that
changes any of them fails here, which is the point.
"""

from __future__ import annotations

import os

import pytest

from sdip.errors import UntrustedInputError
from sdip.ingest.file_headers import (
    SAVE_FILE_HEADER_STRICT,
    SAVE_FILE_HEADER_VAR,
    RawFileHeaders,
    file_headers_persisted,
    read_raw_file_headers,
)
from tests.fixtures.generators import make_poststack3d


def test_mdio_discards_both_file_headers_by_default():
    """MEASURED. The default is OFF, which is why SDIP has to set it.

    If upstream ever changes this default, this fails and the reasoning in
    ``file_headers.py`` must be re-read rather than assumed still necessary.
    """
    from mdio.core.config import MDIOSettings

    assert MDIOSettings().save_segy_file_header == 0


def test_raw_binary_header_is_gated_on_a_barred_variable():
    """MEASURED. §4.3's raw bytes are unreachable through MDIO without violating §9.1.

    ``rawBinaryHeader`` is written only when ``settings.raw_headers`` is set, and that
    is ``MDIO__IMPORT__RAW_HEADERS`` - barred. Hence SDIP reads the bytes itself.
    """
    import inspect

    from mdio.core.config import MDIOSettings
    from mdio.ingestion.segy import file_headers as upstream

    source = inspect.getsource(upstream)
    assert "if settings.raw_headers:" in source
    assert "rawBinaryHeader" in source
    field = MDIOSettings.model_fields["raw_headers"]
    assert field.alias == "MDIO__IMPORT__RAW_HEADERS"


def test_lenient_mode_rewrites_the_text_header():
    """MEASURED. Why SDIP uses mode 1 and never mode 2.

    §4.2: "Decode failure is not an ingestion failure; silent substitution is."
    """
    from mdio.segy.text_header import sanitize_text_header

    mangled = "C 1 \x00\x01BAD"
    assert "\x00" not in sanitize_text_header(mangled)


def test_sdip_uses_strict_mode_never_lenient():
    assert SAVE_FILE_HEADER_STRICT == "1"


def test_the_setting_is_scoped_and_restored(monkeypatch):
    """SDIP does not leave the process configured differently from how it found it."""
    monkeypatch.delenv(SAVE_FILE_HEADER_VAR, raising=False)
    with file_headers_persisted():
        assert os.environ[SAVE_FILE_HEADER_VAR] == SAVE_FILE_HEADER_STRICT
    assert SAVE_FILE_HEADER_VAR not in os.environ


def test_an_existing_value_is_restored_not_clobbered(monkeypatch):
    monkeypatch.setenv(SAVE_FILE_HEADER_VAR, "2")
    with file_headers_persisted():
        assert os.environ[SAVE_FILE_HEADER_VAR] == "1"
    assert os.environ[SAVE_FILE_HEADER_VAR] == "2"


def test_the_variable_sdip_sets_is_not_barred():
    """The distinction is the direction of travel, and it must stay true."""
    from sdip._pins import BARRED_ENV_VARS

    assert SAVE_FILE_HEADER_VAR not in BARRED_ENV_VARS


def test_raw_headers_are_read_at_fixed_offsets(tmp_path):
    article = make_poststack3d(tmp_path / "a.sgy")
    headers = read_raw_file_headers(article.path)
    assert headers.textual == article.textual_header
    assert headers.binary == article.binary_header
    assert len(headers.textual) == 3200
    assert len(headers.binary) == 400


def test_wrong_sized_headers_are_refused():
    """NEGATIVE CONTROL: the sizes are mandated, not advisory."""
    with pytest.raises(UntrustedInputError, match="textual header is 10 bytes"):
        RawFileHeaders(textual=b"x" * 10, binary=b"y" * 400)
    with pytest.raises(UntrustedInputError, match="binary header is 4 bytes"):
        RawFileHeaders(textual=b"x" * 3200, binary=b"yyyy")


def test_digests_are_recorded_not_the_bytes(tmp_path):
    """A certificate carries evidence, not a copy of the source."""
    payload = read_raw_file_headers(make_poststack3d(tmp_path / "a.sgy").path).to_json()
    assert set(payload) == {
        "textual_bytes",
        "textual_sha256",
        "binary_bytes",
        "binary_sha256",
    }
    assert len(payload["textual_sha256"]) == 64
