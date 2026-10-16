# What fifty real contracts taught a pattern matcher, and what they didn't

*Every contract here is real, filed with the SEC and annotated by law students and attorneys under The Atticus Project, released under CC BY 4.0. The answer key is theirs, not ours. It stayed out of the pipeline throughout and was read exactly once, after our predictions were already committed to paper.*

## The problem

A legal-operations or due-diligence team facing a stack of contracts asks the same handful of questions of nearly all of them: who signed, when, whose courts, can it be assigned, is liability capped, is competition restricted. Answering these well is the ordinary, expensive work of contract review, and most of it repeats from one contract to the next.

We tested twelve such questions across fifty real commercial contracts. A model read each one and answered every question not yet taken over by a matcher; an overseer watched which questions kept getting answered off the same handful of phrasings and tried to write ordinary code to take over. What is new here is that none of it is invented. The corpus is CUAD, 510 real contracts from SEC filings, annotated under The Atticus Project. We selected 50 for the model to read and 100 more it never saw, held out for the matchers alone, and marked everything against CUAD's own attorney-reviewed answers, pre-registering our predictions for all 12 categories before running anything.

## What happened, in numbers

| Measure | Result |
|---|---|
| Corpus | 510 real CUAD contracts; 50 read by the model, 100 held out (matchers only) |
| Categories tested | 12, spanning near-universal boilerplate to bespoke negotiated language |
| Predictions vs actual | 4 of 12 correct, pre-registered before the run, misses in both directions |
| Matchers reaching the holdout | 8 of 12 (1 killed at the gate, 3 demoted mid-stream) |
| Holdout presence accuracy, matcher-only (176 answers) | 173/176, 98.3%, at zero marginal cost |
| Comparisons marked against the key | 776 (600 stream, 176 holdout) |
| Run cost, introductory pricing (central estimate) | ≈ $10.9 (list ≈ $16.4) |
| Counterfactual (the model reading the 100-contract holdout) | ≈ $10.4 central; the matchers answered the same 176 categories for nothing |

## How it works

A Claude Sonnet subagent reads each contract once and answers all 12 questions against one schema (presence, the supporting text, and, for 5 categories, a normalised answer such as a date or jurisdiction). An overseer watches the model's accepted answers category by category and, once one has enough consistent examples, writes a deterministic matcher, ordinary pattern-matching code with no model at run time. An activation gate checks that the matcher reproduces the model's own accepted answers before it goes live; afterwards, shadow comparisons run alongside the stream, one per category per batch (33 in all across 23 contracts, a spot check, not a proof), and any disagreement demotes the matcher for good. This is the same mechanism as the ERP cleanup and invoice case studies. There the system learned report formats and suppliers; here the unit of learning is the category of clause itself.

## The twelve matchers

Twelve matchers were written. Eight survived to the holdout and answered 176 categories across 100 unseen contracts, 173 correctly, 98.3%, at zero marginal cost. A matcher answers only the instances it trusts and refers the rest back to the model, so that figure is measured over an easier subset by construction.

One never reached the holdout. **IP Ownership Assignment**, predicted to stay with the model because IP transfers have no fixed phrasing, produced a replay false positive at its activation gate. The gate confirmed the prediction.

Three more passed the gate, went live, and were demoted by shadow checks, each for a different reason. **Document Name** fell on a bare schedule issued under a master agreement, where the key itself names both titles. **Parties** fell on a preamble scan that overran into a background section and captured 2 defined terms as signatories. **Governing Law** fell on a contract naming Texas, Singapore and Belgium law together; its whitelist only knew US states.

The shadow system is a spot check, not a proof. Of 33 comparisons during the stream, 30 agreed and 3 produced the demotions above; the later hand adjudication turned up four further matcher errors on contracts the shadows had not sampled. Among the survivors, the audit-rights matcher activated on ten narrow patterns and matched nothing across the holdout because its nine induction contracts phrased the clause differently from all 38 that carry one. The expiration-date matcher, whose answer is computed, not quoted, covered 4% of the holdout and got 2 of those 4 answers wrong.

## The predictions, and what the key said back

| Category | Predicted | Actual | What happened |
|---|---|---|---|
| Governing Law | A | R | demoted – foreign-jurisdiction blindness |
| Document Name | A | R | demoted – schedule-vs-master ambiguity |
| Agreement Date | A | P | active, 21% holdout coverage |
| Parties | P | R | demoted – preamble scan overran |
| Anti-Assignment | P | P ✓ | 52% coverage, 100% holdout accuracy |
| License Grant | P | P ✓ | 39% coverage, 97.4% holdout accuracy |
| Insurance | P | P ✓ | 19% coverage, 100% holdout accuracy |
| Expiration Date | R | P | activated, wrong on 2 of 4 holdout answers |
| Cap on Liability | R | P | 30% coverage, 100% holdout accuracy |
| Audit Rights | R | P | activated, 0% holdout coverage |
| IP Ownership Assignment | R | R ✓ | the gate confirmed the floor |
| Non-Compete | R | P | 11% coverage, 90.9% holdout accuracy |

Four of the twelve predictions were right, and the misses ran in both directions. None of the three categories called fully automatable got there, each for a reason unrelated to volume of examples: two were demoted, and the third answered only 21% of the holdout. Four we expected to stay with the model grew matchers that handle a narrow, formulaic minority and refer the rest back. The floor we predicted is real; it sits per instance, not per category.

Marked against the key, the matchers answered 88 of 89 stream questions correctly on presence (98.9%) and 37 of 44 on the underlying answer where one was called for (84.1%); the model answered 476 of 511 on presence (93.2%) and 141 of 174 on answer (81.0%); on the holdout, where only matchers operate, presence accuracy was 173 of 176 (98.3%) and answer accuracy 22 of 23 (95.7%). These figures are not directly comparable. A matcher answers only the instances it trusts and refers the rest back to the model, so its accuracy is measured over an easier subset by construction. The matchers are equivalent-or-better on the instances they choose to answer. They are not better than the model in general.

## The adjudication

All 80 disagreements between the pipeline and the key were read by hand, not sampled. About 15 of them, roughly a fifth, turned out to be the key itself in error or arguably so: a misspelled party name, a date recorded in the wrong format for CUAD's own convention, an agreement date contradicting the very span the key quotes as its own evidence. CUAD's annotators did expert legal work, valued by the dataset's own authors at over two million dollars; set against everything marked, those rows amount to roughly 2%. An error margin that size, surfacing in the contested rows, is what expert annotation looks like.

One disagreement needs naming precisely because it is not a key error. The Non-Compete matcher's induction set included a case where the model read an employment contract's outside-activities clause as a non-compete (Theravance), a call the key disputes. The overseer learned it faithfully anyway, because an overseer learns from what the model accepted, not from what is true. That is why the answer key has to stay out of the induction loop. An overseer that could see it would launder the key into "deterministic" code, and the marking that makes this report honest would mean nothing.

## What it cost

All figures here are labelled estimates, published Sonnet prices against measured subagent tokens, banded not exact. The run's central estimate is about $10.9 at introductory pricing (about $16.4 at list). This is not a crossover story like our invoice case study, where an eventual cost curve favours automation. The saving here is the residual. Reading the 100-contract holdout with the model would cost an estimated $10.4 at the stream's own mean cost per read, and the matchers answered the same 176 categories for nothing. That zero-marginal-cost coverage, on exactly the categories judged safe to automate, is the figure that matters.

## What transfers and what does not

What generalises is the method, not the twelve answers it produced this time. That a matcher can pass its own exam and still fail completely on new documents (Audit Rights) is a finding about deterministic code in general, not about this corpus. So is the fact that a computed answer is the one place a text-pattern matcher is most dangerous to trust (Expiration Date), and that "bespoke" and "boilerplate" are properties of an instance as often as of a category. What does not generalise is the count itself (which 12 questions, what share automates, how these numbers land) because that depends on the documents in front of you, not on the method reading them. This closes what the ERP and invoice case studies opened. Formats, then suppliers, then the categories of language, learned the same way each time, from what the model accepted rather than from anything we knew in advance.

## Attribution

Corpus and annotations: **CUAD v1** – Hendrycks, Burns, Chen & Ball, *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review*, NeurIPS 2021 Datasets and Benchmarks (arXiv:2103.06268). Dataset © The Atticus Project, CC BY 4.0. This project adapts `master_clauses.csv` into per-contract key files under the same licence. Nothing in this report is legal advice.
