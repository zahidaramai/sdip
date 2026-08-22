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
