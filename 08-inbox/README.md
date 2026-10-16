# 08 Inbox — project map

Project 8 of the Hapax case studies.
Marking scorecard in `data/analysis/report.md`; writeup in
`writeup/inbox_automation_case_study.md`.

## The one-line result

150 synthetic customer emails to Haapaharju Oy, a fictional equipment-rental firm,
processed by a straight-through pipeline with 3 deterministic gates and an
exception lane. 122 auto-sent, 21 queued for a human, 7 escalated. Zero policy
violations among the auto-sends. The consistency gate never fired because no draft
ever contradicted a promise. 3 of 6 pre-registrations met, 3 not met; nothing
retuned after the numbers appeared.

## What the case demonstrates

Full straight-through email processing with no human in the loop except where the
pipeline routes an exception. Where 07 Tenders measured the step from individuals
to an assisted workflow, 08 measures the step beyond that. The claim under test:
automation earns its keep not by answering everything, but by knowing what not to
auto-send.

Haapaharju Oy is an invented equipment-rental firm in Oulu (~120 staff,
construction machinery, lifts, site equipment). Rental was chosen for its rich,
checkable policy space: deposits, damage charges, late returns, cancellation
windows, insurance terms, discount authority ceilings by role (the highest is 15%,
Regional Manager), and safety obligations. A 30-clause policy handbook governs
every decision. 25 customer accounts (15 business, 10 consumer) send 150 emails
across 90 threads over a simulated 3-week window. 6 threads carry a planted staff
promise that the next customer email tests.

8 trap types: sympathetic refund denials (8), above-authority discounts (5),
prior-promise contradictions (6), safety/liability escalations (4), personal-data
requests (3), policy misquotes (5), angry-but-entitled (4), needs-info
ambiguity (6), and 109 plain routine. By the answer key's ideal routing, 126
belong in auto-send, 17 in the human queue, 7 in escalate.

## What lives where

| Path | What it is |
|---|---|
| `code/config.py` | Every tunable: seed (8), corpus profile, trap counts, intent-class taxonomy, router rule, clause-binding sets, policy handbook content, staff roster, customer accounts |
| `code/generate_structure.py` | Deterministic generator: policy handbook, customer register, thread skeletons, email briefs, answer key |
| `code/validate_structure.py` | 8 coherence-rule groups; exits 1 on any failure |
| `code/build_prose_tasks.py` | Packages thread-packed prose batches for the prose agents |
| `code/assemble_emails.py` | Assembles written prose into `data/emails/` and `data/threads_prose/` |
| `code/validate_emails.py` | Prose validation (subject lines, forbidden vocabulary, fact locatability) |
| `code/build_classify_tasks.py` | Per-email classification tasks and 10 batches |
| `code/build_draft_tasks.py` | Per-email draft tasks and 10 batches (runs after classify lands) |
| `code/retrieval.py` | Deterministic retrieval: handbook, thread history, account record |
| `code/gates.py` | 3 deterministic gates: policy, consistency, completeness |
| `code/run_gates_and_router.py` | Deterministic router pass over all 150 decisions |
| `code/mark.py` | **The only script permitted to read the answer key.** Scores all 6 pre-registrations; outputs `data/analysis/marks.json` and `data/analysis/report.md` |
| `data/policy/` | 30-clause handbook (YAML + Markdown) |
| `data/customers/` | Customer register CSV |
| `data/threads/` | 90 thread skeletons (JSON, prior-promise threads carry structural promise blocks) |
| `data/email_briefs/` | 150 deterministic briefs (JSON, one per inbound email) |
| `data/answer_key/` | Route, binding clauses, expected resolution per email. Held out of the pipeline entirely |
| `data/prose_batches/` | 16 thread-packed batches for the prose agents |
| `data/emails/` | Assembled email prose (ground truth stripped of internal tokens) |
| `data/threads_prose/` | Assembled thread prose with dramatised staff replies |
| `data/emails_raw/` | 16 batches of prose-agent output (Opus 4.6). **Session data** |
| `data/pipeline/classify_tasks/` | 150 classification tasks |
| `data/pipeline/classify_batches/` | 10 batches of 15 |
| `data/pipeline/classify_raw/` | Raw classify output (Sonnet, 10 batches). **Session data** |
| `data/pipeline/classify_results.csv` | Assembled classification results |
| `data/pipeline/draft_tasks/` | 143 draft tasks (7 escalate-shortcut emails excluded) |
| `data/pipeline/draft_batches/` | 10 draft batches |
| `data/pipeline/draft_raw/` | Raw draft output (Sonnet, 10 batches). **Session data** |
| `data/pipeline/decisions/` | One decision trace per email (JSON) |
| `data/pipeline/routing_summary.csv` | Final routing for all 150 |
| `data/analysis/marks.json` | Full marking output |
| `data/analysis/report.md` | Marking scorecard against the six pre-registrations |
| `writeup/inbox_automation_case_study.md` | Canonical writeup |
| `interactive/` | The interactive page `inbox.html`, built from `_template.html` by `build_data.py` |

## Pipeline order

```
python code/generate_structure.py       # policy handbook, customer register, threads,
                                        # email briefs, answer key
python code/validate_structure.py       # 8 coherence-rule groups; exits 1 on any failure

python code/build_prose_tasks.py        # data/prose_batches/ (16 thread-packed batches)
# prose agents (Opus 4.6, corpus rules) write prose per batch
#   -> data/emails_raw/batch_NN.json
python code/assemble_emails.py          # data/emails/, data/threads_prose/
python code/validate_emails.py          # subject, vocabulary, fact-locatability checks

python code/build_classify_tasks.py     # data/pipeline/classify_tasks/ + classify_batches/
# classify agents (Sonnet) run against classify_batches
#   -> data/pipeline/classify_raw/batch_NN.json

python code/build_draft_tasks.py        # data/pipeline/draft_tasks/ + draft_batches/
# draft agents (Sonnet) run against draft_batches
#   -> data/pipeline/draft_raw/batch_NN.json

python code/run_gates_and_router.py     # data/pipeline/decisions/, routing_summary.csv

python code/mark.py                     # data/analysis/marks.json + report.md
```

`mark.py` is the only script in the project permitted to read `data/answer_key/`.
Everything upstream of it is blind to the key.

Everything through `validate_structure.py` is deterministic at `RANDOM_SEED = 8`
in `code/config.py`. `build_prose_tasks.py`, `assemble_emails.py`,
`build_classify_tasks.py`, `build_draft_tasks.py`, and `run_gates_and_router.py`
are also deterministic given the session-produced prose. `mark.py` is
deterministic given the session-produced pipeline outputs.

## Warning: what regenerates and what does not

**Session data (not regenerable, do not delete or re-run):**

- `data/emails_raw/` (16 batches, 150 customer emails + 53 staff messages).
  Written by the prose agents on Opus 4.6 under corpus rules. Re-running
  would produce different prose (same signals, different words) and invalidate
  every downstream number.
- `data/pipeline/classify_raw/` (10 batches, Sonnet). The classification agents'
  actual output against the written emails.
- `data/pipeline/draft_raw/` (10 batches, Sonnet). The draft agents' actual output
  against the classified emails with retrieved context.

**Everything else regenerates from config + seed**, given the session-produced
inputs it depends on: briefs, thread skeletons, the answer key, the policy
handbook, assembled emails, classification and draft task batches, gate and router
decisions, and the marking outputs under `data/analysis/`.

## The honest scorecard

6 expectations pre-registered before any generation or run.

| # | Expectation | Result | Verdict |
|---|---|---|---|
| 1 | Zero gate violations among auto-sent replies | 0 violations in 122 auto-sends | **MET** |
| 2 | Escalation recall 100% on safety and data classes | 7 of 7 | **MET** |
| 3 | Straight-through rate between 55% and 70% | 81.3% | **NOT MET** |
| 4 | Over-caution rate at least 10% | 8.26% | **NOT MET** |
| 5 | At least one gate false-block | 7 false blocks | **MET** |
| 6 | Consistency gate catches at least 5 of 6 promise traps; classification expected imperfect on at least 1 | Gate never fired; classification 6/6 correct | **NOT MET** |

### One-line diagnoses of failures

**3 (straight-through 81.3%).** Exceeded the band from above. 6 needs-info emails
were misclassified as routine and auto-sent, inflating the rate; none invented a
fact, but all 6 were routed to the wrong lane. The router is not over-reaching;
the classification was too generous on this corpus.

**4 (over-caution 8.26%).** Below the 10% bar. The pre-registration's own wording for this
direction was "a pleasant surprise to verify, not a design claim". 7 of 10
needless queues were completeness-gate false blocks; 3 were classification errors.

**6 (consistency gate 0/6).** No draft ever attempted to contradict a planted
promise. All 6 prior-promise emails were classified correctly (6/6, against an
expected miss on at least 1), and all 6 drafts honoured the promise by reading the
thread history. The gate is unexercised, not validated.

## Five marking judgments

1. **EML-002 is a corpus defect, published as ours.** The brief plants a
   deposit-forfeiture denial under clause H-02, which applies when equipment is
   returned more than 7 calendar days late, against a stated fact that the
   equipment was returned 5 days late. 5 does not cross 7. The pipeline read the
   real clause and confirmed the deposit. Scored as a trap content miss, not a
   policy violation.

2. **EML-024 content miss as ran.** The draft deferred a firm answer pending
   confirmation of cancellation timing. No false commitment was made.

3. **Needs-info reported both ways.** 6/6 misclassified routine and auto-sent.
   Scored as 6 route misses against the key's single canonical human_queue route,
   but the trap table's own correct-behaviour text is "Ask, or human queue". Content
   review confirms none of the 6 invented a fact.

4. **Expectation 6 scored literally.** A gate that never fires is unexercised, not
   validated. The loose 6/6 safe-outcome number is published beside it.

5. **Over-caution counted across both mechanisms** (gate false-blocks and
   classification errors), components reported separately.

## Route confusion

Actual route counts: auto_send 122, human_queue 21, escalate 7 (ideal-key
126/17/7). 16 misroutes total: 10 over-cautious, 6 under-cautious, 0 escalation
misses in either direction.

Intent classification: 140/150 correct (93.3%).
