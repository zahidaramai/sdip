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

## Amendment A — a local object-store leg, declared 2026-08-23

**Registered before this leg is run.** The original method names S3, GCS and Azure, none
of which is available, and the first result recorded P8 `NOT RUN` — deliberately, because
a mock would have produced a green result answering a different question.

**This amendment adds a leg that is not a mock.** MinIO is a real S3 server: real HTTP,
real multipart uploads, real authentication, real partial writes on a real filesystem. It
is not one of the three named backends and this amendment does **not** claim it is.

**What it can honestly answer** — and these are the parts §11.2 calls out by name:

| Question | Answerable locally? |
|---|---|
| Does the object-store write path execute end to end? | **yes** |
| Does a store written to an object store read back byte-identically against a local-filesystem ingest of the same source? | **yes** |
| Does a **killed** run leave a resumable checkpoint, or an unambiguously incomplete store? | **yes** |
| **Can a partially written store validate as complete?** | **yes** — and this is the security-class question |
| Auth expiry mid-run | **partially** — MinIO issues expiring STS credentials |
| Real cloud throttling, 5xx, eventual consistency | **no** |
| GCS, Azure | **no** |

**Declared parameters, fixed now:**

| Parameter | Value |
|---|---|
| Backend | MinIO, local, S3 API |
| Fixture | The Appendix A.1 30-trace article, plus one larger store if time allows |
| Comparison | **Byte equality against a local-filesystem ingest of the same source.** Not "valid", not "opens" — identical. |
| Fault injections | process kill mid-ingest; credential expiry mid-ingest |
| Repetitions | 3 per fault |

**Falsifier for this leg**, narrowed from the original to what this backend can decide:

> **A partially written store that validates as complete**, or a byte difference between
> the object-store ingest and the local-filesystem ingest of the same source, or an
> interruption that leaves neither a resumable checkpoint nor an unambiguously incomplete
> store.

**What this leg does NOT discharge.** The original falsifier — *"a run that can return
nothing after hours"* — is about **real cloud** behaviour over long durations: throttling,
transient 5xx, eventual consistency, credential lifetimes measured in hours. **None of
that is measurable here, and D7 stays open regardless of this leg's outcome.** A pass here
means the code path and the interruption semantics are sound, not that the project is
cloud-ready.

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

---

## Results — Amendment A, the local object-store leg. Appended 2026-08-23, never edited into the sections above

| Field | Value |
|---|---|
| Run date | 2026-08-23 |
| Backend | MinIO `RELEASE.2025-10-15T17-29-55Z` (commit `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`), go1.26.3 darwin/arm64, single node, single drive, bound to `127.0.0.1:9000` |
| Client | `s3fs` 2026.1.0 · `fsspec` 2026.1.0 · `aiobotocore` 3.9.0 · `botocore` 1.43.56 · `zarr` 3.3.0 · `universal-pathlib` 0.3.10 |
| Pins | `multidimio` 1.2.1, `segy` 0.6.0 — **unchanged**. Nothing in `src/sdip` was modified for this leg. |
| Tree measured | `src/sdip/ingest/orchestrator.py` SHA-256 `fbbc97a7db55946a98846c917281acace4438ce98ab202a1ace5ca8d81b167a1` — the uint8-header-plane orchestrator. `HEAD` was `a6f5acb` when the run started and `84459fa` when it ended; concurrent work in `src/sdip` was committed underneath it. **The file digest is the reproducible reference, not the commit.** |
| Fixtures | The Appendix A.1 30-trace article (14,640 bytes), plus two larger variants from the same committed generator — 256×256×256 (82.8 MB) and 256×256×1024 = 65,536 traces (284.2 MB). The larger one exists because the 83 MB fixture's chunk flush was too fast to interrupt. |
| **Verdict** | **RAN. The falsifier FIRED.** A partially written store — the shape a real credential expiry produced twice in three attempts — passes all five planes, and `sdip verify` reports `verify: PASS` with exit 0. |

`s3fs` was added to `[dependency-groups] dev` for this leg. It is test-only and the runtime
tree did not grow: `sdip doctor` after the change reports `runtime-licences 51 runtime
distributions scanned, no GPL/AGPL entry` and passes all 8 checks. **MinIO is AGPL-3.0 and
that is not a contamination risk here** — an external server binary spoken to over HTTP, not
a dependency, not linked, not distributed, not in the tree `doctor` scans. Nothing was added
to `tests/`: CI has no MinIO and no network, so such a test could never run.

---

### 0. The prior question: can SDIP address an object store at all? **No — and it does not say so.**

Every other question presupposes that the object-store write path can be reached. It cannot,
and the way it fails is worse than a refusal.

| Entry point | Asked for | Objects in bucket | What actually happened |
|---|---|---|---|
| `sdip.ingest.ingest(src, "s3://sdip-p8/via-sdip.mdio")` | an object store | **0** | Returned normally, no exception. `IngestResult.output_path` = `/Users/…/seis-mdio-zarr/s3:/sdip-p8/via-sdip.mdio`. A complete 20-file store written under a local directory literally named `s3:`, at the process working directory. |
| `sdip ingest src s3://sdip-p8/via-cli.mdio` | an object store | **0** | **Exit code 0.** Printed `G1 PASS`, `read path intact`, and `output /…/work/s3:/sdip-p8/via-cli.mdio`. |

The cause is one line in `sdip.ingest.orchestrator.ingest`:

```python
output_path = Path(output).resolve()
```

`pathlib` normalises the doubled slash, so `s3://sdip-p8/store.mdio` becomes the *relative*
path `s3:/sdip-p8/store.mdio` and resolves against the working directory. No scheme is
recognised, nothing is validated, no error is raised.

**This is not "the `cloud` extra is unsupported". It is a successful-looking run that wrote
somewhere the operator did not ask for.** An operator who runs `sdip ingest` against a bucket
from a container gets exit 0 and a store on the container's ephemeral disk — which is what
§11.2 is about, since that disk is then discarded. The CLI cannot address a store either:
`verify`, `export` and `certify` all type their store argument as
`click.Path(exists=True, file_okay=False)`, which no URL satisfies.

**The `cloud` extra has therefore never been usable, and §11.2's requirements were never
reachable through any shipped entry point.** D7 understated this: it recorded the cloud path
as *unmeasured*; it is *unreachable*.

**What a fix would have to touch — measured, not guessed.** With the path left as an `s3://`
URL and every SDIP helper called exactly as shipped, the rest of the pipeline works against
MinIO unchanged:

| Step | Result against `s3://` |
|---|---|
| `mdio.segy_to_mdio(..., output_path=UPath(...))` | works — 18 objects. Upstream's signature is already `UPath \| Path \| str`. |
| `sdip.ingest.file_headers.attach_raw_file_headers` | works, unmodified |
| `sdip.ingest.raw_samples.attach_raw_sample_view` | works, unmodified |
| `sdip.ingest.header_plane.attach_header_plane` | works, unmodified |
| Planes 1–5 | **all five PASS** against the object store |

They work because each calls `zarr.open_group(str(store))`, stock `zarr` routes a URL through
`fsspec`, and the endpoint arrives via `AWS_ENDPOINT_URL`. **The blocker is the two
`Path(...).resolve()` calls and the CLI argument types, and nothing else this leg could
find.** That is a maintainer decision; no `src/sdip` file was touched.

---

### The four questions

| # | Question | Measured |
|---|---|---|
| 1 | **Does a partially written store validate as complete?** | **YES, at one interruption point.** A store that loses only `amplitude_raw_ibm32` and `headers_raw_uint8` passes all five planes; `sdip verify` prints `verify: PASS`, exit 0, output byte-identical to a complete store. Reached by 2 of 3 real credential expiries. Every other interruption point measured **is** caught. |
| 2 | Byte-identical against a local-filesystem ingest? | **Yes.** 10/10 chunk files byte-identical, 11/11 arrays `array_equal`, 11/12 `zarr.json` byte-identical; the twelfth differs in exactly one leaf key, `attributes.createdOn`. |
| 3 | Resumable checkpoint, or unambiguously incomplete? | **Neither.** No checkpoint of any kind — a restart re-ingests from zero. The store carries no incompleteness marker, opens clean under stock `zarr`, and returns fabricated `NaN` with zero warnings. |
| 4 | Credential expiry mid-ingest | **Answered.** MinIO's STS floor is 900 s, measured. Expiry is enforced (`403 InvalidAccessKeyId`). The ingest dies with a typed `PermissionError` in 9–11 s, no write crosses the expiry — and 2 of 3 leave the store from question 1. |

---

### 1. Does a partially written store validate as complete? **Yes, at one interruption point.**

#### Where it does not

Six SIGKILLs — three per kill point, as declared — against the 284 MB fixture, whose
uninterrupted run produces **90 objects and 32 `amplitude` chunks**. `SIGKILL` went to the
whole process group, because MDIO parses headers in a spawn pool and killing only the parent
leaves workers writing.

| Kill point | Rep | Objects | `amplitude` chunks | P1 | P2 | P3 | P4 | P5 | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| mid-convert | 1 | 25/90 | 5/32 | RAISED | RAISED | PASS | **FAIL** | PASS | **NON-EQUIVALENT** |
| mid-convert | 2 | 26/90 | 6/32 | RAISED | RAISED | PASS | **FAIL** | PASS | **NON-EQUIVALENT** |
| mid-convert | 3 | 28/90 | 8/32 | RAISED | RAISED | PASS | **FAIL** | PASS | **NON-EQUIVALENT** |
| post-convert | 1 | 52/90 | 32/32 | RAISED | RAISED | PASS | PASS | PASS | PROVISIONAL |
| post-convert | 2 | 52/90 | 32/32 | RAISED | RAISED | PASS | PASS | PASS | PROVISIONAL |
| post-convert | 3 | 52/90 | 32/32 | RAISED | RAISED | PASS | PASS | PASS | PROVISIONAL |

Verdicts are `sdip.equivalence.certificate.verdict_for`'s, not this probe's. Both raises are
the same typed error and it names the cause:

```
sdip.errors.UntrustedInputError: store carries no SDIP raw file header attribute
sdipRawTextHeader. The plane that needs it cannot be checked against this store.
```

`plane_4`'s failure carries an offset, which is what makes it a diagnosis rather than a
complaint — first repetition:

```
{'source_ordinal': 0, 'cell': [0, 0], 'first_sample': 128,
 'expected': 32.0, 'observed': nan, 'differing_samples': 896}
```

#### Where it does

`ingest()`'s sequence has four post-convert steps. A run that stops **between step 8 and step
9** — after `attach_raw_file_headers`, before `attach_raw_sample_view` and
`attach_header_plane` — leaves a store missing two whole arrays that passes everything.

That is not a hypothetical window. **Two of the three real credential expiries in question 4
landed in it**, both with markers `01_spec_ready, 02_convert_done, 03_raw_file_headers_done`
and a 52-object store on which all five planes returned `PASS` and
`verdict_for(planes, {"G7": "PASS"})` returned **`EQUIVALENT`**.

`sdip verify` cannot be handed a URL, so the state was reconstructed on the local filesystem
— ingest normally, then delete exactly the two arrays the expiry deleted — and the shipped
command run against both:

```
--- complete store (82 files) ---          --- truncated store (68 files) ---
[PASS] G1        G1 PASS: 97 fields …      [PASS] G1        G1 PASS: 97 fields …
[PASS] Plane 1 (G2a)  Textual header …     [PASS] Plane 1 (G2a)  Textual header …
[PASS] Plane 2 (G2b)  Binary header …      [PASS] Plane 2 (G2b)  Binary header …
[PASS] Plane 3 (G2c)  All 240 trace-…      [PASS] Plane 3 (G2c)  All 240 trace-…
[PASS] Plane 4 (G2d)  Live samples …       [PASS] Plane 4 (G2d)  Live samples …
[PASS] Plane 5 (G2e)  Cardinality, …       [PASS] Plane 5 (G2e)  Cardinality, …
[PASS] G4        stock zarr+xarray …       [PASS] G4        stock zarr+xarray …

verify: PASS       exit 0                  verify: PASS       exit 0
```

**The two outputs are identical.** `amplitude_raw_ibm32` (9 files) and `headers_raw_uint8`
(5 files) are gone and nothing printed says so.

**The engine is not blind to it — the verdict is.** `plane_4`'s evidence records the fact
precisely, and the code is explicit about what it means:

```
raw_ibm32_view_present  : False
raw_ibm32_words_verified: False
raw_ibm32_identical     : None
raw_ibm32_note          : "store carries no amplitude_raw_ibm32 array. Written only for an
                           ibm32 source (OPEN_DEBTS D1); its absence is NOT evidence that
                           the raw words match."
```

That evidence reaches `--json`. It never reaches the human output, and **no verdict consults
it**. `_raw_ibm32_evidence` treats an absent array as *not checked* rather than *checked and
passed*, which is correct for a `float32` source that legitimately has none — but the verdict
cannot tell "this source has no raw view because it does not need one" from "this source is
`ibm32` and its raw view was never written". This fixture's source **is** `ibm32`
(`TraceDataSpec(format=ScalarType.IBM32)`).

**What is and is not lost, stated exactly.** The decoded `amplitude`, `headers`, `trace_mask`
and both file headers are complete and correct in this store; every plane's primary
comparison genuinely passes. What is missing is the pair of parallel arrays that exist
*because those primary comparisons are known to be insufficient*:

- `amplitude_raw_ibm32` — the undecoded `uint32` view, written because P2 measured
  `ibm32 → float32` as not exactly invertible: 2,447 of 4,103 words fail bit-identity and
  1,939 lose the value (`OPEN_DEBTS` D1).
- `headers_raw_uint8` — the byte plane, written because P4 measured three Zarr readers
  disagreeing about the structured `headers` dtype (`DECISIONS.md` D-0047).

So the store that passes is one from which the D1 and D-0047 mitigations have vanished
silently. `sdip certify` is not exposed the same way — it performs its own ingest, cannot be
pointed at a pre-existing partial store, and records `raw_view_present` on the certificate.
But `ibm32_blocks_equivalence` does **not** consult `raw_view_present`; it blocks only when
the round trip is not byte-identical. And §11.2's *"persist and verify before terminating
ephemeral compute"* names **verify**, which is the command that says `PASS`.

#### The single-object controls: each corruption fails its own plane and only its own

The kills cannot be steered to a chosen object, so the mechanism was pinned separately, in
the G7 style: take a complete store, delete exactly one object, run the planes.

| Object deleted from a complete 42-object store | Targets | P1 | P2 | P3 | P4 | P5 | Verdict |
|---|---|---|---|---|---|---|---|
| *nothing — baseline* | — | PASS | PASS | PASS | PASS | PASS | PROVISIONAL |
| `amplitude/c/0/0/0` | `plane_4` | PASS | PASS | PASS | **FAIL** | PASS | **NON-EQUIVALENT** |
| `headers/c/0/0` | `plane_3` | PASS | PASS | **FAIL** | PASS | PASS | **NON-EQUIVALENT** |
| `trace_mask/c/0/0` | `plane_5` | PASS | PASS | PASS | PASS | **FAIL** | **NON-EQUIVALENT** |
| `amplitude_raw_ibm32/c/0/0/0` | `plane_4` | PASS | PASS | PASS | **FAIL** | PASS | **NON-EQUIVALENT** |
| `headers_raw_uint8/c/0/0/0` | `plane_3` | PASS | PASS | **FAIL** | PASS | PASS | **NON-EQUIVALENT** |

Every case fails the plane whose data went missing and no other — the property §7 G7 calls
for, measured in the object-store setting rather than assumed to carry over.

**Note the asymmetry, which is the whole finding in one line: deleting *one chunk* of
`amplitude_raw_ibm32` fails `plane_4`; deleting the *whole array* passes it.** A missing chunk
reads back as `fill_value` and is caught; a missing array is treated as a source that never
had one.

The baseline reads `PROVISIONAL` rather than `EQUIVALENT` only because this harness hands
`verdict_for` a `G7: NOT_RUN`; it does not run G7 itself. That is the harness's scope, not a
statement about the store.

#### The first kill pass missed, and it is kept

The first attempt used the 83 MB fixture and an S3 `LIST` poll as the kill trigger. **All six
kills landed after the chunk flush had completed** — dask writes chunks in a burst and a
`LIST` round trip is far slower — so every wreck looked like the post-convert case and
`plane_4` never had a missing chunk to catch. That pass is kept unedited at
`local/p8/logs/step3_kill_slowpoll_83MB.json`. A measurement that missed its target is still
a measurement, and the fix — a bigger fixture and a poll of MinIO's own storage directory
instead of its API — is what a stranger reproducing this needs to know.

---

### 2. Byte equality against the local-filesystem ingest of the same source. **Identical.**

The 30-trace article, ingested twice from the same source: once to MinIO, once to the local
filesystem through the real `sdip.ingest.ingest`. The object store's 22 objects were then
downloaded and compared as **stored bytes**, never through a decompressor — reading them back
through `zarr` would normalise away exactly the difference being measured.

| Comparison | Result |
|---|---|
| Chunk files compared | 10 |
| Chunk files present on only one side | 0 |
| Chunk files differing | **0** |
| Arrays compared with `numpy.array_equal` | 11 of 11 — `amplitude`, `amplitude_raw_ibm32`, `cdp_x`, `cdp_y`, `crossline`, `headers`, `headers_raw_uint8`, `inline`, `segy_file_header`, `time`, `trace_mask` |
| Arrays not equal | **0** |
| `zarr.json` files compared | 12 |
| `zarr.json` files differing | **1** — the root |

The one differing file was diffed leaf key by leaf key: **8 leaf keys, 1 differing.**

```
.attributes.createdOn
  local filesystem : 2026-08-23 00:10:04.404170+00:00
  object store     : 2026-08-23 00:10:01.097038+00:00
```

Both files are 304 bytes. That key is the one `sdip.equivalence.determinism` excludes by name,
for the reason it gives: MDIO writes `createdOn`, so it is not reproducible between any two
runs, on any storage. **Every other byte of the store is identical.** All five planes pass
against both copies.

---

### 3. Interruption: checkpoint, or unambiguous incompleteness? **Neither.**

**There is no checkpoint.** Re-running the same ingest over the wreckage took **36.13 s**
against **36.91 s** for a fresh run and ended at 90/90 objects. It restarted; it did not
resume. Nor is there anything to resume *from*: in all six wrecks the store contains **no
object that is not an array, its metadata, or a chunk** — no manifest, no progress record, no
lock, no marker.

That is worth separating from the falsifier, because §11.2 does not phrase it as one branch of
a disjunction:

> **Checkpoint-on-write is mandatory for any long run.** A harness that can return nothing
> after hours is a defect.

**Mandatory, and absent.** Whatever the interruption semantics are judged to be, a 284 MB
ingest killed six seconds in loses all six seconds, and a survey that takes hours would lose
the hours.

The one part of the *original* method this leg satisfies outright is item 5,
*persist-and-verify before terminating ephemeral compute*: every plane result above came from
reading the store back out of MinIO in a fresh process, never from anything the ingest
remembered. `sdip.equivalence.planes` states that requirement in its own docstring — *"a
checker that validates its own in-memory copy is a tautology"* — and it holds against an
object store as written.

**The store is not unambiguously incomplete either.** Read with `mdio` asserted absent from
`sys.modules` — the assertion the `portability` CI job makes, because a §10.3 consumer has
neither MDIO nor the source SEG-Y:

| Store | Objects | Samples reading `fill_value` | Live traces holding fabricated samples | Warnings emitted |
|---|---|---|---|---|
| mid-convert rep 2 | 26/90 | 54,525,952 / 67,108,864 (**81.25 %**) | **65,536 / 65,536** | **0** |
| mid-convert rep 3 | 28/90 | 50,331,648 / 67,108,864 (**75 %**) | **65,536 / 65,536** | **0** |
| post-convert rep 1–3 | 52/90 | 0 | 0 | 0 |
| uninterrupted control | 90/90 | 0 | 0 | 0 |

The wreck opens as a normal Zarr group with all nine arrays declared at full size. Three
quarters of the samples come back as `amplitude`'s `fill_value`, which is `NaN`. `trace_mask`
— written before the kill, and correct — marks all 65,536 traces **live**. The store asserts
every trace is real while most of their samples are values that were never in the source.
**That is fabrication, SP12**, and nothing in the store says so.

> The incompleteness is **detectable** — by SDIP, holding the source SEG-Y, running the
> Equivalence Engine, *and only at the interruption points question 1 shows are caught*. It is
> **not declared**: not by the store, not to a reader without the source.

---

### 4. Credential expiry mid-ingest

**MinIO's STS will not issue a credential shorter than 900 seconds.** Measured, not read: 15,
60, 300 and 899 are all refused with `invalid token expiry`; 900 succeeds. The expiry
therefore cannot be shortened to fit the run, so the run was moved to fit the expiry — take a
token, wait out almost the whole 15 minutes, start the ingest 8 seconds before it dies. Three
repetitions, staggered 90 s apart so three 15-minute lifetimes overlap into ~19 minutes.

**Two controls, because a green result here would otherwise be unreadable:**

| Control | Result |
|---|---|
| Token accepted while alive (`ListObjectsV2` at mint time) | `200` — 3/3 |
| Same token after the run | **`403 InvalidAccessKeyId`** — 3/3. Expiry is genuinely enforced. |
| Did any object write cross the expiry instant? | **No** — 3/3. Newest object mtime precedes expiry by 0.8–2.0 s in every run. |

| Rep | Exit | Seconds | Stages completed | Objects | Planes | Verdict |
|---|---|---|---|---|---|---|
| 1 | **1** | 10.51 | spec, convert, raw file headers | 52/90 | PASS ×5 | **`EQUIVALENT` if G7 passes** |
| 2 | **1** | 10.67 | spec, convert, raw file headers | 52/90 | PASS ×5 | **`EQUIVALENT` if G7 passes** |
| 3 | **1** | 9.28 | spec only | 16/90 | RAISED, RAISED, FAIL, FAIL, PASS | NON-EQUIVALENT |

**The failure is typed and it is not a crash**, which is what the original method asked for:

```
PermissionError: The Access Key Id you provided does not exist in our records.
```

But the message names the wrong thing. MinIO deletes the STS key on expiry, so the client sees
"does not exist" rather than "expired" — `ExpiredToken` and `InvalidToken` appear nowhere in
any of the three runs. An operator reading that line would go looking for a misconfigured key,
not an expired session.

**And two of three landed in the window question 1 describes.** A credential that dies in the
seconds between `attach_raw_file_headers` and `attach_raw_sample_view` produces a store that
`sdip verify` calls `PASS`. That is not a contrived interruption point; it is where this fault
naturally lands, because those two steps are separated by a long local read of the source.

#### The first expiry pass was void, and it is kept

The first attempt reported all three runs succeeding with 90/90 objects and five passing
planes. **It measured nothing.** `run_with` built an environment carrying the STS credentials
and called `subprocess.run` **without `env=`**, so the child never saw them, fell through to
`install_credentials()`, and ran on MinIO **root** credentials, which never expire.

It was caught by asking why a run that outlived its credential by 13 seconds had no errors.
MinIO's storage directory says **21 of 90 objects carry mtimes after the stated expiry** — not
plausible against a server that enforces expiry, and the `403` control proves it does. The
green result was the harness, not the backend. `local/p8/step6_credential_expiry.py` carries a
`VOID` banner and its log is kept; `step6b_expiry_enforced.py` is the measurement.

**Suspect your test before you suspect the dependency** — twice in this leg. The other one: the
first pass of steps 3 and 4 keyed the plane mapping `P1…P5` while `verdict_for` looks planes up
by `PLANE_KEYS` (`plane_1`…`plane_5`). An unrecognised mapping reads as "no plane reported
anything" and returns `PROVISIONAL` rather than raising, so every wrecked store came back
`PROVISIONAL` when the true answer was `NON-EQUIVALENT`. The shipped caller builds that mapping
from `PLANE_KEYS` itself and is not exposed; the harness was. Both passes were re-run after the
fix and the tables above are the corrected numbers.

---

### Verdict against the declared falsifier

> **A partially written store that validates as complete**, or a byte difference between the
> object-store ingest and the local-filesystem ingest of the same source, or an interruption
> that leaves neither a resumable checkpoint nor an unambiguously incomplete store.

| Limb | Fired? | Evidence |
|---|---|---|
| **A partially written store that validates as complete** | **YES** | A 52/90-object store, produced by 2 of 3 real credential expiries, passes all five planes. `sdip verify` prints `verify: PASS` and exits 0, with output byte-identical to a complete store. `verdict_for(planes, {"G7": "PASS"})` returns `EQUIVALENT`. |
| A byte difference against the local-filesystem ingest | No | 10/10 chunk files identical, 11/11 arrays `array_equal`, one differing leaf key and it is `createdOn`. |
| An interruption leaving neither a checkpoint nor an unambiguously incomplete store | **YES** | No checkpoint, measured — a restart re-ingests from zero, and no non-chunk object exists to resume from. No incompleteness marker on the store, no warning to a stock-`zarr` reader. |

**The falsifier fired.** Per the amendment's own *If it fires* clause, the first limb is the one
it names as the most serious outcome and as **security-class** under `SECURITY.md`, because it
produces a false `EQUIVALENT`. It is reported as such, with the scope stated plainly: the data
a reader would call primary is intact in that store; what vanished silently is the pair of
arrays that exist precisely because the primary data is known not to be sufficient on its own.

**Cloud deployment does not proceed. D7 stays open**, as the amendment declared it would
regardless of outcome, and it now carries a second item: the cloud entry point does not exist,
and fails silently when used.

---

### Findings

**F1 — a store missing `amplitude_raw_ibm32` and `headers_raw_uint8` validates as complete.**
`verify: PASS`, exit 0, output indistinguishable from a complete store. Reached by 2 of 3 real
credential expiries. `plane_4` records `raw_ibm32_view_present: False` in evidence that reaches
`--json`, is never printed, and gates nothing. Deleting one *chunk* of that array fails
`plane_4`; deleting the *array* passes it. **Security-class per the amendment.** What should
consult array presence — `verdict_for`, `ibm32_blocks_equivalence`, a plane, or a new gate — is
a maintainer decision this probe does not presume to make; no `src/sdip` file was touched.

**F2 — `sdip ingest` silently writes to the local filesystem when given an `s3://` URL and
reports success.** Exit 0, `G1 PASS`, a store in a directory named `s3:` under the working
directory, zero objects in the bucket. `Path(output).resolve()` in
`sdip.ingest.orchestrator.ingest`. Either reject a non-filesystem path with a typed error or
carry the URL through; both are maintainer calls.

**F3 — no checkpoint exists, and §11.2 makes one mandatory.** A restart re-ingests from zero;
nothing on the store records progress.

**F4 — an interrupted store is fabrication that announces nothing.** 75–81 % of samples read
back as `NaN` `fill_value` with `trace_mask` calling every trace live, under stock `zarr`, with
zero warnings. SDIP catches it at that interruption point; a §10.3 portability consumer cannot,
having no source to compare against.

**F5 — a credential expiry surfaces as `PermissionError: The Access Key Id you provided does not
exist in our records`.** Typed, non-zero exit, no crash, no write past the expiry — but the
message points at a misconfigured key rather than an expired session, and `ExpiredToken` never
appears. Worth knowing before someone debugs it at 3 a.m.

**F6 — `sdip verify` on a store missing its raw file headers used to exit by traceback.**
Measured at orchestrator digest `fbbc97a7…`: empty stdout, `Traceback (most recent call last)`,
exit 1. **This was independently found and fixed while this probe ran** (commit `2e05144`,
"catch every SdipError at the CLI boundary"); re-measured after it, the same wreck yields
`sdip: UntrustedInputError: store carries no SDIP raw file header attribute sdipRawTextHeader.`
and exit 1 with no traceback. Recorded because two residual points survive the fix: `verify`
still prints no verdict for such a store, and because `plane_1` raises first, **planes 3, 4 and
5 never run** — the one that would have reported `FAIL` with an offset is never reached.

**F7 — MinIO's STS will not issue a credential shorter than 900 seconds.** 15, 60, 300 and 899
refused with `invalid token expiry`; 900 accepted. Recorded because the shape of question 4's
method follows from it.

---

### What this leg does NOT discharge

Restating the amendment, because both the pass and the failure above are narrower than they
look:

- **Real cloud throttling, transient 5xx, connection resets and eventual consistency were not
  exercised.** MinIO on loopback does none of them.
- **GCS and Azure were not touched at all.** Two of the three named backends remain entirely
  unmeasured.
- **Nothing here ran for hours.** The original falsifier — *"a run that can return nothing after
  hours"* — is about duration and long-lived credentials. The longest measurement is a
  37-second ingest; the credential lifetime was 15 minutes because that is the shortest MinIO
  will issue.
- **The stores validated here were not produced by SDIP as it ships.** They came from a harness
  that bypasses the `Path(...).resolve()` blocker. Every "works against an object store"
  statement is conditional on a code change that has not been made.
- **F1 is not conditional on the object store.** It was reproduced on the local filesystem and
  is a property of the Equivalence Engine, not of S3. The object store is how this leg found it,
  not where it lives.

**`OPEN_DEBTS.md` D7 stays open.** No claim about S3, GCS or Azure behaviour may cite this leg.
It answers what a real S3 server on loopback can decide, and nothing beyond that.

---

### To reproduce

The harness is in `local/p8/`, inside the publication firewall and not committed. The
credentials below are throwaway MinIO root credentials for a server bound to `127.0.0.1` and
are worthless anywhere else.

```
mkdir -p local/p8/data/sdip-p8
MINIO_ROOT_USER=sdipprobe MINIO_ROOT_PASSWORD=sdipprobe123 \
  minio server local/p8/data --address 127.0.0.1:9000 &

uv run python local/p8/step1_sdip_to_s3.py           # question 0
uv run python local/p8/step2_objectstore_ingest.py   # question 2
uv run python local/p8/step3_kill.py                 # questions 1 and 3 - 6 kills
uv run python local/p8/step4_missing_chunk.py        # single-object controls
uv run python local/p8/step5_portable_view.py        # what a reader without MDIO sees
uv run python local/p8/step6b_expiry_enforced.py     # question 4 - about 19 minutes
uv run python local/p8/step7_cli_verify_on_wreck.py  # F6, local filesystem only
uv run python local/p8/step8_truncated_verify.py     # F1, local filesystem only
```

`step6_credential_expiry.py` is **void** and is kept only as the record of a harness bug; do not
cite it. Every run writes its evidence to `local/p8/logs/*.json`, and `local/p8/README.md`
records what each script measures and why.

---

### Addendum, appended 2026-08-23 — F2 is closed. Nothing above is edited (**SP10**)

**F2 above is now stale, and this note is how that is recorded** — the entry stays as
written, because it is what was measured. `sdip ingest` no longer accepts an `s3://`
output. `sdip.ingest.orchestrator.validate_output_path` refuses any URI scheme before the
source is read, before the spec is built and before anything is allocated, with a typed
`PhaseNotAuthorisedError` naming D7:

```
$ sdip ingest article.sgy s3://bucket/store.mdio
sdip: output path names the URI scheme 's3' (s3:/bucket/store.mdio). SDIP writes to the
local filesystem only; object-store output is NOT implemented (OPEN_DEBTS D7, probe P8) …
exit 2, working directory unchanged
```

`tests/negative/test_object_store_output_refused.py` holds the control: **32 tests, all
passing; 12 of them fail** when the single `validate_output_path(output)` call is unwired,
including the ordering proof, the working-directory proof and the CLI exit code. Recorded
in `DECISIONS.md` **D-0058**; `OPEN_DEBTS.md` D7 carries it as a known symptom.

**This closes F2 only.** It is a refusal, not object-store support — D7 is untouched and
every "not discharged" item above still stands. **F1 — the partially written store that
passes all five planes — is NOT addressed here**, is not conditional on the object store,
and awaits a maintainer ruling under §9.
