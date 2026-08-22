"""Published Equivalence Certificate schemas.

Specification §4.7 requires the certificate schema to be *published*, so a third
party can validate SDIP output **without running SDIP**. That requirement was
unsatisfiable while the only copy lived in ``docs/``, which is never committed
(``DECISIONS.md`` D-0010): ``git ls-files`` returned nothing.

The schema is not documentation. It is a machine artifact that ``sdip certify`` needs
at runtime to validate its own output, and that a consumer needs to check a
certificate they were handed. It therefore ships **inside the package**, which means
``pip install sdip`` gives a validator to someone who never clones the repository, and
the file is tracked in the public tree for someone who does. See D-0015.

SDIP does not vendor a JSON Schema validator. Loading returns the parsed document;
validating it is the caller's choice of library, which keeps a barred-licence surface
and a dependency out of the runtime tree for something every consumer already has.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, Final

__all__ = ["SCHEMA_FILENAMES", "available_versions", "load_schema", "schema_path"]

SCHEMA_FILENAMES: Final[dict[str, str]] = {
    "0": "sdip-certificate-v0.schema.json",
}
"""Certificate schema version -> filename. Versioned independently of the software."""


def available_versions() -> tuple[str, ...]:
    """Certificate schema versions this package ships, newest last."""
    return tuple(SCHEMA_FILENAMES)


def schema_path(version: str = "0") -> Any:
    """Return an ``importlib.resources`` traversable for a schema version.

    Args:
        version: Certificate schema version.

    Raises:
        KeyError: If the version is not shipped.
    """
    return files(__package__).joinpath(SCHEMA_FILENAMES[version])


def load_schema(version: str = "0") -> dict[str, Any]:
    """Return the parsed JSON Schema document for a certificate schema version.

    Args:
        version: Certificate schema version.

    Returns:
        The parsed schema.

    Raises:
        KeyError: If the version is not shipped.
    """
    return json.loads(schema_path(version).read_text(encoding="utf-8"))  # type: ignore[no-any-return]
