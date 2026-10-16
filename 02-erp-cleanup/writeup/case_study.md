# The automation that retires itself, demonstrated

*Hapax Oy case study. The company, the documents, and the one deliberately unfixable error described below are invented. The measurements are real, taken against an answer key we wrote before any parsing ran.*

## The problem

Jalavakoski Konepaja Oy is a Tampere machinery manufacturer with about 350 employees, exporting across the Nordics and Germany. Its SAP R/3 system was implemented in 2003 by a German consultancy, and nobody has touched the configuration since. Month-end reports still arrive as raw text exports from five standard SAP transactions (FBL3N, ME2M, VA05, FBL1N, MB52): fixed-width columns, repeated page headers, German number formats such as 1.234,56, status codes like @0A@ sitting inside the data, and totals rows distinguishable from ordinary line items only by indentation. One person has read these reports competently for two decades. That person retires this year.

Two fixes usually get proposed. Rebuilding the ERP is a seven-figure project that nobody signs off in a year when nothing is visibly broken. Putting an LLM permanently in the parsing path works from day one, but it bills per document for as long as the reports keep coming, a standing cost with no end date.

The third option is what this case study demonstrates. An agent parses the documents directly; it is slow and it costs money, but it works. An overseer watches what the agent produces, and once it has seen enough structurally consistent examples of one report type, it writes an ordinary Python parser for that type: code that runs in milliseconds and costs nothing per document. Month by month, less of the stream needs the agent at all. This is the demonstrated version of an exemplum on Hapax's advisory page, "the automation that retires itself," presented there as hypothetical. Here it runs on data we built and can score.

Jalavakoski Konepaja Oy does not exist. We wrote the generator that produced its 240 month-end reports, we hold the answer key for every field in every one of them, and neither the parsing agent nor the parser-writing overseer was ever allowed to read that key.

## What happened, in numbers

| Measure | Result |
|---|---|
| Deterministic share of the 240-document stream | 184 documents (76.7%), against a target of ≈75% set before the run |
| LLM-path field accuracy | 99.962% (34,470 fields across 56 documents; 13 wrong, one root cause) |
| Deterministic-path field accuracy | 100.000% excluding one planted silent error; 99.952% including it (137,726 fields across 184 documents; 66 wrong, all from that one document) |
| Hybrid pipeline cost, central estimate | ~$8.51 (band $5.32–$26.60) |
| All-LLM counterfactual cost, central estimate | ~$21.81 (band $13.63–$68.15) |
| Estimated saving | ~61% of the counterfactual, on this stream length |

The accuracy figures are exact. Every field was checked against the answer key. The cost figures are estimates. We ran the LLM path as Claude Code subagents, not metered API calls, so there is no invoice to point to. Instead we applied published per-token prices to measured token counts, as a band running from an all-input floor to an all-output ceiling, with a central estimate at a stated 85/15 input-to-output split. The all-LLM counterfactual is modelled the same way.

From month 3 of the twelve-month stream onward, every routine document parses deterministically, in single-digit milliseconds, at zero marginal cost. That claim is more durable than the whole-stream percentage above it. The percentage depends on how long the stream runs and how much of it is discovery; the month-3 floor does not.

## How the pipeline works

An agent reads each raw document and returns a structured record (header fields, line items, totals) against a schema shared by every part of the system. This step is the expensive one. One model call per document, schema-validated on the way out, with a logged retry if the schema check fails.

An overseer watches the agent's accepted output accumulate, per report type, and checks whether each new parse has the same fields, the same shape, and the same layout as the ones that came before it.

After eight consistent parses of one type, the overseer writes an ordinary deterministic parser for that type. No model is involved at run time; the parser is plain code, pattern matching and arithmetic, nothing learned, nothing probabilistic. Five report types produced five generated parsers over the course of the stream. Writing them cost an estimated $3.50 in total, and that cost was recouped roughly twice over within this single 240-document demonstration.

A generated parser does not go live on trust. It has to reproduce the agent's own accepted output on every document of that type parsed so far. That is a regression gate checked against the pipeline's own history, not against the answer key; nobody peeked at the correct answers to help a parser pass.

The router then sends each new document to the deterministic parser if one exists for its type, and every deterministic result is checked against the schema, its own arithmetic totals, and lookups against master data before it is accepted. If any check fails, the document falls back to the agent automatically, and the failure is logged.

## What the demonstration shows

Every document in the corpus was assigned a class before any parsing ran, and the evaluation is scored against that plan.

| Class | Design | Actual |
|---|---|---|
| Routine (218) | LLM during discovery, deterministic once a parser exists | 40 on the LLM path, 178 deterministic, zero field errors |
| Variant (6) | Stays on the LLM path (too rare to justify a parser) | 6 LLM fallbacks, as designed |
| Fail-and-recover (15) | Built to break the generated parser; validation should catch it and fall back | 10 as designed; 5 deviated |
| Silent error (1) | Passes every check and is quietly wrong | Deterministic path, 66 wrong fields, found only by the answer key |

The five deviations were vendor-line-item documents engineered with a mid-table currency change to break the generated parser and force a fallback. The overseer's parser for that report type treats currency as ordinary data and resolves per-currency totals in general, so all five parsed correctly on the deterministic path instead of failing over.

The one planted silent error took three attempts to design. The first version swapped an amount and a tax column on a G/L report; it was rejected at the design stage, because that report's totals are split by debit and credit and labelled to match, so a column swap would have thrown the arithmetic off in a way any check would catch. The second version swapped a purchase-order column pair, headers and values together; it was rejected empirically, because the generated parser for that report type resolves columns by their header label on each page and would have read it correctly regardless. The version that shipped corrupts the document itself. The header labels stay right, but the values under 2 adjacent columns (net price and value still to be delivered) are written into each other's positions. The printed total still reconciles, because it does not depend on which of the two columns a given number sits in. No reader working from the text alone catches this. Only the answer key sees it, which is the role an independent reconciliation against the source system plays in production. A line-level price-times-quantity check on the parsed values would catch it too (0,00 × 2.000 does not equal the printed 7.480,00). We recommend running that check on every deterministic parse, and keeping a sampled human reconciliation against source-system totals regardless of how clean the automated checks look.

One further result changes what "accuracy" means for the LLM path itself. The 40 discovery-wave documents, parsed under a precise brief, produced zero errors across 26,509 fields. A later batch of 16 fallback-wave documents, parsed under a brief that had been compressed for length, produced 13 field errors, all traced to one cause. The shorter brief dropped a qualifying phrase, and an agent captured a whole line of text, "1000 Jalavakoski Konepaja Oy," where it should have captured a four-digit code from within it. All 13 passed schema and master-data validation. Instructions to a model need the same version control as code.

## What this would mean on your ERP

The steady-state claim, every routine document handled deterministically at zero marginal cost from month 3, is the part of this result built to generalise. It follows from how the overseer works, not from anything specific to Jalavakoski Konepaja Oy's reports.

The numbers above will not be the same on another system. Real SAP installations vary enough between companies that no single canonical spool format exists to test against, which is why we built a synthetic one, grounded in documented conventions, not copied from any one real system. Your accuracy, your deterministic share, and your cost curve will depend on how consistent your own report formats actually are, and we do not know that until we look.

So the first step of an engagement on a real system is narrower than anything in this case study. It starts with a short audit of your actual exports, covering report types, monthly volumes per type, and how much genuine variation exists within a type against how much is just formatting noise. That tells us whether the overseer's learning threshold would trigger on your volumes at all, and roughly how long the discovery phase would run before deterministic parsing starts paying for itself.

## Method and reproducibility

The generation code, the corpus, the answer key, and the pipeline that parses it are all published. `code/` holds the document generator, the validator, the router, and the evaluation script. The model-path parses are recorded artefacts in `data/runs/llm_parses/`, and the five parsers the overseer wrote sit in `code/parsers_generated/` with provenance headers recording which documents generated them; neither stage re-runs. `data/` holds the 240 documents and their answer key. Every figure in this document reproduces from two scripts: `code/router.py`, which runs the stream, and `code/evaluate.py`, which scores it against the answer key, run against the corpus recorded in `data/runs/report.md` and `data/runs/evaluation.json`.
