# Contributing to SDIP

Contributions are welcome from anyone, any project, any organisation, under Apache-2.0
with DCO sign-off.

Read this file in full before your first change, and read the section of the SDIP
Specification v1.0 your change touches. The section, not the summary.

> **On the specification.** SDIP v1.0 is the governing specification and is referenced
> throughout by section number (§4 the Equivalence Contract, §5 the spec mechanism, §7
> the gates, §9 the forbid list). It is **not distributed in this repository.** Every
> rule it imposes on a contribution is restated here and in [`README.md`](README.md), and
> every measurement it rests on is recorded in [`DECISIONS.md`](DECISIONS.md), so a
> contribution can be written and reviewed from what is committed. Open an issue if a
> rule you are asked to follow is not stated in one of those three files — that is a
> defect in them, not in you.

---

## The five things that get a PR rejected

1. **A tolerance-based comparison in the equivalence engine.** `np.allclose` on samples
   or headers is a specification defect. Comparisons are `array_equal` or byte
   equality. No epsilon, no "close enough for seismic".
2. **A suppressed warning.** Never add `warnings.filterwarnings("ignore", ...)`.
   See [`DECISIONS.md`](DECISIONS.md) D-0004 for how SP6 is actually implemented and
   why re-raising is not available.
3. **Reading or setting a barred environment variable.** `MDIO_IGNORE_CHECKS` and
   `MDIO__IMPORT__RAW_HEADERS` are barred (§9.1). Setting them makes tests pass and the
   project worthless.
4. **A lossy codec.** Blosc and Zstd only. `zfpy` must not be installed.
5. **Processing.** SDIP does not filter, scale, resample, regrid, mute, interpolate, or
   denoise. If you find yourself writing a transform, stop — you are outside the
   mission (§1.3).

---

## Setup

```bash
git clone https://github.com/OWNER/sdip && cd sdip
uv sync                    # Python >=3.12,<3.14
uv run sdip doctor         # must pass before anything else
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

`doctor` exits 1 on a dirty working tree. That is intentional and there is no override
flag — see [`DECISIONS.md`](DECISIONS.md) D-0007.

---

## What a good PR looks like

- Satisfies **exactly one** gate or one probe leg. Nothing more.
- **Ships its negative control in the same commit** if it touches the engine (§5 below).
- Carries a message stating **what was measured, under what config, with what N**.
- Leaves the append-only records current.
- Adds no suppressed warning, no tolerance, no barred variable, no new dependency.
- Would let a stranger reproduce the result from the repository alone.

That last line is the whole test. **If a stranger cannot reproduce it from what is
committed, it did not happen.**

### Commit messages report claims with numbers

> `G2c passes on the 30-trace fixture; unmeasured at scale, P3 open`

is worth more than

> `header preservation works`

The first is a measurement with a declared scope. The second is a claim, and claims get
sent back.

---

## The G7 discipline — write the failure first

For every equivalence check you add, write a negative control that **must fail it**:

- one flipped header byte
- one flipped sample bit
- one dropped trace
- two transposed traces
- live mask inverted on one trace
- truncated textual header

Each corruption must fail **its** gate and **only** its gate. Controls live permanently
in `tests/negative/`. A failed configuration becomes the permanent negative control for
its fix.

**A gate a corrupted store passes is not a gate.** A PR that adds an engine check
without its negative control fails the `negative` CI job, by design.

---

## Adding a probe

Probes are pre-registered (**SP9**). The order is not negotiable:

1. Open an issue with the **Probe proposal** template. It states the question, the
   method, the threshold, the N, and the **falsifier** — what result would prove the
   hypothesis wrong. A maintainer registers it against the probe register.
2. **Merge it before running anything.**
3. Run the probe.
4. Open a second PR with results.

**Never write a pre-registration after seeing a result.** Better-than-expected does not
tighten a gate post hoc; worse-than-expected does not relax one. Gates never bend in
either direction.

---

## Adding a survey spec override

Overrides (§6.4) are declarative data — never code branches. Each carries a provenance
note stating the evidence for the remapping: an observer report, a contractor
specification, or textual-header content.

**An override with no cited evidence is rejected at review.** Re-run G2c after applying
one: overrides change labels and numeric interpretation, never byte content.

---

## Test data policy — binding

**No proprietary or restricted data enters this repository, ever.** Fixtures are either
synthetic and generated deterministically by committed code with a fixed seed, or
openly licensed and redistributable with licence and provenance recorded in
[`tests/fixtures/PROVENANCE.md`](tests/fixtures/PROVENANCE.md). Large open datasets are
fetched at test time by checksum, never vendored.

**Do not attach proprietary SEG-Y to an issue or a PR.** If you hit a bug on data you
cannot share, reproduce it with a synthetic file that has the same structural property
— byte layout, revision, geometry irregularity — and attach that instead. A synthetic
reproducer is more useful anyway: it becomes a permanent fixture.

---

## The `__main__` guard — you will hit this

MDIO's header parser uses a **`spawn`** multiprocessing context. **Every entry point
that can trigger ingestion must be guarded by `if __name__ == "__main__":`.** Without
it the child process re-executes the ingest and dies with `BrokenProcessPool`. This is
measured (Appendix A.5), not theoretical. There is a regression test and a
`spawn-guard` CI job; do not delete either.

---

## Licence hygiene

- Contributions are accepted under Apache-2.0 with DCO sign-off.
- The round-trip test fixture is lifted from
  [`TGSAI/mdio-python`](https://github.com/TGSAI/mdio-python) (Apache-2.0).
  **Attribution in [`NOTICE`](NOTICE) is a legal obligation and must survive
  refactors.**
- [`ThomasHertweck/seisio`](https://github.com/ThomasHertweck/seisio) (LGPL) is cited as
  design prior art with an explicit "no code copied" statement. Read it; copy nothing.
- **Never** copy from `trhallam/segysak` (GPL) or `stuliveshere/pyseis-io` (AGPL-3.0),
  at any size, including "just this one function". This is a distributed, permissively
  licensed library — copyleft contamination is not a hypothetical concern here.

### DCO sign-off

Every commit needs a `Signed-off-by` line, which `git commit -s` adds:

```
Signed-off-by: Your Name <you@example.com>
```

It certifies you have the right to submit the work under Apache-2.0. Full text:
<https://developercertificate.org/>.

---

## When to stop and ask

Open an issue rather than deciding alone:

- A gate fails, or a measurement contradicts a documented conclusion
- A named probe falsifier fires (§8) — especially P2 or P4
- Anything that would require forking upstream or bumping a pin
- Any change to the Equivalence Contract (§4), the spec mechanism (§5), or the gates (§7)
- A specification deviation, or a fork in the road with no clear guideline

Changes to §4, §5, or §7 require maintainer consensus and a **successor specification
version**. They are never edited in place.
