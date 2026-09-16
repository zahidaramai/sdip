"""Binding upstream pins and barred bindings. Specification v1.0 sections 3.3 and 9.

This module is the single source of truth for every value CI and ``sdip doctor``
assert against. It imports nothing outside the standard library so that
``sdip doctor`` can report a broken environment rather than fail to start in one.

Changing anything here is a maintainer decision that must be recorded in
``DECISIONS.md`` (spec section 12.1). A pin bump invalidates every certificate
issued under the previous pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

SPEC_VERSION: Final[str] = "1.0"
"""Version of the SDIP Specification this code implements."""

CERTIFICATE_SCHEMA_VERSION: Final[str] = "0"
"""Certificate schema version. Versioned independently of the software (spec 4.7)."""


@dataclass(frozen=True, slots=True)
class Pin:
    """An exact upstream pin: version, its release tag, and the commit that tag points at.

    **The SHA is the commit the release tag points at, and nothing else (D-0087).** Until
    D-0087 both SHAs here were one commit PAST their tags - ``a2895b53`` adds a CRG template
    after mdio v1.2.1, ``8e93e97d`` changes segy's inference and file code after v0.6.0 -
    and the installed wheels contain neither change, so every certificate named code that
    had not run. A wheel does not carry the SHA it was built from, so this stays
    declared rather than runtime-verified (D9); ``release_tag`` is recorded so anyone can
    check it with ``git rev-parse <release_tag>^{commit}`` in the upstream repository.
    """

    distribution: str
    version: str
    commit_sha: str
    repository: str
    release_tag: str


PINS: Final[tuple[Pin, ...]] = (
    Pin(
        distribution="multidimio",
        version="1.2.1",
        commit_sha="76df396e545017d2a32ee25a5f98989fa37afec4",
        repository="https://github.com/TGSAI/mdio-python",
        release_tag="v1.2.1",
    ),
    Pin(
        distribution="segy",
        version="0.6.0",
        commit_sha="557bceba4abce09d084a1f0b8ac466382ce5c502",
        repository="https://github.com/TGSAI/segy",
        release_tag="v0.6.0",
    ),
)

BAR: Final[str] = "bar"
"""Changes how the source is read, what the store contains, or what upstream accepts."""
RECORD: Final[str] = "record"
"""Changes nothing read or written, but is part of reproducing a run; recorded (§3.4)."""
ALLOW: Final[str] = "allow"
"""Cannot change a byte read or written, or is set by SDIP itself around every call."""


@dataclass(frozen=True, slots=True)
class UpstreamSetting:
    """One environment variable the pinned upstream reads, and what SDIP does about it."""

    model: str
    field: str
    env: str
    case_sensitive: bool
    action: str
    reason: str


UPSTREAM_SETTINGS: Final[tuple[UpstreamSetting, ...]] = (
    UpstreamSetting(
        "segy.config.SegyFileSettings",
        "endianness",
        "SEGY_ENDIANNESS",
        False,
        BAR,
        "Overrides the byte order a survey declaration states, from outside the "
        "declaration, so the store and its certificate would describe a reading nobody "
        "declared (D-0087).",
    ),
    UpstreamSetting(
        "segy.config.SegyFileSettings",
        "storage_options",
        "SEGY_STORAGE_OPTIONS",
        False,
        ALLOW,
        "fsspec options for remote paths. SDIP refuses every URI scheme (D7), so they "
        "cannot reach a byte SDIP reads.",
    ),
    UpstreamSetting(
        "segy.config.SegyHeaderOverrides",
        "binary_header",
        "SEGY_OVERRIDE_BINARY_HEADER",
        False,
        BAR,
        "Rewrites binary-header values before the decode is chosen. MEASURED: set during "
        "ingest and verify, 191 of 192 stored samples were wrong and sdip verify "
        "reported every plane PASS - a false PASS, because writer and verifier read the "
        "source the same wrong way (D-0087).",
    ),
    UpstreamSetting(
        "segy.config.SegyHeaderOverrides",
        "trace_header",
        "SEGY_OVERRIDE_TRACE_HEADER",
        False,
        BAR,
        "Rewrites trace-header values, and upstream writes them into the store as though "
        "they were read from the file. Header content that did not come from the source "
        "is fabrication (SP12).",
    ),
    UpstreamSetting(
        "mdio.core.config.MDIOSettings",
        "export_cpus",
        "MDIO__EXPORT__CPU_COUNT",
        True,
        RECORD,
        "Export worker count. Worker counts are part of reproducing a run and are "
        "recorded on the certificate (spec 3.4).",
    ),
    UpstreamSetting(
        "mdio.core.config.MDIOSettings",
        "import_cpus",
        "MDIO__IMPORT__CPU_COUNT",
        True,
        RECORD,
        "Import worker count. Worker counts are part of reproducing a run and are "
        "recorded on the certificate (spec 3.4).",
    ),
    UpstreamSetting(
        "mdio.core.config.MDIOSettings",
        "grid_sparsity_ratio_warn",
        "MDIO__GRID__SPARSITY_RATIO_WARN",
        True,
        BAR,
        "Raising it silences upstream's sparse-grid warning. SDIP records every warning a "
        "run emits and suppresses none (SP6); a threshold moved from the environment is "
        "a suppression.",
    ),
    UpstreamSetting(
        "mdio.core.config.MDIOSettings",
        "grid_sparsity_ratio_limit",
        "MDIO__GRID__SPARSITY_RATIO_LIMIT",
        True,
        BAR,
        "Moves the sparsity refusal OPEN_DEBTS D30 records as a hard limit whose only "
        "route past is the barred MDIO_IGNORE_CHECKS. Raising it is the same bypass under "
        "another name.",
    ),
    UpstreamSetting(
        "mdio.core.config.MDIOSettings",
        "save_segy_file_header",
        "MDIO__IMPORT__SAVE_SEGY_FILE_HEADER",
        True,
        ALLOW,
        "Set by SDIP itself around every upstream import call and restored afterwards "
        "(file_headers.py, D-0055), so an operator's value never reaches upstream.",
    ),
    UpstreamSetting(
        "mdio.core.config.MDIOSettings",
        "raw_headers",
        "MDIO__IMPORT__RAW_HEADERS",
        True,
        BAR,
        "Deprecated upstream for removal in 1.4. SDIP reaches full 240-byte header "
        "persistence through the public API instead (spec 3.2); depending on this "
        "flag is a specification violation even though it looks helpful.",
    ),
    UpstreamSetting(
        "mdio.core.config.MDIOSettings",
        "cloud_native",
        "MDIO__IMPORT__CLOUD_NATIVE",
        True,
        BAR,
        "Switches upstream to a different ingest mode that no SDIP gate, probe or "
        "certificate has ever measured.",
    ),
    UpstreamSetting(
        "mdio.core.config.MDIOSettings",
        "ignore_checks",
        "MDIO_IGNORE_CHECKS",
        True,
        BAR,
        "Demotes the MDIO grid-sparsity error to a log line. A suppressible gate is "
        "not a gate (SP11).",
    ),
)
"""Every environment variable the pinned upstream reads (D-0087, amending spec 9.1).

Hand-written so that importing SDIP never imports MDIO. It cannot drift silently:
``tests/unit/test_upstream_settings.py`` and ``sdip doctor`` both compare it against what
the installed upstream actually defines, and the tests set each variable to prove the
name and its case sensitivity are real.
"""

BARRED_ENV_VARS: Final[dict[str, str]] = {
    s.env: s.reason for s in UPSTREAM_SETTINGS if s.action == BAR
}
"""Environment variables that must be absent. Spec section 9.1, as amended by D-0087."""

RECORDED_ENV_VARS: Final[dict[str, str]] = {
    s.env: s.reason for s in UPSTREAM_SETTINGS if s.action == RECORD
}
"""Environment variables recorded on the certificate when set (spec 3.4)."""

BARRED_MODULES: Final[dict[str, str]] = {
    "zfpy": (
        "Lossy codec. SP3 permits Blosc family and Zstd only. The multidimio[lossy] "
        "extra must not be present in an SDIP environment."
    ),
}
"""Top-level modules that must not be importable. Spec section 9.2."""

BARRED_EXTRAS: Final[dict[str, str]] = {
    "multidimio[lossy]": "Pulls zfpy. Barred by SP3 / spec section 9.2.",
}

BARRED_LICENCE_SUBSTRINGS: Final[tuple[str, ...]] = (
    "GPL",
    "AGPL",
)
"""Copyleft markers barred from the runtime dependency tree. Spec sections 3.6 / 9.4.

Matching is substring-based and deliberately over-inclusive; LGPL and any
``GNU General Public License`` spelling are caught. Allowances are explicit and
listed in ``LICENCE_ALLOWLIST`` with a recorded reason.
"""

LICENCE_ALLOWLIST: Final[dict[str, str]] = {
    "google-crc32c": (
        "UNDETERMINED by metadata: google-crc32c 1.8.0 ships no License-Expression, "
        "no License:: classifier, and no License field. Evidence: the wheel bundles "
        "google_crc32c-*.dist-info/licenses/LICENSE, which is the verbatim Apache "
        "License 2.0, and Author is 'Google LLC' with Home-page "
        "https://github.com/googleapis/python-crc32c (Apache-2.0). Read 2026-08-22 "
        "against the installed artifact, not from documentation. See DECISIONS.md D-0006."
    ),
}
"""Distribution -> cited reason, for entries the licence scan cannot resolve or flags.

An entry with no cited evidence is rejected at review, on the same terms as a survey
spec override (spec section 6.4). Every addition is a maintainer decision recorded in
DECISIONS.md.
"""

PERMITTED_CODECS: Final[frozenset[str]] = frozenset(
    {"blosc", "zstd", "bytes", "crc32c", "transpose", "sharding_indexed"}
)
"""Codec / codec-adjacent names permitted on disk. SP3. Anything else voids a store."""

LOSSY_CODECS: Final[frozenset[str]] = frozenset({"zfpy", "zfp", "jpeg", "jpeg2000"})
"""Codecs whose presence in a store manifest makes the store void (SP3)."""

SEGY_TRACE_HEADER_BYTES: Final[int] = 240
"""Every SEG-Y trace header is 240 bytes. G1 asserts full coverage of 1..240."""

SEGY_TEXTUAL_HEADER_BYTES: Final[int] = 3200
SEGY_BINARY_HEADER_BYTES: Final[int] = 400
