# `ci/` — the workflows live in `.github/workflows/`

**They ran nowhere until 2026-08-23.** GitHub Actions executes workflows **only** from
`.github/workflows/`, and these files were deliberately kept out of it while the gates were
being built — an always-failing job would have blocked the very pull request that built the
gate (`DECISIONS.md` D-0012). At v1.0.0 they moved there and execute (D14, D-0076).

**Since 2026-10-15 they run only when asked for** (`DECISIONS.md` D-0095): on a pull request,
or started by hand (`gh workflow run ci`). Never on push.

| File | Now at | Trigger | Jobs |
|---|---|---|---|
| `ci.yml` | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | pull request, manual | `firewall`, `check` |
| `dco.yml` | [`.github/workflows/dco.yml`](../.github/workflows/dco.yml) | pull request, manual | `sign-off` |
| `publish.yml` | [`.github/workflows/publish.yml`](../.github/workflows/publish.yml) | a published GitHub Release, manual | container, wheel + sdist |

## What `check` runs

One dependency install, then: `sdip doctor`; `ruff check`, `ruff format --check`, `mypy`;
the forbid-list scans (barred variables, `zfpy`); the runtime licence scan; fixture policy;
the unresolved-placeholder check; and **one run of the whole test suite** — unit,
integration and negative, every gate's tests and every negative control. Each step runs even
after an earlier one failed, so one red check never hides another.

The suite ignores one file, `tests/integration/test_p7_latency.py`: the **63 P7 latency
benchmarks**, which assert that a chunk shape built for an access pattern beats the default
**at millisecond scale** — a real comparison on a quiet machine and **noise on a shared
runner** (**D39**: observed failing at load average 11.2, then passing 3/3 in isolation on the
same commit). **A flaky gate teaches people to re-run rather than read.** The other `slow`
suites — **P2 `ibm32` fidelity** and the **D8 hostile corpus** — are correctness and run.

## Green still does not mean the Equivalence Contract holds on your data

CI runs against committed synthetic fixtures. A certificate is issued against a specific store
from a specific source; CI cannot certify anything. `EQUIVALENCE_LEDGER.md` indexes what was
actually certified.
