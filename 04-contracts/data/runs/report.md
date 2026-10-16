# Contract review — findings report

Case 4 of the Hapax case studies. Run 3–4 July 2026. Written from `evaluation.json`, `stream_events.json`, `holdout_coverage.json`, `extract_agent_log.json`, and a hand adjudication of every disagreement in `evaluation_worksheet.md`. *The corpus is real (CUAD, CC BY 4.0, © The Atticus Project); the answer key is the dataset's own attorney-reviewed annotations, held out from the pipeline throughout and read exactly once, by `evaluate.py`, after the stream closed.*

## The one-line result

Fifty real contracts were read by the model while an overseer induced twelve deterministic matchers from its accepted answers; the activation gate killed one before use, shadow checks killed three more in flight — each for a different real failure mode — and the eight survivors answered 176 categories on a 100-contract holdout at 98.3% presence accuracy for zero marginal cost; marked against 776 attorney-annotated comparisons, our pre-registered predictions went 4 for 12, and the disagreement adjudication found the published expert key itself wrong or internally inconsistent in roughly a fifth of the contested rows.

## Accounting

| Quantity | Value |
|---|---|
| Stream (read by the model, 8 sequential batches) | 50 contracts, 52 reads incl. 2 span-verbatim retries (cap 60) |
| Holdout (never read by the model) | 100 contracts, matchers only |
| Category-level comparisons marked against the key | 776 (600 stream + 176 holdout) |
| Measured subagent tokens (method B, estimates) | 3,412,095 total = 1,696,432 extraction + 1,651,185 overseer + 64,478 calibration spike; batch 7's pre-drop segment additionally unmeasured (connection loss; est. +100–200k) |
| Run cost band (introductory pricing, central) | ≈ $10.9 (list ≈ $16.4); bands in `evaluation.json` |
| Counterfactual: model-reading the 100-contract holdout | ≈ $10.4 central at the stream's mean 32.6k tokens/read — the matcher path answered its 176 holdout categories for $0 |

## Matcher lifecycle — the honest arc

Twelve commissions, each reviewed by hand before its gate:

- **11 gate-PASSed** (Parties on its second attempt — see the recommission below); 1 **gate-FAILED terminally** (IP Ownership Assignment — replay false positive on an accepted negative; frozen, never recommissioned).
- **1 protocol-failure recommission** (Parties: `import os` in a `__main__` scaffold, caught by the gate's source-level allowlist; fix limited to deleting the block, no logic change).
- **3 demoted in flight by shadow regression**, each a distinct failure mode:
  1. **Document Name** (batch 3): a bare Schedule A issued under a master agreement — the matcher named the schedule, the shadow read named the master. *The key names both* — the demotion trigger was a document the attorneys themselves recorded with two titles.
  2. **Parties** (batch 5): preamble scan overran into a BACKGROUND section and captured two defined terms as bogus parties — an unambiguous matcher defect, caught live.
  3. **Governing Law** (batch 6): a Texas/Singapore/Belgium multi-law contract — the matcher's closed US-state whitelist made the foreign clauses invisible, converting a genuine conflict into confident "Texas" against the shadow's UNDETERMINED.

Every demotion is permanent and the matcher's pre-demotion answers stand in the scored stream (trust-then-verify: past damage visible and counted, future damage stopped).

**What the shadow system did and did not catch.** 33 shadow comparisons ran; 30 agreed, 3 triggered the demotions above. The adjudication then found **four further matcher errors on stream contracts the shadows never sampled**: a four-party chained preamble collapsed to two parties (Armstrong, batch 3); a Document Name overcapture with trailing text (Deltathree, batch 3); an Agreement Date answered from a blank joinder form at the back of the document while the real date sat in an unanchored preamble phrasing (GWG, batch 8); and a License Grant anchor firing on third-party-licensing text out of scope (IGENE, batch 3). One-shadow-per-category-per-batch is a spot check, not a proof — stated plainly here and in the writeup.

## Predicted vs actual — 4 of 12, wrong in both directions

| Category | Predicted | Actual | What happened |
|---|---|---|---|
| Governing Law | A | **R** | demoted (foreign-jurisdiction blindness) |
| Document Name | A | **R** | demoted (schedule-vs-master ambiguity) |
| Agreement Date | A | **P** | active, holdout coverage only 21% |
| Parties | P | **R** | demoted (scan overrun) |
| Anti-Assignment | P | **P** ✓ | coverage 52%, holdout accuracy 100% |
| License Grant | P | **P** ✓ | coverage 39%, holdout accuracy 97.4% |
| Insurance | P | **P** ✓ | coverage 19%, holdout accuracy 100% |
| Expiration Date | R | **P** | activated — then went 2-for-4 on holdout (see below) |
| Cap on Liability | R | **P** | coverage 30%, holdout accuracy 100% |
| Audit Rights | R | **P** | activated — **0% holdout coverage** (answered nothing) |
| IP Ownership Assignment | R | **R** ✓ | the gate itself confirmed the floor |
| Non-Compete | R | **P** | coverage 11%, holdout accuracy 90.9% |

The misses split into two families, and both are the finding:

1. **We over-promised the formulaic end.** All three predicted-A categories died. Boilerplate *language* is real, but full retirement of a category needs more than an anchor phrase — document-identity ambiguity, unusual preambles, and foreign phrasings each killed a matcher that was perfect on its induction set. Nothing earned A-actual (the pre-registered two-sided-waiver never came into play: every active matcher fell short on coverage, not on the trust label).
2. **We under-estimated how much of the bespoke end has a formulaic *core*.** Four predicted-R categories grew gate-passing matchers that answer their formulaic minority accurately and refuse the rest. The floor is real, but it is a floor per-instance, not per-category.

Two rows deserve their own sentences. **Audit Rights** activated on ten narrow induction patterns and then matched *nothing* in 100 held-out contracts — a matcher that passed the exam it wrote for itself and generalised to zero; technically P-actual, practically R. **Expiration Date** — the row the pre-registration singled out as the "silently wrong computed dates" risk — activated, covered 4% of the holdout, and got two of those four answers wrong (a mis-computed date and a false presence). The one category whose failure mode is a wrong deterministic answer is the one that shipped wrong deterministic answers. The prediction was scored a miss by the pinned rule; its reasoning was vindicated.

## Accuracy as marked (against the external key)

| Path / split | Presence | Answers (key-answerable rows) |
|---|---|---|
| Matcher, stream (89 answers) | 88/89 (98.9%) | 37/44 (84.1% — dragged by the pre-demotion Parties/Document Name errors, which stand) |
| Model, stream (511 answers) | 476/511 (93.2%) | 141/174 (81.0%) |
| Matcher, holdout (176 answers) | 173/176 (98.3%) | 22/23 (95.7%) |

12 span-only key rows (spans recorded, answer blank) scored presence-only per the pre-registered rule. **Where an active matcher chose to answer, it was near-perfect on presence everywhere** (holdout violations: zero; the three holdout presence errors are the Expiration Date false presence and one false positive each from License Grant and Non-Compete). The matcher-vs-model accuracy comparison carries a selection effect, stated plainly: matchers answer only the formulaic instances they trust and NoMatch the hard ones, so their high accuracy is over an easier subset — the honest claim is "equivalent-or-better *on the instances they accept*", not "better than the model".

## The adjudication — what the 80 disagreements actually were

Every mismatch was adjudicated by hand (all 80 — the pre-registered floor was all extraction/A-P rows plus a seeded 20 R-sample; the full set was small enough to read). Verbatim rows and contexts in `evaluation_worksheet.md`. By family:

| Family | Rows (approx.) | Reading |
|---|---|---|
| **Key errors or arguable key errors** | **~15 (19%)** | Typos in party names (`CORAL GOLD RESOURCED`), a dd/mm-formatted date (`31/01/2025`) violating CUAD's own convention, an Agreement Date answer contradicting the key's own quoted span (GluMobile: `11/18/05` vs "November 11, 2005"), a parent/subsidiary conflation (GPAQ's Village Media Company), a collective mislabel + typo (SUNTRON's "Lenders"), an explicit "right to audit MP3.com's records" marked absent (Tickets.com), an IP-vesting clause quoting the definition almost verbatim marked absent (Senmiao), damage-type waivers counted as Cap on Liability in one contract but not another (Snap vs iDreamSky), likeness/trademark licences counted in one contract but not its twins (EcoScience vs PROLONG/MERCATA), and computed dates that contradict the clause's own conditions (Blackstone) |
| **Genuinely ambiguous** | **~28 (35%)** | The Non-Compete/Exclusivity boundary (6 rows — CUAD's own calls straddle it); open-ended terms rendered three different ways by the key itself (perpetual / absent / a date); incorporation-by-reference documents; data-ownership vs IP-assignment; who counts as a party (limited-purpose signatories, referenced parents); an off-by-one-day term computation; a redacted-date notation difference |
| **Equivalent readings defeated by the pinned comparator** | **~19 (24%)** | Almost all Parties rows: the key packs collective parentheticals ("each a Party…") and role definitions into answer strings that token-set comparison cannot survive, plus key respellings of entities the filed text spells otherwise. The comparator was pre-registered and stands; these rows are reported as what they are |
| **Pipeline (model) genuinely wrong** | **~8 (10%)** | Mostly over-calls on flagged borderlines: disclosure documents describing another agreement's covenants read as the covenants themselves (Soupman ×2), a rights-disclaimer's carve-out read as a licence, a commencement date used as an agreement date, a pay-when-paid clause read as a liability cap |
| **Pipeline (matcher) genuinely wrong** | **~10 (13%)** | The 4 uncaught stream errors + the demotion-batch answers that stand (Regan Parties, West Governing Law, Cardlytics Document Name — the last genuinely ambiguous) + 4 holdout errors (Expiration Date ×2, License Grant ×1, Non-Compete ×1) |

Zero adjudicate-first rows (no case where both paths agreed with each other against the key on a shadowed overlap). The key is never edited; scores above are as-marked. CUAD's annotators did expert work at a scale we benefit from freely. A ~19% key-error share **among disagreements** (roughly 15 rows against 776 marked comparisons, ≈ 2% of everything marked) is the ordinary margin of expert annotation, and the reason a pipeline should be marked rather than trusted.

**One instructive lineage**: the Non-Compete matcher's induction set included the model's Theravance call (an employment outside-activities clause read as Non-Compete) — a call the attorneys dispute. The overseer faithfully learned it. Overseers learn from the model's accepted answers, not from truth; when the model and the key diverge, the matcher inherits the divergence. That is the honest cost of key-blind induction, and the reason the key must stay out of the loop: an overseer that peeked would launder the key into "deterministic" code and destroy the marking.

## Process and audit notes

- All 8 extraction batches and 12 overseer runs returned complete file-audit lists; no agent touched `data/answer_key/` or `master_clauses.csv` (rule-10 whitelist enforced by the validator; every transcript's audit list checked by hand).
- Batch 2: two files rejected by the verbatim-span validator (a page-number line stitched over; an OCR artefact silently corrected) — both re-quoted warts-and-all on retry. The evidence discipline works.
- Batch 7: API connection dropped mid-batch after 1/7 outputs; resumed with only-what-is-on-disk-counts instructions; the pre-drop token usage is lost and recorded as an estimate range in the agent log.
- CUAD contains near-duplicate filings: the same Armstrong Flooring IP agreement entered the stream twice under different filenames (different byte content, so the checksum dedup rule passed correctly). Both were marked; their rows agree.
- The stream ran key-blind end to end: no mid-stream accuracy checks, agent instructions frozen at v1 (one widening of the Insurance definition after a spot-read during corpus preparation, recorded before any batch ran).
- In-flight fixes during the stream: shadow-eligibility rule tightened before any batch-2 read; router demotion-window check corrected to match the pinned accept-time semantics; console-encoding guards.

## Deviations — frozen, not patched

1. Predicted-outcome table: 8/12 misses, published as scored.
2. IP Ownership Assignment: gate failure (prediction confirmed by mechanism, not by fiat).
3. Three shadow demotions; pre-demotion answers stand in the scored stream.
4. Four stream matcher errors the shadow sampling missed — the sampling density is a stated limitation.
5. Audit Rights: activated with zero holdout generalisation.
6. Expiration Date: 2/4 holdout answers wrong — the pre-registered risk, realised.
7. Batch-7 unmeasured token segment.
8. Read cap used 52/60; the 8 unspent reads are headroom, not a saving claim.

## Attribution

Corpus and annotations: **CUAD v1** — Hendrycks, Burns, Chen & Ball, *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review*, NeurIPS 2021 Datasets and Benchmarks (arXiv:2103.06268). Dataset © The Atticus Project, CC BY 4.0. This project adapts `master_clauses.csv` into per-contract key files under the same licence. Nothing in this report is legal advice; the pipeline processes documents, it does not practise law.
