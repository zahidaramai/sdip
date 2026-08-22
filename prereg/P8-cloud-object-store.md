# P8 — Cloud object store

| Field | Value |
|---|---|
| Probe | `P8` · Status `REGISTERED` · Registered 2026-08-22 |
| Blocks | cloud deployment |
| Related debt | `OPEN_DEBTS.md` D7 · Spec §11.2, §8 P8 |

## Question

Does the ingest-and-read path hold against S3, GCS, and Azure — including auth, retry,
partial-write recovery, and checkpoint-on-write?

## Why it matters

§11.2 states it plainly: **a harness that can return nothing after hours is a defect.**
Object stores fail differently from filesystems. They fail *partially*, they fail
*intermittently*, and they fail *late*. A store left half-written by a credential
expiry at hour six is not an inconvenience — it is an artifact indistinguishable from a
complete one unless something checked.

## Method

Per backend — S3, GCS, Azure:

1. Ingest a fixture to the object store; read it back and run all five planes.
2. **Auth expiry:** run with a credential that expires mid-ingest. Assert a clean,
   typed error and a recoverable checkpoint — never a silent truncation.
3. **Retry:** inject transient 5xx and connection resets. Assert the run completes and
   the result is byte-identical to an uninterrupted run.
4. **Partial write:** kill the process mid-ingest. Assert the store is either resumable
   from its checkpoint or unambiguously marked incomplete. **A partially written store
   must never validate as complete.**
5. **Persist-and-verify before terminating ephemeral compute** (§11.2): assert the
   verification step runs against the persisted store, not against memory.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Backends | S3, GCS, Azure — all three |
| Fixture | The P1 30-trace article, plus one multi-GB store if P3 has run |
| Fault injections | auth expiry, transient 5xx, connection reset, process kill |
| N repetitions per fault | *declared before the run* |
| Comparison | Exact byte equality against the local-filesystem ingest of the same source |

## Falsifier

**A run that can return nothing after hours.** Concretely, any one of:

- A partially written store that validates as complete.
- An interruption that leaves no resumable checkpoint.
- A byte difference between the cloud store and the local-filesystem store for the same
  source.
- An auth or network failure surfacing as a crash rather than a typed error.

## If it fires

Cloud deployment does not proceed for that backend and D7 stays open against it. A
partial-write failure that validates as complete is the most serious outcome and would
additionally be treated as a **security-class** finding, per `SECURITY.md`: it produces
a false `EQUIVALENT` verdict.

---

## Results — appended 2026-08-22, never edited into the sections above

| Field | Value |
|---|---|
| Run date | 2026-08-22 |
| **Verdict** | **NOT RUN — blocked on credentials.** The falsifier was not evaluated. |

### Why it did not run

P8 needs a real S3, GCS and Azure account. This machine has none, and the project's CI
*"has no network access except the pinned package index"* (§7.8), so it cannot obtain
them either.

**No substitute was used, and that is a deliberate choice.** `moto`, `minio` and
`fsspec`'s memory filesystem would all have produced a green result. None of them would
have answered the question P8 actually asks, which is not *"does the object-store code
path execute"* but:

> **Does a run that takes hours survive auth expiry, transient 5xx, connection reset and
> process kill, and does it ever leave a partially written store that validates as
> complete?**

A mock does not expire credentials mid-run, does not throttle, does not fail on the
17,000th PUT of 20,000, and has no eventual-consistency behaviour. Reporting a mocked
pass against this pre-registration would have been the *precise* failure this project
exists to prevent: a claim with a number behind it that does not mean what a reader would
take it to mean (**SP8**).

### What this leaves open

**`OPEN_DEBTS.md` D7 is untouched.** Cloud deployment is unsupported and unmeasured. The
`cloud` extra exists in `pyproject.toml` and has never been exercised.

The single most consequential unanswered item is the one §11.2 calls out directly:

> **A harness that can return nothing after hours is a defect.**

Nothing yet demonstrates that a killed or expired cloud run leaves either a resumable
checkpoint or an unambiguously incomplete store. **A partially written store that
validates as complete is a security-class finding** under `SECURITY.md`, because it
produces a false `EQUIVALENT` verdict — and it is exactly the outcome a mocked run would
be least likely to surface.

### To run this later

1. Credentials for at least one backend, and authorisation to spend on them.
2. A fault-injection harness: expire a token mid-run, inject 5xx, reset the connection,
   kill the process.
3. The comparison is against a **local-filesystem ingest of the same source**, byte for
   byte — the cloud store must be identical, not merely valid.

Until then this probe is `NOT RUN`, and no claim about cloud behaviour may cite it.
