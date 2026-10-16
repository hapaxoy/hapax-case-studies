# Hybrid parsing pipeline — findings

Run of 3 July 2026. All numbers reproduce from `code/router.py` → `code/evaluate.py` over the corpus in `data/`; raw usage in `parse_agent_log.json`; per-document detail in `evaluation.json`. Cost figures are **estimates** (method B — subagents, not API calls); accuracy figures are exact against the answer key.

## Headline results

| Measure | Value |
|---|---|
| Documents on the deterministic path | **184 of 240 (76.7%)** — pre-registered ≈75%; the 1.7pp gap is the FBL1N deviation below |
| LLM-path field accuracy (56 docs, 34,470 fields) | 99.962% (13 wrong fields, all one root cause) |
| Deterministic-path field accuracy (184 docs, 137,726 fields) | 99.952% including the planted silent error; **100.000% excluding it** (66 wrong fields, all from the one S-class document) |
| Hybrid cost, central estimate | ~$8.51 (band $5.32–$26.60), including the one-time parser-generation cost |
| All-LLM counterfactual, central estimate | ~$21.81 (band $13.63–$68.15) |
| Estimated saving | ~61% of the counterfactual — on a 240-document stream; the share grows with stream length because the marginal deterministic document costs nothing |

Steady state from month 3: every routine document parses deterministically, in ~1–10 ms locally, at zero marginal cost.

## The designed-outcome table, scored

| Class | Designed | Actual |
|---|---|---|
| R (218) | LLM during discovery, deterministic after activation | 40 discovery + 178 deterministic — exactly as designed, zero field errors |
| V (6) | Stays on the LLM path (below learning threshold) | 6 LLM fallbacks — as designed |
| F (15) | Break the parser → validation fails → LLM fallback | **10 as designed; 5 deviated** (see below) |
| S (1) | Parses cleanly, passes all checks, silently wrong | Exactly as designed: deterministic path, 66 silently wrong fields, revealed only by the answer key |

**The FBL1N deviation — the system beat our trap.** The five FBL1N "mid-table currency change" documents were designed to break the generated parser. They didn't: the overseer's FBL1N parser treats currency as data and handles per-currency totals generally, so all five parsed *correctly* on the deterministic path. The pre-registration stayed frozen and the deviation is reported, not patched. Together with the S-mechanism history (below), this means two of our planted failures were defeated by the quality of the generated code, and pre-registration is what makes that checkable rather than a convenient story.

**The silent error took three design iterations**: (1) an FBL3N amount/tax column swap — killed at design review because FBL3N's label-matched, S/H-split totals make any amount swap arithmetically loud; (2) an ME2M layout swap (columns + headers move together) — killed empirically when the generated ME2M parser turned out to resolve columns by header label per page and would have parsed it *correctly*; (3) the shipped version: headers stay canonical, the *values* of Nettopreis and Noch offen Wert are written into each other's columns — upstream corruption, "the document lies." No text-only reader can catch it; totals reconcile; only reconciliation against an independent truth sees it. A line-level price × quantity cross-check catches it on parsed values (0,00 × 2.000 ≠ 7.480,00) — the production recommendation.

## LLM-path findings

- **Discovery wave (40 docs, precise brief): 26,509 fields, zero errors.** Agents self-verified by reconciling parsed line items against rendered totals.
- **Fallback wave (16 docs, compressed brief): 13 field errors, one root cause** — the fallback prompts dropped the discovery prompts' "the *number* after Einkaufsorganisation:/Verkaufsorganisation:" qualifier, and agents captured the whole line (`'1000   Jalavakoski Konepaja Oy'`). These pass schema and master-data checks; production would have shipped them; they stand in the record. The lesson is structural: **deterministic accuracy is a property of code; LLM accuracy is a property of the brief. Version your briefs.**
- **Retry (3 docs):** one batch emitted integer-typed identifier fields, caught by schema validation → pipeline-mandated retry, costed separately (53,880 tokens). The safety net working as specified.
- Incidental finds: one agent initially mis-sliced wide right-aligned amounts by header position (dropping a leading digit) before switching to token-pattern parsing — exactly the failure mode the regression gate exists to catch; another handled a vendor subtotal printed after a page break.

## Overseer and gate

Five parsers generated (one per type) from 8 documents + 8 accepted LLM parses each; the answer key was never readable by any parser or parse agent. All five passed the regression gate (reproduce the LLM path's accepted output exactly) on first submission; a code review confirmed stdlib-only, no I/O, no non-determinism, fail-loud posture (strict column-set checks, cell-count checks, totals-pattern checks). One-time generation cost: 729,630 measured tokens (~$3.50 central estimate) — recouped roughly twice over within this 240-document stream alone.

## Cost accounting method (labels)

Method B throughout: Claude Code subagents. `subagent_tokens` are measured, undifferentiated session totals (input+output+overhead), so they are an **upper bound** on what a purpose-built extractor would use. Costs = published Sonnet-tier list prices ($3/$15 per MTok, checked 3 Jul 2026) applied as a **band** (all-input floor to all-output ceiling) with a central estimate at a stated 85/15 split. The counterfactual models unparsed documents at their type's mean measured tokens per document. Latency figures for LLM documents are harness-inclusive wall clock; deterministic parse times are measured locally.

## Process notes (honestly logged)

- Two parse agents disclosed over-scoped Grep calls (document text only; the answer key directory was never touched).
- Parallel agents share a temporary working folder: one agent executed a sibling batch's leftover script (outputs verified unaffected). Later waves used uniquely-prefixed scratch names.
- The corpus was corrected twice before any parsing ran (truncation ground-truth principle; a false-alarm VA05 totals diagnosis honestly reversed).

