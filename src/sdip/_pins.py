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
    """An exact upstream pin: version and the commit SHA it was cut from."""

    distribution: str
    version: str
    commit_sha: str
    repository: str


PINS: Final[tuple[Pin, ...]] = (
    Pin(
        distribution="multidimio",
        version="1.2.1",
        commit_sha="a2895b53088ffacbf4bd1b9e882856cbda78e235",
        repository="https://github.com/TGSAI/mdio-python",
    ),
    Pin(
        distribution="segy",
        version="0.6.0",
        commit_sha="8e93e97db33ea4b2ce77433f6fdbef5d31ac6e78",
        repository="https://github.com/TGSAI/segy",
    ),
)

BARRED_ENV_VARS: Final[dict[str, str]] = {
    "MDIO_IGNORE_CHECKS": (
        "Demotes the MDIO grid-sparsity error to a log line. A suppressible gate is "
        "not a gate (SP11)."
    ),
    "MDIO__IMPORT__RAW_HEADERS": (
        "Deprecated upstream for removal in 1.4. SDIP reaches full 240-byte header "
        "persistence through the public API instead (spec 3.2); depending on this "
        "flag is a specification violation even though it looks helpful."
    ),
}
"""Environment variables that must be absent. Spec section 9.1."""

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
