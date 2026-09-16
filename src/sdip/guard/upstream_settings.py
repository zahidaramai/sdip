"""Prove the environment-variable registry matches what the installed upstream reads.

``sdip._pins.UPSTREAM_SETTINGS`` is written by hand so that importing SDIP never imports
MDIO. This module is the check that stops a hand-written list from drifting: it walks
every module of the installed ``segy`` and ``mdio``, finds every ``pydantic-settings``
model, and derives each field's environment variable name and case sensitivity from the
model itself. ``sdip doctor`` runs it, and so does the test suite.

**It fails closed.** A module that cannot be imported is a gap, not a skip: it could be
where a new setting lives. At the pinned versions all 127 upstream modules import.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Any

from sdip._pins import UPSTREAM_SETTINGS

UPSTREAM_PACKAGES = ("segy", "mdio")


@dataclass(frozen=True, slots=True)
class DiscoveredSetting:
    """A setting as the installed upstream defines it."""

    model: str
    field: str
    env: str
    case_sensitive: bool


def _env_name(model: Any, name: str, info: Any) -> str:
    alias = info.validation_alias if info.validation_alias is not None else info.alias
    if isinstance(alias, str):
        return alias
    prefix = str(model.model_config.get("env_prefix") or "")
    return f"{prefix}{name}".upper()


def introspect_upstream_settings() -> tuple[list[DiscoveredSetting], list[str]]:
    """Every settings field the installed upstream defines, and any unimportable module."""
    from pydantic_settings import BaseSettings

    discovered: dict[tuple[str, str], DiscoveredSetting] = {}
    unimportable: list[str] = []
    for package_name in UPSTREAM_PACKAGES:
        package = importlib.import_module(package_name)
        for info in pkgutil.walk_packages(package.__path__, f"{package_name}."):
            try:
                module = importlib.import_module(info.name)
            except Exception as exc:
                unimportable.append(f"{info.name}: {type(exc).__name__}")
                continue
            for obj in vars(module).values():
                if (
                    not isinstance(obj, type)
                    or not issubclass(obj, BaseSettings)
                    or obj is BaseSettings
                    or not obj.__module__.startswith(UPSTREAM_PACKAGES)
                ):
                    continue
                qualified = f"{obj.__module__}.{obj.__name__}"
                for name, field_info in obj.model_fields.items():
                    discovered[(qualified, name)] = DiscoveredSetting(
                        model=qualified,
                        field=name,
                        env=_env_name(obj, name, field_info),
                        case_sensitive=bool(obj.model_config.get("case_sensitive", False)),
                    )
    return sorted(discovered.values(), key=lambda s: (s.model, s.field)), sorted(unimportable)


def classification_gaps() -> dict[str, list[str]]:
    """Differences between the registry and the installed upstream. Empty lists are clean."""
    discovered, unimportable = introspect_upstream_settings()
    found = {(s.model, s.field): s for s in discovered}
    registry = {(s.model, s.field): s for s in UPSTREAM_SETTINGS}
    gaps: dict[str, list[str]] = {
        "unclassified": [
            f"{m}.{f} ({found[(m, f)].env})" for m, f in sorted(set(found) - set(registry))
        ],
        "stale": [
            f"{m}.{f} ({registry[(m, f)].env})" for m, f in sorted(set(registry) - set(found))
        ],
        "mismatched": [
            f"{m}.{f}: registry {registry[(m, f)].env} case_sensitive="
            f"{registry[(m, f)].case_sensitive}, upstream {found[(m, f)].env} "
            f"case_sensitive={found[(m, f)].case_sensitive}"
            for m, f in sorted(set(found) & set(registry))
            if (registry[(m, f)].env, registry[(m, f)].case_sensitive)
            != (found[(m, f)].env, found[(m, f)].case_sensitive)
        ],
    }
    if unimportable:
        gaps["unimportable"] = unimportable
    return gaps
