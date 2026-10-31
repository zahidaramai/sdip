# P16 — A file that declares a variable number of extended textual headers

> **SP9.** Committed **before** the run. The commit is local only: the workspace's top ruling
> forbids a push without the owner's command, and GeoSuite pushes under its own approval.
> Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P16` |
| Status | `REGISTERED` |
| Registered | 2026-10-31 |
| Registered by | Claude Code session, on GeoSuite's relay of owner D-216 |
| Blocks | nothing |
| Related debt | `OPEN_DEBTS.md` D8, residual 2 |
| Spec clause | §11.4; operating contract §3.6 |

## Question

When binary-header bytes 3505–3506 hold `-1` ("a variable number of extended textual headers,
ended by a stanza", defined since SEG-Y revision 1), what does each `sdip` command do? And when
a store is written, does it hold the file's traces or bytes from the wrong offset?

## Why it matters

`sdip.ingest.preflight` does not size a file whose bytes 3505–3506 hold `-1`. It returns
"layout unknown", and its comment says it is "letting the parser that can read stanzas
decide". The pinned `segy` 0.6.0 does not search for stanzas: `SegyFile._update_spec` copies
the binary-header value into the extended-header count unchanged. So nothing known reads the
stanza, and a `-1` reaches offset arithmetic as a count. If the first trace is then taken
from the wrong offset, the store is built from header bytes read as samples. A store like that
can still agree with itself, so this probe compares against data that is known to be right. D8
recorded that no corpus member covers the case, because the `segy` writer cannot produce one.
These members are built byte by byte instead.

## Method

1. **Members.** Each starts from the D8 well-formed 30-trace file (`make_poststack3d`, seed
   20260822, revision 1, `ibm32`, 3600 bytes of file headers then 30 traces). Bytes 3505–3506
   are set to `-1` (int16, big-endian), and 3200-byte EBCDIC (cp037) extended textual records
   are inserted between byte 3600 and the first trace:

   | Member | Records inserted after byte 3600 |
   |---|---|
   | `variable_extended_one_stanza` | one: the end stanza `((SEG: EndText))`, padded to 3200 bytes |
   | `variable_extended_two_records` | an ordinary record, then the end stanza |
   | `variable_extended_no_records` | none: `-1`, but the first trace sits at byte 3600 |
   | `variable_extended_unterminated` | one ordinary record, and no end stanza anywhere |

   The trace bytes in every member are byte-identical to the well-formed file's.
2. **Run.** Each member goes through the unchanged D8 child (library ingest, then CLI
   `ingest`, `verify`, `export`, `certify`), judged by P15's `falsifier_hits`.
3. **Ground truth for any member that converts.** The well-formed file is ingested with the
   library to a reference store. A member's store is compared with it:
   - `amplitude` under the live mask (`array_equal`);
   - the live-trace count;
   - `headers_raw_uint8` under the live mask.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| N | 4 members, each run once; plus the positive control |
| Timeout, memory ceiling | P15's: 300 s, 512 MiB |
| Environment | locked environment, `multidimio` 1.2.1, `segy` 0.6.0, this host |

## Falsifier

For **any** member:

- clauses 1–6 of P15; or
- **7:** the member converts, and its store's live-trace count is not 30, or its live
  `amplitude` or live `headers_raw_uint8` is not byte-equal to the reference store's.

## If it fires

The remedy is decided now. `preflight` refuses bytes 3505–3506 = `-1` with an
`UntrustedInputError`, in every command that runs the preflight. The message says that SDIP
and the pinned `segy` read extended headers by count only and cannot find the first trace. The
member becomes a permanent corpus member, as the negative control for that refusal. Refusing
an input revision 1 allows narrows supported input, so it is recorded as a new debt, and the
branch is reported to the owner through GeoSuite before `main` moves (operating contract §9).

## If it does not fire

D8 residual 2 closes for these four layouts. The members join the corpus with their
measured outcomes.

---

## Results — *appended after the run, never edited into the sections above*
