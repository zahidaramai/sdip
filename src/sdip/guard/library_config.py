"""zarr's and dask's configuration, from any channel, checked against their shipped defaults.

**OPEN_DEBTS D58, DECISIONS.md D-0088.** Both libraries are configured through donfig, which
reads ``ZARR_*``/``DASK_*`` environment variables, a serialised ``<NAME>_INTERNAL_INHERIT_CONFIG``,
and YAML or JSON files under ``/etc/<name>``, ``<sys.prefix>/etc/<name>``, ``~/.config/<name>``,
``$<NAME>_ROOT_CONFIG`` and ``$<NAME>_CONFIG``. A list of variable names sees only the first of
those channels. The effective configuration sees all of them, so that is what is compared:
every key whose effective value differs from the library's defaults is a deviation, classified
by ``sdip._pins.LIBRARY_CONFIG_RULES``.

Measured in a clean run after importing everything a run imports: 0 deviations in zarr's 48
default keys and dask's 30. The guard therefore refuses nothing an unconfigured machine does.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from sdip._pins import BAR, LIBRARY_CONFIG_RULES, RECORD, LibraryConfigRule

LIBRARIES = ("zarr", "dask")


def _flatten(tree: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in dict(tree).items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def _config(library: str) -> Any:
    if library == "zarr":
        import zarr

        return zarr.config
    import dask.config

    return dask.config


def _effective_and_defaults(library: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = _config(library)
    defaults: dict[str, Any] = {}
    for layer in config.defaults:
        defaults.update(_flatten(layer))
    return _flatten(config.config), defaults


def _canonical(key: str) -> str:
    """Donfig treats ``-`` and ``_`` as the same key and dask stores both spellings."""
    return key.replace("-", "_")


def rule_for(library: str, key: str) -> LibraryConfigRule | None:
    """The first rule naming ``key``, or ``None``. Patterns are matched on canonical keys."""
    for rule in LIBRARY_CONFIG_RULES:
        if rule.library == library and fnmatch.fnmatchcase(
            _canonical(key), _canonical(rule.pattern)
        ):
            return rule
    return None


def _sources(library: str) -> str:
    prefix = f"{library.upper()}_"
    variables = sorted(k for k in os.environ if k.startswith(prefix))
    files = [
        str(path)
        for base in getattr(_config(library), "paths", [])
        for path in ([Path(base)] if Path(base).is_file() else sorted(Path(base).glob("*")))
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml", ".json"}
    ]
    parts = []
    if variables:
        parts.append("environment " + ", ".join(variables))
    if files:
        parts.append("config file " + ", ".join(files))
    return "; ".join(parts) or "an inherited configuration"


def deviations() -> list[dict[str, Any]]:
    """Every effective setting that differs from its library's defaults, classified."""
    found: list[dict[str, Any]] = []
    for library in LIBRARIES:
        effective, defaults = _effective_and_defaults(library)
        canon_defaults = {_canonical(k): v for k, v in defaults.items()}
        seen: set[str] = set()
        for key, value in sorted(effective.items()):
            canon = _canonical(key)
            if canon in seen or canon_defaults.get(canon, object()) == value:
                continue
            seen.add(canon)
            rule = rule_for(library, key)
            reported = key.replace("_", "-") if library == "dask" else key
            found.append(
                {
                    "library": library,
                    "key": reported,
                    "value": value,
                    "action": rule.action if rule else BAR,
                    "reason": rule.reason if rule else "unclassified setting: fail closed (D58)",
                }
            )
    return found


def refusals() -> list[dict[str, Any]]:
    """Deviations that bar a run."""
    return [d for d in deviations() if d["action"] == BAR]


def recorded_library_config() -> dict[str, str]:
    """Deviations recorded on the certificate, as ``library:key`` to the value's text."""
    return {
        f"{d['library']}:{d['key']}": str(d["value"]) for d in deviations() if d["action"] == RECORD
    }


def refuse_library_config(action: str) -> None:
    """Raise if any barred deviation is in effect. Called before a command reads a byte.

    Raises:
        BarredEnvironmentError: Naming each setting, its value, where it came from, and why.
    """
    from sdip.errors import BarredEnvironmentError

    barred = refusals()
    if barred:
        detail = "; ".join(
            f"{d['library']} {d['key']}={d['value']!r} "
            f"(from {_sources(d['library'])}): {d['reason']}"
            for d in barred
        )
        msg = f"refusing to {action}: barred library configuration in effect (spec 9.1). {detail}"
        raise BarredEnvironmentError(msg)


def classification_gaps() -> list[str]:
    """Zarr default keys no explicit rule names. Empty means every setting has a ruling."""
    _, defaults = _effective_and_defaults("zarr")
    return sorted(k for k in defaults if rule_for("zarr", k) is None)
