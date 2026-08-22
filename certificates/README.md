# Issued certificates

Every Equivalence Certificate SDIP issues is written here as JSON and indexed in
[`EQUIVALENCE_LEDGER.md`](../EQUIVALENCE_LEDGER.md).

**A certificate with `verdict != EQUIVALENT` is still committed.** Failures are
evidence (**SP10**). A directory containing only successes is a directory that has been
curated, and a curated evidence set is not evidence.

## Validation

Certificates validate against the SDIP certificate schema, shipped **inside the
package** at [`src/sdip/schema/`](../src/sdip/schema/) and versioned independently of
the software, so a third party can check SDIP output **without running SDIP**:

```bash
python -c "from sdip.schema import schema_path; print(schema_path())"

uvx check-jsonschema \
  --schemafile src/sdip/schema/sdip-certificate-v0.schema.json \
  certificates/*.json
```

`pip install sdip` carries the schema, so a consumer who never clones this repository
still has the validator. Several project rules are encoded as schema constraints rather than left to
prose, so an invalid certificate cannot be produced by accident:

| Constraint | Rule |
|---|---|
| `spec_itemsize` is `const: 240` | Every SEG-Y trace header is 240 bytes |
| `spec_gap_free` is `const: true` | A sparse spec is a rejected input, not a fast path (**SP4**) |
| `lossy_codec_present` is `const: false` | A store with a lossy codec is void (**SP3**) |
| `git.dirty` is `const: false` | A certificate from a dirty tree is invalid, with no override |
| `verdict: EQUIVALENT` implies all five planes `PASS` and G1/G2/G7 `PASS` | There is no partial credit |

That last row is the important one: it makes the strongest claim the project can make
structurally unrepresentable unless the evidence for it is present in the same document.

## Naming

    <source-sha256-first-12>-<issued-at-utc-compact>.json

The source hash comes first so certificates for the same source sort together, and the
timestamp disambiguates re-issues. Neither component is ever derived from file
*content* — §11.4 bars deriving a path from what a parsed file says.

## Status

**Empty.** The Equivalence Engine is roadmap phase F3; its non-vacuity suite is F4.

**Until G7 passes, every certificate the engine issues is unvalidated** (**D11**). Do
not publish certificates from an engine whose gates have never been shown to fail.
