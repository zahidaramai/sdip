# Integration tests

**Status: phase F3.** The seed for this directory is the upstream round-trip test:

    tests/integration/test_segy_roundtrip_teapot.py
    https://github.com/TGSAI/mdio-python/blob/a2895b53088ffacbf4bd1b9e882856cbda78e235/tests/integration/test_segy_roundtrip_teapot.py

Apache-2.0, © TGS. **Attribution in `NOTICE` is a legal obligation and must survive
refactors** — see `NOTICE` section 3.

## What SDIP adds to the seed

The upstream test is scoped to **spec-declared header fields**. SDIP extends it to:

1. The full **240-byte** trace-header plane, including `uint8` fillers over bytes with
   no known semantic (**SP5**).
2. A whole-file **SHA-256** assertion on the export (**G3**), not a field-wise compare.
3. All five planes of the Equivalence Contract, not the round trip alone.

That extension is the contribution. The seed is TGS's.

## Rules that bind here specifically

- **Exact equality only.** No `allclose`, no `rtol`, no `atol`. A tolerance-based
  comparison is a specification defect (§4.5), and the `forbid-list` CI job greps for it.
- **`__main__` guard.** Any test that triggers ingestion must run behind one, or the
  `spawn` child re-executes the ingest and the pool dies with `BrokenProcessPool`
  (§11.1, Appendix A.5).
- **Suspect your test before you suspect the dependency.** The canonical failure mode
  here is Appendix A.4.2: the first round-trip comparison used a saved sample-template
  buffer as "expected", which is an IBM-encoded view — the library was correct and the
  test was wrong. **Is this number too good?** Impossible precision is a metric bug
  until proven otherwise.
