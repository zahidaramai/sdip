# `ci/` — the workflows moved to `.github/workflows/` and now execute

**They ran nowhere until 2026-08-23.** GitHub Actions executes workflows **only** from
`.github/workflows/`, and these files were deliberately kept out of it while the gates
were being built — an always-failing job would have blocked the very pull request that
built the gate (`DECISIONS.md` D-0012).

**v1.0.0 changed what that parking means.** At `0.x`, deferred CI reads as honest
immaturity. At a version that claims maturity, a check that exists but never runs is an
overstatement (**D14**, and `DECISIONS.md` D-0076).

| File | Now at | Jobs |
|---|---|---|
| `ci.yml` | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | `doctor`, `lint`, `unit`, `forbid-list`, `licence`, `firewall`, `fixture-policy`, `publication-readiness`, `gates`, `roadmap` |
| `dco.yml` | [`.github/workflows/dco.yml`](../.github/workflows/dco.yml) | `sign-off` |

## What the `gates` job does and does not run

It runs `tests/integration` with **`-m 'not slow'`**, which removes **exactly** the 63
**P7 latency benchmarks** and nothing else — verified against the collected set, not
assumed.

Those benchmarks assert that a chunk shape built for an access pattern beats the default
**at millisecond scale**. That is a real comparison on a quiet machine and **noise on a
shared runner** (**D39**: observed failing at load average 11.2, then passing 3/3 in
isolation on the same commit). **A flaky gate teaches people to re-run rather than read**,
so the benchmark runs locally and the correctness legs gate here.

**The other two `slow` suites still run**, because they are correctness rather than
timing: **P2 `ibm32` fidelity** under `tests/unit`, and the **D8 hostile corpus** under
`tests/negative`.

## Green still does not mean the gates pass

The five gate jobs **arm themselves** on the presence of their own subject and report
`NOT_RUN` otherwise (**D-0012**). A green build means *everything that exists passes*.
The `roadmap` job writes all seven gate states into every run summary so the distinction
is visible in the run rather than only here. See **D14**.
