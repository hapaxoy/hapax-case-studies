# Findings report — invoice-processing pipeline runs

Written 3 July 2026 from `evaluation.json`, `stream_events.json`,
`parse_agent_log.json` and the agents' audit trails. Everything that went wrong or deviated
stays in.

## Scorecard against the pre-registered designed-outcome table

| Class | Designed | Actual | Verdict |
|---|---|---|---|
| R (165) | 48 LLM discovery + 117 deterministic | 48 discovery + **113 deterministic + 4 LLM fallback** | **Deviation, frozen**: four R documents are two-page; the s3/s8 parsers (single-page induction sets) refused them — see below |
| O (20) | 20 permanently LLM | 20 permanently LLM | As designed |
| T (8) | 6 LLM fallback → v2 → 2 deterministic | 6 fallback → parser_s8v2 → 2 deterministic | **Exactly as designed** — the re-learning arc worked end to end under the same N=6 rule as first learning |
| F (4) | 4 fail → LLM fallback | **3** fail → fallback; **1 defeated** | **Deviation, frozen**: F1 (the September fuel-surcharge line) parsed correctly — parser_s6's dynamic column derivation treats an unfamiliar line as data. The Case 2 FBL1N pattern: the plant was beaten by parser quality, and pre-registration is what makes that visible |
| S (1) | Deterministic, silently wrong | Deterministic, silently wrong | **Exactly as designed** — parses cleanly, passes schema, arithmetic and existence checks; only the answer key sees the transposed quantity/price |

Stream totals: 117 deterministic / 48 discovery / 13 fallback / 20 one-off = 198; router
consistency check PASS (the set of LLM-path documents equals the set of recorded parses,
both directions). Whole-stream deterministic share **59.1%** vs pre-registered 60.6% — the
gap is exactly the two deviations above (−4 two-page fallbacks, +1 defeated trap).

## The unplanned finding: two-page documents beat two parsers

The corpus naturally contains multi-page invoices. Where an overseer's induction set happened
to include one (s1, s4), the generated parser handles continuation pages generically. Where it
didn't (s3, s8's v1), the parser asserts single-page and **refuses rather than guesses** —
exactly the fail-loud posture the overseer's instructions require. Four documents (2025-05_s3_02,
2025-06_s3_01, 2025-11_s3_01, 2025-06_s8_02) therefore fell back to the LLM unplanned. At 3
and 1 documents per layout-pair they never reach the N=6 re-learning threshold, so they are
permanent LLM residents. This is the strongest unscripted illustration of the design's central
safety claim: what the parser has not seen, it does not invent. It also pushed the LLM-parse
count from the designed 78 to 81 (the pre-registered cap of 80 was raised to fit them).

## Accuracy (marked against the held-out answer key)

| Path | Documents | Fields | Errors | Accuracy |
|---|---|---|---|---|
| LLM (Sonnet subagents, vision reads) | 81 | 5,427 | **0** | **100.0000%** |
| Deterministic (9 generated parsers) | 117 | 8,223 | 0 excl. S | 100.0000% excl. S; 99.9757% incl. |
| Overall | 198 | 13,650 | 2 (both the S document) | 99.9853% incl. S |

- **The only wrong values in the entire pipeline are the S document's two fields — and they are
  wrong at the source.** The document prints quantity 50 × €2,00 where the true transaction was
  2 × €50,00; both paths read the document faithfully; every automated check passes (the line
  total, €100,00, is identical either way). Only the answer key — in production, a three-way
  match against the purchase order — catches it. This is the honest ceiling, exactly as
  pre-registered, and the production recommendation follows: run line-level PO reconciliation
  on every parse, however clean the extraction.
- **The feared vision-read failure mode did not materialise.** Dense identifiers (18–24-char
  IBANs, viitenumero and OCR references, VAT IDs) were transcribed without a single digit
  error across 81 documents in five languages. Zero schema-failure retries were needed
  (Case 2 had 3). One batch (U) demonstrated genuine two-page reading: s8's VAT ID appears
  only in the page-2 footer and was captured.
- **Instruction discipline held**: the parse and overseer instructions (v1) were used verbatim
  for every agent; no drift (the Case 2 lesson applied — its 13 field errors all traced to a
  mid-run instruction edit; this run made none).
- Four answer-key ground-truth defects were found and fixed during the run — all ours, none
  the agents' (payment-terms phrase vs config integer; null bank keys omitted; German register
  number conflated with its court — all three at D1 first contact; and a signed-zero artefact
  "-0.00" found by the F wave).
  In each case the rendered corpus was verified bit-identical across the fix. The answer key
  is the one artefact that must never be wrong; first contact with real parses is what proved
  it wrong, which is an argument for running exactly this kind of pipeline against any key
  before trusting it.

## Parser-birth timeline (from stream_events.json)

s1 (end Feb), s2/s8 (mid Mar), s5/s3/s4/s6 (late Mar), s7 (end Jun — the monthly-cadence slow
learner), s8v2 (late Oct — re-learning after the August redesign). All within the pre-registered
timing constraints. From April onward every routine invoice from seven suppliers parses
deterministically; the December stream ran 14 of 17 documents deterministic (82%), the
residue being two one-offs and the planted Swedish two-pager.

The long-tail exhibit: **8 of 26 suppliers (31%) were automated, and those suppliers carry
178 of 198 documents (90%) of the stream.** The other 69% of suppliers — 10% of volume —
stay with the LLM by design; automating any of them would cost more than it saves. Whole-year
deterministic share (59.1%) is lower than the supplier-volume figure because each parser's
discovery documents are LLM-path by construction; in steady state (post-birth months) the
automated suppliers' documents are 100% deterministic.

## Costs (LABELLED ESTIMATES — method B)

Measured subagent tokens (harness-inclusive, an upper bound on a purpose-built extractor):
1,885,139 total, of which 1,066,271 (57%) is the overseer generation wave (nine parser-writing
agents incl. self-tests) and 818,868 the 81 document parses (~10.1k tokens/document — vision
reads run ~7× Case 2's plain-text parses per document).

At published Sonnet list prices ($3/$15 per MTok; band = all-input floor to all-output
ceiling, central at an 85/15 split):

| Quantity | Band | Central |
|---|---|---|
| Hybrid pipeline, year 1 (parses + parser generation) | $5.66–$28.28 | **~$9.05** |
| All-LLM counterfactual (198 × mean parse tokens) | $6.01–$30.03 | **~$9.61** |
| Year-1 saving | — | **~6%** |

**The honest cost story is the amortisation, not the year-1 percentage.** At this stream
length the overseer's one-time cost (~$5.12 central) almost exactly equals the parse cost it
displaced in year 1 (117 deterministic documents × ~10.1k tokens ≈ $5.67 central): the
automation approximately pays for itself within the first year. The parsers are durable
artefacts — in a second year of the same stream, the LLM path would carry only the one-off
tail (20) plus the fallbacks that never reach the re-learning threshold (7; the redesign's
re-learning was a one-time event), i.e. 27 documents: roughly **$1.31 vs $9.61
counterfactual — an ~86% saving, about a seventh of the cost — and every year thereafter**.
The cost curve's crossover point, not the year-1 total, is the exhibit. Two further honesty notes: (i) introductory Sonnet pricing ($2/$10)
was actually in force on the run date (through 31 Aug 2026), which would reduce every figure
above by a further third — list prices are used for comparability with Case 2 and as the
conservative basis; (ii) subagent token counts include harness overhead, so the true marginal
cost of both the hybrid and the counterfactual would be lower in a purpose-built system —
the *ratio* is the robust claim, not the dollar figures.

Latency: per-batch wall-clock in `parse_agent_log.json`, harness-inclusive (a parse batch of
8 documents ran 2.5–5 minutes; a single deterministic parse runs in milliseconds).

## Process notes

- Every parse and overseer agent returned a complete files-opened/files-written audit list;
  all lists contain only assigned inputs + the pinned instructions. No agent touched the answer key,
  the HTML sources, config, templates, or another supplier's artefacts.
- Every batch was validated before the next was dispatched (schema +
  field-level accuracy); the overseer wave started only after all 68 discovery/one-off parses
  were verified perfect.
- Line-by-line code review of all nine generated parsers: stdlib+pdfplumber only, no I/O beyond
  the given pdf_path, no clock or randomness, no answer-key or config references, provenance
  headers and real fail-loud ParserLayoutError checks in all nine. Behavioural evidence: the
  198-document dry run and the router replay.
- Notable inductions: parser_s7's overseer inferred **banker's
  rounding from a single boundary document** (794,75 × 14% printed as 111,26, not 111,27);
  three overseers independently rejected pixel-coordinate matching after detecting auto-fit
  column drift and chose token anchors instead; two ran unprompted negative controls against
  other suppliers' documents (all correctly rejected); parser_s8v2 uses the invoice-number
  series ("2025-NNNN" vs "T-NNNN") as a hard discriminator against the old layout.
