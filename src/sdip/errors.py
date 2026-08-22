"""SDIP exception hierarchy.

SDIP parses binary files it did not create (spec section 11.4). A malformed or
hostile SEG-Y must produce a clean, typed error - never a crash, an unbounded
allocation, or a write outside the output path.
"""

from __future__ import annotations


class SdipError(Exception):
    """Base class for every error SDIP raises deliberately."""


class GuardError(SdipError):
    """A forbid-list binding was violated. Spec section 9."""


class BarredEnvironmentError(GuardError):
    """A barred environment variable is set. Spec section 9.1."""


class BarredPackageError(GuardError):
    """A barred package is importable. Spec section 9.2."""


class PinMismatchError(GuardError):
    """An installed upstream distribution does not match its binding pin. Spec 3.3."""


class BarredLicenceError(GuardError):
    """A copyleft licence was found in the runtime dependency tree. Spec 3.6 / 9.4."""


class DirtyTreeError(SdipError):
    """A certificate was requested from a dirty working tree. Spec 11.3. No override."""


class SpecCompletenessError(SdipError):
    """G1 failed: the trace-header spec is not gap-free. Spec sections 5 and 7."""


class EquivalenceError(SdipError):
    """An equivalence gate failed. Spec section 7."""


class UntrustedInputError(SdipError):
    """A source file failed validation before allocation. Spec section 11.4."""


class PhaseNotAuthorisedError(SdipError):
    """The requested capability belongs to a later roadmap phase. Spec section 13.

    Raised instead of returning a wrong or partial answer. SDIP would rather refuse
    than produce an unvalidated result.
    """
