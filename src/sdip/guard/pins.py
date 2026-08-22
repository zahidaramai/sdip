"""Upstream pin verification. Spec section 3.3.

The pins are binding and they are pinned *together*: the ``ibm32`` header fix
straddles the ``segy`` 0.6.0 boundary. A version bump invalidates every certificate
issued under the previous pin.

Honesty note (SP8): this check verifies the installed **version** exactly. It does
not verify the commit SHA, because an installed wheel does not carry the SHA it was
built from. The SHA is *declared*, recorded on every certificate, and pinned in
``uv.lock`` by artifact hash; runtime SHA attestation is an open debt (D9).
Every result therefore states which of the two it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from sdip._pins import PINS, Pin


@dataclass(frozen=True, slots=True)
class PinStatus:
    """Result of checking one binding pin against the installed environment."""

    distribution: str
    expected_version: str
    installed_version: str | None
    declared_commit_sha: str
    commit_sha_verified: bool
    ok: bool

    @property
    def detail(self) -> str:
        """Human-readable one-line explanation of this status."""
        if self.installed_version is None:
            return f"{self.distribution} is not installed (expected {self.expected_version})"
        if not self.ok:
            return (
                f"{self.distribution} {self.installed_version} installed, "
                f"pin requires exactly {self.expected_version}"
            )
        return (
            f"{self.distribution} {self.installed_version} matches pin; "
            f"commit SHA {self.declared_commit_sha[:12]} declared, not runtime-verified"
        )


def _status_for(pin: Pin) -> PinStatus:
    try:
        installed: str | None = version(pin.distribution)
    except PackageNotFoundError:
        installed = None
    return PinStatus(
        distribution=pin.distribution,
        expected_version=pin.version,
        installed_version=installed,
        declared_commit_sha=pin.commit_sha,
        commit_sha_verified=False,
        ok=installed == pin.version,
    )


def check_pins() -> list[PinStatus]:
    """Return the status of every binding pin, in declaration order."""
    return [_status_for(pin) for pin in PINS]
