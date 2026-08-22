# Negative controls — the G7 non-vacuity suite

> **A gate a corrupted store passes is not a gate.**

**SP11.** Every equivalence check carries a permanent negative control that **must fail
it**. Controls live here forever; they are not deleted when the bug they caught is
fixed. A failed configuration becomes the permanent negative control for its fix.

## The minimum set (§7 G7)

Each corruption must fail **its** gate and **only** its gate. A corruption that fails
the wrong gate is as much a G7 failure as one that passes.

| Control | Corruption | Must fail | Must NOT fail |
|---|---|---|---|
| `flipped_header_byte` | One bit in one trace header | **G2c** | G2a, G2b, G2d, G2e |
| `flipped_sample_bit` | One bit in one live sample | **G2d** | G2a, G2b, G2c, G2e |
| `dropped_trace` | One trace removed | **G2e** | G2a, G2b |
| `transposed_traces` | Two traces swapped | **G2e** | G2a, G2b |
| `inverted_live_mask` | Live mask flipped on one trace | **G2e** | G2a, G2b |
| `truncated_textual_header` | Textual header cut short | **G2a** | G2b, G2c, G2d, G2e |
| `roundtrip_byte_change` | One byte differs in the export | **G3** | — |

## Status

**Empty. `NOT_RUN`.**

No control exists because no gate exists: the Equivalence Engine is roadmap phase F3
and this suite is **F4**. Recorded as **D11** in `OPEN_DEBTS.md`.

**F4 is not optional and is not last.** Until G7 passes, every certificate the engine
issues is unvalidated. Do not publish certificates from an engine whose gates have
never been shown to fail, and say so in any report touching certificates.

## Adding a control

1. Write the corruption as a **deterministic** transform of a clean fixture — same seed,
   same bytes, every run.
2. Assert the target gate **fails**.
3. Assert every other gate **passes**. This half is the one people skip, and it is the
   half that catches an over-broad check.
4. Name what it defends in the docstring, citing the specification clause.

A PR that adds an engine check without its negative control fails the `negative` CI job.
That is by design and is not a bug in the job.

## Why "only its gate" matters

A checker that fails everything on any corruption looks maximally safe and is
maximally useless: it cannot localise a fault, and it will be silenced the first time
it fires on something benign. The five planes are separable claims (§4.1), and the
controls are what keep them separable in practice rather than only on paper.
