# `ci/` — workflow definitions that are **not currently executed**

| File | What it defines |
|---|---|
| [`ci.yml`](ci.yml) | `doctor`, `lint`, `unit`, `forbid-list`, `licence`, `firewall`, `fixture-policy`, `publication-readiness`, `gates`, `roadmap` |
| [`dco.yml`](dco.yml) | `sign-off` — every commit in a pull request carries `Signed-off-by` |

## Why they are here and not in `.github/workflows/`

GitHub Actions executes workflows **only** from `.github/workflows/`. These files were
moved out of that directory, so **no job below runs on any push or pull request.**

CI is deferred until the project is complete. Leaving the workflows in place while they
cannot run produced a failed check on every commit, which trains reviewers to ignore CI
— the exact failure mode this project criticises elsewhere. A check nobody reads is not
a check (**SP11**).

**Nothing was deleted.** The files are unchanged and moved with `git mv`, so their
history follows them and every job, step, and assertion remains public and reviewable.

## Re-enabling

```bash
git mv ci/*.yml .github/workflows/
```

That is the whole operation. Then update the path references — this file, the CI/CD
section of [`README.md`](../README.md), the *Continuous integration* section of
[`CONTRIBUTING.md`](../CONTRIBUTING.md), and the four `ci/ci.yml` reads in
`tests/unit/test_repository_contract.py`.

## These checks are still binding on a contributor

**Unexecuted is not unenforced.** These files are the reviewable statement of the
specification's §7.8 job table — what CI asserts, and what a PR is reviewed against
whether or not a runner has confirmed it. In particular:

- the `ast`-based forbid-list scans — barred environment variables, tolerance
  comparisons, suppressed warnings, and the negative controls proving each detector fires
- the `firewall` job's history scan (`--all`), which is the only layer that catches an
  unpublishable path in **any** commit on **any** ref rather than at `HEAD`
- the licence scan — no GPL or AGPL in the runtime dependency tree
- the self-arming gate jobs, which run the real check or report `NOT_RUN` with the phase
- the DCO sign-off check

A PR that would fail one of these fails review for the same reason.

`tests/unit/test_repository_contract.py` asserts on the contents of `ci.yml` directly —
the firewall layer set, the self-arming gate design, the absence of a hard `exit 1` in
an unbuilt gate, and the absence of barred variables. Those assertions run in the local
suite, so the job definitions stay under test while the jobs themselves do not run.

## Running the equivalent locally

```bash
uv run sdip doctor
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```
