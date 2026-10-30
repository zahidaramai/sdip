# Where each cited section is restated

SDIP's governing specification and its operating contract are kept on the working copy and
are not published (`DECISIONS.md` D-0010). Public files still cite them by number - `§4.2`,
`§7` - so this file names, for **every** section number cited in a published file, a public
file and a verbatim line where that rule is restated. `tests/unit/test_section_citations.py`
fails on a citation with no entry and on an entry whose line is missing, duplicated, or in an
unpublished file (`OPEN_DEBTS.md` D13, owner ruling D-0106).

**Read the scheme.** `spec` is the specification's numbering; `contract` is the operating
contract's, which numbers differently (its §3.3 is "public API only", the specification's §3.3
is "upstream pins"). Older records cite both with a bare `§N`; where a number is used under
both, both are listed. `external` is another document cited by its own numbers. A `note` says
where a restatement covers only part of a section.

**What this does not prove:** that a restatement says what the private text says. That is a
maintainer's reading; this index makes drift visible instead of silent.

```json
[
 {
  "section": "0",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "an MDIO store without a passing certificate is an untrusted"
 },
 {
  "section": "0.1",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "Every SEG-Y conversion is a chance to lose something quietly"
 },
 {
  "section": "1",
  "scheme": "external",
  "file": "NOTICE",
  "anchor": "SDIP - Seismic Data Ingestion & Preparation",
  "note": "a section of NOTICE itself"
 },
 {
  "section": "1.2",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "Base specs for **rev 0, 1, 2, 2.1**; certified end to end on **rev 1**",
  "note": "Restates supported revisions only; the full rev 0-2.1 scope is in DECISIONS (D-0003 / P6)."
 },
 {
  "section": "1.3",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "**Processing.** SDIP does not filter, scale, resample, regrid, mute, interpolate, or"
 },
 {
  "section": "2.1",
  "scheme": "external",
  "file": "tests/fixtures/PROVENANCE.md",
  "anchor": "Sleipner CO2 Reference Dataset License",
  "note": "the Sleipner dataset licence, cited by its own section numbers"
 },
 {
  "section": "2.4",
  "scheme": "external",
  "file": "tests/fixtures/PROVENANCE.md",
  "anchor": "Sleipner CO2 Reference Dataset License",
  "note": "the Sleipner dataset licence, cited by its own section numbers"
 },
 {
  "section": "3",
  "scheme": "external",
  "file": "NOTICE",
  "anchor": "SDIP - Seismic Data Ingestion & Preparation",
  "note": "a section of NOTICE itself"
 },
 {
  "section": "3.2",
  "scheme": "contract",
  "file": "CHANGELOG.md",
  "anchor": "**An upstream pin bump is a MAJOR release**, because it **invalidates every certificate",
  "note": "operating contract: pins are binding; a bump is a maintainer decision"
 },
 {
  "section": "3.2",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "**Decision.** The \"pin, don't fork\" conclusion stands. No fork is authorised; the",
  "note": "States the conclusion; the reachability chain itself is tabulated in D-0002 (same entry)."
 },
 {
  "section": "3.3",
  "scheme": "contract",
  "file": "DECISIONS.md",
  "anchor": "**Ruling (maintainer).** SDIP files no issue, pull request or comment with any upstream project.",
  "note": "operating contract: public API only; nothing filed upstream (D-0089)"
 },
 {
  "section": "3.3",
  "scheme": "spec",
  "file": "NOTICE",
  "anchor": "Pinned version 1.2.1 (release tag v1.2.1), commit",
  "note": "States the pin for multidimio (segy pin on the following lines). The consequence of a bump is at CHANGELOG.md line 8 and SECURITY.md line 27."
 },
 {
  "section": "3.4",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "| `HeaderSpec.customize` merges into an existing spec | `segy/schema/header.py:270`",
  "note": "Restates the SHA-less file:line references as a verified table; spec 3.4 itself is a list of URLs, not a rule."
 },
 {
  "section": "3.5",
  "scheme": "contract",
  "file": "README.md",
  "anchor": "**In the container, `certify` needs a git working tree** — it refuses to issue from one",
  "note": "operating contract: a certificate from a dirty tree is invalid"
 },
 {
  "section": "3.6",
  "scheme": "contract",
  "file": "SECURITY.md",
  "anchor": "partner exchange, an email attachment. A malformed or deliberately hostile file must",
  "note": "operating contract: untrusted input"
 },
 {
  "section": "4",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "runs an **Equivalence Engine** over five independent planes and exports back to SEG-Y"
 },
 {
  "section": "4.1",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "**All five must hold simultaneously.** There is no partial credit"
 },
 {
  "section": "4.2",
  "scheme": "contract",
  "file": "CONTRIBUTING.md",
  "anchor": "- Satisfies **exactly one** gate or one probe leg. Nothing more.",
  "note": "operating contract: the smallest thing that satisfies the gate"
 },
 {
  "section": "4.2",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "If bytes cannot be decoded, the **raw 3200 bytes are preserved** and the decode failure",
  "note": "Quotes the rule; also quoted in OPEN_DEBTS.md."
 },
 {
  "section": "4.3",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "The 400 bytes are preserved; the raw bytes are authoritative"
 },
 {
  "section": "4.4",
  "scheme": "contract",
  "file": "CONTRIBUTING.md",
  "anchor": "### Commit messages report claims with numbers",
  "note": "operating contract: report claims with numbers"
 },
 {
  "section": "4.4",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "All **240 bytes** of every trace are recoverable, bit-exact"
 },
 {
  "section": "4.5",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "Every live sample is bit-exact after the declared decode"
 },
 {
  "section": "4.6",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "Trace count, ordering, live mask and duplicates all reconcile"
 },
 {
  "section": "4.7",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "The certificate is a **JSON document**, validated against a published schema"
 },
 {
  "section": "5",
  "scheme": "contract",
  "file": "CONTRIBUTING.md",
  "anchor": "## The G7 discipline — write the failure first",
  "note": "operating contract: write the failure first"
 },
 {
  "section": "5",
  "scheme": "spec",
  "file": "CHANGELOG.md",
  "anchor": "**Gap-free spec generator** (`sdip.spec`) implementing §5.1: one `uint8` filler per"
 },
 {
  "section": "5.1",
  "scheme": "spec",
  "file": "CHANGELOG.md",
  "anchor": "**Gap-free spec generator** (`sdip.spec`) implementing §5.1: one `uint8` filler per",
  "note": "Same anchor as section 5; the next line adds pad_<byte> naming (SP5)."
 },
 {
  "section": "5.4",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "measured 19.4 B/trace, but on synthetic headers carrying",
  "note": "Records the figure by comparison with a real measurement; no public file tabulates the 5.4 table."
 },
 {
  "section": "6",
  "scheme": "contract",
  "file": "CONTRIBUTING.md",
  "anchor": "## Test data policy — binding",
  "note": "operating contract: test data policy"
 },
 {
  "section": "6",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "**No proprietary or restricted data enters this repository, ever.** Fixtures are either",
  "note": "The only spec-cited use of bare section 6 (prereg/P12-f3-certify.md) means 6.6, the test data policy."
 },
 {
  "section": "6.2",
  "scheme": "spec",
  "file": "CHANGELOG.md",
  "anchor": "All required public-project files (§6.2): `LICENSE`, `NOTICE`, `README.md`,",
  "note": "Lists the files; the per-file purpose table is not restated."
 },
 {
  "section": "6.3",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "The tree as it stands (specification §6.3, restated here because the",
  "note": "restated in CONTRIBUTING.md for D13; the tree as it stands, not as first drafted"
 },
 {
  "section": "6.4",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "Overrides (§6.4) are declarative data — never code branches. Each carries a provenance"
 },
 {
  "section": "6.4.1",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "Ingest writes the survey declaration's digest into the provenance marker.",
  "note": "Ruling 1 of the entry lists binding; the D-0091 whole-declaration amendment is only partly restated."
 },
 {
  "section": "6.5",
  "scheme": "spec",
  "file": "OPEN_DEBTS.md",
  "anchor": "Prestack chunking is `UNMEASURED`. **Do not guess in production.**",
  "note": "Covers the prestack/UNMEASURED rule; the template class table and the (128,128,128) default are in the line above."
 },
 {
  "section": "6.6",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "**No proprietary or restricted data enters this repository, ever.** Fixtures are either"
 },
 {
  "section": "7",
  "scheme": "contract",
  "file": "README.md",
  "anchor": "## CLI reference",
  "note": "operating contract: commands"
 },
 {
  "section": "7",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "Gates are binary (§7); the report type has no",
  "note": "Restates only \"gates are binary\"; individual gate definitions G1-G7 are spread over README, DECISIONS and the gate tables."
 },
 {
  "section": "7.8",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "and when a maintainer starts it by hand — never on push** (`DECISIONS.md` D-0095), as two",
  "note": "Restates the amended CI shape (two jobs); the 10-assertion table is not restated in CONTRIBUTING (ci/README.md has the list)."
 },
 {
  "section": "8",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "Probes are pre-registered (**SP9**). The order is not negotiable:"
 },
 {
  "section": "8.9",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "**Decision.** The \"pin, don't fork\" conclusion stands. No fork is authorised; the",
  "note": "Partial: states no fork is authorised and the fallback dormant. The clause \"activates only if a named falsifier fires, by maintainer decision\" is not stated in any public file."
 },
 {
  "section": "9",
  "scheme": "contract",
  "file": "CONTRIBUTING.md",
  "anchor": "## When to stop and ask",
  "note": "operating contract: when to stop and ask"
 },
 {
  "section": "9",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "`sdip doctor` checks the Python version, the binding upstream pins, barred packages and environment variables"
 },
 {
  "section": "9.1",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "`MDIO__IMPORT__RAW_HEADERS` are barred (§9.1). Setting them makes tests pass and the",
  "note": "Names the two original barred variables; the later additions (SEGY_*, MDIO__GRID__*, MDIO__IMPORT__CLOUD_NATIVE, library config) are in DECISIONS.md D-0087 / D-0088 and sdip._pins.UPSTREAM_SETTINGS."
 },
 {
  "section": "9.5",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "1. **A tolerance-based comparison in the equivalence engine.** `np.allclose` on samples",
  "note": "Covers tolerance and processing (item 5) and warning suppression (item 2); dirty-tree issuance is at CONTRIBUTING line 54."
 },
 {
  "section": "10.1",
  "scheme": "spec",
  "file": "SECURITY.md",
  "anchor": "The certificate is what a downstream consumer trusts instead of",
  "note": "Partial: no public file says a non-EQUIVALENT store must not be presented downstream as confirmed data."
 },
 {
  "section": "10.3",
  "scheme": "spec",
  "file": "README.md",
  "anchor": "The output is **plain Zarr v3**. Neither SDIP nor MDIO is needed to read it"
 },
 {
  "section": "11.1",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "MDIO's header parser uses a **`spawn`** multiprocessing context. **Every entry point",
  "note": "Worker-count pinning (second paragraph of spec 11.1) is not restated there."
 },
 {
  "section": "11.2",
  "scheme": "spec",
  "file": "OPEN_DEBTS.md",
  "anchor": "checkpoint-on-write. A harness that can return nothing after hours is a defect.",
  "note": "Also OPEN_DEBTS.md line 1224 quotes the mandatory clause."
 },
 {
  "section": "11.3",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "`doctor` exits 1 on a dirty working tree. That is intentional and there is no override",
  "note": "Covers the dirty-tree rule only; sha256-before-and-after and environment capture are not restated there (README line 182 / certificate section cover the latter)."
 },
 {
  "section": "11.4",
  "scheme": "spec",
  "file": "SECURITY.md",
  "anchor": "**SDIP parses untrusted binary input.** A SEG-Y file is a header-length-prefixed binary"
 },
 {
  "section": "12.1",
  "scheme": "spec",
  "file": "CONTRIBUTING.md",
  "anchor": "Changes to §4, §5, or §7 require maintainer consensus and a **successor specification"
 },
 {
  "section": "12.4",
  "scheme": "spec",
  "file": "CHANGELOG.md",
  "anchor": "**An upstream pin bump is a MAJOR release**, because it **invalidates every certificate",
  "note": "Public text says MAJOR (corrected at 1.0.0, CHANGELOG line 12); spec 12.4 as written says minor. Spec and public record disagree."
 },
 {
  "section": "13",
  "scheme": "spec",
  "file": "DECISIONS.md",
  "anchor": "| **F0** | Repo skeleton, public files, `NOTICE`, `sdip doctor` | **complete** |",
  "note": "The Phases (spec 13) table in the status snapshot; phase table restated with states."
 }
]
```
