"""Placeholder for the template layer declared in the specification layout (§6.3).

**This package holds no code today, and that is the accurate state rather than an
omission.** SDIP selects templates straight from MDIO's own registry
(``mdio.builder.template_registry.get_template``) in ``sdip.ingest.orchestrator``,
because a thin SDIP variant would be a wrapper around a public API that already does
the job — and §3.3 bars reaching around upstream for anything the public API supplies.

The directory is kept because ``tests/unit/test_repository_contract.py`` asserts the
layout the specification declares. Removing it would be a specification deviation, which
§9 says to raise rather than decide alone.

**Prestack chunking is no longer unmeasured.** Probe **P7** ran on 2026-08-23: its
falsifier **does not fire** on the two geometries that clear the correctness
precondition, and is **not evaluable** on the other two, which stay blocked by clause 1.
See ``prereg/P7-prestack-chunking.md`` for the config and N behind each number.
"""

from __future__ import annotations

__all__ = ["PHASE"]

PHASE = "F2"
