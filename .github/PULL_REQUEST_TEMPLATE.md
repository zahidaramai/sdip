## What was measured

<!--
State what was measured, under what config, with what N. Not conclusions.

  "G2c passes on the 30-trace fixture; unmeasured at scale, P3 open"

is worth more than

  "header preservation works"

The first is a measurement with a declared scope. The second is a claim, and claims get
sent back.
-->

## Which gate or probe leg this satisfies

<!-- Exactly one. Spec section 7 for gates, section 8 for probes. -->

## Checklist

- [ ] Satisfies **exactly one** gate or one probe leg — no unrequested scope
- [ ] If it touches the engine: **the negative control ships in this same commit**
- [ ] No tolerance-based comparison anywhere (`allclose`, `isclose`, `rtol`, `atol`)
- [ ] No `warnings.filterwarnings("ignore", ...)` added
- [ ] No barred environment variable read or set (`MDIO_IGNORE_CHECKS`, `MDIO__IMPORT__RAW_HEADERS`)
- [ ] No new runtime dependency, no lossy codec, no `zfpy`
- [ ] Any entry point that can trigger ingestion is behind `if __name__ == "__main__":`
- [ ] Append-only records updated where relevant (`DECISIONS.md`, `OPEN_DEBTS.md`, `EQUIVALENCE_LEDGER.md`) — **by appending**
- [ ] No proprietary data added, attached, or referenced
- [ ] Every commit is signed off (`git commit -s`)
- [ ] A stranger could reproduce this from the repository alone

## Anything inferred rather than observed

<!-- Flag it here. Inference is allowed; unlabelled inference is not. -->

## Is this number too good?

<!--
Impossible precision is a metric bug until proven otherwise. During the original audit a
round trip appeared to fail because the *expectation* was wrong, not the code.

Suspect your test before you suspect the dependency.
-->
